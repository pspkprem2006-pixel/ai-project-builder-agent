from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.generation_job import GenerationJob
from app.models.project import Project
from app.models.user import User
from app.schemas.project import (
    AISuggestion,
    GenerateResponse,
    GenerationJobOut,
    ProjectCreate,
    ProjectListItem,
    ProjectListOut,
    ProjectOut,
    ProjectStatistics,
    ProjectUpdate,
    RegenerateSectionRequest,
    TemplatesOut,
)
from app.services.ai.agents import AGENT_KEYS
from app.services.blueprint_compat import BlueprintIncompatibleError, normalize_blueprint
from app.services.generation_jobs import cancel_job, create_job
from app.services.memory import get_memory_store
from app.services.orchestrator import (
    duplicate_project,
    regenerate_section_for_project,
)

router = APIRouter(prefix="/projects", tags=["Projects"])

REGENERATABLE_SECTIONS = set(AGENT_KEYS) | {"deployment"}

BUILT_IN_TEMPLATES: list[ProjectCreate] = [
    ProjectCreate(
        name="Hospital Management System",
        description="Complete hospital operations platform: patient registration, appointments, medical records, prescriptions, departments, staff management and billing.",
        category="Healthcare",
        target_users="Hospital admins, doctors, reception staff, patients",
        features=["Patient registration", "Appointment scheduling", "Medical records", "Prescriptions", "Billing and payments", "Doctor schedules", "Reports"],
        preferred_frontend="Next.js",
        preferred_backend="FastAPI",
        database="PostgreSQL",
        auth_method="JWT",
        deployment_platform="Docker",
        language="TypeScript",
    ),
    ProjectCreate(
        name="Food Delivery App",
        description="End-to-end food delivery platform connecting customers, restaurants and couriers with live order tracking.",
        category="Food & Delivery",
        target_users="Customers, restaurant owners, delivery couriers, admins",
        features=["Restaurant discovery", "Menu browsing", "Cart and checkout", "Order tracking", "Courier dispatch", "Reviews", "Payments"],
        preferred_frontend="React",
        preferred_backend="Node.js",
        database="PostgreSQL",
        auth_method="JWT",
        deployment_platform="Railway",
        language="TypeScript",
    ),
    ProjectCreate(
        name="AI Resume Analyzer",
        description="Upload a resume and receive AI-powered analysis: skill extraction, job match scoring, and improvement suggestions.",
        category="AI & Analytics",
        target_users="Job seekers, recruiters, career coaches",
        features=["Resume upload", "Skill extraction", "Job match scoring", "ATS compatibility report", "Improvement suggestions", "History and re-analysis"],
        preferred_frontend="Next.js",
        preferred_backend="FastAPI",
        database="PostgreSQL",
        auth_method="OAuth",
        deployment_platform="Render",
        language="Python",
    ),
    ProjectCreate(
        name="Inventory Management System",
        description="Track stock across warehouses with suppliers, purchase orders, alerts and reporting.",
        category="Business",
        target_users="Warehouse staff, procurement teams, business owners",
        features=["Product and SKU management", "Stock movements ledger", "Supplier management", "Purchase orders", "Low-stock alerts", "Reports"],
        preferred_frontend="React",
        preferred_backend="FastAPI",
        database="PostgreSQL",
        auth_method="JWT",
        deployment_platform="Docker",
        language="TypeScript",
    ),
    ProjectCreate(
        name="College ERP",
        description="Academic ERP: student records, courses, enrollments, attendance, grades and fee management.",
        category="Education",
        target_users="Students, faculty, administrators, finance team",
        features=["Student records", "Course catalog", "Enrollments", "Attendance tracking", "Grades", "Fee management", "Timetables"],
        preferred_frontend="Next.js",
        preferred_backend="Django",
        database="PostgreSQL",
        auth_method="JWT",
        deployment_platform="AWS",
        language="TypeScript",
    ),
    ProjectCreate(
        name="Chat Application",
        description="Real-time chat with direct and group conversations, read receipts, reactions and file sharing.",
        category="Communication",
        target_users="Consumers, teams",
        features=["Direct messaging", "Group chats", "Read receipts", "Message reactions", "File attachments", "Search", "Notifications"],
        preferred_frontend="React",
        preferred_backend="Node.js",
        database="MongoDB",
        auth_method="Firebase",
        deployment_platform="Railway",
        language="TypeScript",
    ),
]


def _get_owned_project(project_id: int, db: Session, user: User) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get("/templates", response_model=TemplatesOut)
def list_templates():
    return TemplatesOut(templates=BUILT_IN_TEMPLATES)


@router.get("", response_model=ProjectListOut)
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
    q: str = Query("", description="Search by name, description or category"),
    category: str = Query("", description="Filter by category"),
):
    query = db.query(Project).filter(Project.user_id == user.id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Project.name.ilike(like)) | (Project.description.ilike(like)) | (Project.category.ilike(like))
        )
    if category:
        query = query.filter(Project.category == category)
    total = query.count()
    items = (
        query.order_by(Project.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ProjectListOut(
        items=[ProjectListItem.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/statistics", response_model=ProjectStatistics)
def project_statistics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    projects = db.query(Project).filter(Project.user_id == user.id).all()
    by_category: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_stack: dict[str, int] = {}
    last_generated = None
    for project in projects:
        by_category[project.category or "General"] = by_category.get(project.category or "General", 0) + 1
        by_status[project.status] = by_status.get(project.status, 0) + 1
        key = f"{project.preferred_backend} + {project.preferred_frontend}"
        by_stack[key] = by_stack.get(key, 0) + 1
        if project.last_generated_at and (last_generated is None or project.last_generated_at > last_generated):
            last_generated = project.last_generated_at
    return ProjectStatistics(
        total_projects=len(projects),
        completed=by_status.get("complete", 0),
        in_progress=by_status.get("processing", 0),
        drafts=by_status.get("draft", 0) + by_status.get("failed", 0),
        by_category=dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        by_status=by_status,
        by_stack=dict(sorted(by_stack.items(), key=lambda kv: -kv[1])),
        last_generated_at=last_generated,
    )


@router.get("/suggestions", response_model=list[AISuggestion])
def ai_suggestions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    suggestions = get_memory_store().suggest(user.id)
    return [AISuggestion(**s) for s in suggestions]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = Project(user_id=user.id, **payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = _get_owned_project(project_id, db, user)
    blueprint = project.blueprint
    if blueprint is not None:
        try:
            blueprint = normalize_blueprint(blueprint)
        except BlueprintIncompatibleError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    out = ProjectOut.model_validate(project)
    out.blueprint = blueprint
    return out


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _get_owned_project(project_id, db, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = _get_owned_project(project_id, db, user)
    db.query(GenerationJob).filter(GenerationJob.project_id == project_id).delete(
        synchronize_session=False
    )
    db.delete(project)
    db.commit()
    return None


@router.post("/{project_id}/duplicate", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def duplicate(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    name: str | None = Query(None),
):
    project = _get_owned_project(project_id, db, user)
    copy = duplicate_project(db, project, name=name)
    return ProjectOut.model_validate(copy)


@router.post("/{project_id}/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
def generate(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a durable generation job.

    The job is processed by a separate worker process. Duplicate requests
    return the existing active job instead of creating a second pipeline.
    """
    project = _get_owned_project(project_id, db, user)
    job = create_job(db, project.id)
    return GenerateResponse(
        status=job.status,
        detail="Generation job created",
        project_id=project.id,
        job_id=job.id,
    )


@router.get("/{project_id}/jobs", response_model=list[GenerationJobOut])
def list_generation_jobs(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_owned_project(project_id, db, user)
    return (
        db.query(GenerationJob)
        .filter(GenerationJob.project_id == project_id)
        .order_by(GenerationJob.id.desc())
        .all()
    )


@router.get("/{project_id}/jobs/{job_id}", response_model=GenerationJobOut)
def get_generation_job(
    project_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_owned_project(project_id, db, user)
    job = db.get(GenerationJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/{project_id}/jobs/{job_id}/cancel", response_model=GenerationJobOut)
def cancel_generation_job(
    project_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_owned_project(project_id, db, user)
    job = db.get(GenerationJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    cancel_job(db, job)
    db.refresh(job)
    return job


@router.post("/{project_id}/regenerate-section", response_model=ProjectOut)
def regenerate_section(
    project_id: int,
    payload: RegenerateSectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Regenerate only one blueprint section (used by the Blueprint Review agent),
    then re-run validation so the quality report reflects the change."""
    project = _get_owned_project(project_id, db, user)
    if project.blueprint is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no blueprint yet. Generate it first.",
        )
    if payload.section not in REGENERATABLE_SECTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown section '{payload.section}'. Choose from: {', '.join(sorted(REGENERATABLE_SECTIONS))}",
        )
    return ProjectOut.model_validate(regenerate_section_for_project(db, project, payload.section))

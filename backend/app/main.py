import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import actions, auth, codegen, diagrams, export, pm, projects, revisions, workspace
from app.config import get_settings
from app.database import init_db
from app.middleware import BodySizeLimitMiddleware

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Multi-agent AI application that turns a short project idea into a complete, "
        "professional software blueprint: architecture, database, APIs, UI plan, roadmap, "
        "tests, deployment and documentation."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.MAX_REQUEST_BODY_BYTES)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Unexpected errors: log server-side, respond with a generic 500.

    Never echoes the exception (no tracebacks, paths, connection strings or
    secrets). Expected validation errors keep their detailed 422 responses via
    FastAPI's own handlers.
    """
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(projects.router, prefix=settings.API_V1_PREFIX)
app.include_router(export.router, prefix=settings.API_V1_PREFIX)
app.include_router(codegen.router, prefix=settings.API_V1_PREFIX)
app.include_router(diagrams.router, prefix=settings.API_V1_PREFIX)
app.include_router(actions.router, prefix=settings.API_V1_PREFIX)
app.include_router(revisions.router, prefix=settings.API_V1_PREFIX)
app.include_router(pm.router, prefix=settings.API_V1_PREFIX)
app.include_router(workspace.router, prefix=settings.API_V1_PREFIX)


@app.get("/healthz", tags=["System"])
def healthz():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/", tags=["System"])
def root():
    return {
        "name": settings.APP_NAME,
        "docs": "/docs",
        "health": "/healthz",
        "api_prefix": settings.API_V1_PREFIX,
        "llm_configured": settings.llm_configured,
    }

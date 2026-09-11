"""Backend generators: FastAPI (Python) and Express.js (Node.js)."""

from __future__ import annotations

from typing import Any

from app.services.codegen.base import (
    PY_TYPE_MAP,
    SA_TYPE_MAP,
    blueprint_context,
    column_precision,
    is_nullable,
    is_pk,
    is_unique,
    map_type,
    pascal_case,
    render_template,
    singularize,
    snake_case,
    table_columns,
    table_plural,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _python_default(column: dict[str, Any]) -> str | None:
    """Return a Python default expression from a column type/DEFAULT clause."""
    type_upper = (column.get("type") or "").upper()
    if "DEFAULT TRUE" in type_upper or "DEFAULT 'true'" in type_upper:
        return "True"
    if "DEFAULT FALSE" in type_upper or "DEFAULT 'false'" in type_upper:
        return "False"
    if "DEFAULT NOW()" in type_upper or "DEFAULT CURRENT_TIMESTAMP" in type_upper:
        return "utcnow"
    if "DEFAULT" in type_upper:
        raw = type_upper.split("DEFAULT", 1)[1].strip().rstrip(";")
        if raw.startswith("'") and raw.endswith("'"):
            return repr(raw.strip("'"))
        if raw.replace(".", "", 1).isdigit():
            return raw
    return None


def _pydantic_field(column: dict[str, Any]) -> str:
    name = column.get("name") or ""
    py_type = map_type(column.get("type") or "TEXT", PY_TYPE_MAP)
    nullable = is_nullable(column) and not is_pk(column)
    precision = column_precision(column.get("type") or "")
    default = _python_default(column)
    description = (column.get("description") or name).replace('"', "'")

    if is_pk(column):
        return f"    {name}: {py_type} | None = None  # {description}"

    if py_type == "datetime" and default == "utcnow":
        return (
            f"    {name}: {py_type} = Field(default_factory=utcnow, description=\"{description}\")"
        )

    if nullable:
        args = ["Field(None"]
    else:
        args = ["Field(..."]

    if precision and py_type == "str":
        args.append(f"max_length={precision}")
    if default is not None and default != "utcnow":
        args.append(f"default={default}")
    args.append(f"description=\"{description}\"")

    if nullable:
        return f"    {name}: Optional[{py_type}] = {', '.join(args)})"
    return f"    {name}: {py_type} = {', '.join(args)})"


def _fastapi_model(table: dict[str, Any]) -> str:
    """SQLAlchemy 2.0 model for a single table (columns only, no relationships)."""
    model = pascal_case(singularize(table.get("name") or "item"))
    pk_cols = [c for c in table_columns(table) if is_pk(c)]
    has_serial = any("SERIAL" in (c.get("type") or "").upper() for c in pk_cols)
    id_is_pk = bool(pk_cols) and any(c.get("name") == "id" for c in pk_cols)

    body_lines: list[str] = []
    for column in table_columns(table):
        name = column.get("name") or ""
        type_raw = column.get("type") or "TEXT"
        sa_type = map_type(type_raw, SA_TYPE_MAP)
        precision = column_precision(type_raw)
        if sa_type == "String" and precision:
            sa_type = f"String({precision})"
        elif sa_type == "Numeric" and precision:
            sa_type = f"Numeric({precision})"

        if name == "id" and id_is_pk and has_serial:
            body_lines.append("    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)")
            continue
        args = [sa_type]
        if id_is_pk and name == "id":
            args.append("primary_key=True")
        if is_unique(column):
            args.append("unique=True")
        if not is_nullable(column) and not (id_is_pk and name == "id"):
            args.append("nullable=False")
        if "now()" in type_raw.upper():
            args.append("server_default=func.now()")
        if "REFERENCES" in type_raw.upper():
            target = type_raw.upper().split("REFERENCES", 1)[1].split("(")[0].strip()
            args.append(f'ForeignKey("{target}.id")')
        py_base = map_type(type_raw, PY_TYPE_MAP)
        body_lines.append(f"    {name}: Mapped[{py_base} | None] = mapped_column({', '.join(args)})")

    header = (
        "from datetime import date, datetime, time\n"
        "from decimal import Decimal\n"
        "from typing import Any\n\n"
        "from sqlalchemy import (\n"
        "    BigInteger,\n"
        "    Boolean,\n"
        "    Date,\n"
        "    DateTime,\n"
        "    Float,\n"
        "    ForeignKey,\n"
        "    Integer,\n"
        "    Numeric,\n"
        "    SmallInteger,\n"
        "    String,\n"
        "    Text,\n"
        "    Time,\n"
        "    func,\n"
        "    mapped_column,\n"
        ")\n"
        "from sqlalchemy.dialects.postgresql import JSONB, Uuid\n"
        "from sqlalchemy.orm import Mapped\n\n"
        "from app.database import Base\n\n\n"
    )
    body = f"class {model}(Base):\n    __tablename__ = \"{table.get('name')}\"\n\n"
    body += "\n".join(body_lines) + "\n"
    return header + body


def _python_module_context(context: dict[str, Any]) -> dict[str, str]:
    """Shared template tokens for the FastAPI generator."""
    primary = context["primary_table"]
    table_name = primary.get("name") or "items"
    model = pascal_case(singularize(table_name))
    plural = table_plural(table_name)
    return {
        "PROJECT_NAME": context["project_name"],
        "APP_SLUG": context["app_slug"],
        "MODEL": model,
        "MODEL_LOWER": model.lower(),
        "TABLE": table_name,
        "PLURAL": plural,
        "PLURAL_LOWER": plural.lower(),
        "AUTH_METHOD": context["auth_method"],
        "AUTH_METHOD_LOWER": context["auth_method"].lower(),
    }


FASTAPI_MAIN = '''"""__PROJECT_NAME__ - FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import __MODEL_LOWER__, auth, deps
from app.core.logging import setup_logging
from app.database import Base, engine

setup_logging()

app = FastAPI(
    title="__PROJECT_NAME__ API",
    version="0.1.0",
    description="REST API generated from an AI blueprint. Interactive docs at /docs.",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    # Create tables from SQLAlchemy models (use Alembic for real migrations)
    Base.metadata.create_all(bind=engine)


app.include_router(auth.router, prefix="/api/v1", tags=["Auth"])
app.include_router(__MODEL_LOWER__.router, prefix="/api/v1", tags=["__MODEL__"])
'''

FASTAPI_CONFIG = '''"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "__PROJECT_NAME__"
    debug: bool = False

    secret_key: str = "CHANGE_ME_secret_key_at_least_32_chars"
    access_token_expire_minutes: int = 60 * 24  # 24 hours
    algorithm: str = "HS256"

    database_url: str = "postgresql://app:app_password@localhost:5432/__APP_SLUG__"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
'''

FASTAPI_DATABASE = '''"""Database engine, session factory and declarative base."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency that yields a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''

FASTAPI_SECURITY = '''"""Password hashing and JWT utilities."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError:
        return None
'''

FASTAPI_LOGGING = '''"""Logging setup for the application."""

import logging
import sys


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
'''

FASTAPI_USER_MODEL = '''from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
'''

FASTAPI_DEPS = '''"""Shared FastAPI dependencies (authentication)."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exc
    user = db.get(User, int(payload.get("sub", 0)))
    if user is None or not user.is_active:
        raise credentials_exc
    return user
'''

FASTAPI_AUTH_SCHEMAS = '''"""Authentication request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    full_name: str | None = Field(None, max_length=150)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime
'''

FASTAPI_AUTH_ROUTER = '''"""Authentication endpoints: register, login, me."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
'''

FASTAPI_SERVICE = '''"""Service layer for __PLURAL_LOWER__ (clean architecture business logic)."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.__MODEL_LOWER__ import __MODEL__ as Model
from app.schemas.__MODEL_LOWER__ import __MODEL__Create, __MODEL__Update


def list_(db: Session, skip: int = 0, limit: int = 100) -> list[Model]:
    return db.query(Model).offset(skip).limit(limit).all()


def get(db: Session, item_id: int) -> Model:
    item = db.get(Model, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="__MODEL__ not found")
    return item


def create(db: Session, payload: __MODEL__Create) -> Model:
    item = Model(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update(db: Session, item_id: int, payload: __MODEL__Update) -> Model:
    item = get(db, item_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


def delete(db: Session, item_id: int) -> None:
    item = get(db, item_id)
    db.delete(item)
    db.commit()
'''

FASTAPI_ROUTER = '''"""REST endpoints for __MODEL__ (CRUD)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.__MODEL_LOWER__ import (
    __MODEL__Create,
    __MODEL__Out,
    __MODEL__Update,
)
from app.services import __MODEL_LOWER__ as service

router = APIRouter(prefix="/__PLURAL_LOWER__", tags=["__MODEL__"])


@router.get("", response_model=list[__MODEL__Out])
def list_items(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
):
    return service.list_(db, skip=skip, limit=limit)


@router.post("", response_model=__MODEL__Out, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: __MODEL__Create,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
):
    return service.create(db, payload)


@router.get("/{item_id}", response_model=__MODEL__Out)
def get_item(
    item_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
):
    return service.get(db, item_id)


@router.patch("/{item_id}", response_model=__MODEL__Out)
def update_item(
    item_id: int,
    payload: __MODEL__Update,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
):
    return service.update(db, item_id, payload)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
):
    service.delete(db, item_id)
'''

FASTAPI_SCHEMAS = '''"""Pydantic schemas for __MODEL__ (validation + serialization)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from datetime import datetime as utcnow  # noqa: F401


class __MODEL__Base(BaseModel):
__BASE_FIELDS__


class __MODEL__Create(__MODEL__Base):
    pass


class __MODEL__Update(__MODEL__Base):
    pass


class __MODEL__Out(__MODEL__Base):
    model_config = ConfigDict(from_attributes=True)

    id: int
'''

FASTAPI_REQUIREMENTS = """fastapi>=0.115
uvicorn[standard]>=0.32
sqlalchemy>=2.0,<3.0
psycopg2-binary>=2.9
pydantic[email]>=2.8
pydantic-settings>=2.5
PyJWT>=2.9
bcrypt>=4.2
python-multipart>=0.0.12
pytest>=8.3
httpx>=0.27
"""

FASTAPI_ENV_EXAMPLE = """# App
DEBUG=true
SECRET_KEY=CHANGE_ME_secret_key_at_least_32_chars
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Database
DATABASE_URL=postgresql://app:app_password@localhost:5432/__APP_SLUG__
"""

FASTAPI_DOCKERFILE = """FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""

FASTAPI_COMPOSE = """services:
  api:
    build: .
    container_name: __APP_SLUG___api
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://app:app_password@db:5432/__APP_SLUG__
      SECRET_KEY: CHANGE_ME_secret_key_at_least_32_chars
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - .:/app

  db:
    image: postgres:16-alpine
    container_name: __APP_SLUG___db
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app_password
      POSTGRES_DB: __APP_SLUG__
    ports:
      - "5432:5432"
    volumes:
      - db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d __APP_SLUG__"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  db_data:
"""

FASTAPI_GITIGNORE = """__pycache__/
*.py[cod]
.venv/
.env
.pytest_cache/
.coverage
"""

FASTAPI_TESTS = {
    "tests/conftest.py": '''"""Test fixtures: in-memory SQLite database and test client."""

import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client
''',
    "tests/test_health.py": '''from fastapi.testclient import TestClient

from app.main import app


def test_openapi_docs_available(client: TestClient):
    response = client.get("/docs")
    assert response.status_code == 200
''',
    "tests/test_auth.py": '''from fastapi.testclient import TestClient


def test_register_and_login(client: TestClient):
    register = client.post(
        "/api/v1/auth/register",
        json={"email": "dev@example.com", "password": "strongpassword1"},
    )
    assert register.status_code == 201
    token = register.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "dev@example.com"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "dev@example.com", "password": "wrong"},
    )
    assert login.status_code == 401
''',
}

FASTAPI_README = """# __PROJECT_NAME__ - FastAPI Service

REST API generated from the project blueprint. Clean architecture with a clear
separation: `api` (HTTP layer) -> `services` (business logic) -> `models` (data).

## Features

- JWT authentication (`register` / `login` / `me`)
- CRUD API for `__TABLE__` with Pydantic validation
- Centralized error handling, structured logging
- Swagger UI at http://localhost:8000/docs and ReDoc at /redoc
- Tests with pytest, Docker + docker-compose for local development

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows
pip install -r requirements.txt
cp .env.example .env
docker compose up -d db         # PostgreSQL
uvicorn app.main:app --reload   # http://localhost:8000/docs
```

## Test

```bash
pytest
```

## Structure

```text
app/
  api/         HTTP routes and dependencies
  core/        security, logging, config
  models/      SQLAlchemy models
  schemas/     Pydantic validation schemas
  services/    business logic
tests/         pytest suite
```

> Replace `SECRET_KEY` before deploying. Use Alembic for production migrations.
"""


def _schema_fields(table: dict[str, Any]) -> str:
    lines: list[str] = []
    for column in table_columns(table):
        if is_pk(column):
            continue
        lines.append(_pydantic_field(column))
    return "\n".join(lines) if lines else "    pass"


def generate_fastapi(blueprint: dict[str, Any]) -> dict[str, str]:
    context = blueprint_context(blueprint)
    tokens = _python_module_context(context)
    primary = context["primary_table"]

    schema_file = render_template(
        FASTAPI_SCHEMAS,
        **tokens,
        BASE_FIELDS=_schema_fields(primary),
    )
    tests = {
        f"tests/test_{tokens['MODEL_LOWER']}.py": render_template(
            """from fastapi.testclient import TestClient


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "crud@example.com", "password": "strongpassword1"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_crud_flow(client: TestClient):
    headers = _auth_headers(client)
    base = "/api/v1/__PLURAL_LOWER__"

    created = client.post(base, json={}, headers=headers)
    assert created.status_code in (200, 201)

    listing = client.get(base, headers=headers)
    assert listing.status_code == 200
""",
            **tokens,
        ),
        **{k: render_template(v, **tokens) for k, v in FASTAPI_TESTS.items()},
    }

    files = {
        "README.md": render_template(FASTAPI_README, **tokens),
        ".gitignore": FASTAPI_GITIGNORE,
        ".env.example": render_template(FASTAPI_ENV_EXAMPLE, **tokens),
        "requirements.txt": FASTAPI_REQUIREMENTS,
        "Dockerfile": FASTAPI_DOCKERFILE,
        "docker-compose.yml": render_template(FASTAPI_COMPOSE, **tokens),
        "app/__init__.py": "",
        "app/main.py": render_template(FASTAPI_MAIN, **tokens),
        "app/config.py": render_template(FASTAPI_CONFIG, **tokens),
        "app/database.py": render_template(FASTAPI_DATABASE, **tokens),
        "app/core/__init__.py": "",
        "app/core/security.py": FASTAPI_SECURITY,
        "app/core/logging.py": FASTAPI_LOGGING,
        "app/models/__init__.py": "",
        "app/models/user.py": FASTAPI_USER_MODEL,
        f"app/models/{tokens['MODEL_LOWER']}.py": _fastapi_model(primary),
        "app/schemas/__init__.py": "",
        "app/schemas/auth.py": FASTAPI_AUTH_SCHEMAS,
        f"app/schemas/{tokens['MODEL_LOWER']}.py": schema_file,
        "app/api/__init__.py": "",
        "app/api/deps.py": FASTAPI_DEPS,
        "app/api/auth.py": FASTAPI_AUTH_ROUTER,
        f"app/api/{tokens['MODEL_LOWER']}.py": render_template(FASTAPI_ROUTER, **tokens),
        "app/services/__init__.py": "",
        f"app/services/{tokens['MODEL_LOWER']}.py": render_template(FASTAPI_SERVICE, **tokens),
        **tests,
    }
    return files


# ---------------------------------------------------------------------------
# Express.js generator
# ---------------------------------------------------------------------------

EXPRESS_README = """# __PROJECT_NAME__ - Express.js API

REST API generated from the project blueprint. Clean layered structure:
`routes` -> `controllers` -> `services` -> `models`.

## Features

- JWT authentication (register / login / me)
- CRUD API for `__TABLE__` with Zod validation
- Centralized error handling, structured logging (winston)
- Swagger docs at http://localhost:3000/docs (openapi.yaml)
- Jest tests, Docker + docker-compose for local development

## Quick start

```bash
npm install
cp .env.example .env
npm run dev            # http://localhost:3000
```

## Test

```bash
npm test
```

## Structure

```text
src/
  config/         env config, logger
  controllers/    HTTP request handling
  middlewares/    auth, validation, error handling
  models/         data layer (replace with your DB)
  routes/         route definitions
  services/       business logic
  utils/          ApiError, pick
  validations/    Zod schemas
  server.js       entry point
  app.js          Express app
```

> Replace `JWT_SECRET` before deploying. Swap the in-memory model for
> Postgres/Prisma when ready.
"""

EXPRESS_PACKAGE_JSON = """{
  "name": "__APP_SLUG__-api",
  "version": "0.1.0",
  "description": "__PROJECT_NAME__ REST API generated from an AI blueprint",
  "main": "src/server.js",
  "scripts": {
    "start": "node src/server.js",
    "dev": "nodemon src/server.js",
    "test": "jest --runInBand"
  },
  "dependencies": {
    "bcryptjs": "^2.4.3",
    "cors": "^2.8.5",
    "dotenv": "^16.4.5",
    "express": "^4.21.0",
    "helmet": "^8.0.0",
    "jsonwebtoken": "^9.0.2",
    "morgan": "^1.10.0",
    "swagger-ui-express": "^5.0.1",
    "winston": "^3.15.0",
    "yamljs": "^0.3.0",
    "zod": "^3.23.8"
  },
  "devDependencies": {
    "jest": "^29.7.0",
    "nodemon": "^3.1.7",
    "supertest": "^7.0.0"
  }
}
"""

EXPRESS_ENV_EXAMPLE = """# App
NODE_ENV=development
PORT=3000
JWT_SECRET=CHANGE_ME_secret_key_at_least_32_chars
JWT_EXPIRES_IN=1d
"""

EXPRESS_SERVER = """const http = require("http");

const app = require("./app");
const logger = require("./config/logger");

const port = process.env.PORT || 3000;

const server = http.createServer(app);

server.listen(port, () => {
  logger.info(`__PROJECT_NAME__ API listening on http://localhost:${port}`);
  logger.info(`Swagger docs at http://localhost:${port}/docs`);
});
"""

EXPRESS_APP = """const cors = require("cors");
const express = require("express");
const helmet = require("helmet");
const morgan = require("morgan");
const swaggerUi = require("swagger-ui-express");
const YAML = require("yamljs");

const logger = require("./config/logger");
const errorHandler = require("./middlewares/errorHandler");
const routes = require("./routes");

const app = express();

app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(morgan("combined", { stream: { write: (msg) => logger.http(msg.trim()) } }));

const swaggerDocument = YAML.load(process.cwd() + "/openapi.yaml");
app.use("/docs", swaggerUi.serve, swaggerUi.setup(swaggerDocument));

app.get("/health", (req, res) => res.json({ status: "ok", service: "__APP_SLUG__" }));

app.use("/api/v1", routes);

// 404 handler
app.use((req, res) => {
  res.status(404).json({ success: false, message: "Route not found" });
});

// Centralized error handler
app.use(errorHandler);

module.exports = app;
"""

EXPRESS_CONFIG = """const dotenv = require("dotenv");

dotenv.config();

module.exports = {
  env: process.env.NODE_ENV || "development",
  port: parseInt(process.env.PORT, 10) || 3000,
  jwt: {
    secret: process.env.JWT_SECRET || "CHANGE_ME_secret_key_at_least_32_chars",
    expiresIn: process.env.JWT_EXPIRES_IN || "1d",
  },
};
"""

EXPRESS_LOGGER = """const winston = require("winston");

const logger = winston.createLogger({
  level: process.env.NODE_ENV === "production" ? "info" : "debug",
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.printf(({ timestamp, level, message }) => `${timestamp} | ${level.toUpperCase()} | ${message}`)
  ),
  transports: [new winston.transports.Console()],
});

module.exports = logger;
"""

EXPRESS_APPERROR = """class ApiError extends Error {
  constructor(statusCode, message, details = undefined) {
    super(message);
    this.statusCode = statusCode;
    this.details = details;
    Error.captureStackTrace(this, this.constructor);
  }
}

module.exports = ApiError;
"""

EXPRESS_ERROR_HANDLER = """const logger = require("../config/logger");
const ApiError = require("../utils/ApiError");

// eslint-disable-next-line no-unused-vars
function errorHandler(err, req, res, next) {
  if (err instanceof ApiError) {
    return res.status(err.statusCode).json({
      success: false,
      message: err.message,
      ...(err.details && { details: err.details }),
    });
  }

  if (err.name === "ValidationError") {
    return res.status(400).json({ success: false, message: "Validation failed", details: err.errors });
  }

  if (err.type === "entity.parse.failed") {
    return res.status(400).json({ success: false, message: "Malformed JSON body" });
  }

  logger.error(err);
  return res.status(500).json({ success: false, message: "Internal server error" });
}

module.exports = errorHandler;
"""

EXPRESS_AUTH_MIDDLEWARE = """const jwt = require("jsonwebtoken");

const config = require("../config");
const ApiError = require("../utils/ApiError");
const User = require("../models/user.model");

async function authenticate(req, res, next) {
  try {
    const header = req.headers.authorization || "";
    const token = header.startsWith("Bearer ") ? header.slice(7) : null;
    if (!token) throw new ApiError(401, "Authentication required");

    const payload = jwt.verify(token, config.jwt.secret);
    const user = await User.findById(payload.sub);
    if (!user) throw new ApiError(401, "User no longer exists");

    req.user = user;
    next();
  } catch (error) {
    next(new ApiError(401, "Invalid or expired token"));
  }
}

module.exports = authenticate;
"""

EXPRESS_VALIDATE = """const ApiError = require("../utils/ApiError");

function validate(schema) {
  return (req, res, next) => {
    const result = schema.safeParse({
      body: req.body,
      query: req.query,
      params: req.params,
    });
    if (!result.success) {
      const details = result.error.issues.map((issue) => ({
        field: issue.path.join("."),
        message: issue.message,
      }));
      throw new ApiError(400, "Validation failed", details);
    }
    Object.assign(req, result.data);
    next();
  };
}

module.exports = validate;
"""

EXPRESS_USER_MODEL = """const crypto = require("crypto");

// In-memory user store - swap with your database (e.g. Prisma + Postgres).
const users = new Map();

class User {
  constructor({ email, passwordHash, fullName = null }) {
    this.id = crypto.randomUUID();
    this.email = email;
    this.passwordHash = passwordHash;
    this.fullName = fullName;
    this.role = "user";
    this.isActive = true;
    this.createdAt = new Date().toISOString();
  }

  static async create(data) {
    const user = new User(data);
    users.set(user.email, user);
    return user;
  }

  static async findByEmail(email) {
    return users.get(email) || null;
  }

  static async findById(id) {
    for (const user of users.values()) {
      if (user.id === id) return user;
    }
    return null;
  }

  toJSON() {
    const { passwordHash, ...safe } = this;
    return safe;
  }
}

module.exports = User;
"""

EXPRESS_AUTH_SERVICE = """const bcrypt = require("bcryptjs");
const jwt = require("jsonwebtoken");

const config = require("../config");
const ApiError = require("../utils/ApiError");
const User = require("../models/user.model");

async function register({ email, password, fullName }) {
  const existing = await User.findByEmail(email);
  if (existing) throw new ApiError(409, "Email already registered");

  const passwordHash = await bcrypt.hash(password, 10);
  const user = await User.create({ email, passwordHash, fullName });
  return { user: user.toJSON(), accessToken: signToken(user.id) };
}

async function login({ email, password }) {
  const user = await User.findByEmail(email);
  if (!user) throw new ApiError(401, "Invalid email or password");

  const valid = await bcrypt.compare(password, user.passwordHash);
  if (!valid) throw new ApiError(401, "Invalid email or password");

  return { user: user.toJSON(), accessToken: signToken(user.id) };
}

function signToken(userId) {
  return jwt.sign({ sub: userId }, config.jwt.secret, { expiresIn: config.jwt.expiresIn });
}

module.exports = { register, login };
"""

EXPRESS_AUTH_CONTROLLER = """const authService = require("../services/auth.service");
const asyncHandler = require("../utils/asyncHandler");

const register = asyncHandler(async (req, res) => {
  const result = await authService.register(req.body);
  res.status(201).json({ success: true, data: result });
});

const login = asyncHandler(async (req, res) => {
  const result = await authService.login(req.body);
  res.json({ success: true, data: result });
});

const me = asyncHandler(async (req, res) => {
  res.json({ success: true, data: req.user.toJSON() });
});

module.exports = { register, login, me };
"""

EXPRESS_AUTH_VALIDATION = """const { z } = require("zod");

const register = z.object({
  body: z.object({
    email: z.string().email(),
    password: z.string().min(8, "Password must be at least 8 characters"),
    fullName: z.string().max(150).optional(),
  }),
});

const login = z.object({
  body: z.object({
    email: z.string().email(),
    password: z.string(),
  }),
});

module.exports = { register, login };
"""

EXPRESS_AUTH_ROUTES = """const router = require("express").Router();

const authenticate = require("../middlewares/auth");
const validate = require("../middlewares/validate");
const authController = require("../controllers/auth.controller");
const authValidation = require("../validations/auth.validation");

router.post("/auth/register", validate(authValidation.register), authController.register);
router.post("/auth/login", validate(authValidation.login), authController.login);
router.get("/auth/me", authenticate, authController.me);

module.exports = router;
"""

EXPRESS_ASYNC_HANDLER = """function asyncHandler(fn) {
  return (req, res, next) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

module.exports = asyncHandler;
"""

EXPRESS_MODEL_TEMPLATE = """const crypto = require("crypto");

// In-memory store for __MODEL__ - swap with your database when ready.
const items = new Map();

class __MODEL__ {
  constructor(data) {
    this.id = crypto.randomUUID();
__ASSIGNMENTS__
    this.createdAt = new Date().toISOString();
  }

  static async create(data) {
    const item = new __MODEL__(data);
    items.set(item.id, item);
    return item;
  }

  static async findAll() {
    return Array.from(items.values());
  }

  static async findById(id) {
    return items.get(id) || null;
  }

  static async update(id, data) {
    const item = items.get(id);
    if (!item) return null;
    Object.assign(item, data, { id });
    return item;
  }

  static async delete(id) {
    return items.delete(id);
  }
}

module.exports = __MODEL__;
"""

EXPRESS_SERVICE_TEMPLATE = """const ApiError = require("../utils/ApiError");
const __MODEL__ = require("../models/__MODEL_LOWER__.model");

async function listItems() {
  return __MODEL__.findAll();
}

async function getItem(id) {
  const item = await __MODEL__.findById(id);
  if (!item) throw new ApiError(404, "__MODEL__ not found");
  return item;
}

async function createItem(payload) {
  return __MODEL__.create(payload);
}

async function updateItem(id, payload) {
  const item = await __MODEL__.update(id, payload);
  if (!item) throw new ApiError(404, "__MODEL__ not found");
  return item;
}

async function deleteItem(id) {
  const deleted = await __MODEL__.delete(id);
  if (!deleted) throw new ApiError(404, "__MODEL__ not found");
}

module.exports = { listItems, getItem, createItem, updateItem, deleteItem };
"""

EXPRESS_CONTROLLER_TEMPLATE = """const asyncHandler = require("../utils/asyncHandler");
const service = require("../services/__MODEL_LOWER__.service");

const list = asyncHandler(async (req, res) => {
  const data = await service.listItems();
  res.json({ success: true, data });
});

const getOne = asyncHandler(async (req, res) => {
  const data = await service.getItem(req.params.id);
  res.json({ success: true, data });
});

const create = asyncHandler(async (req, res) => {
  const data = await service.createItem(req.body);
  res.status(201).json({ success: true, data });
});

const update = asyncHandler(async (req, res) => {
  const data = await service.updateItem(req.params.id, req.body);
  res.json({ success: true, data });
});

const remove = asyncHandler(async (req, res) => {
  await service.deleteItem(req.params.id);
  res.status(204).end();
});

module.exports = { list, getOne, create, update, remove };
"""

EXPRESS_ROUTES_TEMPLATE = """const router = require("express").Router();

const authenticate = require("../middlewares/auth");
const validate = require("../middlewares/validate");
const controller = require("../controllers/__MODEL_LOWER__.controller");
const validation = require("../validations/__MODEL_LOWER__.validation");

router.use(authenticate);

router.get("/__PLURAL_LOWER__", controller.list);
router.get("/__PLURAL_LOWER__/:id", controller.getOne);
router.post("/__PLURAL_LOWER__", validate(validation.create), controller.create);
router.patch("/__PLURAL_LOWER__/:id", validate(validation.update), controller.update);
router.delete("/__PLURAL_LOWER__/:id", controller.remove);

module.exports = router;
"""

EXPRESS_ROUTES_INDEX = """const router = require("express").Router();

const authRoutes = require("./auth.routes");
const __MODEL_LOWER__Routes = require("./__MODEL_LOWER__.routes");

router.use(authRoutes);
router.use(__MODEL_LOWER__Routes);

module.exports = router;
"""

EXPRESS_JEST_CONFIG = """module.exports = {
  testEnvironment: "node",
  testMatch: ["**/tests/**/*.test.js"],
};
"""

EXPRESS_TESTS = {
    "tests/health.test.js": """const request = require("supertest");

const app = require("../src/app");

describe("GET /health", () => {
  it("reports service health", async () => {
    const response = await request(app).get("/health");
    expect(response.status).toBe(200);
    expect(response.body.status).toBe("ok");
  });
});
""",
    "tests/auth.test.js": """const request = require("supertest");

const app = require("../src/app");

describe("Auth flow", () => {
  it("registers a user and returns a token", async () => {
    const response = await request(app)
      .post("/api/v1/auth/register")
      .send({ email: "dev@example.com", password: "strongpassword1", fullName: "Dev" });
    expect(response.status).toBe(201);
    expect(response.body.data.accessToken).toBeDefined();
  });

  it("rejects wrong credentials on login", async () => {
    const response = await request(app)
      .post("/api/v1/auth/login")
      .send({ email: "dev@example.com", password: "wrong" });
    expect(response.status).toBe(401);
  });
});
""",
}

EXPRESS_DOCKERFILE = """FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

EXPOSE 3000
CMD ["npm", "start"]
"""

EXPRESS_COMPOSE = """services:
  api:
    build: .
    container_name: __APP_SLUG___api
    ports:
      - "3000:3000"
    environment:
      NODE_ENV: production
      JWT_SECRET: CHANGE_ME_secret_key_at_least_32_chars
    volumes:
      - .:/app
"""

EXPRESS_GITIGNORE = """node_modules/
.env
coverage/
"""


def _js_type(column: dict[str, Any]) -> str:
    base = map_type(column.get("type") or "TEXT", PY_TYPE_MAP)
    if base == "datetime":
        return "string"
    if base == "date":
        return "string"
    if base == "Decimal":
        return "number"
    if base == "Any":
        return "object"
    if base == "bytes":
        return "string"
    return base


def _zod_field(column: dict[str, Any]) -> str:
    name = column.get("name") or ""
    js_type = _js_type(column)
    precision = column_precision(column.get("type") or "")
    nullable = is_nullable(column)
    description = (column.get("description") or name).replace('"', "'")

    if js_type == "string":
        rule = "z.string()"
        if precision:
            rule += f".max({precision})"
        if not nullable:
            rule += ".min(1)"
    elif js_type == "number":
        rule = "z.number()"
    elif js_type == "boolean":
        rule = "z.boolean()"
    else:
        rule = "z.unknown()"

    if nullable:
        rule += ".optional()"
    return f"  {name}: {rule}, // {description}"


def _express_tokens(context: dict[str, Any]) -> dict[str, str]:
    primary = context["primary_table"]
    table_name = primary.get("name") or "items"
    model = pascal_case(singularize(table_name))
    plural = table_plural(table_name)
    return {
        "PROJECT_NAME": context["project_name"],
        "APP_SLUG": context["app_slug"],
        "MODEL": model,
        "MODEL_LOWER": snake_case(singularize(table_name)),
        "PLURAL_LOWER": plural.lower(),
    }


def _zod_schema_fields(table: dict[str, Any]) -> str:
    lines = []
    for column in table_columns(table):
        if is_pk(column):
            continue
        lines.append(_zod_field(column))
    return "\n".join(lines)


def generate_express(blueprint: dict[str, Any]) -> dict[str, str]:
    context = blueprint_context(blueprint)
    tokens = _express_tokens(context)
    primary = context["primary_table"]
    model_lower = tokens["MODEL_LOWER"]

    assignments = []
    for column in table_columns(primary):
        if is_pk(column) or column.get("name") in ("created_at", "updated_at"):
            continue
        assignments.append(f"    this.{column.get('name')} = data.{column.get('name')};")

    validation = f"""const {{ z }} = require("zod");

const create = z.object({{
  body: z.object({{
{_zod_schema_fields(primary)}
  }}),
}});

const update = create.partial();

module.exports = {{ create, update }};
"""

    openapi_paths = _openapi_paths(context, primary)
    model_file = render_template(
        EXPRESS_MODEL_TEMPLATE,
        **tokens,
        ASSIGNMENTS="\n".join(assignments),
    )
    tests = {
        f"tests/{model_lower}.test.js": render_template(
            """const request = require("supertest");

const app = require("../src/app");

async function authHeaders() {
  const register = await request(app)
    .post("/api/v1/auth/register")
    .send({ email: "crud@example.com", password: "strongpassword1" });
  return { Authorization: `Bearer ${register.body.data.accessToken}` };
}

describe("__MODEL__ CRUD", () => {
  it("creates and lists items", async () => {
    const headers = await authHeaders();
    const created = await request(app)
      .post("/api/v1/__PLURAL_LOWER__")
      .send({})
      .set(headers);
    expect([200, 201]).toContain(created.status);

    const listing = await request(app).get("/api/v1/__PLURAL_LOWER__").set(headers);
    expect(listing.status).toBe(200);
  });
});
""",
            **tokens,
        ),
        **{k: render_template(v, **tokens) for k, v in EXPRESS_TESTS.items()},
    }

    files = {
        "README.md": render_template(EXPRESS_README, **tokens),
        ".gitignore": EXPRESS_GITIGNORE,
        ".env.example": render_template(EXPRESS_ENV_EXAMPLE, **tokens),
        "package.json": render_template(EXPRESS_PACKAGE_JSON, **tokens),
        "Dockerfile": EXPRESS_DOCKERFILE,
        "docker-compose.yml": render_template(EXPRESS_COMPOSE, **tokens),
        "openapi.yaml": render_template(
            EXPRESS_OPENAPI,
            **tokens,
            PATHS=openapi_paths,
        ),
        "src/server.js": render_template(EXPRESS_SERVER, **tokens),
        "src/app.js": render_template(EXPRESS_APP, **tokens),
        "src/config/index.js": EXPRESS_CONFIG,
        "src/config/logger.js": EXPRESS_LOGGER,
        "src/middlewares/auth.js": EXPRESS_AUTH_MIDDLEWARE,
        "src/middlewares/errorHandler.js": EXPRESS_ERROR_HANDLER,
        "src/middlewares/validate.js": EXPRESS_VALIDATE,
        "src/models/user.model.js": EXPRESS_USER_MODEL,
        f"src/models/{model_lower}.model.js": model_file,
        "src/services/auth.service.js": EXPRESS_AUTH_SERVICE,
        f"src/services/{model_lower}.service.js": render_template(EXPRESS_SERVICE_TEMPLATE, **tokens),
        "src/controllers/auth.controller.js": EXPRESS_AUTH_CONTROLLER,
        f"src/controllers/{model_lower}.controller.js": render_template(EXPRESS_CONTROLLER_TEMPLATE, **tokens),
        "src/validations/auth.validation.js": EXPRESS_AUTH_VALIDATION,
        f"src/validations/{model_lower}.validation.js": validation,
        "src/routes/index.js": render_template(EXPRESS_ROUTES_INDEX, **tokens),
        "src/routes/auth.routes.js": EXPRESS_AUTH_ROUTES,
        f"src/routes/{model_lower}.routes.js": render_template(EXPRESS_ROUTES_TEMPLATE, **tokens),
        "src/utils/ApiError.js": EXPRESS_APPERROR,
        "src/utils/asyncHandler.js": EXPRESS_ASYNC_HANDLER,
        "jest.config.js": EXPRESS_JEST_CONFIG,
        **tests,
    }
    return files


def _openapi_paths(context: dict[str, Any], primary: dict[str, Any]) -> str:
    """Build OpenAPI 3 path definitions for the primary resource."""
    model = pascal_case(singularize(primary.get("name") or "item"))
    plural = table_plural(primary.get("name") or "item")
    base = f"/api/v1/{plural.lower()}"
    return f"""  {base}:
    get:
      summary: "List all {plural}"
      tags: [{model}]
      security:
        - bearerAuth: []
      responses:
        '200':
          description: OK
    post:
      summary: "Create a new {model}"
      tags: [{model}]
      security:
        - bearerAuth: []
      responses:
        '201':
          description: Created
  {base}/{{id}}:
    get:
      summary: "Get {model} by id"
      tags: [{model}]
      security:
        - bearerAuth: []
      responses:
        '200':
          description: OK
    patch:
      summary: "Update {model}"
      tags: [{model}]
      security:
        - bearerAuth: []
      responses:
        '200':
          description: OK
    delete:
      summary: "Delete {model}"
      tags: [{model}]
      security:
        - bearerAuth: []
      responses:
        '204':
          description: No Content
"""


EXPRESS_OPENAPI = """openapi: 3.0.3
info:
  title: __PROJECT_NAME__ API
  version: 0.1.0
  description: REST API generated from an AI blueprint.
servers:
  - url: http://localhost:3000/api/v1
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
paths:
__PATHS__
"""

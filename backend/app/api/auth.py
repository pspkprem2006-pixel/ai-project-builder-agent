import logging
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import get_settings
from app.core.email import send_reset_email
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordOut,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TokenOut,
    UserCreate,
    UserLogin,
    UserOut,
    UserUpdate,
)
from app.services.rate_limiting import client_ip, enforce_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()

RESET_TOKEN_TTL_HOURS = 1

# Generic, non-enumerating response used for every forgot-password request in
# production: identical whether or not the account exists or the email was sent.
GENERIC_RESET_RESPONSE = "If the account exists, a password reset email has been sent."


def _user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


def _rate_limits() -> dict[str, int]:
    s = get_settings()
    return {
        "login": (s.RATE_LIMIT_LOGIN, s.RATE_LIMIT_LOGIN_WINDOW),
        "register": (s.RATE_LIMIT_REGISTER, s.RATE_LIMIT_REGISTER_WINDOW),
        "forgot": (s.RATE_LIMIT_FORGOT, s.RATE_LIMIT_FORGOT_WINDOW),
        "forgot_ip": (s.RATE_LIMIT_FORGOT_IP, s.RATE_LIMIT_FORGOT_WINDOW),
        "reset": (s.RATE_LIMIT_RESET, s.RATE_LIMIT_RESET_WINDOW),
    }


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    limit, window = _rate_limits()["register"]
    if get_settings().RATE_LIMIT_ENABLED:
        enforce_rate_limit(db, request, "register", client_ip(request), limit, window)
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return TokenOut(access_token=token, user=_user_out(user))


@router.post("/login", response_model=TokenOut)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    limit, window = _rate_limits()["login"]
    if get_settings().RATE_LIMIT_ENABLED:
        # Keyed per IP + account: slows brute force and credential stuffing
        # without letting one shared IP throttle unrelated accounts.
        enforce_rate_limit(
            db, request, "login", f"{client_ip(request)}:{payload.email.lower()}", limit, window
        )
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    token = create_access_token(user.id)
    return TokenOut(access_token=token, user=_user_out(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout():
    """Client-side logout. Tokens are short-lived; revocation is enforced by expiry."""
    return None


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return _user_out(current_user)


@router.put("/me", response_model=UserOut)
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.password is not None:
        current_user.hashed_password = hash_password(payload.password)
    db.commit()
    db.refresh(current_user)
    return _user_out(current_user)


@router.post("/forgot-password", response_model=ForgotPasswordOut)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    limit, window = _rate_limits()["forgot"]
    ip_limit, _ = _rate_limits()["forgot_ip"]
    if get_settings().RATE_LIMIT_ENABLED:
        # Per account + per IP: prevents both token spam on one account and
        # bulk reset-mail flooding of many accounts from one address. The 429
        # response is identical for every identity (no enumeration).
        enforce_rate_limit(
            db, request, "forgot", f"{client_ip(request)}:{payload.email.lower()}", limit, window
        )
        enforce_rate_limit(db, request, "forgot_ip", client_ip(request), ip_limit, window)
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None:
        # Never reveal whether an account exists.
        return ForgotPasswordOut(detail=GENERIC_RESET_RESPONSE)
    token = token_urlsafe(32)
    user.reset_token = token
    user.reset_token_expires = datetime.now(UTC) + timedelta(hours=RESET_TOKEN_TTL_HOURS)
    db.commit()

    reset_link = f"{settings.APP_PUBLIC_URL}/reset-password?token={token}"
    sent = send_reset_email(user.email, reset_link)
    if sent:
        return ForgotPasswordOut(detail=GENERIC_RESET_RESPONSE)
    if settings.DEBUG:
        # Development-only fallback: SMTP is unavailable, so expose the token to
        # keep local flows testable. Never active outside explicit DEBUG mode.
        logger.warning(
            "Password reset email could not be sent (SMTP unavailable); returning the "
            "reset token in the response. DEBUG mode only."
        )
        return ForgotPasswordOut(
            detail="SMTP is not configured; using development reset link.",
            reset_token=token,
        )
    # Production: the reset token must never reach an HTTP response. Log the
    # delivery failure without the token and answer identically to the
    # non-existing-account branch.
    logger.error("Password reset email could not be sent to %s", user.email)
    return ForgotPasswordOut(detail=GENERIC_RESET_RESPONSE)


@router.post("/reset-password", status_code=status.HTTP_200_OK)
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    limit, window = _rate_limits()["reset"]
    if get_settings().RATE_LIMIT_ENABLED:
        # Per IP: reset tokens are one-time and cryptographically random, so a
        # per-token key adds nothing; the IP cap stops token-guessing floods.
        enforce_rate_limit(db, request, "reset", client_ip(request), limit, window)
    user = db.query(User).filter(User.reset_token == payload.token).first()
    if (
        user is None
        or user.reset_token_expires is None
        or user.reset_token_expires < datetime.now(UTC).replace(tzinfo=None)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")
    user.hashed_password = hash_password(payload.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    return {"detail": "Password updated successfully"}

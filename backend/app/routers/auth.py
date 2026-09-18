from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app import config, security
from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.rate_limit import rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])

_auth_rate_limit = rate_limit(config.LOGIN_RATE_LIMIT_ATTEMPTS, config.LOGIN_RATE_LIMIT_WINDOW_SECONDS)


class Credentials(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str


@router.get("/setup-required")
def setup_required(session: Session = Depends(get_session)):
    return {"setup_required": session.exec(select(User)).first() is None}


@router.post("/setup", response_model=UserOut, dependencies=[_auth_rate_limit])
def setup(creds: Credentials, response: Response, session: Session = Depends(get_session)):
    """Creates the first admin user. Only works while the User table is empty --
    after that, add more admins via `backend/scripts/create_user.py` (there's no
    signup endpoint, deliberately -- see docs/SECURITY.md)."""
    if session.exec(select(User)).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup already completed")
    if len(creds.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    user = User(username=creds.username, password_hash=security.hash_password(creds.password))
    session.add(user)
    session.commit()
    session.refresh(user)

    _set_session_cookie(response, user.id)
    return UserOut(id=user.id, username=user.username)


@router.post("/login", response_model=UserOut, dependencies=[_auth_rate_limit])
def login(creds: Credentials, response: Response, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == creds.username)).first()
    if user is None or not security.verify_password(creds.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    _set_session_cookie(response, user.id)
    return UserOut(id=user.id, username=user.username)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(config.SESSION_COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, username=user.username)


def _set_session_cookie(response: Response, user_id: int):
    token = security.create_session_token(user_id)
    response.set_cookie(
        config.SESSION_COOKIE_NAME,
        token,
        max_age=config.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
    )

from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from sqlmodel import Session

from app import config, security
from app.db import get_session
from app.models import User


def get_current_user(
    session: Session = Depends(get_session),
    session_token: Optional[str] = Cookie(default=None, alias=config.SESSION_COOKIE_NAME),
) -> User:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = security.read_session_token(session_token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

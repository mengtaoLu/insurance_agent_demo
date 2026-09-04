from fastapi import Cookie,Depends,HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from db.conn import SessionLocal
from db.entities import User,AuthSession
import hashlib
from datetime import datetime,timezone

def get_db():
    with SessionLocal() as db:
        yield db

def hash_token(token:str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def get_current_user(
        session_id:str | None = Cookie(default=None),
        db: Session = Depends(get_db)
) -> User:
    if not session_id:
        raise HTTPException(status_code=401,detail="未登陆")

    token_hash = hash_token(session_id)

    auth_session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
    )

    if auth_session is None:
        raise HTTPException(status_code=401,detail="会话过期！")

    user = db.get(User,auth_session.user_id)

    if user is None or user.status != 1:
        raise HTTPException(status_code=401, detail="用户不可用")

    return user

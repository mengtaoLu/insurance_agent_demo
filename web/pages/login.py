from datetime import datetime, timedelta, timezone
import secrets

from fastapi import Request, APIRouter, Form, Depends, Cookie
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from web.utils import get_db, hash_token, get_current_user
from db.entities import AuthSession, User
from db.services.chats import get_user_chats

app = APIRouter()

templates = Jinja2Templates(directory="templates")

@app.get("/")
async def index():
    return RedirectResponse(url="/login")

@app.get("/login")
async def login_page(request:Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )

@app.post("/login")
async def handle_login(
    username: str = Form(...),
    password: str = Form(...),
    db = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()

    if not user:
        return RedirectResponse(
            url="/",
            status_code=303
        )

    session_token = secrets.token_urlsafe(32)

    auth_session = AuthSession(
        user_id = user.id,
        token_hash = hash_token(session_token),
        expires_at = datetime.now(timezone.utc) + timedelta(hours=2),
        revoked_at=None
    )

    db.add(auth_session)
    db.commit()

    response = RedirectResponse(url="/home",status_code=303)
    response.set_cookie(
        key="session_id",
        value=session_token,
        max_age = 2*60*60,
        httponly=True,
        secure=False, # 关闭https
        samesite="lax",
        path="/"
    )

    return response

@app.get("/home")
async def to_home(
    request:Request,
    user:User = Depends(get_current_user),
    db = Depends(get_db)
):

    # 查询聊天信息
    chats = get_user_chats(user.id,db)

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "username": user.username,
            "chats": chats,
            "current_chat": None,
            "messages": [],
        }
    )

@app.post("/logout")
async def logout(
    session_id: str | None = Cookie(default=None),
    db = Depends(get_db),
):
    if session_id:
        auth_session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == hash_token(session_id),
                AuthSession.revoked_at.is_(None),
            )
        )

        if auth_session:
            auth_session.revoked_at = datetime.now(timezone.utc)
            db.commit()

    response = RedirectResponse(
        url="/login",
        status_code=303
    )
    response.delete_cookie(key="session_id", path="/")
    return response

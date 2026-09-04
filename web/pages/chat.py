from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from web.utils import get_current_user, get_db
from db.services.chats import create_new_chat
from sqlalchemy import select
from db.entities import Chat, Messages, User

app = APIRouter()

templates = Jinja2Templates(directory="templates")

@app.post('/chat')
async def do_chat(
    message: str = Form(...),
    user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """在未选择会话时发送消息：创建会话并保存第一条消息。"""
    content = message.strip()
    if not content:
        raise HTTPException(status_code=422, detail="消息不能为空")

    chat = Chat(
        user_id=user.id,
        title=content[:30],
    )
    db.add(chat)
    db.flush()

    db.add(Messages(
        chat_id=chat.id,
        role="user",
        content=content,
    ))
    db.commit()

    return RedirectResponse(
        url=f"/chat/{chat.id}",
        status_code=303
    )

@app.post("/chat/new")
async def add_new_chat(
    request:Request,
    user = Depends(get_current_user),
    db = Depends(get_db)
):
    print(f"新建对话！")

    chat = create_new_chat(user_id=user.id,db=db)

    print(f"新建对话id: {chat.id}")

    return RedirectResponse(
        url=f"/chat/{chat.id}",
        status_code=303
    )


@app.post("/chat/{chat_id}")
async def to_new_chat(
    chat_id: int,
    message: str = Form(...),
    user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    chat = db.scalar(
        select(Chat)
        .where(Chat.id == chat_id,Chat.user_id == user.id)
    )

    if chat is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    content = message.strip()
    if not content:
        raise HTTPException(status_code=422, detail="消息不能为空")

    # 保存第一条 / 后续用户消息
    user_message = Messages(
        chat_id=chat.id,
        role="user",
        content=content
    )

    db.add(user_message)

    # 如果还是空标题，就用第一条消息生成标题
    if not chat.title:
        chat.title = content[:30]

    chat.updated_at = datetime.now()

    db.commit()

    return RedirectResponse(
        url=f"/chat/{chat.id}",
        status_code=303
    )

@app.get("/chat/{chat_id}")
async def get_chat_page(
    request: Request,
    chat_id:int,
    user = Depends(get_current_user),
    db = Depends(get_db)
):
    chat = db.scalar(
        select(Chat)
        .where(Chat.id == chat_id,Chat.user_id == user.id)
    )

    if chat is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 2. 查询左侧 Chat 列表
    chats = db.scalars(
        select(Chat)
        .where(Chat.user_id == user.id)
        .order_by(Chat.updated_at.desc())
    ).all()

    # 3. 查询当前 Chat 的历史消息
    messages = db.scalars(
        select(Messages)
        .where(Messages.chat_id == chat_id)
        .order_by(Messages.created_at.asc())
    ).all()

    # 4. 渲染页面
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "username": user.username,
            "chats": chats,
            "current_chat": chat,
            "messages": messages,
        }
    )

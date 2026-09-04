from sqlalchemy.orm import Session
from sqlalchemy import select
from db.entities import Chat
from fastapi import Depends
from web.utils import get_db

def get_user_chats(user_id:int,db:Session):
    chats = db.scalars(
        select(Chat)
        .where(Chat.user_id == user_id)
        .order_by(Chat.updated_at.desc())
    ).all()

    return chats

def create_new_chat(user_id:int,db:Session):
    chat = Chat(
        user_id=user_id
    )
    db.add(chat)
    db.commit()
    return chat

from sqlalchemy.orm import Session
from sqlalchemy import select
from db.entities import Messages

def get_messages_by_chat_id(chat_id:int,db:Session) -> list[Messages]:
    messages = db.scalars(
        select(Messages)
        .where(Messages.chat_id == chat_id)
        .order_by(Messages.created_at.asc())
    ).all()

    return messages

def create_new_message(
        role:str,
        content:str,
        chat_id:int,
        db:Session
):
    message = Messages(
        role=role,
        content=content,
        chat_id=chat_id
    )

    db.add(message)
    db.commit()

def save_message(
        message:Messages,
        db:Session
):
    db.add(message)
    db.commit()
from sqlalchemy.orm import Session
from sqlalchemy import select
from db.entities import Messages

def get_messages_by_chat_id(chat_id:int,db:Session) -> list[Messages]:
    messages = db.scalars(
        select(Messages)
        .where(Messages.chat_id == chat_id)
        .order_by(Messages.id.asc())
    ).all()

    return messages

def get_messages_after_message_id(chat_id:int,message_id:int,db:Session) -> list[Messages]:
    """返回message_id后面的消息"""
    messages = db.scalars(
        select(Messages)
        .where(Messages.id > message_id, Messages.chat_id == chat_id)
        .order_by(Messages.id.asc())
    )

    return list(messages)

def get_messages_by_chat_id_amount(chat_id:int,amount:int,db:Session):
    messages = db.scalars(
        select(Messages).
        where(Messages.chat_id == chat_id)
        .limit(amount)
        .order_by(Messages.created_at.desc())
    )
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

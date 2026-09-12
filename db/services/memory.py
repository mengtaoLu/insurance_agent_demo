from db.entities import ChatMemoryRecord
from sqlalchemy.orm import Session
from sqlalchemy import select

def get_memory_by_id(chat_id:int,db:Session) -> ChatMemoryRecord | None:
    memory = db.scalars(
        select(ChatMemoryRecord)
        .where(ChatMemoryRecord.chat_id == chat_id)
    ).first()

    return memory
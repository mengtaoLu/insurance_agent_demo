from sqlalchemy.orm import declarative_base,relationship,mapped_column,Mapped
from sqlalchemy import Column,Text,Integer,String,DateTime,func,ForeignKey,JSON
from datetime import datetime

Base = declarative_base()

class User(Base):

    __tablename__ = 'user'

    id:Mapped[int] = mapped_column(primary_key=True,autoincrement=True)
    username = Column(String,nullable=False)
    email = Column(String,nullable=True)
    password_hash = Column(Text,default='a')
    status:Mapped[int] = mapped_column(default=1)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    auth_sessions = relationship("AuthSession",back_populates="user")

    chats: Mapped[list[Chat]] = relationship(back_populates="user")

class AuthSession(Base):

    __tablename__ = 'auth_session'

    id = Column(Integer,primary_key=True,autoincrement=True)
    user_id = Column(Integer,ForeignKey("user.id"))
    user = relationship("User",back_populates="auth_sessions")

    token_hash = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime,comment="自然过期时间",nullable=False)
    revoked_at = Column(DateTime,comment="强制被踢下线时间")

class Chat(Base):

    __tablename__ = 'chat'

    id:Mapped[int] = mapped_column(primary_key=True,autoincrement=True)
    user_id:Mapped[int] = mapped_column(ForeignKey("user.id"))

    user:Mapped[User] = relationship(back_populates="chats")

    messages:Mapped[list[Messages]] = relationship(back_populates="chat")

    title: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

class Messages(Base):

    __tablename__ = 'messages'

    id:Mapped[int] = mapped_column(primary_key=True,autoincrement=True)
    chat_id:Mapped[int] = mapped_column(ForeignKey("chat.id"))

    chat:Mapped[Chat] = relationship(back_populates="messages")

    role:Mapped[str] = mapped_column()
    content:Mapped[str] = mapped_column()
    created_at:Mapped[datetime] = mapped_column(default=datetime.now)
    metadata_:Mapped[dict | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True
    )

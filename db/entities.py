from sqlalchemy.orm import declarative_base,relationship,mapped_column,Mapped
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
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

    def __str__(self):
        import json
        from sqlalchemy import inspect

        mapper = inspect(self).mapper
        data = {attr.key: getattr(self, attr.key) for attr in mapper.column_attrs}
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)


class TraceEvent(Base):
    """一次 Agent 运行中的单个可观测事件。"""

    __tablename__ = "trace_event"
    __table_args__ = (
        UniqueConstraint("trace_id", "sequence_no", name="uq_trace_event_sequence"),
        CheckConstraint(
            "status IN ('pending', 'running', 'success', 'fail')",
            name="ck_trace_event_status",
        ),
        CheckConstraint("turn_no >= 0", name="ck_trace_event_turn_no"),
        CheckConstraint("step_no >= 0", name="ck_trace_event_step_no"),
        CheckConstraint("sequence_no >= 0", name="ck_trace_event_sequence_no"),
        Index("idx_trace_event_trace", "trace_id", "sequence_no"),
        Index("idx_trace_event_chat", "chat_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chat.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_no: Mapped[int] = mapped_column(nullable=False)
    step_no: Mapped[int] = mapped_column(nullable=False)
    sequence_no: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

from sqlalchemy.orm import declarative_base,relationship,mapped_column,Mapped
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from datetime import datetime
from typing import Any

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

    def to_dict(self):
        """返回可安全供其他模块调用的消息字典。"""
        from sqlalchemy import inspect

        mapper = inspect(self).mapper
        data = {str(attr.key): getattr(self, attr.key) for attr in mapper.column_attrs}
        return data


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
    prompt: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_tokens_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Plan(Base):
    """计划当前状态；执行历史由 Trace 保存。"""

    __tablename__ = "plan"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'running', 'success', 'failed', 'cancelled')"),
        CheckConstraint("result IS NULL OR json_valid(result)"),
        Index("idx_plan_chat", "chat_id", "id"),
        Index("idx_plan_trace", "trace_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chat.id"))
    trace_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_input: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, server_default="pending")
    result: Mapped[Any | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )
    steps: Mapped[list["PlanStep"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="PlanStep.step_seq"
    )


class PlanStep(Base):
    """计划中的一步，可以包含多次 LLM 或工具调用。"""

    __tablename__ = "plan_step"
    __table_args__ = (
        UniqueConstraint("plan_id", "step_seq", name="uq_plan_step_sequence"),
        CheckConstraint("step_seq > 0"),
        CheckConstraint("status IN ('pending', 'running', 'success', 'failed', 'skipped', 'cancelled')"),
        CheckConstraint("result IS NULL OR json_valid(result)"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan.id", ondelete="CASCADE"))
    step_seq: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, server_default="pending")
    result: Mapped[Any | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )
    plan: Mapped["Plan"] = relationship(back_populates="steps")


class ChatMemoryRecord(Base):
    """每个会话一份当前记忆。LLM 输出模型仍使用 agent.memory 中的 ChatMemory。

    memory 保存 {"topics": [...]}。更新时重新赋值整个字典，避免嵌套修改漏存。
    last_processed_message_id 是处理游标，0 表示尚未处理，由程序按输入批次维护。
    memory 和游标应在同一事务提交。所有时间采用 UTC。
    """

    __tablename__ = "chat_memory"
    __table_args__ = (
        UniqueConstraint("chat_id", name="uq_chat_memory_chat"),
        CheckConstraint(
            "json_valid(memory) AND json_type(memory) = 'object'",
            name="ck_chat_memory_json",
        ),
        CheckConstraint(
            "last_processed_message_id >= 0",
            name="ck_chat_memory_cursor",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chat.id", ondelete="CASCADE"), nullable=False,
    )
    memory: Mapped[dict[str, Any]] = mapped_column(
        JSON(none_as_null=True), nullable=False,
        server_default='{"topics":[]}',
    )
    last_processed_message_id: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

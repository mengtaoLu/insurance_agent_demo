from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db.entities import TraceEvent


TRACE_EVENT_STATUSES = {"pending", "running", "success", "fail"}
TRACE_EVENT_ROLES = {"system", "user", "assistant", "tool"}
TRACE_EVENT_UPDATE_FIELDS = {
    "status",
    "content",
    "usage",
    "finish_reason",
    "error",
    "metadata",
    "finished_at",
}


def _validate_status(status: str) -> None:
    if status not in TRACE_EVENT_STATUSES:
        raise ValueError(f"不支持的 TraceEvent 状态：{status}")


def _validate_role(role: str | None) -> None:
    if role is not None and role not in TRACE_EVENT_ROLES:
        raise ValueError(f"不支持的 TraceEvent role：{role}")


def create_trace_event(
    db: Session,
    *,
    trace_id: str,
    chat_id: int,
    turn_no: int,
    step_no: int,
    sequence_no: int,
    event_type: str,
    status: str = "pending",
    role: str | None = None,
    name: str | None = None,
    content: str | None = None,
    usage: dict[str, Any] | None = None,
    finish_reason: str | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TraceEvent:
    """创建一条 Trace 事件并返回刷新后的 ORM 对象。"""
    if not trace_id.strip():
        raise ValueError("trace_id 不能为空")
    if not event_type.strip():
        raise ValueError("event_type 不能为空")
    if min(turn_no, step_no, sequence_no) < 0:
        raise ValueError("turn_no、step_no、sequence_no 不能小于 0")
    _validate_status(status)
    _validate_role(role)

    event = TraceEvent(
        trace_id=trace_id,
        chat_id=chat_id,
        turn_no=turn_no,
        step_no=step_no,
        sequence_no=sequence_no,
        event_type=event_type,
        status=status,
        role=role,
        name=name,
        content=content,
        usage=usage,
        finish_reason=finish_reason,
        error=error,
        metadata_=metadata,
    )

    try:
        db.add(event)
        db.commit()
        db.refresh(event)
    except Exception:
        db.rollback()
        raise

    return event


def get_trace_event(event_id: int, db: Session) -> TraceEvent | None:
    """根据主键查询单条 Trace 事件。"""
    return db.get(TraceEvent, event_id)


def get_trace_events_by_trace_id(
    trace_id: str,
    db: Session,
) -> list[TraceEvent]:
    """按事件发生顺序查询一次 Agent 运行的完整链路。"""
    return list(
        db.scalars(
            select(TraceEvent)
            .where(TraceEvent.trace_id == trace_id)
            .order_by(TraceEvent.sequence_no.asc())
        ).all()
    )


def get_trace_events_by_chat_id(
    chat_id: int,
    db: Session,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[TraceEvent]:
    """分页查询某个会话的 Trace 事件，最新事件优先。"""
    if limit <= 0:
        raise ValueError("limit 必须大于 0")
    if offset < 0:
        raise ValueError("offset 不能小于 0")

    return list(
        db.scalars(
            select(TraceEvent)
            .where(TraceEvent.chat_id == chat_id)
            .order_by(TraceEvent.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )


def update_trace_event(
    event_id: int,
    db: Session,
    **changes: Any,
) -> TraceEvent | None:
    """局部更新执行结果；Trace 的标识、顺序和事件类型不可修改。"""
    unknown_fields = set(changes) - TRACE_EVENT_UPDATE_FIELDS
    if unknown_fields:
        fields = "、".join(sorted(unknown_fields))
        raise ValueError(f"不允许更新 TraceEvent 字段：{fields}")

    if "status" in changes:
        _validate_status(changes["status"])

    event = db.get(TraceEvent, event_id)
    if event is None:
        return None

    for field_name, value in changes.items():
        target_name = "metadata_" if field_name == "metadata" else field_name
        setattr(event, target_name, value)

    if (
        changes.get("status") in {"success", "fail"}
        and "finished_at" not in changes
    ):
        event.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        db.commit()
        db.refresh(event)
    except Exception:
        db.rollback()
        raise

    return event


def delete_trace_event(event_id: int, db: Session) -> bool:
    """删除单条 Trace 事件；不存在时返回 False。"""
    event = db.get(TraceEvent, event_id)
    if event is None:
        return False

    try:
        db.delete(event)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return True


def delete_trace_events_by_trace_id(trace_id: str, db: Session) -> int:
    """删除一次 Agent 运行的全部事件并返回删除数量。"""
    try:
        result = db.execute(
            delete(TraceEvent).where(TraceEvent.trace_id == trace_id)
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return result.rowcount or 0

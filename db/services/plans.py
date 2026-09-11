"""同步 SQLAlchemy CRUD；每个写方法独立提交，异常时回滚。"""
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from db.entities import Chat, Plan
from db.services._plan_common import (
    PLAN_STATUSES, remove, save, utcnow, validate_result, validate_status, validate_text,
)


def create_plan(
    db: Session, *, chat_id: int, user_input: str, goal: str,
    trace_id: str | None = None,
) -> Plan:
    """新计划初始为 pending；trace_id 是链路标识，不是 TraceEvent 主键。"""
    validate_text(user_input, "user_input")
    validate_text(goal, "goal")
    if trace_id is not None:
        validate_text(trace_id, "trace_id")
    if db.get(Chat, chat_id) is None:
        raise ValueError(f"会话不存在：{chat_id}")
    return save(db, Plan(
        chat_id=chat_id, user_input=user_input, goal=goal,
        trace_id=trace_id, status="pending",
    ))


def get_plan(plan_id: int, db: Session) -> Plan | None:
    return db.get(Plan, plan_id)


def get_plans_by_chat_id(
    chat_id: int, db: Session, *, limit: int = 100, offset: int = 0,
) -> list[Plan]:
    if limit <= 0 or offset < 0:
        raise ValueError("limit 必须大于 0，offset 不能小于 0")
    return list(db.scalars(
        select(Plan).where(Plan.chat_id == chat_id)
        .order_by(Plan.id.desc()).limit(limit).offset(offset)
    ))


def get_plans_by_trace_id(trace_id: str, db: Session) -> list[Plan]:
    return list(db.scalars(
        select(Plan).where(Plan.trace_id == trace_id).order_by(Plan.id.asc())
    ))


def update_plan(plan_id: int, db: Session, **changes: Any) -> Plan | None:
    """只更新明确传入的字段；result=None、error=None 表示清空。"""
    unknown = set(changes) - {"goal", "status", "result", "error"}
    if unknown:
        raise ValueError(f"不允许更新 Plan 字段：{sorted(unknown)}")
    if "goal" in changes:
        validate_text(changes["goal"], "goal")
    if "status" in changes:
        validate_status(changes["status"], PLAN_STATUSES)
    if "result" in changes:
        validate_result(changes["result"])
    if "error" in changes and changes["error"] is not None:
        validate_text(changes["error"], "error")
    plan = get_plan(plan_id, db)
    if plan is None or not changes:
        return plan
    for key, value in changes.items():
        setattr(plan, key, value)
    plan.updated_at = utcnow()
    return save(db, plan)


def delete_plan(plan_id: int, db: Session) -> bool:
    """通过 ORM 级联删除全部所属步骤，即使 SQLite 未开启外键也能清理。"""
    return remove(db, get_plan(plan_id, db))

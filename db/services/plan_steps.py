"""步骤 CRUD；顺序执行版本，暂不包含依赖调度和自动重试。"""
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from db.entities import Plan, PlanStep
from db.services._plan_common import (
    STEP_STATUSES, remove, save, utcnow, validate_result,
    validate_seq, validate_status, validate_text,
)


def create_plan_step(
    db: Session, *, plan_id: int, step_seq: int, description: str,
) -> PlanStep:
    validate_seq(step_seq)
    validate_text(description, "description")
    if db.get(Plan, plan_id) is None:
        raise ValueError(f"计划不存在：{plan_id}")
    return save(db, PlanStep(
        plan_id=plan_id, step_seq=step_seq, description=description, status="pending",
    ))


def get_plan_step(step_id: int, db: Session) -> PlanStep | None:
    return db.get(PlanStep, step_id)


def get_plan_steps_by_plan_id(plan_id: int, db: Session) -> list[PlanStep]:
    return list(db.scalars(
        select(PlanStep).where(PlanStep.plan_id == plan_id)
        .order_by(PlanStep.step_seq.asc())
    ))


def update_plan_step(step_id: int, db: Session, **changes: Any) -> PlanStep | None:
    """开始/结束时间由状态更新自动维护；重新 pending/running 会清理旧执行产出。"""
    unknown = set(changes) - {"step_seq", "description", "status", "result", "error"}
    if unknown:
        raise ValueError(f"不允许更新 PlanStep 字段：{sorted(unknown)}")
    if "step_seq" in changes:
        validate_seq(changes["step_seq"])
    if "description" in changes:
        validate_text(changes["description"], "description")
    if "status" in changes:
        validate_status(changes["status"], STEP_STATUSES)
    if "result" in changes:
        validate_result(changes["result"])
    if "error" in changes and changes["error"] is not None:
        validate_text(changes["error"], "error")
    step = get_plan_step(step_id, db)
    if step is None or not changes:
        return step
    now = utcnow()
    new_status = changes.get("status", step.status)
    if new_status != step.status:
        if new_status in {"pending", "running"}:
            step.started_at = now if new_status == "running" else None
            step.finished_at = None
            step.result = None
            step.error = None
        else:
            step.finished_at = now
    for key, value in changes.items():
        setattr(step, key, value)
    step.updated_at = now
    return save(db, step)


def delete_plan_step(step_id: int, db: Session) -> bool:
    return remove(db, get_plan_step(step_id, db))

"""Plan services 共用校验；时间统一存 UTC 无时区值，与 Trace 一致。"""
from datetime import datetime, timezone
from typing import Any
import json

PLAN_STATUSES = {"pending", "running", "success", "failed", "cancelled"}
STEP_STATUSES = PLAN_STATUSES | {"skipped"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def validate_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 不能为空")


def validate_status(value: str, allowed: set[str]) -> None:
    if value not in allowed:
        raise ValueError(f"不支持的状态：{value}")


def validate_result(value: Any) -> None:
    # 提前拒绝 ORM 对象、datetime 等不能直接持久化为 JSON 的结果。
    json.dumps(value, ensure_ascii=False, allow_nan=False)


def validate_seq(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("step_seq 必须是正整数")


def save(db, record):
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        raise
    return record


def remove(db, record) -> bool:
    if record is None:
        return False
    try:
        db.delete(record)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True

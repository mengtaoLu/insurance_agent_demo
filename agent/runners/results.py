"""执行流程返回值；暂时保留 ORM message，兼容已有 Web 和 Trace。"""
from dataclasses import dataclass
from typing import Any, Literal
from db.entities import Messages


@dataclass(frozen=True)
class LLMCallResult:
    message: Messages
    usage: dict[str, Any] | None
    finish_reason: str | None
    duration_ms: float
    output_tokens_per_second: float | None


@dataclass(frozen=True)
class ReactResult:
    message: Messages
    trace_id: str
    turn_no: int
    sequence_no: int
    react_steps: int
    stop_reason: Literal["completed", "max_steps"] = "completed"

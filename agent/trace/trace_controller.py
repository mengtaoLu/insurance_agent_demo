from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from agent.tools.tool_execution import ToolExecution
from agent.tools.tool_status import ToolStatus
from db.entities import Messages, TraceEvent
from db.services.trace_events import (
    create_trace_event,
    get_max_turn_no_by_chat_id,
)


class TraceController:
    """把 Agent 运行过程转换为持久化的 TraceEvent。"""

    def create_turn_start_event(
        self,
        chat_id: int,
        user_input: str,
        db: Session,
    ) -> TraceEvent:
        """为一次用户请求创建唯一 Trace，并记录首个事件。"""
        return create_trace_event(
            db=db,
            trace_id=str(uuid4()),
            chat_id=chat_id,
            turn_no=get_max_turn_no_by_chat_id(chat_id=chat_id, db=db) + 1,
            step_no=0,
            sequence_no=0,
            event_type="user_input",
            status="success",
            role="user",
            content=user_input,
        )

    def create_llm_response_trace(
        self,
        *,
        trace_id: str,
        chat_id: int,
        response: Messages,
        prompt: list[dict[str, Any]],
        turn_no: int,
        step_no: int,
        sequence_no: int,
        usage: dict[str, Any] | None,
        finish_reason: str | None,
        duration_ms: float,
        output_tokens_per_second: float | None,
        model_name: str | None,
        db: Session,
    ) -> TraceEvent:
        """记录一次非流式 LLM 调用及其端到端指标。"""
        return create_trace_event(
            db=db,
            trace_id=trace_id,
            chat_id=chat_id,
            turn_no=turn_no,
            step_no=step_no,
            sequence_no=sequence_no,
            event_type="llm_response",
            status="success",
            role="assistant",
            name=model_name,
            prompt=prompt,
            content=response.content,
            usage=usage,
            finish_reason=finish_reason,
            duration_ms=duration_ms,
            output_tokens_per_second=output_tokens_per_second,
            metadata=response.metadata_,
        )

    def create_tool_trace(
        self,
        *,
        trace_id: str,
        chat_id: int,
        turn_no: int,
        step_no: int,
        tool_result: ToolExecution,
        sequence_no: int,
        db: Session,
    ) -> TraceEvent:
        """记录工具名称、参数、结果和错误。"""
        status = (
            "fail"
            if tool_result.tool_status == ToolStatus.FAIL
            else "success"
        )
        error = None
        if tool_result.errors:
            error = tool_result.get_tool_result_content()

        return create_trace_event(
            db=db,
            trace_id=trace_id,
            chat_id=chat_id,
            turn_no=turn_no,
            step_no=step_no,
            sequence_no=sequence_no,
            event_type="tool_call",
            status=status,
            role="tool",
            name=tool_result.tool_call.name,
            content=tool_result.get_tool_result_content(),
            error=error,
            metadata={
                "tool_call_id": tool_result.tool_call.tool_call_id,
                "arguments": tool_result.tool_call.arguments,
            },
        )

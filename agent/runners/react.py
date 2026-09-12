"""保留原有 ReAct 算法，集中负责循环、工具执行和 Trace。"""
from copy import deepcopy
import logging
from typing import Any
from db.entities import Messages
from db.services.messages import get_messages_by_chat_id, save_message
from agent.llm.client import LLMClient
from agent.llm.messages import to_llm_message, to_record
from agent.runners.results import LLMCallResult, ReactResult
from agent.tools.tool_call import transfer_raw_call
from agent.tools.tool_executor import ToolExecutor
from agent.tools.tool_registry import ToolRegistry
from agent.trace.trace_controller import TraceController

logger = logging.getLogger(__name__)


class ReactRunner:
    def __init__(self, llm: LLMClient, tool_registry: ToolRegistry,
                 trace_controller: TraceController, system_prompt: str):
        self.llm = llm
        self.tool_registry = tool_registry
        self.trace_controller = trace_controller
        self.system_prompt = system_prompt
        self.model_name = llm.model_name

    async def chat(self, chat_id, messages, tools=None) -> LLMCallResult:
        result = await self.llm.complete(messages, tools=tools)
        return LLMCallResult(
            message=to_record(chat_id, result.response),
            usage=result.usage,
            finish_reason=result.finish_reason,
            duration_ms=result.duration_ms,
            output_tokens_per_second=result.output_tokens_per_second,
        )

    async def run(
        self,
        user_input: str,
        chat_id: int,
        db,
        persist_user_message: bool = True,
    ):
        """普通对话入口：保存消息、组装上下文并执行 ReAct。"""
        real_messages: list[dict[str, Any]] = [{
            "role": "system",
            "content": self.system_prompt,
        }]

        if persist_user_message:
            user_message = Messages(
                chat_id=chat_id,
                role="user",
                content=user_input,
            )
            db.add(user_message)
            db.commit()

        for message in get_messages_by_chat_id(chat_id, db):
            real_messages.append(to_llm_message(message))

        first_trace = self.trace_controller.create_turn_start_event(
            chat_id=chat_id,
            user_input=user_input,
            db=db,
        )

        result = await self.react(
            chat_id=chat_id,
            db=db,
            context_messages=real_messages,
            trace_id=first_trace.trace_id,
            turn_no=first_trace.turn_no,
            sequence_no=first_trace.sequence_no,
        )
        return result.message

    async def react(
        self,
        *,
        chat_id: int,
        db,
        context_messages: list[dict[str, Any]],
        trace_id: str,
        turn_no: int,
        sequence_no: int = 0,
        max_steps: int = 5,
        step_no_base: int = 0,
    ) -> ReactResult:
        """执行完整 ReAct 循环。

        调用方负责准备上下文、保存用户消息并创建首个 Trace 事件。
        ``sequence_no`` 表示调用前最后一个 Trace 序号；返回结果中的
        序号可用于下一次调用，以复用同一条 Trace。
        """
        if max_steps <= 0:
            raise ValueError("max_steps 必须大于 0")
        if sequence_no < 0 or step_no_base < 0:
            raise ValueError("sequence_no 和 step_no_base 不能小于 0")

        real_messages = deepcopy(context_messages)
        tools = [
            tool.tool_schema
            for tool in self.tool_registry.get_tools().values()
        ]
        trace_seq_no = sequence_no
        now_step = 0

        while now_step < max_steps:
            now_step += 1
            logger.info("开始 ReAct 循环：%s", now_step)

            prompt_snapshot = deepcopy(real_messages)
            llm_call = await self.chat(
                chat_id=chat_id,
                messages=real_messages,
                tools=tools,
            )
            response = llm_call.message
            save_message(response, db)
            real_messages.append(to_llm_message(response))

            trace_seq_no += 1
            self.trace_controller.create_llm_response_trace(
                trace_id=trace_id,
                chat_id=chat_id,
                response=response,
                prompt=prompt_snapshot,
                turn_no=turn_no,
                sequence_no=trace_seq_no,
                step_no=step_no_base + now_step,
                usage=llm_call.usage,
                finish_reason=llm_call.finish_reason,
                duration_ms=llm_call.duration_ms,
                output_tokens_per_second=llm_call.output_tokens_per_second,
                model_name=self.model_name,
                db=db,
            )

            if not (response.metadata_ and response.metadata_.get("tool_calls")):
                return ReactResult(
                    message=response,
                    trace_id=trace_id,
                    turn_no=turn_no,
                    sequence_no=trace_seq_no,
                    react_steps=now_step,
                )

            tool_call_list = [
                transfer_raw_call(raw_call)
                for raw_call in response.metadata_["tool_calls"]
            ]
            tool_executor = ToolExecutor(tool_call_list, self.tool_registry)
            results = await tool_executor.handler()

            for result in results:
                tool_message = result.to_system_tool_message(chat_id=chat_id)
                real_messages.append(to_llm_message(tool_message))
                save_message(tool_message, db)

                trace_seq_no += 1
                self.trace_controller.create_tool_trace(
                    db=db,
                    trace_id=trace_id,
                    chat_id=chat_id,
                    turn_no=turn_no,
                    step_no=step_no_base + now_step,
                    tool_result=result,
                    sequence_no=trace_seq_no,
                )

        # 达到最大 ReAct 步数后，禁用工具请求生成最终总结。
        real_messages.append({
            "role": "system",
            "content": "当前已经达到最大步数，请根据用户的问题进行最终总结。",
        })
        prompt_snapshot = deepcopy(real_messages)
        llm_call = await self.chat(
            chat_id=chat_id,
            messages=real_messages,
            tools=None,
        )
        response = llm_call.message
        save_message(response, db)

        trace_seq_no += 1
        self.trace_controller.create_llm_response_trace(
            trace_id=trace_id,
            chat_id=chat_id,
            response=response,
            prompt=prompt_snapshot,
            turn_no=turn_no,
            sequence_no=trace_seq_no,
            step_no=step_no_base + now_step,
            usage=llm_call.usage,
            finish_reason=llm_call.finish_reason,
            duration_ms=llm_call.duration_ms,
            output_tokens_per_second=llm_call.output_tokens_per_second,
            model_name=self.model_name,
            db=db,
        )

        return ReactResult(
            message=response,
            trace_id=trace_id,
            turn_no=turn_no,
            sequence_no=trace_seq_no,
            react_steps=now_step,
            stop_reason="max_steps",
        )

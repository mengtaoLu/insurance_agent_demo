from openai import AsyncOpenAI
from copy import deepcopy
from dataclasses import dataclass
from dotenv import load_dotenv
import os
from time import perf_counter
from db.entities import Messages
from openai.types.chat import ChatCompletion
from agent.tools.tool_call import transfer_raw_call
from agent.tools.tool_registry import default_tool_registry,ToolRegistry
from agent.tools.tool_executor import ToolExecutor
from typing import Any
from db.services.messages import get_messages_by_chat_id,save_message
from agent.trace.trace_controller import TraceController
import logging
from agent.plan.system_plan import (
    plan_prompts,
    PlanOutPut,
    StepResult,
    create_plan_from_message,
)
from uuid import uuid4
from agent.context import ContextBuilder
from agent.memory.memory_controller import refresh_memory

logger = logging.getLogger(__name__)

load_dotenv()


@dataclass(frozen=True)
class LLMCallResult:
    message: Messages
    usage: dict[str, Any] | None
    finish_reason: str | None
    duration_ms: float
    output_tokens_per_second: float | None


@dataclass(frozen=True)
class ReactResult:
    """一次 ReAct 循环的结果及其 Trace 游标。"""

    message: Messages
    trace_id: str
    turn_no: int
    sequence_no: int
    react_steps: int


class Model:

    def __init__(self,system_prompt:str,
                 temperature:float=0.7,
                 tool_registry:ToolRegistry = default_tool_registry) -> None:
        self.model_name = os.getenv("model_name")
        self.model_temperature = temperature
        self.base_url = os.getenv("base_url")
        self.api_key = os.getenv("api_key")
        self.system_prompt = system_prompt
        self.tool_registry = tool_registry
        self.trace_controller = TraceController()

        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=300
        )

    async def chat(
        self,
        chat_id: int,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMCallResult:
        request_params: dict[str, Any] = {
            "messages": messages,
            "model": self.model_name,
            "temperature": self.model_temperature,
        }
        if tools:
            request_params["tools"] = tools

        started_at = perf_counter()
        response = await self.client.chat.completions.create(
            **request_params
        )
        duration_seconds = perf_counter() - started_at

        usage = response.usage.model_dump(exclude_none=True) if response.usage else None
        completion_tokens = usage.get("completion_tokens") if usage else None
        output_tokens_per_second = None
        if completion_tokens is not None and duration_seconds > 0:
            output_tokens_per_second = completion_tokens / duration_seconds

        return LLMCallResult(
            message=self._to_system_messag_from_openai(chat_id, response),
            usage=usage,
            finish_reason=response.choices[0].finish_reason,
            duration_ms=duration_seconds * 1000,
            output_tokens_per_second=output_tokens_per_second,
        )

    def _to_openai_message(self,message:Messages) -> dict:
        """转换为openai兼容的消息格式"""
        if message.role == 'tool':
            # 工具消息，带有tool id
            # 从message的metadata中获取
            tool_id = message.metadata_.get("tool_id",None) if message.metadata_ else None
            if not tool_id:
                raise RuntimeError(f"message id: {message.id} 格式错误，缺少 ‘tool_id’ ")
            return {
                "tool_call_id": tool_id,
                "role":"tool",
                "content": message.content
            }
        elif message.metadata_:
            ## 判断是否有工具调用
            tool_calls = message.metadata_.get('tool_calls',None)
            if tool_calls:
                # 有工具调用
                return {
                    "role":message.role,
                    "content":message.content,
                    "tool_calls": tool_calls
                }
            else:
                return {
                    "role":message.role,
                    "content":message.content
                }
        else:
            return {
                "role":message.role,
                "content": message.content
            }

    def _to_system_messag_from_openai(self,chat_id:int,origin_message:ChatCompletion):
        """将openai message转为系统兼容message"""
        message = Messages(
            chat_id=chat_id,
            role="assistant",
            content=origin_message.choices[0].message.content or ""
        )

        tool_calls = origin_message.choices[0].message.tool_calls

        if tool_calls:

            tool_calls_json = []

            for tool_call in tool_calls:
                tool_calls_json.append(tool_call.model_dump())

            message.metadata_ = {
                "tool_calls": tool_calls_json
            }

        return message

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
            real_messages.append(self._to_openai_message(message))

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
            real_messages.append(self._to_openai_message(response))

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
                real_messages.append(self._to_openai_message(tool_message))
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
        )

    async def plan_execute(
        self,
        user_input: str,
        chat_id: int,
        db,
        persist_user_message: bool = True,
    ):
        """进行plan-execute模式"""
        ## 分解plan
        logger.info(f"开始分解plan：{user_input}")

        memory =  await refresh_memory(chat_id=chat_id,db=db)

        context_builder = ContextBuilder(type="plan",memory=memory)
        plan_messages = context_builder.build_plan_context(
            chat_id=chat_id,
            db=db,
            user_input=user_input,
            json_schema=PlanOutPut.model_json_schema(),
            tools=[t for t in self.tool_registry.get_tools().values()]
        )

        # 保存用户信息；Web 路由已经保存时关闭，避免重复记录。
        if persist_user_message:
            user_message = Messages(
                chat_id=chat_id,
                role="user",
                content=user_input
            )
            db.add(user_message)
            db.commit()

        first_trace = self.trace_controller.create_turn_start_event(
            chat_id=chat_id,
            user_input=user_input,
            db=db,
        )
        trace_id = first_trace.trace_id
        turn_no = first_trace.turn_no
        # trace_seq_no 始终表示当前 Trace 中最后一个已使用的序号。
        trace_seq_no = first_trace.sequence_no
        plan_prompt = [self._to_openai_message(m) for m in plan_messages]

        logger.info(f"plan模式注入上下文：{plan_prompt}")

        started_at = perf_counter()
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                temperature=self.model_temperature,
                messages=plan_prompt,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            duration_ms = (perf_counter() - started_at) * 1000
            trace_seq_no += 1
            self.trace_controller.create_plan_trace(
                trace_id=trace_id,
                chat_id=chat_id,
                turn_no=turn_no,
                step_no=1,
                sequence_no=trace_seq_no,
                prompt=plan_prompt,
                content=None,
                status="fail",
                error=f"Plan 生成调用失败：{type(exc).__name__}: {exc}",
                duration_ms=duration_ms,
                db=db,
                metadata={"phase": "generate_plan"},
            )
            raise

        duration_ms = (perf_counter() - started_at) * 1000
        usage = response.usage.model_dump(exclude_none=True) if response.usage else None
        completion_tokens = usage.get("completion_tokens") if usage else None
        output_tokens_per_second = (
            completion_tokens / (duration_ms / 1000)
            if completion_tokens is not None and duration_ms > 0
            else None
        )
        raw_plan = response.choices[0].message.content

        # 先记录模型确实生成了什么，再进行结构化解析。
        trace_seq_no += 1
        self.trace_controller.create_plan_trace(
            trace_id=trace_id,
            chat_id=chat_id,
            turn_no=turn_no,
            step_no=1,
            sequence_no=trace_seq_no,
            prompt=plan_prompt,
            content=raw_plan,
            status="success",
            usage=usage,
            finish_reason=response.choices[0].finish_reason,
            duration_ms=duration_ms,
            output_tokens_per_second=output_tokens_per_second,
            model_name=self.model_name,
            db=db,
            metadata={"phase": "generate_plan"},
        )

        plan_parsed = False
        try:
            all_plans = create_plan_from_message(response=response)
            plan_parsed = True

            # react执行plan的步骤
            step_results = []
            for t in all_plans.steps:
                logger.info(f"开始执行第{t.step_seq}步，目标：{t.description}")
                step_message = context_builder.build_step_context(
                    user_input=user_input,
                    current_step=t.step_seq,
                    full_plan=all_plans,
                    results=step_results
                )
                step_response = await self.react(
                    chat_id=chat_id,
                    db=db,
                    context_messages=step_message,
                    trace_id=trace_id,
                    turn_no=turn_no,
                    sequence_no=trace_seq_no,
                    step_no_base=t.step_seq - 1,
                )
                trace_seq_no = step_response.sequence_no
                step_result = StepResult(
                    step_seq=t.step_seq,
                    step_result=step_response.message.content or "",
                    status="success",
                    errors=None,
                )
                step_results.append(step_result)
                logger.info(
                    "第%s步执行完成，执行结果为：%s",
                    t.step_seq,
                    step_result.step_result,
                )

            # 最终总结
            result = await self.client.chat.completions.create(
                messages=context_builder.build_final_plan_response(
                    user_input=user_input,
                    full_steps=all_plans,
                    results=step_results
                ),
                model=self.model_name or "",
                temperature=self.model_temperature
            )

            logger.info(f"最终步骤汇总结果：{result}")

            final_system_message = self._to_system_messag_from_openai(chat_id=chat_id,origin_message=result)
            save_message(final_system_message,db)

            return final_system_message


        except Exception as e:
            # 步骤执行或最终汇总失败时，不要误记为 Plan 解析失败。
            if plan_parsed:
                raise

            logger.error(f"Plan 解析失败，错误原因：{e}")
            trace_seq_no += 1
            self.trace_controller.create_plan_trace(
                trace_id=trace_id,
                chat_id=chat_id,
                turn_no=turn_no,
                step_no=1,
                sequence_no=trace_seq_no,
                prompt=plan_prompt,
                content=raw_plan,
                status="fail",
                error=f"Plan 解析失败：{type(e).__name__}: {e}",
                db=db,
                event_type="plan_parse",
                role="system",
                name="plan_parser",
                metadata={"phase": "parse_plan"},
            )
            plan_error_message = Messages(
                chat_id=chat_id,
                role="user",
                content = f"构建计划失败了，错误原因：{e}"
            )

            response = await self.client.chat.completions.create(
                model=self.model_name,
                temperature=self.model_temperature,
                messages=[self._to_openai_message(plan_error_message)]
            )

            final = self._to_system_messag_from_openai(chat_id,response)
            save_message(final,db)

            print(f"final is : {final}")

            return final

        return all_plans

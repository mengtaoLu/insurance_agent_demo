from openai import OpenAI
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

load_dotenv()


@dataclass(frozen=True)
class LLMCallResult:
    message: Messages
    usage: dict[str, Any] | None
    finish_reason: str | None
    duration_ms: float
    output_tokens_per_second: float | None


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

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=30
        )

    def chat(
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
        response = self.client.chat.completions.create(
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
        print(f"==========")
        print(f"origin_messages is : {origin_message}")
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

    def run(self,user_input:str,chat_id:int,db):
        """ReAct循环"""
        max_steps = 5

        # 简单组装上下文
        real_messages:list[dict] = [{
            "role":"system",
            "content": self.system_prompt
        }]

        # 保存第一条 / 后续用户消息
        user_message = Messages(
            chat_id=chat_id,
            role="user",
            content=user_input
        )

        db.add(user_message)
        db.commit()

        ## 简单搜索消息
        messages = get_messages_by_chat_id(chat_id,db)

        for message in messages:
            real_messages.append(self._to_openai_message(message))

        # 工具
        print("==========tool registry==========")
        print(f"{len(self.tool_registry.get_tools())}")
        print("==========tool registry==========")

        tools = [t.tool_schema for t in self.tool_registry.get_tools().values()]

        # 当前的
        now_step = 0

        ## 记录刚开始
        first_trace = self.trace_controller.create_turn_start_event(
            chat_id=chat_id,
            user_input=user_input,
            db=db
        )

        trace_seq_no = first_trace.sequence_no
        turn_no = first_trace.turn_no
        trace_id = first_trace.trace_id

        while now_step < max_steps:
            now_step += 1
            print(f"=============ReAct循环第 【{now_step}】 步=======================")
            prompt_snapshot = deepcopy(real_messages)
            llm_call = self.chat(
                chat_id=chat_id,
                messages=real_messages,
                tools=tools
            )
            response = llm_call.message
            print(f"LLM回复答案：{response}")
            # 保存下来，统一存到db
            save_message(response,db)
            real_messages.append(self._to_openai_message(response))

            ## 序列加1
            trace_seq_no += 1
            self.trace_controller.create_llm_response_trace(
                trace_id=trace_id,
                chat_id=chat_id,
                response=response,
                prompt=prompt_snapshot,
                turn_no=turn_no,
                sequence_no=trace_seq_no,
                step_no=now_step,
                usage=llm_call.usage,
                finish_reason=llm_call.finish_reason,
                duration_ms=llm_call.duration_ms,
                output_tokens_per_second=llm_call.output_tokens_per_second,
                model_name=self.model_name,
                db=db
            )

            if response.metadata_ and response.metadata_.get('tool_calls'):
                tool_call_dict_list = response.metadata_.get("tool_calls")
                # 有工具调用，转换为ToolCall
                tool_call_list =[
                    transfer_raw_call(t)
                    for t in tool_call_dict_list
                ]

                # 执行工具
                tool_excutor = ToolExecutor(tool_call_list)
                results = tool_excutor.handler()

                for r in results:
                    tool_message = r.to_system_tool_message(chat_id=chat_id)
                    # 保存到上下文中，历史消息记录中
                    real_messages.append(self._to_openai_message(tool_message))

                    # 后续统一保存消息记录
                    save_message(tool_message,db)

                    ## 保存trace
                    trace_seq_no += 1
                    self.trace_controller.create_tool_trace(
                        db=db,
                        trace_id=trace_id,
                        chat_id=chat_id,
                        turn_no=turn_no,
                        step_no=now_step,
                        tool_result=r,
                        sequence_no=trace_seq_no
                    )


            else:
                # 没有工具调用，直接输出
                return response

        ## 超过了最大步数，应该终止
        prompt = f"""当前已经达到最大步数，请根据用户的问题，进行最终总结。"""
        real_messages.append({"role": "system", "content": prompt})
        prompt_snapshot = deepcopy(real_messages)
        llm_call = self.chat(
            chat_id=chat_id,
            messages=real_messages,
            tools=None,
        )
        response = llm_call.message
        save_message(response, db)

        ## 序列加1
        trace_seq_no += 1
        self.trace_controller.create_llm_response_trace(
            trace_id=trace_id,
            chat_id=chat_id,
            response=response,
            prompt=prompt_snapshot,
            turn_no=turn_no,
            sequence_no=trace_seq_no,
            step_no=now_step,
            usage=llm_call.usage,
            finish_reason=llm_call.finish_reason,
            duration_ms=llm_call.duration_ms,
            output_tokens_per_second=llm_call.output_tokens_per_second,
            model_name=self.model_name,
            db=db
        )

        return response

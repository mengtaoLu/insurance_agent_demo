"""唯一的模型请求入口；不依赖 ORM、chat_id 或执行器。"""
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any, NotRequired, TypedDict

from dotenv import load_dotenv
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion


class LLMMessage(TypedDict):
    role: str
    content: str | None
    tool_calls: NotRequired[list[dict[str, Any]]]
    tool_call_id: NotRequired[str]


@dataclass(frozen=True)
class CompletionResult:
    response: ChatCompletion
    usage: dict[str, Any] | None
    finish_reason: str | None
    duration_ms: float
    output_tokens_per_second: float | None


class LLMClient:
    def __init__(self, *, client=None, model_name: str | None = None,
                 temperature: float = 0.7):
        load_dotenv()
        self.model_name = model_name or os.getenv("model_name")
        self.temperature = temperature
        self._owns_client = client is None
        self.client = client if client is not None else AsyncOpenAI(
            base_url=os.getenv("base_url"),
            api_key=os.getenv("api_key"),
            timeout=300,
        )

    async def complete(self, messages: list[LLMMessage], *,
                       tools: list[dict[str, Any]] | None = None,
                       json_mode: bool = False) -> CompletionResult:
        params: dict[str, Any] = {
            "model": self.model_name,
            "temperature": self.temperature,
            "messages": messages,
        }
        if tools:
            params["tools"] = tools
        if json_mode:
            params["response_format"] = {"type": "json_object"}
        started_at = perf_counter()
        response = await self.client.chat.completions.create(**params)
        duration = perf_counter() - started_at
        usage = response.usage.model_dump(exclude_none=True) if response.usage else None
        tokens = usage.get("completion_tokens") if usage else None
        return CompletionResult(
            response=response,
            usage=usage,
            finish_reason=response.choices[0].finish_reason,
            duration_ms=duration * 1000,
            # 非流式：这是整次请求耗时下的平均输出速率，不是纯解码速度。
            output_tokens_per_second=tokens / duration if tokens is not None and duration > 0 else None,
        )

    async def structured(self, messages: list[LLMMessage]) -> ChatCompletion:
        """记忆等已有调用方仍接收 SDK response，避免一次重写所有解析逻辑。"""
        return (await self.complete(messages, json_mode=True)).response

    async def close(self):
        # 注入的客户端由调用方管理；只释放本对象创建的资源。
        if self._owns_client:
            await self.client.close()

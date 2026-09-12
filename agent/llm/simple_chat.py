"""兼容原有函数名；全部请求走 LLMClient，独立调用时及时关闭资源。"""
from agent.llm.client import LLMClient, LLMMessage


async def _chat(messages: list[LLMMessage], *, json_mode: bool, llm: LLMClient | None):
    owned = llm is None
    gateway = llm if llm is not None else LLMClient()
    try:
        return (await gateway.complete(messages, json_mode=json_mode)).response
    finally:
        if owned:
            await gateway.close()


async def simpleChat(messages: list[LLMMessage], *, llm: LLMClient | None = None):
    return await _chat(messages, json_mode=False, llm=llm)


async def simpleStructChat(messages: list[LLMMessage], *, llm: LLMClient | None = None):
    return await _chat(messages, json_mode=True, llm=llm)

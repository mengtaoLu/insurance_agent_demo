"""兼容原有 Model 入口；具体算法分别在 runners/react.py 和 plan.py。"""
from agent.llm.client import LLMClient
from agent.llm.messages import to_llm_message, to_record
from agent.runners.react import ReactRunner
from agent.runners.plan import PlanRunner
from agent.runners.results import LLMCallResult, ReactResult
from agent.tools.tool_registry import default_tool_registry, ToolRegistry
from agent.trace.trace_controller import TraceController


class Model:
    def __init__(self, system_prompt: str, temperature: float = 0.7,
                 tool_registry: ToolRegistry = default_tool_registry, *,
                 llm: LLMClient | None = None):
        self.llm = llm if llm is not None else LLMClient(temperature=temperature)
        self._owns_llm = llm is None
        self.system_prompt = system_prompt
        self.tool_registry = tool_registry
        self.trace_controller = TraceController()
        self.react_runner = ReactRunner(
            self.llm, tool_registry, self.trace_controller, system_prompt,
        )
        self.plan_runner = PlanRunner(self.llm, self.react_runner)

    async def run(self, user_input: str, chat_id: int, db,
                  persist_user_message: bool = True):
        return await self.react_runner.run(user_input, chat_id, db, persist_user_message)

    async def plan_execute(self, user_input: str, chat_id: int, db,
                           persist_user_message: bool = True):
        return await self.plan_runner.run(user_input, chat_id, db, persist_user_message)

    async def react(self, **kwargs) -> ReactResult:
        return await self.react_runner.react(**kwargs)

    async def chat(self, chat_id, messages, tools=None) -> LLMCallResult:
        return await self.react_runner.chat(chat_id, messages, tools)

    async def close(self):
        if self._owns_llm:
            await self.llm.close()

    # 保留原有转换方法名，旧的学习脚本可以继续调用。
    _to_openai_message = staticmethod(to_llm_message)

    @staticmethod
    def _to_system_messag_from_openai(chat_id, origin_message):
        return to_record(chat_id, origin_message)

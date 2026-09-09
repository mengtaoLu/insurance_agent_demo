from mcp.types import Tool
from agent.tools.tool_spec import ToolSpec
from agent.tools.policy.tool_policy import ToolPolicy
from agent.tools.policy.enums import SideEffect


class McpToolAdapter:
    def __init__(self, mcp_tools: list[Tool]) -> None:
        self.tools = mcp_tools

    @staticmethod
    def _get_side_effect(tool: Tool) -> SideEffect:
        annotations = tool.annotations
        if annotations is None:
            return SideEffect.UNKNOWN
        if annotations.destructive_hint is True:
            return SideEffect.EXTERNAL
        if annotations.read_only_hint is True:
            return SideEffect.READ
        return SideEffect.UNKNOWN

    def get_tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=t.name,
                description=t.description or "",
                tool_policy=ToolPolicy(
                    max_attempt_times=1,
                    side_effect=self._get_side_effect(t),
                ),
                input_schema=t.input_schema,
                output_schema=t.output_schema,
                param_model=None,
                result_type=None,
                tool_source="mcp",
            )
            for t in self.tools
        ]

    # 兼容已有调用；新代码使用复数形式 get_tool_specs。
    def get_tool_spec(self) -> list[ToolSpec]:
        return self.get_tool_specs()

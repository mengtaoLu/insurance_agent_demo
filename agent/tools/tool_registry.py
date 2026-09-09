from agent.tools.tool_spec import ToolSpec
from agent.erros.tool_errors import ToolNameExistsError,ToolNotFounError
import logging
from agent.mcp_client.mcp_adapter import McpToolAdapter
from agent.mcp_client.client import MyMcpClient, default_mcp_client

logger = logging.getLogger(__name__)

class ToolRegistry:
    def __init__(self, tools: list[ToolSpec] | None = None) -> None:
        self._tools:dict[str,ToolSpec] = {}
        for tool in tools or []:
            self.registry(tool)

    def registry(self,tool:ToolSpec):
        if tool.name in self._tools.keys():
            raise ToolNameExistsError(f"工具【{tool.name}】已经存在！")
        self._tools[tool.name] = tool

    def get_tools(self):
        return self._tools

    def get_tool(self,name:str) -> ToolSpec:
        tool = self._tools.get(name,None)

        if not tool:
            raise ToolNotFounError(f"工具：{name}不存在！")

        return tool

    def replace_tools(self, source: str, tools: list[ToolSpec]) -> None:
        """原子替换某一来源的工具，并保留其他来源的工具。"""
        incoming: dict[str, ToolSpec] = {}
        for tool in tools:
            if tool.tool_source != source:
                raise ValueError(
                    f"工具【{tool.name}】的来源是 {tool.tool_source}，预期为 {source}"
                )
            if tool.name in incoming:
                raise ToolNameExistsError(f"工具【{tool.name}】在 {source} 中重复！")
            incoming[tool.name] = tool

        retained = {
            name: tool
            for name, tool in self._tools.items()
            if tool.tool_source != source
        }
        conflicts = retained.keys() & incoming.keys()
        if conflicts:
            names = "、".join(sorted(conflicts))
            raise ToolNameExistsError(f"工具名称与现有工具冲突：【{names}】")

        self._tools = {**retained, **incoming}

default_tool_registry = ToolRegistry()

async def load_builtin_tools(
    mcp_client: MyMcpClient = default_mcp_client,
) -> None:
    import agent.tools.tools
    logger.info("开始导入工具")

    mcp_tools = await load_mcp_tools(mcp_client)
    adapter = McpToolAdapter(mcp_tools)
    default_tool_registry.replace_tools("mcp", adapter.get_tool_specs())

    keys = list(default_tool_registry.get_tools().keys())
    logger.info("当前总共有 %s 个工具", len(keys))
    for name in keys:
        tool = default_tool_registry.get_tool(name)
        logger.info("【工具名称】：%s 【工具描述】：%s", tool.name, tool.description)

async def load_mcp_tools(
    mcp_client: MyMcpClient = default_mcp_client,
):
    await mcp_client.connect_to_server()
    return await mcp_client.get_tools()


async def close_mcp_tools(
    mcp_client: MyMcpClient = default_mcp_client,
) -> None:
    try:
        await mcp_client.close()
    finally:
        default_tool_registry.replace_tools("mcp", [])


# 兼容原来拼写错误的方法名。
load_buildin_tools = load_builtin_tools

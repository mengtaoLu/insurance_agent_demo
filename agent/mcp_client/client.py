from __future__ import annotations

from contextlib import AsyncExitStack
import asyncio
import logging
from pathlib import Path
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import PaginatedRequestParams, Result, Tool


logger = logging.getLogger(__name__)


class MyMcpClient:
    """管理一个本地 STDIO MCP Server 的连接与工具调用。"""

    def __init__(
        self,
        command: str | None = None,
        args: list[str] | None = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        project_root = Path(__file__).resolve().parents[2]
        self.server_params = StdioServerParameters(
            command=command or sys.executable,
            args=args or ["-m", "my_mcp.server"],
            cwd=cwd or project_root,
            env=env,
        )
        self.session: ClientSession | None = None
        self.initialize_result: Any | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._connect_lock = asyncio.Lock()

    async def connect_to_server(self) -> ClientSession:
        """启动本地 MCP Server，建立会话并完成协议初始化。"""
        async with self._connect_lock:
            if self.session is not None:
                return self.session

            exit_stack = AsyncExitStack()
            try:
                read_stream, write_stream = await exit_stack.enter_async_context(
                    stdio_client(self.server_params)
                )
                session = await exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                initialize_result = await session.initialize()
            except BaseException:
                await exit_stack.aclose()
                raise

            self._exit_stack = exit_stack
            self.session = session
            self.initialize_result = initialize_result
            logger.info("MCP Server 连接成功：%s", initialize_result.server_info.name)
            return session

    def _require_session(self) -> ClientSession:
        if self.session is None:
            raise RuntimeError("MCP Client 尚未连接，请先调用 connect_to_server()")
        return self.session

    async def get_tools(self) -> list[Tool]:
        """获取 MCP Server 发布的全部工具，自动处理分页。"""
        session = self._require_session()
        tools: list[Tool] = []
        cursor: str | None = None

        while True:
            params = PaginatedRequestParams(cursor=cursor) if cursor else None
            result = await session.list_tools(params=params)
            tools.extend(result.tools)

            if not result.next_cursor:
                break
            cursor = result.next_cursor

        logger.info("发现 MCP 工具：%s", [tool.name for tool in tools])
        return tools

    async def execute_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Result:
        """调用指定 MCP 工具并返回 MCP 原始结果。"""
        session = self._require_session()
        tool_name = name.strip()
        if not tool_name:
            raise ValueError("工具名称不能为空")

        logger.info("开始调用 MCP 工具：%s", tool_name)
        result = await session.call_tool(tool_name, arguments or {})

        if getattr(result, "is_error", False):
            logger.warning("MCP 工具调用失败：%s", tool_name)
        else:
            logger.info("MCP 工具调用成功：%s", tool_name)
        return result

    async def close(self) -> None:
        """关闭 MCP 会话及其启动的 Server 子进程。"""
        exit_stack = self._exit_stack
        self.session = None
        self.initialize_result = None
        self._exit_stack = None

        if exit_stack is not None:
            await exit_stack.aclose()
            logger.info("MCP Client 已关闭")

    async def __aenter__(self) -> MyMcpClient:
        await self.connect_to_server()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.close()


# 应用级 MCP Client：在 FastAPI lifespan 中建立连接并在停机时关闭。
# ToolExecutor 复用同一会话，避免每次工具调用都重启 MCP Server。
default_mcp_client = MyMcpClient()


async def main() -> None:
    from agent.mcp_client.mcp_adapter import McpToolAdapter

    
    async with MyMcpClient() as client:
        tools = await client.get_tools()
        mcp_adapter = McpToolAdapter(tools)

        for t in mcp_adapter.get_tool_spec():
            print(t)


        result = await client.execute_tool(
            "search_project_files",
            {
                "name_pattern": "tool",
                "relative_dir": "agent",
                "max_results": 10,
            },
        )
        logger.info("MCP 工具返回：%s", result.model_dump(by_alias=True))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

import asyncio
import inspect
import logging
from typing import Any

from mcp.types import CallToolResult, Result, TextContent

from agent.tools.tool_call import ToolCall
from agent.tools.tool_spec import ToolSpec
from agent.tools.tool_execution import ToolExecution
from agent.tools.tool_status import ToolStatus
from agent.tools.tool_registry import ToolRegistry, default_tool_registry
from agent.erros.tool_errors import (
    ToolNotFounError,
    WrongToolNameError,
    WrongToolParamsError,
    ToolPermissionError,
)
from agent.mcp_client.client import MyMcpClient, default_mcp_client


logger = logging.getLogger(__name__)

class ToolExecutor:
    def __init__(
        self,
        tool_call: list[ToolCall],
        tool_registry: ToolRegistry = default_tool_registry,
        mcp_client: MyMcpClient = default_mcp_client,
    ) -> None:
        self.tool_calls = tool_call
        self.tool_registry = tool_registry
        self.mcp_client = mcp_client

    async def handler(self) -> list[ToolExecution]:
        return [
            await self._handle_single_tool_call(t)
            for t in self.tool_calls
        ]

    def _get_tool(self,tool_call:ToolCall) -> ToolSpec:
        """单个toolcall获取工具"""
        try:
            return self.tool_registry.get_tool(tool_call.name)
        except ToolNotFounError as exc:
            raise WrongToolNameError(
                f"工具：【{tool_call.name}】不存在！"
            ) from exc

    def _handle_params(self,tool_call:ToolCall,tool:ToolSpec) -> dict[str, Any]:
        # 校验参数
        try:
            if tool.param_model:
                param_result = tool.param_model.model_validate(tool_call.arguments)
                return param_result.model_dump()
            return tool_call.arguments
        except Exception as exc:
            logger.exception(
                "解析 ToolCall 参数错误，tool_call_id=%s，参数=%s",
                tool_call.tool_call_id,
                tool_call.arguments,
            )
            raise WrongToolParamsError(
                "error: ToolCall参数解析错误，"
                f"tool_call: {tool_call.model_dump_json(indent=2)}"
            ) from exc

    def _handle_privilage(self,tool_call:ToolCall) -> bool:
        """校验权限"""
        ## 暂不详细设计权限方面的了，默认都有权限，先学习主线
        return True

    async def _execute_local_tool(
        self,
        tool: ToolSpec,
        params: dict[str, Any],
    ) -> Any:
        if tool.handler is None:
            raise RuntimeError(f"本地工具【{tool.name}】缺少 handler")

        if inspect.iscoroutinefunction(tool.handler):
            result = await tool.handler(**params)
        else:
            result = await asyncio.to_thread(tool.handler, **params)

        if tool.result_type is not None:
            return tool.result_type.validate_python(result)
        return result

    async def _execute_mcp_tool(
        self,
        tool: ToolSpec,
        arguments: dict[str, Any],
    ) -> Any:
        result = await self.mcp_client.execute_tool(tool.name, arguments)
        return self._normalize_mcp_result(result)

    @staticmethod
    def _normalize_mcp_result(result: Result) -> Any:
        if not isinstance(result, CallToolResult):
            raise RuntimeError(
                "当前 Agent 尚不支持该 MCP 响应类型："
                f"{type(result).__name__}"
            )

        if result.structured_content is not None:
            payload: Any = result.structured_content
        else:
            text_parts = [
                item.text
                for item in result.content
                if isinstance(item, TextContent)
            ]
            payload = "\n".join(text_parts) if text_parts else result.model_dump(by_alias=True)

        if result.is_error:
            raise RuntimeError(f"MCP 工具返回错误：{payload}")
        return payload

    async def _handle_single_tool_call(self,tool_call:ToolCall):
        """处理单个的tool_call"""
        try:
            # 1.处理参数
            tool = self._get_tool(tool_call)
            params_dict = self._handle_params(tool_call, tool)

            # 权限控制
            self._handle_privilage(tool_call)

            # 2.重试策略
            try_times = 0
            max_retrable_times = tool.tool_policy.max_attempt_times
            errors = []

            if max_retrable_times <= 0:
                raise ValueError(f"工具【{tool.name}】最大重试次数为0，不可调用！")
            while try_times < max_retrable_times:
                try_times += 1
                try:
                    async with asyncio.timeout(tool.tool_policy.timeout):
                        if tool.tool_source == "local":
                            result = await self._execute_local_tool(tool, params_dict)
                        elif tool.tool_source == "mcp":
                            result = await self._execute_mcp_tool(
                                tool,
                                tool_call.arguments,
                            )
                        else:
                            raise RuntimeError(
                                f"不支持的工具来源：{tool.tool_source}"
                            )
                    return ToolExecution(
                        tool_call=tool_call,
                        tool_status=ToolStatus.SUCCESS,
                        result=result
                    )
                except Exception as exc:
                    error = f"调用工具：[{tool.name},第：{try_times}次，错误：{exc}]"
                    logger.exception(error)
                    errors.append(error)

            return ToolExecution(
                tool_call=tool_call,
                tool_status=ToolStatus.FAIL,
                errors=errors
            )

        except WrongToolParamsError as e:
            return ToolExecution(
                tool_call=tool_call,
                result=None,
                tool_status=ToolStatus.FAIL,
                errors=str(e)
            )
        except WrongToolNameError as e:
            return ToolExecution(
                tool_call=tool_call,
                result=None,
                tool_status=ToolStatus.FAIL,
                errors=str(e)
            )
        except ToolPermissionError as e:
            return ToolExecution(
                tool_call=tool_call,
                result=None,
                tool_status=ToolStatus.FAIL,
                errors=str(e)
            )
        except Exception as e:
            return ToolExecution(
                tool_call=tool_call,
                result=None,
                tool_status=ToolStatus.FAIL,
                errors=str(e)
            )

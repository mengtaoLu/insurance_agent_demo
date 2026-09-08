from agent.tools.tool_call import ToolCall
from agent.tools.tool_spec import ToolSpec
from agent.tools.tool_execution import ToolExecution
from agent.tools.tool_status import ToolStatus
from agent.tools.tool_registry import default_tool_registry
from agent.erros.tool_errors import WrongToolNameError,WrongToolParamsError,ToolPermissionError

class ToolExecutor:
    def __init__(self,tool_call:list[ToolCall]) -> None:
        self.tool_calls = tool_call

    def handler(self) -> list[ToolExecution]:
        return [
            self._handle_single_tool_call(t)
            for t in self.tool_calls
        ]

    def _get_tool(self,tool_call:ToolCall) -> ToolSpec:
        """单个toolcall获取工具"""
        tool = default_tool_registry.get_tool(tool_call.name)

        if not tool:
            raise WrongToolNameError(f"工具：【{tool_call.name}】不存在！")

        return tool

    def _handle_params(self,tool_call:ToolCall,tool:ToolSpec):
        # 校验参数
        try:
            param_result = tool.param_model.model_validate(tool_call.arguments)
            return param_result
        except Exception as e:
            print(f"error: 解析ToolCall参数错误，tool_call_id: {tool_call.tool_call_id},参数：{tool_call.arguments}")
            raise WrongToolParamsError(f"error: ToolCall参数解析错误，tool_call: {tool_call.model_dump_json(indent=2)}")

    def _handle_privilage(self,tool_call:ToolCall) -> bool:
        """校验权限"""
        ## 暂不详细设计权限方面的了，默认都有权限，先学习主线
        return True

    def _handle_single_tool_call(self,tool_call:ToolCall):
        """处理单个的tool_call"""
        try:
            # 1.处理参数
            tool = self._get_tool(tool_call)
            params = self._handle_params(tool_call,tool)
            ## 参数转为dict
            params_dict = params.model_dump()

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
                    result = tool.handler(**params_dict)
                    return ToolExecution(
                        tool_call=tool_call,
                        tool_status=ToolStatus.SUCCESS,
                        result=result
                    )
                except Exception as e:
                    print(f"调用工具：[{tool.name},第：{try_times}次，错误：{str(e)}]")
                    errors.append(f"调用工具：[{tool.name},第：{try_times}次，错误：{str(e)}]")

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
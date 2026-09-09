from pydantic import BaseModel,ConfigDict,Field,create_model,TypeAdapter
from agent.tools.policy.enums import SideEffect
from agent.tools.policy.tool_policy import ToolPolicy
from agent.tools.tool_spec import ToolSpec
from agent.tools.tool_context import ToolContext
from agent.erros.tool_errors import ToolDescriptionNotFoundError
from agent.tools.tool_registry import default_tool_registry
import inspect
from typing import get_type_hints
import logging

logger = logging.getLogger(__name__)

class ToolDecParam(BaseModel):
    """工具装饰类的参数
        可以额外添加参数
    """

    model_config = ConfigDict(extra="allow")

    name:str|None = Field(default=None,description="工具名称")
    description:str|None = Field(default=None,description="工具描述")
    timeout:int = Field(default=30,description="工具超时/秒")
    required_permissions:list[str] = Field(default_factory=list,description="工具的权限")
    max_attempt_times:int = Field(default=1,description="最大重试次数，默认为1，就是不能重试")
    retryable_errors:list[str] = Field(default_factory=list,description="可以重试的错误类型")
    side_effect: SideEffect = Field(default=SideEffect.UNKNOWN,description="工具的副作用")

################装饰器###########################
"""这是一个装饰器方法，可以将普通函数，转换为agent系统支持的工具
    工具存储在default_tool_registry
"""
def tool_decorate(
        name:str|None = None,
        description:str|None = None,
        timeout:int = 30,
        required_permissions:list[str] = [],
        max_attempt_times:int = 1,
        retryable_errors:list[str] = [],
        side_effect:SideEffect = SideEffect.UNKNOWN
):
    tool_policy = ToolPolicy(
        timeout=timeout,
        required_permissions=required_permissions,
        retryable_errors=retryable_errors,
        side_effect=side_effect,
        max_attempt_times=max_attempt_times
    )

    def tool_wrapper(handler):
        logger.info(f"发现工具：{handler.__name__}")
        # 默认使用函数名当作工具名称
        tool_name = name if name is not None else handler.__name__
        tool_description = description if description is not None else inspect.getdoc(handler)
        if not tool_description:
            raise ToolDescriptionNotFoundError(f"工具：{tool_name} 缺少描述")


        params_model,return_type = _handler_tool_params(handler)
        tool_spec = ToolSpec(
            name=tool_name,
            description=tool_description,
            handler=handler,
            param_model=params_model,
            result_type=TypeAdapter(return_type),
            tool_policy=tool_policy
        )
        default_tool_registry.registry(tool_spec)

        return handler

    def _handler_tool_params(handler):
        """处理工具参数，转换为basemodel
            同时处理返回类型
        """
        signatures = inspect.signature(handler)
        type_hints = get_type_hints(handler,include_extras=True)
        field_params = {}

        for name,parameter in signatures.parameters.items():
            # 参数类型
            annotation = type_hints[name]
            # 用户传递的ToolContext暂时不做参数验证
            if annotation == ToolContext:
                continue

            # 默认参数，...为必填，没有默认参数就是必填项
            default = ... if parameter.default is inspect.Parameter.empty else parameter.default
            field_params[name] = (annotation,default)

        # 判定返回类型
        return_type = type_hints.get("return")

        if return_type is None:
            return_type = type(None)

        base_model = create_model(handler.__name__,**field_params)
        return base_model,return_type

    return tool_wrapper

if __name__ == "__main__":
    @tool_decorate(description="fake tool")
    def fake_tool(name:str,desc:str) -> list[str]:
        return []

    print(default_tool_registry.tools[0])

from agent.tools.tool_spec import ToolSpec
from agent.erros.tool_errors import ToolNameExistsError,ToolNotFounError

class ToolRegistry:
    def __init__(self,tools:list[ToolSpec]=[]) -> None:
        self._tools:dict[str,ToolSpec] = {}

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

default_tool_registry = ToolRegistry()

def load_buildin_tools():
    import agent.tools.tools
    print(f"开始导入工具：")
    keys = list(default_tool_registry.get_tools().keys())
    print(f"当前总共有：{len(keys)} 个工具！")
    for i in range(len(keys)):
        keys[i]
        print(f"【工具名称】：{default_tool_registry.get_tool(keys[i]).name} 【工具描述】：{default_tool_registry.get_tool(keys[i]).description}")

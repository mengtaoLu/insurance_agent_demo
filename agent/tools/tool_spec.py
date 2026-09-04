from typing import Callable
from pydantic import BaseModel,Field
import inspect
import json

class ToolSpec:
    def __init__(self,
                 handler:Callable,
                 param_model:type[BaseModel],
                 result_model:type[BaseModel]) -> None:
        self.name = handler.__name__
        self.handler = handler
        self.param_model = param_model
        self.result_model = result_model
        self.tool_schema = self._to_openai_tool_schema()

    def _to_openai_tool_schema(self):
        return {
            "type":"function",
            "function": {
                "name": self.name,
                "description": inspect.getdoc(self.handler),
                "parameters": self.param_model.model_json_schema()
            }
        }

    def __repr__(self) -> str:
        return json.dumps(self.tool_schema,ensure_ascii=False,indent=2)

if __name__ == '__main__':
    class AParam(BaseModel):
        name:str = Field(description="姓名")
        values: list[str] = Field(description="值")

    class RParam(BaseModel):
        pass

    def save(name:str,values:list[str]):
        pass

    tool = ToolSpec(
        handler=save,
        param_model=AParam,
        result_model=RParam
    )

    print(tool)
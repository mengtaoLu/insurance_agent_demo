from typing import Callable,Any
from pydantic import BaseModel,Field,TypeAdapter
import json
from dataclasses import dataclass
from agent.tools.policy.tool_policy import ToolPolicy
from typing import Literal

class ToolSpec:
    """工具的定义"""
    def __init__(self,
                 name:str,
                 description:str,
                 param_model:type[BaseModel] | None,
                 result_type:TypeAdapter | None,
                 tool_policy:ToolPolicy,
                 input_schema:dict[str,Any] | None = None,
                 output_schema:dict[str,Any] | None = None,
                 tool_source:Literal["mcp","local"]="local",
                 handler:Callable | None = None) -> None:
        self.name = name
        self.description = description
        self.handler = handler
        self.param_model = param_model
        self.tool_policy = tool_policy
        self.result_type = result_type
        self.tool_source = tool_source
        self.input_schema = input_schema
        self.output_schema = output_schema

        self.tool_schema = self._to_openai_tool_schema()

    def _to_openai_tool_schema(self) -> dict[str,Any]:

        if self.input_schema:
            parameters = self.input_schema
        elif self.param_model:
            parameters = self.param_model.model_json_schema()
        else:
            raise ValueError("input schema 和 param model不能全部为空！")

        return {
            "type":"function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters
            }
        }

    def __repr__(self) -> str:
        return json.dumps(self.tool_schema,ensure_ascii=False,indent=2)

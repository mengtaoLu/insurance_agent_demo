from typing import Callable,Any
from pydantic import BaseModel,Field,TypeAdapter
import json
from dataclasses import dataclass
from agent.tools.policy.tool_policy import ToolPolicy

class ToolSpec:
    """工具的定义"""
    def __init__(self,
                 name:str,
                 description:str,
                 handler:Callable,
                 param_model:type[BaseModel],
                 result_type:TypeAdapter,
                 tool_policy:ToolPolicy) -> None:
        self.name = name
        self.description = description
        self.handler = handler
        self.param_model = param_model
        self.tool_schema = self._to_openai_tool_schema()
        self.tool_policy = tool_policy
        self.result_type = result_type

    def _to_openai_tool_schema(self) -> dict[str,Any]:
        return {
            "type":"function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.param_model.model_json_schema()
            }
        }

    def __repr__(self) -> str:
        return json.dumps(self.tool_schema,ensure_ascii=False,indent=2)

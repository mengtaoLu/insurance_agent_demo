"""工具调用结果"""
from pydantic import BaseModel,model_validator
from agent.tools.tool_call import ToolCall
from agent.tools.tool_status import ToolStatus
from typing import Any
from db.entities import Messages
import json

class ToolExecution(BaseModel):
    tool_call: ToolCall
    tool_status: ToolStatus
    result: Any|None = None
    errors: Any|None = None

    @model_validator(mode="after")
    def check_result_errors(self):
        if self.tool_status == ToolStatus.FAIL and self.errors is None:
            raise ValueError(f"工具结果失败的时候，必须要存在errors！")

        return self

    def to_system_tool_message(self,chat_id:int):
        """转换为系统的message"""
        payload = self.result if self.tool_status == ToolStatus.SUCCESS else self.errors
        return Messages(
                    chat_id=chat_id,
                    content=payload if isinstance(payload,str) else json.dumps(payload,ensure_ascii=False,default=str) ,
                    metadata_={
                        "tool_id":self.tool_call.tool_call_id
                    },
                    role="tool"
                )
    def get_tool_result_content(self) -> str:
        payload = self.result if self.tool_status == ToolStatus.SUCCESS else self.errors
        return payload if isinstance(payload,str) else json.dumps(payload,ensure_ascii=False,default=str)

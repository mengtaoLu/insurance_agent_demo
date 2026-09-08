from pydantic import BaseModel,ConfigDict

class ToolContext(BaseModel):
    """工具的上下文"""

    model_config = ConfigDict(extra="allow")

    user_id:str|None
    trace_id:str
    chat_id:int
    tool_call_id:str
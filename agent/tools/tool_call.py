from pydantic import BaseModel,ConfigDict
from typing import Any
import json
from uuid import uuid4

class ToolCall(BaseModel):
    id:str
    name:str
    arguments: dict[str,Any]
    tool_call_id:str

    model_config = ConfigDict(frozen=True,extra="forbid")


def transfer_raw_call(tool_call_metadata:dict[str,Any]):
    """将tool call得字符串转为当前的ToolCall
        原始输出如下：
"tool_calls": [
      {
        "id": "803472681",
        "function": {
          "arguments": "{\"id\":1234}",
          "name": "query_insurance_detail"
        },
        "type": "function"
      }
    ]
    """
    tool_call_id = tool_call_metadata.get("id",'')
    name = tool_call_metadata.get('function',{}).get('name')
    arguments = json.loads(tool_call_metadata.get("function",{}).get("arguments"))
    return ToolCall(
        id=str(uuid4()),
        name=name,
        arguments=arguments,
        tool_call_id=tool_call_id
    )


if __name__ == "__main__":
    t = ToolCall(
        id='1',name="text",arguments={"a":1},tool_call_id="aa"
    )

    print(t.model_dump_json(indent=2))
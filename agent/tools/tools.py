from agent.tools.tool_decorate import tool_decorate
from typing import Annotated

@tool_decorate()
def query_insurance_detail(id: Annotated[int, "保单号"]) -> dict:
    """根据保单号查询信息"""

    return {
        "success":True,
        "id": id,
        "detail": "受益人是A，保费是300元"
    }

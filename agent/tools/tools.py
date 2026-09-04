from pydantic import BaseModel,Field
from agent.tools.tool_spec import ToolSpec

tools:list[ToolSpec] = []

class QueryInsuranceDetailParam(BaseModel):
    id:int = Field(description="保单号")

class QueryInsuranceDetailResult(BaseModel):
    success:bool = Field(description="是否成功")
    id:int = Field(description="保单号")
    detail:str = Field(description="保单详情")

def query_insurance_detail(id:int):
    """根据保单号查询信息"""

    return {
        "success":True,
        "id": id,
        "detail": "受益人是A，保费是300元"
    }

query_insurance_detail_tool = ToolSpec(
    handler=query_insurance_detail,
    param_model=QueryInsuranceDetailParam,
    result_model=QueryInsuranceDetailResult
)

tools.append(query_insurance_detail_tool)
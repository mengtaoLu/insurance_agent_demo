import inspect
from typing import get_type_hints,Annotated
from pydantic import create_model,BaseModel

class T(BaseModel):
    name:str
    agen:int


t = T(name="a",agen=12)


g = t.model_dump()

print(type(g))
print(g)
    

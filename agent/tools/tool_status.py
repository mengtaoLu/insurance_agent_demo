from enum import Enum

class ToolStatus(str,Enum):
    SUCCESS = "success"
    FAIL = "fail"
    PENDING = "pending"
from enum import Enum

class SideEffect(str,Enum):
    """工具副作用枚举"""

    NONE = "none" #纯计算工具，无副作用
    READ = "read" #只读工具，读取数据库或者外部服务等
    WRITE = "write" #写工具，会造成内部状态修改
    EXTERNAL = "external" #外部写工具，修改外部状态
    UNKNOWN = "unknown" # 未知，或者是默认

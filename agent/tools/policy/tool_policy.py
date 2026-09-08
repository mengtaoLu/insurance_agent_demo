from dataclasses import dataclass,field
from .enums import SideEffect

@dataclass
class ToolPolicy:
    """工具策略，包含重试、幂等、权限等问题"""
    timeout:int = 30 #超时，单位秒
    required_permissions: list[str] = field(default_factory=list)
    max_attempt_times: int = 3 #最大重试次数
    retryable_errors: list[str] = field(default_factory=list) #可以重试的错误类型
    side_effect: SideEffect = SideEffect.NONE # 工具外部影响
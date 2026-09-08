class ToolHandlerDefException(Exception):
    """工具的实际执行函数定义错误"""
    pass

class ToolDescriptionNotFoundError(Exception):
    """缺少工具定义错误"""
    pass

class ToolNotFounError(Exception):
    """工具没找到错误"""
    pass

class ToolNameExistsError(Exception):
    """工具名称重复错误"""
    pass

class WrongToolNameError(Exception):
    """LLM给出的ToolCall错误，找不到这个工具"""
    pass

class WrongToolParamsError(Exception):
    """LLM给出的工具参数错误"""
    pass

class ToolPermissionError(Exception):
    """没有权限调用工具"""
    pass
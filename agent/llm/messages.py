"""持久化消息和模型消息之间的显式转换；不执行数据库读写。"""
from db.entities import Messages
from openai.types.chat import ChatCompletion
from agent.llm.client import LLMMessage


def to_llm_message(message: Messages) -> LLMMessage:
    result: LLMMessage = {"role": message.role, "content": message.content}
    metadata = message.metadata_ or {}
    if message.role == "tool":
        tool_id = metadata.get("tool_id")
        if not tool_id:
            raise ValueError(f"message id: {message.id} 缺少 tool_id")
        result["tool_call_id"] = tool_id
    elif metadata.get("tool_calls"):
        result["tool_calls"] = metadata["tool_calls"]
    return result


def to_record(chat_id: int, response: ChatCompletion) -> Messages:
    """创建尚未保存的 ORM 实体；保存由执行流程决定。"""
    reply = response.choices[0].message
    record = Messages(chat_id=chat_id, role="assistant", content=reply.content or "")
    if reply.tool_calls:
        record.metadata_ = {"tool_calls": [call.model_dump(mode="json") for call in reply.tool_calls]}
    return record

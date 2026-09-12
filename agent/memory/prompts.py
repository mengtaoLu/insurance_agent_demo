from string import Template
from pydantic import BaseModel,ConfigDict,Field

class ChatMemory(BaseModel):

    model_config = ConfigDict(extra="forbid")

    topics:list[MemoryTopics] = Field(description="一个对话包含的所有主题")

class MemoryTopics(BaseModel):
    """记忆的主题结构"""

    model_config = ConfigDict(extra='forbid')

    topic_name:str = Field(description="记忆的主题")
    topic_description:str = Field(description="记忆的主题描述")
    message_ids:list[int] = Field(description="相关的消息id")
    facts:list[str] = Field(description="一些相关的事实，例如订单号，订单结果之类的其他可以记录的事实")



first_prompts_template = Template("""
    你是一个Ai的消息总结助手，可以将用户的消息以及工具的结果等整理成一个结构化的数据。
    一些关键的事实证据等，不能凭空捏造，需要根据用户的描述或者是工具结果得出结论。
    输出的结果需要是json格式，不能为markdown，不要有多余的部份。

    记忆输出格式：
    $memory_schema

""")

update_memory_template = Template("""
    根据已有的记忆和新消息，返回更新后的完整记忆。

    - 保留未被纠正，仍然有效的消息；
    - 将同一主题的新消息合并，避免重复；
    - 将用户明确纠正旧消息时，更新对应事实；
    - 不同保单、不同主题的信息不能相互覆盖。
    - 不把助手的推测或计划当成已执行的事实。
    - message_ids 只能引用输入中提供的来源 ID。

    记忆输出格式：
    $memory_schema
""")

if __name__ == "__main__":
    st = first_prompts_template.substitute(
        messages=['a','b'],
        memory_schema = ChatMemory.model_json_schema()
    )
    print(st)
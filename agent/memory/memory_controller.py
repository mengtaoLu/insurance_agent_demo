from agent.memory.prompts import first_prompts_template,update_memory_template
from db.services.messages import get_messages_by_chat_id,get_messages_after_message_id
from agent.llm.simple_chat import simpleStructChat
from agent.llm.client import LLMClient
from agent.memory.prompts import ChatMemory
import json
from time import perf_counter
import logging
from db.entities import ChatMemoryRecord
from db.services.memory import get_memory_by_id

logger = logging.getLogger(__name__)

async def refresh_memory(chat_id:int,db, *, llm: LLMClient | None = None):
    ## 先查询是否有记忆
    memory = get_memory_by_id(chat_id,db)

    if not memory:
        return await _init_memory(chat_id=chat_id,db=db,llm=llm)
    else :
        return await _update_memory(chat_id=chat_id,db=db,old_memory=memory,llm=llm)

async def _init_memory(chat_id:int,db, *, llm: LLMClient | None = None):
    """初始化记忆读取用户对话id的信息"""
    messages = get_messages_by_chat_id(chat_id,db)

    prompts = first_prompts_template.substitute(
        memory_schema=json.dumps(ChatMemory.model_json_schema(),ensure_ascii=False)
    )

    logger.info(f"开始进行记忆初始化！")
    logger.info(f"prompts is : {prompts}")
    started_at = perf_counter()

    response = await simpleStructChat([
        {"role":"system","content":prompts},
        {"role":"user","content":f"""
        用户的消息列表如下：
        {
            [str(m) for m in messages]
        }
"""}
    ], llm=llm)

    init_duration = perf_counter() - started_at
    logger.info(f"完成记忆初始化，耗时：{init_duration}")
    try:
        memory = ChatMemory.model_validate_json(response.choices[0].message.content or '')
        memory_record = ChatMemoryRecord(
            chat_id=chat_id,
            memory=memory.model_dump(),
            last_processed_message_id= messages[-1].id if len(messages) > 0 else 0
        )
        db.add(memory_record)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        return memory_record
       
    except Exception as e:
        logger.error(f"生成的记忆格式有问题：原始记忆输出：{response.choices[0].message.content},错误原因：{e}")
        raise

async def _update_memory(chat_id:int,db,old_memory:ChatMemoryRecord, *, llm: LLMClient | None = None):
    """更新记忆"""
    last_message_id = old_memory.last_processed_message_id
    new_messages = get_messages_after_message_id(chat_id=chat_id,db=db,message_id=last_message_id)
    if len(new_messages) == 0:
        return old_memory

    new_message_data = [
        {
            "id":m.id,
            "role":m.role,
            "content":m.content
        }
        for m in new_messages
    ]

    messages = [
        {"role":"system","content":update_memory_template.substitute(
            memory_schema=json.dumps(ChatMemory.model_json_schema(),ensure_ascii=False)
        )},
        {"role":"user","content":f"""
            旧的记忆如下：
            {json.dumps(old_memory.memory,ensure_ascii=False)}
        """},
        {"role":"user","content":f"""
            新的消息如下：
            {json.dumps(new_message_data,ensure_ascii=False)}
        """}
    ]

    new_response = await simpleStructChat(
        messages=messages, llm=llm
    )

    updated_memory = ChatMemory.model_validate_json(new_response.choices[0].message.content or '')

    logger.info(f"更新记忆：{updated_memory.model_dump()}")

    old_memory.memory = updated_memory.model_dump()
    old_memory.last_processed_message_id = new_messages[-1].id
    
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return old_memory

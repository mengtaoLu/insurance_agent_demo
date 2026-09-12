import logging
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os
from typing import Any

load_dotenv()

logger = logging.getLogger(__name__)

def get_client():
    base_url = os.getenv('base_url')
    api_key = os.getenv('api_key')

    return AsyncOpenAI(
        base_url=base_url,
        api_key=api_key
    )

async def simpleChat(messages:list[Any]):
    """极简客户端，返回消息"""
    client = get_client()
    return await client.chat.completions.create(
        model=os.getenv('model_name'),
        messages=messages
    )

async def simpleStructChat(messages:list[Any]):
    """极简客户端，返回格式化输出"""
    client = get_client()
    return await client.chat.completions.create(
        model=os.getenv('model_name'),
        messages=messages,
        response_format={
            "type":"json_object"
        }
    )
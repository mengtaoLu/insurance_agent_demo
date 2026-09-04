from openai import OpenAI
from dataclasses import dataclass
from dotenv import load_dotenv
import os
from db.entities import Messages
from openai.types.chat import ChatCompletion
from agent.tools.tool_spec import ToolSpec

load_dotenv()

class Model:

    def __init__(self,system_prompt:str,temperature:float=0.7) -> None:
        self.model_name = os.getenv("model_name")
        self.model_temperature = temperature
        self.base_url = os.getenv("base_url")
        self.api_key = os.getenv("api_key")
        self.system_prompt = system_prompt

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=30
        )

    def chat(self,chat_id:int,
             messages:list[Messages],
             tools:list[ToolSpec]=[]):
        # 简单组装上下文
        real_messages:list[dict] = [{
            "role":"assistant",
            "content": self.system_prompt
        }]

        for message in messages:
            real_messages.append(self._to_openai_message(message))

        response = self.client.chat.completions.create(
            messages=real_messages,
            model=self.model_name,
            temperature=self.model_temperature,
            tools=[ t.tool_schema for t in tools]
        )

        return self._to_system_messag_from_openai(chat_id,response)

    def _to_openai_message(self,message:Messages) -> dict:
        """转换为openai兼容的消息格式"""
        if message.role == 'tool':
            # 工具消息，带有tool id
            # 从message的metadata中获取
            tool_id = message.metadata_.get("tool_id",None) if message.metadata_ else None
            if not tool_id:
                raise RuntimeError(f"message id: {message.id} 格式错误，缺少 ‘tool_id’ ")
            return {
                "tool_call_id": tool_id,
                "role":"tool",
                "content": message.content
            }
        elif message.metadata_:
            ## 判断是否有工具调用
            tool_calls = message.metadata_.get('tool_calls',None)
            if tool_calls:
                # 有工具调用
                return {
                    "role":message.role,
                    "content":message.content,
                    "tool_calls": tool_calls
                }
            else:
                return {
                    "role":message.role,
                    "content":message.content
                }
        else:
            return {
                "role":message.role,
                "content": message.content
            }

    def _to_system_messag_from_openai(self,chat_id:int,origin_message:ChatCompletion):
        """将openai message转为系统兼容message"""
        print(f"==========")
        print(f"origin_messages is : {origin_message}")
        message = Messages(
            chat_id=chat_id,
            role="assistant",
            content= origin_message.choices[0].message.content
        )

        tool_calls = origin_message.choices[0].message.tool_calls

        if tool_calls:

            tool_calls_json = []

            for tool_call in tool_calls:
                tool_calls_json.append(tool_call.model_dump())

            message.metadata_ = {
                "tool_calls": tool_calls_json
            }

        return message

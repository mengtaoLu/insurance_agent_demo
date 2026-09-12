"""结构重构回归：SQLite 内存库、假模型；禁止构造真实模型客户端。"""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from agent.context import ContextBuilder
from agent.llm.client import LLMClient
from agent.llm.messages import to_llm_message
from agent.llm.models import Model
from agent.memory.memory_controller import refresh_memory
from agent.plan.system_plan import PlanOutPut, StepResult
from agent.tools.tool_registry import ToolRegistry
from db.entities import Base, Chat, ChatMemoryRecord, Messages, TraceEvent, User


def completion(content, tool_calls=None, usage=None):
    return SimpleNamespace(
        usage=usage,
        choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content=content, tool_calls=tool_calls),
        )],
    )


def fake_llm(responses):
    create = AsyncMock(side_effect=responses)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        close=AsyncMock(),
    )
    return LLMClient(client=client, model_name="offline"), create


class StructureTests(unittest.TestCase):
    def setUp(self):
        guard = patch("agent.llm.client.AsyncOpenAI",
                      side_effect=AssertionError("测试不能创建真实模型客户端"))
        guard.start()
        self.addCleanup(guard.stop)
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        user = User(username="offline")
        self.db.add(user)
        self.db.flush()
        self.chat = Chat(user_id=user.id)
        self.db.add(self.chat)
        self.db.commit()

    def test_context_contains_objects_not_json_strings(self):
        plan = PlanOutPut(goal="查找", steps=[{"step_seq": 1, "description": "查询"}])
        result = StepResult(step_seq=1, step_result="找到", status="success", errors=None)
        builder = ContextBuilder(memory={"topics": []})
        step = builder.build_step_context("查询", 1, plan, [result])
        payload = json.loads(step[1]["content"])
        self.assertIsInstance(payload["previous_results"][0], dict)
        messages = builder.build_plan_context("查询", [], plan.model_json_schema(), [])
        self.assertTrue(all(isinstance(m, dict) for m in messages))

    def test_tool_message_requires_matching_call_id(self):
        message = Messages(role="tool", content="ok", metadata_={"tool_id": "call_1"})
        self.assertEqual(to_llm_message(message)["tool_call_id"], "call_1")
        with self.assertRaises(ValueError):
            to_llm_message(Messages(role="tool", content="missing id"))

    def test_plain_chat_keeps_single_user_message(self):
        llm, create = fake_llm([completion("answer")])
        model = Model("system", tool_registry=ToolRegistry(), llm=llm)
        reply = asyncio.run(model.run("question", self.chat.id, self.db))
        self.assertEqual(reply.content, "answer")
        users = list(self.db.scalars(select(Messages).where(Messages.role == "user")))
        self.assertEqual(len(users), 1)
        self.assertEqual(create.await_count, 1)

    def test_memory_update_and_failure_preserve_cursor(self):
        llm, create = fake_llm([completion('{"topics":[]}'), completion("invalid")])
        memory = asyncio.run(refresh_memory(self.chat.id, self.db, llm=llm))
        self.assertEqual(memory.last_processed_message_id, 0)
        # 没有新消息，不应再次调用模型。
        asyncio.run(refresh_memory(self.chat.id, self.db, llm=llm))
        self.assertEqual(create.await_count, 1)
        self.db.add(Messages(chat_id=self.chat.id, role="user", content="new fact"))
        self.db.commit()
        with self.assertRaises(ValidationError):
            asyncio.run(refresh_memory(self.chat.id, self.db, llm=llm))
        self.db.refresh(memory)
        self.assertEqual(memory.memory, {"topics": []})
        self.assertEqual(memory.last_processed_message_id, 0)

    def test_memory_success_advances_cursor(self):
        llm, _ = fake_llm([completion('{"topics":[]}'), completion('{"topics":[]}')])
        memory = asyncio.run(refresh_memory(self.chat.id, self.db, llm=llm))
        message = Messages(chat_id=self.chat.id, role="user", content="new")
        self.db.add(message)
        self.db.commit()
        asyncio.run(refresh_memory(self.chat.id, self.db, llm=llm))
        self.assertEqual(memory.last_processed_message_id, message.id)

    def test_plan_parse_failure_trace(self):
        llm, _ = fake_llm([
            completion('{"topics":[]}'), completion("invalid"), completion("计划生成失败"),
        ])
        model = Model("system", tool_registry=ToolRegistry(), llm=llm)
        result = asyncio.run(model.plan_execute("question", self.chat.id, self.db))
        self.assertEqual(result.content, "计划生成失败")
        events = list(self.db.scalars(select(TraceEvent)))
        self.assertTrue(any(e.event_type == "plan_parse" and e.status == "fail" for e in events))

    def test_react_budget_and_injected_registry(self):
        from agent.tools.tool_call import ToolCall
        from agent.tools.tool_execution import ToolExecution
        from agent.tools.tool_status import ToolStatus

        raw = {"id": "call_1", "type": "function",
               "function": {"name": "lookup", "arguments": "{}"}}
        call = SimpleNamespace(model_dump=lambda **kwargs: raw)
        llm, _ = fake_llm([completion("", [call]), completion("达到上限")])
        registry = ToolRegistry()
        model = Model("system", tool_registry=registry, llm=llm)
        tool_result = ToolExecution(
            tool_call=ToolCall(id="execution_1", tool_call_id="call_1", name="lookup", arguments={}),
            tool_status=ToolStatus.SUCCESS, result="ok",
        )
        with patch("agent.runners.react.ToolExecutor") as executor:
            executor.return_value.handler = AsyncMock(return_value=[tool_result])
            result = asyncio.run(model.react(
                chat_id=self.chat.id, db=self.db,
                context_messages=[{"role": "user", "content": "question"}],
                trace_id="offline-trace", turn_no=1, max_steps=1,
            ))
        self.assertIs(executor.call_args.args[1], registry)
        self.assertEqual(result.stop_reason, "max_steps")

    def test_plan_stops_after_budget_exhaustion(self):
        from agent.runners.results import ReactResult
        llm, create = fake_llm([
            completion('{"topics":[]}'),
            completion('{"goal":"answer","steps":[{"step_seq":1,"description":"first"},{"step_seq":2,"description":"second"}]}'),
            completion("未完成"),
        ])
        model = Model("system", tool_registry=ToolRegistry(), llm=llm)
        model.react_runner.react = AsyncMock(return_value=ReactResult(
            message=Messages(role="assistant", content="达到上限"),
            trace_id="test", turn_no=1, sequence_no=2,
            react_steps=5, stop_reason="max_steps",
        ))
        asyncio.run(model.plan_execute("question", self.chat.id, self.db))
        model.react_runner.react.assert_awaited_once()
        summary = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn('"status": "fail"', summary)
        self.assertIn("达到 ReAct 步数上限", summary)

    def test_plan_network_failure_not_mislabelled_as_parse_error(self):
        llm, _ = fake_llm([completion('{"topics":[]}'), RuntimeError("offline failure")])
        model = Model("system", tool_registry=ToolRegistry(), llm=llm)
        with self.assertRaisesRegex(RuntimeError, "offline failure"):
            asyncio.run(model.plan_execute("question", self.chat.id, self.db))
        events = list(self.db.scalars(select(TraceEvent)))
        self.assertTrue(any(e.event_type == "plan_generation" and e.status == "fail" for e in events))
        self.assertFalse(any(e.event_type == "plan_parse" for e in events))

    def test_injected_client_not_closed_by_gateway(self):
        llm, _ = fake_llm([])
        asyncio.run(llm.close())
        llm.client.close.assert_not_awaited()

    def test_owned_client_is_closed(self):
        client = SimpleNamespace(close=AsyncMock())
        with patch("agent.llm.client.AsyncOpenAI", return_value=client):
            llm = LLMClient(model_name="offline")
        asyncio.run(llm.close())
        client.close.assert_awaited_once()

    def test_metrics_and_json_mode(self):
        usage = SimpleNamespace(model_dump=lambda **kwargs: {"completion_tokens": 10})
        llm, create = fake_llm([completion("{}", usage=usage)])
        with patch("agent.llm.client.perf_counter", side_effect=[10.0, 12.0]):
            result = asyncio.run(llm.complete([{"role": "user", "content": "json"}], json_mode=True))
        self.assertEqual(result.duration_ms, 2000)
        self.assertEqual(result.output_tokens_per_second, 5)
        self.assertEqual(create.call_args.kwargs["response_format"], {"type": "json_object"})

    def test_web_lifespan_releases_resources_on_failure(self):
        from web.app import app, lifespan
        model = SimpleNamespace(close=AsyncMock())
        async def exercise():
            async with lifespan(app):
                self.assertIs(app.state.model, model)
                raise RuntimeError("request failed")
        with patch("web.app.load_builtin_tools", new_callable=AsyncMock), \
             patch("web.app.close_mcp_tools", new_callable=AsyncMock) as close_mcp, \
             patch("web.app.Model", return_value=model):
            with self.assertRaisesRegex(RuntimeError, "request failed"):
                asyncio.run(exercise())
            model.close.assert_awaited_once()
            close_mcp.assert_awaited_once()

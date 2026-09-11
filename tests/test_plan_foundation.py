"""Plan 基础回归：仅使用内存 SQLite 和模拟模型响应。"""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent.context import ContextBuilder
from agent.plan.system_plan import PlanOutPut, StepResult
from db.entities import Base, Chat, Messages, PlanStep, TraceEvent, User
from db.services.plans import create_plan, delete_plan
from db.services.plan_steps import create_plan_step, update_plan_step


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        user = User(username="test")
        self.db.add(user)
        self.db.flush()
        self.chat = Chat(user_id=user.id)
        self.db.add(self.chat)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_plan_sequence_and_failure_reason(self):
        with self.assertRaises(ValidationError):
            PlanOutPut(goal="test", steps=[{"step_seq": 2, "description": "test"}])
        for reason in (None, "", "   "):
            with self.assertRaises(ValidationError):
                StepResult(step_seq=1, step_result="", status="fail", errors=reason)
        StepResult(step_seq=1, step_result="", status="fail", errors="timeout")
        StepResult(step_seq=1, step_result="ok", status="success", errors=None)

    def test_crud_rollback_status_and_cascade(self):
        plan = create_plan(self.db, chat_id=self.chat.id, user_input="question", goal="answer")
        step = create_plan_step(self.db, plan_id=plan.id, step_seq=1, description="lookup")
        with self.assertRaises(IntegrityError):
            create_plan_step(self.db, plan_id=plan.id, step_seq=1, description="duplicate")
        step = update_plan_step(step.id, self.db, status="running")
        self.assertIsNotNone(step.started_at)
        step = update_plan_step(step.id, self.db, status="failed", error="timeout")
        self.assertIsNotNone(step.finished_at)
        step = update_plan_step(step.id, self.db, status="pending")
        self.assertIsNone(step.error)
        self.assertIsNone(step.started_at)
        self.assertIsNone(step.finished_at)
        with self.assertRaises(ValueError):
            update_plan_step(step.id, self.db, status="unknown")
        with self.assertRaises(ValueError):
            update_plan_step(step.id, self.db, result=float("nan"))
        self.assertTrue(delete_plan(plan.id, self.db))
        self.assertEqual(list(self.db.scalars(select(PlanStep))), [])

    def test_planning_history_filters_tool_protocol(self):
        self.db.add_all([
            Messages(chat_id=self.chat.id, role="user", content="question"),
            Messages(chat_id=self.chat.id, role="assistant", content="", metadata_={"tool_calls": [{}]}),
            Messages(chat_id=self.chat.id, role="tool", content="result"),
            Messages(chat_id=self.chat.id, role="assistant", content="answer"),
        ])
        self.db.commit()
        history = ContextBuilder()._get_history(self.chat.id, self.db, amount=2)
        self.assertEqual([m.content for m in history], ["question", "answer"])
        self.assertEqual(ContextBuilder()._get_history(self.chat.id, self.db, amount=0), [])

    def test_plan_execute_with_mock_model(self):
        from agent.llm.models import Model
        from agent.tools.tool_registry import ToolRegistry

        def completion(content):
            return SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=content, tool_calls=None),
                )],
            )

        create = AsyncMock(side_effect=[
            completion('{"goal":"answer","steps":[{"step_seq":1,"description":"lookup"},{"step_seq":2,"description":"explain"}]}'),
            completion("step one result"),
            completion("step two result"),
            completion("final answer"),
        ])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch("agent.llm.models.AsyncOpenAI", return_value=client):
            model = Model("test", tool_registry=ToolRegistry())
            result = asyncio.run(model.plan_execute("question", self.chat.id, self.db))
        self.assertEqual(result.content, "final answer")
        self.assertEqual(create.await_count, 4)
        users = list(self.db.scalars(select(Messages).where(Messages.role == "user")))
        self.assertEqual(len(users), 1)
        events = list(self.db.scalars(select(TraceEvent).order_by(TraceEvent.sequence_no)))
        self.assertEqual(len({e.trace_id for e in events}), 1)
        self.assertEqual([e.sequence_no for e in events], list(range(len(events))))
        self.assertTrue(any(e.event_type == "plan_generation" for e in events))


if __name__ == "__main__":
    unittest.main()

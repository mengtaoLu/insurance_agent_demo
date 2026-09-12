"""Plan-and-Solve 编排：保留原有解析、步骤执行和错误 Trace。"""
import logging
from time import perf_counter
from db.entities import Messages
from db.services.messages import get_messages_by_chat_id, save_message
from agent.context import ContextBuilder
from agent.llm.client import LLMClient
from agent.llm.messages import to_llm_message, to_record
from agent.memory.memory_controller import refresh_memory
from agent.plan.system_plan import PlanOutPut, StepResult, create_plan_from_message
from agent.runners.react import ReactRunner

logger = logging.getLogger(__name__)


class PlanRunner:
    def __init__(self, llm: LLMClient, react_runner: ReactRunner):
        self.llm = llm
        self.react_runner = react_runner
        self.tool_registry = react_runner.tool_registry
        self.trace_controller = react_runner.trace_controller
        self.model_name = llm.model_name

    async def run(
        self,
        user_input: str,
        chat_id: int,
        db,
        persist_user_message: bool = True,
    ):
        """进行plan-execute模式"""
        ## 分解plan
        logger.info(f"开始分解plan：{user_input}")

        memory = await refresh_memory(chat_id=chat_id, db=db, llm=self.llm)

        context_builder = ContextBuilder(memory=memory.memory if memory else None)
        plan_messages = context_builder.build_plan_context(
            history=[
                to_llm_message(m) for m in get_messages_by_chat_id(chat_id, db)
                if m.role != "tool" and not (m.metadata_ or {}).get("tool_calls")
            ],
            user_input=user_input,
            json_schema=PlanOutPut.model_json_schema(),
            tools=[t for t in self.tool_registry.get_tools().values()]
        )

        # 保存用户信息；Web 路由已经保存时关闭，避免重复记录。
        if persist_user_message:
            user_message = Messages(
                chat_id=chat_id,
                role="user",
                content=user_input
            )
            db.add(user_message)
            db.commit()

        first_trace = self.trace_controller.create_turn_start_event(
            chat_id=chat_id,
            user_input=user_input,
            db=db,
        )
        trace_id = first_trace.trace_id
        turn_no = first_trace.turn_no
        # trace_seq_no 始终表示当前 Trace 中最后一个已使用的序号。
        trace_seq_no = first_trace.sequence_no
        plan_prompt = plan_messages

        logger.info(f"plan模式注入上下文：{plan_prompt}")

        started_at = perf_counter()
        try:
            completion = await self.llm.complete(plan_prompt, json_mode=True)
            response = completion.response
        except Exception as exc:
            duration_ms = (perf_counter() - started_at) * 1000
            trace_seq_no += 1
            self.trace_controller.create_plan_trace(
                trace_id=trace_id,
                chat_id=chat_id,
                turn_no=turn_no,
                step_no=1,
                sequence_no=trace_seq_no,
                prompt=plan_prompt,
                content=None,
                status="fail",
                error=f"Plan 生成调用失败：{type(exc).__name__}: {exc}",
                duration_ms=duration_ms,
                db=db,
                metadata={"phase": "generate_plan"},
            )
            raise

        duration_ms = completion.duration_ms
        usage = completion.usage
        output_tokens_per_second = completion.output_tokens_per_second
        raw_plan = response.choices[0].message.content

        # 先记录模型确实生成了什么，再进行结构化解析。
        trace_seq_no += 1
        self.trace_controller.create_plan_trace(
            trace_id=trace_id,
            chat_id=chat_id,
            turn_no=turn_no,
            step_no=1,
            sequence_no=trace_seq_no,
            prompt=plan_prompt,
            content=raw_plan,
            status="success",
            usage=usage,
            finish_reason=response.choices[0].finish_reason,
            duration_ms=duration_ms,
            output_tokens_per_second=output_tokens_per_second,
            model_name=self.model_name,
            db=db,
            metadata={"phase": "generate_plan"},
        )

        plan_parsed = False
        try:
            all_plans = create_plan_from_message(response=response)
            plan_parsed = True

            # react执行plan的步骤
            step_results = []
            for t in all_plans.steps:
                logger.info(f"开始执行第{t.step_seq}步，目标：{t.description}")
                step_message = context_builder.build_step_context(
                    user_input=user_input,
                    current_step=t.step_seq,
                    full_plan=all_plans,
                    results=step_results
                )
                step_response = await self.react_runner.react(
                    chat_id=chat_id,
                    db=db,
                    context_messages=step_message,
                    trace_id=trace_id,
                    turn_no=turn_no,
                    sequence_no=trace_seq_no,
                    step_no_base=t.step_seq - 1,
                )
                trace_seq_no = step_response.sequence_no
                step_result = StepResult(
                    step_seq=t.step_seq,
                    step_result=step_response.message.content or "",
                    status="success" if step_response.stop_reason == "completed" else "fail",
                    errors=None if step_response.stop_reason == "completed" else "达到 ReAct 步数上限",
                )
                step_results.append(step_result)
                if step_result.status == "fail":
                    break  # 前置步骤未完成时不继续依赖它的后续步骤。
                logger.info(
                    "第%s步执行完成，执行结果为：%s",
                    t.step_seq,
                    step_result.step_result,
                )

            # 最终总结
            result = await self.llm.complete(
                context_builder.build_final_plan_response(
                    user_input=user_input,
                    full_steps=all_plans,
                    results=step_results,
                )
            )
            final_system_message = to_record(chat_id, result.response)
            save_message(final_system_message,db)

            return final_system_message


        except Exception as e:
            # 步骤执行或最终汇总失败时，不要误记为 Plan 解析失败。
            if plan_parsed:
                raise

            logger.error(f"Plan 解析失败，错误原因：{e}")
            trace_seq_no += 1
            self.trace_controller.create_plan_trace(
                trace_id=trace_id,
                chat_id=chat_id,
                turn_no=turn_no,
                step_no=1,
                sequence_no=trace_seq_no,
                prompt=plan_prompt,
                content=raw_plan,
                status="fail",
                error=f"Plan 解析失败：{type(e).__name__}: {e}",
                db=db,
                event_type="plan_parse",
                role="system",
                name="plan_parser",
                metadata={"phase": "parse_plan"},
            )
            plan_error_message = Messages(
                chat_id=chat_id,
                role="user",
                content = f"构建计划失败了，错误原因：{e}"
            )

            response = await self.llm.complete([to_llm_message(plan_error_message)])
            final = to_record(chat_id, response.response)
            save_message(final,db)

            logger.info("Plan 失败回复：%s", final.content)

            return final

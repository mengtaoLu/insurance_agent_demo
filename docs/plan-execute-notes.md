# Plan-Execute 学习记录 · 2026-09-11

本次是 V0.4.0 之后的开发提交：复用已有异步模型、工具和 Trace，实现规划、逐步 ReAct 执行及最终汇总。未创建新发布 tag。

## 五层架构对应

| 层级 | 当前落地 |
| --- | --- |
| 能力层 | 复用 LLM、ToolRegistry、ToolExecutor 与 MCP 适配能力 |
| Agent 决策层 | PlanOutPut 结构化计划；按顺序执行，每步复用 ReAct；最终汇总 |
| 运行时与状态层 | ContextBuilder 分阶段上下文；ReactResult 返回 Trace 游标；Plan/PlanStep 状态模型与 CRUD |
| 平台与治理层 | SQLite 增量建表、约束、索引、JSON 校验和失败回滚 |
| 质量安全与可观测性 | 计划生成/解析事件、共享 trace_id 和递增 sequence_no；离线回归测试 |

## 关键知识点

1. **Plan 与 ReAct 可以组合。**外层 Plan 决定目标和步骤，内层 ReAct 根据模型输出调用工具。一项计划步骤可能执行多轮 ReAct，不能将二者的编号视为同一种含义。
2. **JSON 合法不等于计划有效。**模型返回 JSON 后仍需 Pydantic 校验：至少一步、最多十步、编号从 1 连续递增、不接受未声明字段。业务上可执行、数据真实和工具确实存在还需进一步验证。
3. **上下文是按阶段构造的输入。**规划阶段看用户目标、工具说明和有限历史；执行阶段看当前步骤与前序结果；总结阶段看原始目标和各步结果。工具输出作为数据处理，提示词本身不能替代权限控制。
4. **历史截断要考虑工具协议。**规划当前过滤 tool 消息及带 tool_calls 的 assistant 消息，避免截断后残留孤立调用。普通 ReAct 的工具调用历史则需要保留调用与结果配对。
5. **执行状态与 Trace 用途不同。**Plan/PlanStep 表用于查询当前业务状态，Trace 保存发生过的事件。只有主执行器真正更新状态表，才形成持久化执行闭环。
6. **SQLAlchemy 事务需要明确归属。**当前每个 CRUD 写方法独立提交并在错误后 rollback；可恢复继续使用 Session，但跨多个写方法的业务操作并非原子事务。
7. **SQLite 的两种级联需要区分。**ORM 的 delete-orphan 与 SQL 的 ON DELETE CASCADE 不等同；后者需要连接启用 foreign_keys。增量 CREATE TABLE IF NOT EXISTS 不会升级已存在表的结构。
8. **校验失败要保存原因。**本次修复 StepResult 的反向条件：fail 必须带非空错误原因。内存 StepResult 使用 fail，数据库使用 failed，后续接入时需要显式映射。

## 已知边界

- Plan/PlanStep CRUD 尚未由 Model.plan_execute 调用；步骤结果仍保存在内存，重启不能恢复。
- ReAct 返回后目前无条件标记步骤 success，尚不能可靠识别业务失败；没有自动重规划、取消或步骤重试。
- Trace 已记录计划生成与解析失败，但最终汇总未完整采集 Trace，执行异常也未统一落库。
- step_no_base 使用计划序号偏移，多轮 ReAct 下 step_no 可能重叠；严格事件顺序应依据 sequence_no。
- ContextBuilder 中 base 构造方法仍为空；规划历史是全量查询再筛选，尚无 Token 预算和压缩。
- 本次离线验证不代表真实模型、MCP 联调或生产安全验证；登录仍缺少密码验证，不能用于真实用户数据。

## 自测与复习

运行 `uv run python -m unittest discover -s tests -v`。测试仅使用内存 SQLite 与模拟模型响应，覆盖计划编号、失败原因、CRUD 回滚、重复步骤约束、状态时间清理、级联删除、规划历史过滤和两步 Plan 执行。

- 为什么模型输出 JSON 后还需要 schema 和业务校验？
- 如果第二个步骤失败，计划状态、步骤状态、Trace 各应如何保存？
- 为什么“保存聊天历史”不能直接等同于“已实现 Agent 记忆”？
- 如何将一次步骤内的 ReAct 轮数与计划步骤编号区分？
- 如果进程在工具完成后、结果落库前退出，下一版如何避免重复执行？

建议下一步先连接计划持久化和执行状态，再完善失败传播、最终汇总 Trace 与恢复逻辑。

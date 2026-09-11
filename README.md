# Insurance Agent Demo

## 2026-09-11 开发进展：Plan 模式

当前主分支已在 ReAct、Trace 和 MCP 基础上增加 Plan-Execute：页面勾选 Plan 模式后，生成结构化计划、逐步调用 ReAct，最后汇总结果。普通模式继续使用 ReAct。

- `agent/context.py`：分别构建规划、步骤执行和最终汇总的上下文。
- `agent/plan/system_plan.py`：校验计划结构、连续步骤编号及步骤结果。
- `db/services/plans.py`、`plan_steps.py`：提供计划和步骤 CRUD、状态与时间字段、JSON 校验及异常回滚。
- `db/sqls/plan.sql`：为已有数据库新增计划相关表；这是增量建表脚本，不是 Alembic 迁移。

阶段边界：计划 CRUD 尚未接入 `Model.plan_execute`，目前步骤结果只保存在运行内存中；尚无断点恢复、自动重规划或完整的步骤失败判定。不能把“已有状态字段”视为“已完成持久化执行器”。本次提交不新增发布 tag。

离线验证（不调用真实模型或 MCP，不写入开发数据库）：

```bash
uv run python -m unittest discover -s tests -v
```

知识点与已知限制见 [Plan 模式学习笔记](docs/plan-execute-notes.md)。以下保留 V0.2.0 的早期版本说明，相关“尚未实现”描述仅适用于当时版本。

一个围绕 Agent 能力逐步演进的保险客服学习项目。当前版本聚焦基础 LLM 环境：在已有 Web、认证、会话和消息持久化基础上，接入 OpenAI 兼容模型，并搭建工具描述骨架。

## 当前版本

`V0.2.0` — 基础 LLM 环境

已完成：

- FastAPI + Jinja 服务端页面
- SQLite + SQLAlchemy 数据持久化
- 登录会话与聊天会话隔离
- 用户消息和助手消息持久化
- OpenAI 兼容模型客户端配置
- System Prompt 和历史消息组装
- 基于 Pydantic 的工具参数、结果模型与 Tool Schema 骨架
- 模型返回消息转换为内部 `Messages` 实体

本版本边界：

- 工具只完成定义和传递，尚未执行
- 尚未形成完整 Tool Call / Tool Result 循环
- 尚未统一捕获模型、工具与数据库异常
- 尚未实现上下文 Trace
- 用户认证用于学习项目演示，不作为本版本的学习重点

## 项目结构

```text
agent/
  llm/          模型客户端与消息转换
  tools/        工具定义和 Schema
db/
  services/     Chat 与 Message 数据访问
  entities.py   SQLAlchemy 实体
web/
  pages/        登录与聊天路由
templates/      Jinja 页面
```

## 本地运行

安装依赖：

```bash
uv sync
```

复制环境变量模板并填写模型配置：

```bash
cp .env.example .env
```

启动应用：

```bash
uv run python main.py
```

默认访问地址：`http://localhost:8082`

## 下一版本

`V0.3.0` 只完成三个目标：

1. 完整工具调用链路：解析参数、执行工具、保存 Tool Result、再次调用模型。
2. 错误捕获：统一处理模型、工具、参数校验和数据库错误。
3. 上下文 Trace：记录每轮模型输入、输出、工具调用、耗时和状态变化。

本阶段暂不扩展 RAG、长期记忆、多 Agent、复杂前端和生产级认证。

# 工程化实践：在保留现有 Agent 实现的前提下整理代码结构

日期：2026-09-13。基线提交：`7be8fe1`。这是渐进式结构重构，不是新的 Agent 范式，也不代表达到生产级。

## 1. 背景与目标

此前已实现工具装饰器、ToolSpec / Registry / Executor、MCP、Trace、Plan-and-Solve 与增量记忆。
问题不在于没有目录，而在于 Model 同时负责请求模型、编排任务、组装上下文、保存消息和记录 Trace。
新增能力时不断向同一入口加分支，容易出现数据类型混用和测试依赖遗漏。

本次目标：保留主要算法和 Web 调用入口，让“改哪项能力就去哪个模块”更明确。
不更换框架、不修改数据库表、不重写工具实现、不调整页面布局。

## 2. 改造前后

| 关注点 | 改造前 | 改造后 |
| --- | --- | --- |
| 普通对话与工具循环 | Model.run / react | ReactRunner；Model 转发 |
| 计划编排 | Model.plan_execute | PlanRunner；Model 转发 |
| 模型请求 | Model 和 simple_chat 分别创建客户端 | LLMClient.complete 统一配置与指标计算 |
| 消息转换 | Model 内部方法 | llm/messages.py 显式转换 |
| 上下文 | 查询数据库并混用 ORM 和 dict | 接收普通数据，返回 list[LLMMessage] |
| 记忆请求 | 自己创建另一个客户端 | 接收同一个 LLMClient；旧独立调用仍支持 |
| 生命周期 | 导入 Web 路由时创建 Model | lifespan 创建、关闭；Depends 取得共享对象 |
| 离线测试 | 只替换旧 Model 客户端，记忆链路遗漏 | 注入假客户端，防止意外构造真实客户端 |

## 3. 目录与阅读顺序

```text
agent/
  llm/
    models.py       原 Model 兼容入口，负责组装/转发
    client.py       模型请求、配置、耗时/用量，独立于数据库
    messages.py     ORM 消息与模型消息转换
    simple_chat.py  原函数名的兼容封装
  runners/
    react.py        普通对话与工具循环
    plan.py         生成计划、执行步骤、汇总
    results.py      执行结果与循环终止原因
  context.py        纯上下文组装
  memory/           原记忆算法，增加可注入模型依赖
  tools/            保留原有工具实现
  trace/            保留原有 Trace 实现
db/                 本次不迁移表或改造数据服务
web/app.py          资源的创建与释放
tests/              内存 SQLite + 假模型回归
```

建议按 models.py → runners/react.py → llm/client.py → runners/plan.py → context.py → tests 的顺序阅读。
对照 Git diff 时，先看旧 methods 搬到哪里，再看真正改变行为的少数行；不要把大段移动误认为全部重写。

## 4. 为什么这样拆

### 单一职责不是“一类只有一个方法”

判断依据是变化原因。更换模型配置应该改 client；修改计划执行应该改 PlanRunner。
把方法拆成许多小文件但仍互相依赖全局对象，并不会自然降低耦合。

### 使用组合，不引入多层继承

Model 组装 LLMClient、ReactRunner 和 PlanRunner。
PlanRunner 接收 ReactRunner，复用相同的工具注册表和 Trace 控制器。
构造函数传对象就是最简单的依赖注入，不必引入额外容器框架。

### 明确数据边界

数据库 Messages 用于存储；LLMMessage 是普通字典的类型约定。
ContextBuilder 不再创建“只是临时提示词、不会落库”的 ORM 对象。
TypedDict 只提供静态类型提示，不负责运行时校验；计划和记忆仍由 Pydantic 校验。
本次为降低变动，CompletionResult 仍包含 SDK response，Runner 的结果仍包含 ORM message，属于过渡设计。

### 谁创建，谁释放

Web lifespan 创建 Model，结束时关闭其模型客户端；MCP 关闭放在 finally 中。
注入的客户端不由接收方擅自关闭，而由创建它的调用方管理。
独立调用 simpleChat / simpleStructChat 会创建临时客户端，并在 finally 中关闭。

### 兼容入口允许渐进重构

Model.run、plan_execute、react、chat 仍可使用。
simpleChat、simpleStructChat 名字暂时保留。
ContextBuilder 改为纯数据接口，旧调用需要改成先查询、再传 history；项目内调用和测试已同步。
本次没有承诺保持所有私有属性、旧 monkeypatch 路径不变。

## 5. 与纯搬迁区分开的行为修正

1. 步骤上下文改用 model_dump(mode="json")，不再把每个结果序列化为 JSON 字符串后再次整体序列化。
2. ReactResult 增加 stop_reason，区分 completed 与 max_steps。
3. 达到步数上限的步骤记为 fail，停止后续步骤并汇总已知结果；汇总提示不再声称所有步骤均已完成。
4. 记忆也使用统一客户端的超时与 temperature 配置，不再依赖另一入口的隐式默认值。
5. 原有自定义 Registry 已正确传给执行器，本次保留并添加测试，不将其记为新修复。

completed 只代表模型停止请求工具，不等价于业务目标已经验证成功。完整失败分类与业务验收仍待建设。
非流式 output_tokens_per_second 是输出 token 数除以整次请求耗时，并不是纯解码速率，也没有首 token 指标。

## 6. 验证方法与边界

运行：

```bash
.venv/bin/python -B -m unittest discover -s tests -v
```

17 项离线回归覆盖计划结构、CRUD、工具协议历史过滤、计划正常执行、普通对话、
上下文对象格式、记忆成功/失败时的游标行为、计划解析/请求失败区分、
循环上限、计划停止、Registry 传递、指标计算和资源关闭。

所有数据库为内存 SQLite；模型和工具执行采用替身，没有启动真实 MCP，也没有使用真实模型或开发数据库。
不等价于真实模型质量评测、完整浏览器验收或生产负载测试。

## 7. 有意留到后续的工作

- db/services 与 Trace/Memory 中的 commit 仍未统一；后续以短业务操作为单位整理事务，不将网络等待放进长事务。
- Web 仍保存用户消息，并通过 persist_user_message=False 避免重复；后续可加入 ChatService 明确唯一入口。
- Plan/PlanStep CRUD 尚未接入执行器，没有断点恢复和自动重规划。
- 部分名称、SDK 返回类型、ORM 结果仍保留，以免扩大此次重构。
- 历史查询仍可能读取全量消息；后续再做 SQL 限制与 token 预算。
- 工具注册模块仍包含启动加载逻辑；不为目录整齐而一次全部拆散。
- 记忆和最终汇总尚未形成完整统一 Trace；这次统一的是请求入口和指标计算，并不代表所有指标已落库。
- 未完成 Router 和临时 ttest.py 是用户已有工作，本次不修改、不提交。

## 8. 用户实现与 AI 协助边界

用户已有成果：Agent 学习主线、现有工具/MCP/Trace/计划/记忆实现及此前修复；历史上已有 AI 协助，不能把所有基线代码都归为独立手写。
用户本次决策：要求保留实现、整理组织结构，并用前后对比学习工程方法。
本次 AI 协助：抽取 Runner 与统一客户端、调整数据边界和生命周期、补充回归测试、整理说明文档。
因此此次应记录为“AI 协助完成结构重构，用户通过阅读与复现掌握”，而不是“已独立掌握全部架构设计”。

## 9. 复习与能力落地

- 能说明 Model、LLMClient、ReactRunner、PlanRunner 各自不应该做什么。
- 能沿一次普通请求和一次计划请求找到模型调用、工具调用、消息保存的路径。
- 能解释为什么测试必须替换整个模型依赖，而不是只替换其中一个入口。
- 能区分 JSON 字符串与 JSON 对象，以及静态类型提示与运行时校验。
- 能独立增加一个失败路径测试，再尝试抽取一个小职责；不要立刻引入新架构框架。
- 下一次重构先问四件事：职责是什么、输入输出是什么、依赖由谁提供、副作用由谁负责。

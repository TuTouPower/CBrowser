# Task spec

## 背景

2026-11-10 intensive review 在 API、数据层与迁移方面列出一组一致性缺陷，adoption_decision 采纳为 A1、A2、A15、A17、A21、A23、A26、A28、A29、A31、A60：

- 迁移连接 pragma 顺序与 session 相反；control 恢复升级路径在提交前 publish。
- 错误契约残余不一致：部分 handler 缺必填 `message`，dict detail 整包嵌套与顶层字段重复，429 无稳定错误码，Gateway / Supervisor 错误形态各异且 Coordinator 丢弃下游原因。
- 代理改密会用当前配置为「仅绑定版引用」的 Profile 生成错误快照，使其永久无法启动。
- `display_number` 列可空、领域模型默认 1，同一数据缺陷三种表现。
- 分组 / 代理的 Idempotency-Key 后端不认；代理与分组表单无防重；Profile 创建锁基于 React 状态，弹窗在途可关闭重开再提交。
- `get_last_error` 读取即删除错误，收敛判定不看 config_version，新版启动失败可被一次 GET 抹掉。
- group / proxy 引用无服务层校验；reorder 接受子集产生重复 sort_order。
- 迁移守卫对空 alembic_version 放行，注释与实现矛盾。
- 分组 / 代理变更不跨客户端传播。
- 迁移中为历史混合形态保留的容错分支与不可逆 downgrade 违反零兼容。

## 契约区

### 范围

- A1：迁移连接先设 `busy_timeout` 再切 WAL。
- A2：control renew-upgrade 在事务提交成功后再 publish。
- A15：API 全部异常处理器输出统一 `ErrorResponse`（error / message / retryable，可选结构化 details），去除 detail 整包嵌套；429 映射为 `rate_limited` 并带 `Retry-After`；Gateway 与 Supervisor 采用同一错误结构；Coordinator 保留下游 `error` 与 `message` 写入 error_reason；重新生成 OpenAPI 与前端类型并同步前端消费。
- A17：代理改密时，只为当前配置引用该代理的 Profile 生成新配置版本；仅运行中绑定版引用的 Profile 只发 runtime 事件，不建版；frozen revision 取快照实际引用代理的 revision。
- A21：`display_number` 改为 NOT NULL，领域模型必填、无默认值；读路径遇 NULL 抛明确错误。
- A23：分组 / 代理的 create、update、delete 实现与 Profile 相同的 Idempotency-Key 语义；代理与分组写入口在请求在途时禁用；Profile 创建锁改为同步 ref，幂等键绑定到本次打开弹窗的草稿，关闭重开沿用同一键直到成功。
- A26：读取运行时错误不清除；错误只在同一 config_version 的实例成功达到 running 时清除；收敛判定绑定目标版本。
- A28：group / proxy 引用不存在返回字段级 422；reorder 要求全集，否则 422。
- A29：库中已有业务表但 alembic_version 为空或缺行时抛 `LegacySchemaError` 并给出重建指引；修正 `migrations.py`、`deploy.sh:69-73` 注释与 `docs/blueprint/supervisor.md:3` 过时陈述。
- A31：分组 / 代理写成功后经 SSE 发布变更事件，前端失效对应查询与 Profile 列表。
- A60：删除迁移 0004「列已存在即跳过」分支与 0003 的历史混合形态修补分支；全部 revision 的 `downgrade()` 抛出明确的不支持降级错误；不改变任何 revision 的 upgrade 产物结构。

### 非范围

- 不改网络事务（由 t054 删除，0003 相关表随之删除）。
- 不改代理端点模型与出口观测（t052）。
- 不重置 Alembic baseline。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：迁移在另一连接持有写事务时等待 busy_timeout 后完成切换，不立即返回 BUSY。
- [x] AC-002：control 恢复升级的事务提交失败时，SSE 订阅者收不到该次升级事件；提交成功时收到。
- [x] AC-003：API 所有错误响应都含 `error` 与 `message`，且不含与顶层重复的 detail 包；429 响应的 `error` 为 `rate_limited` 并带 `Retry-After`。
- [x] AC-004：Gateway 与 Supervisor 错误响应与 API 结构一致；Supervisor 返回的失败原因出现在 Profile 的 last_coordinator_error 中。
- [x] AC-005：Profile 绑定版引用代理 A、当前配置已改为代理 B 时，修改 A 的密码不会推进该 Profile 的配置版本；该 Profile 之后可正常启动。
- [x] AC-006：`display_number` 为 NULL 的行无法写入；领域模型缺少 display_number 时构造失败。
- [x] AC-007：分组 / 代理的 create、update、delete 以相同 Idempotency-Key 与相同参数重放时，返回首次结果且不产生重复记录；同键不同参数返回 409。
- [x] AC-008：代理表单、分组管理的写操作在途时，提交入口禁用；Profile 创建弹窗在途时关闭再打开并提交，不会产生第二个 Profile。
- [x] AC-009：旧版 running、新版启动失败时，多次读取运行时状态（REST 与 SSE 重连）都返回该错误，直到新版成功 running。
- [x] AC-010：创建或修改 Profile 时引用不存在的 group / proxy 返回 422 并指出字段；reorder 未提供全集时返回 422。
- [x] AC-011：有业务表但 alembic_version 为空的库启动时报 `LegacySchemaError` 与重建指引。
- [x] AC-012：一个客户端修改或删除分组 / 代理后，另一个已打开列表的客户端无需刷新即显示新状态。
- [x] AC-013：0004 在列已存在但定义不符时迁移失败而非静默跳过；任何 revision 的降级调用都失败并给出明确错误；全新库 upgrade 到 head 的结构与改动前一致。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试（迁移与 pragma 单测、错误契约结构测试、repository / service 单测、幂等重放集成测试、前端组件测试、SSE 集成测试、schema 对比测试）。

## 上下文区

- 来源：`docs/reviews/review_20261110_200842/adoption_decision.md` A1、A2、A15、A17、A21、A23、A26、A28、A29、A31、A60（审阅原文第 1、2、55–58、65、71、75–78、84、86–89、91、106–109 项）。2026-11-10 已抽验第 1 项（`migrations.py:81-82` 顺序相反）。
- 已定约束：已部署 revision 不改结构身份（memory no-legacy-data），故 A60 只删容错与降级，不改 upgrade 产物。

### 有意不测

- 同一 tick 双击绕过状态锁：以同步 ref 锁的单元测试覆盖锁语义，不做浏览器级时序复现。

### 测试策略

- 后端：每项触达生产代码的单元 / 集成测试；错误契约以 OpenAPI 结构与运行时响应双侧断言。
- 前端：防重与幂等键复用的组件测试；SSE 事件驱动的查询失效测试。
- 迁移：pragma 顺序、空 version 守卫、降级失败、全新库结构对比。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。

### 风险与回退

- 风险：错误契约改动牵动前端全部错误展示；以生成类型驱动，前端编译期发现不一致。
- 风险：代理改密影响集逻辑与 t052 的代理模型重构交叠；先合并者为准，后者 rebase 时保留 AC-005 测试。
- 回退：revert 实现 commit；`display_number` 增量迁移可回退。

### 依赖与约束

- 与 t052（代理）、t054（错误契约中的网络端点、迁移）、t058（前端 ProfileForm / 创建弹窗）存在文件重叠，按 `conflicts_with` 串行。
- 需增量迁移（`display_number` NOT NULL）。

### Finalization 时更新的 blueprint

- `docs/blueprint/conventions.md`：错误契约与幂等约定。
- `docs/blueprint/persistence.md`：迁移只前进、不支持降级；空 version 守卫。
- `docs/blueprint/domain.md`：代理改密影响集、display_number 必填。
- `docs/blueprint/frontend.md`：写操作防重与参考数据事件。
- `docs/specs/profile_management.md`、`docs/specs/proxy_management.md`、`docs/specs/runtime_lifecycle.md`：对应行为。

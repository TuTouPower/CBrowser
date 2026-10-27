# Task spec

## 背景

v2.3 需要把 Profile、运行期状态与页面连接分开，以持久配置和真实事件恢复替代旧进程内状态。本 task 在 t001 全部通过后建立独立新后端骨架，不处理现有用户数据迁移。

## 契约区

### 范围

- 新 Domain、Service、Repository、/api/v1 应用入口及空数据库初始化迁移；Profile 配置版本、标签、运行状态、Artifact 元数据、设置、运行事件和审计存储。保留计划15.2中仍有效的配置字段。不建立租约或持久 ViewerConnection。主写域为 src/backend/cbrowser/domain、services、adapters/database、api 与 src/backend/migrations、schemas/openapi，以及本 task 新测试；保留并扩展 src/backend/diagnostics.py 的结构化运行时诊断；运行状态模型包含 desired_state、observed_state、runtime_instance_id、config_version、failure_count、restart_blocked、last_exit_event_id。不改 Runtime Agent、Stream Runtime 或旧正式入口。

### 非范围

- 用户数据库迁移、旧路由删除、正式部署切换、登录和自动化凭证实现、Docker 调用、浏览器或媒体容器生命周期。不得以兼容层维护两套正式内部 API。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [x] AC-001：通过新 API 创建、读取、修改和删除 Profile；配置字段及标签在真实服务进程重启后完整保留，非法更新不改变已保存配置。

- [x] AC-002：配置修改产生可查询的不可变版本快照；重复幂等操作不产生重复 Profile 或重复状态转换，失败事务不留下半写数据。

- [x] AC-003：正常退出事件将目标与实际状态收敛为停止，异常退出保留运行意愿；重复事件不再转换状态，旧 runtime_instance_id 事件不能覆盖新实例状态。

- [x] AC-004：多个真实并发请求在数据库锁竞争时按忙等待策略完成或返回明确可重试错误，不丢配置、不留下未提交事务；事务期间不等待 Docker 或浏览器启动。

- [x] AC-005：新数据库可从空目录初始化并由独立 API 进程读取；通过导出的接口契约调用新接口并验证响应，正式现有数据目录与旧服务不被写入。

- [x] AC-006：独立 API 进程处理运行时事件时，诊断日志可机器解析并关联 Profile、实例和事件；保留既有诊断查询能力，不输出密码、Token、Cookie、剪贴板或输入文本。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试，使用独立 API 进程、真实 HTTP 与隔离 SQLite 文件；本 task 不调用 Docker、Chrome 或外部网络，不包含部署验收。

## 上下文区

- 来源：docs/v2_architecture_plan.md（2026-10-27 核对）；t001 为技术验证硬门禁，已完成并合入（执行 d7ee99c，集成 2fb32ba）

### 有意不测

- 迁移现有用户数据与正式环境发布：由后续独立迁移/发布 task 验收，本 task 只在全新隔离测试目录运行

### 测试策略

- 真实临时 SQLite 文件、事务回滚、重复/过期事件、并发 HTTP 和独立 uvicorn 进程重启；先红后绿。黑盒操作新 /api/v1 Profile 接口并重启服务，不能用 TestClient 存活代替持久化验证。旧测试继续运行，不就地修改旧预期。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 数据写入和退出事件语义以计划12、15章及 t001 验证结论为准：已由 t001/d006 与 d008 验证通过。API 离线落盘事件在恢复后可送达并收敛为 stopped，旧 runtime_instance_id 事件与重复 event_id 被拦截，多轮 reconcile 不误自启；Gateway 重启与信令断开不影响浏览器主进程。本 task 依据此契约建立数据模型与收敛逻辑。

### 风险与回退

- 风险：新旧字段映射、事件幂等与事务竞争会造成状态丢失；禁止将运行连接写成业务所有权。
- 回退：实验和新模块通过独立 worktree、数据目录及容器前缀验证；不覆盖现有用户数据、不切换旧正式运行入口。失败保留证据和当前分支，不迁移或删除旧链路。

### 依赖与约束

- t001 全部通过并冻结技术结论后才能 start。持久化约束按计划12.1显式启用 SQLite WAL 与 busy_timeout=5000；测试实际读取PRAGMA并结合并发HTTP验证，配置值不替代行为验收。公共索引与跨模块总览由主控在各 task 收尾阶段串行更新，实现 agent 只写本模块，不并发改公共控制面。

### Finalization 时更新的 blueprint

- docs/blueprint/persistence.md：配置、事件去重与数据库单写者边界；docs/specs/runtime_persistence.md：本 task 累积行为。公共 specs_index 由主控在 task worktree 收尾时串行更新。

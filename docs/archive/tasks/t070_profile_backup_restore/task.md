# Task spec

## 背景

从 t066/p080 分出完整备份恢复。README 已先 down 再 tar，真实缺口是 tar 不含 named volume 数据库及其与 Profile 状态的一致恢复；保证既有数据操作有可验证恢复能力，不新增身份模型迁移。

## 契约区

### 范围

- 备份包括 named volume DB（正确 SQLite backup）、Profile userDataDir、必要配置与凭据引用/恢复前提清单；停机并验证无实际写者后取得同一恢复点。
- 恢复在 staging 验证完整性/版本/空间，再成套切换；处理 DB+目录跨介质切换中断与恢复日志，失败保留旧完整恢复点。
- 隔离实例执行真实备份/恢复往返并修正文档；不在本 task 执行生产恢复。

### 非范围

- 用户已取消配额；不加入单/总存储、并发、时长配额，不再保留产品待决项。
- 不设计 IdentityBundle，不声称安全擦除；不把两次 rename 当作 DB+目录跨介质原子事务。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：完整备份同时包含可恢复 DB 与对应 Profile 状态/配置；恢复后 Profile 配置版本、cookie/localStorage 和登录态与该恢复点一致，不遗漏 named volume。
- [ ] AC-002：运行实例拒绝不安全文件快照；stopped 标志但存在实际容器/残留 runtime_instance_id 时不会无保护复制，恢复与启动互斥。
- [ ] AC-003：损坏、空间不足、数据库校验失败以及成套切换每个中断点都能恢复旧完整版本或完成新版本，不遗留 DB 与目录版本错配；原数据不被未校验内容覆盖。
- [ ] [deploy] AC-004：在隔离真实部署中执行备份→状态变化→恢复，验证配置、登录态和必要凭据恢复前提；指南所列命令能从 named volume 取得并恢复 DB。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001：可自动测试，触达生产函数或实际工具入口。
- AC-002：可自动测试，触达生产函数或实际工具入口。
- AC-003：可自动测试，触达生产函数或实际工具入口。
- AC-004：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。

## 上下文区

- 来源：2026-11-13 审阅复核：p080，原 t066 AC-006 与备份部分 AC-005；现有 deploy DB backup/restore 能力优先复用，不重复另起存储系统。原归档仍经 t066 导航到本 task。

### 有意不测

- 非范围中的新增产品功能不作为本 task 验收；已声明 AC 不豁免。

### 测试策略

- SQLite WAL/在线 backup、tar 目录与 manifest 完整性测试；跨 DB/目录阶段故障注入，不仅测 rename。
- 隔离 named volume + Browser 实际写入的往返恢复测试，生产数据不用作试验。
- 按 docs/blueprint/testing.md 的 doctor_cmd/test_cmd/blackbox_verify 执行；本次仅改 backlog，创建校验不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 现有 DB backup/restore 与 Profile 停机切换契约：UNVERIFIED-SPIKE，先演练已有工具与跨介质故障恢复协议，再实现完整一致恢复点。

### 风险与回退

- 风险：跨模块/制品或状态变更需按上述负向测试与 spike 验证；产品 BLOCKING 未消除不得实施。
- 回退：回退本 task 的完整实现 release；涉及数据先停写者并从已验证成套备份恢复，禁止仅降级数据库或以旧兼容分支兜底。

### 依赖与约束

- 硬依赖和冲突以 progress.md 的 task.py 调度字段为准；不把文件重叠当硬依赖。plan 仅输出图上候选，不能替代 preflight；产品 BLOCKING 必须先确认，SPIKE 先验证并回填。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md、docs/blueprint/testing.md：备份恢复点、写者排他与故障矩阵。
- docs/blueprint/security.md、docs/blueprint/decisions.md：备份凭据边界与恢复前提；同步 README/DOCKER_DEPLOYMENT。

# Task spec

## 背景

t081 既有缺陷（pending p138）：`tests/integration/test_font_sets_api.py` 在 `-n 4` 并行门禁下偶发 `sqlite3.OperationalError: database is locked`，隔离复跑全过。根因是 `src/backend/cbrowser/adapters/database/font_repository.py` 的 `apply_audit_verdict` 缺 `write_transaction(session)`（BEGIN IMMEDIATE），并发写冲突触发 SQLite WAL `SQLITE_BUSY_SNAPSHOT`。t077 第 4 轮门禁再次复现：`test_default_font_set_id_requires_integrity_ok` 在 commit（`font_repository.py:142`）时 `database is locked`，隔离复跑 3/3 通过。

## 契约区

### 范围

- `font_repository.apply_audit_verdict` 补 `write_transaction(session)` 包裹写操作。
- 补并发回归测试：多会话并发调用 `apply_audit_verdict`，断言无锁错误且 verdict 持久化。
- 全仓扫查同类缺 `write_transaction` 的写路径，逐项确认修复或论证无并发写暴露。

### 非范围

- 不改字体审计的业务语义（verdict 判定规则、默认集选择逻辑）。
- 不碰 t078 并发删除收敛竞态（已另登记 p139）。
- 不做部署验证（本 task 无 `[deploy]` AC）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：`apply_audit_verdict` 的全部写操作在 `write_transaction(session)` 内执行（读码确认 BEGIN IMMEDIATE 路径）。
- [ ] AC-002：新增并发回归测试：多会话并发调用 `apply_audit_verdict`，全部完成且无 `OperationalError` / `database is locked`，verdict 持久化后可读。
- [ ] AC-003：全仓扫查产出同类写路径清单：每条缺 `write_transaction` 的写路径或已补齐，或有书面论证说明无并发写暴露（清单写入 progress.md 或 findings）。
- [ ] AC-004：`test_font_sets_api.py` 全套隔离通过，且连续 3 轮 `-n 4` 并行复跑不再出现 `database is locked`。
- [ ] AC-005：p138 经 `pending.py close p138 --resolution resolved --fix-ref <task/commit> --write` 关闭。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- 全部 AC 可自动测试（AC-003 的“无并发写暴露”论证部分由审阅人工复核清单）。

## 上下文区

- 关联 spec：无
- 来源：p138（2026-11-19 登记；`docs/pending/p138_font_repository_write_transaction.md`）；t077 第 4 轮门禁证据 `~/workspace/cloud-task-logs/gate-t077-final3/logs/integration.log`（`font_repository.py:142` commit 时 `database is locked`）

### 有意不测

- 真实多进程/多容器并发写：云端无 Docker 环境，不测；单机多会话并发已覆盖竞态机制。

### 测试策略

- 先写并发回归测试复现锁错误（红），再修 `apply_audit_verdict`（绿）；扫查清单逐项回归；最后 3 轮 `-n 4` 复跑 `test_font_sets_api.py`。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。

### 风险与回退

- 风险：补事务可能改变写路径的异常语义（如部分写入变整批回滚）；扫查可能漏掉动态拼接的写路径。
- 回退：实现 commit 单独可 revert；回归测试先行，失败即停。

### 依赖与约束

- 无前置 task 依赖；基线为当前 main（t077 已合入，`14a44a8`）。
- 门禁跑全量时须 `TMPDIR` 落大盘并以 `flock ~/workspace/cloud-task-logs/gate.lock` 串行（本机 1.5 核）。

### Finalization 时更新的 blueprint

- 无。

---
tid: "t084"
slug: "font_repository_write_transaction"
title: "font_repository apply_audit_verdict 补写事务与并发回归测试"
status: "done"
branch: "t084_font_repository_write_transaction"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "1939aaac9dc74747d303cfd396eea4403791d8e7"
spec_source_sha: "1939aaac9dc74747d303cfd396eea4403791d8e7"
depends_on: ""
conflicts_with: ""
note: "来源：pending p138（t081 既有缺陷）。范围：src/backend/cbrowser/adapters/database/font_repository.py 的 apply_audit_verdict 补 write_transaction(session)（BEGIN IMMEDIATE），补并发回归测试（多会话并发调用断言无锁错误），并全仓扫查同类缺 write_transaction 的写路径。完成后用 pending.py close p138（--resolution resolved --fix-ref <task/commit> --write）。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- TDD 红：新增 `tests/unit/test_t081_font_catalog.py::test_concurrent_audit_verdicts_serialize_without_lock_error`（8 并发 adoption + 8 并发同 fence verdict，断言各恰好 1 个 True、无 OperationalError、verdict 持久化），未修复前失败为 `sqlite3.OperationalError: database is locked`（SQLITE_BUSY_SNAPSHOT），与 p138 一致。
- 修复：`src/backend/cbrowser/adapters/database/font_repository.py::apply_audit_verdict` 全体读写改走 `async with self._session_maker() as session, write_transaction(session)`（BEGIN IMMEDIATE）；显式 `session.commit()` 改为 `session.flush()`（IntegrityError 路径仍回滚返回 False，行为不变）。
- 绿：新测试连续 5 次通过；`test_t081_font_catalog.py` + `test_font_sets.py` + `tests/integration/test_font_sets_api.py` 共 34 passed。
- AC-004：`tests/integration/test_font_sets_api.py` 连续 3 轮 `-n 4` 各 7 passed，无 `database is locked`。
- AC-003 扫查（全后端 AST + 人工复核）：除本次修复点外，仅 3 处写操作在词法上位于 `write_transaction` 之外，且均为 helper（调用方全部在事务内）：`repository._record_operation_audit`（6 调用方全在事务内）、`control_service._get_or_create_row`（3 调用方全在事务内）、`session.write_transaction` 自身的 commit。`create_profile` 内的 `text()` INSERT/UPDATE 在 `write_transaction` 块内。另 2 个不可解析文件（`preview.py`、`runtime_agent/preview_capture.py`，Python 2 风格 except 语法）经 grep 确认只做文件预览、无 DB 写。无新增修复点。
- 门禁基线对照：unit 老基线 15 项（t063×12、t068×2、a16×1）；并行抖动形态已知（前端 5 秒超时、t078 并发删除间歇失败 p139）。
- 全量门禁（`~/workspace/cloud-task-logs/gate-t084-final/`，exit 1）：9 套件 8 过——protocol_drift_check 0、requirements_check 0、contract 0、integration 0（228 cases）、design_lint 0、design_check 0、frontend_test 0（718 cases）、frontend_build 0；unit 1：4 failed + 10 errors 共 14 项，全部在已知基线内（t063×12、t068×2；a16 本轮未败），2371 passed，零新增。首轮门禁曾因 worktree 缺 `.scratch/selkies_wheels` 与前端 `node_modules` 导致 environment/前端套件失败，已按既定办法补齐（主仓拷入 wheels + jpeginfo，`CBROWSER_GATE_VENV` 指主仓 venv，worktree 内 `npm ci`）后重跑通过；中途一次重跑被 SIGTERM 杀掉（153 秒，原因未查明、无残留进程），再次重跑完整通过。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round N (YYYY-MM-DDThh:mm:ss+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t000_code_f001|critical/important/minor|已修/遗留/撤回|一句话|文件:行 / pNNN / tid|

无 finding 时写“Round N 零 finding”。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：新并发回归测试 5/5 通过；`test_t081_font_catalog.py` + `test_font_sets.py` + `tests/integration/test_font_sets_api.py` 共 34 passed；`test_font_sets_api.py` 连续 3 轮 `-n 4` 各 7 passed，无 `database is locked`；全量门禁 `~/workspace/cloud-task-logs/gate-t084-final/` 9 套件 8 过（unit 仅 14 项已知基线 t063×12、t068×2，2371 passed）
- 黑盒：不适用——后端仓储写事务修复，无 UI 与部署变更；并发语义由单元回归测试与 `-n 4` 复跑覆盖
- review：Round 1 PASS，零 finding，AC 5/5 TICK-VALID（`review_general.md`）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- `apply_audit_verdict` 全体读写改走 `write_transaction`（BEGIN IMMEDIATE），并发 verdict 串行化；新增并发回归测试（红绿对照：原代码 3/3 失败 `database is locked`）；全仓扫查无其他缺失写事务的位点；p138 已关闭（fix-ref t084）；遗留：无（t078 并发删除竞态已另登记 p139，不在本 task 范围）

### 长期文档闭环

- specs_index: not_applicable: 本 task 为后端仓储写事务缺陷修复（font_repository.apply_audit_verdict 补 write_transaction），无长期 spec 变更；task.md 已写“关联 spec：无”。
- 在 active spec 的 front matter `tasks` 清单中登记当前 tid（`task.py specs list --json`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

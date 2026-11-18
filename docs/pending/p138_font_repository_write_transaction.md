---
pid: "p138"
slug: "font_repository_write_transaction"
status: "closed"
resolution: "resolved"
reason: "t084 修复：apply_audit_verdict 全体读写改走 write_transaction（BEGIN IMMEDIATE）；新增并发回归测试 5 次通过；test_font_sets_api.py 连续 3 轮 -n 4 各 7 passed，无 database is locked；全仓扫查无其他缺失写事务的位点"
fix_ref: "t084"
---
# p138 font_repository apply_audit_verdict 缺 write_transaction 致并发 SQLITE_BUSY_SNAPSHOT（t081 既有缺陷）

- 现象：`tests/integration/test_font_sets_api.py` 在 `-n 4` 并行下偶发 `sqlite3.OperationalError: database is locked`；`-n 0` 串行全套稳定通过，`-n 4` 5 轮复跑第 3 轮复现（2026-11-19 本地收尾定性，隔离复跑证据见 docs/handoff.md）。
- 影响：字体集审计裁决写入路径 `apply_audit_verdict` 与并发写事务冲突时偶发失败；与本批（p130/p136 等）无关，属 t081 既有缺陷，非回归。
- 根因：`src/backend/cbrowser/adapters/database/font_repository.py` 的 `apply_audit_verdict` 未走 `write_transaction(session)`（BEGIN IMMEDIATE），读后写升级与并发写事务冲突触发 SQLite WAL `SQLITE_BUSY_SNAPSHOT`。同类位点待修复时全仓扫查确认。
- 测试缺口：现有集成测试串行可过、并行仅概率复现；应补并发写回归用例（多会话并发调用 apply_audit_verdict 与其他写入，断言无锁错误）。
- 线索：复现命令 `pytest tests/integration/test_font_sets_api.py -n 4`（多轮）；定性记录在 docs/handoff.md 本地收尾段。
- 处理：t084；resolution=resolved；reason=t084 修复：apply_audit_verdict 全体读写改走 write_transaction（BEGIN IMMEDIATE）；新增并发回归测试 5 次通过；test_font_sets_api.py 连续 3 轮 -n 4 各 7 passed，无 database is locked；全仓扫查无其他缺失写事务的位点

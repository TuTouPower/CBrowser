# Task review t084（reviewer_focus: 通用）

- task：`t084_font_repository_write_transaction`
- spec：`docs/tasks/t084_font_repository_write_transaction/task.md`
- diff_anchor：`1939aaac9dc74747d303cfd396eea4403791d8e7`
- target：`git diff 1939aaac9dc74747d303cfd396eea4403791d8e7`
- round：1
- reviewed_at：2026-11-19T05:54:00+08:00

reviewed_scope: 27b9a04abcbffcca

## Findings

无 finding。本轮按 7 视角扫过 diff 全部内容（规格合规、实现正确性、安全、契约·类型、性能与资源、架构与可维护性、健壮性与可观测、测试可信与覆盖、文档一致性），未命中可报项。

本轮独立实测（不采信 progress.md 自述）：

- 读码：`src/backend/cbrowser/adapters/database/font_repository.py` 全文、`src/backend/cbrowser/adapters/database/session.py` 全文、新测试全文、`src/backend/cbrowser/services/font_set_catalog.py` 唯一调用点。
- 新并发测试自跑 5 次：5/5 通过；`tests/unit/test_t081_font_catalog.py` + `tests/unit/test_font_sets.py` 共 27 passed。
- 红绿对照：把新测试覆盖到 diff_anchor 原代码上复跑 3 次，3/3 失败，均为 `sqlite3.OperationalError: database is locked`（SQLITE_BUSY_SNAPSHOT），与 p138 现象一致，确认新测试是真回归测试而非假绿。
- AC-004 自跑：`tests/integration/test_font_sets_api.py -n 4` 连续 3 轮，各 7 passed，无 `database is locked`。
- AC-003 自扫：以祖先链精确的 AST 扫查全后端写操作（`session.add/delete/flush/commit/merge` 与 DML `execute`），另 grep 核对两个不可解析文件；结果见 AC-003 复验行。
- 门禁日志核对：`gate-t084-final/suites.tsv` 9 套件 8 过；unit 套件 4 failed + 10 errors，共 14 项，全部落在 `tests/unit/test_t063_patched_keyboard_behavior.py`（12 项）与 `tests/unit/test_t068_engine_artifact_pinning.py`（2 项），两文件均不在本 diff 内且均无 font 相关导入，属已知老基线；全部 10 份门禁日志中 `database is locked` 出现 0 次。

## 结论

- 本轮新发现：0 条
- 未进表的提示：全量门禁 exit 1 唯一原因是上述 unit 老基线 14 项（t063×12、t068×2），与本 diff 无关，不入 finding 表；`write_transaction` 的 `busy_timeout=5000` 为既有会话配置，并发 verdict 串行等待以此为上限，属既有约束而非本 task 引入的问题。
- 总体判断：diff 精确命中 p138 根因——`apply_audit_verdict` 全体读写进入 `write_transaction`（BEGIN IMMEDIATE），并发回归测试红绿对照成立，全仓扫查清单经独立复核闭合，p138 已关闭；无未解决 critical / important。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`src/backend/cbrowser/adapters/database/font_repository.py:120` 全体读写在 `async with self._session_maker() as session, write_transaction(session)` 内，`src/backend/cbrowser/adapters/database/session.py:17-29` 的 `write_transaction` 在 `begin` 事件里执行 BEGIN IMMEDIATE，退出时 commit；两处显式 `session.commit()` 已分别改为 `flush()`（:147）与删除（原 :159 行处），无旁路写操作。
- AC-002：TICK-VALID，re_verified。`tests/unit/test_t081_font_catalog.py::test_concurrent_audit_verdicts_serialize_without_lock_error` 用真实 SQLite 文件库与真实 `FontSetRepository`，8 并发 adoption 与 8 并发同 fence verdict 各恰好 1 个 True、无 `OperationalError`，`repo.get`（新会话）复核 verdict 持久化且 `state_seq == 2`；自跑 5/5 通过，覆盖到 diff_anchor 原代码上 3/3 失败且均为 `database is locked`。
- AC-003：TICK-VALID，re_verified。独立 AST 扫查：词法上位于 `write_transaction` 之外的写操作仅 3 处，且均为 helper——`src/backend/cbrowser/adapters/database/repository.py:159` `_record_operation_audit`（6 调用点 create/update/delete_group 与 create/update/delete_proxy 全部在事务内）、`src/backend/cbrowser/services/control_service.py:204-205` `_get_or_create_row`（3 调用点 `_claim/_handoff/_restore` 全部在事务内）、`src/backend/cbrowser/adapters/database/session.py:26`（`write_transaction` 自身的 commit）；全部 DML `execute`（含 `repository.py:224/232` 的 `create_profile` text INSERT/UPDATE）均在事务内；`preview.py` 与 `runtime_agent/preview_capture.py` 不可解析但 grep 无任何 DB 写词；与 progress.md 清单一致，无新增修复点。
- AC-004：TICK-VALID，re_verified。自跑 `tests/integration/test_font_sets_api.py -n 4` 连续 3 轮各 7 passed；门禁 integration 套件 exit 0，全部 10 份门禁日志中 `database is locked` 出现 0 次。
- AC-005：TICK-VALID，re_verified。`docs/pending/p138_font_repository_write_transaction.md` 实读：status closed、resolution resolved、fix_ref t084（task 引用，符合 AC-005 的 `<task/commit>` 口径），reason 与修复内容一致。

coverage = 5 / 5

verdict: PASS

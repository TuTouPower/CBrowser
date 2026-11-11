# Task review t002（reviewer_focus: 测试）

- task：`t002_v2_backend_foundation`
- spec：`docs/tasks/t002_v2_backend_foundation/task.md`
- diff_anchor：`d3ca80b0141c19a715a90c71ba2f5862c1c79711`
- target：`git -C '<repo>_t002' diff d3ca80b0141c19a715a90c71ba2f5862c1c79711`
- round：2
- reviewed_at：2026-10-28T03:35:25+08:00

reviewed_scope: bfeffb3d43a6d56d

## Round 2 (2026-10-28T03:35:25+08:00)

## 7视角正交审查

- 安全：已覆盖的运行事件（`emit_runtime_event_log` 白名单过滤）、输入校验（422 错误体去敏）及已分类 SQLite 异常处理（IntegrityError 下响应与物理日志均未泄漏 SQL 绑定参数及密码/Token，符合 d015 边界说明）；测试断言明确核查敏感字符串不存在于响应与服务物理日志中。扫描未发现安全断言漏洞。0 finding。
- 正确性：测试断言覆盖 Profile 完整 24 项历史配置字段与标签 CRUD 回读、不可变版本快照、退出事件状态收敛（正常退出收敛 stopped，异常退出保留 running，重复事件幂等，陈旧实例拦截）及幂等冲突判定（409 Conflict）。断言直接基于真实 SQLite 存储回读与 HTTP 状态码。扫描未发现正确性缺口。0 finding。
- 契约·Breaking：`test_exported_openapi_schema_matches_live_app` 深度比对实时 FastAPI app 与 `schemas/openapi/cbrowser_v1.json`；集成测试中所有 HTTP 响应均由 `jsonschema` 对照导出组件模式严格校验。扫描未发现契约破坏或伪造校验。0 finding。
- 性能·资源：`test_ac004_sqlite_busy_timeout_contention_and_recovery` 验证 WAL 模式与 `busy_timeout=5000`，1.5s 独占写锁时 HTTP 请求忙等待完成（1.4s~4.5s），>5.0s 锁超时准确返回 503 Retry-After；`test_wal_reader_parallelism_while_write_lock_held` 验证普通读（BEGIN）在外部持有写锁（BEGIN IMMEDIATE）时不被阻塞。扫描未发现资源泄露或死锁隐患。0 finding。
- 架构·可维护性：依赖关系清晰分层，Domain 为独立纯模型，Service 协调 Repository 与 Domain，API 在 composition root 装配数据库连接与服务，Repository 内部写事务均采用 `BEGIN IMMEDIATE` 显式串行化，普通只读查询采用标准 `BEGIN`；测试无任何内部 mock，均在外部边界执行。扫描未发现架构倒置或 mock 误用。0 finding。
- 健壮性·可观测：`test_ac003_and_ac006_runtime_events_convergence_and_diagnostics` 真实解析服务端物理输出的 `RUNTIME_EVENT_JSON:` 行；5 轮并发非交叠 PATCH 验证无更新丢失；分类异常处理器准确区分 IntegrityError (409) 与 DatabaseLockError (503)。扫描未发现吞异常或未观测盲区。0 finding。
- 测试·文档·规格：19 个单元测试与 9 个真实子进程集成测试直接对齐契约区 AC-001 至 AC-006；全部使用真实临时 DB 与 uvicorn 独立子进程执行；无跳过标记（.skip）、无恒真断言、无 `# type: ignore`，无迁就实现改测。扫描未发现规格违背。0 finding。

## Findings

（无）

## 结论

- 前轮 finding 复核：Round 1 执行期间前审查会话因越过只读边界被外部中断，未产出有效报告；本轮为 Round 2 完整独立审查
- 改测方向复核：无（本次提交的 19 项单元测试与 9 项真实子进程集成测试均为全新交付，无迁就实现的改测行为，无既有测试被弱化或删除）
- 本轮新发现：0 条
- 未进表的提示：`src/backend/cbrowser/api/app.py` 中引用了已废弃的常量名称 `HTTP_422_UNPROCESSABLE_ENTITY`（Starlette 建议平滑迁移至 `HTTP_422_UNPROCESSABLE_CONTENT`），存在轻微运行时 DeprecationWarning，不破坏契约与测试行为
- 总体判断：所有 6 条 AC 均具备真实可信的自动化测试覆盖；测试通过独立 uvicorn 进程、真实 HTTP 请求、隔离 SQLite 文件与并发线程锁竞争执行验证；无 mock 伪造、无恒真/弱化断言等危险模式，判定 PASS
- 系统性 follow-up：无

### AC 复验方式

- AC-001：`re_verified`（独立复验 `tests/integration/test_v2_api_subprocess.py::test_ac001_and_ac005_crud_restart_and_empty_dir_init` 与 `tests/unit/test_domain_and_repository.py::test_profile_crud_and_full_legacy_fields_roundtrip`，验证完整 Profile CRUD、非法字段校验拦截、服务子进程退出并重启后完整回读 24 项配置字段及标签）
- AC-002：`re_verified`（独立复验 `test_ac002_immutable_snapshots_and_idempotency_conflicts`、`test_immutable_config_version_snapshots_include_tags` 及并发事务测试，验证相同 Idempotency-Key 重复请求幂等返回、异构 Payload 或不同目标 Profile 返回 409 Conflict、不可变版本快照在服务重启后仍可回读、并发非交叠字段 PATCH 5 轮无丢失更新）
- AC-003：`re_verified`（独立复验 `test_ac003_and_ac006_runtime_events_convergence_and_diagnostics` 与 `test_runtime_events_convergence_and_exit_contract`，验证正常退出收敛为 stopped、异常退出保留 running 意愿、重复退出事件去重、陈旧 instance 退出事件被拦截、主动 stop 后迟到 crash 事件不复活容器）
- AC-004：`re_verified`（独立复验 `test_ac004_sqlite_busy_timeout_contention_and_recovery` 与 `test_wal_reader_parallelism_while_write_lock_held`，验证 PRAGMA busy_timeout=5000 生效、1.5s 独占写锁时 HTTP 请求忙等待并在 5s 内成功返回 201、>5.0s 独占写锁准确超时返回 503 Retry-After、锁释放后自愈无悬挂事务、普通读取操作在写事务进行期间不被阻塞）
- AC-005：`re_verified`（独立复验 `test_ac001_and_ac005_crud_restart_and_empty_dir_init` 与 `test_exported_openapi_schema_matches_live_app`，验证空目录数据库自动初始化、独立 API 进程通信、HTTP 响应经 OpenAPI Schema 校验完全吻合、导出的静态 OpenAPI Schema 与实时 FastAPI 实例深度一致）
- AC-006：`re_verified`（独立复验 `test_ac003_and_ac006_runtime_events_convergence_and_diagnostics`、`test_ac006_db_constraint_integrity_error_no_secret_leak_in_logs` 及关键字参数化测试，验证运行时结构化 JSON 诊断日志被完整解析，密码/Token/Cookie/剪贴板等敏感信息严格脱敏，含 busy/locked 关键字的 IntegrityError 准确返回 409 且服务器物理日志未泄漏 SQL 绑定参数）

coverage = 6 / 6 = 1.0 (100.0%)

verdict: PASS

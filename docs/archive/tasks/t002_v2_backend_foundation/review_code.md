# Task review t002（reviewer_focus: 代码）

- task：`t002_v2_backend_foundation`
- spec：`docs/tasks/t002_v2_backend_foundation/task.md`
- diff_anchor：`d3ca80b0141c19a715a90c71ba2f5862c1c79711`
- target：`git -C '/Users/karson/kar/code/CBrowser_t002' diff d3ca80b0141c19a715a90c71ba2f5862c1c79711`
- round：Round 2
- reviewed_at：2026-10-28T03:33:48+08:00

reviewed_scope: bfeffb3d43a6d56d

## Round 2 (2026-10-28T03:33:48+08:00)

### 前轮状态与独立审阅说明

前轮 Round 1 因审查者误操作违反只读边界被外部监管中断，未留下有效审阅结论与报告。本轮为全新的 Round 2 独立代码审查，基于完整 7 视角体系以及 `d3ca80b0141c19a715a90c71ba2f5862c1c79711` 锚点 diff 进行穷尽核验。

## Findings

无 blocking finding（critical / important 均为 0 项，minor 0 项）。

## 评审维度核验结果（7 视角正交体检）

1. **安全（Security）**

    - 扫描状态：已扫过，无 finding。
    - 证据与分析：Pydantic `Field` 严格限制各字段长度与格式边界；SQLAlchemy ORM 采用参数化绑定，杜绝 SQL 注入；FastAPI 422 验证处理器（`src/backend/cbrowser/api/app.py:171-188`）对报错进行清洗，剔除原始输入回显，防止报错回显敏感注入载荷；结构化诊断日志 `emit_runtime_event_log`（`src/backend/diagnostics.py:267-297`）实施白名单字段投影与非标准 ID 单向不可逆哈希清洗（`_sanitize_id`），防止注入令牌作为 ID 泄密。经 `test_ac006_db_constraint_integrity_error_no_secret_leak_in_logs` 验证，分类后的数据库异常处理不向物理日志泄漏 SQL 绑定参数或敏感词（限定在 d015 划定的已分类异常与结构化事件边界内，不作全未知异常无界泛化断言）。

2. **正确性（Correctness）**

    - 扫描状态：已扫过，无 finding。
    - 证据与分析：`ProfileRepository.consume_runtime_event`（`src/backend/cbrowser/adapters/database/repository.py:594-696`）严格按退出码状态机收敛：`exit_code == 0` 收敛目标与观测状态为 `stopped`，`exit_code != 0` 保留既有 `desired_state`、递增 `failure_count` 且达 3 次置 `restart_blocked = True`，`test_runtime_events_convergence_and_exit_contract` 验证通过；`ProfileService._handle_db_error` 针对 `IntegrityError` 严格按类型映射，且判断锁状态时通过 `(code & 0xFF) in (5, 6)` 与 `sqlite_errorname` 双重判定，彻底消除此前因参数含 `busy` / `locked` 文本误报 503 的缺陷，`test_ac006_duplicate_tags_with_busy_and_locked_keywords_return_409` 验证通过。

3. **契约·Breaking（Contract & Breaking Changes）**

    - 扫描状态：已扫过，无 finding。
    - 证据与分析：`schemas/openapi/cbrowser_v1.json` 与 FastAPI live 导出的 OpenAPI 契约经 `test_exported_openapi_schema_matches_live_app` 深度逐字段断言完全一致；接口模型均声明于 `cbrowser/domain/models.py`，无隐式 `Any` 透传；本 task 主写路径均在 `/api/v1` 及独立新模块，未修改现有旧接口或外部调用路径，无 breaking change。

4. **性能·资源（Performance & Resources）**

    - 扫描状态：已扫过，无 finding。
    - 证据与分析：SQLite 强制开启 `PRAGMA journal_mode=WAL`（`src/backend/cbrowser/adapters/database/session.py:48`），普通读事务统一使用默认 `BEGIN`，写事务由 `write_transaction`（`session.py:18-27`）显式执行 `BEGIN IMMEDIATE` 排他锁，彻底杜绝写时并发升级引发的死锁，写操作串行化执行；`test_wal_reader_parallelism_while_write_lock_held` 验证在持写锁期间普通读取耗时约 11ms 不受阻塞；ORM 关联关系配置 `lazy="selectin"`（`models.py:87,93,100,106`），有效避免 N+1 查询。

5. **架构·可维护性（Architecture & Maintainability）**

    - 扫描状态：已扫过，无 finding。
    - 证据与分析：结构依赖单向清晰：`domain` 独立包含业务纯模型与值对象；`adapters/database` 依赖 `domain` 实现 ORM 映射与持久化仓储；`services` 使用 `repository` 与 `domain` 编排业务流程与异常归一；`api` 依赖 `services` 并作为 composition root（`app.py:50-59`）装配数据库引擎与依赖注入。单向依赖无循环。

6. **健壮性·可观测（Robustness & Observability）**

    - 扫描状态：已扫过，无 finding。
    - 证据与分析：`DatabaseLockError` 统一映射为 `HTTP 503` 并附带规范响应头 `Retry-After: 1` 与 `retryable: true`；并发写锁竞争与超时恢复经 `test_ac004_sqlite_busy_timeout_contention_and_recovery` 验证；事件去重与幂等处理在仓储层与 API 异常处理器双重兜底，未捕获异常收敛于 500 且不泄漏堆栈详情。

7. **测试·文档·规格（Tests, Documentation & Specs）**

    - 扫描状态：已扫过，无 finding。
    - 证据与分析：19 项单元测试与 9 项真实 HTTP 独立子进程集成测试全部覆盖范围；`docs/specs/runtime_persistence.md` 与 `docs/blueprint/persistence.md` 详尽记录持久化、状态收敛与单写者边界契约；`specs_index.md` 对应注册完整，文档与实现规格完全匹配。

## 规格合规逐项核验（AC 覆盖）

- **AC-001**：实现完整。`ProfileRepository` 与 `/api/v1/profiles` 支持 CRUD；配置字段与标签完整映射并在进程重启后完全持久化；Pydantic `ProfileConfig` 与 `ProfileUpdateRequest` 实现强类型校验，非法输入拒绝并不污染已保存状态。
- **AC-002**：`profile_config_versions` 表由 `ProfileRepository.create_profile` 与 `update_profile` 自动写入不可变版本快照，包含完整 `config` 与关联 `tags`；通过 `AuditEventModel` 与请求全维度签名（`action` + `entity_id` + `sig_hash`）保证幂等，重复请求返回一致状态且不增加状态转换；`write_transaction` 上下文确保异常时完全回滚（通过 `test_actual_db_constraint_failure_rollback` 验证）。
- **AC-003**：`consume_runtime_event` 实现正常退出（`exit_code == 0`）将 `desired_state` 与 `observed_state` 均收敛为 `stopped`；异常退出（`exit_code != 0`）保持现有 `desired_state`，将 `observed_state` 置为 `stopped`，递增 `failure_count` 且达 3 次阻断自启（`restart_blocked = True`）；通过 `RuntimeEventModel` PK 物理去重；比对当前 `runtime_instance_id`，陈旧实例事件记录审计但不改变当前运行时状态。
- **AC-004**：SQLite 显式启用 `PRAGMA journal_mode=WAL` 与 `PRAGMA busy_timeout=5000`；所有写操作由 `BEGIN IMMEDIATE` 独占串行保护，普通读使用 `BEGIN` 并行不阻塞；锁竞争超时准确捕获并映射为可重试的 `HTTP 503`（带有 `Retry-After: 1` 响应头与 `retryable: true` JSON 体）；事务期间纯为本地数据库原子操作，无外部耗时依赖等待。
- **AC-005**：`run_database_migrations` 保证从空目录自动创建并由 Alembic 迁移至最新 8 张业务表；FastAPI 独立进程及 `/api/v1` 路由按 OpenAPI 导出契约严格对齐；测试与运行路径使用隔离目录，不写现有旧数据目录。
- **AC-006**：`diagnostics.py` 中的 `emit_runtime_event_log` 仅提取白名单字段输出结构化 JSON 日志（`cbrowser.events`），使用非对称 ID 消毒（`_sanitize_id`）与枚举校验（`_sanitize_reason`）；全局异常处理对 `IntegrityError` 与 `DBAPIError` 进行脱敏处理，杜绝底层 SQL 参数及日志泄密。

## 结论

- 前轮 finding 复核：前轮无有效 finding。
- 本轮新发现：0 条。
- 未进表的提示：
    - 文件物理行数提示（仅作规模观察，按规范文件长度本身不阻断）：
        - `src/backend/cbrowser/adapters/database/repository.py`（777 行，聚合承载 8 张业务表仓储）。
        - `src/backend/cbrowser/api/v1/router.py`（621 行，路由声明与参数注入）。
        - `tests/integration/test_v2_api_subprocess.py`（816 行）。
        - `tests/unit/test_domain_and_repository.py`（675 行）。
    - 圈复杂度提示：`ProfileRepository.update_profile` 承载各可选补丁字段合并校验，近似 CC 约为 11，逻辑线性且分支明确，无状态不一致或分支遗漏缺陷。
- 总体判断：所有 6 条 AC 均已真实完整实现，7 个正交维度体检均通过且有确凿代码与测试证据支撑。
- 系统性 follow-up：无

## AC 复验方式

- AC-001：`re_verified`，通过 `verify.sh` 中 `test_profile_crud_and_full_legacy_fields_roundtrip` 以及真实子进程测试 `test_ac001_and_ac005_crud_restart_and_empty_dir_init`，验证 Profile 增删改查、服务重启保留以及非法更新保持原样。
- AC-002：`re_verified`，通过 `test_immutable_config_version_snapshots_include_tags`、`test_ac002_immutable_snapshots_and_idempotency_conflicts` 及 `test_actual_db_constraint_failure_rollback`，验证不可变配置快照、幂等重放防重及事务回滚无半写。
- AC-003：`re_verified`，通过 `test_runtime_events_convergence_and_exit_contract` 与 `test_ac003_and_ac006_runtime_events_convergence_and_diagnostics`，验证正常退出收敛、异常退出保留意愿、重复事件幂等与旧实例事件拦截。
- AC-004：`re_verified`，通过 `test_sqlite_pragmas_wal_and_busy_timeout`、`test_wal_reader_parallelism_while_write_lock_held` 与 `test_ac004_sqlite_busy_timeout_contention_and_recovery`，验证 WAL 读写并发、排他写锁竞争返回 503 重试头及锁释放后无事务泄漏。
- AC-005：`re_verified`，通过 `test_eight_tables_exist`、`test_exported_openapi_schema_matches_live_app` 及 `test_ac001_and_ac005_crud_restart_and_empty_dir_init`，验证空目录数据库自动迁移、OpenAPI 契约深层一致性及隔离目录运行。
- AC-006：`re_verified`，通过 `test_ac006_db_constraint_integrity_error_no_secret_leak_in_logs`、`test_ac006_duplicate_tags_with_busy_and_locked_keywords_return_409` 与结构化日志断言，验证脱敏日志输出、ID 哈希清洗与 SQL 异常日志无密码/密钥泄漏。

coverage = 6 / 6 (100%)

verdict: PASS

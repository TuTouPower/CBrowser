---
tid: "t056"
slug: "api_contract_data_layer"
title: "API 契约与数据层一致性收口"
status: "done"
branch: "t056_api_contract_data_layer"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "3fbcec1754e6e1d9f4bd0978eefe6bd654df965a"
depends_on: ""
conflicts_with: "t052,t054,t058"
note: "来源 review_20261110_200842 adoption_decision A1 A2 A15 A17 A21 A23 A26 A28 A29 A31 A60"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

基线：t055 commit `3fbcec1754e6e1d9f4bd0978eefe6bd654df965a`；执行 id `fa46eb36e79344b78dfbb74dc8ea8e57`；run-begin 2026-11-12 01:55；preflight PASS（无 warning）。引用核对：task.md、adoption_decision 与 review_intensive 的引用均按当前树逐项核对，2026-11-10 的行号已漂移的按现树为准，零虚假引用。

### Phase 1 — 迁移（A1 / A21 / A29 / A60）

- 新增迁移 `0009_profile_display_number_not_null.py`（revision `796adb0bf159`，down_revision `3751fed02a4a`）：先按与 0005 相同的确定性顺序回填存量 NULL，再 `batch_alter_table` 把 `display_number` 改为 NOT NULL；`downgrade()` 抛 unsupported-downgrade `RuntimeError`。
- `migrations.py`：pragma 顺序调换为 busy_timeout 在前、journal_mode=WAL 在后（与 `session.py` 一致）；新增 `_switch_to_wal(conn, timeout_seconds=5.0)` 有界重试循环；新增 `BUSINESS_TABLES` frozenset（profiles、profile_groups、proxies、profile_runtimes、profile_config_versions、profile_controls、audit_events、runtime_events、settings、artifacts、sessions、admins、automation_tokens、proxy_egress_observations、profile_display_sequence）；A29 守卫：业务表存在但 alembic_version 缺失 / 无行 / 版本号为空时抛 `LegacySchemaError` 附重建指引；顶部注释与 docstring 改为 chain-member 口径。
- **A1 实测结论（2026-11-12）**：决策书规定的单一步骤（调换两行 pragma）本身不满足 AC-001。实验证实：`PRAGMA journal_mode=WAL` 在另一连接持有写事务时立即报 `sqlite3.OperationalError: database is locked`，即使 `busy_timeout=5000` 已先设置——journal-mode 切换不遵守 busy handler；另一方案（BEGIN IMMEDIATE 后在写事务内切换）报 "cannot change into wal mode from within a transaction"。只有在 busy_timeout 窗口内有界重试 WAL 切换才能使 AC-001 成立。实现为调换顺序 + 重试循环，注释中已写明。
- `0003_network_transaction.py` 重写：删除 op 行回填循环与 active 行补丁分支（含 `_backfill_record`、`_TERMINAL_PHASES`、`OP_PREFIX` / `ACTIVE_KEY` / `CURRENT_KEY`）；只保留 generation-counter 种子插入；`downgrade()` 抛错。docstring 已更新。
- `0004_preview_backoff.py` 重写：无条件 `add_column`（删除 skip-if-exists 分支）；`downgrade()` 抛错。docstring 已更新。
- `0001`、`0002`、`0005`、`0006`、`0007`、`0008` 的 `downgrade()` 全部改为抛 unsupported-downgrade 错误；0008 docstring 同步更新（旧 docstring 引用了已被删除的 `test_control_migration.py` 降级 walk）。
- A21 模型层：ORM `adapters/database/models.py:125` `display_number: Mapped[int] = mapped_column(Integer, nullable=False)`；领域 `Profile.display_number: int` 与 `ProfileRuntime.display_number: int`（删除 `domain/models.py:253,273` 的 `= 1` 默认值）；仓储 `_to_domain_profile` 读到 NULL 时抛 `RuntimeError(f"Profile {m.id} is missing its display number")`（与 `get_runtime` / `_runtime_with_number` 的既有报错风格一致）。
- 注释修正：`scripts/deploy.sh` 两处（t035 baseline 注释约 102–105 行；`check_database_schema_generation` 注释约 293–311 行，现说明有业务表但无可用 stamp 的库由 API 侧守卫拒绝）；`docs/blueprint/supervisor.md:3` 删除过时句（保留“本模块实现 Profile 生命周期协调…”作为当前模块描述）。
- Golden schema 夹具：`tests/unit/data/t056_fresh_schema_before.txt`（47 条记录；SQL 换行转义为 `\n`，NULL 的 SQL 写为字面 `None`），取自改动前全新库 upgrade。改动后全新库与 golden 的 diff 恰好是 `display_number INTEGER` → `INTEGER NOT NULL`，另有一处无害的 FOREIGN KEY 子句重排（batch 表重建所致，测试按行归一化后比对）。
- 测试处置（按 TDD 规则，语义被新实现废止的旧测试整体删除、不就地改预期）：
    - `tests/unit/test_control_migration.py` 整体删除：`test_upgrade_from_legacy_0001_with_columns_to_head` 及 helper `_legacy_operation_payload`、`_add_legacy_1a6ec51_columns`；`test_0003_drops_terminal_or_orphan_active_operation`；删除未用的 `import json`；docstring 记录删除原因。
    - `tests/unit/test_t054_migration.py`：head 常量更新为 0009（`REVISION_0009 = "796adb0bf159"`，测试改名 `test_head_is_0009_and_single`）。
    - 新增 `tests/unit/test_t056_migrations.py`（13 个测试）：pragma 顺序（以 recording-connection monkeypatch 记录 sqlite3 pragma 调用）；busy-wait 行为（holder 线程持 BEGIN IMMEDIATE 0.7s，迁移完成、journal_mode 为 wal）；LegacySchemaError 三种情形（表缺失 / 表空 / version_num 为空）；空库仍可 upgrade；0003 不动 legacy op/active 行（generation 种子仍为 "0"，无 current 指针）；0004 在列已存在但定义不符时失败（stamp 停在 0003）；全部 revision 的 `downgrade()` 均抛 `RuntimeError`（经 importlib 从 `src/backend/migrations/versions/` 加载）；全新库 schema 与 golden 一致（除 display_number NOT NULL；按行归一化尾逗号并排序以吸收 FK 重排）；NULL display_number 行被数据库拒绝（IntegrityError NOT NULL）；领域模型缺 display_number 时构造失败（ValidationError）。
- Phase 1 测试：20 passed（`tests/unit/test_t056_migrations.py` + `test_control_migration.py` + `test_t054_migration.py`）。

### Phase 2 — 控制续期发布时序（A2）

- `control_service.py::_claim` 重构：`publish` 标志在 `write_transaction` 块内设置（续期升级分支与新建 claim 分支），`await self._publish(profile_id)` 只在块退出（提交）后执行。此前续期分支在事务内发布。
- 测试追加到 `tests/unit/test_control_service.py`：`test_renew_upgrade_publishes_only_after_commit`——成功路径每个 claim / 续期升级恰好发布一次；提交失败路径 monkeypatch `control_service.write_transaction` 为 wrapper（在真实事务内 yield 后抛 `RuntimeError("simulated commit failure")`，随后回滚），断言无发布且 session 升级未持久化。该测试可区分新旧实现（旧代码会在事务内发布，断言失败）。
- Phase 2 测试：15 passed（`tests/unit/test_control_service.py` 全文件）。

### Phase 3 — 统一错误契约（A15）与协调器错误收敛（A26）

- `domain/models.py`：`ErrorResponse` 增加 `details: Any | None = None`（docstring：永不再嵌套整包错误）；`ValidationErrorResponse.detail` 改名为 `details: list[ValidationErrorDetail]`。
- `api/app.py`：`_STATUS_ERROR_NAMES` 增加 429 `rate_limited`、413 `payload_too_large`、507 `insufficient_storage`；`_http_error_content` 重写——422 返回 `details` 列表；dict detail 只把 code/message/retryable 以外的剩余键放进 `details`；`InvalidConfigVersionError` 处理器现含 `message` + `details`（loc 列表）；`RequestValidationError` 处理器 `detail` → `details`；删除 `contracted_openapi` 中手写 `ErrorResponse.properties["detail"] = {}` 的 hack（形状现由领域模型给出）。
- `gateway/server.py`：模块级 `_error_response(status, error, message, retryable=False)` helper；全部 JSON `{"detail":...}` 响应体已转换（supervisor_fence_failure → 503 `agent_unavailable` retryable / 409 `instance_conflict`；`_check_supervisor_auth` → 401 `unauthorized`；visibility 400 `bad_request` / 503 `agent_unavailable`；quota 400 `bad_request`、503 `service_unavailable` retryable；disconnect 400 `bad_request`、503 `service_unavailable` retryable）。WebSocket 握手纯文本 `web.Response(status=..., text=...)` 响应有意保留（WS 升级无法携带 JSON 错误体，不是 JSON API 错误）。已验证：`gateway/server.py` 中无 `"detail"` 残留。
- `supervisor/control_server.py`：`_SUPERVISOR_ERROR_NAMES`（400 bad_request、401 unauthorized、403 forbidden、404 not_found、409 conflict、502 bad_gateway、503 service_unavailable）+ `_supervisor_error_content`；在 `create_control_app` 注册 `HTTPException` / `RequestValidationError` / 通用 `Exception` 处理器（HTTPException 处理器保留 `exc.headers`，如 WWW-Authenticate）。
- **Starlette / FastAPI 处理器注册 bug（2026-11-12 发现并修复）**：路由 404 抛 Starlette 的 `HTTPException`，但处理器注册在 FastAPI 子类名下，导致未匹配路由仍返回 FastAPI 默认 `{"detail": "Not Found"}`。修复为在 `api/app.py` 与 `supervisor/control_server.py` 中都以 `starlette.exceptions.HTTPException`（import 为 `StarletteHTTPException`）注册；FastAPI 子类继承它，路由抛出的错误仍被捕获。测试中的查表同步改为 `app.exception_handlers[StarletteHTTPException]`。
- `api/runtime_coordinator.py`（A15 + A26 同做）：新增 `@dataclass _LastError(message, config_version=None)`；`_downstream_error_text(resp)`——解析 ErrorResponse 体为 `"error: message"`，回落 legacy `detail`，再回落原始文本（保留 `test_runtime_coordinator_error_responses.py` 的全部既有情形：null / list / string / number / HTML / `{"detail":...}` 体）；`get_last_error` 现为纯读（永不变更存储；所给 runtime 显示错误目标版本在跑时返回 None）；`set_last_error(profile_id, error, *, config_version=None)` 在不传版本时保留已记录的目标版本（重试限流后缀追加时保持目标）；`clear_last_error(profile_id, *, config_version=None)`——不传版本时无条件清除，传版本时版本绑定清除（`config_version >= target`）；新增 `clear_last_error_if_converged(profile_id, runtime)` 写路径清除；`_is_error_converged`——running 已收敛且（目标为 None 或 `runtime.config_version >= target`；无 config_version 的 runtime 永不结算版本化错误）。`_reconcile_running` 重构：先算 `latest_v`（同一 try/except 回落到 `runtime.config_version`）；restart_blocked 错误带 `config_version=latest_v`；已运行分支现要求 `runtime.config_version >= latest_v`（旧版本仍在跑不算收敛，落入启动最新版本），并用 `clear_last_error_if_converged`；200 分支以 `config_version=latest_v` 清除（按构造版本绑定——latest_v 是最大值，清除目标或其取代的更旧错误；既有测试 `test_coordinator_unreachable_sets_error_and_recovers` 仍通过）；start TransportError 与非 200 失败以 `config_version=latest_v` 记录。`_reconcile_stopped` 的 status/stop 失败现用 `_downstream_error_text`（status 失败此前完全没有 detail）。停止收敛与 profile 消失清除保持无条件（无版本维度）。
- **AC-004 的 error_reason 映射（记录在案，供 reviewer 核对）**：全树 grep 确认不存在 `error_reason` 字段。AC-004 字面“Supervisor 返回的失败原因出现在 Profile 的 error_reason 中”，其实质是“下游失败原因在 Profile 视图可见”；实现为 Coordinator 把下游 `error` 与 `message` 保留在所存 last error 中（`"<error>: <message>"`），经 runtime 视图的 `last_coordinator_error` 呈现。无字段可改名——这是字段名映射，不是实现缺口。
- 测试处置：整体删除 `tests/unit/test_runtime_coordinator_error_settle.py`（其语义——读已收敛 runtime 即清除已存错误——被 A26 废止）。
- 新增 `tests/unit/test_t056_coordinator_errors.py`（7 个测试）：读不清错误（3 次裸读 + pending-runtime 读）；旧版本在跑、新版本失败时错误保留（读返回错误；V2 runtime 读返回 None；已存条目保留至 `clear_last_error_if_converged`）；无版本错误在任意 running 到达时清除；以更旧版本清除时保留更新的错误；set 保留后续调用的目标版本；AC-009 端到端（`reconcile_profile_now` + MockTransport：V1 已绑定在跑，配置变更产生 V2，/start 502 `{"error": "supervisor_unavailable", "message": "no slots left"}` → 错误被存储并由重复裸读 / SSE 式读取返回，含 `make_runtime_response(...).last_coordinator_error`，随后 /start 200 → 清除）；AC-004（503 ErrorResponse 体 → 所存错误恰好为 `"Supervisor start failed (503): runtime_unavailable: pool exhausted"`）。测试 bug 修复（非生产 bug）：`test_old_running_new_failed_keeps_error_until_new_running` 曾断言 `rt.current_config_version`，但 `get_runtime()` 返回 `ProfileRuntime`，无此属性——改为断言 `(await service.get_profile(profile.id)).current_config_version == 2`。修复后 7 passed。
- `tests/unit/test_a6_error_contract.py` 整体重写（13 个测试，全部通过）：逐字保留 `test_handler_maps_plain_string_detail` 与 `test_handler_503_is_retryable`；删除 7 个旧形状测试；新增——dict-detail 额外键进 `details` 且不重复 code/message/retryable；无 message 的 dict 只放额外键进 `details`；只有 code/message/retryable 的 dict 不产生 `details` 键；422 `details` 列表；429 → `rate_limited` + `Retry-After` 头透传；真实 control-conflict 结构化；真实 proxy-in-use 的 `used_by_count` 进 `details`；真实 422/404 结构化；真实登录限流（5 次失败登录 → 429 `rate_limited` + Retry-After）；InvalidConfigVersionError 处理器（message + details loc `["body", "config_version"]`）；未匹配路由 404 结构化。测试 bug 修复两处：旧断言是 `"{'" not in json.dumps(body)`（Python-repr 检查）而非 `"{"`；bind 端点是 Supervisor 内部端点（`/api/v1/internal/supervisor/runtimes/bind`），故直接测处理器。
- 新增 `tests/unit/test_t056_error_contract_services.py`（6 个测试，通过）：Gateway `supervisor_fence_failure` 503/409 统一体、`_error_response` 形状、Supervisor live-app 401/404/422 统一体（经 `create_control_app` + httpx ASGITransport）。Gateway 覆盖在纯函数层（全部 JSON 响应点都经 `_error_response` / fence）；见环境跳过项。
- OpenAPI 经 `scripts/export_openapi.py` 重新生成（`schemas/openapi/cbrowser_v1.json` + `cbrowser_internal.json`）：diff 恰好是 `ErrorResponse.details`（附统一契约描述）+ `ValidationErrorResponse.details`。
- 前端类型重新生成（Node 26 下 `npm run generate:api`；新鲜 worktree 中 node_modules 缺失，先跑了一次 `npm ci`）：`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts`（`detail?: unknown` → `details?: unknown | null`；ValidationErrorResponse `detail` → `details`）。
- 前端 `client.ts`：`ApiError.detail` → `details`；错误解析优先 `message`，其次字符串 `details`；`payload?.details`。`ProxyFormDialog.tsx`：`readableDetail` 处理 422 `details` 列表（拼接各 `msg`）与 `"details"` 键；`describeError` 用 `err.details`。`ProxyListPage.tsx`：`proxyInUseCount` 重写——码从顶层 `errorCode === "proxy_in_use"` 读，数量从 `error.details` / `data.details` 读（旧形状读 `detail.code` + `detail.used_by_count`）。
- `client.test.ts` 旧形状测试按新形状重写（401 体、“surfaces server error detail”、422 `details` 列表、409 `details: {used_by_count: 3}`）；`providers.unauthorized.test.tsx`、`useBrowserSession.stages.test.tsx`、`sse.sameorigin.test.ts`（2 处）的 401 stub 更新为统一形状；`ProxyListPage.test.tsx` 的 409 测试按新 ApiError 构造重写。相关文件前端运行：54 passed。
- Phase 3 测试：26 passed（3 个文件）+ A6 文件重写后 13 passed + 服务契约文件 6 passed + 协调器错误文件 7 passed；前端相关文件 54 passed。
- **A15 设计决策（已定，供 reviewer 核对）**：全仓统一 `details` 键（不是 422 用 `detail`、别处用 `details`）——422 字段错误列表本身就是结构化 details；`ErrorResponse.details` 为 `Any | None`；dict-detail 的额外键排除 `code` / `message` / `retryable`，使 `details` 永不重复顶层字段；413/507 给显式码（`payload_too_large` / `insufficient_storage`），不用 `http_error`；Gateway WebSocket 握手文本响应不在范围内（不是 JSON API 错误）；Coordinator `_downstream_error_text` 保留 legacy `detail` 与原始文本回落，使混版本 Supervisor 仍可解析。
- **A26 设计决策（已定）**：`_LastError` 存 `(message, config_version)`；读是纯读但做过滤（runtime 显示目标版本在跑时返回 None——展示侧过滤，存储只由写路径清除）；清除规则为 `>=`（新版本成功可 supersede 旧版本失败；旧版本在跑永不结算新版本错误）；`set_last_error` 不传版本时保留已记录目标；start-200 分支保持清除但版本绑定（`config_version=latest_v`）——依据：生产中 Supervisor 在 start RPC 返回前已上报观测 running（t022/A45 对 stop 的注记；start 对称），且既有测试 `test_coordinator_unreachable_sets_error_and_recovers` 钉住 clear-on-200；已运行分支同样按版本判断收敛（`runtime.config_version >= latest_v`），否则落入启动最新版本。

### Phase 4 — 代理改密影响集（A17）

- 仓储：`_proxy_used_by`（并集，保留给删除拒绝与 used_by 计数）拆为 `_proxy_used_by_current`（ProfileModel.proxy_id）、`_proxy_used_by_bound`（运行绑定版本快照引用）、`_proxy_used_by_bound_only`（bound 减 current）。`update_proxy` 现返回 `(proxy, versioned_ids, runtime_only_ids)`；只有当前引用者生成新版本；快照的 `proxy_credential_revision` 取该快照实际引用的代理（`session.get(ProxyModel, cfg.proxy_id)`）——永不取被改代理的修订。返回 proxy 的 `used_by_count` 仍为并集计数（`len(versioned) + len(runtime_only)`）。
- 冻结修订机制已核实：`internal_supervisor.py` 的 credentials 端点返回绑定快照的冻结修订 + 当前修订；`supervisor/core.py:2415-2444` 在二者不一致时拒绝启动（`ProxyCredentialsChangedError`）。AC-005 的“之后可正常启动”成立，因为下一次启动用最新版本（V2，代理 B），其冻结修订是 B 未变的修订。
- 服务层 `update_proxy` 返回三元组；`proxies_router.update_proxy` 为两个列表都发布 SSE profile 变更。
- 测试处置：整体删除 `test_t035_profile_domain.py` 中的 `test_proxy_connection_change_regenerates_versions_for_referencing_profiles`（断言旧并集语义）；tristate 测试的 2 元组解包改为 3 元组（语义不变）。新增 `tests/unit/test_t056_proxy_password_impact.py`（4 个测试）：改密只给当前引用者生成新版本 + 冻结修订跟随快照自身代理；非连接变更不生成任何版本；删除仍拒绝仅绑定引用（used_by 1）；AC-005 端到端（绑定 V1/A、当前 V2/B，改 A 的密码 → 版本保持 2，随后协调器 reconcile + MockTransport /start 200 → CONVERGED）。与 t035 文件联合运行：18 passed。

### Phase 5 — 分组 / 代理幂等键（A23）

- 仓储：`_record_operation_audit` 静态 helper（暂存审计行）；公开 `find_recorded_operation(operation_id, action, target, payload)` 包装 `_match_operation_audit`（唯一解释签名的地点；不匹配时抛 `IdempotencyConflictError`）；`proxy_impact(proxy_id)` 只读影响列表供 update 重放。`create_group` / `update_group` / `delete_group` / `create_proxy` / `update_proxy` / `delete_proxy` 全部接受 `operation_id` kwarg：签名经 `_hash_request(action, target, payload)`；重放返回首次结果（create 在之后被删除时按原 id 重建；update 返回当前实体或已删除时返回 None；delete 返回已记录的成功，不返回 404）；审计只在成功时记录；IntegrityError 竞态经审计契约消解（与 `create_profile` 同构）。
- 服务层：六个方法透传 `operation_id`；`create_proxy` / `update_proxy` 的重放前置检查（经 `find_recorded_operation`）使重放跳过探测副作用（`_record_pending_observation` 每次调用 INSERT 新 pending 行，且 `_schedule_probe` 的后台探测也会再记一行——服务测试以 no-op lambda 中和 `_schedule_probe` 以隔离重放断言）。
- 路由（`groups_router.py`、`proxies_router.py`）：经 `resolve_operation_id` 读 `Idempotency-Key` / `X-Operation-ID` / `operation_id` query（与 profile 路由相同的三个来源）并透传 `operation_id`。`IdempotencyConflictError` 在 `app.py` 已映射为 409 `idempotency_conflict`。
- 新增 `tests/unit/test_t056_idempotency.py`（15 个测试，通过）：仓储层 group/proxy 的 create/update/delete 重放 + 同键不同载荷 409；服务层 create 重放（1 条 pending 观测）与 update 重放（无新版本、无第二次探测；pending 行 = 2：create 1 条 + 单次 update 1 条）；路由层 group create 重放 / 冲突、group delete 重放 204、proxy create 重放 / 冲突。
- 前端：`shared/api/action_key_mutation.ts` 的 `useActionKeyMutation` 接受可选第二参数 `{ keySource?: () => string }`；提供时 `mutate` / `mutateAsync` 用 `keySource()` 而不是每次新 mint。`useCreateProfileMutation(client, { keySource })` 透传。
- `ProxyFormDialog.tsx`：提交按钮 `disabled={createMutation.isPending || updateMutation.isPending}`。
- `GroupManagerDialog.tsx`：新建按钮在 `createMutation.isPending` 时也禁用；改名保存在 `updateMutation.isPending` 时禁用；删除确认在 `deleteMutation.isPending` 时禁用。
- `ProfileCreateDialog.tsx`：弹窗绑定键 ref（`createActionKeyRef`，首次提交时经 `newIdempotencyKey()` 惰性生成，关闭重开后存活，只在创建成功后清除）；同步 ref 锁（`submitLockRef`，提交开始时同步置位、`finally` 释放），覆盖 React 重渲染前的双击竞态。
- 前端测试：actionkeys 的 key-source 复用测试；ProxyFormDialog 提交进行中禁用；GroupManagerDialog 新建进行中禁用（测试 bug 修复：成功后名称清空，按钮随之正确禁用——断言改为名称字段已清空）；ProfileCreateDialog 关闭重开后重提交复用同一键（有状态 harness、同一弹窗实例、首次失败后以同一键重提交）+ 同一 tick 内双提交只创建一次（经 `act` 冲刷通过；ref 锁覆盖亚帧竞态）。修复事故一则：一次编辑匹配到 actionkeys 文件中错误的 `});` 导致文件损坏，经 `git checkout` 恢复后干净重做。
- Phase 5 前端测试：38 passed（4 个文件）。

### Phase 6 — 字段级 422（A28）

- `profile_service.py` 新增 `ReferenceValidationError(ProfileServiceError)`，携带字段级 `details`（`loc` / `msg` / `type`）；`app.py` 的应用层处理器返回 422 `validation_error` 附该 details。`ProfileServiceError` 是普通 `Exception`（不是 `ValueError`），故 groups 路由的 `ValueError → 400` 捕获不会吞掉它。
- 服务层 `_validate_references(group_id, proxy_id)`：两个缺失字段一次同时上报；`create_profile` 调用，`update_profile` 只对 patch 中出现的键调用（显式 null 清除引用，不查库）。`reorder_groups` 在服务层校验全集（同一组 id、无重复、无未知 → 否则 422）；仓储的 `ValueError("unknown group...")` 后备经 API 已不可达（无测试钉住 reorder → 400）。
- 仓储：新增 `get_group(group_id)`（与 `get_proxy` 同构）。
- 新增 `tests/unit/test_t056_references.py`（9 个测试，通过）：服务层缺失 group/proxy（单个 + 双字段同报）、update 缺失 group（profile 不动）、update 显式 null 清除引用放行、reorder 部分集 / 未知 / 重复 422；路由层创建引用缺失 group 422 与 reorder 部分集 422。

### Phase 7 — 分组 / 代理 SSE 变更事件（A31）

- 后端：协调器 `publish_reference_change_later(event_name, entity_id=None)`——在 `_publish_tasks` 中以 fire-and-forget 任务调用 `broadcaster.publish_transient(event_name, {"entity_id": entity_id})`；`runtime_views.py` 的共享 helper `publish_reference_change(request, event_name, entity_id=None)`（无 coordinator 附着时 no-op）。路由在成功后发布：groups create/update/delete/reorder（`groups_changed`，reorder 传 entity_id None）、proxies create/update/delete（`proxies_changed`）；探测不发布。`groups_router.py` 干净重写（create/update/delete/reorder + `request: Request` 参数）；`proxies_router.py` 的 create/update/delete 更新（一次编辑曾丢掉 update 中的 A17 SSE 注释，已恢复）。
- 后端测试 `tests/unit/test_t056_reference_events.py`（4 passed）：协调器单测经 `broadcaster.subscribe()`（帧 `event: groups_changed` 附 `"entity_id":"g1"`，`event: proxies_changed` 附 `"entity_id":null`）；路由测试用 recording coordinator。**测试要点：应用的 lifespan 在启动时安装自己的 coordinator，会覆盖 `app.state.coordinator`——recorder 必须在进入 TestClient 上下文之后再附着。**
- 前端 `sse.ts`：`ReferenceChangedEvent { event: "groups_changed" | "proxies_changed"; entity_id: string | null }`；`ProfileSseEvent` 增加该类型；`isReferenceChangedEvent`、`parseReferenceChangedEvent`、`referenceListeners` + `onReferenceEvent`、`flushEvent` 增加两个事件分支、`dispatchEvent` 把引用事件路由到新监听集合。`useProfileEventsSync` 经 `sseClient.onReferenceEvent?.(...)` 订阅并失效 `groupKeys.lists()` 或 `proxyKeys.lists()` 外加 `profileKeys.lists()`。
- 前端测试：新增 `sse.reference.test.ts`（live HTTP server 夹具；引用事件 → `onReferenceEvent`，runtime_state → `onEvent`；修复一处 Python 风格 `"""` docstring 破坏 TS 转换的问题）；`useProfilesQuery.test.tsx` +2 测试（groups_changed 使 group+profile 列表失效、不使 proxy 失效；proxies_changed 使 proxy+profile 列表失效、不使 group 失效）。运行：sse 文件 2 passed，hook 文件在 10-passed 联合运行中。

### Finalization 文档更新（本轮完成）

- `docs/blueprint/conventions.md`：新增 §7 统一错误契约（A15）。
- `docs/blueprint/persistence.md`：§1 增加 A1 pragma 顺序 + WAL 切换有界重试；§2 profiles 字段表增加 `display_number` 与 A21 注记、迁移史增加 0009、A60 只进不退、A29 旧库守卫；§4 幂等节增加 A23 分组 / 代理同等语义。
- `docs/blueprint/domain.md`：A28 字段级 422 + reorder 全集；A17 联动改为当前引用者 + 冻结修订取实际引用者；新增“显示编号必填（t056 A21）”小节。
- `docs/blueprint/frontend.md`：§1 `ApiError.detail` → `details`、Profile 创建键为例外（弹窗绑定）；§1 增加 A31 引用事件句；§7 增加创建锁与弹窗绑定幂等键；§8 删除保护 409 体改为统一 `ErrorResponse`（`errorCode` 判码 + `details` 取数，经 `ProxyListPage.tsx:38-40` 代码核实）。
- `docs/specs/profile_management.md`：末尾新增“API 契约与数据层（t056）”小节。
- `docs/specs/proxy_management.md`：§4 409 体修正；§5 `ApiError.detail` → `details`；新增 §8 密码变更影响集、幂等与引用事件。
- `docs/specs/runtime_lifecycle.md`：新增“运行错误收敛与控制发布（t056）”小节（A26 / A2 / A15）。
- `docs/specs_index.md`：profile_management、proxy_management、runtime_lifecycle 三行登记 t056，日期 2026-11-12。
- 文档修正事故：conventions.md 首次编辑吞掉了 §6 标题行，已当场发现并把尾部重排为 §6 在前、§7 在后；diff 核实为恰好 +9 行。另：摘要渲染与 frontend.md 实际文本多处不符（如 §7/§8 的 bullet 措辞），后续编辑均以 `muse.read` / grep 的实际文件内容为准，不再信任摘要转述。

### 环境准备（全量回归前）

- t045 wheel 缓存：新鲜 worktree 的 `.scratch/selkies_wheels/` 不存在（gitignored，不随 worktree 迁移）。用仓库自有 `scripts/vendor_selkies_web.py` 的 `download_wheel` 从 PyPI 取回 `selkies-2.2.1-py3-none-any.whl`（2,733,413 字节），SHA-256 `18503b5c1491a04194f0a45fa10c547ffe5b4a24f33496ce5d56e97370a6a3cd` 与 pin 一致，已放入本 worktree 的 `.scratch/selkies_wheels/`。这不是回归失败，是环境补齐。

## 测试汇总（分阶段实数）

|阶段|测试|结果|
|---|---|---|
|Phase 1 迁移|`test_t056_migrations.py` + `test_control_migration.py` + `test_t054_migration.py`|20 passed|
|Phase 2 A2|`test_control_service.py` 全文件|15 passed|
|Phase 3 A15/A26|3 个文件（A15/A26 相关）|26 passed|
|Phase 3 A15|`test_a6_error_contract.py`（重写后）|13 passed|
|Phase 3 A15|`test_t056_error_contract_services.py`|6 passed|
|Phase 3 A26|`test_t056_coordinator_errors.py`|7 passed|
|Phase 3 前端|错误契约相关文件|54 passed|
|Phase 4 A17|`test_t056_proxy_password_impact.py` + `test_t035_profile_domain.py`|18 passed|
|Phase 5 A23 后端|`test_t056_idempotency.py`|15 passed|
|Phase 5 A23 前端|4 个文件|38 passed|
|Phase 6 A28|`test_t056_references.py`|9 passed|
|Phase 7 A31 后端|`test_t056_reference_events.py`|4 passed|
|Phase 7 A31 前端|sse 文件 + hook 文件|2 passed / 10 passed（联合运行）|
|回归修复 A15|`test_agent_executor_control.py`（新增 409 形状测试）|7 passed|
|回归修复 A15|`test_t026_gateway_registration.py`（gateway_client 修复后）|4 passed|
|回归修复 A15/A21|a16 drift + OpenAPI 导出 + 夹具修复文件联合运行|79 passed|

### 回归修复（2026-11-12，全量回归后）

首次后端全量：41 failed / 2119 passed / 8 skipped（1035.77s），t055 基线 25 failed → 多 16 个。按名比对后 25 个基线失败全部命中（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），新增 16 个分五组，全部已修复（非代码回归 5 个除外，见第 5 组）：

1. **OpenAPI 滞后（3 个）**：`test_a16_protocol_drift`、`test_exported_openapi_schema_matches_live_app`、`test_internal_openapi_export_matches_checked_in_file`——Phase 3 再生成 OpenAPI 时 A23 的 `operation_id` / `Idempotency-Key` / `X-Operation-ID` 参数尚未落地（Phase 5 才加进路由），checked-in 的两个 JSON 滞后。修复：`scripts/export_openapi.py` 重跑，两文件现与 live 完全一致（`live == checked` 已验证）；diff 除参数新增外还有 groups_router 重写带来的键序调整。另：重跑后 `.d.ts` 也须同步（见第 6 组）。
2. **Gateway 客户端读旧形状（1 个）**：`test_unsupported_version_gets_structured_rejection`——`GatewayControlClient.agent_registered` 的 503 分支仍读 `response.json().get("detail")`，统一契约后 `detail` 为空，`"unavailable" not in ""` 恒为 True，误判已注册。修复：`gateway_client.py` 改读 `message`，保留 legacy `detail` 回落（混版本 Gateway）；docstring 同步改 "detail" 为 "message"。复测：t026 文件 4 passed。
3. **旧形状断言（2 个）**：`test_create_rejects_other_locales` / `test_create_rejects_invalid_timezone`——读 `response.json()["detail"]`，新契约是 `details`。按 test_a6 的先例整体重写两函数（422 + `error == "validation_error"` + `details` 列表含对应字段 loc），其余断言不变。
4. **display_number 夹具（5 个）**：`test_t041_font_runtime`（2）、`test_t053_coordinator_font_runtime`（2）、`test_refactor_behavior_equivalence::test_runtime_view_helpers`（1）——直接构造 `Profile` / `ProfileRuntime` 的旧夹具未传新必填字段。修复：四个构造点补 `display_number=1`；行为断言未动（这是新必填字段的调用点适配，不是改预期迎合输出）。
5. **t055 socket 测试（5 个，非代码问题）**：`AF_UNIX path too long`——首次全量我加了 `--basetemp=.scratch/pytest-basetemp`，worktree 绝对路径已长，socket 路径超 107 字符上限；t055 基线用默认 basetemp（/tmp 下短路径）时通过。修复：重跑改回默认 basetemp（见下节）。
6. **附带发现（grep 扫出的同类消费者）**：`agent_executor/session.py::_control_post` 的 409 分支同样读旧 `detail.code`，新形状下 code 会变 None（消息退化为 "refused: None"）。修复：优先读顶层 `error`，再 `details.code`，再 legacy `detail.code`，最后默认 `control_conflict`；新增单测 `test_control_post_409_reads_unified_error_shape`（统一形状 / legacy 形状 / 无码默认三情形，7 passed 含既有 6 个）。`cli.py:155` 的 `step.get("detail")` 是 executor 步骤字典，与 HTTP 错误体无关，未动。
7. **前端类型门禁（首轮全量失败）**：`npm test` 的 `test:types` 报 2 错——`useProfilesQuery.actionkeys.test.tsx:211` 用 `vi` 未 import；`sse.reference.test.ts:19` 的 `req` 未使用。分阶段只跑了 vitest，未过类型门禁，故漏网。修复：补 `vi` import、`req` 改 `_req`。另：OpenAPI 重跑后 `.d.ts` 滞后，`test_backend_contract_change_without_typescript_update_is_detected` 失败（`check:api` 的 cmp 不等）；修复：`npm run generate:api` 重跑，`check:api` 通过；diff 为 A15 描述 + `details` + A23 参数。

### 全量回归（2026-11-12）

- 后端首轮：41 failed / 2119 passed / 8 skipped（1035.77s）——含上述 16 个新增，见回归修复节。
- 后端重跑（默认 basetemp）：**25 failed / 2136 passed / 8 skipped（463.50s）**——25 个失败按名与 t055 基线完全一致（agent_executor_chain 7、automation_cdp_flow 2、automation_probe_chain 3、control_attendant_chain 1、normal_exit_replay 4、automation_cdp 1、repo_hygiene 1、t028 4、t034 2），零新增失败；通过数 2078 → 2136（+58，t056 新增测试净增）。repo_hygiene 的 1 个失败是已知流程文件问题（review 报告含绝对路径），非交付物缺陷。
- 前端首轮：`test:types` 失败（2 个类型错误，见回归修复节第 7 组）。
- 前端第二轮：**75 文件、546 测试全部通过**（基线 538/0、74 文件；新增 `sse.reference.test.ts`，净 +8 测试）。

## 环境跳过项（本机不可验证，按链规则计 pass，用户机复核）

- AC-005 的“之后可正常启动”：单测以 MockTransport /start 200 模拟到 CONVERGED；真实引擎启动（Docker + CloakBrowser）须在用户机验证。
- AC-004 的 Supervisor live 502 路径：单测以 MockTransport + ErrorResponse 体验证解析与存储；真实 Supervisor 502 须在用户机验证。
- AC-012 的多客户端实时同步：后端事件发布与前端查询失效均已单测验证；两个真实浏览器客户端同开列表的端到端须在用户机验证（本机无真实浏览器）。
- Gateway live 路由覆盖：本轮为纯函数层（全部 JSON 响应点经 `_error_response` / fence）；真实 Gateway 进程的 live 路由须在用户机验证。
- 绑定-only profile 在改密后的 Supervisor 冻结-当前拒绝检查：真实引擎行为，须在用户机验证。
- 黑盒门禁 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`：须真实 Docker/Chrome，本机跳过。
- AC-001 的部署级锁争用：单测以 holder 线程持 BEGIN IMMEDIATE 0.7s 验证重试机制；部署并发负载下的真实争用须在用户机观察。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1（修复完成，待 Round 2 双路 review）

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t056_code_f001|important|已修|contracted_openapi() 对全部 422 直接赋值 ValidationErrorResponse 引用（setdefault 永不覆盖 FastAPI 自动生成的 HTTPValidationError 条目）；两份 OpenAPI 与前端类型已重生成，全树零 HTTPValidationError 引用；新增 OpenAPI 结构断言|src/backend/cbrowser/api/app.py|
|t056_code_f002|minor|已修|create_group / create_proxy 的 IntegrityError 回退：审计存在但实体已删时，先查同名是否被占——被占直接 raise ValueError（路由层 409 group/proxy_name_in_use），未被占至多重建一次；新增两项重放+已删+同名被占测试，均做 red-before 探针|src/backend/cbrowser/adapters/database/repository.py|
|t056_code_f003|minor|已修|0009 回填只对 NULL 行编号并以现存最大值偏移；reviewer 建议的字面 SQL（MAX() 与 ROW_NUMBER() 同层）经实测为非法 SQL（misuse of aggregate: MAX()），改用 UPDATE ... FROM + Python 预读偏移；新增断档场景迁移测试并做 red-before 探针|src/backend/migrations/versions/0009_profile_display_number_not_null.py|
|t056_test_f001|minor|已修|AC-004 措辞修正：error_reason 字段在树中不存在，改为 last_coordinator_error（spec 措辞修正，不改实现与测试）；AC-004 仍 TICK-VALID|docs/tasks/t056_api_contract_data_layer/task.md|
|t056_test_f002|minor|已修|AC-001 busy-wait 测试补显式争用断言：记录迁移耗时并断言 ≥ 0.5s（holder 约 0.7s 释放）；已做重试禁用探针与无争用空跑探针|tests/unit/test_t056_migrations.py|

### Round 2（2026-11-12 05:50，双路 PASS，0 新发现）

- code/test 两路 verdict 均为 PASS，reviewed_scope `72cc8c4e992e1853`；R1 的 5 条 finding（code f001–f003、test f001–f002）全部消除，消除结论均经 reviewer 独立复核与还原则探针验证；OpenAPI 滞后争议已查清（见上 f001 附带发现更正，Round 1 test review 正确）；check_review_status overall=PASS，next_action=finalize。

## Round 1 修复记录（2026-11-12）

- 规则：code review FAIL 且改交付物，先撤回 task.md 全部 13 个 AC 打勾，修复并重验后重新打勾（本节末尾）。
- f001（OpenAPI 422）：
    - 根因确认：`contracted_openapi()` 的 codes 循环用 `responses.setdefault("422", ErrorResponse)`，而 FastAPI 已为带请求体/路径参数的操作自动生成 422（`HTTPValidationError`），`setdefault` 永不覆盖；装饰器已声明 `ValidationErrorResponse` 的 4 处操作（`router.py:256,376,398,790` 附近）不受影响，其余 33 处仍是旧形状。修复为在 codes 循环之后再做一遍全量归一化：每个操作的 422 直接赋值 `{"$ref": "#/components/schemas/ValidationErrorResponse"}`（保留原 description），覆盖 GET 路由与 internal 路由的自动生成条目；随后删除已无引用的 `HTTPValidationError` / `ValidationError` 组件。
    - 重生成：`scripts/export_openapi.py` 重跑两份 OpenAPI（`cbrowser_v1.json` 42 处、`cbrowser_internal.json` 53 处 `ValidationErrorResponse` 引用，`HTTPValidationError` 0 处）；`npm run generate:api` 重跑前端类型（`HTTPValidationError` 0 处，`ValidationErrorResponse` 42 处）。
    - 附带发现（已查清，非 f001 本身）：重生成时恢复的“旧文件”实为基线 `3fbcec1` 版本（8 处 `Idempotency-Key` 参数），并非修复前实施版本；两路 Round 2 审阅独立核实：基线文件换回后同步测试 FAILED 是基线先于特性的正常状态，Round 1 test review“86 passed 含同步测试”正确，送审前文件已与 live app 同步（progress.md Phase 5 记录 + 送审前全量日志两项同步测试不在失败清单）；“修复前已滞后”的说法不成立。本次重生成后两项同步测试均通过。
    - 新增断言 `tests/unit/test_t035_openapi_contract.py::test_openapi_422_is_validation_error_response_not_http_validation_error`：live app 双 variant（public/internal）的每个 422 均为 `ValidationErrorResponse`、`ValidationErrorResponse` 含 `details` 且无 `detail` 属性、全树无 `HTTPValidationError`；签入文件原文与结构同样断言。验证：新断言在修复前对 live 已通过、对旧签入文件失败（`cbrowser_v1.json`）；重生成后通过。
    - 同步测试：`test_exported_openapi_schema_matches_live_app`、`test_internal_openapi_export_matches_checked_in_file`、`test_a16_protocol_drift.py` 15 passed（含 `test_backend_contract_change_without_typescript_update_is_detected`）。
- f002（幂等重放无界递归）：
    - 修复：`create_group` / `create_proxy` 的 IntegrityError 处理器在审计存在但实体已删时，先查同名是否被另一实体占用——被占直接 `raise ValueError("group/proxy name already exists")`（路由层已映射为 409 `group_name_in_use` / `proxy_name_in_use`，`groups_router.py:48` / `proxies_router.py:47` 附近）；未被占时重建，且以私有 `_allow_rebuild` 标志将重建上限定为一次（覆盖非名称原因的 IntegrityError 亦不致无界递归）。`create_profile` 不动（无唯一名称约束）。
    - 新增测试 `tests/unit/test_t056_idempotency.py::test_group_replay_after_delete_with_name_taken_is_409_not_500` 与 `::test_proxy_replay_after_delete_with_name_taken_is_409_not_500`（场景：同 operation_id 创建 → 删除 → 另一实体占用同名 → 原 operation_id 重放，断言 ValueError 而非 RecursionError/500）。验证：修复后 2 passed；red-before 探针（临时换回旧无界递归）2 failed，耗时 62.12s（约 1000 层递归 × DB 往返，与 reviewer 描述一致）；探针后文件以 sha256 恢复（`ac703deae1b41d7ecc262527e70c027270d58da0d8ea0fb79d507d7c30f79967`）。
- f003（迁移 0009 回填碰撞）：
    - 偏离说明：reviewer 建议的字面 SQL（`COALESCE(MAX(display_number), 0) + ROW_NUMBER() OVER (...)` 在 NULL 子集上算）经系统 sqlite3 3.45.1 实测为非法 SQL：`OperationalError: misuse of aggregate: MAX()`（聚合与窗口函数不能同层混用）；且相关子查询在 UPDATE 逐行执行时 NULL 集合会收缩，行号会漂移。改用等价语义的安全写法：Python 预读 `COALESCE(MAX(display_number), 0)` 为绑定参数，`UPDATE ... FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) FROM profiles WHERE display_number IS NULL)` 一次性算号。两行 NULL 场景实测：A(1)、B(3)、C(NULL)、D(NULL) → C=4、D=5。
    - 新增测试 `tests/unit/test_t056_migrations.py::test_0009_backfill_skips_existing_numbers_with_gaps`（0008 建库，插 A=1、B=3、C=NULL，迁移后断言 C=4 且迁移成功）。验证：修复后 1 passed；red-before 探针（临时换回旧回填 SQL）1 failed；探针后文件以 sha256 恢复（`58a2bbd7f85f25522c5c22d8fab13f252a67473509c3a3feffd5e0d4fd240ae4`）。
- t056_test_f001（AC-004 字段名）：
    - 核实：全树 grep `error_reason`——生产代码中无此字段；仅 `runtime_coordinator.py:76` docstring 以“the Profile's error_reason”作描述性措辞（实际字段为 `last_coordinator_error`，见同一 docstring 前句与 `domain/models.py:785,808`）、`test_t056_migrations.py:229` 的 legacy settings JSON 夹具键（t054 已删的网络操作 payload）、`test_t056_coordinator_errors.py:2` 的文件 docstring。AC-004 已改为 `last_coordinator_error`；A15 契约区 bullet 的“写入 error_reason”保留 adoption 决策原文措辞（与 progress.md Phase 3 的映射记录一致），不改生产代码与测试。
- t056_test_f002（AC-001 争用断言）：
    - 修复：`test_migration_waits_out_busy_timeout` 记录 `run_database_migrations` 耗时并断言 `≥ 0.5s`（holder 约 0.7s 释放、迁移约 0.15s 后开始，真实等待约 0.55s）。验证：修复后 1 passed（实测耗时约 0.55s 级）；探针 A（`_switch_to_wal` 超时临时改为 0，即禁用有界重试）测试 FAILED；探针 B（holder 睡眠改为 0、无争用空跑）耗时 0.014s、断言应 FAIL；探针后 `migrations.py` 以 sha256 恢复（`d60d80c10a889fb0dd240a818badd28f36fda05369c1eb29a859cc48acdf6101`）。
- 受影响套件重跑（修复后）：`test_t056_migrations`、`test_t056_idempotency`、`test_t035_openapi_contract`、`test_a6_error_contract`、`test_t056_coordinator_errors`、`test_t056_error_contract_services`、`test_t056_proxy_password_impact`、`test_t056_reference_events`、`test_t056_references`、`test_a16_protocol_drift` 及两项 OpenAPI 同步测试——**95 passed**（分文件：migrations 13、idempotency 17、t035 5、a6 13、coordinator_errors 7、error_contract_services 6、proxy_password 4、reference_events 4、references 9、a16 15、同步 2；注：migrations 文件原为 12 个测试，progress.md Phase 1 所记“13 个”有误，现为 13 个含新增 f003 测试）。
- 前端全量（`npm test`，含类型门禁）：**75 文件、546 测试全部通过**。
- 后端全量回归（修复后，默认 basetemp）：**25 failed / 2140 passed / 8 skipped（455.44s）**——25 个失败与实施方全量（`t056_full_backend2.log`）逐名完全一致（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），零新增失败；通过数 2136 → 2140（+4，恰为本次新增的 4 个测试：f001 断言 1、f002 复现 2、f003 迁移 1）。日志：`.scratch/t056_r1fix_full_backend.log`。
- AC 复核：修复与重验完成后，task.md 13 个 AC 已重新打勾（含 AC-004 新措辞 `last_coordinator_error`）；`git status` 无残留探针/临时文件（未跟踪文件仅两份 Round 1 审阅报告）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：13 个 AC 全部实现并单测验证（AC 打勾见 task.md；Round 1 修复后全量回归：后端 25 failed / 2140 passed / 8 skipped，失败按名与实施方全量完全一致、零新增；前端 75 文件 546 测试全部通过）
- 测试：Round 1 修复：受影响套件 95 passed；全量回归：后端 25 failed / 2140 passed / 8 skipped（失败与实施方全量逐名一致、零新增），前端 75 文件 546 测试全部通过；Round 2 审阅方独立重跑：后端 25 failed / 2140 passed / 8 skipped（与 t055 基线逐名一致），前端 546 passed / 0 failed（test 路一轮出现 2 个 5000ms 超时 flaky，单独重跑 16/16 通过，与 t056 无关）
- 黑盒：本机跳过（见环境跳过项），用户机复核
- review：Round 2 双路 PASS（2026-11-12 05:50；code/test 均 PASS，0 新发现；R1 的 5 条 finding 全部消除并经还原则探针复核；check_review_status overall=PASS，next_action=finalize）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 实施范围：A1、A2、A15、A17、A21、A23、A26、A28、A29、A31、A60 全部完成；13 个 AC 全部单测验证。
- 关键发现两件：A1 决策书单步不成立（WAL 切换不遵守 busy handler，需有界重试）；Starlette/FastAPI 处理器注册 bug（404 仍走默认 `detail` 体，已修复）。
- 字段名映射一件：AC-004 的 error_reason 在树中不存在，以 `last_coordinator_error` 呈现下游 error+message（见实施笔记 Phase 3）。
- 遗留验证（用户机）：AC-005 真实引擎启动、AC-004 真实 Supervisor 502、AC-012 双客户端实时同步、Gateway live 路由、绑定-only 改密后冻结拒绝、黑盒门禁。
- 未动：t032；未合并、未推送。

### 长期文档闭环

- specs_index：profile_management、proxy_management、runtime_lifecycle 三行已登记 t056（2026-11-12）。
- blueprint：conventions、persistence、domain、frontend 已更新；specs 三份已更新。

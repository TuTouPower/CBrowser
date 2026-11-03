# Task review t016（reviewer_focus: 测试）

- task：`t016_v2_backend_hardening`
- spec：`docs/tasks/t016_v2_backend_hardening/task.md`
- diff_anchor：`fb6185c46f41500a9089e526a1773774a7cd6c67`
- target：`git -C '/Users/karson/kar/code/CBrowser_t016' diff fb6185c46f41500a9089e526a1773774a7cd6c67`
- round：1
- reviewed_at：2026-11-03T03:13:25+08:00
reviewed_scope: eeed07bc84c7977e

## Findings

### t016_test_f001 - 仓储测试仍用 ORM metadata 建表，迁移与模型一致性无守护

- 严重度：critical
- 锚点：AC-007（“仓储测试在真实迁移建出的 schema 上运行，且模型与迁移的一致性受测试守护”）
- 位置：`tests/unit/test_domain_and_repository.py:36-42`（`db_context` 用 `Base.metadata.create_all`）；`tests/unit/test_domain_and_repository.py:45-76`（八表存在性同样基于 ORM schema）；`tests/unit/test_runtime_event_policy.py:11-12` 复用该 fixture
- 问题：AC-007 已打勾，但仓储 fixture 没有调用 `run_database_migrations`，测试实际验证的是 SQLAlchemy metadata，不是 Alembic 迁移。没有任何测试从 `0003_artifact_storage` 的既有 schema（含 `profiles.runtime_mode/viewer_mode` 与数据）升级到 head；也没有 `compare_metadata` 漂移守卫。我实测：手工建 0003 schema、插入 Profile 后 `upgrade head` 能保留行并删除两列（当前迁移行为正常），但 `alembic.autogenerate.compare_metadata(MigrationContext, Base.metadata)` 返回 `[('remove_index', Index('idx_artifacts_profile_sha256', ...))]`——模型与迁移已存在真实漂移，而 AC 要求的守卫若存在会直接失败。也就是说，迁移回归和模型/迁移分叉现在都无法被测试发现。
- 建议：把 `db_context` 改为先 `run_database_migrations(temp_db_path)` 再建 engine；新增“0003 既有库 + Profile 行升级到 head”测试，断言行保留、两列消失、`expires_at` 出现；新增 `compare_metadata(...) == []` 守卫，并同步修正 `idx_artifacts_profile_sha256` 的模型声明或明确记录为有意差异。

### t016_test_f002 - POST /profiles 非法 launch_args 返回 500，缺少 API 层 422 测试

- 严重度：important
- 锚点：AC-009（“Profile 启动参数按白名单在 API 层校验，非法参数返回 422”）
- 位置：`src/backend/cbrowser/domain/models.py:249-282`（`ProfileCreateRequest` 没有 `launch_args` validator）；`src/backend/cbrowser/api/v1/router.py:171-198`（路由内构造 `ProfileConfig`）；`src/backend/cbrowser/api/app.py:327-337`（通用异常处理为 500）；现有测试仅 `tests/unit/test_launch_args.py:33-35`
- 问题：`tests/unit/test_launch_args.py` 只证明 `ProfileConfig` 会抛 `ValidationError`。实际 HTTP 请求 `POST /api/v1/profiles` 携带 `{"launch_args": ["--load-extension=/tmp/evil"]}` 能通过 `ProfileCreateRequest` 校验，随后路由构造 `ProfileConfig` 时抛 `pydantic_core.ValidationError`，被通用异常处理器映射为 **500 `internal_server_error`**，不是 AC 要求的 422。我用 `TestClient(..., raise_server_exceptions=False)` 复现；同一 payload 走 `PATCH` 返回 422（因为 `ProfileUpdateRequest` 有 validator）。该缺口完全没有集成测试覆盖。
- 建议：把 `launch_args` 校验同时放到 `ProfileCreateRequest`（或捕获 `ValidationError` 映射 422），并补 `tests/integration` 级用例：POST 非法启动参数返回 422 且数据库无新 Profile；PATCH 非法参数同样 422。

### t016_test_f003 - AC-005 的令牌过期、过期会话清理、文档默认关闭、未配置 503 均无测试

- 严重度：important
- 锚点：AC-005
- 位置：`src/backend/cbrowser/auth/service.py:224-228`（`expires_at` 计算）、`src/backend/cbrowser/auth/service.py:349-351`（`token_expired`）；`src/backend/cbrowser/auth/service.py:162-166`（登录时清理过期 session）；`src/backend/cbrowser/api/app.py:75`（`CBROWSER_API_DOCS` 默认关闭）；`src/backend/cbrowser/auth/dependencies.py:15-22` 与 `src/backend/cbrowser/api/internal_supervisor.py:30-36`（未配置返回 503）
- 问题：`tests/unit/test_auth_service.py:125-176` 只测 token 创建/列出/吊销；`tests/unit/test_auth_service.py:180-261` 只测 valid / session-as-token / unauthorized profile / revoked，未测 `expires_in_hours`、`token_expired`。没有任何测试断言 `create_session` 会删除过期 session；没有测试断言默认 `/docs`、`/redoc`、`/openapi.json` 不可达；也没有测试断言 `app.state.auth_service` 或 `app.state.supervisor_token` 缺失时返回 503 而非 500。AC-005 这些子项已被打勾但无有效验证。
- 建议：补单元测试：创建带 `expires_at` 的 token 后断言 `authorize_automation` 返回 `token_expired`；插入过期 session 后登录并断言行被删除；集成测试断言 docs 路径默认 404、设置 `CBROWSER_API_DOCS=1` 后可达，以及未配置守卫返回 503。

### t016_test_f004 - 伪造自动化令牌“不落库且被限流”无测试，限流路径也未实现

- 严重度：important
- 锚点：AC-005（“伪造的自动化令牌不产生数据库写入且被限流”）
- 位置：`src/backend/cbrowser/auth/service.py:321-343`（invalid/unknown token 只记日志）；`src/backend/cbrowser/api/v1/automation_router.py:75-91`（自动化 CDP 入口无 throttle）；`tests/unit/test_auth_service.py:226-250`（只覆盖合法、session token、未授权 profile、已吊销）
- 问题：代码已改成 invalid/unknown token 不写 `audit_events`，但没有测试断言 `AuditEventModel` 不新增行；`authorize_automation` 与 automation WebSocket 路由都没有按来源限流，只有管理员登录用的 `LoginRateLimiter`，`test_gateway_signaling.py::test_viewer_authorization_failures_are_rate_limited` 也只覆盖 viewer。因此“被限流”既无测试也无可执行的实现证据。
- 建议：为自动化授权失败增加按来源/Profile 的限流并在超限时返回 429 或关闭连接；补测试断言伪造 token 后 `audit_events` 行数不变、连续失败达到阈值后被限流，同时覆盖内部 `automation-authorize` 与公开 WS 入口。

### t016_test_f005 - SSE 快照/实时事件的乱序修复没有时序测试

- 严重度：important
- 锚点：AC-005（“SSE 订阅的初始快照与实时事件不乱序，断线续传语义明确且有测试”）
- 位置：`src/backend/cbrowser/api/runtime_coordinator.py:72-135`；`tests/unit/test_runtime_event_broadcaster_epoch.py:42-58`、`tests/integration/test_api_sse_events.py:61-156`（均为既有测试，未随修复新增）
- 问题：本次修复的关键是持有 `_lock` 构建快照/补发、在同一锁内注册订阅队列、并把快照事件写入 `_history`。现有测试只验证 catch-up 和快照 ID 唯一，没有测试在 `initial_snapshot_provider` 执行期间并发 `publish` 后断言“快照先于实时事件且 ID 单调”；也没有测试用快照事件 ID 作为 `Last-Event-ID` 重连以验证快照已进入历史。旧实现的乱序窗口在这些测试下仍会通过。
- 建议：加一个确定性时序测试：snapshot provider 阻塞在事件/屏障上时并发 publish 一个实时事件，恢复后断言输出顺序为快照事件在前、实时事件在后且 ID 单调；另加一个用快照 ID 重连、断言只补发间隙事件的测试。

### t016_test_f006 - AC-002 的非法帧/重连测试弱化，未验证后续事件与下载捕获恢复

- 严重度：important
- 锚点：AC-002（“单个非法或异常帧不影响后续事件与命令，连接断开后自动重连并恢复下载捕获”）
- 位置：`tests/unit/test_runtime_agent_faults.py:174-212`；对照 `tests/unit/test_runtime_agent.py:302-316`（健康探活只测 `/health` 延迟）
- 问题：`test_listener_isolates_malformed_frame_and_keeps_running` 只发送一个非法帧，随后 `asyncio.sleep(1.0)`，测试只等 0.1 秒并断言 `not manager._event_listener_task.done()`。这不能证明非法帧已被消费，也不能证明其后的有效事件/命令仍被处理——任务在“尚未读到坏帧”或“读到坏帧后卡住”时同样不会 done。旧断言 `manager.capture_alive` 被替换成私有任务状态，属于弱化。`caplog.at_level(logging.ERROR)` 也捕获不到实现实际写出的 WARNING，canary 断言形同虚设。没有任何单元测试关闭 CDP 连接后断言自动重连并再次 `rearm_download_capture`；现有 E2E `test_browser_runtime_e2e.py::test_ac004_download_capture_and_recovery` 覆盖的是外部自动化覆盖后的 rearm，不是事件监听器断线自愈。
- 建议：坏帧后发送一个有效 `Browser.downloadWillBegin`/`downloadProgress` 并等待 `EventStorage` 出现对应事件；断言 `manager.capture_alive`；关闭上游连接后等待重连，断言 `rearm_count` 增长或 download 事件再次落盘；用事件/条件等待替代 0.1 秒 sleep，并把 caplog 级别降到 WARNING。

### t016_test_f007 - Pulse cookie/Xauthority 的 0600 精确权限无测试

- 严重度：important
- 锚点：AC-008（“Pulse cookie、Xauthority 仅属主可读写”）
- 位置：`src/backend/cbrowser/runtime_agent/runner.py:167-195`（pulse 目录 0700、cookie 0600）、`src/backend/cbrowser/runtime_agent/runner.py:252-269`（xauth 0600）；`tests/unit/test_runtime_persistence_guards.py:202-228` 只断言路径与环境变量，不断言 mode
- 问题：AC-008 的测试策略明确要求“权限模型改动以单元测试断言精确 mode”。当前有 artifact/profile 复制/supervisor 目录/cache/snapshot 的精确 mode 测试，但 `pulse.cookie`、`Xauthority` 以及它们所在目录没有 0600/0700 断言。真实 Docker E2E 只能证明容器可读，不能发现 0644（group/other 可读）；该安全属性未被验证。
- 建议：用 monkeypatch 替代 `pulseaudio`/`xauth`/`Xvfb` 子进程调用，直接调用 `setup_pulse`/`setup_display` 并断言 `pulse.cookie`、`Xauthority` 为 0600，pulse/x11 config 目录为 0700；或在现有精确 mode 测试中补这些路径。

### t016_test_f008 - AC-006 要求的“契约响应码守卫”不存在

- 严重度：important
- 锚点：AC-006（“守卫测试保证实现可达响应码包含于契约”）
- 位置：`tests/unit/test_runtime_agent_protocol_export.py:27-50`
- 问题：该测试只对 `/api/v1/profiles` POST 和一个内部 route 硬编码断言少量状态码，并未枚举路由，也没有比较“实现实际可达响应码 ⊆ 契约声明”。新增 route 或某 route 实际返回未声明的 429/404 不会使测试失败。AC-006 的守卫要求未被满足。前端类型同步我用 `npx openapi-typescript schemas/openapi/cbrowser_v1.json` 生成到临时文件与 `src/frontend/src/shared/api/generated/cbrowser_v1.d.ts` 比较，当前 MATCH，但没有自动化漂移守护。
- 建议：增加通用守卫：遍历 `app.routes`/OpenAPI operations，对每个方法校验实现可能返回的状态码集合包含于该 operation 的 `responses`，缺项即失败；同时增加生成 `.d.ts` 的漂移检查（生成到临时文件后 diff），或明确该步骤只靠人工门禁。

### t016_test_f009 - AC-001 的“枚举全部路由”退化为三条路径点检

- 严重度：minor
- 锚点：AC-001（“架构测试枚举全部路由，断言上报类路径只出现在服务面”）
- 位置：`tests/unit/test_runtime_agent_protocol_export.py:53-65`
- 问题：测试只检查三个已知路径是否出现在 public/internal OpenAPI，没有遍历 `app.routes`。如果以后把上报 handler 挂到另一个 `include_in_schema=False` 的用户 router，public OpenAPI 看不到，测试仍会通过，不能实现 AC 所说的“枚举全部路由”。
- 建议：遍历 `app.routes`，按路径/依赖/所属 router 分类，断言上报 handler 只挂在 supervisor 服务面；保留现有 OpenAPI 检查作为补充。

### t016_test_f010 - AC-010 的内部 URL 标识符转义无测试

- 严重度：minor
- 锚点：AC-010（“内部 URL 中的标识符正确转义”）
- 位置：`src/backend/cbrowser/supervisor/core.py:225,850,882,1176,1272`；`src/backend/cbrowser/supervisor/control_server.py:97,177`；`src/backend/cbrowser/supervisor/gateway_client.py:30`；`src/backend/cbrowser/gateway/api_client.py:39`
- 问题：实现已改为 `quote(..., safe="")`，但全仓测试没有构造含 `/`、`?`、`#` 或空格的 profile_id 来断言请求路径被正确编码。若某处回退为裸拼接，现有测试不会发现。
- 建议：用 `httpx.MockTransport` 捕获请求 URL，传入含特殊字符的 profile_id，断言实际 `url.path` 被编码为单一路径段；至少覆盖 `SupervisorCore` 与 `control_server` 两处。

### t016_test_f011 - AC-011 文档仍有 runtime_mode/viewer_mode 残留

- 严重度：minor
- 锚点：AC-011（后端相关 blueprint 与 spec 与代码一致）
- 位置：`docs/blueprint/persistence.md:24`（profiles 字段列表仍列 `runtime_mode`、`viewer_mode`）；`docs/specs/runtime_persistence.md:19`（仍称 `POST /api/v1/profiles` 将两字段统一为 docker/webrtc）
- 问题：代码与迁移已删除两字段，但这两处文档仍把它们描述为当前 schema/API 行为；其中 `docs/blueprint/persistence.md` 本次还在 diff 中被修改，却未修正该字段列表。按“spec 过时”处理，应改文档，不计 FAIL。
- 建议：删除字段列表中的两项，并把 `runtime_persistence.md` 该句改为历史说明或移除；在 AC-011 复核记录中保留 grep 结果。

### t016_test_f012 - AC-004 的“后台重试”与 labels 字符串化无直接测试

- 严重度：minor
- 锚点：AC-004（“启动对账失败时控制面仍可用并后台重试”；“标签……格式问题按约定映射”）
- 位置：`tests/unit/test_supervisor_startup_recovery.py:293-324`；`src/backend/cbrowser/supervisor/runner.py:160-166,260-290`；`src/backend/cbrowser/supervisor/container_spec.py:66-79`
- 问题：新增测试只证明初次对账失败后 `create_control_app` 被调用（并把它 mock 成抛异常），没有驱动后台 monitoring loop 再跑一次 `scan_and_reconcile_existing`，无法防止“初次失败后再也不重试”的回归。`stream_labels` 的 `str(config_version)` 修复也没有测试（`tests/unit/test_refactor_behavior_equivalence.py:234` 传入的本来就是字符串）。
- 建议：补一个测试驱动 `serve_supervisor` 的 monitor 循环一轮，断言初次失败后再次调用 `scan_and_reconcile_existing`；补 `stream_labels(..., 3)` 返回 `"3"` 的断言。

## 结论

- 前轮 finding 复核：Round 1，无前轮 finding。
- 改测方向复核：本轮没有发现“把旧断言改成当前实现输出”的迁就型改测。`test_supervisor_file_permissions.py`、`test_profile_copy_reset.py`、`test_runtime_agent.py`、`test_runtime_persistence_guards.py`、`test_domain_and_repository.py`、`test_v2_api_subprocess.py` 与 `test_runtime_profile_defaults_e2e.py` 的预期变更是字段删除、白名单化与权限收紧的直接结果，属合法改测；旧测试 `test_launch_args_security_sanitization` 被白名单测试替代，旧 mode 断言随字段删除而删除，均可解释。唯一需要指出的是 `test_runtime_agent_faults.py` 的替换改测同时弱化了断言（见 f006），这是测试质量缺陷而非“迁就实现”的方向问题。
- 本轮新发现：12 条（blocking：f001–f008；minor：f009–f012）。
- 未进表的提示：
    - 本 worktree 用 `check_review_status.py` 重算的 scope 指纹为 `30228cb0c5a1a149`，与 prompt 注入的 `eeed07bc84c7977e` 不一致；本报告按 prompt 要求保留注入值，但该差异说明 prompt 渲染后工作区仍有变化，实施方修复后应重新渲染 prompt 再派下一轮。
    - `src/frontend/tsconfig.tsbuildinfo` 被修改；`docs/blueprint/testing.md` 明确要求构建后还原该文件，属仓库卫生问题（范围外，建议提交前还原）。
    - `note.md` 自述 unit 530 passed；本地复跑 `tests/unit` 为 529 passed。其余复跑结果：`tests/integration` 79 passed、`src/backend/tests` 384 passed、`.repo_template/tests -m contract` 169 passed；数量以实际为准。
    - 若干测试断言私有内部状态（`service._locks._locks`、`manager._event_listener_task.done()`、`store._apply_runtime_permissions`、`core._write_runtime_snapshot`），建议优先断言对外可观察结果；其中 `_event_listener_task` 的问题已在 f006 记录。
    - `tests/unit/test_download_reconciler.py` 的 dead-letter 用例只断言隔离文件存在，未断言内容保留与“修复后可重试”的可操作性；属可选覆盖扩展。
    - `tests/unit/test_supervisor_startup_recovery.py` 与 `test_supervisor_reconcile_fences.py` 通过 monkeypatch 替换 `create_control_app`、`_query_agent_health` 等内部方法；作为单元测试可接受，但不应替代更靠近真实边界的集成验证。
    - Health 探活测试用 0.6s 阈值区分串行/并行（三次 0.25s 探活）；在负载较高的机器上存在偶发超时风险，当前不作为 finding。

### AC 复验方式

- AC-001：`re_verified`。复跑 `test_v2_api_subprocess` 与 `test_supervisor_rpc`，确认内部面 Bearer 与 session 拒绝路径；缺陷仅在“枚举全部路由”退化为三条路径点检（f009）。
- AC-002：`re_verified`。复跑 `tests/unit/test_runtime_agent.py` 与 `test_runtime_agent_faults.py`，并阅读 `cdp_proxy.py`；未重跑真实 Docker CDP 场景，且发现非法帧/重连覆盖不足（f006）。
- AC-003：`re_verified`。复跑 artifact/download reconciler 单测与集成测试，确认死信、版本隔离、明确失败原因与超长名截断均有断言。
- AC-004：`re_verified`。复跑 `test_resource_fault_isolation.py`、`test_supervisor_control_auth.py`、`test_supervisor_reconcile_fences.py`、`test_supervisor_startup_recovery.py`；后台重试与 labels 仍无直接测试（f012，minor）。
- AC-005：`re_verified`。复跑 auth 单测/集成测试并检查实现，发现 token 过期、会话清理、docs 关闭、未配置 503、伪造令牌限流与 SSE 时序均缺测试（f003–f005）。
- AC-006：`re_verified`。复跑 OpenAPI 漂移单测；额外用 `npx openapi-typescript` 生成临时文件并与已入库 `cbrowser_v1.d.ts` 比较为 MATCH；契约响应码守卫缺失（f008）。
- AC-007：`re_verified`。检查 fixture 与测试，并额外执行 0003→head 升级探针与 `compare_metadata` 探针；仓储测试未使用真实迁移、模型/迁移漂移已被探针暴露（f001）。
- AC-008：`trust_prior`。单元测试复跑覆盖 snapshot/目录/cache/copy 的精确 mode，但 Pulse cookie/Xauthority 0600 无单元测试；双容器 E2E 依赖实施侧 note 声称的 `test_frontend_session_e2e.py::test_frontend_session_dual_tab_identity_refresh_copy_no_kick_and_close` 通过，本次未重跑镜像拓扑。
- AC-009：`re_verified`。复跑白名单单测并运行 TestClient 探针；POST /profiles 非法参数实际返回 500（f002）。
- AC-010：`re_verified`。复跑 artifact 并发/锁、event storage、operation journal、metrics、CDP pre-accept、runner 路径/环境测试；URL 标识符转义无测试（f010，minor）。
- AC-011：`re_verified`。用 grep 检查 blueprint/spec 与代码；`persistence.md` 与 `runtime_persistence.md` 仍有已删除字段（f011，minor）。

coverage = 10 / 11（AC-008 的 Docker 双容器 E2E 为 `trust_prior`；其余为 reviewer 独立复验）

- 总体判断：存在未解决的 critical/important 测试缺口（f001–f008），当前不能 PASS。
- 系统性 follow-up：无。f001–f008 均属 t016 自身 AC 的测试与契约缺口，不应转交 t018 的测试体系整体整改。

verdict: FAIL

## Round 2 (2026-11-03T03:46:51+08:00)

reviewed_scope: c36146bcdf06fa14

### 前轮 finding 复核

- t016_test_f001 - 已消除（主体）。`tests/unit/test_domain_and_repository.py:37-42` 的 `db_context` 已改为 `run_database_migrations`，`tests/unit/test_domain_and_repository.py:541-561` 新增 `test_models_match_migrations`（`compare_metadata(...) == []`）且本轮复跑通过；`src/backend/cbrowser/adapters/database/models.py:188-190` 也补了 `idx_artifacts_profile_sha256`。残留：仍无“0003 既有库 + Profile 行升级到 head”的用例，数据保真只靠人工探针，降为可选覆盖。
- t016_test_f002 - 已消除。`src/backend/cbrowser/domain/models.py:250-258` 已给 `ProfileCreateRequest` 加白名单 validator；`tests/integration/test_v2_api_subprocess.py:193-199` 通过真实 HTTP 进程断言非法 `launch_args` 返回 422 且没有新增 Profile；`tests/unit/test_launch_args.py:33-39` 覆盖 DTO。PATCH 分支仍无 HTTP 级用例，属可选扩展。
- t016_test_f003 - 仍存在。复跑 `tests/unit/test_auth_service.py` 与 `tests/integration/test_auth_api.py` 未发现 `expires_in_hours`/`token_expired`、`create_session` 清理过期 Session、`CBROWSER_API_DOCS` 默认关闭、`app.state.auth_service` 缺失时 503 的任何断言。实现位于 `src/backend/cbrowser/auth/service.py:155-168,219-229,351-360`、`src/backend/cbrowser/api/app.py:75,172`、`src/backend/cbrowser/auth/dependencies.py:18-22`；这些 AC-005 子项仍无测试守护。
- t016_test_f004 - 修不彻底。`src/backend/cbrowser/auth/service.py:321-380` 已加 `_automation_limiter`，`tests/unit/test_auth_service.py:241-250` 已断言连续 10 次伪造令牌后返回 `rate_limited`；但没有任何断言“伪造 token 不新增 `audit_events` 行”。`authorize_automation` 对 invalid format / not-found 只记日志（`src/backend/cbrowser/auth/service.py:326-346`），若回归为 `_record_auth_denied`，现有测试仍会通过；AC-005 的“不产生数据库写入”仍无有效证据。
- t016_test_f005 - 仍存在。`src/backend/cbrowser/api/runtime_coordinator.py:76-135` 已改为同锁构建快照并注册订阅，但 `tests/unit/test_runtime_event_broadcaster_epoch.py` 与 `tests/integration/test_api_sse_events.py` 没有新用例：仍无“`initial_snapshot_provider` 阻塞期间并发 `publish`，恢复后快照事件先于实时事件且 ID 单调”的时序断言，也无“用快照事件 ID 作为 `Last-Event-ID` 重连只收到间隙事件”的断言。旧实现的乱序窗口仍可通过现有测试。
- t016_test_f006 - 仍存在。`tests/unit/test_runtime_agent_faults.py:174-211` 仍是发一个非法帧后 `await asyncio.sleep(0.1)`，只断言私有 `_event_listener_task` 未 done；`caplog` 仍设在 `ERROR`（实现实际写 WARNING），canary 断言是空转。仍没有“坏帧后有效事件被消费”“断线后 `rearm_count` 增长/下载事件再次落盘”的用例；`src/backend/cbrowser/runtime_agent/cdp_proxy.py:137-225` 的重连/finally 分支无回归测试。
- t016_test_f007 - 仍存在。`src/backend/cbrowser/runtime_agent/runner.py:165-195,245-269` 已设置 pulse 目录 0700、cookie 0600、xauth 0600，但 `tests/unit/test_runtime_persistence_guards.py:202-257` 新增用例只断言路径和环境变量，没有 `stat.S_IMODE` 断言；E2E 仅检查文件存在（`tests/e2e/test_browser_runtime_e2e.py:2300-2313`）。AC-008 要求的“仅属主可读写”仍未被自动测试验证。
- t016_test_f008 - 仍存在（且本轮实测确认契约确有漏项）。新的 `tests/unit/test_runtime_agent_protocol_export.py:27-76` 只硬编码检查少量响应码，没有枚举路由/实现可达码。实测 `create_app().openapi()`：`POST /api/v1/profiles/{profile_id}/artifacts` 只声明 201/401/403/404/422/503，而 `src/backend/cbrowser/api/v1/artifact_router.py:36-44,62-70` 可达 400/413/507；内部 `GET /api/v1/internal/supervisor/profiles/{profile_id}` 可达 404（`src/backend/cbrowser/api/internal_supervisor.py:64` 复用 `get_profile`），契约未声明。AC-006 的“实现可达响应码 ⊆ 契约”守卫仍不存在。
- t016_test_f009 - 仍存在（minor）。`tests/unit/test_runtime_agent_protocol_export.py:53-66` 仍只检查三条已知路径，没有遍历 `app.routes`。
- t016_test_f010 - 仍存在（minor）。实现已在 `src/backend/cbrowser/supervisor/recovery_coordinator.py:180,278,410,459,620` 等统一 `quote(..., safe='')`，但全仓仍没有特殊字符 profile_id 的请求路径断言。
- t016_test_f011 - 已消除。`rg 'runtime_mode|viewer_mode' docs/blueprint docs/specs` 已无输出；`docs/blueprint/persistence.md:24` 字段列表与 `docs/specs/runtime_persistence.md:19` 的创建说明已修正，`docs/blueprint/domain.md:12` 的 ObservedState 枚举已同步为 `stopped/starting/running/stopping/error`。
- t016_test_f012 - 修不彻底（minor）。`tests/unit/test_supervisor_startup_recovery.py:294-324` 只证明初次对账失败后仍会尝试创建控制面（`create_control_app` 被 mock 成抛异常），没有驱动后台 `background_monitoring_loop` 再执行一次 `scan_and_reconcile_existing`；`stream_labels(..., 3)` 的字符串化仍无断言（`tests/unit/test_refactor_behavior_equivalence.py:234` 传的是字符串 `"3"`）。

### 改测方向复核

本轮新增/改写的测试预期变更均有实现或 spec 归因：字段删除（`tests/integration/test_v2_api_subprocess.py`、`tests/e2e/test_runtime_profile_defaults_e2e.py`）、白名单化（`tests/unit/test_runtime_agent.py`、`tests/unit/test_runtime_persistence_guards.py`）、权限精确化（`tests/unit/test_supervisor_file_permissions.py`、`tests/unit/test_profile_copy_reset.py`、`tests/unit/test_artifact_service.py`）、Artifact 返回类型改为 `IngestDownloadResult`、控制面 WS 先鉴权、迁移改用 Alembic。未发现把旧断言改成当前实现输出的迁就型改测；唯一弱化仍是 Round 1 已记录的 `tests/unit/test_runtime_agent_faults.py` 替换（见 f006），本轮未修复。

### 本轮新发现

#### t016_test_f013 - 名为“by default”的 uid 1000 测试显式传参，未验证生产默认值

- 严重度：minor
- 锚点：AC-008（“运行时数据统一归属运行用户（uid 1000）”）
- 位置：`tests/unit/test_artifact_service.py:361-366`、`tests/unit/test_profile_copy_reset.py:546-560`
- 问题：两个测试名都声称验证“默认 uid 1000”，但都显式传入 `runtime_uid=1000, runtime_gid=1000`；生产 `create_app` 构造 `ProfileService(repo)`/`ArtifactStore(root)` 时走构造函数默认值，而 `tests/integration/test_artifacts_api.py:35-38` 与 `tests/integration/test_profile_copy_reset_api.py:54-57` 又把 runtime_uid 覆盖为 `os.getuid()`。因此把默认值改回 `os.getuid()`（root 下即 0）不会让任何测试失败；AC-008 的默认归属没有被守护。
- 建议：增加不传 uid 的构造/应用级测试并断言 chown 目标为 1000，或把测试改名为“explicit 1000”并另补默认值断言。

### AC 复验方式

- AC-001：`re_verified`。复跑 `tests/unit/test_runtime_agent_protocol_export.py`、`tests/integration/test_v2_api_subprocess.py` 与 `tests/unit/test_supervisor_rpc.py`，并读 `src/backend/cbrowser/api/v1/router.py`、`internal_supervisor.py`；上报路由只在内部服务面。
- AC-002：`re_verified`（部分）。复跑 `tests/unit/test_runtime_agent.py`、`tests/unit/test_runtime_agent_faults.py` 并读 `cdp_proxy.py`；健康探活并发测试通过，但非法帧后续事件/断线重连仍无有效测试（f006），未重跑真实 Chrome E2E。
- AC-003：`re_verified`。复跑 `tests/unit/test_artifact_service.py`、`test_download_reconciler.py`、`test_supervisor_event_delivery.py`、`test_runtime_instance_storage.py`；越界拒绝、dead-letter、版本隔离、失败原因、长文件名截断均有断言。
- AC-004：`re_verified`。复跑 `tests/unit/test_resource_fault_isolation.py`、`test_supervisor_control_auth.py`、`test_supervisor_reconcile_fences.py`、`test_supervisor_startup_recovery.py`；per-Profile 隔离与 503 映射通过，后台重试仍无直接测试（f012，minor）。
- AC-005：`re_verified`。复跑 auth 单测/集成/SSE 测试并读实现；token 过期、过期会话清理、docs 关闭、未配置 503、伪造令牌不落库与 SSE 时序仍有缺口（f003/f004/f005）。
- AC-006：`re_verified`。复跑 `tests/unit/test_runtime_agent_protocol_export.py` 与 `tests/unit/test_domain_and_repository.py`，并用 `create_app().openapi()` 探针检查 artifact/internal 路由；发现可达码漏项与守卫缺失（f008）。前端生成类型用 `openapi-typescript` 重新生成到临时文件与入库 `.d.ts` 比较为 MATCH。
- AC-007：`re_verified`。复跑 `tests/unit/test_domain_and_repository.py`（含 `test_models_match_migrations`）并检查 0004/0005 迁移；`rg` 确认 v2 代码/schemas/生成类型无 `runtime_mode`/`viewer_mode`。旧库带数据升级场景仍无测试（f001 残留，minor）。
- AC-008：`trust_prior`。单元测试复跑覆盖 snapshot/目录/cache/artifact/profile 复制精确 mode；Pulse cookie/Xauthority 0600 仍无单测（f007），双容器真实 Docker E2E 依赖实施侧记录，本轮未重跑。
- AC-009：`re_verified`。复跑 `tests/unit/test_launch_args.py` 与 `tests/integration/test_v2_api_subprocess.py` 的 422 用例；POST 非法参数 422 且无新 Profile 已实测，PATCH 无 HTTP 级用例（可选扩展）。
- AC-010：`re_verified`。复跑 artifact 并发/锁、event storage、operation journal、metrics、CDP pre-accept、runner 路径/环境测试；URL 转义无测试（f010，minor）。
- AC-011：`re_verified`。用 `rg`/diff 检查 blueprint 与 spec；残留字段与 ObservedState 已修正。

coverage = 10 / 11（AC-008 为 trust_prior；其余为 reviewer 独立复验）

### 未进表提示

- AC-003 的 dead-letter 用例仍只断言隔离文件存在，未断言内容保留与“修复后重试”的可操作性；属可选覆盖扩展。
- Agent 磁盘下载事件信封的 `version` 写入没有直接断言；新增的 `test_spool_envelope_carries_version` 验证的是 Supervisor spool，不是 Agent 的 download event 文件。
- `tests/unit/test_auth_service.py:241-250` 只断言第 11 次返回 `rate_limited`，未断言前 10 次的失败原因；属测试精度可选改进。
- PATCH `/profiles/{id}` 的非法 `launch_args` 仍无 HTTP 级用例。
- `src/frontend/tsconfig.tsbuildinfo` 仍在工作区被修改；`docs/blueprint/testing.md` 要求构建后还原（范围外仓库卫生）。
- `note.md` 自述 unit 530 passed；本地复跑 `tests/unit` 为 531 passed，`tests/integration` 为 79 passed（以实际输出为准）。
- 真实 Docker/Chrome E2E（AC-008 双容器、AC-002 真实 CDP）本轮未重跑；依赖实施侧记录。

### 结论

- 前轮 finding 复核：f001 主体消除；f002 消除；f011 消除；f003、f005、f006、f007、f008 仍存在；f004 修不彻底（限流已覆盖，“不落库”未断言）；f009、f010、f012 仍为 minor 残留。
- 改测方向复核：无“迁就实现”的改测；f006 的弱化替换测试沿用 Round 1 结论。
- 本轮新发现：1 条（f013，minor）。
- 未进表的提示：见上。
- 总体判断：核心阻塞方向有进展（真实迁移/漂移守卫、422、限流、权限精确化、重连实现等），但 AC-005 的 token 过期/会话清理/docs/503/SSE 时序、AC-002 的坏帧/重连、AC-008 的 Pulse/Xauthority 0600、AC-006 的可达码守卫仍未落实，当前不能 PASS。
- 系统性 follow-up：无（均在 t016 自身 AC 范围）。

verdict: FAIL

## Round 3 (2026-11-03T04:14:39+08:00)

reviewed_scope: 0c4e212ea79e95c9

### 前轮 finding 复核

- t016_test_f001 - 已消除（Round 2 主体保持）。`tests/unit/test_domain_and_repository.py:37-42` 的 `db_context` 仍走 `run_database_migrations`，`:541-561` 的 `test_models_match_migrations` 本轮复跑通过。残留仍是「0003 既有库 + 数据升级到 head」无自动化用例（minor，不阻断）。
- t016_test_f002 - 已消除。`tests/integration/test_v2_api_subprocess.py:193-199` 仍通过真实 HTTP 进程断言非法 `launch_args` 返回 422 且无新 Profile；本轮复跑通过。PATCH 的 HTTP 级 422 用例仍缺（minor）。
- t016_test_f003 - 已消除（主体）。`tests/unit/test_auth_service.py:254-259` 覆盖 `expires_in_hours=-1` 后返回 `token_expired`；`:261-270` 创建过期 Session 后断言剩余 Session 均未过期；`tests/unit/test_runtime_agent_protocol_export.py:91-99` 覆盖 docs/redoc/openapi 默认关闭；`tests/unit/test_auth_service.py:306-315` 覆盖 `auth_service` 缺失返回 503。残留：`app.state.supervisor_token` 缺失时内部面 503 仍无行为测试（minor）。
- t016_test_f004 - 已消除。`tests/unit/test_auth_service.py:248-250` 断言两次伪造/未知 token 后 `audit_events` 行数不变；`:272-282` 断言同一来源连续失败后返回 `rate_limited`。残留：公开 WS 入口把 `rate_limited` 映射为 close code 4408 的行为仍无端点级用例（minor）。
- t016_test_f005 - 已消除（主体）。`tests/unit/test_runtime_event_broadcaster_epoch.py:168-190` 新增时序测试：快照 provider 阻塞期间并发 `publish`，恢复后断言快照先于 live 且事件 ID 单调。旧实现的「快照构建期间注册订阅」乱序窗口会在此测试下漏事件并超时。残留：用快照事件 ID 作为 `Last-Event-ID` 重连只补发间隙事件的用例仍缺（minor）。
- t016_test_f006 - 已消除（主体）。`tests/unit/test_runtime_agent_faults.py:175-224` 在非法帧后发送有效 `Browser.downloadWillBegin` 并断言 `download_after_bad` 进入 `active_downloads`；`:228-259` 新增断线后自动重连且 `rearm_count` 增长的用例。两用例本轮复跑通过。残留：`caplog` 仍设在 `ERROR`，实现实际写 `WARNING`，canary 断言无法失败（minor，见未进表提示）。
- t016_test_f007 - 仍存在。本轮新增的 0600 断言位于 `tests/e2e/test_browser_runtime_e2e.py:2310-2311`，但模块导入区（`:13-36`）没有 `import stat`，`stat.S_IMODE` 在运行到该行时必抛 `NameError`（`pyflakes` 报 `undefined name 'stat'`）。全仓没有其他 `pulse.cookie`/`Xauthority` 的 0600 断言，AC-008 的该子项仍无有效证据。详见 f015。
- t016_test_f008 - 仍存在。`tests/unit/test_runtime_agent_protocol_export.py:68-88` 仍只对 artifact 上传、内部 profile GET、login、内部 bind 四条已知 operation 硬编码断言响应码；没有遍历 `app.routes`/OpenAPI operations 的「实现可达响应码 ⊆ 契约」守卫。新增 `test_internal_openapi_export_matches_checked_in_file`（`:40-50`）只保证内部 schema 文件与 live app 一致，不覆盖可达码集合。
- t016_test_f009 - 仍存在（minor）。`test_supervisor_reporting_routes_are_service_plane_only`（`tests/unit/test_runtime_agent_protocol_export.py:53-66`）仍只检查三条已知路径，未遍历 `app.routes`。
- t016_test_f010 - 仍存在（minor）。全仓仍无含 `/`、`?`、`#` 等特殊字符 `profile_id` 的内部 URL 编码断言。
- t016_test_f011 - 已消除（Round 2 保持）。本轮 `rg 'runtime_mode|viewer_mode' docs/blueprint docs/specs` 无输出。
- t016_test_f012 - 修不彻底（minor）。`tests/unit/test_supervisor_startup_recovery.py:294-324` 仍只证明初次对账失败后仍会尝试创建控制面（`create_control_app` 被 mock 成抛异常），没有驱动 `background_monitoring_loop` 再执行一次 `scan_and_reconcile_existing`；`stream_labels` 的字符串化仍只在 `tests/unit/test_refactor_behavior_equivalence.py:234` 传入字符串 `"3"`。
- t016_test_f013 - 已消除。`tests/unit/test_launch_args.py:46-52` 新增 `test_runtime_storage_defaults_target_uid_1000`，直接断言 `ArtifactStore(...)` 与 `ProfileService(repo=None)` 的默认 `runtime_uid == 1000`。残留：`tests/unit/test_artifact_service.py` 与 `test_profile_copy_reset.py` 中两个名为 “by default” 的用例仍显式传 1000，命名有误导（minor）。

### 改测方向复核

本轮测试预期变更均有实现或 spec 归因：`tests/unit/test_automation_cdp.py:108-115` 把「先 accept 再断开」改为「连接阶段即抛 `WebSocketDisconnect(4401)`」，对应 AC-010「控制面 CDP WebSocket 在接受连接前鉴权」；`test_supervisor_file_permissions.py`、`test_artifact_service.py`、`test_profile_copy_reset.py` 把宽松的权限断言收紧为精确 `S_IMODE`；`test_runtime_agent.py` 的启动参数用例随白名单 spec（A45）替换。未发现把旧断言改成当前实现输出的迁就型改测。唯一问题是新增 E2E 断言本身写坏（f015），不是改测方向问题。

### 本轮新发现

#### t016_test_f014 - 前端生成类型未与公开契约同步（artifact 400/413/507 缺失）

- 严重度：important
- 锚点：AC-006（「前端生成类型与契约同步」）
- 位置：`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts:2039-2105`（`upload_artifact_api_v1_profiles__profile_id__artifacts_post` 只有 201/401/403/404/422/503）；`schemas/openapi/cbrowser_v1.json:1819-1839`（artifact 路由声明 400/413/507）；生成命令 `src/frontend/package.json:16`
- 问题：用仓库内 `./src/frontend/node_modules/.bin/openapi-typescript schemas/openapi/cbrowser_v1.json` 重新生成到临时文件，与入库 `.d.ts` 比较，差异恰好是四个 artifact 操作的 400/413/507 响应缺失（120 行 diff，其余内容一致）。AC-006 已打勾，但生成类型落后于契约；`test_exported_openapi_schema_matches_live_app` 只比对 JSON schema 文件，不守护 `.d.ts`，所以现有测试不会发现。`note.md` 声称「前端类型重新生成」与实测不符。
- 建议：重新执行 `npm run generate:api` 并提交生成物；增加 `.d.ts` 漂移守卫（生成到临时文件后 diff）或把生成命令纳入门禁。

#### t016_test_f015 - 新增 AC-008 E2E 断言引用未导入的 `stat`，运行必 NameError

- 严重度：important
- 锚点：AC-008（「Pulse cookie、Xauthority 仅属主可读写」）
- 位置：`tests/e2e/test_browser_runtime_e2e.py:2310-2311`；模块导入区 `tests/e2e/test_browser_runtime_e2e.py:13-36`
- 问题：新增的两行 `assert stat.S_IMODE(...) == 0o600` 使用 `stat`，但该模块从未 `import stat`；`uv run --with pyflakes python -m pyflakes tests/e2e/test_browser_runtime_e2e.py` 报 `undefined name 'stat'`（2310、2311）。该 E2E 一旦运行到此处必抛 `NameError`，无法作为 AC-008 的证据；全仓也没有其他 Pulse cookie/Xauthority 0600 断言。f007 因此仍未消除。
- 建议：在文件顶部补 `import stat`（或改用 `os.stat(...).st_mode & 0o777`），并在真实 Docker 环境重跑该 E2E，把可复现命令与输出记入 `note.md`。

### AC 复验方式

- AC-001：`re_verified`。复跑 `tests/unit/test_runtime_agent_protocol_export.py`、`tests/integration/test_v2_api_subprocess.py`、`tests/integration/test_supervisor_rpc.py`，上报路由只在内部服务面；「枚举全部路由」仍退化为三条路径点检（f009，minor）。
- AC-002：`re_verified`。复跑 `tests/unit/test_runtime_agent.py`、`tests/unit/test_runtime_agent_faults.py`；健康探活并发、坏帧后有效事件、断线重连 rearm 均有断言并通过。真实 Chrome E2E 本轮未重跑。
- AC-003：`re_verified`。复跑 artifact/download reconciler 单测与集成测试；越界拒绝、dead-letter、信封版本、ingest 失败原因、超长名截断均有断言。dead-letter 内容保留与「人工修复后重试」仍无直接断言（minor）。
- AC-004：`re_verified`。复跑 `test_resource_fault_isolation.py`、`test_supervisor_control_auth.py`、`test_supervisor_reconcile_fences.py`、`test_supervisor_startup_recovery.py`；单 Profile 隔离、malformed stats 隔离、状态 503 映射通过。后台重试与 labels 字符串化仍无直接测试（f012，minor）。
- AC-005：`re_verified`。复跑 auth 单测/集成与 SSE broadcaster 测试；token 过期、过期 Session 清理、docs 默认关闭、auth_service 缺失 503、伪造 token 不落库、限流、SSE 快照/实时顺序均有断言并通过。`supervisor_token` 缺失 503 与 WS 4408 映射仍无端点级测试（minor）。
- AC-006：`re_verified`。复跑 OpenAPI 测试并用 `openapi-typescript` 重新生成前端类型；契约响应码守卫仍不存在（f008），且入库 `.d.ts` 与当前契约不同步（f014）。
- AC-007：`re_verified`。复跑 `tests/unit/test_domain_and_repository.py`（含 `test_models_match_migrations`）；模型与迁移一致性守卫通过。0003 既有库带数据升级到 head 仍无自动化用例（minor）。
- AC-008：`trust_prior`。单元测试复跑覆盖 snapshot/目录/cache/artifact/profile 复制精确 mode；新增的 E2E 0600 断言因 `stat` 未导入而无法执行（f015），双容器真实 Docker E2E 本轮未重跑。依赖的是 `note.md` 的 E2E 通过声明，但该声明无法用当前测试复现。
- AC-009：`re_verified`。复跑 `tests/unit/test_launch_args.py` 与 `tests/integration/test_v2_api_subprocess.py` 的 422 用例；POST 非法参数 422 且无新 Profile 通过。PATCH HTTP 级用例仍缺（minor）。
- AC-010：`re_verified`。复跑 journal 损坏隔离、累计/区间指标、下载事件有界与去重、artifact 并发配额、artifact_id 单组件、CDP WS 先鉴权、runner 路径/env 用例；内部 URL 标识符转义仍无测试（f010，minor）。
- AC-011：`re_verified`。`rg`/diff 检查 blueprint 与 spec；残留字段已清除，ObservedState 与 schema 落点一致。

coverage = 10 / 11（AC-008 为 `trust_prior`；其余为 reviewer 独立复验）

### 未进表的提示

- `tests/unit/test_auth_service.py:262` 的 `before_sessions` 赋值后未使用，Session 清理用例只断言 `len(remaining) >= 1` 而非精确行数；当前仍能通过 `all(expires_at > created_at)` 捕获未清理回归，属测试精度问题。
- `tests/unit/test_runtime_agent_faults.py:220` 的 `caplog.at_level(logging.ERROR)` 捕获不到实现写出的 `WARNING`，`canary not in caplog.text` 无法失败；不影响 AC-002 的主要断言，但该安全 canary 是空转。
- `tests/unit/test_runtime_agent.py:302-317` 用 0.6s 阈值区分并发/串行探活（三次 0.25s），在负载较高的机器上有偶发超时风险。
- `tests/unit/test_artifact_service.py` 与 `tests/unit/test_profile_copy_reset.py` 中名为 “by default” 的用例仍显式传 `runtime_uid=1000`；默认值已由 `test_launch_args.py:46-52` 守护，命名可后续清理。
- AC-003 的 dead-letter 用例只断言隔离文件存在，未断言内容保留与「人工修复后可重试」；Agent 磁盘下载事件的 `version` 字段仍无直接断言。
- `src/frontend/tsconfig.tsbuildinfo` 仍在工作区被修改；`docs/blueprint/testing.md` 要求构建后还原（范围外仓库卫生）。
- `note.md` 自述 unit 530 passed、Browser Runtime E2E 通过；本地复跑 `tests/unit` 为 537 passed、`tests/integration` 为 79 passed、`src/backend/tests` 为 384 passed、模板契约 169 passed。E2E 的 scratch 目录为空且新增断言写坏，不能采信「E2E 通过」的自述。

### 结论

- 前轮 finding 复核：f001、f002、f003、f004、f005、f006、f011、f013 已消除（f001/f003/f005/f006 有 minor 残留）；f007 仍存在且本轮新增证据本身 broken（f015）；f008 仍存在；f009、f010、f012 仍为 minor 残留。
- 改测方向复核：无「迁就实现」的改测；`test_automation_cdp.py` 的 pre-accept 断言变更对应 AC-010 的鉴权前移。
- 本轮新发现：2 条（f014 important、f015 important）。
- 未进表的提示：见上。
- 总体判断：核心测试缺口继续收敛，但 AC-006 的可达码守卫与前端类型同步仍不成立（f008、f014），AC-008 的 Pulse/Xauthority 0600 证据因 E2E 断言写坏而失效（f007、f015），当前不能 PASS。
- 系统性 follow-up：无（均在 t016 自身 AC 范围）。

verdict: FAIL

## Round 4 (2026-11-03T04:26:49+08:00)

reviewed_scope: 026a732d5e26f680

### 前轮 finding 复核

- t016_test_f001 - 已消除（保持）。`tests/unit/test_domain_and_repository.py:37-42` 仍先 `run_database_migrations`，`:541-561` 的 `test_models_match_migrations` 本轮复跑通过。残留「0003 带数据升级到 head」仍无自动化用例（minor）。
- t016_test_f002 - 已消除（保持）。`tests/integration/test_v2_api_subprocess.py:193-199` 用真实 HTTP 进程断言非法 `launch_args` 返回 422 且无新增 Profile，本轮 `tests/integration` 79 passed。PATCH HTTP 级用例仍缺（minor）。
- t016_test_f003 - 已消除（保持）。`tests/unit/test_auth_service.py:254-259` 覆盖 token 过期，`:261-270` 覆盖过期 Session 清理，`tests/unit/test_runtime_agent_protocol_export.py:99-106` 覆盖 docs 默认关闭，`tests/unit/test_auth_service.py:306-315` 覆盖 auth_service 缺失 503；本轮复跑通过。`app.state.supervisor_token` 缺失时内部面 503 仍无端点级用例（minor）。
- t016_test_f004 - 已消除（保持）。`tests/unit/test_auth_service.py:242-250` 断言伪造/未知 token 后 `audit_events` 行数不变，`:272-282` 断言同源连续失败后 `rate_limited`。公开 WS 入口把 `rate_limited` 映射为 close code 4408 仍无端点级用例（minor）。
- t016_test_f005 - 已消除（保持）。`tests/unit/test_runtime_event_broadcaster_epoch.py:168-188` 在快照 provider 阻塞期间并发 `publish`，断言 snapshot 先于 live 且 ID 单调，本轮通过。用快照事件 ID 作 `Last-Event-ID` 重连只补间隙事件的用例仍缺（minor）。
- t016_test_f006 - 已消除（保持）。`tests/unit/test_runtime_agent_faults.py:175-224` 坏帧后有效 `Browser.downloadWillBegin` 进入 `active_downloads`，`:228-259` 断线后自动重连且 `rearm_count` 增长，本轮通过。`caplog` 仍设在 `ERROR`（实现写 WARNING），canary 断言空转（minor）。
- t016_test_f007 - 仍存在（blocking）。唯一新增的 Pulse cookie/Xauthority 0600 断言位于 `tests/e2e/test_browser_runtime_e2e.py:2310-2311`，但模块导入区 `:13-26` 仍无 `import stat`，运行到该行必抛 `NameError`；全仓无其他 `pulse.cookie`/`Xauthority` 0600 断言。AC-008 该子项仍无有效测试证据（与 f015 同源）。
- t016_test_f008 - 仍存在（blocking）。`tests/unit/test_runtime_agent_protocol_export.py:68-97` 仍是对 artifact 上传、内部 profile GET/ingest、desired-state、bind 的硬编码子集断言，没有遍历 `app.routes` 或全部 OpenAPI operations 的「实现可达响应码 ⊆ 契约」守卫。新增路由、或未被点名的 operation 多返回一个状态码时，现有测试不会失败；AC-006 已打勾但守卫要求未满足。
- t016_test_f009 - 仍存在（minor）。`tests/unit/test_runtime_agent_protocol_export.py:53-66` 仍只点检三条已知上报路径，未遍历 `app.routes`。
- t016_test_f010 - 仍存在（minor）。全仓仍无含 `/`、`?`、`#`、空格等特殊字符 `profile_id` 的内部 URL 编码断言。
- t016_test_f011 - 已消除（保持）。`rg 'runtime_mode|viewer_mode'` 在 `docs/blueprint`、`docs/specs`、schemas、v2 源码与生成类型中无输出；仅 Alembic 迁移按需引用。
- t016_test_f012 - 修不彻底（minor）。`tests/unit/test_supervisor_startup_recovery.py:294-323` 仍只证明初次对账失败后仍会创建控制面（`create_control_app` 被 mock 成抛异常），没有驱动后台 monitoring loop 再执行一次 `scan_and_reconcile_existing`；`stream_labels(..., 3)` 的字符串化仍无断言。
- t016_test_f013 - 已消除（保持）。`tests/unit/test_launch_args.py:46-52` 直接断言 `ArtifactStore(...)` 与 `ProfileService(...)` 的默认 `runtime_uid == 1000`。两个名为 “by default” 的旧用例仍显式传 1000（命名残留，minor）。
- t016_test_f014 - 已消除。本轮用 `src/frontend/node_modules/.bin/openapi-typescript` 从 `schemas/openapi/cbrowser_v1.json` 重新生成到临时文件，与 `src/frontend/src/shared/api/generated/cbrowser_v1.d.ts` 字节一致（`cmp` MATCH），artifact 400/413/507 等响应已包含。
- t016_test_f015 - 仍存在（blocking）。`tests/e2e/test_browser_runtime_e2e.py:2310-2311` 仍引用未导入的 `stat`；`pyflakes` 报 `undefined name 'stat'`（两行）。E2E 执行到此处必 `NameError`，`note.md` 的 E2E 通过自述无法用当前测试复现。

### 改测方向复核

以当前完整 diff 为准，本轮可见增量主要是重新生成公开 OpenAPI 前端类型（f014 消除）与声称的 `stat` 修复（未落地）；未见新增或改写既有测试预期，也没有把旧断言改成当前实现输出的迁就型改测。E2E 0600 断言写坏属测试代码缺陷（f015），不是改测方向问题。

### 本轮新发现

- 0 条新 finding；f007、f008、f015 为前轮未解决的 blocker。

### AC 复验方式

- AC-001：`re_verified`。复跑 `tests/unit/test_runtime_agent_protocol_export.py`、`tests/integration/test_v2_api_subprocess.py`、`tests/integration/test_supervisor_rpc.py`；上报路由只在内部服务面。枚举全部路由仍退化为三条路径点检（f009，minor）。
- AC-002：`re_verified`。复跑 `tests/unit/test_runtime_agent.py`、`tests/unit/test_runtime_agent_faults.py`；健康探活并发、坏帧后有效事件消费、断线重连 rearm 均通过。真实 Chrome E2E 本轮未重跑。
- AC-003：`re_verified`。复跑 `tests/unit/test_artifact_service.py`、`test_download_reconciler.py`、`test_supervisor_event_delivery.py`、`test_runtime_instance_storage.py`；越界拒绝、dead-letter、信封版本、失败原因、长文件名截断、有界保留与去重均有断言。
- AC-004：`re_verified`。复跑 `tests/unit/test_resource_fault_isolation.py`、`test_supervisor_control_auth.py`、`test_supervisor_reconcile_fences.py`、`test_supervisor_startup_recovery.py`；单 Profile 隔离与 malformed 状态 503 映射通过。后台重试仍无直接测试（f012，minor）。
- AC-005：`re_verified`。复跑 auth 单测/集成与 SSE broadcaster 测试；token 过期、过期 Session 清理、docs 默认关闭、auth_service 缺失 503、伪造 token 不落库、限流、快照/实时顺序均通过。`supervisor_token` 503 与 WS 4408 映射仍无端点级用例（minor）。
- AC-006：`re_verified`。复跑 `tests/unit/test_runtime_agent_protocol_export.py`；用 `openapi-typescript` 重新生成前端类型与入库文件字节一致（f014 消除）。可达码守卫仍不存在（f008）。
- AC-007：`re_verified`。复跑 `tests/unit/test_domain_and_repository.py`（真实迁移 fixture + `compare_metadata` 守卫）；`rg` 确认代码/契约/生成类型无 `runtime_mode`/`viewer_mode`。带数据旧库升级仍无自动化用例（minor）。
- AC-008：`trust_prior`。单元测试复跑覆盖 snapshot/目录/cache/artifact/profile 复制的精确 mode；Pulse cookie/Xauthority 0600 的唯一断言因 `stat` 未导入无法执行（f007/f015），双容器真实 Docker E2E 本轮未重跑。
- AC-009：`re_verified`。复跑 `tests/unit/test_launch_args.py` 与 `tests/integration/test_v2_api_subprocess.py` 的 422 用例；runner 第二道校验有单测。PATCH HTTP 级用例仍缺（minor）。
- AC-010：`re_verified`。复跑 journal 损坏隔离、累计/区间指标、下载事件有界保留与去重、artifact 并发配额、artifact_id 单组件、CDP WS 先鉴权、runner 路径/env 用例；内部 URL 标识符转义仍无测试（f010，minor）。
- AC-011：`re_verified`。`rg`/diff 检查 blueprint 与 spec；残留字段已清除，ObservedState 与 schema 落点一致。

coverage = 10 / 11（AC-008 为 `trust_prior`；其余为 reviewer 独立复验）

### 未进表提示

- `pyflakes` 在 `tests/unit/test_auth_service.py:262` 报 `before_sessions` 赋值未使用；Session 清理用例仍只断言 `len(remaining) >= 1`（`all(expires_at > created_at)` 仍能捕获未清理回归）。
- `tests/unit/test_launch_args.py:51` 的 `# type: ignore[arg-type]` 属仓库既有测试约定，仅抑制 `ProfileService(repo=None)` 的静态类型告警，不改变运行行为，且项目无 typecheck 门禁，故不按「静默错误」出 finding。
- `tests/unit/test_artifact_service.py:361` 与 `tests/unit/test_profile_copy_reset.py:546` 中名为 “by default” 的用例仍显式传 `runtime_uid=1000`；默认值已由 `test_launch_args.py` 守护，命名可后续清理。
- `tests/e2e/test_browser_runtime_e2e.py` 的 0600 断言除缺 `stat` 外，本轮未在真实 Docker 拓扑重跑；修复后需重跑并把输出记入 `note.md`。
- `src/frontend/tsconfig.tsbuildinfo` 仍在工作区被修改；`docs/blueprint/testing.md` 要求构建后还原（范围外仓库卫生）。
- 本轮复跑：`tests/unit` 537 passed、`tests/integration` 79 passed、`src/backend/tests` 384 passed、模板契约 169 passed；数量以实际输出为准。

### 结论

- 前轮 finding 复核：f001、f002、f003、f004、f005、f006、f011、f013、f014 已消除（多项有 minor 残留）；f009、f010、f012 仍为 minor；f007、f008、f015 仍为未解决 important。
- 改测方向复核：无「迁就实现」的改测；本轮只有前端类型重新生成与未落地的 `stat` 修复。
- 本轮新发现：0 条。
- 未进表的提示：见上。
- 总体判断：公开 OpenAPI 前端类型已同步（f014 消除），但 AC-006 的可达码守卫仍缺失（f008），AC-008 的 Pulse/Xauthority 0600 证据仍因 `stat` 未导入而不可执行（f007/f015），当前不能 PASS。
- 系统性 follow-up：无（均在 t016 自身 AC 范围）。

verdict: FAIL

## Round 5 (2026-11-03T04:42:27+08:00)

reviewed_scope: b4916e893f916e54

### 前轮 finding 复核

- t016_test_f007 - 已消除（证据可执行）。`tests/e2e/test_browser_runtime_e2e.py:22` 已补 `import stat`，`:2311-2312` 对宿主机挂载的 `Xauthority` 与 `pulse.cookie` 断言 `stat.S_IMODE(...) == 0o600`。`py_compile` 与 `pyflakes` 均无报错，`pytest --collect-only` 可正常收集该用例；实现 `src/backend/cbrowser/runtime_agent/runner.py:174,269` 确实对两文件 `chmod(0o600)`。残留（不阻断）：仍无单元级精确 mode 用例，且本轮缺少 Linux engine cache 无法真实执行该 Docker E2E，AC-008 仍按 `trust_prior` 处理。
- t016_test_f008 - 已消除（主体）。`tests/unit/test_runtime_agent_protocol_export.py:109-129` 新增 `test_openapi_all_operations_declare_structural_contract_codes`：遍历 public/internal 全部 OpenAPI operations，按路径/方法断言 401/403/503、路径参数 404、写操作 422、公开 artifact 400/413/507；结合 `:68-97` 的 bind/desired-state/internal artifact 404/409 与 login 429 定点断言，已补上 Round 4 要求的全路由枚举守卫。本轮复跑该文件 9 passed。残留（不阻断）：守卫验证的是「契约包含结构性错误码集合」，不是从实现异常路径动态推导可达码；例如 `src/backend/cbrowser/api/v1/artifact_router.py:45` 的兜底 500 仍未在契约声明，也不会被该测试发现。
- t016_test_f015 - 已消除。同一修复补上 `import stat`；`pyflakes` 对 `tests/e2e/test_browser_runtime_e2e.py` 无输出（此前 2310/2311 的 `undefined name 'stat'` 消失），`py_compile` 通过，E2E collect-only 成功。

其余前轮项：本轮仅新增上述两处测试改动，f001-f006、f011、f013、f014 保持已消除；f009、f010、f012 仍为 minor。

### 改测方向复核

无「迁就实现」的改测。本轮新增/修改仅为：E2E 补 `import stat` 与 0600 断言（AC-008 行为验证），以及新增全 operation 契约码枚举测试（AC-006 守卫）；未删除或反转任何既有断言，未修改既有测试预期以匹配当前实现输出。

### 本轮新发现

- 0 条新 finding；无未解决的 critical / important。

### AC 复验方式

- AC-001：`re_verified`。复跑 `tests/unit/test_runtime_agent_protocol_export.py`、`tests/integration/test_v2_api_subprocess.py`、`tests/integration/test_supervisor_rpc.py`；上报路由只在内部服务面。「枚举全部路由」仍退化为三条路径点检（f009，minor）。
- AC-002：`re_verified`。复跑 `tests/unit/test_runtime_agent.py`、`tests/unit/test_runtime_agent_faults.py`；健康探活并发、坏帧后有效事件消费、断线重连 rearm 断言均通过。真实 Chrome E2E 本轮未重跑。
- AC-003：`re_verified`。复跑 artifact/download reconciler 单测与集成测试；越界拒绝、dead-letter、信封版本、ingest 失败原因、长文件名截断、有界保留与去重均有断言。
- AC-004：`re_verified`。复跑 `test_resource_fault_isolation.py`、`test_supervisor_control_auth.py`、`test_supervisor_reconcile_fences.py`、`test_supervisor_startup_recovery.py`；单 Profile 隔离与 malformed 状态 503 映射通过。后台重试仍无直接测试（f012，minor）。
- AC-005：`re_verified`。复跑 auth 单测/集成与 SSE broadcaster 测试；token 过期、过期 Session 清理、docs 默认关闭、auth_service 缺失 503、伪造 token 不落库、限流、快照/实时顺序均通过。
- AC-006：`re_verified`。复跑 OpenAPI 测试（9 passed），确认全 operation 结构码守卫存在且通过；用 `openapi-typescript` 重新生成前端类型与入库文件在 Round 4 已验证一致。守卫的「可达码动态推导」残留见 f008 说明。
- AC-007：`re_verified`。复跑 `tests/unit/test_domain_and_repository.py`（真实迁移 fixture + `compare_metadata` 守卫）；`rg` 确认代码/契约/生成类型无 `runtime_mode`/`viewer_mode`。带数据旧库升级仍无自动化用例（minor）。
- AC-008：`trust_prior`。E2E 的 0600 断言已可执行且实现侧 chmod 路径已核实，但本机无 `CBROWSER_RUNTIME_ENGINE_CACHE` 的 Linux chromium 缓存，未真实运行双容器 E2E；依赖实施侧的 Browser Runtime E2E 声明与本轮静态核实。
- AC-009：`re_verified`。复跑 `tests/unit/test_launch_args.py` 与 `tests/integration/test_v2_api_subprocess.py` 的 422 用例；runner 第二道校验有单测。PATCH HTTP 级用例仍缺（minor）。
- AC-010：`re_verified`。复跑 journal 损坏隔离、累计/区间指标、下载事件有界保留与去重、artifact 并发配额、artifact_id 单组件、CDP WS 先鉴权、runner 路径/env 用例；内部 URL 标识符转义仍无测试（f010，minor）。
- AC-011：`re_verified`。`rg`/diff 检查 blueprint 与 spec；残留字段已清除，ObservedState 与 schema 落点一致。

coverage = 10 / 11（AC-008 为 `trust_prior`；其余为 reviewer 独立复验）

### 未进表的提示

- `tests/unit/test_runtime_agent_protocol_export.py:109-129` 的枚举守卫是结构映射而非动态可达码推导；`artifact_router.py:45` 的 500 兜底仍不在契约中（可选加固，不阻断本 AC 的既有缺陷修复）。
- `test_supervisor_reporting_routes_are_service_plane_only` 仍只检查三条路径（f009 minor）。
- 全仓仍无含 `/`、`?`、`#`、空格等特殊字符 `profile_id` 的内部 URL 编码断言（f010 minor）。
- `test_supervisor_startup_recovery.py` 的后台重试与 `stream_labels(..., 3)` 字符串化仍无直接测试（f012 minor）。
- `tests/e2e/test_browser_runtime_e2e.py` 的 0600 断言本轮未在真实 Docker 执行：镜像存在但 `.scratch/t003_implementation/tmp/engine-cache` 为空，E2E 前置不满足；只能确认测试可执行与实现 chmod 路径。
- 本轮复跑：`tests/unit` 538 passed，`tests/integration` 79 passed，`tests/unit/test_runtime_agent_protocol_export.py` 9 passed；`pyflakes` 与 `py_compile` 干净。
- `src/frontend/tsconfig.tsbuildinfo` 仍在工作区被修改；`docs/blueprint/testing.md` 要求构建后还原（范围外仓库卫生）。
- `note.md` 未记录本轮修复，仍为旧验证声明；实施侧收尾时需补记（不改变本轮 verdict）。

### 结论

- 前轮 finding 复核：f007、f008、f015 均已消除/主体消除；f009、f010、f012 仍为 minor；其余保持已消除。
- 改测方向复核：无。
- 本轮新发现：0 条。
- 未进表的提示：见上。
- 总体判断：Round 4 的三项 blocker 已用 diff、代码与测试核实修复，剩余仅为 non-blocking minor 与 AC-008 的 `trust_prior` 环境限制，可 PASS。
- 系统性 follow-up：无。

verdict: PASS

## Round 6 (2026-11-03T04:56:30+08:00)

reviewed_scope: 511322016902a4df

### 前轮 finding 复核

- t016_test_f007 - 已消除（保持）。`tests/e2e/test_browser_runtime_e2e.py:22` 仍有 `import stat`，`:2311-2312` 的 Xauthority / pulse.cookie 0600 断言可执行；`pyflakes` 对该文件无输出，`tests/e2e --collect-only` 79 tests 正常收集。
- t016_test_f008 - 已消除（保持）。`tests/unit/test_runtime_agent_protocol_export.py:109-129` 的全 operation 结构码守卫仍在，本轮复跑该文件通过。
- t016_test_f015 - 已消除（保持）。与 f007 同一修复，无 `undefined name 'stat'`。
- t016_test_f001/f002/f003/f004/f005/f006/f011/f013/f014 - 保持已消除；本轮复跑 `tests/unit` 539 passed、`tests/integration` 79 passed、`src/backend/tests` 384 passed、模板契约 169 passed，无回归。
- t016_test_f009 - 仍存在（minor）。`test_supervisor_reporting_routes_are_service_plane_only` 仍只点检三条路径。
- t016_test_f010 - 仍存在（minor）。本轮实现补了 `src/backend/cbrowser/api/v1/automation_router.py:61` 与 `src/backend/cbrowser/api/runtime_coordinator.py:420` 的 `quote(profile_id, safe="")`，但全仓仍无特殊字符 `profile_id` 的 URL 编码断言；该测试缺口未变。
- t016_test_f012 - 仍存在（minor）。后台对账重试与 `stream_labels(..., 3)` 字符串化仍无直接测试。

### 六项 minor 修复复核（本轮增量）

- 限流来源：已修（代码）。`src/backend/cbrowser/api/v1/automation_router.py:83-92` 用 `resolve_client_ip` + `app.state.trusted_proxy_cidrs` 解析来源，`:95` 把 `rate_limited` 映射为 close code 4408；`tests/unit/test_auth_client_ip.py` 覆盖解析器，`tests/unit/test_auth_service.py:272-282` 覆盖服务层限流。残留（minor）：公开 WS 的 XFF 来源与 4408 映射仍无端点级用例；`src/backend/cbrowser/api/internal_gateway.py:123` 仍用固定 `"internal-gateway"` 键。
- URL 转义：已修（代码）。上述两处已 `quote(..., safe="")`；测试缺口仍由 f010 跟踪（minor）。
- 损坏事件隔离：已修并有新测试。`src/backend/cbrowser/runtime_agent/event_storage.py:206-221,322-338` 对损坏下载事件文件移入 `quarantine/` 后继续；`tests/unit/test_runtime_instance_storage.py:157-166` 的 `test_corrupt_download_event_is_quarantined_and_does_not_block_new_events` 本轮复跑通过。残留（minor）：未断言错误日志、隔离文件内容保留与「修复后重试」。
- 属性初始化：已修（代码）。`src/backend/cbrowser/runtime_agent/cdp_proxy.py:51` 初始化 `_last_rearm_ok=False`，`:65` 的 `capture_alive` 依赖它，`:336` 的 `close()` 清零；无直接测试覆盖 start 前读取（minor）。
- 重复校验器：未修（代码层，见未进表提示）。`src/backend/cbrowser/domain/models.py:305-308` 与 `:349-354` 仍是两个 `launch_args` 校验器；实测 `ProfileUpdateRequest(launch_args=None).model_dump(exclude_unset=True)` 仍返回 `{"launch_args": []}`。
- 文档：部分修复。`docs/blueprint/security.md:32-35` 与 `docs/blueprint/browser_runtime.md:19` 的 X11 权限改为 0750、删除 0777/0666 回退描述；`docs/specs_index.md` 的 storage_and_artifacts/runtime_persistence 已登记 t016；`docs/specs/v2_runtime_validation.md:135` 已加 t001 时点标注；`rg 'runtime_mode|viewer_mode' docs/blueprint docs/specs schemas src/backend/cbrowser src/frontend/src/shared/api/generated` 无输出（exit 1）。残留两处文档不一致（`docs/blueprint/domain.md:27` 的 `failed`、`docs/blueprint/artifacts.md:14` 的 0755/0644 回退描述）由 code review Round 6 的 `t016_code_f010` 跟踪，属 non-blocking minor。

### 改测方向复核

无「迁就实现」的改测。Round 5 后测试增量仅为 `tests/unit/test_runtime_instance_storage.py:157-166` 新增的损坏事件隔离用例，断言隔离文件落位与新事件仍可保存/读取，属行为级验证；未删除、反转或弱化既有断言。

### 本轮新发现

- 0 条新 finding；无未解决的 critical / important。

### AC 复验方式

- AC-001：`re_verified`。复跑 `tests/unit/test_runtime_agent_protocol_export.py` 与 `tests/integration/test_v2_api_subprocess.py`；上报路由只在内部服务面。「枚举全部路由」仍退化为三条路径点检（f009，minor）。
- AC-002：`re_verified`。复跑 `tests/unit/test_runtime_agent.py`、`test_runtime_agent_faults.py`；坏帧后有效事件消费、断线重连 rearm 断言通过。真实 Chrome E2E 未重跑。
- AC-003：`re_verified`。复跑 `test_runtime_instance_storage.py`（含新增损坏事件隔离用例）、`test_download_reconciler.py` 等；越界拒绝、dead-letter、信封版本、长文件名截断、有界保留与去重均有断言。隔离文件内容保留与人工修复后重试仍无直接断言（minor）。
- AC-004：`re_verified`。复跑 `test_resource_fault_isolation.py`、`test_supervisor_control_auth.py`、`test_supervisor_reconcile_fences.py`、`test_supervisor_startup_recovery.py`；单 Profile 隔离与 503 映射通过。后台重试仍无直接测试（f012，minor）。
- AC-005：`re_verified`。复跑 auth 单测/集成与 SSE broadcaster 测试；token 过期、过期 Session 清理、docs 默认关闭、auth_service 缺失 503、伪造 token 不落库、服务层限流、快照/实时顺序均通过。WS 4408 端点级用例仍缺（minor）。
- AC-006：`re_verified`。复跑 `tests/unit/test_runtime_agent_protocol_export.py`（全 operation 结构码守卫）；前端生成类型在 Round 4 已用 `openapi-typescript` 重新生成并比对一致。
- AC-007：`re_verified`。复跑 `tests/unit/test_domain_and_repository.py`（真实迁移 fixture + `compare_metadata` 守卫）；`rg` 确认代码/契约/生成类型无 `runtime_mode`/`viewer_mode`。带数据旧库升级仍无自动化用例（minor）。
- AC-008：`trust_prior`。单元测试复跑覆盖 snapshot/目录/cache/artifact/profile 复制的精确 mode；E2E 0600 断言已可执行但本机无 Linux engine cache，未真实运行双容器 E2E；依赖实施侧 Browser Runtime E2E 声明。
- AC-009：`re_verified`。复跑 `tests/unit/test_launch_args.py` 与 `tests/integration/test_v2_api_subprocess.py` 的 422 用例；runner 第二道校验有单测。PATCH HTTP 级用例仍缺（minor）。
- AC-010：`re_verified`。复跑 journal 损坏隔离、累计/区间指标、下载事件有界保留与去重、artifact 并发配额、artifact_id 单组件、CDP WS 先鉴权、runner 路径/env 用例；内部 URL 转义实现已补齐但无测试（f010，minor）。
- AC-011：`re_verified`。`rg`/diff 检查 blueprint 与 spec；六项 minor 中的文档项主体已修，残留 `docs/blueprint/domain.md:27` 的 `failed` 与 `docs/blueprint/artifacts.md:14` 的 0755/0644 回退描述（由 code review `t016_code_f010` 跟踪，minor）。

coverage = 10 / 11（AC-008 为 `trust_prior`；其余为 reviewer 独立复验）

### 未进表的提示

- 代码层（不属测试 review 职责）：「重复校验器」修复未落地。`src/backend/cbrowser/domain/models.py:305-308` 与 `:349-354` 仍是两个 `launch_args` 校验器，显式 `null` 仍被 `filter_launch_args` 转成 `[]`（实测 `ProfileUpdateRequest(launch_args=None).model_dump(exclude_unset=True) == {"launch_args": []}`）；与 note.md 声称已修不符，需 code reviewer 或实施侧复核。
- 代码层：`src/backend/cbrowser/api/internal_gateway.py:123` 的限流键仍固定为 `"internal-gateway"`，f013 建议的「内部网关可被锁死」分支未处理。
- `tests/unit/test_runtime_agent_faults.py:220` 的 `caplog.at_level(logging.ERROR)` 仍捕获不到实现写出的 WARNING，canary 断言空转（既有 minor）。
- AC-003 的隔离区用例只断言文件落位与新事件可保存，未断言错误日志、隔离内容保留与「人工修复后重试」。
- 全仓仍无含 `/`、`?`、`#`、空格等特殊字符 `profile_id` 的内部 URL 编码断言（f010 minor）。
- `tests/unit/test_artifact_service.py:361` 与 `tests/unit/test_profile_copy_reset.py:546` 中名为 “by default” 的用例仍显式传 `runtime_uid=1000`（命名残留）。
- `src/frontend/tsconfig.tsbuildinfo` 仍在工作区被修改；`docs/blueprint/testing.md` 要求构建后还原（范围外仓库卫生）。
- 本轮复跑：`tests/unit` 539 passed、`tests/integration` 79 passed、`src/backend/tests` 384 passed、`.repo_template/tests -m contract` 169 passed、`tests/e2e --collect-only` 79 tests；`pyflakes` 对本次改动文件无输出。当前 worktree 重算指纹 `511322016902a4df` 与注入值一致。

### 结论

- 前轮 finding 复核：f007、f008、f015 保持已消除；f009、f010、f012 仍为 minor；其余保持已消除。
- 六项 minor 修复复核：限流来源、URL 转义、损坏事件隔离、属性初始化四项已落地并验证；文档主体已修、残留两处 minor 由 code review `t016_code_f010` 跟踪；「重复校验器」未落地（代码层，已提示，不构成本测试报告 blocker）。
- 改测方向复核：无。
- 本轮新发现：0 条。
- 未进表的提示：见上。
- 总体判断：Round 5 的 PASS 结论未被推翻，本轮无新增 critical / important 测试问题，剩余均为 non-blocking minor 与 AC-008 的 `trust_prior` 环境限制，维持 PASS。
- 系统性 follow-up：无。

verdict: PASS

## Round 7 (evidence repair)

reviewed_scope: 568063954593bda2

### 前轮 finding 复核

- t016_test_f001 - 保持已消除。`tests/unit/test_domain_and_repository.py:39` 的 fixture 仍走 `run_database_migrations`，`:541-561` 的 `test_models_match_migrations`（真实迁移 schema + `compare_metadata == []`）本轮复跑通过。残留仍是「0003 既有库带数据升级到 head」无自动化用例（minor）。
- t016_test_f002 - 保持已消除。`tests/integration/test_v2_api_subprocess.py:190-199` 仍通过真实 HTTP 进程断言非法 `launch_args` 返回 422 且 Profile 数量不变，本轮 `tests/integration` 79 passed。PATCH 的 HTTP 级 422 用例仍缺（minor）。
- t016_test_f003 - 保持已消除。`tests/unit/test_auth_service.py` 覆盖 `expires_in_hours=-1` 返回 `token_expired`、过期 Session 清理、同源连续失败 `rate_limited`；`tests/unit/test_runtime_agent_protocol_export.py` 覆盖 docs 默认关闭；`test_missing_auth_service_returns_503` 覆盖 503。
- t016_test_f004 - 保持已消除。`tests/unit/test_auth_service.py:248-250` 断言伪造/未知 token 前后 `audit_events` 行数不变；`:272-282` 断言限流。公开 WS 的 4408 端点级用例仍缺（minor）。
- t016_test_f005 - 保持已消除。`tests/unit/test_runtime_event_broadcaster_epoch.py:168-190` 在快照 provider 阻塞期间并发 `publish`，断言 snapshot 先于 live 且事件序号单调；`tests/integration/test_api_sse_events.py:61-141` 覆盖 `Last-Event-ID` 续传。本轮复跑通过。
- t016_test_f006 - 保持已消除。`tests/unit/test_runtime_agent_faults.py:175-224` 坏帧后有效 `Browser.downloadWillBegin` 进入 `active_downloads`；`:228-259` 断线后自动重连且 `rearm_count` 增长。本轮复跑通过。
- t016_test_f007 - 保持已消除（静态）。`tests/e2e/test_browser_runtime_e2e.py:22` 已 `import stat`，`:2311-2312` 的 Xauthority / pulse.cookie `S_IMODE == 0o600` 断言可执行；`pyflakes` 该文件无报错，`tests/e2e --collect-only` 79 tests 正常收集。真实 Docker E2E 本轮未重跑，见 AC-008 `trust_prior`。
- t016_test_f008 - 保持已消除（主体）。`tests/unit/test_runtime_agent_protocol_export.py:109-129` 的全 operation 结构码守卫仍在并通过；残留仍是「结构映射而非动态可达码推导」（minor，见未进表提示）。
- t016_test_f009 - 仍存在（minor）。`test_supervisor_reporting_routes_are_service_plane_only`（`tests/unit/test_runtime_agent_protocol_export.py:53-66`）仍只点检三条上报路径，未遍历全部路由。
- t016_test_f010 - 仍存在（minor）。`src/backend/cbrowser/api/v1/automation_router.py` 与 `runtime_coordinator.py` 已用 `quote(profile_id, safe="")`，但全仓仍无含 `/`、`?`、`#`、空格等特殊字符 `profile_id` 的内部 URL 编码断言。
- t016_test_f011 - 保持已消除。`rg 'runtime_mode|viewer_mode' docs/blueprint docs/specs schemas src/backend/cbrowser src/frontend/src/shared/api/generated` 无输出；蓝图中残留的 `domain.md:27` `failed` 与 `artifacts.md:14` 的 0755/0644 回退描述由 code review `t016_code_f010` / p017 跟踪（minor）。
- t016_test_f012 - 仍存在（minor）。`tests/unit/test_supervisor_startup_recovery.py:294-324` 只证明初次对账失败后仍会创建控制面；后台 monitoring loop 的再次对账与 `stream_labels(..., 3)` 字符串化仍无直接断言。
- t016_test_f013 - 保持已消除。`tests/unit/test_launch_args.py:46-52` 直接断言 `ArtifactStore(...)` 与 `ProfileService(repo=None)` 的默认 `runtime_uid == 1000`；两个名为 “by default” 的用例仍显式传 1000（命名残留，minor）。
- t016_test_f014 - 保持已消除。本轮用 `src/frontend/node_modules/.bin/openapi-typescript` 从 `schemas/openapi/cbrowser_v1.json` 重新生成到临时文件，与 `src/frontend/src/shared/api/generated/cbrowser_v1.d.ts` `cmp` 一致（cmp=0），artifact 400/413/507 已在生成类型中。
- t016_test_f015 - 保持已消除。与 f007 同一修复；`pyflakes` 对 `tests/e2e/test_browser_runtime_e2e.py` 无 `undefined name 'stat'`，E2E 可正常收集。

### 改测方向复核

无「迁就实现」的改测。相对 Round 6，`tests/` 下无文件在 2026-11-03 04:56 后发生改动；本轮复跑的测试预期仍对应已批准的 spec 变更（字段删除、白名单、精确权限、Artifact 返回类型、信封版本、pre-accept CDP 鉴权），未发现把旧断言改成当前实现输出的情况。

### 本轮新发现

- 0 条新 finding；无未解决的 critical / important。

### AC 复验方式

- AC-001：`re_verified`。复跑 `tests/unit/test_runtime_agent_protocol_export.py`、`tests/integration/test_v2_api_subprocess.py` 与 `test_supervisor_rpc.py`；上报路由只存在于内部服务面。枚举全部路由仍退化为三条路径点检（f009，minor）。
- AC-002：`re_verified`。复跑 `tests/unit/test_runtime_agent.py`、`test_runtime_agent_faults.py`；健康探活并发、坏帧后有效事件消费、断线重连 rearm 均通过。真实 Chrome E2E 本轮未重跑。
- AC-003：`re_verified`。复跑 `test_artifact_service.py`、`test_download_reconciler.py`、`test_supervisor_event_delivery.py`、`test_runtime_instance_storage.py`；越界拒绝、dead-letter、信封版本兼容/隔离、ingest 失败原因、长文件名截断、有界保留与去重均有断言。隔离后「人工修复再重试」仍无直接用例（minor）。
- AC-004：`re_verified`。复跑 `test_resource_fault_isolation.py`、`test_supervisor_control_auth.py`、`test_supervisor_reconcile_fences.py`、`test_supervisor_startup_recovery.py`；单 Profile 隔离、malformed 状态 503、启动对账失败不阻断控制面通过。后台重试仍无直接测试（f012，minor）。
- AC-005：`re_verified`。复跑 auth 单测、SSE broadcaster 与 integration SSE；token 过期、过期 Session 清理、docs 默认关闭、服务未配置 503、伪造 token 不落库、服务层限流、快照/实时顺序与 `Last-Event-ID` 续传均通过。WS 4408 端点级用例仍缺（minor）。
- AC-006：`re_verified`。复跑 `tests/unit/test_runtime_agent_protocol_export.py`（含全 operation 结构码守卫）；`openapi-typescript` 重新生成前端类型与入库文件 `cmp` 一致（cmp=0）。守卫的可达码动态推导残留见 f009 说明。
- AC-007：`re_verified`。复跑 `tests/unit/test_domain_and_repository.py`（真实迁移 fixture + `compare_metadata` 守卫）；`rg` 确认代码/契约/生成类型无 `runtime_mode`/`viewer_mode`。带数据旧库升级仍无自动化用例（minor）。
- AC-008：`trust_prior`。单元测试复跑覆盖 snapshot/目录/cache/artifact/profile 复制的精确 mode；`tests/e2e/test_browser_runtime_e2e.py:2311-2312` 的 0600 断言已可执行且 `--collect-only` 通过，但本机无 Linux engine cache，未真实运行双容器 E2E；依赖实施侧已产出的 Browser/Stream E2E 证据。
- AC-009：`re_verified`。复跑 `tests/unit/test_launch_args.py` 与 `tests/integration/test_v2_api_subprocess.py` 的 422 用例；runner 第二道校验有单测，白名单覆盖扩展、JS 引擎、位置参数与指纹参数拒绝。PATCH HTTP 级用例仍缺（minor）。
- AC-010：`re_verified`。复跑 journal 损坏隔离、累计/区间指标、下载事件有界保留与去重、artifact 并发配额、artifact_id 单组件、CDP WS 先鉴权、runner 路径/env 用例。内部 URL 转义仍无测试（f010，minor）。
- AC-011：`re_verified`。`rg`/diff 检查 blueprint 与 spec；`runtime_mode`/`viewer_mode` 已清除，ObservedState 与 schema 落点一致。残留 `docs/blueprint/domain.md:27` 的 `failed` 与 `docs/blueprint/artifacts.md:14` 的 0755/0644 回退描述由 code review `t016_code_f010` 跟踪（minor）。

coverage = 10 / 11（AC-008 为 `trust_prior`；其余为 reviewer 独立复验）

### 未进表的提示

- 本轮复跑：`tests/unit` 539 passed、`tests/integration` 79 passed、`src/backend/tests` 384 passed、`.repo_template/tests -m contract` 169 passed、`tests/e2e --collect-only` 79 tests。`pyflakes` 仅报 `tests/unit/test_auth_service.py:262` 的 `before_sessions` 赋值未使用，无 undefined name。
- `# type: ignore[arg-type]`（`tests/unit/test_launch_args.py:51`）仅抑制 `ProfileService(repo=None)` 的静态类型告警，不改变运行行为，且项目无 typecheck 门禁；按 Round 4 已说明的理由不按「静默错误」出 finding。
- `tests/unit/test_artifact_service.py:584-586` 与 `tests/unit/test_profile_copy_reset.py:536-540` 直接断言私有 `_locks._locks == {}`，属内部状态断言；不影响本轮 AC 证据，可作为后续测试风格清理。
- f009（路由/实现可达码动态枚举）、f010（特殊字符 URL 编码断言）、f012（后台重试与 labels 字符串化）仍为 non-blocking minor；p017 正文当前只列 code findings，建议补记这三项。
- `tests/unit/test_runtime_agent_faults.py:215` 的 `caplog.at_level(logging.ERROR)` 仍捕获不到实现写出的 WARNING，canary 断言空转（既有 minor）。
- `tests/unit/test_artifact_service.py:361` 与 `tests/unit/test_profile_copy_reset.py:546` 中名为 “by default” 的用例仍显式传 `runtime_uid=1000`；默认值已由 `test_launch_args.py` 守护（命名残留）。
- AC-008 真实 Docker E2E 本轮未重跑；`src/frontend/dist` 为 gitignored 构建产物，不属于审查范围。
- 当前 worktree 重算指纹 `568063954593bda2` 与注入值一致；`check_review_status.py` 的旧报告指纹仍显示 stale，本轮追加即修复该证据绑定。

### 结论

- 前轮 finding 复核：f001、f002、f003、f004、f005、f006、f007、f008、f011、f013、f014、f015 已消除或保持已消除；f009、f010、f012 仍为 minor。
- 改测方向复核：无。
- 本轮新发现：0 条。
- 未进表的提示：见上。
- 总体判断：当前测试无未解决的 critical / important；Round 5/6 的 PASS 结论在完整 worktree 指纹下仍成立，仅余 non-blocking minor 与 AC-008 的 `trust_prior` 环境限制。
- 系统性 follow-up：已有 p017 承接 t016 收尾 minor；建议把测试类 f009/f010/f012 补入 p017 正文，无需新建 tid。

verdict: PASS

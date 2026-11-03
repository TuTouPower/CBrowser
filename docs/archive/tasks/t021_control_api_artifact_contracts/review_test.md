# Task review t021（reviewer_focus: 测试）

- task：`t021_control_api_artifact_contracts`
- spec：`docs/tasks/t021_control_api_artifact_contracts/task.md`
- diff_anchor：`a644f7c3df22c65482cca22b2f10e3b507bc21c4`
- target：`git -C ~/workspace/CBrowser_t021 diff a644f7c3df22c65482cca22b2f10e3b507bc21c4`
- round：1
- reviewed_at：2026-11-04T02:20:19+08:00

reviewed_scope: d730af7080310f72

## Findings

### t021_test_f001 - AC-011 的提交竞争恢复分支（IntegrityError 回滚后重查）无证据被真正触发

- 严重度：minor
- 锚点：AC-011「提交竞争后的相同幂等请求得到一致结果」
- 位置：`tests/unit/test_repository_idempotency.py` 的 `test_concurrent_create_with_same_operation_returns_one_profile`、`test_concurrent_update_with_same_operation_applies_once`；实现 `repository.py` create/update 的 `except IntegrityError` 恢复段
- 证据：两条并发测试以 `asyncio.gather` 同 operation_id 竞争，断言结果一致（同 id / 同 version、最终只一行/一版），审查侧连跑 5 次全过、稳定。但没有任何覆盖率或故障注入证据证明两请求真的同时越过了前置审计检查、走进 IntegrityError 恢复分支；SQLite 单写者 + 会话 await 点完全可能使第二个请求在前置检查阶段就命中审计行、走顺序重放路径全绿。若恢复分支本身损坏（如重查签名构造错误），现有测试大概率仍绿。顺序重放、异签名冲突、删后重放（update→None、create→同 id 重建）与时间单一实现均有真实断言，故主体证据成立，仅「竞争恢复」这一子路径未被证伪性覆盖。
- 建议：补一条确定性竞争注入（如在首个事务提交前用事件/屏障卡住前置检查之后、插入之前的窗口，或直接对仓储 helper 注入一次 IntegrityError），断言恢复路径返回原结果；或用 coverage 证明恢复分支在并发用例中被执行。

### t021_test_f002 - AC-008 删除状态机只注入了文件阶段失败，DB 阶段失败与完成后重复删除语义未断言

- 严重度：minor
- 锚点：AC-008「文件或 DB 操作失败、进程重启后可按持久化意图继续且重复调用幂等」
- 位置：`tests/unit/test_artifact_service.py` 的 `test_delete_failure_keeps_intent_and_retry_completes`、`test_pending_deletion_resumes_in_fresh_service`、`test_delete_with_escaping_recorded_path_keeps_intent`
- 证据：已覆盖的一半很扎实——`store.delete` 首呼抛 OSError 的真实注入（断言意图/文件/元数据俱在、重试完成）、仓储直接登记意图 + 新鲜 service 实例 `resume_pending_deletions()` 续跑（断言完成数 1、再跑为 0）、逃逸路径拒绝且不触碰外部文件。但「文件已删、DB 删行失败」这一边界无注入用例：审查侧核实实现靠 `ArtifactStore.delete` 的 `unlink(missing_ok=True)` 使续跑可收敛，属构造安全但未经测试钉住；另外删除完成后再调用 `delete` 的语义（当前实现抛 `ArtifactNotFound`→API 404）与 service docstring 的「repeating the call is idempotent」措辞之间的口径无任何断言，AC 的「重复调用幂等」目前只由「失败后重试」与「resume 再跑为 0」两处支撑。
- 建议：补一条 monkeypatch `repository.delete_artifact` 首呼抛错的用例（断言意图保留、续跑后行与文件俱无）；并补完成后重复删除的语义断言（无论定版为 404 还是静默成功，与 docstring 对齐）。

### t021_test_f003 - AC-009 的逐消息入口校验对 runtime/supervisor 两协议只是抽样，尾换行无测试断言

- 严重度：minor
- 锚点：AC-009「每种实际 HTTP/WS 协议消息均能定位并通过自身导出 schema 入口校验；导出确定、包含一致文档元数据与尾换行」
- 位置：`tests/unit/test_runtime_agent_protocol_export.py::test_runtime_agent_schema_uses_entry_index_convention`、`tests/unit/test_supervisor_schema.py::test_supervisor_schema_uses_entry_index_convention`、`tests/unit/test_stream_protocol_schema.py`
- 证据：三协议的 messages 索引全集与 `{$id, $ref}` 形态、`$defs` 无注入 `$id`、顶层无 `anyOf`、文档 version 值均被逐项断言，生成一致性由既有「checked-in 文件 == 导出函数输出」相等测试守卫——「定位」一半完整。但「通过入口校验有效消息」一半只有 stream 是全量（5 种消息各有 valid 包 + 3 条 invalid）；runtime 只验了 ControlRequest 一条 valid/一条 invalid（共 7 种消息），supervisor 只验了 StartProfileRequest 与 ProfileRuntimeStatus 两条 valid（共 7 种消息）。其余消息的 `$defs` 内容由模型生成相等性间接守卫，风险低，但字面 AC 的逐消息有效包证据不齐。另：尾换行无任何测试断言（审查侧手动核实四份导出文件均以单个 `\n` 结尾、三个导出器与 export_openapi 均显式 `+ "\n"`，现状正确； dict 相等类测试对尾换行天然不敏感，未来导出器丢掉 `+ "\n"` 不会变红）。
- 建议：runtime/supervisor 各补齐每种消息至少一条 valid 包经入口 validator 通过（可参数化）；对四份导出文件补 `read_bytes().endswith(b"\n") and not endswith(b"\n\n")` 类断言。

### t021_test_f004 - AC-010 的运行事件日志「写入」与「打包后导入」无直接测试

- 严重度：minor
- 锚点：AC-010「运行事件日志在打包后的 cbrowser 包内可正常导入和写入」
- 位置：`src/backend/cbrowser/runtime_event_log.py`（`emit_runtime_event_log`）；`tests/unit/test_exit_reason_allowlist.py`（仅改导入路径）
- 证据：全仓 grep 显示没有任何测试直接调用或断言 `emit_runtime_event_log` 的输出（caplog 类断言为零）；包内导入仅由 `test_exit_reason_allowlist` 从新路径导入 `_sanitize_reason` 间接证明，且测试以源码布局 `PYTHONPATH=src/backend` 运行，不是安装后 wheel 布局——「打包后的包内可导入」严格说未在打包产物上验证。`profile_service` 的生产调用点经大量 integration 测试间接触发（导入失败会大面积变红），故导入回归风险已被兜住；缺的是 emit 本身的脱敏/写入行为断言与 wheel 级证据。
- 建议：补一条 caplog 断言 emit 输出含净化后的 id/reason 且不含原始敏感值；打包级导入可并入 p023 的真实环境清单（构建镜像/wheel 后 import 一次）。

### t021_test_f005 - 前端 useBrowserSession 的枚举清理改动无前端测试覆盖 SSE 状态分支

- 严重度：minor
- 锚点：AC-007 连带改动（A31 枚举定版后删除 `failed`/`ready` 死比较）
- 位置：`src/frontend/src/features/browser-session/useBrowserSession.ts`（diff 仅此 4 行前端逻辑）；前端测试目录无任何文件 import 该 hook
- 证据：改动本身是类型驱动的死代码删除——`observed_state` 定版为领域枚举后 `failed`/`ready` 不再可能到达，删除后行为对所有合法输入不变，tsc/build 门禁（实施侧记录 build 通过）守住类型一致性。但审查侧核实：没有任何前端测试直接覆盖该 hook 的 SSE observed_state 分支（error→error stage、running→就绪、其他→runtime_not_ready 的现行三条路径均无断言），此文件的回归防线实际只有类型检查。若未来有人误改现行分支（如把 `error` 漏掉），前端测试不会变红。
- 建议：给 useBrowserSession 补最小 hook 级测试，喂入 error/running/stopping/stopped 四种 observed_state 断言 stage 迁移；或在 BrowserSessionPage 测试中经 SSE 事件覆盖。

## 结论

- 政策变更替换复核（重点 2）：**完整且合法，无偷偷弱化**。A54 三处旧测试逐一核对 base 原文：unit `test_quota_and_mime_are_enforced` 拆为 `test_quota_is_enforced`（配额断言原样保留）+ 新增可执行上传接受/声明类型保留 + `validate_content_type` 统一规则（缺省/去参数/小写/五种非法头值拒绝）；unit `test_executable_download_is_registered_as_octet_stream` 整体替换为 `test_executable_download_keeps_its_declared_type`（含 None 时按文件名猜测类型保留的第二例）；integration `test_upload_rejects_bad_name_mime_and_oversize_without_partial_files` 改名 oversize-only 并注明政策——审查侧核对 base 原文，该用例名为 bad_name 但体内从无坏名断言（仅 MIME 400 + 超限 413 + 无残留文件），改名后无任何实际断言丢失，坏名/穿越另有既有用例守卫；新 integration round-trip 断言 stored 类型为 `application/x-sh`、取回 wire 类型 octet-stream + attachment + nosniff，与 AC-012「存储不重标、取回始终 attachment/nosniff」一致。A40 两处：unit auth 的「未知/非法令牌不产生审计行」（base 为 before==after 计数断言）已按新政策整体改写为聚合断言——两桶 (invalid_token count=1 / token_not_found count=2)、details 不含任何令牌原文，比旧断言更强；integration ingest 用例改为先经真实 bind API 绑定实例 i1 而非绕过信任检查，且新增 ghost 实例拒绝断言。另有 `test_automation_success_does_not_erase_failure_history` 以 3+7 次失败精确钉住「成功不清限速历史」（预算 10 边界可证伪）。
- 危险模式扫描：未命中系统性假绿。Argon2 探针经审查侧突变实测可证伪（见复跑节）；删除失败/glob OSError 均为真实 monkeypatch 注入且断言双向（失败 profile 保留 + 正常 profile 正常修剪同测并存）；Referer 用例带合法 CSRF token 走 logout，同源放行只能经来源校验分支成立，外站与三种畸形（含触发 urlsplit ValueError 的 IPv6 形式）均 403；A4 用 SQLAlchemy 事件监听捕获真实语句断言历史表名不出现且 tags 被加载，不是 mock 仓储；A6 新 integration 文件走真实 TestClient 全栈断言 503 错误码/retryable=false、错/无令牌 401、双令牌互斥与 Artifact 归 Supervisor 身份。弱断言点已分别记为 f001–f005（均为 minor）。
- 基线声明核对（重点 3）：**属实**。审查侧在 t021 worktree 复跑三条点名失败均失败；另建临时 worktree 于干净 base `a644f7c`（借用同一 run_tests.sh 与 toolvenv）同命令复跑，`test_repo_hygiene` home 路径、`test_runtime_persistence_guards` terminal_storage_failure、`test_runtime_coordinator_integration.py::test_ac009_api_supervisor_start_and_stop_coordination` 三条同 ID 同签名失败——零新增失败的声明成立。临时 worktree 已删除。
- 覆盖盲区与披露核对（重点 4）：note 与 p023 的披露与实际相符。真实进程重启续跑（lifespan `resume_pending_deletions` 在真实进程重启下）、真实 Chrome 容器下载全链、Gateway 真实 Origin 链路均为 trust_prior，p023 逐项点名（下载入库记录、重启后续跑删除结果、viewer 授权变体）且要求 evidence 回填，承载充分。本机层面的「重启」证据是新鲜实例重放（forwarder 新实例重读游标文件、ArtifactService 新实例 resume），属同进程新对象而非新进程，已在用例注释中如实建模、未冒充进程级证据。前端 useBrowserSession 无测试覆盖见 f005（note 未单独披露此点，但该改动为枚举定版的连带死代码删除，note 有记录其来由与「行为不变」判断，审查侧认同该判断）。
- reviewer 独立复跑结果：unit 定向 10 文件 **99 passed**（artifact_service/auth_service/repository_idempotency/profile_query_loading/download_reconciler/launch_args/三协议导出/exit_reason）；integration 定向 5 文件 **40 passed**（artifacts_api/auth_api/internal_service_config/profile_launch_args_api/gateway_fixtures）；并发幂等 2 条连跑 5 次全过；基线对照如上。实施侧全量数字（unit 603+2、integration 105+1、前端 97、模板 169）未独立全量复跑，采信其与基线对照口径（已抽查验证基线部分）。
- 突变抽查：Argon2 回退突变 1 项——把 auth/service.py 两处 verify 的 `asyncio.to_thread` 改回同步直调（审查侧在交付文件上操作、测后已还原并核对 diff 统计与原状一致），两条 Argon2 ticker 测试**均变红**（`test_argon2_verify_does_not_block_event_loop`、`test_argon2_dummy_verify_and_hash_do_not_block_event_loop`），证明阻塞探针（300ms `time.sleep` 慢哈希 + 10ms ticker、阈值 5 ticks）在实现回退时确实变红，非恒绿摆设；hash 卸载由同一测试的 init_admin_password ticker 段守卫。
- AC 复核记录：
  - AC-001（A2）：`re_verified`。复跑 integration launch_args 文件（PUT/PATCH 参数化越界 422 且存储不变、合法值、absent 保留/null 清空三态、历史行读时过滤）与 unit launch_args（DTO 严格校验 + null 的 fields_set 三态）全过；断言均为真实 HTTP 状态码与读回值。
  - AC-002（A4）：`re_verified`。复跑 test_profile_query_loading：SQL 语句捕获断言普通 get/list 不触 config_versions/artifacts 表、tags 被加载、DTO 内容不变；存在性标量与去重 storage_path 下推 SQL 均有语句级证据。
  - AC-003（A5）：`re_verified`。复跑两条 ticker 测试全过 + 回退突变双红（见突变抽查）。注记：错误密码路径未单独计 ticks，但与合法路径共用同一 to_thread 调用点，突变实测覆盖该调用点，可接受。
  - AC-004（A6）：`re_verified`。复跑 test_internal_service_config 全过：三面未配置 503/service_not_configured/retryable=false（含四条 Supervisor 写端点参数化）、无/错令牌 401 且错误码不同、双令牌独立。database_busy 保留由既有 integration 用例（test_v2_api_subprocess AC-004）在实施侧全量跑中守卫且 handler 未被本 diff 触碰，采信。
  - AC-005（A7）：`re_verified`。复跑 auth_api 中 Referer 三组用例（同源放行 200、外站 403、畸形 ×3 403）全过；用例设计能证明进入来源校验分支（带合法 CSRF、无 Origin、仅 Referer）。
  - AC-006（A12）：`re_verified`（本机层）。复跑 download_reconciler 新增三条全过：完整扫描后消失实例游标清除且新鲜 forwarder 重读一致、glob OSError 注入时失败 profile 游标保留而其他 profile 正常修剪、单例锁名单 `is` 同一对象断言。真实进程重启重放归 p023 trust_prior。
  - AC-007（A31）：`re_verified`。复跑 runtime_agent_protocol_export：双身份 scheme 集合、bind/gateway/ingest 三路由 security 精确断言、runtime/SSE DTO 枚举集合与非法值 ValidationError 均过；前端连带改动见 f005。
  - AC-008（A40）：`re_verified`（本机层，缺口见 f002）。复跑 artifact_service A40 三条 + auth 聚合审计与限速历史两条 + integration ingest 的 bind/ghost 两段全过；故障注入真实、迟到历史实例接纳走 runtime_events 历史行构造、伪造实例拒绝且源文件不动均有断言。真实进程重启归 p023 trust_prior。
  - AC-009（A41）：`re_verified`（缺口见 f003）。复跑三协议导出测试全过：索引形态/全集/version/无 anyOf 逐项断言、stream 五消息 valid + 三 invalid 经入口校验、生成一致性守卫在位；尾换行经审查侧手动核实四文件现状正确。
  - AC-010（A42）：`re_verified`（缺口见 f004）。复跑 exit_reason 改导入测试 + auth_api 中 automation-authorize 404 断言 + unit viewer Origin 变体归一化断言全过；automation-authorize 生产路由/DTO/网关 fixture 假面均已删除且有 404 钉住，真实 CDP 入口走 v1 路由未受影响。Gateway→API 真实链路归 p023 trust_prior。
  - AC-011（A46）：`re_verified`（缺口见 f001）。复跑 repository_idempotency 六条全过且并发两条连跑 5 次稳定；顺序/并发一致结果、异签名冲突、删后语义、utc_now_iso 来源同一性（逐模型列默认 provenance 断言）均为真实断言。
  - AC-012（A54）：`re_verified`。复跑 unit 可执行上传/下载保留类型 + validate_content_type 统一规则 + integration 可执行 round-trip（attachment/nosniff/wire octet-stream）全过；政策替换完整性见结论首段。
  - coverage = 12 / 12（全部 AC 至少达本机层 re_verified；其中 AC-006/008/010 的真实拓扑子集为 trust_prior 并由 p023 承载）
- 本轮新发现：5 条（minor 5；critical/important 0）。
- 总体判断：12 条 AC 打勾真实，证据链以真实 HTTP/SQL 捕获/故障注入/阻塞探针为主，政策变更替换完整无弱化，基线声明经干净 base 对照属实，trust_prior 披露与 p023 承载与实际相符；5 条 minor 均为覆盖深度问题（竞争恢复分支未证触发、DB 阶段故障未注入、逐消息抽样、emit 无直测、前端 hook 无测），不推翻任何 AC 的主体证据，给予 PASS。

verdict: PASS

## Round 2（delta 重签）

- round：2
- reviewed_at：2026-11-04T02:31:57+08:00
- reviewed_scope: 7b5dc5f73d104653（本 reviewer 在 worktree 内以任务给定命令独立实算，与实施侧声称值一致；复跑测试后再次实算仍为该值，工作区无测试残留污染）
- 范围：仅复核 Round 1 处置 delta（test 路 5 条 + code 路处置的测试侧 2 条），不重审 Round 1 已签主体。

### Delta 逐条复核

- t021_test_f001（竞争恢复注入）：**处置属实**。`test_create_commit_race_recovers_through_integrity_error` 先以同 operation_id 真实创建 winner，再把实例级 `_match_operation_audit` 首呼 rig 为返回 None——winner 的审计行已在库，前置检查被人为放行后，插入流程必然以已存在的审计主键在提交时产生真实 IntegrityError（非 mock 异常）。断言 `calls["count"] == 2` 可证伪地区分两条路径：顺序重放只需 1 次匹配即返回，恢复分支才有第 2 次（`repository.py` except IntegrityError 段的重查）；`recovered.id == winner.id` 且 `list_profiles()` 仅一行，若恢复分支损坏（重抛/重建新 id/双行）该用例必红。审查侧定向复跑通过。
- t021_test_f002（DB 阶段失败 + 完成后重复删除）：**处置属实**。`test_delete_db_stage_failure_keeps_intent_and_resume_completes` monkeypatch 的是仓储 `delete_artifact` 首呼抛 RuntimeError，注入点位于 `ArtifactService._complete_deletion` 的文件删除之后（store.delete 已真实执行），断言三段齐全：文件已不存在、意图与元数据行保留（`delete_requested_at is not None`）、恢复真实实现后 `resume_pending_deletions() == 1` 且 `get` 转 ArtifactNotFound——续跑收敛依赖 store 删除 missing-ok 的构造被真实钉住。`test_delete_after_completion_reports_not_found` 断言完成后再 delete 抛 ArtifactNotFound，与 service docstring 定版措辞（「意图未完成期间重试幂等、完成后 not found、API 映射 404」）、`docs/blueprint/artifacts.md` 与 `docs/specs/storage_and_artifacts.md` §删除条目的 404 口径逐字对齐（审查侧 grep 核对三处一致）。
- t021_test_f003（逐消息 valid 包 + 尾换行）：**处置属实**。supervisor 与 runtime 两测试文件各含 7 条 valid_packets，且均有 `assert set(valid_packets) == set(schema["messages"])` 的集合相等断言（消息增删会使两侧集合漂移而变红），每条经各自 messages 入口 validator 真实校验；连同既有 stream 全量校验，三协议逐消息证据补齐。`test_exported_schema_files_end_with_exactly_one_newline` 覆盖五份导出文件（supervisor/runtime/stream 三协议 + 双 OpenAPI），断言 `endswith(b"\n") and not endswith(b"\n\n")`，对导出器丢失尾换行或多加空行均可证伪。定向复跑通过。
- t021_test_f004（emit 直测 + 打包级并入 p023）：**处置属实**。`test_emit_runtime_event_log_writes_sanitized_json` 以 caplog 真实调用 `emit_runtime_event_log`，断言恰一条 `RUNTIME_EVENT_JSON:` 记录、JSON 解包后 event_id/runtime_instance_id 均以 `id_hash_` 开头、exit_reason 收敛为 `custom_reason`、exit_code 保真，且原始 event_id 与原始 instance 值不出现在日志行中——净化器若回退为原文透传，多条断言同时变红。p023 条目措辞核对：已明确含「在构建产物（镜像/wheel 布局）中 import `cbrowser.runtime_event_log` 并调用 `emit_runtime_event_log` 一次的打包级验证（本机测试以源码布局运行，打包布局未验，见 review t021_test_f004）」，打包级证据的去向与 Round 1 建议一致。
- t021_test_f005（useBrowserSession hook 测试）：**处置属实**。新增 `useBrowserSession.test.tsx` 用 renderHook + mock ApiClient 的 `getRuntime` 喂入全部五种 ObservedState（error/running/stopping/stopped/starting），以 waitFor 断言 stage 分别迁移至 error/connecting_signaling/stopping/runtime_not_ready/runtime_not_ready，与 hook 现行分支（stopping→stopping、error→error、非 running→runtime_not_ready、running→connecting_signaling）逐一对应；初始 stage 为 checking_runtime，断言的是真实迁移而非初始值。审查侧复跑：该文件隔离运行 5 passed；前端全量第二轮 102 passed（见复跑节注记）。
- code 路处置的测试侧（f002/f003）：**处置属实**。`test_unknown_token_audit_failure_keeps_clean_denial` 把 `_record_unknown_token_denied` 注入为恒抛 RuntimeError，经 `_audit_unknown_token_denied` 的尽力而为包装后，两种拒绝路径均断言干净结果——格式非法得 `(False, "invalid_token")`、未知令牌得 `(False, "token_not_found")`，存储错误不再污染授权语义。`test_resume_survives_pending_list_failure` 把 `list_pending_deletions` 注入为恒抛错，断言 `resume_pending_deletions() == 0` 且不抛异常，与实现入口的 try/except 记 warning 返回 0 对应；若容错被移除该用例必红。

### 附带观察（不作 finding）

- `test_unknown_token_audit_failure_keeps_clean_denial` 的 docstring 提到「失败仍计入限速器」，用例体未直接断言限速计数；该行为由调用方结构保证（包装吞错后两条路径均无条件执行 `record_failure`），且 code_f002 的最低回归要求（DB 故障时仍返回干净拒绝）已被双路径断言满足，故不立项。同理 `test_resume_survives_pending_list_failure` 未预置待续跑意图，其证明对象是「清单读取失败不中断、返回 0」本身，意图留存由「未触碰任何行」构造保证。

### reviewer 独立复跑结果

- unit 定向 7 文件（repository_idempotency / artifact_service / supervisor_schema / runtime_agent_protocol_export / stream_protocol_schema / exit_reason_allowlist / auth_service）：**74 passed**（审查侧以 `--collect-only` 复核总数同为 74，与实际运行结果一致）。
- 前端 Vitest：首轮全量 101 passed + 1 failed，失败为 `sse_hardening.test.ts` 的「无尾空行最终事件」用例——该文件不在本 diff 内，用例以真实本地服务器 + 固定 50ms 等待断言，满载下时序抖动；隔离复跑该文件 2 passed，随后第二轮全量 **102 passed**，与实施侧记录一致，判定为与 delta 无关的既存时序 flake，不影响 f005 结论（hook 文件隔离 5 passed、全量两轮均在通过集内）。
- 实施侧全量数字（unit 610 + 2 基线存量失败、build 通过）未独立全量复跑，采信口径与 Round 1 基线对照结论一致，本轮定向证据与之不矛盾。

### 结论

- 本轮新发现：0 条（formal finding 0；附带观察 2 处，均为 docstring 措辞宽于断言、行为由结构保证，不推翻处置）。
- Round 1 的 5 条 test minor 与 code 路 2 条处置的测试侧均经源码核对 + 定向复跑证实为真实、可证伪的覆盖补强，无恒绿摆设、无断言偷换；当前指纹 7b5dc5f73d104653 与实算一致。

verdict: PASS

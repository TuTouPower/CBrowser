# Task review t021（reviewer_focus: 代码）

- task：`t021_control_api_artifact_contracts`
- spec：`docs/tasks/t021_control_api_artifact_contracts/task.md`
- diff_anchor：`a644f7c3df22c65482cca22b2f10e3b507bc21c4`
- target：`git -C ~/workspace/CBrowser_t021 diff a644f7c3df22c65482cca22b2f10e3b507bc21c4`
- round：1
- reviewed_at：2026-11-04T02:19:53+08:00

reviewed_scope: d730af7080310f72

## Findings

本轮共 3 条 finding，全部为 minor；无 critical / important。

### t021_code_f001（minor）删除完成后的重复 DELETE 返回 404，HTTP 层不满足字面「重复调用幂等」

- 位置：`src/backend/cbrowser/services/artifact_service.py`（`ArtifactService.delete`）+ `src/backend/cbrowser/api/v1/artifact_router.py:133-146`（DELETE 路由）。
- 证据：`delete()` 先 `mark_delete_requested`，行不存在时其返回 `None`，服务随即抛 `ArtifactNotFound`，路由映射为 404。也就是说：失败中途的重试（意图已登记）与重启续跑（`resume_pending_deletions` 二次调用返回 0）确为幂等且有 unit 测试钉住（`test_delete_failure_keeps_intent_and_retry_completes`、`test_pending_deletion_resumes_in_fresh_service`），但删除已完成后再发一次 DELETE 得到 404 而非 204。AC-008 的「重复调用幂等」在状态机/重试层成立、在 HTTP 层只成立到「结果可预测」为止。此行为与 t021 之前一致（旧实现对已删 artifact 同样 404），非本 task 回归。
- 影响评估：调用方若按「DELETE 可无脑重发」编写会在成功后收到一次 404，需要自行把 404 当已删处理；不构成数据或安全风险。
- 建议：二选一并写回契约——DELETE 对「已完成删除」返回 204 使 HTTP 层真幂等，或在 spec/blueprint 中把 AC-008 的幂等口径明确为「意图登记后的重试与续跑幂等、完成后的重复调用返回 404」。

### t021_code_f002（minor）未知令牌审计聚合使每次猜测尝试都占全局写锁，DB 忙时拒绝路径会变成 503 而非干净拒绝

- 位置：`src/backend/cbrowser/auth/service.py`（`authorize_automation` → `_record_unknown_token_denied`）。
- 证据：格式非法/未知 token 的拒绝现在先开一个 `write_transaction`（`BEGIN IMMEDIATE`）做聚合行读改写，再 `record_failure`。本 reviewer 探针实测并发正确性成立：同一来源 6 个并发未知 token 调用全部返回 `(False, "invalid_token")`，写锁串行化使 get-then-insert 不产生主键冲突、计数聚合不丢。但代价是：猜测洪泛期每个新来源的首个 bogus token 都要排队拿全库写锁；若 `busy_timeout=5000` 内拿不到锁，`DatabaseLockError` 会从授权函数直接传播出去，调用方拿到的是可重试 503（database_busy）而不是确定的 `invalid_token` 拒绝——拒绝语义被存储层可用性污染。限速检查在审计写之前，单一来源越过阈值后不再写库，故影响限于多来源/低频猜测场景。
- 影响评估：可用性/语义整洁问题，非正确性或脱敏问题（聚合行只存 reason/source/count，不存 token/哈希，本 reviewer 已核源码与测试断言）。
- 建议：审计聚合写失败时降级为「记日志 + 仍返回原拒绝原因」，不让审计可用性改变授权结果；或把聚合计数改走有界内存缓冲 + 批量落库。至少补一条 DB 忙时 `authorize_automation` 仍返回 `invalid_token` 的回归。

### t021_code_f003（minor）启动续跑的意图清单读取在逐项容错之外，清单读取失败会中断启动

- 位置：`src/backend/cbrowser/api/app.py`（lifespan 中 `await app.state.artifact_service.resume_pending_deletions()`）+ `src/backend/cbrowser/services/artifact_service.py`（`resume_pending_deletions`）。
- 证据：`resume_pending_deletions` 对每个 artifact 的完成动作都做了逐项 try/except（失败保留意图、记 warning、继续其余项），但进入循环前的 `list_pending_deletions()` 一次性查询不在任何容错内，lifespan 调用点也没有包裹。若启动瞬间 DB 被锁或该查询瞬时失败，异常直接冒泡使应用启动失败——与该函数自身「失败保留意图、下次继续」的政策不一致：意图明明还在 DB 里、本可下次启动再续，却先把进程挡在门外。
- 影响评估：启动瞬间 DB 锁忙在本系统多为更深层故障的前兆（其他启动路径同样依赖 DB），实际触发概率低；定 minor。
- 建议：lifespan 调用点或 `resume_pending_deletions` 入口对清单读取失败做「记 error 日志并跳过本次续跑」处理，使续跑严格成为尽力而为的启动步骤（意图不丢、下次启动重试）。

## 审查覆盖记录

- AC-001（A2）：已核。`ProfileUpdateRequest` 删除 `normalize_launch_arguments` 过滤器、保留严格 `validate_launch_args`（null 透传、越界 422）；`ProfileCreateRequest` 同为严格校验；`ProfileConfig` 历史读取仍走 `filter_launch_args` 过滤，且新增 `coerce_null_lists`（before-validator）把显式 null 的 `launch_args`/`extension_paths` 归一为 `[]`，PATCH 三态（absent 不动 / null 清空 / 合法列表写入）语义闭合、不再 null→500。本 reviewer 复跑 `test_profile_launch_args_api.py` + `test_launch_args.py` 通过。
- AC-002（A4）：已核。四集合关系改 `lazy="noload"` + `passive_deletes=True`，普通读取经 `_load_profile_model`/`list_profiles` 显式 `selectinload(tags)`；本 reviewer 全仓 grep 确认无其他代码经关系属性消费 versions/artifacts/runtime（删除走 FK `ondelete="CASCADE"` + `PRAGMA foreign_keys=ON`，与 passive_deletes 配套成立）。`ArtifactRepository.profile_exists` 为标量 `select(id).limit(1)`；`find_download_duplicate` 把 `storage_path` 下推 SQL WHERE 并 `.first()`。`test_profile_query_loading.py` 复跑通过。
- AC-003（A5）：已核。登录真实/哑元 `verify` 与 bootstrap `hash` 全部 `asyncio.to_thread` 卸载；限速顺序（限速检查→哑元/真实校验→成功/失败记录）与脱敏不变。`test_auth_service.py`（含阻塞探针）复跑通过。
- AC-004（A6）：已核。新建 `cbrowser/service_errors.py:ServiceNotConfiguredError`，Supervisor/Gateway/Artifact 三面未配置统一经 app 级 handler 返回 503 `service_not_configured`/`retryable=false`，与 `DatabaseLockError` 的 `database_busy` 可重试响应分离；v1 artifact 入口的未配置也改走同一错误（diff 外溢一处、同语义）。`test_internal_service_config.py`（未配置/无令牌/错令牌/双令牌独立身份/三条状态写端点）复跑通过。
- AC-005（A7）：已核。`require_csrf_and_origin` 的 Referer 回退新增 `urlsplit` 的 `ValueError` 捕获，畸形 Referer 落入 403 而非 500；Referer-only 同源放行/外站拒绝/畸形拒绝用例在 `test_auth_api.py` 中且保留正确 CSRF token、确实进入来源校验分支，复跑通过。
- AC-006（A12）：已核。`forward_pending` 仅在扫描完整跑完（无 transport 错误/可重试状态早退）后调用 `_prune`；`_prune` 改为遍历已存游标：仍在场的实例做 `intersection_update`、消失实例整表删除、空 profile 清理；`glob` 抛 `OSError` 的 profile 进 `failed_profiles` 豁免修剪。`recovery_coordinator` 改引 `volume_spec.SINGLETON_LOCK_NAMES` 单一来源。`test_download_reconciler.py` 复跑通过。附带观察（不作 finding）：profile 目录在但 `events/downloads` 子目录缺失时该 profile 不在豁免集、游标会被修剪——子目录曾产出过游标必然曾经存在，其整体消失与「实例消失」同义，按契约处理可接受。
- AC-007（A31）：已核。本 reviewer 直接解析导出的 `schemas/openapi/cbrowser_internal.json`：`/internal/supervisor/**`（含 Artifact 下载入库面）标注 `SupervisorServiceBearer`、`/internal/gateway/**` 标注 `GatewayServiceBearer`、通用 `serviceBearer` 已删除；`ProfileRuntimeResponse`/`ProfileRuntimeStatusEvent`/`GatewayRuntimeResponse` 的状态字段改领域 `DesiredState`/`ObservedState` 枚举，前端生成类型已同步，`useBrowserSession` 删除枚举外 `failed`/`ready` 死比较属定版连带修复、行为不变。
- AC-008（A40）：已核（除 f001/f002 两条 minor）。迁移 `0008_artifact_delete_intent`（`down_revision=0007_font_bundle`、batch add/drop 对称可逆）；删除两阶段：意图落库→`store.delete`→删行，文件删除失败/逃逸路径（`ensure_inside_profile` 不再静默吞 `ArtifactInvalidName`）均保留意图，lifespan 启动续跑（见 f003）；`is_trusted_instance` = 当前绑定 ∪ `runtime_events` 历史，未知实例在触碰文件前以 `unknown_instance` 拒绝、内部路由映射为 `rejected` 而非 `ignored`；审计聚合见 AC 覆盖 f002 条，成功授权已删除 `record_success` 调用、失败记录只按时间窗衰减（`test_auth_service.py:444` 起的回归钉住）。
- AC-009（A41）：已核。三导出脚本同形：`$defs` 保持 union 原样、`messages` 按消息名给 `{"$id": "#/$defs/<Name>", "$ref": "#/$defs/<Name>"}` 入口、顶层 `anyOf` 删除；version 各自独立（supervisor `1.0.0` / runtime agent `2.0.0` / stream `v2` 且与线上 envelope 字面量一致，文档明示不冒充协商版本）；本 reviewer 实测四份导出文件均以尾换行结尾、messages 清单与各自协议模型集逐一对应；`export_openapi.py` 同补尾换行。按消息入口校验的测试（stream/supervisor/runtime 三套）复跑通过。
- AC-010（A42）：已核。`emit_runtime_event_log` 及净化器原样移入包内 `cbrowser/runtime_event_log.py`（与旧 `diagnostics.py` 对应段逐字比对一致），`profile_service` 改包内导入；旧 `diagnostics.py` 其余函数全仓 grep 无引用方后整文件删除、无兼容转发层。`automation-authorize` 路由/DTO 已从 `internal_gateway` 与内部 OpenAPI 删除（本 reviewer 在导出 OpenAPI 路径清单中确认无此路径），`authorize_automation` 本体保留供真实 CDP 入口（v1 automation）使用。Origin 双边归一：本 reviewer 探针实测 `authorize_viewer` 对尾斜杠/默认端口变体放行至下一校验、对非法配置项 fail-closed 返回 `invalid_origin` 不抛异常。`gateway/api_client` 冗余 `.strip()` 已删（`read_secret_file` 本就 strip，源码核实）。
- AC-011（A46）：已核。三处幂等审计解释收敛为仓储 `_match_operation_audit` 单一 helper（create/update/desired-state 共用，签名不符一律 `IdempotencyConflictError`）；create 竞争恢复走同一 helper，目标已删的 create 重放按审计 `entity_id` 确定性重建、update 重放返回 `None`（与 fresh update 的未找到语义一致）；`utc_now_iso` 收敛到 `domain/models.py` 单一实现，DB 列默认与 auth 服务改引同一函数、无别名残留。`test_repository_idempotency.py` 复跑通过。
- AC-012（A54）：已核。`DANGEROUS_CONTENT_TYPES` 删除；上传与下载入库共用 `validate_content_type` 单一规范化（去参数/小写/缺省 `application/octet-stream`/正则校验 token 对），下载侧原「非法类型静默重标 octet-stream」分支删除、改为抛错经内部路由判 `rejected`，声明类型（含可执行）保留为元数据；用户取回路由的 `attachment` + `nosniff` 为存量行为未放宽（本 reviewer 核 `artifact_router` 下载响应头未被本 diff 触碰而弱化）。旧政策测试按裁决整体删除换新政策测试，非就地改预期。
- 范围纪律：diff 共 61 文件，全部落在 task.md 范围（控制 API/鉴权/仓储/Artifact/协议导出/生成物/blueprint/specs/finalization 与 p023 立项）；无 repo_template 改动、无 legacy 恢复、无顺手功能。唯一契约外沿是 v1 artifact 入口未配置错误并入 `ServiceNotConfiguredError`（与 AC-004 同语义收敛）与前端死比较清理（AC-007 定版连带），均属本组契约的直接后果，不作 finding。
- 测试复跑（本 reviewer 独立执行）：unit 定向 10 文件 99 passed（artifact/auth/查询加载/幂等/下载对账/launch_args/三协议导出/exit allowlist）；integration 定向 5 文件 40 passed（内部服务配置矩阵、launch_args HTTP、auth、artifacts、gateway fixtures）。另以临时探针实测了聚合审计并发（6 并发全数正确拒绝）与 Origin 归一变体（尾斜杠/默认端口放行、非法项 fail-closed），探针文件已删除、工作区无残留。全量 unit/integration 未复跑（实施侧记录 603+105 通过、3 条基线存量失败同 ID），本轮定向复跑与之不矛盾。

## 结论

- 本轮新发现：3 条，全部 minor（critical 0 / important 0 / minor 3）。
- 总体判断：12 条 AC 的契约语义逐条在源码层成立且有真实调用路径测试钉住——PATCH 三态与 null 归一、noload 加载边界与 DB 级联、Argon2 线程卸载、503 错误码区分、Referer 畸形防护、游标修剪条件、OpenAPI 按路径身份与枚举、删除两阶段状态机与实例信任、审计聚合脱敏与有界性、协议导出三脚本同形、事件日志入包与旧面删除完整性、Origin 双边归一、内容类型双入口统一，均经本 reviewer 源码核对 + 定向复跑 + 两组探针证实。3 条 minor 分别是 HTTP 层删除幂等的口径差、审计写的可用性耦合、启动续跑入口容错缺口，不改变任何 AC 的行为结论，建议在本 task 内小修或在 note.md 登记去向。

verdict: PASS

## Round 2 — delta re-attestation（三条 minor 处置复核，非全新业务审阅）

- round：2（delta re-attestation）
- reviewed_at：2026-11-04T02:28:56+08:00
- 性质：Round 1 本路结论为 PASS、零 critical / important、3 条 minor（t021_code_f001–f003），实施方逐项处置导致交付内容变更、Round 1 指纹 `d730af7080310f72` 过期。本轮只独立核实「三项处置属实、delta 清单完整、test 路 delta 未触碰生产语义、当前指纹正确」，不重做业务审阅。

### 核实结果

1. **f001 写回契约（属实）**。`ArtifactService.delete` docstring 已改明「意图未完成期间重复调用幂等、完成后报 NotFound（API 404）为既定终态信号」；`docs/blueprint/artifacts.md:41` 与 `docs/specs/storage_and_artifacts.md:48` 同步同一口径（意图期幂等 / 完成后 404）；新增 `test_delete_after_completion_reports_not_found`（`tests/unit/test_artifact_service.py:873`），本轮复跑通过。生产行为未变，只是把既有语义写回契约——正是 Round 1 建议的二选一中的写回方案。
2. **f002 审计写降级（属实）**。`auth/service.py` 新增 `_audit_unknown_token_denied` 包装：聚合审计写抛错时记 warning 吞掉，两个未知令牌调用点（`invalid_token` / `token_not_found`）均改走包装，且其后的 `record_failure` 限速计数不被跳过；新增 `test_unknown_token_audit_failure_keeps_clean_denial`（`tests/unit/test_auth_service.py:482`，monkeypatch 聚合写抛错断言仍返回干净拒绝），本轮复跑通过。授权结果不再被审计可用性污染，Round 1 的污染路径已消除。
3. **f003 启动续跑容错（属实）**。`resume_pending_deletions` 把 `list_pending_deletions()` 纳入 try：失败记 warning（含 exc_info）并返回 0，docstring 同步「清单读取亦为尽力而为、意图保留待下次启动」；新增 `test_resume_survives_pending_list_failure`（`tests/unit/test_artifact_service.py:892`），本轮复跑通过。
4. **test 路 delta 未触碰生产语义（属实）**。按文件 mtime（UTC 18:22–18:24，即 +08:00 02:22–02:24，晚于 Round 1 的 02:19）核对，Round 1 后变更的交付文件恰为 12 个：生产代码只有 f002/f003 对应的 `auth/service.py`、`services/artifact_service.py` 两文件；其余为 `docs/blueprint/artifacts.md`、`docs/specs/storage_and_artifacts.md`（f001 口径）、`docs/pending/todo/p023_*.md`（措辞）与 7 个测试文件（`test_artifact_service.py`、`test_auth_service.py`、`test_repository_idempotency.py`、`test_supervisor_schema.py`、`test_runtime_agent_protocol_export.py`、`test_exit_reason_allowlist.py`、`useBrowserSession.test.tsx` 新增）。清单外零变更；同批新增的 `test_delete_db_stage_failure_keeps_intent_and_resume_completes` 本轮复跑通过，补上了删除 DB 阶段失败的故障注入覆盖。
5. **当前指纹独立重算一致**。以 `repo_task.monitoring.review_scope_fingerprint("a644f7c3df22c65482cca22b2f10e3b507bc21c4", "docs/tasks/t021_control_api_artifact_contracts")` 在当前工作区独立实算，结果为 `7b5dc5f73d104653`，与预期逐字一致。本文件属指纹排除的过程文件，本次追加不改变该指纹（追加后已复算确认）。

### 结论

- 本轮新发现：0 条。code 路 3 条 minor（f001–f003）处置逐项回查源码 / 文档 / 测试均属实，test 路 delta 仅测试与措辞、未触碰生产语义；Round 1 的 PASS 结论在处置后的交付内容上重签成立。
- 测试复跑（本 reviewer 独立执行）：`test_artifact_service.py`、`test_auth_service.py`、`test_repository_idempotency.py`、`test_supervisor_schema.py`、`test_runtime_agent_protocol_export.py`、`test_exit_reason_allowlist.py` 共 **71 passed**，含本轮 4 条新增用例。实施侧全量口径（unit 610 passed + 2 基线存量失败、前端 102 passed + build）与本轮定向复跑不矛盾。
- AC 复验方式沿用 Round 1 记录不变；真实环境执行债务仍由 p023 追踪。

reviewed_scope: 7b5dc5f73d104653

verdict: PASS

# Task review t016（reviewer_focus: 代码）

- task：`t016_v2_backend_hardening`
- spec：`docs/tasks/t016_v2_backend_hardening/task.md`
- diff_anchor：`fb6185c46f41500a9089e526a1773774a7cd6c67`
- target：`git -C '<repo>_t016' diff fb6185c46f41500a9089e526a1773774a7cd6c67`
- round：1
- reviewed_at：2026-11-03T03:22:45+08:00

reviewed_scope: eeed07bc84c7977e

## Findings

### t016_code_f001 - launch_args 白名单校验放在领域模型，旧库 Profile 的读取与更新全部 500

- 严重度：critical
- 锚点：AC-009（“Profile 启动参数按白名单在 API 层校验”）；AC-007（“数据库迁移可从现有 schema 升级”）——实现把校验放进被 DB 行反序列化共用的 `ProfileConfig`，导致升级后既有数据不可读。
- 位置：`src/backend/cbrowser/domain/models.py:89-92`（`ProfileConfig` 的 `launch_args` 校验器）；`src/backend/cbrowser/adapters/database/repository.py:783-800`（`_to_domain_profile` 用 DB 行构造 `ProfileConfig`）、`:322`（`update_profile` 同样用行数据构造）、`src/backend/cbrowser/supervisor/control_server.py:105`（`ProfileConfig(**cfg_data)` 读快照）。
- 问题：旧版 API 允许任意 `launch_args`（旧安全层只在 runner 里静默过滤，不限制入库）。升级后只要任一既有 Profile 的某个参数不在新白名单内（如 `--force-color-profile=srgb`、`--user-agent=...`、`--disable-features=...`），任何读取该 Profile 的路径都会抛 `pydantic.ValidationError`：`GET /api/v1/profiles`、`GET /api/v1/profiles/{id}` 返回 500，`PATCH` 也 500；Supervisor 启动该 Profile 时构造 `ProfileConfig` 失败，返回 502。整个 Profile 列表会被单个旧 Profile 拖垮。已复现：迁移建库后插入 `launch_args='["--flag-one"]'` 的行，`repo.list_profiles()` 抛 `ValidationError`。现有单测把旧测试参数改成白名单值（`tests/unit/test_domain_and_repository.py:99`），掩盖了这条路径。
- 建议：把白名单校验放到 API 请求 DTO（`ProfileCreateRequest` / `ProfileUpdateRequest`）并保持 runner 第二道校验；领域/仓储读取旧行时不得因参数旧值失败（告警后保留或按明确策略丢弃），并补“旧行 + 旧参数”的读取/更新回归测试。

### t016_code_f002 - CDP 断线重连在监听任务内等待自己消费 ACK，下载捕获永不恢复

- 严重度：critical
- 锚点：AC-002（“连接断开后自动重连并恢复下载捕获”）。
- 位置：`src/backend/cbrowser/runtime_agent/cdp_proxy.py:186-202`（重连后 `await self.rearm_download_capture()` 仍在 `_listen_events` 协程内）；`:106-124`（rearm 等待 `send_command` 的 future）；`:140-147`（唯一读取 CDP 帧的循环）；`:56-64`（`capture_alive` 只看 socket/task 存活）。
- 问题：连接断开后监听协程重连，再 `await rearm_download_capture()`；该调用发送 `Browser.setDownloadBehavior` 并等待响应，但响应只有同一个 `_listen_events` 协程能读。协程被自己阻塞，5 秒超时后 `TimeoutError`，rearm 永远不会应用；日志出现 `CDP reconnect failed (TimeoutError)`。之后 socket 仍开着、监听任务继续运行，健康探活仍报 `cdp_ready=True`（`capture_alive` 不反映 rearm 状态），下载事件从此不再捕获。已用本地 websockets 服务端复现：重连后 `rearm_count == 0`，日志为 `CDP reconnect failed (TimeoutError); retrying in 2.0s`。
- 建议：重连/rearm 放到独立任务，或在新 socket 上内联发送并读取匹配的响应后再回到事件循环；让 `capture_alive` 依赖最近一次成功的 rearm，并补“断线后下载事件仍落盘”的测试。

### t016_code_f003 - POST /profiles 非法 launch_args 返回 500 而非 AC 要求的 422

- 严重度：important
- 锚点：AC-009（“非法参数返回 422”）。
- 位置：`src/backend/cbrowser/domain/models.py:249-282`（`ProfileCreateRequest` 没有 `launch_args` 校验器）；`src/backend/cbrowser/api/v1/router.py:171-227`（路由内构造 `ProfileConfig`）；`src/backend/cbrowser/api/app.py:327-337`（兜底 500）。
- 问题：`POST /api/v1/profiles` 携带 `{"launch_args":["--load-extension=/tmp/evil"]}` 时，`ProfileCreateRequest` 校验通过，随后路由构造 `ProfileConfig` 抛 `pydantic.ValidationError`，被通用异常处理器映射为 500 `internal_server_error`；同一 payload 走 `PATCH` 才是 422（因为 `ProfileUpdateRequest` 有校验器）。已用 `TestClient` 复现：创建非法参数 500，合法参数 201。
- 建议：在 `ProfileCreateRequest` 上加同一校验器（或在路由捕获 `ValidationError` 映射 422）；补 HTTP 级用例，断言 422 且数据库无新 Profile。

### t016_code_f004 - 自动化令牌授权没有按来源限流

- 严重度：important
- 锚点：AC-005（“伪造的自动化令牌不产生数据库写入且被限流”）。
- 位置：`src/backend/cbrowser/auth/service.py:317-369`（`authorize_automation` 无任何 limiter）；`src/backend/cbrowser/api/v1/automation_router.py:76-89`（WS 握手直接调用）；`src/backend/cbrowser/api/internal_gateway.py:120-125`（内部 RPC 直接调用）；唯一限流器只用于管理员登录（`src/backend/cbrowser/auth/service.py:101`、`src/backend/cbrowser/api/v1/auth_router.py:75-80`）。
- 问题：invalid-format 与 not-found 已经改成一概不落库，但没有任何节流；revoked / expired / profile_unauthorized / profile_not_found 每次尝试仍会写一条审计行。攻击者可无限次触发自动化 WS 握手与内部授权 RPC（每次至少一次 SELECT，部分分支 INSERT），AC 要求的“被限流”未实现；`tests/unit/test_gateway_signaling.py` 的限流用例只覆盖 viewer 信令。
- 建议：在自动化授权入口按来源（及 Profile/token）加滑动窗口，超限返回 429 或关闭连接（如 4408）；补断言“伪造 token 不新增 audit_events，连续失败达到阈值后被拒绝”。

### t016_code_f005 - OpenAPI 契约缺少实现可达状态码，守卫测试未断言可达性

- 严重度：important
- 锚点：AC-006（“声明实现实际可达的错误码；守卫测试保证实现可达响应码包含于契约”）。
- 位置：`src/backend/cbrowser/api/internal_supervisor.py:97-99`（`add_api_route` 丢弃原路由的 `responses` 元数据）；`src/backend/cbrowser/api/v1/router.py:700-710,731-739`（bind/observed 会抛 404/409）；`src/backend/cbrowser/api/v1/auth_router.py:73-85`（登录会返回 429）；`src/backend/cbrowser/api/app.py:382-411`（通用补码只加 401/403/503/422/404）；`tests/unit/test_runtime_agent_protocol_export.py:27-38`（守卫只断言固定子集）。
- 问题：`schemas/openapi/cbrowser_internal.json` 中 `/runtimes/bind`、`/runtimes/observed` 的响应只有 200/401/403/422/503，但实现可返回 404（Profile 不存在）与 409（实例冲突）；公开契约中 `POST /api/v1/auth/login` 可返回 429（限流），但没有 429 声明。守卫测试没有枚举可达码，只硬编码检查少量码，AC-006 的守卫要求未满足。
- 建议：`add_api_route` 透传原路由的 `responses`（或直接注册原 `APIRoute`）；登录补 429；把守卫改成“实现可达状态码集合 ⊆ 契约声明”的通用检查。

### t016_code_f006 - 运行时数据归属默认取 API 进程 uid，root 运行时不满足 uid 1000

- 严重度：important
- 锚点：AC-008（“运行时数据统一归属运行用户（uid 1000）……Browser 与 Stream 双容器在此权限下正常工作”）。
- 位置：`src/backend/cbrowser/services/profile_service.py:204`、`src/backend/cbrowser/adapters/filesystem/artifact_store.py:134`（默认 `os.getuid()`）；`src/backend/cbrowser/api/app.py:116,119-122`（生产构造点未传 uid/gid、未读环境变量）；部署侧 API 以 root 运行（`tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile` 无 `USER`，`tests/fixtures/frontend_probe/harness.py:71-82` 与 `tests/fixtures/gateway_probe/topology.py:203-231` 启动 API 容器时未传 `user=`）。
- 问题：进程 uid 为 0 时，上传的 Artifact 与 Profile 状态复制结果会被 chown 为 `0:0`，权限 0640/0750（Artifact）或 0600/0700（复制态）；Browser/Stream 以 uid 1000 运行，读不到这些文件——上传文件在 `/exchange/uploads` 不可用，带浏览器状态的复制 Profile 启动后无法读取自己的 user_data。单测通过显式注入 `runtime_uid=os.getuid()` 或 `1000` 绕过了这条路径。AC-008 声称已由真实双容器 E2E 验证，但该 E2E 的 API 进程是 root，且没有覆盖“API 写 Artifact/复制态 → 1000 容器读取”。
- 建议：默认 1000（与 Supervisor 的 `CBROWSER_RUNTIME_UID` 对齐）或显式从环境变量/构造参数注入并让部署以 1000 运行 API；补一个“以非 1000 uid 启动 app，断言写入目标 uid 为 1000 且容器可读”的回归测试。

### t016_code_f007 - recovery_coordinator 的内部 URL 仍未转义 profile_id

- 严重度：important
- 锚点：AC-010（“内部 URL 中的标识符正确转义”）。
- 位置：`src/backend/cbrowser/supervisor/recovery_coordinator.py:179,277,409,458,619`；对照已修复的 `src/backend/cbrowser/supervisor/core.py:225,850,882,1176,1272` 与 `src/backend/cbrowser/supervisor/control_server.py:97,177`。
- 问题：这些 profile_id 来自 Docker 容器标签（`scan_active_containers` 只按前缀过滤，不校验 profile-id），却直接拼进带 Supervisor Bearer 的内部 URL。标签值含 `/`、`?`、`#`、`..` 时会把请求导向不同路径（路径穿越/参数注入），与 AC 的全量转义要求不符；同一 task 内其它调用点已统一 `quote(..., safe="")`，这里是遗漏。
- 建议：全部改为 `quote(profile_id, safe="")`，并补一个含特殊字符 profile_id 的 MockTransport 断言测试。

### t016_code_f008 - 下载事件磁盘信封没有 version，且 agent 索引与 supervisor 读取器对 version 的兼容策略相反

- 严重度：important
- 锚点：AC-003（“磁盘事件信封带版本并按版本兼容或隔离”）。
- 位置：`src/backend/cbrowser/runtime_agent/event_storage.py:247-250`（`save_download_event` 直接写 `event.model_dump()`，无 version）；`src/backend/cbrowser/supervisor/artifact_forwarder.py:115-130`（读取侧缺省当 1 并剥离 version）；`src/backend/cbrowser/runtime_agent/event_storage.py:205-232`（`_rebuild_download_index` 用 `DownloadEventRecord.model_validate` 校验原始文件）。
- 问题：唯一下载事件生产者从不写 `version`，所以“信封带版本”只体现在读取端的缺省容错；更糟的是 `DownloadEventRecord` 配置了 `extra="forbid"`（`src/backend/cbrowser/runtime_agent/protocol.py:73`），一旦按 AC 给文件加 `version`，agent 自己的索引重建就会失败：已复现 `DownloadEventRecord.model_validate({"version":1,...})` → `ValidationError`；只要索引需要重建（文件集变化或索引缺失），`save_download_event`/`get_download_events` 就会抛 `StorageError`。两个读取器对同一信封的兼容语义不一致。
- 建议：写入侧统一加 `version`（下载与运行事件同理）；两个读取器共用同一“剥信封/校验/隔离”函数；补“带 version 的写入 → 索引重建 → 转发”往返测试。

### t016_code_f009 - AC-007 的仓储测试与模型/迁移一致性守护未实现，且现有 schema 漂移会让守护失败

- 严重度：important
- 锚点：AC-007（“仓储测试在真实迁移建出的 schema 上运行，且模型与迁移的一致性受测试守护”）；来源 A23（HIGH）。
- 位置：`tests/unit/test_domain_and_repository.py:36-43`（`db_context` 仍用 `Base.metadata.create_all`）；`src/backend/cbrowser/adapters/database/models.py:188`（只声明 `idx_artifacts_profile_id`）；`src/backend/migrations/versions/0003_artifact_storage.py:27`（额外创建 `idx_artifacts_profile_sha256`）；没有任何 `compare_metadata`/迁移建表比较测试。
- 问题：仓储测试验证的是 ORM metadata，不是 Alembic 迁移，无法发现模型与迁移分叉；实际已存在分叉（迁移多出 `idx_artifacts_profile_sha256`，模型未声明），若按 AC 增加 `compare_metadata == []` 守护会立即失败。AC 已打勾但两个子项都未落地；本次还缺少“从 0003 既有库（含两列与数据）升级到 head”的迁移测试。
- 建议：`db_context` 改为先 `run_database_migrations`；补 0003→head 带数据升级用例与 `compare_metadata` 守卫；同步修正索引漂移或记录为有意差异。

### t016_code_f010 - AC-011 的文档对齐仍有残留

- 严重度：minor
- 锚点：AC-011（“后端相关 blueprint 与 spec 与代码和已落地决策一致……t001 spec 时点标注”）。
- 位置：`docs/blueprint/persistence.md:24`（profiles 字段列表仍含 `runtime_mode`/`viewer_mode`）；`docs/specs/runtime_persistence.md:19`（仍称创建 Profile 会把两字段统一为 docker/webrtc）；`docs/specs/v2_runtime_validation.md:135`（仍用现在时说“服务代码、Alembic 迁移与前端组件均未合入生产代码库”，没有 A14 要求的“截至 t001 验收时点”标注）；`docs/blueprint/domain.md:27`（状态图仍用 `failed`，枚举已是 `error`）。
- 问题：代码、迁移和契约已删除两字段，这些文档仍把它们描述为当前行为；t001 spec 的时点标注完全缺失。`docs/specs_index.md` 还把 `runtime_persistence` 的时间戳更新为 2026-11-03，但该文件内容未变。属“文档与实现不一致”，处置为改文档。
- 建议：修正上述四处并复核 AC-011 的 grep 结果；时点标注加到 t001 spec 的非生产声明处。

### t016_code_f011 - docker_adapter 仍存在 0644 写 runtime snapshot 的分支

- 严重度：minor
- 锚点：AC-008（“配置快照……仅属主可读写”）。
- 位置：`src/backend/cbrowser/supervisor/docker_adapter.py:637-640`。
- 问题：该分支在 `snapshot_json_path != target_snap` 时用 `atomic_write_text(..., mode=0o644)` 重写 `snapshot.json`，且不做 runtime uid chown；snapshot 含完整 ProfileConfig（可能带代理凭证）。当前唯一生产调用 `core.start_profile` 传入的就是 `dirs["runtime"]/snapshot.json`，所以分支实际不可达，但它是 A31 “snapshot 0644”问题的残留，一旦未来新增调用点就会复现凭证暴露。
- 建议：删除该分支，或统一改为 0600 + chown runtime uid。

## 结论

- 前轮 finding 复核：Round 1，无前轮 finding。
- 本轮新发现：11 条（blocking：f001–f009；minor：f010–f011）。
- 未进表的提示：
    - 文件过大（实现源码阈值 400/800，均本 task 净增）：`src/backend/cbrowser/supervisor/core.py` 1288 行（+39）、`src/backend/cbrowser/supervisor/docker_adapter.py` 1058 行（+24）、`src/backend/cbrowser/runtime_agent/runner.py` 858 行（+78）、`src/backend/cbrowser/services/profile_service.py` 636 行（+56）、`src/backend/cbrowser/domain/models.py` 516 行（+6）、`src/backend/cbrowser/api/app.py` 419 行（+78）；测试源码阈值 600/1200 命中 `tests/integration/test_v2_api_subprocess.py` 918 行（+6）。生成物 `schemas/openapi/*.json`、`src/frontend/src/shared/api/generated/*.d.ts` 已排除。
    - 圈复杂度：`SupervisorCore._reconcile_profile`、`DownloadArtifactForwarder.forward_pending`、`CdpProxyManager._listen_events` 估计 ≥10，前两者接近/达到 15；本次主要是搬移与分支隔离，未单独出 finding，建议后续拆分。
    - `/events/downloads` 未分页：`src/backend/cbrowser/runtime_agent/agent.py:293-295` 仍无 `limit/offset` 参数，虽然 `EventStorage.get_download_events` 已支持（A32 的“分页”只完成一半）；当前有 100 条/实例上限，无阻断性影响。
    - `src/frontend/tsconfig.tsbuildinfo`（构建缓存）被修改；不属于“重新生成前端 API 类型”，建议提交前还原（测试 reviewer 也记录了该仓库卫生问题）。
    - AC-005 的 SSE 时序测试、AC-001 的全路由枚举测试、AC-002 的非法帧/重连测试仍偏弱，归测试 reviewer 复核范围；本轮不重复出 finding。
    - `note.md` 自述 unit 530 passed；本地复跑 `tests/unit` 529 passed（`tests/integration` 79 passed，`src/backend/tests` 未在本轮复跑）。
    - 审查范围指纹：prompt 注入 `eeed07bc84c7977e`，按 `check_review_status.py` 的同源函数在当前 worktree 复算为 `30228cb0c5a1a149`。本报告按 prompt 要求保留注入值，但该差异说明 prompt 渲染后工作区仍有变化，实施方需重新渲染 prompt 后重派，否则 PASS 指纹无效。
- 总体判断：核心加固方向正确（路由收敛、per-profile 隔离、权限收紧、契约导出均有实现并通过现有测试），但存在两项可复现的 critical（旧库 launch_args 读取 500、CDP 重连后下载捕获失效）及多项 important 缺口，当前不可信。
- 系统性 follow-up：无（本轮均在 t016 范围；`idx_artifacts_profile_sha256` 的模型/迁移漂移建议随 f009 在本 task 内修复）。

### AC 复验方式

- AC-001：re_verified——枚举公开/内部 OpenAPI 路径，确认 bind/observed/events 只挂在 `supervisor_router`；现有 `test_supervisor_reporting_routes_are_service_plane_only` 通过。
- AC-002：re_verified——逐行检查 health 探活的 `to_thread` 与监听器逐帧隔离；用本地 websockets 服务复现重连后 rearm 自锁（见 f002）。
- AC-003：re_verified——复核 `translate_download_path` 越界拒绝、dead-letter、长文件名截断与测试；发现信封版本只做了一半（f008）。
- AC-004：re_verified——复核 `_reconcile_profile` 的 per-profile try/except、`serve_supervisor` 初次失败继续启动与 30s 后台重扫；相关单测通过。
- AC-005：re_verified——复核 token 过期、过期 session 清理、docs 默认关闭、503 映射与 Retry-After 修剪；发现自动化授权无限流（f004）。
- AC-006：re_verified——实际比较 live OpenAPI 与两份 schema（public 漂移与 internal 漂移测试均过；前端生成类型用 `openapi-typescript` 重生成到临时文件后 diff MATCH）；发现可达码缺项（f005）。
- AC-007：re_verified——grep 确认 v2 代码/schemas/生成类型无 runtime_mode/viewer_mode，0004/0005 迁移可在临时库升级；发现仓储测试未改用迁移、且已有模型/迁移漂移（f009）。
- AC-008：trust_prior——真实 Browser/Stream 双容器媒体、输入、剪贴板 E2E 未在本轮复跑，依赖实施侧记录；代码层静态复核发现 uid 默认值缺口（f006）与 0644 snapshot 残留（f011）。
- AC-009：re_verified——白名单单测通过；实测非法 `POST /api/v1/profiles` 返回 500（f003），旧库参数导致读取 500（f001）。
- AC-010：re_verified——grep 内部 URL、复核 CDP WS accept 前鉴权、journal 隔离、累计/区间指标与并发配额测试；发现 recovery_coordinator 未转义（f007）。
- AC-011：re_verified——grep 文档残留并核对 A14 列表（f010）。

coverage = 10 / 11

verdict: FAIL

## Round 2 (2026-11-03T03:56:00+08:00)

reviewed_scope: c36146bcdf06fa14

## Findings

### t016_code_f012 - 升级后旧 config version 快照无法被 ProfileConfig 解析，既有 Profile 无法启动且 API 仍回传已删字段

- 严重度：critical
- 锚点：AC-007（“数据模型、API 响应、配置快照与契约中不再包含 runtime_mode/viewer_mode；数据库迁移可从现有 schema 升级”）；失败场景：升级前创建的 Profile 在升级后点击启动，Supervisor 返回 502，Profile 永远无法启动。
- 位置：`src/backend/migrations/versions/0004_remove_runtime_viewer_mode.py:20-23`；`src/backend/cbrowser/domain/models.py:54-55`（`extra="forbid"`）；`src/backend/cbrowser/adapters/database/repository.py:765-780`；`src/backend/cbrowser/api/v1/router.py:509-520,548-556`；`src/backend/cbrowser/supervisor/control_server.py:112`；`src/backend/cbrowser/supervisor/recovery_coordinator.py:632`。
- 问题：0004 只删除 `profiles` 的两列，没有重写既有 `profile_config_versions.snapshot`。t016 之前的 create/update 路径把 `config.model_dump()` 整体落盘（base `repository.py:145-156,377-389`），所以老快照含 `runtime_mode`/`viewer_mode`；`ProfileConfig` 是 `extra="forbid"`。已复现：用 0003 schema 建库、插入带旧格式快照的 Profile，再升级到 head，`get_config_version()` 返回的 `config` 仍含两键，`ProfileConfig(**config)` 抛 `ValidationError: extra_forbidden`。Supervisor `/supervisor/v1/profiles/start` 在 `control_server.py:112` 构造配置失败并映射为 502 `Configuration query failed`；RuntimeCoordinator 用最新版本号发起 start，因此所有升级后未编辑过的既有 Profile 都无法启动；`recovery_coordinator.py:632` 的恢复路径同样失败。公开 API `GET .../versions` 直接把旧 config dict 原样返回，仍含两个已删除字段，也违反 AC-007 的“API 响应/配置快照不再包含”。
- 建议：在 0004（或新迁移）中逐行重写 `profile_config_versions.snapshot`，删除两个键（磁盘 `runtime/*/snapshot.json` 也做同样清理或由写入侧覆盖）；或在 `_to_domain_snapshot`/响应 DTO 统一剥离该两个遗留键并让 `ProfileConfig` 解析时兼容。补“0003 既有库含 Profile + 旧快照升级 head 后 GET versions 与 Supervisor start 成功”的回归测试。

### t016_code_f005 - internal OpenAPI 仍缺可达错误码，AC-006 守卫测试仍是硬编码子集（Round 2 复核）

- 严重度：important
- 锚点：AC-006（“公开 OpenAPI 与新增的内部 API 契约声明……实现实际可达的错误码；守卫测试保证实现可达响应码包含于契约”）。
- 位置：`src/backend/cbrowser/api/internal_supervisor.py:83-95`（`add_api_route` 仍丢弃原路由的 `responses` 元数据）；`src/backend/cbrowser/api/app.py:392-406`（internal 分支只补 401/403/503，且仅 bind/observed 补 404/409）；`schemas/openapi/cbrowser_internal.json:2733,2973,3322`；`tests/unit/test_runtime_agent_protocol_export.py:27-50`。
- 问题：f005 只修了 login 的 429 与 bind/observed 的 404/409，其他内部契约仍缺实现可达码。例如 `GET /api/v1/internal/supervisor/profiles/{profile_id}` 实际在 `router.py:240-248` 返回 404，但 `schemas/openapi/cbrowser_internal.json:2733` 仅声明 200/401/403/422/503；`GET /profiles/{profile_id}/runtime`（可 404）、`PATCH /profiles/{profile_id}/runtime/desired-state`（可 404/409）、`GET /profiles/{profile_id}/versions/{version}`（可 404）、`GET /api/v1/internal/gateway/profiles/{profile_id}/runtime`（`internal_gateway.py:154-158` 可 404/409）、`POST /api/v1/internal/supervisor/artifacts/downloads`（`internal_artifacts.py:43-44` 可 404）同样缺 404/409。`add_api_route` 没有透传原路由 `responses`；`contracted_openapi` 的 internal 分支只做固定补码。守卫测试仍只断言少量固定码，没有遍历路由比较“实现可达码 ⊆ 契约声明”，AC-006 的守卫要求未满足。
- 建议：`add_api_route` 透传原 `responses`（或复用原始 `APIRoute`）；internal 分支按路径/方法和已声明的 `responses` 补码；把守卫改成遍历 `app.routes` 或统一提取 `HTTPException` 状态码后与契约做集合包含检查，缺项即失败。

### t016_code_f013 - 自动化令牌限流按反向代理地址归并，可被伪造 token 锁死全部自动化连接

- 严重度：minor
- 锚点：AC-005（“伪造的自动化令牌……被限流”）；认证路径可用性。
- 位置：`src/backend/cbrowser/api/v1/automation_router.py:83-86`；`src/backend/cbrowser/auth/service.py:321-326`；对照登录路径 `src/backend/cbrowser/api/v1/auth_router.py:68-72`。
- 问题：自动化 WS 用 `websocket.client.host` 作为限流键，这是直连 TCP peer；部署在 Caddy/Gateway 反向代理后，所有客户端共享代理地址。`_automation_limiter` 阈值 10 次/60s，任意客户端发送 10 个伪造 `cbat_` token 就会让该代理地址进入限流，随后所有合法自动化 WS 握手返回 4408；`internal_gateway.py:120-125` 的固定 `"internal-gateway"` 键也有同样归并问题。登录路径已使用 `resolve_client_ip` + `trusted_proxy_cidrs`，自动化入口没有复用。
- 建议：WS 入口复用 `resolve_client_ip`（传入 `app.state.trusted_proxy_cidrs` 与 X-Forwarded-For），或按 token hash/profile 维度限流并提高全局阈值；补“伪造 token 达阈值后合法 token 仍可连接”的回归测试。

### t016_code_f014 - 仍有内部 URL 未转义 profile_id

- 严重度：minor
- 锚点：AC-010（“内部 URL 中的标识符正确转义”）。
- 位置：`src/backend/cbrowser/api/v1/automation_router.py:58-61`（`_supervisor_ws_url`）；`src/backend/cbrowser/api/runtime_coordinator.py:419`（status URL）。
- 问题：本 task 已把 supervisor/recovery/control/gateway 的调用点改为 `quote(..., safe="")`，但这两处仍直接插值。`profile_id` 来自路由参数/服务调用，含 `?`/`#`/`/` 时会改变目标路径或查询；当前 profile id 由 uuid4 生成，实际触发面窄，但 AC 要求统一转义，且新增 URL 测试也没有覆盖这两个调用点。
- 建议：两处改为 `quote(profile_id, safe="")`，用 `httpx.MockTransport` 传特殊字符 id 断言实际请求路径。

### t016_code_f015 - 任一损坏的下载事件文件会让新下载事件保存与索引重建持续失败

- 严重度：minor
- 锚点：AC-003（“无法解析的事件……进入可人工恢复的隔离区、修复后可重试”）；行为回归。
- 位置：`src/backend/cbrowser/runtime_agent/event_storage.py:205-245,247-260`。
- 问题：`save_download_event` 先写事件文件，再在 `_get_download_index` 首次构建时调用 `_rebuild_download_index`，后者对任一 `*.json` 解析失败即抛 `StorageError`。已复现：下载事件目录预置 `corrupt.json` 后调用 `save_download_event`，事件文件虽写入但抛 `StorageError`，`download-index.json` 不生成；后续每次保存仍抛错（CDP 监听器把它记为 malformed frame），`/events/downloads` 持续 503。Supervisor 的 forwarder 会把该文件 dead-letter 后自愈，但 agent 自身没有“隔离损坏文件后继续”的路径；按 AC-003 应在读取侧隔离。
- 建议：`_rebuild_download_index` 对损坏文件记录并移入隔离区（或 `*.corrupt-*`）后继续；补“损坏文件 + 新事件保存/索引恢复”测试。

### t016_code_f016 - capture_alive 在 \_last_rearm_ok 初始化前访问会抛 AttributeError

- 严重度：minor
- 锚点：行为缺陷（管理器生命周期/健康信号）。
- 位置：`src/backend/cbrowser/runtime_agent/cdp_proxy.py:56-65,78,166-215`。
- 问题：`_last_rearm_ok` 只在 `start()` 的 await 之后或重连分支赋值；`capture_alive` 在监听任务已创建但 rearm 尚未完成时被调用（或直接对未 start 的 manager 调用）会抛 AttributeError，而不是返回 False。生产 main 在 app 创建前 await start，当前路径不可达；但公开属性应始终可安全读取，重连/启动失败路径也会留下未定义状态。
- 建议：在 `__init__` 初始化为 False，并在 `close()` 清除。

## 结论

- 前轮 finding 复核：
    - f001：已消除（旧 `profiles.launch_args` 读取/更新不再 500；我用 0003 库插入旧参数后升级 head 复现读取与更新均正常。策略是读时过滤旧参数、无日志；后续 PATCH 会把过滤结果持久化，属提示级观察）。旧参数问题不覆盖 config version 快照，见 f012。
    - f002：已消除（本地 websockets 探针：断线后重连，`rearm_count` 1→2，`capture_alive=True`；`_listen_events` 不再自锁）。新增未初始化属性问题见 f016。
    - f003：已消除（`POST /api/v1/profiles` 非法 launch_args 由 `ProfileCreateRequest` 校验；`test_v2_api_subprocess` 的 create 流程实际断言 422 且不新增 Profile）。
    - f004：已消除（invalid-format/not-found 不再写 audit；10 次失败后返回 rate_limited；单测覆盖）。限流键的代理归并问题见 f013。
    - f005：未消除（部分修复，见上方 Round 2 复核）。
    - f006：已消除（`ProfileService`/`ArtifactStore` 默认 1000；chown 失败抛错；API 构造点不再依赖进程 uid；单测覆盖显式 uid）。AC-008 的真实双容器 E2E 仍为 trust_prior。
    - f007：已消除（recovery_coordinator 5 处、core、control_server 均已 `quote`）；仍有 automation_router/runtime_coordinator 两处，见 f014。
    - f008：已消除（`DownloadEventRecord`/`RuntimeEventRecord` 加 `version=1`，写入侧落盘版本，agent 索引重建与 supervisor `_parse_event` 均可读 v1；v99 被 supervisor 隔离。agent 索引不显式检查版本，仅按 schema 兼容，当前生产者只写 v1，无可见缺陷）。
    - f009：已消除（`db_context` 改用 `run_database_migrations`；`test_models_match_migrations` 的 `compare_metadata` 返回 `[]`；模型补 `idx_artifacts_profile_sha256`）。我另行验证 0003 带数据升级 head：行保留、两列删除。0003→head 数据测试仍缺，归 test reviewer；旧 snapshot 数据问题见 f012。
    - f010：修不彻底（persistence 字段列表、runtime_persistence、domain 描述已改；但 `docs/blueprint/domain.md:27` 状态图仍用 `failed`；`docs/specs/v2_runtime_validation.md:135` 仍用现在时且无 t001 时点；`docs/blueprint/security.md:32,35` 仍写 X11 1777/开发路径保留 0777 回退；`docs/blueprint/browser_runtime.md:19,24` 仍写 sticky 1777；`docs/specs_index.md:13` 声称 access_control 由 t016 更新但该文件无 diff）。
    - f011：已消除（`docker_adapter.py:637-643` 改为 0600 + chown；分支仍不可达）。
- 本轮新发现：5 条（f012 critical；f013–f016 minor）。前轮 f005 仍未解决，见上方复核。
- 未进表的提示：
    - 文件过大（实现源码阈值 400/800，均本 task 净增）：`supervisor/core.py` 1288（+39）、`docker_adapter.py` 1060（+26）、`runtime_agent/runner.py` 858（+78）、`services/profile_service.py` 636（+56）、`domain/models.py` 531（+21）、`api/app.py` 428（+90）、`supervisor/recovery_coordinator.py` 632（+1）；测试源码 `tests/integration/test_v2_api_subprocess.py` 926（+14）。生成物 `schemas/openapi/*.json`、`src/frontend/src/shared/api/generated/*.d.ts` 排除。
    - 圈复杂度：`SupervisorCore._reconcile_profile`、`DownloadArtifactForwarder.forward_pending`、`CdpProxyManager._listen_events`、`contracted_openapi` 估计 ≥10；本次主要是搬移/分支隔离，未单独出 finding，建议后续拆分。
    - `/events/downloads` 仍未暴露 `limit/offset`（`event_storage.get_download_events` 已支持分页），A32 的“分页”只完成一半；当前有 100 条/实例上限，无阻断性影响。
    - `src/frontend/tsconfig.tsbuildinfo`（构建缓存）仍在 diff 中，建议提交前还原。
    - 旧 launch_args 在读时静默丢弃且无日志，后续 PATCH 会持久化丢弃结果；属 f001 的明确策略选择，建议至少记录一次 warning 便于用户发现配置被裁剪。
    - `note.md` 自述 unit 530 passed；本地复跑 `tests/unit` 531 passed（新增测试后数量）。
    - `contracted_openapi` 对 `/api/v1/health`、`/api/v1/auth/login` 这类无认证路由也补了 401/403/503，属过度声明；AC-006 只要求可达码包含于契约，未单独出 finding，建议顺手收敛。
- 总体判断：f012 使升级后的既有 Profile 无法启动且 API 仍回传已删字段，f005 的 internal 契约与守卫仍未达标；当前不可信。
- 系统性 follow-up：无（f012、f005 均在 t016 范围；旧 snapshot 迁移应作为本 task 的 0004 数据迁移补充）。

### AC 复验方式

- AC-001：re_verified——枚举公开/内部 OpenAPI，确认 reporting 路径只挂内部面；`test_supervisor_reporting_routes_are_service_plane_only` 通过。
- AC-002：re_verified——逐帧隔离代码复核 + 本地 websockets 断线重连探针（重连后 rearm，捕获存活）。
- AC-003：re_verified——复核越界拒绝、dead-letter、长文件名截断与版本信封；探针确认 v1 往返、v99 隔离；发现 agent 索引损坏文件路径（f015）。
- AC-004：re_verified——复核 per-profile try/except、启动失败后控制面继续与后台 30s 重试；相关单测通过。
- AC-005：re_verified——复核 token 过期、过期 session 清理、docs 默认关闭、503 映射与 Retry-After；限流键归并作为 f013 提示。
- AC-006：re_verified——实际比较 live 与两份 schema（漂移测试通过）、前端类型重生成 MATCH；发现 internal 可达码缺项（f005）。
- AC-007：re_verified——grep 确认 v2 新代码/新快照/生成类型无 runtime_mode/viewer_mode；0003→head 带数据升级验证行保留、列删除；发现旧 config version 快照未迁移（f012）。
- AC-008：trust_prior——真实 Browser/Stream 双容器媒体、输入、剪贴板 E2E 未在本轮复跑，依赖实施侧记录的 E2E 结果；代码层复核了 uid 默认值与权限异常路径。
- AC-009：re_verified——白名单单测通过；`test_v2_api_subprocess` 实测非法 `POST /profiles` 返回 422；runner 第二道校验存在。
- AC-010：re_verified——grep 内部 URL、CDP WS accept 前鉴权、journal 隔离、累计/区间指标与并发配额测试；仍有 2 处未转义（f014）。
- AC-011：re_verified——grep 文档残留并核对 A14 列表；仍有 f010 所列残留。

coverage = 10 / 11

verdict: FAIL

## Round 3 (2026-11-03T04:15:41+08:00)

reviewed_scope: 0c4e212ea79e95c9

## Findings

### t016_code_f005 - internal OpenAPI 仍缺可达错误码，AC-006 守卫测试仍未枚举可达集合（Round 3 复核）

- 严重度：important
- 锚点：AC-006（“公开 OpenAPI 与新增的内部 API 契约声明……实现实际可达的错误码；守卫测试保证实现可达响应码包含于契约”）。
- 位置：`src/backend/cbrowser/api/internal_supervisor.py:97-99`（`add_api_route` 仍不传原路由 `responses`）；`src/backend/cbrowser/api/app.py:396-405`（internal 分支只按路径猜测补码）；`schemas/openapi/cbrowser_internal.json`；`tests/unit/test_runtime_agent_protocol_export.py:68-88`。
- 问题：Round 2 的缺口只修了一部分。当前 internal 契约仍缺实现可达码，实测：
    - `POST /api/v1/internal/supervisor/artifacts/downloads` 在 Profile 不存在时返回 404（`src/backend/cbrowser/api/internal_artifacts.py:44`），契约只声明 `200/401/403/422/503`；该路径没有 `{}`，`app.py` 的启发式不会补 404。
    - `PATCH /api/v1/internal/supervisor/profiles/{profile_id}/runtime/desired-state` 在复用 `Idempotency-Key` 且请求体不同时返回 409（`repository.py:641` → `IdempotencyConflictError` 全局 handler），契约只声明 `200/401/403/404/422/503`；启发式只给 `/runtimes/bind`、`/runtimes/observed` 补 409。
    - 守卫测试仍只断言固定子集（artifact upload 的 400/413/507、bind 的 404/409），没有遍历路由或提取 `HTTPException` 状态码做“实现可达集合 ⊆ 契约声明”的通用检查，与 A26 的修复要求不符。
- 建议：`add_api_route` 透传原路由 `responses`（或直接复用原 `APIRoute`）；internal artifacts 补 404、internal desired-state 补 409；把守卫改成枚举 `app.routes` 并断言可达状态码集合包含于契约。

### t016_code_f017 - 前端生成 API 类型与最新公开 OpenAPI 契约不同步

- 严重度：important
- 锚点：AC-006（“前端生成类型与契约同步”）。
- 位置：`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts:1972-2247`（4 个 artifact 操作）；`schemas/openapi/cbrowser_v1.json`（2026-11-03T04:00 更新，生成类型 mtime 为 2026-11-03T03:33）。
- 问题：`app.py` 在 04:00 的 OpenAPI 补码（artifact 的 400/413/507）没有重新生成前端类型。用仓库脚本 `openapi-typescript ../../schemas/openapi/cbrowser_v1.json` 重生成到临时文件后，与签入文件有 108 行差异：`list/upload/download/delete` 四个 artifact 操作都缺 `400`、`413`、`507`。例如 `upload_artifact_api_v1_profiles__profile_id__artifacts_post`（`:2039`）的 responses 只有 401/403/404/422/503。AC-006 已打勾但“前端生成类型与契约同步”实际未满足；这也会让前端开发者看不到配额/文件过大/非法请求的类型分支。
- 建议：运行 `npm run generate:api --prefix src/frontend` 并提交生成文件；在契约漂移测试中增加“重新生成后与签入文件一致”的检查（与 `cbrowser_internal.json` 的漂移测试同类）。

### t016_code_f018 - ProfileUpdateRequest 重复 launch_args 校验器，显式 null 被静默清空

- 严重度：minor
- 锚点：代码质量（死代码/重复校验）；AC-009 的写入拒绝仍由前一个校验器保证。
- 位置：`src/backend/cbrowser/domain/models.py:307-310`、`:351-356`。
- 问题：`ProfileUpdateRequest` 上声明了两个 `field_validator("launch_args")`。第二个 `normalize_launch_arguments` 的注释和实现是从 `ProfileConfig` 复制的，实际不会再拒绝非法值（第一个已抛错），且会把显式 `null` 转成 `[]`：`ProfileUpdateRequest(launch_args=None).model_dump(exclude_unset=True)` 返回 `{"launch_args": []}`。同一请求里的其他可选列表字段（如 `extension_paths: null`）会在后续 `ProfileConfig` 构造时报 422，因此 null 语义不一致；一个按 OpenAPI `string[] | null` 发送 null 的客户端会静默清空用户的启动参数。
- 建议：删除第二个校验器；若希望 null 表示清空，请在请求 DTO 上显式实现并补测试，而不是依靠复制来的过滤函数。

## 结论

- 前轮 finding 复核（以当前 diff/代码为准）：
    - f001：已消除。`ProfileConfig.normalize_launch_arguments` 用 `filter_launch_args` 读取旧行，旧参数不再触发 500；新写入由 `ProfileCreateRequest`/`ProfileUpdateRequest` 严格校验。
    - f002：已消除。重连路径在监听协程内发送 rearm 且不等待自身消费 ACK，`test_cdp_listener_reconnects_and_rearms_after_disconnect` 覆盖；f016 的未初始化属性仍是 minor。
    - f003：已消除。`ProfileCreateRequest` 的 `launch_args` 校验器存在，非法 `POST /profiles` 返回 422。
    - f004：已消除。`authorize_automation` 引入了按来源的 `LoginRateLimiter`，invalid-format/not-found 只记日志不落库，单测覆盖 10 次失败后 `rate_limited`。
    - f005：**未消除**（见上，internal artifacts 404 与 desired-state 409 仍缺，守卫仍为硬编码子集）。
    - f006：已消除。`ProfileService`/`ArtifactStore` 默认 `runtime_uid=1000`，chown 失败抛错，API 构造点不再取进程 uid。
    - f007：已消除。recovery_coordinator 5 处、core、control_server 均改为 `quote(profile_id, safe="")`；f014 的两处遗留仍为 minor。
    - f008：已消除。`DownloadEventRecord`/`RuntimeEventRecord` 增加 `version=1`，agent 写盘带版本，supervisor `_parse_event` 兼容 v1 并隔离其他版本。
    - f009：已消除。`db_context` 改为 `run_database_migrations`；`test_models_match_migrations` 的 `compare_metadata` 返回 `[]`。
    - f010：修不彻底（minor）。`docs/blueprint/domain.md:27` 仍用 `failed`；`docs/specs/v2_runtime_validation.md:135` 仍用现在时且无 t001 时点；`docs/blueprint/security.md:32,35` 仍写 X11 1777 与 0777 回退；`docs/blueprint/browser_runtime.md:19,24` 仍写 1777；`docs/specs_index.md:13` 声称 access_control 由 t016 更新但该文件无 diff。
    - f011：已消除。`docker_adapter.py:637-647` 改为 0600 + 运行时 uid chown。
    - f012：**已消除**。新增 `0006_clean_snapshot_modes` 重写 `profile_config_versions.snapshot`；我在 0003 schema 建库、插入含 `runtime_mode`/`viewer_mode` 的旧快照后升级 head，迁移后 snapshot 只剩配置字段，`ProfileConfig` 解析成功。磁盘 `runtime/snapshot.json` 在启动时由 `core.start_profile` 重写，不参与 `ProfileConfig` 解析；未发现新的启动阻塞。该迁移没有专门的数据回归测试，归 test reviewer 复核。
    - f013：仍存在（minor）。`automation_router.py:83-86` 仍用 `websocket.client.host`，反代后所有客户端共享代理地址；`internal_gateway.py:120-125` 仍用固定 `"internal-gateway"` 键，伪造 token 可锁死该来源的自动化授权。
    - f014：仍存在（minor）。`api/v1/automation_router.py:61` 与 `api/runtime_coordinator.py:419` 仍直接拼接 `profile_id`。
    - f015：仍存在（minor）。`event_storage.py:205-231` 的 `_rebuild_download_index` 遇到损坏文件仍抛 `StorageError`，不隔离损坏文件，后续保存与索引重建会持续失败。
    - f016：仍存在（minor）。`cdp_proxy.py:56-65` 的 `capture_alive` 仍读取未在 `__init__` 初始化的 `_last_rearm_ok`，在 `start()` 完成前访问会抛 `AttributeError`。
- 本轮新发现：2 条（blocking：f017；minor：f018）。前轮 f005 仍未解决。
- 未进表的提示：
    - 文件过大（实现源码阈值 400/800，测试源码 600/1200；均本 task 净增）：`supervisor/core.py` 1288、`supervisor/docker_adapter.py` 1060、`runtime_agent/runner.py` 858、`services/profile_service.py` 636、`supervisor/recovery_coordinator.py` 632、`domain/models.py` 531、`api/app.py` 435；测试 `tests/integration/test_v2_api_subprocess.py` 926。生成物 `schemas/openapi/*.json`、`src/frontend/src/shared/api/generated/*.d.ts` 按规则排除。
    - 圈复杂度：`SupervisorCore._reconcile_profile`、`DownloadArtifactForwarder.forward_pending`、`CdpProxyManager._listen_events`、`contracted_openapi` 估计 ≥10；建议后续拆分，本轮未单独出 finding。
    - `/events/downloads` 仍未暴露 `limit/offset`（`agent.py:293-295`），A32 的“分页”只完成存储层一半；当前每实例 100 条上限，无阻断性影响。
    - `src/frontend/tsconfig.tsbuildinfo`（构建缓存）仍在 diff 中，建议提交前还原。
    - `contracted_openapi` 对 `/api/v1/health`、`/api/v1/auth/login` 也补了 401/403/503，属过度声明；AC-006 只要求可达码包含于契约，未单独出 finding。
    - 旧 `launch_args` 在读时静默丢弃且无 warning；建议至少记录一次日志便于用户发现配置被裁剪。
    - `note.md` 自述 unit 530 passed；本地复跑 `tests/unit` 537 passed、`tests/integration` 79 passed。
- 总体判断：f012 已真修，f001–f004、f006–f009、f011 已消除；但 f005 的 internal 契约与守卫仍未达标，且 f017 使前端生成类型落后于最新公开契约，当前不可信。
- 系统性 follow-up：无（f005、f017 均在 t016 范围；f012 的迁移数据测试归 test reviewer）。

### AC 复验方式

- AC-001：re_verified——枚举公开/内部 OpenAPI，确认 reporting 路径只挂内部面；`test_supervisor_reporting_routes_are_service_plane_only` 通过。
- AC-002：re_verified——逐帧隔离、重连与 rearm 代码复核；`test_cdp_listener_reconnects_and_rearms_after_disconnect` 通过；f016 仅剩未初始化属性提示。
- AC-003：re_verified——复核越界拒绝、dead-letter、版本信封、文件名截断与 ingest 结果；f015 的 agent 索引损坏路径仍为 minor。
- AC-004：re_verified——复核 per-profile try/except、启动失败后控制面继续与后台 30s 重试；相关单测通过。
- AC-005：re_verified——复核 token 过期、过期 session 清理、docs 默认关闭、503 映射、Retry-After 与自动化限流单测；f013 的限流键仍为 minor。
- AC-006：re_verified——比较 live 公开/内部 schema 与签入文件（漂移测试通过）；实测 internal artifacts 404、desired-state 409 未声明（f005）；重新生成前端类型到临时文件发现与签入文件不同（f017）。
- AC-007：re_verified——0003 既有库含旧快照升级 head 后快照清理、字段删除、`ProfileConfig` 解析成功；`test_models_match_migrations` 通过；`0006` 无专门数据回归测试，归 test reviewer。
- AC-008：trust_prior——真实 Browser/Stream 双容器媒体、输入、剪贴板 E2E 未在本轮复跑，依赖实施侧记录的 E2E；代码层复核了 uid 默认值、0700/0600 与 0750/0640 权限和 chown 失败路径。
- AC-009：re_verified——白名单单测通过；`test_v2_api_subprocess` 实测非法 `POST /profiles` 返回 422；runner 第二道校验存在。
- AC-010：re_verified——grep 内部 URL、CDP WS accept 前鉴权、journal 隔离、累计/区间指标与并发配额测试；仍有 f014 两处未转义。
- AC-011：re_verified——grep 文档残留并核对 A14 列表；仍有 f010 所列残留。

coverage = 10 / 11

verdict: FAIL

## Round 4 (2026-11-03T04:35:00+08:00)

reviewed_scope: 026a732d5e26f680

## Findings

### t016_code_f005 - internal OpenAPI 可达码已补齐；守卫测试仍为硬编码子集（Round 4 复核）

- 严重度：minor（代码层缺口已消除；剩余属测试层，与 `t016_test_f008` 同一问题）
- 锚点：AC-006（“守卫测试保证实现可达响应码包含于契约”）；Round 3 指出的契约漏项已消除。
- 位置：`src/backend/cbrowser/api/internal_supervisor.py:97-99`；`src/backend/cbrowser/api/app.py:380-436`；`schemas/openapi/cbrowser_internal.json`；`tests/unit/test_runtime_agent_protocol_export.py:68-96`。
- 问题：Round 3 的三处漏项已补齐：`/api/v1/internal/supervisor/artifacts/downloads` 声明 404、`/profiles/{profile_id}/runtime/desired-state` 声明 409、`/profiles/{profile_id}` 声明 404。实测 `create_app(include_internal_schema=True).openapi()` 与签入 `cbrowser_internal.json` deep-equal，`$ref` 无悬空；公开 schema 同样与签入文件一致。但守卫测试仍只对若干已知 operation 硬编码断言状态码，未遍历 `app.routes`/OpenAPI 做“实现可达码 ⊆ 契约”的通用检查；新增 route 返回未声明码时不会失败。该剩余项属测试层，已由 `t016_test_f008` 跟踪，本轮不作为代码 blocking。
- 建议：测试侧补通用枚举守卫；代码侧无需再改。

### t016_code_f010 - AC-011 文档残留（Round 4 复核）

- 严重度：minor
- 锚点：AC-011（“后端相关 blueprint 与 spec 与代码和已落地决策一致”）。
- 位置：`docs/blueprint/security.md:32,33,35`；`docs/blueprint/browser_runtime.md:19`；`docs/specs_index.md:13`；`docs/specs/v2_runtime_validation.md:135`。
- 问题：`security.md:32` 与 `browser_runtime.md:19` 仍写 X11 目录 1777，代码已为 0750（`src/backend/cbrowser/supervisor/docker_adapter.py:386`）；`security.md:33` 仍写“无法 chown 时回退 0755/0644”，代码已改为 chown 失败抛错（`src/backend/cbrowser/adapters/filesystem/artifact_store.py:141-148`、`src/backend/cbrowser/services/profile_service.py:125-131`）；`security.md:35` 仍写宿主直跑保留 0777 回退，代码已无 0777；`specs_index.md:13` 声称 `access_control` 由 t016 更新，但该文件无 diff；`v2_runtime_validation.md:135` 仍用现在时说“均未合入生产代码库”，缺 t001 时点标注。`domain.md:27` 的 `failed`→`error` 已修正。
- 建议：按 ADR 014 与当前代码修正上述文档；`specs_index` 去掉 t016 或同步更新 access_control；t001 spec 加“截至 t001 验收时点”。

### t016_code_f013 - 自动化令牌限流按反向代理地址归并（Round 4 复核）

- 严重度：minor
- 锚点：AC-005（“伪造的自动化令牌……被限流”）；认证路径可用性。
- 位置：`src/backend/cbrowser/api/v1/automation_router.py:84`；`src/backend/cbrowser/api/internal_gateway.py:123`；`src/backend/cbrowser/auth/service.py:41-43`。
- 问题：自动化 WS 仍用 `websocket.client.host` 作为限流键，反代后所有客户端共享代理地址；`_automation_limiter` 阈值 10 次/60s，任意客户端发送 10 个伪造 `cbat_` token 即可让该代理地址进入限流，随后合法自动化 WS 握手返回 4408；`internal_gateway.py:123` 的固定 `"internal-gateway"` 键同样可被锁死。登录路径已用 `resolve_client_ip`，自动化入口未复用；新增的全局 200/15min 上限缓解但不能消除。
- 建议：WS 入口复用 `resolve_client_ip` + `trusted_proxy_cidrs`，或按 token hash/profile 维度限流。

### t016_code_f014 - 仍有内部 URL 未转义 profile_id（Round 4 复核）

- 严重度：minor
- 锚点：AC-010（“内部 URL 中的标识符正确转义”）。
- 位置：`src/backend/cbrowser/api/v1/automation_router.py:58-61`；`src/backend/cbrowser/api/runtime_coordinator.py:418-420`。
- 问题：`_supervisor_ws_url` 与 runtime_coordinator 的 status URL 仍直接插值 `profile_id`；含 `/`、`?`、`#` 时会改变目标路径或查询。supervisor/recovery/control/gateway 的调用点已统一 `quote(..., safe="")`，这两处遗漏。
- 建议：两处改为 `quote(profile_id, safe="")`，补 `httpx.MockTransport` 特殊字符断言。

### t016_code_f015 - 损坏下载事件文件使索引重建持续失败（Round 4 复核）

- 严重度：minor
- 锚点：AC-003（“无法解析的事件……进入可人工恢复的隔离区、修复后可重试”）。
- 位置：`src/backend/cbrowser/runtime_agent/event_storage.py:205-225`、`:290-296`。
- 问题：`_rebuild_download_index` 与 `get_download_events` 对任一损坏 `*.json` 抛 `StorageError`，不隔离损坏文件；后续 `save_download_event`/`get_download_events` 持续失败，`/events/downloads` 503。Supervisor 侧会 dead-letter 自愈，agent 侧无隔离路径。
- 建议：读取侧把损坏文件移入隔离区后继续；补“损坏文件 + 新事件保存/索引恢复”测试。

### t016_code_f016 - capture_alive 在 _last_rearm_ok 初始化前访问会抛 AttributeError（Round 4 复核）

- 严重度：minor
- 锚点：行为缺陷（管理器生命周期/健康信号）。
- 位置：`src/backend/cbrowser/runtime_agent/cdp_proxy.py:56-65`；`__init__`（`:40-53`）未初始化 `_last_rearm_ok`。
- 问题：`capture_alive` 在 `start()` 的 await 完成前或 `start()` 失败后访问 `_last_rearm_ok` 会抛 AttributeError，而非返回 False。生产路径当前先 await start，但公开属性应始终可安全读取。
- 建议：`__init__` 初始化为 False，`close()` 清除。

### t016_code_f018 - ProfileUpdateRequest 重复 launch_args 校验器，显式 null 被静默清空（Round 4 复核）

- 严重度：minor
- 锚点：代码质量（重复校验）；AC-009 的写入拒绝仍由第一个校验器保证。
- 位置：`src/backend/cbrowser/domain/models.py:309-312`、`:353-357`。
- 问题：两个 `field_validator("launch_args")`；第二个 `normalize_launch_arguments` 从 `ProfileConfig` 复制，实际不再拒绝非法值，且把显式 `null` 转成 `[]`。实测 `ProfileUpdateRequest(launch_args=None).model_dump(exclude_unset=True)` 返回 `{"launch_args": []}`；客户端按 OpenAPI `string[] | null` 发 null 会静默清空启动参数，与其他可选列表字段（null → 422）语义不一致。
- 建议：删除第二个校验器；若要 null 表示清空，请在请求 DTO 显式实现并补测试。

## 结论

- 前轮 finding 复核（以当前 diff/代码为准）：
    - f001：已消除。`ProfileConfig.normalize_launch_arguments` 用 `filter_launch_args` 读旧行，旧参数不再触发 500；新写入由 `ProfileCreateRequest`/`ProfileUpdateRequest` 严格校验。
    - f002：已消除。重连路径在监听协程内 send rearm 且不 await 自身 ACK；`test_cdp_listener_reconnects_and_rearms_after_disconnect` 通过；f016 的未初始化属性仍为 minor。
    - f003：已消除。`ProfileCreateRequest` 的 `launch_args` 校验器存在，非法 `POST /profiles` 返回 422；`test_v2_api_subprocess` 覆盖。
    - f004：已消除。`authorize_automation` 的 invalid-format/not-found 不落库，10 次失败后 `rate_limited`；单测覆盖。
    - f005：**代码层已消除，降为 minor**。internal 可达码补齐、live/签入 schema deep-equal、无悬空 `$ref`；剩余守卫测试为硬编码子集，属测试层，`t016_test_f008` 跟踪。
    - f006：已消除。`ProfileService`/`ArtifactStore` 默认 `runtime_uid=1000`，chown 失败抛错，API 构造点不取进程 uid。
    - f007：已消除。recovery_coordinator 5 处、core、control_server 均 `quote(profile_id, safe="")`；f014 的两处遗留仍为 minor。
    - f008：已消除。`DownloadEventRecord`/`RuntimeEventRecord` 增加 `version=1`，agent 写盘带版本，supervisor `_parse_event` 兼容 v1 并隔离其他版本。
    - f009：已消除。`db_context` 改为 `run_database_migrations`；`test_models_match_migrations` 的 `compare_metadata` 返回 `[]`；模型补 `idx_artifacts_profile_sha256`。
    - f010：仍存在（minor，见上）；`domain.md:27` 的 `failed`→`error` 已修正。
    - f011：已消除。`docker_adapter.py:637-647` 改为 0600 + 运行时 uid chown。
    - f012：已消除。`0006_clean_snapshot_modes` 重写 `profile_config_versions.snapshot`；0003 旧库含旧快照升级 head 后 `ProfileConfig` 解析成功。
    - f013：仍存在（minor，见上）。
    - f014：仍存在（minor，见上）。
    - f015：仍存在（minor，见上）。
    - f016：仍存在（minor，见上）。
    - f017：**已消除**。用仓库内 `openapi-typescript ../../schemas/openapi/cbrowser_v1.json` 重生成到临时文件，与签入 `cbrowser_v1.d.ts` diff MATCH；`test_internal_openapi_export_matches_checked_in_file` 与 `test_exported_openapi_schema_matches_live_app` 通过。`.d.ts` 仍无自动化漂移守卫（测试层 minor）。
    - f018：仍存在（minor，见上）。
- 本轮新发现：0 条（无新 finding）。
- 未进表的提示：
    - 文件过大（实现源码阈值 400/800，测试源码 600/1200；均本 task 净增）：`supervisor/core.py` 1288、`supervisor/docker_adapter.py` 1060、`runtime_agent/runner.py` 858、`services/profile_service.py` 636、`supervisor/recovery_coordinator.py` 632、`domain/models.py` 531、`api/app.py` 439；测试 `tests/integration/test_v2_api_subprocess.py` 926。生成物 `schemas/openapi/*.json`、`src/frontend/src/shared/api/generated/*.d.ts` 按规则排除。
    - 圈复杂度：`SupervisorCore._reconcile_profile`、`DownloadArtifactForwarder.forward_pending`、`CdpProxyManager._listen_events`、`contracted_openapi` 估计 ≥10；建议后续拆分，本轮未单独出 finding。
    - `/events/downloads` 仍未暴露 `limit/offset`（`src/backend/cbrowser/runtime_agent/agent.py:293-295`）；当前每实例 100 条上限，无阻断性影响。
    - `contracted_openapi` 的路径启发式对 `/api/v1/health`、GET 路由、DELETE/stop、artifact GET 等补了不可达的 401/403/422/400/413/507，属过度声明；AC-006 只要求可达码 ⊆ 契约，未出 finding，建议收敛。
    - `src/frontend/tsconfig.tsbuildinfo`（构建缓存）仍在 diff 中，建议提交前还原。
    - `tests/e2e/test_browser_runtime_e2e.py:2310-2311` 新增的 `stat.S_IMODE` 断言仍缺 `import stat`（测试层，`t016_test_f015` 跟踪；不影响本代码报告）。
    - `note.md` 自述 unit 530 passed；本地复跑 `tests/unit` 537 passed、`tests/integration` 79 passed、`src/backend/tests` 384 passed。
- 总体判断：f005 的代码层契约缺口与 f017 均已真修（live/签入 schema deep-equal、前端类型重生成 MATCH、无悬空 `$ref`），本轮无新 blocker；剩余为 f010/f013/f014/f015/f016/f018 六项 minor 与测试层守卫缺口（`t016_test_f008`）。
- 系统性 follow-up：无（均在 t016 范围；守卫测试归 `t016_test_f008`，E2E stat 归 `t016_test_f015`）。

### AC 复验方式

- AC-001：re_verified——public schema 无 internal 路径，internal schema 含 bind/observed/events；`test_supervisor_reporting_routes_are_service_plane_only` 通过。
- AC-002：re_verified——复核 `_listen_events` 逐帧隔离与重连 send rearm；`test_cdp_listener_reconnects_and_rearms_after_disconnect` 通过；f016 minor。
- AC-003：re_verified——复核越界拒绝、dead-letter、version 信封、长文件名截断；f015 minor。
- AC-004：re_verified——复核 per-profile try/except、启动失败后控制面继续与后台重试；相关单测通过。
- AC-005：re_verified——复核 token 过期、过期 session 清理、docs 默认关闭、503、Retry-After、自动化限流；f013 minor。
- AC-006：re_verified——实测 live public/internal schema 与签入文件 deep-equal、无悬空 `$ref`；`openapi-typescript` 重生成 MATCH；auth schemes 与可达码已覆盖；守卫测试仍为硬编码子集（测试层，`t016_test_f008`）。
- AC-007：re_verified——0003 旧库含旧快照升级 head 后 `ProfileConfig` 解析成功；`test_models_match_migrations` 的 `compare_metadata` 为 `[]`。
- AC-008：trust_prior——真实 Browser/Stream 双容器 E2E 未在本轮复跑；依赖 note.md 的 E2E 声明，但 `tests/e2e/test_browser_runtime_e2e.py:2310-2311` 缺 `import stat` 使新增 0600 断言不可执行（测试层，`t016_test_f015`）。
- AC-009：re_verified——白名单单测、非法 `POST /profiles` 422 集成用例、runner 第二道校验均通过。
- AC-010：re_verified——复核 URL 转义（f014 minor 仍在）、CDP WS accept 前鉴权、journal 隔离、累计/区间指标、并发配额；相关单测通过。
- AC-011：re_verified——grep 文档残留，仍有 f010 所列 minor。

coverage = 10 / 11

verdict: PASS

## Round 5 (2026-11-03T04:41:01+08:00)

reviewed_scope: b4916e893f916e54

## Findings

本轮无新 finding。相对 Round 4，最终修复只触及测试：

- `tests/unit/test_runtime_agent_protocol_export.py:109-129` 新增 `test_openapi_all_operations_declare_structural_contract_codes`，遍历公开与内部 schema 的每个 operation，断言 401/403/503、参数化路径 404、写方法 422、artifact 400/413/507。
- `tests/e2e/test_browser_runtime_e2e.py:22` 补 `import stat`，`:2311-2312` 断言 Xauthority 与 Pulse cookie 均为 0600，与生产 `src/backend/cbrowser/runtime_agent/runner.py:174,269` 的 `chmod(0o600)` 一致；文件语法通过 `ast.parse`。

生产代码与两份 OpenAPI schema 自 Round 4 后无变化（`src/backend/cbrowser/api/app.py` 仍 439 行，`schemas/openapi/*.json` 重新对比 live app 均 deep-equal）。

## 结论

- 前轮 finding 复核（以当前 diff/代码与复跑结果为准）：
    - f001：已消除。旧 `launch_args` 读取仍走 `filter_launch_args`（`src/backend/cbrowser/domain/models.py:89-94`），生产代码未变，unit/integration 全绿。
    - f002：已消除。重连 rearm 不 await 自身 ACK（`src/backend/cbrowser/runtime_agent/cdp_proxy.py:190-215`）；`test_cdp_listener_reconnects_and_rearms_after_disconnect` 在 538 passed 中通过。
    - f003：已消除。`ProfileCreateRequest` 校验器在位（`src/backend/cbrowser/domain/models.py:254-257`）；integration 79 passed 含 create 422 用例。
    - f004：已消除。自动化令牌 invalid-format/not-found 不落库与限流未变，相关单测通过。
    - f005：代码层已消除，维持 minor。live internal/public schema 与签入文件 deep-equal，可达码齐全；新增通用结构守卫覆盖每个 operation 的结构性码，但仍未从 handler 提取实际可达状态码做集合包含检查，属测试层，`t016_test_f008` 跟踪。
    - f006：已消除。`ProfileService`/`ArtifactStore` 默认 runtime uid 1000、chown 失败抛错未变。
    - f007：已消除。supervisor/recovery/control 的 `quote(..., safe="")` 未变。
    - f008：已消除。下载/运行事件 `version=1` 信封与 supervisor 兼容/隔离未变。
    - f009：已消除。`tests/unit/test_domain_and_repository.py:541` 的 `test_models_match_migrations` 通过，`compare_metadata` 为空。
    - f010：仍存在（minor）。`docs/blueprint/security.md:32,33,35` 仍写 X11 1777 与 0777 回退；`docs/blueprint/browser_runtime.md:19` 仍写 1777；`docs/specs_index.md:13` 声称 `access_control` 由 t016 更新但该文件无 diff；`docs/specs/v2_runtime_validation.md:135` 仍缺 t001 时点标注。
    - f011：已消除。`src/backend/cbrowser/supervisor/docker_adapter.py` snapshot 分支为 0600 + chown。
    - f012：已消除。`0006_clean_snapshot_modes` 快照清理未变；`test_models_match_migrations` 通过。
    - f013：仍存在（minor）。`src/backend/cbrowser/api/v1/automation_router.py:84` 仍以 `websocket.client.host` 为限流键，`src/backend/cbrowser/api/internal_gateway.py:123` 仍用固定 `"internal-gateway"` 键。
    - f014：仍存在（minor）。`src/backend/cbrowser/api/v1/automation_router.py:61`、`src/backend/cbrowser/api/runtime_coordinator.py:419` 仍未 `quote(profile_id, safe="")`。
    - f015：仍存在（minor）。`src/backend/cbrowser/runtime_agent/event_storage.py:215-223` 与 `:288-296` 对损坏下载事件文件仍抛 `StorageError`，不隔离。
    - f016：仍存在（minor）。`src/backend/cbrowser/runtime_agent/cdp_proxy.py:56-65` 的 `capture_alive` 仍读取未在 `__init__` 初始化的 `_last_rearm_ok`（仅在 `:78,166,173,215` 赋值）。
    - f017：已消除。`openapi-typescript ../../schemas/openapi/cbrowser_v1.json` 重生成到临时文件与签入 `src/frontend/src/shared/api/generated/cbrowser_v1.d.ts` diff MATCH。
    - f018：仍存在（minor）。`src/backend/cbrowser/domain/models.py:307-310` 与 `:351-356` 两个 `launch_args` 校验器，第二个把显式 null 转成 `[]`。
- 本轮新发现：0 条。最终修复未引入新 blocker：新守卫测试 9 passed，public/internal live schema 与签入文件 deep-equal 且无悬空 `$ref`，前端类型重生成 MATCH，e2e 新增 0600 断言与生产权限一致。
- 复跑：`tests/unit` 538 passed、`tests/integration` 79 passed、`src/backend/tests` 384 passed。
- 未进表的提示：
    - 文件过大（实现源码阈值 400/800、测试源码 600/1200，均本 task 净增）：`supervisor/core.py` 1288、`supervisor/docker_adapter.py` 1060、`runtime_agent/runner.py` 858、`services/profile_service.py` 636、`supervisor/recovery_coordinator.py` 632、`domain/models.py` 531、`api/app.py` 439；测试 `tests/integration/test_v2_api_subprocess.py` 926、`tests/e2e/test_browser_runtime_e2e.py` 2912（本轮 +3）。生成物 `schemas/openapi/*.json`、`src/frontend/src/shared/api/generated/*.d.ts` 按规则排除。
    - 圈复杂度：`SupervisorCore._reconcile_profile`、`DownloadArtifactForwarder.forward_pending`、`CdpProxyManager._listen_events`、`contracted_openapi` 估计 ≥10；未单独出 finding，建议后续拆分。
    - `/events/downloads` 仍未暴露 `limit/offset`（`src/backend/cbrowser/runtime_agent/agent.py:293-295`），当前每实例 100 条上限，无阻断性影响。
    - `src/frontend/tsconfig.tsbuildinfo`（构建缓存）仍在 diff 中，建议提交前还原。
    - `contracted_openapi` 对 `/api/v1/health` 等无认证路由补 401/403/503，属过度声明；AC-006 只要求可达码 ⊆ 契约，未出 finding。
    - e2e 的 0600 断言属测试层 `t016_test_f015` 跟踪范围，本轮仅确认语法与生产权限一致，未执行真实 Docker E2E。
    - `note.md` 自述 unit 530 passed 与当前 538 不一致，属实施笔记未更新（流程文件，不影响 verdict）。
- 总体判断：最终 OpenAPI/test 修复未引入 blocker；仅剩 f005/f010/f013/f014/f015/f016/f018 七项 minor，维持 PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：re_verified——`test_supervisor_reporting_routes_are_service_plane_only` 通过；public schema 无 internal 路径，internal schema 含 bind/observed/events。
- AC-002：re_verified——复核 `_listen_events` 逐帧隔离与重连 send rearm；`test_cdp_listener_reconnects_and_rearms_after_disconnect` 通过；f016 minor。
- AC-003：re_verified——复核越界拒绝、dead-letter、version 信封、长文件名截断与相关单测；f015 minor。
- AC-004：re_verified——复核 per-profile try/except、启动失败后控制面继续与后台重试；相关单测通过。
- AC-005：re_verified——复核 token 过期、过期 session 清理、docs 默认关闭、503、Retry-After、自动化限流；f013 minor。
- AC-006：re_verified——live public/internal schema 与签入文件 deep-equal、无悬空 `$ref`，`openapi-typescript` 重生成 MATCH，新增结构守卫通过；按 handler 可达码全集的守卫仍属测试层（`t016_test_f008`）。
- AC-007：re_verified——`test_models_match_migrations` 通过；0006 快照清理与字段删除未变（Round 3/4 已实测 0003 旧库升级）。
- AC-008：trust_prior——真实 Browser/Stream 双容器 E2E 未在本轮复跑；代码层复核默认 uid 1000、0600/0640/0750 权限与新增 e2e 0600 断言一致。
- AC-009：re_verified——白名单与请求 DTO 校验未变，`test_launch_args` 及 integration create 422 用例通过，runner 第二道校验存在。
- AC-010：re_verified——复核 URL 转义、CDP WS accept 前鉴权、journal 隔离、累计/区间指标、并发配额；f014 minor 仍在。
- AC-011：re_verified——grep 文档残留，仍有 f010 所列 minor。

coverage = 10 / 11

verdict: PASS

## Round 6 (2026-11-03T04:54:18+08:00)

reviewed_scope: 511322016902a4df

## Findings

### t016_code_f010 - AC-011 文档对齐仍有两处残留（Round 6 复核）

- 严重度：minor
- 锚点：AC-011（“后端相关 blueprint 与 spec 与代码和已落地决策一致”）。
- 位置：`docs/blueprint/domain.md:27`；`docs/blueprint/artifacts.md:14`。
- 问题：f010 原先列出的四项（`security.md` 的 X11 1777/0777 回退、`browser_runtime.md` 的 1777、`specs_index.md` 的 `access_control` 归属、`v2_runtime_validation.md` 的 t001 时点）均已修正；但 `domain.md:27` 的生命周期图仍写 `starting ──> failed`，而 `ObservedState` 枚举是 `error`（`src/backend/cbrowser/domain/models.py:23`）；`artifacts.md:14` 仍称“无法 chown 的宿主开发环境回退到 0755/0644”，与 ADR 014（`docs/blueprint/decisions.md:134`）及 `artifact_store.py:141-150` 的“非 root 且非 runtime uid 时跳过 chown，但仍使用 0750/0640，chown 失败即报错”相反。
- 建议：把状态图改为 `error`；把 `artifacts.md` 的回退描述改成“保留开发者属主、精确 mode，不回退到全局可写”。

### t016_code_f018 - ProfileUpdateRequest 仍有两个 launch_args 校验器（Round 6 复核）

- 严重度：minor
- 锚点：代码质量（重复校验）；AC-009 的非法写入拒绝仍由第一个校验器保证。
- 位置：`src/backend/cbrowser/domain/models.py:305-308`、`:349-354`。
- 问题：第二轮 `normalize_launch_arguments` 仍存在，注释仍是“Older rows…dropped on read”，但 `ProfileUpdateRequest` 是请求 DTO，不存在“旧行”。实测 `ProfileUpdateRequest(launch_args=['--load-extension=/tmp/evil'])` 被第一个校验器拒绝，`ProfileUpdateRequest(launch_args=None).model_dump(exclude_unset=True)` 仍返回 `{'launch_args': []}`，显式 null 被静默清空，与其他可选列表字段的 null → 422 语义不一致。f018 本轮未修。
- 建议：删除第二个校验器；若确要 null 表示清空，请在请求 DTO 显式实现并补测试。

### t016_code_f019 - 重连 rearm 未校验 CDP 响应即置 capture_alive 为真

- 严重度：minor
- 锚点：行为缺陷（健康信号）；AC-002 的“重连后恢复下载捕获”在主路径成立，但失败响应被静默忽略。
- 位置：`src/backend/cbrowser/runtime_agent/cdp_proxy.py:193-216`（重连发送 `Browser.setDownloadBehavior` 后直接 `_last_rearm_ok = True`）、`:57-66`（`capture_alive` 依赖 `_last_rearm_ok`）、`:147-151`（监听循环只匹配 `pending_cmd_futures` 中的 id）。
- 问题：重连路径为避免自锁，发送 rearm 后不等待 ACK；该命令 id 没有登记到 `pending_cmd_futures`，因此监听循环收到带 `error` 的响应时会被当作普通帧忽略，`rearm_count` 与 `_last_rearm_ok` 仍递增/置真。若 Chrome 拒绝 `setDownloadBehavior`（例如下载目录不可写或状态异常），health 会报告 `cdp_ready=True` / `capture_alive=True`，但下载事件不再落盘。启动路径 `start()` 会 await ACK 并在失败时抛错，两条路径的成功判定不一致。
- 建议：记录本次 rearm 的 command id，在监听循环收到该 id 的响应时检查 `error`，失败则 `_last_rearm_ok = False` 并记录日志；或在独立任务里等待 ACK 后更新状态。

## 结论

- 前轮 finding 复核（以当前 diff/代码与复跑结果为准）：
    - f001：已消除。旧 `launch_args` 读取走 `filter_launch_args`（`domain/models.py:89-92`），`test_launch_args` 覆盖旧参数过滤；unit/integration 全绿。
    - f002：已消除。监听协程内发送 rearm、不 await 自身 ACK；`test_cdp_listener_reconnects_and_rearms_after_disconnect` 通过；f019 是失败响应未校验的新提示。
    - f003：已消除。`ProfileCreateRequest` 校验器在位（`domain/models.py:252-255`），非法参数 422；integration 通过。
    - f004：已消除。invalid-format/not-found 不落库，10 次失败后 `rate_limited`；`test_auth_service` 覆盖。
    - f005：代码层已消除，维持 minor。live/签入 schema 一致；守卫测试仍为结构性子集，属测试层，`t016_test_f008` 跟踪，本报告不重复出 finding。
    - f006：已消除。`ProfileService`/`ArtifactStore` 默认 runtime uid 1000、chown 失败抛错未变。
    - f007：已消除。supervisor/recovery/control 的 `quote(..., safe="")` 未变。
    - f008：已消除。下载/运行事件 `version=1` 信封与 supervisor 兼容/隔离未变。
    - f009：已消除。`test_models_match_migrations` 的 `compare_metadata` 为空。
    - f010：修不彻底（minor）。原列四项已修，残留 `domain.md:27` 与 `artifacts.md:14`，见上。
    - f011：已消除。snapshot 分支 0600 + chown 未变。
    - f012：已消除。`0006_clean_snapshot_modes` 快照清理未变。
    - f013：已消除。自动化 WS 入口改用 `resolve_client_ip` + `trusted_proxy_cidrs`（`api/v1/automation_router.py:83-97`），`rate_limited` 以 4408 关闭；`internal_gateway.py:123` 仍用固定 `"internal-gateway"` 键，但该路由仅服务面 Bearer 可达且生产代码无调用方，不构成用户面锁死，降为提示。
    - f014：已消除。`automation_router.py:61`、`runtime_coordinator.py:420` 均已 `quote(profile_id, safe='')`；grep 未再发现未转义的内部 URL 标识符。
    - f015：已消除。`_rebuild_download_index` 与 `get_download_events` 将损坏文件移入 `downloads/quarantine/` 后继续（`event_storage.py:205-240,285-305`）；`test_corrupt_download_event_is_quarantined_and_does_not_block_new_events` 通过。
    - f016：已消除。`__init__` 初始化 `_last_rearm_ok = False`（`cdp_proxy.py:51`），`capture_alive` 纳入该状态（`:57-66`）；实测未 start 的 manager 返回 False，`close()` 清除。
    - f017：已消除。前端类型与公开 schema 未变，重生成 MATCH。
    - f018：仍存在（minor），见上；本轮“重复校验器”修复未落地。
- 本轮新发现：1 条（f019，minor）；六项 minor 修复核验结果：限流来源、URL 转义、损坏事件隔离、属性初始化四项已修，文档部分修复，重复校验器未修。
- 复跑：`tests/unit` 539 passed（含新增 quarantine 用例）、`tests/integration` 79 passed、`src/backend/tests` 384 passed；针对性 43 passed。未复跑真实 Docker E2E。
- 未进表的提示：
    - 文件过大（实现源码阈值 400/800、测试源码 600/1200，均本 task 净增）：`supervisor/core.py` 1288、`supervisor/docker_adapter.py` 1060、`runtime_agent/runner.py` 858、`services/profile_service.py` 636、`supervisor/recovery_coordinator.py` 632、`domain/models.py` 529、`api/app.py` 439；测试 `tests/integration/test_v2_api_subprocess.py` 926、`tests/e2e/test_browser_runtime_e2e.py` 2912。生成物 `schemas/openapi/*.json`、`src/frontend/src/shared/api/generated/*.d.ts` 按规则排除。
    - 圈复杂度：`SupervisorCore._reconcile_profile`、`DownloadArtifactForwarder.forward_pending`、`CdpProxyManager._listen_events`、`contracted_openapi` 估计 ≥10；建议后续拆分，未单独出 finding。
    - `/events/downloads` 仍未暴露 `limit/offset`（`runtime_agent/agent.py:293-295`），当前每实例 100 条上限，无阻断性影响。
    - `src/frontend/tsconfig.tsbuildinfo`（构建缓存）仍在 diff 中，建议提交前还原。
    - `contracted_openapi` 对 `/api/v1/health` 等无认证路由补 401/403/503，属过度声明；AC-006 只要求可达码 ⊆ 契约，未出 finding。
    - `internal_gateway.py:123` 的固定限流键保留为服务面提示（见 f013 复核）。
    - `note.md` 自述 unit 530 passed 与当前 539 不一致，属实施笔记未更新（流程文件，不影响 verdict）。
- 总体判断：六项 minor 修复中四项已真修，f010 文档仅部分修复、f018 未修，二者与新增 f019 均为 non-blocking minor；无未解决的 critical / important，维持 PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：re_verified——公开 schema 无 internal reporting 路径；`test_supervisor_reporting_routes_are_service_plane_only` 在 539 passed 中通过。
- AC-002：re_verified——复核逐帧隔离、重连与 rearm 发送；`test_listener_isolates_malformed_frame_and_keeps_running`、`test_cdp_listener_reconnects_and_rearms_after_disconnect` 通过；f019 为新发现的重连失败响应提示。
- AC-003：re_verified——复核越界拒绝、dead-letter、version 信封、长文件名截断；新增 quarantine 用例通过，f015 已消除。
- AC-004：re_verified——per-profile try/except、启动失败后控制面继续与后台重试；相关单测通过。
- AC-005：re_verified——复核 token 过期、过期 session 清理、docs 默认关闭、503、Retry-After 与自动化限流；WS 限流来源已改为 `resolve_client_ip`，`test_auth_service` 通过。
- AC-006：re_verified——live public/internal schema 与签入文件一致、无悬空 `$ref`，前端类型重生成 MATCH；按 handler 可达码全集的守卫仍属测试层（`t016_test_f008`）。
- AC-007：re_verified——`test_models_match_migrations` 通过；0006 快照清理与字段删除未变。
- AC-008：trust_prior——真实 Browser/Stream 双容器 E2E 未在本轮复跑，依赖实施侧已有 E2E 记录；代码层复核默认 uid 1000、0600/0640/0750 权限与 chown 失败路径未变。
- AC-009：re_verified——白名单与请求 DTO 校验未变，`test_launch_args`、integration create 422 用例通过，runner 第二道校验存在。
- AC-010：re_verified——grep 确认内部 URL 标识符均已 `quote(..., safe="")`；CDP WS accept 前鉴权、journal 隔离、累计/区间指标、并发配额相关单测通过。
- AC-011：re_verified——grep 文档残留；四项已修，仍有 f010 所列两处 minor。

coverage = 10 / 11

verdict: PASS

## Round 7 (evidence repair)

reviewed_scope: 568063954593bda2

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核（以当前 diff/代码与复跑结果为准）：f001–f004、f006–f009、f011–f017 已消除，与 Round 6 结论一致；f005 维持 minor（代码层可达码已补齐，按 handler 可达码全集的守卫仍属测试层，`t016_test_f008` 跟踪）；f010 两处文档残留仍在——`docs/blueprint/domain.md:27` 状态图写 `starting ──> failed`，而 `ObservedState` 枚举为 `error`（`src/backend/cbrowser/domain/models.py:23`）；`docs/blueprint/artifacts.md:14` 仍称无法 chown 时回退 0755/0644，与 ADR 014 及 `artifact_store.py:141-150` 的“保持精确 mode、失败报错”相反；f018 两个 `launch_args` 校验器仍在（`src/backend/cbrowser/domain/models.py:305-308`、`:349-354`，显式 null 被静默转成 `[]`）；f019 重连 rearm 仍不校验 CDP error 响应即置 `_last_rearm_ok = True`（`src/backend/cbrowser/runtime_agent/cdp_proxy.py:190-216`）。以上四项均为 minor，非 blocking。
- 证据修复核验：当前 worktree 指纹与 prompt 声明一致，`review_scope_fingerprint('fb6185c46f41500a9089e526a1773774a7cd6c67', 'docs/archive/tasks/t016_v2_backend_hardening')` 输出 `568063954593bda2`。修复前 `check_review_status.py` 为 `review_scope=stale / overall=INCOMPLETE / round=6`；原因是 Round 6 后任务目录迁入 `docs/archive/`、新增 `docs/pending/todo/p017_t016_minor_cleanup.md` 与还原 `src/frontend/tsconfig.tsbuildinfo`，均为流程/非交付内容，指纹排除后重新锚定。`git status` 中所有非流程文件 mtime ≤ `2026-11-03T04:47:08+08:00`，早于 Round 6 报告（04:54）；04:54 之后仅 p017（04:57）、archive 迁移（04:59）与 tsbuildinfo 还原。当前 `git diff` 的生产/测试内容与 Round 6 所审一致，未跟踪文件仅 archive 下 `task.md` / `note.md` / 两份 review / `handoff.json` 流程文件。
- 本轮新发现：0 条。
- 复跑：`tests/unit` 539 passed；`tests/integration` 79 passed；`src/backend/tests` 384 passed；`openapi-typescript` 重生成 `src/frontend/src/shared/api/generated/cbrowser_v1.d.ts` 与签入文件 MATCH。
- 未进表的提示：文件过大与圈复杂度同 Round 6（`supervisor/core.py` 1288、`supervisor/docker_adapter.py` 1060、`runtime_agent/runner.py` 858、`services/profile_service.py` 636、`supervisor/recovery_coordinator.py` 632、`domain/models.py` 529、`api/app.py` 439；`tests/integration/test_v2_api_subprocess.py` 926、`tests/e2e/test_browser_runtime_e2e.py` 2912；`SupervisorCore._reconcile_profile`、`DownloadArtifactForwarder.forward_pending`、`CdpProxyManager._listen_events`、`contracted_openapi` 估计 ≥10）；`/events/downloads` 仍未暴露 `limit/offset`（`runtime_agent/agent.py:293-295`，每实例 100 条上限）；`internal_gateway.py:123` 固定限流键仅服务面 Bearer 可达；`contracted_openapi` 对 `/api/v1/health` 等无认证路由补 401/403/503 属过度声明，AC-006 只要求可达码 ⊆ 契约。
- 总体判断：当前 diff 无未解决的 critical / important；仅剩 f005/f010/f018/f019 四项 minor，维持 PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：re_verified——`test_supervisor_reporting_routes_are_service_plane_only` 通过；公开 schema 无 internal 路径，内部 schema 含 bind/observed/events。
- AC-002：re_verified——`test_listener_isolates_malformed_frame_and_keeps_running`、`test_cdp_listener_reconnects_and_rearms_after_disconnect` 通过；`runtime_agent/agent.py:193-199` 健康检查改为 `asyncio.gather(asyncio.to_thread(...))`，不阻塞事件循环。
- AC-003：re_verified——`tests/unit/test_download_reconciler.py` 11 项通过（路径越界、dead-letter、版本隔离、长文件名截断）；`DownloadEventRecord.version` 信封与 ingest 失败原因已落地。
- AC-004：re_verified——`test_one_profile_failure_does_not_block_another_restore`、`test_initial_reconcile_failure_still_reaches_control_plane` 通过；`supervisor/core.py:170-190` 对每个 Profile 独立 try/except。
- AC-005：re_verified——`test_auth_service` 覆盖 token 过期、伪造 token 不写 audit、来源限流、过期 session 清理、服务未配置 503；`test_runtime_event_broadcaster_epoch` 覆盖初始快照与实时事件顺序。
- AC-006：re_verified——`test_runtime_agent_protocol_export.py` 10 项通过（公开/内部 schema deep-equal、三种安全方案、结构错误码）；前端类型重生成 MATCH。
- AC-007：re_verified——`test_models_match_migrations` 的 `compare_metadata` 为空；v2 代码、`schemas/`、前端生成类型与 blueprint/spec grep 均无 `runtime_mode`/`viewer_mode`。
- AC-008：trust_prior——本轮未复跑真实 Docker 双容器 E2E；依赖实施侧已有 E2E 记录（`note.md`）与代码复核（默认 uid/gid 1000、0600/0640/0750、chown 失败抛错）。
- AC-009：re_verified——`test_launch_args` 白名单正反例、`BrowserRunner.validate_launch_arguments` 第二道门；integration create 非法参数返回 422。
- AC-010：re_verified——grep 确认内部 URL 标识符均 `quote(..., safe="")`；journal 隔离、累计/区间指标、下载事件有界索引、并发配额、CDP WS accept 前鉴权相关单测通过。
- AC-011：re_verified——grep 文档；仍存 f010 两处 minor（`domain.md:27`、`artifacts.md:14`）。

coverage = 10 / 11

verdict: PASS

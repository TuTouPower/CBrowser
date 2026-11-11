# Task review t008（reviewer_focus: 代码）

- task：`t008_v2_artifacts_automation`
- spec：`docs/tasks/t008_v2_artifacts_automation/task.md`
- diff_anchor：`63cbd08e40e5b0448829d06d1faed5851ce973ca`
- target：`git -C '<repo>_t008' diff 63cbd08e40e5b0448829d06d1faed5851ce973ca`
- round：1
- reviewed_at：2026-11-02T09:59:48+08:00

reviewed_scope: 4306d5704dd859b2

## Findings

### t008_code_f001 - Supervisor 镜像缺少 websockets 依赖，按仓库 Dockerfile 构建后启动即崩溃

- 严重度：critical
- 锚点：AC-002「外部自动化经独立认证入口到 Supervisor/UDS/loopback CDP」；生产 Supervisor 进程无法启动，整条转发链路不可用。
- 位置：`src/backend/cbrowser/supervisor/control_server.py:23`；`config/docker/supervisor_runtime/requirements.txt:1-21`
- 问题：`control_server.py` 在模块顶层 `import websockets`，但唯一官方 Supervisor 镜像的依赖清单 `config/docker/supervisor_runtime/requirements.txt`（Dockerfile 用 `pip install -r` 安装）没有 `websockets`，也没有 `uvicorn[standard]`。本地用 baseline Supervisor 镜像挂载当前 worktree 的 supervisor 源码实测：
    `ModuleNotFoundError: No module named 'websockets'`（文件 `/app/cbrowser/supervisor/control_server.py`, line 23）。
    因此按仓库 Dockerfile 重建后 Supervisor 在导入阶段即退出，AC-002 的 API→Supervisor→Agent UDS 链路在正式镜像中不可用。现有单测/集成测试在 uv 临时环境中显式 `--with websockets`，掩盖了镜像依赖缺口。
- 建议：在 `config/docker/supervisor_runtime/requirements.in` 与 `requirements.txt` 增加 `websockets`（与 browser_runtime 的 17.4 对齐或其他验证过的版本；也可改用 `uvicorn[standard]` 并锁版本），重建 Supervisor 镜像并执行一次真实 `WS /supervisor/v1/profiles/{id}/cdp` 握手验证。

### t008_code_f002 - DownloadArtifactForwarder 的单游标裁决会永久跳过已完成下载事件

- 严重度：critical
- 锚点：AC-002「自动化断开后……随后真实下载完整入库」、AC-004「为缺少完成事件的已完成文件补登 Artifact……不重复入库」。
- 位置：`src/backend/cbrowser/supervisor/artifact_forwarder.py:96`、`:101-109`、`:117-120`、`:171-174`
- 问题：`forward_pending()` 按文件名排序遍历事件文件，却只维护每个 `(profile, runtime_instance_id)` 的一个 `(mtime_ns, name)` 游标。任何排序在前、mtime 更新的事件（例如 `dl_begin_*`、`dl_canceled_*`，或另一条更晚的 `dl_completed_*`）会先把游标推进到较新的 marker；随后 mtime 更早的 `dl_completed_*` 命中 `marker <= cursor`，被永久跳过。复现脚本 `.scratch/t008_review_code/repro_forwarder_two_completed.py`：两条待转发 completed 事件，一个较旧、一个较新；输出 `forwarded counts: [1, 0, 0]`、`api calls: ['dl_completed_aaaa']`，较旧事件永不发送。`repro_forwarder_cursor.py` 的 canceled+completed 组合同样为 `forwarded: 0 0 0`。
    实际触发场景：Supervisor/API 短暂不可用期间积压了多个 begin/completed/canceled 事件，恢复后完成事件被跳过；API 从未入库，而 Agent 侧事件存储已包含该文件 `(path, sha256)`，后续扫描也会跳过，下载永久不可见。
- 建议：不要用单 mtime 游标裁决；改为持久化 `event_id` 已处理集合（可定期按磁盘现存事件清理），或按 `marker` 升序处理且只在确认不存在更早未处理事件时推进。另需明确 `outcome=ignored` 是否应重试，当前 200 响应一律推进游标。

### t008_code_f003 - 下载入库复用了上传的危险 MIME 拒绝列表，.exe/.msi/.sh 等正常下载被静默拒绝

- 严重度：important
- 锚点：AC-001「下载经 Agent 事件可见且内容/大小正确」。
- 位置：`src/backend/cbrowser/services/artifact_service.py:160-165`
- 问题：`ingest_download()` 用 `mimetypes.guess_type(safe_name)` 推断下载文件类型后调用 `validate_content_type()`，后者包含 `DANGEROUS_CONTENT_TYPES`（`application/x-msdownload`、`application/x-sh` 等）。Python 的 `mimetypes` 把 `.exe/.msi/.bat` 映射为 `application/x-msdownload`、把 `.sh` 映射为 `application/x-sh`，于是这些下载直接抛 `ArtifactInvalidContentType`。`internal_artifacts.py` 将其映射为 HTTP 200 `outcome=rejected`，forwarder 推进游标，文件留在 `/exchange/downloads`，UI 永远不列出。
    复现脚本 `.scratch/t008_review_code/repro_exe_download.py` 输出：
    `raised: ArtifactInvalidContentType Executable content type is not allowed`、`file still present: True`、`artifacts: []`。
- 建议：把危险 MIME 拒绝限制在上传入口；下载入库不要按文件名 denylist 拒绝，可统一记为 `application/octet-stream` 或只记录推断类型。AC-001 的「MIME 校验」针对上传，不应阻断浏览器下载。

### t008_code_f004 - 下载去重使用「name 或 storage_path」而非「路径与校验和」，第二次同名下载被误判为重复

- 严重度：important
- 锚点：AC-004「与 CDP 事件重复时按路径与校验和去重，不重复入库」；AC-001「下载经 Agent 事件可见」。
- 位置：`src/backend/cbrowser/adapters/database/artifact_repository.py:82-84`；`src/backend/cbrowser/services/artifact_service.py:167-174`
- 问题：`find_download_duplicate()` 在相同 `(profile, kind, sha256)` 下，只要 `row.name == name` **或** `row.storage_path == storage_path` 就判重复。两次下载同一 URL/同名文件（Chrome 的 CDP 下载路径分别是 `/exchange/downloads/<guid1>` 与 `<guid2>`，`suggestedFilename` 相同）时，第二次会命中 name 分支，`ingest_download()` 直接返回旧 artifact，不移动、不建行；Agent 侧已保存的完成事件又使启动扫描跳过该文件，最终第二个文件永久留在 downloads 目录且 UI 不可见。
    复现脚本 `.scratch/t008_review_code/repro_duplicate_download.py`：第二次 `created: False`，列表只有 1 条，`guid2 still on disk: True`。
- 建议：按 AC 语义只以规范化后的 `storage_path` + `sha256` 判定重复（同名同内容但路径不同应视为新下载）；同时保留对已移入 `downloads/{artifactId}/` 的旧文件按 storage_path 去重，避免扫描重复入库。

### t008_code_f005 - 下载入库在 DB 写入失败时删除已移动的唯一文件，造成不可逆数据丢失

- 严重度：critical
- 锚点：可观测数据丢失；AC-001「下载内容/大小正确」及失败状态一致性。
- 位置：`src/backend/cbrowser/services/artifact_service.py:178-199`
- 问题：`ingest_download()` 先 `import_download()` 用 `os.replace` 把浏览器下载文件移到 artifact 目录，随后 `create_artifact()` 若抛异常（SQLite busy/磁盘错误/其他 DB 故障），`except BaseException: await ... store.delete(target)` 会把刚移动的唯一文件删除；原 `/exchange/downloads` 路径也已不存在，数据库中没有任何记录。复现脚本 `.scratch/t008_review_code/repro_db_failure_download.py`（monkeypatch `create_artifact` 抛 `RuntimeError("database is locked")`）输出 `source still present: False`、`files anywhere under profile: []`，用户下载文件彻底丢失。
- 建议：DB 失败时把 target 移回 source（或保留 target 并让后续对账重试），不要删除用户文件；只有在 DB 已持久化成功后才允许清理。`import_download` 内部的 move 后哈希失败也应套用同一回滚策略。

### t008_code_f006 - 上传文件以 API 进程 UID/0600 创建，Browser 容器 UID 1000 无法读取 `/exchange/uploads`

- 严重度：important
- 锚点：AC-001「上传返回……容器内 container_path（/exchange/uploads/...）」的可使用性；AC-003「文件只能经 Artifact Service 进出 Profile」。
- 位置：`src/backend/cbrowser/adapters/filesystem/artifact_store.py:195`、`:199`；`src/backend/cbrowser/supervisor/docker_adapter.py:374-390`；Browser 容器 `user="1000:1000"` 见 `docker_adapter.py:679`
- 问题：`write_upload()` 以 `mode=0o750` 创建 `uploads/{artifactId}`、以 `0o600` 创建文件，属主是 API 进程。Supervisor 的 `prepare_profile_directories()` 只对顶层 `uploads`/`downloads` 目录执行 `_secure_directory()`，不递归子目录；Browser 容器固定 UID/GID 1000。当前 v2 API 入口/验证镜像以 root 运行（`config/docker/entrypoint.sh` 未切换用户，API 验证镜像 `Config.User` 为空），因此 `uploads/{artifactId}` 对 UID 1000 既不可遍历也不可读，返回的 `container_path` 在浏览器文件选择器中会 EACCES。只要 API UID 不等于 1000，该问题即出现；只有 API 也以 1000 运行且文件属主一致时才偶然可用。
- 建议：Artifact 文件/目录创建时使用可配置 runtime UID/GID（或 0750/0640 的共享组），或让 Supervisor 在每次启动时递归收敛 `uploads` 属主；同时在 `docs/blueprint/security.md` 补充 uploads 的权限约定，并用真实 Docker 验证浏览器可读取上传文件。

### t008_code_f007 - 下载 API 的 OpenAPI 响应被导出为 application/json，与实际二进制响应不一致

- 严重度：minor
- 锚点：契约·类型一致性（非阻断）。
- 位置：`src/backend/cbrowser/api/v1/artifact_router.py:100-119`；`schemas/openapi/cbrowser_v1.json` 中 `/api/v1/profiles/{profile_id}/artifacts/{artifact_id}` 的 200 响应
- 问题：路由返回 `FileResponse`，但未声明 `response_class`/`responses`，FastAPI 导出的 OpenAPI 200 是 `application/json` 空 schema。依赖生成类型的客户端会误把下载响应当 JSON；前端目前绕过生成类型直接拼接 URL，所以测试未暴露。
- 建议：声明 `response_class=FileResponse` 并补 200 的 `application/octet-stream` binary schema，重新导出 OpenAPI 与前端类型。

### t008_code_f008 - 新增死代码：`ArtifactService.scan_downloads` 与 `_get_auth_service` 无生产调用

- 严重度：minor
- 锚点：死代码。
- 位置：`src/backend/cbrowser/services/artifact_service.py:201-218`；`src/backend/cbrowser/api/v1/automation_router.py:35-39`
- 问题：`scan_downloads()` 仅被单测调用，生产对账由 Agent 的 `download_reconciler` 完成；`_get_auth_service()` 在 automation_router 内没有任何引用。保留这些接口会让后续读者误以为存在 API 侧扫描入口或另一种鉴权路径。
- 建议：删除 `scan_downloads()`（连同 `iterate_completed_downloads` 的 API 侧使用）或真正接入一个受控入口；删除 `_get_auth_service` 及未使用 import。

### t008_code_f009 - 下载完成回调在事件循环内同步计算 SHA-256，最多阻塞 256 MiB 文件时长的 CDP 事件循环

- 严重度：minor
- 锚点：性能/资源（非阻断）。
- 位置：`src/backend/cbrowser/runtime_agent/cdp_proxy.py:224-228`
- 问题：`_handle_download_progress()` 是 CDP WebSocket 监听回调（async 上下文中的同步函数），其中 `_sha256_file()` 直接读整个文件；大文件完成时会阻塞 Agent 事件循环，延迟同一 Agent 上的 CDP/事件处理。`download_reconciler` 与 API 入库均已用 `asyncio.to_thread`，此处行为不一致。
- 建议：把哈希/大小计算移到 `asyncio.to_thread` 或后台任务，完成后再写事件；至少对超过一定大小的文件异步化。

### t008_code_f010 - 跟踪了前端构建缓存 `tsconfig.tsbuildinfo` 并在本 task 改动

- 严重度：minor
- 锚点：仓库卫生（构建产物不应入库/改动静默提交）。
- 位置：`src/frontend/tsconfig.tsbuildinfo:1`
- 问题：该文件是 TypeScript incremental build 缓存，baseline 已跟踪，本 task 又更新了整行内容；它不承载产品行为，只会制造大 diff 和合并噪声。
- 建议：从 Git 移除并加入 `.gitignore`（如项目确实要求保留，应在 AGENTS/README 说明理由）。

### t008_code_f011 - 新 artifact 配置键与 Supervisor/Compose 未打通，部署配置可能静默失效

- 严重度：minor
- 锚点：配置契约一致性（非阻断，t012 部署前需收敛）。
- 位置：`src/backend/cbrowser/api/app.py:103-114`
- 问题：`CBROWSER_ARTIFACTS_DIR` 只在 API 读取；Supervisor 始终用 `--data-root` 下的 `artifacts/` 并据此挂载 `/exchange/uploads|downloads`。一旦按新 blueprint 设置该环境变量，上传会写到未被挂载的目录，下载事件路径也会落在 API ArtifactStore 根之外，`resolve_download_source` 会拒绝全部下载。另 `compose.yaml` 已有的 `ARTIFACT_MAX_BYTES/COUNT/TOTAL_BYTES` 只被旧 `src/backend/artifacts.py` 读取，v2 `ArtifactService` 不读取，t012 若继续使用这些键，配额配置不会生效。
- 建议：把 artifacts root/配额配置作为 API 与 Supervisor 共享的单一部署契约（同一环境变量或显式双向传递），或在 v2 中移除 `CBROWSER_ARTIFACTS_DIR` 并对 `ARTIFACT_MAX_*` 明确弃用；同步 `.env.example` 与 blueprint。

### t008_code_f012 - 删除 Profile 成功后才清理 Artifact，清理失败时返回 500 且无法重试

- 严重度：minor
- 锚点：异常路径状态一致性（非阻断）。
- 位置：`src/backend/cbrowser/api/v1/router.py:339-349`
- 问题：`service.delete_profile()` 已提交删除后，`artifact_service.remove_profile()` 若因 DB busy 或文件系统错误抛异常，接口返回 500；客户端看到「删除失败」，但 Profile 已不存在，重试得到 404，Artifact 行/目录可能残留。
- 建议：把 Artifact 清理放进与 Profile 删除相同的服务事务/顺序中，或将其改为 best-effort 并记录告警后仍返回 204（文件残留由后续清理任务处理）。

## 结论

- 前轮 finding 复核：本轮为 Round 1，无前轮 finding。
- 本轮新发现：12 条（critical 3 / important 3 / minor 6）。
- 未进表的提示：
    - 文件规模：本 task 新增/触及源码均未超过 400 行阈值（最大 `artifact_store.py` 287 行）；测试文件未超过 600 行阈值。
    - 复杂度：`DownloadArtifactForwarder.forward_pending` 约 13（接近 15，建议拆分）；`ArtifactService.ingest_download` 约 10；仅作提示，不单独出 finding。
    - 范围外噪声：`docker_adapter.py`、`agent.py`、`path_validator.py`、`api/v1/router.py` 含少量纯格式化改动，无功能价值，建议后续避免纳入 task diff。
    - 规格一致性：`docs/specs/storage_and_artifacts.md` 的 AC-003 被从「文件选择对话框可选择上传文件」改写为「上传原子写入 Artifact 存储」；原文件选择器行为目前没有承接 task（t014 的 AC 聚焦剪贴板/输入）。请确认这是已批准的计划收缩，否则应登记 pending/后续 task 并保留该行为。
    - 长期文档：`docs/blueprint/security.md` 的宿主目录清单未加入新的 `uploads/` 目录与属主约定，和 f006 一起在 t012 前收敛。
    - 未跟踪的 `docs/tasks/t008_v2_artifacts_automation/review_test.md` 是测试 reviewer 的流程产物，不视为实现交付文件；本次代码范围指纹仍以给定 diff 计算。
- 总体判断：AC-001/AC-002/AC-004 的实现存在可复现的 blocking 缺陷（Supervisor 镜像启动崩溃、完成事件漏送、可执行文件下载被拒、去重误判、DB 失败删用户文件），打勾声明不成立，本 task 当前不可合并。
- 系统性 follow-up：t012 已存在（Docker 正式交付），需纳入 Supervisor `websockets` 依赖、Artifact root/配额环境变量、`uploads` 属主与镜像内真实启动验证；文件选择器行为与规格 AC-003 改写建议登记 `pNNN`（标题：确认 v2 上传文件在容器文件选择器可达，slug：v2_upload_picker_access）或由用户确认放弃。

### AC 复验方式

|AC|类别|证据 / 依赖|
|---|---|---|
|AC-001|re_verified|独立重跑 `tests/integration/test_artifacts_api.py`、`tests/unit/test_artifact_service.py`，并阅读 `artifact_router.py`/`artifact_service.py`/`artifact_store.py`；发现 f003、f004、f005、f006。|
|AC-002|trust_prior|独立重跑 `tests/integration/test_automation_api.py` 与 `test_automation_cdp_flow.py`（API→Supervisor control→UDS echo），但未重跑真实 Chrome loopback CDP，也未用官方 Supervisor 镜像启动；真实部署证据依赖实施方 e2e/d002，且 f001 表明镜像依赖未验证。|
|AC-003|trust_prior|仅重跑 `tests/unit/test_selkies_file_transfers.py` 的 env/entrypoint 断言；未连接真实 Selkies 客户端验证数据通道文件请求被拒，依赖官方 2.1.0 行为与 t007 既有实现。|
|AC-004|trust_prior|仅重跑 `tests/unit/test_download_reconciler.py` 的扫描/去重用例；真实 Agent 重启 e2e 未在本机重跑；f002/f004 说明该 AC 当前不成立。|

coverage = 1 / 4

trust_prior 占比 75% > 30%，建议合并前人工抽查 trust_prior 项，尤其是 AC-002 的真实 Supervisor 镜像启动与 AC-004 的真实 Agent 重启对账。

verdict: FAIL

______________________________________________________________________

## Round 2 (2026-11-02T10:47:29+08:00)

reviewed_scope: 83fb2d9defce7ac5

### 前轮 finding 复核

|finding_id|severity|复核结论|证据|
|---|---|---|---|
|t008_code_f001|critical|已修|`config/docker/supervisor_runtime/requirements.in:6` 增加 `websockets>=17.0`，锁文件 `requirements.txt:22` 为 `websockets==17.4`；独立运行 `docker run --rm --entrypoint python cbrowser-t008-supervisor:e2e -c "import websockets, cbrowser.supervisor.control_server"` 输出 `websockets 17.4`、`control_server import ok`，且 `websockets.unix_connect` 存在。|
|t008_code_f002|critical|已修（原缺陷）|改为持久化 `event_id` 集合（`artifact_forwarder.py:32-95`）。独立复现 `.scratch/t008_review_code_r2/repro_forwarder_r2.py`：乱序 completed 首轮发送 2 条、后续/重启均为 0，`api calls: ['dl_completed_aaaa', 'dl_completed_zzzz']`；503 中断后恢复为 `0 2 0`。修复引入的新 4xx 问题另见 f013。|
|t008_code_f003|important|已修|独立重跑 `.scratch/t008_review_code/repro_exe_download.py`：`setup.exe` 成功入库，`content_type='application/octet-stream'`，源文件已移入 artifact 目录，不再被危险 MIME denylist 拒绝。|
|t008_code_f004|important|已修|独立重跑 `.scratch/t008_review_code/repro_duplicate_download.py`：同名同内容不同路径的第二次下载 `created: True`，列表两条 artifact，`guid2 still on disk: False`；`artifact_repository.py:62-85` 现仅以 `storage_path`（同 `sha256`）比较。|
|t008_code_f005|critical|已修|独立重跑 `.scratch/t008_review_code/repro_db_failure_download.py`：`create_artifact` 抛 `RuntimeError("database is locked")` 后 `source still present: True`，profile 下仅保留原下载文件；`artifact_service.py:183-200` 调 `restore_download` 移回源路径而非删除。|
|t008_code_f006|important|已修（默认部署）|`artifact_store.py:136-146` 发布子目录/文件时 chown 到 runtime UID/GID 并设置 0750/0640，chown 不可用时回退 0755/0644；本机非 root 复验得到 `file 0644 / dir 0755`，root 部署路径为 `0640/0750` 属 UID 1000。标准部署（UID/GID 1000）下容器可读。自定义 `CBROWSER_RUNTIME_UID/GID` 未传递到 ArtifactStore，见结论提示。|
|t008_code_f007|minor|已修|`artifact_router.py:98-109` 声明 `response_class=FileResponse` 与 `application/octet-stream` binary schema；独立加载 `create_app().openapi()` 确认 200 content 为 `application/octet-stream` + `format: binary`。|
|t008_code_f008|minor|已修|`grep -rn "scan_downloads\|iterate_completed_downloads\|_get_auth_service" src/backend tests` 无引用；对应实现已删除。|
|t008_code_f009|minor|已修|`cdp_proxy.py:222-227` 改为 `await asyncio.to_thread(_sha256_file, ...)`，完成事件哈希不再同步占用事件循环；事件监听协程仍串行等待哈希，见结论提示。|
|t008_code_f010|minor|已修|`git diff --stat 63cbd08e... -- src/frontend/tsconfig.tsbuildinfo` 为空，`git status` 无该文件改动；文件仍被基线跟踪，属既有仓库卫生问题，不在本 task diff。|
|t008_code_f011|minor|已修|`CBROWSER_ARTIFACTS_DIR` 只出现在历史 review/note；`app.py:108-130` 读取 `ARTIFACT_MAX_BYTES/COUNT/TOTAL_BYTES`，与 `compose.yaml:20-22`、`.env.example:23-25` 一致。|
|t008_code_f012|minor|已修|`api/v1/router.py:336-349` 在 Profile 删除后对 Artifact 清理做 best-effort，失败仅告警，不再向客户端返回 500。|

### t008_code_f013 - DownloadArtifactForwarder 把 401 等 4xx 永久标记为已处理，认证恢复后完成下载永不重试

- 严重度：important
- 锚点：AC-001「下载经 Agent 事件可见且内容/大小正确」、AC-002「下载捕获恢复，随后真实下载完整入库」；同时违反 `artifact_forwarder.py:28` 类文档声明的「At-least-once delivery」。
- 位置：`src/backend/cbrowser/supervisor/artifact_forwarder.py:161-168`
- 问题：`forward_pending` 对所有 `400 <= status < 500` 的响应都执行 `_mark_processed` 并持久化 event_id。其中 `401` 来自 `require_supervisor` 的 token 不匹配（token 轮换、Supervisor 启动时 token 文件缺失或 API/Supervisor 重启顺序不一致），并非该事件本身的永久语义错误；一旦被标记，后续轮次不再发送，且 Agent 的 `installed_download_keys` 已包含该 completed 事件的 `(path, sha256)`，重启扫描也不会补登，下载文件永久不出现在 Artifacts 列表。独立复现 `.scratch/t008_review_code_r2/repro_forwarder_r2.py` 的 `scenario_401_then_fix`：API 首次返回 401、随后恢复 200，输出 `401 forwarded before_fix/after_fix: 0 0 calls: 1`，事件没有被重试。`422`（如 `suggested_filename` 超过 255 字符或宿主路径超过 4096）同样被永久丢弃，只能等下一次扫描触发才可能补登。
- 建议：把 `401/403/408/429` 视为可重试失败：不写入 `_processed`，跳过该事件/本轮返回；仅对确定性的语义拒绝（如 404、已清洗后的 422）标记 processed。同时在构造 payload 前对 `name` 做与 `safe_filename` 一致的截断，避免合法长文件名触发 422；补充 401→恢复后的重试用例。

### t008_code_f014 - 去重文档仍写 name|storage_path，接口保留未使用的 name 参数

- 严重度：minor
- 锚点：文档与实现一致性（f004 修复后的契约残留）。
- 位置：`docs/blueprint/artifacts.md:34`；`src/backend/cbrowser/adapters/database/artifact_repository.py:64-66`
- 问题：f004 已把下载去重改为仅按 `storage_path` + `sha256`，但长期蓝色文档仍写 `(profile, sha256, name|storage_path)`，且 `find_download_duplicate` 仍保留从未使用的 `name` 参数。后续实现者按文档恢复 name 分支会重新引入 f004 的同名不同路径误判。
- 建议：文档改为 `(profile, sha256, storage_path)`；删除未使用的 `name` 参数及调用点，或明确注释保留原因。

## 结论

- 前轮 finding 复核：f001-f012 均已修，无仍存在或撤回项；f006 在标准 UID/GID 1000 部署下闭合，自定义 runtime UID/GID 未接入 ArtifactStore，见下方提示。
- 本轮新发现：2 条（important 1 / minor 1）。
- 未进表的提示：
    - 文件规模：`tests/e2e/test_browser_runtime_e2e.py` 2607 行（测试源码阈值 1200，本 task 净增 276 行），按降级规则不进 finding 表，建议后续拆分 E2E 场景。
    - 复杂度：radon 对 `DownloadArtifactForwarder.forward_pending` 给出 CC 21（D），`ArtifactService.ingest_download` CC 14；本轮无证据表明复杂度直接导致可观测缺陷，仅作拆分提示。
    - `ArtifactStore` 的 runtime UID/GID 默认硬编码 1000，`create_app` 未传递 `CBROWSER_RUNTIME_UID/GID`；同时 Browser 容器 user 也硬编码 `1000:1000`（`docker_adapter.py:679`），这是既有的配置面不一致，自定义 UID 部署会在 f006 路径上再次 EACCES。建议 t012 统一运行时 UID/GID 契约。
    - `tests/e2e/test_browser_runtime_e2e.py` 的 f006 证据读取的是测试直接写入的 `visible.txt`，不是 API 上传后的文件；代码路径已由 `test_uploaded_file_is_readable_by_runtime_user` 覆盖模式位，但真实 API→容器读取仍建议在 t012 用官方镜像补一次。
    - `docs/specs/storage_and_artifacts.md` 的 AC-003 仍把原「容器文件选择器可选择上传文件」改写为「原子写入 Artifact 存储」；Round 1 已提示，当前无 pending/follow-up 承接。请确认该行为收缩已获批准，否则登记 pending（建议标题：确认 v2 上传文件在容器文件选择器可达，slug：v2_upload_picker_access）。
    - `tests/e2e/test_browser_runtime_e2e.py` 遗留 `.scratch/t008_e2e/t008_*` 目录来自失败运行，最终通过运行的目录已由 finally 清理；未发现产品代码受其影响。
- 总体判断：Round 1 的 critical/important 已消除，但 f013 是本次 event-id 修复引入的新的持久化丢事件路径，本 task 仍不可合并。
- 系统性 follow-up：t012 已存在（Docker 正式交付），需纳入 `CBROWSER_RUNTIME_UID/GID` 与 ArtifactStore 的统一、以及真实 API 上传→容器读取验证；文件选择器行为建议按上条登记 pending。

### AC 复验方式

|AC|类别|证据 / 依赖|
|---|---|---|
|AC-001|re_verified|独立重跑 f003/f004/f005 MIME、去重、DB 失败恢复复现脚本；重跑 `tests/unit/test_artifact_service.py`、`tests/integration/test_artifacts_api.py` 与前端 `ProfileFilesPage`/`router` 测试；检查 `artifact_router.py` 的宿主路径隔离与 `container_path`。|
|AC-002|trust_prior|独立重跑 `tests/integration/test_automation_api.py`、`test_automation_cdp_flow.py`（API→Supervisor control→真实 Agent app→fake Chrome）及 Supervisor 镜像导入检查；真实 Chrome loopback CDP 与真实 Supervisor 全链路依赖实施方 e2e 产物。|
|AC-003|trust_prior|独立重跑 `tests/unit/test_selkies_file_transfers.py` 并检查 `config/docker/stream_runtime/entrypoint.sh` 的 `--file-transfers=none`；未连接真实 Selkies 客户端验证数据通道拒绝，依赖官方 2.1.0 行为与 t007 实现。|
|AC-004|trust_prior|独立重跑 `tests/unit/test_download_reconciler.py`（扫描排除临时文件、校验和、重启不重复）及自建 forwarder 乱序/503 复现；真实 Agent 重启与真实 Chrome 下载对账依赖实施方 e2e 证据（历史失败目录已确认，最终通过运行无遗留目录）。|

coverage = 1 / 4

trust_prior 占比 75% > 30%，建议合并前人工抽查 AC-002 真实 Chrome/Supervisor 链路与 AC-004 真实 Agent 重启对账。

verdict: FAIL

______________________________________________________________________

## Round 3 (2026-11-02T11:08:11+08:00)

reviewed_scope: 80bdf0894cda099f

### 前轮 finding 复核

|finding_id|severity|复核结论|证据|
|---|---|---|---|
|t008_code_f013|important|已修|`artifact_forwarder.py:17` 定义 `RETRYABLE_4XX = {401, 403, 408, 429}`，`:164-168` 命中时不写 `_processed` 并结束本轮；`:144-146` 把转发 name 截断到 255 字符。独立复现 `.scratch/t008_review_code_r3/repro_forwarder_r3.py` 对 401/403/408/429 四种状态首次均 0 条、API 恢复后各转发 1 条并落盘；404 仍永久标记仅尝试 1 次；300 字符文件名实际发送 255 字符且无 422。新增用例 `tests/unit/test_download_reconciler.py:197-241` 断言 `(0, 1)` 与调用序列 `[401, 200]`，触达真实 forwarder 逻辑。|
|t008_code_f014|minor|已修|`docs/blueprint/artifacts.md:34` 已改为 `(profile, sha256, storage_path)`；`artifact_repository.py:60-85` 的 `find_download_duplicate` 仅保留 `profile_id/sha256/storage_path`，唯一调用点 `artifact_service.py:171-174` 同步更新，无残留 `name` 参数引用。|

### 本轮新发现

无。f013/f014 修复未引入新的 critical / important / minor finding。

### 独立验证

- `tests/unit`：469 passed（含新增 retryable 4xx 用例）。
- `tests/integration`：79 passed。
- 前端 `npm test`：16 文件 / 116 用例 passed。
- `tests/e2e/test_browser_runtime_e2e.py -k t008`：1 passed。首次直接运行因未设置 `CBROWSER_RUNTIME_ENGINE_CACHE`（镜像内 `/data/engine-cache` 为空）而 `browser_runner` 退出；显式指向 `.scratch/v2_orchestration/t003_engine_cache`（chromium-146.0.7680.177.3，与 cloakbrowser 0.6.4 linux-arm64 构建一致）后通过，属环境前置条件而非代码回归。
- 独立复现见 `.scratch/t008_review_code_r3/repro_forwarder_r3.py`。

### 未进表的提示

- retryable 4xx 采用「立即结束本轮」策略：单条 429/408 会在本轮阻塞其后所有 profile 的事件，需等下一轮重试，属队头阻塞而非丢事件。当前 API 未启用限流，401/403 为全局认证失败，未观察到可复现数据丢失，仅作提示。
- `name` 截断按字符计（`[:255]`），API 侧 `safe_filename` 再按 255 字节截断并保留扩展名；请求可通过校验，最终落盘名可能短于转发名，不构成缺陷。
- 文件规模/复杂度沿用 Round 2 结论：`artifact_forwarder.py` 189 行、`artifact_service.py` 204 行，未超阈值；`forward_pending` CC 仍偏高，仅提示。
- `docs/pending/todo/p014_v2_upload_picker_access.md` 已登记 Round 1 提示的文件选择器行为收缩，处置闭环由该 pending 承接。

### AC 复验方式

|AC|类别|证据 / 依赖|
|---|---|---|
|AC-001|re_verified|独立重跑单元 469、集成 79、前端 116；上传/下载/去重/DB 失败恢复代码路径与 Round 1/2 复现脚本仍成立。|
|AC-002|trust_prior|独立重跑 `tests/integration/test_automation_cdp_flow.py`（API→Supervisor control WS→真实 Agent app→fake Chrome）与 t008 E2E 真实 Chrome 下载；真实 Chrome 经 Supervisor→UDS→loopback CDP 的双向自动化仍依赖实施方 e2e/d002 证据。|
|AC-003|trust_prior|独立重跑 `tests/unit/test_selkies_file_transfers.py` 并检查 `--file-transfers=none`；未连接真实 Selkies 客户端验证数据通道文件请求被拒，依赖官方 2.1.0 行为与 t007 实现。|
|AC-004|re_verified|独立运行 `tests/e2e/test_browser_runtime_e2e.py -k t008`：真实 Chrome 下载→forwarder→真实 API 入库、Agent 重启扫描补登、再次重启不重复；1 passed。|

coverage = 2 / 4

trust_prior 占比 50% > 30%，建议合并前人工抽查 AC-002 真实 Chrome 自动化全链路与 AC-003 Selkies 数据通道拒绝。

### 结论

- 前轮 finding 复核：f013、f014 均已按 diff 核实消除，无遗留或需撤回项；f001-f012 在 Round 2 已核实，本轮相关文件（artifact_forwarder/artifact_repository/artifact_service/blueprint）改动未回退其修复。
- 本轮新发现：0 条。
- 总体判断：唯一 blocker f013 已修，独立复现与全量单元/集成/前端/E2E 门禁通过，当前无未解决的 critical / important，可合并。

verdict: PASS

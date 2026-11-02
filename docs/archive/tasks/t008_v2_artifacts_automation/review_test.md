# Task review t008（reviewer_focus: 测试）

- task：`t008_v2_artifacts_automation`
- spec：`docs/tasks/t008_v2_artifacts_automation/task.md`
- diff_anchor：`63cbd08e40e5b0448829d06d1faed5851ce973ca`
- target：`git -C '/Users/karson/kar/code/CBrowser_t008' diff 63cbd08e40e5b0448829d06d1faed5851ce973ca`
- round：1
- reviewed_at：2026-11-02T09:54:20+08:00

reviewed_scope: 4306d5704dd859b2

## Findings

### t008_test_f001 - AC-002 的真实下载入库链路没有任何测试贯通

- 严重度：important
- 锚点：AC-002「自动化断开后下载捕获恢复，随后真实下载完整入库」
- 位置：`tests/e2e/test_browser_runtime_e2e.py:1435-1449`、`tests/unit/test_download_reconciler.py:94-135`、`tests/integration/test_artifacts_api.py:157-200`
- 问题：新增 e2e 只把 `manual.csv` 写进宿主 downloads 目录并断言 Agent UDS 返回的 `dl_scan_*` 事件（`tests/e2e/test_browser_runtime_e2e.py:1445-1449`），全程没有启动 Supervisor 或 API，也没有断言 Artifact 记录。Forwarder 单测用 `source.write_bytes` 加 `httpx.MockTransport`（`tests/unit/test_download_reconciler.py:94,121`）；API ingest 集成测试又直接把 fake payload 写进 downloads 目录（`tests/integration/test_artifacts_api.py:157-158`）。没有任何测试让真实 Chrome 下载经过 `DownloadArtifactForwarder` 落入 API DB。若 forwarder 的根路径翻译、Bearer 认证或 API ingest 接线断裂，现有测试仍全绿。这直接违反任务上下文区测试策略「禁止以临时 fake 文件替代实际下载」。
- 建议：补一条 Agent→Supervisor→API 的全链路测试：通过受认证的 automation 端点触发真实下载，轮询 `GET /api/v1/profiles/{id}/artifacts`，断言下载 Artifact 的 name/size/sha256 与内容，并断言源文件已被移动；退而求其次，也要让 `DownloadArtifactForwarder` 对真实 `create_app` 实例发送请求并断言 DB。

### t008_test_f002 - AC-004 只验证到扫描事件，未验证 Artifact 补登

- 严重度：important
- 锚点：AC-004「为缺少完成事件的已完成文件补登 Artifact」
- 位置：`tests/e2e/test_browser_runtime_e2e.py:1445-1454`、`tests/unit/test_artifact_service.py:168-170`、`src/backend/cbrowser/services/artifact_service.py:201`
- 问题：重启 e2e 只断言 Agent 产生了 `dl_scan_*` 事件，没有断言 API 侧出现 Artifact；服务层 `scan_downloads()` 在单元测试里只在完成一次 ingest 后调用并断言结果为 `[]`（`tests/unit/test_artifact_service.py:168-170`），其「扫描到无事件完成文件 → 创建 Artifact」分支从未被测试，且该方法在生产代码中没有调用方（`grep` 仅命中定义）。因此 AC-004 的核心「补登 Artifact」无法被现有测试证明：Supervisor 若未转发、cursor 卡住或 API 拒绝扫描事件，测试仍然通过。
- 建议：为 `scan_downloads()` 增加「存在无完成事件的完成文件 → 返回 created Artifact 且文件被移动」的测试；或在重启 e2e 中轮询 API artifacts 并断言记录。若该方法确实不由生产调用，删除它，不要用死代码测试冒充 AC 覆盖。

### t008_test_f003 - `/exchange/uploads` 挂载与容器内 container_path 可达性无测试

- 严重度：important
- 锚点：AC-001「上传返回……容器内 container_path（/exchange/uploads/...）」；AC-003「文件只能经 Artifact Service 进出 Profile」
- 位置：`src/backend/cbrowser/supervisor/volume_spec.py:19,31`、`tests/unit/test_refactor_behavior_equivalence.py:146-171`、`tests/e2e/test_browser_runtime_e2e.py:302-331`、`tests/integration/test_artifacts_api.py:72-75`
- 问题：`browser_volumes()` 新增 `/exchange/uploads` bind，但 `test_container_spec_browser_volumes_and_labels` 的 `dirs` 只含 `profile/events/exchange/runtime/x11/pulse`，既没有传 `uploads`，也没有断言这条 bind；e2e 辅助容器只挂载 `/exchange/downloads`（`tests/e2e/test_browser_runtime_e2e.py:316`）；API 测试只断言 container_path 字符串。若 uploads 目录没有挂载或挂到错误路径，上传文件在浏览器容器内根本不可达，用户无法取用，而所有测试仍然通过。这个 AC 的核心承诺因此没有被验证。
- 建议：在 volume 测试中把 `uploads` 放入 `dirs` 并断言 `{"bind": "/exchange/uploads", "mode": "rw"}`；e2e 辅助容器同步挂载 uploads，并实际上传后从容器内读取 `/exchange/uploads/{id}/{name}` 校验内容（`docker exec cat` 或 CDP 读取均可）。

### t008_test_f004 - 自动化入口只验证到 echo UDS，未验证真实 Agent/loopback CDP

- 严重度：important
- 锚点：AC-002「外部自动化经独立认证入口到 Supervisor/UDS/loopback CDP，完整双向协议可用」
- 位置：`tests/integration/test_automation_cdp_flow.py:55-76,177-191`、`tests/unit/test_automation_cdp.py:28-51,84-91`
- 问题：两个新增测试的 UDS 上游都是 `_UnixEchoServer`，只把收到的字符串原样回显；它们没有连接真实 Runtime Agent 的 `/cdp`，更没有连接 Chrome loopback CDP。现有的真实 UDS/CDP e2e 直接连 Agent UDS（`tests/e2e/test_browser_runtime_e2e.py:1003`、`test_ac004_download_capture_and_recovery`），绕过了新的 API/Supervisor 自动化入口。若 Supervisor 的 `ws://localhost/cdp` 握手、路径或 Agent 的 `browser_ws_url` 校验不兼容，echo 测试仍会通过，AC 的「完整双向协议」没有真实证据。
- 建议：增加真实 Agent + Chrome 的 e2e：用 Bearer token 连接 `/api/v1/automation/profiles/{id}/cdp`，发送 `Browser.getVersion` 并断言真实响应；至少也应使用真实 `create_agent_app` 配合 fake Chrome upstream，验证 Supervisor→Agent 的握手与消息路径。

### t008_test_f005 - 磁盘空间校验测试只覆盖 free=0，且用宽泛异常断言与 type-ignore

- 严重度：important
- 锚点：AC-001「真实上传校验……磁盘空间」
- 位置：`tests/unit/test_artifact_service.py:118-124`、`src/backend/cbrowser/services/artifact_service.py:41-50`、`src/backend/cbrowser/adapters/filesystem/artifact_store.py:157-161`
- 问题：唯一的磁盘空间测试把 `store.free_bytes` 替换成恒 0（`tests/unit/test_artifact_service.py:122`，并加了 `# type: ignore[method-assign]`），然后只捕获宽泛的 `Exception`（`:123`）。`service.upload` 没有传 `size_hint`，所以实际只证明固定 16 MiB reserve 的拒绝路径，完全没有覆盖「free 大于 reserve 但小于实际上传大小」的场景；如果实现忽略 `size_hint` 或抛出无关异常，测试仍会通过。这与 AC-001 的磁盘空间承诺不匹配，并且 `# type: ignore` 属于测试文件静默类型错误。
- 建议：改用 `monkeypatch.setattr(store, "free_bytes", ...)`，断言具体的 `ArtifactInsufficientStorage`；增加 free 略大于 reserve、上传大小超过 free 的用例，传入 `size_hint`，证明检查使用了实际大小。

### t008_test_f006 - 删除只验证列表为空，未验证磁盘文件/UI 行实际移除

- 严重度：minor
- 锚点：AC-001「UI 可列出/下载/删除获授权文件」
- 位置：`tests/integration/test_artifacts_api.py:89-94`、`src/frontend/src/features/artifacts/ProfileFilesPage.test.tsx:101-114`
- 问题：集成测试删除后只断言 `GET artifacts` 返回空列表；前端测试只断言 mock 的 `client.artifacts.delete` 被调用。没有任何断言检查 `uploads/{artifact_id}` 目录/文件已从磁盘删除，也没有断言 UI 行消失。若 `ArtifactStore.delete` 变成 no-op，DB 记录仍会被删而磁盘泄漏，测试全绿。
- 建议：删除后断言 `env["root"]/<pid>/uploads/<artifact_id>` 不存在；前端测试让 mock 的 list 在 delete 后返回空数组并断言 `artifact-row` 消失。

### t008_test_f007 - 文件 API 的未认证负例只覆盖 upload；automation「missing token」未真正测

- 严重度：minor
- 锚点：AC-001「获授权文件」、AC-002「独立认证入口」
- 位置：`tests/integration/test_artifacts_api.py:202-219`、`tests/integration/test_automation_api.py:62-73`
- 问题：`test_upload_requires_authentication_and_csrf` 只覆盖 upload；list/download/delete 的匿名访问负例没有测试。`test_automation_websocket_rejects_missing_or_foreign_token` 名字包含 missing，但实际只发送了 `Bearer cbat_wrong`，没有测试完全没有 Authorization 头的情况（Supervisor 单测覆盖了 None，但公开 API 层没有）。
- 建议：用 parametrize 覆盖四个 artifacts 端点的 401；在 automation API 测试中补一个不带 Authorization 头的 WebSocket 连接，断言 4401。

### t008_test_f008 - entrypoint Selkies 断言是子串匹配，注释掉配置仍会通过

- 严重度：minor
- 锚点：AC-003「显式关闭（file_transfers=none）」
- 位置：`tests/unit/test_selkies_file_transfers.py:30-35`
- 问题：`assert "export SELKIES_FILE_TRANSFERS=none" in content` 与 `assert "--file-transfers=none" in content` 只做全文子串匹配；把这两行注释成 `# export ...` / `# --file-transfers=none`，测试仍然通过。脚本是 AC-003 的实际生效入口，这种断言不能证明配置没有被禁用。
- 建议：按行 strip 后排除 `#` 开头再断言，或解析 shell 命令参数；至少断言非注释行中同时存在 env export 与 CLI flag。

## 结论

- 前轮 finding 复核：本轮为 Round 1，无前轮 finding。
- 改测方向复核：无。既有测试仅 `src/frontend/src/app/router.test.tsx` 把 placeholder 的 test-id 改为真实页面 test-id，属于占位组件被正式页面替换后的规格同步；没有把断言迁就当前实现。
- 危险模式扫描：未发现 `skip` / `only` / 恒真断言 / 删除或注释断言 / 删除既有测试；placeholder 组件被正式页面替换，router 测试同步更新，属于等价迁移。命中的 `# type: ignore` 与宽泛异常、子串断言分别在 f005、f008 记录。
- 本轮新发现：8 条（5 important、3 minor）。
- 未进表的提示：`src/frontend/tsconfig.tsbuildinfo` 被修改，属构建产物而非测试交付；`test_upload_rejects_bad_name_mime_and_oversize_without_partial_files` 名称含 bad name 但实际未测 bad name；`test_upload_publishes_atomically_*` 只验证最终文件，不验证临时文件/原子发布；`test_automation_cdp_flow.py` 给 supervisor logger 挂载的 `FileHandler` 在删除临时目录后未移除，可能影响同进程后续测试日志；`test_supervisor_cdp_rejects_missing_or_foreign_token` 未覆盖 valid token + profile 非 running 的 4404 分支；`ensure_inside_profile` 缺少 symlink 逃逸用例。以上均为可选补强，不改变本轮 verdict。
- 总体判断：现有单元/集成/前端测试面较广且全部通过，但 AC-002/AC-004 的真实下载入库链路、AC-001 的容器 uploads 路径、AC-002 的真实 loopback CDP 均未被测试触达，AC-001 的磁盘空间测试也不足以证明校验；5 条 important 未解决，判 FAIL。
- 系统性 follow-up：无已登记 tid；若决定把这套全链路夹具跨 task 复用，建议标题 `v2_artifact_cdp_e2e_harness`，但 f001-f004 应在 t008 内补测闭合。

### AC 复验方式

- AC-001：trust_prior。已重跑 `tests/unit/test_artifact_service.py`（18 passed，其中含该文件）、`tests/integration/test_artifacts_api.py`、前端全量（116 passed）；但容器 `/exchange/uploads` 挂载与真实下载事件需要 Docker e2e，未独立复验（见 f003），打勾完整性也不被 f005/f006 支撑。
- AC-002：trust_prior。已重跑 `tests/integration/test_automation_cdp_flow.py` 与 `tests/integration/test_automation_api.py`（11 passed），但上游是 echo UDS，真实 loopback CDP 未复验（f004）；真实下载入库未复验（f001）。
- AC-003：trust_prior。已重跑 `tests/unit/test_selkies_file_transfers.py`，但只验证 env/脚本文本；真实 Selkies 数据通道拒绝未运行，脚本断言本身偏弱（f008）。
- AC-004：trust_prior。已重跑 `tests/unit/test_download_reconciler.py`，但真实 Chrome 重启 e2e 未运行（缺 `CBROWSER_RUNTIME_TEST_IMAGE` 与 engine cache，未启动 Docker），Artifact 补登链路未复验（f002）。

coverage = 0 / 4
建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 2 (2026-11-02T10:45:00+08:00)

reviewed_scope: 83fb2d9defce7ac5

### 前轮 finding 复核

|finding_id|severity|状态|核实证据|
|---|---|---|---|
|t008_test_f001|important|已修|`tests/e2e/test_browser_runtime_e2e.py:1513-1581` 现在用真实容器 Chrome 下载 `download-1.txt`，经 `DownloadArtifactForwarder` 投递到真实 `create_app` API，断言 Artifact 记录 name/kind/sha256 且源文件已移走；本轮独立重跑该 E2E 通过。不再存在「真实下载不入库」的空链路。|
|t008_test_f002|important|已修|`tests/e2e/test_browser_runtime_e2e.py:1583-1616` 在 Agent 重启后扫描 `manual.csv`，经 forwarder 入库并断言 Artifact 列表；`tests/unit/test_download_reconciler.py:21-44` 覆盖「无完成事件文件→scan 事件→再次扫描不重复」，`tests/integration/test_artifacts_api.py:149-200` 覆盖 ingest 去重。本轮 E2E 与单测均通过。|
|t008_test_f003|important|已修|`tests/unit/test_refactor_behavior_equivalence.py:146-180` 将 `uploads` 放入 `dirs` 并断言 `{"bind": "/exchange/uploads", "mode": "rw"}`；`tests/e2e/test_browser_runtime_e2e.py:1515-1522` 挂载 uploads 后从容器内读取 `/exchange/uploads/visible.txt` 成功。本轮单测与 E2E 均通过。残余为分段验证（见「未进表的提示」），不影响关闭该条。|
|t008_test_f004|important|已修|`tests/integration/test_automation_cdp_flow.py:86-201` 用 automation Bearer token 经真实 API→Supervisor→UDS；`:240-306` 用真实 `create_agent_app` + fake Chrome upstream，经 Supervisor control WS 发送 `Browser.getVersion` 并断言真实响应 `Chrome/123.0 E2E`。本轮 integration 全绿。|
|t008_test_f005|important|已修|`tests/unit/test_artifact_service.py:115-133` 改为 `monkeypatch.setattr(store, "free_bytes", lambda: reserve + 10)`，传 `size_hint=20`，断言具体 `ArtifactInsufficientStorage` 且列表为空；若实现忽略 `size_hint` 该用例会失败。本轮单测通过。|
|t008_test_f006|minor|已修|`tests/integration/test_artifacts_api.py:89-95` 删除后断言 `uploads/<artifact_id>` 目录不存在；`src/frontend/src/features/artifacts/ProfileFilesPage.test.tsx:99-120` 删除后让 list 返回空并断言 `artifact-row` 消失。本轮 integration 与前端全量通过。|
|t008_test_f007|minor|已修|`tests/integration/test_artifacts_api.py:223-247` 覆盖 list/download/delete 的 401；`tests/integration/test_automation_api.py:62-74` 循环覆盖无 Authorization 与错误 token，均断言 4401。本轮 integration 通过。|
|t008_test_f008|minor|已修|`tests/unit/test_selkies_file_transfers.py:30-40` 先 `splitlines()` 再排除空行与 `#` 开头行，注释掉 export/flag 会使断言失败；本轮单测通过。|

前轮重要 finding 全部关闭；次要 finding 全部关闭；无撤回。

### 本轮新 Findings

无。未发现新的 critical / important finding；新轮次无 `skip` / `only` / 恒真断言 / 删除或注释断言 / `type: ignore` / 条件跳过 / 用赋值替代真实交互。

### 结论

- 前轮 finding 复核：f001-f008 全部按 diff 与代码/测试本身核实为已修；E2E 与目标套件本轮独立重跑通过，未采信 `note.md` 自述。
- 改测方向复核：无「迁就实现」的改测。`src/frontend/src/app/router.test.tsx` 将 placeholder test-id 换成正式页面 test-id，属于占位组件被替换后的规格同步；`tests/unit/test_runtime_agent_faults.py:84-106` 由同步调用改为 `await`，是生产签名改为 async 后的等价调整；`tests/unit/test_refactor_behavior_equivalence.py` 只新增 uploads bind 断言。
- 危险模式扫描：未发现跳过/独占、删断言、注释断言、`# type: ignore`、`eslint-disable`、`@ts-ignore`、条件跳过弱化断言、`.value =` 替代交互。E2E 中 `assert await forwarder.forward_pending() >= 1` 有后续 Artifact 列表精确断言兜底，不构成掩盖失败。
- 本轮新发现：0 条。
- 未进表的提示：
    1. `tests/e2e/test_browser_runtime_e2e.py:1613-1616` 第三次重启后的 `assert scan_events() == events` 场景偏窄：`manual.csv` 已被 ingest 移入 canonical 子目录，扫描根目录不会再次看到它，因此该断言几乎无法失败；AC-004 的重复扫描抑制已由 `tests/unit/test_download_reconciler.py:21-44` 的二次扫描用例覆盖。可选加固：第三次启动前在 downloads 根目录重新放一个已完成文件，或直接断言 `scan_completed_downloads(existing_keys=...)` 不产生事件。
    2. `tests/e2e/test_browser_runtime_e2e.py:1515-1522` 的 uploads 检查使用手工写入宿主的 `visible.txt`，未走「API 上传 → 容器内读取 `/exchange/uploads/{id}/{name}`」单流；bind 与权限已分别有测试覆盖，单流贯通属于可选补强，不影响当前 AC 判定。
    3. `test_upload_rejects_bad_name_mime_and_oversize_without_partial_files` 名称含 bad name 但仍未测 bad name；`test_upload_publishes_atomically_*` 仍只验证最终文件、不验证临时文件/原子发布（Round 1 已列，未变化）。
    4. `tests/integration/test_automation_cdp_flow.py:92-94` 给 supervisor logger 挂的 `FileHandler` 未移除，可能影响同进程后续测试日志（Round 1 已列，未变化）。
    5. `src/frontend/src/shared/api/client.ts:182-220` 新增 artifacts/automation 客户端方法未被 `client.test.ts` 覆盖；两个页面测试 mock 了 `defaultApiClient`，客户端 URL/方法拼写错误不会被当前测试发现。可选补 `client.test.ts` 的 URL/method 断言，并让上传用例在 upload 后返回新 Artifact 以断言行出现。
- 总体判断：Round 1 的 5 条 important 与 3 条 minor 均已按当前 diff 和本轮重跑结果关闭；无新的 blocking finding；判 PASS。
- 系统性 follow-up：无。当前跨 task 的 E2E 夹具未形成重复缺口；若后续需要把「API automation token → 真实 Agent」单流夹具复用到其他 task，可另立 `v2_artifact_cdp_e2e_harness`，但不阻断本 task。

### AC 复验方式

- AC-001：re_verified。重跑 `tests/unit/test_artifact_service.py`、`tests/integration/test_artifacts_api.py` 与前端全量（116 passed）；E2E 在容器内读取 `/exchange/uploads/visible.txt` 通过；上传文件→容器内 `{id}/{name}` 为分段验证，已在「未进表的提示」注明。
- AC-002：re_verified。重跑 `tests/integration/test_automation_api.py`、`tests/integration/test_automation_cdp_flow.py` 与 E2E 真实下载入库；API automation token 到真实 Agent 的单流组合未单独运行，但各跳均有真实测试并通过。
- AC-003：trust_prior。重跑 `tests/unit/test_selkies_file_transfers.py` 验证 `file_transfers=none` 生效入口；真实 Selkies 数据通道文件请求拒绝需要真实 Selkies 会话，本轮未运行。
- AC-004：re_verified。独立重跑 `tests/e2e/test_browser_runtime_e2e.py::test_t008_download_reconcile_after_agent_restart`（`CBROWSER_RUNTIME_TEST_IMAGE=cbrowser-t008-browser:e2e`，`CBROWSER_RUNTIME_ENGINE_CACHE=/Users/karson/kar/code/CBrowser/.scratch/v2_orchestration/t003_engine_cache`）1 passed；真实容器重启、扫描事件与 API Artifact 断言均通过。

coverage = 3 / 4

verdict: PASS

## Round 3 (2026-11-02T11:01:11+08:00)

reviewed_scope: 80bdf0894cda099f

审查范围：Round 2 后 worktree 中变更的文件经 mtime 核对仅 `artifact_forwarder.py`、`artifact_repository.py`、`artifact_service.py`、`tests/unit/test_download_reconciler.py`、`tests/e2e/test_browser_runtime_e2e.py`、`docs/blueprint/artifacts.md` 与两位 reviewer 报告，与派审说明一致；指纹独立重算为 `80bdf0894cda099f`，与 prompt 一致。

### 前轮 finding 复核

|finding_id|severity|状态|核实证据|
|---|---|---|---|
|t008_test_f001|important|已消除（保持）|独立重跑 `tests/e2e/test_browser_runtime_e2e.py::test_t008_download_reconcile_after_agent_restart` 1 passed（`CBROWSER_RUNTIME_TEST_IMAGE=cbrowser-t008-browser:e2e`）；真实 Chrome 下载经 `DownloadArtifactForwarder` 投递真实 API 的断言仍在 `tests/e2e/test_browser_runtime_e2e.py:1570-1581`，未被本轮改动弱化。|
|t008_test_f002|important|已消除（保持）|同一次 E2E 的重启对账断言仍在 `tests/e2e/test_browser_runtime_e2e.py:1583-1616`，重启补登 `manual.csv` 后断言 Artifact 列表；`tests/unit/test_download_reconciler.py:21-44` 二次扫描不重复用例通过。|
|t008_test_f003|important|已消除（保持）|E2E `:1516-1522` 仍挂载 uploads 并从容器内读取 `/exchange/uploads/visible.txt`，本次重跑通过；volume 单测在 469 passed 中。|
|t008_test_f004|important|已消除（保持）|integration 79 passed，含 `test_automation_token_reaches_agent_uds_through_supervisor` 与 `test_supervisor_cdp_reaches_real_agent_app_and_fake_chrome`（真实 `create_agent_app` + fake Chrome upstream）。|
|t008_test_f005|important|已消除（保持）|`tests/unit/test_artifact_service.py` 全量通过；`monkeypatch.setattr(store, "free_bytes", ...)` + `size_hint` + 具体异常断言仍在 `:115-133`。|
|t008_test_f006|minor|已消除（保持）|`tests/integration/test_artifacts_api.py:89-95` 磁盘目录消失断言与前端删除行断言均在本次重跑的 integration/前端套件内通过。|
|t008_test_f007|minor|已消除（保持）|`tests/integration/test_artifacts_api.py:223-247`、`tests/integration/test_automation_api.py:62-74` 负例通过。|
|t008_test_f008|minor|已消除（保持）|`tests/unit/test_selkies_file_transfers.py` 的排除注释行断言通过。|

本轮重点复核新增的 `tests/unit/test_download_reconciler.py:197-240` `test_forwarder_retries_after_retryable_4xx`：独立运行该文件 5 passed；用例首次返回 401 后断言 `forward_pending()` 返回 0，第二次返回 200 后断言返回 1 且 `calls == [401, 200]`。旧实现对所有 4xx 执行 `_mark_processed`，该断言会得到 `(0, 0) = [401]` 而失败，属有效回归护栏。Mock 仅在 `httpx.MockTransport` 的 HTTP 边界，转发器与事件解析均为真实生产代码，不构成 mock 被测逻辑。

### 本轮新 Findings

#### t008_test_f009 - 新增长文件名截断无测试

- 严重度：minor
- 锚点：AC-001「下载经 Agent 事件可见且内容/大小正确」的边界输入补强，非阻断
- 位置：`src/backend/cbrowser/supervisor/artifact_forwarder.py:144-146`；`tests/unit/test_download_reconciler.py`
- 问题：本轮新增 `name` 的 `[:255]` 截断，用于满足 API `ArtifactDownloadReport.name` 的 `max_length=255`（`src/backend/cbrowser/domain/models.py:201`）。现有测试没有任何超过 255 字符 `suggested_filename` 的用例。若该截断被移除，长文件名下载会在 ingest 处得到 422，而 422 不在 `RETRYABLE_4XX` 中，会被永久标记为已处理，用户侧再无 Artifact，当前套件仍全绿。
- 建议：在 `tests/unit/test_download_reconciler.py` 增加 300 字符 `suggested_filename` 用例，断言 POST payload 的 `name` 长度为 255 且第二次 `forward_pending()` 不重复提交。

### 结论

- 前轮 finding 复核：f001-f008 在 Round 2 已关闭，本轮 diff 未触及对应断言路径；重跑 unit/integration/frontend/E2E 后仍全部保持关闭，无「换形式弱化」。本轮新增的 retryable-4xx 用例有效，且未削弱既有覆盖。
- 改测方向复核：本轮仅向 `tests/unit/test_download_reconciler.py` 追加新用例，未修改任何既有断言；`tests/e2e/test_browser_runtime_e2e.py` 仅随 forwarder 变更重新保存，其下载/重启断言与 Round 2 引用一致（`:1570-1616`）。无「迁就实现」的改测。
- 危险模式扫描：无 `.skip` / `.only` / 恒真断言 / 删或注释断言 / `# type: ignore` / `eslint-disable` / 条件跳过 / 用赋值替代交互。新用例的 HTTP mock 属合法系统边界；`assert first == 0` 有紧随其后的 `calls == [401, 200]` 与成功计数兜底，不构成掩盖失败。
- 本轮新发现：1 条（minor）。
- 未进表的提示：
    1. `RETRYABLE_4XX` 的 403/408/429 未被参数化覆盖，仅 401 有测试；非重试 4xx（如 404/422）应标记 processed 的负例也未覆盖。属可选补强。
    2. 可重试失败后 `forward_pending` 整轮提前 return；「一个 401 事件阻塞同批后续事件」的多事件顺序场景无测试，建议后续按需补一个两事件用例。
    3. `note.md` 未见 Round 2 零 finding 小节；属流程记录缺口，不是测试缺陷，未进 finding 表。
- 总体判断：Round 2 全部 finding 保持关闭；当前 diff 无新增 critical/important；新增长文件名截断的测试缺口为 minor，不阻断。判 PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：re_verified。重跑 `tests/unit` 469 passed、`tests/integration` 79 passed、前端 116 passed，并重跑 t008 E2E；上传/列出/下载/删除、路径穿越与跨 Profile 拒绝由 `tests/integration/test_artifacts_api.py:61-146` 覆盖，前端页面三用例通过。API 上传→容器内 `{id}/{name}` 仍为分段验证。
- AC-002：re_verified。重跑 `tests/integration/test_automation_api.py` 与 `test_automation_cdp_flow.py`（79 passed 内含），以及 E2E 真实 Chrome 下载入库；真实 Chrome loopback CDP 仍由既有 Agent UDS E2E 分段覆盖，非本轮新增证据。
- AC-003：trust_prior。重跑 `tests/unit/test_selkies_file_transfers.py` 验证 `file_transfers=none` 生效入口；真实 Selkies 数据通道文件请求拒绝未运行，依赖 t007/官方 2.1.0 行为。
- AC-004：re_verified。独立重跑 `tests/e2e/test_browser_runtime_e2e.py::test_t008_download_reconcile_after_agent_restart` 1 passed（镜像 `cbrowser-t008-browser:e2e`，缓存 `/Users/karson/kar/code/CBrowser/.scratch/v2_orchestration/t003_engine_cache`），真实容器重启、扫描事件与 Artifact 列表断言均通过。

coverage = 3 / 4

verdict: PASS

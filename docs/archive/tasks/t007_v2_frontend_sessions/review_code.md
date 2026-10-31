# Task review t007（reviewer_focus: 代码）

- task：`t007_v2_frontend_sessions`
- spec：`docs/tasks/t007_v2_frontend_sessions/task.md`
- diff_anchor：`077778fef84f22312e6b18583c547c8b5f418617`
- target：`git -C '/Users/karson/kar/code/CBrowser_t007' diff 077778fef84f22312e6b18583c547c8b5f418617`
- round：1
- reviewed_at：2026-10-31T22:53:36+08:00

reviewed_scope: 33ff6aed2fc94ea3

## Findings

### t007_code_f001 - SSE 断线重连按事件 id 判定补发，跨 API 进程 epoch 时既不补发也不发快照，前端保留陈旧运行状态

- 严重度：important
- 锚点：AC-006「后端状态经 SSE 更新，断线恢复无陈旧控制状态」
- 位置：`src/backend/cbrowser/api/runtime_coordinator.py:62-77`（判定 `target_id >= min(history_ids)` 即视为可续传）
- 问题：事件 id 是进程内自增（`_next_event_id` 从 1 开始），前端只把上一进程收到的 id 作为 `Last-Event-ID` 发回。API 重启后若已发布过至少 1 条事件，history 的 id 为 `1..N`；客户端旧 id（例如 500）满足 `500 >= min([1..N])`，循环只补发 `id > 500` 的事件（0 条），随后 `replayed = True` 跳过初始快照。结果是：重连成功、拿到 keep-alive，但断线期间的状态变化永远不会下发，直到该 Profile 再次产生事件。
  已用 `.scratch/t007_review_code/sse_epoch_probe.py` 直接调用生产 `RuntimeEventBroadcaster` 复现：新 broadcaster 发布 1..3 后以 `last_event_id="500"` 订阅，`snapshot_called=False`，1s 内无任何 chunk。
- 建议：仅当 `min(history_ids) <= target_id <= max(history_ids)` 才走补发，否则按未知 epoch 处理并发送初始快照（或给 id 加服务端 epoch 前缀）。补一条「跨进程 epoch」单测。

### t007_code_f002 - AC-007 已勾，但「检测失效连接并以原 client_tab_id/resume_key 重建」与「ICE 失败阶段」没有真实证据

- 严重度：important
- 锚点：AC-007「页面冻结/恢复…后检测失效连接并以原 client_tab_id/resume_key 重建；运行时未就绪、信令失败、ICE 失败、媒体无帧分别显示阶段与可执行操作」
- 位置：`src/frontend/src/features/browser-session/BrowserSessionView.test.tsx:155-169`、`:137-153`；`tests/e2e/test_frontend_app_e2e.py:717-723`；`tests/e2e/test_frontend_session_e2e.py:383-396`
- 问题：
    1. 唯一声称验证生命周期重连的单测（`BrowserSessionView.test.tsx:155`）派发 `CBROWSER_LIFECYCLE_STALE` 后仅断言 `iframe` 元素存在（`toBeDefined()`，该元素恒存在），没有任何「重新加载/重建」断言；`reconnect` 按钮用例（`:137-153`）同样只断言 `iframe.src` 含 `profileId`（恒真）。
    2. 两个真实 Chrome E2E 的 freeze/resume 都只验证「恢复后仍连接、tab_id 不变、frames 增长」，即重建路径根本没被触发（连接没失效）；AC 要求的「以原 client_tab_id/resume_key 重建」无任何执行证据。
    3. `ice_failed` 阶段只在单测里用 `initialStage="ice_failed"` 属性直出渲染（`BrowserSessionView.test.tsx:80-114`），未验证 `useBrowserSession` 从 `CBROWSER_PC_STATE.iceConnectionState === "failed"` 的真实检测；真实栈 E2E 只覆盖 runtime_not_ready / signaling_failed / media_no_frames。
- 建议：补一条可触达生产路径的用例（断开 iframe 内 WebSocket/PeerConnection 或 CDP 使连接进入 `failed` 后 resume，断言 iframe 以同一 `client_tab_id` 重建且 HELLO 带原 `resume_key`），并让 ICE 失败经由真实状态消息而非 `initialStage` 注入；否则把 AC-007 的这两项改回未勾。

### t007_code_f003 - Supervisor stop 协调路径吞掉状态查询异常，且「双方都无实例」分支必然抛 StaleInstanceError

- 严重度：minor
- 锚点：行为缺陷（降级依据：见「问题」中的触发条件极窄）
- 位置：`src/backend/cbrowser/api/runtime_coordinator.py:339-360`（`except Exception: pass` 于 :350-351；`report_observed_state(profile_id, "unknown", "stopped")` 于 :355-357）
- 问题：desired=stopped 且 DB 无 `runtime_instance_id` 时，向 Supervisor 查实例的 GET 异常被静默丢弃，随后按「Supervisor 也没有实例」写 `observed_state=stopped`。但 `ProfileService.report_observed_state` → 仓储侧只有 `m.runtime_instance_id == "unknown"` 才更新（`src/backend/cbrowser/adapters/database/repository.py:538-539`），实际必然返回 `None` → 抛 `StaleInstanceError`；该异常从 `reconcile_profile_now` 逃逸，`_reconcile_profile_loop` 只捕获 `CancelledError`（:410），任务以未取回的异常结束，重试链断掉、错误也不上报。当前状态机下该分支几乎不可达（exit 事件会把 `observed_state` 置 stopped 并清空实例），故按 minor 记录，但一旦可达即为静默不收敛。
- 建议：区分「Supervisor 不可达」与「Supervisor 无实例」，前者写 `last_error` 返回 False 以继续退避重试；后者不要用假实例 id 调 `report_observed_state`，改用能表达「无实例」的路径并补单测。

### t007_code_f004 - 新增 i18n 键未被使用，会话/页头/表单仍硬编码中英文；与 `docs/blueprint/frontend.md`「文案全部经 t()」不符

- 严重度：minor
- 锚点：文档与实现不一致（`docs/blueprint/frontend.md` 第 1 节末条）
- 位置：`src/frontend/src/i18n.tsx:260-267`、`:499-506`（`audioStatus*`/`audioMute`/`audioUnmute` 新增键，全仓库无 `t("audio…")` 引用）；`src/frontend/src/features/browser-session/SessionDiagnostics.tsx:13-33`、`:175`、`:185`；`src/frontend/src/features/browser-session/BrowserSessionView.tsx:77-81`、`:94`；`src/frontend/src/app/AppLayout.tsx:152`、`:166`、`:234`、`:252`；`src/frontend/src/features/profiles/ProfileDetailPage.tsx:148`、`:224`、`:238`、`:264`
- 问题：语言切换后这些文案不随 locale 变化（固定「中文 (English)」双语串），新增的 audio i18n 键为死键；蓝图文档声称文案全部走 `t()`，与实现不符。E2E 固定 `zh-CN` 故未暴露。
- 建议：把这些文案改为 `t()`（audio 键已备好），或删除未用键并把 blueprint 的表述改为「主要文案经 i18n」。

### t007_code_f005 - `BrowserSessionMount` 用 `import.meta.glob` 动态解析并保留 placeholder 兜底，属并行 lane 遗留的投机间接层

- 严重度：minor
- 锚点：架构/可维护性（薄包装 + 被拒遗产）
- 位置：`src/frontend/src/shared/components/BrowserSessionMount.tsx:9-50`、`:70-82`
- 问题：`features/browser-session/BrowserSessionView.tsx` 已存在且被唯一引用，glob 查找 + `React.lazy` + 「模块未交付则显示占位」的注释与 fallback 都是 lane 并行期的脚手架；现在运行时若动态导入失败会静默退化成「Session module placeholder」，反而掩盖真实错误，并让 `noUnused`/打包分析拿不到静态依赖。
- 建议：改为静态 `import { BrowserSessionView }` 直接渲染，删除 glob 与 placeholder 分支。

### t007_code_f006 - 宿主 `message` 监听未校验 `event.origin`/`event.source`，任意持有该窗口引用的页面可伪造连接阶段并强制重连

- 严重度：minor
- 锚点：行为/安全（低影响）
- 位置：`src/frontend/src/features/browser-session/useBrowserSession.ts:154-191`（`CBROWSER_PC_STATE`/`CBROWSER_WS_CLOSE`/`CBROWSER_LIFECYCLE_STALE` 全部无条件采信）；iframe 侧以 `"*"` 发送：`src/frontend/src/features/browser-session/adapter.ts:169`、`:427`
- 问题：任何能把本页作为子窗口打开（保留 opener 引用）的页面，可 postMessage `{type:"CBROWSER_PC_STATE", connectionState:"connected"}` 把界面切到 media_waiting/connected，或发 `CBROWSER_LIFECYCLE_STALE` 反复强制重连；不涉及数据泄露，但属于外部输入直接驱动 UI 状态。
- 建议：只接受 `event.source === iframeRef.current?.contentWindow` 且 `event.origin === window.location.origin`；adapter 侧改用具体 origin 作为 targetOrigin。

### t007_code_f007 - 在子页面点击侧边栏 Profile 只改当前路由的 query，不切回会话页，页头目标与页面主体不一致

- 严重度：minor
- 锚点：行为缺陷（导航一致性；AC-001 未明确覆盖）
- 位置：`src/frontend/src/app/AppLayout.tsx:42-45`（`setSearchParams({ profileId: id })`）；路由 `src/frontend/src/app/router.tsx:37-40`
- 问题：在 `/profiles/:id`、`/settings` 等子路由点击侧边栏条目，URL 变成 `/profiles/<旧 id>?profileId=<新 id>`：页面仍渲染旧的编辑表单，而页头 `activeProfile`/Launch/Stop 已切到新 id，用户看不到所选 Profile 的会话页，需要再点一次「Back to Session」。E2E 均在 `"/"` 上点侧边栏，未覆盖此路径。
- 建议：`handleSelectProfile` 改为 `navigate({ pathname: "/", search: ?profileId= })`（会话页之外统一跳到 `/`），或在子路由上隐藏/改写选择行为。

### t007_code_f008 - AC-002「刷新…保留 resume_key」与官方 Selkies 客户端语义不符，需改 spec 措辞（非实现缺陷）

- 严重度：minor
- 锚点：spec 描述与实现合理冲突（处置为改 spec，不计 FAIL）
- 位置：`docs/tasks/t007_v2_frontend_sessions/task.md` AC-002；官方客户端 `src/frontend/public/selkies/src/selkies-core.js`（`He` 构造器 `this.resume_key=ze()`，每次实例化重新随机）；证据测试 `tests/e2e/test_frontend_app_e2e.py:483-486`（刷新只断言 `tab_id` 不变，`resume_key` 仅断言 HELLO 中存在）
- 问题：`resume_key` 由官方客户端按实例生成，页面刷新必然产生新的 resume_key；能保留的是 `client_tab_id`（sessionStorage）与同一连接内重连的 resume_key。实现若强行持久化 resume_key 就必须改写官方 HELLO，与同一 AC 的「不重写官方 HELLO」冲突。
- 建议：AC-002 改为「刷新保留 client_tab_id 身份，连接内重连保留 resume_key」，测试补一条同页断线重连的 `RESUMED` 断言。

## 结论

- 前轮 finding 复核：Round 1，无前轮。
- 本轮新发现：8 条（important 2、minor 6）。
- 未进表的提示：
    - 文件过大（含本 task 净增）：`src/backend/cbrowser/stream_agent/agent.py` 1153（+13）、`src/backend/cbrowser/supervisor/docker_adapter.py` 1098（+55）、`src/backend/cbrowser/api/v1/router.py` 697（+187）、`src/frontend/src/features/browser-session/adapter.ts` 552（新建）、`src/backend/cbrowser/api/runtime_coordinator.py` 415（新建）。均为协议/适配一体文件或既有大文件延展，本次不单独出表。
    - 圈复杂度：`RuntimeCoordinator.reconcile_profile_now` 约 25（新建，start/stop 双分支 + 多层异常处理），建议拆 start/stop 两个私有方法。
    - `asyncio.create_task(coord.publish_profile_change(...))` 在 `src/backend/cbrowser/api/v1/router.py:496/537/584/636/693` 五处均未保存引用，任务可能被 GC 或异常无人取回（`publish` 内部吞异常，暂无观测故障）。
    - 交付文档 `docs/blueprint/frontend.md`、`docs/specs/profile_management.md` 仍为未跟踪文件（未 `git add -N`），本次经文件系统读取复核；指纹已覆盖，不影响本轮结论，但流程上应由实施侧补 intent-to-add。
    - `ruff` 门禁 r3 报 2 文件未格式化；本次以只读方式复跑 `ruff format --check` 确认 `tests/e2e/test_frontend_display_apply_e2e.py`、`tests/unit/test_supervisor_display_config.py` 现已格式化，仅涉测试文件排版，不构成门禁回归。
    - 范围外观察：`config/docker/Dockerfile` 直接 `COPY src/frontend/dist/`，而 `dist/selkies` 依赖先手工运行 `scripts/vendor_selkies_web.py`（`npm run build` 不包含该步），正式交付构建无机械保障——归 t012。另 `dirs["runtime"]`（含 `selkies_tokens.json` 0600 与既有 `agent_secret.txt` 0644）被 rw 挂载进 Browser 容器（`docker_adapter.py:671-672`），master token 因此落在不可信沙箱可读目录，建议后续安全任务收敛（browser 容器 egress 仅放行 proxy，故当前不可直达 Selkies）。`r3` 的 `runtime_e2e` 失败项为 t003 pulse 用例（与本 task 无关），`r3_rerun/` 复跑 1 passed ×2。
- 总体判断：SSE 断线恢复协议在 API 重启后会产生陈旧控制状态，且 AC-007 的「失效连接重建 / ICE 失败」勾选缺乏真实证据；两项 important 未解决前不能 PASS。
- 系统性 follow-up：无新增（SSE epoch 修复属本 task；构建接线归 t012；运行目录凭据挂载建议登记 pending）。

### AC 复验方式

- AC-001：`re_verified`。复核 `src/frontend/src/app/router.test.tsx:163` 及 `tests/e2e/test_frontend_app_e2e.py:285` 断言内容，并重跑 Vitest（13 文件 93 passed）。
- AC-002：`trust_prior`。真实 Chrome 双标签/复制页结论依赖 r3 `frontend_e2e`（21 passed）日志；已逐行核对 `tests/e2e/test_frontend_app_e2e.py:420-545` 的断言（DOM/storage/WS 全量搜 token、复制页 tab 重映射、原页不踢）。
- AC-003：`re_verified`。Vitest `BrowserSessionView.test.tsx:25`（卸载不发 stop/desired-state）实跑通过；容器仍运行的结论依赖 r3 E2E 日志。
- AC-004：`trust_prior`。依赖 r3 `frontend_e2e`/`stream_e2e` 中 `test_ac004_visibility_stop_start_through_full_app`、`test_display_profile_size_requires_explicit_apply` 的结果；已核对断言（consumer 2→1→0、前台 FPS 下限、外部 resize 不改远端、应用后 1600×900）。
- AC-005：`trust_prior`。依赖 r3 `test_ac005_product_mute_is_independent_per_page`（STOP_AUDIO 后 A 字节不增长、B 继续）、`test_ac005_remote_tab_switch...`、音频故障诊断用例；已核对 `audio_status.ts` 判定逻辑。
- AC-006：`re_verified`。重跑 `tests/integration/test_api_sse_events.py`、`tests/integration/test_runtime_coordinator_integration.py`（7 passed）与 Vitest SSE/查询用例；并据此发现 f001。
- AC-007：`trust_prior`。依赖 r3 `test_ac007_freeze_resume_and_diagnostic_stages`；正因为逐行核对发现重建与 ICE 失败无真实断言，出 f002。
- AC-008：`trust_prior`。依赖 r3 `stream_e2e`（19 passed）中 `test_e2e_ac008_dual_mode_disabled_negative_and_positive`（真实 Stream 镜像 403）与 `tests/unit/test_stream_selkies_tokens.py:277` 对 entrypoint 指令的断言。
- AC-009：`re_verified`。重跑 coordinator 单测 8 例 + 集成 3 例（start/stop RPC、Supervisor 不可达保留意愿并恢复）通过；真实 Supervisor E2E 依赖 r3 `frontend_e2e`/`sup_*` 日志。
- AC-010：`trust_prior`。依赖 r3 `stream_e2e` 的真实镜像用例（错误/缺失 token Close 4001、Agent 代注入）与 `frontend_e2e` 的 DOM/storage/网络/WS 全量搜 master/controller token；「日志不含 token」仅由 `_sanitize_packet` 代码核对，无断言。

coverage = 4 / 10
建议合并前人工抽查 trust_prior 项（真实 Chrome 双标签复制页、可见性 STOP/START、独立静音字节、Stream token 拒绝）。

verdict: FAIL

## Round 2 (2026-11-01T01:28:28+08:00)

reviewed_scope: 288d20330554968b

### 前轮 finding 复核（以当前 diff/代码为准，不采信处置表自述）

- `t007_code_f001`（important，SSE epoch）：已消除。事件 id 改为 `<epoch>:<seq>`（`src/backend/cbrowser/api/runtime_coordinator.py:26,33,78-97`），仅当 epoch 相同且 `target_id` 落在历史窗口内才补发，否则发完整快照（`:99-110`）。本轮本地复跑 `tests/integration/test_sse_epoch_integration.py`、`tests/integration/test_api_sse_events.py` 共 3 passed，其中 epoch 用例真实重启 uvicorn 进程并断言新 epoch 快照（`test_sse_epoch_integration.py:121-156`）。
- `t007_code_f002`（important，AC-007 失效检测/重建）：已消除。`useBrowserSession.ts:182-209` 用真实 `CBROWSER_PC_STATE` 的 `failed`/`disconnected`（5s 宽限）迁移 `ice_failed`；`:210-236` WS 异常关闭先给官方客户端 5s resume，再按 `__getWebRTCStats().connected` 决定重建；`:237-242,355-381` 处理 stale/resume/pageshow。单测断言真实 `_k` 增长与 `data-stage` 迁移（`BrowserSessionView.test.tsx:163-276`）；真实栈有 `test_frontend_ice_failure_e2e.py:144-188`（暂停 coturn 进入 `ice_failed`）与 `test_frontend_app_e2e.py:830-861`（`pc.close()`+resume → iframe 重建，新 HELLO 同 `client_tab_id`、新 `resume_key`）。lane 证据 `fix_fe/t007_fix_fe/e2e_ice7.log`（1 passed）、`e2e_app_ac007_rerun3.log`（1 passed）。
- `t007_code_f003`（minor，stop 路径）：已消除。`runtime_coordinator.py:380-430` 区分 Supervisor 不可达（TransportError → `last_error` + 退避重试）与无实例（status 200 且 `runtime_instance_id` 为空 → 直接收敛），不再用假实例 id 调 `report_observed_state`；`:434-446` 循环捕获意外异常并上报。本轮复跑 `tests/unit/test_runtime_coordinator_stop_paths.py` 5 passed。
- `t007_code_f004`（minor，i18n）：主体已修，**修不彻底**（不阻断）。会话阶段/诊断/页头/表单改用 `t()`（`BrowserSessionView.tsx:80,84`、`SessionDiagnostics.tsx:15-51`、`AppLayout.tsx:126-168`）。残留硬编码：`SettingsPage.tsx:25,77-78,83-94`、`ProfileNewPage.tsx:77,90,131`、`ProfileDetailPage.tsx:230` 的 placeholder，以及 `useBrowserSession.ts:135-136,143-144,195,201,234` 的阶段错误文案；`docs/blueprint/frontend.md:11`「文案全部经 `t()`」因此仍略强于实现。
- `t007_code_f005`（minor，动态挂载）：已消除。`shared/components/BrowserSessionMount.tsx:1-22` 静态 import `BrowserSessionView`，glob/lazy/placeholder 分支已删除。
- `t007_code_f006`（minor，postMessage 校验）：已消除。宿主校验 `event.source === iframe.contentWindow` 且 `event.origin === window.location.origin`（`useBrowserSession.ts:164-170`）；iframe 侧改用具体 origin（`adapter.ts:168-177,427-435,540-543`）。伪造 source/origin 单测通过（`BrowserSessionView.test.tsx:278-304`）。
- `t007_code_f007`（minor，侧边栏导航）：已消除。`AppLayout.tsx:42-45` 统一 `navigate("/?profileId=")`；`router.test.tsx:196-216` 断言子路由点击后落到会话页。
- `t007_code_f008`（minor，spec 措辞）：已按约定处置。`task.md:59-60` 记录 AC-002/AC-007 按官方 `resume_key` 语义改写；drift 与上下文区记录一致，不重复计 finding。
- `t007_master_sec001`（important，token 目录隔离）：**生产侧已消除**。凭证写到 `runtime/.secrets/<profile>`（`path_validator.py:126-137`、`core.py:498-503`），Stream 以单文件 0600 只读挂载并校验权限（`docker_adapter.py:808-818,839-861`），Browser 容器不挂载该目录。本轮复跑 `tests/unit/test_supervisor_selkies_token_isolation.py`、`test_supervisor_selkies_tokens.py`、`test_stream_selkies_tokens.py`（含 browser 挂载不含 secret dir、`validate_secret_source` 拒绝 runtime 目录文件）全部通过。**但**生产路径变更后，测试夹具仍按旧路径读取（`tests/fixtures/frontend_app_probe/harness.py:111-113` 使 `test_frontend_app_e2e.py:455` 抛 `FileNotFoundError`）；该测试层缺口已由 test reviewer 报为 `t007_test_f009`，按职责不在本报告重复出 finding，但它使本轮 AC-002/AC-010 的 app E2E 证据无法在当前树复现。

### Findings

#### t007_code_f009 - SSE 推送在无缓存条目时伪造 `config_version: 1`，可能误显示“设置待应用/需重启”

- 严重度：minor
- 锚点：行为缺陷（AC-004「显示尺寸…由 Profile 配置控制…设置变更须明确应用」的控制态展示失真，可导致不必要的重启）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:188-203`（`if (!old)` 分支 `config_version: 1`）；消费点 `src/frontend/src/app/AppLayout.tsx:76-81`、`src/frontend/src/features/profiles/ProfileDetailPage.tsx:46-50`
- 问题：SSE 事件载荷不含 `config_version`，但 `useProfileEventsSync` 在缓存中无该 Profile 的 runtime 时直接合成 `config_version: 1`。SSE 全局广播且 `setQueryData` 对所有 `profile_id` 生效，因此另一标签页/尚未打开该 Profile 的页面会先写入伪造版本；随后打开该 Profile 时 `useProfileRuntimeQuery` 命中“新鲜”缓存（`staleTime: 5000`）而不立即重取，`displayPending = runtime.config_version !== profile.current_config_version` 对 `current_config_version > 1` 的 Profile 误判为待应用，页头出现“设置已保存，重启后生效”与“应用并重启”按钮（最多持续到下次重取/失效）。不会丢数据，但会误导用户重启正在运行的实例。
- 建议：事件中无版本信息时不要伪造；要么不写入缓存而改为 `invalidateQueries(profileKeys.runtime(id))`，要么在缺少缓存时触发一次 `getRuntime`，避免用常量 1 充当真实版本。

#### t007_code_f010 - AC-007 明确列出的 bfcache `pageshow(persisted)` 触发路径没有任何测试覆盖

- 严重度：minor
- 锚点：AC-007「页面冻结/恢复（Page Lifecycle freeze/resume、bfcache pageshow）后检测失效连接并以原 client_tab_id 重建」
- 位置：实现 `src/frontend/src/features/browser-session/useBrowserSession.ts:372-375`、`src/frontend/src/features/browser-session/adapter.ts:551-553`；现有测试 `BrowserSessionView.test.tsx:264-276`（派发 `CBROWSER_LIFECYCLE_STALE`）、`tests/e2e/test_frontend_app_e2e.py:783-861`（CDP freeze/active、手动 `resume` 事件）
- 问题：宿主与 iframe 的 `pageshow` + `event.persisted` 监听是本 AC 点名的一半触发条件，但仓库中没有用例派发 `PageTransitionEvent("pageshow", {persisted:true})`，也没有真实的 bfcache 往返。该 wiring 若写错（例如漏 `persisted` 判断或漏监听）不会被任何自动化发现。因它复用的正是已被单测/E2E 覆盖的 `handleHostReactivate` → `reconnect()` 路径，故按“覆盖可更广”记 minor，不阻断。
- 建议：补一条单测派发 `pageshow{persisted:true}`（连接失效时断言 `_k` 增长、健康时不断言重建），或补 `window.history` 往返的真实 bfcache 用例。

### 结论

- 前轮 finding 复核：f001/f002/f003/f005/f006/f007/f008 与 master_sec001 生产侧已消除；f004 修不彻底（仅 minor 残留文案）；撤回：无。前轮两个 blocker（f001、f002）均以当前代码与可复跑测试核实消除，不采信处置表自述。
- 本轮新发现：2 条（minor 2）。
- 未进表的提示：
  - 测试层跨轮缺口（非本报告职责，已由 `t007_test_f009` 记录）：`tests/fixtures/frontend_app_probe/harness.py:111-113` 仍读 sec001 之前的 token 路径，导致 `test_frontend_app_e2e.py:455` 起的 token 泄漏扫描与官方 HELLO 断言在当前树不可运行；修复后须重跑 `test_frontend_app_e2e.py`。
  - `_sanitize_packet`（`src/backend/cbrowser/stream_agent/agent.py:90-110`）生产代码无调用点，仅测试引用；本轮为它新增 `master_token/controller_token/client_token` 键不改变运行时行为。AC-010「日志不含 token」实际成立的原因是转发路径从不记录 HELLO，而不是该函数消毒。
  - `SessionStage` 的 `connecting_ice`（`types.ts:15`）与 `onSessionError`（`types.ts:59`）无生产使用；属 dead 声明，不阻断。
  - 文件过大（本 task 净增，不进 finding）：`src/frontend/src/features/browser-session/adapter.ts` 555（新建）、`src/backend/cbrowser/api/runtime_coordinator.py` 481（新建）、`src/frontend/src/features/browser-session/useBrowserSession.ts` 406（新建）、`src/backend/cbrowser/api/v1/router.py` 697（+186）；均为协议/适配一体或既有大文件延展。`runtime_coordinator.reconcile_profile_now` 圈复杂度仍约 10-12，建议后续拆 start/stop 分区，不阻断。
  - 范围外观察保持 Round 1 结论：`dist/selkies` 的 vendor 步骤未并入 `npm run build`，归 t012。
- AC 复验方式：
  - AC-001：`trust_prior`。核心证据是真实双标签 E2E `test_frontend_app_e2e.py:347-373`（A 页切换 B 后 B 页帧数增长、tab_id 不变）；本轮仅复跑 Vitest 路由/独立实例用例（`npm test --prefix src/frontend`：13 文件 102 passed）。
  - AC-002：`trust_prior`。依赖 `test_frontend_app_e2e.py:435-560`、`test_frontend_session_e2e.py:125-227` 与 lane `e2e_all.log`（16 passed）；其中 app E2E 因 `t007_test_f009` 在当前树不可复跑。noopener 单测已随 Vitest 重跑通过。
  - AC-003：`re_verified`。复跑 `BrowserSessionView.test.tsx:60-76`（卸载不发 stop/desired-state，生产 hook 路径）通过；容器仍运行由 `test_frontend_session_e2e.py:204-220` 支撑（`trust_prior`）。
  - AC-004：`trust_prior`。依赖 lane `test_frontend_media_e2e.py`（STOP/START_VIDEO、consumer 2→1→0、前台 FPS、静音字节）与 `test_frontend_display_apply_e2e.py`（外部 resize 不改远端、应用后新尺寸）结果。
  - AC-005：`trust_prior`。依赖同一 media/session E2E 的真实输入值与独立静音字节/`STOP_AUDIO` 断言；本轮只核对了 `audio_status.ts` 判定逻辑。
  - AC-006：`re_verified`。本轮重跑 `tests/integration/test_sse_epoch_integration.py` + `test_api_sse_events.py`（3 passed）、coordinator 单测/SSE epoch 单测，并核对生成类型与导出 OpenAPI（`test_exported_openapi_schema_matches_live_app` 1 passed）。
  - AC-007：`re_verified`（检测/重建逻辑）+ `trust_prior`（真实栈时序）。复跑 `BrowserSessionView.test.tsx:174-276` 覆盖 `PC_STATE failed`、5s 宽限、WS_CLOSE/stale 重建；真实 freeze/ICE 依赖 `e2e_ice7.log`、`e2e_app_ac007_rerun3.log`。bfcache 见 f010。
  - AC-008：`trust_prior`。真实 Stream 镜像的 dual-mode 403 用例见 `fix_be/e2e_stream_selkies_tokens.log`（4 passed）；entrypoint 指令断言随本轮单测重跑通过。
  - AC-009：`re_verified`（协调逻辑）+ `trust_prior`（真实 Supervisor）。本轮复跑 coordinator 单测（含 unreachable/无实例/停止路径）与 `tests/integration/test_runtime_coordinator_integration.py`；真实启停/断连收敛依赖 `test_frontend_app_e2e.py:961-1040`。
  - AC-010：`trust_prior`。真实镜像用例（错误/缺失 token Close 4001、Agent 代注入、各容器日志扫 master token）见 `fix_be` 日志；token 生成/目录隔离单测本轮重跑通过；app E2E 的 DOM/网络/WS token 扫描因 `t007_test_f009` 当前不可运行。

  coverage = 4 / 10
  建议合并前人工抽查 trust_prior 项（真实双标签切换、可见性 STOP/START 与前台帧率、音频字节/独立静音、真实 Supervisor 启停收敛、Stream token 拒绝与日志扫描），并在修复 `t007_test_f009` 后重跑 `test_frontend_app_e2e.py`。
- 总体判断：代码层无未解决 critical/important；两个 Round 1 blocker 已消除，本轮仅新增 2 条 minor（缓存伪版本、bfcache 覆盖缺口）。AC-002/AC-010 的前端 E2E 证据因测试夹具路径过期（`t007_test_f009`，测试层）暂时不可复现，合并前需修复复跑，但不构成代码层 FAIL。
- 系统性 follow-up：无新增。已开放 `p005`（t006 遗留 minor）与本轮 test reviewer 的 `t007_test_f009`（本 task 内修）。

verdict: PASS

## Round 3 (2026-11-01T03:18:00+08:00)

reviewed_scope: d89125a5fbd33eae

### Findings

无新增 finding。四视角（规格合规 / 正确性 / 安全 / 契约·性能·可维护）对本轮增量逐项扫描未发现可锚定的 critical / important / minor 新缺陷。

### 前轮 finding 复核（以当前 diff/代码为准，不采信处置表自述）

- `t007_code_f009`（minor，SSE 伪造 runtime）：**已消除**。`useProfilesQuery.ts:186-203` 在无缓存条目时返回 `undefined`（不再合成 `config_version: 1`），`:211` 对每个事件 `invalidateQueries(profileKeys.runtime(...))` 触发真实重取；`useProfilesQuery.test.tsx:174-191` 直接断言 `getQueryData(runtime("uncached"))` 为 `undefined`。本轮重跑 `NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend`：13 文件 / 104 passed；主控 RED/GREEN 日志（`.scratch/t007_master/red|green_sse_no_fabricated_runtime.log`）与代码一致。
- `t007_code_f010`（minor，bfcache 覆盖）：**已消除**。生产监听 `useBrowserSession.ts:369-390`（`pageshow` 仅 `event.persisted` 时检查，失效才 `reconnect`）；新增用例 `BrowserSessionView.test.tsx:278-306` 分三种状态断言 `_k=0/_k=1`。变异日志（`.scratch/t007_master/bfcache_pageshow_mutant.log`）显示去掉 `persisted` 判断后健康连接分支失败，说明该断言能捕获回归，不是恒真。
- `t007_test_f009`（test，important，夹具 token 路径）：**已修且静态一致**。`tests/fixtures/frontend_app_probe/harness.py:111-115` 改读 `<data_dir>/runtime/.secrets/<profile>/selkies_tokens.json`，与生产 `path_validator.py:126-138`（`get_secret_dir`）及 `core.py:498-503` 写入路径一致，测试拓扑把同一 `data_dir` 挂给 Supervisor（`frontend_probe/harness.py:260-303`）。**但修复后未执行**：`.scratch/project_gates/` 目前只有 r1–r3，无 r4 日志，故 AC-002/AC-010 的 app E2E 仍是未跑证据（见结论）。
- `t007_test_f010`（test，minor，静音空真断言）：**已修**。`test_frontend_app_e2e.py:686-707` 与 `test_frontend_session_e2e.py:301-311` 先要求 `nodes.length > 0` 再比较 `muted`；静态核对其选择器与官方客户端产品路径一致（`public/selkies/src/selkies-core.js` 的 `pipelineControl` audio 分支对 `b.muted=!e`，`b` 为 `video#stream` 元素）。
- `t007_code_f001`–`f008`、`t007_master_sec001`：以当前代码复核仍为已消除，本轮无回退。重点复跑：`tests/unit/test_api_runtime_coordinator.py`、`test_runtime_coordinator_stop_paths.py`、`test_runtime_coordinator_background_tasks.py`、`test_supervisor_selkies_tokens.py`、`test_supervisor_selkies_token_isolation.py`、`test_stream_selkies_tokens.py`（30 passed）与 `tests/integration/test_api_sse_events.py`、`test_sse_epoch_integration.py`、`test_runtime_coordinator_integration.py`（8 passed）。SSE epoch、stop 路径区分不可达/无实例、无伪造 runtime 均成立。
- 遗留登记复核：`p007` 与 f004 残留（设置页/新建页/阶段错误文案）相符；`p006`/`p008`/`p009`/`p010` 描述与当前代码事实一致（Browser 挂载 `runtime` 目录含 0644 `agent_secret.txt`、Stream Agent resume、多 viewer 固定 sleep、vendor 未并入 `npm run build`）。处置合理，不另出 finding。

### 结论

- 前轮 finding 复核：f001–f010 与 master_sec001 均已消除；`t007_test_f009` / `t007_test_f010` 代码侧修复正确；无撤回。p006–p010 与 p007（f004 残留）处置合理。
- 本轮新发现：0 条。
- 未进表的提示：
  - **门禁缺口（影响证据时效，非代码缺陷）**：Round 2 修复后未生成 r4 门禁，`frontend_e2e` 尚未在 `t007_test_f009` 修复与 sec001 后的拓扑上跑过；合并前必须重跑 `tests/e2e/test_frontend_app_e2e.py`（含 token 扫描与 HELLO 断言）。`.scratch/project_gates/` 现有 r1/r1_rerun/r2/r2_rerun/r3/r3_rerun。
  - 文件过大（本 task 净增，按阈值仅提示不进表）：`src/frontend/src/features/browser-session/adapter.ts` 555（新建，>400 实现阈值，属官方协议薄适配一体文件）、`useBrowserSession.ts` 406（新建）、`src/backend/cbrowser/api/runtime_coordinator.py` 481（新建）、`src/backend/cbrowser/api/v1/router.py` 696（+约186，既有大文件延展）、`src/backend/cbrowser/supervisor/docker_adapter.py` 1098（+55）、`src/backend/cbrowser/stream_agent/agent.py` 1153（+13）；测试侧 `tests/e2e/test_frontend_app_e2e.py` 1077、`test_frontend_media_e2e.py` 935 超 600 建议拆分，`test_stream_selkies_tokens_e2e.py` 591、`test_runtime_coordinator_integration.py` 582 未超阈值。
  - 圈复杂度：本轮增量的 `useProfileEventsSync` 回调、`_reconcile_running/_stopped` 均为低分支；`installSelkiesClientAdapter` 与 `agent._handle_control_packet` 分支较多但属既有协议分发/接线代码，本 task 未显著增加嵌套，不另计。
  - `useProfileEventsSync` 现对每个 SSE 事件额外失效一次 runtime 查询（活跃 Profile 每次事件一次 GET）。TanStack 对同 key 并发重取有去重，且 GET `/runtime` 不再发事件，无回环；仅记为轻微放大，不是 finding。
  - `adapter.ts:11,278` 注释与 `docs/blueprint/frontend.md:23` 写「拦截 activity/visibility 帧」，过滤器实际只匹配 `"cbrowser"`+`"activity"`；因 Gateway 本就丢弃全部 `cbrowser` 控制帧（`docs/blueprint/gateway.md:47`），无可观测缺陷，建议后续把注释/文档措辞改准。
  - `_sanitize_packet`（`stream_agent/agent.py:90-110`）仍无生产调用点，AC-010 的「日志不含 token」由「转发路径不记录 HELLO」+ `test_stream_selkies_tokens_e2e.py:577-589` 全容器日志扫描保证，不是该函数生效。
- AC 复验方式：
  - AC-001：`trust_prior`。双真实 Chrome 标签隔离与切换依赖 r3 `frontend_e2e`（21 passed）与 `test_frontend_app_e2e.py:300-430`；本轮只复跑 Vitest 路由/URL 隔离（`router.test.tsx:163-215`）。
  - AC-002：`trust_prior`。依赖 `test_frontend_session_e2e.py:125-240`（刷新 tab_id、复制页重映射、不踢原页）、`test_frontend_app_e2e.py:435-596`（noopener、官方 HELLO 子集、连接内 resume_key）；后者在 f009 修复后未重跑。
  - AC-003：`re_verified`。本轮复跑 `BrowserSessionView.test.tsx:60-76`（卸载不调用 stop/desired-state，走生产 hook 清理路径）通过；真实容器仍运行依赖 `test_frontend_session_e2e.py:204-220`（trust_prior）。
  - AC-004：`trust_prior`。依赖 `test_frontend_media_e2e.py:435-575`（STOP/START_VIDEO、consumer 2→1→0、前台 FPS）与 `test_frontend_display_apply_e2e.py:170-275`（外部 resize 不改远端、应用后新尺寸）及 r3 日志。
  - AC-005：`trust_prior`。依赖 media/session E2E 的真实输入值、`STOP_AUDIO`/`START_AUDIO` 与音频字节/能量断言；f010 的静音断言已由空真改为要求元素存在。
  - AC-006：`re_verified`。本轮重跑 integration 8 passed，并核对 `runtime_coordinator.py:78-110`（epoch 前缀 + 窗口外发完整快照）与 `useProfilesQuery.ts:186-211`（SSE 增量合并 + 失效重取，不再伪造版本）；Vitest 104 passed。
  - AC-007：`re_verified`（检测/重建/bfcache 逻辑）+ `trust_prior`（真实栈时序）。本轮复跑 `BrowserSessionView.test.tsx:174-306`（真实 `CBROWSER_PC_STATE`/WS_CLOSE/LIFECYCLE_STALE/pageshow 断言 `_k` 与 `data-stage`）；真实 freeze/ICE 依赖 lane `e2e_ice7.log`、`e2e_app_ac007_rerun3.log`。
  - AC-008：`trust_prior`。`test_stream_selkies_tokens.py::test_entrypoint_script_ac008_and_ac010_directives` 随本轮重跑通过；真实 Stream 镜像 dual-mode 403 依赖 `test_stream_selkies_tokens_e2e.py:149-190`（Docker）。
  - AC-009：`re_verified`。本轮重跑 coordinator 单测（含 Supervisor 不可达保留意愿、无实例直接收敛）与 `test_runtime_coordinator_integration.py`；真实 Supervisor 启停收敛依赖 `test_frontend_app_e2e.py:971-1040`（trust_prior）。
  - AC-010：`trust_prior`。真实镜像用例（错误/缺失 token Close 4001、Agent 代注入、全容器日志扫 master token）见 `test_stream_selkies_tokens_e2e.py:192-589` 与 lane `fix_be/t007_fix_be/e2e_stream_selkies_tokens.log`（4 passed，sec001 之后）；token 生成/0600/目录隔离单测随本轮重跑通过；app E2E 的 DOM/存储/网络/WS token 扫描待 f009 修复后重跑。

  coverage = 4 / 10
  建议合并前人工抽查 trust_prior 项（真实双标签切换与复制页、可见性 STOP/START 与前台帧率、音频字节/独立静音、真实 Supervisor 启停收敛、Stream token 拒绝与日志扫描），并先跑 r4 门禁重跑 `tests/e2e/test_frontend_app_e2e.py`。
- 总体判断：无未解决 critical / important。Round 2 的两条 minor 已真实消除且未引入新缺陷；仅因 r4 门禁缺席，AC-002/AC-010 的 app E2E 需在合并前重跑确认，不构成代码层 FAIL。
- 系统性 follow-up：无新增。p007 覆盖 f004 残留；p006/p008/p009/p010 已登记，均与当前代码事实一致。

verdict: PASS

## Round 4 (2026-11-01T05:20:00+08:00)

reviewed_scope: 9513f639f821e03b

### 本轮增量范围（已核实）

`find -newermt "2026-11-01 05:03:30"`（排除 `.scratch`、`src/frontend/public/selkies`、`tsconfig.tsbuildinfo` 等生成物）与 `git status --short` 交叉核对，Round 3 之后的生产/测试增量只有：

- `src/frontend/src/features/browser-session/audio_status.ts`（健康音频诊断跳变 `unknown` 的修复）
- `src/frontend/src/features/browser-session/audio_status.test.ts`（新增约 1.05s 采样节奏回归用例）
- `docs/blueprint/testing.md`（补前端阶段验证命令）
- `docs/pending/todo/p011_t007_test_minor_followups.md`、`p012_stream_tokens_eviction_close_race.md`、`note.md`（流程文件，不进代码结论）

`review_code.md` / `review_test.md` 为 review 产物；其余交付文件与 Round 3 一致。

### Findings

无新增 finding（`t007_code_f013` 起未使用）。

七视角对增量逐项扫描（均无 finding）：

- 规格合规：修复直接服务 AC-005「运行/媒体/音频故障分别给出可理解状态」——黑盒 r1 的 `test_ac005_audio_diagnostics_normal_silence_and_link_failure` 失败（健康音频周期性显示「音频状态未知」），根因正是 3s 窗口 + `WARMUP_RATIO` 与约 1s `getStats` 采样耦合。修复后预热按保留历史起点判定、增长比较以窗口起点前最后样本为基线，未新增范围外行为。
- 正确性：`audio_status.ts:31-50` 的 `recent` 上限为 `windowMs*2`，与生产消费者 `useBrowserSession.ts:281-290` 的裁剪上限一致；生产采样间隔固定 1000ms（`useBrowserSession.ts:326`），保留历史可达约 6s，预热阈值 2.4s 后不再周期性成立，跳变消除。逐分支手算 `no_track`/`no_data`/`normal`/`muted` 与 `windowMs` 自定义分支均符合注释语义；`muted` 短路、`last.present === false` 走 `no_data`、baseline 为空回退 `present[0]` 均无空值/越界。
- 安全：增量不触外部输入、凭证、渲染注入或日志；`AudioStatsSample` 仅数值字段，无 secret/PII 落盘。
- 契约·Breaking：无公开签名、配置键、API/schema 变更；`AudioStatus` 联合类型与既有消费点兼容。
- 性能·资源：纯函数多一次数组 `filter`（样本上限约 7 条/连接），无循环内 IO、无泄漏；采样仍为既有 1s 定时器。
- 架构·可维护性：无薄包装/重复实现/死代码；逻辑集中在单一纯函数，注释与实现一致；测试直接 import 生产 `deriveAudioStatus`（`audio_status.test.ts:1-6`），非 mock/夹具替代。
- 健壮性·可观测：`unknown` 预热期与真实故障（`no_track`/`no_data`）仍可区分；无空 catch、无静默吞错；无新增日志或敏感信息。
- 测试·文档·规格：新增用例断言真实分支（RED `.scratch/t007_master/red_audio_status_flap.log` 失败 → GREEN `green_audio_status_flap.log` 8 passed），旧 7 例保留未弱化；`docs/blueprint/testing.md` 新增命令与 `package.json` 脚本、`tsconfig.tsbuildinfo` 已入库事实一致。

### 前轮 finding 复核（以当前 diff/代码为准）

- `p011`（Round 3 遗留处置，t007_test_f011 / f012）：**处置合理，不另出 finding**。
    - f011：`useProfilesQuery.test.tsx:140-171` 只断言事件字段合并、`:174-191` 只断言无缓存不伪造，确无「事件后 `invalidateQueries(runtime)` 触发重取」的断言；`useProfilesQuery.ts:211` 的失效调用目前无回归测试，与 p011 描述一致。
    - f012：`tests/e2e/test_frontend_session_e2e.py:232,237` 仍接受 `("running", "created")`，与 p011 描述一致；同 AC 在 `tests/e2e/test_frontend_app_e2e.py` 有严格 `running` 断言，按 minor 遗留可接受。
- `t007_code_f001`–`f010`、`t007_master_sec001`：本轮增量未触及相关文件，Round 3 的「已消除」结论保持，无回退。
- `t007_test_f009` / `f010`（测试层）：不在本报告职责，Round 3 结论保持。

### 结论

- 前轮 finding 复核：无未解决 blocker；p011 两项遗留登记准确、定级合理；无撤回。
- 本轮新发现：0 条。
- 未进表的提示：
    - **门禁缺口（影响证据时效，非代码缺陷）**：r4（`.scratch/project_gates/r4/`，05:03–05:14）已跑 unit 305、integration 55、stream_e2e 19、runtime_e2e 13，但**仍无 `frontend_e2e`**；`test_frontend_app_e2e.py` / `test_frontend_session_e2e.py` / `test_frontend_media_e2e.py` / `test_frontend_display_apply_e2e.py` / `test_frontend_ice_failure_e2e.py` / `test_frontend_app_auth_e2e.py` 在 Round 2 夹具修复（f009）后仍未在完整应用拓扑上复跑，AC-001/002/004/005/007/009 的真实栈证据仍依赖 r3（22:39，修复前）。合并前必须补跑 `frontend_e2e`。
    - **音频修复的 E2E 未复跑**：`audio_status.test.ts` 单测（RED `.scratch/t007_master/red_audio_status_flap.log` → GREEN `green_audio_status_flap.log`）已证明跳变根因消除，但暴露该缺陷的 `test_ac005_audio_diagnostics_normal_silence_and_link_failure` 未在修复后重跑；从代码手算（1000ms 采样、4s 静音窗口）预期通过，仍建议随 `frontend_e2e` 一并复跑确认。
    - **低置信度边界（不作 finding）**：若页面采样出现 3–6s 的短暂停顿（后台定时器节流过渡），`recent` 仅保留少量样本，可能有一次轮询把健康音频报成 `no_data`；<3s 或 >6s 停顿分别落到预热 `unknown` 或样本全被裁剪后 `unknown`。影响为单次瞬时误报，无数据/安全问题，故仅记录。
    - 文件过大/复杂度：本轮增量文件远低于阈值（`audio_status.ts` 59 行、`audio_status.test.ts` 105 行），无新增提示；Round 3 的既有大文件提示保持不变。
    - `docs/blueprint/testing.md` 新增命令与 `package.json` 的 `build` / `generate:api` 脚本、`tsconfig.tsbuildinfo` 已入库事实一致，未发现错误指令。
- AC 复验方式：
    - AC-001：`trust_prior`。双真实 Chrome 标签页隔离依赖 `tests/e2e/test_frontend_app_e2e.py`（r3 21 passed，f009 后未复跑）；本轮 Vitest 覆盖 `router.test.tsx` 的 URL 目标隔离。
    - AC-002：`trust_prior`。刷新/复制页/不踢原页依赖 `test_frontend_app_e2e.py`、`test_frontend_session_e2e.py`（r3，修复前）。
    - AC-003：`re_verified`。本轮全量 Vitest 含 `BrowserSessionView.test.tsx:60-76`（卸载不调用 stop/desired-state，走生产 hook 清理路径）；容器仍运行依赖 r3 session E2E。
    - AC-004：`trust_prior`。依赖 `test_frontend_media_e2e.py`（STOP/START_VIDEO、consumer 2→1→0、前台 FPS）与 `test_frontend_display_apply_e2e.py`（外部 resize 不改远端、应用后新尺寸），均为 r3 证据。
    - AC-005：`re_verified`（诊断逻辑）+ `trust_prior`（真实栈）。`audio_status.test.ts::deriveAudioStatus` 8 例本轮重跑通过（含新增 1.05s 节奏用例），直接调用生产函数；真实音频字节/独立静音/故障诊断依赖 `test_frontend_media_e2e.py` 与 `test_frontend_app_e2e.py`（r3）。
    - AC-006：`re_verified`。本轮全量 Vitest 105 passed 含 `useProfilesQuery.test.tsx`（SSE 合并、不伪造 runtime）；r4 日志 unit 305 / integration 55 覆盖 SSE epoch 与断线恢复。
    - AC-007：`re_verified`（检测/重建/bfcache 逻辑）+ `trust_prior`（真实栈时序）。全量 Vitest 含 `BrowserSessionView.test.tsx:174-306`（真实 `CBROWSER_PC_STATE`/WS_CLOSE/LIFECYCLE_STALE/pageshow 断言 `_k` 与 `data-stage`）；真实 freeze/ICE 依赖 r3 lane 日志。
    - AC-008：`trust_prior`。r4 `stream_e2e` 19 passed（`test_stream_selkies_tokens_e2e.py`，含 dual-mode 403）为 sec001 之后的 Docker 证据；entrypoint 指令断言随 r4 unit 通过。
    - AC-009：`re_verified`（协调逻辑）+ `trust_prior`（真实 Supervisor）。r4 integration 55 passed 含 Supervisor 不可达保留意愿/恢复收敛；真实容器启停依赖 r3 `test_frontend_app_e2e.py`。
    - AC-010：`trust_prior`。r4 `stream_e2e` 19 passed 覆盖错误/缺失 token Close 4001、Agent 代注入与容器日志扫描；前端 DOM/网络/WS token 扫描仍待 `frontend_e2e` 复跑。
    - 本轮本地执行：`NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend` → 13 files / 105 passed（含 `audio_status.test.ts` 8 passed）。
    - coverage = 4 / 10
    - 建议合并前人工抽查 trust_prior 项（真实双标签切换与复制页、可见性 STOP/START 与前台帧率、音频字节/独立静音、真实 Supervisor 启停收敛、Stream token 拒绝与日志扫描），并补跑 r4 `frontend_e2e`。
- 总体判断：Round 3 之后唯一的代码增量（音频诊断跳变修复）逻辑正确、有真实 RED/GREEN 与直接触达生产函数的回归测试，未引入新的 critical / important；无未解决 blocker，本轮 PASS。合并前的唯一硬前置是补跑 `frontend_e2e`（证据时效，不是代码缺陷）。
- 系统性 follow-up：无新增。p011（f011/f012）与 p012 登记与当前代码事实一致。

## Round 5 (2026-11-01T06:42:00+08:00)

reviewed_scope: a006b995998b9c28

### 本轮增量范围（已核实）

`find -newermt "2026-11-01 05:20:00"`（排除 `.scratch`、`node_modules`、`dist`、`public/selkies`、`tsconfig.tsbuildinfo`、缓存）与 `git status --short` 交叉核对，Round 4 之后的生产/测试增量只有：

- `src/backend/cbrowser/supervisor/selkies_tokens.py`（新增 `provision_credentials_file`：每实例新文件名并删除旧实例文件）
- `src/backend/cbrowser/supervisor/core.py:498-516`（改调 `provision_credentials_file`，其余 start 流程未变）
- `tests/unit/test_supervisor_selkies_token_instances.py`（新增 2 例，直接 import 生产 `SelkiesTokens`）
- `tests/unit/test_supervisor_selkies_tokens.py`、`tests/e2e/test_stream_selkies_tokens_e2e.py::test_e2e_ac010_gateway_topology_runtime_in_secure_mode_with_chrome`、`tests/fixtures/frontend_app_probe/harness.py:111-116` 的文件定位改为按 `selkies_tokens_*.json` 前缀查找
- `docs/blueprint/stream_runtime.md`、`note.md`、`p011`（流程/文档，不进代码结论）

`schemas/{openapi,runtime,stream}` 与 `generated/cbrowser_v1.d.ts` 的 mtime 变化是 r5 门禁重新导出，复核内容与当前指纹不变（`reviewed_scope` 前后一致）。

### Findings

无新增 finding（`t007_code_f014` 起未使用）。

七视角对本轮增量逐项扫描（均无 finding）：

- 规格合规：修复直接服务 AC-010 的「服务端为每 Profile 生成 token」与 AC-009 的 Supervisor 启停/重启路径——r4 的 `test_supervisor_real_subprocess_retry_e2e` 回归正是本节流恢复失败，修复未引入范围外行为。
- 正确性：`core.py:421` 每次 start 生成新 `runtime_instance_id`，`core.py:388-389` 持 Profile 锁，故新文件名 `selkies_tokens_<instance>.json`（`selkies_tokens.py:50-56`）不会与上次相同；旧文件删除限定在 `get_secret_dir(profile_id)` 内。文件经 `atomic_write_text(..., mode=0o600)` + `fchmod` 落盘（`selkies_tokens.py:38`，`file_storage.py:9-32`），目录 0700（`core.py:500-501`）。空目录/首次启动、旧文件不存在等边界均安全。
- 安全：master/controller 仍为 `secrets.token_urlsafe(32)`（`selkies_tokens.py:22-27`）；路径在 `runtime/.secrets/<profile>`（与挂进 Browser 的 `runtime/<profile>` 平级，`path_validator.py:124-137`），经 `validate_secret_source`（`docker_adapter.py:839-841`）校验；新代码不打日志、不返回 token。删除仅匹配 `selkies_tokens_*.json`，不触及 `agent_secret.txt` 等其它文件。
- 契约·类型·Breaking：无公开 API/schema/配置键变化；凭证文件名是容器与宿主间的内部契约，`docs/blueprint/stream_runtime.md:15` 与 Stream 挂载点 `/tmp/selkies_credentials.json`（`docker_adapter.py:867-870`）一致。
- 性能·资源：每次 start 多一次目录 glob + unlink，规模为单 Profile 单个文件，无循环内 IO、无泄漏。
- 架构·可维护性：逻辑集中在 57 行单模块，复用既有 `write_credentials_file`/`atomic_write_text`，注释解释「为何换名而非原地替换」，无重复实现或死代码。
- 健壮性·可观测：删除在写新文件之前，写失败时无凭证可用、启动显式失败（fail-closed）；无空 catch、无静默吞错。`_INSTANCE_ID` 仅放行内部 `inst_<hex>` 形态，越权路径（`../x`、`a/b`）抛 `ValueError`，有单测断言。
- 测试·文档·规格：新增单测直接调用生产函数（`test_supervisor_selkies_token_instances.py:17,33`），有 RED/GREEN 证据；`test_supervisor_selkies_tokens.py:325-344` 断言真实 `core.start_profile` 产出的文件名与 0600；文档与夹具同步到新前缀。

### 前轮 finding 复核（以当前 diff/代码为准，不采信处置表自述）

- **r4 回归修复（Sup-重启）**：已消除。r4 `sup_lifecycle.log:378` 失败后，主控在最终代码上跑 `test_supervisor_real_subprocess_retry_e2e`：`.scratch/t007_master/token_instance_verify/retry_1.log` 与 `retry_2.log` 各 `1 passed`（95.95s / 95.96s），`rest.log` 14 passed；官方 r5 门禁 `.scratch/project_gates/r5/sup_lifecycle.log` 再次 `6 passed`（含该用例）。不得再按 r4 的旧失败判 FAIL。
- `p011`（`t007_test_f011` / `t007_test_f012` / `t007_test_f013`）：**仍与当前代码一致，处置合理**。`useProfilesQuery.test.tsx:141-192` 仍只断言缓存合并与「无缓存不伪造」，未断言 `useProfilesQuery.ts:211` 的 `invalidateQueries` 触发重取（f011）；`test_frontend_session_e2e.py:232,237` 仍接受 `("running", "created")`（f012）；`audio_status.test.ts:8-16` 的 `samples()` 仍丢弃 `totalAudioEnergy`（f013）。均 minor 且已登记 p011，不另出 finding。
- `t007_code_f001`–`f010`、`t007_master_sec001`：本轮增量未触及相关实现，无回退。本轮复跑 `tests/unit` 307 passed、token 子集 17 passed、integration 8 passed、Vitest 105 passed；SSE epoch、stop 路径、无伪造 runtime、token 目录隔离结论保持。
- **契约区 drift 复核**：相对 anchor 的 AC 变化为 Round 1 已记录的 AC-002/AC-007 `resume_key` 语义修订（上下文区 2026-10-31 条）与实施侧勾选；本轮未发现新的未确认需求变更，不按 blocking 处理。

### 结论

- 前轮 finding 复核：无未解决 blocker；r4 回归已由最终代码的真实 subprocess 复跑与 r5 门禁双重证实修复；p011 三项遗留登记准确、定级合理；无撤回。
- 本轮新发现：0 条。
- 未进表的提示：
  - **r5 `frontend_e2e` 1 项失败（测试时序，非本轮代码）**：`.scratch/project_gates/r5/summary.txt` 记 `frontend_e2e rc=1`，`r5/frontend_e2e.log:102` 为 `test_ac001_ac006_profile_ui_dual_tab_sse_and_stale_state`，失败点 `tests/e2e/test_frontend_app_e2e.py:377`：`assert 1 > 1`（B 页 `framesDecoded` 在 `:371` 固定 `sleep(2.0)` 前后不变）。同一 nodeid 在最终代码上 32 分钟前已通过（`token_instance_verify/rest.log` 14 passed）且 r4_final 为 22 passed，期间源码/生成物指纹未变（仅门禁重新导出，`reviewed_scope` 不变），故不是本轮增量引入的回归。另 `wait_iframe_stats`（`test_frontend_app_e2e.py:156-164`）在 `min_frames=1` 时立即返回，实际等待只有那 2 秒；若 B 页处于后台，Selkies 官方 STOP_VIDEO（AC-004 允许）本就会暂停该连接视频，该断言还可能是测试设计不稳。建议合并前重跑并把 `page_b.bring_to_front()` 纳入用例、改为对 `framesDecoded` 增长做显式轮询/超时；若复现则归入 p009（同类固定 sleep 抖动）或 test reviewer 继续定位，不阻断本报告代码 verdict。
  - **文件过大**：本轮新增 `selkies_tokens.py` 57 行、`test_supervisor_selkies_token_instances.py` 43 行，均远低于阈值；Round 3 已列的大文件清单（`adapter.ts` 555、`useBrowserSession.ts` 406、`runtime_coordinator.py` 481、`router.py` 696、`docker_adapter.py` 1098、`stream_agent/agent.py` 1153；测试侧 `test_frontend_app_e2e.py` 1077、`test_frontend_media_e2e.py` 935）不变。
  - **圈复杂度**：`provision_credentials_file` 约 3 个分支，无新增热点；`RuntimeCoordinator.reconcile_profile_now` / `installSelkiesClientAdapter` 等既有热点建议后续拆分，不阻断。
  - **低置信度**：`_INSTANCE_ID` 用 `^[A-Za-z0-9_-]+$`，Python `$` 会放过单个尾部换行；调用方 id 固定为内部 `inst_<12 hex>`（`core.py:421`），无可观测影响，若后续允许外部传 instance id 建议改 `fullmatch`。
  - **范围外观察**：Profile 删除只删 DB（`services/profile_service.py::delete_profile` → `repository.py::delete_profile`），`runtime/.secrets/<profile>` 的最后一份凭证文件不会被清理；Profile 数据清理/重置归 t013，建议届时一并覆盖。
- AC 复验方式：
  - AC-001：`trust_prior`。真实双标签目标/连接隔离依赖 `test_frontend_app_e2e.py:300-430`；本轮 r5 该用例失败、`rest.log` 同用例通过（见上条），故只依赖已产出日志，建议重跑后复审。
  - AC-002：`trust_prior`。`test_frontend_app_e2e.py::test_ac002_ac003_ac010_identity_copy_close_and_tokens` 与 `test_frontend_session_e2e.py:125` 在最终代码的 `token_instance_verify/rest.log`（14 passed）中通过；token 泄漏扫描因夹具改为 glob 后重新生效。
  - AC-003：`re_verified`。本轮 Vitest 105 passed 含 `BrowserSessionView.test.tsx` 的卸载不调 stop/desired-state 用例（生产 hook 清理路径）；真实容器存活依赖 `rest.log` 的 AC-002/003 用例（`trust_prior`）。
  - AC-004：`trust_prior`。依赖 `test_frontend_media_e2e.py:435-575` 与 `test_frontend_display_apply_e2e.py:170-275`（r5 frontend_e2e 21 passed 含媒体/显示用例）。
  - AC-005：`trust_prior`。依赖 media/session E2E 的真实输入、STOP/START_AUDIO 与音频字节断言（r5 21 passed；`test_ac005_audio_diagnostics...` 已随音频修复转绿）。
  - AC-006：`re_verified`。本轮复跑 integration 8 passed（r5 门禁 integration 55 passed），Vitest 105 passed 含 `useProfilesQuery.test.tsx` 的 SSE 合并/不伪造用例；断线 epoch 由 `test_sse_epoch_integration.py` 真实重启进程覆盖。
  - AC-007：`re_verified`（检测/重建/bfcache 逻辑）+ `trust_prior`（真实栈时序）。Vitest 105 passed 含 `BrowserSessionView.test.tsx` 的 `CBROWSER_PC_STATE`/WS_CLOSE/LIFECYCLE_STALE/pageshow 断言；真实 freeze/ICE 依赖 r5 21 passed 中的 `test_ac007_freeze_resume_and_diagnostic_stages` 与 `test_ac007_ice_failure_stage`。
  - AC-008：`trust_prior`。r5 `stream_e2e` 19 passed 含 `test_e2e_ac008_dual_mode_disabled_negative_and_positive`（真实 Stream 镜像 403）。
  - AC-009：`re_verified`（协调逻辑）+ `trust_prior`（真实 Supervisor）。本轮 unit 307 / integration 8 复跑通过，r5 `sup_lifecycle` 6 passed（含跨 SIGKILL 重启收敛）；真实容器启停依赖 `test_ac009_ui_start_stop_and_supervisor_outage_convergence`（r5 21 passed）。
  - AC-010：`trust_prior`。r5 `stream_e2e` 19 passed 覆盖直连缺/错 token 4001、Agent 代注入、双 tab 共存/驱逐、容器日志无 master token；`test_e2e_ac010_gateway_topology...` 按新前缀读取 0600 文件并验证 Browser 容器不可见；前端 DOM/网络/WS token 扫描依赖 `rest.log` 的 AC-002/003/010 用例。
  - 本轮本地执行：`NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend` → 13 files / 105 passed；`pytest tests/unit` → 307 passed；token 子集 17 passed；integration（SSE/coordinator）8 passed。
  - coverage = 4 / 10
  - 建议合并前人工抽查 trust_prior 项（真实双标签切换与复制页、可见性 STOP/START 与前台帧率、音频字节/独立静音、真实 Supervisor 启停收敛、Stream token 拒绝与日志扫描），并重跑 r5 `frontend_e2e` 归因 AC-001 用例。
- 总体判断：本轮增量只改 token 凭证文件命名/清理与相应测试定位，逻辑正确、无害且已由真实 subprocess 与 r5 门禁验证修复了 r4 回归；无未解决 critical / important，本轮 PASS。r5 `frontend_e2e` 的 AC-001 单例失败在最终代码上无对应源码变化且此前同用例通过，属测试时序/后台可见性交互，须重跑归因，不构成代码层 FAIL。
- 系统性 follow-up：无新增。p011 覆盖三项测试遗留；p009 已覆盖「固定 sleep + 多 viewer」同类抖动，建议把 `test_frontend_app_e2e.py:371-377` 纳入 p009 的重跑/收紧范围。

verdict: PASS

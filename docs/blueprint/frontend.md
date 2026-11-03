# 前端

v2 前端为 `src/frontend` 下的 React 19 + Vite 单页应用，由 Caddy 作为静态资源托管，只经 `/api/v1` 与 `/stream/{profileId}/signal` 访问后端。t017 已删除 v1 前端树、旧测试、noVNC 类型与仅其使用的依赖；路由只保留 `react-router-dom` 单一实现。

## 1. 外壳与数据

- 路由（React Router 7，`app/router.tsx`）：`/login`、`/`（`?profileId=` 指定当前页面的操控目标）、`/settings`、`/profiles/new`、`/profiles/:profileId`、`/profiles/:profileId/files`、`/automation/:profileId`；会话失效（401）或登出时跳转 `/login`。
- API 客户端（`shared/api/client.ts`）使用 `openapi-typescript` 从 `schemas/openapi/cbrowser_v1.json` 生成的类型（`npm run generate:api`，产物 `shared/api/generated/`），禁止手写与后端重复的响应类型。写方法带 `X-CSRF-Token`（取 `cbrowser_csrf` Cookie）；运行意愿为 `PATCH /api/v1/profiles/{id}/runtime/desired-state`。普通请求默认 30s、上传 5min、长操作 2min 超时；绝对 URL 只允许同源；`ApiError` 携带 `errorCode`、`retryable` 与 `detail`。SSE 遇 401 停止重连并触发登出，流结束时 flush 解码器残留事件。
- 服务器状态由 TanStack Query 5 管理。SSE 事件 id 为 `<epoch>:<seq>`（epoch 为 API 进程随机值）：同 epoch 且在历史窗口内的 `Last-Event-ID` 只补发缺失事件，其余情况（API 重启、旧格式、超窗口）发送完整初始快照。运行状态经 `GET /api/v1/events`（SSE，事件 `runtime_state`，fetch 流式读取以携带 Cookie）增量合并进查询缓存（含 `last_coordinator_error`）并使 Profile 列表查询失效重取；断线自动重连，前端不保存任何控制状态。
- 运行协调错误（Supervisor 未配置或不可达）在页头与会话页以 `runtime-coordinator-error` 显式展示，运行意愿保持不变。
- `/profiles/:profileId/files` 为 Artifact 管理页：经 `shared/api/client.ts` 的 `artifacts` 方法列出、上传、下载、删除文件，展示 `container_path`，写操作带 CSRF。
- `/automation/:profileId` 为自动化页：经 `automation.status()` 展示授权 WS 端点、运行状态、运行实例、Supervisor 配置状态与 `Authorization: Bearer <cbat_...>` 头格式；不展示任何明文凭证。
- Profile 详情页提供复制与重置面板：复制可选仅配置或含浏览器状态（运行中禁用状态复制并提示停止）；重置面板明确列出将清除的 Cookie、站点数据、缓存、登录状态与指纹身份，并说明保留设置与 Artifact。
- 会话、页头与 Profile 主表单文案经 `i18n.tsx` 的 `t()`（en/zh）；语言偏好存储键为 `cbrowser.locale`（迁移旧 `cbm.locale`），切换时同步 `document.documentElement.lang`。

## 2. 页面独立状态

- 每个 Chrome 标签页独立维护 `selectedProfileId`（URL 查询参数）、ViewerConnection 与会话阶段；切换 Profile 只改变本页目标与连接。禁止跨标签页共享的 `localStorage.currentProfileId`。
- 同一 Profile 可有多个页面同时连接，全部为 controller；前端不维护租约或唯一控制者状态。
- 页面关闭、刷新或切换目标只关闭自身 PeerConnection 与信令，不调用 Profile stop；只有用户明确停止 Profile 才停止 Browser。

## 3. Selkies 官方客户端薄适配

- 官方 Selkies 2.1.0 Web 客户端由 `scripts/vendor_selkies_web.py` 从固定 wheel（SHA-256 固定）解出并校验文件清单（`config/selkies/selkies_web_sha256.txt`，不依赖测试目录），放到 `src/frontend/public/selkies/`（gitignore）。`npm run build` 的 `prebuild` 自动执行 vendor，`postbuild` 自动执行 `scripts/verify_frontend_dist.py`，校验 `dist/selkies/index.html` 的 adapter tag 顺序、`selkies_adapter.js` 的经典 IIFE 形态与全部官方资源哈希；生产镜像在 COPY `dist/` 后必须再次运行同一校验，禁止绕过。会话页以同源 iframe `/selkies/index.html?profileId=` 加载。
- 适配层唯一实现为 `features/browser-session/adapter.ts`，经 `vite.selkies.config.ts`（入口 `selkies_adapter_entry.ts`）构建为经典 IIFE 脚本 `dist/selkies/selkies_adapter.js`，vendor 脚本只在官方 `index.html` 的 module bundle 之前注入 `<script src="./selkies_adapter.js">`，不携带任何适配代码。职责：信令改写到 `/stream/{profileId}/signal`；不改写官方 HELLO、`client_tab_id`、`resume_key`；复制标签页经 Web Locks 探测冲突并重映射身份，不踢原页（d007）；锁定远端分辨率/DPR，外部 resize 不改变远端；新窗口强制 `noopener`；键盘焦点守卫（未聚焦时 `stopImmediatePropagation()` 阻断向远端转发，配合宿主 `AppLayout` 在外部点击时主动 `blur()` iframe，隔离宿主浏览器全局快捷键）。媒体为同机直连，适配层不再处理 RTC/TURN 配置或 ICE restart。生产代码不暴露任何测试用全局；测试需要的 DataChannel/PeerConnection 探针由测试夹具写入复制后的 Selkies 目录，并在 `selkies_adapter.js` 之前插入 `<script>`，保证探针先于 adapter 包装原生接口。
- 页面可见性只由官方客户端每 Peer `STOP_VIDEO`/`START_VIDEO` 处理（计划 9.3），适配层丢弃 activity/visibility 帧，不向 Gateway 上报。
- 宿主与 iframe 的唯一生产统计契约为 `window.__getWebRTCStats()`；适配层另向父窗口发送 `CBROWSER_PC_STATE`、`CBROWSER_WS_CLOSE`、`CBROWSER_LIFECYCLE_STALE` 与 `CBROWSER_WEB_LOCKS_UNAVAILABLE` 消息。
- 页面不持有任何 Selkies token；controller token 由 Stream Agent 在转发 HELLO 时代注入（d024）。

## 4. 会话阶段与恢复

- 阶段：`checking_runtime`、`runtime_not_ready`、`connecting_signaling`、`signaling_failed`、`web_locks_unavailable`、`connecting_ice`、`ice_failed`、`media_waiting`、`media_no_frames`、`connected`、`reconnecting`。运行时检查经统一 API 客户端：401 由鉴权层跳转登录，网络/服务不可达进入带原因的 `runtime_not_ready`；Web Locks 不可用进入专门阶段。失败阶段给出可执行操作（重连、查看运行状态），不出现无解释黑屏，不新增媒体回退通道。
- 诊断取自 `RTCPeerConnection` 状态与 `getStats()`（选中候选对类型、RTT、接收字节）。
- Page Lifecycle `freeze`/`resume` 与 bfcache `pageshow` 后检查信令与 PeerConnection，失效则重建 iframe（同一 `client_tab_id`，官方客户端生成新 `resume_key`）；信令 WS 异常关闭时先给官方客户端 5 秒以原 `resume_key` 重连，仍不健康再重建。
- ICE：`failed` 立即进入 `ice_failed`；`disconnected` 持续 5 秒（`iceDisconnectGraceMs`）才判失败，期间恢复则不报。
- 宿主只接受来自本会话 iframe（`event.source`）且同源的 postMessage；适配层向父窗口发送时指定具体 origin。
- 侧边栏选择 Profile 一律导航到 `/?profileId=`（会话页）。
- 剪贴板：`ClipboardPermissionHint` 在宿主会话页中按需探测权限（与 `/selkies` iframe 同源），拒绝/提示状态显示可执行说明；自身不调用 `navigator.clipboard` 读写，复制粘贴同步由 iframe 内官方 Selkies seamless 客户端完成（decisions 012）。
- 音频：每页静音按钮经官方 `pipelineControl` audio（`STOP_AUDIO`/`START_AUDIO`）；音频状态（`audio_status.ts`）由 getStats 推导，与视频阶段独立：`normal`/`muted`/`no_track`/`no_data`/`unknown`，内容静音不判故障。
- 显示设置：运行时 `config_version` 与 Profile 当前配置版本不同即显示待应用提示与“应用并重启”（经 API stop → running）。

## 5. 测试

- Vitest（`npm test --prefix src/frontend`，需 `NODE_OPTIONS=--no-experimental-webstorage`）覆盖 API 客户端、SSE、路由与会话组件。
- 真实栈 E2E 用构建产物 + 官方 Selkies 资源，经 Caddy/API（启用 Runtime Coordinator）/Supervisor/Gateway/Browser/Stream 与无头 Google Chrome（无 coturn）：`tests/e2e/test_frontend_app_e2e.py`、`test_frontend_session_e2e.py`、`test_frontend_session_vendor.py`。所有浏览器测试必须无头。

# 前端

v2 前端为 `src/frontend` 下的 React 19.3 + Vite 8 单页应用，由 Caddy 作为静态资源托管，只经 `/api/v1` 与 `/stream/{profileId}/signal` 访问后端。t017 已删除 v1 前端树、旧测试、noVNC 类型与仅其使用的依赖；路由只保留 `react-router` 8 单包实现（t033 由 `react-router-dom` 换包，DOM API 全部由单包导出）。

## 1. 外壳与数据

- 路由（React Router 8 单包，`app/router.tsx`，plan 5.1 / t036）：`/login`、`/`（环境列表）、`/session`（会话入口）、`/session/:profileId`（会话页，目标由 path param 决定）、`/profiles/:profileId`（重定向到 `config`）、`/profiles/:profileId/{config,files,automation,maintenance}`、`/proxies`、`/settings`；旧路由 `/?profileId=`、`/profiles/new`、`/automation/:profileId` 直接删除（`/profiles/new` 显式置于 `:profileId` 之前并回落首页 catch-all），导航与环境链接均为真实 `<a href>`；会话失效（401）或登出时跳转 `/login`。`/` 由 t037 环境列表承载、`/proxies` 由 t038 代理库承载；`/session` 为会话入口页（t039：本标签页无目标时列出运行中环境供选择）、`/session/:profileId` 为 t039 重新设计的新会话页。t039 已启用全局颜色门禁（见 testing.md）。
- API 客户端（`shared/api/client.ts`）使用 `openapi-typescript` 从 `schemas/openapi/cbrowser_v1.json` 生成的类型（`npm run generate:api`，产物 `shared/api/generated/`），禁止手写与后端重复的响应类型。写方法带 `X-CSRF-Token`（取 `cbrowser_csrf` Cookie）；运行意愿为 `PATCH /api/v1/profiles/{id}/runtime/desired-state`。普通请求默认 30s、上传 5min、长操作 2min 超时；出站三入口（ApiClient 请求、SSE 连接、Artifact 下载链接）统一按最终解析 URL 做同源判定，跨源（含反斜杠/协议相对变体）在附带凭据前拒绝，客户端无可配置的跨源基地址（无 baseUrl/url 配置项，测试以同源夹具接入）；`ApiError` 携带 `errorCode`、`retryable` 与 `detail`。登出请求失败时本地认证状态与内存 CSRF token 一律清除，各注销调用点显式处置 logout 的 rejection，不产生 unhandled rejection。请求取消分两种语义：调用方外部取消产生不可重试的 `cancelled` 错误，内部超时产生可重试的 `timeout` 错误，请求结束后必须释放外部信号监听。页面与布局经 `ApiClientContext`（`shared/api/client_context.tsx`）取得 `AppProviders` 下发的客户端实例并透传给数据 hooks，禁止在组件中直接引用单例；写操作的幂等键（`Idempotency-Key`）在每次 `mutate`/`mutateAsync` 调用边界生成、该次逻辑动作的自动重试全程复用同一键，复合动作（如应用显示设置的 stop→start）由单次动作键派生各自的操作键。SSE 遇 401 停止重连并触发登出，流结束时 flush 解码器残留事件。
- 服务器状态由 TanStack Query 5 管理。SSE 事件 id 为 `<epoch>:<seq>`（epoch 为 API 进程随机值）：同 epoch 且在历史窗口内的 `Last-Event-ID` 只补发缺失事件，其余情况（API 重启、旧格式、超窗口）发送完整初始快照。运行状态经 `GET /api/v1/events`（SSE，事件 `runtime_state`，fetch 流式读取以携带 Cookie）增量合并进查询缓存（含 `last_coordinator_error`）并使 Profile 列表查询失效重取；断线自动重连，前端不保存任何控制状态。SSE 事件类型即生成的 `ProfileRuntimeStatusEvent`：投递前逐字段验证核心字段与状态枚举，畸形或未知事件只进错误通道不投递；连接以代次（generation）隔离，重复 `start` 不新增连接，旧代次不得投递、报错或重连，`stop` 后不得重连。
- 运行协调错误（Supervisor 未配置或不可达）经 `useRuntimeSnapshot` 聚合 runtime 查询缓存（随 SSE 更新），在外壳主内容顶部以 `runtime-coordinator-error` 警示横幅（`Banner`）显式展示，运行意愿保持不变。
- `/profiles/:profileId/files` 为 Artifact 管理页：经 `shared/api/client.ts` 的 `artifacts` 方法列出、上传、下载、删除文件，展示 `container_path`，写操作带 CSRF。多文件上传顺序执行、首个失败即停止，失败文案须给出已成功数、失败文件名与未处理数（不输出文件内容）。
- 设置页的健康状态只呈现其真实探测对象——Control API 健康检查，不声称网关或其它服务的状态。
- `/automation/:profileId` 为自动化页：经 `automation.status()` 展示授权 WS 端点、运行状态、运行实例、Supervisor 配置状态与 `Authorization: Bearer <cbat_...>` 头格式；不展示任何明文凭证。
- Profile 详情页提供复制与重置面板：复制可选仅配置或含浏览器状态（运行中禁用状态复制并提示停止）；重置面板明确列出将清除的 Cookie、站点数据、缓存、登录状态与指纹身份，并说明保留设置与 Artifact。
- 会话、页头与 Profile 主表单文案经 `i18n.tsx` 的 `t()`（en/zh）；语言偏好存储键为 `cbrowser.locale`（迁移旧 `cbm.locale`），切换时同步 `document.documentElement.lang`。翻译键集由 en 字典派生（`TranslationKey = keyof typeof en`），zh 字典以 `satisfies Record<TranslationKey, string>` 编译期对齐，并有键集相等测试兜底；新增文案必须 en/zh 同步补键。

## 2. 页面独立状态

- 每个 Chrome 标签页独立维护会话目标（`/session/:profileId` path param，写入 `sessionStorage` 的 `cbrowser.session.target` 供侧栏「会话」导航回跳）、ViewerConnection 与会话阶段；切换 Profile 只改变本页目标与连接。禁止跨标签页共享的 `localStorage.currentProfileId`。
- 页面与布局的动作状态（error/pending）按动作目标 Profile 隔离呈现（`scopeMutationToProfile`）：常驻组件（AppLayout、会话页、详情页）只显示目标为当前 Profile 的动作状态，其他 Profile 的错误、pending 与迟到响应不进入当前视图，本地结果横幅不跨 Profile 携带。
- 同一 Profile 可有多个页面同时连接，全部为 controller；前端不维护租约或唯一控制者状态。
- 页面关闭、刷新或切换目标只关闭自身 PeerConnection 与信令，不调用 Profile stop；只有用户明确停止 Profile 才停止 Browser。
- 详情面板展开状态持久化在 `cbrowser.session.details_open`（刷新后保持），默认收起（t039）。
- 专注模式隐藏导航侧栏与页头，鼠标悬停顶部边缘显示悬浮退出工具条，**不用 Esc 退出**（Esc 与常用组合键留给远端 iframe）；专注状态经 `SessionFocusProvider` 提升到 `AppProviders`（`app/providers.tsx` 的 `AuthProvider` 内）供 `AppLayout` 与会话页共享读取，专注期间不条件卸载 iframe 与 `useBrowserSession`，不重建连接、不中断远端输入（t039）。
- `/session` 会话入口在本标签页无目标时列出运行中环境（真实链接）；侧栏「会话」导航在本标签页已有目标时回跳该会话（t039）。

## 3. Selkies 官方客户端薄适配

- 官方 Selkies 2.2.1 Web 客户端由 `scripts/vendor_selkies_web.py` 从固定 wheel（SHA-256 固定）解出并校验文件清单（`config/selkies/selkies_web_sha256.txt`，不依赖测试目录），放到 `src/frontend/public/selkies/`（gitignore）。`npm run build` 的 `prebuild` 自动执行 vendor，`postbuild` 自动执行 `scripts/verify_frontend_dist.py`，校验 `dist/selkies/index.html` 的 adapter tag 顺序、`selkies_adapter.js` 的经典 IIFE 形态与全部官方资源哈希；生产镜像在 COPY `dist/` 后必须再次运行同一校验，禁止绕过。会话页以同源 iframe `/selkies/index.html?profileId=` 加载。
- 适配层唯一实现为 `features/browser-session/adapter.ts`，经 `vite.selkies.config.ts`（入口 `selkies_adapter_entry.ts`）构建为经典 IIFE 脚本 `dist/selkies/selkies_adapter.js`，vendor 脚本只在官方 `index.html` 的 module bundle 之前注入 `<script src="./selkies_adapter.js">`，不携带任何适配代码。职责：信令改写到 `/stream/{profileId}/signal`；不改写官方 HELLO、`client_tab_id`、`resume_key`；复制标签页经 Web Locks 探测冲突并重映射身份，不踢原页（d007）；锁定远端分辨率/DPR，外部 resize 不改变远端；新窗口强制 `noopener`；键盘焦点守卫（未聚焦时 `stopImmediatePropagation()` 阻断向远端转发，配合宿主 `AppLayout` 在外部点击时主动 `blur()` iframe，隔离宿主浏览器全局快捷键）。媒体为同机直连，适配层不再处理 RTC/TURN 配置或 ICE restart。生产代码不暴露任何测试用全局；测试需要的 DataChannel/PeerConnection 探针由测试夹具写入复制后的 Selkies 目录，并在 `selkies_adapter.js` 之前插入 `<script>`，保证探针先于 adapter 包装原生接口。
- 页面可见性只由官方客户端每 Peer `STOP_VIDEO`/`START_VIDEO` 处理（计划 9.3），适配层丢弃 activity/visibility 帧，不向 Gateway 上报。
- 宿主与 iframe 的唯一生产统计契约为 `window.__getWebRTCStats()`；适配层另向父窗口发送 `CBROWSER_PC_STATE`、`CBROWSER_WS_CLOSE`、`CBROWSER_LIFECYCLE_STALE` 与 `CBROWSER_WEB_LOCKS_UNAVAILABLE` 消息。
- 页面不持有任何 Selkies token；controller token 由 Stream Agent 在转发 HELLO 时代注入（d024）。

## 4. 会话阶段与恢复

- 阶段：`checking_runtime`、`runtime_not_ready`、`connecting_signaling`、`signaling_failed`、`web_locks_unavailable`、`connecting_ice`、`ice_failed`、`media_waiting`、`media_no_frames`、`connected`、`reconnecting`。运行时检查经统一 API 客户端：401 由鉴权层跳转登录，网络/服务不可达进入带原因的 `runtime_not_ready`；Web Locks 不可用进入专门阶段。失败阶段给出可执行操作（重连、查看运行状态），不出现无解释黑屏，不新增媒体回退通道。
- 会话页加载状态严格区分：加载中、加载失败（显式错误加重试）、Profile 不存在（仅真实 404）、已停止待启动；请求失败不得呈现为已停止。语言切换只改变文案，不得重跑运行时检查或重置已连接会话（效果依赖不含翻译函数身份，经 ref 读取最新翻译）。
- 诊断取自 `RTCPeerConnection` 状态与 `getStats()`（选中候选对类型、RTT、接收字节）。
- Page Lifecycle `freeze`/`resume` 与 bfcache `pageshow` 后检查信令与 PeerConnection，失效则重建 iframe（同一 `client_tab_id`，官方客户端生成新 `resume_key`）；信令 WS 异常关闭时先给官方客户端 5 秒以原 `resume_key` 重连，仍不健康再重建。
- ICE：`failed` 立即进入 `ice_failed`；`disconnected` 持续 5 秒（`iceDisconnectGraceMs`）才判失败，期间恢复则不报。
- 宿主只接受来自本会话 iframe（`event.source`）且同源的 postMessage；适配层向父窗口发送时指定具体 origin。
- 会话目标由 `/session/:profileId` 决定；导航侧栏不再列 Profile，「会话」项在本标签页已有目标时回跳该会话，否则进 `/session`。
- 剪贴板：`ClipboardPermissionHint` 在宿主会话页中按需探测权限（与 `/selkies` iframe 同源），拒绝/提示状态显示可执行说明；自身不调用 `navigator.clipboard` 读写，复制粘贴同步由 iframe 内官方 Selkies seamless 客户端完成（decisions 012）。
- 音频：每页静音按钮经官方 `pipelineControl` audio（`STOP_AUDIO`/`START_AUDIO`）；音频状态（`audio_status.ts`）由 getStats 推导，与视频阶段独立：`normal`/`muted`/`no_track`/`no_data`/`unknown`，内容静音不判故障。
- 显示设置：运行时 `config_version` 与 Profile 当前配置版本不同即显示待应用提示与“应用并重启”（经 API stop → running）。该动作带阶段跟踪（按动作键保存 stop 前实例与 start 已发出标记）：自动重试先观测运行时再续跑——stop 已生效不重发不重等、start 已生效而响应丢失时收敛到新实例的 running（不等待 stopped、不停止或重建新实例）、未生效步骤以同一操作键续跑、状态查询持续失败有界报错。
- 会话页画面区由 `SessionPage` 承载：iframe 铺满、不绘制模拟浏览器框（ADR 003/006）。全部非 `connected` 阶段显示居中状态面板（`SessionStagePanel`），给出阶段原因与可执行操作（重连 / 查看运行状态 / 启动），`connected` 不显示面板；阶段清单以 blueprint 本节为权威——`connecting_ice` 在 `types.ts` 未定义，`SessionStagePanel` 以字符串字面量分支保留该 stage，逻辑层（`useBrowserSession`）暂不产生它（t039）。
- 详情面板（`SessionDetailsPanel`）右侧 300px、默认收起，分环境 / 网络 / 指纹 / 运行四区（指纹含平台、字体集与缺失字体告警；运行含浏览器版本与 UA、实例 ID、配置版本、transport 状态、最近错误、启动时间），每个值可复制（t039）。
- 剪贴板权限提示（`ClipboardPermissionHint`）、音频状态与诊断浮层按设计系统重建、行为语义不变：剪贴板只探测权限不读写本机剪贴板，音频经官方 `pipelineControl` 的 `STOP_AUDIO` / `START_AUDIO`，诊断取自 `RTCPeerConnection` 状态与 `getStats()`（t039）。
- 旧会话页组件（`BrowserSessionPage` / `BrowserSessionView` / `BrowserSessionMount` 及旧测试）整体删除；`data-testid` 全部改 `sess-*` 结构（旧 `browser-session-*` / `session-*` / `diag-*` 弃用），会话 E2E 与组件测试选择器同步改写（t039）。
- 旧页面全部替换后启用全局颜色门禁：`npm run design:lint` 的 `--lint` 经 `runLintSources(sources)` 同时跑尺寸断言与颜色断言，扫描前端源码颜色字面量与默认调色板类发现即失败、无豁免（见 testing.md「t039 全局颜色门禁」）。

SSE 消费契约（t022）：快照帧为订阅私有数据，携带 live 基点事件 id（快照时刻最后一条实时事件序号），不进入共享历史；重连以基点 id 经 Last-Event-ID 续传，服务端回放基点之后的实时事件，无缺口无倒退；窗口不足时服务端以全量快照显式重建。Profile 详情页呈现独立的默认搜索初始化状态：`search_defaults.state == "failed"` 时显示与浏览器可用性分离的失败提示与重试按钮（调用 `POST /profiles/{id}/runtime/search-defaults/retry`），不要求重启浏览器。

分层观测消费（t026）：runtime 响应与 SSE 事件携带 `transport` 分层观测（browser/stream/transport 状态与最近错误），前端校验与缓存同步规则与 `search_defaults` 同构：结构不合法的事件整帧拒绝，事件未携带字段时保留缓存值。会话信令呈现区分恢复与失败：首次连接的信令异常关闭（含 1006）在 transport 为 recovering 时呈现恢复中并在有界窗口（默认 30 秒）内轮询运行状态，transport 变 ready 后重连、明确 failed 或窗口耗尽才呈现信令失败；已连接后的断开沿用既有 resume 语义不变。

SSE 按事件类型分发（t040）：`shared/api/sse.ts` 解析 `event:` 行按类型路由，`runtime_state` 走原运行状态通道，新增 `profile_preview` 走 `onPreviewEvent`；`useProfilesQuery.ts` 订阅 preview 事件刷新 runtime 缓存。`profile_preview` 只实时扇出、绝不进入 runtime 事件重放环，SSE 重连后的 runtime 状态重放不受缩略图事件数量影响（AC-003）。`ProfileRuntimeResponse.preview_captured_at` 无预览为 null，首屏据此显示图片或占位，**无值不请求图片**；`EnvironmentCard` 以 `?v=<captured_at>` 作为图片 URL 版本参数触发刷新，404 / onError 回退占位。

## 5. 测试

- Vitest 5（`npm test --prefix src/frontend`，无需 `NODE_OPTIONS`）覆盖 API 客户端、SSE、路由与会话组件；`npm test` 先执行 `test:types`（`tsc -p tsconfig.test.json`）对全部测试文件做严格类型检查，再运行 Vitest。页面与守卫测试在 ApiClient 边界注入每例独立 stub 并走真实 hooks 接线，禁止 mock 数据 hooks 模块、禁止对共享单例做方法赋值；测试夹具与事件字面量须使用生成类型的完整线形状。
- 真实栈 E2E 用构建产物 + 官方 Selkies 资源，经 Caddy/API（启用 Runtime Coordinator）/Supervisor/Gateway/Browser/Stream 与无头 Google Chrome（无 coturn）：`tests/e2e/test_frontend_app_e2e.py`、`test_frontend_session_e2e.py`、`test_frontend_session_vendor.py`。所有浏览器测试必须无头。

## 6. 设计系统与应用外壳（t036）

- 设计权威：仓库根 `DESIGN.md`（google-labs-code/design.md alpha 格式，YAML front matter）。章节顺序 Overview / Colors（含 `### Modes`）/ Typography / Layout / Elevation & Depth / Shapes / Components / Do's and Don'ts。`primary` 为模式无关品牌色，其余颜色角色以 `light-*` / `dark-*` 成对出现且角色集合相同，组件以 `<component>-light` / `<component>-dark` 成对定义；字体、间距、圆角与模式无关只定义一次。业务代码只用语义 token，不写颜色字面量。
- 生成与门禁：`npm run design:tokens` 调用 `@google/design.md@0.4.0` 的 `lint()` 读取 `DESIGN.md`，校验角色集合相等、无未解析引用、颜色 token 只能是 `primary` 或带模式前缀，确定性生成 `src/frontend/src/styles/design_tokens.css`（Tailwind 4 `@theme` 以亮色为默认值、`.dark` 覆盖全部颜色变量，另含字体 / 字号 / 圆角 / 间距变量）；产物入库。`npm run design:lint`（error 或 warning 任一非零即失败）、`npm run design:check`（产物与重新生成结果不一致即失败）与 `design:tokens` 三条命令接入 `scripts/run_gates.sh` 前端阶段。
- Tailwind 4：`@tailwindcss/vite` 插件，删除 PostCSS / autoprefixer / `tailwind.config.ts`；`@theme` 以 `--color-*: initial` 重置默认调色板，只暴露设计 token。Space Grotesk Variable 与 IBM Plex Mono 经 `@fontsource` 自托管，中文回退栈按 4.4 节，产物不引用外部字体 / 图标 CDN。
- 主题运行时：偏好 `system` / `light` / `dark`，默认 `dark`，存 `localStorage` 的 `cbrowser.theme`；`public/theme_boot.js` 为 `<head>` 中外链经典脚本，首帧前设置 `<html>` 的 `dark` / `light` class 与 `color-scheme`，页面不含内联脚本；`system` 模式监听 `prefers-color-scheme` 变化。UI 主题与 Profile 的 `color_scheme` 互不影响。
- 应用外壳：导航侧栏（环境 / 代理 / 会话 / 设置；品牌标识；底部运行中环境数随 SSE 更新，并放主题切换、语言切换、退出登录），可折叠为 72px 图标栏、200–360px 拖宽，状态存 `cbrowser.sidebar.width` / `cbrowser.sidebar.collapsed`；窄屏（\<1024px）改抽屉。Runtime Coordinator 错误用全局警示横幅；保留 iframe 焦点守卫（宿主外部点击时 `blur()` iframe）。
- 基础组件在 `src/frontend/src/shared/ui/`：按钮族（primary / secondary / ghost / danger / connect / stop 及 hover / disabled / 小号）、IconButton、Input、Select、SearchField、Checkbox、Switch、StatusBadge、GroupChip、ProtocolChip、RegionCode、Table 原语、EmptyState、Banner、Toast（全局单实例）；Dialog / DropdownMenu / Popover / Tooltip 基于 Radix 原语（焦点陷阱、焦点归还、Esc 关闭与 ARIA 角色由原语保证）。
- 登录页与设置页按设计系统重做；设置页新增平台字体区块，数据来自 `GET /api/v1/font-sets`，完整性不一致显示告警。

## 7. 环境管理界面（t037）

- 首页 `/` 由 `features/profiles/EnvironmentListPage.tsx` 承载（替换 t036 占位页）；`app/router.tsx` 的 `/profiles/:profileId/{config,files,automation,maintenance}` 四个路由统一指向新 `ProfileDetailPage`（按 `useLocation().pathname` 渲染对应 Tab），`/profiles/:profileId` 仍重定向 `config`。`/proxies` 由 t038 代理库页面承载（见第 8 节），`session` 占位页留给 t039。

- 数据装配：`ProfileResponse` 只含 `group_id` / `proxy_id`，列表的分组名、网络列（代理名 / 协议 / 地区）与分组使用环境数由 `useGroupsQuery` / `useProxiesQuery` 与 `useProfilesQuery` 客户端 join；五态与 last activity 来自 `ProfileRuntimeResponse`（`useProfileRuntimeQuery` / `useRuntimeSnapshot` 与 SSE 缓存）。`ApiClient` 新增 `groups` / `proxies` / `fontSets` 三个命名空间，只复用 `request()` 与生成类型，不手写契约。

- `useEnvironmentFilters`（URL 查询参数）、`useEnvironmentLayout`（localStorage）、`useBatchActions`（逐项 `mutateAsync` + `useActionKeyMutation` 自动独立幂等键）、`useGroupReorder`（`POST /groups/reorder`）为纯逻辑 / hooks 层；页面组件只用语义 token 类与 `shared/ui` 组件族。

- 共用 `ProfileForm`（`features/profiles/ProfileForm.tsx`）区分元数据字段与运行配置字段，驱动 `ConfigTab` 的待应用判据；`SharedProfileBanners` 在四个标签共享搜索失败与待应用提示，沿用 `useApplyDisplaySettingsMutation` 阶段跟踪。

- 测试：`npm test` 先 `tsc -p tsconfig.test.json`（严格类型、生成类型完整线形状夹具）再 Vitest；页面测试在 ApiClient 边界注入每例独立 stub 并走真实 hooks。`src/test_setup.ts` 提供 Radix 所需 `ResizeObserver` / `matchMedia` polyfill。旧页面与其测试整体删除，按 D16 在 task `progress.md`「测试处置清单」逐用例登记去向。

- 真实栈无头 E2E「新建 → 启动 → 打开会话」走新建弹窗 UI（`env-new` → `env-new-dialog` → `profile-form-name` → `profile-form-submit`），不再直接 POST API 伪造创建。

- 尺寸语义 token（`DESIGN.md` 的 `## Container sizes`）：`--container-*` 独立于 `--spacing-*`，业务代码只用 `max-w-dialog`/`w-dialog-width`/`max-w-panel`/`max-w-page`/`min-w-menu`/`h-control-sm` 等语义类；`npm run design:lint` 的 `assertNoSizeTokenHijack` 禁止命名尺寸类（`max-w-lg` 等会被 spacing token 劫持）与任意尺寸值（`max-w-[...]`）。

## 8. 代理库界面（t038）

- `/proxies` 由 `features/proxies/ProxyListPage.tsx` 承载（替换 t036 占位页）；`ProxyListToolbar` 提供搜索（名称 / host / 地区标签，大小写不敏感）与协议筛选（http / https / socks5）可组合，`ProxyTable` 列 = 名称 / 协议（`ProtocolChip`）/ 地址（`MonoValue` 的 `host:port`）/ 认证（有 / 无，文字不可只靠颜色）/ 地区（`RegionCode` + 标签）/ 使用环境数 / 操作。页面沿用环境列表的全量客户端过滤、无分页。
- 使用环境数为 `<Link to={"/?proxy=" + id}>`：`useEnvironmentFilters` 已读 `proxy` URL 参数，环境列表无需改动即可按代理筛选（AC-006）。
- 添加 / 编辑用受控 `Dialog`（`ProxyFormDialog`），字段校验与 `ProxyCreateRequest` / 后端 `models.py` 一致（name 1..255、host 1..512、port 1..65535 整数、country_code 空或 2 字母大写、scheme 枚举），错误在字段旁与底部汇总。保存成功后 `proxyKeys.lists()` 与 `profileKeys.lists()` 失效，列表即时更新。
- 密码只写：`ProxyResponse` 不含 password；编辑态只凭 `has_password` 显示「已设置，留空不修改」，提供「清除密码」。提交 `ProxyUpdateRequest.password` 三态——留空**省略该键**、`null` 清除、字符串设置；已存密码不进入表单 state / DOM / query cache / URL，关闭弹窗清空本地 state。
- 「从 URL 粘贴」由纯函数 `features/proxies/parseProxyUrl.ts` 解析 `scheme://[user[:pass]@]host[:port]`：scheme 白名单归一、IPv6 方括号、百分号编码账密解码、port 1..65535；失败返回判别联合的错误结果，**已填字段保持不变**。表驱动测试覆盖合法与非法形态。
- 删除保护：`used_by_count > 0` 时删除按钮禁用并提示先改绑；后端 409 响应体为 `{"detail":{"code":"proxy_in_use","used_by_count":N}}`（非 `ErrorResponse`），前端从 `ApiError.detail` / `.data` 取引用数展示，**不依赖 `errorCode`**。
- 带认证 SOCKS5（AC-007）：依据 `docs/findings/d031_authenticated_socks5_supported.md` 与 ADR 023（`decisions.md`），CloakBrowser 0.6.4 / Chromium 146 支持带认证 SOCKS5；后端无任何 socks5 拒绝分支、API 永不返回该 422。表单直接允许 `socks5` + 用户名/密码提交，**无降级路径、无「引擎不支持」提示**；所有后端错误统一走 `describeError()` 结构化展示。task.md 中「引擎不支持时阻止提交」沿用旧假设、前提不成立，不实现推测性代码（详见 `docs/specs/proxy_management.md` 第 5 节）。
- `ApiClient.proxies` 在 t037 的 `list`/`get` 之外补 `create`/`update`/`remove`（照 `groups` 同构、写操作带 `Idempotency-Key`），`useProfilesQuery.ts` 补 `useCreateProxyMutation` / `useUpdateProxyMutation` / `useDeleteProxyMutation`（`useActionKeyMutation` 独立幂等键、失效代理与 Profile 列表）；`shared/api/types.ts` 补 `ProxyCreateRequest` / `ProxyUpdateRequest` 生成类型别名，不改 generated 产物。
- i18n 在 `i18n.tsx` 的 en / zh 同步补 `proxy*` 键，`i18n.test.tsx` 键集相等与非空兜底。
- 真实栈无头 E2E（`tests/e2e/test_proxy_library_e2e.py`，`serial`）覆盖 AC-008：UI 新建代理 → 环境引用该代理 → 启动 → 浏览器出站经本地记录代理（日志 `PROXY_GET`），不依赖公网。

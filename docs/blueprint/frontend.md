# 前端

前端为 `src/frontend` 下的 React 19.3 + Vite 8 单页应用，由 Caddy 作为静态资源托管，只经 `/api/v1` 与 `/stream/{profileId}/signal` 访问后端。t017 已删除 v1 前端树、旧测试、noVNC 类型与仅其使用的依赖；路由只保留 `react-router` 8 单包实现（t033 由 `react-router-dom` 换包，DOM API 全部由单包导出）。

## 1. 外壳与数据

- 路由（React Router 8 单包，`app/router.tsx`，plan 5.1 / t036）：`/login`、`/`（环境管理）、`/session`（工作台入口）、`/session/:profileId`（工作台会话页，目标由 path param 决定）、`/profiles/:profileId`（重定向到 `config`）、`/profiles/:profileId/{config,files,automation,maintenance}`、`/proxies`（代理管理）、`/settings`（t074 起 `<Navigate to="/" replace />` 旧链接回落，设置改为 `AppLayout` 内宽弹窗）；旧路由 `/?profileId=`、`/profiles/new`、`/automation/:profileId` 直接删除（`/profiles/new` 显式置于 `:profileId` 之前并回落首页 catch-all），导航与环境链接均为真实 `<a href>`；会话失效（401）或登出时跳转 `/login`。t039 已启用全局颜色门禁（见 testing.md）。
- API 客户端（`shared/api/client.ts`）使用 `openapi-typescript` 从 `schemas/openapi/cbrowser_v1.json` 生成的类型（`npm run generate:api`，产物 `shared/api/generated/`），禁止手写与后端重复的响应类型。写方法带 `X-CSRF-Token`（取 `cbrowser_csrf` Cookie）；运行意愿为 `PATCH /api/v1/profiles/{id}/runtime/desired-state`。普通请求默认 30s、上传 5min、长操作 2min 超时；出站三入口（ApiClient 请求、SSE 连接、Artifact 下载链接）统一按最终解析 URL 做同源判定，跨源（含反斜杠/协议相对变体）在附带凭据前拒绝，客户端无可配置的跨源基地址（无 baseUrl/url 配置项，测试以同源夹具接入）；`ApiError` 携带 `errorCode`、`retryable` 与 `details`（统一错误契约，见 conventions.md §7；旧 `detail` 字段已删除）。登出请求失败时本地认证状态与内存 CSRF token 一律清除，各注销调用点显式处置 logout 的 rejection，不产生 unhandled rejection。请求取消分两种语义：调用方外部取消产生不可重试的 `cancelled` 错误，内部超时产生可重试的 `timeout` 错误，请求结束后必须释放外部信号监听。页面与布局经 `ApiClientContext`（`shared/api/client_context.tsx`）取得 `AppProviders` 下发的客户端实例并透传给数据 hooks，禁止在组件中直接引用单例；写操作的幂等键（`Idempotency-Key`）在每次 `mutate`/`mutateAsync` 调用边界生成、该次逻辑动作的自动重试全程复用同一键，复合动作（如应用显示设置的 stop→start）由单次动作键派生各自的操作键；**例外：Profile 创建的幂等键绑定到当前打开的创建弹窗**（见第 7 节），关闭重开复用同一键直至创建成功。SSE 遇 401 停止重连并触发登出，流结束时 flush 解码器残留事件。
- 服务器状态由 TanStack Query 5 管理。SSE 事件 id 为 `<epoch>:<seq>`（epoch 为 API 进程随机值）：同 epoch 且在历史窗口内的 `Last-Event-ID` 只补发缺失事件，其余情况（API 重启、旧格式、超窗口）发送完整初始快照。运行状态经 `GET /api/v1/events`（SSE，事件 `runtime_state`，fetch 流式读取以携带 Cookie）增量合并进查询缓存（含 `last_coordinator_error`）并使 Profile 列表查询失效重取；断线自动重连，前端不保存任何控制状态。SSE 事件类型即生成的 `ProfileRuntimeStatusEvent`：投递前逐字段验证核心字段与状态枚举，畸形或未知事件只进错误通道不投递；连接以代次（generation）隔离，重复 `start` 不新增连接，旧代次不得投递、报错或重连，`stop` 后不得重连。引用数据变更事件（t056 A31）：分组或代理写成功后服务端经同一 SSE 流推送 `groups_changed` / `proxies_changed`（`entity_id` 为变更实体、无实体时为 null），前端使对应列表查询与 Profile 列表查询失效重取；探测不发事件。
- 运行协调错误（Supervisor 未配置或不可达）经 `useRuntimeSnapshot` 聚合 runtime 查询缓存（随 SSE 更新），在外壳主内容顶部以 `runtime-coordinator-error` 警示横幅（`Banner`）显式展示，运行意愿保持不变。
- `/profiles/:profileId/files` 为 Artifact 管理页：经 `shared/api/client.ts` 的 `artifacts` 方法列出、上传、下载、删除文件，支持图标化的列表/卡片视图切换，写操作带 CSRF。多文件上传顺序执行、首个失败即停止，失败文案须给出已成功数、失败文件名与未处理数（不输出文件内容）。
- 设置页的健康状态只呈现其真实探测对象——Control API 健康检查，并提供退出登录入口。
- `/profiles/:profileId/automation` 为自动化页：经 `automation.status()` 展示授权 WS 端点、运行状态、运行实例、Supervisor 配置状态与 `Authorization: Bearer <cbat_...>` 头格式；不展示任何明文凭证。
- Profile 详情页提供复制与重置面板：复制可选仅配置或含浏览器状态（运行中禁用状态复制并提示停止）；重置面板明确列出将清除的 Cookie、站点数据、缓存、登录状态与指纹身份，并说明保留设置与 Artifact。
- 会话、页头与 Profile 主表单文案经 `i18n.tsx` 的 `t()`（en/zh）；语言偏好存储键为 `cbrowser.locale`，切换时同步 `document.documentElement.lang`。翻译键集由 en 字典派生（`TranslationKey = keyof typeof en`），zh 字典以 `satisfies Record<TranslationKey, string>` 编译期对齐，并有键集相等测试兜底；新增文案必须 en/zh 同步补键。

## 2. 页面独立状态

- 每个 Chrome 标签页独立维护会话目标（`/session/:profileId` path param，写入 `sessionStorage` 的 `cbrowser.session.target` 供侧栏「工作台」导航回跳）、ViewerConnection 与会话阶段；切换 Profile 只改变本页目标与连接。禁止跨标签页共享的 `localStorage.currentProfileId`。
- 页面与布局的动作状态（error/pending）按动作目标 Profile 隔离呈现（`scopeMutationToProfile`）：常驻组件（AppLayout、会话页、详情页）只显示目标为当前 Profile 的动作状态，其他 Profile 的错误、pending 与迟到响应不进入当前视图，本地结果横幅不跨 Profile 携带。
- 同一 Profile 可有多个页面同时连接，全部为 controller；前端不维护租约或唯一控制者状态。
- 页面关闭、刷新或切换目标只关闭自身 PeerConnection 与信令，不调用 Profile stop；只有用户明确停止 Profile 才停止 Browser。
- 详情面板展开状态持久化在 `cbrowser.session.details_open`（刷新后保持），默认收起（t039）。
- 全屏隐私浏览器（专注模式）隐藏导航侧栏与页头，鼠标悬停顶部边缘显示悬浮退出工具条，**不用 Esc 退出**（Esc 与常用组合键留给远端 iframe）；专注状态经 `SessionFocusProvider` 提升到 `AppProviders`（`app/providers.tsx` 的 `AuthProvider` 内）供 `AppLayout` 与会话页共享读取，专注期间不条件卸载 iframe 与 `useBrowserSession`，不重建连接、不中断远端输入（t039）。
- `/session` 会话入口在本标签页无目标时列出运行中环境（真实链接）；侧栏「工作台」导航在本标签页已有目标时回跳该会话（t039）。

## 3. Selkies 官方客户端薄适配

- 官方 Selkies 2.2.1 Web 客户端由 `scripts/vendor_selkies_web.py` 从固定 wheel（SHA-256 固定）解出并校验文件清单（`config/selkies/selkies_web_sha256.txt`，不依赖测试目录），放到 `src/frontend/public/selkies/`（gitignore）。`npm run build` 的 `prebuild` 自动执行 vendor，`postbuild` 自动执行 `scripts/verify_frontend_dist.py`，校验 `dist/selkies/index.html` 的 adapter tag 顺序、`selkies_adapter.js` 的经典 IIFE 形态与全部官方资源哈希；生产镜像在 COPY `dist/` 后必须再次运行同一校验，禁止绕过。会话页以同源 iframe `/selkies/index.html?profileId=` 加载。
- 适配层唯一实现为 `features/browser-session/adapter.ts`，经 `vite.selkies.config.ts`（入口 `selkies_adapter_entry.ts`）构建为经典 IIFE 脚本 `dist/selkies/selkies_adapter.js`，vendor 脚本只在官方 `index.html` 的 module bundle 之前注入 `<script src="./selkies_adapter.js">`，不携带任何适配代码。职责：信令改写到 `/stream/{profileId}/signal`；不改写官方 HELLO、`client_tab_id`、`resume_key`；复制标签页经 Web Locks 探测冲突并重映射身份，不踢原页（d007）；锁定远端分辨率/DPR，外部 resize 不改变远端；新窗口强制 `noopener`；键盘焦点守卫（未聚焦时 `stopImmediatePropagation()` 阻断向远端转发，配合宿主 `AppLayout` 在外部点击时主动 `blur()` iframe，隔离宿主浏览器全局快捷键）。媒体为同机直连，适配层不再处理 RTC/TURN 配置或 ICE restart。生产代码不暴露任何测试用全局；测试需要的 DataChannel/PeerConnection 探针由测试夹具写入复制后的 Selkies 目录，并在 `selkies_adapter.js` 之前插入 `<script>`，保证探针先于 adapter 包装原生接口。
- 页面可见性只由官方客户端每 Peer `STOP_VIDEO`/`START_VIDEO` 处理（计划 9.3），适配层丢弃 activity/visibility 帧，不向 Gateway 上报。
- 宿主与 iframe 的唯一生产统计契约为 `window.__getWebRTCStats()`；适配层另向父窗口发送 `CBROWSER_PC_STATE`、`CBROWSER_WS_CLOSE`、`CBROWSER_LIFECYCLE_STALE` 与 `CBROWSER_WEB_LOCKS_UNAVAILABLE` 消息。
- 页面不持有任何 Selkies token；controller token 由 Stream Agent 在转发 HELLO 时代注入（d024）。

## 4. 会话阶段与恢复

- 阶段：`checking_runtime`、`runtime_not_ready`、`stopping`、`connecting_signaling`、`signaling_failed`、`web_locks_unavailable`、`ice_failed`、`media_waiting`、`media_no_frames`、`connected`、`reconnecting`、`error`（以 `SessionStage` 类型为唯一权威，不存在 `connecting_ice` 阶段）。运行时检查经统一 API 客户端：401 由鉴权层跳转登录，网络/服务不可达进入带原因的 `runtime_not_ready`；Web Locks 不可用进入专门阶段。阶段呈现分级（t061）：等待态（`checking_runtime`、`connecting_signaling`、`media_waiting`、`reconnecting`）只显示轻量指示，不渲染居中诊断表或操作按钮；故障态（`signaling_failed`、`ice_failed`、`media_no_frames`、`web_locks_unavailable`、`error`）保留诊断与适用重连动作；`runtime_not_ready` 保留启动与查看状态；`stopping` 只显示停止提示与查看状态入口。不出现无解释黑屏，不新增媒体回退通道。
- 会话页加载状态严格区分：加载中、加载失败（显式错误加重试）、Profile 不存在（仅真实 404）、已停止待启动；请求失败不得呈现为已停止。语言切换只改变文案，不得重跑运行时检查或重置已连接会话（效果依赖不含翻译函数身份，经 ref 读取最新翻译）。
- 诊断取自 `RTCPeerConnection` 状态与 `getStats()`（选中候选对类型、RTT、接收字节）。
- Page Lifecycle `freeze`/`resume` 与 bfcache `pageshow` 后检查信令与 PeerConnection，失效则重建 iframe（同一 `client_tab_id`，官方客户端生成新 `resume_key`）；信令 WS 异常关闭时先给官方客户端 5 秒以原 `resume_key` 重连，5 秒恢复检查确认媒体仍健康（`stats.connected`）即收敛回 `connected`、不重建 iframe——诊断快照不变时诊断源不发新信号，健康收敛出口就在此检查内，且受 generation fence 保护，旧代次迟到结果不覆盖当前状态；媒体不健康才重建（t061）。
- ICE：`failed` 立即进入 `ice_failed`；`disconnected` 持续 5 秒（`iceDisconnectGraceMs`）才判失败，期间恢复则不报。
- 宿主只接受来自本会话 iframe（`event.source`）且同源的 postMessage；适配层向父窗口发送时指定具体 origin。
- 会话目标由 `/session/:profileId` 决定；导航侧栏不再列 Profile，「工作台」项在本标签页已有目标时回跳该会话，否则进 `/session`。
- 剪贴板：`ClipboardPermissionHint` 在宿主会话页中按需探测权限（与 `/selkies` iframe 同源），拒绝/提示状态显示可执行说明；自身不调用 `navigator.clipboard` 读写，复制粘贴同步由 iframe 内官方 Selkies seamless 客户端完成（decisions 012）。
- 音频：每页静音按钮经官方 `pipelineControl` audio（`STOP_AUDIO`/`START_AUDIO`）；音频状态（`audio_status.ts`）由 getStats 推导，与视频阶段独立：`normal`/`muted`/`no_track`/`no_data`/`unknown`，内容静音不判故障。
- 显示设置：运行时 `config_version` 与 Profile 当前配置版本不同即显示待应用提示与“应用并重启”（经 API stop → running）。该动作带阶段跟踪（按动作键保存 stop 前实例与 start 已发出标记）：自动重试先观测运行时再续跑——stop 已生效不重发不重等、start 已生效而响应丢失时收敛到新实例的 running（不等待 stopped、不停止或重建新实例）、未生效步骤以同一操作键续跑、状态查询持续失败有界报错。
- 会话页画面区由 `SessionPage` 承载：iframe 铺满并仅保留 `xs`（4px）外边距、不绘制模拟浏览器框（ADR 003/006）。阶段呈现按本节分级矩阵由 `SessionStagePanel` 渲染（等待态轻量指示、故障态居中诊断面板），`connected` 不显示面板；阶段清单以 `SessionStage` 类型为权威（t061）。页头 transport 状态与详情面板统一经单一映射显示本地化文案（ready/recovering/failed/unknown 均有中英文案，未知或缺失值回落本地化「未知」，不显示原始机器码）；环境切换器触发器与下拉列表内每个环境项前均渲染状态指示灯（圆点），触发器不带文字状态徽标，顶栏文字运行状态只出现一次，各环境文字状态徽标保留在下拉条目内（t061+）。
- 详情面板（`SessionDetailsPanel`）右侧 300px、默认收起，分环境 / 代理 / 指纹 / 运行状态四区（全部标签与平台/字体包名称均显示本地化可读文案，不暴露内部 ID），每个值可复制（t039+）。开关只有页头详情按钮一个：面板内无标题与第二开关，关闭时不渲染、不占宽度（t061）。
- 剪贴板权限提示（`ClipboardPermissionHint`）、音频状态与诊断浮层按设计系统重建、行为语义不变：剪贴板只探测权限不读写本机剪贴板，音频经官方 `pipelineControl` 的 `STOP_AUDIO` / `START_AUDIO`，诊断取自 `RTCPeerConnection` 状态与 `getStats()`（t039）。
- 旧会话页组件（`BrowserSessionPage` / `BrowserSessionView` / `BrowserSessionMount` 及旧测试）整体删除；`data-testid` 全部改 `sess-*` 结构（旧 `browser-session-*` / `session-*` / `diag-*` 弃用），会话 E2E 与组件测试选择器同步改写（t039）。
- 旧页面全部替换后启用全局颜色门禁：`npm run design:lint` 的 `--lint` 经 `runLintSources(sources)` 同时跑尺寸断言与颜色断言，扫描前端源码颜色字面量与默认调色板类发现即失败、无豁免（见 testing.md「t039 全局颜色门禁」）。
- t073：工作台顶栏状态徽标直接显示带主语的本地化文案（`sessHeaderEnv*` / `sessHeaderTransport*`），不再用 `sr-only` 隐藏主语；`SessionDetailsPanel` 左列短词仍用 `sessTransport` / `transportState*` 不受影响。`status-badge-running-*` 指向 success 语义色，环境切换器 running 圆点改 `bg-success`，深色顶栏上彩色文字与语义描边通过 WCAG AA。`SearchField` 改 Flex 组合（外层容器承载边框 / 聚焦高亮，内部图标槽 + 无边框 input），从架构上根除图标与文本重叠。

SSE 消费契约（t022）：快照帧为订阅私有数据，携带 live 基点事件 id（快照时刻最后一条实时事件序号），不进入共享历史；重连以基点 id 经 Last-Event-ID 续传，服务端回放基点之后的实时事件，无缺口无倒退；窗口不足时服务端以全量快照显式重建。Profile 详情页呈现独立的默认搜索初始化状态：`search_defaults.state == "failed"` 时显示与浏览器可用性分离的失败提示与重试按钮（调用 `POST /profiles/{id}/runtime/search-defaults/retry`），不要求重启浏览器。

分层观测消费（t026）：runtime 响应与 SSE 事件携带 `transport` 分层观测（browser/stream/transport 状态与最近错误），前端校验与缓存同步规则与 `search_defaults` 同构：结构不合法的事件整帧拒绝，事件未携带字段时保留缓存值。会话信令呈现区分恢复与失败：首次连接的信令异常关闭（含 1006）在 transport 为 recovering 时呈现恢复中并在有界窗口（默认 30 秒）内轮询运行状态，transport 变 ready 后重连、明确 failed 或窗口耗尽才呈现信令失败；已连接后的断开沿用既有 resume 语义不变。

SSE 按事件类型分发（t040）：`shared/api/sse.ts` 解析 `event:` 行按类型路由，`runtime_state` 走原运行状态通道，新增 `profile_preview` 走 `onPreviewEvent`；`useProfilesQuery.ts` 订阅 preview 事件刷新 runtime 缓存。`profile_preview` 只实时扇出、绝不进入 runtime 事件重放环，SSE 重连后的 runtime 状态重放不受缩略图事件数量影响（AC-003）。`ProfileRuntimeResponse.preview_captured_at` 无预览为 null，首屏据此显示图片或占位，**无值不请求图片**；`EnvironmentCard` 以 `?v=<captured_at>` 作为图片 URL 版本参数触发刷新，404 / onError 回退占位。

## 5. 测试

- Vitest 5（`npm test --prefix src/frontend`，无需 `NODE_OPTIONS`）覆盖 API 客户端、SSE、路由与会话组件；`npm test` 先执行 `test:types`（`tsc -p tsconfig.test.json`）对全部测试文件做严格类型检查，再运行 Vitest。页面与守卫测试在 ApiClient 边界注入每例独立 stub 并走真实 hooks 接线，禁止 mock 数据 hooks 模块、禁止对共享单例做方法赋值；测试夹具与事件字面量须使用生成类型的完整线形状。
- 真实栈 E2E 用构建产物 + 官方 Selkies 资源，经 Caddy/API（启用 Runtime Coordinator）/Supervisor/Gateway/Browser/Stream 与无头 Google Chrome（无 coturn）：`tests/e2e/test_frontend_app_e2e.py`、`test_frontend_session_e2e.py`、`test_frontend_session_vendor.py`。所有浏览器测试必须无头。

## 6. 设计系统与应用外壳（t036, t047, t059+）

- 设计权威：仓库根 `DESIGN.md`（google-labs-code/design.md alpha 格式，YAML front matter）。章节顺序 Overview / Colors（含 `### Modes`）/ Typography / Layout / Elevation & Depth / Shapes / Components / Contrast / Do's and Don'ts。`primary` 与 `brand-*`（logo 渐变三色与 `brand-ink` 墨色）为品牌色，其余颜色角色以 `light-*` / `dark-*` 成对出现且角色集合相同，组件以 `<component>-light` / `<component>-dark` 成对定义；字体、间距、圆角与模式无关只定义一次。Shapes 正文含逐 component 的圆角映射表，Contrast 正文含 components 之外文字 / 图形角色对声明表，两表均为机读门禁输入。组件尺寸规格（控件高度、浮层宽度、图标尺寸阶梯 `icon-xs`–`icon-3xl` 等）写在 components 条目的官方 `height` / `width` / `size` 字段。业务代码只用语义 token，不写颜色字面量。
- 生成与门禁：`npm run design:tokens` 调用 `@google/design.md@0.4.0` 的 `lint()` 读取 `DESIGN.md`，校验角色集合相等、无未解析引用、颜色 token 只能是 `primary`、`brand-*` 或带模式前缀、字体栈由 `body-md` 与 `mono-md` 派生，确定性生成 `src/frontend/src/styles/design_tokens.css`（Tailwind 4 `@theme` 以亮色为默认值、`.dark` 覆盖全部颜色与阴影变量，另含字号、字重、行高、字距、圆角、间距与阴影变量），并按品牌 token 生成 `public/` 下 logo 与 favicon 五件资产（几何不变、仅颜色取 token 值）；产物入库。
- Tailwind 4：`@tailwindcss/vite` 插件，删除 PostCSS / autoprefixer / `tailwind.config.ts`；`@theme` 以 `--color-*: initial` 重置默认调色板，只暴露设计 token。Inter Variable 与 JetBrains Mono Variable 经 `@fontsource` 自托管，中文回退栈按 4.4 节，产物不引用外部字体 / 图标 CDN。
- 主题运行时：偏好 `system` / `light` / `dark`，默认 `dark`；`public/theme_boot.js` 为 `<head>` 中外链经典脚本，首帧前设置 `<html>` 的 `dark` / `light` class 与 `color-scheme`，页面不含内联脚本；`system` 模式监听 `prefers-color-scheme` 变化。UI 主题与 Profile 的 `color_scheme` 互不影响。t074 起权威值持久化于控制面 `settings` 表（`ui.theme` / `ui.locale`，经 `/api/v1/settings` 同步），`localStorage` 的 `cbrowser.theme` / `cbrowser.locale` 降级为首帧防闪烁镜像（见 §9）。
- 应用外壳：导航侧栏顶部为主导航（环境管理 / 代理管理 / 工作台），底部左下角「设置」按钮直接打开 `SettingsDialog` 宽弹窗（不离开当前页面上下文）；侧栏可折叠为 72px 图标栏（折叠态隐藏折叠按钮，点击左上角品牌图标展开）、200–360px 拖宽（双击重置默认宽度），状态存 `cbrowser.sidebar.width` / `cbrowser.sidebar.collapsed`；窄屏（\<1024px）改抽屉。Runtime Coordinator 错误用全局警示横幅；保留 iframe 焦点守卫（宿主外部点击时 `blur()` iframe）。
- 基础组件在 `src/frontend/src/shared/ui/`：按钮族（primary / secondary / ghost / danger / connect / stop 及 hover / disabled / 小号）、IconButton、Input、Select、SearchField、Checkbox、Switch、StatusBadge、GroupChip、ProtocolChip、RegionCode、Table 原语、EmptyState、Banner、Toast（全局单实例）；Dialog / DropdownMenu / Popover / Tooltip 基于 Radix 原语。
- 登录页按设计系统重做；t074 设置改为宽弹窗（§9），平台字体区块展示人类可读字体包名称与本地化平台名称，完整性不一致时展开异常明细。
- t073：`Colors` 新增成对 `light/dark-success` 与 `light/dark-success-soft`，`Contrast` 表声明 success 对各类 surface 的 text（≥4.5:1）与 graphic（≥3.0:1）校验行；`status-badge-running/transition/error` 的 `textColor` 改指 `*-success` / `*-warning` / `*-danger` 彩色语义文字并加语义描边，`stopped` 保持中性。`Container sizes` 新增 `dialog-sm/md/lg/xl` 梯度（生成器产出 `--container-*` 与 `max-w-dialog-*`）。`Dialog` 新增 `size` prop 与 header 固定、body 内部平滑滚动；`IconButton` 新增 `variant="danger" | "warning"`；基础组件只用语义 token。

## 7. 环境管理界面（t037+）

- 首页 `/` 由 `features/profiles/EnvironmentListPage.tsx` 承载；`app/router.tsx` 的 `/profiles/:profileId/{config,files,automation,maintenance}` 四个路由统一指向 `ProfileDetailPage`（按 `useLocation().pathname` 渲染对应 Tab），`/profiles/:profileId` 重定向 `config`。
- 数据装配：`ProfileResponse` 只含 `group_id` / `proxy_id`，列表的分组名、代理列（仅显示代理名或「直连」）、备注 Tooltip 图标与本地化平台/时区由 `useGroupsQuery` / `useProxiesQuery` 与 `useProfilesQuery` 客户端 join；五态与 last activity 来自 `ProfileRuntimeResponse`（`useProfileRuntimeQuery` / `useRuntimeSnapshot` 与 SSE 缓存）。不向用户展示 `#0001` 内部显示编号。
- `useEnvironmentFilters`（支持搜索、状态、分组、系统平台 `windows`/`macos`、代理 `direct`/具体代理与排序，同步 URL 查询参数）、`useEnvironmentLayout`（localStorage，由图标按钮切换列表/卡片视图）、`useBatchActions`（逐项 `mutateAsync` + `useActionKeyMutation` 自动独立幂等键）、`useGroupReorder`（`POST /groups/reorder`）为纯逻辑 / hooks 层；「分组管理」作为独立按钮置于工具栏右侧。
- 共用 `ProfileForm`（`features/profiles/ProfileForm.tsx`）区分元数据字段与运行配置字段，驱动 `ConfigTab` 的待应用判据；种子范围（`100000 – 999999`）通过感叹号图标悬浮 Tooltip 展示，重摇种子使用图标化刷新按钮；选择代理、切换语言或切换系统平台时自动对齐对应的时区、语言、平台字体包（展示可读名称而非 SHA256 哈希）与默认分辨率。
- t073：环境列表与卡片仅在 `profile.timezone` 显式非空时显示时区，隐藏默认 / 自动匹配时区；`env-running-count` 改为带标签的 `runningProfiles` 文案与绿色运行圆点，不再渲染裸数字。`EnvironmentRowActions` 每行仅 1 个带文字主按钮（运行中蓝色「打开」、非运行「启动」），详情 / 编辑 / 复制 / 停止 / 删除收敛为带 `aria-label` 与 `title` 的纯图标按钮，运行态显示 warning 停止、非运行态显示 danger 红色删除。新建 `ProfileCreateDialog` 与编辑 `ProfileEditDialog` 统一用 `Dialog size="lg"` 宽弹窗 + `ProfileForm` 多列布局，编辑走 `diffProfileValues` 差分更新；列表行「编辑」直接唤起编辑弹窗，「配置详情」跳转 `/profiles/:id/config`，详情页页头也提供编辑入口。

## 8. 代理管理界面（t038+；t074 重写）

- `/proxies` 由 `features/proxies/ProxyListPage.tsx` 承载；`ProxyListToolbar` 提供搜索（名称 / host / 国家名 / 城市 / 地区标签，大小写不敏感）、协议筛选（http / https / socks5）与**独立「国家筛选」「城市筛选」**（城市选项随所选国家联动去重），右侧提供批量闪电测速按钮（`Zap` 图标）、图标化列表/卡片视图切换器与「添加代理」主按钮。`useProxyFilters` 把 `q` / `scheme` / `country` / `city` 存 URL SearchParams、`useProxyLayout` 把 `list` / `card` 存 `localStorage`，刷新后筛选、视图、国家、城市、延迟、状态全部保留；联动筛选须在一次 `setFilters({country, city})` 内原子提交，两次 `setSearchParams` 会同 tick 互相覆盖。
- `ProxyTable` / 卡片展示 **8 列** = 名称（备注以感叹号图标悬浮 Tooltip 展示）/ 协议（`ProtocolChip`）/ 地址（`MonoValue` 的 `host:port`）/ 国家 / 城市 / 状态 / 使用环境 / 操作，**不展示认证列**，也不再把「位置 + 状态」混为一列。状态列：`pending` 显示探测中；`ok` 仅以绿色语义文字显示 `{latency_ms}ms`（无延迟显示「可用」），不显示额外状态数字；`failed` 以红色语义文字显示脱敏 `observation_error_code`；`unknown` 显示中性未测速提示。删除按钮用 t073 的 `IconButton variant="danger"`。
- 使用环境列只渲染 `0 个` / `1 个` / `2 个` 等计数（去掉「查看环境」文案）：`0` 为不可点 `<span>`；`1` 点击经 `useNavigate` 直接进入对应环境配置页；`>=2` 点击先打开 `ProxyUsedByPopover` 列出全部环境（含名称与绿/灰运行点）再点选进入。计数按 `useProfilesQuery` 的 `proxy_id` 客户端分组。
- 添加 / 编辑用 `Dialog size="lg"`（`ProxyFormDialog`），默认只显示「代理链接」「备注」与只读观测区（国家 / 城市 / 出口 IP / 延迟 / 失败原因）；高级设置默认折叠，链接与高级字段由同一端点值对象双向同步。`SessionDetailsPanel` 的代理位置同步展示国家 · 城市 · 延迟与失败态。
- 单条与批量闪电测速调用 `ApiClient.proxies.probe`（`POST /api/v1/proxies/{id}/probe`，无 body）+ `useProbeProxyMutation`；**彻底删除 `speedResults` state 与 `Date.now() - startedAt` 伪测速**，延迟只取后端持久化的 `ProxyResponse.latency_ms`。`observation_status === "failed"` 即使 HTTP 200 也提示错误 toast、不误报成功；`ok` 显示成功 toast。批量测速按后端结果汇总失败数。

## 9. 网络访问与设置（t042；t054 只读；t074 改为宽弹窗）

- t074 起 `/settings` 不再是独立窄页：侧栏「设置」按钮直接打开 `SettingsDialog`（`Dialog size="lg"`，`AppLayout` 内），不离开当前页面上下文；旧 `/settings` 路由 `<Navigate to="/" replace />`。弹窗分三大块：外观（主题 `system`/`light`/`dark`）与界面语言（`en`/`zh`）；Control API 健康状态 + 退出登录 + 只读网络访问摘要；平台字体包清爽卡片（默认隐去 `source_version` 技术哈希，仅完整性异常时展开 `problems`）。网络访问区块只读：显示当前访问地址与端口（取 `window.location`），并注明网络配置在部署期确定、运行期不可更改。
- 偏好持久化：`theme` / `locale` 经 `GET /api/v1/settings` 与 `PATCH /api/v1/settings` 读写控制面数据库（`settings` 表）；`AppProviders` 内 `SettingsSync` 在登录后 hydrate、后续变更写服务端（`I18nProvider` / `ThemeProvider` 保持不依赖 auth 与 API client）。未登录页（`/login`）只读写本地，不发 401 请求。清缓存或重新登录后偏好保持。
- 会话静音：`useBrowserSession` 的 `audioMuted` 持久化到按标签页隔离的 `sessionStorage`（key `cbrowser.session.audio_muted.${profileId}`），刷新本标签页保持静音，双标签页打开同 Profile 互不串扰。

## 10. 前端状态一致性（t058）

- Profile 编辑只提交与初始值不同的字段（`ProfileForm` 以差分驱动提交）；字段分类（元数据 / 即时 / 运行配置）以后端 `repository.py` 的三分常量为准，经生成类型同步，前后端逐值一致。
- 会话阶段与错误文案的单一权威是 `runtimeQuery`：`SessionPage` 把 `runtimeQuery.data?.observed_state` 作为唯一 `runtimeState` 传入 `useBrowserSession`。
- 错误边界分层：`ErrorBoundary.componentDidCatch` 经前端日志通道记录；路由内容由 `RouteErrorBoundary` 包裹，随路由切换复位。

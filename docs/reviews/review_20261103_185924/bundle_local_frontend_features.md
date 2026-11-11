# bundle_local_frontend_features

## responsibilities

- 前端业务功能层：auth（登录页、next 跳转清洗、AuthProvider 会话状态）、profiles（会话页/详情页/新建页 + react-query 数据层 + SSE 缓存同步）、browser-session（会话视图与状态机 hook、Selkies iframe 适配器、音频状态推导与 pipelineControl、剪贴板权限探针、诊断浮层）、artifacts（Profile 文件页与上传/删除 mutations）、automation（CDP 端点页）、settings（语言与健康状态页）
- 随附的 feature 测试：会话状态机与适配器契约、音频状态、剪贴板桥、profiles 数据层（含 apply/retry/wait 专项）、页面 i18n，以及一支放在本单元的 SSE 客户端硬化测试（回环 HTTP 实测）

## interfaces

- BrowserSessionView(props: profileId/clipboardSync/initialStage/diagnostics/errorMessage/onCheckRuntimeStatus/apiClient) 与 useBrowserSession 返回的 stage/diagnostics/errorMessage/reloadKey/reconnect/audioMuted/toggleAudio
- iframe 适配器与宿主页契约（adapter.ts 文件头声明）：宿主调用 window.\_\_getWebRTCStats()；iframe 向 parent 发送 CBROWSER_PC_STATE / CBROWSER_WS_CLOSE / CBROWSER_LIFECYCLE_STALE / CBROWSER_WEB_LOCKS_UNAVAILABLE，目标 origin 为具体同源 origin
- 数据层 hooks：useProfilesQuery/useProfileQuery/useProfileRuntimeQuery、八个 profile mutations、useApplyDisplaySettingsMutation（stop→wait→start 复合操作）、useProfileEventsSync(ProfileEventsClient)；artifacts 与 automation 的 query/mutation hooks
- 经 shared/api/client 的 REST 面：/api/v1/profiles\*、/artifacts（含 downloadUrl 直链）、/automation、/auth/\*、/health；写请求带 Idempotency-Key 与 CSRF（由 client 统一处理）

## dependencies

- frontend_shell 单元的 shared/api（client.ts、sse.ts、types.ts 与 generated OpenAPI 类型）、i18n、app 路由与 BrowserSessionMount
- @tanstack/react-query（缓存/失效/重试）、react-router-dom、lucide-react
- iframe 内的 Selkies 官方客户端（外部运行时依赖）：适配器靠覆写 WebSocket/RTCPeerConnection/RTCDataChannel.prototype.send 与之协作

## flows

- 会话建立：BrowserSessionPage 按 runtime observed_state 分流（running→挂载 BrowserSessionView；否则展示启动页，启动失败有错误渲染）→ useBrowserSession 先查 runtime 状态，再由 postMessage 事件 + 1s stats 轮询驱动 stage 状态机（checking_runtime→connecting_signaling→media_waiting→connected，失败分支 ice_failed/signaling_failed/media_no_frames/web_locks_unavailable，ICE disconnected 有 5s 宽限）
- 标签仲裁：适配器在 HELLO 时用 Web Locks 以 selkies_tab_id 抢锁，冲突时换新 id 并以 1000 关闭当前连接（不踢原标签）；Web Locks 不可用时发 CBROWSER_WEB_LOCKS_UNAVAILABLE 并以 1008 关闭，宿主显示专用诊断阶段（无降级路径）
- SSE 同步：ProfileEventsClient 事件 → useProfileEventsSync 先 setQueryData 补丁 runtime 缓存（事件不带 config_version，缓存不存在时不合成条目），再 invalidate runtime 与 list 触发权威重拉
- 显示设置应用：update 保存后若 runtime.config_version 与 profile.current_config_version 不一致，详情页提示并可一键 apply（stop→轮询等 stopped（120s）→setDesiredState running→轮询等 running（180s），轮询连续失败 3 次与超时分别报错）
- 工件上传：文件页顺序逐个 mutateAsync 上传，每个文件经 onSettled 后换新 Idempotency-Key；首个失败即中止并显示错误

## constraints

- AC-003：会话组件卸载只清理定时器并把 iframe 置 about:blank，绝不调用 stop 或 desired-state PATCH（有专门测试以 fetch 间谍断言）
- postMessage 双向校验：宿主侧校验 event.source===iframe.contentWindow 且 origin===location.origin（有伪造 source/origin 的负测试）；适配器侧向 parent 发送时使用具体的 location.origin
- mutation 的 Idempotency-Key 在 React Query 重试间必须复用（shouldRetryRequest + 专项 retry 测试锁定），settle 后才换新
- 剪贴板桥只探权限状态、从不读写剪贴板内容（测试以 readText/writeText 间谍断言）；适配器不暴露任何测试钩子全局量（\_\_sentDataChannelMessages 等，测试逐个断言 undefined）
- 全单元无 dangerouslySetInnerHTML/eval/innerHTML 注入面，无 console.log 残留；自动化页展示的 token_header 为后端返回的模板字符串（测试值为 'Authorization: Bearer \<cbat\_...>' 占位形态），前端只做展示

## decisions

- 音频状态与视频 stage 解耦：deriveAudioStatus 以 3s 窗口的字节/包增长判 no_data，静默 DTX 不算故障；静音走官方 pipelineControl 消息而非自建通道，且只作用于本页 iframe
- 详情页表单以 dirtyFields 保护未保存编辑不被后台刷新覆盖（有专项测试）；会话页启动 mutation 失败显式渲染 session-start-error（有专项测试）
- Web Locks 不可用即整会话不可用（专用阶段 + 1008 关闭），不做无仲裁降级——与同机直连、官方 Chrome 客户端的定位一致，属有意取舍
- runtime 检查遇 401 时停留在 checking_runtime 交由 auth 层跳转（测试锁定），不自行跳登录

## evidence

- src/frontend/src/features/browser-session/adapter.ts:1-19 文件头契约与实现逐项对应（postMessage 类型、\_\_getWebRTCStats、无测试钩子）
- src/frontend/src/features/browser-session/useBrowserSession.ts:208-297 postMessage 校验与 stage 迁移；:356-360 卸载清理注释与实现
- src/frontend/src/features/profiles/useProfilesQuery.ts:237-260 waitForRuntimeState 的失败/超时区分；:324-365 SSE 缓存补丁不合成 runtime 条目
- src/frontend/src/features/auth/redirect.ts:1-13 next 路径清洗规则
- src/frontend/src/shared/api/sse_hardening.test.ts:22-71 以真实回环 HTTP 服务器验证 401 停连与尾事件 flush（被测 sse.ts 属 frontend_shell 单元，此处仅作随附测试审阅）

## uncertainties

- host_entry.tsx 是测试宿主页入口（tests/fixtures/frontend_probe/host_builder.py 引用），其是否被排除在生产 bundle 之外取决于构建接线（frontend_shell/contracts_deploy 单元范围），本单元仅能确认生产入口代码未 import 它
- f_frontend_features_01 的实际影响取决于后端对「同 Idempotency-Key、不同请求体/路径」的处理语义（拒绝、回放首响应或忽略），属后端单元范围，本单元只能确认前端确实会产生这种组合
- ProfileDetail/ProfileNew 表单只可编辑 name/proxy/分辨率/tags，其余字段（fingerprint_seed、gpu_family、humanize、geoip、clipboard_sync、auto_launch、launch_args、extension_paths）创建时取 DEFAULT_PROFILE_CREATE_VALUES 且 UI 无编辑入口；是否为 spec 有意收敛，本单元无规格材料可判，留待 docs_current 单元
- automation.data.token_header 的真实内容由后端生成（backend_api_auth 单元范围）；若后端某部署下返回真实 token 而非模板占位，该页会明文展示——前端侧无从区分，未立 finding

## Findings

- [Low][70] src/frontend/src/features/profiles/useProfilesQuery.ts:60-77, src/frontend/src/features/artifacts/useArtifacts.ts:35-53 — Idempotency-Key 按 hook 实例共享：同一实例的并发异参调用会复用同一把 key

    - ID: f_frontend_features_01; verification: static
    - Evidence: 全部 mutation hooks（profiles 八个 + apply 的 stop/start + artifacts 两个）都用单个 useRef 保存 actionKey，mutationFn 无论 variables 是什么都取 `(actionKey.current ??= newIdempotencyKey())`，仅在 onSettled 时清零; useMutation 的 mutate/mutateAsync 在前一次未 settle 时再次调用会并发执行 mutationFn，两次不同目标/不同请求体的写操作（如先启动 profile A、未完成时又对 profile B 发起 setDesiredState）将携带同一 Idempotency-Key; 现有 UI 缓解：已知调用点（AppLayout、BrowserSessionPage、详情页）多以 isPending 禁用按钮，但这是调用点约定而非 hook 契约；hook 本身不按 variables 区分 key; 对照正面证据：useProfilesQuery.retry.test.tsx 锁定了「React Query 重试间复用同一 key」这一预期语义，问题只在跨调用复用
    - Impact: 后端若按 key 做去重/回放，第二个异参写操作可能被当作第一个的重试而被吞掉或返回首个响应，造成用户操作静默失效；影响触发需要同实例并发异参调用，当前 UI 下窗口较窄，故定 Low。
    - Fix: key 应按逻辑动作生成：mutationFn 内以 variables（目标 id + 操作 + 关键载荷哈希）为作用域生成/缓存 key，或为每次 mutate 调用生成 key 并仅在 React Query 内部重试间复用（把 key 存入 mutation 的 meta/context 而非 hook 级 ref）。

- [Low][75] src/frontend/src/features/auth/redirect.ts:9-11 — sanitizeNextPath 只拦截精确的 /login，/login/ 与大小写变体可造成登录页自跳转循环

    - ID: f_frontend_features_02; verification: static
    - Evidence: redirect.ts:9-11 仅以 path === "/login" 判断回环，未处理尾斜杠与大小写；react-router 路由匹配默认大小写不敏感且容忍尾斜杠; LoginPage.tsx:19,48-50：已登录时直接 <Navigate to={target}>，target 为 /login/ 或 /LOGIN 时会再次命中登录路由并再次 Navigate，形成渲染级重定向循环; 其余清洗项完备：// 前缀、/\\ 前缀、控制字符均已拦截，loginRedirectPath 对 /login 本身也返回纯 /login
    - Impact: 已登录用户打开被构造的 /login?next=/login/（或大小写变体）链接时标签页陷入重定向循环；属自伤型问题、无跨用户影响，故定 Low。
    - Fix: 比较前先规范化：path.toLowerCase() 并去除尾斜杠后再与 "/login" 比较，或对一切以 /login 开头后接 /,?,# 边界的路径返回 null。

- [Low][80] src/frontend/src/features/profiles/BrowserSessionPage.tsx:22-25 — runtime 查询失败被当作「未运行」：会话页对 runtime 端点错误无任何呈现

    - ID: f_frontend_features_03; verification: static
    - Evidence: BrowserSessionPage.tsx:23 只解构 useProfileRuntimeQuery 的 data/isLoading，未取 error；:74 以 runtime?.observed_state === "running" 判活; runtime 查询失败（500/网络错误）时 runtime 为 undefined 且 isRuntimeLoading 为 false，页面落入未运行分支，展示带 Launch 按钮的「运行时未就绪」页，把后端故障误报为已停止状态; 对照：同页 profile 查询失败有 !profile 分支、启动 mutation 失败有 session-start-error 渲染，唯独 runtime 查询错误无分支
    - Impact: 后端 runtime 面故障时用户看到的是可点击启动的停止态页面，点击后才可能从 mutation 错误间接得知，状态呈现失真；不影响数据，故定 Low。
    - Fix: 解构 runtime 查询的 error 并增加错误分支（展示错误与重试），或至少在 runtime 为 undefined 且非加载中时不渲染 Launch 而渲染状态未知。

- [Low][85] src/frontend/src/features/browser-session/BrowserSessionView.test.tsx:253-303 — 会话视图测试多处依赖真实定时器与多秒睡眠，慢且在负载下易抖

    - ID: f_frontend_features_04; verification: static
    - Evidence: 「transient ICE disconnect」用例真实等待 1000ms + 5500ms（:253-269），「persistent ICE disconnect」waitFor 超时 8000ms（:272-287），「WS_CLOSE rebuild」同样 8000ms（:290-303），三个用例均声明 12_000ms 的 it 超时; 被测的 5s ICE 宽限与 5s WS 健康检查都走生产常量、未注入可缩放的测试时钟；useBrowserSession 已提供 iceDisconnectGraceMs/mediaTimeoutMs 注入点但用例未用; 同文件其余用例以 waitFor/act 同步驱动，风格不一致
    - Impact: 单文件即贡献 20s 量级的真实等待，CI 负载下 8s 的 waitFor 与 5s 宽限的相对时序可能翻转导致偶发失败，削弱套件可信度；非生产缺陷，故定 Low。
    - Fix: 对时序用例注入 iceDisconnectGraceMs 的小值（如 50ms）或使用 vi.useFakeTimers 并推进时钟；保留一条真实定时器的冒烟用例即可。

- [Low][85] src/frontend/src/features/profiles/BrowserSessionPage.test.tsx:8-32, src/frontend/src/features/profiles/ProfileDetailPage.test.tsx:16-25 — 两个页面测试整体 mock 掉 useProfilesQuery 模块，页面主要流程无测试覆盖

    - ID: f_frontend_features_05; verification: static
    - Evidence: BrowserSessionPage.test.tsx 以 vi.mock("./useProfilesQuery") 固定返回 stopped 运行时，全文件仅一条用例（启动错误渲染）；running→挂载会话视图、Launch 点击触发 setDesiredState、无 profileId 的引导分支均未覆盖; ProfileDetailPage.test.tsx 同样整模块 mock，全文件仅一条用例（dirty 字段不被刷新覆盖）；保存提交、删除确认、duplicate/reset 面板、display-pending 与 apply 按钮均未覆盖; 形成对照：同单元的 hooks 层测试（useProfilesQuery 四个文件）在 client 边界 mock 并覆盖扎实，缺口集中在页面层
    - Impact: 页面级回归（如分流条件、按钮接线、确认流程）只能靠 e2e 或人工发现；mock 的是被测页面自身的数据层模块，测试对真实 hook 契约变化不敏感。按测试视角启发式属覆盖缺口，定 Low。
    - Fix: 页面测试改为在 ApiClient 边界 stub（参照 artifacts/automation 页面测试的做法），补 running 分流、Launch、删除/复制/重置与 apply 的行为用例；保留现有 dirty 字段用例。

- [Info][90] src/frontend/src/features/browser-session/clipboard_bridge.ts:22-38 — readClipboardPermission 已无生产调用方，仅被自身测试引用

    - ID: f_frontend_features_06; verification: static
    - Evidence: 全仓 grep：readClipboardPermission 仅出现于 clipboard_bridge.ts 定义与 clipboard_bridge.test.tsx 两条断言；生产组件 ClipboardPermissionHint 使用的是同文件 watchClipboardPermission; 两者逻辑重复（同样的 granted/denied/prompt 归约），保留双份实现有漂移风险
    - Impact: 死代码与重复逻辑，增加维护面；无运行影响。
    - Fix: 删除 readClipboardPermission 及其测试，或让 watchClipboardPermission 复用同一归约函数并删除独立实现。

- [Info][95] src/frontend/src/features/browser-session/types.ts:48 — BrowserSessionViewProps.onSessionError 声明后从未被消费

    - ID: f_frontend_features_07; verification: static
    - Evidence: types.ts:48 声明 onSessionError?: (err: Error) => void；BrowserSessionView.tsx:16-26 的解构与 useBrowserSession 的 options 均不包含该字段，全仓无其他引用; 会话错误实际经 stage/errorMessage 呈现，回调通道不存在
    - Impact: 公开接口存在假承诺：调用方传入 onSessionError 会被静默忽略。无运行影响，故定 Info。
    - Fix: 从 BrowserSessionViewProps 删除该字段，或在 useBrowserSession 的错误迁移处真正调用它并补测试。

- [Info][70] src/frontend/src/features/browser-session/host_entry.tsx:11-24 — 测试宿主页入口 host_entry.tsx 位于生产 feature 源码树内且无 test-only 标识

    - ID: f_frontend_features_08; verification: static
    - Evidence: host_entry.tsx 把 onCheckRuntimeStatus 实现为仅置位 window.\_\_statusBtnClicked 的桩，并设置 \_\_cbrowserHostLoaded 全局量；文件无任何注释说明其为测试 fixture 入口; 其消费者是 tests/fixtures/frontend_probe/host_builder.py（前端 e2e 探针构建），生产入口（main.tsx/router）不 import 它；是否进入生产 bundle 取决于构建配置（不在本单元范围，未能确认）
    - Impact: 读者无法从源码判断该入口的性质；若构建接线误将其纳入出货产物，「查看状态」按钮将是无实际动作的假按钮。当前无证据表明已出货，故定 Info。
    - Fix: 在文件头注明 test-fixture-only 及其构建方（host_builder.py），或将其迁至 tests 侧目录由 fixture 构建引用。

- [Low][60] src/frontend/src/features/browser-session/useBrowserSession.ts:194-200 — runtime 检查 effect 依赖 t（i18n 函数），语言切换会重跑检查并回退会话 stage

    - ID: f_frontend_features_09; verification: static
    - Evidence: useBrowserSession.ts:157-200 的挂载检查 effect 依赖数组包含 t；checkRuntime 在 runtime 为 running/ready 时无条件 setStage("connecting_signaling")，不区分当前是否已 connected; t 的身份随 locale 变化而变化；会话存续期间若发生语言切换（t 换新），effect 重跑，已 connected 的会话会被打回 connecting_signaling 并闪现诊断浮层，直到下一次 stats 轮询（1s 内）以 framesDecoded>0 拉回 connected; 同文件 message/media-timeout 两处 effect 也依赖 t，但仅重注册监听/重置计时，后果可忽略；问题集中在检查 effect 的 stage 回写
    - Impact: 语言切换时会话画面短暂被浮层遮挡、stage 抖动一次；自愈且无数据影响，故定 Low、置信 60（t 身份变化的实际频率取决于 i18n 实现，属 frontend_shell 单元）。
    - Fix: 检查 effect 移除 t 依赖（错误文案改由渲染期按当前语言生成，或将 t 存 ref），或在 checkRuntime 写 stage 前判断 stageRef.current 已是 connected/media_waiting 时不回退。

- [Info][80] src/frontend/src/features/settings/SettingsPage.tsx:12-16 — 设置页以单个 /api/v1/health 探活结果冒充「网关与服务」整体状态

    - ID: f_frontend_features_10; verification: static
    - Evidence: SettingsPage.tsx:12-16 仅调用 defaultApiClient.health.check()（GET /api/v1/health）一次，二值映射 healthy/error; 页面文案（i18n systemGatewayControlApi/systemApiServicesStatus，测试锁定为「系统网关与控制 API」「v2 API 服务状态」）声称的是网关与多服务状态，单个 API 存活探针不能支撑该断言（网关/Supervisor/Stream 故障时此探针仍可能健康）
    - Impact: 运维误判面：状态徽章可能在媒体链故障时显示「正常」。纯呈现层问题，故定 Info。
    - Fix: 文案收窄为「控制 API 状态」，或改为聚合后端提供的多组件健康端点后再声称整体状态。

- [Low][85] src/frontend/src/features/browser-session/media_controls.test.tsx:32-44 — 音频 pipelineControl 测试未钉住 postMessage 的目标 origin

    - ID: f_frontend_features_11; verification: static
    - Evidence: media_controls.test.tsx:33-43 两次断言 postMessage 参数时，origin 只写 expect.any(String)；生产代码 sendAudioPipelineControl 传入的是 window.location.origin（audio_control.ts:14-23）这一具体值; 对照同单元 adapter_restart.test.ts 与 BrowserSessionView.test.tsx 对 parent postMessage 均断言了具体 origin 字符串，此处标准不一致; 若实现回归为 "\*" 通配 origin，该测试仍会通过
    - Impact: 跨窗口消息的目标 origin 是安全相关参数，测试未钉住意味着通配符回归不可检；属测试强度缺口，定 Low。
    - Fix: 断言改为 expect.objectContaining 后第二参数等于 window.location.origin 的具体值。

- [Info][85] src/frontend/src/features/artifacts/ProfileFilesPage.tsx:44-54 — 多文件上传中途失败时已上传文件无部分成功提示

    - ID: f_frontend_features_12; verification: static
    - Evidence: ProfileFilesPage.tsx:44-54 pickFiles 顺序上传，首个失败即 setError 并 return；此前已成功上传的文件只靠列表 invalidate 刷新可见，notice 不出现，用户无法从文案得知「N 个中已成功 M 个」; 失败文件之后的文件被静默跳过（ input 已清空，需重新挑选）
    - Impact: 批量上传部分成功时状态表达不完整，用户可能重复上传已成功文件（有 Idempotency-Key 与列表可见性兜底，后果轻微），故定 Info。
    - Fix: 失败时在错误文案中带上已成功计数，或改为逐个收集结果后统一汇总成功/失败明细。

## views

```json
{
  "contracts": {
    "reviewer": "e4bfa8eb-9593-4e49-a627-92ceae0b12fd",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "e4bfa8eb-9593-4e49-a627-92ceae0b12fd",
    "status": "completed"
  },
  "design": {
    "reviewer": "e4bfa8eb-9593-4e49-a627-92ceae0b12fd",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "e4bfa8eb-9593-4e49-a627-92ceae0b12fd",
    "status": "completed"
  },
  "performance": {
    "reviewer": "e4bfa8eb-9593-4e49-a627-92ceae0b12fd",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "e4bfa8eb-9593-4e49-a627-92ceae0b12fd",
    "status": "completed"
  },
  "security": {
    "reviewer": "e4bfa8eb-9593-4e49-a627-92ceae0b12fd",
    "status": "completed"
  },
  "tests": {
    "reviewer": "e4bfa8eb-9593-4e49-a627-92ceae0b12fd",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "src/frontend/src/features/artifacts/ProfileFilesPage.test.tsx",
  "src/frontend/src/features/artifacts/ProfileFilesPage.tsx",
  "src/frontend/src/features/artifacts/useArtifacts.ts",
  "src/frontend/src/features/auth/LoginPage.tsx",
  "src/frontend/src/features/auth/redirect.ts",
  "src/frontend/src/features/auth/useAuth.tsx",
  "src/frontend/src/features/automation/ProfileAutomationPage.test.tsx",
  "src/frontend/src/features/automation/ProfileAutomationPage.tsx",
  "src/frontend/src/features/automation/useAutomation.ts",
  "src/frontend/src/features/browser-session/BrowserSessionView.test.tsx",
  "src/frontend/src/features/browser-session/BrowserSessionView.tsx",
  "src/frontend/src/features/browser-session/ClipboardPermissionHint.tsx",
  "src/frontend/src/features/browser-session/SessionDiagnostics.tsx",
  "src/frontend/src/features/browser-session/adapter.ts",
  "src/frontend/src/features/browser-session/adapter_restart.test.ts",
  "src/frontend/src/features/browser-session/audio_control.ts",
  "src/frontend/src/features/browser-session/audio_status.test.ts",
  "src/frontend/src/features/browser-session/audio_status.ts",
  "src/frontend/src/features/browser-session/clipboard_bridge.test.tsx",
  "src/frontend/src/features/browser-session/clipboard_bridge.ts",
  "src/frontend/src/features/browser-session/host_entry.tsx",
  "src/frontend/src/features/browser-session/index.ts",
  "src/frontend/src/features/browser-session/media_controls.test.tsx",
  "src/frontend/src/features/browser-session/selkies_adapter_entry.ts",
  "src/frontend/src/features/browser-session/types.ts",
  "src/frontend/src/features/browser-session/useBrowserSession.ts",
  "src/frontend/src/features/profiles/BrowserSessionPage.test.tsx",
  "src/frontend/src/features/profiles/BrowserSessionPage.tsx",
  "src/frontend/src/features/profiles/ProfileDetailPage.test.tsx",
  "src/frontend/src/features/profiles/ProfileDetailPage.tsx",
  "src/frontend/src/features/profiles/ProfileNewPage.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.apply.test.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.retry.test.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.test.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.ts",
  "src/frontend/src/features/profiles/useProfilesQuery.wait.test.ts",
  "src/frontend/src/features/settings/SettingsPage.test.tsx",
  "src/frontend/src/features/settings/SettingsPage.tsx",
  "src/frontend/src/shared/api/sse_hardening.test.ts"
]
```

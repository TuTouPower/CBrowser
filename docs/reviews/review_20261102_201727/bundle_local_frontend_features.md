# bundle_local_frontend_features

## responsibilities

- v2 业务功能层（源码事实）：features/auth 提供基于 shared/api/client 的会话登录（密码→/api/v1/auth/login）与 open-redirect 防护（redirect.ts sanitizeNextPath）；features/profiles 提供 Profile 列表/详情/新建/会话页与 TanStack Query 数据层（useProfilesQuery，含 SSE 事件同步与显示设置应用的 stop→start 编排）；features/artifacts 提供 Profile 文件（产物）列表/上传/删除/下载页；features/automation 展示 CDP WebSocket 端点与 token header 模板；features/settings 提供语言切换与 /api/v1/health 状态。
- 浏览器会话层（源码事实）：features/browser-session 把官方 Selkies 客户端装入 iframe，adapter.ts 在 iframe 内猴补 WebSocket/RTCPeerConnection/RTCDataChannel，实现信令改写到 /stream/{profileId}/signal、Gateway rtc_config/ice_restart 控制帧处理、Web Locks 标签冲突防护、分辨率锁定与活动帧拦截；useBrowserSession 在宿主页聚合 postMessage 与 getStats 轮询，驱动会话阶段机与诊断覆盖层；audio_status.ts 从 getStats 样本推导音频状态；clipboard_bridge.ts 仅探测剪贴板权限（文档声明且源码核实：从不读写剪贴板数据）。
- 遗留 v1 层（源码事实）：lib/api.ts + hooks/useProfiles.ts 是旧版 /api/\* 客户端与轮询 hook，仍被单元外 components/\* 与 App.tsx 引用（frontend_shell 单元范围），与 v2 shared 客户端并存，非死代码。
- 文档声明与实现一致性：adapter.ts 头注释列出的行为（d022 配置保留、AC-002/004/007）在源码中均可对应定位；ProfileAutomationPage 展示的 token_header 经后端 domain/models.py:224 核实为静态模板字符串（kind：占位模板），非真实凭据，页面显示不构成泄漏。

## interfaces

- 对 shared/api/client（单元外）：ApiClient 的 profiles/artifacts/automation/auth/health 命名空间与 SessionResponse/LoginRequest 等生成类型（shared/api/types.ts 转出 generated/cbrowser_v1.d.ts），本单元核对字段使用与后端 domain 模型一致（AutomationEndpointResponse.token_header 默认模板、ProfileResponse.current_config_version、ProfileRuntimeResponse.config_version 均存在）。
- 对后端 HTTP：v2 全部走 /api/v1/\*（经 shared client，含 CSRF 与 401 回调）；例外是 useBrowserSession 直接 fetch /api/v1/profiles/{id}/runtime（见 finding f_frontend_features_04）。遗留 lib/api.ts 走 /api/profiles、/api/auth/login（{token}）等 v1 路由，由 src/backend/main.py 的 legacy 应用提供。
- iframe postMessage 协议：宿主→iframe 仅 pipelineControl 音频消息（audio_control.ts，targetOrigin=window.location.origin）；iframe→宿主 CBROWSER_PC_STATE / CBROWSER_WS_CLOSE / CBROWSER_LIFECYCLE_STALE，宿主校验 event.source===iframe.contentWindow 且 origin===同源后才处理（useBrowserSession.ts:213-219）。
- 组件公开面：BrowserSessionView（types.ts BrowserSessionViewProps）、useBrowserSession、installSelkiesClientAdapter 经 index.ts 导出，供 shared/components/BrowserSessionMount 与 vite.selkies.config 入口（selkies_adapter_entry.ts）消费。

## dependencies

- 单元外同仓：shared/api/client.ts、shared/api/sse.ts、shared/api/types.ts、i18n.tsx（全部 feature 组件依赖 useI18n）、app/providers.tsx（AuthProvider 与 SseSyncBridge 装配点）。
- 第三方：react、react-router-dom、@tanstack/react-query、lucide-react；测试用 vitest + @testing-library/react。
- 运行时外部面：官方 Selkies Web 客户端（/selkies/index.html iframe）、Gateway 信令 WebSocket、后端 v1/v2 API。

## flows

- 登录：LoginPage 提交密码→useAuth.login（shared client）→checkSession 刷新会话→navigate(sanitizeNextPath(next) ?? '/')；任意 v2 请求 401→client.onUnauthorized→AuthProvider 清除登录态。
- 会话打开：BrowserSessionPage 查 profile+runtime，running 时挂载 BrowserSessionMount→BrowserSessionView 建 iframe（/selkies/index.html?profileId&\_k=reloadKey）→useBrowserSession 先查 runtime 状态，再经 adapter 上报的 PC/WS 事件与 1s getStats 轮询推进 stage（checking_runtime→connecting_signaling→media_waiting→connected，或 ice_failed/signaling_failed/media_no_frames）。
- ICE 重启：Gateway 下发 ice_restart 控制帧→adapter 在 iframe 内 setRemoteDescription/createAnswer 并回 ice_restart_answer（adapter.ts:371-462）。
- 显示设置应用：ProfileDetailPage 保存后若 config_version 漂移，useApplyDisplaySettingsMutation 执行 stop→轮询至 stopped（≤120s）→setDesiredState(running)→轮询至 running（≤180s）（useProfilesQuery.ts:186-231）。
- 文件管理：ProfileFilesPage 经 useArtifacts 的 query/mutation 串行逐个上传，失败即停并报错；下载为 downloadUrl 直链锚点。

## constraints

- adapter.ts 的猴补必须保留官方 Selkies 的 HELLO/client_tab_id/resume_key 语义与 Gateway 下发的 iceServers/iceTransportPolicy（d022），且不得踢掉既有标签页（AC-002）；宿主卸载时禁止调用 stop/期望状态变更（AC-003，useBrowserSession.ts:394-407 注释与测试均固化）。
- redirect.ts 的 sanitizeNextPath 是登录后跳转的唯一净化点：必须拒绝 //、/\\、控制字符与 /login 自引用（源码已实现；由 frontend_shell 单元的 app/auth_guard.test.tsx 集成覆盖，本单元内无专测）。
- SSE 事件不携带 config_version，useProfileEventsSync 明确禁止为未缓存 profile 合成 runtime 条目（useProfilesQuery.ts:225-228 注释+测试固化）。

## decisions

- 双 API 栈并存是迁移期状态：仓库 docs 将 legacy 移除列为后续 task（t011_v2_remove_legacy，属 docs_current/archive 单元材料），本单元仅记录其在本单元内的重复与漂移风险（f_frontend_features_05），不判为缺陷性阻断。
- adapter 对 Web Locks 缺失采取 fail-closed（关闭信令 WS），与 AC-002 防重复标签冲突的设计目标一致，但可用性代价未见降级路径（f_frontend_features_02）。
- 剪贴板在 t014 drop 后仅保留权限提示（clipboard_bridge 只读探测），实际无缝同步依赖 Selkies 官方客户端自身，符合仓库最新提交的范围收缩。

## evidence

- 全单元 37 个文件逐文件通读（含 5 个大文件 adapter.ts 575 行、useBrowserSession.ts 423 行、BrowserSessionView.test.tsx 570 行）。
- 跨单元核对：shared/api/client.ts（CSRF/401/端点路径）、shared/api/sse.ts（start/stop 语义）、shared/api/types.ts 与 generated/cbrowser_v1.d.ts（AutomationEndpointResponse/ProfileResponse 字段）、backend domain/models.py:216-224（token_header 静态默认值）、backend api/v1/automation_router.py:41-58（automation_status 构造）、backend main.py:530-578 与 config/docker/entrypoint.sh:27（legacy 应用仍被该入口启动）、app/providers.tsx:8-18（SseSyncBridge 负责 stop 的装配事实）。
- XSS 探针：grep dangerouslySetInnerHTML/innerHTML/eval/document.write 于 features/hooks/lib 无命中；所有服务端字符串均以 React 文本节点渲染（artifact.name、container_path、errorMessage 等）。
- git HEAD 核对：5136766aceb2a7bb5a7b6c766e1d4f29b36439d5（与任务给定一致）。

## uncertainties

- 静态审阅未运行测试/构建：BrowserSessionView.test.tsx 等测试的实际通过状态未验证，tests 视角结论基于测试代码本身的可观察性与时序写法。
- lib/api.ts 对应的 legacy 前端（App.tsx/components）是否仍在发布产物中作为入口，由 frontend_shell 单元与 contracts_deploy 单元（Docker 入口）共同决定；本单元仅确认源码与 legacy 后端路由仍成对存在。
- adapter 记录 DataChannel 报文的实际内容构成（键入事件/剪贴板帧的协议细节）取决于官方 Selkies 客户端实现，未在本单元源码内证实到单个报文字段；f_frontend_features_01 按 Selkies 输入通道的公开语义判定。

## Findings

- [Medium][85] src/frontend/src/features/browser-session/adapter.ts:77-95 — adapter 把全部 DataChannel 发送报文（含键入/剪贴板类输入通道数据）原文记录到 window 全局数组

    - ID: f_frontend_features_01; verification: static
    - Evidence: adapter.ts:77 初始化 win.\_\_sentDataChannelMessages=[]；81-95 重写 RTCDataChannel.prototype.send，对每一个发送报文先 pushBounded(..., DATA_CHANNEL_HISTORY_LIMIT=500) 再调原生 send，无通道 label 过滤、无内容脱敏; Selkies 的键盘/鼠标输入与剪贴板同步均经 DataChannel 发送，该数组因此会留存最近 500 条输入类报文原文（含在远端页面键入的口令、剪贴板文本的可能）; 数组挂在 iframe window 全局上，iframe 内任意脚本（含官方客户端自身脚本与未来注入脚本）可直接读到；adapter.ts 头注释将其定位为诊断用途
    - Impact: 远端会话中的敏感输入在页面内存中长期留存并扩大可读面；一旦 iframe 上下文出现 XSS 或第三方脚本注入，留存的输入历史可被整表窃取。本机单人部署降低了利用概率，但与该产品隐私隔离定位相冲突。
    - Fix: 在 adapter.ts 的 send 包装中只记录元数据（通道 label、字节数、时间戳），或对 input/clipboard 通道跳过内容记录；如需保留内容级诊断，改为显式调试开关开启且默认关闭。

- [Medium][70] src/frontend/src/features/browser-session/adapter.ts:118-140 — Web Locks 不可用时 adapter 直接关闭信令 WebSocket，非安全上下文/旧浏览器下会话功能整体不可用且无降级

    - ID: f_frontend_features_02; verification: static
    - Evidence: adapter.ts:121-124 acquireLock 在 navigator.locks.request 不存在时 reject(new Error("Web Locks required")); adapter.ts:262-289 的 HELLO 拦截路径对 acquireLock 的 catch 一律 ws.close(1008, "tab_identity_unavailable")，没有无锁降级发送 HELLO 的路径; Web Locks API 仅在 Secure Context 提供；经局域网 IP 的 http 访问或旧版浏览器将稳定触发该分支
    - Impact: 在任何非安全上下文部署形态下，远程浏览器会话永远无法建立信令连接，用户只看到信令失败。与 AC-002 的 fail-closed 意图一致，但可用性悬崖没有文档提示或回退（例如单标签场景直接放行）。
    - Fix: 在 adapter.ts acquireLock 失败路径增加受控降级：无 Web Locks 时仍发送 HELLO 并依赖服务端 tab 冲突处理，或至少让宿主诊断层区分『浏览器不支持 Web Locks』与一般信令失败并给出明确文案。

- [Medium][90] src/frontend/src/features/profiles/BrowserSessionPage.tsx:69-71 — 会话页启动浏览器的 mutation 失败被完全吞掉，页面无任何错误提示

    - ID: f_frontend_features_03; verification: static
    - Evidence: BrowserSessionPage.tsx:69-71 handleLaunch 仅调用 setDesiredStateMutation.mutate(...)，全文未读取 setDesiredStateMutation.error，也没有为启动失败渲染任何 role=alert/错误区; 按钮仅以 isPending 与 observed_state==='starting' 控制 disabled（131-132 行），失败后静默恢复可点击状态; 对照同仓 ProfileDetailPage 对 applyDisplayMutation.error 有专门渲染（该文件 317-327 行），说明本页是遗漏而非统一约定
    - Impact: 后端拒绝启动（如协调器错误、授权/容量问题）时用户反复点击 Launch 无任何反馈，只能去详情页看 last_coordinator_error；与详情页已有的错误呈现能力不一致。
    - Fix: 在 BrowserSessionPage 渲染 setDesiredStateMutation.error 的错误条（复用 runtime-coordinator-error 的样式与 testid 约定）。

- [Low][80] src/frontend/src/features/browser-session/useBrowserSession.ts:128-167 — 运行时检查绕过 shared ApiClient 且网络层失败被当作『运行时就绪』继续连接信令

    - ID: f_frontend_features_04; verification: static
    - Evidence: useBrowserSession.ts:132 用裸 fetch(url, {credentials:"include"}) 查 /api/v1/profiles/{id}/runtime，不经 shared ApiClient：401 时不会触发 client.onUnauthorized 的登出流，而是落入 !resp.ok 分支显示『运行时状态检查失败（HTTP 401）』阶段; useBrowserSession.ts:161-165 catch 分支把任何 fetch 异常（API 不可达、网络中断）统一 setStage("connecting_signaling")，注释自承是为本地 mock/直达测试放行（'In local mock or direct view tests, ignore fetch failure'）; 生产环境中 API 短暂不可达会先误判就绪、随后以更难定位的信令失败呈现
    - Impact: 会话过期与后端不可达两种常见故障的诊断信号被扭曲：前者不跳登录，后者跳过就绪检查直接进入信令阶段，排障成本上升；测试便利逻辑泄漏进生产路径。
    - Fix: 改走 ApiClient.profiles.getRuntime（或至少复用其 401 处理）；catch 分支区分测试注入与真实失败，真实网络失败应进入 runtime_not_ready/error 并显示原因。

- [Low][85] src/frontend/src/lib/api.ts:146-319 — 本单元内并存两套 API 客户端与两套 Profile 数据层，类型与端点已发生漂移

    - ID: f_frontend_features_05; verification: static
    - Evidence: lib/api.ts 定义独立 Profile/ProfileFile/LaunchResult 等类型与 /api/*（非 v1）端点、{token} 登录；shared 客户端（单元外）定义 /api/v1/* 与 {password} 登录、CSRF、生成类型；hooks/useProfiles.ts 以 3s 轮询消费前者，features/profiles/useProfilesQuery.ts 以 react-query+SSE 消费后者; 漂移实例：lib/api.ts:300-304 updateSettings 的返回类型误写为 SystemStatus（PUT /api/settings 的语义应为设置对象）；lib Profile 含 v2 已不存在的 vnc_ws_port/cdp_url/status 字段且缺 current_config_version; 两套栈均仍被引用：单元外 App.tsx 与 components/\* 引用 lib/api（grep 核实），Docker 入口 config/docker/entrypoint.sh:27 仍启动 legacy backend.main:app
    - Impact: 同一 Profile 概念两份手写类型定义，任一端点/字段变更需双改且无编译期交叉校验；新贡献者难以判断哪套是权威（仓库已将 legacy 移除列为后续 task，本项记录本单元内的漂移事实与维护成本）。
    - Fix: 在 legacy 移除 task 落地前，至少修正 updateSettings 返回类型，并在 lib/api.ts 与 hooks/useProfiles.ts 文件头标注 legacy 状态与权威替代（shared/api + features/profiles），防止新功能继续写入旧栈。

- [Low][80] src/frontend/src/features/browser-session/adapter.ts:398-418 — ice_restart 的 ICE 收集等待在超时胜出时不移除 icegatheringstatechange 监听器

    - ID: f_frontend_features_06; verification: static
    - Evidence: adapter.ts:401-417 等待收集完成的 Promise 中，removeEventListener 只在 check() 观察到 complete 时执行；setTimeout(resolve, 3000) 超时路径直接 resolve，监听器永久留在 activePC 上; 每次 ICE 重启走超时路径都会再累积一个 check 闭包监听
    - Impact: 长会话多次 ICE 重启后监听器缓慢累积，且陈旧 check 在后续收集完成时仍会被触发执行（仅做 resolve 空转）。影响小但属明确的资源清理缺口。
    - Fix: 把 removeEventListener 提到统一的 settle 函数中，complete 与 timeout 两条路径都先移除监听再 resolve。

- [Low][75] src/frontend/src/features/browser-session/BrowserSessionView.test.tsx:250-345 — 会话视图测试用真实计时器等待 ICE 宽限期与 WS 重连（多处 5.5s+ 睡眠与 12s 超时），套件慢且对 CI 负载敏感

    - ID: f_frontend_features_07; verification: static
    - Evidence: BrowserSessionView.test.tsx 中 transient/persistent ICE 用例以 setTimeout 1000/5500ms 真实睡眠断言未误报/已报错，test 超时放宽到 12000ms；WS_CLOSE 重建用例同样等待 5s 内部定时器后断言（waitFor timeout 8000ms）; useBrowserSession 的宽限期本可注入（options.iceDisconnectGraceMs），但 WS 关闭后的 5000ms 健康检查定时器在 useBrowserSession.ts 中为硬编码，测试只能真等; 同文件其余用例使用同步 act+waitFor，时序策略不一致
    - Impact: 该文件单跑即需数十秒量级，CI 机器负载抖动时 5.5s 睡眠边界与 8s waitFor 容易偶发失败，侵蚀 AC-007 关键回归的可信度。
    - Fix: 对可注入的宽限期传小值（如 50ms）编写等价用例；WS 健康检查的 5000ms 提取为可注入选项或常量后在测试中覆写；或用 vi.useFakeTimers 限定在该 describe 内推进。

- [Low][85] src/frontend/src/hooks/useProfiles.test.ts:13-24 — useProfiles 测试的 api mock 缺失 resetProfile 等方法，hook 的 reset 路径无覆盖且在该 mock 下调用即抛错

    - ID: f_frontend_features_08; verification: static
    - Evidence: useProfiles.ts:118-130 暴露 reset() 并调用 api.resetProfile(id)；lib/api.ts:239-240 确有该方法; useProfiles.test.ts:13-24 的 vi.mock("../lib/api") 只提供 listProfiles/createProfile/updateProfile/deleteProfile/reorderProfiles/launchProfile/stopProfile/duplicateProfile，未含 resetProfile，测试文件也无任何 reset 用例; 其余 CRUD（create/update/remove/reorder/duplicate）均有用例，reset 是唯一未覆盖的公开动作
    - Impact: reset 是破坏性动作（清浏览器状态+重掷指纹种子），其 hook 层错误处理与刷新行为无回归保护；且 mock 与真实 api 表面不一致，后续补测时会先撞上 TypeError 噪声。
    - Fix: 在 mock 中补 resetProfile 并加一条用例：断言调用参数、成功后触发 listProfiles 刷新、失败时设置 error。

- [Low][70] src/frontend/src/features/profiles/ProfileDetailPage.tsx:38-50 — 详情页表单用 useEffect 无条件跟随 profile 查询结果回填，后台刷新会覆盖用户未保存的编辑

    - ID: f_frontend_features_09; verification: static
    - Evidence: ProfileDetailPage.tsx:38-50 useEffect 依赖 [profile]，每次 profile 对象变化即 setName/setProxy/setScreenWidth/setScreenHeight/setTagsInput 全量回填，无『表单脏』保护; profile 来自 react-query useProfileQuery；同页 update/duplicate/reset 等 mutation 的 onSuccess 都会 invalidate detail 查询，窗口聚焦等默认 refetch 也会产生新对象; 保存成功后回填是期望行为，但编辑中途的无关 refetch（如聚焦回填）会静默丢失输入
    - Impact: 用户编辑名称/代理/分辨率期间发生任意一次 detail refetch，未保存输入被服务器值覆盖且无提示；低频但属数据丢失型体验问题。
    - Fix: 仅在 profile.id 变化或首次加载时回填，或记录 dirty 字段集合，refetch 时只回填未被用户修改的字段。

- [Low][80] src/frontend/src/features/profiles/useProfilesQuery.ts:168-183 — 显示设置应用的轮询等待对单次 getRuntime 失败零容忍：已停机的 Profile 会因一次瞬时错误中断整个重启编排

    - ID: f_frontend_features_10; verification: static
    - Evidence: useProfilesQuery.ts:168-183 waitForRuntimeState 循环内 await client.profiles.getRuntime 无 try/catch，任何一次网络/5xx 错误直接抛出并终止 mutation; 调用链（186-210 行）先 stop 再 setDesiredState(running)：若第二段等待因瞬时错误抛出，Profile 已被停机且期望状态已改，UI 只显示 displayApplyFailed，无法区分『重启其实仍在进行』; 轮询间隔 500ms、窗口最长 120s+180s，期间出现一次瞬时失败的概率不可忽略
    - Impact: 偶发网络抖动即可让『应用并重启』误报失败并留下停机状态，用户需手动再启动；错误信息（超时时 JSON.stringify(last)）也不包含失败原因分类。
    - Fix: waitForRuntimeState 对 getRuntime 错误做有限重试/连续失败计数（如连续 3 次才终止），并在错误信息中区分轮询失败与超时未收敛。

- [Low][70] src/frontend/src/hooks/useProfiles.ts:24-29 — 遗留 useProfiles 的 3 秒轮询无在途请求串行化，慢响应可晚于乐观 reorder 落地并短暂回滚列表顺序

    - ID: f_frontend_features_11; verification: static
    - Evidence: hooks/useProfiles.ts:24-29 useEffect 中 setInterval(refresh, 3000) 与首帧 refresh 并发模型无 abort/序号保护，refresh 每次都以返回值整体 setProfiles; reorder（52-71 行）先乐观重排再 POST，其注释假设轮询只会『确认』服务器顺序；但 reorder 之前已发出、之后才返回的轮询响应携带旧顺序，会覆盖乐观结果直到下一轮轮询（约 3s 内可见顺序闪回）; create/update 等动作后的手动 refresh 与轮询 refresh 之间存在同样的后到先覆盖窗口
    - Impact: 列表顺序与内容出现秒级闪回/抖动；在 v1 栈仍作为入口的部署形态下是可观察的正确性瑕疵。属遗留栈，优先级随 legacy 移除而消失。
    - Fix: 为 refresh 增加在途计数/最新请求序号，仅接受最后发出请求的响应写回；或在 reorder 完成前暂停轮询写回。

- [Info][85] src/frontend/src/features/profiles/useProfilesQuery.ts:219-254 — useProfileEventsSync 自身 cleanup 只退订不停止 SSE 客户端，连接生命周期依赖调用方另行 stop

    - ID: f_frontend_features_12; verification: static
    - Evidence: useProfilesQuery.ts:219-254 useProfileEventsSync 在 effect 中 sseClient.start()，cleanup 仅 unsubscribe()，未调用 sseClient.stop()/close(); shared/api/sse.ts 的 start() 无幂等保护：重复 start 会新建 AbortController 并再开一条读取循环，旧循环失去引用无法中止; 当前唯一调用点 app/providers.tsx:8-18 的 SseSyncBridge 另用 effect 在卸载时调用 sseClient.stop()，实际装配下已被补偿；风险仅在于该 hook 被其他宿主复用时
    - Impact: 当前生产装配无实际泄漏；但 hook 的资源契约不自洽，未来在未配对 stop 的宿主中使用会产生重复 SSE 连接与双份重连定时器。
    - Fix: 把 stop 责任收进 useProfileEventsSync 的 cleanup（与 start 对称），并删除或保留 providers 侧的冗余 stop 均可（stop 幂等）。

## views

```json
{
  "contracts": {
    "reviewer": "538ba5c4-4db8-47bb-af15-97bae6f67834",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "538ba5c4-4db8-47bb-af15-97bae6f67834",
    "status": "completed"
  },
  "design": {
    "reviewer": "538ba5c4-4db8-47bb-af15-97bae6f67834",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "538ba5c4-4db8-47bb-af15-97bae6f67834",
    "status": "completed"
  },
  "performance": {
    "reviewer": "538ba5c4-4db8-47bb-af15-97bae6f67834",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "538ba5c4-4db8-47bb-af15-97bae6f67834",
    "status": "completed"
  },
  "security": {
    "reviewer": "538ba5c4-4db8-47bb-af15-97bae6f67834",
    "status": "completed"
  },
  "tests": {
    "reviewer": "538ba5c4-4db8-47bb-af15-97bae6f67834",
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
  "src/frontend/src/features/profiles/BrowserSessionPage.tsx",
  "src/frontend/src/features/profiles/ProfileDetailPage.tsx",
  "src/frontend/src/features/profiles/ProfileNewPage.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.test.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.ts",
  "src/frontend/src/features/settings/SettingsPage.test.tsx",
  "src/frontend/src/features/settings/SettingsPage.tsx",
  "src/frontend/src/hooks/useProfiles.test.ts",
  "src/frontend/src/hooks/useProfiles.ts",
  "src/frontend/src/lib/api.test.ts",
  "src/frontend/src/lib/api.ts"
]
```

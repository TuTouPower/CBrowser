# bundle_local_frontend_shell

## responsibilities

- 应用外壳：main.tsx 以 StrictMode 挂载 Providers + RouterProvider；router.tsx 定义 /login 与受 RequireAuth 保护的根布局及 6 条子路由，未知路径重定向到 /。
- 路由守卫与会话接线：RequireAuth 在会话检查 pending 时只渲染 loading、不发业务请求，未登录时经 loginRedirectPath 跳 /login 并保留 next 目标；providers.tsx 组装 QueryClient（staleTime 5s、retry=shouldRetryRequest、refetchOnWindowFocus）、I18nProvider、AuthProvider 与仅登录后挂载的 SSE 同步桥。
- 共享 API 客户端：client.ts 的 ApiClient 统一处理 baseUrl 拼接、同源校验、credentials include、写请求 CSRF 头（cookie cbrowser_csrf 或内存 token）、三级超时（30s/上传 300s/长操作 120s）、401 回调与结构化 ApiError（error/retryable/detail）；按 profiles/artifacts/automation/auth/health 分组暴露类型化方法。
- 实时事件客户端：sse.ts 的 ProfileEventsClient 用 fetch 流式解析 SSE，维护 Last-Event-ID 断线续传、1s 起步 1.5 倍退避（上限 30s）重连、401 停连回调。
- 国际化：i18n.tsx 内置 en/zh 两套字典（本轮机械核对 150/150 键双向完全对齐），locale 持久化于 localStorage cbrowser.locale 并迁移旧键 cbm.locale，t() 缺键回退 en 并支持 {param} 插值。
- 布局与样式：AppLayout 提供顶栏（会话状态点、启停、显示设置待应用徽标、语言切换、设置、登出）与可折叠 Profile 侧边栏（搜索过滤、按 ?profileId= 选目标）；tailwind.config.ts 定义 surface/border/accent/primary 色板（dark class 模式）；globals.css 提供基础层与组件类。
- 构建配置：package.json 的 build = tsc -b + 主 vite build + selkies adapter 的 IIFE 独立构建（vite.selkies.config.ts），prebuild/postbuild 钩子接 selkies vendor 校验与构建戳脚本；generate:api 从 schemas/openapi/cbrowser_v1.json 再生 generated/cbrowser_v1.d.ts，types.ts 以别名对外暴露。

## interfaces

- ApiClient.request<T>(endpoint, init, timeoutMs) 及 profiles/artifacts/automation/auth/health 分组方法（client.ts）
- ProfileEventsClient：start/stop/close、onEvent/onError、setOnUnauthorized、getLastEventId（sse.ts）
- types.ts 导出的 Schema 别名（ProfileResponse 等 10 个）与 DEFAULT_PROFILE_CREATE_VALUES
- AppProviders/Providers（可注入 queryClient/apiClient/sseClient 供测试）与 routes/RouteObject 树
- useI18n：{ locale, setLocale, t(key, params) }；TranslationKey = keyof en
- BrowserSessionMount({ profileId, clipboardSync, onCheckRuntimeStatus }) 转发到 features 的 BrowserSessionView

## dependencies

- react 19 / react-dom、react-router-dom 7、@tanstack/react-query 5、lucide-react（package.json 全部 ^ 范围，仓内有 package-lock.json）
- features 层：auth（useAuth/redirect）、profiles（useProfilesQuery 及各 hook、BrowserSessionPage 等页面）、settings/artifacts/automation 页面、browser-session（BrowserSessionView 经 shared/components 反向引用）
- 后端契约：schemas/openapi/cbrowser_v1.json（经 generate:api 生成 .d.ts，本轮核对路径集 19/19 与 .d.ts 一致）；运行时同源 /api/v1/* 与 /api/v1/events
- 构建脚本：scripts/vendor_selkies_web.py、verify_frontend_dist.py、write_frontend_build_stamp.py（属 contracts_deploy 单元）

## flows

- 冷启动：main.tsx → AuthProvider.checkSession（GET /auth/session）→ RequireAuth 三态（loading/重定向/放行）；登录后 AuthenticatedSseBridge 挂载，useProfileEventsSync 订阅事件并 start()，事件写入 runtime 查询缓存并失效 lists。
- 写请求：React Query mutation → ApiClient.request 组装 CSRF 头与幂等键 → fetch（AbortController 超时）→ 401 触发 onUnauthorized 清空登录态、非 2xx 解析 detail/message/error/retryable 成 ApiError → shouldRetryRequest 决定重试（ApiError 仅 retryable 且 <2 次，普通错误 <1 次）。
- 登出/会话失效：SseSyncBridge 与 useProfileEventsSync 的 effect 清理双路调用 sseClient.stop() 并注销 onUnauthorized；RequireAuth 跳 /login?next=<原路径>，登录成功后由 LoginPage 经 sanitizeNextPath 校验 next 防开放重定向（auth_guard.test 覆盖了 6 种 hostile next）。
- 语言切换：AppLayout 顶栏按钮 setLocale → 写 localStorage、同步 document.documentElement.lang。

## constraints

- 同源约束在客户端二次设防：request() 对 http/// 开头的绝对 URL 做 origin 校验，跨源在发请求前抛 ApiError（client.test 有覆盖）。
- CSRF token 只存内存 + cbrowser_csrf cookie，前端不把任何凭据写入 localStorage（仅 locale）；auth_guard.test 断言 localStorage.currentProfileId 绝不被使用（AC-001 目标隔离）。
- tsconfig strict + noUncheckedIndexedAccess + noUnusedLocals/Parameters，但 exclude 了全部测试文件（见 finding 05）。
- generated/cbrowser_v1.d.ts 为生成产物（文件头注明），只能经 generate:api 再生，禁止手改；本轮未发现手改痕迹。

## decisions

- SSE 不用原生 EventSource 而用 fetch 流式读取，以获得 401 处理、Last-Event-ID 手工续传与可注入 URL（测试用真实本地 HTTP 服务器验证）。
- API 客户端手写 fetch 封装而非用生成的 operations 类型直接调用；生成类型仅经 types.ts 别名约束请求/响应形状。
- 路由目标由 URL ?profileId= 决定而非全局状态/存储，支持多标签页独立目标（AC-001，router.test 有双实例隔离测试）。
- 深色单主题：index.html 硬编码 class=dark，tailwind darkMode=class，无浅色切换。

## evidence

- src/frontend/src/shared/api/client.ts:91-210（request 全流程：同源校验、CSRF、超时、401、错误解析）
- src/frontend/src/shared/api/sse.ts:96-205（connect 读循环、尾事件 flush、退避重连）
- src/frontend/src/app/providers.tsx:10-29（SSE 桥挂载/清理语义）
- src/frontend/src/app/auth_guard.test.tsx:145-266（守卫、401 失效、开放重定向用例）
- src/frontend/src/i18n.tsx:19-326（en/zh 字典，本轮脚本核对键集各 150 且差集为空）
- schemas/openapi/cbrowser_v1.json 与 generated/cbrowser_v1.d.ts 路径集核对：各 19 条 /api/v1 路径，一致
- git log：5a3da22 feat(t017) converge v2 frontend and harden shared clients 为本单元最近主要变更；legacy v1 App.tsx/components 已不在文件清单中

## uncertainties

- finding 01 的 stop→start 竞态未做运行时复现，仅静态推演；实际触发窗口取决于已中止 fetch 的 rejection 何时被处理，未实测。
- 仓级门禁（scripts/run_gates.sh、CI）是否对前端测试另行做 tsc --noEmit 全量类型检查不在本单元文件内，未核对；finding 05 仅断言本单元 package.json/tsconfig 口径下测试不被类型检查。
- selkies adapter 构建产物与 dist 新鲜度校验属 contracts_deploy 单元脚本，本单元仅核对 package.json 钩子接线，未审脚本本身。

## Findings

- [Low][70] src/frontend/src/shared/api/sse.ts:74-77 — ProfileEventsClient 无连接代次防护，stop 后快速 start 可能留下双读循环
  - ID: f_frontend_shell_01; verification: suspected
  - Evidence: start() 无条件置 isClosed=false 并调用 connect()（sse.ts:74-77）；connect() 开头把 this.abortController 直接覆写为新控制器（sse.ts:100），stop() 只能 abort 最新一个（sse.ts:82-93）。; 旧 connect() 循环在被 abort 后进入 catch/finally 时读的是共享的 this.isClosed（sse.ts:195-205）：若期间已再次 start()，isClosed 已被重置为 false，旧循环会 dispatchError 并 scheduleReconnect，从而与新循环并存、共享 lastEventId 与 reconnectTimeout。; 调用方确有 stop→start 相邻时序：providers.tsx:19-25 的 SseSyncBridge 清理调用 stop()，useProfileEventsSync（features/profiles/useProfilesQuery.ts:305-310）在 effect 中 start()、清理中 stop()；登录态翻转与 main.tsx StrictMode 的开发期双 effect 都会产生相邻的 stop/start。; 本单元 sse.test.ts 只覆盖单次生命周期与重连；sse_hardening.test.ts（属 frontend_features 清单）覆盖 401 停连与尾事件 flush，均未覆盖 stop→start 或重复 start。
  - Impact: 竞态命中时同一单例出现两条 SSE 连接：事件重复投递（缓存写入与失效重复执行，数据本身幂等）、多占一条服务器连接；更坏时 stop() 无法终止旧循环，登出后连接残留到服务器侧关闭。生产触发需亚毫秒级登录态翻转，开发期 StrictMode 下更易命中。
  - Fix: 在 ProfileEventsClient 引入连接代次（generation 计数）：start/stop 时自增，connect() 捕获自身代次并在每次 await 后、catch 与 finally 中校验代次是否仍有效，无效则直接退出不调度重连；或让 start() 在已有活跃循环时先 stop 并等待其退出。补一条 stop→start 立即重启只保留一条连接的测试。

- [Low][80] src/frontend/src/shared/api/client.ts:118-145 — 调用方主动 abort 被统一误报为可重试的「Request timed out」
  - ID: f_frontend_shell_02; verification: static
  - Evidence: request() 把 init.signal 的 abort 转发给内部 controller（client.ts:120-125），catch 中只要 controller.signal.aborted 就抛 ApiError("Request timed out", errorCode=timeout, retryable=true)（client.ts:138-143），不区分超时与外部取消。; providers.tsx:57-59 把 mutations 的 retry 设为 shouldRetryRequest，而 shouldRetryRequest 对 retryable 的 ApiError 允许重试 2 次（client.ts:32-37）——被取消的写请求存在被重试的通道。; 本轮 grep 确认当前仓内无调用方给 request() 传 signal，故影响为潜伏：公开 API 契约已把取消语义写错，首个接入 signal 的调用方（如查询取消、上传取消）即会踩到误报与误重试。
  - Impact: 错误文案与统计把用户/框架取消记为超时，掩盖真实失败分布；若未来有调用方用 signal 取消写操作，React Query 重试可能使已取消的写请求再次发出（带幂等键时可控，未带时重复提交）。
  - Fix: 在 catch 中区分来源：externalSignal?.aborted 且非内部计时器触发时，透传原始 AbortError（或抛不可重试的 ApiError errorCode=aborted）；仅计时器触发才映射为 timeout。补外部 signal 取消的单测。

- [Low][95] src/frontend/src/styles/globals.css:44-66 — globals.css 的 @layer components 组件类（.btn/.input/.label 等）全仓零使用，是死 CSS
  - ID: f_frontend_shell_03; verification: static
  - Evidence: globals.css:44-66 定义 .btn、.btn-primary、.btn-secondary、.btn-danger、.input、textarea.input、.label 共 7 个组件类。; 本轮 grep 全仓 src/**/*.tsx 的 className（含模板字符串）对 btn/input/label 组件类的使用为 0 处；btn-primary 等仅出现在 globals.css 定义自身。features 页面一律内联 Tailwind 工具类拼装样式。; 这些类经 @tailwind components 进入最终 CSS 产物，持续占用 bundle 并向新贡献者暗示存在一套并不存在的共享组件类规范。
  - Impact: 死样式随每次构建发布；更主要的是误导后续开发按 .btn/.input 约定写新页面，与实际内联工具类的主流写法分叉。
  - Fix: 删除整个 @layer components 块；若团队希望保留组件类规范，则反过来把高频按钮/输入迁移到这些类并在 blueprint/conventions 中登记，二选一，不要保留无消费者的定义。

- [Low][85] src/frontend/src/shared/components/BrowserSessionMount.tsx:1-9 — shared 层反向依赖 features 层，且 BrowserSessionMount 本地重声明 props 类型造成漂移面
  - ID: f_frontend_shell_04; verification: static
  - Evidence: BrowserSessionMount.tsx:1 从 ../../features/browser-session/BrowserSessionView 导入组件——shared/ 目录内其余模块（client/sse/types）均不依赖 features，此处是 shared→features 的反向依赖，破坏 shared 作为底层共享层的单向分层。; 该文件第 3-7 行本地重声明 BrowserSessionViewProps（profileId/clipboardSync/onCheckRuntimeStatus），而非从 BrowserSessionView 导入其 props 类型；BrowserSessionView 若新增可选 prop，经此挂载点的唯一消费者（features/profiles/BrowserSessionPage.tsx:61）将静默无法传递。; 包装层本身仅加一层 div（data-testid + flex 类）并原样转发三个 props，无其他逻辑。
  - Impact: 分层反转使 shared 不再可独立演进/复用；props 双份定义是典型的静默漂移源，新增会话能力时容易漏接挂载层。
  - Fix: 把 BrowserSessionMount 移入 features/browser-session 或 features/profiles（与其唯一消费者同层），shared/ 只保留无业务依赖的模块；props 类型改为从 BrowserSessionView 处 import type 复用同一定义。

- [Low][90] src/frontend/tsconfig.json:23 — 测试文件被 tsconfig 整体排除，构建与测试链路均不类型检查测试代码
  - ID: f_frontend_shell_05; verification: static
  - Evidence: tsconfig.json:22-23 include 仅 src 且 exclude src/**/*.test.ts(x)；package.json:11 的 build 用 tsc -b 只查非测试代码，vitest 仅转译不做类型检查——本单元 5 个测试文件（约 920 行）无任何类型门禁。; 具体残留：router.test.tsx:13-19 在 beforeEach 中构造 queryClient 变量但从未使用（renderWithRouter 内部自建 testQueryClient），若测试在 include 内，noUnusedLocals（tsconfig.json:16）本应报错。; 后果已可见于测试代码的类型松紧不一：router.test.tsx 直接给 defaultApiClient 的 readonly 对象属性赋普通 async 函数，auth_guard.test.tsx 用 as unknown as 强转伪造 ProfileEventsClient，均在无类型检查下累积。
  - Impact: 测试中的类型错误、过期签名与死代码只能靠 IDE 偶然发现；重构生产 API 时测试侧的类型漂移不会让 build 变红，削弱测试作为契约证据的可信度。
  - Fix: 新增 tsconfig.test.json（include 测试文件、noEmit）并在 test 脚本或门禁中加 tsc -p tsconfig.test.json；或直接把测试纳入主 tsconfig 并为 vitest/globals 配置 types。先清理 router.test.tsx 的未用变量。

- [Low][95] src/frontend/src/i18n.tsx:328 — i18n 无 en/zh 键对齐的自动守卫，zh 字典的开放 Record 类型使缺键对 tsc 不可见
  - ID: f_frontend_shell_06; verification: static
  - Evidence: zh 与 en 同为 MessageDict = Record<string, string>（i18n.tsx:15、zh 定义处），TranslationKey 只约束 en 的键；t() 在 zh 缺键时静默回退 en（i18n.tsx:412-415），因此 zh 漏键不会产生任何构建或测试失败，只会在界面上混入英文。; i18n.test.tsx 仅 1 条用例（旧键迁移 + document.lang 同步），无键对齐断言。; 本轮以脚本核对当前状态：en/zh 各 150 键、双向差集为空——现状对齐，本条针对的是缺失回归守卫而非现存漂移。
  - Impact: 后续新增文案只加 en 时，中文界面会静默混杂英文且无任何信号，与仓库其余契约面（OpenAPI 有漂移守卫测试）的防护标准不一致。
  - Fix: 给 zh 标注类型为 Record<TranslationKey, string>（或 satisfies），让缺键/多键在 tsc 阶段报错；并在 i18n.test.tsx 增加一条键集相等断言作为双保险。

- [Low][90] src/frontend/src/shared/api/client.test.ts:71-82 — client.test.ts 两条用例的标题声称了未被断言的行为（credentials 与 retries）
  - ID: f_frontend_shell_07; verification: static
  - Evidence: client.test.ts:71-82 用例名为 "sends credentials: 'include' on GET requests"，断言只有 method 与 url；其真实本地 HTTP 服务器只能观察请求头/行，fetch 的 credentials 标志在该装置下不可观察，cookie 也不会由 Node 侧 fetch 依据 jsdom 的 document.cookie 自动附带——credentials 行为实际未被验证。; client.test.ts:241-258 用例名为 "uses the caller-supplied action key for retries"，内容是手工连续调用两次 create 并断言两次都带同一 Idempotency-Key，全程没有发生任何 retry。; 被声称的行为在 client.ts 中确实实现（client.ts:106、各写方法透传 idempotencyKey），问题在测试证据与标题不符：日后 credentials 或重试接线回归时这两条仍会绿。
  - Impact: 测试名义覆盖与实际覆盖不一致，误导后续维护者以为凭据携带与重试幂等已被锁定，属于验证假行为类的弱化信号。
  - Fix: 把两条用例改名为与断言一致的表述（如 "sends Idempotency-Key header when provided"）；credentials 行为改在 jsdom 内以 fetch spy 断言 init.credentials === 'include'（sse/client 的其他 hardening 用例已有 fetch spy 先例）。

- [Low][85] src/frontend/src/app/auth_guard.test.tsx:67-107 — 外壳测试以直接赋值方式 monkey-patch 共享 defaultApiClient 单例且从不还原
  - ID: f_frontend_shell_08; verification: static
  - Evidence: auth_guard.test.tsx:67-107 把 defaultApiClient.auth.session/login/logout、profiles.* 逐个赋值为 vi.fn，甚至整体替换 setOnUnauthorized 方法本身；afterEach（:140-143）只有 cleanup() 与 vi.restoreAllMocks()，后者不撤销普通属性赋值。; router.test.tsx:22-118 同样直接赋值 defaultApiClient 的方法，无任何还原。; 当前之所以不出问题，靠的是 vitest 默认 per-file 模块隔离 + 每个文件 beforeEach 重新赋值全套方法这一隐含约定；新测试若漏给某个方法重新赋值，或将来为性能关闭 isolate，假实现会跨用例/跨文件泄漏。
  - Impact: 测试隔离依赖未声明的约定而非机制，假认证/假 Profile 数据有串扰到其他用例的风险，且失败时会以与被测代码无关的方式变红，侵蚀套件可信度。
  - Fix: 改用 AppProviders 已预留的 apiClient 注入点传入每个用例独立构造的假 ApiClient（providers.tsx:39-44 已支持），或在 afterEach 中用 vi.restoreAllMocks 配合 spyOn 形式（vi.spyOn 返回的 mock 才可被 restore）；避免直接改写单例属性。

- [Info][95] src/frontend/src/app/AppLayout.tsx:65 — AppLayout 中标签回调参数命名为 t，遮蔽了 i18n 的 t() 函数
  - ID: f_frontend_shell_09; verification: static
  - Evidence: AppLayout.tsx:62-68 的 filteredProfiles 中 some((t) => ...) 以 tag 对象/字符串遮蔽外层 const { t } = useI18n()；:258 的 p.tags.map((t) => ...) 同样遮蔽。; 当前两处回调内部没有调用 t()，行为无误；但该组件 render 通篇依赖 t()，未来在这些回调内补文案调用会直接把 tag 值当函数调用或得到错误结果。
  - Impact: 可读性与后续编辑的踩坑面，无当前行为影响。
  - Fix: 把两处回调参数改名为 tag，与数据模型 Tag 的命名一致。

- [Info][95] src/frontend/tailwind.config.ts:21-28 — tailwind 色板中 accent 与 primary 是同值双名，代码在两名之间分裂使用
  - ID: f_frontend_shell_10; verification: static
  - Evidence: tailwind.config.ts:21-28 accent 与 primary 均为 DEFAULT #6366f1 / hover #818cf8，primary-foreground 单列白色。; globals.css 的组件类用 accent（focus:ring-accent、bg-accent），AppLayout 用 primary（bg-primary、border-primary/30、focus:border-primary），同一品牌色在外壳内就有两套叫法。
  - Impact: 换肤/调色时必须同步改两处且容易漏改其一，造成界面色值分叉；无当前视觉影响。
  - Fix: 保留一个权威名（建议 primary），accent 改为引用同一值或删除，globals.css 与组件统一到一个名下。

- [Info][90] src/frontend/src/shared/api/sse.ts:1-10 — SSE 事件类型 ProfileRuntimeEvent 为手写重复定义，未复用生成的 ProfileRuntimeStatusEvent
  - ID: f_frontend_shell_11; verification: static
  - Evidence: sse.ts:1-10 手写 ProfileRuntimeEvent 接口；生成文件 components.schemas 中已有 ProfileRuntimeStatusEvent（由 /api/v1/events 的 text/event-stream 内容类型生成），types.ts 未导出该别名，sse.ts 也未引用。; 两份定义字段大体一致但可选性不同（如 failure_count 在生成型为必填、手写型为可选），后端事件结构演进时 generate:api 只会更新生成型，手写型无任何漂移信号。
  - Impact: 同一线协议两份类型定义，事件字段增减时 SSE 消费侧可能静默按旧形状解析；当前字段集兼容，无行为影响。
  - Fix: 在 types.ts 导出 ProfileRuntimeStatusEvent 别名，sse.ts 以其为基础（必要时用 Partial/Pick 表达线上可选性）替换手写接口，或在 sse.ts 注释中声明与生成型的对应关系并加一条类型层断言（Expect<Equal<...>> 风格的编译期校验）。

## views

```json
{
  "contracts": {
    "reviewer": "f7ba9ca3-42a1-4996-93d2-71da3114722f",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "f7ba9ca3-42a1-4996-93d2-71da3114722f",
    "status": "completed"
  },
  "design": {
    "reviewer": "f7ba9ca3-42a1-4996-93d2-71da3114722f",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "f7ba9ca3-42a1-4996-93d2-71da3114722f",
    "status": "completed"
  },
  "performance": {
    "reviewer": "f7ba9ca3-42a1-4996-93d2-71da3114722f",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "f7ba9ca3-42a1-4996-93d2-71da3114722f",
    "status": "completed"
  },
  "security": {
    "reviewer": "f7ba9ca3-42a1-4996-93d2-71da3114722f",
    "status": "completed"
  },
  "tests": {
    "reviewer": "f7ba9ca3-42a1-4996-93d2-71da3114722f",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "src/frontend/index.html",
  "src/frontend/package.json",
  "src/frontend/postcss.config.js",
  "src/frontend/public/logo.svg",
  "src/frontend/public/menubar-icon.svg",
  "src/frontend/src/app/AppLayout.tsx",
  "src/frontend/src/app/RequireAuth.tsx",
  "src/frontend/src/app/auth_guard.test.tsx",
  "src/frontend/src/app/providers.tsx",
  "src/frontend/src/app/router.test.tsx",
  "src/frontend/src/app/router.tsx",
  "src/frontend/src/i18n.test.tsx",
  "src/frontend/src/i18n.tsx",
  "src/frontend/src/main.tsx",
  "src/frontend/src/shared/api/client.test.ts",
  "src/frontend/src/shared/api/client.ts",
  "src/frontend/src/shared/api/generated/cbrowser_v1.d.ts",
  "src/frontend/src/shared/api/sse.test.ts",
  "src/frontend/src/shared/api/sse.ts",
  "src/frontend/src/shared/api/types.ts",
  "src/frontend/src/shared/components/BrowserSessionMount.tsx",
  "src/frontend/src/styles/globals.css",
  "src/frontend/src/vite-env.d.ts",
  "src/frontend/tailwind.config.ts",
  "src/frontend/tsconfig.json",
  "src/frontend/vite.config.ts",
  "src/frontend/vite.selkies.config.ts",
  "src/frontend/vitest.config.ts"
]
```

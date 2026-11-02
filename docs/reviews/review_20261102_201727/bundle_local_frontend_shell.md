# bundle_local_frontend_shell

## responsibilities

- 应用入口与外壳：src/main.tsx 以 app/router.tsx 的 createBrowserRouter + app/providers.tsx（QueryClient、I18nProvider、AuthProvider、认证后才挂载的 SSE 同步桥）为唯一生效入口；app/AppLayout.tsx 是 v2 布局（顶栏、侧边 Profile 列表、Outlet），app/RequireAuth.tsx 是路由守卫
- 共享 API 层：shared/api/client.ts 提供类型化 ApiClient（cookie 凭据、写请求自动附 X-CSRF-Token、401 回调、ApiError），shared/api/sse.ts 提供带 Last-Event-ID 续传与指数退避重连的 ProfileEventsClient；shared/api/types.ts 仅做 generated/cbrowser_v1.d.ts 的别名再导出并附 DEFAULT_PROFILE_CREATE_VALUES 常量
- i18n：src/i18n.tsx 内嵌 en/zh 两部字典（各 291 键，静态比对完全对齐、无缺失无重复），locale 存 localStorage 并按 navigator.language 兜底检测，缺键时回退 en
- 构建接线：package.json build = tsc -b && vite build（主应用）&& vite build --config vite.selkies.config.ts（IIFE 适配器注入 Selkies 官方 bundle 前），prebuild 经 scripts/vendor_selkies_web.py  Vendoring、postbuild 经 scripts/verify_frontend_dist.py 校验；vite.config.ts 仅 dev 代理 /api→localhost:8080
- 遗留 v1 界面：src/App.tsx 与全部 src/components/* 构成一个以上游 lib/api（token 认证）为根的封闭导入图，是重构前的单体应用，与 v2 并存于同一 src 树（详见 finding f_frontend_shell_01）

## interfaces

- ApiClient.request<T>(endpoint, init) 及 profiles/artifacts/automation/auth/health 分组方法，路径全部为 /api/v1/* 相对路径并 encodeURIComponent 路径参数（client.ts:57-288）
- ProfileEventsClient.onEvent/onError/start/stop，事件类型 ProfileRuntimeEvent 与后端 ProfileRuntimeStatusEvent 字段基本同构（sse.ts:1-24）
- shared/api/types.ts 对外别名：ArtifactResponse、ProfileResponse、ProfileCreateRequest、ProfileUpdateRequest、ProfileRuntimeResponse、LoginRequest/Response、SessionResponse、Tag、ApiPaths（其中 ApiPaths 无任何引用方）
- 路由表 app/router.tsx：/login 公开，其余经 RequireAuth 守卫，含 /、/settings、/profiles/new、/profiles/:profileId、/profiles/:profileId/files、/automation/:profileId，通配重定向 /
- BrowserSessionMount 是 shared/components 中唯一组件，仅给 features/browser-session/BrowserSessionView 加一层 div 包装并透传 props

## dependencies

- react 19 / react-dom 19、react-router-dom 7.18.5（另有从未被 import 的 react-router 7.3.0）、@tanstack/react-query 5、lucide-react
- @dnd-kit/core+sortable+utilities 与 @novnc/novnc 仅被遗留组件引用（ProfileList.tsx、ProfileViewer.tsx），活代码无引用
- 构建链：vite 6、@vitejs/plugin-react、typescript ~5.7、tailwindcss 3.4 + postcss + autoprefixer、vitest 4 + jsdom + @testing-library/react、openapi-typescript 7（generate:api 从 schemas/openapi/cbrowser_v1.json 生成类型）
- 运行时外部依赖：后端 /api/v1（REST + SSE /api/v1/events）、Selkies 官方 web bundle（build 时 vendored 到 public/selkies，gitignore 排除）

## flows

- 启动：main.tsx → Providers（QueryClient staleTime 5s/retry 1）→ AuthProvider 拉 /api/v1/auth/session → RequireAuth 未认证跳 /login?next=… → AppLayout + Outlet；认证成立后 AuthenticatedSseBridge 挂载 SseSyncBridge，SSE 事件驱动 react-query 缓存失效
- 写请求：ApiClient 从 cbrowser_csrf cookie 或内存 token 取 CSRF → X-CSRF-Token 头 + credentials:include → 401 触发 onUnauthorized（由 features/auth/useAuth 注册）→ 登出并跳登录；错误体按 detail/message 字符串提取为 ApiError
- 构建：npm run build 先 vendor Selkies 资源，再 tsc -b 类型检查（含全部 src，连同遗留树），再两次 vite build 产出 dist/ 与 dist/selkies/selkies_adapter.js，最后 verify_frontend_dist.py 校验产物

## constraints

- tsconfig strict 全家桶开启（strict、noUnusedLocals、noUnusedParameters、noUncheckedIndexedAccess、noFallthroughCasesInSwitch），但 exclude 掉全部 test 文件，测试文件不进 tsc -b 检查
- SSE 契约同时支持 Last-Event-ID 头与 last_event_id 查询参数（generated operations.subscribe_runtime_events），客户端只用头方式
- 后端写接口契约支持 Idempotency-Key 头与 409 冲突语义（generated 中 create/update/desired-state/stop/duplicate/reset 六个 operation 均声明），客户端仅 duplicate/reset 发送且每次调用现生成随机键
- repo AGENTS.md 约定 _meta 过程文件 gitignore、.env 真值不入库；本单元未见任何硬编码 secret（client.test.ts 中的 csrf 值是测试夹具假值，已按假值看待）

## decisions

- v2 架构以 features/ 模块 + shared/api 类型化客户端替代 v1 单体 App.tsx + lib/api，但旧树未删除，形成双份实现并存（git log 显示 App.tsx 自 524e34e 结构重组后未再更新，app/router.tsx 由 faee1f3 t007 引入）
- 认证从 v1 的 access token（components/LoginPage.tsx + lib/api）改为 v2 的密码登录 + 会话 cookie + CSRF 双提交（features/auth + shared/api/client.ts），两套登录页同名并存
- Selkies 适配器单独以 IIFE 非压缩构建（vite.selkies.config.ts 注释说明需在官方 module bundle 前注入），主应用则走标准 ESM 构建

## evidence

- src/frontend/src/main.tsx:1-14 只 import app/router 与 app/providers，全仓 grep 无任何文件 import src/App.tsx（除其自身）
- 导入图闭包：grep 显示 src/components/* 的 import 仅来自 src/App.tsx:3-16 与彼此，lib/api 的 import 仅来自 App.tsx、components/*、hooks/useProfiles*
- src/frontend/tsconfig.tsbuildinfo:1 的 root 列表仅含旧布局文件（src/components/*、src/lib/api.ts、src/hooks/useprofiles.ts、src/app.tsx），不含 app/、shared/、features/ 任何现行文件
- git check-ignore 对 tsconfig.tsbuildinfo 返回 NOT IGNORED 且 git ls-files 显示 TRACKED；根 .gitignore 无 *.tsbuildinfo 条目
- .github/workflows/ci.yml:24-39 frontend job 的 working-directory 为 frontend、cache-dependency-path 为 frontend/package-lock.json，仓根不存在 frontend/ 目录（实际为 src/frontend，package-lock.json 在 src/frontend/package-lock.json）
- tailwind.config.ts:8-26 的 colors 仅 surface/border/accent；AppLayout.tsx:235,240,265 使用 focus:border-primary、bg-primary、text-primary-foreground、bg-primary/15、text-primary、border-primary/30
- i18n 键集静态比对：en 291 键、zh 291 键，双向差集为空、无重复键（脚本比对 src/i18n.tsx 两部字典）
- generated 路径集与 schemas/openapi/cbrowser_v1.json 路径集静态比对：22 条完全一致，无漂移
- diff 显示 src/assets/logo.svg 与 public/logo.svg、src/assets/menubar-icon.svg 与 public/menubar-icon.svg 逐字节相同，且无任何文件 import src/assets 下 svg
- package.json:27-28 同时列 react-router ^7.3.0 与 react-router-dom ^7.18.5；全仓 grep `from "react-router"` 零命中，全部 import 走 react-router-dom

## uncertainties

- 按任务约束仅做静态审阅，未运行 vitest/tsc/vite build：AppLayout 的 primary 类缺失是否被其他全局样式兜底、tsc -b 在当前 tsconfig（无 composite 字段）下的实际行为、以及遗留树是否仍通过类型检查，均未实测，相关 finding 标 static/suspected 反映静态证据强度
- useProfileEventsSync（frontend_features 单元）如何调用 ProfileEventsClient.start() 未在本单元范围内核对，SSE 重复 start 的实际可达性存疑，已在 finding 中按 suspected 标注该子项
- CI workflow 文件归属 repo_ops 单元；本报告仅从前端构建接线角度记录其路径失效事实，未审阅该 workflow 的其余 job 语义
- src/lib/api.ts 与 src/hooks/useProfiles.ts 归属 frontend_features 单元，本单元只核对了其被 App.tsx/components 引用的关系，未逐行审阅其实现

## Findings

- [High][95] src/frontend/src/App.tsx:1-445 — 整个遗留 v1 应用树以不可达的 App.tsx 为根与 v2 并存，形成双份实现
  - ID: f_frontend_shell_01; verification: static
  - Evidence: 入口 src/main.tsx:3-4 只 import app/router 与 app/providers；全仓 grep 无任何文件 import "./App" 或 src/App.tsx; src/App.tsx:3-16 import 的 hooks/useProfiles、lib/api、components/{ProfileList,ProfileForm,ProfileViewer,NativeWindowStatus,LaunchButton,StatusIndicator,SystemStatusBadge,UpdateBanner,LaunchErrorBanner,SettingsPanel,LoginPage,LanguageToggle} 构成封闭导入图：grep 显示 components/* 的引用方只有 App.tsx 与彼此，lib/api 的引用方只有 App.tsx、components/*、hooks/useProfiles*; 功能与 v2 逐项重复：components/LoginPage.tsx（token 登录）vs features/auth/LoginPage（密码+会话）；components/SettingsPanel.tsx vs features/settings/SettingsPage；components/ProfileFiles.tsx vs features/artifacts/ProfileFilesPage；components/ProfileForm.tsx（853 行）vs features/profiles 的新建/详情页；AppLayout.tsx:190-198 又内联重写了 LanguageToggle 的切换逻辑而非复用 components/LanguageToggle.tsx; 遗留树仍被 tsc -b（tsconfig include:["src"]）与 vitest 全量编译/执行：components/ProfileForm.test.tsx、ProfileFiles.test.tsx 只测这棵死树；其专属 i18n 键（如 quitManager、managerStopped*、tierKeylessTitle 等仅 App.tsx/遗留组件使用）使 291 键字典无法瘦身; git log：src/App.tsx 最后变更为 524e34e（repo_template 结构重组），现行 app/router.tsx 由 faee1f3（t007 v2 前端）引入后持续演进，旧树自此冻结
  - Impact: 约 2,900 行（含测试）死代码长期参与类型检查与测试运行，拉长 CI 并制造假覆盖；两套 API 客户端（lib/api 的 token 认证 vs shared/api/client 的 cookie+CSRF）与两套登录/设置/文件 UI 并存，后续维护者极易改错一份、或误把遗留实现当现行行为修 bug；安全修复若只落 v2，旧树中的旧模式（如 ProfileViewer 的剪贴板日志）仍留在仓内可被误复活
  - Fix: 走 t011_v2_remove_legacy 对应流程整体删除 src/App.tsx 与 src/components/*（及其专属测试），并与 frontend_features 单元协调删除/迁移 src/lib/api.ts、src/hooks/useProfiles.ts；删除前用 grep 确认零引用（已具备证据），同步清理仅遗留树使用的 i18n 键与 novnc.d.ts；若个别遗留能力（如 noVNC 查看器）仍需保留，应显式迁入 features 并注明，而非整树冻结

- [High][90] .github/workflows/ci.yml:24-39 — CI 的 frontend（及 backend）job 仍指向重组前路径，前端测试与构建门禁实际无法运行
  - ID: f_frontend_shell_02; verification: static
  - Evidence: .github/workflows/ci.yml:27-29 defaults.run.working-directory 为 frontend，line 36 cache-dependency-path 为 frontend/package-lock.json，line 37-39 依次 npm ci / npm test / npm run build; 仓根不存在 frontend/ 目录：实际布局为 src/frontend（git ls-files 确认 package-lock.json 在 src/frontend/package-lock.json），路径自 524e34e repo_template 结构重组后变更; 同一文件 line 9-22 的 backend job 同样引用 backend/requirements.txt 与 backend/tests，实际为 src/backend/，说明整份 workflow 停留在重组前布局; package.json:7-16 定义了完整的 test/build 脚本链（vitest run、tsc -b + 双 vite build + verify），但按现行 workflow 路径 job 会在 cd/setup-node 阶段直接失败，这些门禁从未按当前布局执行
  - Impact: 主干与 PR 的前端自动化门禁失效：类型检查、vitest（含 auth_guard/router 等关键行为测试）与双构建校验在 CI 中不运行，回归只能靠本地手动执行发现；workflow 文件属 repo_ops 单元，但失效的正是本单元 package.json 的脚本契约
  - Fix: 将 ci.yml 的 frontend job working-directory 改为 src/frontend、cache-dependency-path 改为 src/frontend/package-lock.json，backend job 同步改为 src/backend 对应路径；改后以一次真实 CI 运行（或本地按相同命令序列）验证 npm ci、npm test、npm run build 全绿，并把该验证写入任务记录

- [Medium][90] src/frontend/src/app/AppLayout.tsx:235-265 — 现行 AppLayout 使用未在 tailwind.config 定义的 primary 色板类，多处关键控件样式静默失效
  - ID: f_frontend_shell_03; verification: static
  - Evidence: src/frontend/tailwind.config.ts:8-26 的 theme.extend.colors 仅定义 surface（0-4）、border（DEFAULT/hover）、accent（DEFAULT/hover），无 primary / primary-foreground; AppLayout.tsx:235 搜索框 focus:border-primary；:240 新建 Profile 按钮 bg-primary text-primary-foreground；:265 选中项 bg-primary/15 text-primary border-primary/30——Tailwind 3 对未定义色板不生成这些工具类，globals.css 也无同名手写类（仅 .btn-primary 组件类）; 对比同文件其余控件均使用已定义的 bg-surface-*、border-border、text-gray-*，说明 primary 系类是从另一套（shadcn 风格）设计令牌迁入时漏配；grep 显示 features/ 下另有 7 个文件使用同系 primary 类（属 frontend_features 单元，问题同源）
  - Impact: 现行外壳的新建按钮无背景色（透明底+近白文字，几乎不可见）、侧边栏选中态无高亮、搜索框聚焦无边框反馈——均为用户每日可见的活缺陷，且因 CSS 类静默缺失不会产生任何构建或测试报错
  - Fix: 在 tailwind.config.ts 的 colors 中补 primary 与 primary-foreground 令牌（值与 accent 体系对齐），或把 AppLayout 等处类名统一改回已定义的 accent 体系；在 frontend_features 单元同步处理其余 7 个文件，并加一条构建后校验（如 verify 脚本 grep dist CSS 中关键类存在性）防再漏配

- [Medium][85] src/frontend/tsconfig.tsbuildinfo:1 — 生成的 tsconfig.tsbuildinfo 被提交入库且内容停留在重组前布局，是误导性的过期产物
  - ID: f_frontend_shell_04; verification: static
  - Evidence: git ls-files 确认该文件被跟踪，git check-ignore 返回 NOT IGNORED，根 .gitignore 无 *.tsbuildinfo 条目（对比 dist/、public/selkies/ 均已忽略）; 文件内容 root 列表仅含旧布局的 19 个文件（./src/app.tsx、./src/components/*.tsx、./src/hooks/useprofiles.ts、./src/lib/api.ts 等），完全不含现行 app/、shared/、features/ 文件，version 戳 5.7.3；与当前 tsconfig.json 的 include:["src"] 不符，证明它生成于 v2 重构之前; tsconfig.json 未设 tsBuildInfoFile，package.json build 的 tsc -b 每次都会在 src/frontend/ 根目录就地重写该文件，使每次本地构建都弄脏工作区，诱发误提交
  - Impact: 生成产物冒充源码入库违反文档规范视角的载体合规（生成文件应改源或生成配置、不得手改/留存产物）；其内容记录的是已不存在的架构布局，会误导后续审阅与增量构建判断；每次构建产生无关 diff 噪声，增加误提交与合并冲突概率
  - Fix: git rm --cached src/frontend/tsconfig.tsbuildinfo，在根 .gitignore（或 src/frontend/.gitignore）加 *.tsbuildinfo，并在 tsconfig.json 显式设置 tsBuildInfoFile 指向被忽略的缓存目录（如 ./node_modules/.tmp/tsconfig.tsbuildinfo，与 Vite 模板惯例一致）

- [Medium][90] src/frontend/src/shared/api/client.ts:57-101 — ApiClient 所有请求无超时与取消，挂起的 fetch 会让查询/变更永久 pending
  - ID: f_frontend_shell_05; verification: static
  - Evidence: client.ts:80-85 的 fetch 调用未传 signal，全类无 AbortController/AbortSignal.timeout 的任何使用（grep 零命中）; 上层 app/providers.tsx:44-52 给 react-query 设的 retry:1 只能在请求 settle 后触发，永不返回的请求连重试都不会发生；artifacts.upload 以 File 为 body 的大文件上传同样无超时与进度取消; 对比同单元 sse.ts 的 ProfileEventsClient 正确使用了 AbortController（sse.ts:74-87），说明超时/取消在本仓是被认可的模式，只是 REST 客户端漏做
  - Impact: 后端卡死、反代半开连接或网络黑洞时，界面会无限停留在 loading/pending（如启动、保存、上传），用户无法重试也收不到错误，只能刷新页面；与本项目远程浏览器管理场景（长连接多、网络环境杂）叠加后出现概率不低
  - Fix: 在 ApiClient.request 增加默认超时（如 AbortSignal.timeout(30000)，上传类请求放宽或单独可配），把外部传入的 init.signal 与超时信号合并（AbortSignal.any），超时统一抛 ApiError 并在 message 中区分超时与 HTTP 错误；为 client.test.ts 增加挂起服务器场景的超时用例

- [Medium][85] src/frontend/src/shared/api/client.ts:156-228 — Idempotency-Key 契约覆盖不一致且每次调用现生成随机键，重试无法去重
  - ID: f_frontend_shell_06; verification: static
  - Evidence: generated operations 显示 create_profile、update_profile（PUT/PATCH）、set_desired_state、stop_profile、duplicate、reset 六个写接口均声明可选 Idempotency-Key 头与 409 Idempotency conflict 响应（cbrowser_v1.d.ts 中对应 operations 段）; client.ts 仅 duplicate（:190-195）与 reset（:205-210）发送该头，create（:156-161）、update（:162-167）、setDesiredState（:175-186）、stop（:187-194）均不发送; 已发送的两处也在每次方法调用时用 crypto.randomUUID() 现生成新键：同一用户动作若被 react-query/上层重试而重新调用方法，键随之变化，服务端无法识别为同一操作，去重语义落空
  - Impact: 创建 Profile、启停等写操作在网络抖动重试或用户重复点击时可能被服务端重复执行（重复建档、重复启停），而契约层预留的幂等机制在客户端侧基本失效；409 冲突路径前端也从未实际触发过，属未验证契约面
  - Fix: 把幂等键的生命周期上移到调用方：由 mutation 层为一次用户动作生成并持有键、重试时复用同一键传入 client 方法（client 方法签名增加可选 idempotencyKey 参数），并给 create/update/setDesiredState/stop 补齐发送；同步在 client.test.ts 增加同键重试只落一次的服务端计数用例

- [Low][85] src/frontend/src/shared/api/sse.ts:113-160 — SSE 解析在流结束时丢弃未以空行结尾的最后一个事件
  - ID: f_frontend_shell_07; verification: static
  - Evidence: sse.ts:113-149 的读循环仅在遇到空行时才 dispatch 已累积的 currentDataLines；:115 reader 返回 done 时直接 break，残留在 currentDataLines/buffer 中的最后一帧（无尾随空行）永不 dispatch，TextDecoder 也未做最终 flush; 服务端正常关闭流、反代截断或进程重启时最后一帧恰是最关键的状态变更（如 observed_state 变为 stopped/error），丢失后 UI 只能等下一次轮询/重连的 Last-Event-ID 补发，若服务端不补发则状态长期陈旧; sse.test.ts 只覆盖带完整 \n\n 结尾的两帧与重连头，未覆盖尾帧截断场景
  - Impact: 低概率但真实的状态丢失：会话结束/异常的最终事件可能不达 UI，表现为 Profile 状态停留在旧值直到用户刷新或下一次事件到来
  - Fix: 在读循环退出（done）后补一次收尾：flush decoder 并把 currentDataLines 中残留数据按同样逻辑 dispatch 一次；为 sse.test.ts 增加服务端写出无尾随空行的最后一帧后关流的用例

- [Low][80] src/frontend/src/shared/api/sse.ts:92-99 — SSE 遇 401 只抛泛化错误并无限重连，不发出未授权信号
  - ID: f_frontend_shell_08; verification: static
  - Evidence: sse.ts:97-99 对 !response.ok 一律 throw new Error(`SSE HTTP error: ${status}`)，catch 后走 finally 的 scheduleReconnect（:150-155、:179-193，退避上限 30s 无限重试），全类无 onUnauthorized 类回调; 与同单元 client.ts:87-91 的处理不一致：REST 客户端在 401 时显式回调 onUnauthorized 触发登出流；SSE 侧会话过期后只会持续向 errorListeners 播发无状态码的泛化错误; 缓解事实：providers.tsx:24-28 的 AuthenticatedSseBridge 仅在已认证时挂载，且任一 REST 请求 401 会经 useAuth 清理认证态并卸载该桥，实际暴露窗口是会话刚过期且尚无 REST 请求发生的时段
  - Impact: 会话过期后的一段时间内 SSE 以 30s 间隔无限重连未授权端点，产生无用请求与误导性错误日志；若过期后用户长时间停留在只读页面，状态更新静默停滞而界面无明确提示
  - Fix: 给 ProfileEventsClient 增加可选 onUnauthorized 回调，在 response.status===401 时停止重连并回调（与 ApiClient 对齐），由 providers/useAuth 侧统一处理登出；或在重连策略中对 401 设置为不可重试状态并 dispatch 带状态码的错误供上层识别

- [Low][95] src/frontend/package.json:26-28 — react-router 与 react-router-dom 双依赖并存且版本错位，实际只用后者
  - ID: f_frontend_shell_09; verification: static
  - Evidence: package.json:27-28 同时声明 react-router ^7.3.0 与 react-router-dom ^7.18.5，两者主版本内小版本差距明显（7.3 vs 7.18）; 全仓 grep `from "react-router"` 零命中：main.tsx:3、app/router.tsx:1、app/RequireAuth.tsx:2、AppLayout.tsx:2 等所有 import 均来自 react-router-dom；react-router 仅作为 react-router-dom 的传递依赖被实际使用; react-router-dom v7 本身是对 react-router 的再导出包装，直依赖 react-router 不带来任何能力，只增加 lockfile 体积与未来误 import 时双实例（context 不共享导致 RouterProvider/useNavigate 失效）的风险面
  - Impact: 依赖面冗余与潜在的双实例隐患：后续开发者若按 v7 官方文档示例从 react-router import，会与现存 react-router-dom 的 router 实例分属两份包拷贝，出现难以排查的上下文失效；版本错位使该风险更难被注意到
  - Fix: 二选一统一：删除直依赖 react-router 并把全部 import 保持 react-router-dom（同时将其版本与传递的 react-router 对齐），或整体迁移到 react-router 包并删除 react-router-dom；改后跑 npm ls react-router 确认单实例

- [Low][95] src/frontend/package.json:19-22 — @dnd-kit 三件套与 @novnc/novnc 仅被已不可达的遗留组件引用
  - ID: f_frontend_shell_10; verification: static
  - Evidence: grep 显示 @dnd-kit/core、sortable、utilities 的唯一引用方是 components/ProfileList.tsx:3-16；@novnc/novnc 的唯一引用方是 components/ProfileViewer.tsx:128 的动态 import 与 src/novnc.d.ts 的模块声明; 两组件均属 f_frontend_shell_01 的死树（仅被不可达的 App.tsx 引用），活代码（app/、features/、shared/）零引用; package.json:19-22 将四者列为生产 dependencies，随每次 npm ci 安装并进入依赖审计面
  - Impact: 无用依赖持续占用安装时间、lockfile 体积与漏洞审计噪声（novnc、dnd-kit 均为有实际攻击面的库）；若将来删除死树时漏删依赖，问题会长期残留
  - Fix: 随 f_frontend_shell_01 删除死树时一并从 package.json dependencies 移除 @dnd-kit/* 与 @novnc/novnc 并删除 src/novnc.d.ts，重新生成 package-lock.json 后以 npm ls 与一次完整 build 验证无残留引用

- [Low][100] src/frontend/src/components/ProfileViewer.tsx:272 — 遗留 VNC 查看器把剪贴板明文内容写入 console.log
  - ID: f_frontend_shell_11; verification: static
  - Evidence: ProfileViewer.tsx:272 console.log("[clipboard] poll: new text from VNC:", text.substring(0, 30)) 直接输出远程浏览器剪贴板的前 30 字符; 同文件 :186-190 的 sendPasteToVnc 亦有多条 console.log 记录剪贴板推送动作（不含明文，但暴露操作时序）; 该组件属死树（见 f_frontend_shell_01），当前构建产物不含此路径，故定级 Low；但剪贴板内容常含密码、令牌等敏感信息，一旦旧树被复活或代码被复制到 v2 会话实现即成为隐私泄漏
  - Impact: 当前无实际暴露（死代码）；风险在于模式扩散——v2 的 features/browser-session 剪贴板桥若沿用此调试日志习惯，用户的剪贴板明文会进入浏览器控制台与任何日志采集面
  - Fix: 删除该行及同文件其余 clipboard 相关 console.log（保留 console.warn/debug 的无内容错误信息即可）；删除死树时一并消除，并在 v2 clipboard_bridge 侧确认无同类日志（属 frontend_features 单元，建议全局审阅时交叉核对）

- [Low][75] src/frontend/src/shared/api/client.ts:58-77 — ApiClient 接受绝对 URL 却仍强制 credentials:include 并附 CSRF 头，存在潜在的跨源凭据外带路径
  - ID: f_frontend_shell_12; verification: static
  - Evidence: client.ts:58-60 endpoint 以 "http" 开头时直接作为完整 URL 使用，绕过 baseUrl 拼接；:66 credentials 默认 "include"；:71-77 写方法无条件附 X-CSRF-Token（值来自会话 cookie/内存）; 当前全部内置调用方（client.ts:148-288 的 profiles/artifacts/automation/auth/health）只传相对路径，代码内无绝对 URL 调用，故为潜在而非现行问题; artifacts.downloadUrl（:242-244）返回的 URL 若被未来调用方回喂给 request，或任何数据驱动的 URL 进入 request，CSRF token 与会话 cookie 将被发往该源
  - Impact: 一旦未来有调用方把外部/用户可控 URL 传入 request，CSRF token 会随写请求发往第三方源，削弱双提交 CSRF 防护；同源策略下 cookie 虽受 CORS 限制不回读，但 token 出现在出站请求头本身即是泄漏
  - Fix: 在 request 入口校验解析后的 URL 必须与 location.origin（或配置的 baseUrl 源）同源，跨源直接抛错；确有跨源需求时显式 opt-in 且不附 CSRF 头与 credentials，并补 client.test.ts 的跨源拒绝用例

- [Low][85] src/frontend/src/shared/api/client.ts:104-127 — ApiError 丢弃契约 ErrorResponse 的 error 码与 retryable 标志，调用方无法区分可重试错误
  - ID: f_frontend_shell_13; verification: static
  - Evidence: generated 的 ErrorResponse 定义为 {error, message, retryable}（cbrowser_v1.d.ts components.schemas.ErrorResponse），且多个 operation 把 503 标注为 "Database busy (retryable)"、422 使用含 detail 数组的 ValidationErrorResponse; client.ts:104-127 解析错误体时仅提取字符串型 detail 或 message 拼 ApiError.message，error 码、retryable、ValidationErrorDetail[] 全部丢弃，ApiError 类（:13-22）也只有 status 与原始 data 字段（data 未在任何 UI 路径被结构化消费）; providers.tsx:46-50 的 react-query 全局策略只能统一 retry:1，无法对 retryable=false 的 4xx 免重试、对 503 按服务端标志退避
  - Impact: 契约层明确给出的可重试语义在前端被抹平：校验错误（不可重试）与数据库忙（可重试）走同一路径，用户看到的错误信息也丢失结构化 detail（如字段级校验原因），排障与体验均受损
  - Fix: 扩展 ApiError 携带 errorCode 与 retryable（从 ErrorResponse 解析，ValidationErrorResponse 时保留 detail 数组），并让 react-query 的 retry 函数改为按 ApiError.retryable/status 决策；在 client.test.ts 增加 503 retryable 与 422 detail 两种响应体的解析用例

- [Info][100] src/frontend/src/assets/logo.svg:1-46 — src/assets 下两份品牌 SVG 与 public 下同名文件逐字节重复且无人引用
  - ID: f_frontend_shell_14; verification: static
  - Evidence: diff 验证 src/assets/logo.svg 与 public/logo.svg、src/assets/menubar-icon.svg 与 public/menubar-icon.svg 逐字节相同; 全仓 grep 无任何文件 import src/assets/*.svg；所有引用都走 public 的 URL 路径（index.html:6 的 /logo.svg、AppLayout.tsx:97 的 /menubar-icon.svg、遗留组件中的 /logo.svg）
  - Impact: 同一品牌资源双份留存，后续换 logo 时极易只改一份造成 favicon 与页内图标不一致；属低风险卫生问题
  - Fix: 删除 src/assets/ 下两份重复 svg（保留 public/ 为唯一来源），或反之统一走 bundler import 并删除 public 副本，二选一后全局 grep 确认引用一致

- [Info][90] src/frontend/src/components/ProfileFiles.test.tsx:1-156 — 本单元的组件级测试全部落在已不可达的遗留组件上，活外壳无专属测试
  - ID: f_frontend_shell_15; verification: static
  - Evidence: 本单元内测试文件：app/auth_guard.test.tsx 与 app/router.test.tsx 是集成式渲染测试（真实覆盖 RequireAuth/路由/providers，质量高），shared/api/client.test.ts 与 sse.test.ts 用真实 node:http 服务器验证线缆行为（非 mock 自身逻辑）; 但 components/ProfileFiles.test.tsx（156 行）与 components/ProfileForm.test.tsx（106 行）测的都是 f_frontend_shell_01 死树组件，其断言的下载 URL 还是 v1 形状 /api/profiles/p1/files/a1（ProfileFiles.test.tsx:84-86）; 活外壳组件 AppLayout.tsx（292 行，含显示设置待应用、启停、搜索过滤逻辑）与 shared/components/BrowserSessionMount.tsx 在本单元内无专属测试文件，仅经集成测试间接触达
  - Impact: 测试套件给出虚假的安全感：约 260 行测试维护成本花在永不运行的代码上，而活外壳的交互回归只能靠集成测试的大网兜底，定位粒度粗
  - Fix: 随死树删除一并删除其专属测试；把其中仍有价值的行为断言（如文件面板焦点管理、Escape 关闭）对照 v2 的 features/artifacts 实现补到 frontend_features 单元的对应测试中，并为 AppLayout 的 displayPending/启停按钮状态补组件级用例

- [Info][90] src/frontend/src/i18n.tsx:690-706 — locale 切换不回写 document.lang 且存储键保留上游 cbm 前缀，文档/无障碍一致性小缺口
  - ID: f_frontend_shell_16; verification: static
  - Evidence: index.html:2 硬编码 <html lang="en">，i18n.tsx 的 I18nProvider（:713-731）切换 locale 时只写 localStorage 与 context，未同步 document.documentElement.lang，zh 界面下屏幕阅读器仍按 en 发音规则处理; STORAGE_KEY 为 "cbm.locale"（i18n.tsx:690），cbm 是上游 CloakBrowser-Manager 的缩写，本仓已更名 CBrowser，键名属上游残留（更改键名需考虑老用户已存偏好的迁移，故仅记录）; 正面事实：en/zh 字典 291 键静态比对完全对齐，t() 有 en 回退与 {param} 插值，localStorage 检测有 navigator.language 兜底，本项仅为边角一致性问题
  - Impact: 影响轻微：无障碍朗读语言不准、品牌更名残留一处内部键名；无功能影响
  - Fix: 在 I18nProvider 中以 useEffect 同步 document.documentElement.lang = locale === "zh" ? "zh-CN" : "en"；cbm.locale 键名如要更名应做读旧写新的兼容迁移，否则保留并在代码注释中标明其历史来源

## views

```json
{
  "contracts": {
    "reviewer": "046ceb3a-f093-49d9-813c-b13a18f5d981",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "046ceb3a-f093-49d9-813c-b13a18f5d981",
    "status": "completed"
  },
  "design": {
    "reviewer": "046ceb3a-f093-49d9-813c-b13a18f5d981",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "046ceb3a-f093-49d9-813c-b13a18f5d981",
    "status": "completed"
  },
  "performance": {
    "reviewer": "046ceb3a-f093-49d9-813c-b13a18f5d981",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "046ceb3a-f093-49d9-813c-b13a18f5d981",
    "status": "completed"
  },
  "security": {
    "reviewer": "046ceb3a-f093-49d9-813c-b13a18f5d981",
    "status": "completed"
  },
  "tests": {
    "reviewer": "046ceb3a-f093-49d9-813c-b13a18f5d981",
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
  "src/frontend/src/App.tsx",
  "src/frontend/src/app/AppLayout.tsx",
  "src/frontend/src/app/RequireAuth.tsx",
  "src/frontend/src/app/auth_guard.test.tsx",
  "src/frontend/src/app/providers.tsx",
  "src/frontend/src/app/router.test.tsx",
  "src/frontend/src/app/router.tsx",
  "src/frontend/src/assets/logo.svg",
  "src/frontend/src/assets/menubar-icon.svg",
  "src/frontend/src/components/CdpEndpointButton.tsx",
  "src/frontend/src/components/LanguageToggle.tsx",
  "src/frontend/src/components/LaunchButton.tsx",
  "src/frontend/src/components/LaunchErrorBanner.tsx",
  "src/frontend/src/components/LoginPage.tsx",
  "src/frontend/src/components/NativeWindowStatus.tsx",
  "src/frontend/src/components/ProfileFiles.test.tsx",
  "src/frontend/src/components/ProfileFiles.tsx",
  "src/frontend/src/components/ProfileForm.test.tsx",
  "src/frontend/src/components/ProfileForm.tsx",
  "src/frontend/src/components/ProfileList.tsx",
  "src/frontend/src/components/ProfileViewer.tsx",
  "src/frontend/src/components/SettingsPanel.tsx",
  "src/frontend/src/components/StatusIndicator.tsx",
  "src/frontend/src/components/SystemStatusBadge.tsx",
  "src/frontend/src/components/UpdateBanner.tsx",
  "src/frontend/src/i18n.tsx",
  "src/frontend/src/main.tsx",
  "src/frontend/src/novnc.d.ts",
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
  "src/frontend/tsconfig.tsbuildinfo",
  "src/frontend/vite.config.ts",
  "src/frontend/vite.selkies.config.ts",
  "src/frontend/vitest.config.ts"
]
```

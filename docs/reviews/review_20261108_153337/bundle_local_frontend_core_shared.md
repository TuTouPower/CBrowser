# bundle_local_frontend_core_shared

## responsibilities

- 应用顶层装配与上下文分发（QueryClient、认证鉴权、i18n 多语言、亮暗主题、全局 Toast）
- 统一 API 客户端（ApiClient）与同源防御（resolveSameOriginUrl，CSRF Token 注入，请求超时与中止信号控制）
- SSE 运行时状态同步桥接（ProfileEventsClient / SseSyncBridge），将推送事件注入 React Query 缓存
- 通用 UI 基础组件库（基于 Radix UI 原语封装 Dialog, DropdownMenu, Select, Popover 等）
- 构建配置与规范检查（Vite 8, TypeScript 5.9, scripts/design_tokens.mjs 规范门禁）

## interfaces

- ApiClient / useApiClient 类型化 API 客户端
- ProfileEventsClient / useProfileEvents SSE 运行时事件流
- useActionKeyMutation 幂等请求包装器
- useTheme, useI18n 全局上下文钩子

## dependencies

- React 19.3
- React Router 8.5
- @tanstack/react-query 5.106
- Radix UI
- Tailwind CSS 4.3
- @google/design.md

## flows

- 应用加载流：index.html (theme_boot.js) -> main.tsx -> AppProviders -> AuthProvider -> RequireAuth 守卫 -> AppLayout
- SSE 同步流：认证就绪 -> AuthenticatedSseBridge -> 连接 /api/v1/events -> 校验事件 -> 写入 Query 缓存
- 出站拦截流：ApiClient.request -> resolveSameOriginUrl 校验同源 -> 附加 CSRF Header -> 挂载超时 AbortSignal -> fetch

## constraints

- 严格同源解析，跨源直接抛出 ApiError(0)
- 零颜色字面量与非语义尺寸，必须使用 DESIGN.md 派生语义 token
- 无凭据持久化，Token 与密码严禁写入 Web Storage

## decisions

- ADR 021: 迁移至 React Router 8 单包架构
- OpenAPI Schema 单向生成 TypeScript 类型定义（npm run generate:api）
- SSE 401 或长期失活主动触发 logout 并清理内存 CSRF 令牌

## evidence

- src/frontend/src/app/providers.tsx:1-80
- src/frontend/src/shared/api/client.ts:63-220
- src/frontend/src/shared/api/same_origin.ts:1-40
- src/frontend/src/shared/api/sse.ts:185-320
- src/frontend/src/styles/design_tokens.css:1-200

## uncertainties

## Findings

- [High][90] src/frontend/src/app/router.tsx:12-71; src/frontend/src/main.tsx:8-14 — 全局与路由树缺少 ErrorBoundary，组件渲染异常导致白屏崩溃

    - ID: f_frontend_missing_error_boundary; verification: static
    - Evidence: main.tsx 直接挂载 RouterProvider，router.tsx 定义的路由树根节点及各子路由均未声明 errorElement 或 ErrorBoundary
    - Impact: 任一子组件在渲染期发生未捕获异常时，整个 React Fiber 树完全卸载，页面直接白屏，用户失去全部交互与错误上下文
    - Fix: 在 shared/ui 实现通用 ErrorBoundary 组件并在 router.tsx 根路由配置 errorElement: <RouteErrorFallback />

- [Medium][90] src/frontend/src/app/router.tsx:4-10 — 路由页面同步导入，未做按需代码分割与懒加载

    - ID: f_frontend_router_no_code_split; verification: static
    - Evidence: router.tsx 顶层直接同步 import 了 SessionPage, SettingsPage, EnvironmentListPage, ProxyListPage 等全部页面组件
    - Impact: 首屏加载必须下载包含流媒体会话、WebRTC 适配、代理与自动化配置在内的完整巨大 JS Bundle，拖慢 FCP 与 TTI
    - Fix: 使用 React.lazy() 配合 <Suspense> 改造所有二级路由页面为按需懒加载

- [Medium][85] src/frontend/src/app/useRuntimeSnapshot.ts:16-21; AppLayout.tsx:95; useProfilesQuery.ts:444 — 全局布局轮询全量 Runtime 查询并在 SSE 更新时产生并发 HTTP 惊群

    - ID: f_frontend_runtime_snapshot_thundering_herd; verification: static
    - Evidence: useRuntimeSnapshot 在全局 AppLayout 挂载，使用 useQueries 对全量 Profile 发起并发 getRuntime 请求; 每次 SSE 广播事件触发 invalidateQueries，导致全量 Profile 的 getRuntime 瞬间并发重发
    - Impact: 当 Profile 数量增加时，每次状态更新引发大量并发 HTTP 请求产生网络惊群，增加后端压力并抵消 SSE 收益
    - Fix: 提供单一聚合接口，或在前端仅基于本地 QueryClient 已有缓存进行聚合计算，不再主动为未激活详情的 Profile 挂载独立 fetcher

- [Low][85] src/frontend/src/shared/ui/cn.ts:1-5 — cn 仅执行简单字符串拼接，缺少 Tailwind 样式优先级覆盖合并

    - ID: f_frontend_cn_class_collision; verification: static
    - Evidence: cn 函数实现仅为 parts.filter(Boolean).join(' ')，未处理同一属性的 Tailwind 类名冲突
    - Impact: 外部传入自定义高度/边距类名时，与组件内部默认类名并存，生效规则取决于 CSS 编译顺序，产生样式覆盖不确定 Bug
    - Fix: 引入 tailwind-merge 处理类名覆盖合并，或在基础组件中使用排他型 variant 控制

- [Medium][95] src/frontend/src/i18n.tsx:924,937-941,968; src/frontend/src/i18n.test.tsx:33-42 — 违反零兼容负担铁律：保留上游旧仓 cbm.locale 存储键迁移兼容逻辑与无用测试

    - ID: f_frontend_legacy_cbm_locale_key; verification: static
    - Evidence: i18n.tsx:924 定义了 LEGACY_STORAGE_KEY = 'cbm.locale'，并在 937-941 行实现读旧写新并删除旧键的兼容迁移逻辑; i18n.test.tsx:33 为该兼容逻辑单独编写了单元测试; cbm 为上游已废弃项目 CloakBrowser-Manager 的历史缩写，CBrowser 作为破坏性重构项目，严禁背负旧系统兼容包袱
    - Impact: 在核心基础设施中引入不必要的历史迁移兼容逻辑，违背零兼容负担原则
    - Fix: 彻底删除 LEGACY_STORAGE_KEY 及所有相关的旧键读取和清理代码，清理对应单元测试

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "agent_frontend_core_shared"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "agent_frontend_core_shared"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "agent_frontend_core_shared"
  },
  "performance": {
    "status": "completed",
    "reviewer": "agent_frontend_core_shared"
  },
  "design": {
    "status": "completed",
    "reviewer": "agent_frontend_core_shared"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "agent_frontend_core_shared"
  },
  "tests": {
    "status": "completed",
    "reviewer": "agent_frontend_core_shared"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "agent_frontend_core_shared"
  }
}
```

## files_reviewed

```json
[
  "src/frontend/index.html",
  "src/frontend/package.json",
  "src/frontend/public/favicon-dark.svg",
  "src/frontend/public/favicon-light.svg",
  "src/frontend/public/favicon.svg",
  "src/frontend/public/logo.svg",
  "src/frontend/public/menubar-icon.svg",
  "src/frontend/public/theme_boot.js",
  "src/frontend/scripts/check_node.mjs",
  "src/frontend/scripts/design_tokens.mjs",
  "src/frontend/scripts/design_tokens.test.mjs",
  "src/frontend/src/app/AppLayout.focus.test.tsx",
  "src/frontend/src/app/AppLayout.shell.test.tsx",
  "src/frontend/src/app/AppLayout.tsx",
  "src/frontend/src/app/RequireAuth.tsx",
  "src/frontend/src/app/auth_guard.test.tsx",
  "src/frontend/src/app/providers.defaults.test.tsx",
  "src/frontend/src/app/providers.tsx",
  "src/frontend/src/app/providers.unauthorized.test.tsx",
  "src/frontend/src/app/router.test.tsx",
  "src/frontend/src/app/router.tsx",
  "src/frontend/src/app/useRuntimeSnapshot.ts",
  "src/frontend/src/i18n.test.tsx",
  "src/frontend/src/i18n.tsx",
  "src/frontend/src/main.tsx",
  "src/frontend/src/routes/PlaceholderPage.tsx",
  "src/frontend/src/shared/api/action_key_mutation.ts",
  "src/frontend/src/shared/api/client.sameorigin.test.ts",
  "src/frontend/src/shared/api/client.test.ts",
  "src/frontend/src/shared/api/client.ts",
  "src/frontend/src/shared/api/client_context.tsx",
  "src/frontend/src/shared/api/generated/cbrowser_v1.d.ts",
  "src/frontend/src/shared/api/same_origin.ts",
  "src/frontend/src/shared/api/sse.control.test.ts",
  "src/frontend/src/shared/api/sse.sameorigin.test.ts",
  "src/frontend/src/shared/api/sse.test.ts",
  "src/frontend/src/shared/api/sse.transport.test.ts",
  "src/frontend/src/shared/api/sse.ts",
  "src/frontend/src/shared/api/sse_generation.test.ts",
  "src/frontend/src/shared/api/sse_hardening.test.ts",
  "src/frontend/src/shared/api/sse_preview.test.ts",
  "src/frontend/src/shared/api/sse_t035_runtime_fields.test.ts",
  "src/frontend/src/shared/api/types.ts",
  "src/frontend/src/shared/ui/Banner.tsx",
  "src/frontend/src/shared/ui/Button.tsx",
  "src/frontend/src/shared/ui/Checkbox.tsx",
  "src/frontend/src/shared/ui/Dialog.tsx",
  "src/frontend/src/shared/ui/DialogWidth.test.tsx",
  "src/frontend/src/shared/ui/DropdownMenu.tsx",
  "src/frontend/src/shared/ui/EmptyState.tsx",
  "src/frontend/src/shared/ui/Input.tsx",
  "src/frontend/src/shared/ui/Popover.tsx",
  "src/frontend/src/shared/ui/Select.tsx",
  "src/frontend/src/shared/ui/StatusBadge.tsx",
  "src/frontend/src/shared/ui/Switch.tsx",
  "src/frontend/src/shared/ui/Table.tsx",
  "src/frontend/src/shared/ui/Toast.tsx",
  "src/frontend/src/shared/ui/Tooltip.tsx",
  "src/frontend/src/shared/ui/cn.ts",
  "src/frontend/src/shared/ui/index.ts",
  "src/frontend/src/shared/ui/ui.test.tsx",
  "src/frontend/src/styles/design_tokens.css",
  "src/frontend/src/styles/globals.css",
  "src/frontend/src/test_setup.ts",
  "src/frontend/src/theme.test.tsx",
  "src/frontend/src/theme.tsx",
  "src/frontend/src/theme_boot.test.mjs",
  "src/frontend/src/vite-env.d.ts",
  "src/frontend/tsconfig.json",
  "src/frontend/tsconfig.test.json",
  "src/frontend/vite.config.ts",
  "src/frontend/vite.selkies.config.ts",
  "src/frontend/vitest.config.ts"
]
```

# p111 启用系统 settings 持久化表并统一前端筛选、布局与标签页静音状态分层

- 来源：技术债自查（2026-11-16 按开发铁律全仓状态排查）
- 内容：与代理测速刷新丢失同根源，全仓存在多处状态归属分裂与未持久化缺口：1）后端数据库已建 `settings` 表（`SettingModel`，甚至被 `repository.py:20` 导入）却零 CRUD/API，导致主题（`theme.tsx`）与界面语言（`i18n.tsx`）等全局设置仅存浏览器 `localStorage`，换浏览器/清缓存即丢——应正式开放 `/api/v1/settings` 持久化（`localStorage` 仅保留首屏防闪烁本地镜像）；2）`ProxyListPage.tsx:84-87` 将搜索词 `query`、协议筛选 `scheme`、位置筛选 `region` 与视图布局 `layout` 全部存放在组件 `useState`，刷新页面即丢失（不同于 `EnvironmentListPage` 的 URL SearchParams + `localStorage`）——应统一迁移至 URL SearchParams 与持久化布局偏好；3）`useBrowserSession.ts:59` 的 `audioMuted` 仅为内存 `useState(false)`，刷新标签页即恢复有声——考虑到双页面独立静音要求（`test_frontend_session_e2e.py`），应按标签页隔离持久化于 `sessionStorage`（如随 `selkies_tab_id` 或会话页实例作用域），而非跨页共享。
- 处理：t074；resolution=transferred；reason=已合并转交 t074（settings API、主题语言同步、标签页静音与代理筛选持久化；其中容器尺寸底座与环境弹窗归 t073）

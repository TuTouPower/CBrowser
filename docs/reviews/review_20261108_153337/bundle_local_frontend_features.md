# bundle_local_frontend_features

## responsibilities

- 远程画质传输与输入适配（browser-session）：Selkies iframe 注入、WebRTC 信令重写、Web Locks 多 Tab 冲突抢占换签
- 会话状态机驱动（useBrowserSession）：checking_runtime -> connecting_signaling -> media_waiting -> connected
- 音频质量监控（deriveAudioStatus）与静音控制、诊断面板（RTT、丢包率、首帧解码统计）与专注模式切换
- Profile 隔离与环境生命周期控制（profiles）：配置表单、指纹分辨率、SOCKS5 代理绑定、平台字体集选择、启动/停止/重置
- 代理与自动化接入配置（proxies, automation, artifacts, settings）：CDP 凭证展示、文件上传下载、局域网 HTTPS 配置

## interfaces

- useBrowserSession(profileId, iframeRef, options) 会话主控制器
- installSelkiesClientAdapter(win, profileId) iframe 注入 hook
- useProfilesQuery, useProfileRuntimeQuery Profile 状态与变更 hook
- useBatchActions 批量操作执行器

## dependencies

- WebRTC (RTCPeerConnection, RTCDataChannel)
- Web Locks API (navigator.locks)
- TanStack React Query 5
- React Router 8

## flows

- WebRTC 会话建立流：SessionPage 挂载 -> useBrowserSession 检查运行态 -> 挂载 iframe -> adapter.ts 拦截握手 -> 检查 Web Locks -> 建立信令 -> 检出 framesDecoded -> 转移为 connected
- 多 Tab 冲突换签流：用户 Duplicate Tab -> 检测 lock 失败 -> 生成全新 tab ID 存入 sessionStorage -> 关闭旧 WS 重新连接
- 环境重置流：用户点击重置 -> 弹出确认弹窗 -> 提交重置请求 -> API 重新生成种子与版本 -> 触发重启

## constraints

- 单机直连，ICE 强制 iceServers: []，严禁回退外部 STUN/TURN
- 绝对分辨率锁定，丢弃前端尺寸变更请求，尺寸完全由 Profile 配置决定
- 零 Token 接触，前端完全不持有 Selkies master token，由后端代理注入

## decisions

- iframe 卸载时严格遵循 AC-003：仅清理定时器并置空 iframe.src，绝不停止容器
- 剪贴板自动同步由 iframe 内 Selkies seamless 客户端直接完成，宿主仅监听权限提示

## evidence

- src/frontend/src/features/browser-session/adapter.ts:22-370
- src/frontend/src/features/browser-session/useBrowserSession.ts:48-528
- src/frontend/src/features/browser-session/SessionPage.tsx:150-250
- src/frontend/src/features/profiles/useProfilesQuery.ts:150-450
- src/frontend/src/features/settings/SettingsPage.tsx:110-250

## uncertainties

## Findings

- [High][90] src/frontend/src/features/settings/SettingsPage.tsx:185-203 — 确认应用网络设置后启动的 pollTimer 闭包泄漏，组件卸载后无休止空转

    - ID: f_frontend_settings_poll_timer_leak; verification: static
    - Evidence: SettingsPage.tsx:185 启动 pollTimer = setInterval(...) 轮询操作状态，未保存至 ref，未在卸载时 clearInterval，且 catch 吞没异常持续执行
    - Impact: 用户在操作进行中离开页面，计时器永久驻留内存以 1 秒为周期持续请求后端，并在已卸载组件上触发更新与内存泄漏
    - Fix: 使用 useRef 保存定时器句柄，在 useEffect cleanup 中清除，并增加最大重试轮询次数限制

- [Medium][85] src/frontend/src/features/browser-session/useBrowserSession.ts:77-79,192-194,518-528 — 会话卸载清理钩子未清理 transportRecoveryTimerRef 导致内存泄漏

    - ID: f_frontend_session_recovery_timer_leak; verification: static
    - Evidence: useBrowserSession.ts:192 启动了 transportRecoveryTimerRef.current = setTimeout(...)，但在 518-528 行卸载清理中未清除
    - Impact: 用户在信令重连期间关闭页面，定时器依然会在后台触发一次多余的 getRuntime 请求
    - Fix: 在 useEffect 卸载清理函数中增加 if (transportRecoveryTimerRef.current) clearTimeout(transportRecoveryTimerRef.current)

- [Medium][85] src/frontend/src/features/browser-session/useBrowserSession.ts:82,202-256 — mountedRef 错误挂载在参数驱动的 checkRuntime 副作用上，生命周期判断失真

    - ID: f_frontend_mounted_ref_lifecycle; verification: static
    - Evidence: mountedRef 挂在 checkRuntime 的 useEffect 上；若传入 options.initialStage，在 205 行提前 return 导致未注册 cleanup，卸载后 mountedRef 恒为 true; 当 reconnect() 导致 reloadKey 自增时，重新触发导致 mountedRef 短暂被置为 false
    - Impact: 异步回调中的 if (!mountedRef.current) 守卫失效，或在重连时误杀正在执行的异步操作
    - Fix: 使用独立的空依赖 useEffect 管理组件真实的 mount/unmount 状态

- [Medium][85] src/frontend/src/features/browser-session/SessionPage.tsx:158,184-193; useBrowserSession.ts:387-465 — 会话页与底层 Hook 存在状态机分流，后台 Profile 停止后 WebRTC 轮询未停止

    - ID: f_frontend_session_stage_split_brain; verification: static
    - Evidence: SessionPage 依据 runtimeQuery.data 计算 stage；而 useBrowserSession 内部维持独立 stage 且只在初始化查一次 runtime; 外部 Profile 停止时，页面显示未就绪，但 useBrowserSession 内部仍为 connected，每秒继续对 iframe 执行 \_\_getWebRTCStats()
    - Impact: 状态机两处分流造成数据不一致，并在容器已停止时产生无意义的后台指标轮询开销
    - Fix: 将 useProfileRuntimeQuery 的数据状态作为入参或依赖传入 useBrowserSession，消除重复请求与分流

- [Medium][85] src/frontend/src/features/settings/SettingsPage.tsx:16-59,112-238 — 网络与字体设置绕过 OpenAPI 生成契约与 ApiClient 抽象，手写重叠 DTO 与裸请求

    - ID: f_frontend_settings_contract_violation; verification: static
    - Evidence: SettingsPage 手写定义 NetworkAccessConfig 等接口并通过 client.request 发起裸请求，未封装至 ApiClient 且未复用 useFontSetsQuery; 违背 docs/blueprint/conventions.md 关于 OpenAPI 统一生成类型的约定
    - Impact: 后端契约调整时无法通过 test:types 静态检出漂移，增加代码维护难度
    - Fix: 从 shared/api/types.ts 导入生成的类型并在 ApiClient 中封装网络设置子域

- [Medium][80] src/frontend/src/features/profiles/ProfileDetailPage.tsx:68-74,98-106 — Profile 详情页 Tab 与打开会话操作使用原生 <a> 标签，破坏 SPA 客户端路由

    - ID: f_frontend_profile_detail_nav_link; verification: static
    - Evidence: ProfileDetailPage 中 TABS.map 与打开会话直接使用 <a href='...'> 标签
    - Impact: 用户在详情页切换 Tab 时触发浏览器整页硬刷新，重新下载 HTML 并丢失 React Query 内存缓存与 SSE 状态
    - Fix: 使用 react-router 的 <Link> 或 <NavLink> 替代原生 <a> 标签

- [Medium][80] src/frontend/src/features/profiles/MaintenanceTab.tsx:24-37 — 维护面板删除 Profile 成功后未执行路由重定向

    - ID: f_frontend_maintenance_missing_redirect; verification: static
    - Evidence: handleDelete 在 deleteMutation.mutateAsync 成功后未做任何跳转
    - Impact: 环境已被删除，界面依然停留在已失效路由，后续 Query 抛出 404 并展示空界面
    - Fix: 引入 useNavigate，在删除成功后执行 navigate('/', { replace: true })

- [Low][80] src/frontend/src/features/browser-session/adapter.ts:26,50,98,108 — Selkies 适配层采用松散 any 强制转换，缺乏结构化类型约束

    - ID: f_frontend_adapter_any_casting; verification: static
    - Evidence: adapter.ts 大量使用 const win = targetWindow as any，以及 args: any[]
    - Impact: 削弱 TypeScript 静态检查能力，WebRTC 或上游 Selkies 变更时无法在编译期暴露接口破坏风险
    - Fix: 为 targetWindow 扩展强类型 SelkiesWindow 接口，消除裸 any 强转

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "agent_frontend_features"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "agent_frontend_features"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "agent_frontend_features"
  },
  "performance": {
    "status": "completed",
    "reviewer": "agent_frontend_features"
  },
  "design": {
    "status": "completed",
    "reviewer": "agent_frontend_features"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "agent_frontend_features"
  },
  "tests": {
    "status": "completed",
    "reviewer": "agent_frontend_features"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "agent_frontend_features"
  }
}
```

## files_reviewed

```json
[
  "src/frontend/src/features/artifacts/ProfileFilesTab.test.tsx",
  "src/frontend/src/features/artifacts/ProfileFilesTab.tsx",
  "src/frontend/src/features/artifacts/useArtifacts.actionkeys.test.tsx",
  "src/frontend/src/features/artifacts/useArtifacts.ts",
  "src/frontend/src/features/auth/LoginPage.tsx",
  "src/frontend/src/features/auth/redirect.test.ts",
  "src/frontend/src/features/auth/redirect.ts",
  "src/frontend/src/features/auth/useAuth.tsx",
  "src/frontend/src/features/automation/ProfileAutomationTab.test.tsx",
  "src/frontend/src/features/automation/ProfileAutomationTab.tsx",
  "src/frontend/src/features/automation/useAutomation.ts",
  "src/frontend/src/features/browser-session/ClipboardPermissionHint.test.tsx",
  "src/frontend/src/features/browser-session/ClipboardPermissionHint.tsx",
  "src/frontend/src/features/browser-session/EnvironmentSwitcher.test.tsx",
  "src/frontend/src/features/browser-session/EnvironmentSwitcher.tsx",
  "src/frontend/src/features/browser-session/FocusModeToolbar.test.tsx",
  "src/frontend/src/features/browser-session/FocusModeToolbar.tsx",
  "src/frontend/src/features/browser-session/SessionDetailsPanel.test.tsx",
  "src/frontend/src/features/browser-session/SessionDetailsPanel.tsx",
  "src/frontend/src/features/browser-session/SessionEntryPage.test.tsx",
  "src/frontend/src/features/browser-session/SessionEntryPage.tsx",
  "src/frontend/src/features/browser-session/SessionHeader.test.tsx",
  "src/frontend/src/features/browser-session/SessionHeader.tsx",
  "src/frontend/src/features/browser-session/SessionPage.test.tsx",
  "src/frontend/src/features/browser-session/SessionPage.tsx",
  "src/frontend/src/features/browser-session/SessionStagePanel.test.tsx",
  "src/frontend/src/features/browser-session/SessionStagePanel.tsx",
  "src/frontend/src/features/browser-session/adapter.ts",
  "src/frontend/src/features/browser-session/adapter_restart.test.ts",
  "src/frontend/src/features/browser-session/audio_control.ts",
  "src/frontend/src/features/browser-session/audio_status.test.ts",
  "src/frontend/src/features/browser-session/audio_status.ts",
  "src/frontend/src/features/browser-session/clipboard_bridge.ts",
  "src/frontend/src/features/browser-session/index.ts",
  "src/frontend/src/features/browser-session/selkies_adapter_entry.ts",
  "src/frontend/src/features/browser-session/session_audio_control.test.tsx",
  "src/frontend/src/features/browser-session/session_focus.tsx",
  "src/frontend/src/features/browser-session/session_keys.ts",
  "src/frontend/src/features/browser-session/types.ts",
  "src/frontend/src/features/browser-session/useBrowserSession.stages.test.tsx",
  "src/frontend/src/features/browser-session/useBrowserSession.test.tsx",
  "src/frontend/src/features/browser-session/useBrowserSession.transportRecovery.test.tsx",
  "src/frontend/src/features/browser-session/useBrowserSession.ts",
  "src/frontend/src/features/profiles/BatchActionBar.tsx",
  "src/frontend/src/features/profiles/ConfigTab.test.tsx",
  "src/frontend/src/features/profiles/ConfigTab.tsx",
  "src/frontend/src/features/profiles/EnvironmentCard.preview.test.tsx",
  "src/frontend/src/features/profiles/EnvironmentCard.tsx",
  "src/frontend/src/features/profiles/EnvironmentCardGrid.tsx",
  "src/frontend/src/features/profiles/EnvironmentEmptyState.tsx",
  "src/frontend/src/features/profiles/EnvironmentListPage.test.tsx",
  "src/frontend/src/features/profiles/EnvironmentListPage.tsx",
  "src/frontend/src/features/profiles/EnvironmentListToolbar.tsx",
  "src/frontend/src/features/profiles/EnvironmentTable.tsx",
  "src/frontend/src/features/profiles/GroupColorPicker.tsx",
  "src/frontend/src/features/profiles/GroupManagerDialog.test.tsx",
  "src/frontend/src/features/profiles/GroupManagerDialog.tsx",
  "src/frontend/src/features/profiles/MaintenanceTab.test.tsx",
  "src/frontend/src/features/profiles/MaintenanceTab.tsx",
  "src/frontend/src/features/profiles/ProfileCreateDialog.test.tsx",
  "src/frontend/src/features/profiles/ProfileCreateDialog.tsx",
  "src/frontend/src/features/profiles/ProfileDetailPage.test.tsx",
  "src/frontend/src/features/profiles/ProfileDetailPage.tsx",
  "src/frontend/src/features/profiles/ProfileForm.test.tsx",
  "src/frontend/src/features/profiles/ProfileForm.tsx",
  "src/frontend/src/features/profiles/ProfileIsolation.test.tsx",
  "src/frontend/src/features/profiles/SharedProfileBanners.tsx",
  "src/frontend/src/features/profiles/formatRelativeTime.ts",
  "src/frontend/src/features/profiles/scopeMutationToProfile.test.ts",
  "src/frontend/src/features/profiles/useBatchActions.ts",
  "src/frontend/src/features/profiles/useEnvironmentFilters.ts",
  "src/frontend/src/features/profiles/useEnvironmentLayout.ts",
  "src/frontend/src/features/profiles/useGroupReorder.ts",
  "src/frontend/src/features/profiles/useProfilesQuery.actionkeys.test.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.apply.test.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.applyresume.test.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.control.test.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.retry.test.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.test.tsx",
  "src/frontend/src/features/profiles/useProfilesQuery.ts",
  "src/frontend/src/features/profiles/useProfilesQuery.wait.test.ts",
  "src/frontend/src/features/proxies/ProxyFormDialog.test.tsx",
  "src/frontend/src/features/proxies/ProxyFormDialog.tsx",
  "src/frontend/src/features/proxies/ProxyListPage.test.tsx",
  "src/frontend/src/features/proxies/ProxyListPage.tsx",
  "src/frontend/src/features/proxies/ProxyListToolbar.tsx",
  "src/frontend/src/features/proxies/ProxyTable.tsx",
  "src/frontend/src/features/proxies/parseProxyUrl.test.ts",
  "src/frontend/src/features/proxies/parseProxyUrl.ts",
  "src/frontend/src/features/settings/SettingsPage.network.test.tsx",
  "src/frontend/src/features/settings/SettingsPage.test.tsx",
  "src/frontend/src/features/settings/SettingsPage.tsx"
]
```

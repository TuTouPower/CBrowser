# p025 Dialog 与权限弹窗分流及管道挂起防御

- 来源：借鉴 ego-lite 技术调研 / 用户提出
- 内容：实现浏览器弹窗分流与生命周期可靠性防护：1. 弹窗分流规则：alert、confirm、prompt、beforeunload 等页面级 JS Dialog 路由给 Agent 自动响应处理；摄像头、麦克风、地理位置、USB 等系统级权限弹窗路由给人类处理；2. 建立 Chromium 命令管道挂起防御：针对原生 JS Dialog 弹出期间 Chromium 挂起渲染线程、导致后续所有页面命令（含 Page.enable）超时崩溃的问题，在 CDP 代理层与客户端设立即时监听拦截与超时熔断恢复策略。
- 处理：未开

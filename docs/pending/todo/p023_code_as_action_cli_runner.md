# p023 基于 Playwright 的 Code-as-Action Agent 执行器与 Skill

- 来源：借鉴 ego-lite 技术调研 / 用户提出
- 内容：为外部 AI Agent 提供轻量宿主端执行工具链与 Skill：1. 提供 CLI 执行器（`cbrowser-agent <<'JS'`），支持单次会话批处理执行多步页面动作、等待与结果提取；2. 优先基于 Playwright `connectOverCDP` 实现底层交互，避免重复造轮子；3. 集成带引用的 aria snapshot 或可访问性树紧凑表征，建立 stable locator 与 `@refId` 持久映射；4. 驱动细节遵循反检测最佳实践，严禁使用 `isTrusted: false` 的合成事件兜底与全局探测变量；5. 实现两层 Skill 架构（薄入口 Skill + 随 CLI 动态下发规范）。
- 处理：未开

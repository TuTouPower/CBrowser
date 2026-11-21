# d053 固定 CloakBrowser 支持按 Profile 双向设置原生配色

- 来源：s027，验证于 2026-11-21。 [Spike 报告](../spikes/s027_profile_native_color_scheme/report.md)
- 结论：在固定 CloakBrowser `146.0.7680.177.3` / OrbStack arm64 上，浏览器启动前设置 Profile 的 `browser.theme.color_scheme2`（浅色 `1`、深色 `2`）和 Chromium 自带主题（`extensions.theme.system_theme = 0`），会同步改变标签栏、地址栏、工具栏和原生菜单。选用 GTK 系统主题时，其颜色优先。
- 证据：同一持久化 Profile 完成浅 → 深 → 浅，地址栏采样依次为 `(237,242,250)` → `(40,40,40)` → `(237,242,250)`。两实例同时保持独立配色。网页媒体偏好跟随环境，固定白底页实测仍为 `(255,255,255)`。实验代码和完整矩阵见 s027。
- 影响：t099 可在启动前将环境配色投影到 Chromium 原生偏好。网页媒体偏好沿用同一环境设置。目标引擎升级时应重验原生切换。
- 现状：有效

# 015 默认无中文字体 + per-profile 可选开源 CJK 字体包（2026-11-04T01:04:09+08:00）

- 背景：历史提交 `0b4dc78` 曾 purge 全部 CJK 字体以降低中文字体指纹暴露，Browser 镜像因此对中文网页缺字或 fallback。用户要求改为按 Profile 配置：部分 Profile 保持无中文字体，部分可选不同中文字体包。2026-11-03 已在本地真实引擎验证：字体放在 fontconfig 默认扫描路径之外、按 Profile 生成 `FONTCONFIG_FILE`（include 系统配置并追加字体目录）可精确开关 Chrome 的中文字体可见性。
- 选项：
    1. 镜像全局安装中文字体，所有 Profile 一律可见（回到指纹暴露且不可按 Profile 区分）。
    2. 镜像 staged 文泉驿微米黑/正黑到 `/opt/cbrowser-fonts/`（默认扫描路径之外），`ProfileConfig.font_bundle` 三档（`none` 默认、`wqy-microhei`、`wqy-zenhei`）经 Runner 生成专属 fontconfig 配置控制可见性。
    3. 引入 Windows 专有中文字体（SimSun、Microsoft YaHei）以贴近 Windows 平台伪装。
- 结论：采用选项 2。默认 `none` 保持既有反指纹基线；启用 bundle 的 Profile 明确接受 Linux 中文字体特征与 Windows 伪装不一致的取舍，镜像增大约 22MB。选项 3 因字体不可自由分发、授权风险明确不做。不挂载宿主字体目录、不在宿主数据目录预置字体文件；Stream 容器不涉及（画面渲染只发生在 Browser 容器）。
- 替代：无（`0b4dc78` 的全局 purge 由本决定的 staged + 开关机制取代其效果面，默认行为保持一致）

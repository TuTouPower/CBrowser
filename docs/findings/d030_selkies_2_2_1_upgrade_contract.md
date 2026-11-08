# d030 Selkies 2.2.1 升级契约（t043 / s012）

- 来源：`docs/spikes/s012_selkies_2_2_upgrade_contract/report.md` 正式 spike，2026-11-05 实测。
- 事实：PyPI 最新 2.x 为 2.2.1，METADATA 声明支持 Python 3.15。与 2.1.0 相比：Python 模块清单相同；`webrtc_signaling_server.py` 的 HELLO / client_tab_id / resume_key / resume 语义仅有一处日志字符串格式调整；`_XTestKeyboard` 私有 ABI（4 方法签名、`_BIND_SETTLE_S`、6 个实例属性）逐项 AST 校验全部一致；Web 客户端 `selkies-core.js` 从 `src/` 移到根但 `HELLO ${...}` 模板、`client_tab_id`、`resume_key` 上下文逐字相同（仅 minify 变量名变化）；`HELLO client ` 为运行时拼接串、不在静态字面量里，`adapter.ts` 的 `window.WebSocket` hook 保持有效。
- 需适配的变化：Web 客户端文件清单（新增 Inter 字体/rolldown chunk/jsdb，`src/` 两文件移除）须重生成 `config/selkies/selkies_web_sha256.txt`；index.html 新增 `__SELKIES_DEFER_INITIALIZATION`、modulepreload 与末尾 `selkies-core.js` module，vendor 注入 marker 写死的 2.1.0 bundle 名须改为通用 module tag（经典 IIFE adapter 仍在 head 首位、早于全部 module）；原生依赖 pixelflux 2.2.1→2.2.3、pcmflux 2.2.0→2.2.1。
- 结论：**可适配，无阻断性破坏变化**；t043 采用 2.2.1。x11_keymap 的 `version("selkies")` 硬编码门禁须放宽到目标版本，ABI 校验本身不变。
- 现状：有效（现行运行基线；ADR 022 / t043 已采用 Selkies 2.2.1）
- 采纳：t043（无后续 tid）。

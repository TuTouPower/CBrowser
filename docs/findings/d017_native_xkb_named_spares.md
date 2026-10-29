# d017 原生中文映射重载只可复用有 XKB 名称的空闲键位

- 来源：t004_v2_stream_runtime；补充 d014 的真实双页与长提交验证。
- 结论：固定 Selkies 2.1.0 在活跃 Chromium 中仅修改 core keymap 时可能仍按旧 XKB 映射解释按键。重载完整映射可以通知客户端刷新，但必须先按运行时 XKB 名称过滤 spare；无名称的键位会被 xkbcomp 合并为 `key <>`，破坏映射并触发 Native 缓存失效、重分配与确定性错序。不能靠延长等待或硬编码排除某个键码修复。
- 证据：真实 Xvfb 下原生 19 个绑定在重载前一致、重载后出现覆盖；仅排除键码 8 仍损坏键码 93；按实际名称过滤后 17 个绑定在重载前后均一致。正式量具为 `tests/fixtures/stream_probe/x11_keymap_probe.py` 与 `tests/e2e/test_stream_x11_keymap_e2e.py`。双 Google Chrome 连续 8 次提交、124 个汉字严格匹配远端 DOM，X11 剪贴板哨兵保持不变；独立冻结复验连续两轮通过。全部 spare 实际按住的负例曾允许覆盖，现已在生产适配器提前拒绝，真实 Xvfb 回归覆盖此边界。
- 影响：`stream_agent/x11_keymap.py` 固定 SDK 私有签名，保留 Native preferred 顺序与 settle 机制；evdev 容量必须按有限、未按住且未被当前批次占用的槽计算。t007/t008 沿用官方 composition 消息与 XTest，不回退剪贴板；升级 SDK/XKB 工具链时重跑真实重载和多页量具。同步子进程的延迟及资源开销仍须由 t009/t012 的 P95、1000 次与长期验收测量，当前短测不能代替。
- 现状：有效；只验证当前 Mac/OrbStack arm64 与固定依赖，不推定公网、原生 x86 或 OS 候选窗已通过。

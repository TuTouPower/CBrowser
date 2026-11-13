# p077 核验 Selkies 版本前提并启用双模回退

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P0-5、结论先行 1），依据 Selkies 官方 README 与 2.2.1 release notes
- 内容：上游 `selkies-project/selkies` README 明写「It streams over plain WebSockets by default, with WebRTC available as an opt-in transport」；2.2.1 release notes 同样把 WebSocket 称作 default 并注明「WebRTC behind NAT may still need a STUN/TURN server; the default WebSocket transport does not」。CBrowser 靠 `SELKIES_MODE=webrtc` + `SELKIES_WEBRTC_ICE_LITE=true` 强制 opt-in、`CBROWSER_WEBRTC_PUBLIC_IP=127.0.0.1` 同机直连无 TURN（`docs/specs/webrtc_remote_display.md`）。项目文档把 opt-in 表述成「Selkies 2.2.1 官方 WebRTC 远程捕获传输协议栈」，口径不精确、会误导后续升级决策；「无 TURN」应写成当前同机拓扑结论，而非协议前提。本次为只读调研，未授权改生产代码。
- 处理：未开
- 时间：2026-11-13T19:16:54+08:00
- 关联：p072（todo，Selkies 私有 ABI 重构；本条不重复其升级适配层范围）、p020（archive，ICE/TURN 5 秒延迟已闭环 t019）、p054（archive，Selkies wheel 缓存）

## 目标

1. 核对锁定 2.2.1 的实际 `SELKIES_MODE` / `SELKIES_ENABLE_DUAL_MODE` / ICE-lite 配置与 `--network` 拓扑，把文档口径改为「强制 opt-in 的 WebRTC + 当前拓扑无 TURN」。
2. 评估启用 `SELKIES_ENABLE_DUAL_MODE=true`：WebRTC 优先、媒体路径持续失败自动回退 WebSocket；上游 2.2.1 已把 stall 恢复从 19–22s 压到 2–4s，同机场景两种传输体验差距需实测。
3. 明确跨机 / 非 host 网络 / 公网时官方点名「容器无 host networking 时 WebRTC 需要 TURN」，按条件启用 coTURN + TURN-REST 短期凭据，不把无 TURN 写成架构前提。

## 谨慎边界

上游 `main` 已换 Rust 服务器与 `selkies-rtc`（未找到官方 3.x 稳定 tag），不能把当前 main 的结论武断套到钉死的 2.2.1 Python 服务器；版本代际差异本身需复核。

## 验收

1. 文档与部署配置对默认传输、opt-in 方式、无 TURN 适用范围三者表述一致且可核对。
2. 双模回退在媒体路径持续失败时自动降级，viewer 无感；真链 E2E 覆盖 WebRTC 与 WebSocket 两条路径。

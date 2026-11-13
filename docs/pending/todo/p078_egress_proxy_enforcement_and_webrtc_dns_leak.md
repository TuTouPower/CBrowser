# p078 出口代理强制化与 WebRTC/DNS 泄漏闭环

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P0-6、本仓风险节），借鉴 TransparentTorProxy、Chrome `WebRtcIPHandling` 策略、SealSkin 零宿主端口思路
- 内容：本地源码实读（非网上调研结论，需实测复核）：`network_policy.py:136-139` 对 Browser 角色公网出口 `-A OUTPUT -j ACCEPT` 全放行，`--proxy-server` 只在 Chromium 进程层生效；未配代理 Profile（`runner.py:110-111` 直接不加 `--proxy-server`）与其它未配代理 Profile 共享宿主出口 IP；代理端点不可达而 iptables 规则仍在时会从「走代理」降级为「裸奔宿主 IP」，现有 `verify_policy()` + `install_fail_closed()` 只对策略漂移，未见代理进程 watchdog。全仓未设 `WebRtcIPHandling` / `--host-resolver-rules` / `--proxy-bypass-list` / 禁 QUIC，DNS/DoH/QUIC 未拦 UDP/53、未统一 resolver。页面发起的 WebRTC `srflx` 候选与 Selkies 画面 WebRTC 是两条独立路径，ICE-lite 只管后者；mDNS `.local` 只护 host 候选不护 `srflx`。本次为只读调研，未授权改生产代码。
- 处理：未开
- 时间：2026-11-13T19:16:54+08:00
- 关联：p041（parked，独立桌面 app，已明确暂搁，不复活）、p062（archive，macOS OrbStack 网关透明代理，不同根因）、p016（archive，网络隔离与配额 E2E）、p055（archive，privacy allowlist）

## 与 p041 的边界与冲突

p041 写「Docker 版由每环境防火墙保证只走代理」并列出 `disable_non_proxied_udp` / `--disable-quic` 方案，但那是桌面 app 形态且用户已明确暂搁。**本条针对 Docker 版 netns，且须先实测复核「已保证」是否成立**，不能只凭文档；不复活 p041 的 LAN/桌面 app 范围。

## 目标

1. netns 内用 nftables `REDIRECT` 把 TCP/80,443 与 UDP/53 强制导向本地代理（代理自身 UID `return` 规避回环），代理进程死亡或规则被 flush 触发 `install_fail_closed()` 全 DROP；补代理进程 watchdog。
2. 显式设 `WebRtcIPHandling=disable_non_proxied_udp`、禁 QUIC、统一 resolver、`--host-resolver-rules` 固定解析路径。
3. 一 Profile 一 sticky 出口，避免 IP 段聚类；出口探测须与 Browser 同网络视角（p060 已闭环结论）。

## 验收

1. 代理进程被 kill 后 Browser 角色不通公网，且不回退宿主 IP 直连。
2. 检测页无 `srflx` 真实出口候选、无 DNS/QUIC 直出；解析归属与出口 IP 一致。
3. 两个未配代理 Profile 不共享可关联的出口身份；真链 E2E 覆盖强制代理与无代理两种 Profile。

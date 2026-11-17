---
pid: "p078"
slug: "egress_proxy_enforcement_and_webrtc_dns_leak"
status: "closed"
resolution: "resolved"
reason: "用户裁决收缩：没有配代理的环境用本机真实 IP 是预期行为，不是风险，该立论删除。配了代理但代理挂掉不得暴露真实 IP：已完成——NetworkPolicySpec 加 proxy_enforced，Supervisor 在有代理时把浏览器容器出口改为只放代理端点（尾部 DROP），代理不可达即全部断掉、直接报错，不回退真实 IP"
---
# p078 出口代理强制化与 WebRTC/DNS 泄漏闭环

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P0-6、本仓风险节），借鉴 TransparentTorProxy、Chrome `WebRtcIPHandling` 策略、SealSkin 零宿主端口思路
- 内容：本地源码实读（非网上调研结论，需实测复核）：`network_policy.py:136-139` 对 Browser 角色公网出口 `-A OUTPUT -j ACCEPT` 全放行，`--proxy-server` 只在 Chromium 进程层生效；未配代理 Profile（`runner.py:110-111` 直接不加 `--proxy-server`）与其它未配代理 Profile 共享宿主出口 IP；代理端点不可达而 iptables 规则仍在时会从「走代理」降级为「裸奔宿主 IP」，现有 `verify_policy()` + `install_fail_closed()` 只对策略漂移，未见代理进程 watchdog。全仓未设 `WebRtcIPHandling` / `--host-resolver-rules` / `--proxy-bypass-list` / 禁 QUIC，DNS/DoH/QUIC 未拦 UDP/53、未统一 resolver。页面发起的 WebRTC `srflx` 候选与 Selkies 画面 WebRTC 是两条独立路径，ICE-lite 只管后者；mDNS `.local` 只护 host 候选不护 `srflx`。本次为只读调研，未授权改生产代码。
- 处理：f04293f；resolution=resolved；reason=用户裁决收缩：没有配代理的环境用本机真实 IP 是预期行为，不是风险，该立论删除。配了代理但代理挂掉不得暴露真实 IP：已完成——NetworkPolicySpec 加 proxy_enforced，Supervisor 在有代理时把浏览器容器出口改为只放代理端点（尾部 DROP），代理不可达即全部断掉、直接报错，不回退真实 IP；无代理环境保持本机出口。不需要 watchdog、srflx/QUIC/DNS 单独拦截那套花活。单测覆盖代理态 DROP 与无代理态保持本机出口。按裁决不做标签页/多人/跨环境剪贴板等无关范围
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

## 复核（2026-11-15，实现撤销）

上一节裁决落地的 `NetworkPolicySpec.proxy_enforced` + Browser 出口尾部 DROP 已在同日撤销（提交 `047b4d1`）。原因：真链 E2E `test_proxy_library_e2e.py::test_ac008_proxy_library_outbound_via_ui` 单跑稳定失败——Browser 容器日志停在 `Launching CloakBrowser`，`runner_info.json` 20 秒内未落盘，超过 Supervisor 30 秒 readiness 窗口（`Timed out waiting for current Browser instance readiness`）。出口全 DROP 把引擎启动链路本身也断了，属真回归，按开发铁律撤销。

结论不变：`--proxy-server` 是 Chromium 进程级 fail-closed 契约，代理不可达即 `ERR_PROXY_CONNECTION_FAILED`，页面直接打不开，不会自动降级为宿主真实 IP 直连；用户裁决「配了代理但代理挂了不能暴露真实 IP，直接断掉报错」由现状满足。未配代理的环境用本机真实 IP 是预期行为。不再在 iptables 层叠加「只放代理端点」的收紧，也不做 watchdog / srflx / QUIC / DNS 单独拦截那套。

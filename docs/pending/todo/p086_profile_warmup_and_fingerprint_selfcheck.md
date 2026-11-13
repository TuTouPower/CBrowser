# p086 Profile 预热 cookie 与内置指纹自检清单

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P2-15），借鉴 Multilogin pre-farmed cookies、GoLogin/Dolphin Cookie Robot、CloakBrowser-Manager 首次启动书签
- 内容：per-Profile 首次启动前 warm-up（访问若干站点积累历史/cookie，对抗「空 jar 可疑」）；把 Pixelscan / Iphey / CreepJS / BrowserScan / BrowserLeaks TLS / reCAPTCHA / Turnstile 做成一键自检页，且自检测「跨 API 自洽 + 群体分布」而非刷单站 PASS——storage quota 二选一即证明两家检测站查的是相反方向，单站 PASS 不构成结论。本次为只读调研，未授权改生产代码。
- 处理：未开
- 时间：2026-11-13T19:16:54+08:00
- 关联：p040（parked，代理连通性与出口 IP 检测）、p028（archive，CDP fingerprint harness）、p074（原子身份 bundle）、p081（回归基线）、p085（群体分布）

## 风险与前置

- warm-up 与自检本身会向第三方站点发出可关联流量；必须在 per-Profile 网络视角下执行、不外送凭据，且不与 p078 的强制代理路径冲突。
- IP 回显 / 地理查询的隐私边界沿用 p060 已闭环结论（本机 GeoIP + 最小回显，优先不外送出口 IP）。
- 自检结果需可追溯（时间、目标站、视角、Profile 身份版本），不得把厂商自报通过率当 SLA。

## 验收

1. 新建 Profile 可按策略 warm-up，且 warm-up 流量只走该 Profile 的出口路径。
2. 一键自检给出跨 API 自洽与群体分布两类结论，单站 PASS 不显示为「通过」。
3. 自检不引入新的 localhost 端口暴露或 CDP 泄漏面。

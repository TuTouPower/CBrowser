# p081 引擎升级后的 Profile 级指纹回归基线

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P1-8），依据 CloakBrowser 闭源二进制、Foil 四层拆解、Client Hints 检测资料
- 内容：CloakBrowser 是闭源预编译 Chromium 二进制 + 开源 wrapper，C++ 补丁数量各来源说法不一（16/32/33/42/49/58/87），只能当营销口径、不能进规格或回归断言。引擎升级会改变 canvas/WebGL/audio 哈希、GPU renderer、`navigator` 值、Client Hints、storage quota，甚至 TLS/HTTP2 栈，从而破坏 Profile 身份一致性；而「TLS 继承真 Chrome」是厂商说法，容器 Linux 却报 Windows 时 JA4/JA3 与 UA/Client Hints 跨层一致性需单独实测。目标：`CLOAKBROWSER_VERSION` 钉死 + `CLOAKBROWSER_AUTO_UPDATE=false` + Ed25519 校验下载；为每个 Profile 建指纹可观测基线，升级前后比对 canvas/WebGL/audio 哈希、GPU renderer、`hardwareConcurrency`/`deviceMemory`/`screen`、UA + Client Hints（含 `getHighEntropyValues`）、`storage.estimate()` quota、HTTP 头 vs navigator、JA4/JA3、WebRTC ICE IP，任一漂移即判该 Profile 不可直接升级。本次为只读调研，未授权改生产代码。
- 处理：t068；resolution=transferred；reason=已核实当前代码与有效 task，按同一交付面聚合转交 t068；过时描述与剩余范围见 task spec，归档仅表示转办
- 时间：2026-11-13T19:16:54+08:00
- 关联：p072（todo，Selkies 私有 ABI 重构）、p028（archive，CDP fingerprint harness，已闭环 spike）、p045（parked，UA-CH arch，含 s014 三个探针脚本可复用）、p074（原子身份 bundle）、p077（Selkies 版本前提）

## 边界

不重复 p028 已闭环的「Playwright/CDP 兼容性与指纹增量」spike 结论；本条针对 cloakbrowser 引擎二进制升级对 Profile 身份的影响。补丁数量、自报通过率（0.9 reCAPTCHA v3、30/30、50+ 站点）无方法论与日期，不作验收依据。

## 验收

1. 引擎版本变更前后自动产出每个 Profile 的基线差异报告，漂移项可定位到具体 API。
2. 存在漂移时升级被阻断并给出该 Profile 的处置动作；无漂移时回归断言覆盖主文档、iframe、Worker、ServiceWorker 与请求头全上下文。
3. JA4/JA3 与 UA/Client Hints 一致性用实测数据判定，不引用厂商宣称。

# Task spec

## 背景

现行 ADR 007 允许多真人 Viewer 并发，但没有外部 Agent 与真人的强制仲裁。仅拦部分 CDP Mutating 方法不能阻止任意 evaluate 修改页面。通过断开/拒绝外部自动化通道建立可验证交接边界，保留多 Viewer 行为。

## 契约区

### 范围

- 新 ADR 明确 Profile 人机控制权、Agent 身份及实例代次；默认/重启/崩溃回 user，同 Profile 首版同时仅一个协作 Agent，恢复需真人显式操作。
- API 唯一持久化权威；Supervisor/Agent 执行强制通道 gate 与 fence，失联时拒绝新的 Agent 动作；同 Profile 多真人 Viewer 保持原契约。
- 在真实输入来源可辨识的 WebRTC/Stream 入口触发真人优先；接管边界后断开既有外部 CDP 通道、拒绝重连及 XTEST/清理旁路；已发送动作明确结果可能未知。
- CLI 主动 handOff、权限/验证码/2FA 交接，SSE 广播与 /manage 状态/恢复入口；操控纯画面不新增遮挡页头侧栏。

### 非范围

- 不引入通用租约平台，不限制真人多 Viewer；不支持任意只读 CDP 黑名单保证。
- 不自动识别所有 CAPTCHA 或解决验证码，不支持首版同 Profile 多 Agent 并发；不回滚浏览器已经执行的业务动作。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：默认、runtime 重启、旧 Agent 崩溃或身份失效后进入 user 安全状态；同 Profile 第二个 Agent 无授权不能进入，旧实例/旧身份不能复用控制权；API 是唯一业务 DB 写入者。
- [ ] AC-002：真人实际输入入口和主动 handOff 均形成可观察的交接边界；边界后的外部 Agent 命令被拒绝，已有自动化 CDP 通道被撤销且重连拒绝，任意 evaluate/callFunctionOn、跨 target/session 与清理均无旁路。
- [ ] AC-003：已执行或已进入浏览器的动作不被声称可撤销，调用方获得稳定状态/错误与结果未知语义；不因取消/超时自动重放。
- [ ] AC-004：接管仍保留同 Profile 多真人 Viewer 音视频、输入和 Browser 页面；关闭一个 Viewer 不停止浏览器；XTEST 自身事件不被误认成真人抢占来源。
- [ ] AC-005：user 状态下即使 CLI finish/异常退出，也不自动关闭本任务页面来绕过接管；真人显式恢复后 Agent 新动作可用，过期响应和 SSE 不覆盖新代次状态。
- [ ] AC-006：权限/设备提示或 CLI handOff 进入 user，JS Dialog 按 t030 处理且不无故切换控制权；恢复必须显式授权，不使用倒计时自动抢回。
- [ ] AC-007：/manage 可观察控制方、交接原因、实例与恢复结果，SSE 同步；操控页保持 ADR 006 纯画面，ADR 清楚说明与 ADR 007 真人多连接的关系。
- [ ] AC-008：云端真实服务/WS/CDP 与输入适配器测试覆盖已建立长连接的接管、竞争、失联、代次围栏及恢复；目标 WebRTC/X11 来源和原生权限交接用例交 t032。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、可用的普通 Chromium 测试，以及可收集的真实环境用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- ego-lite 参考仓库：https://github.com/citrolabs/ego-lite ；固定研究基线：https://github.com/citrolabs/ego-lite/tree/12407167f84a58af24044f072868051952131491 。云端可直接读取公开源码，无需本机目录。其 AGENTS.md 明确只开源 harness/Skill，浏览器本体与 globalThis.ego 原生绑定闭源；只能借鉴公开实现与故障案例，不依赖原生绑定，不照搬合成事件兜底，不将上游效果当成本项目证据。

- 来源：p029；消费 t030 的 Dialog/页面保护接口；2026-11-04，main@c6a9322 核实。Supervisor 不在所有 WebRTC 输入路径；透明 CDP 可执行任意 JS。ADR 007 不允许把真人 Viewer 重新改为排他租约，ADR 006 要求纯画面。ego handOff 依赖闭源 binding，不能直接复用。创建采用保守首版：单协作 Agent、真人优先、显式恢复、adopt 默认保留；与 p028/p032/p033 安全建议一致。

### 有意不测

- 宿主 Mac/OrbStack、目标 CloakBrowser、真实媒体/X11/指纹站点：当前 task 执行端为云端 Muse，统一由 t032 执行；不得记为 PASS。

### 测试策略

- API/Coordinator/Supervisor/Agent 真实组件集成，用已建立 CDP 通道与重连尝试验证拒绝，而非只检查 control_owner 字段。
- 输入入口测试必须触达生产适配器并验证后续命令时序；记录已在途动作边界。迁移在隔离 DB 测试，生成 schema 与前端类型同步。
- 本地 WebRTC/X11、真实双 Viewer、权限/验证码/2FA 手工交接由 t032 判定。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无（首版可强制边界已限定为暂停/撤销整个外部自动化通道）；原生输入源与系统 UI 的目标环境行为只在 t032 宣称实测。

### 风险与回退

- 风险：交接事件晚于自动化动作；失联状态被误当授权；输入源识别错误引发抢占循环。
- 回退：回退功能时保持 user/自动化禁用，先保留可恢复 DB 备份与迁移回退；不恢复过期 Agent 授权，不关闭用户页面。

### 依赖与约束

- 硬依赖 t030，需其执行结果已进入本 task 基线。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/decisions.md：人机控制权 ADR 及 ADR 006/007 关系。
- docs/blueprint/automation.md、docs/blueprint/security.md：控制 gate、代次与在途边界。
- docs/blueprint/frontend.md、docs/blueprint/testing.md：管理界面和交接矩阵。

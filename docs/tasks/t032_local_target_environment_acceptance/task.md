# Task spec

## 背景

云端 Muse 缺少宿主 Mac/OrbStack、用户局域网及目标 CloakBrowser/Stream/X11 环境。合并 p021–p024、p026、p027 历史实跑债，并集中验收 t025–t031 新交付；此前 skip/trust_prior 不是本轮证据。本 task 是最后本地执行的一轮最终验收，不倒挂成云端实施前置。

## 契约区

### 范围

- 当前源镜像冷构建/打包运行、全部历史真实环境债与云端新增探针实跑。
- 兼容性、指纹增量、XTEST 路径与原生 Dialog/权限/人机交接的目标环境证据及采用结论。
- 运行时故障、隔离、资源配额、发布/回退的隔离演练；逐项证据和最终发布判定。

### 非范围

- 不实现生产修复、不借验收修改旧测试阈值、不部署到用户现有生产栈、不清理用户 Profile/缓存/数据。
- 不把云端探针结果冒充目标结果；不新增 ego 闭源依赖或自动解决 CAPTCHA。
- 不恢复已豁免的公网 TURN/原生 Linux x86_64 测试；不要求为本 task 破坏共享 Docker daemon。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] [deploy] AC-001：运行前记录当前 commit、Mac/OrbStack/Chrome/引擎及工具版本、全部不可变镜像 ID 和缓存身份；在隔离资源前缀/卷/数据库中启动，缺少任何必需前提即明确失败，不能用旧镜像或源码 import 代替构建产物。
- [ ] [deploy] AC-002：以当前源真实隔离构建 Supervisor 与 Stream；Supervisor 镜像可 import cbrowser.launch_args，实际交付镜像/wheel 可 import cbrowser.runtime_event_log 并调用 emit_runtime_event_log；Stream 冷构建成功、最终层无构建工具链且真实媒体/输入/剪贴板运行所需库完整。
- [ ] [deploy] AC-003：真实 Mac Chrome 执行 t019 候选集和时延：仅 host、远端 127.0.0.1，无 srflx/relay/prflx，切换已运行 Profile 与刷新到首帧均不超过 2 秒；回归多页面/复制/可见性暂停恢复/断线 resume，并保存逐次耗时与候选快照。
- [ ] [deploy] AC-004：真实 Browser 镜像执行 font bundle image_layout、三档 render 与双 Profile isolation，记录 fc-list/fc-match、canvas/CDP 字体和实际渲染；同 Profile 配置在目标镜像中生效且两 Profile 不串扰。
- [ ] [deploy] AC-005：真实 Chrome 下载→Browser Agent→Supervisor→API Artifact 全链、删除意图跨真实进程重启续跑、Origin 变体 viewer 授权均按正式入口通过；保留入库、删除恢复与授权结果证据。
- [ ] [deploy] AC-006：实际容器执行 X11 helper 权限、缓存代次与双族 DROP 兜底；记录 Selkies 2.1.0 owner-loss/正常退出/keymap 初始化真实调用顺序、多 Agent 注册预算/429/恢复及 search-defaults 重试活 context 结果。
- [ ] [deploy] AC-007：当前构建产物通过 frontend app/session 与新 frontend_probe harness；会话挂载、语言切换、SSE 代次、t025 URL/注销/跨 Profile/阶段重试均无回归，构建链确实托管当前产物而非测试替身。
- [ ] [deploy] AC-008：执行 t028 全部隔离/清理/回滚、配额至实际画面和 Agent 替换场景，记录正向网络基线、内核负例、实际 CPU/帧数及 close=1001/conn_id/上下行/Viewer 存活，不互换证据层级。
- [ ] [deploy] AC-009：两个以上 Profile 运行时执行 Gateway 替换/进程退出、Supervisor 重启、网络断开、策略缺失、API 离线及协议不兼容；兼容替换不重建 Browser/Stream，不兼容仅有界替换 Stream，页面保留；固定 Gateway 端点真实可附着且不会被 Docker 自动分配占用。
- [ ] [deploy] AC-010：隔离拓扑演练 t027 连续发布、部分服务不 ready、Gateway 永不 ready 与上一 release 回退；失败非零且有界保留诊断，成功代表所有活跃 Runtime 收敛，无 Browser/用户数据清理及无条件 Caddy 重启。Docker daemon 故障仅在独立测试 daemon/VM 验证，不能未经授权重启宿主共享 daemon。
- [ ] [deploy] AC-011：经正式 cbat\_ 隧道运行 t029/t030 目标兼容与生命周期矩阵：默认 context、既有页面、popup/iframe/OOPIF、下载、导航/ref 失效、adopt/未知页面、最后 Tab、超时/取消/异常退出均符合契约；真实 Dialog 在 pending 命令与跨 CLI 调用后可恢复，beforeunload 具备真实激活。
- [ ] [deploy] AC-012：固定 seed/引擎/配置/视口并重复采样，分别比较当前 runtime、raw CDP、Playwright、Runtime/Page、snapshot/locator 与输入的指纹字段；记录 BrowserLeaks/CreepJS/Pixelscan 可达性和波动。给出新增变化、因果证据强度和候选是否可采用；不可达/样本不足只记 INCONCLUSIVE，不以总分/isTrusted=true 证明不可检测。
- [ ] [deploy] AC-013：完成 CDP/XTEST 坐标/DPR/装饰/滚动/iframe/复杂交互/焦点比较；明确是否存在足够收益采用 XTEST，无证据不增加第二驱动。真人 WebRTC 输入、权限/设备提示及主动 CAPTCHA/2FA handOff 能撤销已建 Agent 通道、拒绝重连，保留多 Viewer 和用户页，显式恢复后才允许 Agent 新动作。
- [ ] [deploy] AC-014：执行 CBROWSER_RUN_E2E=1 scripts/run_gates.sh 的 required 模式并记录各 suite、命令、退出码和脱敏 evidence；逐项对应历史债与新增 AC，未执行/跳过/失败/结论不足分别列出，禁止延用旧 trust_prior 或把 skip 算 PASS。
- [ ] [deploy] AC-015：出具最终验收报告与运行入口索引；发布要求的行为与安全检查全部有目标环境证据，未通过项保留未勾选并登记具体缺陷/所需补证，修复后重跑受影响项。若需新输入驱动或改变控制权架构，先凭证据修订方案，禁止静默回退到合成事件或放宽隔离。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001–AC-011、AC-014：有自动测试/探针，但必须本地真实镜像、Mac Chrome 和 Docker 拓扑运行，云端不能替代。
- AC-012：指纹对照可采集，外站判读与因果复核需人工；保存字段级样本、对照条件及明确可达性。
- AC-013：坐标可自动测，原生权限/设备选择器、真人输入与 CAPTCHA/2FA 主动交接需本地人工；录像/截图脱敏并配套事件时序、页面存活与通道拒绝证据。
- AC-015：人工复核证据完整性与发布判定；失败、未执行或结论不足不允许勾选对应行为为通过。

## 上下文区

### 执行环境与 ego-lite 参考

- 仅本地执行：Mac + OrbStack + 官方 Google Chrome + 真实 CloakBrowser/Stream/X11；执行人可用本机 Agent，云端 Muse 只交付上游 t025–t031。
- ego-lite：https://github.com/citrolabs/ego-lite ；研究基线：https://github.com/citrolabs/ego-lite/tree/12407167f84a58af24044f072868051952131491 。只参考公开 harness/Skill；globalThis.ego/浏览器本体闭源，不作为运行依赖。

### 历史债与执行映射

|来源|本地必须取得的证据|本 task AC|
|---|---|---|
|p021 / t019|host-only 候选、切换/刷新首帧 ≤2 秒与媒体矩阵|AC-003|
|p022 / t020|镜像字体、三档渲染、双 Profile 隔离|AC-004|
|p023 / t021|打包 import/emit、真实下载入库、删除续跑与 viewer 授权|AC-002、AC-005|
|p024 / t022|X11/keymap、缓存/策略、多 Agent 注册、search-defaults 真链|AC-006|
|p026 / t023|frontend app/session 及迁移后测试宿主构建链|AC-007|
|p027 / t024|Supervisor 准入隔离构建、Stream 冷构建与运行库完整性|AC-002|
|p016 / t028|网络保护、真实配额画面、Agent 替换断言|AC-008|
|p034 / t026、t027|固定端点、自愈、离线恢复、协议升级、发布失败/回退|AC-009、AC-010|
|p028 / t029|目标 CDP/Playwright、指纹增量及 CDP/XTEST 比较|AC-011、AC-012、AC-013|
|p030、p032、p033 / t030|执行器、Tab/ref 生命周期与 Dialog 跨调用恢复|AC-011|
|p029 / t031|真人抢占、原生权限/设备及主动 CAPTCHA/2FA 交接|AC-013|

- 来源：p021、p022、p023、p024、p026、p027 全部转入本 task；p016/p028/p029/p030/p032/p033/p034 的目标环境执行义务亦在本 task 汇总。2026-11-04 核对 main@c6a9322，各条历史真实环境证据尚未交付，原来源 t019–t024 均已 done，不重复创建实现 task。

### 有意不测

- 公网 TURN/公网 ICE 与原生 Linux x86_64：当前产品同机直连且已有明确豁免，不借本地补证扩大平台。
- 用户现有生产实例：只在独立测试拓扑验证，防止故障演练影响既有工作。

### 测试策略

- 从 docs/blueprint/testing.md、stream_runtime_validation.md、supervisor_validation.md 的现行入口启动，执行前核对镜像/缓存和真实调用路径。
- 使用 CBROWSER_RUN_E2E=1 scripts/run_gates.sh；新增专项入口由 t026–t031 提供，不凭空引用未交付脚本。必要专项独立运行并保留命令/样本，不另造巨型探针总控。
- 资源前缀、网络、卷、端口和 evidence 每轮独立；finally/trap 只清理本轮对象。秘密、页面内容和指纹隐私原始样本按最小范围留本地产物，入库报告只保留脱敏结论及 artifact 位置。
- 任一行为失败则保留现场，按 bug-to-pending 工作流登记并关联修复 task，修复后重跑；验证报告不替代修复。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 本 task 的工作正是验证尚未实跑的目标行为，不能预先声称通过。候选兼容/输入/指纹结论由 AC-011–AC-013 的实际实验给出，失败或结论不足时保留发布阻断。
- 环境前置：本地 Mac/OrbStack、官方 Google Chrome、可用引擎缓存、当前源镜像和用户提供凭证；缺失须列缺项，不能移给云端或用硬编码默认值补齐。

### 风险与回退

- 风险：故障演练误操作既有服务；镜像/源码混用；外站波动和观察扰动误判指纹；旧阈值豁免造成假绿。
- 回退：只销毁本轮可识别测试资源；保留用户数据和失败 evidence。隔离发布演练选择上一不可变 release 并重新 readiness；不自动重试不明状态发布，不回滚业务数据。

### 依赖与约束

- 硬依赖 t025、t026、t027、t028、t029、t030、t031 全部交付并进入本地验收基线；本 task 放最后，云端不得执行。
- 真实验证失败意味着产品仍待修复，不意味着云端先前已经提供真实执行证据；禁止重用历史“跳过按 pass 计”口径。
- 需要独立 Docker daemon 故障环境时先提供隔离环境；现有共享 daemon 不在破坏性演练授权内。

### Finalization 时更新的 blueprint

- docs/blueprint/testing.md：本轮真实证据、未通过项及历史实跑债闭环。
- docs/blueprint/automation.md、docs/blueprint/decisions.md：目标兼容、指纹增量与 CDP/XTEST 采用结论，只记录实测范围，不夸大为不可检测。

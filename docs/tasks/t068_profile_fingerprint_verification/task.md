# Task spec

## 背景

升级前后指纹测量、创建期 persona 一致性与用户自检共用同一份探针及身份版本。合并避免三套测量口径；现有 CDP/字体探针可复用，调研中的补丁数量、通过率与固定 seed 空间均不能视为事实。

## 契约区

### 范围

- 建立 Profile/身份版本/引擎制品绑定的基线与差异报告，覆盖 canvas/WebGL/audio、GPU/hardware/memory/screen、UA/CH、storage quota、请求头、TLS 与页面 WebRTC 出口观测。
- 引擎固定不可变版本、关闭隐式更新并核实下载完整性/签名；升级存在未经批准漂移时阻断，给出保留旧引擎、显式轮换或重新基线处置。
- persona 工厂基于有来源和版本的参考分布生成引擎支持的合理组合；seed 资源去重/耗尽显式失败，与 bundle 单身份一致性共享规则。
- 显式 opt-in 的 warm-up 和一键自检走该 Profile 网络视角；第三方访问列出目标、时间和数据边界，默认不访问公网检测站，不外送凭据。

### 非范围

- 不复活 parked p045 的 UA-CH arch 改造；现有已知不一致只记录或阻断相关 persona，不暗中覆盖架构字段。
- 不承诺第三方反爬通过率或完全不可检测，不把单站 PASS 当整体结论。
- 不采信调研所称固定五位数 seed、GPU 池或 TLS 厂商宣称；不要求不同 Profile 永不共享真实设备组合，判断依据为整体分布。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：同一 Profile 在指定旧/新引擎制品上可重复产出带时间、身份版本、探针版本和上下文的报告；变化能定位具体 API/请求层，缺少观测记不可测而非 PASS。
- [ ] AC-002：未批准的身份漂移阻断该 Profile 的直接升级，报告可执行处置；无漂移验证包含主文档、iframe、Worker、ServiceWorker 及对应请求头，API 不适用的上下文明确标注。
- [ ] AC-003：发布使用已固定且可校验的引擎制品，下载损坏或签名/完整性失败不会运行，隐式自动更新不能绕过回归门禁。
- [ ] AC-004：同一输入参考分布和生成种子可复现批量 persona；组合自洽，按确认的样本量/统计阈值检查分布；seed 碰撞重试、空间耗尽明确失败，不承诺概率意义上的绝对无聚类。
- [ ] AC-005：用户未显式启用 warm-up/公网检测时不访问第三方；启用后只走所选 Profile 出口，不出现新 localhost 暴露端口或 viewer CDP 泄漏。
- [ ] AC-006：自检分开报告跨 API 一致性、群体分布与第三方单站观测，全部关联 Profile 身份/引擎/时间；TLS/UA/CH 结论有实际握手证据，无采集条件时显示不可判定。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；涉及真实 Chrome、引擎、Docker 或网络行为的 AC 使用隔离真实环境探针，不以 mock 结果替代。界面视觉补人工核验，第三方公网检查仅显式 opt-in。

## 上下文区

- 来源：`p081`、`p085`、`p086`。2026-11-13 核实 generate_fingerprint_seed 为 random.randint(100000, 999999)，reset 幂等路径另有派生范围；不能采用 p085 的 9 万种子作为现行事实。ProfileConfig 已有 platform/font_set/seed/screen/gpu 等字段；t029 与字体 E2E 已提供部分探针，但未发现 persona/warmup/identity_bundle 实现。当前代码未显式设置引擎自动更新变量，实际 wrapper/二进制更新与签名能力待测。

### 有意不测

- 不复活 parked p045 的 UA-CH arch 改造；现有已知不一致只记录或阻断相关 persona，不暗中覆盖架构字段。：超出本 task 范围；其余已声明 AC 不豁免。

### 测试策略

- 复用本地离线指纹/字体探针，真实两引擎制品差异、漂移阻断及损坏制品测试；不通过第三方网站通过率验收。
- 固定样本输入验证 persona 可重复生成与统计检验，测 seed 碰撞/耗尽和非法组合。
- 通过本地受控测试站验证 warm-up、网络视角、上下文覆盖与凭据不外送，真实公网检测只在用户明确 opt-in 后进行。
- 项目门禁：按 docs/blueprint/testing.md 的 doctor_cmd / test_cmd / blackbox_verify 执行；本批创建仅验证文档结构，不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 引擎二进制更新、签名算法/公钥和可控制 seed/GPU/硬件字段：UNVERIFIED-SPIKE，检查当前锁定 wrapper 与实际制品；若不支持 Ed25519 不虚构保证，记录可验证完整性方案。
- 可合法使用的真实设备参考分布、persona 平台范围、统计 N/阈值与允许漂移规则：UNVERIFIED-BLOCKING，需提供有来源/版本的数据集及明确判定方案后由用户确认，不编造市场份额。
- TLS/JA3/JA4 采集能力及 Worker/ServiceWorker 中各 API 可用性：UNVERIFIED-SPIKE，在本地受控目标和实际引擎测量，不把缺指标当无漂移。

### 风险与回退

- 风险：过度随机、误判分布或外部自检会增加可关联流量；所有报告标注观测范围与数据来源。
- 回退：保留旧引擎、旧基线和可恢复 Profile 快照；关闭显式 warm-up，回退生成器版本，不覆盖已存在身份。

### 依赖与约束

- 保持本机 Docker/OrbStack 与唯一外部 Chrome 客户端边界；不复活 parked 条目。依赖建议见 progress.md；产品 BLOCKING 未确认前不可 start，SPIKE 先验证后回填。

### Finalization 时更新的 blueprint

- docs/blueprint/testing.md、docs/blueprint/security.md：探针口径、升级阻断与公网 opt-in 数据边界。
- docs/blueprint/domain.md、docs/blueprint/decisions.md：persona 参考分布、seed 与漂移处置；同步 fingerprint_platform spec。

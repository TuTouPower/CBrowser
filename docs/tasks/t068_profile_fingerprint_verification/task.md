# Task spec

## 背景

缩减为本地指纹测量与引擎升级回归门禁；Persona、预热与用户自检已由用户明确取消，t071/t072 取消归档；本 task 仅保留引擎升级工程回归门禁。当前已有 ProfileConfigVersion 可标识基线，无需等待尚不存在的 IdentityBundle。

## 契约区

### 范围

- 复用离线 CDP/字体探针，报告 Profile id、当前 config version/配置摘要、引擎制品、探针版本与采集上下文；使用现有配置版本，本 task 不增加身份模型或依赖 t066。
- 测量实际支持 API、主文档/iframe/Worker/ServiceWorker 与请求头差异；TLS/JA3/JA4 仅在本地受控采集可验证时给结论。
- 固定引擎制品并验证下载/cache_init/自动更新路径，升级遇变化、缺测或不确定结论默认阻断，禁止用未确认阈值放行。

### 非范围

- 不实现 Persona 工厂、预热爬虫或自检 UI；不修改生成 seed 范围，统一工作属 t066。
- 不复活 parked p045，不把六位普通 seed 断言套到当前五位 reset 路径，不宣称所有引擎字段可控或有 Ed25519 签名。
- 不为实验下载/升级到违反 ADR 021 的商业/并发受限版本；使用已获准制品。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] [deploy] AC-001：同 Profile/config version 在指定已获准旧/候选引擎上重复产出可定位 API/请求层的差异报告，缺测和不支持上下文明确区分，不作为无漂移。
- [ ] [deploy] AC-002：有未经批准的漂移、未测指标或不确定结果时阻断直接升级；主文档/iframe/Worker/ServiceWorker 以实际 API 适用性列完整矩阵，非确定性指标先报告重复采样分布，不用未知阈值宣称一致。
- [ ] [deploy] AC-003：发布与 cache_init 使用固定可校验引擎制品，损坏/身份不符被拒，自动更新不能绕开门禁；若无上游可验证签名则如实说明完整性机制与信任来源。
- [ ] [deploy] AC-006：TLS/UA/Client Hints 一致性结论绑定实际握手/请求证据与引擎/config/探针版本；无本地采集能力标不可判定，不引用厂商通过率。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-002：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-003：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-006：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。

## 上下文区

- 来源：2026-11-13 审阅复核：p081；原 p085/p086 曾分到 t071/t072，现按用户明确指令取消，不转回 pending。generate_fingerprint_seed 六位、幂等 reset 五位均存在，不能说现行 seed 一律六位。wrapper 锁定 0.6.4（ADR 021），cache_init 仍 ensure_binary；只读 engine-cache 不足以代替初始化更新路径核验。

### 有意不测

- 非范围中的新增产品功能不作为本 task 验收；已声明 AC 不豁免。

### 测试策略

- 本地受控站点、离线探针及两套已授权制品报告；用变化/缺测/损坏输入验证拒绝升级，真实运行比对替代源码变量检查。
- 分别记录确定性字段与跨运行噪声；不设置虚构可接受漂移。第三方公网结果不参与本 task 门禁。
- 按 docs/blueprint/testing.md 的 doctor_cmd/test_cmd/blackbox_verify 执行；本次仅改 backlog，创建校验不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 锁定 wrapper 的制品/签名/下载与 cache_init 行为：UNVERIFIED-SPIKE，检查实际包和二进制；不预设签名算法。
- 跨上下文 API 可用性、TLS 采集与重复运行噪声：UNVERIFIED-SPIKE，本地重复测量后定稿字段/归一化；默认变化或不确定即阻断，若要允许漂移须另向用户提交具体规则。

### 风险与回退

- 风险：跨模块/制品或状态变更需按上述负向测试与 spike 验证；产品 BLOCKING 未消除不得实施。
- 回退：回退本 task 的完整实现 release；涉及数据先停写者并从已验证成套备份恢复，禁止仅降级数据库或以旧兼容分支兜底。

### 依赖与约束

- 硬依赖和冲突以 progress.md 的 task.py 调度字段为准；不把文件重叠当硬依赖。plan 仅输出图上候选，不能替代 preflight；产品 BLOCKING 必须先确认，SPIKE 先验证并回填。

### Finalization 时更新的 blueprint

- docs/blueprint/testing.md、docs/blueprint/security.md：本地基线、缺测/噪声与升级封闭。
- docs/blueprint/decisions.md：引擎制品信任来源与 ADR 021 约束。

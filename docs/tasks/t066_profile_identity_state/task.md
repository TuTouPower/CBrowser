# Task spec

## 背景

围绕同一环境数据目录交付保存配置、复制、重置和备份恢复的安全闭环。合并已收缩的 t066/t070，直接复用现有配置模型与 DB backup/restore，不新增身份模型、自动回收或配额。

## 契约区

### 范围

- 任何普通配置保存均保留现有浏览器数据；不按字段触发清理。
- 既有 reset 仅在明确确认且环境真正停止后清空整个浏览器用户目录，书签、偏好、Cookie、站点存储、缓存等一并清空；保留环境配置与独立 Artifact，按现行语义重新生成 seed。
- 修复两态 clone/reset 与启动的写入互斥、失败回滚、取消清理；验证实际 OSCrypt/portable_cookies，不盲删 Local State。
- 统一普通创建与幂等 reset 的 seed 范围，保留同操作重放确定性，不修改已保存 seed。
- 备份包括 named volume DB（正确 SQLite backup）、Profile userDataDir、必要配置与凭据引用/恢复前提清单；停机并验证无实际写者后取得同一恢复点。
- 恢复在 staging 验证完整性/版本/空间，再成套切换；处理 DB+目录跨介质切换中断与恢复日志，失败保留旧完整恢复点。
- 隔离实例执行真实备份/恢复往返并修正文档；不在本 task 执行生产恢复。

### 非范围

- 不新增身份模型、独立身份轮换入口或配置变更自动清状态；reset 全清，不做书签/偏好保留白名单。
- 不做 Persona、预热、自检、配额、自动回收或无人连接超时停止；不承诺 SSD/COW 安全擦除。
- 不操作真实生产环境数据；不把两次 rename 误当 DB+目录跨介质原子事务，不盲删 Local State。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] [deploy] AC-001：同 Profile 在配置不变时重复启动使用同一实际支持的身份参数；任何普通配置保存都不清空或重建浏览器状态目录，已有 Cookie、localStorage、IndexedDB、缓存等保留，不因代理、分辨率、时区、语言或指纹参数变化自动清理；清状态只能来自用户明确确认的独立操作。
- [ ] [deploy] AC-003：两态 clone 分别无源状态或保留约定可用状态，源不受影响；若引擎确有可复制密钥根，include-state clone 使用独立根且保持 cookie 可用，失败/取消不残留目录或 DB 行，不以盲删 Local State 通过测试。
- [ ] [deploy] AC-004：明确确认 reset 后，浏览器用户目录中的书签、历史、偏好、Cookie、登录态、localStorage、IndexedDB 与缓存全部清空，按现行语义重新生成 seed；环境 ID、名称、代理等配置和独立 Artifact 保留；失败时旧目录与配置能成套恢复。
- [ ] [deploy] AC-005：启动与 clone/reset/备份恢复竞争不会并发写 userDataDir；desired/observed 即使看似 stopped，有残留 runtime_instance_id 或实际写者时拒绝状态改写；多个 viewer 或无人连接都不授权停止环境或清理数据，备份/恢复必须由显式操作触发。
- [ ] AC-008：普通创建和幂等 reset 使用同一已声明 seed 范围；相同操作 ID 重试保持相同 seed，不改变既有已保存 seed，也不保留五位/六位生成路径分裂。
- [ ] AC-009：完整备份同时包含可恢复 DB 与对应 Profile 状态/配置；恢复后 Profile 配置版本、cookie/localStorage 和登录态与该恢复点一致，不遗漏 named volume。
- [ ] AC-010：损坏、空间不足、数据库校验失败以及成套切换每个中断点都能恢复旧完整版本或完成新版本，不遗留 DB 与目录版本错配；原数据不被未校验内容覆盖。
- [ ] [deploy] AC-011：在隔离真实部署中执行备份→状态变化→恢复，验证配置、登录态和必要凭据恢复前提；指南所列命令能从 named volume 取得并恢复 DB。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001、AC-003..005、AC-011：需隔离真实 Docker/Chrome/引擎及 named volume 验收，可自动化但不以 mock 替代；[deploy] 不授权生产发布。
- AC-008..010：生产服务/工具的 seed、manifest、SQLite WAL 与切换中断自动测试；完整恢复另由 AC-011 真链证明。

## 上下文区

- 合并来源：t070（p080）。来源 AC-001→本 task AC-009；AC-002 合入 AC-005 操作互斥；AC-003→AC-010；AC-004→AC-011。原已退休的 AC-002/006/007 不复用，现有配置与 reset 语义以用户最新定稿为准。
- 来源：2026-11-13 审阅复核：p074、p089；p080 的备份恢复由 t070 合入本 task。普通创建 100000..999999，reset.\_seed_for_operation 当前 10000..99999，两条路径均真实存在。delete_profile 查 runtime_instance_id，duplicate/reset 停机条件遗漏该项；需覆盖与 set_desired_state 的交错。OSCrypt 漏洞尚未实测。

### 有意不测

- 非范围中的新增产品功能不作为本 task 验收；已声明 AC 不豁免。

### 测试策略

- 真实 Cookie/localStorage/IndexedDB/书签/偏好等数据预置后修改配置并重启，验证数据保留；显式 reset 后验证全部清空且配置/Artifact 保留。
- 生产服务测试覆盖残留 runtime_instance_id、error 态、启动与 clone/reset 交错、取消/中断与 DB 失败回滚；跨进程围栏不由进程内锁单测替代。
- 两态 clone 源不变、可用 cookie 与真实密钥边界、seed 统一与幂等重放回归。
- 按 docs/blueprint/testing.md 的 doctor_cmd/test_cmd/blackbox_verify 执行；本次只修订 backlog，不操作真实环境数据。
- SQLite WAL/在线 backup、tar 目录与 manifest 完整性测试；跨 DB/目录阶段故障注入，不仅测 rename。
- 隔离 named volume + Browser 实际写入的往返恢复测试，生产数据不用作试验。
- 按 docs/blueprint/testing.md 的 doctor_cmd/test_cmd/blackbox_verify 执行；本次仅改 backlog，创建校验不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 产品边界已确认：保存配置保留状态、reset 全清、不做新身份模型/白名单/配额/自动回收，无产品 BLOCKING。
- OSCrypt/portable_cookies 复制可用性：UNVERIFIED-SPIKE，用实际引擎一次性样本验证，不盲删 Local State。
- 现有 DB backup/restore 与 Profile 停机切换契约：UNVERIFIED-SPIKE，先演练现有工具，再定稿跨介质成套恢复及中断恢复协议。

### 风险与回退

- 风险：按上述负向测试及技术 spike 验证恢复/数据原子性；产品边界已确认，不再以已取消功能阻塞实施。
- 回退：回退本 task 的完整实现 release；涉及数据先停写者并从已验证成套备份恢复，禁止仅降级数据库或以旧兼容分支兜底。

### 依赖与约束

- 硬依赖和冲突以 progress.md 的 task.py 调度字段为准；不把文件重叠当硬依赖。plan 仅输出图上候选，不能替代 preflight；技术 SPIKE 先验证并回填，不新增产品功能。

### Finalization 时更新的 blueprint

- docs/blueprint/domain.md、docs/blueprint/testing.md：配置保留、reset 全清、clone/reset/备份恢复互斥及 seed 统一。
- docs/blueprint/architecture.md、docs/blueprint/security.md：成套恢复点、密钥与必要凭据恢复前提；同步 README/DOCKER_DEPLOYMENT 备份指南。

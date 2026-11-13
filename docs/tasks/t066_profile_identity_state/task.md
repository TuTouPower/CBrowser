# Task spec

## 背景

身份配置、状态目录、clone/reset 与备份都改变同一个持久 Profile，合并为原子身份和可恢复状态生命周期交付。现有配置版本、两态 clone、停机检查及失败清理继续复用，重点补身份版本绑定、完整备份和独立状态边界。

## 契约区

### 范围

- ProfileMeta/IdentityBundle/ProfileState 分责；身份字段构成原子版本，普通名称/备注变更不动状态，身份轮换整体生效并清 cookie/localStorage/cache。
- bundle 涵盖引擎实际支持的 seed/GPU/platform/hardware/screen/quota/locale/timezone/language/代理引用/WebRTC 策略/字体与 voices/Client Hints；秘密沿用安全存储与版本引用，禁止复制明文进普通配置快照。
- 两态 clone/reset 与身份版本绑定；复制只在源停止且持独占写锁时进行，排除运行锁/预览，验证 OSCrypt 的真实存储后独立生成或安全重加密，不直接删除 Local State 导致 cookie 不可用。
- 完整备份包含 named volume 数据库、Profile userDataDir 与必要配置；停机一致性/在线 DB backup、stage/swap/校验恢复；单 Profile 与总量的存储/时长/并发配额取更严约束。

### 非范围

- 不承诺 SSD/COW 安全擦除；不触及生产数据，执行迁移需先验证备份可恢复并取得破坏性操作授权。
- 不把多 viewer 当多个 Browser 写者，不取消现行同 Profile 多 viewer。
- 不在此实现真实市场分布 persona 工厂、自检或引擎升级测量，交 t068。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：同一 Profile 多次启动保持同一身份版本与实际支持的跨 API 指纹；身份字段不能独立产生不一致配置，名称/备注等非身份 PATCH 不清状态。
- [ ] AC-002：显式身份轮换整体更新身份与状态绑定并清 cookie/localStorage/cache；失败时旧身份与旧状态成对保留，重启不会出现新配置配旧状态。
- [ ] AC-003：exclude-state clone 无源 cookie/localStorage；include-state clone 按约定保留可用状态但不共享可用的加密密钥根，源 Profile 不变；复制失败/取消不残留半目录或 DB 行。
- [ ] AC-004：reset 生成新身份版本、清会话状态并保留 Bookmarks 与已确认允许保留的偏好；密钥/凭据及标识性内容不因无差别保留 Preferences/Web Data 跨身份继承。
- [ ] AC-005：运行中对同一 Profile 的 clone/备份/轮换/reset 与启动竞争不会并发写 userDataDir；操作结果可解释且不误拒绝多个只读 viewer。
- [ ] AC-006：完整备份恢复后数据库、身份版本、cookie/localStorage 与登录状态一致；文件损坏、空间不足或 stage/swap 中断不产生半恢复，旧完整版本仍可回退。
- [ ] AC-007：单 Profile/总量的并发、存储与时长配额按更严值执行，超限操作返回稳定原因；未明确额度前不得用任意默认值影响用户状态。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；涉及真实 Chrome、引擎、Docker 或网络行为的 AC 使用隔离真实环境探针，不以 mock 结果替代。界面视觉补人工核验，第三方公网检查仅显式 opt-in。

## 上下文区

- 来源：`p074`、`p080`、`p089`。2026-11-13 核实 ProfileConfig 与配置版本已存在，generate_fingerprint_seed 当前为六位数，不能采用调研五位数断言。profile_service.duplicate_profile 已支持 include_browser_state、停机复查、锁、目录先完成再建 DB 行、取消失败清理；reset 已备份目录并回滚，当前清全状态而非保留书签。\_copy_user_data 仅排除 Singleton 文件，尚未验证 Linux OSCrypt 根及 portable_cookies 实际行为。README 已 compose down 再 tar，问题为 named volume db 不在 tar 内，不是缺少停机。

### 有意不测

- 不承诺 SSD/COW 安全擦除；不触及生产数据，执行迁移需先验证备份可恢复并取得破坏性操作授权。：超出本 task 范围；其余已声明 AC 不豁免。

### 测试策略

- 迁移前在隔离数据副本做备份/恢复往返，再覆盖断电点、stage/swap、空间不足与 DB 失败；不使用真实生产数据做破坏性探针。
- 扩展 test_profile_copy_reset.py / test_profile_copy_reset_api.py，新增跨进程启动竞争、真实加密 cookie 复制/重加密、轮换失败原子性和配额测试。旧 clone 同种子/reset 全清契约需整体替换并记录破坏性变更理由。
- 真引擎检测 cookie/localStorage、书签、偏好及两身份间解密隔离；真实 named volume 恢复。
- 项目门禁：按 docs/blueprint/testing.md 的 doctor_cmd / test_cmd / blackbox_verify 执行；本批创建仅验证文档结构，不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- Linux CloakBrowser OSCrypt、portable_cookies 与 Local State 的真实密钥边界：UNVERIFIED-SPIKE，用一次性加密 cookie 样本验证是否存在可复制密钥根，确定保状态且密钥独立的方案；未核实前不宣称已证实跨 Profile 解密漏洞。
- 引擎对 bundle 各字段的控制与可观测支持：UNVERIFIED-SPIKE，实际二进制探针后定稿字段，不声称 seed 可控制所有 API。
- reset 偏好保留白名单、配额默认值与身份字段修改入口：UNVERIFIED-BLOCKING，按保留书签/清凭据目标提供具体字段与额度方案后由用户确认；创建期不预设产品取舍。

### 风险与回退

- 风险：破坏性模型迁移与状态重加密可能造成数据丢失；未证明备份可恢复不得迁移，未确认产品取舍不得 start。
- 回退：保留迁移前可验证恢复的整套 DB/身份/目录备份；停止写者，成套恢复到旧 release，不降级修改后的数据库，不只回滚其中一个文件。

### 依赖与约束

- 保持本机 Docker/OrbStack 与唯一外部 Chrome 客户端边界；不复活 parked 条目。依赖建议见 progress.md；产品 BLOCKING 未确认前不可 start，SPIKE 先验证后回填。

### Finalization 时更新的 blueprint

- docs/blueprint/domain.md、docs/blueprint/architecture.md：身份/元数据/状态三者绑定与单写者。
- docs/blueprint/decisions.md：身份轮换、clone/reset 破坏性语义及迁移决策。
- docs/blueprint/security.md、docs/blueprint/testing.md：密钥隔离、配额与恢复验收；同步 profile_management、fingerprint_platform、storage_and_artifacts spec。

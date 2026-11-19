# Task spec

## 背景

`0013_profile_identity.py` 迁移在检查和重写 `profile_config_versions.snapshot` 时假定 JSON 为顶层平铺结构，但仓库创建、更新与代理凭据轮换实际写入的是 `{"config": ..., "proxy_credential_revision": ...}` 包装结构。导致线上存量数据库虽已迁移至 `d7e3a91f4c62`，受影响快照内层仍残留 `gpu_family=auto` 与 `color_scheme=null`，且外层被错写冗余字段，启动或恢复旧环境时被 `ProfileConfig` 校验拒绝并返回 502。

## 契约区

### 范围

- 修复 `0013_profile_identity.py` 中 `_blocking_entries` 与 `_rewrite_snapshots`，同时正确校验与重写平铺与 `{config, proxy_credential_revision}` 包装快照，且保留原外层结构与 `proxy_credential_revision`。
- 新增幂等的补偿迁移（接在当前单一 head 之后），对已经执行过旧版 `0013` 的存量数据库执行：fail-before-write 阻断嵌套 `config` 内不可等价映射的条目、清除外层误写冗余字段、按既定身份规则转换内层 `config` 并保留 `proxy_credential_revision`。
- 补充单元与集成回归测试验证迁移、补偿迁移及通过真实 API 读取旧版本快照后进入 Supervisor 启动与恢复流程的兼容性。

### 非范围

- 不修改现行 `ProfileConfig` 严格模型校验规则（继续拒绝 `gpu_family`、空 `color_scheme` 等旧字段，不降级为运行时兼容兜底）。
- 不支持 Alembic downgrade。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：对尚未升级过 `0013` 的数据库，`upgrade` 能正确校验并重写 `{config, proxy_credential_revision}` 包装快照与平铺历史快照：嵌套内含强制 `gpu_family`（非 `auto`）或无效字体绑定或损坏 JSON 时在任何表结构修改前整体阻断；可等价转换时移除内层 `gpu_family`、将空或 `no-preference` 的 `color_scheme` 转为 `light`、按内层 `locale` 派生 `include_cjk_fonts`、按内层 `fingerprint_platform` 绑定默认字体集，保留外层结构与 `proxy_credential_revision` 且不在外层写入多余配置键。

- [ ] AC-002：对已经升级到原 head（`d7e3a91f4c62`）且快照仅外层被旧 `0013` 错改的存量数据库，新增补偿迁移以幂等方式完成修复：先执行 fail-before-write 前置校验（嵌套内含不可等价字段时阻断且不修改快照），再清除外层错写的配置字段、按规则修复内层 `config` 并保留 `proxy_credential_revision`，使补偿后的历史版本快照经由真实 API 查询接口交付并通过 `ProfileConfig` 校验，可正常用于启动与恢复。

- [ ] AC-003：Alembic 迁移链保持单一 head，补偿迁移及修复后的 `0013` 迁移满足幂等性且不触碰浏览器用户数据；已有迁移头校验及新增单元/集成测试全部通过。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 关联 spec：docs/specs/storage_and_artifacts.md
- 来源：p140（2026-11-19，已通过隔离 SQLite 复现与线上只读日志确认 502 根因）

### 有意不测

- 已在本次会话前删除的旧线上 Profile 行不可直接在现存线上库重现：通过隔离合成数据库完整覆盖全部存量行形状与失败恢复路径，并在上线时对现库执行 Alembic `upgrade head`。

### 测试策略

- 在单元层构造生产写入形状（平铺、包装、混合、已盖章错写外层、强制 GPU/坏字体/坏 JSON 阻断、保留 `proxy_credential_revision`、重复运行幂等）先红后绿验证迁移；在集成层验证经过迁移的库通过真实 API 内部快照接口及 `ProfileConfig` / 恢复读取路径成功解析旧版本配置。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。数据库快照结构与 `ProfileConfig` 校验契约已在仓库代码明确。

### 风险与回退

- 风险：既有迁移测试用例（如 `test_t054_migration.py`、`test_t075_migration.py`）若硬编码旧单一 head 修订号，新增补偿迁移后需同步更新其 head 断言或锚点说明，不得删减语义验证。
- 回退：通过部署前自动生成的数据库备份（`deploy.sh restore`）与版本回退恢复。

### 依赖与约束

- 严格遵守 `docs/blueprint/conventions.md` 与 `docs/specs/storage_and_artifacts.md` 中“迁移只向前不提供降级、fail-before-write、迁移头唯一”等约束。

### Finalization 时更新的 blueprint

- `docs/blueprint/domain.md`：如涉及版本快照结构或迁移契约描述需补充则更新。

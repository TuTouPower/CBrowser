# Task review t089（reviewer_focus: 代码）

- task：`t089_wrapped_profile_snapshot_identity_migration`
- spec：`docs/tasks/t089_wrapped_profile_snapshot_identity_migration/task.md`
- diff_anchor：`1f949747dc2d93a935aa9ed9448f0bd25b928b1d`
- target：`git diff 1f949747dc2d93a935aa9ed9448f0bd25b928b1d`
- round：1
- reviewed_at：2026-11-19T16:42:20+08:00

reviewed_scope: e872983f1ac6985b

## Findings

### t089_code_f001 - 补偿迁移 0014 对已符合新格式的存量快照仍强制校验 font_set_id，会阻断合法 d7e3a91f4c62 库的升级与启动

- 严重度：important
- 锚点：行为缺陷——对已经处于 `d7e3a91f4c62` 且包含合法 post-0013 快照（未配置字体根时的 `font_set_id=null`，或历史快照所绑字体集后续审计转为 `failed`）的数据库，执行 `0014` 补偿迁移时仍按 pre-0013 规则强制要求所有行绑定的 `font_set_id` 在 `font_set_assets` 中处于 `verified` 状态或存在平台默认集，导致 `run_database_migrations` 抛 `RuntimeError` 并阻断 API 启动
- 位置：`src/backend/migrations/versions/0014_repair_wrapped_snapshots.py:42`、`src/backend/cbrowser/adapters/database/snapshot_identity.py:87-100`
- 问题：`0014_repair_wrapped_snapshots.upgrade()` 直接调用 `find_blocking_snapshot_entries(conn, verified, defaults)` 扫描 `profile_config_versions` 全表，未区分「仍含 pre-0013 旧字段/缺 `include_cjk_fonts`/外层被旧 0013 污染的快照」与「已在 post-0013 契约下生成且无需迁移的干净快照」。这在两类合法 `d7e3a91f4c62` 数据库上直接失败：1）`api/app.py:338-344` 与 `services/profile_service.py:515-525` 明确允许未设置 `CBROWSER_FONTS_DIR` 的进程创建 `font_set_id=null` 的 Profile（`font_set_assets` 为空），该类历史库升级到 `e89a0014c001` 时会在 `snapshot_identity.py:95-100` 报错退出；2）生产库中历史快照绑定的字体集后续因完整性审计转为 `state='failed'`（`adapters/database/font_repository.py:154`，`docs/blueprint/domain.md:104` 明确要求审计失败不改动历史 Profile 数据），升级到 `e89a0014c001` 时会在 `snapshot_identity.py:89-94` 阻断迁移，导致 API 生命周期启动阶段 `run_database_migrations`（`api/app.py:276`）直接崩溃。同时 `rewrite_profile_config_snapshots` 在 `0014` 中若随后配置了默认集也会改写已符合新格式的 `font_set_id=null` 历史快照（`snapshot_identity.py:138-141`）。
- 建议：在 `snapshot_identity.py` 中增加仅面向 `0014` 补偿路径的开关（例如 `skip_clean: bool = False`），对损坏 JSON / 非对象 / 非字典 `config` / 非 `auto` 的 `gpu_family` 始终全表阻断，而仅当快照尚未收敛到 post-0013 形态（`gpu_family` 仍存在、`color_scheme` 为 `None`/`"no-preference"`、缺布尔型 `include_cjk_fonts`，或包装外层存在 `WRAPPED_SPURIOUS_OUTER_KEYS`）时才在 `0014` 中校验 `font_set_id` 目录可用性并重写；`0013` 保持 `skip_clean=False` 以继续严格拦截所有 pre-0013 存量行。

## 结论

- 本轮新发现：1 条（1 条 important，0 条 minor）
- 未进表的提示：
    - 文件行数均未超阈值：`src/backend/cbrowser/adapters/database/snapshot_identity.py`（151 行）、`src/backend/migrations/versions/0013_profile_identity.py`（161 行）、`src/backend/migrations/versions/0014_repair_wrapped_snapshots.py`（52 行）均低于 400 行；测试文件 `test_t089_wrapped_snapshot_migration.py`（500 行）、`test_t075_migration.py`（457 行）、`test_t089_wrapped_snapshot_recovery.py`（158 行）、`test_t054_migration.py`（140 行）均低于 600 行。
    - 圈复杂度：`src/backend/cbrowser/adapters/database/snapshot_identity.py` 中 `find_blocking_snapshot_entries`（McCabe CC=12）与 `rewrite_profile_config_snapshots`（McCabe CC=14）达到 ≥ 10 的提示阈值（< 15），建议随 `t089_code_f001` 修复抽取公共解包/判定辅助函数。
    - 范围外观察：`docs/specs/storage_and_artifacts.md:65-73` 存在既有重复的 `## 删除数据清理语义（t078）` 段落（非 t089 引入）。
- 总体判断：共享快照解包校验与迁移链修补主路径实现清晰、文档同步一致，但补偿迁移 `0014` 对已符合 post-0013 形态的存量快照无条件校验 `font_set_id` 目录状态存在启动阻断缺陷（`t089_code_f001`），判定 FAIL。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。已核对 `src/backend/migrations/versions/0013_profile_identity.py:72-157` 与 `src/backend/cbrowser/adapters/database/snapshot_identity.py:44-151`，`upgrade` 在任何表/行写操作前先对平铺与包装快照执行强制 `gpu_family` / 无效字体绑定 / 损坏 JSON 阻断，转换仅作用于目标配置对象并保留外层结构与 `proxy_credential_revision`，且 `test_t075_migration.py` 与 `test_t089_wrapped_snapshot_migration.py` 实跑通过。
- AC-002：TICK-VALID，re_verified。已核对 `src/backend/migrations/versions/0014_repair_wrapped_snapshots.py:28-49` 与 `src/backend/cbrowser/adapters/database/snapshot_identity.py:14-151`，接在 `d7e3a91f4c62` 后先执行前置阻断再清除 `WRAPPED_SPURIOUS_OUTER_KEYS`、按规则重写内层 `config` 并保留 `proxy_credential_revision`，通过 `ProfileRepository._to_domain_snapshot` 及 API 版本查询接口交付并通过 `ProfileConfig` 校验；`test_t089_wrapped_snapshot_migration.py` 与 `test_t089_wrapped_snapshot_recovery.py` 实跑通过。
- AC-003：TICK-VALID，re_verified。已核对迁移链单一 head `e89a0014c001`、0013/0014 全程仅操作 SQLite 且不触碰浏览器用户目录、幂等重跑无多余写入；迁移与卫生测试 51 项、关联单测 114 项及 `.repo_template/tests -m contract` 388 passed / 1 skipped 全部通过。

coverage = 3 / 3

verdict: FAIL

## Round 2 (2026-11-19T17:07:18+08:00)

reviewed_scope: 340b259402dc37a9

### Findings

无（本轮新发现 0 条）。

### 结论

- 前轮 finding 复核：
    - `t089_code_f001`：**已消除**。`src/backend/cbrowser/adapters/database/snapshot_identity.py:79-87` 新增 `_snapshot_needs_migration(data, cfg)`，仅当包装外层存在 `WRAPPED_SPURIOUS_OUTER_KEYS`、内层含 `"gpu_family"`、`color_scheme in (None, "no-preference")` 或 `include_cjk_fonts` 缺失/非 `bool` 时返回 `True`；`find_blocking_snapshot_entries`（`116-148`）与 `rewrite_profile_config_snapshots`（`151-192`）均新增 `skip_clean: bool = False`，且 `find_blocking_snapshot_entries` 在 `skip_clean` 跳过之前仍先执行 `_unpack_snapshot`（损坏 JSON/非对象/非字典 `config`）与非 `auto` `gpu_family` 阻断；`src/backend/migrations/versions/0014_repair_wrapped_snapshots.py:42-52` 对两处调用均传入 `skip_clean=True`，而 `src/backend/migrations/versions/0013_profile_identity.py:105,157` 保持 `skip_clean=False` 的全量严格校验。已核对新增回归用例 `test_compensation_0014_allows_clean_post0013_db_with_null_and_failed_font_sets` 与 `test_pre_0013_wrapped_snapshots_upgrade_directly_to_head`，确认无字体根库（`font_set_id=None`）及历史字体集后续变为 `state='failed'` 的 `d7e3a91f4c62` 库可正常升级至 `e89a0014c001` 且不被改写。
- 本轮新发现：0 条
- 未进表的提示：
    - 文件行数：`src/` 改动文件均低于 400 行（`snapshot_identity.py` 192 行、`0013_profile_identity.py` 161 行、`0014_repair_wrapped_snapshots.py` 56 行）；测试文件 `tests/unit/test_t089_wrapped_snapshot_migration.py` 扩充至 661 行（超过 600 行测试文件提示阈值，属测试文件结构观察，未见缺陷）。
    - 圈复杂度：`snapshot_identity.py` 已拆出 `_unpack_snapshot`（CC=5）、`_snapshot_needs_migration`（CC=5）与 `_check_font_set_binding`（CC=5），但 `find_blocking_snapshot_entries`（语句分支 CC=7，含布尔运算符 CC=11）与 `rewrite_profile_config_snapshots`（语句分支 CC=10，含类型收窄与布尔短路共 CC=16）仍处于 `≥ 10` 提示区间；当前逻辑清晰且未引发行为分支缺陷，仅作可读性提示。
    - 范围外观察：`docs/specs/storage_and_artifacts.md:65-73` 既有重复段落（非 t089 引入）同 Round 1。
- 总体判断：Round 1 阻断缺陷 `t089_code_f001` 已通过 `skip_clean=True` 与 `_snapshot_needs_migration` 彻底修复且未引入新缺陷，AC-001/AC-002/AC-003 全部满足，判定 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。已复核 `src/backend/migrations/versions/0013_profile_identity.py:72-157` 与 `src/backend/cbrowser/adapters/database/snapshot_identity.py:44-192`，`0013` 保持 `skip_clean=False` 在表结构修改前先对平铺与包装快照严格阻断强制 `gpu_family`/无效字体绑定/损坏对象，转换仅作用于目标配置字典并保留外层结构与 `proxy_credential_revision`；`test_t075_migration.py` 与 `test_t089_wrapped_snapshot_migration.py` 实跑通过。
- AC-002：TICK-VALID，re_verified。已复核 `src/backend/migrations/versions/0014_repair_wrapped_snapshots.py:39-52` 与 `src/backend/cbrowser/adapters/database/snapshot_identity.py:79-192`，接在 `d7e3a91f4c62` 后先阻断损坏对象与嵌套不可等价条目（同时放行已收敛的 `font_set_id=None` / 历史 `state='failed'` 快照），清除 `WRAPPED_SPURIOUS_OUTER_KEYS` 并按内层规则重写 `config` 且保留 `proxy_credential_revision`；`test_t089_wrapped_snapshot_migration.py` 与 `test_t089_wrapped_snapshot_recovery.py` 实跑通过。
- AC-003：TICK-VALID，re_verified。已核对单一 head `e89a0014c001`、0013/0014 仅读写入库且不触碰浏览器用户目录、幂等重跑无额外更新；Round 2 实跑迁移与卫生测试 53 passed、关联单测 37 passed 及 `.repo_template/tests -m contract` 388 passed / 1 skipped 全过。

coverage = 3 / 3

verdict: PASS

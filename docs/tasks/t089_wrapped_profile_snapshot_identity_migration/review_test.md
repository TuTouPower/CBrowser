# Task review t089（reviewer_focus: 测试）

- task：`t089_wrapped_profile_snapshot_identity_migration`
- spec：`docs/tasks/t089_wrapped_profile_snapshot_identity_migration/task.md`
- diff_anchor：`1f949747dc2d93a935aa9ed9448f0bd25b928b1d`
- target：`git diff 1f949747dc2d93a935aa9ed9448f0bd25b928b1d`
- round：1
- reviewed_at：2026-11-19T16:31:11+08:00

reviewed_scope: e872983f1ac6985b

## Round 1 (2026-11-19T16:31:11+08:00)

reviewed_scope: e872983f1ac6985b

### 评审范围说明

本轮审查相对 `1f949747dc2d93a935aa9ed9448f0bd25b928b1d` 的完整工作区交付（含已执行 `git add -N` 的新增交付文件，`git status --short` 无未跟踪 `??` 文件）。独立复跑：使用仓库门禁环境 `PYTHONPATH=src/backend` 串行实跑全部新增与修改测试文件及迁移基线套件（`tests/unit/test_t089_wrapped_snapshot_migration.py` 7 用例、`tests/unit/test_t054_migration.py` 3 用例、`tests/unit/test_t075_migration.py` 11 用例、`tests/unit/test_control_migration.py` 5 用例、`tests/unit/test_t056_migrations.py` 13 用例、`tests/integration/test_t089_wrapped_snapshot_recovery.py` 1 用例），共 40 passed，0 failed，0 skipped；另核对了非 E2E 门禁全量 `manifest.json`（`all_passed: true`）及 `junit/unit.xml`、`junit/integration.xml`（`t089`、`t075` 迁移用例、`t054` 迁移用例全部 PASS）。危险模式全量扫描：新增与修改的 4 个测试文件中无恒真断言、无删/反转/注释断言、无 `.skip`/`.only`/xfail、无 `# type: ignore` 等静默标记、无 mock 被测迁移或校验逻辑（`test_t089_wrapped_snapshot_recovery.py` 仅通过 `monkeypatch.setenv` 指向 `tmp_path` 字体目录，数据库/Alembic/FastAPI 应用/`ProfileConfig` 均真实执行）。

## Findings

### t089_test_f001 - 集成恢复测试止步于 API 端点，未直接驱动 Supervisor 启动/恢复客户端并校对内部端点字段值

- 严重度：minor
- 锚点：AC-002（使补偿后的历史版本快照经由真实 API 查询接口交付并通过 `ProfileConfig` 校验，可正常用于启动与恢复）
- 位置：`tests/integration/test_t089_wrapped_snapshot_recovery.py:132-158`（`test_migrated_legacy_wrapped_snapshot_serves_valid_config_over_api_and_supervisor`）
- 问题：测试真实覆盖了从 `d7e3a91f4c62` 污染快照经 `run_database_migrations`（`0014`）升级后，通过真实 `create_app` 启动的 UI 版本接口（`/api/v1/profiles/{profile_id}/versions/1`）、Supervisor 内部版本接口（`/api/v1/internal/supervisor/profiles/{profile_id}/versions/1`）、代理凭据接口（`/api/v1/internal/supervisor/proxies/{proxy_id}/credentials`）及 `ProfileConfig.model_validate` 的端到端读取与严格校验链路；但仍有两处精度缺口：① 未直接经 `httpx.ASGITransport` 调用 `RecoveryCoordinator._load_profile_config`（`src/backend/cbrowser/supervisor/recovery_coordinator.py:580-600`）、`SupervisorCore._resolve_proxy_credentials`（`src/backend/cbrowser/supervisor/core.py:2780-2834`）或 `control_server` 的 `start_profile`（`src/backend/cbrowser/supervisor/control_server.py:220-245`）读取路径；② 对 `sup_body["config"]`（第 150 行）只做了 `ProfileConfig.model_validate`，未像 UI 响应那样断言 `sup_body["config"] == body["config"]` 或核对 `include_cjk_fonts is False` / `font_set_id == win_set_id` / `sup_body["profile_id"]` / `sup_body["version"]`（因 `ProfileConfig` 存在默认值 `include_cjk_fonts=True` 与 `font_set_id=None`，单靠模型校验无法感知内部接口这两项字段偏差，尽管生产实现中两侧共享同一 `get_config_version` 服务）。
- 建议：在 `test_migrated_legacy_wrapped_snapshot_serves_valid_config_over_api_and_supervisor` 中补充 `assert sup_body["config"] == body["config"]` 与 `profile_id` / `version` 断言，并可选通过 `httpx.ASGITransport` 直接驱动 `RecoveryCoordinator._load_profile_config`（及 `SupervisorCore._resolve_proxy_credentials`）验证启动与恢复消费路径。

### t089_test_f002 - 迁移单测对阻断整表校验、跨代链幂等及 `0014` 磁盘用户目录未触碰的边界覆盖可加强

- 严重度：minor
- 锚点：AC-001（在任何表结构修改前整体阻断）、AC-003（补偿迁移及修复后的 `0013` 迁移满足幂等性且不触碰浏览器用户数据）
- 位置：`tests/unit/test_t089_wrapped_snapshot_migration.py:180-186`、`tests/unit/test_t089_wrapped_snapshot_migration.py:296-305`、`tests/unit/test_t089_wrapped_snapshot_migration.py:400-450`、`tests/unit/test_t089_wrapped_snapshot_migration.py:491-499`
- 问题：① `test_0013_blocks_nested_wrapped_unmappable_or_corrupt_before_write`（第 296–305 行）验证了 `alembic_version == REVISION_0013_PREDECESSOR` 且 `v-wrap-en` 快照未被改写，但未显式检查 `profiles` 表列结构（如 `gpu_family` 仍在、`include_cjk_fonts` 未建，该表结构检查在 `tests/unit/test_t075_migration.py:248-249` 中已有类似实现）；② `test_compensation_0014_blocks_unmappable_nested_entry_before_writes`（第 491–499 行）仅校验 `v-polluted-en` 与 `v-polluted-mac` 未被改写，未校验 `after == before` 全表一致（包含带外层污染字段的 `v-bad-nested` 自身与 `v-clean-v2`）；③ `test_compensation_0014_repairs_polluted_snapshots_idempotently`（第 400–404、440–449 行）仅检查 `profiles.user_data_dir` 字符串列未变，未像 `tests/unit/test_t075_migration.py:293-325` 为 `0013` 那样在磁盘 `tmp_path` 建立真实用户目录哨兵文件验证 `0014` 不触碰用户数据；且第二次 `run_database_migrations(db)` 在已盖章 `e89a0014c001` 时属于 Alembic 跳过无操作（`0014` 对已干净快照的幂等由同批内的 `v-clean-v2` 覆盖，`0013 -> 0015 -> 0014` 连贯路径由 `tests/unit/test_t075_migration.py::test_upgrade_is_idempotent` 的平铺快照覆盖，但 `test_t089` 未对含包装快照的 pre-0013 库跑一次直达 `head` 的全链升级）。
- 建议：在 `0013` 阻断用例补充 `profiles` 列结构断言；在 `0014` 阻断用例改为 `assert after == before`；为 `0014` 用例构造真实磁盘哨兵文件并补充一条含包装快照的 pre-0013 库直升 `head` 的测试用例。

## 结论

- 改测方向复核：无「迁就实现」的改测。仅两处既有测试按规格上下文区「风险与回退」预期更新了唯一迁移头修订号，语义未削弱且有完整链校验支撑：① `tests/unit/test_t054_migration.py:67-71` 将 `test_head_is_0015_and_single` 更新为 `test_head_is_0016_and_single`，断言唯一 head 精确等于 `REVISION_0016`（`e89a0014c001`）；② `tests/unit/test_t075_migration.py:150-161` 将 `test_0013_connects_predecessor_to_single_head` 更新为 `test_0013_precedes_single_head_in_chain`，继续断言唯一 head（`len(heads) == 1`）、`REVISION_0013` 在主链内且 head 已推进到后续修订（精确 head 值仍由 `test_t054_migration.py` 与 `test_control_migration.py::test_revision_chain_matches_shipped_migration_files` 钉死）。
- 本轮新发现：2 条（critical 0 条，important 0 条，minor 2 条）
- 未进表的提示：无（`0014` 对嵌套坏字体/坏 JSON 阻断共用 `find_blocking_snapshot_entries`，已由 `test_0013_blocks_nested_wrapped_unmappable_or_corrupt_before_write` 四参数覆盖；`0014` 不可降级契约已由 `tests/unit/test_t056_migrations.py::test_every_revision_downgrade_raises` 实跑覆盖）。
- 总体判断：AC-001 至 AC-003 均具备真实可信、直达生产 SQLite/Alembic/FastAPI/`ProfileConfig` 的单元与集成测试支撑，40 项相关迁移与恢复测试独立复跑全部通过且无危险模式；2 条 finding 均为覆盖精度与边界断言增强建议（minor），无阻断项。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`tests/unit/test_t089_wrapped_snapshot_migration.py` 中 `test_0013_upgrades_wrapped_and_flat_snapshots_without_outer_pollution` 与 4 组参数化 `test_0013_blocks_nested_wrapped_unmappable_or_corrupt_before_write` 独立实跑通过，真实执行 Alembic `0013` 校验与重写包装/平铺快照，验证了嵌套强制 `gpu_family`、未认证 `font_set_id`、损坏 `config`/JSON 在写入前阻断及内外层精确字段变换与 `proxy_credential_revision` 保留（阻断后表列结构显式断言补充见 `t089_test_f002`）。
- AC-002：TICK-VALID，re_verified。`tests/unit/test_t089_wrapped_snapshot_migration.py`（`test_compensation_0014_repairs_polluted_snapshots_idempotently` 与 `test_compensation_0014_blocks_unmappable_nested_entry_before_writes`）及 `tests/integration/test_t089_wrapped_snapshot_recovery.py` 独立实跑通过，验证了从 `d7e3a91f4c62` 经 `run_database_migrations` 完成 fail-before-write 阻断与外层去污/内层修复、`proxy_credential_revision` 保留，以及通过真实 FastAPI 版本接口与内部 Supervisor 接口交付并经 `ProfileConfig.model_validate` 严格校验（直接驱动 Supervisor 恢复客户端与内部响应字段等值对比补充见 `t089_test_f001`）。
- AC-003：TICK-VALID，re_verified。`test_t054_migration.py::test_head_is_0016_and_single`、`test_t075_migration.py::test_0013_precedes_single_head_in_chain`、`test_control_migration.py::test_revision_chain_matches_shipped_migration_files`、`test_t075_migration.py`（含 `test_upgrade_is_idempotent` 与 `test_backup_restore_drill`）、`test_t056_migrations.py::test_every_revision_downgrade_raises` 及 `t089` 单元/集成测试共 40 项独立实跑全部通过；单一 head、幂等性与不触碰用户数据均有真实证据（`0014` 磁盘用户目录哨兵与包装快照直达 `head` 补充见 `t089_test_f002`）。

coverage = 3/3

verdict: PASS

## Round 2 (2026-11-19T17:07:10+08:00)

reviewed_scope: 340b259402dc37a9

### 评审范围说明

本轮审查相对第 1 轮（指纹 `e872983f1ac6985b`）的增量修改：`src/backend/cbrowser/adapters/database/snapshot_identity.py` 与 `src/backend/migrations/versions/0014_repair_wrapped_snapshots.py` 引入 `skip_clean` 分支修复 `t089_code_f001`，`tests/integration/test_t089_wrapped_snapshot_recovery.py` 与 `tests/unit/test_t089_wrapped_snapshot_migration.py` 补全 `t089_test_f001`、`t089_test_f002` 与 `t089_code_f001` 配套回归。独立复跑：使用仓库门禁环境 `PYTHONPATH=src/backend` 串行实跑 `tests/unit/test_t089_wrapped_snapshot_migration.py`（9 用例）、`tests/integration/test_t089_wrapped_snapshot_recovery.py`（1 用例）、`tests/unit/test_t054_migration.py`（3 用例）、`tests/unit/test_t075_migration.py`（11 用例）、`tests/unit/test_control_migration.py`（5 用例）及 `tests/unit/test_t056_migrations.py`（13 用例），共 42 passed，0 failed，0 skipped。危险模式扫描（第 2 轮增量）：无恒真断言、无删/反转/注释断言、无 `.skip`/`.only`/xfail、无 `# type: ignore` 等静默标记；`tests/integration/test_t089_wrapped_snapshot_recovery.py:183` 仅向与本测试路径无关的 `DockerAdapter` 传入哨兵 `docker_client=object()`，API 查询、鉴权、`RecoveryCoordinator._load_profile_config`、`SupervisorCore._resolve_proxy_credentials` 与 `ProfileConfig` 均通过真实 ASGI/FastAPI 应用与真实 SQLite 迁移库执行。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核（逐条以代码/测试原文与独立复跑核实，不采信处置表自述）：
    - `t089_test_f001`（minor）：已消除。`tests/integration/test_t089_wrapped_snapshot_recovery.py:157-209` 补充了 `sup_body["profile_id"] == profile_id`、`sup_body["version"] == 1` 与 `sup_body["config"] == body["config"]` 断言，并在 `_verify_supervisor_consumers` 中通过 `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))` 构造真实 `SupervisorCore` 与 `RecoveryCoordinator(core)`，直接执行 `await coordinator._load_profile_config(profile_id, 1)`（精确断言 `loaded_cfg == ProfileConfig.model_validate(body["config"])`、`loaded_cfg.include_cjk_fonts is False`、`loaded_cfg.font_set_id == win_set_id`）及 `await core._resolve_proxy_credentials(profile_id, loaded_cfg, 1)`（断言 `proxy_credential_revision == 4` 与 `credential_revision == 4`）；第 2 轮独立复跑通过。
    - `t089_test_f002`（minor）：已消除。`tests/unit/test_t089_wrapped_snapshot_migration.py` 四处增强均已落地并独立复跑通过：① `test_0013_blocks_nested_wrapped_unmappable_or_corrupt_before_write`（第 300–305 行）显式检查 `PRAGMA table_info(profiles)` 仍保留 `gpu_family` 且未建 `include_cjk_fonts`；② `test_compensation_0014_repairs_polluted_snapshots_idempotently`（第 397–434 行）在 `tmp_path/user_data` 下写入真实 `Preferences` 哨兵文件并绑定到 `profiles.user_data_dir`，验证 `0014` 前后列值与磁盘字节均未触碰；③ `test_compensation_0014_blocks_unmappable_nested_entry_before_writes`（第 511–527 行）在插入 `v-bad-nested` 后抓取全表 `before` 并在失败后断言 `after == before`；④ 新增 `test_pre_0013_wrapped_snapshots_upgrade_directly_to_head`（第 620–661 行），覆盖含包装与平铺快照的 pre-0013 库直接运行 `run_database_migrations` 跨越 `0013 -> 0015 -> 0014` 至 `head` 并重复执行幂等。
- 改测方向复核：无「迁就实现」的改测。第 2 轮在原有测试中仅新增精确断言（表列结构、磁盘哨兵字节、全表 `after == before`、Supervisor 内部接口字段等值与客户端消费校验），未削弱任何既有断言；新增 `test_compensation_0014_allows_clean_post0013_db_with_null_and_failed_font_sets`（`tests/unit/test_t089_wrapped_snapshot_migration.py:532-617`）真实构造 `d7e3a91f4c62` 上无可用已验证字体集且含 `font_set_id=None` 与历史 `state="failed"` 绑定集合的干净 post-0013 快照，验证 `run_database_migrations(db)` 升级至 `e89a0014c001` 且 `after == before`。
- 本轮新发现：0 条
- 未进表的提示：在 `test_compensation_0014_allows_clean_post0013_db_with_null_and_failed_font_sets` 场景中，当前 `font_set_assets` 仅含 `failed` 行；若库内同时存在新的已验证 `windows` 字体集，经核 `rewrite_profile_config_snapshots(..., skip_clean=True)`（`src/backend/cbrowser/adapters/database/snapshot_identity.py:166-167`）同样会跳过干净的 `font_set_id=None` 历史快照而不覆盖为默认集（属于低优先可选用例，不立案）。
- 总体判断：第 1 轮两项 minor finding 均已实质修复，新增 `0014` 跳过干净 post-0013 快照与直达 `head` 回归测试均已独立实跑通过，AC-001 至 AC-003 证据链完整可信，无阻断项。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。第 2 轮独立复跑 `tests/unit/test_t089_wrapped_snapshot_migration.py`（含 `test_0013_upgrades_wrapped_and_flat_snapshots_without_outer_pollution`、4 组参数化 `test_0013_blocks_nested_wrapped_unmappable_or_corrupt_before_write` 含 `profiles` 表列未改断言，以及 `test_pre_0013_wrapped_snapshots_upgrade_directly_to_head`）全部通过，真实执行 Alembic `0013` 校验与转换包装/平铺快照。
- AC-002：TICK-VALID，re_verified。第 2 轮独立复跑 `tests/unit/test_t089_wrapped_snapshot_migration.py`（`test_compensation_0014_repairs_polluted_snapshots_idempotently`、`test_compensation_0014_blocks_unmappable_nested_entry_before_writes` 全表 `after == before` 断言、`test_compensation_0014_allows_clean_post0013_db_with_null_and_failed_font_sets`）与 `tests/integration/test_t089_wrapped_snapshot_recovery.py` 全部通过，真实验证 `0014` 补偿迁移、API 查询交付、`ProfileConfig.model_validate` 及 `RecoveryCoordinator._load_profile_config` / `SupervisorCore._resolve_proxy_credentials` 消费路径。
- AC-003：TICK-VALID，re_verified。第 2 轮独立复跑 `test_t054_migration.py`（3 项含 `test_head_is_0016_and_single`）、`test_t075_migration.py`（11 项含 `test_0013_precedes_single_head_in_chain` 与 `test_upgrade_is_idempotent`）、`test_control_migration.py`（5 项含 `test_revision_chain_matches_shipped_migration_files`）、`test_t056_migrations.py`（13 项含 `test_every_revision_downgrade_raises`）与 `t089` 单元/集成测试共 42 项全过，且 `0014` 磁盘用户目录哨兵字节及 `pre-0013 -> head` 幂等重跑均实跑验证。

coverage = 3/3

verdict: PASS

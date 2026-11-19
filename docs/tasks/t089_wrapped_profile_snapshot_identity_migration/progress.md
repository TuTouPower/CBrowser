---
tid: "t089"
slug: "wrapped_profile_snapshot_identity_migration"
title: "修复身份迁移对嵌套配置快照的校验、重写与已升级库补偿"
status: "done"
branch: "t089_wrapped_profile_snapshot_identity_migration"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "1f949747dc2d93a935aa9ed9448f0bd25b928b1d"
spec_source_sha: "1f949747dc2d93a935aa9ed9448f0bd25b928b1d"
depends_on: ""
conflicts_with: ""
note: "来源 p140，0013 迁移未解开 {config, proxy_credential_revision} 包装快照"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 新增共享模块 `src/backend/cbrowser/adapters/database/snapshot_identity.py` 统一封装 `font_set_assets` verified 目录加载、fail-before-write 快照校验与平铺/`{config, proxy_credential_revision}` 包装快照重写逻辑。
- 重构 `src/backend/migrations/versions/0013_profile_identity.py` 委托共享辅助校验和改写内层 `config`（保持外层仅保留有效包装字段与 `proxy_credential_revision`）；新增前向幂等补偿迁移 `src/backend/migrations/versions/0014_repair_wrapped_snapshots.py`（`e89a0014c001`，接续 `d7e3a91f4c62`）先全量阻断检验、再清除旧 `0013` 外层误写冗余字段并修复内层 `config`。
- 新增单元套件 `tests/unit/test_t089_wrapped_snapshot_migration.py` 与集成回归套件 `tests/integration/test_t089_wrapped_snapshot_recovery.py`，并按 TDD 替换规范将 `tests/unit/test_t054_migration.py::test_head_is_0015_and_single` 替换为 `test_head_is_0016_and_single`、`tests/unit/test_t075_migration.py::test_0013_connects_predecessor_to_single_head` 替换为 `test_0013_precedes_single_head_in_chain`（先观察 RED，实现后 22 passed）。
- 按 Round 1 Code/Test Review 修复：`0014` 跳过已收敛的 post-0013 干净快照（保留对损坏 JSON/非对象/`gpu_family` 的阻断并拆分 `_unpack_snapshot` / `_snapshot_needs_migration` / `_check_font_set_binding` 降低圈复杂度），补齐 `font_set_id=None` / `state='failed'`、`profiles` 表列结构、阻断全表不变、磁盘用户目录哨兵文件、pre-0013 直升 `head`，以及 `ASGITransport` 直驱 `RecoveryCoordinator._load_profile_config` 与 `SupervisorCore._resolve_proxy_credentials`（共 42 passed）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-19T16:42:20+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t089_code_f001|important|已修|0014 仅对仍含旧字段或外层污染键的未收敛快照执行字体集校验与重写，放行干净 post-0013 的 font_set_id=null 与 failed 字体集历史库，并拆分辅助函数降低圈复杂度|`snapshot_identity.py`:45-167, `0014_repair_wrapped_snapshots.py`:42-52|
|t089_test_f001|minor|已修|补齐 sup_body 与 UI 响应等值断言，并以 httpx.ASGITransport 直驱 RecoveryCoordinator.\_load_profile_config 与 SupervisorCore.\_resolve_proxy_credentials|`tests/integration/test_t089_wrapped_snapshot_recovery.py`:154-205|
|t089_test_f002|minor|已修|补充 0013 阻断后 profiles 表列结构断言、0014 阻断全表不变断言、真实磁盘用户目录哨兵文件检查及 pre-0013 直升 head 幂等回归|`tests/unit/test_t089_wrapped_snapshot_migration.py`:300-661|

### Round 2

Round 2 Code/Test Review 均零 finding，前轮 `t089_code_f001`、`t089_test_f001` 与 `t089_test_f002` 全部已修消除，全部 3 条 AC 独立复验 PASS。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：Round 1 修复后重跑全量非 E2E 门禁 `CBROWSER_RUN_E2E=0 CBROWSER_GATE_WORKERS=2 ./scripts/run_gates.sh` 全部退出 0（`protocol_drift_check`、`requirements_check`、`contract` 389、`unit` 2483、`integration` 229、`design_lint`、`design_check`、`frontend_test` 718、`frontend_build` 全绿；定向 `test_t089_wrapped_snapshot_migration.py`、`test_t089_wrapped_snapshot_recovery.py`、`test_t075_migration.py`、`test_t054_migration.py`、`test_control_migration.py`、`test_t056_migrations.py` 共 42 passed）
- 黑盒：真实 API + Alembic `upgrade head` 路由返回（`/api/v1/profiles/{id}/versions/1`、`/api/v1/internal/supervisor/profiles/{id}/versions/1`、`/api/v1/internal/supervisor/proxies/{proxy_id}/credentials`）与真实 `RecoveryCoordinator._load_profile_config` / `SupervisorCore._resolve_proxy_credentials` 消费经 `ProfileConfig.model_validate` 通过；线上存量库升级将在集成后通过 `deploy.sh` 执行
- review：Round 2 Code PASS + Test PASS（3/3 AC `TICK-VALID`，零 finding）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 修复 `0013` 迁移未解开 `{config, proxy_credential_revision}` 包装快照的根因，并追加幂等前向补偿迁移 `0014`（`e89a0014c001`）清理已升级库的外层错写字段与内层遗留字段。

### 长期文档闭环

- 已在 [storage_and_artifacts.md](../../specs/storage_and_artifacts.md) front matter `tasks` 注册 `t089` 并补充契约章节，同步更新 [domain.md](../../blueprint/domain.md)。

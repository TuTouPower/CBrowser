# Task review t050（reviewer_focus: 代码）

- task：`t050_sandbox_compose_grouping`
- spec：`docs/tasks/t050_sandbox_compose_grouping/task.md`
- diff_anchor：`4aae2d122a2c91d4c5f934caeceada87e6326f26`
- target：`git -C '/Users/karson/kar/code/CBrowser_t050' diff 4aae2d122a2c91d4c5f934caeceada87e6326f26`
- round：4
- reviewed_at：2026-11-10T18:01:01+08:00
    reviewed_scope: 9c4cae2a9465a9d9

## Findings

无新增 finding。

## 结论

- 前轮 finding 复核（以 `git diff 4aae...` 与代码为准，不采信处置表）：
    - t050_code_f012（get_runtime 静默伪造编号）已消除：`get_runtime`（`repository.py:606-616`）先取 `ProfileModel`，行缺失或 `display_number IS NULL` 时抛 `RuntimeError`，不再回退 1；`_to_domain_runtime`（`repository.py:983-989`）的 `display_number` 改为 keyword-only、无默认值，全仓 5 处调用均显式传编号，未来新增调用点无法再静默拿到 1。
    - t050_code_f013（`_reconcile_instance_observation` 圈复杂度 ≥15）仍存在，但本轮 diff 未再给该函数加分支（f012 改动仅在 `repository.py`），且已按 Round 3 处置登记 `docs/pending/todo/p058_supervisor_observation_label_helper.md`（`p058` 只为可读性与后续修改成本，无功能缺陷）。同意遗留，不阻断。
- 新改动回归核查：
    - repository runtime 编号：`bind_runtime_instance` 幂等重绑（`repository.py:659`）、`mark_observed`（`repository.py:835`）、`set_desired_state` replay（`repository.py:860`）统一走 `_runtime_with_number`；该方法在 `write_transaction` 内 `session.get(ProfileModel)` 只触发既有预期的 autoflush，未改变原提交/回滚时序；`get_runtime` 与 `_runtime_with_number` 的失败语义一致。无回归。
    - 观察 instance 标签过滤：`core.py:1793-1820` 改为 `containers.list(all=True, filters={label: prefix/profile-id/instance-id/role=browser})`，过滤后仍保留 `instance-id` 显式复核；无匹配 → `container_status="not_found"`，与原 `NotFound` 语义一致；不再按容器名拼接，符合 AC-006。无回归。
    - deploy 放行键（`scripts/deploy.sh:387`）、cleanup 从 `com.cbrowser.profile-number` 反推期望名（`docker_adapter.py:1696-1716`）、前端 `#NNNN`（`EnvironmentTable.tsx:217`、`EnvironmentCard.tsx:63`、`ProfileDetailPage.tsx:98-103`）与 Round 3 一致，无回归。
- 本轮新发现：0 条。
- 未进表的提示：
    - 文件过大（本 task 净增，未直接导致可观测缺陷）：`src/backend/cbrowser/supervisor/core.py` 3416 行、`src/backend/cbrowser/supervisor/docker_adapter.py` 2165 行、`src/backend/cbrowser/adapters/database/repository.py` 1855 行、`src/backend/cbrowser/api/runtime_coordinator.py` 1295 行、`scripts/deploy.sh` 650 行。
    - 潜在兜底：`domain/models.py:204/224` 的 `Profile.display_number` / `ProfileRuntime.display_number` 仍带默认值 1；当前生产唯一构造点是 repository 且始终显式传值，无可复现失败，故不进 finding；若后续新增构造点需一并移除默认值。
    - 测试层观察（交 test reviewer）：`tests/fixtures/docker_doubles.py:43` 及 `test_supervisor_normal_exit_observation.py`/`test_normal_exit_replay.py` 的 `_FakeContainers.list` 忽略 `filters`，观察路径的标签过滤在这些夹具中未被真实建模。
    - 除 f013 外无新增超阈值函数。
- 总体判断：无未解决 critical / important，f012 修复有效，新改动未引入回归，实现层与 AC 对齐。
- 系统性 follow-up：`p058`（Supervisor 实例观察标签定位 helper 抽取）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。迁移 0005 以 `ROW_NUMBER() OVER (ORDER BY created_at, id)` 回填并把 sequence 置为 `MAX(display_number)`；`create_profile` 以 `UPDATE ... RETURNING` 原子分配，`delete_profile` 不触碰 sequence；`test_display_numbers_are_not_reused_after_delete` 断言 1、2 → 删 2 → 新建得 3 且首条仍为 1。
- AC-002：TICK-VALID，re_verified。`ProfileResponse.display_number: int`、`ProfileRuntimeResponse.display_number: int`、`StartProfileRequest.profile_number: Field(ge=1)`；`runtime_coordinator.py:941` 注入 `profile.display_number`；`cbrowser_v1.json` / `cbrowser_internal.json` / `supervisor_protocol.json` 三份 schema 同步 required。
- AC-003：TICK-VALID，re_verified。`container_spec.browser_labels/stream_labels` 写入 `com.cbrowser.profile-number=<:04d>`、`com.docker.compose.project=<prefix>-profiles`、`service=browser|stream`；容器名由 `remember_profile_number` 派生（`docker_adapter.py:658-670`），启动与扫描同源。
- AC-004：TICK-VALID，re_verified。diff 未改 `compose.yaml`；api/gateway/supervisor/caddy 的 `<prefix>` 项目归属与既有标签不变。
- AC-005：TICK-VALID，re_verified。`scripts/deploy.sh:387` 以 `"$PREFIX-profiles"` 且 `role in browser|stream` 放行，其余异项目仍 `exit 1`；`test_t027_release_controller.py` 覆盖放行与拒绝负例。
- AC-006：TICK-VALID，re_verified。`cleanup_container_by_name` 由标签编号反推 `<prefix>-<NNNN>-<role>` 后比对删除；`get_profile_containers`/停止/替换使用编号名；实例观察按 prefix/profile-id/instance-id/role 标签查询（`core.py:1793-1820`），不再依赖 UUID 容器名。
- AC-007：TICK-VALID，trust_prior。依赖实施侧真实 `scripts/deploy.sh deploy` readiness 与停止→启动证据（progress.md），本会话无真实 Docker 环境复跑。
- AC-008：TICK-VALID，trust_prior。Docker Desktop 分组无法脚本复验，依赖实施侧 `docker inspect`/界面证据；前端列表 `#NNNN` 渲染已由代码与组件测试复核。

coverage = 6 / 8

verdict: PASS

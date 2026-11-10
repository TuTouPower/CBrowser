# Task review t050（reviewer_focus: 测试）

- task：`t050_sandbox_compose_grouping`
- spec：`docs/tasks/t050_sandbox_compose_grouping/task.md`
- diff_anchor：`4aae2d122a2c91d4c5f934caeceada87e6326f26`
- target：`git -C '/Users/karson/kar/code/CBrowser_t050' diff 4aae2d122a2c91d4c5f934caeceada87e6326f26`
- round：4
- reviewed_at：2026-11-10T18:01:52+08:00

reviewed_scope: 9c4cae2a9465a9d9

本轮为 Round 4 最终复核（覆盖写入）。落点校验：`git rev-parse --show-toplevel` → `/Users/karson/kar/code/CBrowser_t050`，通过。指纹由 `repo_task.monitoring.review_scope_fingerprint` 对当前 worktree 重算为 `9c4cae2a9465a9d9`，与 prompt 注入值一致。

独立复验（均在 `/Users/karson/kar/code/CBrowser_t050`，未运行重型全量/真实部署）：

- `git status --short`：交付文件均在 diff 内（`0005_profile_display_number.py` 为 `A`，`test_t050_sandbox_grouping.py` 为 `AM` 且已进入 diff）；仅余 `review_code.md` / `review_test.md` / `docs/pending/todo/p058_*.md` 为流程类文件，均不属于交付内容。
- 后端定向实跑（`.venv/bin/python -m pytest -p no:cacheprovider`）：
    - `test_t050_sandbox_grouping.py` + `test_control_migration.py::test_0005_backfills_display_numbers_in_creation_order` + `test_domain_and_repository.py::test_display_numbers_are_not_reused_after_delete` + `test_api_runtime_coordinator.py::test_coordinator_start_rpc_success` + `test_t027_release_controller.py`（prefix_conflict 等）→ **20 passed, 25 deselected**。
    - `test_docker_doubles_contract.py`、`test_supervisor_docker_boundaries.py`、`test_refactor_behavior_equivalence.py`、`test_api_models_and_sse.py`、`test_a8_terminal_observation.py` → **35 passed**。
- 前端定向实跑：`npx vitest run EnvironmentListPage.test.tsx ProfileDetailPage.test.tsx` → **2 files / 31 tests passed**。
- 只读现场 `docker ps -a`：`cbrowser-0001-stream|browser` 属 `cbrowser-profiles`、`profile-number=0001`、`config-version=1`、Up；`cbrowser-supervisor|api|gateway|caddy` 仍属 `cbrowser`。
- 迁移回填 SQL 与唯一索引由 `test_control_migration.py` 真实跑 0004→head 验证；未发现需 reviewer 复跑重型 E2E 的缺口。

## Findings

### t050_test_f018 - ProfileResponse 直接断言与「正整数」约束仍只部分落实（残余 minor）

- 严重度：minor
- 锚点：AC-002（Profile 响应 / 内部 runtime 响应携带编号，且为正整数）
- 位置：`tests/unit/test_t050_sandbox_grouping.py:67-86`
- 问题：用例名含 ProfileResponse，但 `ProfileResponse` 仍只 import 未使用（`:68`），未构造 `ProfileResponse.from_domain(...)` 断言 `display_number`；`assert runtime.display_number > 0`（`:84`）使用的值由用例自身传入 4，属弱断言，不能证明模型拒绝 0/负值；`ProfileResponse` / `ProfileRuntimeResponse` 的 `display_number` 仍是裸 `int`（`src/backend/cbrowser/domain/models.py:479,695`），无 `ge=1`。AC-002 的「正整数」实质约束来自 `StartProfileRequest.profile_number: Field(ge=1)`（`supervisor/protocol.py:20`）与 DB `max+1` 分配，因此本项非唯一证据，残余为测试质量问题，不阻断。
- 建议：用 `ProfileResponse.from_domain(profile)` 断言 `display_number`；补 `display_number=0/-1` 拒绝用例，或将两个响应模型改为 `Field(ge=1)` 并断言。

### t050_test_f019 - 两条放行用例仍只断言 returncode（残余 minor）

- 严重度：minor
- 锚点：AC-005（自有 `<PROJECT>-profiles` 放行后部署应继续）
- 位置：`tests/unit/test_t027_release_controller.py:950-961`、`:995-1006`
- 问题：本轮仅 `test_prefix_conflict_allows_sandbox_group_when_project_differs`（`:992`）补了 `assert _builds(repo)`；`test_prefix_conflict_allows_own_sandbox_group` 与 `test_prefix_conflict_check_requests_role_label` 仍只有 `result.returncode == 0`。若放行分支未来在 `exit 0` 处提前结束（未进入构建），这两条仍会绿。拒绝侧均有 `_builds(repo) == []`，形成不对称。
- 建议：两条放行用例各补 `assert _builds(repo)`。

## 结论

- 前轮 finding 复核（Round 4，以 diff / 代码 / 定向实跑为准）：
    - `f017`（important，AC-003 重启不变量用替身自证）：**已消除**。`test_scan_keeps_number_and_name_across_restarts`（`test_t050_sandbox_grouping.py:194-239`）改为构造两个独立 `DockerAdapter`，各自 `scan_active_containers()` 从容器标签恢复编号；容器名 `legacy-name` 与格式化名不同，断言两者 `get_browser_container_name == cbrowser-0005-browser`、`get_stream_container_name == cbrowser-0005-stream`。触达生产 scan/命名路径，非替身自证；实跑通过。
    - `f018`（minor，ProfileResponse/正整数）：**修不彻底，残余 minor**（见 f018）。
    - `f019`（minor，放行未证明 build 继续）：**修不彻底，残余 minor**（见 f019）。
    - `f020`（minor，详情页编号）：**已消除**。`ProfileDetailPage.test.tsx:201-205` 断言 `profile-detail-number` 为 `#0001`（仅在 running 分支，`ProfileDetailPage.tsx:98-105` 实际与状态无关，属可选扩展）。
    - `f021`（minor，scan 正例无法区分标签/名字来源）：**已消除**。正例容器名改为 `legacy-container-name`，标签 `profile-number=0003`，断言恢复名为 `cbrowser-0003-browser`，名字解析回归会变红。
    - `f022`（minor，替身 fail-closed 无负例）：**已消除**。`test_fake_adapter_fails_closed_without_number`（`:241-245`）断言未 remember 时 `RuntimeError`。
    - `f023`（minor，Coordinator 断言默认 1）：**已消除**。先建 warmup 再建目标 Profile，断言 `p.display_number == 2`（`test_api_runtime_coordinator.py:120-122`），payload `profile_number == p.display_number`（`:157-159`）。
- 改测方向复核：无「迁就实现」的改测。既有改动是新必填字段/新签名（`display_number`、`profile_number`、`remember_profile_number`）与标签语义的适配；`test_refactor_behavior_equivalence.py:222-234` 先 `pop` 并精确断言新标签，再用全等比较旧所有权标签，未降低断言强度。
- 本轮新发现：0 条 blocking；2 条 minor 残余（f018/f019）。
- 未进表的提示：
    - `test_t050_sandbox_grouping.py:85,153` 负例使用 `pytest.raises(Exception)`，建议收紧为 `ValidationError` / `DockerSandboxError`（可选，不影响当前 AC 证据）。
    - `profile-detail-number` 断言仅在 running 分支，可提升到所有状态循环（可选）。
    - `docs/pending/todo/p058_supervisor_observation_label_helper.md` 与 `review_code.md` 为流程/待办文件，非交付内容，未计入 scope。
- 总体判断：f017 已按生产路径修复，f018-f023 除两条 minor 残余外均已落实；无未解决 critical / important，全部 AC 打勾有真实测试或可复核替代证据，PASS。
- 系统性 follow-up：无。

## Round 4 (2026-11-10T18:01:52+08:00)

本轮结论见上文 Findings / 结论；本节重新列出全部 AC 复验行。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。实跑 `test_0005_backfills_display_numbers_in_creation_order`（乱序 `created_at` → p-early=1 / p-late=2，sequence=2）与 `test_display_numbers_are_not_reused_after_delete`（1/2 → 删 2 → 3，原 1 不变）。
- AC-002：TICK-VALID，re_verified。实跑 `test_coordinator_start_rpc_success`：第 2 个 Profile（`display_number=2`）请求体 `profile_number` 断言通过；`StartProfileRequest` 必填/0 拒绝（schema `minimum=1`）；`ProfileRuntimeResponse` 必填且 null 拒绝；`ProfileResponse` required 由 `test_api_subprocess.py:250` schema 校验覆盖。正整数直接断言残余见 f018（minor）。
- AC-003：TICK-VALID，re_verified。`test_sandbox_container_names_use_zero_padded_number` 钉 4 位名并经 `test_docker_doubles_contract.py` 传到真实 adapter；`test_scan_keeps_number_and_name_across_restarts` 用两个独立生产 adapter 从标签恢复 0005 且名称一致（容器名 `legacy-name` ≠ 格式化名）；实跑通过。
- AC-004：TICK-VALID，re_verified。`compose.yaml` 未改；`test_t027_release_controller.py:788` 断言 `${CBROWSER_PREFIX}-api`；现场 `docker ps -a` 确认 api/gateway/supervisor/caddy 仍属 `cbrowser`。
- AC-005：TICK-VALID，re_verified。实跑 6 条 prefix 用例：自有 profiles 放行（含 prefix≠project）、异项目拒绝、role format 校验、非 sandbox 角色拒绝；放行构建断言残余见 f019（minor）。
- AC-006：TICK-VALID，re_verified。`test_scan_recovers_number_from_labels_and_rejects_missing` 标签恢复 0003、缺编号 p2 被拒且命名抛错；`test_cleanup_container_by_name_enforces_numbered_identity` 正例 remove(force=True)、负例 `DockerSandboxError`；`test_fake_adapter_fails_closed_without_number` 对齐生产 fail-closed；实跑通过。
- AC-007：TICK-VALID，trust_prior。现场 `docker ps -a` 显示 `cbrowser-0001-browser|stream` Up、`profile-number=0001`、`config-version=1`；停止删除→重启复用 0001 与 readiness ready 依赖实施侧真实 deploy 记录与 `progress.md` 证据，reviewer 未重跑真实部署。
- AC-008：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx:362,372` 断言 `#0001/#0002`（p2 非默认编号），前端 2 文件 31 用例实跑通过；`docker ps -a` 确认唯一 `cbrowser-profiles` 分组含全部运行中沙箱。Docker Desktop 私有分组渲染按可测试性声明视为人工确认。

coverage = 7 / 8

verdict: PASS

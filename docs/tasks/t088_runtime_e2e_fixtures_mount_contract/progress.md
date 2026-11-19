---
tid: "t088"
slug: "runtime_e2e_fixtures_mount_contract"
title: "修复真实 Docker E2E 夹具的字体绑定与 named volume 挂载契约"
status: "done"
branch: "t088_runtime_e2e_fixtures_mount_contract"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "1f949747dc2d93a935aa9ed9448f0bd25b928b1d"
spec_source_sha: "1f949747dc2d93a935aa9ed9448f0bd25b928b1d"
depends_on: ""
conflicts_with: ""
note: "来源 p145，E2E 夹具与测试对齐 t075 字体绑定与 t080 named volume 挂载"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 新增 `tests/fixtures/e2e_volumes.py` 统一管理 `<prefix>-{db,data,runtime,fonts}` named volume 预初始化、`prepare_minimal_e2e_fonts_root`、`api_volume_mounts`、`supervisor_volume_mounts`、`run_volume_python`/`run_volume_json`、`ContainerPolicyAgentClient` 与按 `com.cbrowser.prefix` 精确清理；`scripts/gate_container_cleanup.py` 同步纳入 `com.cbrowser.gate-run` 命名卷清理。
- 将 `GatewayTopologyHarness`、`RealSupervisorContainer`、`RealApiProcess`、`SpoolDirectoryWatcher`、`ApiRuntimeLookup`（切换至 `/api/v1/internal/supervisor/state/snapshot`）、`conftest.py::real_api_server` 与全部直接驱动 Docker 的 E2E 用例（缓存初始化、X11 权限收敛、IPv6/netns 策略、容器图谱、核心/恢复/重放/重试/启动默认值/预览/Selkies token 等）迁至命名卷与默认受管字体契约，并通过 `/supervisor/v1/state-changes` 同步离线探针状态变更；修复 `test_supervisor_ipv6_policy_e2e.py` 旧修订重放测试遵守 `PolicyAgentRequest.policy_revision >= 1` 契约，并调序 `test_supervisor_recovery_e2e.py` 中 `sup.sigkill` 与 diagnostic spool 写入以消除后台循环竞态。
- 整体替换 `tests/unit/test_baseline_fixture_regressions.py` 与 `tests/unit/test_a36_socket_path_sync.py` 失效 bind-mount 用例，覆盖 named volume 布局、前缀清理与 X11/PolicyAgent 权限归属契约；未改动任何生产 fail-closed 逻辑。
- 全量必跑门禁（`CBROWSER_E2E_REQUIRED=1 CBROWSER_RUN_E2E=1 CBROWSER_GATE_WORKERS=2 ./scripts/run_gates.sh`）全部通过，`manifest.json` 显示 11 个套件全 `exit 0` 且 `all_passed: true`（`contract 389`、`unit 2474`、`integration 228`、`e2e 108`，含 2 个 `CBROWSER_T029_PROBE_E2E=1` 条件跳过与 0 失败/0 错误），门禁收尾清理 `removed 0 containers, 0 networks, 0 volumes`。
- Round 1 处置后补充复验：按 `f001`–`f003` 修复并对齐 `test_supervisor_retry_e2e.py` 的 `sup_client` RPC 超时（`60.0s`，与同组 `offline_recovery` / `recovery` E2E 一致）及 Strike 1/2 就绪轮询上限后，`contract` + `test_baseline_fixture_regressions.py` + `test_t045_gate_container_cleanup.py` 与 `test_supervisor_core_e2e.py` / `test_supervisor_offline_recovery_e2e.py` / `test_supervisor_retry_e2e.py` 全部通过。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-19T16:20:26+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t088_gen_f001|minor|已修|补齐 `remove_prefix_volumes` 与 `gate_container_cleanup` 卷清理单测，使 `docs/blueprint/testing.md:566` 与实测事实一致|`tests/unit/test_baseline_fixture_regressions.py`、`tests/unit/test_t045_gate_container_cleanup.py`|
|t088_gen_f002|minor|已修|`remove_prefix_volumes` 捕获 `volumes_api.list` 的 `APIError`；`test_supervisor_core_e2e.py` 改用 `cleanup_prefixed_resources` + `try/finally: d_client.close()`|`tests/fixtures/e2e_volumes.py:246`、`tests/e2e/test_supervisor_core_e2e.py:417-420`|
|t088_gen_f003|minor|已修|`sync_supervisor_state_notice` 增加 `next_cursor` 分页循环与 `api_epoch` 漂移重试|`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:920-955`|

### Round 2 (2026-11-19T17:01:09+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t088_gen_f004|minor|已修|`sync_supervisor_state_notice` 在 `api_epoch` 跨页切换时重置 `api_epoch=None`、`states=[]`、`cursor=None` 并重新从第 1 页抓取，补充 `MockTransport` 单测验证|`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:938-943`、`tests/unit/test_baseline_fixture_regressions.py:1244-1317`|

### Round 3

Round 3 零 finding，前轮 `t088_gen_f004` 已消除，全部 3 条 AC 独立复验 PASS。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：全量门禁 `CBROWSER_E2E_REQUIRED=1 CBROWSER_RUN_E2E=1 CBROWSER_GATE_WORKERS=2 ./scripts/run_gates.sh` 全部 `exit 0`（`all_passed: true`，`protocol_drift_check` / `requirements_check` / `contract` 389 / `unit` 2474 / `integration` 228 / `design_lint` / `design_check` / `frontend_test` / `frontend_build` / `image_packages` / `e2e` 108 \[106 passed, 2 skipped optional `CBROWSER_T029_PROBE_E2E=1` probe\]）；Round 1–2 处置后 `tests/unit/test_baseline_fixture_regressions.py` + `tests/unit/test_t045_gate_container_cleanup.py` `36 passed`、`contract` `388 passed, 1 skipped`、`core`/`offline`/`retry` 真实容器 E2E 全部通过
- 黑盒：真实 Docker 拓扑、Policy Agent UDS 容器内通信、Browser/Stream 沙箱隔离与全链路 UI/WebRTC 在 Mac Docker Daemon 不可变 `sha256` 镜像与真实字体集下通过；`real_engine` 未启用（不在本 task 门禁范围内）。
- review：Round 3 PASS（3/3 AC `TICK-VALID`，`f001`–`f004` 全部已修，零 finding）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 重构 E2E 基础设施与全部独立 Docker/Supervisor E2E 用例匹配 `t075` 字体绑定、`t080` named volume 挂载布局及 `t083` 状态协议，保持生产 `MountPlanner` 与 `FontSetUnavailableError` fail-closed 约束不变，完成门禁全绿与零资源残留清理。

### 长期文档闭环

- 已经在 [gate_verification.md](../../specs/gate_verification.md) front matter `tasks` 注册 `t088` 并补充第 13 节契约，同步更新 [testing.md](../../blueprint/testing.md)。

# Task review t088（reviewer_focus: 通用）

- task：`t088_runtime_e2e_fixtures_mount_contract`
- spec：`docs/tasks/t088_runtime_e2e_fixtures_mount_contract/task.md`
- diff_anchor：`1f949747dc2d93a935aa9ed9448f0bd25b928b1d`
- target：`git diff 1f949747dc2d93a935aa9ed9448f0bd25b928b1d`（含未跟踪新增文件 `tests/fixtures/e2e_volumes.py`）
- round：1
- reviewed_at：2026-11-19T16:20:26+08:00

## Findings

### t088_gen_f001 - 长期测试文档声称的 e2e_volumes 回收与清理器卷归属单元测试实际缺失

- 严重度：minor
- 锚点：文档/测试覆盖一致性（`docs/blueprint/testing.md` 与实际单元测试不符）
- 位置：`docs/blueprint/testing.md:566`、`tests/unit/test_baseline_fixture_regressions.py:293-382`、`tests/unit/test_baseline_fixture_regressions.py:597-640`、`tests/unit/test_t045_gate_container_cleanup.py:10-91`
- 问题：`docs/blueprint/testing.md:566` 写明 `tests/unit/test_a36_socket_path_sync.py` 与 `tests/unit/test_baseline_fixture_regressions.py` 已覆盖「对 `e2e_volumes` 命名卷布局、前缀隔离回收及清理器卷归属规则的单元测试」。核对源码可见：两文件仅断言了 `RealSupervisorContainer` 的挂载配置（`/run/cb/socks` subpath 与 `/data`/`/data/runtime`/`/fonts`）；`test_gateway_topology_harness_cleanup_ownership_label_rejection` 未配置 `mock_docker.volumes.list`（`MagicMock` 返回值在 `e2e_volumes.py:247` 被 `isinstance(..., (list, tuple))` 跳过），且 `test_t045_gate_container_cleanup.py` 与上述两文件均未对 `e2e_volumes.remove_prefix_volumes` 和 `scripts/gate_container_cleanup.py` 的 `volumes` 归属过滤/删除路径编写单元测试。
- 建议：为 `e2e_volumes.remove_prefix_volumes`（仅删匹配 `com.cbrowser.prefix` 的卷、忽略异前缀卷）及 `scripts/gate_container_cleanup.py` 的 `volumes` 筛选与删除补齐单元测试，或同步收敛 `docs/blueprint/testing.md:566` 的文字表述使文档与测试事实一致。

### t088_gen_f002 - E2E 卷与网络异常清理路径缺少异常隔离，可能跳过卷删除或 client.close()

- 严重度：minor
- 锚点：行为缺陷（Docker daemon 清理阶段瞬时异常导致卷清理与客户端关闭被跳过）
- 位置：`tests/fixtures/e2e_volumes.py:246`、`tests/e2e/test_supervisor_core_e2e.py:421-424`
- 问题：`remove_prefix_volumes` 在 `tests/fixtures/e2e_volumes.py:246` 直接调用 `volumes_api.list(...)` 而未捕获 `APIError`/`DockerException`，若在测试 `finally` 块中调用（如 `test_supervisor_container_graph_e2e.py:884-885`）遇到 daemon 异常，会提前抛出并跳过后续 `client.close()`。此外 `tests/e2e/test_supervisor_core_e2e.py:421-423` 在 `finally` 中直接执行 `for n in d_client.networks.list(names=[f"{prefix}-"]): n.remove()` 而不校对 `com.cbrowser.prefix` 标签、也不捕获 `NotFound`/`APIError`，若网络尚未解绑或已提前消失，`n.remove()` 抛错将跳过 `remove_prefix_volumes(d_client, prefix)` 和 `d_client.close()`，遗留 `<prefix>-{data,runtime,fonts}` 命名卷。
- 建议：在 `remove_prefix_volumes` 内捕获 `volumes_api.list` 的 `APIError` 并写入返回的 `errors` 列表；在 `tests/e2e/test_supervisor_core_e2e.py:417-424` 改用已封装容器/网络/卷标签校验与异常收敛的 `cleanup_prefixed_resources(d_client, prefix)`（并用 `try ... finally: d_client.close()` 包裹）。

### t088_gen_f003 - sync_supervisor_state_notice 未跟随 state/snapshot 游标分页

- 严重度：minor
- 锚点：行为缺陷（Profile 数超过 snapshot 单页上限时后续状态不同步）
- 位置：`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:922-932`
- 问题：`sync_supervisor_state_notice` 仅单次请求 `/api/v1/internal/supervisor/state/snapshot` 并转发首批 `snap["profiles"]`，未像同目录下的 `ApiRuntimeLookup`（`tests/fixtures/supervisor_recovery_probe/gateway_service.py:537-552`）那样迭代 `next_cursor`。当前 E2E 用例每次只建 1–2 个 Profile 不会触发该边界，但作为共享探针工具若后续用于多 Profile 场景会静默漏推后续页状态。
- 建议：参照 `ApiRuntimeLookup` 增加 `cursor` / `next_cursor` 翻页循环收集全部 `profiles` 后再推送 `/supervisor/v1/state-changes`。

## 结论

- 本轮新发现：3 条（0 critical、0 important、3 minor）
- 未进表的提示：
    - 新增交付文件 `tests/fixtures/e2e_volumes.py` 当前在工作区为 untracked 状态（尚未执行 `git add -N`），`git diff 1f949747dc2d93a935aa9ed9448f0bd25b928b1d` 默认不包含该文件；本轮已按完整文件内容完成逐行审查，建议后续在派审或提交前保持 `git add -N` 习惯以确保其直接进入 diff。
    - 已执行 7 视角正交扫描：安全（`tar` 解压使用 basename、辅助容器保持 `cap_drop=ALL` + `no-new-privileges`、`.secrets` 与 `policy-agents` 权限维持 `0o700` 且 Browser 容器不挂载 `.secrets`）、实现正确性、契约/类型、性能/资源（最小字体集导入与缓存复用）、架构/可维护性、健壮性/可观测、测试/文档一致性；`src/` 生产代码零改动，旧 bind-mount 单元测试按规则显式删除并说明原因后以新命名卷测试替换。
- 总体判断：共享真实拓扑 E2E 夹具与全部独立 Docker E2E 用例已完整对齐 `t075` 字体绑定、`t080` named volume 布局与 `t083` 状态协议，生产 fail-closed 逻辑未放宽，全量必跑门禁 11 个套件全部通过且资源零残留；仅存在 3 条 minor 改进项，判定 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。核对 `tests/fixtures/gateway_probe/topology.py`（`GatewayTopologyHarness._do_start` 经 `init_prefix_volumes` 与 `prepare_minimal_e2e_fonts_root` 初始化 `<prefix>-{db,data,runtime,fonts}` 及最小 `windows` 字体集，并以 `api_volume_mounts`/`supervisor_volume_mounts` 与 `CBROWSER_FONTS_DIR=/fonts` 启动服务且先等待 API `/api/v1/health` 与 `/api/v1/font-sets` 默认集采纳后再启 Supervisor）、`tests/fixtures/frontend_app_probe/harness.py`、`tests/e2e/conftest.py` 及 `tests/fixtures/supervisor_recovery_probe/offline_fixture.py`，确认控制面可正常创建并启动绑定字体沙箱；`src/` 无改动，缺失/篡改字体与缺失卷子路径负向测试（`test_t075_supervisor_fonts.py`、`test_t041_font_runtime.py`、`test_font_sets_api.py`、`test_t080_storage_migration.py` 等）保持完整且在门禁中全部通过。
- AC-002：TICK-VALID，re_verified。核对 `tests/e2e/test_supervisor_cache_initialization_e2e.py`、`tests/e2e/test_t068_fingerprint_gate_e2e.py`、`tests/e2e/test_x11_helper_permissions_e2e.py`、`tests/e2e/test_runtime_profile_defaults_e2e.py`、`tests/e2e/test_supervisor_policy_failure_e2e.py`、`tests/e2e/test_supervisor_core_e2e.py`、`tests/e2e/test_supervisor_container_graph_e2e.py`、`tests/e2e/test_supervisor_ipv6_policy_e2e.py`、`tests/e2e/test_supervisor_namespace_policy_e2e.py`、`tests/e2e/test_supervisor_recovery_e2e.py`、`tests/e2e/test_supervisor_retry_e2e.py` 与 `tests/e2e/test_supervisor_offline_recovery_e2e.py`，均已预初始化前缀命名卷与有效字体集并保留原有 fail-closed 断言，且结合 `tests/fixtures/e2e_volumes.py::remove_prefix_volumes`、`cleanup_prefixed_resources` 与 `scripts/gate_container_cleanup.py` 完成容器/网络/命名卷清理（门禁 `cleanup_exit_code: 0`）。
- AC-003：TICK-VALID，re_verified。复核全量门禁产出 `manifest.json`（run_id `6cbd6908178946e88e7aea6296136b5b`、`all_passed: true`、`cleanup_exit_code: 0`、8 项 `image_identity` 均为 `sha256:` 不可变镜像、11 个套件全 `exit_code: 0`）与 `junit/*.xml` 及 `logs/*.log`：`contract` 389（388 passed + 1 授权模板策略跳过）、`unit` 2474（2461 passed + 13 宿主机无 `fc-list`/字体夹具跳过）、`integration` 228（210 passed + 18 宿主机无 Chromium/Xvfb/目标引擎跳过）、`frontend_test` 718 passed、`image_packages` 5 镜像全部一致、`e2e` 两阶段合并 108（并行 44 passed + 2 `CBROWSER_T029_PROBE_E2E=1` 条件跳过，串行 62 passed，达标下限 105），全 diff 无未授权跳过或断言弱化。

coverage = 3 / 3

reviewed_scope: 090658b35f473986

verdict: PASS

## Round 2 (2026-11-19T16:59:42+08:00)

### 本轮 Findings

### t088_gen_f004 - sync_supervisor_state_notice 在 api_epoch 跨页漂移时未重置游标，会丢失前页 Profile

- 严重度：minor
- 锚点：行为缺陷（多页快照拉取第 2 页起发生 `api_epoch` 变更时丢弃第 1 页状态）
- 位置：`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:938-945`
- 问题：`elif snap["api_epoch"] != api_epoch:` 触发于已携带 `cursor` 请求后续页之后，当前实现直接 `states = list(snap["profiles"])` 并将 `cursor` 更新为当前页的 `snap.get("next_cursor")`（若为 `None` 则直接 `break`），既保留了上一轮 `cursor` 对应的后续页数据、又丢弃了前页收集到的 `states`，与第 939 行注释 `# Restart cleanly from page 1 if API epoch rolled mid-pagination.` 相悖。当前 E2E 用例仅创建 1–2 个 Profile（低于 `limit=200`）且拉取期间无 API 重启，不触发该分支，但作为共享探针工具在多页边界会返回不完整快照。
- 建议：在 `elif snap["api_epoch"] != api_epoch:` 分支内执行 `api_epoch = snap["api_epoch"]; states = []; cursor = None; continue`，强制从无游标的第 1 页重新开始拉取。

### 结论

- 前轮 finding 复核：
    - `t088_gen_f001`：**已消除**。`tests/unit/test_baseline_fixture_regressions.py:642-663` 新增 `test_remove_prefix_volumes_filters_by_prefix_and_isolates_api_error` 验证 `remove_prefix_volumes` 前缀标签过滤与 `APIError` 捕获；`tests/unit/test_t045_gate_container_cleanup.py:94-135` 新增 `test_gate_cleanup_selects_and_removes_only_ended_run_volumes` 验证 `gate_container_cleanup` 仅清理已结束 run 命名卷；工作区独立复跑 `tests/unit/test_baseline_fixture_regressions.py`、`tests/unit/test_t045_gate_container_cleanup.py` 与 `tests/unit/test_a36_socket_path_sync.py` 全部通过（52 passed），`contract` 套件通过（388 passed, 1 skipped 授权模板跳过）。
    - `t088_gen_f002`：**已消除**。`tests/fixtures/e2e_volumes.py:246-250` 在 `remove_prefix_volumes` 中捕获 `volumes_api.list` 的 `APIError` 并写入 `errors`；`tests/e2e/test_supervisor_core_e2e.py:417-420` 在 `finally` 中改用 `cleanup_prefixed_resources(d_client, prefix)` 并以 `try ... finally: d_client.close()` 包裹。
    - `t088_gen_f003`：**主路径已修，跨页漂移分支另记 `t088_gen_f004`**。`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:922-956` 已补全 `limit=200` + `next_cursor` 分页循环；其中 `api_epoch` 跨页漂移重启分支遗漏清空 `cursor = None` 的边界缺陷另记为 `t088_gen_f004`（`minor`）。
- 本轮新发现：1 条（0 critical、0 important、1 minor：`t088_gen_f004`）
- 未进表的提示：
    - `tests/e2e/test_supervisor_retry_e2e.py:224,285,394` 将 `sup_client` RPC 超时由 `30.0` 调为 `60.0`（对齐 `test_supervisor_offline_recovery_e2e.py:194` 与 `test_supervisor_recovery_e2e.py:348`），并将 Strike 1/2 等待 `observed_state == "running"` 轮询上限由 `120`/`160`（30s/40s）调为 `200`/`220`（50s/55s）；经核对 `delay_1`（`2.0 <= delay_1 <= 7.0`）与 `delay_2`（`10.0 <= delay_2 <= 15.0`）仍严格基于 DB 时间戳与容器 `Created` 时间差计算、容差未放宽，未掩盖退避时序问题。
    - `tests/fixtures/e2e_volumes.py` 现已执行 `git add -N` 并完整纳入 `git diff 1f949747dc2d93a935aa9ed9448f0bd25b928b1d`。
    - `docs/blueprint/testing.md:566` 仅列出了 `test_a36_socket_path_sync.py` 与 `test_baseline_fixture_regressions.py`，清理器卷归属单测实际补充在 `tests/unit/test_t045_gate_container_cleanup.py:94-135`（轻微交叉引用遗漏）。
- 总体判断：Round 1 提出的核心与测试覆盖问题均已修复且通过工作区单测与 `contract` 复验，Round 2 增量改动未破坏生产 fail-closed 逻辑或弱化 E2E 退避断言；仅存在 1 条不阻塞交付的 `minor` 边界缺陷，判定 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。核对 `tests/fixtures/gateway_probe/topology.py`、`tests/fixtures/frontend_app_probe/harness.py`、`tests/e2e/conftest.py`、`tests/fixtures/supervisor_recovery_probe/offline_fixture.py` 与 `tests/fixtures/e2e_volumes.py` 全量 diff，确认真实拓扑夹具按 `<prefix>-{db,data,runtime,fonts}` 与只读平台字体集初始化并在 API 采纳默认字体后再启 Supervisor，`src/` 零改动，负向字体与卷子路径测试完整保留且在门禁与工作区单测复跑中通过。
- AC-002：TICK-VALID，re_verified。核对全部独立 Docker E2E 用例与 Round 2 更新（`tests/e2e/test_supervisor_core_e2e.py:417-420` 改用 `cleanup_prefixed_resources`、`tests/fixtures/e2e_volumes.py:246-250` 捕获 `volumes_api.list` `APIError`、`tests/e2e/test_supervisor_retry_e2e.py:224,285,394` 仅调整与容器启动耗时对齐的 RPC 超时及就绪等待次数且不放宽 `delay_1`/`delay_2` 退避断言），并在工作区独立重跑 `test_baseline_fixture_regressions.py` 与 `test_t045_gate_container_cleanup.py`（52 passed）验证前缀隔离卷与门禁卷清理单测通过。
- AC-003：TICK-VALID，re_verified。基于 Round 1 核查的全量门禁 `manifest.json`（run_id `6cbd6908178946e88e7aea6296136b5b`、`all_passed: true`、`cleanup_exit_code: 0`、11 套件全 0、8 个 `sha256:` 镜像、合并 `e2e` 108 用例 >= 105 下限）及 Round 2 在当前工作区复跑的 `contract`（388 passed, 1 授权跳过）+ 修改单测文件（52 passed），结合 `test_supervisor_retry_e2e.py` / `core` / `offline` 增量核对，确认全量门禁、非弱化断言与零授权外跳过成立。

coverage = 3 / 3

reviewed_scope: d2deb7ff49d767ac

verdict: PASS

## Round 3 (2026-11-19T17:05:34+08:00)

### 本轮 Findings

Round 3 零 finding。

### 结论

- 前轮 finding 复核：
    - `t088_gen_f004`：**已消除**。`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:938-943` 在 `snap["api_epoch"] != api_epoch` 时重置 `api_epoch = None`、`states = []`、`cursor = None` 并 `continue` 重新从第 1 页拉取，不再残留旧页或跳页游标；`tests/unit/test_baseline_fixture_regressions.py:1245-1316` 新增 `test_sync_supervisor_state_notice_paginates_and_resets_on_epoch_rollover` 以 `httpx.MockTransport` 验证 `[None, "c1", None, "c2"]` 游标轨迹与仅推送新 epoch 完整两页状态；本轮独立复跑 `tests/unit/test_baseline_fixture_regressions.py` 与 `tests/unit/test_t045_gate_container_cleanup.py` 全部通过（36 passed）。
- 本轮新发现：0 条
- 未进表的提示：无
- 总体判断：Round 1–Round 2 的全部 finding（`t088_gen_f001`–`t088_gen_f004`）均已核实消除且相关单元测试通过，无未解决 critical / important / minor，判定 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。Round 1–2 已核对 `tests/fixtures/gateway_probe/topology.py`、`tests/fixtures/frontend_app_probe/harness.py`、`tests/e2e/conftest.py`、`tests/fixtures/e2e_volumes.py` 与 `tests/fixtures/supervisor_recovery_probe/offline_fixture.py` 全量对齐 named volume 与只读字体集布局，Round 3 确认 `offline_fixture.py:938-943` 仅修正状态同步跨页重置逻辑，`src/` 无改动且负向字体/卷子路径测试完整保留。
- AC-002：TICK-VALID，re_verified。Round 1–2 已核对全部独立 Docker E2E 用例对齐预初始化命名卷、有效字体集与前缀清理契约，Round 3 复跑 `tests/unit/test_baseline_fixture_regressions.py` 与 `tests/unit/test_t045_gate_container_cleanup.py`（36 passed）确认前缀卷回收、门禁卷清理与 epoch 跨页状态同步单测全部通过。
- AC-003：TICK-VALID，re_verified。基于 Round 1 核查的全量门禁 `manifest.json`（run_id `6cbd6908178946e88e7aea6296136b5b`、`all_passed: true`、`cleanup_exit_code: 0`、11 套件全 0、合并 `e2e` 108 用例 >= 105 下限）、Round 2 复跑 `contract`（388 passed, 1 授权跳过）及 Round 3 复跑上述单测（36 passed），确认全量门禁与无弱化断言成立。

coverage = 3 / 3

reviewed_scope: e850f776973cf5f6

verdict: PASS

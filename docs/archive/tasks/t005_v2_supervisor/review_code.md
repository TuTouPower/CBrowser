# Task review t005（reviewer_focus: 代码）

- task：`t005_v2_supervisor`
- spec：`docs/tasks/t005_v2_supervisor/task.md`
- diff_anchor：`84f84311815bff330a51bcd35da150fc8b4990b3`
- target：`git -C '/Users/karson/kar/code/CBrowser_t005' diff 84f84311815bff330a51bcd35da150fc8b4990b3`
- round：1
- reviewed_at：2026-10-30T06:15:00+08:00

reviewed_scope: fc9c501c863e0460

## Findings

### t005_code_f001 - RecoveryCoordinator.tick 圈复杂度较高（CC=68），多阶段恢复逻辑未解耦

- 严重度：minor
- 锚点：代码质量 / 圈复杂度标准（CC ≥ 15 建议拆分）
- 位置：`src/backend/cbrowser/supervisor/recovery_coordinator.py:63` (`RecoveryCoordinator.tick`)
- 问题：`RecoveryCoordinator.tick` 方法在一个长达 310 行的单一函数体内串联了 API 健康探测、Docker 容器扫描与按 Profile 分类、异常退出识别与原生退出事件防重保护、孤立/缺失 Runtime 容器补偿上报、以及基于 API 持久化时间窗口（2/10/30s）退避重试调度共 5 个独立生命周期阶段。计算 McCabe 圈复杂度高达 68（显著高于 CC ≥ 15 的重构阈值）。虽当前全套端到端与单元测试均通过，但过深的分支嵌套和长跨度局部状态传递增加了长期可维护性成本与边界竞态排查难度。
- 建议：将 `tick` 内顺序执行的阶段解耦拆分为私有方法，例如：
  1. `_scan_and_classify_containers()`：执行容器快照扫描与按 Profile 分组；
  2. `_detect_and_emit_abnormal_exits()`：处理 exited/dead 容器并进行 API 意愿与 native exit 防重过滤；
  3. `_detect_missing_runtimes()`：处理 API 期望 running 但容器缺失的补偿事件；
  4. `_schedule_due_retries()`：根据 durable updated_at 调度到期重试。
  将主 `tick` 圈复杂度降至 15 以下。

## 结论

- 前轮 finding 复核（Round N≥2 才写）：无（本轮为 Round 1）
- 本轮新发现：1 条（minor：t005_code_f001）
- 未进表的提示：
  - 文件过大提示：
    - `src/backend/cbrowser/supervisor/docker_adapter.py`（1024 行）：超过 800 行门槛。该模块封装了 Browser/Stream 容器初始化、网络策略 helper、挂载点安全预置、孤立容器/网络精确清理及容器快照扫描等多项低级 Docker 操作。经检查内部逻辑内聚、职责划分明确，未发现因文件过大导致的行为不一致或代码重复缺陷，按规则不进 finding 表，建议后续可按容器生命周期与网络/挂载管理解耦拆分。
    - `src/backend/cbrowser/supervisor/core.py`（764 行）：超过 400 行 minor 提示阈值。
    - `src/backend/cbrowser/supervisor/resource_policy.py`（683 行）：超过 400 行 minor 提示阈值。
    - `src/backend/cbrowser/supervisor/recovery_coordinator.py`（606 行）：超过 400 行 minor 提示阈值。
    - `tests/e2e/test_supervisor_recovery_e2e.py`（859 行）：超过 600 行 minor 提示阈值。
    - `tests/e2e/test_supervisor_retry_e2e.py`（666 行）：超过 600 行 minor 提示阈值。
  - 圈复杂度提示：除 `t005_code_f001` 指出的 `tick` (CC=68) 外，`ResourcePolicyService.record_stats` (CC=37)、`SupervisorCore.scan_and_reconcile_existing` (CC=32)、`SupervisorCore.start_profile` (CC=25)、`RecoveryCoordinator._execute_retry` (CC=24)、`SupervisorCore.consume_disk_events` (CC=20)、`DockerAdapter.attach_profile_infrastructure` (CC=20)、`control_server.create_control_app` (CC=19)、`DockerAdapter.disconnect_profile_infrastructure` (CC=16)、`SupervisorCore.stop_profile` (CC=15) 的圈复杂度亦达到或超过 15。目前各方法均有专门测试保护且未观察到逻辑缺陷，建议后续迭代择机重构。
  - 范围外观察：无。
- 总体判断：7 项验收标准（AC-001 至 AC-007）均在实现层完整落地，真实 Docker 与网络隔离/恢复门禁经主控日志和 reviewer 静态代码及独立单测核验无误，无未解决的 critical 或 important 缺陷，架构设计与安全防护严密。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：`re_verified`。核验 `PathValidator` 路径安全逻辑与 `DockerAdapter` 双容器挂载/IPC，独立重跑 25 项路径隔离与所有权单测全部通过；对照主控真实容器图日志 `sup_graph.log` 及 `container_graph_round5.log` 验证双 Profile 独立 Browser/Stream 容器与 X11/Pulse/IPC 隔离及 cross-profile 网络拦截。
- AC-002：`re_verified`。核验 `PortAllocator`、`SupervisorCore.stop_profile` 及 `OperationJournal`，独立重跑 25 项单元与集成测试（包含端口耗尽、幂等性、停机断 Viewer 顺序与释放回收）；对照 `container_graph_round5.log` 验证 3 路并发重复启动返回同一实例及内外一致的 UDP mux 端口。
- AC-003：`re_verified`。核验 `internal_supervisor.py` 的 Bearer 认证中间件与 `control_server.py`，独立重跑 `test_supervisor_rpc.py` 验证非授权 401 及密钥防泄漏；核验 `supervisor_runtime/Dockerfile` 无 SQLAlchemy/SQLite；对照 `sup_graph.log` 验证只有 Supervisor 持有 `/var/run/docker.sock`。
- AC-004：`re_verified`。核验 `EventForwarder` 磁盘 spool 原子写入与 deduplication 逻辑、`ProfileRepository` 正常退出事件收敛；独立运行 `test_runtime_event_policy.py` 通过；对照真实离线进程 E2E 日志 `sup_lifecycle.log` 证实真实 API 停机期间事件落盘、Supervisor SIGKILL 重启恢复后事件按 event_id 重放去重，正常退出在双方重启后不误启动。
- AC-005：`re_verified`。核验 `runtime_policy.py` 的 `AUTO_RETRY_DELAYS=(2.0, 10.0, 30.0)` 与 `BLOCK_AFTER_RUNTIME_FAILURES=4`，独立重跑 `test_runtime_event_policy.py`（4 次异常阻断）与 `test_supervisor_manual_retry.py`（手动清除阻断）通过；对照 `sup_lifecycle.log` 中真实 subprocess retry E2E（87.02s）的 Created/updated_at 时间差（3.04s, 11.59s, 31.21s）与 failure_count=4 阻断证据。
- AC-006：`re_verified`。核验 `DockerAdapter.attach_profile_infrastructure` 动态网络接入与 IP 下发、`network_policy.py` 内核命名空间规则及 helper 回收逻辑；对照 `sup_netpolicy.log` 与 `container_graph_round5.log` 验证 Stream 仅接入媒体网络、Gateway/coturn 动态接入并下发实际 IP、失败原子回滚无孤立网络/端口。
- AC-007：`re_verified`。核验 `ResourcePolicyService` 与 `ResourceMonitor` 采样逻辑与 `/resources` HTTP 控制接口；独立重跑相关单元测试；对照 `sup_resource.log` 与 `stream_e2e_fixed.log` 验证真实 Chrome 测量窗口内帧率在 CPU 压力下由 59 FPS 降至 16 FPS、恢复后回归 60 FPS，后台 Profile 对照不误限。

coverage = 7 / 7 = 100%

verdict: PASS

## Round 2

- task：`t005_v2_supervisor`
- spec：`docs/tasks/t005_v2_supervisor/task.md`
- diff_anchor：`84f84311815bff330a51bcd35da150fc8b4990b3`
- target：`git -C '/Users/karson/kar/code/CBrowser_t005' diff 84f84311815bff330a51bcd35da150fc8b4990b3`
- round：2
- reviewed_at：2026-10-30T10:05:07+08:00

reviewed_scope: 0c131820c44b993e

### 前轮 finding 复核

- `t005_code_f001`（minor）：`RecoveryCoordinator.tick` 圈复杂度较高（CC=68）。已在 `docs/tasks/t005_v2_supervisor/note.md` 处置表登记为 `遗留`，并转办技术债条目 `docs/pending/todo/p001_supervisor_recovery_tick_complexity.md`（p001）。由于 t005 已完成整套真实 Docker 验证门禁冻结，本阶段不改动生产逻辑以防破坏已测通过状态，同意作为技术债遗留，不阻断 PASS。

### 本轮增量复核

1. `tests/fixtures/supervisor_recovery_probe/gateway_contract.md`：仅按 pre-commit md_kx 规范调整列表缩进（由 2 空格改为 4 空格），无契约语义变化。
2. `tests/e2e/test_supervisor_policy_failure_e2e.py`：响应 test reviewer 提出的 `t005_test_f001`，将 `if gates_root.is_dir():` 与 `if runtime_dir.is_dir():` 条件防御弱化断言移除，改为对 `ready_markers` 与 `runner_info` 的无条件断言（验证列表长度为 0）。查证主控真实运行日志 `/Users/karson/kar/code/CBrowser_t005/.scratch/t005_final/round1/policy_failure_p002.log`，测试 1 passed（5.65s），无副作用与逻辑破损。

### 本轮新发现

无（0 条）

### 结论

- 前轮 finding 复核：1 条已合规转办遗留（t005_code_f001 -> p001）
- 本轮新发现：0 条
- 未进表的提示：无新提示，Round 1 文件过大与圈复杂度提示依然适用
- 总体判断：本轮增量仅包含测试断言加固与夹具文档格式化，未引入任何生产代码变更或逻辑破坏，全套 AC 实现与不变量保持完整有效。
- 系统性 follow-up：无

verdict: PASS

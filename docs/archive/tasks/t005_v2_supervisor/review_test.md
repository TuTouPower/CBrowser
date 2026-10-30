# Task review t005（reviewer_focus: 测试）

- task：`t005_v2_supervisor`
- spec：`docs/tasks/t005_v2_supervisor/task.md`
- diff_anchor：`84f84311815bff330a51bcd35da150fc8b4990b3`
- target：`git -C '/Users/karson/kar/code/CBrowser_t005' diff 84f84311815bff330a51bcd35da150fc8b4990b3`
- round：1
- reviewed_at：2026-10-30T06:30:00+08:00

reviewed_scope: fc9c501c863e0460

## Findings

### t005_test_f001 - test_policy_installation_failure_fail_closed_and_cleanup 存在条件跳过断言（if-guard）

- 严重度：minor
- 锚点：测试严谨性 / 条件断言规避风险
- 位置：`tests/e2e/test_supervisor_policy_failure_e2e.py:176` 及 `tests/e2e/test_supervisor_policy_failure_e2e.py:184`
- 问题：用例在验证网络策略安装失败时的封闭状态（fail-closed）时，检查 startup gate 的 `ready.json` 和 `runner_info.json` 遗留标记使用了 `if gates_root.is_dir(): assert len(ready_markers) == 0` 和 `if runtime_dir.is_dir(): assert len(runner_info) == 0`。若测试环境发生路径配置漂移或目录未按预期创建，该断言块将被静默跳过，未能形成无条件绝对断言。虽用例后续有严格的 DockerSandboxError 抛出、API failure_count 统计与 0 容器/网络泄漏断言保护，但条件分支包裹断言属于潜在弱化模式。
- 建议：将条件分支改为无条件断言，例如：
  ```python
  assert not (gates_root.exists() and list(gates_root.glob("**/ready.json")))
  assert not (runtime_dir.exists() and list(runtime_dir.glob("**/runner_info.json")))
  ```
  确保不论目录是否存在，断言均实际执行且不被跳过。

## 结论

- 前轮 finding 复核（Round N≥2 才写）：无（本轮为 Round 1）
- 改测方向复核：本轮无「迁就实现」的改测。既有测试修改两处：
  1. `tests/unit/test_domain_and_repository.py`：旧用例 `test_runtime_events_convergence_and_exit_contract` 中包含硬编码 3 次失败阻断断言，因 AC-005 明确收敛为“首次异常 + 3 次重试（2/10/30s），共 4 次异常后阻断”，实施方按规范整体删除旧语义用例，在新模块 `tests/unit/test_runtime_event_policy.py` 中编写 4 项单元测试完整覆盖正常退出、重复重放、异常保留意愿、迟到异常及 4 次异常阻断，并在 `note.md` 中说明归因，未就地改旧预期制造假绿。
  2. `tests/e2e/test_stream_runtime_e2e.py`：在 `test_stream_runtime_multi_viewer_e2e` 中增补调用 `stream_monitor.py::verify_stream_cpu_policy`，用于在真实 Chrome 解码会话中采集 2 秒窗口帧率并断言 CPU 限额生效（59 FPS -> 16 FPS -> 60 FPS），未修改既有测试预期的任何断言。
- 本轮新发现：1 条（minor：t005_test_f001）
- 未进表的提示：
  - 契约区 drift 核实：`task.md` 契约区自 diff_anchor 以来微调了范围（增加 supervisor_runtime Dockerfile、协议导出脚本及统一重试策略模块）与 AC-005 文本（明确“随后按2/10/30秒各重试一次，三次重试均失败后阻断（failure_count记录实际异常总数，此时为4）”）。该调整已由 `docs/blueprint/decisions.md`（Decision 008）记录为架构决策，消除了“3 档延迟重试”与“3 次失败阻断”的数学计数冲突，且实现与测试均严格覆盖了全部 3 档延迟重试与第 4 次失败阻断，不构成破坏性违约。
- 总体判断：AC-001 至 AC-007 均由真实生产路径的端到端与集成测试支撑，无恒真断言、无 mock 冒充真实服务或弱化断言，无未解决的 critical 或 important 缺陷，测试可信度高。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：`re_verified`。查证 `test_supervisor_core_e2e.py::test_supervisor_dual_profile_real_docker_e2e` 验证双 Profile 独立容器与 IpcMode（shareable / container:<browser>）及只读挂载；`test_supervisor_container_graph_e2e.py` 验证跨 Profile TCP socket 访问被内核网络策略拒绝；`test_supervisor_adapter_paths.py` 与 `test_supervisor_profile_path_ownership.py` 验证符号链接与路径穿越拒绝；`test_supervisor_cache_initialization_e2e.py` 验证只读引擎缓存与 GeoIP 初始化。
- AC-002：`re_verified`。查证 `test_supervisor_container_graph_e2e.py` 验证并发 3 路重复启动幂等性与 UDP mux 端口内外一致绑定；`test_supervisor_core.py::test_port_allocator_exhaustion_and_reuse` 与 `test_supervisor_start_capacity.py` 验证端口耗尽报错与释放后回收；`test_supervisor_container_graph_e2e.py` 验证 Viewer 断开先于容器停止。
- AC-003：`re_verified`。查证 `test_supervisor_container_graph_e2e.py` 容器拓扑 inspect 断言仅 Supervisor 挂载 Docker Socket 且 Supervisor 容器无 SQLite / SQLAlchemy；`test_supervisor_rpc.py` 独立 HTTP 进程验证 Bearer 凭证与未授权 401；`internal_supervisor.py` 白名单路由直接复用规范 handler，事务内不等待容器启动。
- AC-004：`re_verified`。查证 `test_supervisor_offline_recovery_e2e.py` 验证真实 API 停止期间事件落盘、Supervisor SIGKILL 重启恢复后事件重放与去重、以及正常退出在重启后不误启动；`test_supervisor_recovery_e2e.py` 验证 SIGKILL 协调与端口不变性；`test_supervisor_startup_recovery_e2e.py` 验证启动中断与缺失容器补偿。
- AC-005：`re_verified`。查证 `test_supervisor_retry_e2e.py` 真实子进程与容器测试，实测 Docker Created 与 API updated_at 时间差依次满足 2.0s、10.0s、30.0s（SIGKILL Supervisor 不重置计时），第 4 次失败触发 restart_blocked=True，手动 patch 清除阻断立即恢复，正常退出不重试；`test_supervisor_container_graph_e2e.py` 验证 RestartPolicy=no。
- AC-006：`re_verified`。查证 `test_supervisor_container_graph_e2e.py` 验证 Stream 仅接入媒体网络且 Gateway/coturn 动态接入并下发内部 IP；`test_supervisor_infrastructure_network_e2e.py` 验证动态接入失败原子回滚不影响其他 Profile；`test_supervisor_orphan_helpers_e2e.py` 验证启动锁内孤立 helper 回收；`test_supervisor_policy_failure_e2e.py` 验证失败回滚零容器网络泄漏。
- AC-007：`re_verified`。查证 `test_stream_runtime_e2e.py` 中 `verify_stream_cpu_policy` 在真实 Chrome 测量窗口实测 CPU 过载帧率下降（59 FPS -> 16 FPS -> 60 FPS）；`test_supervisor_resource_monitor_e2e.py` 验证 `/resources` Bearer 查询关联测量窗口与决策状态；`test_supervisor_resource_policy_e2e.py` 验证低负载与后台 Profile 不误触发。

coverage = 7 / 7 = 100%

verdict: PASS

## Round 2 (2026-10-30T10:30:00+08:00)

- round：2
- reviewed_at：2026-10-30T10:30:00+08:00

reviewed_scope: 0c131820c44b993e

### Findings

（本轮零新 finding）

### 结论

- 前轮 finding 复核：
  - `t005_test_f001`（minor，条件跳过断言）：已消除。查证 `tests/e2e/test_supervisor_policy_failure_e2e.py:174-188`，两处 `if dir.is_dir():` 外层条件已移除，改为无条件执行 `ready_markers = list(gates_root.glob("**/ready.json"))` 与 `runner_info = list(runtime_dir.glob("**/runner_info.json"))`，断言 `len(...) == 0` 保证在任何路径状态下均被无条件执行。主控已真实复跑该用例（`policy_failure_p002.log`：1 passed in 5.65s）。
- 改测方向复核：本轮无「迁就实现」的改测。
- 本轮新发现：0 条。
- 交付增量核实：
  1. `tests/fixtures/supervisor_recovery_probe/gateway_contract.md`：仅由 `md_kx` 工具统一格式化，列表缩进由 2 空格调整为 4 空格，不含语义或行为逻辑变更。
  2. `tests/e2e/test_supervisor_policy_failure_e2e.py`：按 `t005_test_f001` 将条件断言改为无条件断言，逻辑严格收拢。
- 总体判断：前轮 minor finding 已彻底修复，交付增量纯净且验证通过，无 critical / important 缺陷，测试质量与可信度符合标准。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：`re_verified`。双 Profile 独立容器与受限挂载、内核网络策略拒绝跨 Profile TCP 探测保持不变。
- AC-002：`re_verified`。并发 3 路重复启动幂等性与 UDP mux 端口内外一致绑定保持不变。
- AC-003：`re_verified`。仅 Supervisor 挂载 Docker Socket 且无 SQLite/SQLAlchemy 拓扑断言保持不变。
- AC-004：`re_verified`。API 离线事件落盘与 Supervisor SIGKILL 重放去重收敛保持不变。
- AC-005：`re_verified`。2/10/30s 真实重试延迟、SIGKILL 不重置计时与 failure_count=4 阻断保持不变。
- AC-006：`re_verified`。本轮无条件断言加强（`test_supervisor_policy_failure_e2e.py`）复跑 1 passed，策略失败回滚与零孤立泄漏复验成立。
- AC-007：`re_verified`。真实 Chrome 测量窗口内 CPU 过载降帧（59 -> 16 -> 60 FPS）与决策查询保持不变。

coverage = 7 / 7 = 100%

verdict: PASS

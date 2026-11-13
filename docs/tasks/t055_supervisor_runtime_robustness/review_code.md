# Task review t055（reviewer_focus: 代码）

- task：`t055_supervisor_runtime_robustness`
- spec：`docs/tasks/t055_supervisor_runtime_robustness/task.md`
- diff_anchor：`1c0963845705e355ccdd7e1c3963533c9df7437a`
- target：`git -C '<home>/workspace/CBrowser_t055' diff 1c0963845705e355ccdd7e1c3963533c9df7437a`
- round：1
- reviewed_at：2026-11-11T23:24:00+08:00

## Findings

### t055_code_f001 - prepare_socket_dir 的 entry.stat() 未防条目竞态消失

- 严重度：minor
- 锚点：AC-009（A12 slot 清理先校验再 unlink）；行为缺陷：slot 条目在 `exists()` 与 `stat()` 之间消失时，裸 `FileNotFoundError` 外泄而非结构化错误
- 位置：`src/backend/cbrowser/runtime_agent/socket_root.py:156`
- 问题：`if entry.exists():`（`socket_root.py:152`）之后 `st = entry.stat()`（`:156`）没有任何保护。若条目在此间被删（另一进程或旧实例收尾并发清理同一 slot），`stat()` 抛 `FileNotFoundError`，它既不是 `SocketRootError`，也会绕过 `docker_adapter.py:1154`（`prepare_agent_socket_dir`）的 `except SocketRootError` 转换，原样外泄到 supervisor 启动流程——调用方预期的是结构化冲突/清理错误，得到的是未预期的裸异常。同一函数内 `entry.unlink()` 已有 `except FileNotFoundError: pass`（`:165-167`），同一文件 `managed_socket_target` 的 `stat()` 也有 FileNotFoundError 保护，说明本应同样处理。触发窗口很小（需并发删除，且同一 slot 的清理通常由 per-profile 锁串行化），未观察到可复现的崩溃，属防御性缺口，故定 minor。
- 建议：把 `st = entry.stat()` 包进 try/except FileNotFoundError，条目已消失视为已清理，直接返回 directory（与同函数 unlink 处的处理一致）。

## 结论

- 本轮新发现：1 条，minor；无 critical / important。
- 未进表的提示：
  - A7 偏离评估（成立，无需改动）：恢复锚定 grace 用 `RegistrationState.recovery_armed` 标志而非评审原文「两处都保留 lost_at」。字面做法会破坏 t026 stale-grace 回归——本轮实测 t026 全部 7 个文件 76 绿（`test_t026_supervisor_convergence.py`、`test_t026_runner_network_events.py`、`test_t026_control_endpoints.py`、`test_t026_media_network_adapter.py`、`test_t026_network_policy_verify.py`、`test_t026_address_pool.py`、`test_t026_control_client.py`）。语义等价：grace 属于恢复、锚定在恢复时刻，`_within_registration_recovery_grace` 仅在 `lost_at` 为 None 时设值，Gateway 不可达的收敛轮次不重锚；starting 释放同时清 terminal dedupe，与 t026 f015 逻辑一致（健康确认证明该代未终结，之后终态须可再次上报）；CDP 在 starting 期间的拒绝由既有 `control_server.py:487` 兜底。
  - `_install_network_policy` 超时/传输错误分支不抓 helper 日志（有意的边界，不进表）：AC-001 的「失败分支」指非零退出分支，已实现并有测试（`docker_adapter.py:127` `_HELPER_LOG_TAIL_BYTES = 2000`，日志先截断后经共享 `redact()` 再删 helper）；超时分支按既有脱敏策略仅报异常类型名，且 daemon 可能无响应时调 `helper.logs()` 有挂起风险。建议后续把 AC-001 的措辞收窄为非零退出分支，不改代码。
  - socket root 长度校验的边界（观察，不进表）：`PathValidator` 构造时仅在显式配置 `CBROWSER_SOCKET_ROOT` 时走最长路径校验；未设该变量且 data_root 很长时，默认 `data_root/"sockets"` 不在构造期校验，失败会晚到 agent 启动（agent 内 `resolve_socket_root()` 同一校验会拒绝）。部署实测：`compose.yaml:111` 给 supervisor 设了 `CBROWSER_SOCKET_ROOT`（默认 `/run/cb/socks`），所以受支持的部署路径上校验在 supervisor 启动期即生效；残留边界只影响非 compose 的自定义长 data_root 启动方式，且失败仍是 fail-closed。
  - 复杂度提示：`automation_cdp` CC 37→42（A10 关码透传分支本身带来，本就 37）；`_converge_session` 37、`_reconcile_profile` 61（均为既有巨函数，本轮各增 1–2 个分支）；`prepare_socket_dir` 11、`_install_network_policy` 10、`scan_and_reconcile_existing` 11。均未产出可观测缺陷，按链内惯例仅作结论提示，不进表。
  - 文件规模提示：生产代码净 +204 行（core.py 3207 行 +70、runner.py 667 行 +37、docker_adapter.py 2608 行 +32、automation_router.py 276 行 +22、socket_root.py 225 行 +43）；新测试文件 `test_t055_supervisor_runtime_robustness.py` 820 行。仅作提示。
  - 锁定项核查通过：`com.cbrowser.deployment-id` 全仓零命中；默认前缀 `cbrowser-t005` 完好（`docker_adapter.py:254`）；`NotFound` 在 core.py 中只剩注释（`core.py:1879,1881`）。
  - 基线失败说明：`test_supervisor_cdp_websocket_forwards_to_agent_uds` 在 pristine 基线 `1c09638` 的独立 worktree 上同样失败（已实测，与 t055 无关，是基线存量失败）。
  - 与 test review 的去重：新测试文件 docstring 的 AC 编号整体错位一位（17 处）已由 test reviewer 立为 `t055_test_f001`，本报告不重复建表；test review 的其余 finding（f002–f004）均属测试层，不属代码审阅职责。
  - 本轮自跑实数（验证 venv，`PYTHONPATH=src/backend:tests`）：新 t055 测试 5 文件 + p058/a36 相关批 82 passed；t026 相关批 44 passed + 上述基线失败 1 个；t026 全部 7 文件 76 passed；后端全量（`tests/unit` + `tests/integration`，433.79s）2070 passed / 25 failed / 8 skipped，25 个失败与 t054 基线逐名一致、零新增（executor chain 7、t028 run_gates 4、normal_exit_replay 4、automation_probe_chain 3、t034 依赖锁 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1）。前端未由本轮复跑（test reviewer 已跑：538 passed / 0 failed）。
- 总体判断：实现完整，10 个 AC 全部复验通过，仅 1 处 minor，verdict PASS；minor 须在 progress.md 处置后由下一轮复核。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`_run_policy_helper` finally 内 remove 失败仅记 warning 不覆盖退出码；`_install_network_policy` 非零退出分支先抓 helper 日志尾 2000 字节经共享 redact() 再删 helper；自跑 A4 新测试通过。
- AC-002：TICK-VALID，re_verified。`forget_instance_events` 按 (profile_id, instance_id, config_version) 三元组过滤，只清目标实例跨版本记录；起始路径整 profile 清理为既有有意行为；自跑 A5 新测试通过。
- AC-003：TICK-VALID，re_verified。`_ensure_media_attachment` 捕获 DockerSandboxError 返回 MEDIA_ATTACH_GATEWAY_MISSING；离线恢复消费返回值、按 profile 每 60s 限流记日志；自跑 A6 新测试通过。
- AC-004：TICK-VALID，re_verified。恢复预设 observed_state="starting" 且不立即上报 running；健康确认后升级；CDP 在 starting 期间由 control_server.py:487 拒连（4404）；自跑恢复测试通过。
- AC-005：TICK-VALID，re_verified。恢复锚定 lost_at + recovery_armed，90s 内 Gateway 不可达不重锚；确认未注册且过期后替换；新注册立即替换；自跑 grace 测试通过（含手动老化 200s）。
- AC-006：TICK-VALID，re_verified。非 NotFound 查找失败记 error_type 日志；observed_instance_id 为全部异实例 id 元组；NotFound 分支已删（docker-py list 返回 []，永不抛）；自跑 A8 新测试通过。
- AC-007：TICK-VALID，re_verified。finally 内先读 upstream.close_code 再 upstream.close()（close 包 try/except 不挡客户端关码）；客户端先断开标志抑制透传；1005 不透传；spike 三结论已独立复现（4403/1000/4403）；自跑 4 个 CDP 关码集成测试通过。
- AC-008：TICK-VALID，re_verified。udp_mux_bounds() 在 run_supervisor 内解析一次传给 PortAllocator；空 env 回默认、非法值报 ValueError 明确错误；协议/策略/容器规约/agent 配置共 6 处同源；自跑 4 个新测试通过。
- AC-009：TICK-VALID，re_verified。prepare_socket_dir 按序校验 symlink/属主/类型/存活，冲突原样保留、仅 stale 自有 socket 清理；最长 slot 路径在 PathValidator 构造期校验；compose 部署给 supervisor 设了 CBROWSER_SOCKET_ROOT；自跑 8 个新测试通过。
- AC-010：TICK-VALID，re_verified。container watcher 抽为 _watch_container_events，与 network 版对称，各自只关自己的流；停机最终 pass 仍关双流；自跑 3 个新测试通过。

coverage = 10/10

reviewed_scope: 9872aed1e2feba1b

verdict: PASS

## Round 2 (2026-11-11T23:57:54+08:00)

- task：`t055_supervisor_runtime_robustness`
- spec：`docs/tasks/t055_supervisor_runtime_robustness/task.md`
- diff_anchor：`1c0963845705e355ccdd7e1c3963533c9df7437a`
- target：`git -C '<home>/workspace/CBrowser_t055' diff 1c0963845705e355ccdd7e1c3963533c9df7437a`
- round：2
- reviewed_at：2026-11-11T23:57:54+08:00

## Findings

### t055_code_f002 - managed_socket_target 的 os.lstat() 未防 slot 目录竞态消失

- 严重度：minor
- 锚点：行为缺陷 + A12（socket slot 校验路径）；slot 目录在 `os.open` 与 `os.lstat` 之间消失时，裸 `FileNotFoundError` 外泄而非结构化错误
- 位置：`src/backend/cbrowser/runtime_agent/socket_root.py:207`
- 问题：`managed_socket_target` 内 `fd_stat = os.fstat(dir_fd)`（`:206`）之后 `path_stat = os.lstat(str(directory))`（`:207`）没有任何保护。若 slot 目录在此间被删（另一进程或旧实例收尾并发清理同一 slot），`lstat()` 抛 `FileNotFoundError`，它既不是 `SocketRootError`，也不在 `os.open` 的 `except OSError`（`ENOENT`/`ENOTDIR` 时 yield 回落）覆盖范围内——`os.open` 已成功，异常发生在 open 之后。同一文件的 `os.stat(..., dir_fd=dir_fd)`（`:219-222`）有 `except FileNotFoundError: sock_stat = None` 保护，`prepare_socket_dir` 的 `entry.stat()` 在本轮 f001 修复中也已加同类保护，说明本处本应同样处理。实测复现（/tmp 一次性探针，已删）：把 `os.lstat` 桩为首次调用抛 `FileNotFoundError`，`managed_socket_target` 原样外泄裸 `FileNotFoundError`，而非 `SocketRootError`。与 f001 同类但影响更小：两处调用方均有宽泛 except 兜底——`control_server.py:564`（`except Exception` 记 "CDP tunnel closed" 后关闭客户端连接）、`core.py` `_query_agent_health`（`except Exception` 返回 None）——故可观测后果是偶发的误分类瞬时失败（一次 CDP 建隧失败 / 一次健康查询读作未知），而非崩溃或数据丢失；触发窗口同样很小，故定 minor。
- 建议：把 `path_stat = os.lstat(str(directory))` 包进 try/except FileNotFoundError；目录已消失视为 slot 不可用，按 `os.open` 失败时的同一语义处理（yield `str(sock)` 回落，由调用方按“socket 不存在”处理），或转为 `SocketRootError`。最小修复与 f001 同款。

## 结论

- 前轮 finding 复核：t055_code_f001 已消除（独立实跑 + 先红验证，不采信处置表自述）。`socket_root.py:155-161` 的 `stat()` 确已包进 try/except FileNotFoundError，条目消失时返回 directory；竞态测试 `test_prepare_socket_dir_tolerates_entry_vanishing_between_exists_and_stat`（`test_t055_socket_slot_cleanup.py:64`）是真实竞态模拟——它 monkeypatch `Path.exists`，在 `exists()` 返回 True 后立即 `os.unlink` 删除条目，再调真实的 `prepare_socket_dir`（非桩实现的 stat），断言不抛错且返回 directory。自跑：该测试通过；临时去掉 try/except 的变异探针使该测试变红（`FileNotFoundError`，见 pathlib 栈），恢复后 sha256 校验与变异前字节一致（`91ed3a26…`）。同函数内其余路径已核查：`entry.is_symlink()`（lstat 语义，缺失返回 False 不抛）、`entry.unlink()`（已有 `except FileNotFoundError: pass`）、`_socket_is_live`（connect 的 FileNotFoundError 视为 stale）均已防护。
- 本轮新发现：1 条，minor（t055_code_f002，见上）。本轮修复改动面经核查仅涉 `socket_root.py`（生产）+ 测试文件 + progress.md；`core.py`、`docker_adapter.py`、`automation_router.py` 的 R1 实现标记均在位：A10 读码 `:242-244` 仍在 `upstream.close()` `:254` 之前；A7 `recovery_armed`（`core.py:212,556,665,1543`）未变；A4 `_HELPER_LOG_TAIL_BYTES = 2000`（`docker_adapter.py:127`）未变。
- 未进表的提示：
  - `prepare_socket_dir` 内 `os.chown`/`os.chmod`（`socket_root.py:148-150`）与 `managed_socket_target` 的 `os.fstat(dir_fd)`（`:206`，fd 有效故不受路径消失影响）之外，同一函数的目录级竞态只剩 chown/chmod 窗口：目录刚由本次 `mkdir(exist_ok=True)` 建出，并发删除需恰好落在其后瞬间，窗口比 f001/f002 更窄，无可观测崩溃，不进表。
  - 圈复杂度：`prepare_socket_dir` 因 f001 修复 +1 个 except 分支，约 12，仍低于 15 的 minor 阈值；`managed_socket_target` 未变。
  - 文件规模：`socket_root.py` 231 行（低于 400）；新测试文件 `test_t055_supervisor_runtime_robustness.py` 888 行（R1 时 820 行，修复轮 +68 行），超 600 行测试阈值，按规则只作结论提示、不进表。
  - 锁定项核查通过：`com.cbrowser.deployment-id` 在 src/scripts/compose.yaml 全树零命中；默认前缀 `cbrowser-t005` 完好；`git status` 无计划外未跟踪交付文件。
  - 截断测试字节核实（防回显脱敏误判）：`test_t055_supervisor_runtime_robustness.py:152,171` 的凭据拼接经 base64 解码确为 `SECRET.encode()`（`SECRET = "hunter2-secret-value"`，`:40`），非字面量 `<redacted>`，脱敏断言非空转。
  - 本轮自跑实数（验证 venv，`PYTHONPATH=src/backend:tests`）：新 t055 测试 5 文件 + p058/a36 相关批 69 passed；`test_t055_socket_slot_cleanup.py` 9 passed（含竞态测试）；变异探针（去 guard）竞态测试变红、恢复后 sha256 一致；lstat 探针证实 f002 外泄路径。
- 总体判断：f001 已真实消除，仅 1 条新 minor（f002），无 critical / important，10 个 AC 全部复验通过，verdict PASS；minor 须在 progress.md 处置后由下一轮复核。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。A4 实现未变（`_HELPER_LOG_TAIL_BYTES = 2000`，先截断后 redact 再删 helper）；截断测试经 base64 核实为真实凭据字节，断言非空转；自跑 A4 新测试通过。
- AC-002：TICK-VALID，re_verified。A5 实现未变（三元组过滤 + 起始路径整 profile 清理为既有有意行为）；自跑 A5 新测试通过。
- AC-003：TICK-VALID，re_verified。A6 实现未变（gateway 解析失败转状态、离线恢复限频日志）；自跑 A6 新测试通过。
- AC-004：TICK-VALID，re_verified。A7 实现未变（恢复预设 starting、健康确认后升级、CDP 在 starting 期间拒连）；自跑恢复测试通过。
- AC-005：TICK-VALID，re_verified。A7 宽限实现未变（`recovery_armed` + 90s 锚定恢复时刻）；89s/91s 边界测试自跑通过。
- AC-006：TICK-VALID，re_verified。A8 实现未变（非 NotFound 异常记日志、全部异实例 id 元组、NotFound 分支已删）；自跑 A8 新测试通过。
- AC-007：TICK-VALID，re_verified。A10 实现未变（finally 内先读 `upstream.close_code` `:242-244` 再 `upstream.close()` `:254`）；自跑 4 个 CDP 关码集成测试通过。
- AC-008：TICK-VALID，re_verified。A11 实现未变（`udp_mux_bounds()` 启动时解析一次、非法值启动失败）；自跑 4 个新测试通过。
- AC-009：TICK-VALID，re_verified。f001 已真实消除（先红验证 + sha256 恢复校验）；slot 清理校验顺序（symlink/属主/类型/存活）未变，冲突原样保留；f002 不在 AC-009 的 slot 清理路径上（`managed_socket_target` 为 CDP/健康查询的读路径），不影响本 AC 的打勾成立；自跑 9 个 socket slot 测试通过。
- AC-010：TICK-VALID，re_verified。A13 实现未变（`_watch_container_events` 与 network 版对称、各关自己的流）；自跑 3 个新测试通过。

coverage = 10/10

reviewed_scope: 1ea2d3c9a8a562b0

verdict: PASS

## Round 3 (2026-11-12T00:33:49+08:00)

- task：`t055_supervisor_runtime_robustness`
- spec：`docs/tasks/t055_supervisor_runtime_robustness/task.md`
- diff_anchor：`1c0963845705e355ccdd7e1c3963533c9df7437a`
- target：`git -C '<home>/workspace/CBrowser_t055' diff 1c0963845705e355ccdd7e1c3963533c9df7437a`
- round：3
- reviewed_at：2026-11-12T00:33:49+08:00

## Findings

### t055_code_f003 - managed_socket_target 圈复杂度 17，本 task 又增一分支

- 严重度：minor
- 锚点：代码质量 / 圈复杂度标准；行为缺陷：无——本 finding 只计复杂度，未产出可观测缺陷
- 位置：`src/backend/cbrowser/runtime_agent/socket_root.py:187-240`（`managed_socket_target`）
- 问题：AST 计数器实测 `managed_socket_target` CC=17（基数 1 + 3 个 except + 8 个 if + 3 个 `and` + 1 个 `or` + 1 个嵌套 if；计数口径已校准：同一计数器对 `prepare_socket_dir` 得出 CC=12，与 Round 2 报告的「约 12」逐字一致）。本 task 之前该函数已是 CC=16（task 全量 diff 中本函数仅改一处：f002 修复加的 lstat try/except，+1 分支），即本 task 在已超阈值的函数上继续堆分支，触发「CC ≥ 15 且本 task 仍增加分支 → minor」。该函数守的是 socket slot 的 TOCTOU 一致性校验（fd 与路径 dev/ino 比对、ISDIR、0o022、属主/组），分支密度正是 f001/f002 两处竞态缺口藏身的地方，拆分有实际可读性收益，不只是数字。
- 建议：把 fd/路径一致性校验（dev/ino 比对、ISDIR、0o022、uid/gid 四项）抽为 `_validate_slot_dir(fd_stat, path_stat, managed_uid, managed_gid)`，主函数降到 15 以下；行为与异常语义保持逐字一致（`SocketRootError` 文本不变）。

## 结论

- 前轮 finding 复核：t055_code_f002 已消除（独立实跑 + 先红验证，不采信处置表自述）。
  - 守卫位置正确：`socket_root.py:207-216`，`path_stat = os.lstat(str(directory))` 包进 try/except FileNotFoundError；目录在 open() 与 lstat() 之间消失时 `yield str(sock)` 并 return，与 open() 的 ENOENT/ENOTDIR 回落（`:198-201`）yield 值逐字相同。
  - 调用方语义一致（逐一读过两处调用点）：`control_server.py:510-515`（`if not Path(uds_target).is_socket(): await websocket.close(code=1011); return`）与 `core.py:2051-2057`（`if not Path(uds_target).is_socket(): yield None; return`）均把回落值当“不存在”处理；`_query_agent_health` 另有 `except Exception → None` 兜底。
  - `validate_socket_deployment`（`socket_root.py:125-131`）不调 `os.lstat`（仅长度校验），全文件唯一 `os.lstat` 在 `:208`；回落判定不受影响，修复方该主张属实。
  - 新测试真实：`test_managed_socket_target_tolerates_directory_vanishing_between_open_and_lstat`（`test_t055_socket_slot_cleanup.py:163`）的 lstat 桩仅对目录路径抛 FileNotFoundError、其余路径委托真实 `os.lstat`，断言回落到普通 socket 路径且不抛裸异常。先红验证：临时去掉 guard 后该测试变红（`FileNotFoundError: [Errno 2] .../socks/1a59428c546c4f3c1d65`，exit 1）；恢复后 sha256 与修复前字节一致（`80727d07…`，与修复方 handoff 所称一致）。
  - 无 fd 泄漏：回落分支的 `yield` 在 `try/finally` 内（`os.close(dir_fd)`），return 后 finally 仍执行，与 open 失败路径相同。
  - 回落方案（而非转 `SocketRootError`）成立：两调用方均已按“不存在”处理该返回值，目录中途消失按 slot 不可用而非错误处理，与 open 失败路径语义完全一致。
- Round 1/2 修复仍在位：f001 的 `entry.stat()` 守卫（`socket_root.py:155-161`）未变；A4 `_HELPER_LOG_TAIL_BYTES = 2000`（`docker_adapter.py:127`）、A7 `recovery_armed`（`core.py` 4 处）、A10 读码 `:242-244` 仍在 `upstream.close()` `:254` 之前、A11 `udp_mux_bounds()`（`udp_mux.py:35` 定义，7 处消费者同源）、A13 `_watch_container_events`（`runner.py:274`，`:406` 调用）均在位；本轮修复改动面仅涉 `socket_root.py` + 测试文件 + progress.md。
- 本轮新发现：1 条，minor（t055_code_f003，见上）。
- 未进表的提示：
  - 文件规模：`socket_root.py` 240 行（低于 400）；`test_t055_supervisor_runtime_robustness.py` 888 行（超 600 行测试阈值，按降级规则只作结论提示，不进表；自 Round 2 起未变）。
  - 圈复杂度：`prepare_socket_dir` CC=12（低于 15）；`_converge_session` 37、`_reconcile_profile` 61 为既有巨函数，本轮未再增分支，沿用 Round 1 的结论提示处理，不重立 finding。
  - 锁定项核查通过：`com.cbrowser.deployment-id` 在 `src/backend/cbrowser/{runtime_agent,supervisor,api}`、`scripts/`、`compose.yaml`、`config/` 全树零命中；默认前缀 `cbrowser-t005` 完好（`docker_adapter.py:254`）。
  - AC-001 措辞（Round 1 结论段遗留，未变）：超时分支不抓 helper 日志属有意边界，已记入 progress.md 实施笔记，不改契约、不进 finding。
  - 流程说明：提示词第 1 步要求的不带 `-C` 的 `git rev-parse --show-toplevel` 在本子任务环境无法按字面执行（exec 默认 cwd 为 /home/hatch，非 git 仓）；已改用 workdir=`<home>/workspace/CBrowser_t055` 校验，输出精确等于该路径；全部 git 操作均带 `-C`，落点仓库无误。
  - 本轮自跑实数（验证 venv，`PYTHONPATH=src/backend:tests`）：`test_t055_socket_slot_cleanup.py` 10 passed（含 f002 新测试）；其余 t055 文件 31 passed（robustness 20 + udp_mux 4 + watchers 3 + cdp 4）；先红探针 1 failed 后恢复，sha256 一致。
- 总体判断：f002 已真实消除，仅 1 条新 minor（f003），无 critical / important，10 个 AC 全部复验通过，verdict PASS；minor 须在 progress.md 处置后由下一轮复核。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。A4 实现未变（`_HELPER_LOG_TAIL_BYTES = 2000` 在位，先截断后 redact 再删 helper）；自跑 A4 新测试通过。
- AC-002：TICK-VALID，re_verified。A5 实现未变（`forget_instance_events` 在 `core.py:1713`，三元组过滤）；自跑 A5 新测试通过。
- AC-003：TICK-VALID，re_verified。A6 实现未变（`MEDIA_ATTACH_GATEWAY_MISSING` 在 `core.py:231`，`:456`/`:460` 消费）；自跑 A6 新测试通过。
- AC-004：TICK-VALID，re_verified。A7 实现未变（`recovery_armed` 在位，恢复预设 starting、健康确认后升级）；自跑恢复测试通过。
- AC-005：TICK-VALID，re_verified。A7 宽限实现未变（`recovery_armed` + 90s 锚定恢复时刻）；89s/91s 边界测试自跑通过。
- AC-006：TICK-VALID，re_verified。A8 实现未变（`observed_instance_id: tuple[str, ...]` 在 `core.py:188`，异实例全量上报 `:1913`）；自跑 A8 新测试通过。
- AC-007：TICK-VALID，re_verified。A10 实现未变（读码 `:242-244` 在 `upstream.close()` `:254` 之前）；自跑 4 个 CDP 关码集成测试通过。
- AC-008：TICK-VALID，re_verified。A11 实现未变（`udp_mux_bounds()` 定义在 `udp_mux.py:35`，7 处消费者同源）；自跑 4 个新测试通过。
- AC-009：TICK-VALID，re_verified。f001 守卫仍在位（`socket_root.py:155-161`）；f002 在 CDP/健康查询读路径，不在 slot 清理路径上，不影响本 AC 打勾成立；自跑 10 个 socket slot 测试通过。
- AC-010：TICK-VALID，re_verified。A13 实现未变（`_watch_container_events` 在 `runner.py:274`，`:406` 调用，各关自己的流）；自跑 3 个新测试通过。

coverage = 10/10

reviewed_scope: 408ae12d627ca219

verdict: PASS

## Round 4 (2026-11-12T01:11:23+08:00)

- task：`t055_supervisor_runtime_robustness`
- spec：`docs/tasks/t055_supervisor_runtime_robustness/task.md`
- diff_anchor：`1c0963845705e355ccdd7e1c3963533c9df7437a`
- target：`git -C '<home>/workspace/CBrowser_t055' diff 1c0963845705e355ccdd7e1c3963533c9df7437a`
- round：4
- reviewed_at：2026-11-12T01:11:23+08:00

## Findings

本轮无新发现。

## 结论

- 前轮 finding 复核：t055_code_f003 已消除（独立实跑 + AST 计数器复核，不采信处置表自述）。
  - 拆分属实：fd/路径一致性校验（dev/ino 比对、ISDIR、0o022、uid/gid 四项）抽为 `_validate_slot_dir(fd_stat, path_stat, managed_uid, managed_gid)`（`src/backend/cbrowser/runtime_agent/socket_root.py:186-216`），主函数 `managed_socket_target` 内五处 if 改为 `:242` 一处调用。
  - 圈复杂度独立复核（自写 AST 计数器交叉验证：基数 1 + If/ExceptHandler/For/While/Assert/IfExp 各 +1 + 短路 BoolOp 操作数 −1 + 推导式 if；同一计数器对 `prepare_socket_dir` 得出 CC=12，与 Round 2/3 报告逐字一致，口径已校准）：`managed_socket_target` **17 → 10**，`_validate_slot_dir` **8**，均低于 15 的 minor 阈值；`prepare_socket_dir` 仍为 12。另以基线版文件复核：t054 提交时 `managed_socket_target` CC=16，f002 修复 +1 分支得 17，与 Round 3 实测一致，数字链完整。
  - 语义逐项比对：抽出的五项校验与基线版内联代码逐字一致——条件、求值顺序（dev/ino → ISDIR → 0o022 → uid → gid）、五条 `SocketRootError` 文本均未变；多项同时失败时首项先报的语义不变；调用点仍在 lstat 守卫之后、sock_stat 检查之前，与重构前同一位置；helper 仅返回 None，不改变任何返回值与异常类型。
  - f002 守卫仍在位（`socket_root.py:207-216`，`os.lstat` 包 try/except FileNotFoundError，回落 yield 值与 open() ENOENT/ENOTDIR 路径逐字相同）；先红验证：临时去掉 guard 后 f002 竞态测试变红（1 failed），恢复后 sha256 与探针前字节一致（`a5ca0a4f…`，与修复方 handoff 所称一致）。
  - f001 守卫仍在位（`socket_root.py:155-161`，`entry.stat()` 包 try/except FileNotFoundError）。
  - 本轮改动面经 mtime 核实：自 Round 3 审阅（00:33 CST）以来仅 `socket_root.py`（01:10）、`progress.md`/`task.md`（01:07，AC 重打勾与处置表记账）与两份 review 报告本身被改动，无其他生产/测试文件变化；`socket_root.py` 相对基线的全量 diff 仅含 A12 实现、f001/f002 守卫与本次抽取四项，无计划外改动。
- 本轮新发现：0 条。
- 未进表的提示：
  - 文件规模：`socket_root.py` 256 行（低于 400）；`test_t055_supervisor_runtime_robustness.py` 888 行（超 600 行测试阈值，按降级规则只作结论提示，不进表；自 Round 2 起未变）。
  - 圈复杂度：`prepare_socket_dir` CC=12、`_validate_slot_dir` CC=8，均低于 15；`_converge_session` 37、`_reconcile_profile` 61 为既有巨函数，本轮未再增分支，沿用 Round 1 的结论提示处理，不重立 finding。
  - 锁定项核查通过：`com.cbrowser.deployment-id` 在 `src/`、`scripts/`、`compose.yaml`、`config/`、`tests/` 全树零命中；默认前缀 `cbrowser-t005` 完好（`docker_adapter.py:254`）。
  - AC-001 措辞（Round 1 结论段遗留，未变）：超时分支不抓 helper 日志属有意边界，已记入 progress.md 实施笔记，不改契约、不进 finding。
  - 流程说明：提示词第 1 步要求的不带 `-C` 的 `git rev-parse --show-toplevel` 在本子任务环境无法按字面执行（exec 默认 cwd 为 /home/hatch，非 git 仓）；已改用 workdir=`<home>/workspace/CBrowser_t055` 校验，输出精确等于该路径；全部 git 操作均带 `-C`，落点仓库无误。指纹 `b05debcb03a5c46c` 已用 `repo_task.monitoring.review_scope_fingerprint` 直接重算验证，与提示词所印值一致。
  - 本轮自跑实数（验证 venv，`PYTHONPATH=src/backend:tests`）：t055 新测试 5 文件共 **41 passed**（socket slot 10 + robustness 20 + udp_mux 4 + watchers 3 + cdp 4）；f002 先红探针 1 failed 后恢复，sha256 一致。未改任何实现、未提交、未合入、未 push；探针备份已删。
- 总体判断：f003 已真实消除，本轮 0 新发现，无 critical / important，10 个 AC 全部复验通过，verdict PASS；Round 4 仍为复审轮，finalize 由 chain runner 按门禁脚本判定。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。A4 实现未变（`_HELPER_LOG_TAIL_BYTES = 2000` 在位，`_install_network_policy` 在 `docker_adapter.py:400`）；自跑 A4 新测试通过。
- AC-002：TICK-VALID，re_verified。A5 实现未变（`forget_instance_events` 在 `core.py:1713`）；自跑 A5 新测试通过。
- AC-003：TICK-VALID，re_verified。A6 实现未变（`MEDIA_ATTACH_GATEWAY_MISSING` 在 `core.py:231`，`:456`/`:460`/`:550` 消费）；自跑 A6 新测试通过。
- AC-004：TICK-VALID，re_verified。A7 实现未变（`recovery_armed` 在 `core.py` 4 处，恢复预设 starting、健康确认后升级）；自跑恢复测试通过。
- AC-005：TICK-VALID，re_verified。A7 宽限实现未变（`recovery_armed` + 90s 锚定恢复时刻）；89s/91s 边界测试自跑通过。
- AC-006：TICK-VALID，re_verified。A8 实现未变（`observed_instance_id: tuple[str, ...]` 在 `core.py:188`，异实例全量上报 `:1913`）；自跑 A8 新测试通过。
- AC-007：TICK-VALID，re_verified。A10 实现未变（读码 `automation_router.py:242-244` 在 `upstream.close()` `:254` 之前）；自跑 4 个 CDP 关码集成测试通过。
- AC-008：TICK-VALID，re_verified。A11 实现未变（`udp_mux_bounds()` 定义在 `src/backend/cbrowser/udp_mux.py:35`，7 处消费者同源）；自跑 4 个新测试通过。
- AC-009：TICK-VALID，re_verified。f001/f002 守卫均在位（`socket_root.py:155-161` / `:207-216`）；f003 抽取未改 slot 清理语义；自跑 10 个 socket slot 测试通过。
- AC-010：TICK-VALID，re_verified。A13 实现未变（`_watch_container_events` 在 `runner.py:274`，`:406` 调用，各关自己的流）；自跑 3 个新测试通过。

coverage = 10/10

reviewed_scope: b05debcb03a5c46c

verdict: PASS

## Round 5 (2026-11-12T01:41:44+08:00)

- task：`t055_supervisor_runtime_robustness`
- spec：`docs/tasks/t055_supervisor_runtime_robustness/task.md`
- diff_anchor：`1c0963845705e355ccdd7e1c3963533c9df7437a`
- target：`git -C '<home>/workspace/CBrowser_t055' diff 1c0963845705e355ccdd7e1c3963533c9df7437a`
- round：5
- reviewed_at：2026-11-12T01:41:44+08:00

## Findings

本轮无新发现。

## 结论

- 前轮 finding 复核：t055_test_f005 已消除（独立实跑 + 先红验证，不采信处置表自述）。
  - 3 例新测试全部通过：`test_t055_socket_slot_cleanup.py` 自跑 **13 passed**（10 既有 + 3 新增），验证 venv（`PYTHONPATH=src/backend:tests`）。
  - 先红验证：临时中性化 `_validate_slot_dir` 的 gid 检查后，`test_validate_slot_dir_rejects_group_mismatch` 变红（1 failed，另外 2 例仍绿）；还原后 sha256 与修复前字节一致（`a5ca0a4f…`，与修复方 handoff 所称一致）。测试非空转，gid 检查是承重逻辑。
  - 伪造 `stat_result` 忠实：`_slot_stat` 只提供 `_validate_slot_dir` 实际读取的 5 个字段（`st_dev` / `st_ino` / `st_mode` / `st_uid` / `st_gid`），字段名与 `os.stat_result` 一致；默认 mode `0o40755` 经实测为目录（`S_ISDIR` 为真）且 `mode & 0o022 == 0`，happy-path 前置条件成立；gid 测试两处 stat 除 gid 外完全相同（dev/ino/mode/uid 均匹配），只隔离 gid 分支；`match="group"` 与报错文本 `"Socket slot directory group mismatch"` 逐字对应。
  - ISDIR 分支未补测试正确：`managed_socket_target` 以 `os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW` 打开目录（`socket_root.py:227`），非目录时 open 即报 ENOTDIR 走回落；`fd_stat` 取自该 fd 的 fstat，恒为目录，故 `_validate_slot_dir` 内的 ISDIR raise 经公开路径不可达，不构成缺口。
  - docstring 约定一致：3 例新测试 docstring 均只标 A12（"socket_root read path, not the AC-009 slot-cleanup path"），未编 AC 号，与 f002 测试约定一致，未重蹈 t055_test_f001 的编号错位。
  - 未改生产代码：本轮改动面经 `git status` 与 diff 核实仅涉 `test_t055_socket_slot_cleanup.py`（+3 例测试）与 progress.md 记账；`socket_root.py` 相对基线的全量 diff 与 Round 4 核实的内容一致（A12 实现、f001/f002 守卫、f003 抽取），无计划外改动。
- 前轮 finding 仍消除（抽查）：f001 的 `entry.stat()` 守卫（`socket_root.py:155-161`）、f002 的 `os.lstat` 守卫（`:207-216`，回落 yield 值与 open() ENOENT/ENOTDIR 路径逐字相同）与 f003 的 `_validate_slot_dir` 抽取（`:186-216`，调用点 `:242`）均在位；A4–A8、A10–A13 的实现标记均在位（见 AC 复验方式）。
- 本轮新发现：0 条。
- 未进表的提示：
  - 文件规模：`socket_root.py` 256 行（低于 400）；`test_t055_supervisor_runtime_robustness.py` 888 行（超 600 行测试阈值，按降级规则只作结论提示，不进表；自 Round 2 起未变，本轮未再增行）。
  - 圈复杂度：本轮为纯测试改动，未增任何生产分支；`managed_socket_target` CC=10、`_validate_slot_dir` CC=8（Round 4 已复核），`_converge_session` 37、`_reconcile_profile` 61 为既有巨函数，本轮未动，沿用 Round 1 的结论提示处理。
  - 锁定项核查通过：`com.cbrowser.deployment-id` 在 `src/`、`scripts/`、`compose.yaml`、`config/`、`tests/` 全树零命中；默认前缀 `cbrowser-t005` 完好（`docker_adapter.py:254`）。
  - AC-001 措辞（Round 1 结论段遗留，未变）：超时分支不抓 helper 日志属有意边界，已记入 progress.md 实施笔记，不改契约、不进 finding。
  - 流程说明：提示词第 1 步要求的不带 `-C` 的 `git rev-parse --show-toplevel` 在本子任务环境无法按字面执行（exec 默认 cwd 为 /home/hatch，非 git 仓）；已改用 workdir=`<home>/workspace/CBrowser_t055` 校验，输出精确等于该路径；全部 git 操作均带 `-C`，落点仓库无误（与 Round 3 审阅记录的同一环境情形）。
  - 本轮自跑实数（验证 venv，`PYTHONPATH=src/backend:tests`）：socket slot 文件 **13 passed**；其余 t055 文件共 **31 passed**（robustness 20 + udp_mux 4 + watchers 3 + cdp 4）；gid 先红探针 1 failed 后恢复，sha256 一致。未改任何实现、未提交、未合入、未 push；探针临时文件已删。
- 总体判断：f005 已真实消除，本轮 0 新发现，无 critical / important，10 个 AC 全部复验通过，verdict PASS；本轮为最后一轮（max_review_round=5），finalize 由 chain runner 按门禁脚本判定。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。A4 标记在位（`docker_adapter.py:127` 的 `_HELPER_LOG_TAIL_BYTES = 2000`、`:141` 取尾切片）；robustness 文件自跑绿（含 A4 测试）。
- AC-002：TICK-VALID，re_verified。A5 标记在位（`forget_instance_events` 在 `core.py:1713`）；robustness 文件自跑绿（含 A5 测试）。
- AC-003：TICK-VALID，re_verified。A6 标记在位（`MEDIA_ATTACH_GATEWAY_MISSING` 在 `core.py:231`，消费点 `:456`）；robustness 文件自跑绿（含 A6 测试）。
- AC-004：TICK-VALID，re_verified。A7 标记在位（`recovery_armed` 在 `core.py` 4 处）；robustness 文件自跑绿（含恢复测试）。
- AC-005：TICK-VALID，re_verified。A7 宽限标记在位；89s/91s 边界测试在 robustness 文件内自跑绿。
- AC-006：TICK-VALID，re_verified。A8 标记在位（`observed_instance_id: tuple[str, ...]` 在 `core.py:188`）；robustness 文件自跑绿（含 A8 测试）。
- AC-007：TICK-VALID，re_verified。A10 标记在位（读码 `automation_router.py:243` 在 `upstream.close()` `:254` 之前）；4 个 CDP 关码集成测试自跑绿。
- AC-008：TICK-VALID，re_verified。A11 标记在位（`udp_mux_bounds()` 在 `udp_mux.py:35`）；4 个 udp_mux 测试自跑绿。
- AC-009：TICK-VALID，re_verified。f001/f002 守卫均在位（`socket_root.py:155-161` / `:207-216`）；socket slot 文件 13 passed（含 f005 新测试与 f002 竞态测试）。
- AC-010：TICK-VALID，re_verified。A13 标记在位（`_watch_container_events` 在 `runner.py:274`，`:406` 调用）；3 个 watcher 测试自跑绿。

coverage = 10/10

reviewed_scope: 5aa4d0669a575f9b

verdict: PASS

# Task review t003（reviewer_focus: 代码）

- task：`t003_v2_browser_runtime`
- spec：`docs/tasks/t003_v2_browser_runtime/task.md`
- diff_anchor：`226c8453097fb982835ccb254cea8a3f26d131b3`
- target：`git -C '/Users/karson/kar/code/CBrowser_t003' diff 226c8453097fb982835ccb254cea8a3f26d131b3`
- round：Round 1
- reviewed_at：2026-10-28T17:15:00+08:00

## Round 1

reviewed_scope: e750897e76c5a667

## Findings

无（Round 1 零 finding）

## 结论

- 本轮新发现：0 条
- 未进表的提示：
  - 文件过大标准：
    - `src/backend/cbrowser/runtime_agent/agent.py`：479 行（≥ 400 行 minor 阈值，未超 800 行；职责为 UDS API、CDP proxy 转发与端点控制，无重复逻辑或状态分叉）
    - `src/backend/cbrowser/runtime_agent/runner.py`：750 行（≥ 400 行 minor 阈值，未超 800 行；职责为 display/audio 初始化、SDK context 启动、Chrome wrapper 与退出观测，无重复逻辑或状态分叉）
  - 圈复杂度（CC ≥ 10）提示：
    - `src/backend/cbrowser/runtime_agent/runner.py:start`（CC ≈ 10）：包含环境准备、参数组装与发现重试逻辑，建议后续拆分发现等待子函数
    - `src/backend/cbrowser/runtime_agent/runner.py:_wait_for_chrome_exit`（CC ≈ 12）：包含进程存活判断、重试与 driver loss 区分判定，建议后续精简分支
    - `src/backend/cbrowser/runtime_agent/event_storage.py:get_instance_state`（CC ≈ 11）：包含身份比对、终态事件恢复与一致性校验，分支清晰
    - `src/backend/cbrowser/runtime_agent/profile_defaults.py:initialize_profile_defaults`（CC ≈ 12）：线性步骤检查与 UI 操作重试，无嵌套分叉风险
- AC 复验方式：
  - AC-001：`re_verified`（查证 `runner.py` 与 `entrypoint.sh` 对 `PROFILE_ID` 严格校验防跨目录，`user_data_dir` 挂载及 `atomic_write_json` 落盘；`verify.sh` 重跑通过 80 个测试，包含 `test_runtime_persistence_guards.py` 与 `test_runtime_instance_storage.py`）
  - AC-002：`re_verified`（查证 `subsystems.py` 中 `check_display`、`check_audio` 48000Hz null sink 校验、`check_browser` CDP 探测与 `agent.py` `/health` 全就绪逻辑；`verify.sh` 重跑通过 `test_runtime_agent_faults.py`）
  - AC-003：`re_verified`（查证 `agent.py` 仅开放受控 Unix Domain Socket，`security.py` 白名单过滤拒绝危险参数与任意文件/shell 访问；`verify.sh` 重跑通过 `test_runtime_protocol.py` 与 `test_runtime_agent.py`，验证 schemas 契约与 400 拒绝）
  - AC-004：`re_verified`（查证 `cdp_proxy.py` 通过 `Browser.setDownloadBehavior` 捕获下载并持久化 `DownloadEventRecord`，外部客户端断开在 `agent.py` 退出 handler 自动调用 `rearm_download_capture()`；`verify.sh` 重跑单测通过）
  - AC-005：`re_verified`（查证 `runner.py` 中 `chrome_wrapper.sh` 捕获真实 PID 与退出码，`_wait_for_chrome_exit` 区分 normal/abnormal 及 driver loss，原子写入 `RuntimeEventRecord` 与 `RuntimeStateRecord`，supervisord 设置 `autorestart: false` 阻止自动重启；`verify.sh` 重跑通过 `test_runtime_instance_storage.py`）
  - AC-006：`re_verified`（查证 `Dockerfile` 创建并使用非 root 用户 `cbrowser` (uid 1000)，`entrypoint.sh` 运行于非 root，Xvfb 带 `-auth` 且 `-nolisten tcp`，PulseAudio 使用专用 socket 与 256 字节 cookie；`verify.sh` 重跑单测通过）
  - coverage = 6 / 6 (100%)
- 总体判断：六项行为 AC 真实完整落地，边界安全、持久化与生命周期契约符合 spec 及蓝图，无 blocking 缺陷。
- 系统性 follow-up：无

verdict: PASS

## Round 2 (2026-10-28T17:35:00+08:00)

reviewed_scope: e934e9a6bcba7ff4

### 前轮纠偏与复核说明

1. **测试执行边界界定**：
   - Reviewer 本机通过 `verify.sh` 独立重跑通过 80 项测试（71 unit + 9 real HTTP integration，耗时 39.19s，日志见 `.scratch/t003_review_round1/code/verification.log`）。
   - 13 项真实 Docker E2E 测试（8 项核心用例包含真实 PID/SIGKILL 137/driver loss 观测，5 项 Google 默认引擎用例）为 Root 物理执行记录（见 `.scratch/t003_root_checks/project_blackbox_03_final.log`，耗时 164.31s，13 passed）。Reviewer 通过查验代码断言与物理日志复核，不虚标独立运行 Docker 容器。
   - 本 task 涉及测试文件共 9 个：6 个新增单元测试（`test_runtime_agent.py`, `test_runtime_agent_faults.py`, `test_runtime_instance_storage.py`, `test_runtime_persistence_guards.py`, `test_runtime_profile_defaults.py`, `test_runtime_protocol.py`）、2 个新增 E2E 测试（`test_browser_runtime_e2e.py`, `test_runtime_profile_defaults_e2e.py`）及 1 个 C 语言探针源码（`test_mitshm.c`）；既有旧测试未作修改。
2. **测试语义与安全边界纠偏**：
   - `test_runtime_profile_defaults_e2e.py` 中存在若缺少 `CBROWSER_RUNTIME_TEST_IMAGE` 或 `CBROWSER_RUNTIME_ENGINE_CACHE` 则跳过的前置检查；在注入完整项目环境变量的正式黑盒运行中，13 项 E2E 全部 PASS，无 skip。
   - `event_storage` 单元测试通过 mock/inject 模拟操作系统底层 I/O 错误（EIO/ENOSPC/EINVAL），验证异常状态一致性与 directory fsync 失败处理，非物理断电实验。
   - PulseAudio 错误凭据拒绝针对不同 UID（如 UID 1001），同 UID 1000 进程可能绕过 cookie 校验（d011 契约事实），跨 Profile 隔离主要依赖容器独立的运行卷挂载与 IPC 命名空间，而非单靠 cookie。
   - E2E 异步观测包含固定 `asyncio.sleep` 与有界轮询，断言基于最终真实行为。
   - 协议模式测试验证 JSON 结构与字段定义，不构成深度模型双向等价推导。
   - 排除范围确认：实际许可的 Pro 引擎运行、公网测试、原生 Linux x86 执行及性能压测属于 USER_WAIVED / NOT_RUN，不在本 task 声明通过范围。独立正式黑盒 Round 2 正在另行执行中。

### 七视角代码审查

1. **规格合规 (Spec Compliance / AC Coverage)**：
   - AC-001：`runner.py:343-348`, `event_storage.py:150-164`, `entrypoint.sh:48-54` 实现严格 `PROFILE_ID` 校验与按 Profile 隔离的存储路径；跨容器用户数据与持久化事件独立存储。
   - AC-002：`subsystems.py:15-153` 实现 `check_display`（`xdpyinfo` 探针）、`check_audio`（`pactl` 48000Hz null sink 校验）、`check_browser`（CDP HTTP 探测）；`agent.py:98-182` `/health` 端点在任一子系统异常时置 ready=false 并返回降级/错误状态；`runner.py:519-550` 使用 `xdotool` 调整顶层窗口尺寸与位置，设置 DPR=1。
   - AC-003：`agent.py:208-256` 受控 UDS 仅暴露 `/health`、`/config_version`、`/control`、`/events/*`、`/cdp`，未知 action 返回 400；`security.py:41-84` 过滤非安全参数与危险执行前缀，禁止暴露 CDP TCP 与任意文件/shell 接口。
   - AC-004：`cdp_proxy.py:98-116, 157-227` 通过 `Browser.setDownloadBehavior` 捕获下载并记录不可变事件；`agent.py:321-332` 在外部 WebSocket 客户端断开后自动触发 `rearm_download_capture()`。
   - AC-005：`runner.py:350-369, 551-642` 通过 `chrome_wrapper.sh` 捕获真实 PID 与退出码，区分正常退出、异常退出与 driver loss（`process_observation_lost`）；supervisord（`entrypoint.sh:100-110`）配置 `browser_runner` 为 `autorestart: false`，不自动重启。
   - AC-006：`Dockerfile:56-58, 98` 使用非 root 用户 `cbrowser` (UID/GID 1000)；`runner.py:160-250` Xvfb 配置 `-auth` 且 `-nolisten tcp`；PulseAudio 监听隔离子目录 `/run/cbrowser/runtime/pulse`。
2. **实现正确性 (Correctness)**：
   - `runner.py:591-602`：`_sdk_driver_alive()` 检查 Playwright Node driver `/proc/{pid}/stat` 进程状态，当 driver 消失或 Xvfb 异常退出导致 Chrome 0 退出时，正确标记为 `process_observation_lost`，state 为 `error`，exit_code 为 `None`，避免误清除运行意愿（d016 契约）。
   - `event_storage.py:52-78`：`atomic_write_json` 采用 `tmp_path` 写入 + `fsync` + `os.replace` + 父目录 `_sync_directory`，保证 POSIX 元数据落盘原子性。
   - `cdp_proxy.py:204-212`：下载完成捕获前使用 `path.is_relative_to(default_download_dir)` 与 `is_file()` 校验目标路径，防范越界与虚假完成。
3. **安全审视 (Security)**：
   - 输入校验：`security.py:41-49` `validate_runtime_id` 过滤非法字符与相对路径 `.`/`..`；`security.py:52-84` 强制剔除 `--remote-debugging-*` 等保留前缀及 `--renderer-cmd-prefix`、`--no-sandbox` 等危险选项，且阻断 `--disable-features=isolateorigins`。
   - 凭证与隐私：`runner.py:748-750` 在捕获异常时仅记录异常类型名，不回显 launch_args 或 proxy 认证信息。
   - 权限控制：`agent.py:423-432` 启动 UDS 监听时使用 umask 077，套接字权限设为 0660，父目录设为 0750，防范未授权本地访问。
4. **契约·类型·Breaking (Contract & Breaking)**：
   - 接口契约：`protocol.py` 中 Pydantic 模型严格设置 `extra="forbid"`，与 `schemas/runtime/agent_protocol.json` 规范定义完全吻合。
   - 模块无破坏性影响：新增独立 `cbrowser.runtime_agent` 模块，消费 t002 配置快照，未修改已有数据库或 API 路由契约。
5. **性能与资源 (Performance & Resource)**：
   - 异步任务治理：`agent.py:293-315` 双向 CDP 隧道采用 `asyncio.wait(..., return_when=FIRST_COMPLETED)`，并在 finally 中对挂起任务进行显式取消与回收，避免协程泄漏。
   - 进程资源回收：`runner.py:654-683` `stop()` 显式超时终止 Openbox 与 Xvfb 子进程，避免孤儿进程残留。
   - 同步 I/O 说明：`atomic_write_json` 中的 `fsync` 为单实例短周期本地磁盘同步，无异步跨协程抢占风险。
6. **架构与可维护性 (Architecture & Maintainability)**：
   - Agent 与 Runner 进程分离，由 supervisord 独立监督管理，职责明确；事件存储与子系统探针独立成模块（`event_storage.py`, `subsystems.py`），模块耦合度低。
   - 代码风格严谨，无无用导入与注释死代码。
7. **健壮性与可观测 (Robustness & Observability)**：
   - 日志完备：Agent、Runner、CDP proxy 均具备关键生命周期事件及异常日志。
   - 容错与恢复：`event_storage.py:180-235` 优先使用实例独立 state.json，若缺失则由持久化事件日志恢复终态事实，双重保障崩溃恢复。

## Findings

无（Round 2 零 finding）

## 结论

- 前轮 finding 复核：Round 1 零 finding，无遗留问题；本轮前轮复核结论维持一致。
- 本轮新发现：0 条
- 未进表的提示：
  - 文件过大标准：
    - `src/backend/cbrowser/runtime_agent/agent.py`：479 行（≥ 400 行 minor 阈值，未超 800 行；职责为 UDS 路由、CDP 隧道与生命周期状态组装，未见拆分必要性硬缺陷）
    - `src/backend/cbrowser/runtime_agent/runner.py`：750 行（≥ 400 行 minor 阈值，未超 800 行；职责为显示/音频环境装配、SDK persistent context 托管与退出观测，分支虽多但结构清晰）
  - 圈复杂度（CC ≥ 10）提示：
    - `src/backend/cbrowser/runtime_agent/runner.py:start`（CC ≈ 10）：包含启动时序与重试轮询，建议后续拆解子方法
    - `src/backend/cbrowser/runtime_agent/runner.py:_wait_for_chrome_exit`（CC ≈ 12）：包含退出状态捕获及 driver 丢失判定逻辑
    - `src/backend/cbrowser/runtime_agent/event_storage.py:get_instance_state`（CC ≈ 11）：包含状态恢复与事件一致性校验分支
    - `src/backend/cbrowser/runtime_agent/profile_defaults.py:initialize_profile_defaults`（CC ≈ 12）：线性 UI 配置交互
- AC 复验方式：
  - AC-001：`re_verified`（代码实现与安全校验查验 + Reviewer 80 项单元/集成重跑 PASS；跨容器数据持久化及 Profile 隔离真实表现依据 Root 13 项 Docker E2E 执行记录 `test_ac001_persistence_and_profile_isolation`）
  - AC-002：`re_verified`（代码实现查验 + Reviewer 重跑 `test_runtime_agent_faults.py` 验证子系统失败处理；真实 UI 尺寸及 48000Hz 音频依据 Root Docker E2E 记录 `test_ac002_health_readiness_and_subsystems`）
  - AC-003：`re_verified`（代码实现查验 + Reviewer 重跑 `test_runtime_protocol.py` 与 `test_runtime_agent.py` 验证 UDS 端点契约与 400 校验；CDP loopback 隔离依据 Root Docker E2E 记录 `test_ac003_uds_endpoints_and_security`）
  - AC-004：`re_verified`（代码实现查验 + Reviewer 重跑 CDP 事件解析测试；真实 HTTP 下载及断开后重武装依据 Root Docker E2E 记录 `test_ac004_real_download_and_rearm`）
  - AC-005：`re_verified`（代码实现查验 + Reviewer 重跑 `test_runtime_instance_storage.py` 与 `test_runtime_persistence_guards.py`；真实 wrapper 退出状态与 driver loss 映射依据 Root Docker E2E 记录 `test_ac005_lifecycle_exit_and_agent_restart`）
  - AC-006：`re_verified`（代码实现查验 + Dockerfile 非 root 配置查验；只读文件系统、X11/PulseAudio 权限隔离依据 Root Docker E2E 记录 `test_ac006_security_readiness_and_isolation`）
  - coverage = 6 / 6 (100%)
- 总体判断：文档修正准确反映了 Pulse 隔离子目录及目录树细节，实现层与测试层保持稳定，七个代码维度均符合规范与安全要求，无 blocking 缺陷。
- 系统性 follow-up：无

### Round 2 证据勘误 (Evidence Errata)

- **单元用例计数归正**：本 task 6 个新增 runtime 单元测试文件实际收集 52 项测试用例（详见 `.scratch/t003_review_round2/runtime_collection.log`），加上 t002 既有 19 项单元测试，项目单元测试总计 71 项；结合 9 项 HTTP 集成测试，Reviewer 独立重跑通过用例总数为 80 项。前文表述将 71 统称为本 task 新增单测属笔误，特此归正。
- **Root Docker E2E 函数名精确对齐**：前文引用的 Docker E2E 函数名存在行文笔误，其实际对应 `tests/e2e/test_browser_runtime_e2e.py` 中的精确函数名（`test_ac001_persistence_and_dual_profile_isolation`, `test_ac002_subsystem_readiness_and_geometry`, `test_ac003_controlled_uds_and_allowlist`, `test_ac004_download_capture_and_recovery`, `test_ac005_process_lifecycle_agent_restart_and_exit_events`, `test_ac005_abnormal_termination_lifecycle_and_agent_replay`, `test_ac006_minimal_privileges_and_access_control`）。物理执行日志 13 项 PASS（8 core + 5 Google）及实际断言事实成立，协议实现模块确为 `src/backend/cbrowser/runtime_agent/protocol.py`。
- **WAIVED 与 NOT_RUN 边界精确界定**：仅公网验证与原生 Linux x86_64 执行按用户决定属于 `USER_WAIVED`；真实商业许可的 Pro 引擎运行为 `NOT_RUN`；后续 t009/t012 要求的容量/P95/8小时/1000次输入稳定性指标在当前 task 阶段记为 `NOT_RUN` 且后续必须严格验收，禁止将性能压测指标泛化为 waived。
- **Schema 校验深度事实核定**：`test_runtime_protocol.py` 中的 schema 验证仅执行了 JSON 语法解析及顶层定义名称与字段静态比对，并未进行深度导出的 JSONSchema 与 Pydantic 模型全字段双向等价推导；代码审查在此确认静态字段与约束一致，不虚构深度模型等价验证。
- **时间戳元数据校正**：前文报告记录时间戳存在笔误，依 `root_review_facts.json` 真实记录时间基准归正为 `2026-10-28T17:26:37+08:00`，历史节头保留，以本勘误为准。

reviewed_scope: e934e9a6bcba7ff4

verdict: PASS

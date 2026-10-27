# CBrowser v2 Recovery 原型黑盒重跑与架构审查报告

## 1. 黑盒重跑执行证据 (Exit Code & Status)

- **命令**: `uv run --no-project python test_orchestration.py 2>&1 | tee blackbox.log`
- **执行时间**: 29.3 秒 | **退出码**: 0 (所有断言全部 PASS)
- **子进程与容器证据**:
    - API 独立进程: 端口 `127.0.0.1:58083`，PID 隔离，两阶段真实终止与重启（Step 5 杀，Step 9 重启）。
    - Supervisor 独立进程: 两阶段正常运行与 SIGKILL 注入（Step 8a 退出码 `-9`，Step 8c 成功重启）。
    - Docker 容器: `cbrowser-spike-recovery-runtime-prof_rec_1`，显式 `--restart=no`，测试收尾时无残留容器。
    - CloakBrowser CDP: UDS 接收 `close_browser`，经回环 WebSocket 调用 CDP `Browser.close` 退出，真实进程返回码 `0`。

## 2. 核心机制逐项核实结论

1. **真实子进程重启与状态收敛**:
    - Step 5 终止 API 后浏览器正常退出；Step 8 强杀 Supervisor 并重启，Step 9 重启 API 后本地队列自动排空上报。
    - API 正确将 `desired_state` 从 `running` 收敛为 `stopped`，`observed_state` 为 `stopped`。
2. **挂载物理隔离 (Negative Proof)**:
    - `docker inspect` 证实容器仅挂载 `runtime -> /app_run` 与匿名 volume，无 `api_storage`。
    - 容器内执行 `ls /app_run/cbrowser.db` 返回非零状态码（No such file），SQLite 严格隔绝于沙箱外。
3. **队列原子持久化**:
    - `container_agent.py` (L159-165) 与 `roles.py` (L207-213, L272-278) 均采用 `tmp + flush + fsync + os.replace`，彻底替代原 `open('w')` 截断漏洞。
4. **SIGKILL 注入时点精确界定**:
    - 注入位点: `roles.py` L238-240 (`drain_events_to_api`)。
    - 具体时点: 在 `events.jsonl` 已持久化合并入 `supervisor_queue.jsonl` 且已 `os.remove(events.jsonl)` 之后、向 API 发送 HTTP 请求之前。
    - 结论: 证实“本地队列落盘后、API 发送前 Supervisor 进程崩溃可恢复”；**禁止混称为断电安全**（未测试原子重命名中途断电或容器内写未 fsync 断电）。
5. **事件去重与陈旧事件隔离**:
    - 重放已消费事件 `evt_exit_...`: API 查 `processed_events` 表拒绝，返回 `duplicate_ignored`。
    - 注入旧实例 `inst_live_001` 迟到事件: API 对比当前 `inst_new_002` 拒绝，返回 `stale_instance_rejected`。
6. **真实新实例存活与防误自启**:
    - 调度新实例 `inst_new_002` 后，Supervisor 拉起真实新 Docker 容器，UDS ping 响应证实版本匹配且持续健康运行。
    - `desired=stopped` 期间经历 5 轮 reconciliation，容器未发生任何幽灵重启。

## 3. 代码审查缺陷清单 (含精确行号)

1. **队列排空后未删除空文件导致测试空转等待 15s**:
    - 位点: `roles.py` L271-278 & `test_orchestration.py` L236-238。
    - 原因: 队列全部上报完毕后，L273 往 `supervisor_queue.jsonl` 写入 0 字节而非 `os.remove`；导致测试端 `if not os.path.exists(sup_queue_file)` 无法提前 break，白等 30 轮（15 秒）超时退出。
2. **新实例运行状态未同步致 observed_state 悬空**:
    - 位点: `roles.py` L69-75 vs L130。
    - 原因: `/api/set-desired-state` 仅更新 `desired_state` 与 `runtime_instance_id`，未更新 `observed_state`；Supervisor 无主动心跳上报运行态。在 Step 13b 新容器实际 running 时，DB 内 `observed_state` 仍为陈旧的 `'stopped'`。
3. **异常退出缺乏崩溃循环熔断 (Crash-loop Backoff)**:
    - 位点: `roles.py` L124-130 & L324-337。
    - 原因: 当 `exit_code != 0` 时，`desired_state` 保持 `running`。Supervisor 的 reconcile 循环每秒检查，若无退避与重试上限将引发持续快速拉起与崩溃。
4. **跨进程文件操作缺少文件锁 (Lockless File Contention)**:
    - 位点: `container_agent.py` L150-165 与 `roles.py` L222-235。
    - 原因: Agent 读取 `events.jsonl` 并通过原子替换追加时，与 Supervisor 读取并 `os.remove` 存在并发窗口，虽单次替换原子，但缺乏 `fcntl.flock` 保护多事件并发场景。

## 4. 产品链路定位说明

- 本实验严格验证了“单写者 SQLite + 宿主持久队列 + 实例生命周期版本隔离 + CDP 优雅关闭”在故障场景下的状态机闭环。
- **本原型明确不是正式生产链路**：当前采用简易 `http.server` + Python 原生 `sqlite3` + `docker` CLI 命令，正式产品将迁移至 FastAPI + SQLAlchemy 2.0 ORM + Docker Engine API / 流式 RPC 架构。

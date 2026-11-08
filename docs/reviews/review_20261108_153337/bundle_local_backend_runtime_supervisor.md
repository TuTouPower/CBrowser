# bundle_local_backend_runtime_supervisor

## responsibilities

- 作为系统内唯一 Docker Socket 持有者，负责 Profile 容器沙箱（Browser/Stream）的全生命周期管理
- 维护 ActiveSession 会话管理、多容器对账收敛循环（Convergence Loop）与 Docker 事件监听
- 实现 Linux iptables 双协议栈网络隔离策略（阻断 RFC1918/CGNAT/ULA，放行指定白名单与宿主连接）
- 管理固定端点媒体子网与 UDP Mux 端口池（30000–30991）分配与回收
- 协调异常退避重启（2s/10s/30s 指数退避，第 4 次失败标记 blocked 阻断）与状态自愈
- 在容器内提供常驻 UDS 守护代理（runtime_agent），对接 Chrome CDP 环回连接与弹窗监听托管（DialogAttendant）
- 提供宿主 CLI（cbrowser-agent）与 Agent 执行器（agent_executor），维护 CDP 隧道与动作分发
- 提供敏感凭据 0600 权限检查（secret_files.py）与跨模块异常体系

## interfaces

- REST /supervisor/v1/profiles/\* start, stop, status 控制面端点
- REST /supervisor/v1/reconcile, /readiness 调度与就绪探针
- WS /supervisor/v1/profiles/{id}/cdp 自动化 WebSocket 隧道
- UDS /run/cbrowser/runtime/{id}/agent.sock 容器内部守护代理接口
- CLI cbrowser-agent 宿主机外部自动化执行器

## dependencies

- docker (Python SDK)
- FastAPI / Uvicorn
- websockets
- iptables / ip6tables (via helper container)
- httpx
- ipaddress

## flows

- 容器启动流：start_profile -> 校验意愿 -> 创建媒体网络并附着网关 -> 启动 Browser 容器并等待就绪 -> 启动 Stream 容器并校验注册 -> 建立 ActiveSession
- 容器停止流：stop_profile -> 记录操作账本 -> 断开 Viewer -> teardown_profile -> 释放端口 -> 清理会话 -> 上报 stopped
- CDP 隧道流：客户端 WS -> Supervisor 验证 Bearer Token -> 寻找 agent.sock -> unix_connect 连接内部 Agent -> 双向泵送

## constraints

- 唯一 Docker Socket 持有者，严禁直接触碰 SQLite 数据库
- 清理失败严禁释放仍占用的端口，防止跨沙箱端口串扰
- 容器运行环境强制无特权（UID 1000、read_only 根文件系统、cap_drop ALL、no-new-privileges）

## decisions

- ADR 001: 独立 Docker 双容器沙箱
- ADR 007: Browser 容器提供 shareable IPC，Stream 容器通过 container IPC 挂接
- ADR 008: 2s/10s/30s 三次指数退避自动重试，区分原生退出与合成退出
- ADR 009: 不可变 netns-helper 注入 iptables 规则，业务容器零特权
- ADR 019: 常驻弹窗监听，避免 Chromium 自动关闭未托管弹窗

## evidence

- src/backend/cbrowser/supervisor/core.py:172-237,2114-2520
- src/backend/cbrowser/supervisor/docker_adapter.py:266-310,1135-1473
- src/backend/cbrowser/supervisor/network_policy.py:33-210
- src/backend/cbrowser/supervisor/recovery_coordinator.py:85-239,443-618
- src/backend/cbrowser/runtime_agent/agent.py:770-798
- src/backend/cbrowser/runtime_agent/cdp_proxy.py:152-240

## uncertainties

## Findings

- [Critical][95] src/backend/cbrowser/supervisor/core.py:2491-2503; 1218-1231 — 容器清理失败未阻断端口释放，违反蓝图铁律并引发跨 Profile 端口绑定冲突

    - ID: f_supervisor_teardown_port_leak; verification: static
    - Evidence: core.py:2480-2504 在 teardown_profile 抛出异常被记录到 teardown_error 后，finally 块无视错误执行 self.ports.release(profile_id); 直接违背 docs/blueprint/supervisor.md 第 33 行纲领：'清理失败不释放仍占用的端口'
    - Impact: 当 Docker 守护进程故障或超时导致 Stream 容器未能删除时，宿主 UDP 端口仍被旧容器占用。端口被提前归还后分配给新 Profile，后续 Docker 启动报错 address already in use，或导致 WebRTC 媒体流量发送至陈旧容器产生串扰
    - Fix: 仅当 teardown_error is None 时调用 self.ports.release(profile_id)；清理失败时保留端口映射与 session 故障跟踪状态

- [High][90] src/backend/cbrowser/supervisor/core.py:1598-1606; core.py:1555 — 容器退出状态对账忽略退出码与原生事实，将正常用户退出覆盖为异常崩溃并诱发死循环重启

    - ID: f_supervisor_normal_exit_override; verification: static
    - Evidence: core.py:1598-1606 当 container_status in ('exited', 'dead', 'not_found') 时无条件上报 observed_state='error', reason='container_exit'; 在 consume_disk_events 消费到正常的 Exit 0 原生退出事件后，随即触发 \_reconcile_instance_observation，无条件将其覆盖为 error
    - Impact: 用户主动关闭浏览器被判定为崩溃，触发 RecoveryCoordinator 的 2/10/30s 自动重试机制强行重新拉起容器，导致已正常关闭的 Profile 窗口死循环复活
    - Fix: 在对账确认容器已退出时，先检查是否存在 native exit 事实或检查 Docker ExitCode；若 ExitCode 为 0 上报 observed_state='stopped'

- [High][90] src/backend/cbrowser/supervisor/core.py:696-728; docker_adapter.py:1423-1468 — Stream 局部单容器替换失败时未清理残存容器，导致孤儿容器驻留并耗尽替换预算

    - ID: f_supervisor_replace_stream_leak; verification: static
    - Evidence: docker_adapter.py 中 client.containers.run 启动容器后，若后续 \_install_network_policy 抛出异常，未清理已创建容器; core.py:715-727 捕获异常后记录日志并标记失败，未对残留的 stream 容器执行 cleanup_container_by_name
    - Impact: 启动失败的 Stream 容器处于卡死状态且常驻 Docker 守护进程，持续占用宿主 UDP 端口；3 次替换配额耗尽后成为永久孤儿容器阻断后续同名容器创建
    - Fix: 在 start_stream_container 异常处理中增加对未完成初始化 container 的删除回滚，并在 \_replace_stream_only 失败时兜底清理

- [High][90] src/backend/cbrowser/supervisor/network_policy.py:158,205 — 网络策略对 Stream 角色无条件放行公网出站流量，违背出站最小特权原则

    - ID: f_supervisor_stream_output_accept; verification: static
    - Evidence: network_policy.py:158 在遍历 BLOCKED_IPV4_RANGES 阻断后，无条件追加 lines.append('-A OUTPUT -j ACCEPT'); 与 docs/blueprint/supervisor.md 第 63 行冲突：Stream 仅允许实际 Gateway 地址/端口、本实例 UDP mux、显式白名单与同机直连所需流量
    - Impact: Stream 容器挂载了宿主 X11 与 Pulse 目录，被赋予了主动向公网任意 IP 发起连接的能力。若 WebRTC 或 GStreamer 媒体解析库存在漏洞，攻击者可直接向外部 C2 反弹 Shell
    - Fix: 仅当 spec.role == 'browser' 时才追加默认公网放行；对 stream 角色默认保持 DROP，仅放行网关白名单与 UDP mux 端口

- [High][90] src/backend/cbrowser/supervisor/docker_adapter.py:1868-1887 — Edge 网关容器重建采用非原子删除替换模式，创建异常将导致网关永久离线

    - ID: f_supervisor_caddy_rebuild_no_rollback; verification: static
    - Evidence: docker_adapter.py:1870 先执行 caddy_c.remove(force=True) 删除旧容器，再调用 client.containers.run 创建新容器; 若端口冲突或配置异常导致 run 失败，旧容器已不复存在，且无回滚捕获机制
    - Impact: 网关重建失败将导致整个系统的 HTTPS 入口彻底丢失，无法自动降级或拉起备份，必须人工介入修复
    - Fix: 采用重命名备份模式：先将旧容器重命名，成功启动新容器后再删除；启动失败则恢复重命名并重新拉起旧容器

- [Medium][85] src/backend/cbrowser/supervisor/docker_adapter.py:296-302,676-680 — 底层 HTTP 传输超时异常穿透 Docker 错误处理层，导致 helper 等待超时逃逸

    - ID: f_supervisor_helper_read_timeout; verification: static
    - Evidence: docker_adapter.py 调用 helper.wait(timeout=30) 时仅捕获了 except DockerException; Python docker SDK 中 wait 超时底层抛出的是 requests.exceptions.ReadTimeout（属于 RequestException，不继承 DockerException）
    - Impact: 当 helper 策略注入卡死超时时，未封装的 ReadTimeout 异常向上传播中断流程，破坏异常类型契约且无法被沙箱降级捕获
    - Fix: 在调用 helper.wait(timeout=...) 处同时捕获 DockerException 与 requests.exceptions.RequestException 并转化为 DockerSandboxError

- [Medium][85] src/backend/cbrowser/agent_executor/transport.py:63-96,161-174 — CDP WebSocket 读循环异常退出或主动关闭时未拒绝挂起 Future 造成协程悬挂

    - ID: f_supervisor_transport_pending_futures; verification: static
    - Evidence: transport.py 的 \_read_loop 在发生异常或 close 时仅取消了 \_reader_task，未对 self.\_pending 中的 Futures 做异常置位; 对比 runtime_agent/cdp_proxy.py:227-235 严格遍历 pending_cmd_futures 并设置 set_exception
    - Impact: 外部自动化调用在隧道断开时无法立即感知失败，挂起协程必须等待 30 秒 step_timeout 超时才返回，显著延缓错误反馈
    - Fix: 在 \_read_loop 的 finally 及 close() 中遍历 self.\_pending 将未完成 Future 置为 CdpError('CDP transport disconnected')

- [Medium][85] src/backend/cbrowser/runtime_agent/preview_capture.py:108-139 — 周期截图循环只附加不脱离导致 Chrome CDP 内部 Session 句柄长期累积泄露

    - ID: f_supervisor_preview_session_leak; verification: static
    - Evidence: capture_once 通过 Target.attachToTarget 获取 sessionId 后，获取 metrics 并截图，未调用 Target.detachFromTarget 即返回
    - Impact: 截图循环每 15 秒执行一次，单日产生数千个未释放的 Target Session 结构体，加剧浏览器内存泄漏与 CDP 事件分发负载
    - Fix: 在获取截图后通过 try...finally 确保调用 Target.detachFromTarget 释放 session 资源

- [Medium][80] src/backend/cbrowser/secret_files.py:15-27 — 敏感凭据读取存在检查到使用的时间差漏洞，且未限制正规文件导致 FIFO 悬挂

    - ID: f_supervisor_secret_file_toctou; verification: static
    - Evidence: secret_files.py 先执行 target.stat() 检查权限，随后执行 target.read_text() 重新打开文件; stat() 与 open() 之间存在 TOCTOU 竞争，且对命名管道（FIFO）同样返回 0600 模式，随后的 read_text() 将永久阻塞主线程
    - Impact: 可能遭遇文件替换攻击，或因意外传入命名管道文件导致 Supervisor 启动与主线程无界阻塞 DoS
    - Fix: 使用 os.open 带 O_NOFOLLOW|O_CLOEXEC 获取文件描述符，对 fd 执行 fstat 校验 S_ISREG 正规文件与权限后直接读取

- [Low][80] src/backend/cbrowser/runtime_agent/dialog_attendant.py:339-351 — 弹窗托管服务异常断开未注销正在等待响应的 Future，引发 30 秒无意义等待

    - ID: f_supervisor_dialog_attendant_waiters; verification: static
    - Evidence: dialog_attendant.py 的 \_run 在异常退出时仅调用 attendant.release() 与 ws.close()，未取消 self.\_waiters 中的 Future
    - Impact: 若弹窗应答期间与浏览器内部连接断开，调用端无法立即感知，需等待完整的 30 秒超时才返回 None
    - Fix: 在 \_run 的 finally 块中遍历 self.\_waiters 将挂起的 Future 取消并清空字典

- [Low][80] src/backend/cbrowser/supervisor/core.py:2114-2235 — 核心启动流程未持久化操作账本，并发幂等重试退化为 409 冲突

    - ID: f_supervisor_start_profile_journal; verification: static
    - Evidence: start_profile 接受了 operation_id，但自身从未调用 self.operations.begin() 或 complete()，仅在 stop_profile 中持久化了账本
    - Impact: 因网络抖动携带相同 operation_id 重试 start_profile 时，直接触发 LifecycleConflictError 抛出 409，未享受到操作账本的幂等保护
    - Fix: 在 start_profile 入口处接入 self.operations.begin() 并在完成时记录结果

- [Low][80] src/backend/cbrowser/supervisor/docker_adapter.py:458-463 — 孤儿清理逻辑遭遇非预期命名格式时全盘失败，阻断 Supervisor 启动

    - ID: f_supervisor_orphan_helper_regex; verification: static
    - Evidence: docker_adapter.py 的 \_cleanup_orphan_helpers 对容器名执行严格正则匹配，不匹配直接抛出 DockerSandboxError; 在 runner.py:147 中作为启动必经前置门禁执行
    - Impact: 若宿主机存在同前缀的手动调试容器，正则不匹配直接导致 Supervisor 守护进程崩溃无法启动
    - Fix: 遵循蓝图纲领异常资源逐个拒绝不中断整轮，对命名不匹配容器记录 Warning 跳过，仅清理严格匹配的容器

- [Low][80] src/backend/cbrowser/supervisor/core.py:2404 — 全局协程锁过度序列化 stop 操作造成 Profile 关停并发性能瓶颈

    - ID: f_supervisor_stop_global_lock; verification: static
    - Evidence: core.py:2404 async with self.\_global_lock, lock: 在 stop_profile 中持有了类全局唯一的 self.\_global_lock
    - Impact: 不同 Profile 之间的容器相互独立，持有了全局锁导致多沙箱停止操作必须完全串行等待（单次耗时 1-3 秒，10 个沙箱需等待 20-30 秒）
    - Fix: 移除 self.\_global_lock，单 Profile 粒度的 \_locks[profile_id] 已足以保证互斥

- [Medium][90] src/backend/cbrowser/supervisor/path_validator.py:20-44 — 违反拒绝妥协铁律：使用 /proc/self/fd 魔法路径临时绕过 108 字节 sun_path 限制而非根因规范目录拓扑

    - ID: f_supervisor_sun_path_proc_fd_hack; verification: static
    - Evidence: path_validator.py 的 short_unix_socket_path 通过 os.open(dir, os.O_PATH) 获得目录句柄，拼接成 /proc/self/fd/{fd}/{filename}; 这是为了规避 sockaddr_un.sun_path 的 108 字节限制所使用的临时规避手段（workaround）; 未从根因将 runtime socket 放置在标准短路径拓扑中（如 /run/cbrowser/s/{id}.sock）
    - Impact: 强依赖 Linux 特定的 /proc 文件系统机制，在非 Linux 宿主、特定容器受限环境或 /proc 受保护场景下失效
    - Fix: 从架构顶层规范沙箱 runtime 目录拓扑结构，确保 socket 绝对路径原生控制在 108 字节内，移除 proc 魔法路径

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "agent_backend_runtime_supervisor"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "agent_backend_runtime_supervisor"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "agent_backend_runtime_supervisor"
  },
  "performance": {
    "status": "completed",
    "reviewer": "agent_backend_runtime_supervisor"
  },
  "design": {
    "status": "completed",
    "reviewer": "agent_backend_runtime_supervisor"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "agent_backend_runtime_supervisor"
  },
  "tests": {
    "status": "completed",
    "reviewer": "agent_backend_runtime_supervisor"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "agent_backend_runtime_supervisor"
  }
}
```

## files_reviewed

```json
[
  "src/backend/cbrowser/agent_executor/cli.py",
  "src/backend/cbrowser/agent_executor/dialogs.py",
  "src/backend/cbrowser/agent_executor/ledger.py",
  "src/backend/cbrowser/agent_executor/refs.py",
  "src/backend/cbrowser/agent_executor/session.py",
  "src/backend/cbrowser/agent_executor/state.py",
  "src/backend/cbrowser/agent_executor/transport.py",
  "src/backend/cbrowser/runtime_agent/__main__.py",
  "src/backend/cbrowser/runtime_agent/agent.py",
  "src/backend/cbrowser/runtime_agent/cdp_proxy.py",
  "src/backend/cbrowser/runtime_agent/dialog_attendant.py",
  "src/backend/cbrowser/runtime_agent/download_reconciler.py",
  "src/backend/cbrowser/runtime_agent/event_storage.py",
  "src/backend/cbrowser/runtime_agent/fontconfig.py",
  "src/backend/cbrowser/runtime_agent/preview_capture.py",
  "src/backend/cbrowser/runtime_agent/profile_defaults.py",
  "src/backend/cbrowser/runtime_agent/protocol.py",
  "src/backend/cbrowser/runtime_agent/runner.py",
  "src/backend/cbrowser/runtime_agent/security.py",
  "src/backend/cbrowser/runtime_agent/subsystems.py",
  "src/backend/cbrowser/runtime_agent/tunnel_filter.py",
  "src/backend/cbrowser/secret_files.py",
  "src/backend/cbrowser/service_errors.py",
  "src/backend/cbrowser/supervisor/__init__.py",
  "src/backend/cbrowser/supervisor/__main__.py",
  "src/backend/cbrowser/supervisor/address_pool.py",
  "src/backend/cbrowser/supervisor/agent_credentials.py",
  "src/backend/cbrowser/supervisor/artifact_forwarder.py",
  "src/backend/cbrowser/supervisor/container_spec.py",
  "src/backend/cbrowser/supervisor/control_client.py",
  "src/backend/cbrowser/supervisor/control_server.py",
  "src/backend/cbrowser/supervisor/coordinator_lock.py",
  "src/backend/cbrowser/supervisor/core.py",
  "src/backend/cbrowser/supervisor/docker_adapter.py",
  "src/backend/cbrowser/supervisor/event_forwarder.py",
  "src/backend/cbrowser/supervisor/file_storage.py",
  "src/backend/cbrowser/supervisor/gateway_client.py",
  "src/backend/cbrowser/supervisor/metrics.py",
  "src/backend/cbrowser/supervisor/network_policy.py",
  "src/backend/cbrowser/supervisor/network_spec.py",
  "src/backend/cbrowser/supervisor/operation_journal.py",
  "src/backend/cbrowser/supervisor/path_validator.py",
  "src/backend/cbrowser/supervisor/port_allocator.py",
  "src/backend/cbrowser/supervisor/protocol.py",
  "src/backend/cbrowser/supervisor/recovery_coordinator.py",
  "src/backend/cbrowser/supervisor/recovery_rules.py",
  "src/backend/cbrowser/supervisor/resource_monitor.py",
  "src/backend/cbrowser/supervisor/resource_policy.py",
  "src/backend/cbrowser/supervisor/runner.py",
  "src/backend/cbrowser/supervisor/selkies_tokens.py",
  "src/backend/cbrowser/supervisor/startup_gate.py",
  "src/backend/cbrowser/supervisor/volume_spec.py"
]
```

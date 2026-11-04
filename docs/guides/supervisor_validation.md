# Supervisor 验证

验证使用隔离数据根、随机测试凭证、真实 Docker Engine、独立 API fixture 与生产 Gateway。禁止读取本地 `.env`、覆盖用户 Profile 或停止既有服务。认证入口和 Docker Compose 交付由后续任务完成，测试 fixture 不能当作已交付服务。

## 环境

按 [Browser Runtime 验证](browser_runtime_validation.md) 与 [Stream Runtime 验证](stream_runtime_validation.md) 提供不可变镜像与 Linux 引擎缓存，并设置：

- `CBROWSER_RUNTIME_TEST_IMAGE`：构建后 Browser 镜像 ID。
- `CBROWSER_STREAM_TEST_IMAGE`：构建后 Stream 镜像 ID。
- `CBROWSER_RUNTIME_ENGINE_CACHE`：只读 Linux 引擎缓存源。
- `CBROWSER_RUNTIME_GEOIP_CACHE`：GeoIP 数据缓存源。
- `CBROWSER_SUPERVISOR_TEST_IMAGE`：当前源构建后 Supervisor 镜像 ID。
- `CBROWSER_NETWORK_POLICY_IMAGE`：与 Supervisor 相同的不可变镜像，提供 netns 策略安装入口。
- `CBROWSER_INVALID_POLICY_TEST_IMAGE`：故意不含策略模块的不可变镜像，仅用于 gate 失败封闭负例。
- `CBROWSER_API_TEST_IMAGE`：隔离容器拓扑 API fixture 镜像 ID。
- `CBROWSER_GATEWAY_IMAGE`：生产 Gateway 镜像 ID（`config/docker/gateway_runtime/Dockerfile`）。

镜像构建入口为 `config/docker/supervisor_runtime/Dockerfile` 与 `tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile`，各自带专属 Docker ignore，只发送必要源码；容器拓扑中的 Gateway 直接使用生产镜像。API fixture 的 SQLAlchemy asyncio extra 包含 arm64 冷启动所需 greenlet；Supervisor 镜像不安装 SQLAlchemy。

所有缓存、TMPDIR、pytest basetemp/cache_dir 都应放在允许写域内。先创建 TMPDIR，再启动解释器；避免回退系统临时目录。为本地 HTTP 测试清除当前测试进程的代理环境，不修改宿主机全局配置。使用 Python 3.12+ 和 `python -m pytest`，避免调用 PATH 中其他环境的 pytest。

## 分层验收

1. 单元测试验证端口耗尽、路径归属、凭证、操作重放与资源状态机；真实 HTTP 集成验证 API 认证、持久状态和事件语义。
2. `test_supervisor_startup_recovery_e2e.py` 用实际 bind RPC 重建启动中断状态，使用真实 API/Docker 空扫描及 HTTP 503 故障代理验证补偿与 Native 事件优先；该测试自身不声称执行了 SIGKILL。Host Supervisor E2E 验证真实 Browser/Stream 启动、独立 API 离线、正常 UDS 关闭、事件重放、Supervisor SIGKILL 和持久重试时间。
3. `test_supervisor_container_graph_e2e.py` 验证完整容器拓扑、唯一 Socket 持有者、无 SQLite、双网络、真实 infra 地址及 Viewer 停止握手顺序。
4. `test_supervisor_namespace_policy_e2e.py`、`test_supervisor_ipv6_policy_e2e.py` 和 `test_supervisor_policy_failure_e2e.py` 使用无过滤监听服务、同网正例及真实 kernel 策略验证 IPv4/IPv6 隔离、允许端点、重复安装拒绝和失败时 gate 封闭。`test_supervisor_orphan_helpers_e2e.py` 验证启动锁内回收自有临时 helper，保留 Runtime、Gateway 和不匹配归属的容器。
5. 配额生效的画面证明由 `test_supervisor_quota_chain_e2e.py` 提供：配额经生产控制客户端（`GatewayControlClient.set_quota`）下发，以 Viewer 页官方 Chrome 实际解码帧数的下降与恢复判定，CPU policy 腿（`supervisor_resource_probe/stream_monitor.py`）的帧数窗口同样取自 Viewer 页解码统计；不能以 Docker stats、配额消息或 Native 探针代替画面证明。

任何源变更后，应重建受影响镜像并保存实际 `.Id`，再运行相应 E2E；旧镜像通过不能代表当前源通过。失败轮次保留独立日志。测试 finally 只清理精确自有资源，不做 prune 或强制断开未知网络端点。

本机基准为 M1 Max 10 CPU/64 GiB，OrbStack 实际分配 10 CPU/约15.66 GiB，纯软件编码。公网 ICE 和原生 Linux x86_64 记 `NOT_RUN / USER_WAIVED`；10流容量、P95、8小时与1000次输入验收不能据组件测试提前标记通过。

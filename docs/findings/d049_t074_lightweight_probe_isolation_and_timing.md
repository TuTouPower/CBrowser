# d049 轻量探针可用「每请求新建 httpx.Client + trust_env=False + 动态白名单」在真实容器内保持隔离并把计时压到毫秒级

- 来源：s024 真实 Docker 容器原型（2026-11-16，`cbrowser-api:20261116015449-e88205a` 镜像，`--add-host=host.docker.internal:host-gateway`，代理指向 mihomo-proxy 节点端口）
- 结论：
    1. `ipaddress` 判定 + 精确 allowlist 的 fail-closed 守卫，对 127.0.0.1、10.0.0.1、192.168.1.1、169.254.169.254、::1、0.0.0.0、224.0.0.1 全部返回 `private_or_reserved`，白名单外域名返回 `not_in_allowlist`，不发起任何连接。
    2. 每次请求新建 `httpx.Client(proxy=..., trust_env=False, timeout=15, follow_redirects=True)`，不复用 TCP 连接池：热切换代理端口 21000→`212.107.28.52`（HK）与 21003→`104.249.174.133`（US）各自返回对应出口，无跨代理串扰。
    3. `time.monotonic()` 只包实际 HTTP 请求：合法端点 3 次 RTT 为 458.4 / 391.3 / 390.6ms，热切换两次为 427.2 / 520.8ms；整脚本墙钟 2195.1ms 含多次请求与容器运行，证明计时已与容器/网络生命周期解耦。
    4. 凭据只从环境变量指向的文件读取（`CBROWSER_PROBE_CREDS_FILE`），`argv` 为空且不含任何 password/secret/token 字面量。
- 证据：`docs/spikes/s024_t074_lightweight_probe_isolation/report.md`、`code/probe_isolation_prototype.py`、`code/results.json`。
- 影响：t074 Step 3 `docker_adapter.py` / `supervisor/core.py` 可据此把「每次测速必重建 bridge 网 + helper 容器 + policy 容器 + 冷启动 Python」从热路径移除，改为池化/常驻轻量 helper：单一动态白名单按代理目标热切换、每请求新建短生命周期 client、凭据不进命令行、`latency_ms` 仅取实际代理 HTTP 往返。既有私有/回环拦截与 `test_t052_supervisor_probe.py` / `docker_doubles.py` 边界须保持不变。
- 现状：有效

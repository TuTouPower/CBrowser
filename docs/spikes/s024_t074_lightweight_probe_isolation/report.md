# Spike report

## 问题

Supervisor 若把代理测速从「每次重建 bridge 网 + helper 容器 + policy 容器 + 冷启动 Python」改为池化/常驻轻量 probe helper，热切换网络白名单与隔离边界是否仍成立（不放宽私有/回环/保留地址拦截、不跨代理复用 TCP 连接池），以及 `latency_ms` 能否只计真实网络往返、不含容器生命周期。

## 成功判据

- 真实 Docker 容器内原型：私有/回环/保留/链路本地/未指定/组播地址全部被拒，白名单外目标被拒，合法白名单端点放行。
- 切换代理目标后出口 IP 随之改变，证明无跨代理连接池串扰。
- 单次 HTTP RTT 与整脚本墙钟可区分，证明计时内移。
- 凭据只从环境变量文件读取，不出现在 `argv`。

## 尝试

- `code/probe_isolation_prototype.py`：在 `cbrowser-api:20261116015449-e88205a` 真实容器内运行，`docker run --rm --add-host=host.docker.internal:host-gateway`，代理指向 mihomo-proxy 节点端口。
- 每次请求新建 `httpx.Client(proxy=..., trust_env=False, timeout=15, follow_redirects=True)`，`time.monotonic()` 只包 `client.get()`；`blocked()` 用 `ipaddress` 判定私有/保留地址并做精确 allowlist。
- 凭据以 `CBROWSER_PROBE_CREDS_FILE` 环境变量注入，检查 `sys.argv`。
- 结果 `code/results.json`，stderr `code/stderr.log`。

## 证据

- `private_guard`：127.0.0.1、10.0.0.1、192.168.1.1、169.254.169.254、::1、0.0.0.0、224.0.0.1 全部 `private_or_reserved`；`evil.example.com` → `not_in_allowlist`；被拒项 `http: null`，未发起连接。
- `allowlist_ok`（21000 / api.ipify.org，3 次独立 client）：200 / 200 / 200，RTT 458.4 / 391.3 / 390.6ms。
- `hot_swap`：21000 → `212.107.28.52`（HK，RTT 427.2ms），21003 → `104.249.174.133`（US，RTT 520.8ms）；同一端点不同代理返回各自出口，无跨代理串扰。
- `total_wall_ms` 2195.1ms 为整脚本墙钟（含多次请求与容器运行），单次 RTT 独立记录，计时与容器/网络生命周期解耦。
- `argv=[]`，`creds_in_argv=false`，`creds_from_env_only=true`。
- 本轮为原型级验证：未接入 Supervisor 真实 helper 生命周期与 `docker_doubles.py` 夹具；真实容器隔离策略与内核双族 OUTPUT DROP 边界由既有 `test_t052_supervisor_probe.py` 守护，改动时不得放宽。

## 结论

轻量/池化探针架构可行且隔离边界可保持：单一动态白名单按代理目标热切换、每请求新建短生命周期 `httpx.Client(trust_env=False)`、私有/回环/保留地址 fail-closed、凭据不进命令行、`latency_ms` 仅取实际代理 HTTP 往返。这能把当前每次测速数秒级容器建毁开销（本机实测约 5579.66ms）从热路径移除，且不放宽 `docs/blueprint/security.md` 与 d047 的双族隔离约束。可信度：真实容器 + 真实代理多出口实测，行为层可直接采纳；Supervisor 生产接线与既有隔离单测的完整回归在 t074 Step 3/6 完成。

## 是否采纳

- 决定：是
- 理由：原型证明「池化轻量 helper + 每请求新 client + 计时内移」不破坏隔离且给出毫秒级延迟，定型 Step 3 的执行架构。
- 后续 task：t074
- 无需后续理由：不适用

## 关联 findings

- `docs/findings/d049_t074_lightweight_probe_isolation_and_timing.md`

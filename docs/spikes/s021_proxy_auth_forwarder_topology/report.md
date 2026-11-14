# Spike report

## 问题

t065 要把代理凭据从 Browser 容器彻底隔离：凭据同时出现在 Runner 的
`--proxy-server`（内联 userinfo，`argv`/`/proc` 可见）和 Browser 可读的
`proxy_credentials.json`，且 `docker_adapter.py` 除凭据 ro bind 外还挂整个
runtime 目录——ro 只防写不防读。需要验证：一个本地认证转发器（auth-forwarder）
能否在 Browser 与上游代理之间终结未认证流量、自行注入凭据重发上游，
覆盖 HTTP/HTTPS（CONNECT 隧道）与 SOCKS5（远端 DNS）三协议，
且上游不可达/407/认证失败时失败封闭（无响应体、无直连尝试），
同时与现有容器/网络策略机制（per-profile bridge 网络、容器内 DNS 预解析、
策略 gate、0600 secret 挂载）拼得上。

## 成功判据

- 转发器以 stdlib 实现 HTTP CONNECT 隧道、absolute-form 直发、SOCKS5
  用户名/密码认证＋域名直通（远端 DNS），三协议均有可重复的本地桩验证。
- 上游不可达、407、SOCKS5 认证失败、畸形客户端请求时均关闭连接，
  无响应体、无直连源站尝试；日志永不含密码/Basic token。
- 拓扑拼合无未解矛盾：Browser 只连转发器（同一 bridge 网络内 Docker DNS
  可解析转发器容器名）、转发器出站只允上游端点（IP 字面量 allow-list）
  ＋ Docker DNS（127.0.0.11:53/udp）、凭据只挂进转发器（secret 目录 0600）。

## 尝试

- 新包 `src/backend/cbrowser/proxy_forwarder/`（stdlib only：
  `forwarder.py`、`__main__.py`），固定监听端口 18080，端点文件
  `proxy_forwarder.json`（runtime 目录内、无秘密：scheme 恒 http、
  转发器容器 hostname、端口、冻结 credential_revision）。
- `UpstreamConfig` 严格校验（scheme 白名单 http/https/socks5、
  port 1..65535、有密码无用户名拒、revision 须 int）。
- HTTP/HTTPS 上游：CONNECT 建隧道（https 上游先包 TLS，再发 CONNECT；
  注入 Proxy-Authorization，407 即失败封闭）、absolute-form 直发上游
  （单请求单连接、Connection: close 定界；非 2xx 响应不透传响应体）；
  SOCKS5 上游：用户名/密码认证（用户名无密码时 Basic 恒为 `user:`）、
  目标域名以 domain 地址直通（远端 DNS，本地永不解析目标名）、
  IPv4 字面走 ATYP 0x01、IPv6 字面走 ATYP 0x04。
- TDD 过程修掉的 bug：`asyncio.IncompleteRead` 实为
  `IncompleteReadError`；`_relay` 须 FIRST_COMPLETED 语义（任一方向
  结束即关会话，否则 keep-alive 挂住）；absolute-form 须分流（HTTP
  上游走纯 TCP 直发、SOCKS5 走隧道＋改 origin-form 请求行）；
  `_relay` 调用参数顺序曾交叉成回环。

## 证据

- `tests/unit/test_t065_proxy_forwarder.py` 通过（HTTP CONNECT 隧道、
  absolute-form GET、407 失败封闭且日志无凭据、SOCKS5 远端 DNS、SOCKS5
  认证失败、上下游宕机无直连、absolute-form 经 SOCKS5、IPv6＋特殊字符、
  配置校验、origin-form 拒绝、首包 smoke（仅存活验证，报告样本中位数；
  基线对比顺延 p098 第 4 项）、端口常量；审阅修复后补：https 上游 TLS
  包裹、SOCKS5 IPv6 字面 ATYP 0x04、absolute-form 407 体不透传、
  用户名无密码 Basic 恒带冒号、超 64 KiB 请求头失败封闭）。
- 拓扑拼合的机械依据（均为仓内现成机制复用，无新原语）：
  `DockerAdapter.start_stream_container` 是转发器创建的范本（0600 校验、
  `validate_secret_source`、policy gate、labels、network、restart_policy no、
  user 1000:1000、read_only、cap_drop ALL、no-new-privileges）；
  `_resolved_endpoint` 在容器内以 Docker DNS 预解析上游为 IP 字面量；
  `_install_network_policy` 在 gate ready 后放行；`NetworkPolicySpec`
  的 INPUT 默认 DROP、OUTPUT 默认 DROP（非 browser 角色）。
- 未验证（留待真实部署）：真实 Docker/Chrome/Selkies 拓扑下的端到端
  凭据不可读、三协议上游认证、407/断线故障封闭、首包延迟与 407 往返
  的基线对比——云端无 Docker，按口径顺延 pending（本地补验）。

## 结论

采纳。转发器设计在协议层与拓扑拼合层均已验证通过，t065 按此实现：
凭据只进 secret 目录（`data_root/runtime/.secrets/{profile_id}`）与转发器
容器；Browser 的 `--proxy-server` 改为无凭据的转发器端点
（`http://<转发器容器名>:18080`），其网络策略只允转发器端点；
Runner 只读端点文件、修订号漂移即失败封闭。
残留未知（真实部署链）不在本 spike 结论内，由 pending 登记本地补验。

## 是否采纳

- 决定：是
- 理由：协议行为 12/12 本地桩验证通过；拓扑拼合全部复用仓内现成机制，
  无未解矛盾；残留的真实部署验证已登记 pending，不阻塞实现。
- 后续 task：t065
- 无需后续理由：不适用

## 关联 findings

- 无新建条目：`findings.py new` 因既存编号重复（d037/d038 各出现两次）
  拒绝取号（与 t063 相同工具链缺陷，已挂 `docs/pending/todo/p093_t066_local_deploy_verification.md`
  第 6 项）。本报告即结论载体；待编号缺陷修复后，再由本 spike 结论
  抽取新建 finding 条目。

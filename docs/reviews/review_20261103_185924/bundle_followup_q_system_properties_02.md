# bundle_followup_q_system_properties_02

## Summary

独立复核范围：supervisor 的 network_policy 规则渲染（v4/v6）、container_spec 的 stream 环境与端口发布、docker_adapter 的 stream 容器创建与策略构造、stream_agent/agent.py 全部连接发起点、gateway/ 全目录（含 server.py 与 api_client.py）、stream_runtime entrypoint.sh 的 Selkies 启动参数，以及策略测试的存在性。结论：怀疑消解。没有任何组件被配置为向 Stream 容器新开 TCP 连接——Gateway 是纯 aiohttp 服务端，只接受连接，其与 Agent 的全部下行通信复用 Agent 主动建立的注册 WebSocket 隧道，唯一外呼是指向 API 的授权/运行时查询；StreamAgent 与 Selkies 同容器同进程，Agent 以回环 WS 连 Selkies 信令，且 Selkies 被 entrypoint 钉死 --addr 127.0.0.1 仅绑回环；Browser 容器与 Stream 容器之间走共享 UDS（X11/Pulse 目录 bind mount）与共享 IPC 命名空间，不是 TCP；媒体面只有 WebRTC UDP mux 端口，与 INPUT 策略的 UDP 放行一一对应。因此 INPUT『仅回环 + 已建立 + UDP mux』与实际连接方向自洽，不存在信令/媒体被策略静默丢弃的组合缺口。architecture 审阅者的同向结论经独立复核成立（18096 确为注入 Stream 容器的 SELKIES_PORT 环境变量、非 Gateway 的连接目标）。残余缺口仅一项：Selkies 服务端是 pip 包 selkies==2.1.0、源码不在仓内，其内部连接发起无法逐行核尽；但其绑定地址、媒體端口与无 TURN 配置均由仓内启动参数钉死，且 INPUT DROP 使任何未配置的非回环入站监听同样不可达，该缺口不改变裁决。本轮为静态审阅，未运行测试，策略覆盖以测试断言存在为据。

## Findings

No findings.

## evidence

```json
[
  "src/backend/cbrowser/supervisor/network_policy.py:135-147 与 187-199 — INPUT 默认 DROP，仅放行 -i lo、ESTABLISHED/RELATED，stream 角色额外放行 UDP mux 端口；v4/v6 渲染同构，无任何新入 TCP 放行",
  "src/backend/cbrowser/stream_agent/agent.py:253-262,277-285 — StreamAgent 的 connect_and_run 出站向 Gateway 发起注册 WebSocket（{gateway_url}/stream/agent/register），连接由 Agent 发起、Gateway 只接受",
  "gateway/ 全目录 grep 核对：server.py 是 aiohttp web 应用、只注册路由接受连接，全目录无 ws_connect / ClientSession 外呼；下行 viewer 消息经注册 WS 的既有隧道转发，Agent 不在线时 viewer 直接被拒（gateway/server.py:507）",
  "src/backend/cbrowser/gateway/api_client.py:30,38-78 — Gateway 唯一外呼是 httpx 客户端，base_url 指向 API，仅调用 /api/v1/internal/gateway/profiles/{id}/runtime 与 /viewer-authorize，不连任何 Stream 容器或 Selkies",
  "src/backend/cbrowser/stream_agent/agent.py:745,755-760 与 1059-1063 — 每 viewer 工作线程连接 upstream_url = ws://127.0.0.1:{SELKIES_PORT}/api/webrtc/signaling，代码注释明示 loopback upstream connection",
  "src/backend/cbrowser/stream_agent/agent.py:1049-1084 — Agent 与 Selkies 同进程：patch selkies.__main__.WebRTCService 工厂后在同一进程内启动 agent.connect_and_run 并运行 selkies.main()，不存在跨容器信令连接",
  "config/docker/stream_runtime/entrypoint.sh:191-192,208-213 — export SELKIES_ADDR=127.0.0.1 且启动参数 --addr 127.0.0.1、--port $SELKIES_PORT、--webrtc-udp-mux-port $SELKIES_WEBRTC_UDP_MUX_PORT：Selkies 信令仅绑回环，媒体仅走 UDP mux",
  "src/backend/cbrowser/supervisor/container_spec.py:140,156-157 — SELKIES_PORT=18096 只是注入 Stream 容器的环境变量；stream_ports 只把 UDP mux 端口发布到宿主 127.0.0.1，Stream 容器无任何 TCP 端口发布",
  "src/backend/cbrowser/supervisor/docker_adapter.py:886-898 — stream 角色策略 allowed_tcp 仅为解析后的 Gateway 端点（供 Agent 出站注册），allowed_udp 为空，与 Agent 的出站方向一致",
  "src/backend/cbrowser/supervisor/docker_adapter.py:790-816,873 — Browser 与 Stream 容器经宿主目录 bind mount 共享 X11 socket 与 Pulse 目录，且 Stream 容器 ipc_mode=container:<browser> 共享 IPC：均为 UDS/文件系统路径，不是进入 Stream 容器的 TCP 连接",
  "src/backend/cbrowser/supervisor/container_spec.py stream_environment 与 entrypoint.sh:189 — Stream 容器 env 中无任何 TURN 配置（同机直连），媒体面只有 CBROWSER_UDP_MUX_PORT，与 INPUT 的 UDP mux 放行对应",
  "tests/unit/test_network_policy.py:77-85,153-163 — 单元测试断言 stream 角色 INPUT DROP、lo 放行与 UDP mux 放行；tests/e2e/test_supervisor_namespace_policy_e2e.py:313 test_kernel_network_policy_real_netns 在真实 netns 验证内核策略（本轮静态审阅未执行）",
  "缺口：config/docker/stream_runtime/requirements.in:1 — Selkies 服务端为 pip 包 selkies==2.1.0，Python 源码不在仓内（仓内只 vendored 其 web 资产，见 config/selkies/selkies_web_sha256.txt），其内部连接发起无法逐行静态核尽；仓内可核的启动绑定（回环）、UDP mux 与无 TURN 配置如上，且 INPUT DROP 使未配置的非回环入站监听同样不可达"
]
```

## result

```json
"refuted"
```

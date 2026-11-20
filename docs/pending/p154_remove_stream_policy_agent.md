---
pid: "p154"
slug: "remove_stream_policy_agent"
status: "todo"
---
# p154 删除 Stream 推流容器的 Policy Agent：本机回环推流无需网络策略 Sidecar 与巡检

- 来源：用户 2026-11-21 质询与口述。在看到 Docker/OrbStack 中每个活跃 Profile 都伴随两个 `cbrowser-policy-agent-*` 容器（3 个 Profile 共运行 6 个 agent 容器）时，指出推流容器与外部浏览器之间纯走本地 127.0.0.1 回环推流，且与 Browser 容器仅通过 `/dev/shm` IPC 和 X11 交互，与网络代理和出网策略毫无关系，质疑推流容器挂 Policy Agent 属严重过度考虑（Over-engineering）与形式主义安全。
- 内容：
    1. **现状与事实**：
        - 当前系统（t082 / ADR 039）中，Supervisor 为每个 Profile 的 `browser` 和 `stream` 目标容器各自启动一个常驻的 `cbrowser-policy-agent` sidecar 容器（`network_mode=container:<target_id>`）。
        - 每个活跃 Profile 会产生 2 个 Policy Agent 容器；3 个 Profile 稳态下会运行 6 个 Agent。
        - Stream 容器与 Browser 容器之间交换音视频渲染帧和输入事件完全走 Linux 共享内存（`/dev/shm` IPC）和 UNIX 域套接字，压根不经过网络栈（TCP/IP）。
        - Stream 容器的对外网络仅有两项职责：① 本地监听唯一的 `udp_mux_port`，仅绑定 `127.0.0.1` 供宿主 Chrome 直连接收 WebRTC 媒体流；② 连接同一受管 edge 网络内的 `cbrowser-gateway` 完成 WebRTC 信令握手。
    2. **根因分析（违反开发铁律）**：
        - **历史包袱残留（局域网功能退役但防护逻辑残留）**：早期 t042 时代曾规划局域网直连推流，当时为了防止推流容器被利用扫描内网设计了私网 DROP 规则。而在 t054（ADR 031）中，系统已彻底删除局域网直连、删除运行时网络变更链，推流明确收敛为“媒体直连只走本机回环（127.0.0.1）”。局域网多机暴露面已经彻底不复存在，但为之配备的重型网络过滤逻辑却因惯性被原样保留。
        - **模型抽象一刀切（架构偷懒）**：t082 将网络策略收归常驻 Agent 时，为了实现状态机收敛的“统一抽象”，Supervisor 代码将 `browser` 与 `stream` 统称为 `role in ("browser", "stream")`，一刀切地为两者均配备独立的 Agent 容器、UDS 协议、修订号围栏、周期性 `inspect` 巡检、甚至规则漂移后的 `fail_close` / `recovering` 暂停机制。
        - **职责错位与虚构威胁**：在本地单机隐私浏览器架构下，给推流容器专设一个 sidecar 容器 24 小时巡检 iptables 防内网穿透，属于把多租户公有云或零信任企业网的极端威胁模型硬套在单机桌面工具上，制造了 50% 毫无必要的容器开销与系统复杂度。
    3. **解决方案（从根因彻底重构，不做兼容层）**：
        - **彻底废除 Stream 的 Policy Agent 整条路径**：
            - 删除 Stream 容器的 Policy Agent 创建、配属、接管、孤儿清理与 UDS 通信逻辑。
            - Policy Agent 专职且仅服务于 `browser` 容器（Browser 运行不可信网页 JS/WASM，需严格强制走上游代理、防止真实 IP 泄露与 IPv6/DNS 绕过）。
        - **Stream 隔离收敛为纯 Docker 声明式配置**：
            - Stream 容器仅接入受管 internal/edge 网络，仅暴露绑死 `127.0.0.1` 的 `udp_mux_port`。
            - Stream 容器无需 `cap_add: [NET_ADMIN]`，无需只读根与控制 socket 挂载，无需常驻守护进程。
        - **精简 Supervisor 启动与收敛链路**：
            - `docker_adapter.py` / `runner.py` / `container_spec.py` 中移除所有 `stream` 相关的 policy spec 派生（`stream_policy_spec`）、gate 启动屏障及巡检分支。
            - Stream 容器启动后直接向 Gateway 注册，无需等待 Agent 握手与规则应用。
        - **清理规格与文档**：
            - 更新 ADR 039（明确 Policy Agent 仅为 Browser 独占）、`docs/blueprint/architecture.md`、`docs/specs/webrtc_remote_display.md`。
    4. **预期收益**：
        - 单 Profile 辅助容器数减少 1 个；多 Profile 场景下 Policy Agent 容器数量直接减半（例如 3 Profile 从 6 个降至 3 个）。
        - 显著降低 Docker daemon 容器并发压力与 Docker API 调用频次，缩短 Profile 启动延迟。
        - 架构彻底解耦，推流链路与网络策略控制面彻底脱钩。
- 处理：未开

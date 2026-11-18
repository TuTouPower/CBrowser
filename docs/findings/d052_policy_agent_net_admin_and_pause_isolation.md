# d052 Policy Agent 仅 CAP_NET_ADMIN 可完成双栈规则与 netns DNS 解析，docker pause 可瞬时冻结流量且重启按意图围栏接管

- 来源：p132（t082 两项本地真实 Docker / OrbStack spike，基于部署镜像 release `20261118212912-a0fed8e`）
- 结论：
    1. **最小权限成立**：在 Supervisor 镜像（`iptables v1.8.11 (nf_tables)` / `ip6tables v1.8.11 (nf_tables)`）下启用 `cap_drop=["ALL"]`、`cap_add=["NET_ADMIN"]`、`read_only=True`、`security_opt=["no-new-privileges:true"]`、`network_mode=container:<target>`，挂载清单仅含自身 UDS slot 目录（`/run/cbrowser_policy_agent`，`/tmp` 为 tmpfs），内核 `/proc/1/status` 实测 `CapEff=0000000000001000`、`NoNewPrivs=1`，`/proc` 仅暴露 Agent 自身 PID（`[1, 6]`）。无需 `SYS_ADMIN`、host PID 或 `privileged`。
    2. **双栈策略与 DNS 一致性成立**：Agent 经 UDS `resolve` 返回的双栈解析结果（`['172.31.132.2', 'fd82:132::2']`）与目标容器内 `socket.getaddrinfo` 完全一致；IPv4/IPv6 白名单放行与非白名单阻断、`identity_mismatch` 与 `stale_revision` 拒绝、rev2 热替换均生效；`fail_close` 写入的双栈阻断规则在 Agent 容器拆除后仍持久生效。
    3. **暂停冻结、共享 IPC 与重启围栏成立**：`docker pause` 立即冻结 Browser 容器出站 TCP（正常 RTT `0.19ms` → 暂停后 `TimeoutError 2510.7ms`），`unpause` 耗时 `22.97ms` 并立即恢复通行（`0.14ms`）；Browser `ipc_mode="shareable"` + `shm_size="64m"` 下替换 Stream 容器保持 Browser 容器 ID 与 `/dev/shm` 共享内存不变；Supervisor 重启接管暂停容器时按 `desired_state` 围栏裁决——`desired=running` 的暂停实例通过策略复验后以同一 `runtime_instance_id` 恢复运行，`desired=stopped` 的暂停实例直接拆除清理而不误恢复。
- 证据：本地 OrbStack 隔离 Docker 实测（基于 release `20261118212912-a0fed8e`，`supervisor` 镜像 `sha256:642df88f4b1f337a25454e960c3f79b97ab7eaa3503a1bf9699cf5bd0f1f9a4d`；见 ADR 039 与 `docs/pending/p132_verify_t082_policy_agent_spikes_locally.md`）。
- 影响：ADR 039（`docs/blueprint/decisions/20261118_namespace_policy_agent.md`）的两项延迟 spike 假设已获实证确认；Policy Agent 维持最小权限设计，不扩权。
- 现状：有效

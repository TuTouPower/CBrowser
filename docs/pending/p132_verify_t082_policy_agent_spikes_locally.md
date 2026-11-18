---
pid: "p132"
slug: "verify_t082_policy_agent_spikes_locally"
status: "todo"
---
# p132 本地实证 t082 两项 spike：仅 NET_ADMIN 的完整策略/DNS 能力与暂停/恢复安全行为

- 来源：t082 遗留（云端无 Docker，两项 UNVERIFIED-SPIKE 无法在云端实证；经用户 2026-11-18 裁定延期本地统一处理）
- 内容：在隔离真实 Docker 环境正式执行 t082 的两项 spike 并把结论回填 findings/ADR 039：
    1. 仅 NET_ADMIN、policy 镜像（= Supervisor 镜像）、`network_mode=container:<目标 ID>` 下，Policy Agent 能否完成完整策略能力：双栈 iptables/nft 规则安装与精确比对、fail-closed 安装与确认、目标 netns 视角的 DNS 解析（getaddrinfo 结果与原 gated 容器内解析一致）；若实证需要 SYS_ADMIN/host PID/privileged，停止扩权并回报修订设计，不静默绕过。
    2. 暂停/恢复安全行为：Supervisor 对精确目标执行 Docker pause 后，目标 netns 流量确实冻结（网络负例证明，不能只看 pause API 返回成功）；Stream-only 替换、共享 IPC、Supervisor 重启接管与 pause 所有权（只恢复本机制暂停且仍为当前 desired=running 的实例）在真实链路下成立。
- 处理：未开

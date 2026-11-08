# bundle_global_system_properties

## Summary

从系统整体性质（安全、可靠性、一致性）评估：系统在沙箱权限剥离（0750/0600、只读 rootfs、cap_drop ALL、iptables 私网阻断）方面表现优异，符合隐私沙箱高强度隔离设计。但在反向代理穿透防护与故障清理时序上存在系统级漏洞：网关与控制面限速误用反代 IP 导致连带 DoS 风险，容器清理异常未阻断端口释放导致跨 Profile 端口污染风险。

## Findings

- [High][90] src/backend/cbrowser/api/v1/control_router.py:74; gateway/server.py:731 — 反代 IP 解析穿透不一致引发跨用户、跨租户级连带拒绝服务漏洞
    - ID: f_global_sys_proxy_ip_cascade_dos; verification: static
    - Evidence: control_router.py 与 gateway/server.py 均未调用 resolve_client_ip，直接使用反代网关 Caddy 的内部 IP 进行限流与封禁; 外部恶意请求达到阈值后导致 Caddy 容器 IP 全局被拉黑
    - Impact: 单个恶意客户端的攻击行为会导致共享同一网关的所有合法用户与自动化 Agent 全部遭受 429 阻断，系统整体可用性崩溃
    - Fix: 在网关与控制面全链路强制引入 resolve_client_ip 并配置受信任代理 CIDR 白名单

## questions

```json
[
  {
    "id": "q_system_properties_01",
    "question": "若宿主发生断电或 Supervisor 进程崩溃重启，未完成 teardown 或处于 running 的容器能否被无损对账，端口和子网分配是否能从 Docker 事实中安全恢复而不发生碰撞？",
    "units": [
      "backend_runtime_supervisor"
    ],
    "evidence_needed": "检查 SupervisorCore.scan_and_reconcile_existing 与 PortAllocator.restore 的启动自愈代码",
    "counterevidence": "若启动时有全量容器扫描与端口占用恢复逻辑"
  }
]
```

## question_decisions

```json
{
  "q_system_properties_01": {
    "result": "confirmed",
    "reason": "精查证实恢复逻辑已覆盖正常运行容器，但对处于 exited/dead 残留端口的边缘情况缺乏主动清理，确认为一致性限制",
    "followup_sha256": "e9bc601482c15fb32eb883782f7729ac90f4e9f63c29c8087c170bc6aa8e4ed4"
  }
}
```

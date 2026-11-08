# bundle_followup_q_arch_01

## Summary

精查证实：局域网切换操作在 NetworkService 内部通过 4 阶段状态机（VALIDATING, REBUILDING_CADDY, REBUILDING_STREAMS, FINALIZING）分步执行。但各阶段之间缺乏原子回滚事务：若 REBUILDING_STREAMS 在遍历多个活跃沙箱更新 netns iptables 规则中途抛出异常，已重建的沙箱处于 LAN 模式，而未重建的沙箱处于本地模式，且 Caddy 已切换至新端口，系统出现状态分裂，且无自动回滚机制。

## Findings

No findings.

## evidence

```json
[
  "src/backend/cbrowser/services/network_service.py:135-203 _execute_apply 依次调用 rebuild_edge 与 converge_network_streams",
  "RuntimeCoordinator.converge_network_streams 循环调用 supervisor converge 遍历活跃沙箱",
  "若中间容器更新网络策略失败，异常直接导致整个操作置为 FAILED，无回滚旧网络版本与旧 Caddyfile 逻辑"
]
```

## result

```json
"confirmed"
```

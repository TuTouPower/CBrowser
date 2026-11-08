# bundle_global_architecture

## Summary

从整体架构视角评估：单一写入者 SQLite（API 独占）、单一 Docker 控制者（Supervisor 独占）与不可变配置版本链（ADR 023）执行严密，职责清晰。但在横向通信与网络重构协同上，API 路由前缀、网关配置与部署脚本之间存在多处未对齐裂痕，且局域网重构缺乏跨容器分布式原子性保证。

## Findings

- [High][90] src/backend/cbrowser/services/network_service.py:135-203; runtime_coordinator.py:1144-1190 — 局域网接入模式切换缺乏事务性回滚与补偿，失败将致多沙箱状态分裂
    - ID: f_global_arch_network_switch_atomicity; verification: static
    - Evidence: NetworkService 执行配置应用分 4 阶段推进，若后半部分容器策略更新失败，前期已生效的 Caddy 端口与部分容器网络规则无法自动回滚; 结合 BC-01 的 AttributeError 与 BC-02 的 404 缺陷，网络切换流程极易中断于半完成状态
    - Impact: 网络配置更新失败后系统处于混合中间态，部分沙箱可访问部分沙箱不可访问，且数据库活跃操作被永久死锁
    - Fix: 在 NetworkService 中引入补偿机制（Saga 模式或旧版本回退快照），并在任何阶段失败时调用回滚钩子

## questions

```json
[
  {
    "id": "q_arch_01",
    "question": "当网络从 Local 切换至 LAN 时，Caddyfile 重新生成、证书准备与各 Stream 容器网络策略更新是否具备分布式原子性？若部分容器更新失败是否导致架构状态分裂？",
    "units": [
      "backend_core",
      "backend_runtime_supervisor",
      "backend_stream_gateway"
    ],
    "evidence_needed": "检查 NetworkService、RuntimeCoordinator 与 Supervisor 的多容器循环更新是否有两阶段提交或回滚补偿",
    "counterevidence": "若 Supervisor 存在全局网络重建失败回滚与降级机制"
  }
]
```

## question_decisions

```json
{
  "q_arch_01": {
    "result": "confirmed",
    "reason": "精查证实多阶段 apply 缺乏失败补偿，一旦后序沙箱抛出网络异常，前半已应用的规则停留在新版本，采纳精查证据并确认为 High 级别架构缺陷",
    "followup_sha256": "b8cc5e56923488347e1d9c884f225fce6df29bc13a2412f454249cbc97e9517a"
  }
}
```

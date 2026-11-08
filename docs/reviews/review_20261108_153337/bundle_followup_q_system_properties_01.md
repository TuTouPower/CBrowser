# bundle_followup_q_system_properties_01

## Summary

精查证实：SupervisorCore 在启动时通过 scan_and_reconcile_existing（core.py:937-975）能够扫描 Docker 中已有容器，并通过 port_allocator.restore（port_allocator.py:46-55）从活跃容器标签中恢复已占用的 UDP 端口映射。然而，对于处于异常状态（如 exited 或 Dead）但依然残留端口映射的容器，由于未建立 ActiveSession，其端口可能被遗漏恢复，随后在新分配中产生冲突。总体恢复机制存在但边缘情况需加强。

## Findings

No findings.

## evidence

```json
[
  "src/backend/cbrowser/supervisor/core.py:937-975 scan_and_reconcile_existing 扫描容器并对齐状态",
  "src/backend/cbrowser/supervisor/port_allocator.py:46-55 restore 方法根据已占用集合恢复",
  "若容器处于非运行态但未被清理，PortAllocator 未从其 HostConfig 读取已绑定端口，存在盲区"
]
```

## result

```json
"confirmed"
```

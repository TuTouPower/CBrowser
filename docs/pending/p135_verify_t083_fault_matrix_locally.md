---
pid: "p135"
slug: "verify_t083_fault_matrix_locally"
status: "todo"
---
# p135 本地补验 t083 AC-010：隔离栈故障注入矩阵与资源样本

- 来源：t083 遗留（[deploy] AC-010，用户 2026-11-18 裁定云端不可验者登记本地统一补验）
- 内容：在与 p134 同一隔离真实栈上分别注入 API / Supervisor / Gateway 重启、状态变更通知丢失、策略漂移、单 Profile 慢响应五类故障，核对业务与安全恢复及计数边界（丢通知在下一 30 秒兜底对齐内恢复、漂移按 t082 收敛语义处置、慢 Profile 不阻断其他 Profile）；保存 CPU / rchar / 宿主日志前后样本，OrbStack 错误仅按本轮容器 ID 归属，缺日志不冒充零错误。云端无 Docker/真实 Chrome，无法执行。
- 处理：未开

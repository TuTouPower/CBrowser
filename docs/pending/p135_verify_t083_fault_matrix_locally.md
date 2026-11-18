---
pid: "p135"
slug: "verify_t083_fault_matrix_locally"
status: "closed"
resolution: "resolved"
reason: "已于同一隔离真实栈 cb134 完成五类故障注入与样本归属验证：API 重启后 4 实例 runtime_instance_id 与浏览器状态保持不变；Gateway 重启恢复全部 transport_state=ready 与 Chrome Viewer WebRTC 画面（无 page_errors）；Supervisor 重启后 service_readiness_probe 返回 exit 0（services 全 true）且 4 实例/容器原样收养；pause Supervisor 丢弃 StateChangeNotice（API 记录 ReadTimeout）后于 unpause 1.54 s（<=30 s 兜底窗口）完成状态收敛；P2 Browser Policy Agent 双栈规则漂移于 30.59 s 检出 browser_policy_drift 且 fail-closed（出网 TimeoutError）；pause P3 期间 P4 stop（1.6 s）与 start（10.71 s）均未被阻断。已记录故障前后 CPU/rchar、按容器 ID 隔离日志及 OrbStack 宿主 vmgr/gui/unified-kill 日志增量样本，其中 vmgr.log 在 P4 重建期间出现与本轮网络名 cb134-net-*/cb134-browser-net-* 相关之 failed to add network (too many interfaces) 记录（P4 随后仍于 10.71 s 完成启动与就绪），gui.log 与 unified-kill.log 无本轮归属日志。"
fix_ref: "main"
---
# p135 本地补验 t083 AC-010：隔离栈故障注入矩阵与资源样本

- 来源：t083 遗留（[deploy] AC-010，用户 2026-11-18 裁定云端不可验者登记本地统一补验）
- 内容：在与 p134 同一隔离真实栈上分别注入 API / Supervisor / Gateway 重启、状态变更通知丢失、策略漂移、单 Profile 慢响应五类故障，核对业务与安全恢复及计数边界（丢通知在下一 30 秒兜底对齐内恢复、漂移按 t082 收敛语义处置、慢 Profile 不阻断其他 Profile）；保存 CPU / rchar / 宿主日志前后样本，OrbStack 错误仅按本轮容器 ID 归属，缺日志不冒充零错误。云端无 Docker/真实 Chrome，无法执行。
- 处理：main；resolution=resolved；reason=已于同一隔离真实栈 cb134 完成五类故障注入与样本归属验证：API 重启后 4 实例 runtime_instance_id 与浏览器状态保持不变；Gateway 重启恢复全部 transport_state=ready 与 Chrome Viewer WebRTC 画面（无 page_errors）；Supervisor 重启后 service_readiness_probe 返回 exit 0（services 全 true）且 4 实例/容器原样收养；pause Supervisor 丢弃 StateChangeNotice（API 记录 ReadTimeout）后于 unpause 1.54 s（\<=30 s 兜底窗口）完成状态收敛；P2 Browser Policy Agent 双栈规则漂移于 30.59 s 检出 browser_policy_drift 且 fail-closed（出网 TimeoutError）；pause P3 期间 P4 stop（1.6 s）与 start（10.71 s）均未被阻断。已记录故障前后 CPU/rchar、按容器 ID 隔离日志及 OrbStack 宿主 vmgr/gui/unified-kill 日志增量样本，其中 vmgr.log 在 P4 重建期间出现与本轮网络名 cb134-net-*/cb134-browser-net-* 相关之 failed to add network (too many interfaces) 记录（P4 随后仍于 10.71 s 完成启动与就绪），gui.log 与 unified-kill.log 无本轮归属日志。

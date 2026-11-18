---
pid: "p133"
slug: "verify_t082_deploy_chain_locally"
status: "todo"
---
# p133 本地补验 t082 AC-010：4 Profile 稳态 10 分钟零 churn 与故障窗口网络正负例

- 来源：t082 遗留（AC-010 为 [deploy]，云端无 Docker/真实 Chrome；经用户 2026-11-18 裁定打勾视为流程完成、真实验证延期本地统一补验）
- 内容：在隔离真实部署（生产 Compose、官方 Chrome、4 个隔离 Profile、真实字体）上验证：
    1. 稳态 10 分钟窗口内 policy 临时容器建/毁次数为零、巡检 DNS docker exec 次数为零（按容器 ID 与 exec ID 计数，测量器命令单列）；
    2. 注入实际双栈规则漂移、Policy Agent 故障（kill/UDS 阻塞）、Supervisor 重启三类故障窗口，记录网络正负请求与页面状态：Browser 漂移确认双栈封闭或预算内暂停精确目标、Agent 故障 30 秒内恢复可信观测或隔离、重启后接管正确 Agent 且不重建健康 Browser；
    3. Stream 漂移只替换 Stream/对应 Agent，Browser ID、IPC、页面与数据不变。
- 处理：未开

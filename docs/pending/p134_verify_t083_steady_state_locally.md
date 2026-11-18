---
pid: "p134"
slug: "verify_t083_steady_state_locally"
status: "todo"
---
# p134 本地补验 t083 AC-009：4 Profile 稳态 10 分钟零 churn/exec/字体正文读取

- 来源：t083 遗留（[deploy] AC-009，用户 2026-11-18 裁定云端不可验者登记本地统一补验）
- 内容：在 Mac 隔离真实栈（正式 Compose、容器化 Supervisor、真实字体与 Chrome）上建 4 个隔离 Profile 并进入稳态，用 t083 交付的 `scripts/steady_state_probe.py` 采样 10 分钟窗口（暖机与测量窗口分开）：正式栈产生的 policy 临时建毁、巡检/健康 Docker exec、API 字体正文读取须均为零；实例不重启；Cookie/localStorage、页面、下载完整；计数口径（exec_create 只记一次、exec_start/exec_die 为阶段事件）与测量器自身开销单列可复核。云端无 Docker/真实 Chrome，无法执行。
- 处理：未开

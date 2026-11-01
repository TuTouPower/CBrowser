# p006 Browser 容器可读 Stream Agent 凭证

- 来源：t007 评审遗留（t007_code_f001 范围外观察，t005/t006 既有）
- 内容：Supervisor 把 `agent_secret.txt`（0644）写在 `runtime/<profile_id>/`，该目录以 rw 挂进 Browser 容器（`/run/cbrowser/runtime`），不可信网页沙箱可读到 Agent 注册凭证。应像 t007 处理 Selkies token 一样移到只挂给 Stream 的 `runtime/.secrets/<profile_id>/` 并收紧为 0600，补 Browser 容器内不可读的真实 E2E。t007 未改：属 t005/t006 既有行为，超出 t007 契约。
- 处理：review_20261101_075819/A5；resolution=resolved；reason=agent_secret 迁至 secrets/<profile>/agent_secret.txt 0600 且仅 Stream 挂载；内部 token 统一校验 0600。闭环 A5。

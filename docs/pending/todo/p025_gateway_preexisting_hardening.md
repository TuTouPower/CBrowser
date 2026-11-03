# p025 Gateway 两处存量加固（t022 code review 顺带发现，非 t022 引入）

- 来源：t022 full review 第 1 轮 code 路 f007(b)/f008（审阅者明确标为非本次引入的存量行为，处置为另立条目不在 t022 范围内顺手改）
- 内容：
    1. `gateway/server.py` 查看器授权路径的 `AuthorizationThrottle`（viewer token 授权失败节流）来源映射无 max_sources 类上限：被伪造来源打满时映射可无界增长。t022 已为 `RegistrationThrottle` 建立双预算 + 来源淘汰模式，此处应按同一模式补齐上限与淘汰，并补对应单测。
    2. Agent pump 的 tunnel 分支在 `validate_agent_envelope` 之后是否需要对每条 tunnel 消息复检 profile/instance/session 身份（当前仅在部分分支校验，join/leave 路径主要依赖 envelope 校验与注册时身份）：需先裁决威胁模型（已认证 Agent 连接内伪造 conn_id 的影响面），再决定补每消息复检还是维持现状并成文。
- 处理：未开

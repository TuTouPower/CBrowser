# p022 人机控制权模型与交接机制（需新 ADR）

- 来源：借鉴 ego-lite 技术调研 / 用户提出
- 内容：制定并落实 Profile 级人机控制权模型（撰写新 ADR），解决外部真人经 WebRTC/X11 操作与 Agent 经 CDP 操作同一 Profile 时的冲突问题：1. 定义 Profile 级 `control_owner: agent | user` 状态机与持久化，经 SSE 向前端广播；2. 处于 user 控制时，Supervisor CDP 隧道拦截 Mutating 指令并返回稳定错误码与 reason；3. 确立人类物理输入优先抢占机制，Agent 遭遇验证码/2FA 时主动触发 handOff；4. 前端在页头/侧栏展示交接状态（不违背 ADR 006 铺满无遮挡原则）。
- 处理：未开

# p029 人机控制权模型与交接机制（需新 ADR）

- 来源：借鉴 ego-lite 技术调研 / 用户提出
- 原始登记内容：制定并落实 Profile 级人机控制权模型（撰写新 ADR），解决外部真人经 WebRTC/X11 操作与 Agent 经 CDP 操作同一 Profile 时的冲突问题：1. 定义 Profile 级 `control_owner: agent | user` 状态机与持久化，经 SSE 向前端广播；2. 处于 user 控制时，Supervisor CDP 隧道拦截 Mutating 指令并返回稳定错误码与 reason；3. 确立人类物理输入优先抢占机制，Agent 遭遇验证码/2FA 时主动触发 handOff；4. 前端在页头/侧栏展示交接状态（不违背 ADR 006 铺满无遮挡原则）。
- 处理：未开

## 分析基线

- 分析时间：2026-11-04T00:00:12+08:00。
- CBrowser 基线：main@bba5412b623729e3fb44d5c8b9d2ef150fb60604；工作区含既有前端未提交改动。
- 证据范围：源码、现行文档与 backlog 静态核对；未运行测试、复现实验或外部站点验证。
- 以下方案与验证条件均为分析建议，决策待定；原处理状态和目录归属保持不变。

## 当前边界与主要冲突

- 当前架构按 ADR 007 废弃排他控制租约与接管锁，同一 Profile 可有多个 ViewerConnection 并发输入。
- 原登记的 Profile 级 control_owner 是新模型提案，尚未作为当前实现或生效 ADR。
- 新模型若只仲裁“外部自动化与真人”，可与多个真人 Viewer 并存；若同时限制真人 Viewer，则改变现行并发输入契约，必须明确替代关系。
- 自动化通路当前原样透传 CDP。Supervisor 能观察外部 CDP，却不在全部 WebRTC 输入数据路径上；仅在 Supervisor 修改状态不能自动完成真人输入抢占。
- ADR 006 要求操控页纯画面、管理收纳 /manage。页头/侧栏状态展示需明确落点，不能仅声明“不违背”就视为已协调。
- Ego 的 task.handOff 调用闭源 ego.handOffTaskSpace；开源 harness 只展示接口和本地 gate/ledger 协作，不能证明 CBrowser 已有等价强制能力。

参考：[现行 ADR](../../blueprint/decisions.md)、[架构对象与输入模型](../../blueprint/architecture.md)、[自动化契约](../../blueprint/automation.md)。

## 分析意见与方案取舍

### 控制权语义

1. 首先区分 Profile 人机控制权、真人 Viewer 连接身份与内部 Tab 管理权。三者不同，不宜合并成一把通用租约。
2. 原 agent | user 二态是否足够，需要明确默认值、浏览器重启、Agent 崩溃和用户离开后的行为。不能把持久化旧 agent 状态自动视为当前 Agent 仍获控制。
3. 交接完成应有可观察边界：哪些后续命令被拒、已发送命令如何处理、什么时候允许恢复。状态写入与 SSE 到达不是撤销已发送浏览器动作的证明。
4. 持久化遵循 API 唯一 SQLite 写入者；Supervisor/Agent 可执行策略和上报，不自行增加第二个 DB 写入端。

### CDP 强制执行

仅按 CDP 方法名拦截“Mutating”不可靠：Runtime.evaluate / Runtime.callFunctionOn 内的任意脚本也能修改页面；Browser/Target 命令还可能影响整个浏览器。不能把若干黑名单作为完整隔离保证。

较简单的首版候选是：user 控制期间暂停或断开外部自动化通道，并拒绝重新建立可操作通道；需要观察时通过受限接口或远程画面提供。此方案比支持任意“只读 CDP”更容易定义和验证，但会限制 Agent 观察能力，需另行决策。

若保留任意 CDP，则必须承认方法分类边界，定义可强制的能力范围、跨 session/target 行为和拒绝响应；不能声称任意 JS 只读安全。

### 真人优先与交接来源

- 远程真人输入经 WebRTC/Stream 进入，触发检测应放在实际输入来源可辨识的位置；仅监听 X11 最终事件可能无法区分真人与 Agent XTEST。
- 抢占可以先阻止后续自动化动作，不能假定已在 Chrome 执行的动作可回滚。
- CAPTCHA/2FA handOff 属主动交接；权限弹窗 handOff 与 p032 联动。自动恢复 Agent 控制还是显式恢复尚待决定。
- 多个外部 Agent 同时连接时，Profile 级二态未区分 Agent 身份；是否只允许一个协作 Agent、如何处理竞争，也需明确。

## 后续决策与验证条件（候选，未执行）

|待决策问题|应补证据或定义|
|---|---|
|是否保留真人多 Viewer 并发|ADR 007 关系与可观察输入行为|
|user 状态允许哪些自动化能力|具体可执行边界，不以“Mutating”泛称代替|
|谁是状态权威、谁负责拦截|API 持久化、Supervisor/Agent 执行与失联行为|
|交接期间在途命令如何处理|触发输入与后续自动化命令的时序、拒绝和完成边界|
|默认值、重启与异常恢复|不复用过期实例或过期授权的规则|
|控制状态展示位置|符合 ADR 006 的具体界面方案|

候选验证包括长连接已建立后真人接管、接管后重连拒绝、任意 evaluate 无旁路、过期实例状态隔离、多个 Viewer 继续存活及恢复后新动作可用。本轮未设计新 ADR、未修改状态机，也未批准上述候选方案。

## 关联条目与 Ego 入口

- p028：CDP/XTEST 的实际输入路径与限制。
- p030：执行器对暂停、交接与稳定错误的消费。
- p032：JS Dialog 不应默认切换人机控制权，权限提示按已定规则交接。
- p033：内部页面来源与清理权限独立于 Profile 控制权。
- Ego 参考版本 12407167f84a58af24044f072868051952131491；入口为 ego-lite/AGENTS.md、package/ego-browser/src/page-model.ts 中 handOff 及原生 binding 调用。本地源码不能证明闭源浏览器实现细节。

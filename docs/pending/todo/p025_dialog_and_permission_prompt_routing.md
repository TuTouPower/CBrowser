# p025 Dialog 与权限弹窗分流及管道挂起防御

- 来源：借鉴 ego-lite 技术调研 / 用户提出
- 原始登记内容：实现浏览器弹窗分流与生命周期可靠性防护：1. 弹窗分流规则：alert、confirm、prompt、beforeunload 等页面级 JS Dialog 路由给 Agent 自动响应处理；摄像头、麦克风、地理位置、USB 等系统级权限弹窗路由给人类处理；2. 建立 Chromium 命令管道挂起防御：针对原生 JS Dialog 弹出期间 Chromium 挂起渲染线程、导致后续所有页面命令（含 Page.enable）超时崩溃的问题，在 CDP 代理层与客户端设立即时监听拦截与超时熔断恢复策略。
- 处理：未开

## 分析基线

- 分析时间：2026-11-04T00:00:12+08:00。
- CBrowser 基线：main@bba5412b623729e3fb44d5c8b9d2ef150fb60604；工作区含既有前端未提交改动。
- 证据范围：源码、现行文档与 backlog 静态核对；未运行测试、复现实验或外部站点验证。
- 以下方案与验证条件均为分析建议，决策待定；原处理状态和目录归属保持不变。

## 当前情况与 Ego 证据边界

- CBrowser 当前 CDP 代理主要原样透传，没有据此形成完整 Dialog 路由、跨 CLI 调用状态恢复或权限提示交接契约。
- Ego 文档记录 alert/confirm/prompt 的实际回归及 beforeunload 尚存缺口，并描述调用退出后 Dialog 残留、下一调用 Page.enable 等命令超时的问题。
- 上述属于特定 Ego 版本与其原生桥接行为，不能推定 CBrowser/Chromium 所有命令在所有场景都会挂起；需要在目标引擎和会话拓扑下复现。
- Ego 的文档可提供故障模型和验收案例，不能作为 CBrowser 已验证事实。

参考：[Browser Agent](../../../src/backend/cbrowser/runtime_agent/agent.py)、[CDP manager](../../../src/backend/cbrowser/runtime_agent/cdp_proxy.py)、[现行自动化链路](../../blueprint/automation.md)。

## 分析意见

### 分流与默认策略

1. 页面 JS Dialog 由 Agent 处理，应理解为提供可编程应答能力，不是默认全部 accept。confirm、prompt 和 beforeunload 的肯定响应可能改变业务结果或放弃未保存内容。
2. alert、confirm、prompt、beforeunload 应分别定义无 handler 时行为、超时、错误和返回值；默认策略待决策。
3. 摄像头、麦克风、定位、USB 等权限提示或设备选择器交给真人是目标方向，但能否检测、是否有统一事件、哪些需要 XTEST/原生 UI 路径尚未验证。
4. JS Dialog 不应自动触发 p022 的人机交接；权限提示交接则需明确进入 user、暂停动作和恢复条件。
5. 文件选择器与权限提示不能混为一类；文件上传可有独立受控路径，仍需按具体契约判断。

### 命令挂起与跨调用恢复

- 监听应在触发动作前建立；click、navigate 或文件设置可能尚未返回就已弹出 Dialog，处理响应不能排在该命令完成之后。
- 保持事件与应答可并发，避免把所有 CDP 命令串在一条会被触发动作占住的队列。
- Dialog 可能跨 CLI 进程存在。仅保存在执行器内存的状态不够；现有常驻 Browser Agent 是候选承载点，但其 page session 观察、事件覆盖与恢复方式仍需验证。
- 后续会话必须能识别仍打开的 Dialog，并在页面命令不响应时仍有明确恢复路径；不能只靠再次 Page.enable 后等待事件。
- 多个 CDP 客户端同时存在时，需明确 Dialog 处理责任，避免客户端默认 dismiss、重复应答或不同策略竞争。
- 超时后的结果可能未知，不能自动重放整个 click/提交动作，也不能把关闭整个 Profile 当默认恢复手段。

### 与现有架构关系

代理层若开始观察、记录或处理 Dialog，将超出单纯透明转发职责。应先确定由客户端处理哪些逻辑、Browser Agent 常驻观察哪些状态，避免 API/Supervisor/Agent 三层都保存独立且易漂移的弹窗真相。

## 后续验证条件（候选，未执行）

|场景|需要证明的行为|
|---|---|
|真实点击触发 alert/confirm/prompt|打开/关闭事件正确，接受、取消和 promptText 返回值正确|
|beforeunload|具备真实激活条件，区分未触发与已正确处理；不能因没有事件就记通过|
|文件设置 change handler 打开 confirm|原始设置命令仍 pending 时也可响应，随后命令与页面恢复|
|调用退出时仍有 Dialog|下一调用能发现并恢复，不丢失状态或误判页面失效|
|页面命令超时|错误清晰且可收敛，不自动重放业务动作，不关闭用户其他页面|
|权限与设备提示|真人可见、交接正确，恢复规则明确，不被 Agent 静默授权|
|多客户端|只有按契约获准处理的一方应答，其余连接不制造冲突|

## 关联与 Ego 入口

- p021：先核对目标 Playwright/CDP 会话是否支持所需事件与并发应答。
- p023：基础 Dialog 处理宜进入最小执行器；跨调用恢复单独验证。
- p022：权限提示的人机交接；p026：按 target/page 关联弹窗和清理。
- Ego 参考版本 12407167f84a58af24044f072868051952131491；入口为 ego-lite/docs/native-javascript-dialog-requirement.md、package/ego-browser/src/browser-runtime.ts 与 scripts/real-browser-e2e/cases/page-dialogs.mjs。文档涉及 0.5.0.12、0.5.2.2 的历史观察，不能混同为所有版本已修复或本项目现状。

# p026 Agent 与用户 Tab 归属隔离与生命周期保护

- 来源：借鉴 ego-lite 技术调研 / 用户提出
- 原始登记内容：在人和 Agent 共用同一 Profile 浏览器窗口的场景下，建立标签页归属管理与安全退出机制：1. 维护标签页所有权元数据（如 `openedBy: agent | user`），为页面分配稳定逻辑标识；2. 支持外部已打开页面的接管机制（`adopt`）；3. 任务结束与资源清理时，严格执行生命周期保护：仅关闭由 Agent 创建或明确接管的页面，绝不误关或刷新人类用户原有的标签页。
- 处理：未开

## 分析基线

- 分析时间：2026-11-04T00:00:12+08:00。
- CBrowser 基线：main@bba5412b623729e3fb44d5c8b9d2ef150fb60604；工作区含既有前端未提交改动。
- 证据范围：源码、现行文档与 backlog 静态核对；未运行测试、复现实验或外部站点验证。
- 以下方案与验证条件均为分析建议，决策待定；原处理状态和目录归属保持不变。

## 当前边界与 Ego 借鉴

- CBrowser 当前区分 Profile、BrowserRuntime 与 ViewerConnection；本条管理的是容器内 CloakBrowser 的内部 Tab，不是外部 Chrome 操控页。
- 关闭外部 ViewerConnection 不应关闭 BrowserRuntime；同样，执行器连接退出不应隐式停止 Profile。
- 原登记使用 openedBy: agent | user，但实际来源可能未知；不能把无法证明来源的页面默认归为 Agent。
- Ego 区分 managed/unmanaged 页面并保留 openedBy；adopt 沿用页面原始来源，finish 批量清理只选择 openedBy 为 agent 的页面。
- 因此“adopt 纳入管理”不应直接被解释为“可以在任务结束自动关闭”。原登记把两者连在一起，需进一步明确授权含义。

参考：[领域对象](../../blueprint/domain.md)、[架构并发连接边界](../../blueprint/architecture.md)、[Browser runner 生命周期](../../../src/backend/cbrowser/runtime_agent/runner.py)。

## 分析意见

### 三类概念分开

1. 来源：页面由谁创建；不因 adopt 而改写。
2. 管理权：当前任务是否可定位和操作页面；与 p022 的 Profile 人机控制权共同生效。
3. 清理权限：任务结束是否可以关闭页面；不能只由 managed=true 推导。

最简单的首版候选是：自动清理只关闭可证明由本任务创建的页面，adopt 的用户/未知来源页面默认保留；确需关闭时采用明确动作与授权。是否需要独立关闭权限字段，取决于后续实际契约，不预先增加通用权限框架。

### 页面身份与发现

- 稳定逻辑标识应绑定当前 Profile/runtime 与 target，URL、标题和数组下标都不能作为唯一身份。
- 浏览器重启后不能复用旧 target 映射；用户自行关闭页面后，旧句柄应明确失效，不能重新绑定到另一个页面。
- 任务启动前已有页面构成用户/未知来源基线；启动后出现的所有页面也不能一律归为 Agent，因为用户可能同时新建。
- Agent 点击产生的 popup 可结合 opener、动作时序与既有账本判断；证据不足保持未知。
- 多个 Agent 同 Profile 时，openedBy: agent 仍不足以证明属于当前任务；若允许此场景，需区分具体任务身份及并发操作规则。

### 清理与退出

- 禁止用 browser.close、context.close 或关闭整个 Profile 作为普通任务清理捷径。
- 最后一个内部 Tab 关闭可能触发浏览器退出，需在目标引擎验证并确定保留策略；不能直接照搬 Ego 创建 about:blank 锚点行为。
- adopt 不应刷新或导航用户既有页面来建立身份；发现与记账应尽量避免焦点变化。
- 超时、取消、异常退出后的恢复也要遵守同样清理范围，不能失败时扩大删除。
- p022 控制权转给 user 后，任务自动清理是否仍可执行需明确；不能借清理绕过真人接管。

## 后续验证条件（候选，未执行）

|场景|需要证明的行为|
|---|---|
|用户已有 Tab，Agent 新建另一个 Tab|任务清理只影响 Agent 明确获准清理的页面|
|adopt 用户页面|原始来源保留，默认清理策略明确，不误刷新或关闭|
|未知来源与用户同时新建|来源不误归 Agent，清理保持保护|
|popup、iframe 与跨站导航|popup 归属可解释；iframe 不被当独立用户 Tab；页面逻辑身份不靠 URL|
|用户关闭页面或 runtime 重启|旧句柄失效，不误绑定新 target|
|最后一个内部 Tab|不会意外停止应保留的 BrowserRuntime，或按明确规则报告|
|异常退出与人机交接|连接、账本与清理幂等收敛，用户其他页面持续可用|

## 关联与 Ego 入口

- p023 首版就需要最小页面归属保护，不宜推迟到完整 snapshot SDK 完成后。
- p022 控制权与本条页面权限互补，不能互相替代。
- p025 的弹窗状态应绑定页面身份，页面关闭后清理相关状态。
- p021 的 XTEST 共享焦点能力不等于 Tab 隔离；本条不能承诺真人与 Agent 在同窗口同时输入互不干扰。
- Ego 参考版本 12407167f84a58af24044f072868051952131491；入口为 ego-lite/package/ego-browser/src/page-model.ts 的 adopt、finish、close，及 page-ledger.ts。借鉴范围为开源账本与清理语义，闭源 TaskSpace 行为本轮未验证。

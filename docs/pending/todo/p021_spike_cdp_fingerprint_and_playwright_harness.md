# p021 Spike：验证 Playwright CDP 兼容性、指纹保持度与 XTEST 路径

- 来源：借鉴 ego-lite 技术调研 / 用户提出
- 原始登记内容：开展前置技术探路（Spike），验证三项关键契约：1. Playwright 通过 `connectOverCDP` 经 API/Supervisor `cbat_` 隧道双向通信及弹窗/下载的连通性；2. 外部客户端建立 CDP 长连接并启用相关域（如 Runtime/Page）时，CloakBrowser 隐私指纹在 BrowserLeaks/CreepJS/Pixelscan 下是否发生衰退或留下自动化探测痕迹；3. 在 Browser 容器 Xvfb 环境内通过 XTEST 注入键鼠事件的可行性及窗口坐标换算精度。
- 处理：未开

## 分析基线

- 分析时间：2026-11-04T00:00:12+08:00。
- CBrowser 基线：main@bba5412b623729e3fb44d5c8b9d2ef150fb60604；工作区含既有前端未提交改动。
- 证据范围：源码、现行文档与 backlog 静态核对；未运行测试、复现实验或外部站点验证。
- 以下方案与验证条件均为分析建议，决策待定；原处理状态和目录归属保持不变。

## 当前基础与 Ego 借鉴边界

- CBrowser 已有认证 CDP 通路：外部客户端 → API 自动化入口 → Supervisor → Browser Agent UDS → Chrome loopback；凭证为限定 Profile 的 cbat\_ token，不需要先新建另一套直连端口。
- Browser runner 已通过 CloakBrowser SDK 启动 persistent context，Browser Agent 也已有常驻 CDP 连接。因此实验基线应是现行运行时，不应假设当前完全没有 Playwright/CDP。
- 既有 UDS/下载证据只支持对应链路能力，不能证明 Playwright connectOverCDP 兼容、指纹无变化或 XTEST 精度。
- Ego 参考版本：12407167f84a58af24044f072868051952131491。其 AGENTS.md 明确仓库提供开源 harness，浏览器本体与 globalThis.ego 原生绑定不在开源范围；控制权、snapshot 等能力不能直接照搬。
- Ego pointer/keyboard 源码仍含合成事件回退，不能把参考项目整体视为“无 isTrusted:false”或指纹安全实现。

参考：[现行自动化链路](../../blueprint/automation.md)、[Browser runner](../../../src/backend/cbrowser/runtime_agent/runner.py)、[CDP manager](../../../src/backend/cbrowser/runtime_agent/cdp_proxy.py)、[d002](../../findings/d002_cdp_uds_download_recovery.md)。

## 分析意见

本条是自动化执行器选型的前置研究，价值高于立即建设完整 SDK。建议保留一个 Spike 入口，分三类结论，不把“连通”“指纹无新增退化”“输入精度满足要求”混为一个通过标志。目标版本与实际执行时间待定。

### Playwright 兼容性

- 验证经正式认证 WS URL、Authorization 头和 UDS 隧道建立 browser-level CDP 连接，检查默认 context、既有页面、popup、iframe 与下载行为。
- 检查多客户端共存、断开重连和资源释放；执行器断开不应关闭用户浏览器或覆盖既有下载捕获策略。
- 对不兼容部分记录具体方法、事件、响应和版本，避免仅凭 echo 或单个 Runtime.evaluate 成功判定兼容。

### 指纹增量

- 对照现行 runtime，分别比较新增原始 CDP attach、Playwright attach、启用 Runtime/Page、snapshot/locator 观察与实际输入。
- 固定 Profile seed、引擎版本、配置、视口与测试条件，多次对照；保存具体字段和检测证据，不能仅比较外站总分。
- BrowserLeaks、CreepJS、Pixelscan 可作为候选外部观测面；本轮未访问，也未验证当前页面行为。外站波动与网络因素应与工具新增影响分开。
- isTrusted 为 true 不是“不可检测”的充分条件；禁止合成事件回退只是约束之一，仍需检查观察与驱动路径实际暴露。
- 当前 runner 已有 SDK/CDP 活动，结论应写“额外连接或动作是否产生新增变化”，不能夸大为证明完全没有自动化痕迹。

### XTEST 输入

- Xvfb 启动检查中已有 XTEST 要求，但尚未证明外部 Agent 受控注入、跨缩放坐标换算与复杂交互全部成立。
- 验证 CSS viewport、浏览器内容区、窗口装饰、DPR、滚动、iframe 与屏幕坐标之间关系。
- XTEST 依赖共享窗口焦点，不提供同窗口多 Tab 并行输入隔离；与 p022 控制权及 p026 页面归属联动。
- 是否采用 XTEST 应由精度、功能覆盖与指纹增量证据决定。若 CDP 输入满足需求，不宜仅为猜测收益维护第二套输入路径。
- 保持 Browser Agent 受控 RPC 边界，不引入任意 shell 命令入口。

## 候选输出与判断门槛（未执行）

|输出|需要回答的问题|对后续影响|
|---|---|---|
|兼容性矩阵|Playwright 哪些操作可经现有认证链路稳定完成，哪些需要适配|决定 p023 驱动与连接方式|
|指纹对照记录|哪些连接、域启用、观察与输入动作引入可重复新增变化|决定允许的观察/输入能力及限制|
|输入路径比较|CDP 与 XTEST 的精度、焦点冲突、原生 UI 能力和实际收益|决定是否需要第二套驱动|
|生命周期记录|客户端断开后页面、浏览器、下载捕获是否保持正确|约束 p023、p025、p026|

## 关联与未决策事项

- p023 明确依赖兼容性与驱动结论；p022、p026 的模型设计可先讨论，但实现方式需引用实际能力证据。
- p025 的“弹窗触发命令未返回仍可响应”可作为兼容性探针；完整跨调用恢复属于其自身议题。
- 本条只记录研究建议；未创建 Spike、未批准 Playwright 最终选型、未执行外站或 XTEST 实验。
- Ego 复核入口：ego-lite/AGENTS.md、package/ego-browser/src/browser-runtime.ts、driver/pointer.ts、driver/keyboard.ts。版本固定如上，后续升级应重新核对。

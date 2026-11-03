# p023 基于 Playwright 的 Code-as-Action Agent 执行器与 Skill

- 来源：借鉴 ego-lite 技术调研 / 用户提出
- 原始登记内容：为外部 AI Agent 提供轻量宿主端执行工具链与 Skill：1. 提供 CLI 执行器（`cbrowser-agent <<'JS'`），支持单次会话批处理执行多步页面动作、等待与结果提取；2. 优先基于 Playwright `connectOverCDP` 实现底层交互，避免重复造轮子；3. 集成带引用的 aria snapshot 或可访问性树紧凑表征，建立 stable locator 与 `@refId` 持久映射；4. 驱动细节遵循反检测最佳实践，严禁使用 `isTrusted: false` 的合成事件兜底与全局探测变量；5. 实现两层 Skill 架构（薄入口 Skill + 随 CLI 动态下发规范）。
- 处理：未开

## 分析基线

- 分析时间：2026-11-04T00:00:12+08:00。
- CBrowser 基线：main@bba5412b623729e3fb44d5c8b9d2ef150fb60604；工作区含既有前端未提交改动。
- 证据范围：源码、现行文档与 backlog 静态核对；未运行测试、复现实验或外部站点验证。
- 以下方案与验证条件均为分析建议，决策待定；原处理状态和目录归属保持不变。

## 当前基础与范围判断

- 现有 API/Supervisor/Browser Agent 已提供限定 Profile 的认证 CDP 隧道；可优先复用，不另暴露 Chrome CDP TCP 端口。
- 现有链路以透明转发为主，并未等同于提供宿主 CLI、页面账本、snapshot/ref 生命周期或人机控制权。
- 原登记同时包含执行器、Playwright 驱动、紧凑 snapshot、引用注册表、反检测要求与双层 Skill，整体已接近一套 SDK，不能按“轻量 CLI”估计全部复杂度。
- Playwright connectOverCDP 经现有通道的实际兼容性与指纹增量由 p021 判断；当前是优先候选，非已验证最终选型。
- Ego 的代码执行、引用管理和双层 Skill 可借鉴；原生 snapshot、TaskSpace 控制权等依赖闭源绑定，不能原样移植。

参考：[自动化契约](../../blueprint/automation.md)、[API 自动化入口](../../../src/backend/cbrowser/api/v1/automation_router.py)、[Browser Agent](../../../src/backend/cbrowser/runtime_agent/agent.py)。

## 分析意见

### 最小执行器候选范围

先界定认证连接、选择或创建页面、单次 JS 内多步动作/等待/提取、结果/错误输出、安全断开。凭证由用户现有安全来源注入，不能打印 token、写入生成 Skill 或放入全局探测变量。

宿主执行器与 Browser Agent 的信任边界应保持分离；Code-as-Action 不代表允许向 Browser Agent 发送任意 shell。断开自动化连接也不代表关闭浏览器、context 或用户页面。

首版必须同时具备 p025 的基础 Dialog 响应与 p026 的安全页面清理。跨调用恢复、复杂 snapshot/ref 与完整人机协作可分别评估，不宜等到任务收尾才补生命周期保护。

### Snapshot、locator 与 ref

- “持久映射”只表示可跨 CLI 调用保存映射，不表示 DOM 引用永久有效。
- 引用至少需要绑定当前 runtime、target、frame、document 与节点身份；导航、节点替换、实例重启或页面关闭后失效。
- ref 缺失或来源不明时重新 snapshot，不能静默把旧 ID 绑定到另一节点。
- stable locator 应唯一解析到产生快照的同一节点；只有名字相同或 selector 能命中不够。
- iframe/OOPIF 的节点标识需保留 frame 来源，避免不同 renderer 的 backendNodeId 相同导致误操作。
- 不宜在需求尚不清楚时同时开发 Playwright locator 与另一套完整解析器；先确认已有依赖能满足哪些行为。

Ego 自身会按 document 变化失效 ref，也会保留 target/frame 来源，不能把其跨轮引用理解成永久稳定句柄。

### 反检测与驱动

- 禁止 isTrusted:false 合成事件兜底是原始要求，不能通过复用 Ego 老驱动悄悄放宽。
- Ego pointer/keyboard 仍含 dispatchEvent 回退与页面内探针；参考的是能力组织和接口，不能整体视为符合本项目约束。
- trusted 输入不是不可检测证明；locator、snapshot、事件探针与驱动注入均需进入 p021 的增量对照。
- XTEST 是否需要作为第二驱动，依据 p021 结果决定，不预先增加双路径配置与维护负担。

### 状态与 Skill

- 跨进程只持久化确有需要的页面/ref 元数据；CDP session、objectId 和连接状态不能未经验证直接跨进程复用。
- 是否需要新常驻服务取决于 p025 跨调用弹窗恢复等需求；先检查现有 Browser Agent 能否承载，不为“持久化”默认增加 daemon。
- 保留薄入口 Skill + CLI 动态版本化规范的方向。接口文档随执行器版本输出，减少入口 Skill 与实现漂移。
- 规范应解释实际可用 API、错误与生命周期，不能把内部实现细节塞入用户流程。

## 关联与后续验证条件（候选，未执行）

|关联|需要解决的边界|
|---|---|
|p021|Playwright/CDP 兼容性、指纹增量及输入路径选型|
|p022|user 控制时拒绝、暂停与恢复语义；CLI 不能仅靠自觉遵守状态|
|p025|动作未返回时仍可处理 Dialog，跨调用残留有恢复路径|
|p026|默认只清理有明确权限的内部 Tab，客户端退出不停止 Profile|
|p024|经验包依赖稳定 API；当前不纳入执行器首版|

候选验证覆盖多步成功与中途失败、超时/取消、导航后 ref 失效、iframe/OOPIF 定位、popup 归属、下载捕获恢复及连接退出后用户页面继续可用。本轮未创建 CLI/Skill、未批准分期实现或最终选型。

## Ego 依据

版本 12407167f84a58af24044f072868051952131491；复核入口为 ego-lite/AGENTS.md、package/ego-browser/src/run.ts、browser-runtime.ts、page-ref-registry.ts、page-ledger.ts、driver/observe.ts、driver/pointer.ts、driver/keyboard.ts，以及 package/ego-browser/skill-body/SKILL.md。源码观察只支持对应实现结构，不代表闭源产品效果已在本项目复现。

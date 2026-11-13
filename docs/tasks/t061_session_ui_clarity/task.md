# Task spec

## 背景

会话 UI 三项诉求属于同一页面交付。详情面板关闭仍占宽、正常握手显示故障诊断卡片、顶栏状态重复且传输状态未本地化。t058 明确排除这三项，当前代码仍保留问题。

## 契约区

### 范围

- 顶部详情按钮成为面板唯一开关；关闭面板释放宽度，保留既有开关持久化。
- 正常连接过渡态只显示轻量等待指示；故障态保留诊断与恢复入口。
- 环境切换触发器仅显示名称；列表保留运行状态；顶栏运行状态去重，顶栏与详情传输状态随界面语言切换。

### 非范围

- 不改变传输、重连、控制权或后端生命周期。
- 不更改 DESIGN.md token 体系；不覆盖此前独立提交的重连按钮契约。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：点击顶部详情按钮关闭后，右侧面板不占布局宽度；再次点击恢复详情，刷新后保持已选择状态，面板内部无第二组开关与标题行。
- [ ] AC-002：checking_runtime、connecting_signaling、connecting_ice、media_waiting、reconnecting、stopping 等正常过渡阶段仅显示轻量等待指示，不显示居中诊断表与操作按钮。
- [ ] AC-003：signaling_failed、ice_failed、media_no_frames、web_locks_unavailable、error 等故障阶段仍展示诊断与适用恢复动作；runtime_not_ready 按启动入口保留可操作提示。
- [ ] AC-004：中文和英文界面中 ready/recovering/failed/unknown 均显示对应翻译，顶栏与详情一致，不直接显示原始机器码。
- [ ] AC-005：顶栏环境触发器不含状态徽标，运行状态只显示一次；切换下拉列表仍显示各环境状态。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；涉及真实 Chrome、引擎、Docker 或网络行为的 AC 使用隔离真实环境探针，不以 mock 结果替代。界面视觉补人工核验，第三方公网检查仅显式 opt-in。

## 上下文区

- 来源：`p061`、`p064`、`p065`。2026-11-13 核实 SessionDetailsPanel.tsx 的固定 w-details 与内部开关、SessionHeader.tsx 的 label={transportState}、EnvironmentSwitcher.tsx 的重复徽标、SessionStagePanel.tsx 全阶段诊断容器；SessionPage.test.tsx 已覆盖开关持久化。当前 HEAD 的独立按钮调整未修复上述布局与分级。

### 有意不测

- 不改变传输、重连、控制权或后端生命周期。：超出本 task 范围；其余已声明 AC 不豁免。

### 测试策略

- 组件覆盖开关占位、状态翻译与过渡/故障矩阵；页面测试覆盖顶部按钮及持久化。
- Chrome E2E 覆盖等待到首帧、断线故障及侧栏切换；就绪条件采用真实帧信号，避免依赖大卡片消失。旧测试若固化过时视觉语义，整体替换并说明理由，不就地改预期追随实现。
- 项目门禁：按 docs/blueprint/testing.md 的 doctor_cmd / test_cmd / blackbox_verify 执行；本批创建仅验证文档结构，不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。

### 风险与回退

- 风险：过渡态隐藏按钮可能误伤真正故障恢复；按明确阶段矩阵验证。
- 回退：回退本 task 实现 commit，恢复原组件与测试；无数据迁移。

### 依赖与约束

- 保持本机 Docker/OrbStack 与唯一外部 Chrome 客户端边界；不复活 parked 条目。依赖建议见 progress.md；产品 BLOCKING 未确认前不可 start，SPIKE 先验证后回填。

### Finalization 时更新的 blueprint

- docs/blueprint/testing.md：会话 UI 阶段分级、布局与本地化验收。

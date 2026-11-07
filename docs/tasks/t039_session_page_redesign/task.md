# Task spec

## 背景

`docs/plan_20261105_ui_redesign.md` 第 5.6 节（用户 2026-11-05 确认）：会话页成为独立页面 `/session/:profileId`，有单行页头、环境切换器、详情面板与专注模式；画面区只承载 Selkies iframe，不绘制模拟浏览器框（ADR 003、006）。2026-11-05 于 main@3101540 核实现状：会话页为 `features/profiles/BrowserSessionPage.tsx`（原挂在 `/`），会话阶段与恢复语义由 `features/browser-session/useBrowserSession.ts` 与 `adapter.ts` 实现，`docs/blueprint/frontend.md` 第 4 节列出全部阶段（含 `web_locks_unavailable`）；E2E 依赖 `browser-session-iframe` 与 `session-*` 系列 `data-testid`。t036 已把旧会话组件临时挂在 `/session/:profileId`；t043 已升级 Selkies；t035 已提供浏览器版本、活动时间、分组与代理数据；t041 已提供指纹平台、字体集与运行时字体状态。

## 契约区

### 范围

- `/session/:profileId` 会话页：
    - 单行页头：环境切换器（popover 内可搜索，按分组列出环境与状态，条目为链接）、observed state 与 transport 状态、待应用标记与「应用并重启」，以及音频、诊断、详情面板、专注模式、停止操作。
    - 画面区：iframe 铺满；非 `connected` 阶段显示居中状态面板与可执行操作，沿用 frontend.md 第 4 节全部阶段与恢复语义。
    - 详情面板：右侧 300px，默认收起，状态存 `cbrowser.session.details_open`；分环境、网络、指纹、运行四区（指纹区含平台、字体集与缺失字体告警；运行区含浏览器版本与 UA、实例 ID、配置版本、transport 状态、最近错误、启动时间），每个值可复制。
    - 专注模式：隐藏侧栏与页头，鼠标移到顶部边缘时显示悬浮工具条，可从中退出；不用 Esc 退出。
    - 剪贴板权限提示、音频状态、诊断浮层按设计系统重建，行为语义不变；只复用与 UI 无关的逻辑（如 `useBrowserSession`），不换皮旧组件（plan D16）。
- `/session` 会话入口：本标签页没有目标时，列出运行中的环境供选择；侧栏「会话」导航在本标签页已有目标时回到该会话。
- `data-testid` 按新组件结构命名，不沿用旧命名；会话 E2E 与组件测试同步改写选择器（plan D16）。
- 删除旧会话页组件；此时旧页面已全部替换，启用全局颜色门禁：扫描前端源码中的 Tailwind 默认调色板类与颜色字面量，发现即失败，接入 `scripts/run_gates.sh` 前端阶段，不设豁免。
- 新增与改动文案 en / zh 同步补键。

### 非范围

- 模拟浏览器框（标签栏、地址栏、书签、缩放）。
- 同窗口多会话分屏（p039 已暂搁）。
- 非安全上下文下的「需 HTTPS」降级（t042）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：`/session/:profileId` 保持 frontend.md 第 4 节的全部会话阶段与恢复语义，由新测试按新组件结构等价覆盖并通过（删除的旧测试在实施笔记逐条写明理由）；每个非 `connected` 阶段都显示原因与可执行操作。
- [x] AC-002：本标签页没有目标时，`/session` 列出运行中的环境链接；侧栏「会话」导航在本标签页已有目标时回到该会话。
- [x] AC-003：环境切换器可搜索，按分组列出环境与状态，条目为真实链接；切换器中的链接在新标签页打开后，两个标签页的会话互不影响。
- [x] AC-004：页头显示 observed state、transport 状态与待应用标记，可「应用并重启」，并提供音频、诊断、详情面板、专注模式、停止操作。
- [x] AC-005：详情面板默认收起，展开状态刷新后保持；面板中的值与 API 响应一致（含平台、`font_set_id` 与缺失字体、`browser_product`、`browser_user_agent`、实例 ID、配置版本、最近错误、启动时间），每个值可复制。
- [x] AC-006：进入与退出专注模式不重建 iframe、不中断远端输入；专注模式下鼠标移到顶部边缘时显示退出工具条；Esc 与会转发给远端的常用组合键不被宿主占用。
- [x] AC-007：全局颜色门禁接入前端门禁并通过；在任一前端源码文件中加入默认调色板类或颜色字面量时，门禁失败。
- [x] AC-008：真实栈会话 E2E 无头通过：同 Profile 多页面、复制标签页身份重映射、可见性暂停与恢复、应用并重启。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`docs/plan_20261105_ui_redesign.md` WP12 与第 5.6 节（2026-11-05 于 main@3101540 核实，结论见背景）。

### 有意不测

- 真实的 Chrome 标签页切换可见性事件：无头 Chrome 中标签页始终可见，用页内覆写 `document.visibilityState` 并派发 `visibilitychange` 来模拟（沿用现有做法）。

### 测试策略

- Vitest 覆盖页头、切换器、详情面板与专注模式；会话阶段测试走真实 `useBrowserSession`。
- 真实栈 E2E 保留现有会话用例的覆盖语义，按新路由与新组件结构改写选择器。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。

### 风险与回退

- 风险：页头或专注模式的布局变化触发 iframe 重建或 resize，导致远端分辨率变化或会话重连；宿主快捷键截获远端输入。
- 回退：回退本 task commit。

### 依赖与约束

- 依赖 t037（环境数据与共用组件；本 task 启用全局颜色门禁时，旧页面须已全部替换）与 t043（Selkies 升级）；经 t037 间接依赖 t035、t036、t041。
- 遵守 ADR 003、006：画面区只承载 Selkies iframe。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/frontend.md`：会话页布局、会话入口、专注模式、详情面板。
- `docs/blueprint/testing.md`：全局颜色门禁。
- `docs/specs/webrtc_remote_display.md`：会话页交互。

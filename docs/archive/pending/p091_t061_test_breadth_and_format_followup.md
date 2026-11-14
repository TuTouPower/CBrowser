# p091 t061 测试广度补强与一处格式对齐（review minor 遗留）

- 来源：t061 遗留（review_code f001、review_test f003/f004；均为 minor，不阻断 t061 PASS）
- 内容：
    1. `SessionDetailsPanel.tsx` 删除 `{open && (...)}` 后内容块缩进停留在旧层级，整体回退一层缩进对齐（纯格式，无行为影响；t061 审后未改是因其会使双路 review 指纹失效）。
    2. AC-004 测试广度：补中文界面下 transport 其余三态（recovering/failed/unknown）的顶栏断言，以及详情面板侧 transport 缺失/枚举外值的本地化兜底断言（当前仅顶栏测了枚举外回落、中文仅测 ready；实现共用单一映射 transport_state.ts，属覆盖广度缺口）。
    3. AC-007 测试广度：为「失败原因不含凭据」补显式断言（当前无任何断言；错误文案为固定 i18n 文案仅以关闭码为参数，风险低）。
- 处理：764fed0；resolution=resolved；reason=不立项直接改主分支：缩进对齐（git diff -w 空）、中文 transport 三态与详情面板兜底断言、AC-007 失败原因不含凭据显式断言；npm test 640 全绿、design 检查全 0
- 时间：2026-11-15T00:00:00+08:00

## 开发铁律重判与修复（2026-11-15）

- 重判：本项是零行为影响的格式化 + 断言广度缺口，按「简洁优先」不值得单独立项，直接改主分支即可；AC-007「失败原因不含凭据」是明确断言缺口，该补。
- 修复：`src/frontend/src/features/browser-session/SessionDetailsPanel.tsx` 内容块整体回退一层缩进（`git diff -w` 为空，纯格式）；`SessionHeader.test.tsx` 补中文 recovering/failed/unknown 三态顶栏本地化文案 + 不泄漏原始机器码；`SessionDetailsPanel.test.tsx` 补 transport 缺失/枚举外值回落断言；`useBrowserSession.transportRecovery.test.tsx` 与 `SessionStagePanel.test.tsx` 补 AC-007 显式断言（固定文案含关闭码 1006，不含 token/password/session/凭据）。共新增 4 用例、14 条断言，未删任何现有断言。
- 验证：`npm test --prefix src/frontend` 83 文件 / 640 测试全绿（含 tsc 类型检查）、`design:check` 与 `design:lint` 均 0。

## 本地补验证据（gate4，历史）

- 判定：本项是代码/测试实现增强（`SessionDetailsPanel.tsx` 缩进对齐、AC-004 中文 transport 三态与兜底断言、AC-007「失败原因不含凭据」显式断言），不属「带 Docker/真实 Chrome 的本地验证」范畴，本批次不授权改产品/测试源码凑覆盖。
- 现状：gate4 `frontend_test=0`、`design_check=0`、`unit 2243/0` 全绿，但仅说明现有断言通过，不等于 AC-004/007 的断言广度已补齐。
- 卡点：无本地环境卡点，纯属工作量与立项顺序；按 specs driven 拆 task 后实施。

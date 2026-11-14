# p091 t061 测试广度补强与一处格式对齐（review minor 遗留）

- 来源：t061 遗留（review_code f001、review_test f003/f004；均为 minor，不阻断 t061 PASS）
- 内容：
    1. `SessionDetailsPanel.tsx` 删除 `{open && (...)}` 后内容块缩进停留在旧层级，整体回退一层缩进对齐（纯格式，无行为影响；t061 审后未改是因其会使双路 review 指纹失效）。
    2. AC-004 测试广度：补中文界面下 transport 其余三态（recovering/failed/unknown）的顶栏断言，以及详情面板侧 transport 缺失/枚举外值的本地化兜底断言（当前仅顶栏测了枚举外回落、中文仅测 ready；实现共用单一映射 transport_state.ts，属覆盖广度缺口）。
    3. AC-007 测试广度：为「失败原因不含凭据」补显式断言（当前无任何断言；错误文案为固定 i18n 文案仅以关闭码为参数，风险低）。
- 处理：非本地补验项，本次不处理；保持 todo 待独立立项
- 时间：2026-11-14T19:07:00+08:00

## 本地补验证据（gate4）

- 判定：本项是代码/测试实现增强（`SessionDetailsPanel.tsx` 缩进对齐、AC-004 中文 transport 三态与兜底断言、AC-007「失败原因不含凭据」显式断言），不属「带 Docker/真实 Chrome 的本地验证」范畴，本批次不授权改产品/测试源码凑覆盖。
- 现状：gate4 `frontend_test=0`、`design_check=0`、`unit 2243/0` 全绿，但仅说明现有断言通过，不等于 AC-004/007 的断言广度已补齐。
- 卡点：无本地环境卡点，纯属工作量与立项顺序；按 specs driven 拆 task 后实施。

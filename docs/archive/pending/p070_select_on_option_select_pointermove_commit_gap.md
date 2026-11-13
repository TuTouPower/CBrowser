# p070 共享 Select 的 onOptionSelect 守卫判据比 Radix 提交判据窄（同值拖过释放提交未被记录）

- 现象：共享 `Select`（`src/frontend/src/shared/ui/Select.tsx`）的 `onOptionSelect` 守卫只认 pointerdown 落点（per-item `pressedRef`，t053 Round 4 修复）；pointermove 进入的同值提交漏过记录。实测 D 案：值已是 `__none__` 时 pointerdown 落 "win-1"、pointermove 过 "None"、pointerup 落 "None"——菜单已关（Radix 已提交，因 pointermove 置位其 `pointerTypeRef`），但 `onOptionSelect=[]` 且 `onValueChange=[]`（同值不调 `onValueChange`）。
- 影响：仅限「查询挂起期拖拽手势选「无」后默认到达覆盖」这一组合：ProfileForm 内当前不可达（查询挂起时菜单只有「无」一个选项；查询到达后默认已套用且不再重套）；后果为默认套用一次、可手动再选，无错误值落盘。全仓唯一 `onOptionSelect` 调用方为 `ProfileForm.tsx:518` 的字体集 Select。
- 根因：Radix 的提交条件是 pointerdown **或** pointermove 置位其 `pointerTypeRef`，我方 `pressedRef` 只在 pointerdown 置位。值变化路径由 `onValueChange` 兜底、无用户可见缺口；仅同值提交漏记。
- 测试缺口：Select 级缺 D 案测试（pointerdown 落他项、pointermove 过本项、pointerup 落本项）；ProfileForm 级该组合当前不可达，无测试。
- 线索：t053 Round 5 审阅报告（`docs/tasks/t053_profile_locale_fonts_defaults/review_code.md` Round 5 t053_code_f007；`review_test.md` Round 5 t053_test_f008，含 A/C/C2/D 案探针实测）。
- 处理：main；resolution=resolved；reason=Select.tsx 的 onOptionSelect 守卫判据已与 Radix 2.4.1 提交判据统一（pointerdown/pointermove 共同置位 pointerTypeRef，pointerup 依判据触发一次），补 D 案 Select 级测试；Select.test.tsx 16 passed、全量 vitest 613 passed、test:types 通过

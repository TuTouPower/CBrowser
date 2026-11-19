---
pid: "p141"
slug: "profile_proxy_alignment_misreports_saved_override"
status: "closed"
resolution: "transferred"
reason: "已核实范围并转交 t090"
fix_ref: "t090"
---
# p141 编辑环境时把已保存的代理地域偏差显示为默认对齐

- 现象：日区环境实际保存 `Asia/Shanghai`、`zh-CN`，检测页报告与日本出口不一致。以相同地域组合重新打开环境编辑表单，表单显示 `已按代理 (JP) 默认对齐：Asia/Shanghai …`，并隐藏「恢复默认对齐」。该代理的表单默认时区为 `Asia/Tokyo`。同一摘要还会在英文环境显式打开 CJK 字体时显示「不含中文字体」，与开关相反。现有证据确认误报可复现，无法回溯原配置由哪次操作写入。
- 影响：环境列表编辑弹窗与环境详情配置页复用 `ProfileForm`。已有环境保存的时区或语言偏离所选代理默认值时，再次打开会被标为默认对齐，且缺少恢复入口。显式时区/语言与 GeoIP 的优先级按当前契约工作。当前 Profile 语言仅支持 `zh-CN`、`en-US`，日本本地语言支持需单独确定需求。
- 根因：产品展示缺陷。`ProfileForm` 显示按代理对齐只检查 `timezoneForProxy(selectedProxy)` 是否能推断，摘要却使用实际保存值。`manualOverrides` 初始均为 `false`，恢复按钮只依赖当前表单会话的标志位。代理信息异步到达后也未重新比较保存值与推断值。CJK 摘要按语言计算，未读取独立的 `include_cjk_fonts` 值。修复应让摘要反映真实偏差，并保留显式值直到用户选择恢复。
- 测试缺口：既有 US/HK 测试覆盖同次表单会话中的切换、手动修改和恢复。增加从保存值重新打开的 JP 场景，代理列表异步返回后验证正确摘要和恢复按钮，恢复得到 `Asia/Tokyo`、`en-US`。覆盖时区或语言单独偏离、二者都匹配、自动时区及无法推断代理地域等对照场景。增加英文+CJK 开、中文+CJK 关，断言摘要始终与开关一致。用共用表单覆盖列表编辑与详情配置入口。
- 线索：`.scratch/profile_start_and_identity/profile_align.test.tsx` 在 jsdom 中调用生产 `ProfileForm`，用已保存的 JP 代理及上海时区/中文复现。运行 `src/frontend/node_modules/.bin/vitest run --cache=false --config .scratch/profile_start_and_identity/vitest.config.mts`。
- 处理：t090；resolution=transferred；reason=已核实范围并转交 t090

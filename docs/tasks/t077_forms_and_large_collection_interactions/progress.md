---
tid: "t077"
slug: "forms_and_large_collection_interactions"
title: "表单布局与长集合选择交互统一重构"
status: "done"
branch: "t077_forms_and_large_collection_interactions"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "d66adb623b2899d862756c1e975d5e76b340748d"
spec_source_sha: "d66adb623b2899d862756c1e975d5e76b340748d"
depends_on: "t075,t076"
conflicts_with: "t078,t079"
note: "用户已授权13项todo聚合立项、commit与push；只创建backlog，不实施。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 创建授权：2026-11-18T00:00:06+08:00，用户要求全部todo按已讨论架构聚合为少量task并commit/push；来源为p118、p120。本条仅登记创建事实，未实施、未验证业务AC。
- 关联spec：docs/specs/ui_design_system.md、docs/specs/profile_management.md、docs/specs/proxy_management.md；执行收尾时登记本tid并同步新契约，保留旧task历史。

## 实施计划（2026-11-18 22:0x 写入）

根因（均已实测，见 task.md 引用的 p118/p120 证据）：

- Select Content `position="popper"` + `overflow-hidden` 且无 max-height；Viewport 只有 `p-sm`；Radix 提供的 `--radix-popper-available-height` 未被消费 → 200 代理时 Content 高 6418px、Viewport clientHeight=scrollHeight、滚轮 scrollTop 恒 0。
- ProfileForm Section 按视口断点 `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` 切列，与弹窗实际可用宽无关；时区/语言、配色/CJK 嵌套在 flex 项内再分列；Trigger 固定 36px、无单行截断。
- Popover 无高度约束；ProxyUsedByPopover ul 无滚动；EnvironmentSwitcher 固定 `max-h-panel`；移动分组菜单 fixed + flex-wrap 无滚动无搜索；TimezoneCombobox absolute 菜单非 Portal，被 Dialog 滚动区裁切。
- 9 个高级布尔 + 拟人化预设/启动参数/扩展路径均无帮助说明；种子提示已有但刷新按钮不在标签行、输入框未收紧。

已核实的后端行为依据（帮助文案只写这些，不猜）：

- `runner.py`：allow_3p_cookies → `--fingerprint-allow-3p-cookies`；transparent_proxy → `--fingerprint-transparent-proxy`；portable_cookies → `--fingerprint-portable-cookies`；restore_session → `--restore-last-session`；humanize/human_preset 传给 `launch_persistent_context_async`；extension_paths 传给启动；launch_args 经 `validate_launch_args` 白名单校验后追加。
- `profile_defaults.py`：set_google_default 为真时 runtime agent 在启动前自动化 chrome://settings 把 Google 设为默认搜索引擎（best-effort，失败保留原默认；humanize 开启时打字模拟约 16 秒）。
- `container_spec.py:354`：clipboard_sync → `SELKIES_ENABLE_CLIPBOARD` 环境变量。
- capture_preview 仅控制卡片预览采集、为唯一即时字段（改它不生成新配置版本，见 profile_management.md:81/130）。
- 引擎源码（cloakbrowser 0.6.4，gate_venv 内）：humanize 把自动化鼠标/键盘/打字/滚动转为拟人化操作；human_preset `default` 为正常人速、`careful` 为更慢更谨慎；预设仅在开启拟人化时生效。
- **auto_launch 无消费点**：全仓 grep 仅出现在模型/ORM/仓库/API 入参/表单字段与测试固件，service/supervisor/前端无任何读取。帮助文案必须如实写“保存但当前不触发任何自动启动”，并把该死字段作为发现报给主会话（实现或删除由用户定夺，不在本 task 内擅自实现启动行为）。
- 默认值（domain.md:111 与 profile_management.md:97 一致）：humanize 与 portable_cookies 开；transparent_proxy 与 auto_launch 关；其余 7 项开。

已验证的技术决策：

- Radix Select Viewport 自带 `overflow: hidden auto` + `flex: 1`（react-select dist），只要 Content 限高即内部滚动；只需给 Content 加 `max-h-available-height`。
- Radix Popper 在 Content 内联样式上设置 `--radix-popper-available-height`（px 值），并重命名为 `--radix-select-content-available-height` / `--radix-popover-content-available-height`。
- DESIGN.md 容器 token 可取 `var(--radix-popper-available-height)`：已实测 `design:tokens` 通过，生成 `--container-available-height` 与 `.max-h-available-height` 等工具类。DESIGN.md 已加 `|available-height|var(--radix-popper-available-height)|` 一行，design_tokens.css 已重新生成（仅此两文件改动）。

实施切片（TDD 先红后绿，逐片跑通再下一片）：

- A 共享 Select：Content 加 `max-h-available-height`；Trigger 值单行截断（`min-w-0` + Value `asChild` span `truncate` + trigger `title` 回显全名）；保留 p070/t053 的 onOptionSelect 提交判据与 Select.test.tsx 6 条用例。
- B 新增长型可搜索选择组件（shared/ui/SearchableSelect）：基于 Radix Select，Content 顶部搜索框对完整候选数组客户端过滤，键盘/焦点/同值提交语义与 Select 一致；迁移 ProfileForm 代理/分组、EnvironmentListToolbar 分组/代理、ProxyListToolbar 国家/城市；status/platform/sort/scheme 保持有界 Select。
- C ProfileForm 布局：form 加 `@container`，Section 改容器查询断点（按弹窗实际宽切列）；时区/语言、配色/CJK 解嵌套为直接网格项；对齐摘要 `col-span-full`；种子输入收紧（新增 DESIGN.md 容器 token `seed`，值以真浏览器实测为准）+ 刷新按钮移到标签行。
- D 12 条帮助文案：i18n 中英双语、可聚焦触发器（button，键盘可读）、内容与上列实测行为一致；种子提示保留现有 Tooltip。
- E Popover 视口约束：Content 加 `max-h-available-height`；ProxyUsedByPopover 列表 `min-h-0 flex-1 overflow-y-auto`；EnvironmentSwitcher 改 flex 列布局、列表内部滚动（去掉固定 `max-h-panel`）。
- F 批量移动分组菜单：Popover 锚定到批量操作栏，搜索 + 可滚动分组列表 + 视口约束，键盘方向键/Home/End/Enter/Escape/焦点回归。
- G TimezoneCombobox Portal 化：列表经 Radix Popover Anchor/Content 定位（自动翻转 + 可用高度约束），保留现有键盘/鼠标语义与全部 7 条用例（testid/role 不变）。
- H DESIGN.md 收尾：种子 token + `design:tokens` 生成 + `design:lint` / `design:check`；finalization 更新 profile_management/proxy_management/ui_design_system 的 tasks 清单与 blueprint frontend.md/testing.md。
- I 真浏览器 harness：`.scratch/t077_browser_probe/`（小 vite 应用导入真实组件 + 生产 CSS，headless Chrome + CDP）复现 p118/p120 几何/滚轮失败再验证修复（AC-001/AC-003/AC-004 的 getBoundingClientRect、scrollHeight/clientHeight、真实滚轮 scrollTop、首末项可达）。
- J 全量门禁（TMPDIR 落大盘 + flock 串行），单轴审阅（review_general.md）PASS 后 finish + run-close；不合入、不 push。

## 实施进展（2026-11-18 22:5x 更新）

- 切片 A（共享 Select）完成：Content 加 `max-h-available-height`（Radix 可用高度 token，DESIGN.md 已加 `available-height` 行并重新生成）；Trigger 值单行截断（wrapper `flex-1 truncate` + title 回显全名）；p070/t053 的 6 条 onOptionSelect 用例全部保留通过。教训：`SelectPrimitive.Value` 会吞掉 `className`（解构丢弃）且 `asChild` 会吞掉 label（valueNodeHasChildren 为真时 ItemText 不再 portal 文本）——截断必须包一层 wrapper span，不能用 asChild/className。
- 切片 B（SearchableSelect + 迁移）完成：新组件 `shared/ui/SearchableSelect.tsx`（Radix Select + 顶部搜索框 + 完整数组客户端过滤 + Enter 选首个匹配 + 焦点/Escape/同值提交语义与 Select 一致）；焦点竞态已解决——Radix 在 popper 定位后会把焦点抢到已选项/内容上，组件在 open 时立即聚焦一次、再用零延迟定时器补一次（blur 后 flag 清除，不再抢回）。已迁移 ProfileForm 代理/分组、EnvironmentListToolbar 分组/代理、ProxyListToolbar 国家/城市；status/platform/sort/scheme 保持有界 Select。i18n 新增搜索/无匹配键 7 个（中英）。
- 切片 C（ProfileForm 布局）完成：form 加 `@container`；Section 改容器查询断点 `@[24rem]:grid-cols-2 @[36rem]:grid-cols-3`；时区/语言、配色/CJK 解嵌套为直接网格项；对齐摘要 `col-span-full`；种子输入 `w-seed`（DESIGN.md 新增 `seed: 5rem` token，值待真浏览器实测复核）+ 刷新按钮移到标签行。
- 切片 D（帮助文案）完成：12 条帮助（9 高级布尔 + 预设/启动参数/扩展路径），i18n 中英双语，可聚焦按钮触发器（Tooltip 在 focus 时打开，Radix 自动挂 aria-describedby）；文案依据见本文件“已核实的后端行为依据”，其中 auto_launch 如实写“保存但当前不触发任何自动启动”。种子提示同样改为可聚焦按钮。设计 lint 干净：`min-w-0` 是被禁的数值尺寸工具（含注释内出现也会报），已全部清除。
- 待查核对点（2026-11-18 23:1x 已核实，无需改动）：GroupManagerDialog 的 `<ul>` 本身无高度限制，但外层 Dialog 正文区 `flex-1 overflow-y-auto` 提供滚动（p120 100 组实测结论“无需重写”仍成立）；AC-007 的末项与提交可达由切片 I 真浏览器 harness 实测复核。useEnvironmentFilters 为纯客户端过滤（group/proxy 按 ID 匹配），候选由 toolbar 经 SearchableSelect 传入完整数组，value 即 ID、选择身份与显示/排序分离，符合 AC-003。
- 待做：G（已完成，见下）→ I 真浏览器 harness；H DESIGN.md 收尾（种子 token 待 harness 复核 5rem）+ finalization；J 全量门禁 + 单轴审阅 + finish。

## 实施进展（续，2026-11-18 23:1x 更新）

- 切片 G（TimezoneCombobox Portal 化）完成：候选列表改走 Radix Popover Portal（Anchor 定位 input，side bottom + avoidCollisions + max-h-available-height + 宽 = trigger 宽）。实测依据：Popover Trigger 会在 click 时切换开关，不能包 input（会与 focus-to-open 冲突）；DismissableLayer 只在 `!event.defaultPrevented` 时 dismiss，故 input 上的 outside pointerdown 在 Content 的 onPointerDownOutside 里 preventDefault；非 modal Content 不 trap focus，关闭时 onCloseAutoFocus preventDefault、焦点留在 input。旧“full scrollable IANA list”用例按 TDD 规则整体删除并写明理由，换成新结构用例（portal 断言 + 面板 overflow/max-h-available-height）。TimezoneCombobox 7 条 + ProfileForm 12 条全过，tsc 干净。

## 实施进展（续，2026-11-18 23:0x 更新）

- 切片 E（Popover 视口约束）完成：共享 Popover Content 加 `flex max-h-available-height flex-col overflow-hidden`；ProxyUsedByPopover 列表 `flex-1 overflow-y-auto`（标题固定）；EnvironmentSwitcher 去掉固定 `max-h-panel`，改 flex 列 + 列表内部滚动。`min-h-0`/`min-w-0` 全仓禁用，收缩靠 overflow（overflow 非 visible 时 flex 项自动最小尺寸为 0）。
- 切片 F（批量移动分组菜单）完成：新组件 `MoveGroupMenu`（Popover 锚定到移动按钮 + 搜索 + 内部滚动 + 方向键/Home/End/Enter/Escape/焦点回归）；BatchActionBar 加 `moveControl` 插槽；EnvironmentListPage 删掉固定底部按钮行与 moveMenuOpen 状态。实测：Escape 焦点回归通过，证明 Button 的 ref 经 React 19 rest-spread 到达 Radix 触发器。键盘处理在菜单根节点上（搜索框内 Home/End 保留光标语义）。
- 注意：切片 A/B 跑测试时出现过 1 次并行负载抖动（SearchableSelect 焦点定时器测试单次失败、重跑通过），全量门禁时复核。

## 实施进展（续，2026-11-19 02:3x 更新）

- 切片 I（真浏览器 harness）完成：探针应用 + Electron CDP 驱动（`.scratch/t077_browser_probe/`，不入库），4 个 pass 共 **67/67 检查通过**（2026-11-19 02:4x 全量运行，exit 0，`/tmp/t077_drive_full19.out`）：A 1280x900 light（form 三列/种子 6 位不裁切/reseed 标签行对齐/无横向越出/12 帮助/focus 开 Tooltip/嵌套下拉滚轮只滚列表不滚 Dialog 正文/滚动到底提交可达）；B 1000x400 light（toolbar 三组 SearchableSelect 滚轮+末项+搜索+回显、longvalue 截断、groupmgr 内部滚动+末项+提交可达、switcher/used-by/move 浮层贴合视口+内部滚动+末项可达+搜索、tz 面板贴合+Portal+选 Asia/Shanghai）；C 1280x900 dark（输入对比度 13.30 ≥ 4.5）；D zh form（同 A，中文标签）。证据：`/tmp/t077_drive_full19.out`。驱动成功时须显式 `process.exit(0)`——CDP WebSocket 句柄一直开着，否则成功路径永久挂起（full18 教训）。
- w-full 落地（TDD）：Chrome 里 `<button>` 的 width:auto 按内容定宽（display:flex 也不填满容器），表单 select 触发器在窄格里会按长文本撑到 954px。共享 Trigger 保持内容宽（工具栏 flex 行里 w-full 会纵向堆叠），ProfileForm 的 6 处 select 用法（分组/代理/语言/平台/配色/拟人化预设）各加 `className="w-full"`；ProfileForm.test.tsx 新增用例钉住 6 处（先红后绿）；探针 longvalue 场景同样传 w-full，真浏览器复验 scrollWidth=954 > clientWidth=182、ellipsis 截断、title 全名。Select.test.tsx 新增用例“block-level flex trigger”（SelectTrigger 由 inline-flex 改为 flex）。ProfileForm 13 条 + Select 9 条全过。
- 驱动根因（均经隔离调试脚本实测，dbg28–dbg41 在 /tmp）：① CDP `Runtime.evaluate` 返回 DOM 节点时 `result.value` 为 undefined，waitFor 须包 `!!(...)`；② `Cdp.send` 无超时，渲染器挂起会让驱动永久卡死（full9 教训），已加 30 秒超时；③ `Input.synthesizeScrollGesture` 在按钮/可拖拽行起点上永不返回（groupmgr 对话框、used-by 列表，30 秒超时双源均挂），在 Select 项/链接起点上可用；④ 原始 mouseWheel 在内容中心点上被吞（选项/按钮/链接均然），只在容器右侧槽位（右缘内 6px）生效，且须先有一次中心滚轮建立悬停目标（否则槽位滚轮三次全灭）；⑤ 统一滚轮规则：中心预热 + 槽位滚轮，全部 6 处滚轮检查（toolbar×3、switcher、used-by、move、groupmgr）均以此通过，手势路径已删；⑥ 滚动体须取 scrollHeight 最大者（switcher 曾误取 20/1 的小元素）；⑦ 无头 Electron 里 CDP 鼠标点击不聚焦、键盘事件到不了 tz 输入、insertText 能触发 onChange 却写不进受控输入值——tz 检查改走原生 setter + input 事件写值、鼠标点选；focus-to-open 与键盘选择由 TimezoneCombobox.test.tsx（7 条，fireEvent.focus 打开面板）覆盖；⑧ Portal 检查须走结构断言：Popover Content 自带 role="dialog"（Radix 行为），其父为 Portal 容器 div、再父为 body，且 Portal div 之上无外层 dialog 祖先（初版 `panel.parentElement === body` 误判，已修正）。
- design token 管线根因修复（切片 A 后续）：Tailwind v4 把 `@theme` 里无人引用的 `--container-available-height` tree-shake 掉（`max-h` 工具不读 `--container-*`），且 `:root` 补定义会被继承毒化（变量在 :root 处因被引变量不存在而 guaranteed-invalid）。修法在生成器：`design_tokens.mjs` 对含 `var(` 的 token 值直接把表达式内联进尺寸规则（在用它的元素上求值）；`design_tokens.test.mjs` +1 用例，53/53；`design:tokens` 重生成，`design:lint` 0 error / 0 warning。真浏览器复验：Content maxHeight 810px、Viewport scrollHeight 3312 > clientHeight 755。
- FieldLabel 修复：共享 FieldLabel 的 `mb-sm` 在 flex 标签行内把 label 文本顶起 4px（reseed 按钮 dCenter=4.0）；去掉 `mb-sm`（间距归父布局的 gap-xs），LoginPage 唯一依赖处补 `flex flex-col gap-sm`；真浏览器复验 dCenter=-0.0。
- 全量门禁（2026-11-19 03:xx，两轮，证据 `~/workspace/cloud-task-logs/gate-t077-final` 与 `gate-t077-final2`）：第一轮 exit 1——protocol/requirements/contract/integration/design_lint/design_check/frontend_build 均为 0；unit 1（14 败，全为已知基线 t063×12 Mac 路径 + t068×2 引擎 pin，a16 的 14 条全过，零新增）；frontend_test 1（SearchableSelect 2 条 5000ms 超时）。第二轮（修超时后）exit 1——其余 7 项仍为 0，unit 仍为 14 条基线，frontend_test 1（ConfigTab 1 条超时，隔离复跑 2177ms 通过，定性为负载抖动，见下条）。
- SearchableSelect 超时根因与修复：200 选项夹具在 jsdom 里渲染慢（单跑每条 0.4–3.1 秒），门禁并行负载下超 5 秒 vitest 默认超时。修法只改测试时限不改断言：`SearchableSelect.test.tsx` 顶部 `vi.setConfig({ testTimeout: 20000 })`；第二轮门禁中该文件 8/8 全过，单跑前端套件 87 文件 717 测试全过。ConfigTab 超时（“shows a success echo and remounts…”）为另一文件的同类负载抖动：隔离 2177ms 通过，t075 门禁已有同类前例（frontend 1 条负载 flake，隔离通过，照此定性）。
- 门禁调用说明（工具链缺陷，已报主会话）：直接跑 `scripts/run_gates.sh` 会 exec 进 `gate_run.py`，后者设置 `CBROWSER_GATE_RUNS_DIR`，随后 `run_gates.sh:252` 的 `cleanup_containers` 在无 Docker 的机器上返回 1，`set -e` 下脚本在任何 suite 运行前即退出（前两轮实测）。t075 门禁日志首行 “gate cleanup: no run registry” 证明当时绕过了 gate_run.py；本轮沿用同一做法：`CBROWSER_GATE_ENV_READY=1` + `CBROWSER_SELKIES_WHEEL_CACHE` 指主仓缓存（只读）+ 外层 flock 串行 + TMPDIR 落大盘。

## 审阅第 1 轮（2026-11-19 03:36）与修复（03:4x）

- 审阅 verdict：**FAIL**（`review_general.md`，round 1，reviewer_focus 通用）：finding 2 条——t077_gen_f001 important（AC-005）、t077_gen_f002 minor。审阅方独立复核：门禁 final2 的 unit 14 败确为已知基线、ConfigTab 超时为负载抖动（隔离 3/3 通过）、浏览器探针 67/67 真实、帮助文案逐条对后端核实（含 auto_launch 死字段）；其余 AC 均为 TICK-VALID，仅 AC-005 因 f001 判 TICK-VOID。
- 按流程先把 task.md 全部 7 个 AC 撤回 `- [ ]`，再修复、重验、重审。
- f001 已修（TDD，先红后绿）：SearchableSelect 搜索框 `onKeyDown` 只对单字符键 stopPropagation，Home/End 继续冒泡到 Radix Content，被其 preventDefault 并把焦点抢到首/末选项。修法：Home/End 同样 stopPropagation（ArrowDown/ArrowUp 继续冒泡保留“移入列表”）；组件顶部键盘契约注释同步修正。新增测试 1 条（红→绿）：输入 `199` 后按 Home/End，断言事件未被 Radix 取消（fireEvent 返回 true）且 20ms 后焦点仍在搜索框、selectionStart 未动——jsdom 不模拟按键默认光标移动，故光标移动本身不在 jsdom 断言内；stopPropagation 后真实浏览器的默认光标行为即恢复。SearchableSelect.test.tsx 9/9 全过。
- f002 已修（TDD，先红后绿）：生成器把 `--container-available-height: var(--radix-popper-available-height);` 输出进 `@theme`（Tailwind 会把 @theme 变量暴露到 :root），该值在 :root 处 guaranteed-invalid 且经继承毒化后代——正是上一轮内联修法声称要消除的东西。修法：`design_tokens.mjs` 的 @theme 容器循环跳过含 `var(` 的 token（内联尺寸规则是其唯一出口）；`design_tokens.test.mjs` 在既有用例内 +1 断言（`not.toContain("--container-available-height:")`），53/53 全过；`design:tokens` 重生成、`design:lint` 0 error / 0 warning、`design:check` 通过；生成产物中 `--container-available-height` 定义已消失，仅剩 3 条内联规则（`.h/.max-h/.min-h-available-height`）。
- 重验（2026-11-19 03:5x）：前端 `npm test`（types + vitest）87 文件 718 测试全过（717 + 新增 Home/End 1 条）。
- 全量门禁第 3 轮调用失误（已纠正）：本轮误传 `--out-dir`（run_gates.sh 不认该参数），`CBROWSER_GATE_EVIDENCE_DIR` 未设，脚本走了串行 fail-fast 默认模式：protocol/requirements/contract（388 passed, 1 skipped）均过，unit 在 450s 后失败即停（integration/design/frontend 均未跑），证据目录为空、只有 stdout 日志（`gate-t077-final3.log`）。教训：门禁证据目录须经 `CBROWSER_GATE_EVIDENCE_DIR` 环境变量指定，无 `--out-dir` 参数。
- 门禁第 3 轮 unit 结果：5 failed + 10 errors（2353 passed）。其中 4 failed + 10 errors 与 final2 完全一致，均为已知老基线（t063×12、t068×2）。**唯一新增 1 条 t078**：`test_t078_deletion_lifecycle.py::test_concurrent_requests_create_single_open_intent`（失败在 `:350`，intent stage 为 `failed` 而非 `done`）。该用例在 final/final2 的 junit 里均为通过（无 failure 节点）。主会话在 worktree 内隔离复跑该用例 1 passed（7.41 秒）。其余证据主会话已核对：final3 定向 84 测试全过；ConfigTab 超时已隔离复跑 3/3 通过。**订正（第 2 轮审阅 t077_gen_f003，2026-11-19 04:26）**：此前本段曾写“该失败的上游报错为 `EngineArtifactError: unapproved_engine_build`，即 t068 引擎 pin 波及删除路径”——该归因在 final3.log 里无据：全部 `EngineArtifactError` 出现点（行 478–558）都属于两条 t068 测试；t078 失败小节（行 559–615）通篇无 `EngineArtifactError`，其 intent 错误尾部为 `...le_not_found`，与同一测试文件 `:167` 的 `error == "profile_not_found"` 一致。正确定性：第 3 轮 t078 失败为后端删除生命周期在 `-n 4` 并行负载下的间歇 flake，已见两种模式为 `:350` intent 以 `profile_not_found` 失败与 `:347` 两并发请求生成 2 个 intent 的收敛竞态；与 t077 无关（t077 diff 无后端文件），留待 t078 单立 task 跟进（含 `:347` 竞态）。
- 补充记录（执行方隔离复跑，同一用例另见间歇性收敛竞态）：执行方隔离复跑 5 次为 3 通过、2 失败；其中 1 次失败在 `:347`（两次并发请求生成了 2 个 intent，`len(ids)==2`），与门禁失败模式（`:350` stage failed）不同。结论：该 t078 用例本身存在间歇性竞态，不只一种失败模式；但门禁第 3 轮的失败按主会话定性为引擎 pin 环境基线波及，与 t077 无关——本 task diff 只含前端/design token 生成器/文档，未碰任何后端文件；不在本 task 内修（属 t078 既有 flake，留待单立 task）。
- 全量门禁第 4 轮（证据模式，`CBROWSER_GATE_EVIDENCE_DIR=gate-t077-final3`，2026-11-19 04:xx，约 15 分钟，exit 1，`suites.tsv` 9 项齐全）：protocol_drift_check 0、requirements_check 0、contract 0（388 passed, 1 skipped）、design_lint 0、design_check 0、frontend_test 0（87 文件 718 cases，含新增 Home/End 用例）、frontend_build 0——7 项通过；unit 1——**恰好 14 条已知基线**（4 failed + 10 errors：t063×12、t068×2），零新增，final3 的 t078 用例本轮未复现；integration 1——1 failed（216 passed, 7 skipped）：`test_font_sets_api::test_default_font_set_id_requires_integrity_ok`（`default_font_set_id["windows"]` 为 None）。定性（主会话独立定性，2026-11-19 04:20；措辞订正见下）：发生在 -n 4 并行下，与 p138 同文件、同并行上下文；p138 已登记的根因（font_repository 的 apply_audit_verdict 缺 write_transaction）正是该文件并发写竞态的已知缺陷；主会话隔离复跑 1 passed（4.17 秒）。定性为并行负载抖动，非 t077 回归（t077 只改前端文件）。执行方隔离复跑该用例 3/3 通过；integration 日志的 traceback 显示写失败正是因为 commit 时 `sqlite3.OperationalError: database is locked`（`font_repository.py:142` 的 `session.commit()`），“写丢失”是其后果。**订正（第 2 轮审阅，2026-11-19 04:26）**：此前本段“本次表现为写丢失而非 database is locked”措辞不准——日志显示写失败正是因为 database is locked，二者是同一机制的因果而非两种表现；实质定性（p138 同文件同并行上下文）无误。t077 diff 未碰任何后端/字体代码。

## 审阅第 2 轮（2026-11-19 04:26，verdict: PASS）

- 审阅报告：`review_general.md` 以追加 `## Round 2` 小节方式写入，第 1 轮原文完整保留，末行 `verdict: PASS`；reviewed_scope `2145fa6551a4492d` 与 prompt 注入值一致。
- 前轮 finding 均已消除：f001（审阅方独立重跑 SearchableSelect.test.tsx 9/9；新测试有两条独立红信号可抓原缺陷；已披露 jsdom 不模拟按键默认光标移动的局限）、f002（审阅方独立重跑 design_tokens.test.mjs 53/53、design:lint 0/0、design:check 通过；生成产物全仓 grep 已无 --container-available-height）。
- 本轮新发现 1 条 minor（不阻断）：t077_gen_f003（progress.md 归因措辞，见 Review 处置，已修）。
- AC 逐条全部 TICK-VALID，re_verified，coverage = 7/7；探针 67/67 证据仍有效，并明说探针未覆盖 Home/End 路径、以组件测试为准。
- 门禁定性均认可：第 4 轮 7 项 exit 0、unit 恰好 14 条基线、integration 唯一失败为 p138（traceback 显示 font_repository.py:142 commit 时 database is locked，且该文件 0 处 write_transaction，p138 登记文件已核实存在）；第 3 轮结论一致（定向 84 passed）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

|finding_id|status|fix_ref|备注|
|---|---|---|---|
|t077_gen_f001|已修|src/frontend/src/shared/ui/SearchableSelect.tsx|搜索框 Home/End 加 stopPropagation + 新增组件测试 1 条；SearchableSelect.test.tsx 9/9，第 2 轮审阅独立重跑确认消除。|
|t077_gen_f002|已修|src/frontend/scripts/design_tokens.mjs|生成器 @theme 跳过含 var() 的容器 token + 测试断言；design_tokens.test.mjs 53/53，design:tokens 重生成、design:lint/design:check 全过；第 2 轮审阅独立重跑确认消除。|
|t077_gen_f003|已修|docs/tasks/t077_forms_and_large_collection_interactions/progress.md|progress.md 两处归因措辞已纠正（t078 第 3 轮失败的引擎 pin 归因无据，改为并行负载下间歇 flake 的两种已见模式；integration“写丢失而非 database is locked”改为写失败正是因为 commit 时 database is locked）。:347 竞态记入 t078 跟进任务一事由主会话定夺（本 task 不另立 pending）。|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：AC 7/7 已打勾；第 2 轮审阅 verdict PASS（review-status overall=PASS，round=2）
- 测试：前端 `npm test`（types + vitest）87 文件 718 测试全过；design_tokens.test.mjs 53/53；SearchableSelect.test.tsx 9/9（含新增 Home/End 用例）；全量门禁第 4 轮（证据模式，`~/workspace/cloud-task-logs/gate-t077-final3/`）：7 套件 exit 0，unit 恰好 14 条已知基线（t063×12、t068×2），integration 1 条 p138 并行抖动（隔离 3/3 通过）
- 黑盒：真实浏览器探针（Electron CDP + 生产组件/CSS，200 代理/100 分组/100 环境）4 个 pass 共 67/67 检查通过（`gate-t077-final2/t077_browser_probe_full19.out`）；探针未覆盖 Home/End 路径，以组件测试为准（第 2 轮审阅已明说）
- review：第 1 轮 FAIL（f001 important + f002 minor，均已修），第 2 轮 PASS（新发现 f003 minor 为 progress.md 措辞，已修）
- AC 判定：见 `task.md` 行内打勾；创建时全部未勾选

### 结果摘要

- 共享 Select/Popover 按可用视口限高、内部滚动；SearchableSelect（可搜索选择）迁移全部增长型消费方（代理/分组/国家/城市/移动分组）；ProfileForm 按容器查询分区、种子紧凑 + 刷新在标签行；12 条高级选项帮助（可聚焦、双语、与后端行为一致，含 auto_launch 死字段如实表述）；TimezoneCombobox Portal 化；design token 管线根因修复（var() 值内联进规则，@theme 不再输出 guaranteed-invalid 定义）；spec 与 blueprint 已同步更新。
- 遗留发现（不在本 task 内处理）：auto_launch 为死字段（实现或删除由用户定夺）；gate_run.py 在无 Docker 机器上无法跑全量门禁（须 CBROWSER_GATE_ENV_READY=1 绕行）；t078 并发删除间歇 flake（:350 profile_not_found、:347 两 intent 收敛竞态）与 p138 字体审计写竞态待单立 task。

### 长期文档闭环

- 已更新：`docs/specs/profile_management.md`、`docs/specs/proxy_management.md`、`docs/specs/ui_design_system.md`（tasks 加 t077）；`docs/blueprint/frontend.md`、`docs/blueprint/testing.md`（t077 节）。

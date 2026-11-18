# Task review t077（reviewer_focus: 通用）

- task：`t077_forms_and_large_collection_interactions`
- spec：`docs/tasks/t077_forms_and_large_collection_interactions/task.md`
- diff_anchor：`d66adb623b2899d862756c1e975d5e76b340748d`
- target：`git diff d66adb623b2899d862756c1e975d5e76b340748d`
- round：1
- reviewed_at：2026-11-19T03:36:58+08:00

reviewed_scope: e58e4300d3161060

审查范围说明：`git diff` 本身不含 4 个未跟踪交付文件（`src/frontend/src/shared/ui/SearchableSelect.tsx`、`src/frontend/src/shared/ui/SearchableSelect.test.tsx`、`src/frontend/src/features/profiles/MoveGroupMenu.tsx`、`src/frontend/src/features/profiles/MoveGroupMenu.test.tsx`，`git status` 为 `??`，未做 `git add -N`），本次审查直接通读了这 4 个文件的 worktree 内容并计入审查范围，无 reviewer 看不到的交付文件。

## Findings

### t077_gen_f001 - SearchableSelect 搜索框内 Home/End 被 Radix 劫持，焦点被抢到首末选项、光标不动

- 严重度：important
- 锚点：AC-005 + 一句话失败场景——在任意可搜索选择（代理/分组/国家/城市）的搜索框里输入文字后按 Home 或 End，光标不移动到行首/行尾，焦点反而跳到列表首项或末项
- 位置：`src/frontend/src/shared/ui/SearchableSelect.tsx:118-130`（搜索框 `onKeyDown`）与 Radix Select Content 的按键处理（`node_modules/@radix-ui/react-select/dist/index.js:606-619`）
- 问题：`SearchableSelect` 的搜索框 `onKeyDown` 只对单字符键 `stopPropagation`（注释写明目的是挡掉 Radix typeahead），`Home`/`End`（键名长度 > 1）继续冒泡到 Radix Content。Radix Content 的 `onKeyDown` 对内容区内任意目标（包括搜索框 input）处理 `ArrowUp/ArrowDown/Home/End`：`event.preventDefault()` 后 `setTimeout(() => focusFirst(candidateNodes))`，Home 取正序首项、End 取倒序首项（即末项）。复现路径：在代理选择里输入 `Proxy199`，按 `End` 想把光标移到文本末尾——结果焦点离开输入框落到末项上，输入框光标纹丝不动；按 `Home` 同理落到首项。同一 diff 内的 `MoveGroupMenu`（`src/frontend/src/features/profiles/MoveGroupMenu.tsx:68-76`）明确保留了搜索框内 Home/End 的光标语义，说明本 task 的既定契约就是搜索框内 Home/End 归光标、列表内 Home/End 归首末项；`SearchableSelect` 与该契约分叉。现有测试只覆盖了搜索框内 ArrowDown 移入列表，未覆盖 Home/End，探针也未测这一路径，所以缺陷未被拦住。列表获得焦点后 Home/End 本身是正常的，问题只在焦点位于搜索框时。
- 建议：在 `SearchableSelect` 搜索框的 `onKeyDown` 里对 `Home`/`End` 同样 `stopPropagation()`（只挡这两个键；ArrowDown/ArrowUp 继续冒泡以保留“移入列表”的既有行为），并补一条组件测试：在搜索框输入文字后按 Home/End，断言焦点仍在搜索框且 `selectionStart` 到行首/行末。

### t077_gen_f002 - 生成器仍向 :root 输出无引用的 `--container-available-height`，正是本次修复所称会被毒化的变量

- 严重度：minor
- 锚点：「行为缺陷」+ 一句话失败场景——无可观察行为；生成产物里留下一个 guaranteed-invalid 且无人引用的自定义属性，与修复的自述理由自相矛盾
- 位置：`src/frontend/scripts/design_tokens.mjs:607`（`:root` 变量输出）与生成产物 `src/frontend/src/styles/design_tokens.css:103`
- 问题：本次修复的核心理由是 `var()` 值的容器 token 不能经 `var(--container-<name>)` 中转（`:root` 处被引变量不存在时变为 guaranteed-invalid 并经继承毒化后代），于是 `:626` 把表达式内联进尺寸规则。但 `:607` 仍无条件输出 `--container-available-height: var(--radix-popper-available-height);` 到 `:root`（生成产物 `:103`），而全仓除生成产物外没有任何地方引用 `--container-available-height`（grep 无结果）。该变量在 `:root` 处确实是 guaranteed-invalid 并会继承给全部后代——今天无任何消费者所以无可观察影响，但它正是修复声称要消除的东西，留着等于修了一半。
- 建议：生成器对含 `var(` 的容器 token 跳过 `:root` 的 `--container-<name>` 定义输出（只保留内联进规则的表达式），并补一条 `design_tokens.test.mjs` 用例断言生成产物不含该定义；`design:tokens` 重生成后 `design:check` 应仍通过。

## 结论

- 本轮新发现：2 条（important 1 条，minor 1 条）
- 未进表的提示：
    - 门禁复核（两轮均已独立查证）：final2 的 `unit` 14 败确为已知基线——`junit/unit.xml` 显示 12 条 `test_t063_patched_keyboard_behavior`（Mac 侧路径文件不存在）+ 2 条 `test_t068_engine_artifact_pinning`（`unapproved_engine_build` 引擎 pin），无一触及 t077 文件；`frontend_test` 唯一失败是 `ConfigTab.test.tsx`“shows a success echo and remounts…”的 5000ms 超时（纯超时、无断言失败），我本轮隔离重跑该文件 3/3 通过（该用例 880ms，门禁全量负载下 5169ms），负载抖动定性成立；final1 的 2 条 `SearchableSelect` 超时在加时限后 final2 8/8 通过。其余 7 个 suite 两轮均为 exit 0。
    - 真浏览器探针复核：`t077_browser_probe_full19.out` 为 67/67 PASS、0 FAIL；探针源码（`.scratch/t077_browser_probe/src/probe.tsx`）确认导入真实生产组件与生产 CSS，夹具为 200 代理 / 100 分组 / 100 环境，覆盖 AC-001 三列与种子不裁切、AC-002 标签行对齐、AC-003 滚轮/末项/搜索/回显、AC-004 400px 视口贴合与时区 Portal、AC-005 嵌套滚轮不误滚背景、AC-006 12 个帮助（含中文）与 AC-007 长值截断 + 深色对比度 13.30。探针与驱动不入库，证据为驱动输出文件。
    - 帮助文案已逐条对后端核实：`allow_3p_cookies`/`transparent_proxy`/`portable_cookies`/`restore_session` 对应 `runner.py:625-631` 的 fingerprint 旗标；`clipboard_sync` 对应 `container_spec.py:354` 的 `SELKIES_ENABLE_CLIPBOARD`；`launch_args` 对应 `validate_launch_args` 白名单；`human_preset` 仅在拟人化开启时生效（引擎 `browser.py` 中 `resolve_config` 只在 `if humanize:` 内调用）；`auto_launch` 全仓 grep 确认除模型/ORM/仓库/API 入参外无任何消费点，帮助文案“保存但当前不触发任何自动启动”属实，`formCreateAndStart`“创建并启动”按钮真实存在（`ProfileForm.tsx:894`）。死字段本身是既有问题，spec 已登记“待另行定夺”，不在本 task 范围内。
    - 范围说明：AC-003 的“搜索可找到未加载的末项”在组件/探针层用完整 200/100 数组验证；生产环境候选源按 spec 自身定义走 t076 有界端点（首 50 条 + 已选值单读回显），即生产里搜索范围是已加载的 50 条——这是 t076 的既定约束，不是 t077 的缺陷，此处只作口径记录。
    - `SearchableSelect.test.tsx` 顶部 `vi.setConfig({ testTimeout: 20000 })` 只是把 200 选项夹具在 jsdom 下的渲染耗时（单条 0.4–3.1 秒）导致的 5 秒默认超时放宽，未改动任何断言，final2 该文件 8/8 全过且断言真实执行，不构成“加时限掩盖失败”，故不进 finding 表。
    - `FieldLabel` 去掉 `mb-sm` 的影响已核对全部 3 处调用方：`ProfileForm` 的 `Row` 与 `ProxyFormDialog` 的 `FieldRow` 均自带 `flex flex-col gap-xs`，`LoginPage` 已补 `flex flex-col gap-sm`，无间距塌陷。
    - 实施方注记的门禁调用方式（`CBROWSER_GATE_ENV_READY=1` 绕过 `gate_run.py`）与脚本现状相符：`scripts/run_gates.sh:2` 为 `set -euo pipefail`，`:6-7` 未设该变量时直接 `exec gate_run.py`；门禁证据本身（suites.tsv / junit / logs）完整且已逐项查证，结论不依赖该注记。
    - `TimezoneCombobox` 旧用例“opens to the full scrollable IANA list”整体删除并换为 Portal 结构用例，注释写明理由且替换用例覆盖了同等列表内容与新的滚动/限高结构，符合 TDD“旧测试整体删除并写明理由”的规则，不构成删测试掩盖问题。
- 总体判断：实现主体扎实，AC-001/002/003/004/006/007 均有真实浏览器证据与组件测试支撑；但 AC-005 有一条真实键盘行为缺陷（搜索框内 Home/End 焦点被抢），须修复后重审。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。探针 1280x900 三列/无横向越出/提交可达、窄屏 1 列 320px 无越出，`ProfileForm` 容器查询与 6 处 `w-full` 触发器均已读码确认。
- AC-002：TICK-VALID，re_verified。探针种子 6 位不裁切（scrollWidth=78=clientWidth，宽 80px）且 reseed 在标签行（dCenter=-0.0），组件测试钉住 `w-seed` 与标签行结构。
- AC-003：TICK-VALID，re_verified。探针三组可搜索选择滚轮滚动（scrollTop 0 -> 480）、末项可达、搜索命中 Proxy199/Group99/City99 且回显准确；`SearchableSelect` 8/8 与 `ProfileForm` 搜索用例均过。
- AC-004：TICK-VALID，re_verified。探针 400px 视口下 switcher/used-by/move 浮层贴合且内部滚动末项可达；时区面板 Portal 到 body 外、400px 内贴合、可选中 Asia/Shanghai，组件测试断言 Portal 与 `max-h-available-height`。
- AC-005：TICK-VOID，re_verified。搜索框内 Home/End 被 Radix Content 按键处理劫持（焦点抢到首末选项、光标不动），见 t077_gen_f001；其余键盘/焦点/同值提交语义经测试与探针验证无问题，但 Home/End 这一项不成立。
- AC-006：TICK-VALID，re_verified。探针 light/dark/zh 三 pass 均数到 12 个帮助触发器且 focus 打开 Tooltip；组件测试覆盖全部 12 项与键盘可读；帮助文案已逐条对后端源码核实（含 auto_launch 死字段的如实表述）。
- AC-007：TICK-VALID，re_verified。探针长值截断加 title 全名（scrollWidth=954 > clientWidth=182）、分组管理内部滚动末项与提交可达、深色输入对比度 13.30。

coverage = 7 / 7

verdict: FAIL

## Round 2 (2026-11-19T04:26:36+08:00)

- task：`t077_forms_and_large_collection_interactions`
- spec：`docs/tasks/t077_forms_and_large_collection_interactions/task.md`
- diff_anchor：`d66adb623b2899d862756c1e975d5e76b340748d`
- target：`git diff d66adb623b2899d862756c1e975d5e76b340748d`
- round：2
- reviewed_at：2026-11-19T04:26:36+08:00

reviewed_scope: 2145fa6551a4492d

审查范围说明：本轮指纹由工具链 `review_scope_fingerprint` 对当前 worktree 重算，与审阅 prompt 注入的指纹一致；`git diff` 本身不含 4 个未跟踪交付文件（`src/frontend/src/shared/ui/SearchableSelect.tsx`、`src/frontend/src/shared/ui/SearchableSelect.test.tsx`、`src/frontend/src/features/profiles/MoveGroupMenu.tsx`、`src/frontend/src/features/profiles/MoveGroupMenu.test.tsx`），本轮直接通读了这 4 个文件的 worktree 内容并计入审查范围，无 reviewer 看不到的交付文件。本轮只读证据，不改任何实现/测试/spec 文件，未跑全量门禁；单文件测试与 design 脚本为只读复验。

## Findings

### t077_gen_f003 - progress.md 把第 3 轮 t078 失败归因为引擎 pin，但 final3.log 里没有该证据

- 严重度：minor
- 锚点：「行为缺陷」+ 一句话失败场景——无可观察行为缺陷；progress.md 的根因定性文字与门禁日志原文不符，会误导后续跟进
- 位置：`docs/tasks/t077_forms_and_large_collection_interactions/progress.md:107`（“该失败的上游报错为 `EngineArtifactError: unapproved_engine_build`……即 t068 引擎 pin 的环境基线在并行负载下波及删除路径”）
- 问题：`gate-t077-final3.log`（第 3 轮串行 fail-fast stdout）中全部 `EngineArtifactError: unapproved_engine_build` 出现点（行 478–558）都属于两条 t068 测试失败的 traceback；t078 失败小节（行 559–615）通篇没有 `EngineArtifactError`，其 intent 记录的可见错误尾部是 `...le_not_found`，与同一测试文件 `tests/unit/test_t078_deletion_lifecycle.py:167` 的 `error == "profile_not_found"` 一致——即该 intent 以 `profile_not_found` 失败，而非引擎 pin。另补充记录的隔离复跑第二种失败模式（`:347` 的 `len(ids) == 1`，两次并发请求生成 2 个 intent）是 t078 自身收敛逻辑在 `asyncio.gather` 下的真实间歇竞态，与引擎 pin 也无关。两点都不改变本 task 结论（t077 diff 只含前端/design token 生成器/文档，未碰任何后端文件，该用例第 4 轮已通过、隔离复跑多数通过），但“引擎 pin 波及删除路径”这一具体归因在日志里无据，应予纠正，以免 t078 的跟进任务按错误方向排查。
- 建议：把 progress.md:107 的定性改为“第 3 轮 t078 失败为后端删除生命周期在 `-n 4` 并行负载下的间歇 flake，两种已见模式为 `:350` intent 以 `profile_not_found` 失败与 `:347` 两并发请求生成 2 个 intent 的收敛竞态；与 t077 无关，留待 t078 单立 task 跟进”，并把 `:347` 竞态记入该跟进任务。

## 结论

- 前轮 finding 复核：
    - t077_gen_f001（important，AC-005）：已消除。`src/frontend/src/shared/ui/SearchableSelect.tsx:118-130` 的搜索框 `onKeyDown` 现对 `Home`/`End` 同样 `stopPropagation()`（`event.key.length === 1 || event.key === "Home" || event.key === "End"`），`ArrowDown`/`ArrowUp` 继续冒泡保留“移入列表”；顶部键盘契约注释已同步修正。新测试 `src/frontend/src/shared/ui/SearchableSelect.test.tsx` 的 “Home/End in the search box keep focus and the caret in the search box (t077_gen_f001)” 有两条独立的红信号：无修复时 Radix Content 处理会 `preventDefault` 使 `fireEvent.keyDown` 返回 false，且 20ms 后的 `setTimeout` 会把焦点抢到首/末选项；同文件 ArrowDown 测试已证明该冒泡路径在 jsdom 里真实存在，故该测试能抓到原缺陷（推理，未改代码重跑红态）。本轮独立重跑该文件 9/9 通过。jsdom 不模拟按键默认光标移动，测试对此已明说，光标移动本身不在断言内；修复后默认行为恢复是 stopPropagation 的直接后果，属已披露的局限而非假绿。
    - t077_gen_f002（minor）：已消除。`src/frontend/scripts/design_tokens.mjs:607-613` 的 `@theme` 容器循环跳过含 `var(` 的 token；`src/frontend/scripts/design_tokens.test.mjs` 新增用例断言生成产物含三条内联规则、不含 `var(--container-available-height)` 与 `--container-available-height:`，且字面值 token 仍走 `var(--container-dialog)` 间接引用；本轮以 vitest 独立重跑该文件 53/53 通过。生成产物 `src/frontend/src/styles/design_tokens.css:252-254` 仅剩 `.h/.max-h/.min-h-available-height` 三条内联规则，全仓 grep 已无 `--container-available-height`；生成器内除这三条规则与 `@theme` 定义外无其他 `--container-*` 引用方（如宽度工具），删定义无连带破坏。本轮独立重跑 `design:lint`（0 error / 0 warning）与 `design:check`（up to date）均通过。
- 本轮新发现：1 条（minor 1 条，t077_gen_f003，见上；不阻断 PASS）
- 未进表的提示：
    - 门禁复核（第 4 轮证据模式，`gate-t077-final3` 目录）：`suites.tsv` 9 套件齐全，7 项 exit 0（protocol/requirements/contract/design_lint/design_check/frontend_test 718 cases/frontend_build）；`unit` 恰好 14 条已知基线——`junit/unit.xml` 逐项核对为 t063×12（10 error + 2 failure）+ t068×2（2 failure），零新增，t078 `test_concurrent_requests_create_single_open_intent` 本轮无 failure 节点（通过）；`integration` 唯一失败为 `test_font_sets_api::test_default_font_set_id_requires_integrity_ok`（`default_font_set_id["windows"]` 为 None），`logs/integration.log` 的 traceback 显示 `font_set_catalog.py:213` 的 `_run_audit` 经 `font_repository.py:142` 的 `session.commit()` 抛出 `sqlite3.OperationalError: database is locked`，致使审计写失败、默认值保持 None，且 `font_repository.py` 全文 0 处 `write_transaction`——p138 定性（apply_audit_verdict 缺 write_transaction，t081 既有、非回归）成立；p138 登记文件在主仓 `docs/pending/p138_font_repository_write_transaction.md` 已核实存在。progress.md:109 称本次“表现为写丢失而非 database is locked”措辞不准：日志显示写失败正是因为 commit 时 database is locked，“写丢失”是其后果而非另一机制；实质定性（p138 同文件同并行上下文）无误，仅措辞建议顺手修正，不另开 finding。
    - 第 3 轮结论复核（`gate-t077-final3.log`，串行 fail-fast stdout，误传 `--out-dir` 致证据目录为空、integration/design/frontend 未跑，与 progress.md:106 所述一致）：unit 5 failed + 10 errors，其中 4 failed + 10 errors 与 final2 的 14 条基线一致，唯一新增即 t078 用例（失败在 `:350`，`final.stage == "failed"`）；定向复跑 84 passed（行 635）与 progress.md 所述一致。t078 归因见 f003；无论归因如何，该失败与 t077 无关（t077 diff 无后端文件），不影响 verdict。
    - 浏览器探针复核：`t077_browser_probe_full19.out` 为 67/67 PASS、0 FAIL；`.scratch/t077_browser_probe/src/probe.tsx` 确认导入真实生产组件（ProfileForm、各 Toolbar、EnvironmentSwitcher、ProxyUsedByPopover、MoveGroupMenu、GroupManagerDialog、TimezoneCombobox）与生产 CSS（`main.tsx:4` 导入 `src/frontend/src/styles/globals.css`），夹具为 200 代理 / 100 分组 / 100 环境。探针全文 0 处 `Home`——f001 的 Home/End 路径探针未覆盖，以组件测试为准，此处明说。
    - 既有发现复核：progress.md 仍如实记录 auto_launch 死字段（全仓 grep 无消费点，帮助文案“保存但当前不触发任何自动启动”）与 `gate_run.py` 在无 Docker 机器上无法跑全量门禁（须 `CBROWSER_GATE_ENV_READY=1` 绕行，`scripts/run_gates.sh:6` 有该环境变量分支）；本轮抽查复核的引用均真实存在：`d66adb623b2899d862756c1e975d5e76b340748d`（rev-parse 通过）、p118/p120 pending 文件、`runtime_agent/runner.py:625-631` 四条 fingerprint 旗标、`supervisor/container_spec.py:354` 的 `SELKIES_ENABLE_CLIPBOARD`、引擎 `browser.py:448-451` 的 `resolve_config` 只在 `if humanize:` 内调用。
    - AC-001/AC-004 的 token 侧复核：f002 只删了本就无人引用的 `@theme` 定义，探针实测过的内联规则原样保留且 `design:check` 通过；Tailwind 对未引用 `@theme` 变量本就 tree-shake，几何行为不受影响。
- 总体判断：两条前轮 finding 均已真实修复并独立重验通过；7 个 AC 打勾全部成立；第 4 轮门禁除两项已知既有缺陷（unit 14 条基线、integration p138）外全绿，无 t077 引入的回归；唯一新发现是 progress.md 一处归因措辞问题（minor），不阻断。
- 系统性 follow-up：无（t078 的 `:347` 收敛竞态与 `:350` 间歇失败属 t078 自身 flake，progress.md 已记“留待单立 task”，本轮不重复立项；p138 已有登记）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。内联 `.max-h-available-height` 等规则仍在生成产物中，design:check 通过；第 1 轮探针三列/窄屏几何证据仍有效，f002 只删了无人引用的 @theme 定义。
- AC-002：TICK-VALID，re_verified。第 2 轮未动种子相关代码，第 1 轮探针（6 位不裁切、reseed 在标签行）与组件测试证据仍有效。
- AC-003：TICK-VALID，re_verified。本轮独立重跑 SearchableSelect.test.tsx 9/9 通过；第 1 轮探针滚轮/末项/搜索/回显证据仍有效。
- AC-004：TICK-VALID，re_verified。400px 视口约束依赖的内联 max-h 规则仍在且 design:check 通过；第 1 轮探针贴合/时区 Portal 证据仍有效。
- AC-005：TICK-VALID，re_verified。Home/End stopPropagation 已读码确认，新测试两条红信号可抓原缺陷且本轮 9/9 重跑通过；探针未覆盖 Home/End 路径，以组件测试为准。
- AC-006：TICK-VALID，re_verified。第 2 轮未动帮助文案，第 1 轮逐条对后端核实（含 auto_launch 死字段如实表述）仍有效。
- AC-007：TICK-VALID，re_verified。第 2 轮未动相关代码，第 1 轮探针长值截断/分组管理滚动/深色对比度证据仍有效。

coverage = 7 / 7

verdict: PASS

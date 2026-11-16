# Task review t073（reviewer_focus: 通用）

- task：`t073_frontend_design_system_env_and_session_ui`
- spec：`docs/tasks/t073_frontend_design_system_env_and_session_ui/task.md`
- diff_anchor：`04ff5c5af5439d1182642798be887abc8447ec0d`
- target：`git -C '/Users/karson/kar/code/CBrowser_t073' diff 04ff5c5af5439d1182642798be887abc8447ec0d`
- round：1
- reviewed_at：2026-11-16T10:48:00+08:00

reviewed_scope: 81583ae934a2c908

独立复核方式（不采信实施侧自述）：不带 `-C` 的 `git rev-parse --show-toplevel` 落点校验通过；跑完整 `git -C ... diff 04ff5c5af5439d1182642798be887abc8447ec0d` 与 `status --short`；独立重跑 `npm test --prefix src/frontend`（含 `test:types`，84 files / 659 tests 全绿）、`npm run design:lint`（0 error / 0 warning，97 源码 + 7 public 干净）、`npm run design:check`（css up to date）、`npm run build --prefix src/frontend`（含 verify:selkies 成功）；并读取编译产物 `dist/assets/index-BPQHKuEb.css` 校验语义类真实生成。E2E（`tests/*.py`）grep 确认无 `env-action-*` / `env-running-count` / `sr-only` / `transportStateReady` 引用。

## Findings

### t073_gen_f001 - ProfileEditDialog 重置分支在受控用法下不可达，关闭后重开残留旧错误横幅

- 严重度：minor
- 锚点：行为缺陷（编辑弹窗保存失败 → 关闭 → 重开同一环境，顶部仍显示上一次的 `env-edit-error` 失败横幅，而非干净表单）
- 位置：`src/frontend/src/features/profiles/ProfileEditDialog.tsx:26-32`
- 问题：`handleOpenChange` 仅在 `nextOpen === true` 时执行 `setSaveError(null)` 与 `setFormKey(k=>k+1)`。两个宿主（`EnvironmentListPage.tsx:361-366`、`ProfileDetailPage.tsx:203-208`）都以受控 `open` 直接置 true 打开弹窗，不经过 `onOpenChange(true)`；Radix 仅在用户关闭（ESC / Close / Overlay）时回调 `onOpenChange(false)`。故 `if (nextOpen)` 分支实际不可达，`formKey` 恒为 0（Content 卸载/重挂已保证表单用 `initial` 重建，故草稿不残留），但 `saveError` 状态挂在常驻的 `ProfileEditDialog` 实例上不会清除。复现路径：`ProfileEditDialog.test.tsx` 的失败用例让 update 抛错 → 关闭 → 重开 → `{saveError ? <Banner testId="env-edit-error"> : null}`（`ProfileEditDialog.tsx:60-64`）仍渲染。属可观测的轻微状态残留，不丢数据、不影响 AC-006 的弹出/差分/幂等主行为，按 blocking 硬阈值不属崩溃/错答案/数据丢失/越权/泄漏/协议不兼容，定 minor。
- 建议：最小修复——在 `handleOpenChange(false)` 分支或 `open` 变为 false 时一并 `setSaveError(null)`；更彻底用 `useEffect([open, profile?.id])` 在打开时重置，删除不可达分支与多余的 `formKey`。

### t073_gen_f002 - SearchField 新增 `w-full` 经纯 join 的 `cn()` 覆盖 `containerClassName` 宽度约束

- 严重度：minor
- 锚点：行为缺陷（布局）：环境/代理工具栏搜索框宽度从受控值变为占满 flex 父行，可能把同行 Select 挤到下一行
- 位置：`src/frontend/src/shared/ui/Input.tsx:37`、`src/frontend/src/features/profiles/EnvironmentListToolbar.tsx:85`、`src/frontend/src/features/proxies/ProxyListToolbar.tsx:60-66`
- 问题：新 `SearchField` 外层基础类加了 `w-full`（`Input.tsx:37`，spec 蓝图 Step 2 并无 `w-full`）。`cn.ts:1-5` 是 `parts.filter(Boolean).join(" ")` 纯拼接，非 tailwind-merge，故 `EnvironmentListToolbar.tsx:85` 的 `containerClassName="w-(--component-search-field-width)"`（224px）与 `w-full` 同时留在外层。编译产物 `dist/assets/index-BPQHKuEb.css` 中 `.w-\(--component-search-field-width\){...}` 位于偏移 13500、`.w-full{width:100%}` 位于 13855，后者后定义胜出，宽度约束被覆盖。`ProxyListToolbar.tsx:60` 未传 `containerClassName`，外层仅剩 `w-full`（父为 `flex flex-wrap items-center gap-sm`，`ProxyListToolbar.tsx:58-59`），搜索框占满整行。Flex 组合 + `gap-sm` + `shrink-0` 图标仍保证图标与文本不重叠（AC-001 成立），此为纯视觉排版回归，不违反任何 AC，也不属 blocking 硬阈值列举的坏结果，定 minor。
- 建议：最小修复——移除 `Input.tsx:37` 基础类里的 `w-full`（回到蓝图），给 input 补 `min-w-0`（替代蓝图要求的收缩语义），由 `containerClassName` 独占宽度；并给 `ProxyListToolbar.tsx:60` 补 `containerClassName="w-(--component-search-field-width)"` 与列表页对齐。

## 结论

- 本轮新发现：2 条，均 minor（critical 0 / important 0 / minor 2），无未解决 blocking。
- 未进表的提示（7 视角扫描确认，非 finding、不阻断）：
    - 安全：新增仅静态 className / i18n 文案 / 受控 input props，无外部输入拼接、无 innerHTML、无 secret/PII、无越权面，未命中。
    - 正确性：transport `unknown` 回落、observed `default`、runtime 为空、时区空串条件渲染（`:119`/`:320`）、差分 `{}` 边界均成立；`ProfileEditDialog` 未沿用 `ProfileCreateDialog` 的 `submitLockRef`，编辑连续双击靠 ProfileForm 的 `submitting` state + `isPending` 防重（AC-006 只要求新建幂等，编辑防重非 AC，属健壮性扩展，不进表）。
    - 契约·Breaking：`Dialog` 默认 `size="md"` 映射回 `max-w-dialog`（旧硬编码值），`contentClassName` 保留，两处调用点移除是因新 body 内置滚动；`EnvironmentAction` 新增 `"details"` 且 `handleAction`（`EnvironmentListPage.tsx:145-160`）与卡片复用组件全覆盖；`data-testid` 变更经 grep 确认无 Python E2E 引用、前端测试已同步，无 breaking。
    - 性能·资源：无循环查库 / N+1 / 同步 IO / 超时缺失，纯 CSS grid 与既有 `useQueries`，未命中。
    - 架构·可维护性：`headerTransportLabelKey`（顶栏带主语）与既有 `transportStateLabelKey`（详情左列短词）是刻意分离的语义映射，非无意义同形散落；`formKey` 见 f001。
    - 健壮性·可观测：`ProfileEditDialog.handleSubmit` catch 落 `saveError` 未吞错；`IconButton` danger/warning 的 `focus-visible:outline-danger/warning` 与 `FOCUS`（`outline-focus`）经 `cn()` 共存，编译 CSS 中两个 outline 类均存在、键盘焦点色取决于层叠顺序，属纯视觉细节；`EnvironmentListPage.test.tsx:380-394` 将旧 `toContain(envGeoipFollowProxy)` 就地反转为 `not.toContain` 并改 it 名（写明理由 + 新增 `:526-535` 正向用例），断言真实触达 AC-004 新语义、非恒真非弱化，形式与「旧测试整体删除」偏好略有出入但不构成假绿，不进表；`:619-629`/`:646-650` 由 `.toContain("1")` 强化为带标签 + 非 `/^\s*\d+\s*$/`，属加严；`SessionHeader.test.tsx` 旧用例整体替换并写明理由、`it.each` 真实断言 `label`（`:271`/`:319`），合规。
    - 测试·文档·规格：`design_tokens.test.mjs:211-213` 的 `not.toThrow()` 依赖 `validateAndGenerate` 真实 WCAG 校验，触达生产逻辑非恒真；AC-001 的 Playwright `getBoundingClientRect()` 几何验证、AC-003 observed 各态逐个断言、AC-004 卡片视图显式时区、AC-006 详情页编辑入口交互均未单独补测，属「可补 case」类扩展建议（不 blocking）；`docs/blueprint/frontend.md` 第 4/6/7 节描述与代码一致。范围外 `ProxyListToolbar` / `SettingsPage` 继承原语，vitest 全绿证明无报错。
- 总体判断：6 条 AC 全部经独立复验打勾成立，实现与测试真实覆盖，仅 2 条 minor 视觉/状态残留，无未解决 critical / important，判 PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`Input.tsx:35-54` Flex 组合（图标 `shrink-0` + `gap-sm` + input `flex-1`）从结构上根除重叠，3 处调用（`EnvironmentListToolbar.tsx:79-86`、`ProxyListToolbar.tsx:60-66`、`EnvironmentSwitcher.tsx:164-170`）经 `{...rest}` 把 data-testid 落 `<input>`；`ui.test.tsx:148-216` 独立断言 INPUT / flex / 非 relative / aria-label，vitest 659 全绿。
- AC-002：TICK-VALID，re_verified。`StatusBadge.tsx:7-24` 四态彩色语义色（running=`bg-success-soft text-success border-success` 等），`EnvironmentSwitcher.tsx:63/150/206` 触发器与列表项圆点均 `bg-success`，`transport_state.ts:31` ready→running 绿；`DESIGN.md` Contrast 表经 design:lint/check 0 error，编译 `index-BPQHKuEb.css` 实含 `.text-success`/`.bg-success-soft`/`.border-success`/`.text-danger`/`.border-warning`，深色对比有 CSS 支撑。
- AC-003：TICK-VALID，re_verified。`SessionHeader.tsx:62-91/126-135` 删两处 `sr-only`、改渲染 `sessHeaderEnv*`/`sessHeaderTransport*`，`i18n.tsx:520-528/1026-1034` 中英含主语（"环境运行中"/"数据传输正常"、"Env Running"/"Data Ready"）；`SessionHeader.test.tsx:220-322` 断言无 sr-only、it.each 真实断言 label、中文态，且 `SessionDetailsPanel.tsx:268` 左列短词未动。
- AC-004：TICK-VALID，re_verified。`EnvironmentListPage.tsx:257-266` 改为绿点 + `t("runningProfiles",{count})`（"运行中：1"/"Running: 1"），`EnvironmentTable.tsx:261`/`EnvironmentCard.tsx:47/119/320` 仅显式 `timezone` 条件渲染；`EnvironmentListPage.test.tsx:380-394/526-535/619-629/646-650` 严格断言非 `/^\s*\d+\s*$/` 与隐藏默认时区。
- AC-005：TICK-VALID，re_verified。`EnvironmentTable.tsx:99-181` 每行仅 1 个文本主按钮（running→蓝色 primary 打开 / 非运行→secondary 启动）+ 4 个带 aria-label/title 的 IconButton，删除 `variant="danger"`→`text-danger`、停止 `warning`；`EnvironmentCard.tsx:134` 复用同一组件覆盖卡片；`EnvironmentListPage.test.tsx:770-812` 与 `ui.test.tsx:1535-1546` 断言通过。
- AC-006：TICK-VALID，re_verified。`Dialog.tsx:6-13/38-49` size 梯度 + body 内部滚动，`ProfileCreateDialog.tsx:144` 用 size=lg 且 `createActionKeyRef`/`submitLockRef`（`:30/:48/:94/:134`）完整保留，`ProfileEditDialog.tsx:55-75` + `ProfileForm.tsx:334-340` `diffProfileValues` 差分、`ProfileForm.tsx:172-179` 多栏 grid、`ProfileDetailPage.tsx:148-155/203-208` 编辑入口；独立重跑 vitest 84/659 + tsc + design:lint + design:check + build 全通过。

coverage = 6 / 6

verdict: PASS

## Round 2 (2026-11-16T11:00:00+08:00)

reviewed_scope: b547703abe202511

独立复核方式（不采信实施侧自述）：不带 `-C` 的 `git rev-parse --show-toplevel` 落点校验通过（= `/Users/karson/kar/code/CBrowser_t073`）；跑 `git -C ... diff 04ff5c5af5439d1182642798be887abc8447ec0d`（含 5 文件聚焦 diff）与 `status --short`；逐行读修复后的 `Input.tsx` / `ProxyListToolbar.tsx` / `ProfileEditDialog.tsx` / `ui.test.tsx` / `ProfileEditDialog.test.tsx`，并读 3 处 SearchField 调用、2 处 ProfileEditDialog 宿主与 `Dialog.tsx` 透传；独立重跑 `npm test --prefix src/frontend`（含 test:types，84 files / 659 tests 全绿）、`npm run design:lint --prefix src/frontend`（0 error / 0 warning，97 源码 + 7 public）、`npm run design:check --prefix src/frontend`（css up to date）。

### 前轮 finding 复核结论

- t073_gen_f001：已消除，以 diff / 代码 / 测试断言为准。`ProfileEditDialog.tsx:27-30` 的 `handleOpenChange` 由旧 `if (nextOpen)` 不可达分支改为无条件 `setSaveError(null)`，删除 `formKey` 并把 `ProfileForm` 的 `key` 收敛为 `profile.id`（`:66`）。`Dialog.tsx:33` 把 `onOpenChange` 透传给 Radix Root，用户关闭（ESC / Overlay / Close）必经 `onOpenChange(false)` → `handleOpenChange(false)` → 清 `saveError`；两处宿主 `EnvironmentListPage.tsx:361-367`（`onOpenChange` 仅 `if (!open) setEditingRow(null)`）、`ProfileDetailPage.tsx:206-210`（`setEditOpen`）均为受控 `open`，关闭时 Content 卸载重挂且 saveError 已清，重开无残留横幅。成功提交路径 `handleSubmit:47` 直接 `onOpenChange(false)` 不经 handleOpenChange，但 `:36` 开头已 `setSaveError(null)` 且成功路径无错误可残留，无缺口。回归断言 `ProfileEditDialog.test.tsx:192-196` 在失败用例后 `fireEvent.keyDown(document,{key:"Escape"})` 并 `waitFor(() => expect(screen.queryByTestId("env-edit-error")).toBeNull())`；因 `renderDialog:131` 写死 `open`、`onOpenChange` 为 `vi.fn()` 不改变 open，Dialog 不卸载，横幅消失只能来自 `saveError` 状态变化，真实触达修复逻辑，非恒真、非 mock 被测逻辑，旧 expect `:189-190` 原样保留。
- t073_gen_f002：已消除，以 diff / 代码 / 测试断言为准。`Input.tsx:35-39` SearchField 外层基础类移除 `w-full`，`containerClassName` 经纯 join `cn()` 独占宽度；全仓 `grep w-full` 确认仅 `FIELD`（普通 Input，anchor 既有，与 SearchField 无关）等无关文件残留。3 处调用 `EnvironmentListToolbar.tsx:85` 与 `ProxyListToolbar.tsx:66`（本次新增）均传 `w-(--component-search-field-width)`；`EnvironmentSwitcher.tsx:164-170` 未传，但父容器 `:160-162` 为 `flex flex-col` 默认 `align-items:stretch` 自动撑满，移除 w-full 无布局回归。input 用 `flex-1 overflow-hidden`（`:48-51`），依 CSS Flexbox 规范 `overflow!=visible` 使 `min-width:auto` 解析为 0，等价蓝图 `min-w-0` 收缩语义，Flex + `shrink-0` + `gap-sm` 仍根除重叠。回归断言 `ui.test.tsx:166-168` 新增 `not.toContain("w-full")` 与 `toContain("w-(--component-search-field-width)")`，为新增断言、未弱化或删除旧 expect。

修复过程扫描（5 文件本轮变化）：`Input.tsx`（移除 w-full / input overflow-hidden）、`ProxyListToolbar.tsx`（补 containerClassName）、`ProfileEditDialog.tsx`（无条件清 saveError / 删 formKey / key=profile.id）、`ui.test.tsx`、`ProfileEditDialog.test.tsx`（各追加 1 条回归断言，旧 expect 全保留，无就地改旧预期）。未引入新 bug、类型错误、几何重叠或宽度冲突；门禁 659 tests + test:types + design:lint + design:check 全绿，无退化。

### 本轮新发现的 Findings

本轮新发现：0 条（critical 0 / important 0 / minor 0）。f001 / f002 均已彻底消除，修复过程未引入新的可观测缺陷；finding_id 跨轮全局续编，无新 finding 故不产生 `### t073_gen_f003` 及以后编号。

未进表的提示（非 finding、不阻断）：`Input.tsx:43` SearchField 内部 `<Search>` 图标未带 `pointer-events-none`（蓝图 Step 2 建议写法），点击图标不聚焦 input，属 Round 1 已审范围内的极轻微 UX 细节、不违反任何 AC、非本轮修复引入，按「禁止凑数」不进表；input 用 `overflow-hidden` 替代 `min-w-0` 功能等价，非缺陷。7 视角（安全 / 正确性 / 契约·Breaking / 性能·资源 / 架构·可维护性 / 健壮性·可观测 / 测试·文档·规格）对修复 diff 复扫，均无可观测缺陷命中。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`Input.tsx:35-54` Flex 组合（图标 `shrink-0` + `gap-sm` + input `flex-1`/`overflow-hidden`）从结构根除重叠，外层无 `w-full`、`containerClassName` 独占宽度；3 处调用（`EnvironmentListToolbar.tsx:79-86`、`ProxyListToolbar.tsx:60-67`、`EnvironmentSwitcher.tsx:164-170`）经 `{...rest}` 把 data-testid 落 `<input>`；`ui.test.tsx:148-172` 断言 flex / 非 relative / shrink-0 / 非 absolute / 非 w-full / 含宽度类，659 全绿。
- AC-002：TICK-VALID，re_verified。`StatusBadge` 四态彩色语义（running/transition/error/stopped）与 `EnvironmentSwitcher` `bg-success` 圆点未受本轮修复影响；`design:lint` 0/0 与 `design:check` up to date 证语义 token 与 CSS 一致，`ui.test.tsx` StatusBadge `it.each` 真实断言三态彩色且不含 `bg-accent-soft`/`text-on-surface`，相关用例 659 全绿。
- AC-003：TICK-VALID，re_verified。`SessionHeader` 去 `sr-only` 直渲带主语 `sessHeader*` 文案、`i18n.tsx` 中英含主语、`SessionDetailsPanel` 左列短词未动；`SessionHeader.test.tsx` `it.each` 断言 label，659 全绿，本轮修复未触及该路径。
- AC-004：TICK-VALID，re_verified。`env-running-count` 带标签 `t("runningProfiles",{count})` 非裸数字、`EnvironmentTable`/`EnvironmentCard` 仅显式 `timezone` 条件渲染；`EnvironmentListPage.test.tsx` 严格断言非 `/^\s*\d+\s*$/` 与隐藏默认时区，659 全绿。
- AC-005：TICK-VALID，re_verified。每行 1 文本主按钮（running 蓝 primary 打开 / 非运行 secondary 启动）+ 带 aria-label/title 的 IconButton，删除 `variant="danger"`、停止 `warning`；`EnvironmentListPage.test.tsx` 与 `ui.test.tsx` IconButton danger/warning 断言通过，659 全绿。
- AC-006：TICK-VALID，re_verified。`Dialog.tsx:8-13/41-49` size 梯度 + `max-h-dialog-height` + body `overflow-y-auto`，`ProfileCreateDialog` 幂等键/submitLock 保留，`ProfileEditDialog.tsx:50-75` 宽 lg + `diffProfileValues` 差分 + `handleOpenChange` 清错误，`ProfileDetailPage` 编辑入口；`ProfileEditDialog.test.tsx`（宽 lg / 差分 / 失败不关窗 / f001 回归）与 `ui.test.tsx` Dialog size `it.each` 通过，独立重跑 test:types + 659 tests + design:lint + design:check 全绿。

coverage = 6 / 6

### 结论

- 总体判断：前轮 2 条 minor（f001 / f002）经 diff + 代码 + 测试断言独立核实均已彻底消除，修复过程未引入新缺陷；6 条 AC 全部独立复验 TICK-VALID；无未解决 critical / important，判 PASS。
- 系统性 follow-up：无。

verdict: PASS

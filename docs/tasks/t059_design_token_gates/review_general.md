# Task review t059（reviewer_focus: 通用）

- task：`t059_design_token_gates`
- spec：`docs/tasks/t059_design_token_gates/task.md`
- diff_anchor：`cf04d546162f6e040189c423c5b2afcf5ea43ed1`
- target：`git -C '/home/hatch/workspace/CBrowser_t059' diff cf04d546162f6e040189c423c5b2afcf5ea43ed1`
- round：1
- reviewed_at：2026-11-13T08:00:42+08:00

reviewed_scope: dc1cc4761168036d

## Findings

### t059_gen_f001 - DESIGN.md 正文语义段仍写对比度修正前的 danger/warning 亮色值，与 front matter token 不一致

- 严重度：minor
- 锚点：文档/配置一致性（DESIGN.md 为设计权威，正文与 token 定义自相矛盾）
- 位置：`DESIGN.md:776`（正文语义段）对 `DESIGN.md:38`、`DESIGN.md:42`（front matter）
- 问题：正文语义段写 `danger` 危险（亮 `#DC2626`）、`warning` 警示（亮 `#F5A524`），但 front matter 已按对比度修正改为 `light-danger: "#CA2323"`（`DESIGN.md:38`）、`light-warning: "#8D5F15"`（`DESIGN.md:42`），生成的 `design_tokens.css` 用的是新值。正文是人读口径，不影响生成器与门禁，但设计权威文件内部出现两套值，后续按正文取值会重新引入不达标色对（旧值实测：light-warning 对 light-surface 2.04:1、light-danger 对 light-background 4.01:1，均 < 4.5:1，reviewer 独立 luminance 计算复现）。
- 建议：把 `DESIGN.md:776` 正文的 danger/warning 亮色值同步为 `#CA2323` / `#8D5F15`（其余语义值经核对与 front matter 一致）。

### t059_gen_f002 - public 颜色扫描对 public/selkies 目录设了排除，与 A41「不设 allowlist 例外」措辞不完全一致

- 严重度：minor
- 锚点：A41 / AC-002（扫描范围口径说明与实现措辞不一致，处置为改 spec/蓝图口径，不计 FAIL）
- 位置：`src/frontend/scripts/design_tokens.mjs:486-489`（`collectPublicSources` 跳过 `selkies` 目录）
- 问题：`collectPublicSources` 无条件跳过 `public/selkies/`。该目录是 .gitignore 的构建期 Selkies vendor 投放目录（`.gitignore:20`），不属于仓库交付内容，干净检出时不存在；仓库自有的全部 public 资产（logo、favicon 三件、menubar-icon、theme_boot.js 共 6 文件）与 `index.html` 均在扫描内，reviewer 实测往 `theme_boot.js` 写入非 token 色 `#123456` 时 `design:lint` 以「Public assets contain a non-token color」失败（exit 1），AC-002 的可观察行为成立。但 `docs/specs/ui_design_system.md` 2.6 与 `docs/blueprint/frontend.md` 第 6 节的口径均只写「颜色扫描扩展到 `public/**/*.{svg,html,js}` 与 `index.html`」，未提该 vendor 排除，与 A41「不设 allowlist 例外」的字面措辞有出入，读者无法从文档得知这一例外存在（代码注释与 progress.md 有披露，蓝图/spec 无）。
- 建议：在 `docs/specs/ui_design_system.md` 2.6 与 `docs/blueprint/frontend.md` 第 6 节补一句 vendor 目录（`public/selkies/`，gitignore、构建期投放、非仓库自有资产）排除说明，使文档口径与实现一致；扫描行为本身无需改。

## 复验记录（reviewer 独立执行）

- 落点校验：以工作目录 `/home/hatch/workspace/CBrowser_t059` 执行 `git rev-parse --show-toplevel`，输出精确等于 `/home/hatch/workspace/CBrowser_t059`。
- `npm run design:lint`：exit 0（94 个源码文件 + 7 个 public 文件 clean）；`npm run design:check`：exit 0（design_tokens.css 与五件品牌资产新鲜度通过）。
- 负例验证（临时改动后全部恢复，恢复后 `git diff cf04d54` 的 md5 与验证前一致，均为 `cb556d1dc9e8140913ca75bcc02b816b`，`git status --short` 仍为 44 项交付变更、无多余改动）：
  - N1 对比度：`light-warning` 改回旧值 `#F5A524` → lint exit 1，报 `declared text pair light-warning on light-background: 1.69:1 < 4.5:1` 等对比度失败。
  - N2 counterpart：`input-dark` 的 height 改为 `30px` → lint exit 1，报 `components.input-dark.height '30px' is not the mode counterpart of components.input-light.height '36px'`。
  - N3 Shapes 一致性：Shapes 表 `card` 改为 `md` → lint exit 1，报 `Shapes consistency: components 'card' rounded is '{rounded.lg}' but the Shapes table declares 'md'`。
  - N4 数值类：`Button.tsx` 追加含 `w-72` 的行 → lint exit 1，报 Numeric size/spacing 拦截并指出文件行。
  - N5 public 颜色：`theme_boot.js` 追加 `#123456` → lint exit 1，报 non-token color。
  - N6 任意值：`Button.tsx` 追加含 `w-[100px]` 的行 → lint exit 1，报 Named/arbitrary size utilities 拦截。
- 对比度独立核算：reviewer 用独立 Python luminance 实现复算 8 个修正 token 的关键色对，新值全部达标（light-warning 对 surface 5.56、light-danger 对 background 4.62、双模式 on-surface-subtle 4.62/4.61、light group teal/green/amber/orange 对 background 3.26–3.27 ≥ 3.0），旧值全部不达标且与 progress.md 记载的 2.04 / 4.01 / 3.91 三个实测数逐一吻合；新值同时通过生成器自身对比度门禁（design:lint 绿）。
- 替换等值核对：逐行配对 diff 全部 React 变更行核对计算值，重点五处与生成 CSS 对照无误——Switch checked 位移 `calc(var(--component-switch-width) - var(--component-switch-size) - var(--spacing-2xs))` = 36−16−2 = 18px（`Switch.tsx`，`design_tokens.css:129-131` switch height 20 / width 36 / size 16）；Button `h-9`→`h-(--component-button-primary-height)` = 36px（`design_tokens.css:143`）；Table `h-14`→`h-(--component-table-row-height)` = 56px（`design_tokens.css:116`）；TimezoneCombobox `max-h-64`→`max-h-dropdown-list` = 16rem = 256px（`design_tokens.css:95`）；AppLayout 拖宽 handle `w-2`→`w-(--spacing-sm)` = 8px（确为变量形式而非会被 container 劫持的 `w-sm`），同行 `-right-1`→`-right-xs` = −4px、`top-0`→`top-none` = 0。其余配对（图标阶梯 12/14/16/20/24/32、h-12→app-height 48、w-56→search-field-width 224、w-72→popover-width 288、h-8→menu-item-height 32、py-0.5→py-2xs 2px、p-1→p-xs 4px、inset/min-w/min-h 零值→none 0px、容器类 badge 3rem / swatch 1.5rem / table-select 2.5rem 等）逐项等值，未发现错配。
- 构建产物核对：`npm run build` exit 0；dist CSS 中 `w-badge`/`h-badge`/`w-swatch`/`h-swatch`/`w-table-select`/`max-h-dropdown-list`/`min-w-none`/`inset-none`/`w-(--spacing-sm)`/`size-(--component-icon-md-size)`/`h-(--component-button-primary-height)`/`h-(--component-table-row-height)` 与 Switch checked calc 类均真实生成且声明指向正确变量。
- 测试：生成器测试单跑 49/49 通过；全量前端测试 `npx vitest run` 607/607 通过（80 文件）；`npm run test:types` exit 0。新增生成器测试经抽查为真语义断言（counterpart/Shapes/对比度均以具体报错文案与阈值判别断言，如同一色对作 text 对失败、作 graphic 对通过；品牌资产断言颜色随后 token 变更而变），未见把预期改成实现输出的假绿模式。
- 未能验证：headless 截图比对（本机无 Docker/真实浏览器）未由 reviewer 重跑，AC-005 的截图部分依赖实施侧 progress.md 证据（差异像素 0.029%、仅对比度修正文字像素）；其尺寸等值部分已由 reviewer 以上述配对核对 + 构建产物核对独立复验。后端/E2E 门禁与本 task 前端 diff 无交集，未重跑（progress.md 的基线对账口径不在本轮复核范围）。

## 结论

- 本轮新发现：2 条（均为 minor）
- 未进表的提示：测试夹具字符串（`design_tokens.test.mjs` 中的 `w-72`、`max-w-lg` 等违规示例）会被 Tailwind 自动内容扫描收进 dist 产物形成少量死 CSS（基线已有同类现象，本次新增数值类夹具后略增），无元素使用、无视觉影响，仅产物洁净度提示，不进 finding 表。
- 总体判断：五项新门禁（counterpart、Shapes、对比度三类、public 颜色范围、数值尺寸扫描）经负例实测均可真实失败，当前交付全绿；98 处量级替换逐项等值，8 个对比度修正 token 独立复算达标；仅 2 条 minor 文档口径问题，不阻断。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。DESIGN.md components 中 card 为 `{rounded.lg}`、modal 为 `{rounded.xl}`，Shapes 机读表逐项断言已接入生成器；负例 N3（改 Shapes 表 card 为 md）使 lint 以 Shapes consistency 报错失败，design:check 为绿。
- AC-002：TICK-VALID，re_verified。负例 N5（theme_boot.js 写入 `#123456`）使 lint 以 non-token color 失败；品牌五件资产由生成器按 token 生成且 design:check 新鲜度为绿，generateBrandAssets 测试断言资产颜色随 brand token 变更而变（reviewer 已读断言并跑通全套生成器测试）。selkies vendor 排除口径问题见 f002（minor，不影响本 AC 可观察行为）。
- AC-003：TICK-VALID，re_verified。负例 N1（light-warning 改回旧值）使 lint 以对比度 1.69:1 < 4.5:1 失败；当前 design:lint 为绿，且 reviewer 以独立 luminance 实现复算 8 个修正 token 全部达标、旧值全部不达标。
- AC-004：TICK-VALID，re_verified。负例 N4（`w-72`）与 N6（`w-[100px]`）均使 lint 失败并指出位置；当前 lint 扫描 94 个源码文件全 clean，生成器数值类拦截正/负例测试（49 项）全过。
- AC-005：TICK-VALID，re_verified。reviewer 逐行配对全部 React 替换核对计算值（重点五处见复验记录），并在 build 产物 CSS 中核对全部新工具类真实生成且变量值正确，前端全量测试 607/607 通过；截图比对部分未重跑（无浏览器环境），该部分依赖实施侧 progress.md 的截图证据，但尺寸等值已由计算值核对独立覆盖。

coverage = 5 / 5

verdict: PASS

## Round 1 findings 处置核对（补审，2026-11-13）

- 核对方式：补审 reviewer 独立读 Round 1 报告原文确认 f001/f002 口径，以 `git diff cf04d546162f6e040189c423c5b2afcf5ea43ed1`（TZ=Asia/Shanghai）核对当前工作区全文，并在 `src/frontend` 下重跑门禁、独立复算审阅指纹；除本报告外未修改任何文件，未 commit、未 push。
- t059_gen_f001：已修。`DESIGN.md:776` 正文语义段现为 `danger` 危险（亮 `#CA2323`）、`warning` 警示（亮 `#8D5F15`），与 front matter `DESIGN.md:38` `light-danger: "#CA2323"`、`DESIGN.md:42` `light-warning: "#8D5F15"` 逐字一致；全仓 `DESIGN.md` 中 `#F5A524` 已无残留，`#DC2626` 仅剩 `DESIGN.md:64` `light-group-red: "#DC2626"`（分组色相 token 本身，按处置口径未动）；生成产物 `design_tokens.css` 同为 `--color-danger: #ca2323` / `--color-warning: #8d5f15` / `--color-group-red: #dc2626`，未见顺带改动其他 token 或语义。
- t059_gen_f002：已修。三处均补 selkies 例外说明且口径一致（`public/selkies/` 为 .gitignore 的官方 Selkies vendor 投放目录、自有品牌色、不在扫描内）：`DESIGN.md` Modes 段（L774，括注「`public/selkies/` 为构建投放的官方 Selkies 网页资产，不在扫描内」）、`docs/specs/ui_design_system.md` §2.6（「颜色范围」条）、`docs/blueprint/frontend.md` §6（「生成与门禁」条）。生成器扫描行为本身未改，与 Round 1 建议一致。
- 增量范围已核：处置后交付变更仍为 Round 1 已审的 44 项 tracked 文件（另本报告为 untracked reviewer 文件），增量仅限上述文档文字处置（`DESIGN.md` 两处、`ui_design_system.md` 一处、`frontend.md` 一处）；`progress.md` 的 Review 处置与收尾填写属过程文件，不计交付内容变更。未发现其他 token、语义、代码或资产的顺带改动。
- 门禁复跑：`npm run design:lint` exit 0（94 个源码文件 + 7 个 public 文件 clean，0 error / 0 warning）；`npm run design:check` exit 0（design_tokens.css 与品牌资产新鲜度通过）。
- 指纹复算：`review_scope_fingerprint('cf04d546162f6e040189c423c5b2afcf5ea43ed1', 'docs/tasks/t059_design_token_gates')` 独立复算为 `dc1cc4761168036d`，与实施侧给值一致，`reviewed_scope` 已由 `f2ce086d4d5d5e24` 更新为该值。
- 结论：f001/f002 均已按建议处置，增量范围与指纹核对成立，overall 维持 PASS。

## AC 复验方式

- AC-001：TICK-VALID，re_verified。复验方式：负例验证：Shapes 表 `card` 改为 `md` → lint exit 1，报 Shapes consistency 失败（components 'card' rounded is '{rounded.lg}' but the Shapes table declares 'md'）；另对 components 圆角与实现逐项核对（DESIGN.md components 中 card 为 `{rounded.lg}`、modal 为 `{rounded.xl}`，Shapes 机读表逐项断言已接入生成器）
- AC-002：TICK-VALID，re_verified。复验方式：负例验证：`theme_boot.js` 追加非 token 色 `#123456` → lint exit 1，报 Public assets contain a non-token color；另以 `design:check` 核对品牌资产新鲜度（design_tokens.css 与五件品牌资产新鲜度通过，exit 0）
- AC-003：TICK-VALID，re_verified。复验方式：负例验证：`light-warning` 改回旧值 `#F5A524` → lint exit 1，报 declared text pair light-warning on light-background: 1.69:1 < 4.5:1；另以独立 Python luminance 实现复算 8 个修正 token 的关键色对，新值全部达标、旧值全部不达标；当前 `design:lint` 全绿（exit 0）
- AC-004：TICK-VALID，re_verified。复验方式：负例验证：`Button.tsx` 追加 `w-72` → lint 以 Numeric size/spacing 拦截，追加 `w-[100px]` → lint 以 Named/arbitrary size utilities 拦截；`input-dark` 的 height 改为 `30px` → lint exit 1，报 counterpart 失败（is not the mode counterpart of components.input-light.height '36px'）；另逐行配对全部 React 替换核对计算值等值，重点五处为 Switch checked 位移 calc = 18px、Button `h-(--component-button-primary-height)` = 36px、Table `h-(--component-table-row-height)` = 56px、TimezoneCombobox `max-h-dropdown-list` = 16rem、AppLayout 拖宽 handle `w-(--spacing-sm)` = 8px
- AC-005：TICK-VALID，re_verified。复验方式：构建产物核对：`npm run build` exit 0 后，在 dist CSS 中逐类核对新工具类真实生成且声明指向正确变量（`w-badge`/`h-badge`/`w-swatch`/`h-swatch`/`w-table-select`/`max-h-dropdown-list`/`min-w-none`/`inset-none`/`w-(--spacing-sm)`/`size-(--component-icon-md-size)`/`h-(--component-button-primary-height)`/`h-(--component-table-row-height)` 与 Switch checked calc 类）；headless 截图比对未在审阅侧重跑（本机无 Docker/真实浏览器，reviewer 未亲测），该部分依赖实施侧 progress.md 证据（差异像素 0.029%、仅对比度修正文字像素），其尺寸等值部分已由上述配对核对与构建产物核对独立复验

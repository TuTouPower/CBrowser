---
tid: "t059"
slug: "design_token_gates"
title: "设计系统门禁：圆角、颜色范围、对比度与尺寸 token 化"
status: "done"
branch: "t059_design_token_gates"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "cf04d546162f6e040189c423c5b2afcf5ea43ed1"
depends_on: ""
conflicts_with: "t052,t053,t058"
note: "来源 review_20261110_200842 adoption_decision A40 A41 A42 A62"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 引用逐项核对（2026-11-13，实施前实测）

- task.md 背景四项与现状一致：components 中 card/modal 均为 `rounded.md`；Shapes 正文为卡片 lg、弹窗 xl；生成器（`src/frontend/scripts/design_tokens.mjs`）不校验 components 属性、不计算对比度、源码扫描仅覆盖 `src/**/*.{ts,tsx}`（不含 `public/`、`index.html`、`theme_boot.js`）；logo.svg 渐变色 `#00F0FF/#0088FF/#0052FF` 不在 DESIGN.md token 中。
- adoption_decision A40 位置引用核对：`shared/ui/Dialog.tsx:30` 实测即 `rounded-xl` 行，分毫不差；`EnvironmentCard.tsx` 实测 `rounded-lg`。
- 补充实测：官方 linter 自带 `contrast-ratio` 规则，但仅覆盖 components 成对 textColor/backgroundColor（当前成对组合全部 ≥ 4.5 故未触发）；A42 缺口为其余三类——仅 textColor 的 component 对底色、代码中直接以 token 类使用的文字色（`text-warning` 等）、图形对 3.0，本 task 生成器门禁补齐这三类。
- A42 疑点色对实测（生成器同款 luminance 算法）：dark on-surface-subtle `#858D9C` 对 dark-surface-raised 对比度 3.91、对 dark-surface-subtle 4.26，均 < 4.5；light warning `#F5A524` 作为文字对 light-surface 为 2.04（`EnvironmentTable.tsx:123` 有 `text-warning` 实际用例）；helper-text-light 对 light-background 为 4.498（临界 < 4.5）。components 成对 text/bg 组合则全部 ≥ 4.5。
- A62 数值类实测存在：Popover `w-72`、Button/Input/Select `h-9`、StatusBadge `py-0.5` 等，全仓（collectSources 同口径）共 186 处；任意值仅 Switch `translate-x-[18px]` 一处；分数类（`left-1/2` 等）不是间距值，不在拦截口径。
- **引用不符 1 处**：A41/task.md 称 `theme_boot.js` 有颜色引用需改为生成值；实测当前 `public/theme_boot.js` 无任何颜色字面量（仅切换 class 与 `colorScheme` 关键字），无可改对象，本 task 仅将其纳入颜色扫描（AC-002 负例可失败即达标），不做生成改造。
- Finalization 目标文档全部存在：`docs/blueprint/frontend.md`、`docs/blueprint/decisions.md`（ADR 027 在 L323）、`docs/specs/ui_design_system.md`（specs_index 已有行，task 清单 t036, t037, t047）。

### UNVERIFIED-SPIKE 结论（2026-11-13 实测，实验在 .scratch/spike/）

`@google/design.md@0.4.0` linter 的 components 合法子 token 恰为 `backgroundColor, textColor, typography, rounded, padding, size, height, width` 八个：`height/width/size` 写字面量或 `{spacing.*}` 引用均无 finding 且正常解析为 dimension；自定义字段（如 `iconSize`、`borderColor`）产生 warning「not a recognized component sub-token」，本仓生成器把 warning 视为阻断，故**尺寸规格只用官方 `height/width/size` 字段，在生成器侧读取解析值导出组件级变量，不改官方格式**。另实测 orphaned-tokens 规则：颜色 token 未被任何 component 属性引用即 warning，故品牌色 token 必须被 component 引用（按既有 group-swatch 登记模式处理）。task.md 未知契约清单据此改写为结论。

### 设计决策（实施口径）

- 组件级变量：生成器把每个 component 的 backgroundColor/textColor/rounded/padding/height/width/size 导出为 `--component-<name>-<prop>` CSS 变量（-light/-dark 成对条目先断言互为模式对应，再合并为一组无模式变量，颜色经 `var(--color-*)` 随模式切换）；React 组件以 Tailwind 变量简写类（`h-(--component-…)`)引用。
- 圆角一致性：Shapes 正文改为机读映射表（component 前缀 → rounded token，沿用 Elevation/Container 的正文表格模式），生成器逐 component 断言与 components 定义一致；DESIGN.md components 的 rounded 全部按实现现状改齐（card/environment-card=lg、modal=xl、status-badge/group-chip/protocol-chip/region-code/checkbox=sm、button 族/input/select/search-field/nav-item/menu-item/banner=md、table 族/popover/toast/empty-state=lg、tooltip=sm、switch/dots=full 等，以实现 grep 实测为准）。
- 对比度门禁：components 成对 text/bg 自动按 4.5 校验；仅 textColor 的 component 对同模式四种底色按 4.5 校验；DESIGN.md 新增 `## Contrast` 节声明图形对（danger-dot/warning-dot/group-swatch-*/focus-ring 对同模式 background/surface 按 3.0）与额外文字对（warning/danger 作文字对三种底色按 4.5，源于 `text-warning`/`text-danger` 实际用例）；divider/scrollbar-thumb/modal-backdrop/session-stage 为装饰/结构元素，在该节声明不入对比度对（WCAG 非文本对比度仅约束承载信息的图形）。不达标修正：dark/light on-surface-subtle、light-warning、light group teal/green/amber/orange 共 6 个 token 按求解值调整（AC-005 明确豁免对比度改色）。
- 品牌资产：DESIGN.md 登记 `brand-gradient-start/mid/end`（模式无关品牌色，生成器命名校验扩展允许 `brand-*`）与 `light/dark-brand-ink`；生成器按 token 生成 logo.svg、favicon.svg、favicon-light.svg、favicon-dark.svg、menubar-icon.svg（几何路径保持原文件），`design:check` 校验资产新鲜度；颜色扫描扩展到 `public/**/*.{svg,html,js}` 与 `index.html`，其中字面量必须属于 token 值集合（SVG 无法引用 CSS 变量，生成资产是唯一合法字面量来源），src 源码维持字面量全禁。
- 尺寸/间距门禁：拦截数值型与任意值写法的 p/m/gap/space/w/h/min/max/size/inset/top/right/bottom/left/translate 类（分数 `1/2` 等比例值不属于间距数值，排除）；零值用新增 spacing token `none: 0px`（`inset-none` 等），2px 用新增 `2xs` token；图标尺寸以 components 中 `icon-xs/sm/md/lg/xl/2xl/3xl` 的 `size` 字段登记（模式无关、仅尺寸条目）；零星容器高度（下拉列表 max-h）进 Container sizes 表（`dropdown-list: 16rem`）。
- `design:check` 升级为完整门禁（DESIGN 校验 + 对比度 + 一致性 + 全部扫描 + CSS 与品牌资产新鲜度）；`design:lint` 同步跑全部校验（不含新鲜度），run_gates 两 suite 均覆盖新门禁。

### 实施结果与口径修正（2026-11-13）

- 组件级变量最终只导出 `rounded/height/width/size` 四类（`--component-<name>-radius/-height/-width/-size`）：backgroundColor/textColor 已由颜色工具类直接消费同一 token、再导变量只会产生第二事实来源；padding 在 DESIGN 中为统一占位值（同一 spacing 引用），导出即虚构组件差异。成对条目合并前以声明引用串做 counterpart 断言（生成器读 front matter 声明而非 linter 解析值，因不同 token 可同值、解析值无法区分声明）。
- 对比度修正最终为 8 个 token（在原定 6 个之外，声明对实测另发现 light-danger 作文字对 light-background 仅 4.01，一并调暗至 `#CA2323`）；求解方法为按 HSL/RGB 等比缩放保色相、目标留边距（文字对 ≥4.6、图形对 ≥3.25 求解后取整回填），最终以生成器门禁复验为准。声明对按真实用例底色收敛：warning/danger 文字对 {background, surface}、accent 文字对 {surface, surface-subtle}（代码块底色）、graphic 对含 stage（会话舞台上的状态图标）。
- React 替换共 98 处、30 个文件（门禁违规清单 104 行，含同行多处）；逐项映射在收尾报告与蓝图文档中。两处被既有劫持门禁二次拦截并修正：侧栏拖宽 handle 的 `w-sm` 与聚焦工具条热区的 `h-sm` 会被 Tailwind 解析为 container 值（24rem）而非 spacing，已改用变量形式 `w-(--spacing-sm)` / `h-(--spacing-sm)`（8px，值不变）。分组色板按钮（24px）不用组件变量，入 Container sizes 的 `swatch: 1.5rem`（与 badge/table-select/dropdown-list 同机制）。
- 圆角：实现侧的圆角刻度类本身即 token 引用，DESIGN 改齐后与实现逐项一致，代码侧圆角类不做无谓改写；组件级 `-radius` 变量已导出备用。EnvironmentSwitcher 触发器（select 形态）取 `--component-select-height`；FocusModeToolbar 热区高度取 spacing sm。
- 生成器测试夹具中的违规示例字符串（`translate-x-[18px]` 等）会被 Tailwind 源码扫描生成死 CSS，已改为运行时拼接字面量，生产产物不再含影子类。
- 门禁环境发现两项（非本 task 引入）：(1) `public/selkies/` 为 .gitignore 的构建期 vendor 投放目录（官方 Selkies 网页资产、自有品牌色），首轮全量门禁时被颜色扫描误伤——`collectPublicSources` 已排除该目录并加回归测试，AC-002 的扫描范围为应用自有 public 资产 + index.html；(2) `requirements_check` 依赖 `mise`，本机未安装 mise，该 suite 在基线同样无法运行（其权威漂移检查 `tests/unit/test_t034_dependency_lock.py` 在 unit suite 内执行）。首轮全量门禁在并行负载下另有 2 个前端表单测试与若干后端链式测试超时失败，干净重跑结果见收尾报告。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-13T08:01:26+08:00)

独立 reviewer（general，single 级）overall PASS，AC-001..005 全部 re_verified；负例六项亲手验证真红（对比度/counterpart/Shapes/数值类/public 颜色/任意值），8 个修正 token 经独立 luminance 复算全达标，React 替换逐行配对核对等值，构建产物复核生成。审阅报告 `review_general.md`（reviewed_scope 首轮 f2ce086d4d5d5e24，处置后补审更新）。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t059_gen_f001|minor|已修|DESIGN.md 正文语义段仍写对比度修正前旧值（danger 亮 #DC2626、warning 亮 #F5A524），与 front matter 新值不一致|DESIGN.md:776 改为 #CA2323 / #8D5F15|
|t059_gen_f002|minor|已修|生成器排除 gitignore 的 public/selkies/ vendor 目录与文档「扫描 public」口径有出入，补文档口径（仓库自有资产全在扫描内、AC-002 行为经负例实测成立）|DESIGN.md Modes 段、docs/specs/ui_design_system.md §2.6、docs/blueprint/frontend.md §6 各补 selkies 例外说明|

无 finding 时写“Round N 零 finding”。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：全量门禁 `scripts/run_gates.sh`（证据目录 /tmp/t059_gates2）：contract 0（258 tests）、design_lint 0、design_check 0、frontend_build 0；frontend_test 606/607（基线 575/0，新增 32 为生成器门禁测试，含 selkies 范围回归 1）；unit+integration 2175 tests、8 skipped 与基线同构。基线对账（cf04d54 干净直跑实测）：后端基线 26 个失败名，我方 29 个中 24 个与基线同名、基线独有 2 个（test_a16_protocol_drift、test_t034_dependency_lock）在我方通过、我方独有 5 个（test_t055_socket_slot_cleanup 的 prepare_socket_dir 4 个 + test_stream_transport_hardening 的 ws gateway 1 个）逐名单跑全部通过（14/14，0.60s）——本 task diff 不含任何后端代码，判定为门禁内部并行（后端与前端套件同机并发）在 1.5 CPU 上的超时假象，零代码回归。frontend_test 唯一失败 ProfileForm「renders the four sections…」同理（两轮门禁各失败一次、对象在两轮间漂移；无负载全量手动跑 606/606、该文件单跑 17/17 通过）。requirements_check exit 1 为环境限制（本机未装 mise，基线同），其权威漂移检查 test_t034 在 unit suite 内在我方通过。
- 黑盒：未跑（`CBROWSER_RUN_E2E=1` 需真实 Docker/Chrome，本机无 Docker，按口径跳过；历任 task 均以非 E2E 门禁为 finish 依据）。
- review：single 级独立 reviewer Round 1 overall PASS（AC 5/5 re_verified），2 条 minor（DESIGN 正文旧值残留、selkies 扫描口径）均已修并经补审更新指纹，见下方 Review 处置。

- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- DESIGN.md：components 圆角按实现全量改齐 + Shapes 机读映射表逐项断言；新增 `## Contrast` 声明表与三类对比度门禁，8 个不达标 token 修正（light-warning/danger、双模式 on-surface-subtle、light group teal/green/amber/orange）；品牌 token（brand-gradient-*、brand-ink）登记，logo/favicon 五件资产由生成器生成并校验新鲜度；components 尺寸规格（height/width/size）+ 组件级变量导出；spacing 新增 none/2xs，Container sizes 新增 dropdown-list/badge/table-select/swatch。
- 生成器：声明↔解析交叉断言、counterpart 配对断言、Shapes 一致性、对比度三类校验、public 颜色范围扫描（src 全禁字面量、public 只许 token 值，selkies vendor 目录除外）、数值/任意值尺寸间距扫描（含任意值仅 token 表达式豁免）全部接入 design:lint/design:check；生成器测试 17→49。
- React：30 个文件 98 处数值类替换为组件变量/容器/spacing token 类，计算值逐项不变；构建产物逐类核对 41 个新工具类全部生成且声明正确；登录页 headless 截图与基线构建比对差异像素 0.029%、仅对比度修正的弱文字像素（dark-on-surface-subtle 提亮），零布局变化。
- 遗留：无（门禁环境限制两项见实施笔记，非本 task 引入）。

### 长期文档闭环

在 specs_index 行的 task 清单中登记当前 tid（格式见 `.repo_template/docs/usage.md`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

# Task review t053（reviewer_focus: 代码）

- task：`t053_profile_locale_fonts_defaults`
- spec：`docs/tasks/t053_profile_locale_fonts_defaults/task.md`
- diff_anchor：`1e11e0fda2d2fda130e24e6bdef904c5b96c3516`
- target：`git -C '/home/hatch/workspace/CBrowser_t053' diff 1e11e0fda2d2fda130e24e6bdef904c5b96c3516`
- round：1
- reviewed_at：2026-11-11T16:03:04+08:00

reviewed_scope: ea6850a20f4716ce

## Findings

### t053_code_f001 - UNVERIFIED-SPIKE #1 仍未验证：显式 locale 是否优先于 geoip 推断无任何证据

- 严重度：important
- 锚点：AC-009；task.md「未知契约清单」仍含 `UNVERIFIED-SPIKE`，实施前门禁未完成
- 位置：`docs/tasks/t053_profile_locale_fonts_defaults/task.md:102`；`src/backend/cbrowser/runtime_agent/runner.py:694-697`
- 问题：实现把 `locale=cfg.locale` 与 `geoip=cfg.geoip` 一并显式传给 `launch_persistent_context_async`，但 CloakBrowser 在 `geoip=True` 时是否让显式 `locale` 优先于出口 IP 推断，从未验证——本机无真实引擎，实施方已在 task.md「环境跳过」中承认未验证、须用户机补验。AC-009（运行时 `navigator.language` 等于 Profile 语言，不被出口 IP 推断覆盖）的核心外部契约因此无任何证据支撑，`task.md` 中的打勾不能成立。
- 建议：用户机真实引擎补验（按 task.md 环境跳过项：真实引擎启动两种语言 Profile 读 `navigator.language`）；补验完成并改写未知契约清单前，AC-009 不得打勾。

### t053_code_f002 - 时区空字符串 `""` 在校验与联动规则中含义不一致

- 严重度：minor
- 锚点：行为缺陷——API 对 `timezone: ""` 返回 422，但同一模块的联动规则把 `""` 视为未设置
- 位置：`src/backend/cbrowser/domain/profile_locale.py:34-41`（`locale_for_timezone("")` 返回 `None`）与 `:51-72`（`is_valid_timezone("")` 为 `False`，`validate_timezone("")` 抛错）
- 问题：`validate_timezone` 拒绝 `""`（422），而 `locale_for_timezone` 把 `""` 当作未设置（保持当前语言）。spec 称时区为「合法 IANA 时区或空」，前端送 `null` 不受影响；但存量行若曾存过 `""`，`_to_domain_profile`（`src/backend/cbrowser/adapters/database/repository.py:1044-1080`）构造 `ProfileConfig` 时会抛 `ValidationError`，整行 Profile 读不出。两处对 `""` 的语义分裂是真实存在的不一致，且已被测试双向固定（`tests/unit/test_t053_profile_locale.py` 同时断言 `locale_for_timezone("") is None` 与 `is_valid_timezone("") is False`）。
- 建议：`validate_timezone` 把 `""` 归一化为 `None`（与 `locale_for_timezone` 一致），或在读取路径对存量 `""` 容错。

### t053_code_f003 - TimezoneCombobox 候选内容变化但数量不变时高亮项不复位

- 严重度：minor
- 锚点：行为缺陷——键盘 Enter 可能选中用户未意图的时区
- 位置：`src/frontend/src/features/profiles/TimezoneCombobox.tsx:69-71`
- 问题：`activeIndex` 只在 `options.length` 变化时复位为 0。用户先用方向键移到第 k 项、再键入使候选集合变化但数量不变时，高亮仍停在第 k 项而不回到首个匹配；Enter 提交的是新列表第 k 项，而非用户最可能想要的首个匹配。常见路径（全新输入后直接 Enter）不受影响，因初始 `activeIndex` 为 0。
- 建议：复位依赖改为 `options` 本身（或 `query`），候选变化即回 0。

## 结论

- 前轮 finding 复核（Round 1，无前轮）：无
- 本轮新发现：3 条（1 条 important、2 条 minor）
- 未进表的提示：
  - 文件过大（结论段提示，不进 finding 表）：`src/frontend/src/features/profiles/ProfileForm.tsx` 760 行（基线 722，净增 38）、`src/backend/cbrowser/font_sets/manifest.py` 470 行（基线 417，净增 53），均超 400 行 minor 阈值、未达 800 行 important 阈值；项目 `docs/blueprint/conventions.md` 无覆盖阈值。
  - 圈复杂度（结论段提示，不进 finding 表）：`import_font_set` 手算约 13（AST 近似 16，含生成式计数差异），未达 15 的 minor 阈值，但本 task 为其新增约 4 个分支（完整性检查与修复换位），已接近阈值；`TimezoneCombobox` 的 `handleKeyDown` 约 12，属 ≥10 提示级；其余新增/改动函数均 <10。`check_font_set`（约 21）、`runner.start`（约 31）等高复杂度函数为既有代码，本 task 未增加其分支。
  - 范围外观察：A19 修复路径中若 `os.replace(staging, target)` 成功后 `shutil.rmtree(backup)` 失败，会残留 `.set_id-old-*` 目录并被 `list_font_sets` 当作字体集列出（需单次 OSError 失败触发，概率极低）；迁移 0007 的 downgrade 未实测（upgrade 已由集成测试覆盖）；11 个新文件在 `git status` 中为未跟踪（未执行 `git add -N`），我已逐个直接读全文核查，不属于 reviewer 看不到的交付。
  - 命名锁死核查通过：`src/`、`scripts/`、`compose.yaml` 中 `com.cbrowser.deployment-id` 零命中（仅 `progress.md` 历史叙述中提及被驳回的偏离）；`resource_prefix` 默认仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/docker_adapter.py:234`），未改动。
  - 引用逐项核对通过：`docs/reviews/review_20261110_200842/adoption_decision.md` 的 A16（153 行）、A18（169 行）、A19（177 行）、A20（185 行）、A30（265 行）均存在；`tests/e2e/test_fingerprint_platform_e2e.py` 存在；迁移 0007 的 `down_revision`（`c8d3e7a1f904`）为 0006 的 revision；ADR 030 已新增（`docs/blueprint/decisions.md:367`），标注部分替代 ADR 024。task.md 上下文区旧行号漂移一事实施方已在 progress.md 登记（内容属实、行号作废），不另出 finding。
- 总体判断：实现层整体扎实，AC-001~008、AC-010~015 均有真实代码与测试支撑；但 UNVERIFIED-SPIKE #1 仍未验证使 AC-009 的打勾无证据，判 FAIL。
- 系统性 follow-up：无（#1 的补验已登记在 task.md「环境跳过」项，属本 task 自身的用户机验证义务，非跨 task 缺口）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。后端 DTO/ORM/前端三端默认值均为 humanize/portable_cookies 开启、其余不变；集成测试 test_create_defaults_humanize_and_portable_cookies 重跑通过。
- AC-002：TICK-VALID，re_verified。迁移 0007 只改 server_default 与加 locale CHECK、不改写存量值；test_existing_profile_values_unchanged_by_upgrade 重跑通过。
- AC-003：TICK-VALID，re_verified。TimezoneCombobox 键入过滤/全量滚动/键盘操作代码在位，6 个组件测试随前端全量重跑通过。
- AC-004：TICK-VALID，re_verified。ProfileForm 选时区联动语言、手动覆盖、时区为空语言保持的代码在位，相关 ProfileForm 测试随前端全量重跑通过。
- AC-005：TICK-VALID，re_verified。Literal 枚举与时区/语言校验器在位，集成测试非法值 422 字段级错误重跑通过。
- AC-006：TICK-VALID，trust_prior。en-US 生成 rejectfont 规则与宿主 fontconfig 2.15.0 真实字体 fc-list 测试重跑通过；真实 Browser 内三场景须用户机补验，依赖实施侧已产出的宿主实测证据。
- AC-007：TICK-VALID，trust_prior。zh-CN 配置不追加拒绝规则的单测重跑通过；真实引擎下解析到具体中文字体须用户机补验，依赖实施侧已产出的宿主实测证据。
- AC-008：TICK-VALID，trust_prior。语言修改生成新配置版本一半由集成测试（/versions 为 [1, 2]）重跑验证；重启后字体/navigator.language 一半须用户机真实引擎补验。
- AC-009：TICK-VOID，trust_prior。显式 locale 是否优先于 geoip 推断无任何证据，UNVERIFIED-SPIKE #1 仍在 task.md:102，须用户机真实引擎补验。
- AC-010：TICK-VALID，trust_prior。[deploy]，依赖 AC-006/AC-007 的实现证据；真实部署验证待用户机。
- AC-011：TICK-VALID，re_verified。pick_default_font_set（仅完整性通过集）与 FontSetListResponse、表单预选与显式 null 保持的代码在位，相关单测与集成测试重跑通过。
- AC-012：TICK-VALID，re_verified。A18 fail-closed 单测（绑定集生成失败抛 FontConfigUnavailableError、不启动；未绑定保持回退）重跑通过。
- AC-013：TICK-VALID，re_verified。损坏集导入原子修复与 Coordinator 实时读取（REST runtime_views.py:72 与 SSE runtime_coordinator.py:764 共用 get_font_runtime）代码在位，相关单测重跑通过。
- AC-014：TICK-VALID，re_verified。(platform, set_id) 分组计数与 manifest 平台校验单测重跑通过。
- AC-015：TICK-VALID，re_verified。SessionDetailsPanel「探测字体未覆盖」文案区分与篡改不进 missing_fonts 单测重跑通过。

coverage = 10 / 15

建议合并前人工抽查 trust_prior 项。

verdict: FAIL


## Round 2 (2026-11-11T16:42:39+08:00)

- round：2
- reviewed_at：2026-11-11T16:42:39+08:00

reviewed_scope: 1973e9f3e826758f

## Findings

### t053_code_f004 - 共享 Select 的 onOptionSelect 不覆盖键盘选择：键盘同值重选「无」仍会被延迟到达的后端默认覆盖

- 严重度：important
- 锚点：AC-011——用户选择「无」后保持为无；修复（f005）宣称「每次提交选项都触发，含同值重选」
- 位置：`src/frontend/src/shared/ui/Select.tsx:70`（`onClick={() => onOptionSelect?.(option.value)}`）；`src/frontend/src/features/profiles/ProfileForm.tsx:518-520`（字体集 Select 靠它置 `fontSetUserChosenRef`）
- 问题：`onOptionSelect` 只挂在 `onClick` 上。Radix `SelectItem` 的键盘选择不走 click 事件：`node_modules/@radix-ui/react-select/dist/index.js:1003-1013` 的 `onKeyDown` 在 `SELECTION_KEYS`（`[" ", "Enter"]`，同文件 :110）时直接调 `handleSelect`，全程不派发 click；内容层 keydown（:602）只处理 typeahead 与方向键。键盘打开字体集下拉、回车选中已显示的「无」时，`onValueChange`（值未变，Radix 不调）与 `onOptionSelect`（无 click 事件）均不触发，`fontSetUserChosenRef` 保持 false；随后后端默认到达，`ProfileForm.tsx:243-252` 的默认套用 effect 仍会把「无」改写为默认集。鼠标路径已被 `ProfileForm.test.tsx`「keeps an explicit none font set」固定（实跑通过），但该测试只用 `fireEvent.click`，键盘路径无任何测试覆盖。f005 修复的竞态因此只对鼠标用户关闭，对键盘用户原样存在；且 `Select.tsx:15-21` 的 docstring 称其「每次提交选项都触发」与实际行为不符。
- 建议：把守卫挂到 Radix 每次提交都会走的回调上——对 `SelectPrimitive.Item` 用 `onSelect`（鼠标与键盘均触发）替代 `onClick`，或在 `Select` 内同时处理 `onSelect`；补一个键盘复现测试（查询挂起时键盘选中「无」，释放查询后仍为「无」），并修正 docstring。

## 结论

- 前轮 finding 复核（以 diff/代码/实跑为准，不采信处置表自述）：
  - t053_code_f001（important，AC-009 链路无证据）：已消除。`tests/unit/test_t053_fontconfig_locale.py:427` 的 `test_explicit_locale_reaches_engine_launch_alongside_geoip`（zh-CN/en-US 双值）实测：`runner.start()` 调用中 `locale`、`geoip=True`、`timezone=None` 一并到达 `launch_persistent_context_async`，且同一 locale 驱动生成的 fontconfig（含/不含 `<rejectfont>` 与 locale 一致）；`runner.py:694-697` 的 `locale=cfg.locale, geoip=cfg.geoip` 调用在位。`task.md:102` 的未知契约 #1 已改写为结论（本机已验链路 + 引擎内裁决的用户机补验方法），契约清单内不再有生效的 `UNVERIFIED-SPIKE` 标记（仅存的 `UNVERIFIED` 字样在 :98 的模板说明文字中）。引擎内部是否让显式 locale 优先于出口 IP 推断仍属本机无法验证，progress.md「环境跳过」已写明「本机未验证、不得记为已验」，按链口径（t051 AC-013 / t052 AC-012 前例）AC-009/AC-010 记 TICK-VALID trust_prior。
  - t053_code_f002（minor，时区 `""` 语义分裂）：已消除。`profile_locale.py:71-81` 的 `validate_timezone` 把 `""` 归一化为 `None`，与 `locale_for_timezone("") → None`（:34-41）一致；`ProfileConfig`/`ProfileCreateRequest`/`ProfileUpdateRequest` 均经该校验器（`domain/models.py` 的 `validate_timezone_value`）。`is_valid_timezone("")` 仍为 `False`（:51-72），但其唯一调用方就是 `validate_timezone` 自身，全仓无其他调用者，分工已在 docstring 写明，不构成新的分裂。`test_empty_timezone_means_unset_everywhere` 与 `test_stored_empty_timezone_row_loads_as_unset`（直写 `""` 后重载为 `None`）随后端实跑通过。
  - t053_code_f003（minor，高亮不复位）：已消除。`TimezoneCombobox.tsx:69-74` 的复位 effect 依赖由 `options.length` 改为 `options` 本身（`useMemo` 依赖 `[query, t]`，候选内容变化即新 identity）；`TimezoneCombobox.test.tsx:70` 的同尺寸不同内容键盘测试（`new`/`par` 各 2 候选）复现原问题并固定，随前端实跑通过。
- 本轮新发现：1 条（1 条 important，即 t053_code_f004；无新增 minor）
- 未进表的提示：
  - 文件过大（结论段提示，不进 finding 表）：`ProfileForm.tsx` 约 760 行、font_sets `manifest.py` 约 470 行，仍超 400 行 minor 阈值、未达 800 行 important 阈值，与 Round 1 口径一致；本轮修复净增行数个位，未恶化。
  - 圈复杂度（结论段提示，不进 finding 表）：本轮改动函数均未新增高分支；`Select.tsx` 新增的 `onOptionSelect` 为单行转发，无复杂度变化。
  - 命名锁死核查通过：`src/`、`scripts/`、`compose.yaml` 中 `com.cbrowser.deployment-id` 零命中；默认部署前缀仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/docker_adapter.py:234`），未改动。
  - 引用逐项核对：`task.md:102` 引用的测试名 `test_explicit_locale_reaches_engine_launch_alongside_geoip` 存在且实跑通过；`runner.py` 引用行号与实际调用一致；处置表引用的 `profile_locale.py:71`、`TimezoneCombobox.tsx:74`、`TimezoneCombobox.test.tsx:70`、`Select.tsx:70`、`ProfileForm.tsx:518` 均存在且内容相符。
  - 其余范围外观察沿用 Round 1 结论，本轮未复现新问题；f002 的 `is_valid_timezone` 语义收窄已在 docstring 与测试中固定，无需另出 finding。
- 总体判断：前轮 3 条 finding 均真实修复；但修复中新增的共享 Select 改动留下一个键盘路径缺口（t053_code_f004，important），AC-011「选无保持为无」对键盘用户仍不成立，判 FAIL。
- 系统性 follow-up：无（f004 是本 task 自身的修复缺口，非跨 task 缺口）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。后端 DTO/ORM/前端三端默认值代码在位，相关后端测试随 44 项实跑通过。
- AC-002：TICK-VALID，re_verified。迁移 0007 只改 server_default、不改写存量值，存量值不变测试随 44 项实跑通过。
- AC-003：TICK-VALID，re_verified。TimezoneCombobox 过滤/全量滚动/键盘代码在位，7 个组件测试随前端 18 项实跑通过。
- AC-004：TICK-VALID，re_verified。选时区联动语言、手动覆盖、时区为空语言保持的代码在位，ProfileForm 相关测试随前端 18 项实跑通过。
- AC-005：TICK-VALID，re_verified。语言 Literal 枚举与时区/语言校验器在位，非法值 422 测试随 44 项实跑通过。
- AC-006：TICK-VALID，trust_prior。en-US 生成 rejectfont 规则与宿主 fontconfig 2.15.0 真实字体 fc-list 测试随 44 项实跑通过；真实 Browser 内三场景须用户机补验，依赖实施侧已产出的宿主实测证据。
- AC-007：TICK-VALID，trust_prior。zh-CN 不追加拒绝规则与 fc-match 解析单测随 44 项实跑通过；真实引擎下解析到具体中文字体须用户机补验，依赖实施侧已产出的宿主实测证据。
- AC-008：TICK-VALID，trust_prior。语言修改生成新配置版本一半由集成测试（/versions 为 [1, 2]）与重启重生成 fontconfig 测试随 44 项实跑通过；重启后字体/navigator.language 一半须用户机真实引擎补验。
- AC-009：TICK-VALID，trust_prior。链路测试 test_explicit_locale_reaches_engine_launch_alongside_geoip 随 44 项实跑通过；引擎内显式 locale 是否优先于 geoip 推断本机未验证、不得记为已验，待用户机按 task.md:102 方法补验。
- AC-010：TICK-VALID，trust_prior。[deploy]，依赖 AC-006/AC-007 的实现证据；真实部署验证待用户机。
- AC-011：TICK-VOID，re_verified。鼠标选「无」保持为无已由确定性测试固定并实跑通过；但键盘同值重选「无」不触发 onOptionSelect（Radix 键盘选择不走 click），延迟到达的后端默认仍会覆盖，见 t053_code_f004。
- AC-012：TICK-VALID，re_verified。A18 fail-closed 单测（绑定集生成失败抛错不启动；未绑定保持回退）随 44 项实跑通过。
- AC-013：TICK-VALID，re_verified。损坏集导入原子修复与 Coordinator 实时读取代码在位，相关单测随 44 项实跑通过。
- AC-014：TICK-VALID，re_verified。(platform, set_id) 分组计数与 manifest 平台校验单测随 44 项实跑通过。
- AC-015：TICK-VALID，re_verified。SessionDetailsPanel「探测字体未覆盖」文案区分单测随前端 18 项实跑通过。

coverage = 13 / 15

实跑：后端 `tests/unit/test_t053_profile_locale.py` + `tests/unit/test_t053_fontconfig_locale.py`：44 passed（`~/workspace/.cb-venv-t051/bin/python -m pytest`，`PYTHONPATH=<worktree>/src/backend`）；前端 `TimezoneCombobox.test.tsx` + `ProfileForm.test.tsx`：18 passed（Node 26.13.0，vitest run）。

verdict: FAIL

## Round 3 (2026-11-11T17:12:39+08:00)

- round：3
- reviewed_at：2026-11-11T17:12:39+08:00

reviewed_scope: 0cc2dd5bdc0b8bd6

## Findings

### t053_code_f005 - 鼠标同值重选「无」在真实浏览器里同样到不了 onOptionSelect：onClick 挂在已被卸载的 item 上，AC-011 鼠标路径假绿

- 严重度：important
- 锚点：AC-011——用户选择「无」后保持为无；Round 2 修复的 docstring（`Select.tsx:20-23`）称「pointer picks via `onClick`」
- 位置：`src/frontend/src/shared/ui/Select.tsx:82`（`onClick={() => onOptionSelect?.(option.value)}`）；`src/frontend/src/features/profiles/ProfileForm.test.tsx:288-341`（既有鼠标测试只 `fireEvent.click`）
- 问题：真实鼠标提交的顺序是 pointerdown → pointerup → click，而 Radix 在 pointerup 上提交并关闭菜单：`node_modules/@radix-ui/react-select/dist/index.js:979-985`（`onPointerUp` 在 `pointerType === "mouse"` 时调 `handleSelect`，即 `onUserSelect` + `onOpenChange(false)`，:932-935）。React 对离散事件同步刷状态，菜单在 pointerup 处理结束时已卸载，随后浏览器才派发 click——目标 item 已不在树内，React 的根容器监听收不到这次 click，`Select.tsx:82` 的 `onClick` 全程不触发。于是鼠标同值重选「无」时 `onValueChange`（值未变，Radix 不调）与 `onOptionSelect` 均不触发，`fontSetUserChosenRef` 保持 false，延迟到达的后端默认仍会把「无」改写为默认集——与 f004 的键盘缺口是同一缺陷在鼠标路径上的复现，只是触发机制不同（键盘是根本无回调，鼠标是回调挂在提交后即被卸载的节点上）。既有鼠标测试是假绿：它直接对尚在打开菜单中的 option 派发 click，从未走 pointerup → 关闭 → click 的真实顺序，所以测不出这个问题。实证（审阅期临时 scratch 测试，跑后已删，工作区无残留）：共享 Select 级，忠实序列（trigger pointerdown/up 开菜单 → option pointerdown/up → 对已卸载 option 派 click）下 `onValueChange` 确实被调（pointerup 提交生效、菜单关闭、`option.isConnected === false`），但随后派发的 click 使 `onOptionSelect` 保持 0 次调用；ProfileForm 级同序列复现：deferred 查询释放后选值由「无」被改写为 `win-1`（期望 `Not configured`，实得 `win-1`）。触屏/笔不受影响：Radix 仅在 `pointerType !== "mouse"` 时走 click 提交（dist :973-977），且合成 onClick 里我方处理器先于 Radix 的关闭跑，item 仍在挂载态；键盘路径本轮已真修（见复核）。
- 建议：按 Radix 实际提交漏斗的三路分支分别挂守卫，而不要只依赖 click——item 补 `onPointerUp` 且仅当 `event.pointerType === "mouse"` 时触发（与 dist :979-985 的分支一致，跑在我方处理器先于 Radix 关闭的位置）；`onClick` 保留覆盖 touch/pen（dist :973-977 的非鼠标分支）；`onKeyDown` 保留覆盖键盘。并把鼠标测试改写为忠实序列（trigger pointerdown/up → option pointerdown/up → click，jsdom 需补 `hasPointerCapture` 桩），使它在修复前红、修复后绿。

## 结论

- 前轮 finding 复核（以 diff/代码/实跑为准，不采信处置表自述）：
  - t053_code_f001（important，AC-009 链路无证据）：仍消除。`task.md:102` 已是结论写法（仅 :98 模板说明文字含 `UNVERIFIED` 字样）；`tests/unit/test_t053_fontconfig_locale.py:427` 的链路测试随本轮后端 44 项实跑通过。
  - t053_code_f002（minor，时区 `""` 语义分裂）：仍消除。`profile_locale.py:71-81` 的 `validate_timezone` 把 `""` 归一化为 `None`，与 `locale_for_timezone("") → None`（:34-41）一致；相关测试随本轮后端 44 项实跑通过。
  - t053_code_f003（minor，高亮不复位）：仍消除。`TimezoneCombobox.tsx:69-74` 的复位 effect 依赖为 `options` 本身；同尺寸不同内容键盘测试随本轮前端 552 项实跑通过。
  - t053_code_f004（important，键盘同值重选「无」不触发守卫）：已真实修复。核查逐项成立：(a) 处置表称「审阅建议的 onSelect 在已装 Radix 2.4.1 上不存在」属实——`node_modules/@radix-ui/react-select/dist/index.d.ts` 与 `dist/index.js` 对 `onSelect` 均为 0 命中，`SelectItemProps` 仅含 `value/disabled/textValue`（d.ts :127-131），按字面改确会静默失效；(b) 改挂的 `onKeyDown`（`Select.tsx:83-88`）与 Radix 自身的提交键一致——`SELECTION_KEYS = [" ", "Enter"]`（dist :110），且复用了 Radix 的 `event.target === event.currentTarget` 守卫（dist :1003-1013）；合成处理器里我方回调先于 Radix 的 `handleSelect` 执行，item 仍在挂载态，故 Enter/空格提交必能记下显式选择；(c) 新键盘测试 `ProfileForm.test.tsx:343` 结构上真实复现原问题：与鼠标测试仅差输入方式，而在无 onKeyDown 时从 keydown 到 `onOptionSelect` 不存在任何代码路径（全仓 grep：`onOptionSelect` 的唯一触发点就是 `Select.tsx:82` 的 onClick 与 `:86` 的 onKeyDown），守卫 ref 只能保持 false、默认必改写——红侧由代码路径唯一性保证（审阅只读边界不允许改代码重造红态，此处如实说明，未以改代码方式重跑红）；绿侧随本轮前端 552 项实跑通过；(d) 无重复触发：div 上 Enter/空格不合成 click，鼠标 pointerup 后 Radix 不再走 onClick 提交（`pointerType === "mouse"` 分支，dist :975-976），我方 onClick 只跑一次；(e) docstring 已修正为双路径说明，并写明 Space 在 typeahead 进行时仍计一次选择的边界（`Select.tsx:30-33`），方向安全（仅把当前显示值记为显式选择，不改提交值），不另出 finding；(f) 无 disabled 选项可经此组件产生（`SelectOption` 无 disabled 字段），onKeyDown 未判 disabled 不构成活路径。处置表引用的 `Select.tsx:83`、`Select.tsx:14`、`ProfileForm.test.tsx:343` 行号与内容均相符。
- 本轮新发现：1 条（1 条 important，即 t053_code_f005；无新增 minor）
- 未进表的提示：
  - 文件过大（结论段提示，不进 finding 表）：`ProfileForm.tsx` 实测 767 行、`font_sets/manifest.py` 实测 470 行，仍超 400 行 minor 阈值、未达 800 行 important 阈值；本轮修复净增个位数行，未恶化。
  - 圈复杂度（结论段提示，不进 finding 表）：本轮改动函数均未新增高分支；`Select.tsx` 新增的 onKeyDown 为单条件转发，无复杂度变化。
  - 命名锁死核查通过：`src/`、`scripts/`、`compose.yaml` 中 `com.cbrowser.deployment-id` 零命中（grep exit 1）；默认部署前缀仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/docker_adapter.py:234`），未改动。
  - 引用逐项核对：处置表引用的 `Select.tsx:83`、`Select.tsx:14`、`ProfileForm.test.tsx:343` 均存在且内容相符；Radix 版本实测为 2.4.1（package.json），与处置表一致。
  - 审阅期临时 scratch 测试说明：为验证 f005，我在 `src/frontend/src/shared/ui/__r3_scratch_*.test.tsx`（3 个）与 `src/frontend/src/features/profiles/__r3_scratch_form_mouse.test.tsx`（1 个）写过一次性验证测试，全部已删除，`git status` 复核无残留；验证中途曾发现 jsdom 的 `PointerEvent` 需补 `hasPointerCapture` 桩、以及直接 click 开菜单会误触 Radix 的 trigger-pointerup 一次性 document capture 监听（dist :473-479）导致 pointerup 被 preventDefault——这两点均为 jsdom 实验方法问题，不影响结论，最终复现用的均是忠实序列。
  - 其余范围外观察沿用 Round 1/2 结论，本轮未复现新问题。
- 总体判断：f004 的键盘缺口已真实修复且 onSelect 不存在之说已证实；但同一 AC-011 的鼠标路径在真实浏览器里仍不成立——既有鼠标测试假绿，共享 Select 的 onClick 守卫对鼠标同值重选实际无效，判 FAIL。
- 系统性 follow-up：无（f005 是本 task 自身的守卫缺口，非跨 task 缺口；但同款「Radix 提交后卸载节点上挂 onClick」模式若在其他共享组件存在，值得后续一并排查——本轮 diff 内仅此一处）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。后端 DTO/ORM/前端三端默认值代码在位，相关后端测试随 44 项实跑通过。
- AC-002：TICK-VALID，re_verified。迁移 0007 只改 server_default、不改写存量值，存量值不变测试随 44 项实跑通过。
- AC-003：TICK-VALID，re_verified。TimezoneCombobox 过滤/全量滚动/键盘代码在位，7 个组件测试随前端 552 项实跑通过。
- AC-004：TICK-VALID，re_verified。选时区联动语言、手动覆盖、时区为空语言保持的代码在位，ProfileForm 相关测试随前端 552 项实跑通过。
- AC-005：TICK-VALID，re_verified。语言 Literal 枚举与时区/语言校验器在位，非法值 422 测试随 44 项实跑通过。
- AC-006：TICK-VALID，trust_prior。en-US 生成 rejectfont 规则与宿主 fontconfig 2.15.0 真实字体 fc-list 测试随 44 项实跑通过；真实 Browser 内三场景须用户机补验，依赖实施侧已产出的宿主实测证据。
- AC-007：TICK-VALID，trust_prior。zh-CN 不追加拒绝规则与 fc-match 解析单测随 44 项实跑通过；真实引擎下解析到具体中文字体须用户机补验，依赖实施侧已产出的宿主实测证据。
- AC-008：TICK-VALID，trust_prior。语言修改生成新配置版本一半由集成测试（/versions 为 [1, 2]）与重启重生成 fontconfig 测试随 44 项实跑通过；重启后字体/navigator.language 一半须用户机真实引擎补验。
- AC-009：TICK-VALID，trust_prior。链路测试 test_explicit_locale_reaches_engine_launch_alongside_geoip 随 44 项实跑通过；引擎内显式 locale 是否优先于 geoip 推断本机未验证、不得记为已验，待用户机按 task.md:102 方法补验。
- AC-010：TICK-VALID，trust_prior。[deploy]，依赖 AC-006/AC-007 的实现证据；真实部署验证待用户机。
- AC-011：TICK-VOID，re_verified。键盘同值重选「无」已由新 onKeyDown 与键盘测试固定并实跑通过；但鼠标同值重选「无」在真实浏览器里到不了 onOptionSelect（pointerup 提交即关闭菜单，随后 click 派给已卸载 item），延迟到达的后端默认仍会改写为默认集，见 t053_code_f005。
- AC-012：TICK-VALID，re_verified。A18 fail-closed 单测（绑定集生成失败抛错不启动；未绑定保持回退）随 44 项实跑通过。
- AC-013：TICK-VALID，re_verified。损坏集导入原子修复与 Coordinator 实时读取代码在位，相关单测随 44 项实跑通过。
- AC-014：TICK-VALID，re_verified。(platform, set_id) 分组计数与 manifest 平台校验单测随 44 项实跑通过。
- AC-015：TICK-VALID，re_verified。SessionDetailsPanel「探测字体未覆盖」文案区分单测随前端 552 项实跑通过。

coverage = 10 / 15

建议合并前人工抽查 trust_prior 项。

实跑：后端 `tests/unit/test_t053_profile_locale.py` + `tests/unit/test_t053_fontconfig_locale.py`：44 passed（`~/workspace/.cb-venv-t051/bin/python -m pytest`，`PYTHONPATH=<worktree>/src/backend`）；前端全量 `npm test`（Node 26.13.0，含 `test:types`）：76 files / 552 passed / 0 failed。

verdict: FAIL

## Round 4 (2026-11-11T17:27:39+08:00)

- round：4
- reviewed_at：2026-11-11T17:27:39+08:00

reviewed_scope: a089e455ced309b6

## Findings

### t053_code_f006 - onPointerUp 不校验本次 pointerdown 是否落在本项上：拖过选项松开会误记为显式选择

- 严重度：minor
- 锚点：行为缺陷——守卫 ref 可能在用户未作任何选择时被置位，抑制后端默认自动套用；与 AC-011 的守卫语义（「用户显式选择」才抑制默认）不符
- 位置：`src/frontend/src/shared/ui/Select.tsx:93-101`（`onPointerUp`）
- 问题：我方 `onPointerUp` 只看 `event.pointerType === "mouse"`，而 Radix 是否提交看的是每个 item 自己那份 `pointerTypeRef`（`node_modules/@radix-ui/react-select/dist/index.js:987-991`：仅本项自身的 `onPointerDown`/`onPointerMove` 会把它置为 `"mouse"`，初始值为 `"touch"`；`:983-985` 的提交分支读它）。两者在正常点击时一致，但在「按下在 A 项、拖到 B 项松开」时分叉：Radix 不提交（B 的 ref 仍是 `"touch"`，菜单保持打开、值不变），我方却对 B 触发 `onOptionSelect`。实证（审阅期一次性 scratch 测试，跑后已删，`git status` 无残留）：共享 Select 级，`pointerdown("none") → pointerup("win-1")`（均为 mouse）后 `onOptionSelect` 得 `[["win-1"]]`，而 `onValueChange` 0 次调用、菜单未关闭（`winOpt.isConnected === true`）。落到 ProfileForm 上就是 `fontSetUserChosenRef` 被置 true，但显示值未变；此后后端默认到达也不再自动套用，用户必须手动再选一次。触发路径窄（需按住拖过选项再松开，或在 trigger 上按下后拖入菜单松开），后果仅为默认不再自动套用、可手动恢复，无错误值落盘、无崩溃，故 minor。
- 建议：让守卫与 Radix 的提交门保持同一条件——在 item 上记一个 ref（如 `onPointerDown` 置位、`onPointerUp`/`onPointerLeave` 清零），仅当本次 pointerdown 落在本项时才在 pointerup 触发 `onOptionSelect`。

## 结论

- 前轮 finding 复核（以 diff/代码/实跑为准，不采信处置表自述）：
  - t053_code_f001（important，AC-009 链路无证据）：仍消除。`task.md` 内仅 :98 模板说明文字含 `UNVERIFIED` 字样；`tests/unit/test_t053_fontconfig_locale.py:427` 的链路测试随本轮后端 44 项实跑通过。引擎内显式 locale 是否优先于 geoip 推断仍属本机未验证，progress.md「环境跳过」已写明「本机未验证、不得记为已验」，按链口径 AC-009/AC-010 记 TICK-VALID trust_prior。
  - t053_code_f002（minor，时区 `""` 语义分裂）：仍消除。`profile_locale.py:71-81` 的 `validate_timezone` 把 `""` 归一化为 `None`，与 `locale_for_timezone("") → None`（:34-41）一致；`is_valid_timezone("")` 仍为 `False`，但其唯一调用方就是 `validate_timezone` 自身，分工已在 docstring 写明；相关测试随本轮后端 44 项实跑通过。
  - t053_code_f003（minor，高亮不复位）：仍消除。`TimezoneCombobox.tsx:69-74` 的复位 effect 依赖为 `options` 本身；7 个组件测试随本轮前端 552 项实跑通过。
  - t053_code_f004（important，键盘同值重选不触发守卫）：仍消除。`Select.tsx:103-108` 的 `onKeyDown` 与 Round 3 核查一致，未被本轮改动；键盘测试随本轮前端 552 项实跑通过。
  - t053_code_f005（important，鼠标同值重选在真实浏览器里到不了 onOptionSelect）：已真实修复。核查逐项成立：(a) 修复代码在位——`Select.tsx:93-101` 的 `onPointerUp` 仅 `pointerType === "mouse"` 时触发 `onOptionSelect`，`onClick`（:92）留给 touch/pen，`onKeyDown`（:103-108）留给键盘；(b) 与 Radix 2.4.1 dist 实际行为逐项一致——鼠标提交分支为 `onPointerUp` 内 `pointerTypeRef.current === "mouse"`（dist :983-985，`pointerTypeRef` 由本项 `onPointerDown` 置位，:987-988），非鼠标分支为 `onClick` 内 `pointerTypeRef.current !== "mouse"`（dist :973-977），`composeEventHandlers` 使用者处理器先跑、Radix 自身处理器在后（`@radix-ui/primitive/dist/index.js:35-42`），且我方处理器不调 `preventDefault`、不会跳过 Radix 的关闭；docstring 引用的行号（:979-985、:973-977）与 dist 实际位置相符；(c) 三路无重复触发，审阅期 scratch 实测（共享 Select 级，跑后已删）：鼠标忠实序列下 `onOptionSelect` 恰 1 次、`onValueChange` 0 次、pointerup 后 `option.isConnected === false`、随后对已卸载 option 派 click 计次仍为 1；touch 序列 pointerup 0 次、click 恰 1 次；键盘 Enter 恰 1 次、无指针/click 事件；真实浏览器里 div[role=option] 的 Enter/Space 不合成 click，鼠标 click 派给已卸载节点到不了 React 根容器监听；(d) 忠实序列鼠标测试真实复现原问题——红侧由计数算术保证：修复前鼠标路径唯一的 `onOptionSelect` 触发点就是 `onClick`，而 scratch 实测证明 pointerup 后的 click 对它贡献 0 次，故修复前同一序列下守卫 ref 只能保持 false、延迟到达的默认必改写（与 Round 3 报告的红态「期望 `Not configured`，实得 `win-1`」机制一致；只读边界不允许改代码重造红态，此处如实说明，未以改代码方式重跑红）；绿侧为改写后的鼠标测试随本轮前端 552 项实跑通过，且 `ProfileForm.test.tsx` 12 项单跑中鼠标与键盘两项均明确通过；(e) `isConnected === false` 断言固定的是真实浏览器条件——菜单在 pointerup 的离散事件同步刷状态时卸载，随后 click 才派发，我方 scratch 在共享 Select 级独立复现了同一时序；(f) jsdom 的 `hasPointerCapture` 补桩恰当、无副作用：桩在 `ProfileForm.test.tsx:33-37`（`typeof` 守卫、返回 `false` 并补 `releasePointerCapture` 空实现），只满足 Radix trigger `onPointerDown` 的 `hasPointerCapture` 调用（dist :303-305），返回 false 即「无捕获」的常规点击路径，不改变提交语义；同款桩在 `EnvironmentSwitcher` 等 5 个以上既有测试文件中已有先例，非本 task 新造的特殊处理；(g) docstring 已修正为三路说明并写明 `onClick` 不能覆盖鼠标路径的原因，与实测一致；(h) `Select` 仅 `ProfileForm.tsx:518` 一个调用方用 `onOptionSelect`，其余调用方不受影响；`onKeyDown` 未判 disabled 不构成活路径（`SelectOption` 无 disabled 字段），沿用 Round 3 结论。
- 本轮新发现：1 条（1 条 minor，即 t053_code_f006；无新增 important/critical）
- 未进表的提示：
  - 文件过大（结论段提示，不进 finding 表）：`ProfileForm.tsx` 实测 767 行、`font_sets/manifest.py` 实测 470 行，仍超 400 行 minor 阈值、未达 800 行 important 阈值；本轮修复净增个位数行，未恶化。
  - 圈复杂度（结论段提示，不进 finding 表）：本轮改动函数均未新增高分支；`Select.tsx` 新增的 `onPointerUp` 为单条件转发，无复杂度变化。
  - 命名锁死核查通过：`src/`、`scripts/`、`compose.yaml` 中 `com.cbrowser.deployment-id` 零命中（grep exit 1）；默认部署前缀仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/docker_adapter.py:234`），未改动；其余命中均在 progress.md/review 报告等历史叙述中提及被驳回的偏离，属允许范围。
  - 引用逐项核对：处置表引用的 `Select.tsx:22`、`Select.tsx:93`、`ProfileForm.test.tsx:294` 均存在且内容相符；Radix 版本实测为 2.4.1（`src/frontend/package.json:35`），与处置表一致；docstring 的 dist 行号引用与实际位置相符（见 f005 复核 (b)）。
  - 审阅期一次性 scratch 测试说明：为验证三路分离与 f006，我在 `src/frontend/src/shared/ui/__r4_scratch_select.test.tsx` 写过 4 项一次性验证测试（鼠标/touch/键盘各 1 项、拖过选项 1 项），全部通过后已删除，`git status` 复核无残留（`scratch` 命中 0）；该文件曾短暂导致 `npm test` 的 `test:types` 门失败（`vi.fn()` 未标注类型），已在删除前修正类型标注并单独重跑通过，不影响最终全量结果。
  - 其余范围外观察沿用 Round 1/2/3 结论，本轮未复现新问题。
- 总体判断：f005 已真实修复——三路提交分离与 Radix 2.4.1 dist 实际行为逐项一致、无重复触发，忠实序列鼠标测试先红（机制保证）后绿（实跑通过），AC-011 鼠标与键盘路径均已成立；仅剩 1 条 minor（f006，拖过选项误记显式选择，触发窄、后果轻），判 PASS。
- 系统性 follow-up：无（f006 是本 task 自身共享 Select 守卫的边界情形，非跨 task 缺口；同款「pointerup 不校验 pointerdown 落点」模式若在其他共享组件存在，值得后续一并排查——本轮 diff 内仅此一处）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。后端 DTO/ORM/前端三端默认值代码在位，相关后端测试随 44 项实跑通过。
- AC-002：TICK-VALID，re_verified。迁移 0007 只改 server_default、不改写存量值，存量值不变测试随 44 项实跑通过。
- AC-003：TICK-VALID，re_verified。TimezoneCombobox 过滤/全量滚动/键盘代码在位，7 个组件测试随前端 552 项实跑通过。
- AC-004：TICK-VALID，re_verified。选时区联动语言、手动覆盖、时区为空语言保持的代码在位，ProfileForm 相关测试随前端 552 项实跑通过。
- AC-005：TICK-VALID，re_verified。语言 Literal 枚举与时区/语言校验器在位，非法值 422 测试随 44 项实跑通过。
- AC-006：TICK-VALID，trust_prior。en-US 生成 rejectfont 规则与宿主 fontconfig 2.15.0 真实字体 fc-list 测试随 44 项实跑通过；真实 Browser 内三场景须用户机补验，依赖实施侧已产出的宿主实测证据。
- AC-007：TICK-VALID，trust_prior。zh-CN 不追加拒绝规则与 fc-match 解析单测随 44 项实跑通过；真实引擎下解析到具体中文字体须用户机补验，依赖实施侧已产出的宿主实测证据。
- AC-008：TICK-VALID，trust_prior。语言修改生成新配置版本一半由集成测试（/versions 为 [1, 2]）与重启重生成 fontconfig 测试随 44 项实跑通过；重启后字体/navigator.language 一半须用户机真实引擎补验。
- AC-009：TICK-VALID，trust_prior。链路测试 test_explicit_locale_reaches_engine_launch_alongside_geoip 随 44 项实跑通过；引擎内显式 locale 是否优先于 geoip 推断本机未验证、不得记为已验，待用户机按 task.md:102 方法补验。
- AC-010：TICK-VALID，trust_prior。[deploy]，依赖 AC-006/AC-007 的实现证据；真实部署验证待用户机。
- AC-011：TICK-VALID，re_verified。鼠标忠实序列与键盘两项测试随前端 552 项实跑通过；三路提交分离与 Radix dist 行为逐项核实、无重复触发，见 f005 复核；仅剩 minor 边界 f006（拖过选项误记），不影响 AC 核心路径。
- AC-012：TICK-VALID，re_verified。A18 fail-closed 单测（绑定集生成失败抛错不启动；未绑定保持回退）随 44 项实跑通过。
- AC-013：TICK-VALID，re_verified。损坏集导入原子修复与 Coordinator 实时读取代码在位，相关单测随 44 项实跑通过。
- AC-014：TICK-VALID，re_verified。(platform, set_id) 分组计数与 manifest 平台校验单测随 44 项实跑通过。
- AC-015：TICK-VALID，re_verified。SessionDetailsPanel「探测字体未覆盖」文案区分单测随前端 552 项实跑通过。

coverage = 11 / 15

建议合并前人工抽查 trust_prior 项。

实跑：后端 `tests/unit/test_t053_profile_locale.py` + `tests/unit/test_t053_fontconfig_locale.py`：44 passed（`~/workspace/.cb-venv-t051/bin/python -m pytest`，`PYTHONPATH=<worktree>/src/backend`）；前端全量 `npm test`（Node 26.13.0，含 `test:types`）：552 passed / 0 failed；`ProfileForm.test.tsx` + `TimezoneCombobox.test.tsx` 单跑：19 passed（含鼠标/键盘两项「保持显式无字体集」）。

verdict: PASS


## Round 5 (2026-11-11T09:53:01+08:00)

- round：5
- reviewed_at：2026-11-11T09:53:01+08:00

reviewed_scope: 634fc4db6bd1d4cc

## Findings

### t053_code_f007 - pointermove 进入的同值提交漏过 onOptionSelect：守卫条件比 Radix 自身的提交条件窄

- 严重度：minor
- 锚点：AC-011 守卫语义（只有「用户显式选择」才抑制后端默认自动套用）；`Select.tsx:20-23` 的 docstring 称「Fires for every committed option pick」「All three commit paths are covered」，与实际不符
- 位置：`src/frontend/src/shared/ui/Select.tsx:125-141`（`onPointerDown` / `onPointerUp` / `pressedRef`）
- 问题：Radix 的提交条件是 item 自身 `pointerTypeRef.current === "mouse"`，而该 ref 由本项的 `onPointerDown`（dist `:987-989`）**或** `onPointerMove`（dist `:991-992`，赋值在 `:992`）任一置位；我方 `pressedRef` 只在 `onPointerDown` 置位。带移动的拖拽/悬停会先由 `pointermove` 置 Radix 的 ref，`pointerup` 时 Radix 提交，但我方 `onOptionSelect` 不触发。实证（审阅期一次性 scratch 测试 `__r5_scratch_pointermove.test.tsx`，5 项探针，跑后已删，`git status` 无残留）：
  - A：press "None" → pointermove 到 "win-1" → pointerup 落 "win-1"：Radix 提交（`onValueChange=[["win-1"]]`，菜单关闭），`onOptionSelect=[]`——值变化路径在 ProfileForm 由 `onValueChange` 补记 ref（`ProfileForm.tsx:511`），无用户可见缺口。
  - D：仅悬停 "win-1"（pointermove，无按下）→ press "None" → release "win-1"：Radix 提交 "win-1"（`onValueChange` 触发、菜单关闭），`onOptionSelect=[]`——证明 pointermove 单独即可置 Radix 的 ref。
  - B：press "win-1" → pointerleave → pointermove 回 "win-1" → release "win-1"（同值）：两者均静默、菜单关闭——Radix 已提交（同值故无 `onValueChange`），显式选择漏记。
  - C2：正常开菜单 → pointermove 到 "None" → release "None"（同值）：两者均静默、菜单关闭——同值提交漏记。
  - C：trigger 按下后直接拖入菜单、在已显示的 "None" 上松开（无 trigger pointerup）：jsdom 下菜单未关闭、无提交、无分歧——结论不定，不作证据；真实浏览器行为应与 C2 一致，但本轮不据此断案。
- 实际影响（判定）：用户可见缺口只存在于「查询挂起（菜单仅「无」一项、显示值即「无」）期间用拖拽手势选「无」，随后后端默认到达并覆盖」这一组合；触发比 f006 更窄、后果为默认套用一次、可一点恢复、无错误值落盘；查询已解析后同值拖拽无覆盖可能（默认已套用，`defaultFontSetAppliedRef` 守卫，`ProfileForm.tsx:242-252`）。故 minor，不阻断。
- 建议：`onPointerMove`（mouse）时同样置 `pressedRef.current = true`，使守卫与 Radix 的 `pointerTypeRef` 条件逐位一致（pointerdown 或 pointermove 任一置位）；f006 的无移动拖过情形仍静默（B 从未收到任何指针事件），B/C2/D 随后触发；补一个 pointermove 进入的同值提交测试；修复后 docstring「每次提交都触发」的表述恢复准确。

## 结论

- 前轮 finding 复核（以 diff/代码/实跑为准，不采信处置表自述）：
  - t053_code_f001（important，AC-009 链路无证据）：仍消除。`task.md` 内仅 `:98` 模板说明文字含 `UNVERIFIED-SPIKE` 字样；`tests/unit/test_t053_fontconfig_locale.py:427` 的链路测试随本轮后端 44 项实跑通过。引擎内显式 locale 是否优先于 geoip 推断仍属本机未验证，progress.md「环境跳过」已写明「本机未验证、不得记为已验」，按链口径 AC-009/AC-010 记 TICK-VALID trust_prior。
  - t053_code_f002（minor，时区 `""` 语义分裂）：仍消除。`profile_locale.py:71-81` 的 `validate_timezone` 把 `""` 归一化为 `None`，与 `locale_for_timezone("") → None` 一致；相关测试随本轮后端 44 项实跑通过。
  - t053_code_f003（minor，高亮不复位）：仍消除。`TimezoneCombobox.tsx:76` 的复位 effect 依赖为 `options` 本身；7 个组件测试随本轮前端全量实跑通过。
  - t053_code_f004（important，键盘同值重选不触发守卫）：仍消除。`Select.tsx:145` 的 `onKeyDown` 未被本轮改动，与 Radix `SELECTION_KEYS = [" ", "Enter"]`（dist `:110`）及 `event.target === event.currentTarget` 守卫（dist `:1003-1005`）一致；键盘测试随本轮前端 13 项实跑通过。
  - t053_code_f005（important，鼠标同值重选在真实浏览器里到不了 onOptionSelect）：仍消除。`Select.tsx:130-141` 的 `onPointerUp` 鼠标分支与忠实序列鼠标测试均在位，随本轮前端 13 项实跑通过；三路分离未被本轮改动。
  - t053_code_f006（minor，拖过选项松开误记显式选择）：已真实修复，核查逐项成立：(a) per-item `pressedRef` 机制正确——`onPointerDown` 仅 mouse 置位（`Select.tsx:125-129`，置位在 `:127`）、`onPointerUp` 仅 mouse 且 `pressedRef.current` 为真时触发、随后无条件清零（`:130-141`，触发在 `:137`、清零在 `:140`）、`onPointerLeave` 清零（`:142-144`）；ref 按 item 实例持有（`SelectItem` 组件内 `useRef`，`:120`，key 为 `option.value`，稳定）；`onClick`（`:124`，touch/pen）与 `onKeyDown`（`:145` 起，键盘）未动；(b) 三路无重复触发、无遗漏提交路径——鼠标 pointerup 恰触发 1 次（同项测试断言 `toHaveBeenCalledTimes(1)`）、随后 click 派给已卸载 item 不再触发；touch pointerup 为空操作、随后 click 恰 1 次；键盘 Enter/空格恰 1 次；值变化的提交走 `onValueChange`，ProfileForm 在该路同样置 ref（`ProfileForm.tsx:511`），故守卫覆盖全部提交路径，唯 pointermove 进入的同值提交例外，见本轮新 finding f007；(c) 拖过测试与同项测试真实——拖过测试先红后绿可信：Round 3 版 `onPointerUp` 对 mouse 无条件触发（Round 4 报告引用的原代码），该测试断言 pointerdown 落 "None"、pointerup 落 "win-1" 后 `onOptionSelect` 未被调用，修复前必红（Round 4 审阅的独立 scratch 实证 spy 得 `[["win-1"]]` 佐证），绿侧随本轮 `Select.test.tsx` 3 项实跑通过；同项按下抬起测试为绿-绿防回归桩（修复前后均应触发 1 次，处置表自述「同期已绿」与代码一致），touch 测试为覆盖补齐，均不冒充先红后绿；(d) 表单级拖过测试删除合理——查询挂起时 `fontSets = fontSetsData?.items ?? EMPTY_FONT_SETS`（`ProfileForm.tsx:199`）为空，`fontSetOptions` 只有 `__none__` 一项（`:276-282`），无第二项可拖；查询解析后默认套用 effect 已跑过（`defaultFontSetAppliedRef` 守卫，`:242-252`），「拖过后默认仍套用」在表单级不可复现；切平台路径自行复位 ref 并直接套用新平台默认（`:490`），不经守卫；(e) 修复方如实说明的 pointermove 一点属实且构成残留缺口——Radix 自身 `pointerTypeRef` 确由 pointermove 置位（dist `:991-992`，处置表写的 `:994-995` 偏后约 2 行，实为 `:994` 的 `else if` 行，实质无误），真实浏览器带移动的拖拽确由 Radix 提交（探针 A/D 实测），本修复只以 pointerdown 落点为准，未覆盖该情形，记为本轮新 minor f007，不藏不瞒；(f) 修复未引入新问题——`SelectItem` 抽取无重挂载风险（key 稳定、ref 按实例持有）；`pointercancel` 后 `pressedRef` 可能残留为真，但 Radix 自身的 `pointerTypeRef` 同样只在 pointerdown/move 置位、cancel 时不清理，两者同态，不构成新的分叉；`SelectOption` 无 disabled 字段，`onKeyDown` 未判 disabled 不构成活路径，沿用前轮结论。
- 本轮新发现：1 条（1 条 minor，即 t053_code_f007；无新增 important/critical）
- 未进表的提示：
  - 文件过大（结论段提示，不进 finding 表）：`ProfileForm.tsx` 实测 767 行、`font_sets/manifest.py` 实测 470 行，仍超 400 行 minor 阈值、未达 800 行 important 阈值；本轮零改动，未恶化。
  - 圈复杂度（结论段提示，不进 finding 表）：本轮改动函数均为单条件转发，无新增 ≥10 的函数。
  - 命名锁死核查通过：`src/`、`scripts/`、`compose.yaml` 中 `com.cbrowser.deployment-id` 零命中（grep exit 1）；默认部署前缀仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/docker_adapter.py:234`），未改动。
  - 引用逐项核对：处置表引用的 `Select.tsx:106`（实为 `SelectItem` 在 `:105`，行号差 1，内容相符）、`Select.tsx:121`（`pressedRef` 实际在 `:120`，行号差 1）、`Select.tsx:126`（置位实际在 `:127`，行号差 1）、`Select.test.tsx:39`（拖过测试）、`Select.test.tsx:77`（同项测试）均存在且内容相符；Radix dist 行号逐项实测——`SELECTION_KEYS` `:110`、onClick 非鼠标分支 `:975-977`、onPointerUp 鼠标分支 `:983-985`、onPointerDown 置位 `:987-989`、onPointerMove 置位 `:991-992`、onKeyDown 守卫 `:1003-1005`；Radix 版本仍为 2.4.1。
  - 审阅期一次性 scratch 测试说明：我在 `src/frontend/src/shared/ui/__r5_scratch_pointermove.test.tsx` 写过 5 项一次性探针（A/B/C/C2/D），全部跑后已删，`git status` 复核无本人残留；并行 test 路审阅员的一次性探针文件（`__r5_test_pm_c.test.tsx`）在本轮前端全量进行中出现、随后被其本人删除，非本 task 交付、其结论我未参考——全量 1 项失败即落在该文件上，交付文件 77 files / 556 tests 全绿。
  - 其余范围外观察沿用 Round 1/2/3/4 结论，本轮未复现新问题。
- 总体判断：f006 已真实修复——per-item pressedRef 与 Radix 无移动提交条件逐项一致、三路无重复触发、拖过测试先红（机制保证）后绿（实跑通过）、表单级删除理由成立；仅剩 1 条 minor（f007，pointermove 进入的同值提交漏记，触发窄、后果轻、有明确一行修复方向），判 PASS。
- 系统性 follow-up：无（f007 是本 task 自身共享 Select 守卫的边界情形，非跨 task 缺口；同款「守卫条件比被守卫的提交条件窄」模式若在其他共享组件存在，值得后续一并排查——本轮 diff 内仅此一处）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。后端 DTO/ORM/前端三端默认值代码在位，相关后端测试随 44 项实跑通过。
- AC-002：TICK-VALID，re_verified。迁移 0007 只改 server_default、不改写存量值，存量值不变测试随 44 项实跑通过。
- AC-003：TICK-VALID，re_verified。TimezoneCombobox 过滤/全量滚动/键盘代码在位，7 个组件测试随前端全量实跑通过。
- AC-004：TICK-VALID，re_verified。选时区联动语言、手动覆盖、时区为空语言保持的代码在位，ProfileForm 相关测试随前端全量实跑通过。
- AC-005：TICK-VALID，re_verified。语言 Literal 枚举与时区/语言校验器在位，非法值 422 测试随 44 项实跑通过。
- AC-006：TICK-VALID，trust_prior。en-US 生成 rejectfont 规则与宿主 fontconfig 2.15.0 真实字体 fc-list 测试随 44 项实跑通过；真实 Browser 内三场景须用户机补验，依赖实施侧已产出的宿主实测证据。
- AC-007：TICK-VALID，trust_prior。zh-CN 不追加拒绝规则与 fc-match 解析单测随 44 项实跑通过；真实引擎下解析到具体中文字体须用户机补验，依赖实施侧已产出的宿主实测证据。
- AC-008：TICK-VALID，trust_prior。语言修改生成新配置版本一半由集成测试（/versions 为 [1, 2]）与重启重生成 fontconfig 测试随 44 项实跑通过；重启后字体/navigator.language 一半须用户机真实引擎补验。
- AC-009：TICK-VALID，trust_prior。链路测试 test_explicit_locale_reaches_engine_launch_alongside_geoip 随 44 项实跑通过；引擎内显式 locale 是否优先于 geoip 推断本机未验证、不得记为已验，待用户机按 task.md:102 方法补验。
- AC-010：TICK-VALID，trust_prior。[deploy]，依赖 AC-006/AC-007 的实现证据；真实部署验证待用户机。
- AC-011：TICK-VALID，re_verified。鼠标忠实序列、同项按下抬起、键盘、touch 四项测试随前端全量实跑通过；f006 已真实修复；仅剩 minor 边界 f007（pointermove 进入的同值提交漏记，须查询挂起期拖拽手势才触发），不影响 AC 核心路径。
- AC-012：TICK-VALID，re_verified。A18 fail-closed 单测（绑定集生成失败抛错不启动；未绑定保持回退）随 44 项实跑通过。
- AC-013：TICK-VALID，re_verified。损坏集导入原子修复与 Coordinator 实时读取代码在位，相关单测随 44 项实跑通过。
- AC-014：TICK-VALID，re_verified。(platform, set_id) 分组计数与 manifest 平台校验单测随 44 项实跑通过。
- AC-015：TICK-VALID，re_verified。SessionDetailsPanel「探测字体未覆盖」文案区分单测随前端全量实跑通过。

coverage = 11 / 15

建议合并前人工抽查 trust_prior 项。

实跑：后端 `tests/unit/test_t053_profile_locale.py` + `tests/unit/test_t053_fontconfig_locale.py`：44 passed（`~/workspace/.cb-venv-t051/bin/python -m pytest`，`PYTHONPATH=<worktree>/src/backend`）；前端受影响 3 文件（`Select.test.tsx` + `ProfileForm.test.tsx` + `TimezoneCombobox.test.tsx`）：23 passed（首轮 3 文件并跑时 `ProfileForm.test.tsx`「renders the four sections, blocks an empty name and submits」曾 1 次失败，错误文本未留存；单跑与重跑均通过，未复现，记为瞬时 flaky 而非回归）；前端全量 `npm test`（Node 26.13.0，含 `test:types`）：交付文件 77 files / 556 passed / 0 failed（另有并行 test 路一次性探针文件 2 tests / 1 failed，已被其本人删除，不计入交付）；审阅期一次性探针（A/B/C/C2/D）5 项均跑后删除，结论见 f007。

verdict: PASS

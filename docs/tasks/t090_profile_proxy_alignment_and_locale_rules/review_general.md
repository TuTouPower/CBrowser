# Task review t090（reviewer_focus: 通用）

- task：`t090_profile_proxy_alignment_and_locale_rules`
- spec：`docs/tasks/t090_profile_proxy_alignment_and_locale_rules/task.md`
- diff_anchor：`1f949747dc2d93a935aa9ed9448f0bd25b928b1d`
- target：`git diff 1f949747dc2d93a935aa9ed9448f0bd25b928b1d`
- round：1
- reviewed_at：2026-11-19T16:49:43+08:00

reviewed_scope: 9ce244155d6619ec

## Findings

### t090_gen_f001 - AC-002 测试标题声明覆盖重置操作但未显式断言重置后的摘要字体状态文本

- 严重度：minor
- 锚点：AC-002（「覆盖初始化加载、切换开关与重置操作」）及测试可信与一致性
- 位置：`src/frontend/src/features/profiles/ProfileForm.test.tsx:587-627`（另见 `:520-538`）
- 问题：`ProfileForm.test.tsx:587` 的测试标题声明覆盖 `across init, toggle, and reset (t090 AC-002)`，但测试体内仅覆盖了英文配置开 CJK 初始化（`:588-601`）、取消勾选开关（`:603-610`）与中文配置关 CJK 初始化（`:613-626`），并未执行重置操作；而 AC-001 用例在点击 `profile-form-reset-alignment` 后（`:520-538`）仅断言了复选框 `aria-checked="false"` 与摘要包含 `"Aligned to proxy (JP)"`，未显式断言摘要文本中的 `en.formAlignFontsEn`。生产代码 `src/frontend/src/features/profiles/ProfileForm.tsx:591-593` 的 `fontRule` 无条件读取 `values.include_cjk_fonts` 且 `:657-658` 重置会写入 `defaultIncludeCjkForLocale(resetLocale)`，实现本身无缺陷，故此项仅属测试断言补强。
- 建议：在 `ProfileForm.test.tsx:536-538` 或 AC-002 用例内补充点击 `profile-form-reset-alignment` 后对 `profile-form-alignment-summary` 包含 `en.formAlignFontsEn`（及中文代理重置后包含 `en.formAlignFontsZh`）的显式断言。

### t090_gen_f002 - `docs/specs/profile_management.md` 历史小节与 `t090` 新规在切换语言联动时区上存在表述冲突

- 严重度：minor
- 锚点：文档一致性（不计 blocking）
- 位置：`docs/specs/profile_management.md:110` 与 `docs/specs/profile_management.md:160`
- 问题：`## 语言、时区与参数自动对齐（t053+）` 下的 `docs/specs/profile_management.md:110` 仍写明「切换语言（`locale`）时，在已设时区时对齐对应地区时区」，与本 diff 新增的 `## 代理对齐摘要、词边界匹配与语言不回改时区（t090）`（`:160`：「当已选代理存在推断时区或当前已有非空 `timezone` 时，切换 `locale` 不得改写 `timezone`」）直接冲突。
- 建议：在 `docs/specs/profile_management.md:110` 补充 `（t090 修订）` 并改写为与 `:160` 一致的规则，消除同一文档内的双向矛盾。

## 结论

- 本轮新发现：2 条（均为 minor，无 critical / important）
- 未进表的提示：`src/frontend/src/features/profiles/ProfileForm.tsx` 全文 936 行（本 diff 净增 18 行），属于既有大组件，按规范仅作规模提示；独立复跑 `npm test --prefix src/frontend`（87 files / 722 tests passed，其中 `profile_locale.test.ts` 7 passed、`ProfileForm.test.tsx` 16 passed、`ProfileForm.t058.test.tsx` 5 passed）、`npm run test:types`、`npm run build`、`npm run design:lint`、`npm run design:check` 均退出码 0；外部非 E2E 门禁清单 `.scratch/t090_non_e2e_gates/manifest.json` 9 个套件 `all_passed: true`。
- 总体判断：核心实现与回归测试覆盖均准确闭环（异步代理到达后的偏离判定与重置、CJK 字体规则读取真实开关、`timezoneForProxy` ASCII 词边界匹配、已有代理/非空时区下切语言不覆盖时区，且保持 `zh-CN` / `en-US` 边界与后端零改动），无未解决 critical / important，全部 AC 复验成立。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`src/frontend/src/features/profiles/ProfileForm.tsx:576-668` 依据实时 `selectedProxy` 推导 `proxyInferredTz` 与 `expectedProxyLocale`，在时区或 `activeLocale` 任一不一致时设置 `proxyMismatch=true` 并渲染 `formAlignProxyOverriddenSummary`（不渲染 `formAlignProxySummary`）与 `profile-form-reset-alignment` 按钮，点击后重置 `timezone`/`locale`/`include_cjk_fonts` 回到对齐态；`src/frontend/src/features/profiles/ProfileForm.test.tsx:472-585` 验证了异步 `proxies.list` 到达后的偏离提示与重置恢复、仅时区偏离以及完全匹配时不显示重置提示。
- AC-002：TICK-VALID，re_verified。`src/frontend/src/features/profiles/ProfileForm.tsx:591-593,608-626` 使 `fontRule` 无条件由 `values.include_cjk_fonts` 派生并传入全部三类摘要文案；`src/frontend/src/features/profiles/ProfileForm.test.tsx:587-627` 验证了英文开 CJK、切换开关以及中文关 CJK 的摘要展示，`:520-538` 与 `:357-395` 验证了代理切换及重置时 `include_cjk_fonts` 与摘要联动更新。
- AC-003：TICK-VALID，re_verified。`src/frontend/src/features/profiles/profile_locale.ts:73-141` 的 `hasRegionTerm` 对纯 ASCII 关键字/缩写使用 `(?:^|[^a-z])...(?:$|[^a-z])` 边界匹配，`src/frontend/src/features/profiles/ProfileForm.tsx:546-568` 在 `proxyInferredTz != null || Boolean(prev.timezone) || timezoneManualRef.current` 时保留原时区、仅无代理且无时区时沿用默认联动；`profile_locale.test.ts:77-93`、`ProfileForm.test.tsx:456-470,629-683` 及本轮复跑前端全量 Vitest（722 passed）、`test:types` 与生产构建均通过。

coverage = 3 / 3

verdict: PASS

## Round 2 (2026-11-19T16:59:42+08:00)

reviewed_scope: b5688e428f1894a4

## Findings

本轮无新增 finding。已核对 Round 2 增量修改未引入新问题。

## 结论

- 前轮 finding 复核：
    - `t090_gen_f001`：**已消除**。`src/frontend/src/features/profiles/ProfileForm.test.tsx:539-541` 已补充 JP 代理重置后对 `en.formAlignFontsEn` 的显式断言；`:616-647` 在 AC-002 测试中新增 `px-cn`（Shanghai）代理偏差重置场景，点击 `profile-form-reset-alignment` 后验证摘要包含 `en.formAlignFontsZh`。
    - `t090_gen_f002`：**已消除**。`docs/specs/profile_management.md:110` 已修订为「仅在无代理推断且当前未设 `timezone` 时才按语言对齐默认时区；当已选代理存在推断时区或当前已有非空 `timezone` 时，切换 `locale` 不得改写 `timezone`（t090 修订，详见下文 t090 小节）」，与 `:160` 一致。
- 本轮新发现：0 条
- 未进表的提示：复跑全量前端 Vitest（87 files / 722 tests passed，其中 `profile_locale.test.ts` 7 passed、`ProfileForm.test.tsx` 16 passed、`ProfileForm.t058.test.tsx` 5 passed）、`npm run test:types`、`npm run build`、`npm run design:lint`（0 error / 0 warning）与 `npm run design:check` 均通过，且工作区无额外脏文件。
- 总体判断：Round 1 两项 minor finding 均已真修消除，无未解决 critical / important，全部 AC 复验成立。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`src/frontend/src/features/profiles/ProfileForm.tsx:576-668` 在时区或语言与代理推断默认任一偏离时展示 `formAlignProxyOverriddenSummary` 与 `profile-form-reset-alignment`，点击后重置三字段并恢复对齐态；`src/frontend/src/features/profiles/ProfileForm.test.tsx:472-588` 验证了异步代理到达、重置回退与 `en.formAlignFontsEn` 摘要、仅时区偏离及完全匹配场景。
- AC-002：TICK-VALID，re_verified。`src/frontend/src/features/profiles/ProfileForm.tsx:591-593,608-626` 使 `fontRule` 始终读取 `values.include_cjk_fonts`；`src/frontend/src/features/profiles/ProfileForm.test.tsx:590-648` 完整覆盖英文开 CJK 初始化、开关切换、中文关 CJK 初始化及 `px-cn` 重置后恢复 `en.formAlignFontsZh` 摘要展示。
- AC-003：TICK-VALID，re_verified。`src/frontend/src/features/profiles/profile_locale.ts:73-141` 执行 ASCII 词边界匹配，`src/frontend/src/features/profiles/ProfileForm.tsx:546-568` 在已有代理推断或非空时区时保留原时区；`profile_locale.test.ts:77-93`、`ProfileForm.test.tsx:456-470,650-704` 与本轮全量 Vitest（722 passed）、`test:types`、`build` 均通过。

coverage = 3 / 3

verdict: PASS

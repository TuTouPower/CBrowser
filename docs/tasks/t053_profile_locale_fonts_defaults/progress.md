---
tid: "t053"
slug: "profile_locale_fonts_defaults"
title: "Profile 配置：默认值、时区语言联动、按语言分流中文字体与字体集链路收口"
status: "done"
branch: "t053_profile_locale_fonts_defaults"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "1e11e0fda2d2fda130e24e6bdef904c5b96c3516"
depends_on: ""
conflicts_with: "t051"
note: "来源 p067、p069；用户 2026-11-10 确认英文 Profile 裁剪中文字体; ；扩充 review_20261110_200842 A16 A18 A19 A20 A30"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 引用逐项核对（2026-11-11，t028 教训，本 task 第一步）

- task.md 上下文引用核对：`types.ts` 的 `humanize`/`portable_cookies` 默认 `false`（第 41/51 行）✓；`domain/models.py` 的默认值位置行号已漂移（内容在 194/209、412/427、526/541 行，引用行号 157/172/375/390/489/504 过期）——内容属实，行号作废；ORM `models.py` 同样行号漂移（`humanize` 在 135 行、`portable_cookies` 在 165 行，引用 98/128 过期）——内容属实；`ProfileForm.tsx` 时区/语言裸输入在 430-445 行 ✓；`fontconfig.py` 的 `profile_font_dirs` 只按目录白名单、未绑定回退 `/opt/cbrowser-base-fonts` ✓；`docs/reviews/review_20261110_200842/adoption_decision.md` 的 A16（153 行）、A18（169 行）、A19（177 行）、A20（185 行）、A30（265 行）均存在 ✓；基线提交 `1e11e0f`（t052）✓。
- 命名锁死核对：`com.cbrowser.instance-id` 为唯一规定键，`resource_prefix` 默认 `"cbrowser-t005"`；`com.cbrowser.deployment-id` 在 `src/` 中零命中；本次改动不碰这两处。
- fontconfig 语言排除机制实测（UNVERIFIED-SPIKE #2 预验证，2026-11-11）：本机 fontconfig 2.15.0 + 真实字体（NotoSansCJK-Regular.ttc、DejaVuSans.ttf）实测，`<selectfont><rejectfont>` 按 `lang`（zh-cn 等）排除对 `.ttc` 集合生效——英文配置下 CJK 字体全部不可见、DejaVu 保留；中文配置下全部可见。Browser 镜像内 fontconfig 版本仍须用户机实测（见「环境跳过」）。
- 其余新文件/函数引用（`domain/profile_locale.py`、`CHINESE_REGION_TIMEZONES`、`locale_for_timezone`、迁移 0007、前端 `TimezoneCombobox`/`profile_locale.ts`、`FontSetListResponse`、A18 的 `FontConfigUnavailableError`）为本 task 新建，见各 Area 小节。

### Area 1 实施中（2026-11-11）：默认值、时区/语言域规则、ORM 与迁移

- 新模块 `src/backend/cbrowser/domain/profile_locale.py`：`SUPPORTED_LOCALES=("zh-CN","en-US")`、`DEFAULT_LOCALE="en-US"`、中文地区时区集合（7 个）、`locale_for_timezone`、`is_valid_timezone`（ZoneInfo）、`validate_timezone`/`validate_locale`。
- `domain/models.py`：`ProfileConfig`/`ProfileCreateRequest`/`ProfileResponse` 的 `humanize`、`portable_cookies` 默认改为 `True`；`ProfileCreateRequest.locale` 默认 `"en-US"`；三处 DTO 均加时区/语言校验（非法值进 422 字段级错误）。其余高级选项默认值不变（测试固定）。`ProfileConfig.locale` 仍允许 `None`（存量行原样加载，AC-002）。
- ORM `adapters/database/models.py`：`humanize`/`portable_cookies` 的 Python 默认与 `server_default` 均改为 `True`/`"1"`；`profiles.locale` 加 CHECK 约束 `ck_profiles_locale_enum`。
- 迁移 `0007_profile_locale_enum_defaults.py`（revision `1a8db6b91744`，down `c8d3e7a1f904`）：batch 重建表改 server_default + 加 CHECK；downgrade 回退。存量非枚举 locale 会阻塞升级（无真实用户，须先清掉；迁移 docstring 已写明）。
- 旧测试语义变更（t052 前例，注明理由）：`tests/integration/test_api_subprocess.py` 的创建 payload `locale` 由 `en-GB` 改为 `en-US`（语言已收敛为两值，非法值现被拒绝；拒绝路径由新集成测试覆盖）。
- 测试：`tests/unit/test_t053_profile_locale.py`（28 tests，Round 1 修复后；实施中曾为 17，后增至 26，Round 1 再 +2）+ 迁移 autogenerate 测试通过。

### Area 2 完成（2026-11-11）：fontconfig 按语言分流与 A18 封闭

- `runtime_agent/fontconfig.py`：新增 `CHINESE_LANG_TAGS`（zh/zh-cn/zh-tw/zh-hk/zh-mo/zh-sg）、`FONT_SET_UNAVAILABLE`、`FontConfigUnavailableError`；`build_fontconfig_xml`/`prepare_profile_fontconfig` 增加 `locale` 参数（`en-US` 时每标签一条 `<selectfont><rejectfont>`，`zh-CN`/`None` 时无拒绝）与 `cache_dir` 参数（测试隔离用）；未绑定回退目录同样走该规则。
- 机制实测：本机 fontconfig 2.15.0 + 真实字体夹具（NotoSansCJK-Regular.ttc / DejaVuSans.ttf），`fc-list` 在英文配置下看不到 CJK 字体、中文配置下全部可见；已写成单测 `test_fc_list_hides_cjk_fonts_for_en_us`（fc-list 或夹具缺失时 skip）。
- `runtime_agent/runner.py`：`start()` 传 `locale=cfg.locale`；绑定集且生成失败时写终端 error 状态（`exit_reason=font_set_unavailable`）后抛 `FontConfigUnavailableError`，浏览器不启动；`__main__` 增加对应 except 分支记稳定原因。未绑定时维持既有回退。
- `supervisor/core.py`：观测路径 `is_error_exit_health` 分支中 `exit_reason == font_set_unavailable` 时原因透传为 `font_set_unavailable`（不再统一记 `agent_exit`）。
- 测试：`tests/unit/test_t053_fontconfig_locale.py`（16 tests，Round 1 修复后；实施中曾为 10，review 时为 9，Round 1 再 +7，含真实 fc-list/fc-match）+ 既有 `test_fontconfig.py` 全过。

### Area 3 完成（2026-11-11）：字体集链路 A16/A19/A20 与 API 形态

- `font_sets/manifest.py`：`import_font_set` 在目标已存在且完整性不通过时以新内容原子替换（staging + rename 换位，失败恢复旧目录；`created=True`）；`list_font_sets` 校验 manifest 平台与目录一致，不一致标完整性失败；新增 `pick_default_font_set(items, platform)`（唯一默认规则：完整性通过、按 `created_at` 取最新），`default_font_set` 改为复用它。
- `adapters/database/repository.py`：`font_set_usage_counts` 改为按 `(fingerprint_platform, font_set_id)` 分组；`services/profile_service.py` 同步签名。
- `services/profile_service.py::create_profile`：新增 `font_set_id_supplied` 参数，仅当调用方未提供 `font_set_id` 时才套用后端默认；显式 null 保持为 null。`api/v1/router.py` 以 `payload.model_fields_set` 传入。
- `api/v1/font_sets_router.py`：响应改为 `FontSetListResponse{items, default_font_set_id}`（每平台一个默认集或 null），`used_by_count` 按 `(platform, set_id)` 取数。
- 旧测试语义变更：`tests/unit/test_font_sets_api.py` 的计数断言改为 keyed 形式；`tests/unit/test_a5_font_scan_offload.py` 的 tamper 测试改为 `.items` 访问；`tests/integration/test_font_sets_api.py` 跟随新响应形态并新增 A16 集成用例（显式 null 保持、篡改后默认集消失）。
- 测试：`tests/unit/test_t053_font_sets_chain.py`（8 tests）+ `tests/integration/test_t053_profile_locale_api.py`（AC-001/AC-005/AC-008，5 tests）全过。
- 回归修复（全量首轮后，2026-11-11）：首轮 30 failed 中 3 个为本 task 新增——`test_t027_release_controller.py::test_fonts_preflight_ok_with_valid_set`、`test_t051_deploy_scripts.py::test_check_font_sets_valid_set_reports_ok`、`tests/integration/test_api_subprocess.py::test_ac001_and_ac005_crud_restart_and_empty_dir_init_with_refs`；其余 27 个与 t052 基线按名一致。根因前两项：A20 校验把 manifest 缺 `platform` 字段也判为不一致（`None != "windows"`），而 t027/t051 的夹具按旧契约建集、不写该字段。修复：`manifest.py` 的 `list_font_sets` 只在 manifest 明确写了不同平台时判不一致，缺字段不算不一致（无平台声明 ≠ 平台不一致）；`test_t053_font_sets_chain.py` 补第 9 个测试固定该语义。第三项：`test_api_subprocess.py` 创建 payload 已改 `en-US`，第 317 行重载断言漏改仍为 `en-GB`，补改（同一语义变更的两处，测试意图为 locale 值往返不变）。三项复测全过。

### Area 4 完成（2026-11-11）：Coordinator 字体运行时缓存删除（A19）

- `api/runtime_coordinator.py`：删除 `_font_runtime_cache` 属性与全部读写；`get_font_runtime` 每次按 Supervisor 同一校验函数（`get_font_set` + `check_font_set`）实时读取。集缺失时返回该平台全部探测字体为未覆盖（原缓存把「集不存在」记为无缺失）；篡改文件不进入 `missing_fonts`（完整性轴，A30 区分）。
- 测试：`tests/unit/test_t053_coordinator_font_runtime.py`（3 tests：删除后立即报告缺失、篡改不进探测缺失但删除文件进、无缓存属性）+ 既有 `test_t041_font_runtime.py` 全过。

### Area 5 完成（2026-11-11）：前端——时区组合框、语言联动、默认集预选、A30 文案

- 新模块 `src/frontend/src/features/profiles/profile_locale.ts`：`SUPPORTED_LOCALES` / `DEFAULT_LOCALE="en-US"` / 中文地区时区集合（与后端同一 7 个）/ `localeForTimezone` / `COMMON_TIMEZONES`（15 个置顶）/ `getTimezones`（`Intl.supportedValuesOf("timeZone")`，置顶列表恒可提供——Node 26 的 ICU 列表不含 `UTC`，实现把置顶项并入全集）/ `filterTimezones`（大小写不敏感子串，常用优先）。
- 新组件 `TimezoneCombobox.tsx`：键入过滤、未键入展开可滚动浏览全部 IANA 时区（`max-h-64 overflow-y-auto`）、键盘 ArrowUp/Down/Home/End/Enter/Escape、aria combobox/listbox/option + `aria-activedescendant`、首选项「自动（随出口 IP）」对应 null；选项以 mousedown 提交（先于 blur）。
- `ProfileForm.tsx`：时区行改为 `TimezoneCombobox`（选时区自动联动语言，时区为空时语言保持当前值）；语言行改为中/英二选一 Select（可手动覆盖）；字体集默认预选改为后端 `default_font_set_id[platform]`（创建态、每平台一次，`fontSetUserChosenRef` 守护，选「无」后不再重套；切换平台时套用新平台默认集）；删除旧的“最新集”推导 effect。`SessionDetailsPanel.tsx`：缺失字体横幅改用 `fontSetDetectionMissing`（「探测字体未覆盖」）文案（A30）。
- `types.ts`：`DEFAULT_PROFILE_CREATE_VALUES` 的 `humanize`/`portable_cookies` 改为 `true`，`locale: "en-US"`；`client.ts` 的 `fontSets.list()` 返回 `FontSetListResponse`；`useProfilesQuery.ts` 的 `useFontSetsQuery` 同步；`SettingsPage.tsx` 取 `.items`；`SessionPage.tsx` 向详情面板传 `.items`。
- i18n：en/zh 同步补 `formTimezoneAuto` / `formTimezoneNoMatch` / `formLocaleChinese` / `formLocaleEnglish` / `fontSetDetectionMissing`（键集相等测试守护）。
- 测试：新 `profile_locale.test.ts`（6 tests：规则矩阵、IANA 全集 + 置顶、过滤）、新 `TimezoneCombobox.test.tsx`（6 tests：过滤选中、展开全量可滚动、置顶、键盘、自动选项、无匹配）、`ProfileForm.test.tsx` 扩展为 11 tests（后端默认集胜过最新集、「无」保持、创建提交默认值、时区→语言联动 + 手动覆盖、清空时区语言保持、原有 6 tests 通过）、`SessionDetailsPanel.test.tsx` 补 A30 文案 test（11 tests）。其余 12 个文件的 `fontSets.list` mock 一律改为 `{items, default_font_set_id}` 新形态（`router.test.tsx`、`SessionPage.test.tsx`、`ConfigTab.test.tsx`、`EnvironmentListPage.test.tsx`、`ProfileCreateDialog.test.tsx`、`ProfileDetailPage.test.tsx`、`ProfileIsolation.test.tsx`、`ProxyListPage.test.tsx`、`SettingsPage.test.tsx`、`SettingsPage.network.test.tsx`、`a19_settings_polling.test.tsx`、`a21_settings_contract.test.tsx`）。
- 前端全量：`npm test`（含 `test:types`）76 files / 550 tests 全过（基线 533 + 新增 17）；`npm run check:api` 通过；`npm run build` 通过。

### Area 6 完成（2026-11-11）：语言枚举进 OpenAPI（Literal）与契约重生成

- `domain/models.py`：新增 `ProfileLocale = Literal["zh-CN", "en-US"]`，`ProfileConfig` / `ProfileCreateRequest` / `ProfileUpdateRequest` / `ProfileResponse` 的 `locale` 由 `str | None` 改为 `ProfileLocale | None`（字段级校验器保留）。原因：只用校验器时 OpenAPI 不出枚举，前端生成类型仍是自由字符串；改为 Literal 后 schema 与生成类型均为封闭枚举。
- `scripts/export_openapi.py` 重跑：`schemas/openapi/cbrowser_v1.json` 与 `cbrowser_internal.json` 的 diff 只含 t053 表面——`FontSetListResponse` 新增、两处 `humanize`/`portable_cookies` 默认 `false`→`true`、`locale` 默认 `en-US` 与枚举、`GET /api/v1/font-sets` 响应改为 `FontSetListResponse`。`npm run generate:api` 重生成 `cbrowser_v1.d.ts`：`locale: ("zh-CN" | "en-US") | null`、`FontSetListResponse` 已入生成类型。

### Area 7 完成（2026-11-11）：文档收尾

- `docs/blueprint/domain.md`：实体表补语言/时区行，新增「语言、时区与高级选项默认值（t053）」节（枚举、时区校验、时区→语言规则、新建默认值三端一致、语言属运行配置）。
- `docs/blueprint/browser_runtime.md`：新增「语言分流与字体集链路收紧（t053）」节（按语言生成 fontconfig、A16/A18/A19/A20/A30）。
- `docs/blueprint/frontend.md`：第 7 节补时区组合框与语言联动段。
- `docs/blueprint/decisions.md`：新增 ADR 030「英文 Profile 裁剪中文字体」，标注部分替代 ADR 024（仅「字体集整体可见」部分；ADR 024 其余结论保留）。
- `docs/specs/profile_management.md`：新增 t053 节；修正 t041 节与 t037 节的默认集表述（最新集 → 后端按完整性规则给出的默认集）。
- `docs/specs/fingerprint_platform.md`：引言与 2.1 默认集表述修正，新增 2.7 节，第 3 节补 t053 AC 摘要。
- `docs/specs_index.md`：`profile_management` 行加 t053、日期改 2026-11-11；`fingerprint_platform` 行加 t053。
- `task.md` 未知契约清单：UNVERIFIED-SPIKE #2 改写为结论——宿主 fontconfig 2.15.0 上机制已验证（`.ttc` 集合生效），剩余 Browser 镜像内版本待用户机实测；#1 仍未验证（真实引擎 `navigator.language`）。
- AC 打勾：15 条全部打勾（AC-001~AC-015；AC-006/AC-007/AC-008/AC-009 的真实引擎部分与 AC-010 按链口径跳过计 pass，见「环境跳过」）。

### Review 修复（Round 1，2026-11-11）

- 按规则先撤回 task.md 15 条 AC 打勾，修复并重验后再重新打勾。
- code f001 + test f001（important）：(a) 新增 Runner 链路测试 `test_explicit_locale_reaches_engine_launch_alongside_geoip`（zh-CN/en-US 双值：显式 locale 与 `geoip=True` 一并到达 `launch_persistent_context_async`，同一 locale 驱动 fontconfig）；(b) task.md 未知契约清单 #1 改写为结论（本机已验链路、引擎内裁决待用户机补验、补验方法与 AC-009/AC-010 对应关系），不再留 `UNVERIFIED-SPIKE` 状态。
- code f002：`validate_timezone("")` 归一化为 `None`（与 `locale_for_timezone("")` 一致），`ProfileConfig`/`ProfileCreateRequest`/`ProfileUpdateRequest` 经校验器自动归一化，存量 `""` 行可读（测试以 `ProfileModel` 直写 `""` 后重载验证）；`is_valid_timezone("")` 仍为 `False`（只答“是不是 IANA 名”，`""` 不是名），分工见 `profile_locale.py` docstring。
- code f003：`TimezoneCombobox` 高亮复位依赖由 `options.length` 改为 `options` 本身，候选内容变化即回首选；键盘测试以 `new`/`par` 两组同为 2 个候选、内容不同的查询复现原问题（红）后修复（绿）。
- test f002：新增 `test_zh_cn_fc_match_resolves_to_platform_set_chinese_font`（windows/macos 双集）：zh-CN 配置下 `fc-match :lang=zh-cn` 解析到集内中文字体文件，en-US 下解析到拉丁字体；本机无微软雅黑/宋体/苹方/冬青黑体文件，以宿主真实中文字体 NotoSansCJK-Regular.ttc 代行平台集的中文字体，不编造字体名，确切平台字体名待用户机以真实字体集复核（见「环境跳过」AC-007）。
- test f003：新增 macos 集真实 `fc-list` 测试与未绑定回退真实 `fc-list` 测试（`BASE_FONTS_DIR` monkeypatch 为宿主真实字体目录，`profile_font_dirs` → 生成 → fc-list 全链路实测）；真实基础字体目录（`/opt/cbrowser-base-fonts`，文泉驿）只存在于 Browser 镜像，本机以宿主字体代行。
- test f004：新增 `test_restart_after_locale_change_regenerates_fontconfig`（fake 启动层：en-US 启动 → 改语言 → 新快照版本 + 新运行时实例重启 → zh-CN fontconfig 无拒绝规则，两次启动的 locale 均有记录）；真实引擎内 `navigator.language` 仍属环境跳过。
- test f005：`ProfileForm`「保持显式无字体集」测试改写为确定性断言——字体集查询以 deferred promise 挂起，用户在默认到达前选「无」，再释放查询并以 `act` 刷掉状态更新与 effect，断言仍为「无」且默认集已可提供。改写中暴露生产缺陷：Radix 仅在值变化时调 `onValueChange`，已显示为「无」时再点「无」不触发守卫，默认仍会被重套；修复为共享 `Select` 新增可选 `onOptionSelect`（每次提交选项都触发，含同值重选），`ProfileForm` 字体集 Select 以此记录显式选择。旧 200ms 固定等待已删除。
- 计数订正：`tests/unit/test_t053_profile_locale.py` 为 28 tests（Area 1 原写 17 为实施中旧数，review_test.md 已指正为 26，Round 1 修复 +2）；`tests/unit/test_t053_fontconfig_locale.py` 为 16 tests（Area 2 原写 10，review_test.md 指正为 9，Round 1 修复 +7）。t053 后端新增合计 61 tests。

### Review 修复（Round 2，2026-11-11）

- 按规则先撤回 task.md 15 条 AC 打勾，修复并重验后再重新打勾。
- code f004（important，键盘同值重选「无」不触发守卫）：先红后绿。新增键盘复现测试 `keeps an explicit none font set when picked by keyboard instead of re-applying the default`（`ProfileForm.test.tsx:343`，deferred 查询 + ArrowDown 打开下拉 + 回车选「无」+ 释放查询断言仍为「无」）：修复前红——断言处选值已被延迟到达的默认改写为 `win-1`，与审阅描述一致。修复：共享 `Select` 的 `SelectPrimitive.Item` 补 `onKeyDown`（Enter/空格，`event.target` 须为 item 本身），与既有 `onClick` 并行覆盖鼠标与键盘两路提交；`onOptionSelect` docstring 修正为双路径说明。偏差说明：审阅建议的 `onSelect` 在已装 Radix 2.4.1 上不存在（`SelectItemProps` 仅 `value/disabled/textValue`，dist 与 d.ts 均零命中 `onSelect`），按审阅字面改会静默失效，故改用 Radix 实际提交漏斗的等价挂法；Space 在 typeahead 搜索进行时仍计一次选择（Radix 会当作搜索延续），仅把当前显示值记为显式选择，属守卫的安全方向，已写进 docstring。
- 重验：受影响前端测试 `ProfileForm.test.tsx`（12 tests，含新增键盘测试）+ `TimezoneCombobox.test.tsx`（7 tests）19 passed；前端全量 `npm test`（Node 26.13.0，含 `test:types`）76 files / 552 passed / 0 failed（基线 551 + 新增 1）。后端：本次只改前端（`Select.tsx` + 测试），无任何后端改动；`ProfileForm` 的守卫逻辑只在前端生效，后端 `font_set_id` 显式 null 保存路径未动，无交叉影响，故后端无需重跑（Round 1 后端全量 2089 passed / 27 failed 基线一致仍有效）。
- 命名锁死复核：`src/`、`scripts/`、`compose.yaml` 中 `com.cbrowser.deployment-id` 仍零命中；默认部署前缀仍为 `cbrowser-t005`（`docker_adapter.py:234`），未改动。

### Review 修复（Round 3，2026-11-11）

- 按规则先撤回 task.md 15 条 AC 打勾，修复并重验后再重新打勾。
- code f005（important，鼠标同值重选「无」在真实浏览器里到不了 onOptionSelect）：先红后绿。鼠标测试改写为忠实序列（trigger pointerdown/up → option pointerdown/up → 对已卸载 option 派 click；jsdom 无 `hasPointerCapture`，测试内补桩；断言 `option.isConnected === false` 固定“菜单已卸载”这一真实浏览器条件）：修复前红——延迟到达的默认把选值由「无」改写为 `win-1`（期望 `Not configured`，实得 `win-1`），与审阅实证一致；其余 11 项通过。修复：共享 `Select` 的 `SelectPrimitive.Item` 补 `onPointerUp`，仅 `pointerType === "mouse"` 时触发 `onOptionSelect`（与 Radix 2.4.1 dist :979-985 的鼠标分支一致；`composeEventHandlers` 使用者处理器先跑、Radix 关闭在后，item 仍在挂载态）；`onClick` 留给 touch/pen（dist :973-977 非鼠标分支），`onKeyDown` 留给键盘；三路互不重复触发（鼠标 pointerup 后 click 派给已卸载 item 不再触发；触屏/笔 pointerup 不触发、click 只跑一次；键盘无指针事件）。docstring 修正为三路说明，并写明 `onClick` 不能覆盖鼠标路径的原因（pointerup 提交即同步关闭菜单，随后 click 派给已卸载 item）；逐项核对 docstring 所述与 Radix dist 实际行为一致（onClick 非鼠标分支 :975-977、onPointerUp 鼠标分支 :983-985、`composeEventHandlers` 使用者先跑）。
- 重验：受影响前端测试 `ProfileForm.test.tsx`（12 tests，含改写后的忠实序列鼠标测试）+ `TimezoneCombobox.test.tsx`（7 tests）19 passed；前端全量 `npm test`（Node 26.13.0，含 `test:types`）76 files / 552 passed / 0 failed（与 Round 2 基线一致，无新增测试——鼠标测试为改写非新增）。后端：本次只改前端（`Select.tsx` + 测试），无任何后端改动；`ProfileForm` 的守卫逻辑只在前端生效，后端 `font_set_id` 显式 null 保存路径未动，无交叉影响，故后端无需重跑（Round 1 后端全量 2089 passed / 27 failed 基线一致仍有效）。
- 命名锁死复核：`src/`、`scripts/`、`compose.yaml` 中 `com.cbrowser.deployment-id` 仍零命中；默认部署前缀仍为 `cbrowser-t005`（`docker_adapter.py:234`），未改动。

### Review 修复（Round 4，2026-11-11）

- 按规则先撤回 task.md 15 条 AC 打勾，修复并重验后再重新打勾。
- code f006 + test f006（同根，minor，拖过释放误记显式选择）：先红后绿。新增 `Select.test.tsx` 拖过测试先复现（pointerdown 落 "none"、pointerup 落 "win-1" 时 onOptionSelect 得 `[["win-1"]]`，与审阅实证一致；同项按下抬起与 touch 测试同期已绿），再修复。共享 `Select` 的 Item 抽为独立组件持 per-item `pressedRef`：`onPointerDown`（mouse）置位，`onPointerUp` 仅 mouse 且本次按下曾落在本项时触发 `onOptionSelect`、随后清零，`onPointerLeave` 清零；`onClick`（touch/pen）与 `onKeyDown`（键盘）不动；docstring 补 pointerdown 落点守卫说明。表单级拖过测试曾尝试以 deferred 查询复现“拖过后默认仍套用”，核实不可达后删除——查询挂起时字体集菜单只有「无」一个选项（`fontSetOptions` = `__none__` + 已返回的集），无第二项可拖；且切平台路径会自行把 `fontSetUserChosenRef` 复位，不经守卫。
- test f007（minor，touch 路无交付测试）：补 Select 级 touch 测试（pointerup 空操作、随后 click 恰触发 1 次，修复前已绿，属覆盖补齐，不改生产逻辑）与 ProfileForm 级 touch 测试（deferred 查询竞态：touch 选「无」后释放查询仍为「无」）。核实：Radix trigger 仅 mouse pointerdown 开菜单，touch 靠随后 click 开（dist :293-296 vs :303-305），测试序列按此写。
- 重验：受影响前端测试 `Select.test.tsx`（3 tests，新增）+ `ProfileForm.test.tsx`（13 tests，含新增 touch 测试）+ `TimezoneCombobox.test.tsx`（7 tests）23 passed；前端全量 `npm test`（Node 26.13.0，含 `test:types`）77 files / 556 passed / 0 failed（基线 552 + 新增 4）。后端：本次只改前端（`Select.tsx` + 测试），无任何后端改动；`ProfileForm` 的守卫逻辑只在前端生效，后端 `font_set_id` 显式 null 保存路径未动，无交叉影响，故后端无需重跑（Round 1 后端全量 2089 passed / 27 failed 基线一致仍有效）。
- 命名锁死复核：`src/`、`scripts/`、`compose.yaml` 中 `com.cbrowser.deployment-id` 仍零命中；默认部署前缀仍为 `cbrowser-t005`（`docker_adapter.py:234`），未改动。

以下事项本机无法验证，**不得记为已验**，须在用户机补验；不包装成选项或「待裁定」：

- AC-010（[deploy]）：真实部署后分别新建英文与中文 Profile 启动，页面内字体探测结果符合 AC-006 / AC-007。补验环境：用户机真实部署。
- AC-006 真实引擎部分：英文 Profile 在真实 Browser 内 `fc-list` 与页面字体探测均不含覆盖中文的字体（绑定 windows / macos / 未绑定三种情况）。云端已覆盖：`build_fontconfig_xml` 按语言生成单测 + 宿主 fontconfig 2.15.0 真实字体 `fc-list` 实测（合成单目录、macos 集目录、未绑定回退目录三种情况，`test_fc_list_hides_cjk_fonts_for_en_us` / `test_fc_list_hides_cjk_fonts_for_macos_set` / `test_unbound_fallback_follows_locale_in_real_fc_list`）。补验环境：用户机真实引擎 E2E（参照 `tests/e2e/test_fingerprint_platform_e2e.py` 的 `fc-list` + `document.fonts.check` / measureText 模式）。
- AC-007 真实引擎部分：中文 Profile 下中文文本解析到微软雅黑/宋体（windows）或苹方/冬青黑体（macos）。云端已覆盖：zh-CN 配置不追加拒绝规则、全部白名单字体可见（同上 fc-list 实测）+ `fc-match :lang=zh-cn` 在 zh-CN 配置下解析到平台集目录内的中文字体文件、在 en-US 配置下解析到拉丁字体（`test_zh_cn_fc_match_resolves_to_platform_set_chinese_font`，windows/macos 双集）；本机无微软雅黑/宋体/苹方/冬青黑体文件，以宿主真实中文字体（NotoSansCJK-Regular.ttc）代行平台集的中文字体，确切平台字体名须用户机以真实字体集复核。补验环境：用户机真实引擎 E2E。
- AC-008 真实引擎部分：语言修改并重启后，字体可见性与 `navigator.language` 按新语言生效。云端已覆盖：语言修改生成新配置版本（集成测试 `/versions` 为 [1, 2]）+ 重启后 Runner 按新语言重新生成 fontconfig（`test_restart_after_locale_change_regenerates_fontconfig`，fake 启动层双 Runner 实测）；真实引擎内 `navigator.language` 仍须用户机补验。补验环境：用户机真实引擎 E2E。
- AC-009：运行时 `navigator.language` 等于 Profile 配置的语言，不被出口 IP 自动推断覆盖。云端已覆盖链路一半：显式 locale 原样传到引擎启动调用（`test_explicit_locale_reaches_engine_launch_alongside_geoip`）与同一 locale 驱动 fontconfig；引擎内部是否让显式 `locale` 优先于出口 IP 推断，本机无真实引擎、无法核实，task.md 未知契约清单 #1 已改写为结论（写明补验方法与 AC-009/AC-010 对应关系）。补验环境：用户机真实引擎 E2E（分别新建 zh-CN 与 en-US Profile，geoip 开启、时区留空，启动后读 `navigator.language`）。
- UNVERIFIED-SPIKE #2 剩余部分：Browser 镜像内 fontconfig 版本对 `.ttc` 集合的 `lang` 排除是否生效。云端已验证宿主 fontconfig 2.15.0 机制成立；补验环境：用户机 Browser 镜像内 `fc-list` 实测。

## 回归实数（2026-11-11）

- 后端全量（`tests/unit + tests/integration`，验证 venv，`PYTHONPATH=src/backend`）：**2089 passed / 27 failed / 8 skipped / 2 errors**。基线（t052）：2026 passed / 27 failed / 8 skipped / 2 errors。失败按名与基线 27 个完全一致（a24 2、automation_cdp 1、repo_hygiene 1、t028 4、t034 2、agent_executor_chain 7、automation_cdp_flow 2、automation_probe_chain 3、control_attendant_chain 1、normal_exit_replay 4），无新增失败；其中 `test_normal_exit_replay.py::test_normal_exit_converges_to_desired_stopped_while_container_running` 为顺序依赖型 flaky（全量与单文件跑失败、13 文件子集跑通过），属基线既有。passed +63（新增 t053 测试 61 个 + 集成 font-sets A16 用例 2 个）。首轮曾出现 3 个新增失败（t027/t051/aPI subprocess），根因与修复见 Area 3 末尾；修复后重跑全量确认归零。2 errors 为基线既有 flaky teardown 错误（`tests/integration/test_a35_recovery.py::test_concurrent_apply_is_rejected_by_exclusive_db_registration`、`tests/integration/test_network_apply_operations.py::test_restore_not_found_is_explicit_terminal`，两测试本身通过，单独复跑复现同样 2 errors，t052 已记录）。Round 1 修复后重跑全量：同样 2089 passed / 27 failed / 8 skipped / 2 errors，失败按名与基线一致，无新增失败。
- 前端全量（`npm test`，Node 26.13.0，含 `test:types`）：**77 files / 556 passed / 0 failed**。基线 533 passed / 0 failed；+23 为本 task 新增（`profile_locale.test.ts` 6、`TimezoneCombobox.test.tsx` 7、`ProfileForm.test.tsx` +6、`SessionDetailsPanel.test.tsx` +1、`Select.test.tsx` 3）。Round 2 修复新增 1 个键盘测试（`ProfileForm.test.tsx` 12 tests），由 551 增至 552。Round 3 修复改写鼠标测试为忠实序列（无新增测试），前端全量仍为 552 passed / 0 failed。Round 4 修复新增 4 个测试（`Select.test.tsx` 3 个：拖过释放、同项按下抬起、touch；`ProfileForm.test.tsx` +1 个 touch 测试，13 tests），前端全量 77 files / 556 passed / 0 failed；后端零改动未重跑。`npm run check:api` 通过；`npm run build` 通过。
- 新增测试合计：后端 61（`test_t053_profile_locale.py` 28、`test_t053_fontconfig_locale.py` 16、`test_t053_font_sets_chain.py` 9、`test_t053_coordinator_font_runtime.py` 3、`test_t053_profile_locale_api.py` 5）+ 集成 font-sets A16 用例 2 个；前端 23 个（Round 2 键盘测试 +1、Round 4 拖过/同项/touch 测试 +4）。相关既有文件复跑：`test_font_sets.py` / `test_font_sets_api.py` / `test_a5_font_scan_offload.py` / `test_t041_font_runtime.py` / `test_api_subprocess.py` 等 10 个文件 94 passed。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-11T16:37:54+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t053_code_f001|important|已修|AC-009 链路补测试固定（显式 locale 与 geoip=True 一并到达引擎启动调用），未知契约 #1 改写为结论，不再留 UNVERIFIED-SPIKE；引擎内是否优先仍须用户机补验，已写明方法|tests/unit/test_t053_fontconfig_locale.py:427；task.md:102|
|t053_code_f002|minor|已修|"" 统一为未设置：校验归一化为 None，存量 "" 行可读，新建 "" 可保存|src/backend/cbrowser/domain/profile_locale.py:71；tests/unit/test_t053_profile_locale.py:203；tests/unit/test_t053_profile_locale.py:222|
|t053_code_f003|minor|已修|候选列表变化即复位高亮到首选，不再只看数量；同尺寸不同内容的键盘测试复现并固定|src/frontend/src/features/profiles/TimezoneCombobox.tsx:74；src/frontend/src/features/profiles/TimezoneCombobox.test.tsx:70|
|t053_test_f001|important|已修|与 code f001 同根：AC-009 补 Runner 链路测试，未知契约 #1 改写为结论|tests/unit/test_t053_fontconfig_locale.py:427；task.md:102|
|t053_test_f002|minor|已修|fc-match 实测：zh-CN 配置下中文解析到平台集内中文字体文件，en-US 下解析到拉丁字体；以宿主真实中文字体代行，确切平台字体名待用户机复核|tests/unit/test_t053_fontconfig_locale.py:328|
|t053_test_f003|minor|已修|macos 集与未绑定回退补真实 fc-list 实测；真实基础字体目录只存在于 Browser 镜像，本机以宿主字体代行|tests/unit/test_t053_fontconfig_locale.py:365；tests/unit/test_t053_fontconfig_locale.py:382|
|t053_test_f004|minor|已修|补重启后运行时一半：改语言后重启，Runner 按新语言重新生成 fontconfig 且新 locale 到达引擎调用；真实引擎内 navigator.language 仍属环境跳过|tests/unit/test_t053_fontconfig_locale.py:470|
|t053_test_f005|minor|已修|200ms 固定等待改为确定性断言（deferred 查询 + act 刷状态）；改写中暴露同值重选不触发守卫的生产缺陷，共享 Select 补 onOptionSelect 一并修复|src/frontend/src/features/profiles/ProfileForm.test.tsx:288；src/frontend/src/shared/ui/Select.tsx:70；src/frontend/src/features/profiles/ProfileForm.tsx:518|

### Round 2 (2026-11-11T17:00:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t053_code_f004|important|已修|键盘提交路径补齐：先红后绿——键盘测试先复现（回车选「无」后延迟到达的默认仍改写为 win-1），再修复。实现与审阅建议有一处偏差并已核实：已装 Radix 2.4.1 的 SelectItemProps 只含 value/disabled/textValue，无 onSelect prop（dist/index.js 与 index.d.ts 均零命中），传 onSelect 只会落到 div 的 DOM select 事件上、永不触发；故按 Radix 实际提交漏斗（handleSelect 由 onClick/onPointerUp/onKeyDown 三路调用）补 onKeyDown（Enter/空格，与 Radix SELECTION_KEYS 一致），与既有 onClick 并行；docstring 修正为双路径说明并写明 Space 在 typeahead 搜索进行时仍计一次选择的边界（仅把当前显示值记为显式选择，属守卫的安全方向）|src/frontend/src/shared/ui/Select.tsx:83；src/frontend/src/shared/ui/Select.tsx:14；src/frontend/src/features/profiles/ProfileForm.test.tsx:343|

### Round 3 (2026-11-11T17:19:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t053_code_f005|important|已修|鼠标提交路径补齐：先红后绿——忠实序列鼠标测试先复现（pointerup 提交即关闭菜单，随后 click 派给已卸载 item，延迟到达的默认把「无」改写为 win-1），再修复。共享 Select 的 Item 补 onPointerUp，仅 pointerType === "mouse" 时触发（与 Radix 2.4.1 pointerup 鼠标分支一致，使用者处理器先于 Radix 关闭跑）；onClick 留给 touch/pen，onKeyDown 留给键盘，三路无重复触发；docstring 修正为三路说明并逐项核对与 Radix dist 实际行为一致|src/frontend/src/shared/ui/Select.tsx:22；src/frontend/src/shared/ui/Select.tsx:93；src/frontend/src/features/profiles/ProfileForm.test.tsx:294|

### Round 4 (2026-11-11T09:39:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t053_code_f006|minor|已修|拖过释放不再误记显式选择：先红后绿——Select 级拖过测试先复现（pointerdown 落 "none"、pointerup 落 "win-1" 时 onOptionSelect 得 [["win-1"]]），再修复。共享 Select 的 Item 抽为独立组件持 per-item pressedRef：onPointerDown（mouse）置位，onPointerUp 仅 mouse 且本次按下曾落在本项时触发 onOptionSelect，随后清零；onPointerLeave 清零；onClick（touch/pen）与 onKeyDown（键盘）不动。边界说明：表单级拖过测试曾尝试以 deferred 查询复现“拖过后默认仍套用”，核实不可达后删除——查询挂起时字体集菜单只有「无」一个选项（fontSetOptions = __none__ + 已返回的集），无第二项可拖；且切平台路径会自行把 fontSetUserChosenRef 复位，不经守卫。Select 级测试已按审阅探针序列固定该边界|src/frontend/src/shared/ui/Select.tsx:106；src/frontend/src/shared/ui/Select.tsx:121；src/frontend/src/shared/ui/Select.tsx:126；src/frontend/src/shared/ui/Select.test.tsx:39；src/frontend/src/shared/ui/Select.test.tsx:77|
|t053_test_f006|minor|已修|与 code f006 同根：新文件 Select.test.tsx 固定提交边界——拖过释放不触发 onOptionSelect 且菜单未关（修复前红，spy 得 [["win-1"]]）、同项按下抬起恰触发 1 次；另注：pointermove 也会置 Radix 自身的 pointerTypeRef（dist :994-995），真实浏览器中带移动的拖拽会由 Radix 提交，本修复只按审阅建议与任务要求以 pointerdown 落点为准，pointermove 情形不在本次约定内|src/frontend/src/shared/ui/Select.test.tsx:39；src/frontend/src/shared/ui/Select.test.tsx:77|
|t053_test_f007|minor|已修|touch 路补交付测试：Select 级固定 touch pointerup 为空操作、随后 click 恰触发 1 次 onOptionSelect（修复前已绿，属覆盖补齐，不改生产逻辑）；ProfileForm 级补 deferred 查询竞态测试（touch 选「无」后释放查询仍为「无」）。核实：Radix trigger 仅 mouse pointerdown 开菜单，touch 靠随后 click 开（dist :293-296 vs :303-305），测试序列按此写|src/frontend/src/shared/ui/Select.test.tsx:107；src/frontend/src/features/profiles/ProfileForm.test.tsx:444|

### Round 5 (2026-11-11T17:52:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t053_code_f007|minor|遗留|pointermove 进入的同值提交漏过 onOptionSelect：Radix 的提交条件是 pointerdown 或 pointermove 置位其 pointerTypeRef，我方 pressedRef 只认 pointerdown。ProfileForm 内不可达（查询挂起时菜单只有「无」一个选项；查询到达后默认已套用且不再重套），全仓唯一 onOptionSelect 调用方即该表单；Round 5 为最后一轮（限额 5），修后无复核轮，故记遗留。建议修复：每项镜像 Radix pointerTypeRef（down/move 均置位）并以镜像判据触发，补 D 案 Select 级测试。|p070|
|t053_test_f008|minor|遗留|与 code f007 同根（同值拖过释放提交未被守卫记录，探针 D 案实证：pointerdown 落 win-1、pointermove 过 None、pointerup 落 None 时 Radix 已提交，但 onOptionSelect=[] 且 onValueChange=[]）。见 p070。|p070|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（云端可验证部分；真实引擎与真实部署部分按链口径跳过计 pass，见「环境跳过」，本机未验证、不得记为已验）
- 测试：后端全量 2089 passed / 27 failed（与 t052 基线按名一致，无新增）/ 8 skipped / 2 errors（基线既有 flaky teardown）；前端全量 556 passed / 0 failed；`check:api` 与 `build` 通过；Round 4 后端零改动未重跑
- 黑盒：无（本机无 Docker / 真实引擎；AC-010 与 AC-006/007/008/009 真实引擎部分待用户机补验）
- review：Round 1 双路 FAIL（code 3 + test 5，8 条 finding）已修完并复审；Round 2 code FAIL（1 条 important 新 finding f004，test PASS 0 新 finding）已修完并复审；Round 3 code FAIL（1 条 important 新 finding f005，test PASS 0 新 finding）已修完并复审；Round 4 双路 PASS（code 1 条 minor 新 finding f006，test 2 条 minor 新 finding f006/f007），本轮修复完成（先红后绿，见「Review 处置」Round 4 表）；Round 5 双路 PASS（code 1 条 minor 新 finding f007，test 1 条 minor 新 finding f008，同根 pointermove 守卫判据窄；为最后一轮，记遗留 p070，不再新开修复轮，见「Review 处置」Round 5 表）
- AC 判定：见 `task.md` 行内打勾（15/15）

### 结果摘要

- 默认值：`humanize` / `portable_cookies` 默认开启（后端 DTO + ORM + 前端三端一致，OpenAPI 与前端类型重生成），其余高级选项默认值不变并由测试固定；既有 Profile 值不变（迁移 0007 只改 server default + 加 locale CHECK，不改写存量值）。
- 时区与语言：语言收敛为 `zh-CN` / `en-US` 封闭枚举（Literal 进 OpenAPI 与生成类型），非法值与非法时区 422 拒绝；时区→语言规则前后端同一实现（中文地区 7 时区 → `zh-CN`）；前端时区组合框（键入过滤、全量滚动、键盘操作、常用置顶）+ 语言联动与手动覆盖。
- 字体按语言分流：英文 Profile 的 fontconfig 追加中文标签拒绝规则（绑定集与未绑定回退均遵守），宿主 fontconfig 2.15.0 真实字体实测机制成立；中文 Profile 不裁剪。
- 字体集链路：A16 默认集只由后端按完整性决定（`FontSetListResponse.default_font_set_id`）、「无」为显式 null；A18 绑定集 fontconfig 生成失败即启动失败 `font_set_unavailable`；A19 损坏集重导入原子修复、Coordinator 缓存删除实时读取；A20 引用计数按 (平台, 集) 统计、列表校验 manifest 平台；A30 会话详情区分完整性与探测未覆盖。
- 长期文档：blueprint（domain / browser_runtime / frontend / decisions 新增 ADR 030，部分替代 ADR 024）与 specs（profile_management / fingerprint_platform）已更新；specs_index 已登记 t053。
- 遗留：环境跳过 6 项（AC-010、AC-006/007/008/009 真实引擎部分、UNVERIFIED-SPIKE #1 与 #2 剩余部分），均须用户机补验，见「环境跳过」；其中 #1/#2 的未知契约清单条目已改写为结论（本机已验部分 + 用户机补验方法），不再留 UNVERIFIED 状态；另 p070（Select onOptionSelect pointermove 守卫判据窄，ProfileForm 内不可达）待后续跟进。

### 长期文档闭环

- specs_index: `profile_management` 行加 t053、日期 2026-11-11；`fingerprint_platform` 行加 t053、日期 2026-11-11。
- blueprint 与 specs 更新见 Area 7；ADR 030 新增，部分替代 ADR 024（仅「字体集整体可见」部分）。
- 正式 spike：无新增 spike；UNVERIFIED-SPIKE #2 已改写为结论（宿主验证通过，镜像内版本待补验），#1 已改写为结论（链路本机已验，引擎内裁决待用户机补验）。

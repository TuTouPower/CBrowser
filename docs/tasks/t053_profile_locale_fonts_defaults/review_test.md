# Task review t053（reviewer_focus: 测试）

- task：`t053_profile_locale_fonts_defaults`
- spec：`docs/tasks/t053_profile_locale_fonts_defaults/task.md`
- diff_anchor：`1e11e0fda2d2fda130e24e6bdef904c5b96c3516`
- target：`git -C '/home/hatch/workspace/CBrowser_t053' diff 1e11e0fda2d2fda130e24e6bdef904c5b96c3516`
- round：1
- reviewed_at：2026-11-11T15:56:37+08:00

reviewed_scope: ea6850a20f4716ce

说明：实施方派审前未对 11 个新交付文件执行 `git add -N`（`git status --short` 中仍为 `??`，`git diff` 不含它们），本报告的审查范围仍以指纹为准——11 个新文件已逐个全文读过并实跑其测试，不存在 reviewer 看不到的未跟踪交付文件。

## Findings

### t053_test_f001 - UNVERIFIED-SPIKE #1 仍未验证，且 AC-009 无任何测试

- 严重度：important
- 锚点：AC-009；task.md「未知契约清单」UNVERIFIED-SPIKE #1
- 位置：`docs/tasks/t053_profile_locale_fonts_defaults/task.md`（AC-009 行与未知契约清单 #1 行）；整 diff 无对应测试
- 问题：task.md 未知契约清单仍含 `UNVERIFIED-SPIKE` 标记（#1：CloakBrowser `geoip=True` 时显式传入的 `locale` 是否优先于出口 IP 推断），按 review 规则，进入 review 前清单应已无 UNVERIFIED 标记，仍有即实施前门禁被绕过。AC-009（运行时 `navigator.language` 等于 Profile 配置的语言，不被出口 IP 自动推断覆盖）在整个 diff 中没有任何测试：无 E2E、无单测、无集成测试读取 `navigator.language`；`tests/e2e` 零改动；locale 只被测到“存入配置”为止，是否传给引擎、引擎是否以此覆盖 geoip 推断，全无验证。实施方称“真实引擎验证本机做不了，已列入环境跳过”，但该 AC 在可测试性声明中列为可自动测试（真实引擎 E2E），且替代验证（用户机 E2E）尚未发生。
- 建议：补真实引擎 E2E（参照 `tests/e2e/test_fingerprint_platform_e2e.py` 的 `navigator.language` 读取模式，在用户机验证显式 locale 优先于 geoip 推断），验证后把未知契约清单 #1 改写为结论；在此之前 AC-009 打勾作废。

### t053_test_f002 - AC-007 中文解析到具体字体无测试

- 严重度：minor
- 锚点：AC-007
- 位置：`tests/unit/test_t053_fontconfig_locale.py`（全文件；仅 `test_zh_cn_and_unset_locale_xml_reject_nothing` 与 `test_fc_list_hides_cjk_fonts_for_en_us` 的 zh-CN 一半相关）
- 问题：AC-007 要求中文 Profile 下中文文本解析到微软雅黑/宋体（windows）或苹方/冬青黑体（macos）。现有测试只验证 zh-CN 下字体可见（XML 无拒绝规则、`fc-list` 能列出 Noto CJK 字体），未验证 `:lang=zh` 解析结果落到上述任一具体字体。真实字体集不在本机，属环境受限的覆盖缺口。
- 建议：用户机真实引擎 E2E 中补 `fc-match :lang=zh` / `document.fonts.check` 断言到具体字体名。

### t053_test_f003 - AC-006 三种情况中仅合成单目录做了真实 fc-list 实测

- 严重度：minor
- 锚点：AC-006
- 位置：`tests/unit/test_t053_fontconfig_locale.py::test_fc_list_hides_cjk_fonts_for_en_us`（第 122-150 行）；`tests/unit/test_t053_fontconfig_locale.py::test_unbound_base_fallback_follows_locale_too`（第 79-88 行）
- 问题：AC-006 要求绑定 windows 与 macos 字体集、以及未绑定字体集三种情况均成立。真实 `fc-list` 实测只覆盖一个合成目录（NotoSansCJK-Regular.ttc + DejaVuSans.ttf）；macos 集无任何绑定测试；未绑定回退只断言生成 XML 文本含 `<rejectfont>` 与基础目录路径，未对文泉驿正黑做 `fc-list` 可见性实测。
- 建议：用户机真实引擎 E2E 中对 windows / macos / 未绑定三种情况各跑 `fc-list` 断言；或本机补未绑定回退目录的 `fc-list` 实测。

### t053_test_f004 - AC-008 重启后生效的运行时一半无测试

- 严重度：minor
- 锚点：AC-008
- 位置：`tests/integration/test_t053_profile_locale_api.py::test_locale_change_creates_new_config_version`（第 111-130 行）
- 问题：AC-008 要求语言修改后生成新配置版本、重启后字体可见性与 `navigator.language` 按新语言生效。现有测试只覆盖版本生成一半（`/versions` 为 [1, 2]）；重启后字体可见性与 `navigator.language` 生效无测试，需真实引擎。
- 建议：用户机真实引擎 E2E 中补语言修改 → 重启 → `fc-list` 与 `navigator.language` 复核。

### t053_test_f005 - ProfileForm「保持显式无字体集」测试用 200ms 固定等待断言不重套

- 严重度：minor
- 锚点：AC-011（测试质量）
- 位置：`src/frontend/src/features/profiles/ProfileForm.test.tsx`（「keeps an explicit none font set instead of re-applying the default」内 `await new Promise((resolve) => setTimeout(resolve, 200));` 后断言仍为「无」）
- 问题：以“200ms 内未重套”断言不重套是时序断言：若重套 effect 因查询缓慢在 200ms 后才触发，测试仍会通过而漏报 bug。该测试本身通过（前端全量 550 passed），但断言强度依赖墙钟。
- 建议：改为确定性断言（例如断言 `fontSetUserChosenRef` 守护逻辑的等价行为，或用 `waitFor` 反向断言加 `vi.advanceTimersByTime` 控制时钟）。

## 结论

- 前轮 finding 复核（Round N≥2 才写）：Round 1，无。
- 改测方向复核：无「迁就实现」的改测。逐项核对如下，全部有规格变更归因且保留原测试意图：
  - `tests/integration/test_api_subprocess.py` 的 `locale` 由 `en-GB` 改为 `en-US`（创建 payload 与重载断言两处）：语言已收敛为两值，非法值现被拒绝；拒绝路径由新集成测试覆盖；原测试意图（locale 值往返不变）保留。
  - `tests/unit/test_font_sets_api.py` 的计数断言改为 `(fingerprint_platform, font_set_id)` keyed 形式：A20 规格变更（引用计数按平台隔离），断言行为不变。
  - `tests/unit/test_a5_font_scan_offload.py` 的篡改测试改为 `.items` 访问：A16 响应形态变更，断言不变。
  - `tests/integration/test_font_sets_api.py` 跟随新响应形态并新增 A16 集成用例（显式 null 保持、篡改后默认集消失）。
  - `src/frontend/src/features/profiles/ProfileForm.test.tsx` 的「默认最新集」测试改为「预选后端默认集」（期望 `win-new` → `win-old`）：A16 规格变更（后端默认集胜过最新集），并新增 4 个测试覆盖新语义；dirty-runtime 测试补 focus + Enter 以适配新组合框交互，意图不变。
  - 其余 12 个前端测试文件的 `fontSets.list` mock 一律改为 `{items, default_font_set_id}` 新形态，纯机械适配，无断言改动。
- 本轮新发现：5 条（1 条 important，4 条 minor）。
- 未进表的提示：
  - `test_t053_fontconfig_locale.py:101-105` 的 `pytest.mark.skipif`（fc-list 或夹具字体缺失时跳过真实字体实测）已调查：本机 fc-list 与夹具字体均存在，本轮实跑中该测试实际执行并通过（t053 五个文件 52 passed / 0 skipped），非静默跳过；仅在无 fontconfig 的环境下跳过，属环境门控，不出 finding。
  - `tests/unit/test_t053_coordinator_font_runtime.py::test_no_font_runtime_cache_attribute` 是内部属性缺失断言，仅作回归钉子；AC-013/A19 的行为证据由同文件另两个实时读取测试承担，不以此为 AC 证据。
  - AC-013 的 SSE 一半无字体专用的 SSE 测试，依赖已测的 Coordinator 实时读取路径与通用 SSE 传输测试；REST 一半由 `test_font_sets_api.py` 的篡改反射测试覆盖。未单列 finding。
  - `progress.md` 内计数前后不一致：Area 1 称 `test_t053_profile_locale.py` 为 17 tests，收尾报告称 26 tests；实测该文件确为 26 tests（t053 新增后端合计 52 = 26 + 9 + 9 + 3 + 5），以实测为准。
  - 引用逐项核对通过：`docs/reviews/review_20261110_200842/adoption_decision.md` 存在；`tests/e2e/test_fingerprint_platform_e2e.py` 存在（本 task 未改动）；迁移 `0007_profile_locale_enum_defaults.py` 的 revision/down_revision 与 progress.md 一致（`1a8db6b91744` / `c8d3e7a1f904`）；i18n 键 `fontSetDetectionMissing` / `fontSetIntegrityBad` 中英文均存在；task.md #2 引用的 `test_fc_list_hides_cjk_fonts_for_en_us` 存在。未发现虚假引用。
  - 必查项（用户裁定锁死）通过：`com.cbrowser.deployment-id` 在 `src/`、`tests/`、`scripts/`、`compose.yaml` 中零命中，全仓仅 `docs/blueprint/decisions.md:342`（ADR 028 驳回记录）、`docs/tasks/t051_*` / `docs/tasks/t052_*` 的 progress/review 历史叙述及本 task `progress.md:30` 的锁死核对叙述中提及，均属允许的历史叙述；`resource_prefix` 默认仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/docker_adapter.py:234`），本 diff 未动这两处。
  - 危险模式扫描：`git diff` 与 11 个新文件全文扫描——无删测试、无 `.skip` / `.only`（除上述已调查的 skipif 环境门控）、无恒真/弱化断言、无 mock 被测逻辑（A18 测试 mock 的是 `prepare_profile_fontconfig` 这一协作函数以模拟生成失败，被测的 fail-closed 分支本身为生产代码；Coordinator 测试 mock 的是 `get_profile` 服务边界）、无注释掉的断言、无静默错误抑制、无 `.value =` 替代真实交互（TimezoneCombobox 的 mousedown 提交与生产实现一致，键盘测试用真实 keyDown 事件）。`toContain` 命中均为对渲染文本中精确 i18n 文案的存在/缺席断言（A30 文案区分），非弱化。
- 总体判断：测试整体可信、新测 52 + 17 全部真实触达生产逻辑、全量回归与基线按名一致无新增失败；但 AC-009 完全无测试且 UNVERIFIED-SPIKE #1 仍未验证，阻断 PASS。
- 系统性 follow-up：无（真实引擎 E2E 缺口已在 task.md 环境跳过中登记为用户机补验，不另立 tid）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。单元默认值三端断言 + HTTP 创建默认值集成测试 + ProfileForm 提交默认值测试均实跑通过。
- AC-002：TICK-VALID，re_verified。显式 False 存入后重载仍为 False 的测试实跑通过；集成 fixture 对全新库跑全部迁移（含 0007）。
- AC-003：TICK-VALID，re_verified。TimezoneCombobox 6 tests（过滤选中、全量滚动、置顶、键盘、自动选项、无匹配）随前端全量实跑通过。
- AC-004：TICK-VALID，re_verified。后端规则矩阵 + 前端规则测试 + ProfileForm 联动/手动覆盖/清空保持测试均实跑通过。
- AC-005：TICK-VALID，re_verified。单元与 HTTP 层非法 locale/时区 422 字段级错误测试均实跑通过。
- AC-006：TICK-VALID，re_verified。英文 XML 拒绝规则单测 + 宿主 fontconfig 2.15.0 真实字体 fc-list 实测均实跑通过（该测试实际执行，未跳过）；真实 Browser 引擎与真实字体集部分按链口径环境跳过，见 minor f003。
- AC-007：TICK-VALID，re_verified。zh-CN 下无拒绝规则 + fc-list 可见 CJK 字体的测试均实跑通过；解析到具体字体名部分按链口径环境跳过，见 minor f002。
- AC-008：TICK-VALID，re_verified。语言修改生成新配置版本的集成测试（/versions [1, 2]）实跑通过；重启后生效部分按链口径环境跳过，见 minor f004。
- AC-009：TICK-VOID，re_verified。整 diff 无任何读取 navigator.language 的测试，tests/e2e 零改动；UNVERIFIED-SPIKE #1 仍未验证，见 important f001。
- AC-010：TICK-VALID，trust_prior。[deploy] AC，不要求自动测试；替代验证为部署后人工启动两种语言 Profile（尚未发生，依赖用户机补验，见 progress.md 环境跳过）。
- AC-011：TICK-VALID，re_verified。后端默认集预选/显式 null 保持的 ProfileForm 测试与 HTTP 集成测试均实跑通过。
- AC-012：TICK-VALID，re_verified。绑定集 fontconfig 失败即 font_set_unavailable 且不启动、未绑定集保持回退的 runner 测试均实跑通过。
- AC-013：TICK-VALID，re_verified。重导入修复（删除/篡改）测试与 Coordinator 实时读取测试均实跑通过；REST 列表篡改反射由既有集成测试覆盖。
- AC-014：TICK-VALID，re_verified。按 (平台, 集) 计数测试与 manifest 平台不一致标完整性失败测试均实跑通过。
- AC-015：TICK-VALID，re_verified。会话详情「探测字体未覆盖」文案测试与篡改文件不进探测缺失测试均实跑通过。

coverage = 14 / 15

实跑记录（均为本轮独立复跑，非 implementer 自述）：后端 t053 新增 5 文件 52 passed / 0 failed（`~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=<worktree>/src/backend`）；后端全量 tests/unit + tests/integration 2080 passed / 27 failed / 8 skipped / 2 errors，与 t052 基线（2026 passed / 27 failed / 8 skipped / 2 errors）按名逐项一致，27 failed 全部为基线既有（a24 2、automation_cdp 1、repo_hygiene 1、t028 4、t034 2、agent_executor_chain 7、automation_cdp_flow 2、automation_probe_chain 3、control_attendant_chain 1、normal_exit_replay 4），无新增失败；前端全量 `npm test`（Node 26.13.0，含 test:types）76 files / 550 passed / 0 failed，与基线 533 passed / 0 failed 相比 +17 均为本 task 新增。

verdict: FAIL

## Round 2 (2026-11-11T16:53:21+08:00)

reviewed_scope: 1973e9f3e826758f

说明：指纹已用 `.repo_template/scripts/repo_task/monitoring.py::review_scope_fingerprint` 独立重算，与本轮 prompt 给定指纹一致；审阅期间工作区无变动（`git status --short` 仍为 64 条、13 个未跟踪文件与审阅前一致），不存在 reviewer 看不到的未跟踪交付文件。

### 前轮 finding 复核

- t053_test_f001（important，AC-009 链路测试 + spike #1 改写为结论）：**已消除**。新增 `tests/unit/test_t053_fontconfig_locale.py::test_explicit_locale_reaches_engine_launch_alongside_geoip`（第 427 行，zh-CN / en-US 双参数）实跑通过：断言 `launch_persistent_context_async` 调用收到 `locale == 配置值`、`geoip is True`、`timezone is None`，且同一 locale 驱动生成的 fontconfig（en-US 含 `<rejectfont>`、zh-CN 不含）。生产侧核实：`src/backend/cbrowser/runtime_agent/runner.py:694` 原样传 `locale=cfg.locale, geoip=cfg.geoip`，`:586` 以 `locale=cfg.locale` 生成 fontconfig。变红验证：以无拒绝规则的旧形态配置（locale=None）实跑 `fc-list`/`fc-match`，CJK 字体仍可见、`fc-match :lang=zh-cn` 仍解析到 CJK 文件，证明该测试的 fontconfig 一半在旧实现下会变红。`task.md` 未知契约清单 #1 已改写为结论，全文 grep 无 `UNVERIFIED-BLOCKING` / `UNVERIFIED-SPIKE` 标记（仅剩模板规范说明行）；引擎内显式 locale 是否优先于 geoip 推断仍属环境跳过，`progress.md`「环境跳过」已写明「本机无法验证，不得记为已验」并给出用户机补验方法。
- t053_test_f002（minor，AC-007 fc-match 实测）：**已消除**。新增 `test_zh_cn_fc_match_resolves_to_platform_set_chinese_font`（第 328 行，windows / macos 双参数）实跑通过：真实 `fc-match :lang=zh-cn` 在 zh-CN 配置下解析到平台集目录内的中文字体文件（断言精确文件路径 + family 含 `CJK`），en-US 配置下解析到集内拉丁字体文件，证明分流确由语言驱动。变红验证：同一模式在无拒绝规则的旧形态配置下解析到 CJK 文件，与 en-US 断言冲突。诚实限定：本机无微软雅黑/宋体/苹方/冬青黑体文件，以宿主真实中文字体 NotoSansCJK-Regular.ttc 代行，测试 docstring 与 `progress.md` 环境跳过均已写明确切平台字体名待用户机复核，未编造字体名。
- t053_test_f003（minor，AC-006 macos 集与未绑定回退真实 fc-list）：**已消除**。新增 `test_fc_list_hides_cjk_fonts_for_macos_set`（第 365 行）与 `test_unbound_fallback_follows_locale_in_real_fc_list`（第 382 行）实跑通过：前者对 macos 集目录真实 `fc-list` 断言 en-US 下 CJK 不可见、拉丁可见；后者 monkeypatch `BASE_FONTS_DIR` 为宿主真实字体目录后走 `profile_font_dirs → prepare_profile_fontconfig → fc-list` 全生产路径，en-US/zh-CN 两配置下可见性均符合语言规则。`BASE_FONTS_DIR` 补丁仅替换环境常量（真实目录只存在于 Browser 镜像），被测路径未被 mock。变红验证同 f001：无拒绝规则的旧形态配置下 `fc-list` 仍列出 CJK。
- t053_test_f004（minor，AC-008 重启测试）：**已消除**。新增 `test_restart_after_locale_change_regenerates_fontconfig`（第 470 行）实跑通过：en-US 启动 → 新快照版本 + 新运行时实例重启为 zh-CN，两次启动的 locale 均被 fake 启动层记录为 `["en-US", "zh-CN"]` 且 `geoip` 均为 True；真实 fontconfig 写入器两次均运行，en-US 配置含 `<rejectfont>`、zh-CN 配置不含。变红验证：旧实现两次生成同一份无拒绝规则配置，首个断言即失败。真实引擎内 `navigator.language` 仍属环境跳过（`progress.md` 已写明）。
- t053_test_f005（minor，200ms 固定等待改为确定性断言 + 共享 Select onOptionSelect 改动）：**已消除**。`ProfileForm.test.tsx`「keeps an explicit none font set instead of re-applying the default」（第 288 行）已重写：查询以 deferred promise 挂起，用户先选「无」，测试再以 `act` 释放查询并刷状态，随后断言默认集已可提供但选中仍为「无」；全文 grep 确认该文件已无 `setTimeout` / 200ms 等待。生产缺陷核实：Radix 源码（`node_modules/@radix-ui/react-select/dist/index.js:159-165`，`handleUserSelect → setValue` 经 `useControllableState`）证实同值重选不触发 `onValueChange`，缺陷真实；`Select.tsx:70` 在 `SelectPrimitive.Item` 上加 `onClick → onOptionSelect`，`ProfileForm.tsx:518` 以此记录显式选择。变红依据：按控制流分析，若去掉 `onOptionSelect`，`fontSetUserChosenRef` 保持 false，查询到达后默认应用 effect 会把选中改写为 win-1，末尾断言失败（审阅员只读边界，未做变异运行，此条以控制流 + Radix 源码为证）。无回归：`onOptionSelect` 为可选 prop，全仓唯一调用方即该字体集 Select，其余 Select 调用方均未传；键盘选取同样经 item click 触发，无行为分叉。

### 本轮新发现

0 条。

## 结论

- 前轮 finding 复核：f001–f005 全部已消除，见上（每条均以 diff/代码/实跑核实，未采信处置表自述）。
- 改测方向复核：无「迁就实现」的改测。Round 2 唯一改写既有测试是 f005 的「保持显式无字体集」测试：意图不变（显式「无」不得被默认集覆盖），断言由墙钟等待加强为确定性 deferred 查询 + `act` 刷状态，且改写中暴露的生产缺陷已修复并由同一测试覆盖。其余 4 个既有测试文件的改动与 Round 1 核对一致，未再变动。
- 本轮新发现：0 条。
- 未进表的提示：
  - `onOptionSelect` 无独立的 Select 单元测试，仅由 ProfileForm 端到端测试覆盖；唯一调用方即 ProfileForm 的字体集 Select，其余调用方均未传该 prop，无回归面。列为提示，不进 finding。
  - f004 重启测试两次启动用不同 instance_id（instance_a/instance_b），模拟新运行时实例；不影响所断言的 fontconfig 再生与 locale 传递。
  - AC-009 引擎内优先级仍为环境跳过（`progress.md` 已写明「本机无法验证，不得记为已验」并给出用户机补验方法）；链口径按任务指令（t051 AC-013 / t052 AC-012 前例）打勾，见 AC 复验行。
  - 必查项（用户裁定锁死）复核通过：`com.cbrowser.deployment-id` 在 `src/`、`tests/`、`scripts/`、`compose.yaml` 中零命中；`resource_prefix` 默认仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/docker_adapter.py:234`），本 diff 未动这两处。
  - 危险模式复扫（本轮新增测试 + 全 diff 测试文件）：无删测试、无 `.skip` / `.only`（仅 `test_t053_fontconfig_locale.py:102` 的 `skipif` 环境门控，本轮实跑中 61 个 t053 测试全部执行、0 skipped）、无恒真/弱化断言、无 mock 被测逻辑（stub 均为引擎/显示/脉冲/启动调用等系统边界，`BASE_FONTS_DIR` 补丁仅替换环境常量）、无注释掉的断言、无静默错误抑制、无 `.value =` 替代真实交互；`toContain` 命中均为列表内容 / i18n 文案断言，关键选中态断言仍用 `.toBe` 精确比对。
  - 引用逐项核对通过：`task.md` 未知契约 #1 引用的 `test_explicit_locale_reaches_engine_launch_alongside_geoip` 存在（第 427 行）；`progress.md` 处置表 fix_ref 行号与实际一致（f002:328、f003:365/382、f001:427、f004:470、f005 测试 :288、Select.tsx:70、ProfileForm.tsx:518）；`progress.md` 回归实数与本轮实跑一致（后端 2089 / 前端 551）。
- 总体判断：Round 1 的 5 条 finding 全部真实修复且新测试均会变红（f005 以控制流 + Radix 源码为证），无新问题，全量回归与基线按名一致无新增失败。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。默认值三端单测、HTTP 创建默认值集成测试、ProfileForm 提交默认值测试均随本轮全量回归通过。
- AC-002：TICK-VALID，re_verified。显式 False 存入重载仍为 False、迁移 0007 全量跑通，随本轮全量回归通过。
- AC-003：TICK-VALID，re_verified。TimezoneCombobox 7 tests（含同尺寸候选集高亮复位新测试）随前端全量通过。
- AC-004：TICK-VALID，re_verified。后端规则矩阵、前规则测试、ProfileForm 联动/手动覆盖/清空保持测试随全量通过。
- AC-005：TICK-VALID，re_verified。单元与 HTTP 层非法 locale/时区 422 字段级错误测试随全量通过。
- AC-006：TICK-VALID，re_verified。英文 XML 拒绝规则单测 + 宿主 fontconfig 真实 fc-list 实测（合成单目录、macos 集、未绑定回退三情况）均实跑通过；真实 Browser 引擎部分按链口径环境跳过（progress.md 已写明本机未验证）。
- AC-007：TICK-VALID，re_verified。zh-CN 无拒绝规则 + fc-list 可见 CJK + 新增 fc-match 双集实测（zh-CN 解析到集内中文字体文件、en-US 解析到拉丁字体）均实跑通过；确切平台字体名（微软雅黑/宋体/苹方/冬青黑体）待用户机以真实字体集复核，见环境跳过。
- AC-008：TICK-VALID，re_verified。语言修改生成新配置版本（/versions [1, 2]）+ 新增重启测试（双 Runner、fontconfig 按新语言再生、两次启动 locale 均有记录）均实跑通过；真实引擎内 navigator.language 仍属环境跳过。
- AC-009：TICK-VALID，re_verified。新增链路测试（zh-CN/en-US 双参数：locale 与 geoip=True 一并到达引擎启动调用、同一 locale 驱动 fontconfig）实跑通过；task.md 未知契约 #1 已改写为结论、无 UNVERIFIED 标记；引擎内显式 locale 是否优先于 geoip 推断仍属环境跳过（progress.md 已写明本机未验证、用户机补验方法）。
- AC-010：TICK-VALID，trust_prior。[deploy] AC，不要求自动测试；替代验证为部署后人工启动两种语言 Profile（尚未发生，依赖用户机补验，见 progress.md 环境跳过）。
- AC-011：TICK-VALID，re_verified。后端默认集预选/显式 null 保持的 ProfileForm 测试（含确定性重写后的「保持显式无字体集」测试）与 HTTP 集成测试均实跑通过。
- AC-012：TICK-VALID，re_verified。绑定集 fontconfig 失败即 font_set_unavailable 且不启动、未绑定集保持回退的 runner 测试均实跑通过。
- AC-013：TICK-VALID，re_verified。重导入修复（删除/篡改）测试与 Coordinator 实时读取测试均实跑通过；REST 列表篡改反射由既有集成测试覆盖。
- AC-014：TICK-VALID，re_verified。按 (平台, 集) 计数测试与 manifest 平台不一致标完整性失败测试均实跑通过。
- AC-015：TICK-VALID，re_verified。会话详情「探测字体未覆盖」文案测试与篡改文件不进探测缺失测试均实跑通过。

coverage = 14 / 15

实跑记录（均为本轮独立复跑，非 implementer 自述）：后端 t053 新增 5 文件 61 passed / 0 failed（`~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=<worktree>/src/backend`，含本轮新增 9 个测试：fontconfig 文件 +7、profile_locale 文件 +2）；后端全量 tests/unit + tests/integration 2089 passed / 27 failed / 8 skipped / 2 errors（7 分 51 秒），27 failed 按名与 t052 基线完全一致（a24 2、automation_cdp 1、repo_hygiene 1、t028 4、t034 2、agent_executor_chain 7、automation_cdp_flow 2、automation_probe_chain 3、control_attendant_chain 1、normal_exit_replay 4），无新增失败；前端全量 `npm test`（Node 26.13.0）76 files / 551 passed / 0 failed；变红验证脚本（旧形态无拒绝规则配置下 fc-list 仍列 CJK、fc-match :lang=zh-cn 仍解析到 CJK 文件）已跑，结论见各 finding 复核。

verdict: PASS


## Round 3 (2026-11-11T17:04:57+08:00)

reviewed_scope: 0cc2dd5bdc0b8bd6

说明：指纹已用 `.repo_template/scripts/repo_task/monitoring.py::review_scope_fingerprint` 独立重算，与本轮 prompt 给定指纹一致；审阅期间工作区无变动（`git status --short` 仍为 64 条，与 Round 2 一致），不存在 reviewer 看不到的未跟踪交付文件。注：本报告写完后（17:05 CST）工作区出现 2 个并行 code 审阅员的临时探针文件（`src/frontend/src/shared/ui/__r3_scratch_mouse.test.tsx`、`__r3_scratch_radix.test.tsx`，文件头自述“TRANSIENT reviewer scratch test，deleted after run”），非交付文件、非我创建、我的实跑（前端全量 76 files / 552 passed）完成于其出现之前；其存在期间重算指纹为 `09b208c2543f59f8`，删除后即恢复为本报告的 `0cc2dd5bdc0b8bd6`。本轮后端零改动，按任务指令只跑受影响的 t053 后端文件；前端全量独立重跑。

### 前轮 finding 复核

- t053_test_f001–f005（Round 1）：**全部仍已消除**。本轮 diff 指纹与 Round 2 派审时一致，无任何改动；后端 t053 五文件重跑 61 passed / 0 failed（含 f001–f004 的新增测试），`skipif` 环境门控本轮实际执行、0 skipped；前端全量 552 passed 含 f005 的确定性重写测试。无回退。
- t053_code_f004（Round 2 important，键盘同值重选「无」不触发守卫）——测试侧复核：**已消除**，先红后绿证据可信（以下为审阅员独立验证，非采信处置表自述）：
  - 新键盘测试 `ProfileForm.test.tsx:343`（`keeps an explicit none font set when picked by keyboard instead of re-applying the default`）随前端全量通过；受影响两文件单跑 `ProfileForm.test.tsx`（12 tests）+ `TimezoneCombobox.test.tsx`（7 tests）19 passed。
  - 红（旧实现下确实失败）的控制流证明：表单字体集 Select 为受控组件（`ProfileForm.tsx:505`，`value={values.font_set_id ?? "__none__"}`），测试开始时已显示「无」；Radix `useControllableState.setValue`（`node_modules/@radix-ui/react-use-controllable-state/dist/index.js`）在受控时 `if (value2 !== prop) onChange(...)`——同值重选永不调用 `onValueChange`，即 ProfileForm 的 `onValueChange`（唯一另一处把 `fontSetUserChosenRef` 置 true 的地方，`ProfileForm.tsx:511`）在键盘重选「无」时不会运行；无 `onKeyDown` 时键盘 Enter 只走 Radix 自身 `handleSelect`，ref 保持 false，deferred 查询释放后默认套用 effect（`ProfileForm.tsx:243-252`）把 `font_set_id` 改写为 `win-1`，末尾精确断言 `.toBe(en.formFontSetNone)` 失败。红成立。
  - 绿（新实现下通过）的生产触达证明：`Select.tsx:83` 的 `onKeyDown` 经 Radix `composeEventHandlers(itemProps.onKeyDown, …)`（`node_modules/@radix-ui/react-select/dist/index.js:1003`）与 Radix 自身键盘处理并存，两路都跑；测试在真实渲染的 Radix option 元素上 `fireEvent.keyDown(noneOption, { key: "Enter" })`（`event.target` 即 item 本身，通过 `event.target !== event.currentTarget` 守卫，与真实浏览器里焦点落在 item 上收到的按键一致），未 mock Select/Radix；`onOptionSelect` 置 ref 后 effect 提前返回，选中保持「无」。绿成立。
  - 鼠标与键盘两路均覆盖且互相隔离：鼠标测试（`:288`）用 `fireEvent.click`（只走 `onClick`）；键盘测试用 keyDown Enter（`fireEvent` 不合成 click，不走 `onClick`），两测试除选取路径外结构相同，键盘测试单独隔离了 `onKeyDown` 路径。
  - 无弱化断言：首尾两处关键断言均为精确 `.toBe(en.formFontSetNone)`；中间「win-1 已提供」用 `.toBeInTheDocument()` 仅作默认集可达性的存在检查，不是 AC 证据。
  - `onSelect` 不存在已再核实：已装 Radix 2.4.1 的 `index.d.ts` 中 `onSelect` 零命中，`SelectItemProps` 仅继承 `PrimitiveDivProps`；`onKeyDown`（Enter/Space，与 Radix `SELECTION_KEYS` 一致）是等价挂法，属实。

### 本轮新发现

0 条。

## 结论

- 前轮 finding 复核：Round 1 的 5 条与 Round 2 的 code f004 测试侧全部已消除，见上（f004 的红绿均以 Radix 源码 + 控制流独立证实，未采信处置表自述）。
- 改测方向复核：无「迁就实现」的改测。本轮唯一新增测试是键盘复现测试，意图与鼠标测试相同（显式「无」不得被默认集覆盖），断言为精确 `.toBe`，未改动任何既有测试的预期。
- 本轮新发现：0 条。
- 未进表的提示：
  - Space 键未单独测试：`onKeyDown` 对 Enter/Space 共用同一分支条件，键盘测试只用 Enter；Space 无独立分支，不补 test 不构成缺口。
  - `onKeyDown` / `onClick` 均无 `disabled` 守卫（Radix 自身 handler 有）：但 `SelectOption` 无 `disabled` 字段、`Select` 从不向 Item 传 `disabled`，全仓唯一 `onOptionSelect` 调用方即 ProfileForm 字体集 Select，该路径不可达；列为提示，不进 finding。
  - Space 在 typeahead 搜索进行时仍计一次选择：`Select.tsx` docstring 已披露，仅把当前显示值记为显式选择，属守卫的安全方向。
  - AC-009 引擎内优先级与 AC-010 仍属环境跳过（`progress.md` 已写明「本机未验证、不得记为已验」并给出用户机补验方法）；链口径按任务指令（t051 AC-013 / t052 AC-012 前例）打勾，见 AC 复验行。
  - 必查项（用户裁定锁死）复核通过：`com.cbrowser.deployment-id` 在 `src/`、`tests/`、`scripts/`、`compose.yaml` 中零命中；`resource_prefix` 默认仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/docker_adapter.py:234`），本 diff 未动这两处。
  - 危险模式复扫（本轮增量：`Select.tsx` onKeyDown + docstring、键盘测试）：无删测试、无 `.skip` / `.only`、无恒真/弱化断言、无 mock 被测逻辑（键盘测试用真实 Radix Select + 真实 `fireEvent` 按键）、无注释掉的断言、无静默错误抑制、无 `.value =` 替代真实交互；全 diff 复扫与 Round 2 一致。
  - 引用逐项核对通过：`progress.md` Round 2 处置表 fix_ref 行号与实际一致（`Select.tsx:83`、`ProfileForm.test.tsx:343`）；键盘测试注释引用的 `t053_code_f004` 与 code 报告一致。
- 总体判断：f004 键盘修复的测试侧真实可信（红绿均有源码级证据、鼠标键盘双路覆盖、断言未弱化），无新问题，前端全量 552 passed 与基线一致、后端 t053 文件 61 passed。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。默认值三端单测、HTTP 创建默认值集成测试、ProfileForm 提交默认值测试均随本轮重跑通过（后端 t053 文件 61 passed + 前端全量 552 passed）。
- AC-002：TICK-VALID，re_verified。显式 False 存入重载仍为 False、迁移 0007 全量跑通，随本轮后端 t053 文件重跑通过。
- AC-003：TICK-VALID，re_verified。TimezoneCombobox 7 tests 随本轮前端全量通过（单跑 19 passed 含其中 7 个）。
- AC-004：TICK-VALID，re_verified。后端规则矩阵、前规则测试、ProfileForm 联动/手动覆盖/清空保持测试随本轮重跑通过。
- AC-005：TICK-VALID，re_verified。单元与 HTTP 层非法 locale/时区 422 字段级错误测试随本轮后端重跑通过。
- AC-006：TICK-VALID，re_verified。英文 XML 拒绝规则单测 + 宿主 fontconfig 真实 fc-list 实测（合成单目录、macos 集、未绑定回退三情况）随本轮后端重跑通过；真实 Browser 引擎部分按链口径环境跳过（progress.md 已写明本机未验证）。
- AC-007：TICK-VALID，re_verified。zh-CN 无拒绝规则 + fc-list 可见 CJK + fc-match 双集实测随本轮后端重跑通过；确切平台字体名（微软雅黑/宋体/苹方/冬青黑体）待用户机以真实字体集复核，见环境跳过。
- AC-008：TICK-VALID，re_verified。语言修改生成新配置版本（/versions [1, 2]）+ 重启测试（双 Runner、fontconfig 按新语言再生）随本轮后端重跑通过；真实引擎内 navigator.language 仍属环境跳过。
- AC-009：TICK-VALID，re_verified。链路测试（zh-CN/en-US 双参数：locale 与 geoip=True 一并到达引擎启动调用、同一 locale 驱动 fontconfig）随本轮后端重跑通过；task.md 未知契约 #1 已改写为结论、无 UNVERIFIED 标记；引擎内显式 locale 是否优先于 geoip 推断仍属环境跳过（progress.md 已写明本机未验证、用户机补验方法）。
- AC-010：TICK-VALID，trust_prior。[deploy] AC，不要求自动测试；替代验证为部署后人工启动两种语言 Profile（尚未发生，依赖用户机补验，见 progress.md 环境跳过）。
- AC-011：TICK-VALID，re_verified。后端默认集预选/显式 null 保持的 ProfileForm 测试（含鼠标与键盘两路「保持显式无字体集」测试）与 HTTP 集成测试均随本轮重跑通过。
- AC-012：TICK-VALID，re_verified。绑定集 fontconfig 失败即 font_set_unavailable 且不启动、未绑定集保持回退的 runner 测试随本轮后端重跑通过。
- AC-013：TICK-VALID，re_verified。重导入修复（删除/篡改）测试与 Coordinator 实时读取测试随本轮后端重跑通过；REST 列表篡改反射由既有集成测试覆盖。
- AC-014：TICK-VALID，re_verified。按 (平台, 集) 计数测试与 manifest 平台不一致标完整性失败测试随本轮后端重跑通过。
- AC-015：TICK-VALID，re_verified。会话详情「探测字体未覆盖」文案测试与篡改文件不进探测缺失测试随本轮后端重跑通过。

coverage = 14 / 15

实跑记录（均为本轮独立复跑，非 implementer 自述）：后端 t053 五文件 61 passed / 0 failed / 0 skipped（`~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=<worktree>/src/backend`，16.31s；本次后端零改动，未重跑后端全量）；前端全量 `npm test`（Node 26.13.0，含 `test:types`）76 files / 552 passed / 0 failed（125.80s），与任务基线 551 相比 +1 即新增键盘测试；受影响两文件单跑 `ProfileForm.test.tsx` + `TimezoneCombobox.test.tsx` 19 passed。

verdict: PASS

## Round 4 (2026-11-11T17:31:00+08:00)

reviewed_scope: a089e455ced309b6

说明：指纹已用 `.repo_template/scripts/repo_task/monitoring.py::review_scope_fingerprint` 独立重算，与本轮 prompt 给定指纹一致（与 Round 3 的 `0cc2dd5bdc0b8bd6` 不同，差量为 Round 3 test 报告本文的追加；交付内容本身自 Round 3 派审后无改动，`git status --short` 仍为 64 条）。审阅期间工作区出现过并行 Round 4 code 审阅员的临时探针文件（`src/frontend/src/shared/ui/__r4_scratch_select.test.tsx`，09:22 出现、其后由其所有者删除），非交付文件、非我创建；本轮前端全量以 `--exclude '**/__r4_scratch_select.test.tsx'` 运行，计 76 files / 552 passed，未计入该探针的 4 个测试。本轮结论未参考另一路审阅的任何结论；下述 touch / drag-across 证据均来自我自己的临时探针（`__r4_test_scratch_touch.test.tsx`，跑后即删，`git status` 已核对无残留）。

### 前轮 finding 复核

- t053_test_f001–f005（Round 1）：**全部仍已消除**。后端 t053 五文件重跑 61 passed / 0 failed / 0 skipped；前端全量 552 passed 含 f005 的确定性重写测试与键盘测试。无回退。
- t053_code_f005（Round 3 important，鼠标同值重选「无」在真实浏览器里到不了 onOptionSelect）——测试侧复核：**已消除**，先红后绿证据由审阅员独立变异验证（非采信处置表自述）：
  - 红（旧实现下确实失败）：临时去掉 `Select.tsx:93-102` 的 `onPointerUp`（即 Round 2 形态），忠实序列鼠标测试失败于 `ProfileForm.test.tsx:383`——`expected 'win-1' to be 'Not configured'`，与处置表所述红象完全一致；其余 11 项通过。变异后立即从备份恢复，`diff -q` 核对恢复一致。
  - 绿（新实现下通过）：恢复后同一测试单跑通过；前端全量 552 passed。
  - `isConnected === false` 断言（`ProfileForm.test.tsx:359`）固定了真实浏览器条件：红跑中该断言同样通过（失败点在 :383 的终态断言），即它独立于守卫修复、只锁定“pointerup 提交后菜单已同步卸载、随后 click 派给已卸载节点”这一顺序；Radix 源码佐证：`react-select/dist/index.js` 的 item `onPointerUp` 在 `pointerTypeRef.current === "mouse"` 时调 `handleSelect`（其内 `onOpenChange(false)` 同步关菜单），`onClick` 仅 `!== "mouse"` 时提交；`composeEventHandlers`（`@radix-ui/primitive/dist/index.js:35-42`）使用者处理器先跑、Radix 自身关闭在后，item 在 `onOptionSelect` 触发时仍在挂载态。
  - `hasPointerCapture` 补桩恰当：Radix 在 trigger 的 `onPointerDown`（dist:300）调 `target.hasPointerCapture(event.pointerId)`；jsdom 无此方法，测试文件首 `beforeAll` 以 `typeof` 守卫补 `() => false` + `releasePointerCapture` 空实现，仅填 jsdom 环境缺口（返回 false 即“未持有捕获”，与真实浏览器无捕获时的常规情形一致，且 Radix 只在返回 true 时才调 release），未 mock 被测逻辑。
  - 三路提交覆盖与互不干扰：鼠标（忠实序列，`fireEvent.pointerDown/Up` + 已卸载节点 click）与键盘（Enter，`fireEvent.keyDown`，不合成 click）均有交付测试且互相隔离；touch/pen 路无交付测试，见 minor f007。互不重复触发由探针在 Select 层以调用计数验证：鼠标 pointerup 后 spy 恰 1 次、已卸载 click 不再触发；键盘 Enter 恰 1 次、无指针/click 事件；touch pointerup 为空操作、随后 click 恰 1 次。

### 本轮新发现

2 条（均为 minor）。

### t053_test_f006 - 拖过释放（drag-across）时未提交的 pointerup 也会触发 onOptionSelect，无测试固定提交边界

- 严重度：minor
- 锚点：AC-011；`Select.tsx` docstring 契约「Fires for every committed option pick」
- 位置：`src/frontend/src/shared/ui/Select.tsx:93-103`（`onPointerUp`）
- 问题：`onPointerUp` 只判断 `event.pointerType === "mouse"`，未判断本次 pointerup 是否一次真实提交。探针实测：pointerdown 落在 "none"、pointerup 落在从未按下的 "win-1" 时，`onOptionSelect` 被调 1 次（`spy=[["win-1"]]`），而 Radix 不提交（各 item 的 `pointerTypeRef` 是 per-item 的，win-1 的仍为初始 `"touch"`，其 `onPointerUp` 不调 `handleSelect`）、`onValueChange` 未调、两 option 仍在树内（菜单未关）。后果：一次未形成选择的拖拽手势就把 ProfileForm 的 `fontSetUserChosenRef` 置 true；若此时字体集查询仍在途，随后到达的后端默认将不再自动套用，表单停在「无」而非后端默认集，与 AC-011 “用户未显式选择时默认集生效”的意图相悖。窗口窄（须在查询到达前拖拽释放且随后不再显式选择），影响低，故 minor。
- 建议：把触发条件收窄到真实提交（例如只在该 item 自身见过 pointerdown 时触发），并补测试固定“未提交的 pointerup 不触发 onOptionSelect”。

### t053_test_f007 - touch/pen 提交路径的 onOptionSelect 无交付测试

- 严重度：minor
- 锚点：AC-011
- 位置：`src/frontend/src/shared/ui/Select.tsx:92`（`onClick`）；全仓 `pointerType: "touch"` 在交付测试中零命中
- 问题：共享 Select 的三路提交中，touch/pen 路（`onClick`）的 `onOptionSelect` 无任何交付测试覆盖：鼠标路有忠实序列测试、键盘路有 Enter 测试；`ProxyListPage.test.tsx:182` 的 bare click 只练到 `onValueChange`（该调用方未传 `onOptionSelect`）。探针实测该路径本身工作正常（touch pointerup 为空操作、随后 click 恰触发 1 次 `onOptionSelect("none")`，`onValueChange` 未调），故属覆盖缺口而非 bug。
- 建议：补一个 touch 序列测试（pointerdown/up `pointerType: "touch"` + click），与鼠标测试同构，固定守卫在触屏提交下同样成立。

## 结论

- 前轮 finding 复核：Round 1 的 5 条与 Round 3 的 code f005 测试侧全部已消除，见上（f005 红绿由审阅员独立变异运行证实，未采信处置表自述）。
- 改测方向复核：无「迁就实现」的改测。本轮交付内容与 Round 3 派审时一致，无既有测试改动。
- 本轮新发现：2 条 minor（f006 拖过释放的提交边界未固定、f007 touch 路径无交付测试），均不阻断。
- 未进表的提示：
  - 处置表 Round 3 fix_ref 行号已核对：`Select.tsx:93`（onPointerUp）、`ProfileForm.test.tsx:294`（忠实序列鼠标测试）均准确；键盘测试现位于 `:386`（Round 2 时的 `:343`，因鼠标测试改写增长而移位，非改动）。
  - `Select` 的其余 4 个调用方（EnvironmentListToolbar、ProxyFormDialog、ProxyListToolbar、SettingsPage）均未传 `onOptionSelect`，三路处理器在其上为空操作，无回归面；全量 552 passed 佐证。
  - Space 键仍只由 Enter 测试覆盖（与 Round 3 结论一致，共用同一分支，无独立分支）。
  - AC-009 引擎内优先级与 AC-010 仍属环境跳过（`progress.md` 已写明「本机未验证、不得记为已验」并给出用户机补验方法）；链口径按任务指令（t051 AC-013 / t052 AC-012 前例）打勾，见 AC 复验行。
  - 必查项（用户裁定锁死）复核通过：`com.cbrowser.deployment-id` 在 `src/`、`tests/`、`scripts/`、`compose.yaml` 中零命中；`resource_prefix` 默认仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/docker_adapter.py:234`），本 diff 未动这两处。
  - 危险模式复扫（本轮增量：`Select.tsx` onPointerUp + 忠实序列鼠标测试）：无删测试、无 `.skip` / `.only`、无恒真/弱化断言（关键选中态断言均为精确 `.toBe(en.formFontSetNone)`；`isConnected` 断言为 `.toBe(false)` 精确比对）、无 mock 被测逻辑（`hasPointerCapture` 补桩仅填 jsdom 环境缺口）、无注释掉的断言、无静默错误抑制、无 `.value =` 替代真实交互；鼠标测试内无 `setTimeout` / `waitFor`，无墙钟依赖。
  - 引用逐项核对通过：`progress.md` Round 3 处置表 fix_ref 行号与实际一致（见上）；`task.md` 未知契约清单无 `UNVERIFIED` 标记残留。
- 总体判断：f005 修复的测试侧真实可信（独立变异红绿、忠实序列触达生产逻辑、鼠标/键盘双路覆盖且互不干扰）；新发现仅 2 条 minor（拖过释放边界与 touch 路径覆盖），无回归，全量与基线一致。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。默认值三端单测、HTTP 创建默认值集成测试、ProfileForm 提交默认值测试均随本轮重跑通过（后端 t053 文件 61 passed + 前端全量 552 passed）。
- AC-002：TICK-VALID，re_verified。显式 False 存入重载仍为 False、迁移 0007 全量跑通，随本轮后端 t053 文件重跑通过。
- AC-003：TICK-VALID，re_verified。TimezoneCombobox 7 tests 随本轮前端全量通过。
- AC-004：TICK-VALID，re_verified。后端规则矩阵、前规则测试、ProfileForm 联动/手动覆盖/清空保持测试随本轮重跑通过。
- AC-005：TICK-VALID，re_verified。单元与 HTTP 层非法 locale/时区 422 字段级错误测试随本轮后端重跑通过。
- AC-006：TICK-VALID，re_verified。英文 XML 拒绝规则单测 + 宿主 fontconfig 真实 fc-list 实测（合成单目录、macos 集、未绑定回退三情况）随本轮后端重跑通过；真实 Browser 引擎部分按链口径环境跳过（progress.md 已写明本机未验证）。
- AC-007：TICK-VALID，re_verified。zh-CN 无拒绝规则 + fc-list 可见 CJK + fc-match 双集实测随本轮后端重跑通过；确切平台字体名（微软雅黑/宋体/苹方/冬青黑体）待用户机以真实字体集复核，见环境跳过。
- AC-008：TICK-VALID，re_verified。语言修改生成新配置版本（/versions [1, 2]）+ 重启测试（双 Runner、fontconfig 按新语言再生）随本轮后端重跑通过；真实引擎内 navigator.language 仍属环境跳过。
- AC-009：TICK-VALID，re_verified。链路测试（zh-CN/en-US 双参数：locale 与 geoip=True 一并到达引擎启动调用、同一 locale 驱动 fontconfig）随本轮后端重跑通过；task.md 未知契约 #1 已改写为结论、无 UNVERIFIED 标记；引擎内显式 locale 是否优先于 geoip 推断仍属环境跳过（progress.md 已写明本机未验证、用户机补验方法）。
- AC-010：TICK-VALID，trust_prior。[deploy] AC，不要求自动测试；替代验证为部署后人工启动两种语言 Profile（尚未发生，依赖用户机补验，见 progress.md 环境跳过）。
- AC-011：TICK-VALID，re_verified。后端默认集预选/显式 null 保持的 ProfileForm 测试（含鼠标忠实序列与键盘两路「保持显式无字体集」测试）与 HTTP 集成测试均随本轮重跑通过；touch 路径无交付测试见 minor f007，drag-across 边界见 minor f006，均不影响已覆盖的两路。
- AC-012：TICK-VALID，re_verified。绑定集 fontconfig 失败即 font_set_unavailable 且不启动、未绑定集保持回退的 runner 测试随本轮后端重跑通过。
- AC-013：TICK-VALID，re_verified。重导入修复（删除/篡改）测试与 Coordinator 实时读取测试随本轮后端重跑通过；REST 列表篡改反射由既有集成测试覆盖。
- AC-014：TICK-VALID，re_verified。按 (平台, 集) 计数测试与 manifest 平台不一致标完整性失败测试随本轮后端重跑通过。
- AC-015：TICK-VALID，re_verified。会话详情「探测字体未覆盖」文案测试与篡改文件不进探测缺失测试随本轮后端重跑通过。

coverage = 14 / 15

实跑记录（均为本轮独立复跑，非 implementer 自述）：后端 t053 五文件 61 passed / 0 failed / 0 skipped（`~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=<worktree>/src/backend`，33.82s；本次后端零改动，未重跑后端全量）；前端全量 `npm test`（Node 26.13.0，含 `test:types`，以 `--exclude` 排除并行 code 审阅员的临时探针文件）76 files / 552 passed / 0 failed（189.49s），与任务基线 552 一致；变异验证：去掉 `onPointerUp` 后忠实序列鼠标测试红（`ProfileForm.test.tsx:383`，`expected 'win-1' to be 'Not configured'`），恢复后绿（单跑 1 passed）；自写临时探针 3 tests 全部通过（touch/click 恰 1 次、鼠标 pointerup 恰 1 次且已卸载 click 不重触发、drag-across spy=`[["win-1"]]` 且菜单未关），探针已删除、`git status` 已核对无残留。

verdict: PASS

## Round 5 (2026-11-11T17:45:31+08:00)

reviewed_scope: 634fc4db6bd1d4cc

说明：落点仓库校验通过（不带 `-C` 的 `git rev-parse --show-toplevel` 输出为 `/home/hatch/workspace/CBrowser_t053`）；指纹已用 `.repo_template/scripts/repo_task/monitoring.py::review_scope_fingerprint` 独立重算，与本轮 prompt 给定指纹一致；`git status --short` 为 65 条（51 M + 14 ??），无 scratch/探针残留，不存在 reviewer 看不到的未跟踪交付文件。本轮结论未参考另一路审阅的任何结论；下述变异与探针证据均来自我自己的临时操作（变异后均从 `/tmp` 备份恢复并以 `diff -q` 核对一致，探针文件跑后即删，`git status` 已核对无残留）。

### 前轮 finding 复核

- t053_test_f001–f005（Round 1）：**全部仍已消除**。后端 t053 五文件重跑 61 passed / 0 failed / 0 skipped（含 f001–f004 的新增测试）；前端全量 556 passed 含 f005 的确定性重写测试、键盘测试与忠实序列鼠标测试。无回退。
- t053_test_f006（minor，拖过释放误记显式选择）：**已消除**，先红后绿证据由审阅员独立变异验证（非采信处置表自述）：
  - 红（旧实现下确实失败）：临时去掉 `Select.tsx:121` 的 `pressedRef.current` 条件（即 Round 4 形态），新拖过测试失败于 `Select.test.tsx:70`——`onOptionSelect` 被调 1 次、实参 `[["win-1"]]`，与 Round 4 审阅探针实证完全一致；同文件其余 2 项通过。变异后立即从备份恢复，`diff -q` 核对恢复一致。
  - 绿（新实现下通过）：恢复后 `Select.test.tsx` 3 tests 全过；前端全量 556 passed。拖过测试（`Select.test.tsx:39`）断言三重：`onOptionSelect` 未调、`onValueChange` 未调、两 option 仍在树内（菜单未关），且序列真实触达生产逻辑——pointerdown 落 "none"、pointerup 落从未按下的 "win-1"，win-1 的 per-item `pressedRef` 从未置位；Radix 侧 win-1 的 `pointerTypeRef` 同样仍为初始 `"touch"`，故 Radix 也不提交（源码 `react-select/dist/index.js:983-985`）。
  - 同项按下抬起测试（`Select.test.tsx:77`）真实触达同一生产路径：同项 pointerdown/up 后 `onOptionSelect` 恰 1 次、实参 `"win-1"`；与拖过测试仅落点不同，构成提交边界的正反两面。
  - `pressedRef` 的 `onPointerLeave` 清零（`Select.tsx:126`）与 `onPointerUp` 后的清零均已核对：拖离本项再释放不会误触发；重进同一项后释放时 Radix 侧 `pointerTypeRef` 已由 pointermove 置位、走 `onValueChange` 提交（见下「pointermove 情形」），无守卫丢失。
- t053_test_f007（minor，touch/pen 提交路径无交付测试）：**已消除**，先红后绿证据由审阅员独立变异验证（非采信处置表自述）：
  - 红（onClick 置空后确实失败）：临时把 `Select.tsx:106` 的 `onClick` 置为空操作，恰 2 项失败——Select 级 touch 测试（`Select.test.tsx:135`，spy 0 次、期望 1 次）与 ProfileForm 级 touch 测试（`ProfileForm.test.tsx:524`，选中被延迟到达的默认改写为 `win-1`、期望 `Not configured`）；其余 14 项通过。变异后立即从备份恢复，`diff -q` 核对恢复一致。
  - 绿（新实现下通过）：恢复后两文件 16 tests 全过；前端全量 556 passed。
  - Select 级 touch 测试（`Select.test.tsx:107`）真实覆盖 touch 提交路径：touch pointerdown/up 后断言 `onOptionSelect` 未调（pointerup 为空操作），随后 click 恰触发 1 次、实参 `"__none__"`，且同值选取时 `onValueChange` 未调（守卫是唯一记录）；序列与 Radix 行为一致（touch 靠 click 提交，dist :973-977；trigger 仅 mouse pointerdown 开菜单，dist :293-296 vs :303-305，ProfileForm 级测试按此写 trigger 的 touch pointerdown/up + click 开菜单）。
  - ProfileForm 级 touch 测试（`ProfileForm.test.tsx:444`）与鼠标/键盘测试同构（deferred 查询竞态：touch 选「无」后释放查询仍为「无」），末尾为精确 `.toBe(en.formFontSetNone)`，断言无弱化。
  - 三路提交均有覆盖且互不干扰：鼠标（忠实 pointerdown/up 序列，`ProfileForm.test.tsx:288` + Select 同项测试）、键盘（Enter，`ProfileForm.test.tsx:386`，`fireEvent.keyDown` 不合成 click/pointer 事件）、touch（上述两测试）各自由独立测试覆盖；变异 A 只红拖过测试、变异 B 只红两 touch 测试，互不牵连；其余 Select 调用方均未传 `onOptionSelect`，三路处理器在其上为空操作。
- 表单级拖过测试删除合理性（处置表所述两点均已独立核实，同意删除）：
  - (a) 查询挂起时菜单只有「无」一个选项：`ProfileForm.tsx:199`（`fontSets = fontSetsData?.items ?? EMPTY_FONT_SETS`）→ `fontSetOptions`（`:276-282`）为 `__none__` + 已返回的集；查询挂起时 `fontSetsData` 为 undefined，菜单内无第二项可拖，表单级拖过序列确实不可达。查询到达后默认套用 effect 立即运行（`:243-252`），用户无机会在“默认未套用且两选项并存”的窗口内拖拽。
  - (b) 切平台路径自行复位 ref：平台 Select 的 `onValueChange`（`ProfileForm.tsx:490`）把 `fontSetUserChosenRef.current = false` 并直接按新平台默认集写值，不经过守卫 effect；拖过边界已由 Select 级测试固定，无需表单级重复覆盖。
  - 交付的 `ProfileForm.test.tsx` 仍为 13 tests，无删测试；删除的是未进入交付的尝试性测试写法。
- pointermove 情形（处置表如实说明的两点之二，已用我自己的临时探针独立实测三案；原“约定内、不构成 finding”的判断只覆盖了 A 案，D 案确为新的 minor 缺口，见本轮新发现 f008）：
  - A 案（处置表所述情形）：pointerdown 落 "none"、pointermove 过 "win-1"、pointerup 落 "win-1"，值由 `__none__` 变 `win-1`——探针实测 Radix 提交（`onValueChange=[["win-1"]]`、菜单已关），`onOptionSelect=[]`。该情形在约定内、无影响：提交经 `onValueChange` 到达 ProfileForm（`ProfileForm.tsx:511` 同样把 `fontSetUserChosenRef` 置 true），显式选择已被记录。
  - C 案（press-trigger-drag-release）：pointerdown 按住 trigger 不放、pointermove 过 "None"、pointerup 落在已显示的 "None"——探针实测 `onOptionSelect=[]`、`onValueChange=[]`，且菜单未关（`noneConnected=true`），即 Radix 未提交；无守卫丢失，不构成 finding。C2 案（菜单已开、仅 pointermove + pointerup、无任何 press 落在该项）确会提交且两回调均沉默，但该序列在真实浏览器中不存在（每次 pointerup 之前必有一次 pointerdown；那次 pointerdown 若落在该项则守卫触发、若落在 trigger 则属 C 案不提交），仅作机制注脚。
  - D 案（同值拖过释放，见 f008）：pointerdown 落 "win-1"、pointermove 过 "None"、pointerup 落在已显示的 "None"——探针实测菜单已关（Radix 提交），但 `onOptionSelect=[]` 且 `onValueChange=[]`（同值不调 `onValueChange`）。守卫的触发条件（pointerdown 落在本项）比 Radix 的提交条件（`pointerTypeRef === "mouse"`，pointerdown 或 pointermove 均可置位）窄，同值拖过提交是唯一漏网情形。
- 本轮新发现 f008 的可达性界定：ProfileForm 内 D 案不可达——查询挂起时菜单只有「无」一个选项（`ProfileForm.tsx:199/276-282`），无第二项可按下拖过；查询到达后默认套用 effect 已运行（`defaultFontSetAppliedRef` 守卫，不再重套）。唯一 `onOptionSelect` 调用方即该表单字体集 Select，故 f008 在本仓内无下游后果，定 minor、不阻断 PASS。
- `Select.tsx:24-27` 的 docstring 表述略简（“a pointerup that lands here after a press elsewhere is not a Radix commit”未加 pointermove 限定），但实现注释（`Select.tsx:106-112`）已写明 pointerTypeRef 由“this item's own pointerdown/move”置位；f008 的修复方向应是让守卫判据与 Radix 提交判据对齐（见 f008 建议），不改行为，仅记于此。

### 本轮新发现

1 条（minor）。

### t053_test_f008 - 同值拖过释放提交未被 onOptionSelect 记录（pointermove 置位情形）

- 严重度：minor
- 锚点：AC-011；`Select.tsx` docstring 契约「Fires for every committed option pick」
- 位置：`src/frontend/src/shared/ui/Select.tsx:121-124`（`onPointerUp` 的 `pressedRef.current` 条件）
- 问题：守卫的触发条件（本次 pointerdown 落在本项）比 Radix 自身的提交条件窄。Radix item 的 `pointerTypeRef` 由本项的 pointerdown（dist :987-989）或 pointermove（dist :991-992）置位，pointerup 时为 `"mouse"` 即提交。审阅员临时探针实测 D 案：值已是 `__none__` 时 pointerdown 落 "win-1"、pointermove 过 "None"、pointerup 落 "None"——菜单已关（Radix 已提交），但 `onOptionSelect=[]` 且 `onValueChange=[]`（同值选取不调 `onValueChange`），即一次真实提交完全未被记录。Round 4 的修复在堵住 f006（异值拖过误记）的同时收窄了覆盖：修复前任意 mouse pointerup 都会触发 `onOptionSelect`，D 案本是覆盖的。影响界定：ProfileForm 内不可达——查询挂起时菜单只有「无」一个选项，无第二项可按下拖过；查询到达后默认已套用且不再重套；全仓唯一 `onOptionSelect` 调用方即该表单字体集 Select。故本仓内无下游后果，定 minor。
- 建议：让守卫判据与 Radix 提交判据对齐，例如在组件内为每项镜像一份 Radix 的 `pointerTypeRef`（pointerdown 与 pointermove 均置位、初值 `"touch"`），pointerup 时仅当镜像为 `"mouse"` 才触发 `onOptionSelect`——该判据同时覆盖 D 案与 f006（无移动的拖过：目标项镜像仍为 `"touch"`，不触发）、同项按下抬起与 touch/键盘路径均不受影响；并补一个 D 案 Select 级测试。

## 结论

- 前轮 finding 复核：Round 1 的 5 条与 Round 4 的 2 条 minor 全部已消除，见上（f006/f007 的红绿均由审阅员独立变异运行证实，未采信处置表自述；pointermove 的 A 案实测为约定内无影响，C 案实测不提交，D 案见新发现 f008）。
- 改测方向复核：无「迁就实现」的改测。本轮交付增量为 1 个新文件 `Select.test.tsx`（3 tests）+ `ProfileForm.test.tsx` 新增 1 个 touch 测试 + `Select.tsx` 的 `pressedRef` 守卫，未改动任何既有测试的预期；无删测试。
- 本轮新发现：1 条 minor（f008，同值拖过释放提交未被守卫记录；ProfileForm 内不可达，不阻断）。
- 未进表的提示：
  - Space 键仍只由 Enter 测试覆盖（与 Round 3 结论一致，共用同一分支，无独立分支）。
  - `onPointerLeave` 清零后重进同一项再释放：Radix 经 pointermove 提交、`onValueChange` 兜底记录，见上 pointermove 情形；ProfileForm 内同值重进不可达，见上。
  - `Select.tsx` docstring 关于拖过释放的表述未加 pointermove 限定（见上），行为正确，不进 finding。
  - AC-009 引擎内优先级与 AC-010 仍属环境跳过（`progress.md` 已写明「本机未验证、不得记为已验」并给出用户机补验方法）；链口径按任务指令（t051 AC-013 / t052 AC-012 前例）打勾，见 AC 复验行。
  - 必查项（用户裁定锁死）复核通过：`com.cbrowser.deployment-id` 在 `src/`、`tests/`、`scripts/`、`compose.yaml` 中零命中（grep exit=1）；`resource_prefix` 默认仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/docker_adapter.py:234`），本 diff 未动这两处。
  - 危险模式复扫（本轮增量：`Select.tsx` pressedRef 守卫 + `Select.test.tsx` 3 tests + ProfileForm touch 测试）：无删测试、无 `.skip` / `.only`（仅 `test_t053_fontconfig_locale.py:102` 的 `skipif` 环境门控，本轮实跑中 61 个 t053 测试全部执行、0 skipped）、无恒真/弱化断言（关键选中态断言均为精确 `.toBe` / `toHaveBeenCalledTimes(1)` / `toHaveBeenCalledWith`）、无 mock 被测逻辑（`hasPointerCapture` 补桩仅填 jsdom 环境缺口）、无注释掉的断言、无静默错误抑制、无 `.value =` 替代真实交互、无 `setTimeout` / `waitFor`；`Select.test.tsx` 内无 `toContain` / `toBeTruthy`。
  - 引用逐项核对通过：`progress.md` Round 4 处置表 fix_ref 行号与实际一致（`Select.tsx:106/121/126`、`Select.test.tsx:39/77/107`、`ProfileForm.test.tsx:444`；`Select.tsx:121` 为 `pressedRef.current` 条件行，处置表所标 `:121` 与 `:126` 均准确）；`task.md` 未知契约清单无 `UNVERIFIED` 标记残留。
- 总体判断：f006/f007 修复的测试侧真实可信（独立变异红绿、拖过/同项正反面与 touch 两级覆盖、断言未弱化、三路提交互不干扰）；pointermove 实测挖出 1 条 minor 新发现 f008（同值拖过提交漏记，ProfileForm 内不可达），不阻断；前端全量 556 passed 与基线一致、后端 t053 文件 61 passed。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。默认值三端单测、HTTP 创建默认值集成测试、ProfileForm 提交默认值测试均随本轮重跑通过（后端 t053 文件 61 passed + 前端全量 556 passed）。
- AC-002：TICK-VALID，re_verified。显式 False 存入重载仍为 False、迁移 0007 全量跑通，随本轮后端 t053 文件重跑通过。
- AC-003：TICK-VALID，re_verified。TimezoneCombobox 7 tests 随本轮前端全量通过。
- AC-004：TICK-VALID，re_verified。后端规则矩阵、前规则测试、ProfileForm 联动/手动覆盖/清空保持测试随本轮重跑通过。
- AC-005：TICK-VALID，re_verified。单元与 HTTP 层非法 locale/时区 422 字段级错误测试随本轮后端重跑通过。
- AC-006：TICK-VALID，re_verified。英文 XML 拒绝规则单测 + 宿主 fontconfig 真实 fc-list 实测（合成单目录、macos 集、未绑定回退三情况）随本轮后端重跑通过；真实 Browser 引擎部分按链口径环境跳过（progress.md 已写明本机未验证）。
- AC-007：TICK-VALID，re_verified。zh-CN 无拒绝规则 + fc-list 可见 CJK + fc-match 双集实测随本轮后端重跑通过；确切平台字体名（微软雅黑/宋体/苹方/冬青黑体）待用户机以真实字体集复核，见环境跳过。
- AC-008：TICK-VALID，re_verified。语言修改生成新配置版本（/versions [1, 2]）+ 重启测试（双 Runner、fontconfig 按新语言再生）随本轮后端重跑通过；真实引擎内 navigator.language 仍属环境跳过。
- AC-009：TICK-VALID，re_verified。链路测试（zh-CN/en-US 双参数：locale 与 geoip=True 一并到达引擎启动调用、同一 locale 驱动 fontconfig）随本轮后端重跑通过；task.md 未知契约 #1 已改写为结论、无 UNVERIFIED 标记；引擎内显式 locale 是否优先于 geoip 推断仍属环境跳过（progress.md 已写明本机未验证、用户机补验方法）。
- AC-010：TICK-VALID，trust_prior。[deploy] AC，不要求自动测试；替代验证为部署后人工启动两种语言 Profile（尚未发生，依赖用户机补验，见 progress.md 环境跳过）。
- AC-011：TICK-VALID，re_verified。后端默认集预选/显式 null 保持的 ProfileForm 测试（含鼠标忠实序列、键盘、touch 三路「保持显式无字体集」测试）与 HTTP 集成测试均随本轮重跑通过；拖过释放边界由 Select 级测试固定，见 f006 复核。
- AC-012：TICK-VALID，re_verified。绑定集 fontconfig 失败即 font_set_unavailable 且不启动、未绑定集保持回退的 runner 测试随本轮后端重跑通过。
- AC-013：TICK-VALID，re_verified。重导入修复（删除/篡改）测试与 Coordinator 实时读取测试随本轮后端重跑通过；REST 列表篡改反射由既有集成测试覆盖。
- AC-014：TICK-VALID，re_verified。按 (平台, 集) 计数测试与 manifest 平台不一致标完整性失败测试随本轮后端重跑通过。
- AC-015：TICK-VALID，re_verified。会话详情「探测字体未覆盖」文案测试与篡改文件不进探测缺失测试随本轮后端重跑通过。

coverage = 14 / 15

实跑记录（均为本轮独立复跑，非 implementer 自述）：后端 t053 五文件 61 passed / 0 failed / 0 skipped（`~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=<worktree>/src/backend`，21.32s；本次后端零改动，未重跑后端全量）；前端全量 `npm test`（Node 26.13.0，含 `test:types`）77 files / 556 passed / 0 failed（165.08s），与 Round 4 的 556 一致、无新增失败；变异验证 A：去掉 `pressedRef.current` 条件后 `Select.test.tsx` 1 failed / 2 passed（拖过测试 spy 得 `[["win-1"]]`），恢复后绿；变异验证 B：`onClick` 置空后 `Select.test.tsx` + `ProfileForm.test.tsx` 2 failed / 14 passed（两 touch 测试红），恢复后绿；pointermove 临时探针（我自己的 `__r5_test_pm_c.test.tsx`，跑后即删）：A 案 `onValueChange=[["win-1"]]`、菜单已关、`onOptionSelect=[]`；C 案 `onOptionSelect=[]`、`onValueChange=[]`、菜单未关（未提交）；C2 案菜单已关、两回调均沉默（真实浏览器中不存在的序列）；D 案菜单已关、`onOptionSelect=[]`、`onValueChange=[]`（见 f008）；两次变异均从备份恢复并以 `diff -q` 核对一致，我的探针已删除。注：核对收尾时 `git status` 一度出现并行 Round 5 code 审阅员的同名临时探针（`__r5_scratch_pointermove.test.tsx`，17:45:39 创建、非我创建、内容与我的探针不同），其后由其所有者自行删除；最终 `git status` 仍为 65 条、无残留。
verdict: PASS

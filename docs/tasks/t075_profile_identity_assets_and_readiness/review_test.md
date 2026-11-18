# Task review t075（reviewer_focus: 测试）

- task：`t075_profile_identity_assets_and_readiness`
- spec：`docs/tasks/t075_profile_identity_assets_and_readiness/task.md`
- diff_anchor：`c8737f0df60d146e2f6cf021b4054c8a38a8d5a3`
- target：`git diff c8737f0df60d146e2f6cf021b4054c8a38a8d5a3`
- round：1
- reviewed_at：2026-11-18T10:56:21+08:00

reviewed_scope: e72af9c394c4f887

## Findings

### t075_test_f001 - 实例层字体验证不校验内容哈希，AC-006「内容不符」在挂载层假绿

- 严重度：critical
- 锚点：AC-006（字体挂载内容不符时环境不会被报告为可用）
- 位置：`src/backend/cbrowser/runtime_agent/font_verification.py:136-149`；`tests/unit/test_t075_font_verification.py:38-49`
- 问题：`verify_mounted_font_set` 只校验 manifest 可解析、平台名与逐文件 `is_file()` 存在，全文无 sha256 比对（grep 该文件 `sha256` 零命中）。其测试夹具把 manifest 中每个文件的 sha256 写成假值 `"0" * 64`、文件内容写 `b"font-bytes"`，`test_verified_when_mount_manifest_and_glyphs_agree` 仍断言 `status == "verified"`——即内容被替换/损坏但文件名在，实例层验证照样通过并可被报告就绪。宿主侧 Supervisor 的 `check_font_set` 哈希校验（`tests/unit/test_t041_font_runtime.py` 篡改条）只覆盖挂载前目录，挂载视图与宿主目录不一致时无人发现。实施侧 `progress.md` 称该模块含「逐文件哈希」、blueprint `docs/blueprint/testing.md` 的 AC-006 映射称「内容不符」由 `test_t075_font_verification.py` 覆盖，均与代码不符。
- 建议：在 `verify_mounted_font_set` 内对 manifest 每条记录做 sha256 实算比对（不符返回独立 failure token），并把测试夹具改为真实哈希、新增一条内容篡改用例断言 failed；或明确改为消费 Supervisor 的完整性结论并测试该结论到实例的传递。同步修正 progress/blueprint 的哈希表述。

### t075_test_f002 - AC-007「真实平台中文正确渲染」无任何渲染测试，仅有 fc-list 枚举

- 严重度：important
- 锚点：AC-007（开启中文字体时真实平台中文正确渲染；不能仅以非零像素或缺字框证明中文可用）
- 位置：`tests/unit/test_t075_font_verification.py:161-201`；`tests/unit/test_t075_fontconfig.py:118-143`；`docs/blueprint/testing.md` t075 映射表 AC-007 行
- 问题：与 AC-007 相关的全部自动化证据只有真实 `fc-list` 的语言覆盖枚举（字体自报 zh 覆盖），没有任何字形光栅化、正文/canvas 渲染或截图对照测试；测试策略明确要求「正文、canvas、源端 X11 文字对照，不能用 DOM 文本存在或 CDP 存活冒充渲染通过」，fc-list 元数据比该禁线更弱。blueprint 映射表自认「引擎渲染待 p137」，但 AC-007 不是 `[deploy]` AC、task.md 契约区也没有 AC-009 那样的裁定处置注记，按注记口径打勾无依据。损坏字体（可枚举、不可成形）会全数通过现有测试。
- 建议：要么在云端可执行层补真实渲染验证（真实字体 + fontconfig + 字形渲染对照），要么按 AC-009 同样方式为 AC-007 的渲染部分取得明确处置注记并撤回/限定打勾口径；在此之前该 AC 打勾不成立。

### t075_test_f003 - Runner 与字体验证的接缝无测试：失败分支与 verdict 落盘从未被断言

- 严重度：important
- 锚点：AC-006 / AC-005（验证失败时不启动、就绪结论来自本实例验证）
- 位置：`src/backend/cbrowser/runtime_agent/runner.py:525-567`；`tests/unit/test_egress_plan_and_runner_sdk.py:224-231`；`tests/unit/test_t041_font_runtime.py:315-330`
- 问题：全仓测试中只有 egress 一处引用 `verify_mounted_font_set`，且被 stub 成恒 `verified`（该测试主题是 SDK 启动参数，stub 本身有注释依据）；Agent 健康测试则直接向 `runner_info.json` 写入手工构造的 verdict dict。于是 Runner 的真实接缝——调用真实验证、verdict 非 verified 时写 error 状态并抛 `FontConfigUnavailableError`、不启动浏览器、verified 时把 verdict 写入 runner_info——没有任何一条测试执行过。若接缝回归（如忽略 verdict 照常启动、verdict 未落盘），现有套件全绿无感。
- 建议：补一条 Runner 级测试：以可控的挂载根/字体集夹具（或注入 lister）分别驱动真实 verify 的失败与成功，断言失败时浏览器启动 mock 未被调用且状态为 error、成功时 runner_info 含 verified verdict。

### t075_test_f004 - AC-008 后半句「修改普通配置不清空 Cookie/站点数据/登录会话」无测试

- 严重度：minor
- 锚点：AC-008
- 位置：`tests/unit/test_font_sets_api.py:150-185`（仅断言配置版本递增）
- 问题：AC-008 前半句（可选覆盖缺失与必需失败可区分）在 `test_t075_font_verification.py` 与 t041 健康门禁用例中覆盖充分；但后半句没有任何测试在改配置前后断言 user_data_dir 内容/Cookie/会话存储保持不变，blueprint 映射也只引「配置版本分类」。本 diff 无触碰会话存储的代码路径，故仅记 minor 覆盖缺口。
- 建议：补一条服务层用例：建带 user_data_dir 夹具文件的 Profile，改普通配置后断言目录内容与绑定不变。

### t075_test_f005 - AC-002 的 GPU 身份一致性（同 seed 重启前后 WebGL 实值）无自动化测试

- 严重度：minor
- 锚点：AC-002
- 位置：`docs/spikes/s026_gpu_platform_capability/report.md`；`docs/pending/p137_verify_t075_deploy_ac009_and_gpu_matrix_on_real_stack_locally.md` 第 3 项
- 问题：AC-002 的字体侧（保存/克隆保留绑定、切平台重绑、快照 round-trip）由 `test_t075_profile_identity.py` 真实覆盖，GPU 手选字段/透传 flag 的删除也有请求层拒绝测试；但「同 seed 重启前后 GPU 身份一致」的动态实值部分只靠 s026 源码分析，动态实测已登记 p137。云端无引擎不可执行，属已披露的证据边界，故记 minor，不单独阻断。
- 建议：p137 补验时把 WebGL vendor/renderer 实值与重启一致性结论回填 s026，并在 blueprint 映射中区分「静态已验/动态待验」。

### t075_test_f006 - 被删 t053 真实 fontconfig 用例有三项语义未在新体系下补回

- 严重度：minor
- 锚点：覆盖完整性（删除测试的等价替代核查）
- 位置：`tests/unit/test_t053_fontconfig_locale.py`（整体删除，526 行）；替代文件 `tests/unit/test_t075_fontconfig.py`
- 问题：删除本身有正当理由（locale 驱动语义废止，文件头与 progress 均有说明），且 reject 规则、真实 fc-list 双向可见性、未绑定为空等核心语义已补回。但旧文件的三项真实 fontconfig 覆盖未见替代：① `fc-match` 在 zh 下解析到平台集 中文字体（`test_zh_cn_fc_match_resolves_to_platform_set_chinese_font`）；② macos 集的真实 fc-list 隐藏 CJK（新真实用例只用 windows 目录）；③ 重启后按新配置重新生成 fontconfig（`test_restart_after_locale_change_regenerates_fontconfig`，新语义下对应开关变更后重启）。
- 建议：在 `test_t075_fontconfig.py` 补回三项的新语义版本（开关驱动、双平台各一），或在文件尾注中逐项写明不再需要的原因。

## 结论

- 改测方向复核：逐项核对了 diff 中全部既有测试改动。删除/改写均附新语义说明且未发现「把预期改成迁就当前实现输出」的改测：`test_t053_fontconfig_locale.py` 整体删除（语义废止，见 f006 的替代缺口）、`test_t041_font_runtime.py` 健康三条改为结论驱动（Agent 新契约即读 verdict，喂 verdict dict 是接口层输入而非 mock 被测逻辑）、无绑定启动条改为 fail-closed 并指向新测、ProfileForm 五条字体选择用例随功能删除并在文件尾注记、`test_egress_plan_and_runner_sdk.py` 对 verify 的 stub 有注释且其主题为 SDK 参数（接缝缺口见 f003）。危险模式扫描：无恒真断言、无 `.only`、无删/反转 expect；两处真实 fontconfig 测试的 `pytest.mark.skipif` 为环境守卫，本轮复跑时未跳过（40 条全过）；`test_t075_supervisor_fonts.py:121` 的 `# type: ignore[method-assign]` 仅用于 mock 方法赋值，不掩盖任何断言或行为，经调查不构成 finding。
- 本轮新发现：6 条（critical 1、important 2、minor 3）
- 未进表的提示：① 迁移备份恢复演练（`test_t075_migration.py::test_backup_restore_drill`）只断言 DB 文件回滚，未断言浏览器数据目录未被迁移触碰，建议随手补断言。② 门禁三条负载 flaky 已由本 reviewer 独立单跑复核（不采信实施自述）：`test_t027_release_controller.py::test_instance_identity_parameterized_and_independent` 单跑 passed（5.41s，其门禁失败签名为「cannot determine a single migration head (found 2)」，单跑与 `test_t075_migration.py::test_head_is_0013_and_single` 均证明真实迁移链为单 head，定性并行负载/临时仓污染 flaky，但该签名与本 task 新增迁移同域，建议实施侧留意）、`test_normal_exit_converges_to_desired_stopped_while_container_running` 单跑 passed（16.14s）、frontend `ConfigTab.test.tsx` 单跑 3/3 passed。门禁 unit 失败+错误 16 条 = 15 条既有基线（t063×12、t068×2、a16×1）+ t027 flaky 1 条，与实施侧口径一致。③ 本 reviewer 复跑：`test_t075_*` 五文件 40 passed；`test_t041_font_runtime.py` + `test_font_sets_api.py` + `test_fontconfig.py` + `test_t053_font_sets_chain.py` 37 passed。
- 总体判断：实例层字体验证不校验内容哈希（f001）使 AC-006 的「内容不符」打勾假绿，AC-007 的真实渲染部分无测试支撑（f002），且 Runner 验证接缝无测试（f003）；存在未解决 critical/important，FAIL。
- 系统性 follow-up：无（f001/f002/f003 均为本 task 范围内修复项；真实渲染与 GPU 动态实测的本地补验已有 p137 承接）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本 reviewer 复跑 `test_t075_profile_identity.py` 12 条全过（创建绑平台默认集、无集失败、请求拒绝手选字段、CJK 默认随语言），前端 ProfileForm 的 CJK 开关对齐/手动保持用例在门禁 frontend_test 中通过。
- AC-002：TICK-VALID，re_verified。复跑身份用例证保存/克隆保留已验证绑定、切平台重绑、无集切平台失败且原配置不变、快照 round-trip；GPU 动态一致性部分依赖 s026 源码结论与 p137（见 f005 minor）。
- AC-003：TICK-VALID，re_verified。领域层二值+默认 light+拒绝第三态、identity round-trip 回显 dark、迁移 no-preference/null 收敛 light 均复跑通过；引擎 dark 媒体查询为 spec 上下文已验证基础事实，实测复核在 p137 第 4 项。
- AC-004：TICK-VALID，re_verified。复跑 `test_t075_migration.py` 7 条全过：真实 SQLite+alembic 改写行与快照、nvidia/悬空绑定/无集未绑定三种阻塞均在改写前失败且零写入、幂等、文件级备份恢复、单 head 断言。
- AC-005：TICK-VALID，re_verified。复跑 `test_t075_supervisor_fonts.py`（精确只读 subpath 挂载、源不存在 fail-closed、非法身份拒绝、未绑定 core 拒绝启动）与 t041 挂载/篡改条全过；真实 Docker 挂载链属 AC-009/p137 范围。
- AC-006：TICK-VOID，re_verified。挂载空/manifest 损坏/平台不符/过滤后为空/CJK 必需缺失均有真实用例且复跑通过，但「内容不符」在实例层不校验哈希、测试以假 sha256 断言 verified（f001），且 Runner 接缝无测试（f003），打勾不成立。
- AC-007：TICK-VOID，re_verified。复跑真实 fc-list 用例仅证明语言覆盖枚举与开关过滤，无任何字形渲染验证，与 AC 明示的证明标准不符，blueprint 自认渲染待 p137（f002）。
- AC-008：TICK-VALID，re_verified。复跑 font_verification 与 t041 健康用例：missing_optional 与 failure token 分离、failed/无 verdict 时 ready=False、verified 时 ready=True 均真实断言；后半句 Cookie/会话保留无测试，记 f004 minor 不推翻本条。
- AC-009：TICK-VALID，trust_prior。按 2026-11-18 用户裁定处置注记口径：云端可做部分（挂载构造、验证、就绪门禁）已由上述复跑支撑，真实容器化双平台渲染验证依赖 pending p137 本地补验，未独立复验。

coverage = 8 / 9

verdict: FAIL

## Round 2 (2026-11-18T19:40:21+08:00)

- round：2
- reviewed_at：2026-11-18T19:40:21+08:00

reviewed_scope: 86817c96d31d703c

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核（以 diff 与代码/测试为准，不采信处置表自称）：
    - t075_test_f001（critical，实例层不校验内容哈希）：已消除。`src/backend/cbrowser/runtime_agent/font_verification.py:144-160` 的 `_check_manifest_files` 对 manifest 每条记录流式实算 sha256，不符返回新 token `font_content_mismatch`（`font_verification.py:48`）；夹具哈希改为真实值 `hashlib.sha256(b"font-bytes").hexdigest()`（`tests/unit/test_t075_font_verification.py:38`），不再是 Round 1 的 `"0" * 64`；新增 `test_tampered_content_fails`（同名异字节 → `font_content_mismatch`）与真实字体端到端 `test_real_tampered_font_fails_end_to_end`（替换 Noto CJK 字节后在任何列举/渲染前失败）。本 reviewer 复跑 `test_t075_font_verification.py` 全过。
    - t075_test_f002（important，AC-007 无真实渲染测试）：已消除（云端可做部分）。新模块 `src/backend/cbrowser/runtime_agent/glyph_render.py` 用系统 FreeType 光栅化中/文/字三字，要求字形索引非零、有墨、位图与本字体 `.notdef` 不同（`glyph_render.py:124-151`）；`tests/unit/test_t075_glyph_render.py` 7 条全过且具判别力：真 CJK 字体三字形各异有墨、`prove_cjk_render` 接受 CJK 字体而拒绝 Latin-only 字体（DejaVu 的中映射为字形 0 且位图等同 `.notdef`）、不可读字体抛 `GlyphRenderError` 而非通过、缺 FreeType 报 `GlyphRenderUnavailable`；`test_t075_font_verification.py::test_real_fc_list_end_to_end` 走默认 prover 真实渲染。AC-007 的 task.md 处置注记（2026-11-18 用户裁定）与本轮 diff 一致：Chrome 引擎内渲染延期 p137，不表示已实测通过；云端 FreeType 证明部分已由上述测试真实覆盖。
    - t075_test_f003（important，Runner 验证接缝无测试）：已消除。新文件 `tests/unit/test_t075_runner_fonts.py` 2 条：真实 `import_font_set` 建集 + 真实 `prepare_profile_fontconfig` + 真实 `verify_mounted_font_set`（真实 fc-list、sha256、FreeType）；成功路径断言浏览器启动、verified verdict 写入 `runner_info.json`、状态 running；篡改路径断言抛 `FontConfigUnavailableError`、启动 mock 未被 await、状态 error/`font_set_unavailable`、无 `runner_info.json`、`font_verification` 为 None。生产代码 `src/backend/cbrowser/runtime_agent/runner.py:548-567` 与断言一致（verdict 非 verified 即写 error 状态并抛错，`FONT_SET_UNAVAILABLE = "font_set_unavailable"`，`fontconfig.py:42`）。mock 只落在环境边界（浏览器启动、显示、CDP、urlopen），被测接缝本身全程真实。
    - t075_test_f004（minor，AC-008 后半句无测试）：已消除。新增 `tests/unit/test_t075_profile_identity.py::test_ordinary_config_change_keeps_user_data_and_binding`（第 228 行起）：改 `color_scheme` 后 `Cookies` 与 `Login Data` 字节不变、绑定不变、版本递增为 2。
    - t075_test_f005（minor，GPU 身份动态实值无自动化测试）：仍存在，未修，但为 minor，不阻断。动态 WebGL 实值与重启一致性仍只靠 s026 源码结论并登记 p137；本轮 diff 未新增相关测试。留待 p137 本地补验时回填。
    - t075_test_f006（minor，被删 t053 三项语义未补回）：已消除。`tests/unit/test_t075_fontconfig.py` 新增三条新语义版本：`test_real_fc_match_zh_resolves_to_platform_cjk_font`（`:lang=zh-cn` 开时解析到平台中文字体、关时不解析，注释写明不用裸 `zh` 的原因）、`test_real_macos_set_hides_cjk_when_switch_off`（macos 路径双向可见性）、`test_restart_after_switch_change_regenerates_fontconfig`（同 run 目录开关变更后文件被重写而非复用）。
- 改测方向复核：无。本轮修复均为加法（新模块、新测试文件、新用例）；diff 中既有测试的改动与 Round 1 审查时一致，未发现把预期改成迁就当前实现输出的改测。迁移 0013 快照扫描（code f001 对应）新增 4 条快照用例（`tests/unit/test_t075_migration.py:328-442`：快照强制 GPU、悬空绑定、损坏 JSON、无平台集未绑定均在改写前阻塞且版本仍为 0012），生产代码 `src/backend/migrations/versions/0013_profile_identity.py:83-130` 的 `_blocking_entries` 确实扫描 `profile_config_versions` 全表。
- 危险模式扫描：本轮无新增命中。无恒真断言、无 `.only`/`.skip`、无删/反转 expect；三处 `pytest.mark.skipif` 均为环境守卫（fc-list/ fixture 字体/FreeType 缺失时跳过），本轮复跑 61 条全过、0 跳过；唯一新增的 `# type: ignore[method-assign]`（`tests/unit/test_t075_supervisor_fonts.py:136`）仅用于 mock 方法赋值，与 Round 1 已调查通过的同类用法一致，不掩盖断言。`test_t075_font_verification.py` 的假文件用例把 `glyph_prover` stub 为恒真，但该接缝是生产代码的正式注入参数，且默认 prover 由真实端到端用例与 glyph 测试覆盖，不构成 mock 被测逻辑。`test_t075_runner_fonts.py` 的 mock 只落在启动/显示/CDP 等环境边界。`test_real_fc_list_end_to_end` 的 `effective_fonts >= min_faces` 是字体面数的合理下界，不是弱化断言。
- 本轮新发现：0 条
- 未进表的提示：① Round 1 结论提示的备份演练缺口已顺带修好：`test_t075_migration.py::test_backup_restore_drill` 现把 profile 的 `user_data_dir` 指向含 `Cookies` 哨兵的目录，升级后与恢复后均断言哨兵字节不变。② `test_t075_runner_fonts.py` 的 `_FakeContext.pages` 为类级可变默认值，仅测试替身内部使用，无跨用例污染。③ f005（GPU 动态实值）仍待 p137。
- 总体判断：前轮 critical/important 已全部由真实代码与测试消除，本轮无新 blocker；AC-006 与 AC-007 的打勾现均有真实测试支撑，PASS。
- 系统性 follow-up：无（f005 的动态实测已有 p137 承接）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本 reviewer 复跑 `test_t075_profile_identity.py` 全过：创建绑平台默认集、无集失败、请求拒绝手选字段、CJK 默认随语言。
- AC-002：TICK-VALID，re_verified。复跑身份用例证保存/克隆保留已验证绑定、切平台重绑、无集切平台失败且原配置不变、快照 round-trip；GPU 动态一致性部分依赖 s026 源码结论与 p137（f005 minor 未修，不推翻本条）。
- AC-003：TICK-VALID，re_verified。领域层二值+默认 light+拒绝第三态、identity round-trip 回显 dark、迁移 no-preference/null 收敛 light 均复跑通过。
- AC-004：TICK-VALID，re_verified。复跑 `test_t075_migration.py` 全过：真实 SQLite+alembic 改写行与快照、三类 live 阻塞与四类快照阻塞均在改写前失败且零写入、幂等、备份恢复演练现含用户数据哨兵断言、单 head 断言。
- AC-005：TICK-VALID，re_verified。复跑 `test_t075_supervisor_fonts.py`（精确只读 subpath 挂载、源不存在 fail-closed、非法身份拒绝、未绑定 core 拒绝启动）与 Runner 成功/篡改双路径全过。
- AC-006：TICK-VALID，re_verified。Round 1 的 VOID 原因已消除：实例层逐文件 sha256 实算（假哈希夹具已改真实值），篡改用例分假文件与真实字体两层均断言 `font_content_mismatch`，Runner 接缝双路径已覆盖；本轮复跑 61 条全过。
- AC-007：TICK-VALID，re_verified。FreeType 逐字光栅化证明（字形索引非零、有墨、与 `.notdef` 位图不同）7 条全过且具判别力，真实端到端验证走默认 prover；Chrome 引擎内渲染部分按 2026-11-18 用户裁定处置注记延期至 p137，该部分不在本条云端复验范围内。
- AC-008：TICK-VALID，re_verified。复跑 font_verification 与 t041 健康用例：missing_optional 与 failure token 分离、failed/无 verdict 时 ready=False、verified 时 ready=True；普通配置变更后用户数据目录字节不变的新用例已复跑通过（f004 已消除）。
- AC-009：TICK-VALID，trust_prior。按 2026-11-18 用户裁定处置注记口径：云端可做部分（挂载构造、验证、就绪门禁）已由上述复跑支撑，真实容器化双平台渲染验证依赖 pending p137 本地补验，未独立复验。

coverage = 8 / 9

verdict: PASS

## Round 3 (2026-11-18T19:50:39+08:00)

- round：3
- reviewed_at：2026-11-18T19:50:39+08:00

reviewed_scope: 382b23dcfe742f47

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核（以 diff 与代码/测试为准，不采信处置表自称）：
    - t075_test_f001（critical，实例层不校验内容哈希）：仍已消除。`src/backend/cbrowser/runtime_agent/font_verification.py:137` 的 `_check_manifest_files` 仍逐文件流式实算 sha256，不符返回 `font_content_mismatch`；夹具仍为真实哈希；`tests/unit/test_t075_font_verification.py:138` `test_tampered_content_fails` 与 `:260` `test_real_tampered_font_fails_end_to_end` 均在本轮 61 条重跑中通过。本轮唯一改动（`_optional_coverage` 抽取）不触碰该路径。
    - t075_test_f002（important，AC-007 无真实渲染测试）：仍已消除（云端可做部分）。`src/backend/cbrowser/runtime_agent/glyph_render.py` 与 `tests/unit/test_t075_glyph_render.py` 7 条未改动，本轮重跑全过；AC-007 处置注记（2026-11-18 用户裁定，Chrome 引擎内渲染延期 p137）与 task.md 一致。
    - t075_test_f003（important，Runner 验证接缝无测试）：仍已消除。`tests/unit/test_t075_runner_fonts.py` 2 条（成功/篡改双路径）未改动，本轮重跑全过；`src/backend/cbrowser/runtime_agent/runner.py` 接缝代码未改动。
    - t075_test_f004（minor，AC-008 后半句无测试）：仍已消除。`tests/unit/test_t075_profile_identity.py::test_ordinary_config_change_keeps_user_data_and_binding` 本轮重跑通过（13 条文件全过）。
    - t075_test_f005（minor，GPU 身份动态实值无自动化测试）：仍存在，未修，但为 minor，不阻断。动态 WebGL 实值与重启一致性仍只靠 s026 源码结论并登记 p137；本轮 diff 未新增相关测试。留待 p137 本地补验时回填。
    - t075_test_f006（minor，被删 t053 三项语义未补回）：仍已消除。`tests/unit/test_t075_fontconfig.py` 补回的三条新语义用例（fc-match 解析、macos 双向可见性、开关变更后重启重生成）本轮重跑全过（10 条文件全过）。
- 本轮重点复核（`_optional_coverage` 抽取，无行为回归）：`src/backend/cbrowser/runtime_agent/font_verification.py:248` 的 `_optional_coverage(manifest, platform)` 与 Round 2 代码轴 f004 描述的原内联逻辑逐项一致：`carried = {entry["name"] for entry in manifest["files"]}`，再对 `PLATFORM_DETECTION_LABELS.get(platform, ())` 各 label 的 `DETECTION_FONTS` 取 `sorted` 集合差（`if name not in carried`）。调用点唯一，在 `verify_mounted_font_set` 的 verified 返回分支（`:239-243`），传入同一 `(manifest, platform)`；全部失败路径仍经 `_failed` 返回 `missing_optional=[]`，与抽取前一致。调用前置不变：`_load_manifest` 已保证 `manifest["files"]` 为非空 dict 列表且每条含非空 `name`，helper 无新增 KeyError 面。直接测试证据：`tests/unit/test_t075_font_verification.py:100` `test_verified_when_mount_manifest_and_glyphs_agree` 在 verdict 层断言 `"calibri.ttf" in verdict["missing_optional"]` 且 `"arial.ttf" not in verdict["missing_optional"]`（`:108-109`），即 helper 经公开入口被真实断言，本轮通过。另以 mtime 核实改动范围：自 Round 2 审阅时刻（19:40）起，唯一改动的源码文件是 `font_verification.py`（11:43 UTC），全部 7 个 t075 测试文件 mtime 均早于该时刻，未被触碰。
- 改测方向复核：无。本轮无任何测试文件改动；唯一生产代码改动为纯重构抽取，各失败 token 与测试断言均未变。
- 危险模式扫描：本轮无新增命中。无恒真断言、无 `.only`/`.skip`、无删/反转 expect；四处 `pytest.mark.skipif` 均为 Round 2 已调查通过的环境守卫（fc-list/ fixture 字体/FreeType 缺失时跳过），本轮复跑 61 条全过、0 跳过。`test_t075_font_verification.py` 假文件用例的 `glyph_prover` stub 仍为正式注入参数的接缝替身，默认 prover 由真实端到端用例与 glyph 测试覆盖，复核结论与 Round 2 一致。
- 本轮新发现：0 条
- 未进表的提示：① f005（GPU 动态实值）仍待 p137；② 本 reviewer 复跑：t075 七文件 61 passed（189.60s），其中与抽取直接相关的 `test_t075_font_verification.py`（14）+ `test_t075_glyph_render.py`（7）+ `test_t075_runner_fonts.py`（2）共 23 条全过，与实施侧口径一致；未跑全量门禁。
- 总体判断：前轮 critical/important 仍全部消除，本轮唯一改动为语义不变的纯重构抽取且有 verdict 层测试直接覆盖，无新 blocker；PASS。
- 系统性 follow-up：无（f005 的动态实测已有 p137 承接）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本 reviewer 复跑 `test_t075_profile_identity.py` 全过：创建绑平台默认集、无集失败、请求拒绝手选字段、CJK 默认随语言。
- AC-002：TICK-VALID，re_verified。复跑身份用例证保存/克隆保留已验证绑定、切平台重绑、无集切平台失败且原配置不变、快照 round-trip；GPU 动态一致性部分依赖 s026 源码结论与 p137（f005 minor 未修，不推翻本条）。
- AC-003：TICK-VALID，re_verified。领域层二值+默认 light+拒绝第三态、identity round-trip 回显 dark、迁移 no-preference/null 收敛 light 均复跑通过。
- AC-004：TICK-VALID，re_verified。复跑 `test_t075_migration.py` 全过：真实 SQLite+alembic 改写行与快照、三类 live 阻塞与四类快照阻塞均在改写前失败且零写入、幂等、备份恢复演练含用户数据哨兵断言、单 head 断言。
- AC-005：TICK-VALID，re_verified。复跑 `test_t075_supervisor_fonts.py`（精确只读 subpath 挂载、源不存在 fail-closed、非法身份拒绝、未绑定 core 拒绝启动）与 Runner 成功/篡改双路径全过。
- AC-006：TICK-VALID，re_verified。实例层逐文件 sha256 实算与篡改用例（假文件与真实字体两层）均复跑通过；本轮抽取不触碰内容校验路径，`missing_optional` 的 verified 分支语义由 `test_verified_when_mount_manifest_and_glyphs_agree` 直接断言。
- AC-007：TICK-VALID，re_verified。FreeType 逐字光栅化证明（字形索引非零、有墨、与 `.notdef` 位图不同）7 条全过且具判别力，真实端到端验证走默认 prover；Chrome 引擎内渲染部分按 2026-11-18 用户裁定处置注记延期至 p137，该部分不在本条云端复验范围内。
- AC-008：TICK-VALID，re_verified。复跑 font_verification 与 t041 健康用例：missing_optional 与 failure token 分离、failed/无 verdict 时 ready=False、verified 时 ready=True；普通配置变更后用户数据目录字节不变的新用例已复跑通过；`_optional_coverage` 抽取后 verified 分支的 missing_optional 语义经上述用例直接复验。
- AC-009：TICK-VALID，trust_prior。按 2026-11-18 用户裁定处置注记口径：云端可做部分（挂载构造、验证、就绪门禁）已由上述复跑支撑，真实容器化双平台渲染验证依赖 pending p137 本地补验，未独立复验。

coverage = 8 / 9

verdict: PASS

## Round 4 (2026-11-18T20:04:58+08:00)

- round：4
- reviewed_at：2026-11-18T20:04:58+08:00

reviewed_scope: 8f37c34486db496e

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核（以 diff 与代码/测试为准，不采信处置表自称）：
    - t075_test_f001（critical，实例层不校验内容哈希）：仍已消除。`src/backend/cbrowser/runtime_agent/font_verification.py` 的 `_check_manifest_files` 仍逐文件流式实算 sha256，不符返回 `font_content_mismatch`；夹具仍为真实哈希；`tests/unit/test_t075_font_verification.py` 的 `test_tampered_content_fails` 与 `test_real_tampered_font_fails_end_to_end` 本轮 61 条重跑中通过。自 Round 3（19:50:39）起该文件 mtime 未变（2026-11-18 11:43 UTC），未被触碰。
    - t075_test_f002（important，AC-007 无真实渲染测试）：仍已消除（云端可做部分）。`src/backend/cbrowser/runtime_agent/glyph_render.py` 与 `tests/unit/test_t075_glyph_render.py` 7 条未改动，本轮重跑全过；AC-007 处置注记（2026-11-18 用户裁定，Chrome 引擎内渲染延期 p137）与 task.md 一致；`docs/blueprint/testing.md:379` 的 AC-007 映射行重排后语义不变（FreeType 光栅化证明 + 引擎渲染待 p137）。
    - t075_test_f003（important，Runner 验证接缝无测试）：仍已消除。`tests/unit/test_t075_runner_fonts.py` 2 条（成功/篡改双路径）未改动，本轮重跑全过；`src/backend/cbrowser/runtime_agent/runner.py` 接缝代码未改动。
    - t075_test_f004（minor，AC-008 后半句无测试）：仍已消除。`tests/unit/test_t075_profile_identity.py::test_ordinary_config_change_keeps_user_data_and_binding` 本轮重跑通过。
    - t075_test_f005（minor，GPU 身份动态实值无自动化测试）：仍存在，未修，但为 minor，不阻断。动态 WebGL 实值与重启一致性仍只靠 s026 源码结论并登记 p137；本轮 diff 未新增相关测试。留待 p137 本地补验时回填。
    - t075_test_f006（minor，被删 t053 三项语义未补回）：仍已消除。`tests/unit/test_t075_fontconfig.py` 补回的三条新语义用例本轮重跑全过。
- 本轮重点复核（自 Round 3 起仅 Markdown 格式化重排，无代码/测试/契约改动）：以 mtime 核实改动范围——自 Round 3 审阅时刻（19:50:39+08:00）起，改动的文件只有交付文档 `docs/blueprint/decisions/20261118_profile_identity_readiness.md`、`docs/blueprint/testing.md`（md_kx 断行重排，mtime 2026-11-18 11:55 UTC）与流程文件 `progress.md` / `review_code.md` / `review_test.md` / `docs/pending/p137_verify_t075_deploy_ac009_and_gpu_matrix_on_real_stack_locally.md`；全部 7 个 t075 测试文件与全部 `src/` 文件 mtime 均早于该时刻，未被触碰。两份交付文档相对锚点的 diff 为纯新增（102 insertions，0 deletions），重排后内容与 Round 3 记录的语义逐项一致：`docs/blueprint/testing.md:367-381` 的 AC-001~009 映射表仍写逐文件 sha256 复核（AC-006）、FreeType 光栅化证明且引擎渲染待 p137（AC-007）、AC-009 云端不可验顺延 p137；ADR 040 仍为字体绑定后端托管、CJK 显式开关、GPU 手选取消、单一就绪事实四项决策。指纹由 `task.py review-status` 同源函数重算为 `8f37c34486db496e`，与 Round 3 的 `382b23dcfe742f47` 不同，仅因上述文档换行变化。
- 改测方向复核：无。本轮无任何测试文件改动。
- 危险模式扫描：本轮无新增命中。`tests/unit/test_t075_*.py` 全量 grep：无恒真断言、无 `.only`/`.skip`、无删/反转 expect；四处 `pytest.mark.skipif` 均为 Round 2 已调查通过的环境守卫，本轮复跑 61 条全过、0 跳过；唯一 `# type: ignore[method-assign]`（`tests/unit/test_t075_supervisor_fonts.py:136`）仍为 Round 1 已调查通过的 mock 方法赋值用法，不掩盖断言。
- 本轮新发现：0 条
- 未进表的提示：① f005（GPU 动态实值）仍待 p137；② 本 reviewer 复跑：t075 七文件 61 passed（211.15s，0 跳过），与实施侧口径一致；未跑全量门禁。
- 总体判断：前轮 critical/important 仍全部消除，本轮自 Round 3 起的唯一变化为文档断行重排且语义不变，测试与行为无变化，无新 blocker；PASS。
- 系统性 follow-up：无（f005 的动态实测已有 p137 承接）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本 reviewer 复跑 `test_t075_profile_identity.py` 全过：创建绑平台默认集、无集失败、请求拒绝手选字段、CJK 默认随语言；自 Round 3 起相关代码与测试未改动。
- AC-002：TICK-VALID，re_verified。复跑身份用例证保存/克隆保留已验证绑定、切平台重绑、无集切平台失败且原配置不变、快照 round-trip；GPU 动态一致性部分依赖 s026 源码结论与 p137（f005 minor 未修，不推翻本条）。
- AC-003：TICK-VALID，re_verified。领域层二值+默认 light+拒绝第三态、identity round-trip 回显 dark、迁移 no-preference/null 收敛 light 均复跑通过。
- AC-004：TICK-VALID，re_verified。复跑 `test_t075_migration.py` 全过：真实 SQLite+alembic 改写行与快照、三类 live 阻塞与四类快照阻塞均在改写前失败且零写入、幂等、备份恢复演练含用户数据哨兵断言、单 head 断言。
- AC-005：TICK-VALID，re_verified。复跑 `test_t075_supervisor_fonts.py`（精确只读 subpath 挂载、源不存在 fail-closed、非法身份拒绝、未绑定 core 拒绝启动）与 Runner 成功/篡改双路径全过。
- AC-006：TICK-VALID，re_verified。实例层逐文件 sha256 实算与篡改用例（假文件与真实字体两层）均复跑通过；本轮仅文档重排，不触碰内容校验路径。
- AC-007：TICK-VALID，re_verified。FreeType 逐字光栅化证明（字形索引非零、有墨、与 `.notdef` 位图不同）7 条全过且具判别力，真实端到端验证走默认 prover；Chrome 引擎内渲染部分按 2026-11-18 用户裁定处置注记延期至 p137，该部分不在本条云端复验范围内。
- AC-008：TICK-VALID，re_verified。复跑 font_verification 与 t041 健康用例：missing_optional 与 failure token 分离、failed/无 verdict 时 ready=False、verified 时 ready=True；普通配置变更后用户数据目录字节不变的新用例已复跑通过。
- AC-009：TICK-VALID，trust_prior。按 2026-11-18 用户裁定处置注记口径：云端可做部分（挂载构造、验证、就绪门禁）已由上述复跑支撑，真实容器化双平台渲染验证依赖 pending p137 本地补验，未独立复验。

coverage = 8 / 9

verdict: PASS

## Round 5 (2026-11-18T20:15:16+08:00)

- round：5
- reviewed_at：2026-11-18T20:15:16+08:00

reviewed_scope: 6ae64bcb28c76d56

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核（以 diff 与代码/测试为准，不采信处置表自称）：
    - t075_test_f001（critical，实例层不校验内容哈希）：仍已消除。`src/backend/cbrowser/runtime_agent/font_verification.py:138-156` 的 `_check_manifest_files` 仍逐文件流式实算 sha256，不符返回 `FAILURE_CONTENT_MISMATCH`；夹具仍为真实哈希；`tests/unit/test_t075_font_verification.py` 的 `test_tampered_content_fails` 与 `test_real_tampered_font_fails_end_to_end` 本轮 61 条重跑中通过。自 Round 4（20:04:58）起该文件 mtime 未变（2026-11-18 11:43 UTC），未被触碰。
    - t075_test_f002（important，AC-007 无真实渲染测试）：仍已消除（云端可做部分）。`src/backend/cbrowser/runtime_agent/glyph_render.py` 与 `tests/unit/test_t075_glyph_render.py` 7 条未改动，本轮重跑全过；AC-007 处置注记（2026-11-18 用户裁定，Chrome 引擎内渲染延期 p137）与 task.md 一致。
    - t075_test_f003（important，Runner 验证接缝无测试）：仍已消除。`tests/unit/test_t075_runner_fonts.py` 2 条（成功/篡改双路径）未改动，本轮重跑全过；`src/backend/cbrowser/runtime_agent/runner.py` 接缝代码未改动。
    - t075_test_f004（minor，AC-008 后半句无测试）：仍已消除。`tests/unit/test_t075_profile_identity.py::test_ordinary_config_change_keeps_user_data_and_binding` 本轮重跑通过。
    - t075_test_f005（minor，GPU 身份动态实值无自动化测试）：仍存在，未修，但为 minor，不阻断。动态 WebGL 实值与重启一致性仍只靠 s026 源码结论并登记 p137；本轮 diff 未新增相关测试。留待 p137 本地补验时回填。
    - t075_test_f006（minor，被删 t053 三项语义未补回）：仍已消除。`tests/unit/test_t075_fontconfig.py` 补回的三条新语义用例本轮重跑全过。
- 本轮重点复核（自 Round 4 起仅 ADR 040 第 57 行措辞修正，处置 Round 4 代码轴新发现的 minor f005）：以 mtime 核实改动范围——自 Round 4 审阅时刻（20:04:58+08:00，即 12:04:58 UTC）起，改动的交付文件只有 `docs/blueprint/decisions/20261118_profile_identity_readiness.md`（mtime 2026-11-18 12:06:47 UTC）；`progress.md` 同期亦有改动（12:07:06 UTC），属指纹排除的流程文件，不计入审查范围；全部 7 个 t075 测试文件与全部 `src/` 文件 mtime 均早于该时刻，未被触碰。ADR 第 57 行现写「逐文件 sha256 内容哈希相符（manifest 不含文件大小字段，故本层不做大小比对）」，措辞与实现一致：`src/backend/cbrowser/runtime_agent/font_verification.py:131-133` 的 manifest 校验只要求每条含非空 `name` 与 `sha256`，`_check_manifest_files`（`:138-156`）只做存在性与流式 sha256 比对；`manifest.py` 与 `font_verification.py` 全文 grep `size` 零命中，确无大小字段、无大小比对。该行纯文档措辞，无代码、无测试、无契约改动，不影响任何 AC 的测试支撑。指纹经同源函数（`repo_task.monitoring.review_scope_fingerprint`）重算为 `6ae64bcb28c76d56`，与本 prompt 注入值一致（`task.py review-status` CLI 本轮因超时被 SIGTERM 中断未出结果，改以 gate venv 直接调用同源函数重算成功）。
- 改测方向复核：无。本轮无任何测试文件改动。
- 危险模式扫描：本轮无新增命中。`tests/unit/test_t075_*.py` 全量 grep：无恒真断言、无 `.only`/`.skip`、无删/反转 expect；四处 `pytest.mark.skipif` 均为 Round 2 已调查通过的环境守卫，本轮复跑 61 条全过、0 跳过；唯一 `# type: ignore[method-assign]`（`tests/unit/test_t075_supervisor_fonts.py:136`）仍为 Round 1 已调查通过的 mock 方法赋值用法，不掩盖断言。
- 本轮新发现：0 条
- 未进表的提示：① f005（GPU 动态实值）仍待 p137；② 本 reviewer 复跑：t075 七文件 61 passed（213.80s，0 跳过），与实施侧口径一致；未跑全量门禁。
- 总体判断：前轮 critical/important 仍全部消除，本轮自 Round 4 起的唯一交付改动为 ADR 一行措辞修正且与实现逐字相符，测试与行为无变化，无新 blocker；PASS。
- 系统性 follow-up：无（f005 的动态实测已有 p137 承接）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本 reviewer 复跑 `test_t075_profile_identity.py` 全过：创建绑平台默认集、无集失败、请求拒绝手选字段、CJK 默认随语言；自 Round 4 起相关代码与测试未改动。
- AC-002：TICK-VALID，re_verified。复跑身份用例证保存/克隆保留已验证绑定、切平台重绑、无集切平台失败且原配置不变、快照 round-trip；GPU 动态一致性部分依赖 s026 源码结论与 p137（f005 minor 未修，不推翻本条）。
- AC-003：TICK-VALID，re_verified。领域层二值+默认 light+拒绝第三态、identity round-trip 回显 dark、迁移 no-preference/null 收敛 light 均复跑通过。
- AC-004：TICK-VALID，re_verified。复跑 `test_t075_migration.py` 全过：真实 SQLite+alembic 改写行与快照、三类 live 阻塞与四类快照阻塞均在改写前失败且零写入、幂等、备份恢复演练含用户数据哨兵断言、单 head 断言。
- AC-005：TICK-VALID，re_verified。复跑 `test_t075_supervisor_fonts.py`（精确只读 subpath 挂载、源不存在 fail-closed、非法身份拒绝、未绑定 core 拒绝启动）与 Runner 成功/篡改双路径全过。
- AC-006：TICK-VALID，re_verified。实例层逐文件 sha256 实算与篡改用例（假文件与真实字体两层）均复跑通过；本轮 ADR 措辞修正与该实现逐字相符（manifest 无大小字段、不做大小比对），不触碰内容校验路径。
- AC-007：TICK-VALID，re_verified。FreeType 逐字光栅化证明（字形索引非零、有墨、与 `.notdef` 位图不同）7 条全过且具判别力，真实端到端验证走默认 prover；Chrome 引擎内渲染部分按 2026-11-18 用户裁定处置注记延期至 p137，该部分不在本条云端复验范围内。
- AC-008：TICK-VALID，re_verified。复跑 font_verification 与 t041 健康用例：missing_optional 与 failure token 分离、failed/无 verdict 时 ready=False、verified 时 ready=True；普通配置变更后用户数据目录字节不变的新用例已复跑通过。
- AC-009：TICK-VALID，trust_prior。按 2026-11-18 用户裁定处置注记口径：云端可做部分（挂载构造、验证、就绪门禁）已由上述复跑支撑，真实容器化双平台渲染验证依赖 pending p137 本地补验，未独立复验。

coverage = 8 / 9

verdict: PASS

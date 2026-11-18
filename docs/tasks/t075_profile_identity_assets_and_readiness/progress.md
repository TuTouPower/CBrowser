---
tid: "t075"
slug: "profile_identity_assets_and_readiness"
title: "环境运行身份、字体资产与真实就绪契约统一"
status: "done"
branch: "t075_profile_identity_assets_and_readiness"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "c8737f0df60d146e2f6cf021b4054c8a38a8d5a3"
spec_source_sha: "c8737f0df60d146e2f6cf021b4054c8a38a8d5a3"
depends_on: "t081"
conflicts_with: "t076,t078,t079"
note: "用户已授权13项todo聚合立项、commit与push；只创建backlog，不实施。; 2026-11-18本批协调：消费t080/t081受管存储与字体目录，原AC保留；本次资源立项不包含实施或发布。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 创建授权：2026-11-18T00:00:06+08:00，用户要求全部todo按已讨论架构聚合为少量task并commit/push；来源为p116、p124、p125。本条仅登记创建事实，未实施、未验证业务AC。

- 关联spec：docs/specs/fingerprint_platform.md、docs/specs/profile_management.md、docs/specs/runtime_lifecycle.md、docs/specs/release_deployment.md、docs/specs/ui_design_system.md；执行收尾时登记本tid并同步新契约，保留旧task历史。

- 本批协调：2026-11-18T00:31:35+08:00，用户授权资源根因详细立项；字体路径实现改为消费 t080/t081 受管卷/目录，新增 t081 前置依赖，原行为 AC 保留。新增依赖与冲突只经 task.py 更新；本批未实施、未验证业务结果。

- 实施启动（2026-11-18，cloud-muse-20261118）：run-begin 完成（attempt 1，base c8737f0），preflight PASS（1 条 spike 警告已按下方处置）。

- GPU spike 已建 `docs/spikes/s026_gpu_platform_capability`：SDK 0.6.4 源码核实 GPU 身份由引擎按 seed+平台派生、`--fingerprint-gpu-vendor` 无校验透传；冻结矩阵仅两平台引擎自动派生，动态实测并入 p137。task.md 未知契约清单已回填结论。

- [deploy] AC-009 处置：已在 task.md 契约区写注记，本地补验登记为 p137（含 AC-009、CJK 开关、GPU 矩阵动态实测、配色实测、迁移演练五项）。

- 实施计划（新契约形状）：① 领域：ProfileConfig/创建/更新模型删除 `gpu_family`、删除手选 `font_set_id` 入参（绑定改为后端按平台从 t081 目录解析并持久化）、`color_scheme` 收敛为 `light|dark` 默认 `light`、新增 `include_cjk_fonts`（创建未给定时按语言派生：zh→true、en→false）；无可用平台字体集时创建失败。② DB：迁移 0013（新列 include_cjk_fonts、删 gpu_family、color_scheme 回填 light 并收紧非空）+ 快照 JSON 同步改写；改写前守卫先行：gpu_family 为 nvidia/intel、绑定悬空/未验证、无可用默认集的 null 绑定 → 抛阻塞清单不写任何数据；备份/恢复以 DB 文件级备份演练（测试覆盖）。③ Supervisor：字体挂载改由 volume_spec 边界按 MountPlanner.fonts_root 构造精确只读挂载并校验源存在，删 docker_adapter 深层 CBROWSER_FONTS_DIR 读取；\_validate_font_set 对 null 绑定改为 fail-closed。④ Runtime：fontconfig 改按 include_cjk_fonts 生成 reject 规则、删除 locale 驱动与基础字体回退（无绑定 fail-closed）；Runner 启动前校验实际挂载集（manifest/平台/文件齐全/过滤后必需字形非空），结论写入实例运行记录，Agent /health 以该结论门禁 ready 并区分必需失败与可选覆盖缺失。⑤ 前端：ProfileForm 删除字体包与 GPU 选择、配色仅 light/dark、新增中文字体开关；删 profile_locale 的 selectFontSetForLocaleAndPlatform。⑥ OpenAPI 导出与前端生成类型同步；spec/blueprint finalization。

- 切片 1 领域+服务+仓储完成：新测 `test_t075_profile_identity.py` 12/12（请求拒绝已删字段、配色二值、CJK 派生、创建绑默认集/无集失败、克隆保留已验证绑定、切平台重绑/无集失败不变、身份 round-trip 含快照断言）。

- 切片 2 迁移 0013（revision `d75a0013f001` 接 `c81f0a11b001`）完成：先守卫后写、行+快照同步改写、幂等、备份恢复演练，新测 `test_t075_migration.py` 7/7。

- 切片 3 运行时字体链完成：`runtime_agent/font_verification.py` 新建（manifest/平台/逐文件哈希 + 真实 fc-list 枚举，失败 token 化，可选覆盖与必需失败分离）；fontconfig 改开关驱动并删基础回退；Runner 启动前验证并把结论写 `runner_info.font_verification`，不合格写 error 状态后抛错；Agent 删 `_font_runtime` 逐请求重扫、health 改读结论并门禁 ready；coordinator 未绑定改 (None, [])。新测 `test_t075_fontconfig.py` + `test_t075_font_verification.py` 17/17（含宿主真实 fc-list 双向可见性）。

- 切片 4 Supervisor 完成：`volume_spec.font_set_mount` 源存在校验 + 精确只读 subpath 挂载，docker_adapter 内联深层读 env 的旧块替换为该构造；core `_validate_font_set` 未绑定改 fail-closed。新测 `test_t075_supervisor_fonts.py` 4/4。

- 存量测试处置（旧语义废止，按 TDD 规则整体改写/删除并注明）：`test_t053_fontconfig_locale.py` 整体删除（locale 裁剪语义废止，替代覆盖在 test_t075_fontconfig.py）；`test_t053_font_sets_chain.py` A16 两条改写为托管绑定语义；`test_t041_font_runtime.py` 健康三条改结论驱动、新增 ready 门禁一条、absent 启动分支改 fail-closed 指向新测、runtime 响应 marker 条改写为无标记语义；`test_fontconfig.py` 基础回退条改写为白名单为空；前端 ProfileForm.test.tsx 五条字体选择用例整体删除（理由记于文件尾注）、对齐用例改写为 CJK 开关语义并新增手动保持用例，ProfileForm.t058.test.tsx 夹具更新到新响应形状、时区联动期望补 include_cjk_fonts（语言联动字段）。

- 切片 5 前端完成：ProfileForm 删字体包/GPU 选择与 useFontSetsQuery、配色二值、CJK 开关（未手动时随语言派生）；profile_locale 删 selectFontSetForLocaleAndPlatform/isCjkFontSet、加 defaultIncludeCjkForLocale；i18n 删 formGpu\*/formColorNoPreference/formFontSetMissing/formFontSetInconsistent、加 formIncludeCjk（en/zh）；OpenAPI 双 schema 重新导出、前端生成类型与 profile_field_classification 重新生成（include_cjk_fonts 为 runtime 字段）。前端全量 vitest 693/693、tsc -b 干净。

- finalization 完成：specs 五份（fingerprint_platform / profile_management / runtime_lifecycle / release_deployment / ui_design_system）同步 tasks 清单与新契约表述，browser_isolation 一并修订回退口径；blueprint architecture / browser_runtime / domain / supervisor / testing 同步，新增 ADR 040（decisions/20261118_profile_identity_readiness.md）；s026 结论抽取为 findings d051，spikes.py complete s026。

- 创建失败口径细化（门禁实测后定界）：门禁 run_gates.sh 刻意 unset CBROWSER_FONTS_DIR、26 个集成文件在无字体根环境建 Profile，「无集即创建失败」若无条件适用将整体击穿集成套件。定界为：字体根已配置（一切真实部署）而平台无 verified 集 → 创建/切平台写入前失败（AC-005 的「合法部署下」口径，FontSetCatalogService.root_configured 判定）；未配置字体根的进程创建可暂无绑定，Supervisor/Runner 仍一律失败封闭、永不就绪。spec/ADR 040 已同步此口径；test_supervisor_start_capacity 改为携带真实夹具绑定启动（其被测的端口耗尽行为不变）。

- 修复一处 dict patch 落库缺陷（实测发现）：service.update_profile 对 dict patch 的平台重绑只改了校验用 patch_dict、未传到 repo，API 路径（ProfileConfig）不受影响但服务契约不一致；已改为 dict patch 以富化后的 patch_dict 落库。同时 test_t075_profile_identity 的双平台夹具字体内容原本相同、set_id 相同，重绑断言空转，已改为按平台区分内容使断言真实。

- 门禁第二轮 fallout 处置（unit 9 条 + integration 1 条 + 前端 test:types 23 条，均为新契约的预期连带，非基线）：① test_control_migration 两条旧库夹具被 0013 守卫拦截——与 test_t056 同款处置，跑到 head 前先 upgrade 到 0012 并播种绑定一条 verified 集；② 7 条启动类测试（a3 端口生命周期、infrastructure gateway 选址、recovery 控制面、selkies token、t035 代理 ×2、egress Runner）原以无绑定 config 启动、被失败封闭拦截——unit conftest 新增共享 `fixture_font_set` fixture（真实导入的 windows 集 + CBROWSER_FONTS_DIR 指向），各测试给被测 config 携带夹具绑定，被测行为不变；其中 a3 的 releases_port 条此前因字体失败先于端口分配而空转通过，一并修正为真实走到网络失败路径；egress Runner 测试按其既有打桩方式在 runner 模块 seam 补 verify stub（真实验证由 test_t075_font_verification 与 t041 ready 门禁覆盖）；③ integration test_font_sets_api 的 explicit-null 条改写为托管绑定语义（发送 font_set_id 得 422、不发送则绑定平台默认集）；④ 前端 test:types 23 条：19 个测试文件的 ProfileResponse 夹具删 gpu_family、color_scheme: null 改 "light"、补 include_cjk_fonts: false，useProfilesQuery 工厂同款处理，ProfileForm.test.tsx 删未用 act 导入并把 mock.calls 直取改写为 toHaveBeenCalledWith 否定断言。定向复跑：unit 相关 7 文件 67 passed、integration test_font_sets_api 7 passed、tsc -p tsconfig.test.json 归零。

- 门禁第二轮 integration 另有 6 条「isolated API process did not become ready」（test_normal_exit_replay ×4、test_supervisor_manual_retry、test_supervisor_observation_authority）：与 t083 门禁及前端 vitest 并行抢占 1.5 核时 API 子进程（含迁移到 head）在 fixture 的 10 秒就绪窗口内未起来；负载消退后单跑 test_normal_exit_converges 5.17s 通过，定性为负载 flaky、非本 task 回归，最终门禁在 flock 串行下复核。

- Round 1 审阅修复（2026-11-18，AC 已撤勾）：① font_verification 重写为逐文件 sha256 实算比对（缺 sha256 即 manifest 无效；token `font_content_mismatch`），并按 code f004 拆为 `_load_manifest` / `_check_manifest_files` / `_assess_effective_fonts` / `_prove_cjk_render`；② 新建 `runtime_agent/glyph_render.py`，ctypes 直调系统 FreeType 零新依赖，`prove_cjk_render` 对中/文/字要求字形索引非零、有墨、位图哈希 ≠ `.notdef`，结构体布局经实测钉死（FT_BBox 为 4×FT_Pos；`glyph` 字段在 `underline_thickness` 之后、`size` 之前；upm 校验 0\<upm≤16384；位图上限 1_000_000 字节），NotoSansCJK 的三字字形分别为 9544/20035/15364 且位图互不相同、DejaVu 的中映射到字形 0 且位图与 `.notdef` 同哈希，探针能区分；③ 新建 `test_t075_runner_fonts.py`（Runner 与真实验证接缝）；④ 迁移 0013 的阻塞清单纳入快照扫描；⑤ fontconfig 补回被删 t053 三项语义（fc-match 用 `:lang=zh-cn`，裸 `zh` 在 fontconfig 下不作超集匹配）；⑥ API lifespan 加字体根未配置告警（code f003）；⑦ AC-007 在 task.md 写处置注记，Chrome 引擎内渲染延期 p137。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

Round 1（2026-11-18，指纹 `e72af9c394c4f887`）：代码轴 PASS（4 minor），测试轴 FAIL（1 critical + 2 important + 3 minor）。审阅 FAIL 后 9 条 AC 已全部撤勾，修复重验后才重勾重审。Round 2（指纹 `86817c96d31d703c`）：双轴 PASS，0 新 finding；代码轴复核 code f004 修不彻底（主函数手算 CC 仍约 17），已按建议再抽 helper 降至 14，该改动触发 Round 3 重审。

|finding_id|status|fix_ref|处置说明|
|---|---|---|---|
|t075_test_f001|已修||`runtime_agent/font_verification.py` 重写为逐文件 sha256 实算比对（manifest 缺 sha256 视为 manifest 无效，新 token `font_content_mismatch`）；夹具改真实 sha256，新增篡改内容用例与真实字体端到端篡改用例（`test_tampered_content_fails`、`test_real_tampered_font_fails_end_to_end`），`test_t075_font_verification.py` + `test_t075_glyph_render.py` 共 21 passed|
|t075_test_f002|已修||云端部分：新建 `runtime_agent/glyph_render.py`（ctypes 直调系统 FreeType，零新依赖）对中/文/字三字做真实光栅化证明（字形索引非零、有墨、位图哈希 ≠ 本字体 `.notdef`），接入 `verify_mounted_font_set`（CJK 开时逐个中文面尝试直至证明成功；新 token `font_cjk_render_failed` / `font_render_unavailable`，库缺失不静默跳过），新测 `test_t075_glyph_render.py` 7/7；Chrome 引擎内渲染在 task.md AC-007 下写处置注记延期 p137|
|t075_test_f003|已修||新建 `tests/unit/test_t075_runner_fonts.py` 2/2：真实字体导入打补丁的挂载根，Runner 跑真实 fontconfig 生成 + 真实验证（fc-list、sha256、FreeType 渲染证明）；成功路径断言浏览器启动被调用、runner_info.json 含 verified verdict、状态 running；篡改路径断言抛 `FontConfigUnavailableError`、启动 mock 未调用、状态 error 且 exit_reason=`font_set_unavailable`、无 runner_info.json、font_verification 为 None|
|t075_test_f004|已修||`test_t075_profile_identity.py` 新增 `test_ordinary_config_change_keeps_user_data_and_binding`：建 Profile 后在 user_data_dir 放 Cookies / Login Data 哨兵文件，改普通配置（color_scheme light→dark）后断言目录字节不变、绑定不变、配置版本 +1；该文件 13/13|
|t075_test_f005|遗留|p137|GPU 身份动态实测（同 seed 重启前后 WebGL 实值一致性）云端无引擎不可做；blueprint testing.md 的 AC-002 映射行已区分静态已验与动态待验；p137 补验时把 WebGL 实值与重启一致性结论回填 s026|
|t075_test_f006|已修||`test_t075_fontconfig.py` 按新语义补回三项：① zh-cn 下 fc-match 解析到平台集中文字体（实测发现 fontconfig 对裸 `zh` 不作超集匹配——Noto 的 lang 列表只有 zh-cn/zh-tw 等，裸 zh 会误命中 DejaVu；故用 `:lang=zh-cn`，与被删旧测试名 zh_cn 一致）；② macos 集真实 fc-list 隐藏 CJK；③ 开关变更后重启重新生成 fontconfig；该文件 10/10|
|t075_code_f001|已修||`0013_profile_identity.py` 的 `_blocking_entries` 现扫描 `profile_config_versions`（损坏 JSON、非对象、强制 GPU、悬空绑定、未绑定且平台无默认集各记一条，带 snapshot id 与 profile id），docstring 同步；`test_t075_migration.py` 新增 4 条快照阻塞用例与备份演练的浏览器数据断言（升级与恢复后哨兵文件字节不变），迁移族（t075_migration + t056 + t054 + test_control_migration）32 passed|
|t075_code_f002|已修||选「改表述」一侧。manifest 条目只有 sha256、无 size 字段，故 `docs/blueprint/browser_runtime.md` 与 `docs/specs/fingerprint_platform.md` 的「逐文件哈希与大小」改为只称逐文件 sha256 内容哈希，并补 FreeType 渲染证明句；progress.md 切片 3 原本只写「逐文件哈希」无大小，表述本就准确。testing.md 的 AC-006/AC-007 映射行同步为真实哈希 + 渲染证明 + Runner 接缝测试|
|t075_code_f003|已修||选「启动路径告警」一侧。`api/app.py` lifespan 在 `font_catalog.root_configured()` 为假时写一条 loud warning（生产部署恒设 CBROWSER_FONTS_DIR；未配置进程的豁免口径仍在 ADR 040 与 task.md 契约区）；不硬拒——集成测试的 supervisor_api fixture 不设该变量，硬拒会击穿集成套件|
|t075_code_f004|已修||先拆为 `_load_manifest`、`_check_manifest_files`、`_assess_effective_fonts`、`_prove_cjk_render` 四个小函数；Round 2 代码审阅复核认为主函数手算仍约 17（未落到 15 以下），遂按审阅建议再把可选覆盖计算抽为 `_optional_coverage` helper，主函数手算 CC 降至 14；各失败 token 与现有测试断言保持不变，`test_t075_font_verification.py` + `test_t075_glyph_render.py` + `test_t075_runner_fonts.py` 共 23 passed。此改动在 Round 2 指纹落盘后发生，须走 Round 3 重审|
|t075_code_f005|已修||Round 4 新发现（minor）：ADR 040 第 57 行仍称 Runner 验证「逐文件哈希/大小相符」，系 Round 2 修 code f002 时漏改 ADR 040 的残留。已改为「逐文件 sha256 内容哈希相符（manifest 不含文件大小字段，故本层不做大小比对）」，与 browser_runtime.md:65 与 fingerprint_platform.md 的已修正表述一致；纯文档措辞，AC-006 行为无缺口。此改动在 Round 4 指纹落盘后发生，须走 Round 5 重审|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：云端实施完成，9 条 AC 全部打勾；AC-009 按 2026-11-18 用户裁定打勾（云端可做部分完成），真实部署验证延期 p137 本地补验。
- 测试：全量门禁最终轮证据 `~/workspace/cloud-task-logs/gate-t075-final3/`（总日志 `gate-t075-final3.log`，2026-11-18 11:20 起跑，约 13 分钟）：protocol_drift_check / requirements_check / design_lint / design_check / contract（389 条，388 passed + 1 skipped）/ frontend_build 均 exit 0；unit 2414 条，失败+错误 15 条＝15 条既有基线（t063×12、t068×2、a16 协议漂移×1），t027 本轮未失败；integration 228 条，6 failed + 2 errors（209 passed、7 skipped），8 条隔离复跑全部通过（8 passed、3 skipped，串行 + TMPDIR 指持久盘，80.77s），定性为负载 flaky：其中 2 条错误在门禁日志中实证为 `OSError: [Errno 28] No space left on device`（/tmp 512M tmpfs 在 unit 与 frontend_test 并行时被占满），其余 6 条为并行负载下时序敏感的浏览器链/速率限制用例，final2 同代码下 0 失败，且均不在本 task 改动路径上；frontend_test 692/693，唯一失败仍是 ConfigTab 保存回显用例 5000ms 超时（本轮 5508ms，前轮 6205ms），单跑仅 1123ms，属并行负载下 5 倍放慢的超时 flake，非回归；test:types（tsc -p tsconfig.test.json）已归零。p136 登记的 t078 并发 flaky 本轮未出现。
- 黑盒：云端无 Docker/真实引擎，真实容器化编排与双平台渲染验证（AC-009、GPU 矩阵动态实测、CJK 开关实测、配色实测、身份迁移演练）整体登记 p137 本地补验，未用 mock/历史结果代替。
- review：Round 1 双轴审阅（指纹 `e72af9c394c4f887`）代码轴 PASS、测试轴 FAIL，10 条 finding 已全部处置（见上方 Review 处置表）；Round 2（指纹 `86817c96d31d703c`）双轴 PASS、0 新 finding，唯 code f004 复核为修不彻底；按建议抽 `_optional_coverage` helper 后主函数 CC 降至 14，Round 3（指纹 `382b23dcfe742f47`）双轴 PASS、0 新 finding，f004 彻底消除；finish 门禁 md_format 重排文档换行后 Round 4（指纹 `8f37c34486db496e`）双轴 PASS，代码轴新发现 minor f005（ADR 040 大小措辞残留），已修正一行措辞；Round 5（指纹 `6ae64bcb28c76d56`）双轴 PASS、0 新 finding，f005 消除。`task.py review-status`：overall=PASS、round=5、code_verdict=PASS、test_verdict=PASS、review_scope=ok、ac_review=ok；代码轴 coverage 7/9、测试轴 8/9（trust_prior 均在 30% 内）；唯一遗留为 test f005（GPU 动态实值，minor，p137）。
- AC 判定：见 `task.md` 行内打勾，9/9。

### 结果摘要

- 身份契约统一：ProfileConfig 删除 gpu_family 与用户可写 font_set_id，color_scheme 收敛 light/dark（默认 light），新增 include_cjk_fonts（未给定时按语言派生）；font_set_id 改为后端托管绑定（创建/切平台时按平台从 t081 目录解析默认集），字体根已配置而平台无 verified 集时创建/切平台在写入前失败，未配置字体根的进程仍可暂无绑定但 Supervisor/Runner 一律失败封闭。
- GPU 身份：spike s026 证实引擎按 seed+平台自动派生、SDK 无 GPU 控制面，冻结矩阵仅 (windows|macos, 引擎自动派生)；删除 Runner 的 --fingerprint-gpu-vendor 拼接，结论沉淀 findings d051 与 ADR 040。
- 迁移 0013（d75a0013f001）：先守卫后写——旧 gpu nvidia/intel、绑定非本平台 verified 集、未绑定且平台无 verified 集任一存在即列全清单零写入失败；回填配色、CJK 按旧有效暴露派生、未绑定行绑平台默认集、快照 JSON 同步改写；幂等，downgrade 拒绝，恢复口径为 DB 文件级备份整体还原。
- 真实就绪链：Supervisor volume_spec.font_set_mount 源目录不存在即拒绝（防 daemon 建空目录）；Runner 启动前在真实挂载上 verify_mounted_font_set（manifest/平台/内容哈希/过滤后有效字体/CJK 能力策略，missing_optional 与必需失败分离），失败写 error 状态（FONT_SET_UNAVAILABLE）且不启动浏览器；Agent health 改读本实例验证结论，ready 含 font_ok；删除基础字体回退与逐请求重扫。
- 前端：ProfileForm 删字体包/GPU 选择、配色二值、CJK 开关随语言派生（手动后保持）；OpenAPI 双 schema、生成类型与字段分类重新生成。

### 长期文档闭环

- specs 六份已同步新契约（fingerprint_platform、profile_management、runtime_lifecycle、release_deployment、ui_design_system、browser_isolation）；blueprint architecture/browser_runtime/domain/supervisor/testing 已同步，testing.md 含 t075 AC 映射表；新增 ADR 040（docs/blueprint/decisions/20261118_profile_identity_readiness.md）；s026 spike completed，结论抽取为 findings d051；AC-009 等真实栈补验登记 docs/pending/p137。

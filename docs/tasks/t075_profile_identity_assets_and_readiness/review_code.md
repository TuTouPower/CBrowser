# Task review t075（reviewer_focus: 代码）

- task：`t075_profile_identity_assets_and_readiness`
- spec：`docs/tasks/t075_profile_identity_assets_and_readiness/task.md`
- diff_anchor：`c8737f0df60d146e2f6cf021b4054c8a38a8d5a3`
- target：`git diff c8737f0df60d146e2f6cf021b4054c8a38a8d5a3`
- round：1
- reviewed_at：2026-11-18T18:54:12+08:00

reviewed_scope: e72af9c394c4f887

## Findings

### t075_code_f001 - 迁移的阻塞清单只扫 profiles 表，历史快照的不可等价项被静默改写或原样留置

- 严重度：minor
- 锚点：AC-004（快照侧与 profiles 侧处置不一致）
- 位置：`src/backend/migrations/versions/0013_profile_identity.py:78`、`src/backend/migrations/versions/0013_profile_identity.py:118`
- 问题：`_blocking_entries` 只遍历 `profiles` 表计算阻塞项；`_rewrite_snapshots` 对快照无条件 `data.pop("gpu_family", None)`（第 129 行，快照里存有 `nvidia`/`intel` 也不进阻塞清单）、快照未绑定且其平台无 verified 默认集时静默保持未绑定（第 141-144 行附近的 `if platform in defaults` 无 else）、快照 JSON 损坏时 `continue` 静默跳过（第 124-128 行）。失败场景：某 Profile 当前行已是 windows 且绑定正常，但其历史版本快照是 macos 未绑定且库中无 macos verified 集——迁移成功，该快照仍未绑定，日后按该版本恢复/读取即得到无绑定配置（靠 Supervisor 启动失败封闭兜底，不会误启动）。profiles 侧同类情形会整体阻塞并给清单，快照侧口径不一致。定为 minor 的理由：实时身份（profiles 行）的阻塞/改写前零写入已被 `tests/unit/test_t075_migration.py` 的 forced-gpu、dangling、unbound 三个阻塞用例证实（本人重跑通过），快照 gpu 键删除是迁移 docstring 明示的统一改形，快照残留边缘不影响实时配置正确性。
- 建议：把快照纳入阻塞计算：快照含强制 GPU 值、绑定未 verified、未绑定且平台无默认集、JSON 损坏四类各记一条阻塞项，与 profiles 清单合并后在写入前统一抛出；或在迁移 docstring 与 blueprint 中明确快照侧的豁免口径，消除口径分叉。

### t075_code_f002 - blueprint 与收尾记录称 Runner 验证含「逐文件哈希与大小」，实际只查文件存在

- 严重度：minor
- 锚点：行为缺陷（文档与实现不一致）+ AC-006 周边口径
- 位置：`src/backend/cbrowser/runtime_agent/font_verification.py:138`、`docs/blueprint/browser_runtime.md:65`
- 问题：`verify_mounted_font_set` 对 manifest 文件只做 `(set_dir / name).is_file()` 存在性检查，不比对 manifest 内的 sha256/size；而 `docs/blueprint/browser_runtime.md:65` 与 `docs/tasks/t075_profile_identity_assets_and_readiness/progress.md` 切片 3 均写 Runner 层「核对 manifest、平台、逐文件哈希与大小」。系统级内容完整性实际由 Supervisor 启动前 `check_font_set`（`src/backend/cbrowser/font_sets/manifest.py` 的 sha256 逐文件比对，经 `src/backend/cbrowser/supervisor/core.py:2958` 调用）覆盖，故 AC-006 的「内容不符不报告可用」在整链上成立；但长期真相文档把校验层级写错，后续维护者可能据此误以为容器内挂载另有独立哈希复核（例如在 Supervisor 检查与 Runner 启动之间被替换的同名文件不会被 Runner 层发现）。
- 建议：二选一并保持一致——或在 `verify_mounted_font_set` 中按 manifest 的 sha256/size 真做逐文件校验（与其模块 docstring 的「checks the mount the instance received」定位相符），或把 blueprint 与 progress 的表述改为「Runner 核对 manifest/平台/文件存在与过滤后有效字体，逐文件哈希由 Supervisor 启动前校验」。

### t075_code_f003 - 未配置字体根的进程创建/切平台可产生无绑定 Profile，与 AC-005 字面口径有张力

- 严重度：minor
- 锚点：AC-005（创建失败口径的进程级豁免）
- 位置：`src/backend/cbrowser/services/profile_service.py:515`、`src/backend/cbrowser/services/profile_service.py:625`
- 问题：`create_profile` 在 `font_catalog().root_configured()` 为假时跳过默认集绑定与校验、直接以未绑定状态落库；`update_profile` 平台切换在同一条件下把绑定置 None 落库。AC-005 字面要求「字体源不存在时创建环境失败」。缓解事实：该豁免已写入 ADR `docs/blueprint/decisions/20261118_profile_identity_readiness.md`（真实部署经 deploy.sh 恒配置字体根、不可达），且未绑定 Profile 在 Supervisor（`src/backend/cbrowser/supervisor/core.py` 未绑定即 `FontSetUnavailableError`）与 Runner（`font_binding_missing` 失败封闭）两层都无法启动或就绪，不会产生「创建空目录而成功启动」。定为 minor 是因豁免的不可达性依赖部署脚本恒设环境变量这一仓外事实，代码本身没有第二道防线（如启动时断言 API 进程必有字体根）。
- 建议：维持豁免时，在 API 进程启动路径加一条显式断言/告警（生产 profile 下字体根未配置即拒绝启动或高声告警），把「真实部署不可达」从约定变成代码可验证的事实；或在 task 契约区补记该豁免口径。

### t075_code_f004 - verify_mounted_font_set 圈复杂度约 17，新函数一上来即超简化阈值

- 严重度：minor
- 锚点：行为缺陷（可维护性；复杂度本身未产出可观测缺陷，不 blocking）
- 位置：`src/backend/cbrowser/runtime_agent/font_verification.py:98`
- 问题：手算近似 McCabe：基数 1，叠加绑定缺失、挂载缺失、manifest 读取异常、非 dict、平台不符（`and` 短路）、files 非法（`or` 短路）、逐项 entry 校验循环与条件、lister 异常、空集、CJK 开/关两条复合条件等分支约 16 个，CC ≈ 17 ≥ 15，且为本 task 新建函数。当前分支与失败 token 一一对应、测试覆盖各失败路径，未发现漏处理分支，故仅记 minor。
- 建议：拆为「manifest 解析与结构校验」「过滤后能力判定」「可选覆盖计算」三个小函数，主函数只做编排；拆分后各失败 token 与现有测试断言保持不变。

## 结论

- 本轮新发现：4 条（critical 0、important 0、minor 4）
- 未进表的提示：
    - 文件过大（降级规则，只列示）：`src/backend/cbrowser/services/profile_service.py` 1825 行、`src/backend/cbrowser/runtime_agent/runner.py` 1112 行，均超实现源码 800 行 important 阈值且本 task 仍有净增（分别约 +57、+30 行）；未见由体量直接导致的行为不一致，故不进 finding 表。`src/frontend/src/features/profiles/ProfileForm.tsx` 现 817 行但本 task 净减少约 200 行，不满足「仍净增」条件，不列示。
    - `src/backend/cbrowser/runtime_agent/font_verification.py` 对 manifest 平台字段缺失时放行（字段为 None 不判 mismatch），严于它的 Supervisor 层要求平台严格相等；生产链路由 Supervisor 先行把关，仅作口径提示。
    - `duplicate_profile` 直调 repository 创建、克隆不重验绑定有效性——属既有模式且正合 AC-002「克隆保持绑定身份」，仅提示：源绑定在克隆前失效时克隆体会带出悬空绑定，启动层仍失败封闭。
    - 门禁证据独立核对（`~/workspace/cloud-task-logs/gate-t075-final2/`，仓外证据目录）：unit junit 共 2393 条、失败+错误 16 条，逐条比对为 t063×12、t068×2、a16×1 老基线与 t027 `test_instance_identity_parameterized_and_independent` 1 条；后者本人单跑复核 2 passed。integration 唯一 error 为 `test_normal_exit_converges_to_desired_stopped_while_container_running`（隔离 API 进程未就绪，负载型），frontend 唯一失败为 ConfigTab 保存回显用例 5000ms 超时（负载型）；三者与实施侧背景一致且均非本 task 语义。本人另重跑 t075 五个新测试文件 40/40 passed、字体相关旧套件（t041/fontconfig/font_sets_api/t053 链/domain/migration 等）72/72 passed。
    - 安全/契约面已扫：字体挂载改由 `supervisor/volume_spec.py` 的 `font_set_mount` 在边界构造（平台白名单 + set_id 正则全匹配 + 源目录存在性校验 + 只读），旧深层环境变量读取已删；OpenAPI 与生成类型同步删除 `gpu_family`、收敛 `color_scheme`、新增 `include_cjk_fonts`（protocol_drift_check 与 contract 套件在门禁中 passed）；无 secret 落盘、无吞错新增（Runner 验证失败写 error 状态后抛 `FontConfigUnavailableError`）。
- 总体判断：实现层完整兑现 AC-001–AC-009 的云端可做部分，无未解决 critical / important，仅 4 条 minor；PASS。
- 系统性 follow-up：无（AC-009 与 AC-007 的真实引擎渲染验证、s026 GPU 动态实测已由 pending p137 登记跟踪，不重复立项）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。领域模型以平台+语言+独立 `include_cjk_fonts` 取代手选字体包（`src/backend/cbrowser/domain/models.py`、`src/backend/cbrowser/api/v1/router.py:302` 按 locale 派生默认、前端 `ProfileForm.tsx` 同步开关），本人重跑 `tests/unit/test_t075_profile_identity.py` 全过。
- AC-002：TICK-VALID，re_verified。`gpu_family` 与 `--fingerprint-gpu-vendor` 透传已全仓删除（grep 仅剩迁移与 baseline 历史文件），GPU 身份只由持久 seed+平台派生；克隆保留源配置、切平台重绑定或写入前失败（`src/backend/cbrowser/services/profile_service.py:616` 起），相关用例随 t075 套件重跑通过；双平台多 seed 的引擎动态实测属 p137 本地补验，不属代码层缺口。
- AC-003：TICK-VALID，re_verified。`color_scheme` 在领域/DB/OpenAPI/前端四层收敛为 `Literal["light","dark"]` 默认 light，Runner 以 `color_scheme=cfg.color_scheme` 传固定引擎（`src/backend/cbrowser/runtime_agent/runner.py:660`），后台主题为独立设置未与该字段耦合。
- AC-004：TICK-VALID，re_verified。本人重跑 `tests/unit/test_t075_migration.py` 7 条全过：profiles 阻塞前零写入、幂等、备份恢复演练、快照随行改写均有实测；快照侧阻塞口径分叉记 f001（minor，不推翻打勾）。
- AC-005：TICK-VALID，re_verified。`font_set_mount` 对缺失源目录抛 `PathSecurityError` 而非建空挂载，创建时字体根已配置而平台无 verified 集即失败、Supervisor 对未绑定拒绝启动；本人重跑 `tests/unit/test_t075_supervisor_fonts.py` 通过；未配置字体根的进程级豁免记 f003（minor）。
- AC-006：TICK-VALID，re_verified。挂载空/manifest 损坏/平台不符/文件缺失/过滤后空集/CJK 能力不符各有稳定失败 token，Runner 失败封闭不启动、Agent 以 verdict 门禁 ready（`src/backend/cbrowser/runtime_agent/agent.py` 的 `ready` 合取 `font_ok`）；本人重跑 `tests/unit/test_t075_font_verification.py`、`test_t075_fontconfig.py` 通过，内容哈希由 Supervisor `check_font_set` 覆盖（见 f002）。
- AC-007：TICK-VALID，trust_prior。代码层已复验：fontconfig 按开关生成 reject 规则、验证层以真实 fc-list 的 zh 语言覆盖判开/关双向（随 t075 套件重跑通过）；但「开启时真实平台中文正确渲染」的引擎渲染证据云端不可执行，已登记 p137 本地补验，此项依赖实施侧在 progress/blueprint 中记录的延期安排，未冒充实测。
- AC-008：TICK-VALID，re_verified。健康结果中可选覆盖缺口（`missing_fonts`/`missing_optional`）与必需失败（`font_verification.failure` + ready=false）字段分离，Runner 失败另写 error 状态；配置更新路径（repository update 仅写配置列）不触碰 user_data_dir，Cookie/会话存储不在改写面内。
- AC-009：TICK-VALID，trust_prior。按契约区 2026-11-18 用户裁定处置注记：云端可做部分（受管挂载构造、实例级字体验证、就绪门禁、错误挂载失败封闭）已实现并经单元层复验，真实容器化双平台渲染验证延期 pending p137 本地补验，本行依赖该注记口径，不表示已实测通过。

coverage = 7 / 9

verdict: PASS

## Round 2 (2026-11-18T19:42:17+08:00)

reviewed_scope: 86817c96d31d703c

- 本轮指纹核对：`task.py review-status` 在写报告前显示 `review_scope=stale`（对照 Round 1 指纹 `e72af9c394c4f887`）；本人用 `repo_task.monitoring.review_scope_fingerprint` 对当前 worktree 重算，结果与任务给定的 `86817c96d31d703c` 一致。未跟踪文件只剩两份审阅报告本身（流程文件，指纹排除），无 reviewer 看不到的交付物。
- 本轮独立复验：用门禁 venv（`.scratch/gate_venv/bin/python`，`PYTHONPATH=src/backend`）重跑 7 个 t075 单元测试文件，61/61 passed；另核对门禁 final3 证据（`cloud-task-logs/gate-t075-final3/`，仓外）：unit 2414 条、失败+错误 15 条，逐条为 t063×12、t068×2、a16×1 既有基线，t075 文件 0 失败。

### 前轮 finding 复核

#### t075_code_f001 - 迁移阻塞清单已纳入快照扫描：已消除

- 复核：`src/backend/migrations/versions/0013_profile_identity.py:101` 起 `_blocking_entries` 现扫描 `profile_config_versions`，损坏 JSON、非对象、强制 GPU、悬空绑定、未绑定且平台无默认集各记一条（含 snapshot id 与 profile id）；`_rewrite_snapshots` 的静默 `continue` 只在守卫已先抛错的前提下不可达。新增 4 条快照阻塞用例（`tests/unit/test_t075_migration.py:328` `test_snapshot_forced_gpu_blocks`、`:366` `test_snapshot_dangling_binding_blocks`、`:397` `test_snapshot_corrupt_json_blocks`、`:413` `test_snapshot_unbound_without_platform_set_blocks`），随 61 条重跑全过。

#### t075_code_f002 - Runner 验证改为逐文件 sha256 实算、文档措辞同步：已消除

- 复核：`src/backend/cbrowser/runtime_agent/font_verification.py:137` `_check_manifest_files` 对每个 manifest 条目实算 sha256，不符报 `font_content_mismatch`；`src/backend/cbrowser/runtime_agent/font_verification.py:114` `_load_manifest` 要求每条目含非空 sha256 字符串，缺失即 manifest 无效。新增篡改用例 `tests/unit/test_t075_font_verification.py:138` `test_tampered_content_fails` 与 `:260` `test_real_tampered_font_fails_end_to_end`，重跑通过。文档侧 `docs/blueprint/browser_runtime.md:65` 与 `docs/specs/fingerprint_platform.md:40` 现写「逐文件 sha256 内容哈希」，并明言「manifest 不含文件大小字段，故本层不做大小比对」；与导入侧条目结构（仅 `name` + `sha256`，`src/backend/cbrowser/font_sets/manifest.py` 导入构造）一致。

#### t075_code_f003 - 未配置字体根的进程启动告警：已消除（按处置口径）

- 复核：`src/backend/cbrowser/api/app.py` lifespan 中 `font_catalog.root_configured()` 为假时写 `cbrowser.api` warning，明言该进程创建的 Profile 无绑定、无法启动。按处置表采纳的是「启动路径告警」一侧（非硬拒，集成 fixture 故意不设字体根）；豁免口径仍在 ADR，代码现已在启动时显式发声，不再只靠约定。

#### t075_code_f004 - verify_mounted_font_set 拆分：修不彻底（仍 open，minor）

- 严重度：minor
- 锚点：行为缺陷（可维护性；复杂度本身未产出可观测缺陷，不 blocking）
- 位置：`src/backend/cbrowser/runtime_agent/font_verification.py:194`
- 问题：拆分本身已做，4 个 helper 均小（`_load_manifest` CC≈11、`_check_manifest_files` ≈7、`_assess_effective_fonts` ≈8、`_prove_cjk_render` ≈7，AST 近似计数）。但主函数 `verify_mounted_font_set` 按提示词手算口径仍约 CC≈17（基数 1 + 8 个 `if` + 3 处短路 `or`/`and` + 1 个 `except` + 推导式 4 个 `for`/`if` 子句；AST 近似计数 18），与 Round 1 旧函数同一量级，未落到 15 以下。函数体是扁平 early-return 门禁序列、无嵌套超一层、各失败 token 均有测试覆盖，未发现漏处理分支，故仍只记 minor，不 blocking。
- 建议：把可选覆盖计算（`carried` 集合与 `missing_optional` 推导式，约 4 个分支）抽为 `_optional_coverage(manifest, platform)` helper，主函数可降至约 12–13；或再把 manifest 门禁前序抽为一编排步。

### 本轮新发现：0 条（无新 finding 编号）

### 未进表的提示

- 圈复杂度 ≥10 提示（结论段提示，不进表）：`_load_manifest`（`src/backend/cbrowser/runtime_agent/font_verification.py:114`）CC≈11，建议后续顺手拆分 manifest 结构校验；未产出可观测缺陷。
- 文件过大（降级规则，只列示）：`src/backend/cbrowser/services/profile_service.py` 1825 行、`src/backend/cbrowser/runtime_agent/runner.py` 1112 行，仍超 800 行阈值，但本轮修复未向二者净增行数（改动在 `api/app.py`、`runtime_agent/font_verification.py`、`runtime_agent/glyph_render.py`、迁移 0013 与文档），故无新增项；新文件 `src/backend/cbrowser/runtime_agent/font_verification.py` 258 行、`src/backend/cbrowser/runtime_agent/glyph_render.py` 228 行，均未超阈值。
- 健壮性观察（不进表）：`src/backend/cbrowser/runtime_agent/font_verification.py:137` `_check_manifest_files` 未复用 `manifest.py:109` 的 `_safe_name`（manifest 条目名含 `..` 时可越出集目录读文件）。不构成 finding 的理由：到达 Runner 层的 manifest 已在宿主侧经 Supervisor `check_font_set` 的 `_safe_name` 校验（同一卷）；且下游 `fc-list` 枚举与 FreeType 渲染证明只认集目录内的面，遍历名无法把坏集翻成 verified，也无内容外泄（仅哈希等值判断）。建议后续顺手复用 `_safe_name` 加固。
- 性能观察（不进表）：`src/backend/cbrowser/runtime_agent/glyph_render.py:206` `prove_cjk_render` 每字重开一次 FreeType 库与字体面（4 次 init/open）。只发生在实例启动时的一次性就绪门禁，无可观测影响；如后续复用可把 library/face 作成上下文复用。
- 陈旧 verdict 已封闭（本轮核查，无 finding）：Runner 失败路径不写 `runner_info.json`，但每次启动由 Supervisor 发新 `runtime_instance_id`（`src/backend/cbrowser/supervisor/core.py:3012` 的 `inst_<uuid12>`），失败时错误状态带新实例 id 落库；Agent 健康校验 `runner_info` 与状态记录的 profile/instance/config_version 一致性（`src/backend/cbrowser/runtime_agent/agent.py:210`），失配报 `StorageError` 而非沿用旧 verified 结论，且 `ready` 要求 `font_ok`。无假就绪路径。
- 安全/契约面已扫：R2 新增代码无外部输入直达执行（`fc-list` 为固定 argv、`timeout=60`）；`glyph_render.py` 只用 ctypes 调系统 FreeType，无新依赖、无 secret、无日志敏感信息；`font_verification.py` 的失败 token 均为稳定机器可读串，不含路径细节；OpenAPI/生成类型同步在 final3 `protocol_drift_check` 与 `contract` 套件中 passed。

### 总体判断

实现层完整兑现 AC-001–AC-009 的云端可做部分；前轮 4 条 minor 中 3 条已消除，f004 修不彻底仍为 1 条 minor，无未解决 critical / important；PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。平台+语言+独立 `include_cjk_fonts` 取代手选字体包（`src/backend/cbrowser/domain/models.py`、`src/backend/cbrowser/domain/profile_locale.py` 默认解析、前端 `ProfileForm.tsx` 同步开关），`tests/unit/test_t075_profile_identity.py` 随 61 条重跑全过。
- AC-002：TICK-VALID，re_verified。`gpu_family` 与 `--fingerprint-gpu-vendor` 透传已删除（本轮 grep 仍仅剩迁移与 baseline 历史文件）；GPU 身份只由持久 seed+平台派生，切平台重绑定或写入前失败（`src/backend/cbrowser/services/profile_service.py` 平台切换分支）；双平台多 seed 引擎动态实测属 p137 本地补验，不属代码层缺口。
- AC-003：TICK-VALID，re_verified。`color_scheme` 四层收敛为 `light`/`dark` 默认 light，Runner 以固定引擎传值，后台主题独立未耦合；相关用例随 61 条重跑全过。
- AC-004：TICK-VALID，re_verified。迁移 0013 的 profiles 与快照双侧阻塞前零写入、幂等、备份恢复演练均有实测（`tests/unit/test_t075_migration.py`，含本轮新增 4 条快照阻塞用例），本人重跑通过。
- AC-005：TICK-VALID，re_verified。`font_set_mount` 缺失源目录抛错不建空挂载；未绑定在服务层（`_validate_font_set_binding` 现拒 None）与 Runner 层（无 verdict 即 `font_set_unavailable` 失败封闭）双层拒绝；`tests/unit/test_t075_supervisor_fonts.py` 随重跑通过；未配置字体根的进程级豁免现由 lifespan 告警显式化（f003 已消除）。
- AC-006：TICK-VALID，re_verified。挂载空/manifest 损坏/平台不符/文件缺失/逐文件 sha256 内容不符（本轮新为实算比对，`font_content_mismatch`）/过滤后空集/CJK 能力不符各有稳定失败 token，Runner 失败封闭不启动、Agent 以 verdict 门禁 ready；`tests/unit/test_t075_font_verification.py`、`tests/unit/test_t075_fontconfig.py` 随重跑通过。
- AC-007：TICK-VALID，trust_prior。代码层已复验：fontconfig 按开关生成 reject 规则、CJK 开时 `verify_mounted_font_set` 调 `glyph_render.prove_cjk_render` 做 FreeType 真实光栅化证明（字形索引非零、有墨、位图 ≠ 本字体 `.notdef`，`tests/unit/test_t075_glyph_render.py` 7 条用真实字体通过，本人重跑确认）；但「真实 Chrome 引擎内中文渲染」的证据云端不可执行，已登记 p137 本地补验，此项依赖契约区 2026-11-18 用户裁定处置注记，未冒充实测。
- AC-008：TICK-VALID，re_verified。可选覆盖缺口（`missing_optional`）与必需失败（`font_verification.failure` + ready=false）字段分离；普通配置变更不触碰 user_data_dir（`test_t075_profile_identity.py` 哨兵用例随重跑通过）。
- AC-009：TICK-VALID，trust_prior。按契约区 2026-11-18 用户裁定处置注记：云端可做部分（受管挂载构造、实例级真实字体验证、就绪门禁、错误挂载失败封闭）已实现并经单元层复验，真实容器化双平台渲染验证延期 pending p137 本地补验，本行依赖该注记口径，不表示已实测通过。

coverage = 7 / 9

verdict: PASS

## Round 3 (2026-11-18T19:49:03+08:00)

reviewed_scope: 382b23dcfe742f47

- 本轮指纹核对：`task.py review-status` 在写报告前显示 `review_scope=stale`（对照 Round 2 指纹 `86817c96d31d703c`，`overall=INCOMPLETE`，符合“Round 2 后有改动须重审”的预期）；本人用 `repo_task.monitoring.review_scope_fingerprint` 对当前 worktree 重算，结果 `382b23dcfe742f47` 与提示词给定的指纹一致。未跟踪文件只剩两份审阅报告本身（流程文件，指纹排除），无 reviewer 看不到的交付物。
- 本轮独立复验：用门禁 venv（`.scratch/gate_venv/bin/python`，`PYTHONPATH=src/backend`）重跑 3 个直接相关文件 23/23 passed，7 个 t075 单元测试文件 61/61 passed；另以脚本直接比对 `_optional_coverage` 与 Round 2 内联形式的输出（windows/macos/未知平台 × 三种 manifest），全部一致。

### 前轮 finding 复核

#### t075_code_f001 - 迁移阻塞清单已纳入快照扫描：已消除（Round 2 结论维持，本轮无回归）

- 复核：`src/backend/migrations/versions/0013_profile_identity.py:83` 起 `_blocking_entries` 仍扫描快照表（行号与 Round 2 一致，未动）；`tests/unit/test_t075_migration.py` 随 61 条重跑全过。

#### t075_code_f002 - Runner 验证逐文件 sha256 实算、文档措辞同步：已消除（Round 2 结论维持，本轮无回归）

- 复核：`src/backend/cbrowser/runtime_agent/font_verification.py:137` `_check_manifest_files` 与 `:114` `_load_manifest` 行号、内容与 Round 2 一致，未动；篡改用例随 23 条重跑通过。

#### t075_code_f003 - 未配置字体根的进程启动告警：已消除（Round 2 结论维持，本轮无回归）

- 复核：`src/backend/cbrowser/api/app.py:338` `root_configured()` 告警分支仍在，未动。

#### t075_code_f004 - verify_mounted_font_set 拆分：已消除

- 复核：可选覆盖计算已抽为 `_optional_coverage(manifest, platform)`（`src/backend/cbrowser/runtime_agent/font_verification.py:248`），主函数 `verify_mounted_font_set`（`:194`）成功路径仅调用它（`:243`）。手算主函数 CC：基数 1 + 8 个 `if` + 1 个 `except` + 3 处短路 `or`（`:217` 守卫、`:218` `failure or` 回退、`:226` lister 回退）+ 1 处 `and`（`:220` 平台比对）= 14，落到 15 阈值以下；`_optional_coverage` 本身 CC 约 4（基数 1 + 两层推导式 `for` + 1 个 `if`）。
- 行为等价复核：helper 语义与 Round 2 内联形式逐字一致——`carried = {entry["name"] for entry in manifest["files"]}`，再对 `PLATFORM_DETECTION_LABELS.get(platform, ())` 下各 label 的 `DETECTION_FONTS` 取 `not in carried` 的名字集合后 `sorted`。本轮以脚本实测 windows/macos/未知平台 × 三种 manifest（含已携带中文检测字体、空集），helper 输出与重建的内联形式全部相等且有序去重；且 helper 只在 `verified` 返回路径调用，各 `_failed` 路径仍默认 `missing_optional=[]`，与 Round 2 一致。调用点之前 `_load_manifest` 已保证 `files` 为非空 list 且每条目含非空 str `name`，故 `entry["name"]` 无 KeyError 风险；未知平台时 `get(platform, ())` 返回空集，`missing_optional=[]`。各失败 token 与测试断言不变（12 个 token 常量均在文件顶部原位），23 条直接相关测试重跑全过，无 token/verdict 回归。
- 影响面复核：除 `font_verification.py` 外无其他交付文件改动——该文件内 `_load_manifest`（`:114`）、`_check_manifest_files`（`:137`）、`_assess_effective_fonts`（`:155`）、`_prove_cjk_render`（`:169`）、主函数（`:194`）的行号与 Round 2 记录完全一致；全仓 grep `carried`/`missing_optional` 除本文件外仅 `agent.py:185`、`:191` 的既有消费（读 verdict 字段，未动）。

### 本轮新发现：0 条（无新 finding 编号）

### 未进表的提示

- 圈复杂度 ≥10 提示（结论段提示，不进表）：`_load_manifest`（`src/backend/cbrowser/runtime_agent/font_verification.py:114`）CC≈11，与 Round 2 相同，未动、未产出可观测缺陷。
- 文件过大（降级规则，只列示）：`src/backend/cbrowser/services/profile_service.py` 1825 行、`src/backend/cbrowser/runtime_agent/runner.py` 1112 行，仍超 800 行阈值，但本轮未向二者净增行数；`src/backend/cbrowser/runtime_agent/font_verification.py` 现 265 行，未超阈值。
- Round 2 的两项健壮性/性能观察（`_check_manifest_files` 未复用 `_safe_name`；`prove_cjk_render` 每字重开 FreeType 库与字体面）均未动，结论不变，不进表。
- 安全/契约面已扫：本轮唯一改动为纯计算抽取，无新输入面、无新依赖、无 secret、无日志变化；失败 token 集与 verdict 形状不变，Agent 健康门禁（`missing_optional` 字段）不受影响。

### 总体判断

Round 2 后唯一改动（`_optional_coverage` 抽取）行为等价、无 token/verdict 回归，主函数手算 CC 降至 14，code f004 已彻底消除；前轮 4 条 minor 现全部消除，无未解决 critical / important；PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。平台+语言+独立 `include_cjk_fonts` 取代手选字体包；本轮改动不触及该路径，`tests/unit/test_t075_profile_identity.py` 随 61 条重跑全过。
- AC-002：TICK-VALID，re_verified。GPU 身份只由持久 seed+平台派生，切平台重绑定或写入前失败；本轮改动不触及该路径，相关用例随 61 条重跑全过；双平台多 seed 引擎动态实测属 p137 本地补验，不属代码层缺口。
- AC-003：TICK-VALID，re_verified。`color_scheme` 四层收敛为 `light`/`dark` 默认 light；本轮改动不触及该路径，相关用例随 61 条重跑全过。
- AC-004：TICK-VALID，re_verified。迁移 0013 的 profiles 与快照双侧阻塞前零写入、幂等、备份恢复演练均有实测；本轮改动不触及迁移，`tests/unit/test_t075_migration.py` 随重跑通过。
- AC-005：TICK-VALID，re_verified。`font_set_mount` 缺失源目录抛错不建空挂载，未绑定双层拒绝启动；本轮改动不触及该路径，`tests/unit/test_t075_supervisor_fonts.py` 随重跑通过。
- AC-006：TICK-VALID，re_verified。挂载空/manifest 损坏/平台不符/文件缺失/逐文件 sha256 内容不符/过滤后空集/CJK 能力不符各有稳定失败 token；本轮抽取不改任一 token 或判定顺序，`tests/unit/test_t075_font_verification.py` 随 23 条重跑通过。
- AC-007：TICK-VALID，trust_prior。代码层已复验：FreeType 真实光栅化证明（`tests/unit/test_t075_glyph_render.py` 7 条随重跑通过），且本轮抽取只影响 `verified` 路径的 `missing_optional` 字段、不影响 CJK 判定；但「真实 Chrome 引擎内中文渲染」的证据云端不可执行，已登记 p137 本地补验，此项依赖契约区 2026-11-18 用户裁定处置注记，未冒充实测。
- AC-008：TICK-VALID，re_verified。可选覆盖缺口（`missing_optional`）与必需失败字段分离；本轮正是该字段的计算抽取，已以脚本实测 helper 输出与 Round 2 内联形式一致且有序去重，相关用例随 23 条重跑通过。
- AC-009：TICK-VALID，trust_prior。按契约区 2026-11-18 用户裁定处置注记：云端可做部分已实现并经单元层复验，真实容器化双平台渲染验证延期 pending p137 本地补验，本行依赖该注记口径，不表示已实测通过。

coverage = 7 / 9

verdict: PASS

## Round 4 (2026-11-18T20:01:55+08:00)

reviewed_scope: 8f37c34486db496e

- 本轮指纹核对：`task.py review-status` 在写报告前显示 `review_scope=stale`（对照 Round 3 指纹 `382b23dcfe742f47`，`overall=INCOMPLETE`，符合“Round 3 后有改动须重审”的预期）；本人用 `repo_task.monitoring.review_scope_fingerprint` 对当前 worktree 重算，结果 `8f37c34486db496e` 与提示词给定的指纹一致。未跟踪文件只剩两份审阅报告本身（流程文件，指纹排除），无 reviewer 看不到的交付物。
- 本轮复验范围说明：Round 3 后唯一改动据任务说明为 finish 门禁要求的 Markdown 格式化（md_kx）重排。本轮以三重证据核对该说法：其一，全部 Round 3 代码锚点行号与内容原位未动（`src/backend/cbrowser/runtime_agent/font_verification.py:114/137/155/169/194/243/248`、`src/backend/migrations/versions/0013_profile_identity.py:83`、`src/backend/cbrowser/api/app.py:338`、`tests/unit/test_t075_migration.py:328/366/397/413`，文件行数 `font_verification.py` 265、`profile_service.py` 1825、`runner.py` 1112，均与 Round 3 记录一致）；其二，7 个 t075 单元测试文件用门禁 venv（`.scratch/gate_venv/bin/python`，`PYTHONPATH=src/backend`）重跑 61/61 passed；其三，两份交付文档全文通读——ADR 040（`docs/blueprint/decisions/20261118_profile_identity_readiness.md`，85 行）与 `docs/blueprint/testing.md` 的 t075 验收映射表（9 行，AC-001~009 齐全）语义完整、表格结构未破、交叉引用文件（`docs/findings/d051_gpu_identity_engine_derived_no_sdk_control.md`、`docs/spikes/s026_gpu_platform_capability/report.md`）真实存在，全文件无 U+FFFD 字符损坏（此前 diff 输出里的 `��` 只是终端渲染假象，文件本身为干净 UTF-8，`整体失败`/`不存在` 均正常）。`task.md` 仍为 9/9 打勾，AC-007/AC-009 的 2026-11-18 用户裁定处置注记原文未动，与注入契约区一致。

### 前轮 finding 复核

#### t075_code_f001 - 迁移阻塞清单已纳入快照扫描：已消除（Round 2 结论维持，本轮无回归）

- 复核：`src/backend/migrations/versions/0013_profile_identity.py:83` 起 `_blocking_entries` 仍扫描快照表；4 条快照阻塞用例行号与 Round 2 一致（`tests/unit/test_t075_migration.py:328/366/397/413`），随 61 条重跑全过。

#### t075_code_f002 - Runner 验证逐文件 sha256 实算、文档措辞同步：已消除（Round 2 结论维持，本轮无回归；但同类措辞在 ADR 040 有残留，见本轮 f005）

- 复核：`src/backend/cbrowser/runtime_agent/font_verification.py:137` `_check_manifest_files` 与 `:114` `_load_manifest` 行号、内容与 Round 3 一致，未动；`docs/blueprint/browser_runtime.md:65` 与 `docs/specs/fingerprint_platform.md:40` 仍写「逐文件 sha256 内容哈希」且前者明言「manifest 不含文件大小字段，故本层不做大小比对」。

#### t075_code_f003 - 未配置字体根的进程启动告警：已消除（Round 2 结论维持，本轮无回归）

- 复核：`src/backend/cbrowser/api/app.py:338` `root_configured()` 告警分支仍在，未动。

#### t075_code_f004 - verify_mounted_font_set 拆分：已消除（Round 3 结论维持，本轮无回归）

- 复核：`_optional_coverage` 仍在 `src/backend/cbrowser/runtime_agent/font_verification.py:248`，主函数 `:194` 手算 CC 仍约 14（基数 1 + 8 个 `if` + 1 个 `except` + 3 处短路 `or` + 1 处 `and`），落到 15 阈值以下；`_load_manifest` CC≈11、`_optional_coverage` CC≈4，均与 Round 3 一致。

### Findings

### t075_code_f005 - ADR 040 仍称 Runner 验证「逐文件哈希/大小相符」，实现与已修正文档均无大小比对

- 严重度：minor
- 锚点：行为缺陷（文档与实现不一致）+ AC-006 周边口径
- 位置：`docs/blueprint/decisions/20261118_profile_identity_readiness.md:57`
- 问题：ADR 040 决策 6 写 Runner 验证「manifest 可解析、平台一致、逐文件哈希/大小相符」。实际 manifest 条目只有 `name` + `sha256`（`src/backend/cbrowser/font_sets/manifest.py:268` 导入构造），`_check_manifest_files`（`src/backend/cbrowser/runtime_agent/font_verification.py:137`）只做存在性 + sha256 实算，无任何大小字段读取或比对；`docs/blueprint/browser_runtime.md:65` 已在 Round 2 修正为「manifest 不含文件大小字段，故本层不做大小比对」。失败场景：维护者按 ADR 040 理解，会误以为 Runner 层另有独立的大小复核（例如同名文件被替换为等哈希碰撞外的同大小不同内容时——sha256 已可发现；真正风险是误以为大小是第二道防线而放松对 sha256 覆盖面的检查）。定为 minor 的理由：纯文档措辞问题，与 f002 同类；AC-006 的「内容不符不报告可用」由 sha256 实算完整覆盖，行为无缺口。本 finding 不是 Round 3→4 回归：措辞在重排前已存在（重排只改断行），是 Round 2 修 f002 时只改了 `browser_runtime.md` 与 `fingerprint_platform.md`、漏改 ADR 040 的残留，本轮全文重读交付文档时发现。
- 建议：把 ADR 040:57 的「逐文件哈希/大小相符」改为「逐文件 sha256 内容哈希相符」，与 `browser_runtime.md:65` 和 `fingerprint_platform.md:40` 的已修正措辞一致；或在 ADR 中补一句「manifest 不含大小字段，不做大小比对」。

### 本轮新发现：1 条（critical 0、important 0、minor 1，即 f005）

### 未进表的提示

- 圈复杂度 ≥10 提示（结论段提示，不进表）：`_load_manifest`（`src/backend/cbrowser/runtime_agent/font_verification.py:114`）CC≈11，与 Round 3 相同，未动、未产出可观测缺陷。
- 文件过大（降级规则，只列示）：`src/backend/cbrowser/services/profile_service.py` 1825 行、`src/backend/cbrowser/runtime_agent/runner.py` 1112 行，仍超 800 行阈值，但本轮未向二者净增行数；`src/backend/cbrowser/runtime_agent/font_verification.py` 现 265 行，未超阈值。
- Round 2 的两项健壮性/性能观察（`_check_manifest_files` 未复用 `_safe_name`；`prove_cjk_render` 每字重开 FreeType 库与字体面）均未动，结论不变，不进表。
- 安全/契约面已扫：本轮改动面为纯 Markdown 断行重排，无新输入面、无新依赖、无 secret、无日志变化；`testing.md` 的 t075 映射表 9 行 AC 行为与 `task.md` 契约逐条对应，AC-007/AC-009 行均明言顺延 p137、不得记为已验；无范围外行为。

### 总体判断

Round 3 后改动确为纯文档断行重排，代码、测试与契约均未动，61 条 t075 单元测试重跑全过；前轮 4 条 minor 全部消除仍成立，本轮仅新增 1 条 minor（f005，ADR 040 大小比对措辞残留）；无未解决 critical / important；PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。平台+语言+独立 `include_cjk_fonts` 取代手选字体包；本轮改动不触及该路径，`tests/unit/test_t075_profile_identity.py` 随 61 条重跑全过。
- AC-002：TICK-VALID，re_verified。GPU 身份只由持久 seed+平台派生，切平台重绑定或写入前失败；本轮改动不触及该路径，相关用例随 61 条重跑全过；双平台多 seed 引擎动态实测属 p137 本地补验，不属代码层缺口。
- AC-003：TICK-VALID，re_verified。`color_scheme` 四层收敛为 `light`/`dark` 默认 light；本轮改动不触及该路径，相关用例随 61 条重跑全过。
- AC-004：TICK-VALID，re_verified。迁移 0013 的 profiles 与快照双侧阻塞前零写入、幂等、备份恢复演练均有实测；本轮改动不触及迁移，`tests/unit/test_t075_migration.py` 随重跑通过。
- AC-005：TICK-VALID，re_verified。`font_set_mount` 缺失源目录抛错不建空挂载，未绑定双层拒绝启动；本轮改动不触及该路径，`tests/unit/test_t075_supervisor_fonts.py` 随重跑通过。
- AC-006：TICK-VALID，re_verified。挂载空/manifest 损坏/平台不符/文件缺失/逐文件 sha256 内容不符/过滤后空集/CJK 能力不符各有稳定失败 token；本轮改动不触及验证代码，`tests/unit/test_t075_font_verification.py` 随 61 条重跑通过；ADR 040 的「大小相符」措辞残留记 f005（minor，不推翻打勾）。
- AC-007：TICK-VALID，trust_prior。代码层已复验：FreeType 真实光栅化证明（`tests/unit/test_t075_glyph_render.py` 随 61 条重跑通过），且本轮改动不触及 CJK 判定；但「真实 Chrome 引擎内中文渲染」的证据云端不可执行，已登记 p137 本地补验，此项依赖契约区 2026-11-18 用户裁定处置注记，未冒充实测。
- AC-008：TICK-VALID，re_verified。可选覆盖缺口（`missing_optional`）与必需失败字段分离；本轮改动不触及该路径，相关用例随 61 条重跑通过。
- AC-009：TICK-VALID，trust_prior。按契约区 2026-11-18 用户裁定处置注记：云端可做部分已实现并经单元层复验，真实容器化双平台渲染验证延期 pending p137 本地补验，本行依赖该注记口径，不表示已实测通过。

coverage = 7 / 9

verdict: PASS

## Round 5 (2026-11-18T20:11:48+08:00)

reviewed_scope: 6ae64bcb28c76d56

- 本轮指纹核对：`task.py review-status` 在写报告前显示 `review_scope=stale`（对照 Round 4 指纹 `8f37c34486db496e`，`overall=INCOMPLETE`，符合“Round 4 后有改动须重审”的预期）；本人用 `repo_task.monitoring.review_scope_fingerprint` 对当前 worktree 重算，结果 `6ae64bcb28c76d56` 与任务给定的指纹一致。未跟踪文件只剩两份审阅报告本身（流程文件，指纹排除），无 reviewer 看不到的交付物。
- 本轮复验范围说明：Round 4 后唯一改动据任务说明为 ADR 040 第 57 行一行措辞修正（处置 Round 4 代码轴新发现的 minor f005）。本轮以三重证据核对该说法：其一，全部 Round 4 代码锚点行号与内容原位未动（`src/backend/cbrowser/runtime_agent/font_verification.py:114/137/155/169/194/243/248`、`src/backend/migrations/versions/0013_profile_identity.py:83`、`src/backend/cbrowser/api/app.py:338`、`tests/unit/test_t075_migration.py:328/366/397/413`，文件行数 `font_verification.py` 265、`profile_service.py` 1825、`runner.py` 1112、`0013_profile_identity.py` 250，均与 Round 4 记录一致）；其二，7 个 t075 单元测试文件用门禁 venv（`.scratch/gate_venv/bin/python`，`PYTHONPATH=src/backend`）重跑 61/61 passed；其三，`task.md` 仍为 9/9 打勾，AC-007/AC-009 的 2026-11-18 用户裁定处置注记原文未动，与注入契约区一致。

### 前轮 finding 复核

#### t075_code_f001 - 迁移阻塞清单已纳入快照扫描：已消除（Round 2 结论维持，本轮无回归）

- 复核：`src/backend/migrations/versions/0013_profile_identity.py:83` 起 `_blocking_entries` 仍扫描快照表；4 条快照阻塞用例行号与 Round 2 一致（`tests/unit/test_t075_migration.py:328/366/397/413`），随 61 条重跑全过。

#### t075_code_f002 - Runner 验证逐文件 sha256 实算、文档措辞同步：已消除（Round 2 结论维持，本轮无回归）

- 复核：`src/backend/cbrowser/runtime_agent/font_verification.py:137` `_check_manifest_files` 与 `:114` `_load_manifest` 行号、内容与 Round 4 一致，未动；`docs/blueprint/browser_runtime.md:65` 与 `docs/specs/fingerprint_platform.md:40` 仍写「逐文件 sha256 内容哈希」且前者明言「manifest 不含文件大小字段，故本层不做大小比对」。

#### t075_code_f003 - 未配置字体根的进程启动告警：已消除（Round 2 结论维持，本轮无回归）

- 复核：`src/backend/cbrowser/api/app.py:338` `root_configured()` 告警分支仍在，未动。

#### t075_code_f004 - verify_mounted_font_set 拆分：已消除（Round 3 结论维持，本轮无回归）

- 复核：`_optional_coverage` 仍在 `src/backend/cbrowser/runtime_agent/font_verification.py:248`，主函数 `:194` 手算 CC 仍约 14，落到 15 阈值以下；`_load_manifest` CC≈11、`_optional_coverage` CC≈4，均与 Round 4 一致。

#### t075_code_f005 - ADR 040 大小比对措辞残留：已消除

- 复核：`docs/blueprint/decisions/20261118_profile_identity_readiness.md:57` 现写「逐文件 sha256 内容哈希相符」，`:58` 续写「（manifest 不含文件大小字段，故本层不做大小比对）」，与 f005 建议措辞及 `docs/blueprint/browser_runtime.md:65` 的已修正表述逐字一致。
- 与实现一致性复核：manifest 条目构造只有 `name` + `sha256`（`src/backend/cbrowser/font_sets/manifest.py:268`）；`_check_manifest_files`（`src/backend/cbrowser/runtime_agent/font_verification.py:137`）只做存在性 + sha256 流式实算比对，不符报 `font_content_mismatch`；`_load_manifest`（`:114`）要求每条目含非空 sha256 字符串；`src/backend/cbrowser/runtime_agent/font_verification.py` 与 `src/backend/cbrowser/font_sets/manifest.py` 全文 grep `size` 零命中，确认无任何大小字段读取或比对。宿主侧 `check_font_set`（`src/backend/cbrowser/font_sets/manifest.py:339` 起）同样只比对 sha256。全仓其余「大小」提及：`docs/specs/runtime_lifecycle.md:39` 只写「逐文件哈希」无大小主张，表述准确；其余命中均为无关 task 的历史记录。本轮无新 finding 编号。

### 本轮新发现：0 条（无新 finding 编号）

### 未进表的提示

- 圈复杂度 ≥10 提示（结论段提示，不进表）：`_load_manifest`（`src/backend/cbrowser/runtime_agent/font_verification.py:114`）CC≈11，与 Round 4 相同，未动、未产出可观测缺陷。
- 文件过大（降级规则，只列示）：`src/backend/cbrowser/services/profile_service.py` 1825 行、`src/backend/cbrowser/runtime_agent/runner.py` 1112 行，仍超 800 行阈值，但本轮未向二者净增行数；`src/backend/cbrowser/runtime_agent/font_verification.py` 现 265 行，未超阈值。
- Round 2 的两项健壮性/性能观察（`_check_manifest_files` 未复用 `_safe_name`；`prove_cjk_render` 每字重开 FreeType 库与字体面）均未动，结论不变，不进表。
- 安全/契约面已扫：本轮改动面为纯文档一行措辞修正，无新输入面、无新依赖、无 secret、无日志变化、无代码/测试/契约改动；无范围外行为。

### 总体判断

Round 4 后唯一改动（ADR 040:57–58 措辞修正）准确落地且与实现一致，f005 已消除；前轮 5 条 minor 现全部消除，代码、测试与契约均未动，61 条 t075 单元测试重跑全过；无未解决 critical / important；PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。平台+语言+独立 `include_cjk_fonts` 取代手选字体包；本轮改动不触及该路径，`tests/unit/test_t075_profile_identity.py` 随 61 条重跑全过。
- AC-002：TICK-VALID，re_verified。GPU 身份只由持久 seed+平台派生，切平台重绑定或写入前失败；本轮改动不触及该路径，相关用例随 61 条重跑全过；双平台多 seed 引擎动态实测属 p137 本地补验，不属代码层缺口。
- AC-003：TICK-VALID，re_verified。`color_scheme` 四层收敛为 `light`/`dark` 默认 light；本轮改动不触及该路径，相关用例随 61 条重跑全过。
- AC-004：TICK-VALID，re_verified。迁移 0013 的 profiles 与快照双侧阻塞前零写入、幂等、备份恢复演练均有实测；本轮改动不触及迁移，`tests/unit/test_t075_migration.py` 随重跑通过。
- AC-005：TICK-VALID，re_verified。`font_set_mount` 缺失源目录抛错不建空挂载，未绑定双层拒绝启动；本轮改动不触及该路径，`tests/unit/test_t075_supervisor_fonts.py` 随重跑通过。
- AC-006：TICK-VALID，re_verified。挂载空/manifest 损坏/平台不符/文件缺失/逐文件 sha256 内容不符/过滤后空集/CJK 能力不符各有稳定失败 token；本轮改动不触及验证代码，`tests/unit/test_t075_font_verification.py` 随 61 条重跑通过；ADR 040 的措辞已修正为与实现一致的「逐文件 sha256 内容哈希相符（manifest 不含文件大小字段，故本层不做大小比对）」（f005 已消除）。
- AC-007：TICK-VALID，trust_prior。代码层已复验：FreeType 真实光栅化证明（`tests/unit/test_t075_glyph_render.py` 随 61 条重跑通过），且本轮改动不触及 CJK 判定；但「真实 Chrome 引擎内中文渲染」的证据云端不可执行，已登记 p137 本地补验，此项依赖契约区 2026-11-18 用户裁定处置注记，未冒充实测。
- AC-008：TICK-VALID，re_verified。可选覆盖缺口（`missing_optional`）与必需失败字段分离；本轮改动不触及该路径，相关用例随 61 条重跑通过。
- AC-009：TICK-VALID，trust_prior。按契约区 2026-11-18 用户裁定处置注记：云端可做部分已实现并经单元层复验，真实容器化双平台渲染验证延期 pending p137 本地补验，本行依赖该注记口径，不表示已实测通过。

coverage = 7 / 9

verdict: PASS

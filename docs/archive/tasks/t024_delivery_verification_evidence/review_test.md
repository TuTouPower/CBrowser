# Task review t024（reviewer_focus: 测试）

- task：`t024_delivery_verification_evidence`
- spec：`docs/tasks/t024_delivery_verification_evidence/task.md`
- diff_anchor：`597c09aff927c8cc54f72bfc405ac0336d58e22e`
- target：`git -C '/home/hatch/workspace/CBrowser_t024' diff 597c09aff927c8cc54f72bfc405ac0336d58e22e`
- round：1
- reviewed_at：2026-11-04T05:59:15+08:00

reviewed_scope: 8ecc8ed08998582d

## Findings

### t024_test_f001 - AC-017 隐私守卫在交付树上确定性红：archive/handoff.md 豁免指纹已失效

- 严重度：critical
- 锚点：AC-017——守卫本应证明当前树无开发者路径泄漏（除指纹绑定的已批准存量），交付树上该测试本身失败
- 位置：`tests/unit/test_repo_hygiene.py:119`（`test_tracked_files_do_not_leak_developer_home_paths`）；`tests/unit/review_privacy_allowlist.txt:5`（`docs/archive/handoff.md sha256:40e941ee…`）
- 问题：reviewer 独立重跑 `pytest tests/unit/test_repo_hygiene.py -q`（venv、TMPDIR=/tmp/cbt024-rev2）结果 1 failed / 5 passed：`docs/archive/handoff.md` 出现 32 处 `/Users/karson/` 泄漏未被豁免。该文件当前 sha256 为 `fc58792136c2a5b12ae446e5a7c89eb792394a9820c1350dae31117d478ff216`，allowlist 里的 `40e941ee…` 经核对正是 anchor 版该文件的 sha256——实施进度 4 把旧 handoff 一节追加进该归档文件后，内容指纹变化、豁免按其自身设计失效，但 allowlist 未同步、测试未在文档收敛后重跑（note.md 进度 1 的「6 passed」是追加前的状态）。失败场景：合并后产品门禁在 unit 层即红，AC-017 处于未通过状态。
- 建议：二选一并重跑全量 unit 门禁后留证——追加进 archive 的一节先脱敏再入档；或将该文件的**新内容**作为已批准存量重新登记指纹（须说明批准依据，不能默认自批，见 f002）。

### t024_test_f002 - 隐私豁免只绑内容哈希、丢弃路径，与「路径+指纹双绑定」契约不符

- 严重度：important
- 锚点：AC-017 / A52——「现有历史豁免绑定具体路径及已批准内容指纹，新增文件或新增泄漏不自动继承」
- 位置：`tests/unit/test_repo_hygiene.py:87`（`approved_snapshot_hashes`）、`:102`（`_path, _, fingerprint = line.rpartition(" sha256:")`，路径被解析后丢弃）、`:108`（`is_approved_snapshot(data, hashes)` 只查全局哈希集合）
- 问题：豁免判定只看文件字节的 sha256 是否在集合中，路径完全不参与。失败场景：任何**新文件**只要内容与某个已批准快照逐字节相同（仓库内已有同哈希多文件先例，如三份 `entrypoint_browser.sh` 同为 `dcbc7d70…`），即使它位于从未批准的路径、含有开发者路径，也会被整体跳过扫描——这正是 AC-017 要禁止的「新增文件继承豁免」。现有合成测试 `test_snapshot_exemption_lapses_when_content_changes` 只验证内容变化失效，未验证路径错配失效。
- 建议：豁免键改为 `(path, sha256)` 对（归档移动时按其声明同步改路径），并补一条「同内容、不同路径不豁免」的合成用例。

### t024_test_f003 - AC-001 只做了静态存在性/自研匹配器检查，隔离构建验证未做，与 AC 明文禁止的证据形态相同

- 严重度：important
- 锚点：AC-001——「launch_args 可在隔离构建镜像中导入并运行，不能只通过静态文件存在性检查」
- 位置：`tests/unit/test_docker_build_contexts.py:114`（`test_copy_sources_exist_in_tree`）、`:123`（`test_copy_sources_admitted_by_dockerignore`，dockerignore 语义为测试内自研近似匹配器）、`:168`（`test_launch_args_module_is_importable`，`:174` 仅 `assert module is not None`）
- 问题：三条证据分别是文件存在性、测试代码里平行实现的 dockerignore 近似匹配（不是 Docker 自己的 patternmatcher，更不是构建），以及在门禁 venv 里 import 后做纯存在性断言。AC 明文排除的正是这组证据形态；真实隔离构建已被推到 p027（未开）。可测试性声明写明「镜像…在隔离环境执行，缺前提不作 PASS」——本机无 Docker 是前提缺失，应记未验证，不能以静态守卫冒充 AC-001 已覆盖。
- 建议：AC-001 保持未验证状态直至 p027 在有 Docker 环境完成隔离构建+镜像内导入运行并留证；或把静态守卫的测试命名/docstring 改为明确「仅静态预检，非 AC-001 验收」以免误读（不改变未验证结论）。

### t024_test_f004 - AC-015 同样只有 Dockerfile 文本静态检查，无冷构建与真实媒体/动态库验证

- 严重度：important
- 锚点：AC-015——「从当前源冷构建的 Stream 运行镜像不包含编译器与开发头文件，仍通过真实音视频、输入、剪贴板与动态库加载验证」
- 位置：`tests/unit/test_runtime_image_hygiene.py:29`（`test_stream_runtime_final_stage_has_no_build_toolchain`，对 Dockerfile 文本做子串/正则检查）、`:54`、`:66`（requirements 文本与 AST import 集合比对）
- 问题：最终层无 toolchain 仅由「Dockerfile 最后一段文本不含 build-essential/-dev 字样 + 有 COPY --from=builder」推断；若 runtime 阶段实际 apt 安装了编译器但换名、或 venv 复制漏动态库导致 `ldd` 缺失、或 GStreamer 插件不齐，这些测试全绿而镜像不可用。冷构建与真实音视频/输入/剪贴板验证已推 p027（未开），同 f003 属「缺前提不作 PASS」被静态检查替代。
- 建议：同 f003——AC-015 记未验证，待 p027 冷构建 + ldd/导入 + 真实媒体链路证据齐备后再宣称覆盖；静态测试保留为预检并如实标注。

### t024_test_f005 - busy_timeout/等待时间断言被成倍放宽，属阈值掩盖型改测，与 AC-007/AC-018 明文冲突

- 严重度：important
- 锚点：AC-007（「数据库 busy_timeout 的原有真实上限仍能使超限实现失败」）、AC-018 / A53（「继续按现行…SQLite busy_timeout 上界判断，不擅自改…或扩大阈值」）；危险模式扫描「阈值掩盖」
- 位置：`tests/integration/test_v2_api_subprocess.py:826`（短锁 `1.4 <= elapsed < 4.5` 改为 `1.0 <= elapsed < 5.0`）、`:859`（长锁 `4.5 <= elapsed_timeout <= 6.5` 改为 `4.5 <= elapsed_timeout < 15.0`）；`tests/unit/test_domain_and_repository.py:479`（WAL 读者「promptly」上界 `elapsed < 1.0` 改为 `< 5.0`）
- 问题：就地把旧测试预期改成新实现/新环境的输出，无规格变更依据（spec 上下文反而明文禁止扩大阈值）。失败场景：busy_timeout 被实现成 10s（预算 2 倍）时，长锁用例耗时约 10s 仍落在 [4.5, 15.0) 内判 PASS，原 [4.5, 6.5] 必然失败——超限实现不再被测出；短锁下界 1.4→1.0 使 1.0s 的缩水 timeout 也可通过；WAL 读者在 4.9s 才返回（近乎全程阻塞）也算「未阻塞」。note.md 自述为「派生宽松界」，属实施方理由，不构成降级依据。
- 建议：恢复原上界（长锁 ≤6.5、短锁 <4.5、WAL 读者 <1.0 量级）；若确因环境抖动需放宽，按流程先改 spec/AC 并留归因，再改测试，不得先改测试迁就现状。

### t024_test_f006 - AC-006 跨工作目录运行仍有确定性失败：freshness 用例以 CWD 相对路径加载 conftest

- 严重度：important
- 锚点：AC-006——「测试可从其他工作目录运行」
- 位置：`tests/unit/test_frontend_build_freshness.py:113`（`runpy.run_path("tests/e2e/conftest.py")`）
- 问题：reviewer 从 `/tmp` 以绝对路径重跑该文件：`test_e2e_collection_hook_rejects_stale_frontend` 报 `FileNotFoundError: '/tmp/tests/e2e/conftest.py'`（8 passed 后首个 hook 用例即失败）。该相对路径为存量写法，但本 task 在同一文件内新增了第二个 hook 用例（`test_e2e_collection_hook_rejects_stale_dist_for_non_frontend_names`，AC-003）复用同一 helper，且 A27 明列要修的三处 `__file__` 锚定未覆盖此文件——AC-006 在本文件仍未达成。失败场景：任何从仓库根以外目录发起的门禁/IDE 运行都会在此假红，掩盖真实 freshness 回归信号。
- 建议：helper 改为 `Path(__file__).resolve().parents[2] / "tests/e2e/conftest.py"` 锚定，并把「从其他 cwd 运行 tests/unit」纳入收尾验证留证。

### t024_test_f007 - AC-014 共享 Docker 替身无与真实 DockerAdapter 的契约对照，且其客户端类无人使用

- 严重度：important
- 锚点：AC-014——「产品测试共享 fixture 与真实 DockerAdapter 的行为契约相符，各故障仍能独立注入」；测试策略——「产品 fixture 与真实 adapter 对照」
- 位置：`tests/fixtures/docker_doubles.py:39`（`FakeDockerClient`）、`:55`（`fake_docker_client`）；真实适配器在 `src/backend/cbrowser/supervisor/docker_adapter.py:96`
- 问题：全仓 grep 证实 `FakeDockerClient` 与 `fake_docker_client()` 零调用方；实际被采用的只有 `FakeContainer/FakeContainers`，且仅 `tests/integration/test_supervisor_observation_authority.py:25` 一处。没有任何测试把共享替身与真实 `DockerAdapter` 做行为契约对照（如 get 不存在时抛 docker NotFound、list 过滤语义、status/labels 形状）——替身与真实契约是否相符无证据，漂移时不会变红。note.md 亦承认 normal-exit 与 unit 的特化 `_FakeDockerAdapter` 保留未迁移，「唯一事实源」未成立。
- 建议：补一条契约对照测试（同一组行为断言分别跑共享替身与真实 adapter 的可观察面），并让至少主要消费方真正使用 `fake_docker_client()`，或删除未用类并把 AC-014 的该子项如实记为部分处置。

### t024_test_f008 - 勘误 §6 的 t009 路径指向不存在位置，现行入口无法定位

- 严重度：minor
- 锚点：AC-013——「独立产品勘误可从现行入口定位到原报告/任务与替代关系」
- 位置：`docs/reviews/review_20261102_201727_errata.md:46`（写 `docs/tasks/t009_*/task.md`）
- 问题：t009 已归档，实际路径为 `docs/archive/tasks/t009_v2_full_acceptance/task.md`；`docs/tasks/t009_*` 在当前树不存在，按勘误给出的路径定位不到原文。
- 建议：改为归档实际路径。

### t024_test_f009 - wait_until 超时错误不含最后观测，与 AC-014「deadline + 最后观测」只兑现一半

- 严重度：minor
- 锚点：AC-014——「资源等待使用 deadline 与最后观测」
- 位置：`tests/fixtures/wait.py`（`wait_until`，超时仅报 description；`poll_until` 有 `last=`）
- 问题：本轮多处等待改走 `wait_until`（如 coordinator 两套件），其 predicate 为无值布尔，超时信息里没有最后观测状态，失败诊断弱于同文件 `poll_until` 的口径。
- 建议：`wait_until` 允许 predicate 返回观测值并在超时信息中带出，或在结论中如实标注该子项为部分兑现。

### t024_test_f010 - 容器固定路径例外用 startswith 前缀匹配，非精确例外

- 严重度：minor
- 锚点：AC-017——「固定容器路径有精确例外」
- 位置：`tests/unit/test_repo_hygiene.py:65`（`token.startswith(prefix)`，prefix=`/root/.config/google-chrome`，`:27`）
- 问题：`/root/.config/google-chrome-malicious/…`、`/root/.config/google-chrome.evil/…` 等同前缀异目录路径也会被整体豁免，例外边界未落在路径段上。现行树未见此类路径，故为 minor。
- 建议：例外判定改为 `token == prefix or token.startswith(prefix + "/")`，并补合成负例。

## 结论

- 改测方向复核：有迁就型改测——f005 的三处时间上界放宽是把旧测试预期改向当前实现/环境输出，无规格变更支撑，且与 AC-007/AC-018 及上下文区 A28/A53 的明文（保留原上界、不扩大阈值）冲突。其余改测经逐项核对方向正当：event cursor 游标由集合断言收紧为精确 `e2.json`、ac001 未授权状态由 `(403,404,503)` 析取收紧为精确 403、HELLO 正向检查由接受 CLOSE/CLOSED 改为真实 HELLO TEXT 交换、凭证 mount 由「存在才断言只读」改为强制存在+只读、auth 大测试拆分为 9 个独立行为测试（断言逐条保留）、健康并发由 0.6s 绝对耗时改为区间重叠结构化证明（A28 明文处方）。`test_runtime_persistence_guards.py:157` 的 `skipif(euid==0)` 经调查为合法条件跳过：同行为有无条件 seam 注入变体在前覆盖，chmod 变体仅在权限位对 root 无效时跳过并写明 reason，不出 finding。
- 危险模式扫描：命中阈值放宽（f005，最低 important 已计）；未发现新增恒真断言、注释掉断言、`.only`、静默错误标记或 mock 被测逻辑本身；`test_launch_args_module_is_importable` 的 `assert module is not None` 属纯存在性断言充当 AC 证据，已并入 f003。
- 本轮新发现：10 条（critical 1 / important 6 / minor 3）
- 未进表的提示：`scripts/run_gates.sh` 仍以 `--python ">=3.12"` 建门禁 venv（与 anchor 相同、非本轮引入），gate-requirements.txt 是在 CPython 3.12 下冻结的；在更高版本解释器上重建可能因锁定 wheel 不匹配失败，AC-009 的「支持 Python 固定」口径建议实施方在收尾时明确（本轮未单独出 finding）。E2E 树本轮仅做 collect-only 复验（88 tests collected，无 dist 时 freshness 钩子不触发），其真实 Docker/Chrome 执行属 trust_prior。
- 总体判断：AC-017 的守卫测试在交付树上确定性失败（f001），且 AC-001/AC-015/AC-014 的关键测试证据与 AC 明文要求存在缺口、AC-006 有可复现跨目录失败、busy_timeout 阈值被违规放宽——存在未解决 critical/important，FAIL。
- 系统性 follow-up：p027 已承载 AC-001/AC-015 的真实 Docker 构建验证义务（f003/f004 与之对应，不重复立项）；其余 finding 为本 task 内可修项，无需新 follow-up。

### AC 复验方式

- AC-001：trust_prior——依赖 p027（未开）的隔离构建证据；本机无 Docker 无法复验，静态测试已查证（见 f003，故不作 PASS）。
- AC-002：trust_prior——抽查 handoff 新节、findings 追加标注、blueprint 四文件 diff 与生产 docstring 两处，方向一致；全量逐项文档事实对照未独立重做。
- AC-003：re_verified——重跑 `tests/unit/test_frontend_build_freshness.py`（仓库根）10 条全绿，并查证 `tests/fixtures/frontend_app_probe/harness.py:45`、`tests/fixtures/frontend_probe/host_builder.py:42`、`tests/e2e/conftest.py:53` 三处消费点均在复制/托管前调用校验。
- AC-004：trust_prior——integration 层（FakeApiService 三元组授权键、真实 `create_gateway_app` 断言）随 `test_supervisor_gateway_client.py` 等重跑通过；Gateway/Agent/adapter 的完整客户端链路需 Docker/Chrome，依赖实施侧拓扑套件证据。
- AC-005：re_verified——逐项查证精确 403、真实 HELLO TEXT、精确游标、具体 ArtifactError、seam 注入无写入等断言已落地且相关套件重跑通过；活 Docker client 泄漏检查（ipv6 用例前移断言）仅代码查证，属 E2E 未执行。
- AC-006：re_verified——normal_exit 四用例以 short_data_root 重跑通过（单独运行），但跨目录复验发现 f006 的确定性失败，故本条复验结论为未达成。
- AC-007：re_verified——poll_until/wait_until 改造与结构化并发证明逐项查证属实；同时发现 f005 的阈值放宽与本条冲突，本条复验结论为部分达成。
- AC-008：trust_prior——抽查 docstring/更名/四元组注解（retry、policy_failure、normal_exit、supervisor_core）与实际覆盖对应；历史 AC 勾选未被改动（task.md 全部 AC 仍为未勾选，经查证）。
- AC-009：trust_prior——查证 `scripts/gate-requirements.txt` 为全 pin 锁且 `run_gates.sh` 已改为单 venv 从锁安装；空缓存全量重建依赖 uv 与网络，本机未独立复跑，依赖实施侧 .gate-t024 运行记录（note 仅记契约层 169 passed 已回）。
- AC-010：re_verified——重跑 `tests/unit/test_browser_entrypoint.py` 4 条全绿（--help/-h 退出 0 含用法、非法参数与缺参非零）。
- AC-011：trust_prior——代码查证 Chrome 前提按套件内容判定、namespace 用例新增同条件正向基线、证据私有目录与脱敏集扩充、Selkies runner cap-drop 已落地；真实容器执行需 Docker，未复验。
- AC-012：re_verified——查证根 `.env.example` 为唯一权威（v2 变量、秘密为空），`config/.env.example` 已删且无消费者引用（grep 无命中）。
- AC-013：trust_prior——勘误文件逐节阅读，33/362/A13=5 等数字口径自洽且与 note 的复算说明对应，归档字节未被本 diff 改动（diff 中归档文件仅新增/追加类改动，其中 handoff 追加引发 f001）；数字未逐一独立复算。
- AC-014：re_verified——clock 注入、session_maker fixture 化、wait helper 等子项查证属实且相关套件重跑通过；但共享替身契约对照缺失（f007），本条复验结论为部分达成。
- AC-015：trust_prior——依赖 p027 冷构建证据（未开）；静态守卫已查证（见 f004，故不作 PASS）。
- AC-016：re_verified——stamp v2 的必需输入拒绝生成、文件集增删、新配置/env 文件致过期等用例随 freshness 套件重跑全绿；进程 env 仅 allowlist（空）入集，源码 grep 确认前端无 `import.meta.env`/`VITE_` 消费。
- AC-017：re_verified——独立重跑守卫套件，结果 1 failed / 5 passed（f001），且豁免实现与双绑定契约不符（f002）；本条复验结论为未达成。
- AC-018：re_verified——vendor pin+manifest 双校验用例、adapter_probe per-type 计数与 dropped 计数、perf_samples 证据字段均已查证，相关 unit 层重跑通过；busy_timeout 上界被放宽（f005）使本条部分失效。真实性能预算的 E2E 执行属 trust_prior（需 Docker/Chrome）。

coverage = re_verified 10 / 18（AC-003、005、006、007、010、012、014、016、017、018；其中 006/007/014/017/018 的复验结论含未达成/部分达成，如上逐条注明）
建议合并前人工抽查 trust_prior 项（trust_prior 占 8/18 ≈ 44% > 30%，集中在 Docker/Chrome 真实环境与文档事实类 AC）

verdict: FAIL

## Round 2 (2026-11-04T06:26:00+08:00)

- round：2
- 复审范围：相对 anchor `597c09aff927c8cc54f72bfc405ac0336d58e22e` 的完整 worktree（含未跟踪交付文件，已逐一直接读文件核对；`git status` 中 review 报告、勘误、p027、d027、gate-requirements、docker_doubles 与三份新测试文件仍为 `??`，本轮以文件系统实读为准，不影响结论）

reviewed_scope: 018790f93eec1f3f

## Findings（本轮新发现）

### t024_test_f011 - 契约对照的 containers 集合语义只跑了替身一侧，真实 adapter 同面未被同一组断言触达

- 严重度：minor
- 锚点：AC-014——「共享 fixture 与真实 DockerAdapter 的行为契约相符」（f007 的残留子项，非阻断）
- 位置：`tests/unit/test_docker_doubles_contract.py:44`（`test_containers_collection_semantics_match_docker_sdk` 全程只断言 `FakeDockerAdapter`；真实 adapter 仅在 `:35` 的命名对照中被构造）
- 问题：命名对照是真双跑（fake 与 real 的 browser/stream 命名逐一比对，reviewer 已核对生产实现 `src/backend/cbrowser/supervisor/docker_adapter.py:520` 同式），但集合语义（get 缺失抛 NotFound、list 形状、labels/status）与 `scan_active_containers` 空集只在替身侧断言，未对真实 adapter（经其注入的 client 面）跑同一组断言。漂移风险已大幅收敛（NotFound 语义是替身被消费的实际契约面、真实侧由 docker SDK 原生保证），故为 minor 残留，不推翻 f007 的消除结论。
- 建议：把集合语义断言参数化为对 fake 与 real（注入同一 FakeDockerClient）各跑一遍，或在测试 docstring 中如实标注集合语义为替身单侧契约。

## 结论

- 前轮 finding 复核（逐条，以 diff 与独立复跑为准）：
  - f001（critical）已消除：`tests/unit/review_privacy_allowlist.txt:6` 的 `docs/archive/handoff.md` 指纹已更新为 `fc587921…`，与该文件当前实算 sha256 逐字一致；anchor→current 对该文件的 diff 仅为尾部追加一节（2026-11-02 交接节），reviewer 逐行核对追加节不含开发者路径，32 处存量泄漏均在原已批准字节内，重签依据成立。独立复跑守卫套件 8 passed（见下）。
  - f002（important）已消除：豁免键改为 `(path, sha256)` 对——`tests/unit/test_repo_hygiene.py:90` `approved_snapshots` 返回 `set[tuple[str, str]]`、`:113` `is_approved_snapshot(name, data, approved)` 以 `(name, sha256)` 查表，路径不再被丢弃；新增合成用例 `test_snapshot_exemption_does_not_follow_content_to_a_new_path`（`:197`）断言同字节异路径（两条）均不豁免，复跑通过。
  - f003（important）口径已修、验收义务遗留 p027：`tests/unit/test_docker_build_contexts.py:3` docstring 已标「STATIC PRECHECK ONLY…not the AC-001 acceptance evidence」并指向 p027；收尾报告如实把 AC-001 标为 trust_prior/未验证。不再以静态守卫冒充验收证据，本 finding 按「遗留→p027」处置成立；真实隔离构建仍未做，合并口径不得把 AC-001 读作已实测（`test_launch_args_module_is_importable` 的 `assert module is not None` 仍在，但已明确降格为预检，不再充当 AC 证据）。本轮不阻断，义务由 p027 承载。
  - f004（important）口径已修、验收义务遗留 p027：同 f003——`tests/unit/test_runtime_image_hygiene.py:7` 已标 STATIC PRECHECK ONLY 并指向 p027，收尾报告 AC-015 标 trust_prior。冷构建与真实媒体/ldd 验证仍未做，同 f003 处置。
  - f005（important）已消除：三处上界逐字恢复 anchor 原值，reviewer 以 `git show <anchor>:<path>` 与现行文件逐行比对——短锁 `1.4 <= elapsed < 4.5`（`tests/integration/test_v2_api_subprocess.py:820`，anchor `:793`）、长锁 `4.5 <= elapsed_timeout <= 6.5`（`:853`，anchor `:822`，含 `<=` 上界形态）、WAL 读者 `elapsed < 1.0`（`tests/unit/test_domain_and_repository.py:478`，anchor `:465`），三处均逐字一致、无第四处残留放宽。用恢复后的上界独立复跑：`test_v2_api_subprocess.py` 9 passed（49s，含真实锁等待耗时）、domain 锁相关 2 passed——超限实现重新可被测出。
  - f006（important）已消除：helper 改 `__file__` 锚定（`tests/unit/test_frontend_build_freshness.py:113`，`Path(__file__).resolve().parents[2] / "tests/e2e/conftest.py"`）；reviewer 从仓库外 cwd（`/tmp`、绝对路径、PYTHONPATH 绝对路径）独立复跑该文件 12 passed，原 `FileNotFoundError` 不复现。
  - f007（important）已消除（残留 minor 见 f011）：`tests/fixtures/docker_doubles.py` 新增 `FakeDockerAdapter`（生产同前缀 `cbrowser-t005`、与生产 `:104` 默认值一致）并被 `tests/integration/test_supervisor_observation_authority.py:25` 实际采用（复跑 3 passed）；`FakeDockerClient`/`fake_docker_client()` 现有真实调用方（契约测试与 FakeDockerAdapter 自身），未用的 `find_free_port` 导出已删（grep 无残留）；新增 `tests/unit/test_docker_doubles_contract.py` 命名双跑对照，复跑 3 passed。
  - f008（minor）已消除：勘误 §6 已改归档实际路径 `docs/archive/tasks/t009_v2_full_acceptance/task.md`（`docs/reviews/review_20261102_201727_errata.md:46`，该路径现行树存在）。
  - f009（minor）已消除：`tests/fixtures/wait.py` 的 `wait_until`/`wait_until_sync` 超时错误均补 `last={last!r}` 最后观测，与 `poll_until` 同口径，docstring 已同步说明。
  - f010（minor）已消除：容器固定路径例外改路径段边界判定（`tests/unit/test_repo_hygiene.py:66`，`token == prefix or token.startswith(prefix + "/")`），新增 `test_container_prefix_exemption_respects_segment_boundary` 含 `google-chrome.evil`、`google-chrome2` 两条同前缀异目录负例，复跑通过。
- 改测方向复核：本轮改测均为修复方向，无迁就实现——busy_timeout 三处是把 Round 1 被放宽的预期逐字恢复为 anchor 原值（收紧而非放宽）；其余为新增合成负例（路径错配、段边界、非消费套件不拦截）与锚定修复，未删/反转任何既有断言。危险模式扫描（新文件与修复文件）：无恒真断言、无 `.skip`/`.only`、无静默错误标记、无阈值再放宽（grep 核查）。
- 本轮新发现：1 条（minor 1：f011；critical 0 / important 0）
- 本轮独立复跑证据（venv `.scratch/t024/venv`、PYTHONPATH=src/backend:tests/fixtures、TMPDIR=/tmp/cbt024-r2t）：守卫+契约+构建上下文+镜像卫生+entrypoint 合跑 23 passed；observation_authority 3 passed；freshness 仓外 cwd 12 passed；test_v2_api_subprocess 9 passed；test_domain_and_repository 锁相关 2 passed。
- 未进表的提示：AC-001/AC-015 的真实 Docker 验收仍完全依赖 p027 在有 Docker 环境执行；其静态预检测试名（`test_launch_args_module_is_importable` 等）本身仍带验收语气，靠 docstring 降格而非命名，后续收尾时可考虑更名，非本轮阻断项。
- 总体判断：Round 1 的 critical/important 全部消除或按规则遗留 p027 并如实披露（f003/f004），minor 全部消除；本轮仅新增 1 条 minor（f011），无未解决 critical/important，PASS。
- 系统性 follow-up：p027（AC-001/AC-015 真实构建验收）继续承载；f011 为 task 内小修，无需新 follow-up。

### AC 复验方式（Round 2）

- AC-001：trust_prior——静态预检已复跑通过且已如实降格标注；验收依赖 p027 的隔离构建证据（未开），不作 PASS 依据（处置见 f003 复核）。
- AC-002：trust_prior——沿 Round 1 抽查结论；本轮仅复核其引发的归档追加字节（f001）无新增泄漏。
- AC-003：re_verified——freshness 12 passed（含新增非消费套件负例）仓外 cwd 复跑通过，钩子按实际消费标记触发（`tests/e2e/conftest.py` `_item_consumes_dist`）。
- AC-004：trust_prior——沿 Round 1；本轮 observation/gateway 相关复跑未见回归。
- AC-005：re_verified——busy/存储相关套件以恢复后的精确上界复跑通过（见 f005）；其余精确断言沿 Round 1 查证。
- AC-006：re_verified——f006 已消除，仓外 cwd 复跑 12 passed 为直接证据；normal_exit 沿 Round 1 复跑结论。
- AC-007：re_verified——三处时间上界逐字比对 anchor + 复跑通过（f005），等待 helper 补最后观测（f009）。
- AC-008：trust_prior——沿 Round 1 抽查；本轮静态套件 docstring 降格标注属本条口径，已查证。
- AC-009：trust_prior——沿 Round 1（锁+单 venv 查证）；`run_gates.sh` 已 pin Python 3.12（diff 查证），空缓存全量重建未独立复跑。
- AC-010：re_verified——entrypoint 套件随本轮合跑通过（23 passed 批次内）。
- AC-011：re_verified（代码与负例层）——非消费套件不被陈旧 dist 拦截的新负例随 freshness 复跑通过；真实容器执行部分 trust_prior（Docker）。
- AC-012：trust_prior——沿 Round 1 查证（本轮无相关 diff 变化）。
- AC-013：re_verified——勘误 t009 路径已修正且目标存在（f008）；数字口径沿 Round 1。
- AC-014：re_verified——契约对照 3 passed + observation 3 passed（f007）；集合语义单侧残留记 f011（minor），本条主体达成。
- AC-015：trust_prior——同 AC-001，依赖 p027（处置见 f004 复核）。
- AC-016：re_verified——stamp 必需目录负例（`test_missing_src_directory_rejected_at_generation`）随 freshness 12 passed 复跑通过，`REQUIRED_DIRS=("src",)` 在生成/校验两侧生效（`scripts/verify_frontend_dist.py:50,88`）。
- AC-017：re_verified——守卫 8 passed 独立复跑，双绑定与段边界负例均在套件内（f001/f002/f010）。
- AC-018：re_verified——busy_timeout 上界恢复使本条预算重新可失败（f005 复跑证据）；真实性能 E2E 部分 trust_prior（Docker/Chrome）。

coverage = re_verified 11 / 18（AC-003、005、006、007、011、013、014、016、017、018 及 AC-010；trust_prior 7 条含 AC-001/015 的 p027 未验证义务）
建议合并前人工抽查 trust_prior 项（trust_prior 占 7/18 ≈ 39% > 30%，集中在 Docker 构建/真实环境与文档事实类 AC；其中 AC-001/AC-015 须待 p027 完成后才可称验收通过）

verdict: PASS

## Round 3 (2026-11-04T06:27:12+08:00)

- round：3（定向复审）
- 复审范围：仅 Round 2 之后两处增量——(1) t024_test_f011 修复（`tests/unit/test_docker_doubles_contract.py` 集合语义双侧对照）；(2) code 侧未进表观察增量（`tests/unit/test_stream_ice_config.py` 的 CWD 相对路径改 `__file__` 锚定）。落点校验：`git rev-parse --show-toplevel`（不带 `-C`，workdir 为仓库根）输出精确等于 `/home/hatch/workspace/CBrowser_t024`。

reviewed_scope: 80f9ed5b1772c829

## Findings（本轮新发现）

无（0 条；critical 0 / important 0 / minor 0）。

## 结论

- 前轮 finding 复核：
  - f011（minor）已消除：`tests/unit/test_docker_doubles_contract.py:48` 的 `_sdk_containers()` 构造真实 docker SDK `ContainerCollection`（`docker.models.containers`），仅 stub 其 API 层两点——`inspect_container`（缺失时按 SDK 自身语义抛 `NotFound`）与 `containers`（返回 `[]`）；reviewer 对照 venv 内 SDK 源码核实 `ContainerCollection.get` 经 `client.api.inspect_container` 并传播 `NotFound`、`list` 经 `client.api.containers(...)` 后逐项 `get`，即被测的是 SDK 真实集合代码而非平行实现，stub 落在系统边界（Docker API 层），非 mock 被测逻辑。`:69` 的 `test_containers_collection_semantics_match_docker_sdk` 以同一行为矩阵 `for containers in (fake.containers, sdk)`（`:74`）双侧断言 `get("missing")` 抛 `NotFound` 与 `list() == []`，Round 2 指出的「只跑替身一侧」已对该矩阵消除。`:78` 起 present-container 块在注释中明示为替身侧形状断言（labels/status 属 `FakeContainer` 自身形状），未冒充双侧对照，不构成隐藏缺口；为 SDK present 侧再加 attrs 双跑属可选扩展，记未进表提示、不出 finding。
  - Round 1/Round 2 其余 finding 不在本轮定向范围内，沿 Round 2 复核结论（f003/f004 的 AC-001/AC-015 真实构建义务仍由 p027 承载，本轮未变）。
- ICE 增量复核（code 侧未进表观察）：相对 anchor 的 diff 仅一处 hunk——`tests/unit/test_stream_ice_config.py:16` `ENTRYPOINT` 由 `Path("config/docker/stream_runtime/entrypoint.sh")` 改为 `Path(__file__).resolve().parents[2] / "config/docker/stream_runtime/entrypoint.sh"`，与 f006 的 freshness helper 同锚定模式；文件内其余断言（ICE-lite、禁外部 STUN/TURN 的两组检查）逐字未动，无断言删改/弱化。此修复直接对应 AC-006「测试可从其他工作目录运行」。
- 改测方向复核：无迁就实现——f011 修复是把对照扩到真实 SDK 代码路径（收紧），ICE 增量只改路径锚定不改预期；两处均未删/反转/弱化任何既有断言。
- 危险模式扫描（两处增量文件）：无恒真断言、无 `.skip`/`.only`、无静默错误标记、无阈值改动、无条件跳过弱化；`_sdk_containers` 的 stub 仅限 SDK 的 API 边界两点且保留 SDK 错误语义，非 mock 误用。
- 本轮新发现：0 条
- 本轮独立复跑证据（cwd=`/tmp`、绝对路径、venv `.scratch/t024/venv`、PYTHONPATH=`<repo>/src/backend:<repo>/tests/fixtures`（绝对路径）、TMPDIR=/tmp/cbt024-r3t）：`test_docker_doubles_contract.py` 3 passed + `test_stream_ice_config.py` 4 passed，合计 7 passed——与实施侧自述一致；其中 ICE 文件的两条 entrypoint 用例在旧相对路径下于仓外必然失败（文件不存在），现全绿，直接证明锚定修复生效。
- 未进表的提示：契约对照的 SDK present-container 侧（经 attrs 构造 SDK Container 后比 labels/status）未双跑，现以替身侧形状断言 + 注释明示覆盖；后续若 FakeContainer 形状再扩展可一并参数化，非本轮阻断项。
- 总体判断：本轮定向范围的两处增量均经 diff 与独立复跑核实属实，f011 已消除、ICE 仓外运行已修复，无未解决 critical/important，PASS。
- 系统性 follow-up：无（p027 继续承载 AC-001/AC-015 真实构建验收，与本轮无关）。

### AC 复验方式（Round 3，定向）

- AC-014：re_verified（本轮增量部分）——契约对照集合语义双侧矩阵独立复跑 3 passed，SDK 真实代码路径经源码核对；本条其余子项沿 Round 2 复验结论。
- AC-006：re_verified（本轮增量部分）——`test_stream_ice_config.py` 自 `/tmp` 以绝对路径复跑 4 passed，`__file__` 锚定生效；本条其余子项沿 Round 2 复验结论。
- 其余 AC：本轮定向范围外，未重验，沿 Round 2 结论（含 AC-001/AC-015 为 trust_prior、义务 p027）。

coverage = re_verified 2 / 2（本轮定向范围内的 AC-014、AC-006 增量部分；全量 18 条 AC 的复验口径沿 Round 2 小节）

verdict: PASS

## Round 4 (2026-11-04T06:31:21+08:00)

- round：4（recovery 定向复审）
- 复审范围：仅 Round 3 双路 PASS（reviewed_scope `80f9ed5b1772c829`）之后的三项流程性增量——(1) `tests/unit/review_privacy_allowlist.txt` 追加 4 条 t024 review 报告登记；(2) `note.md` 的 Review 处置改为检查器要求的表格格式；(3) `task.py finish` 把任务目录归档到 `docs/archive/tasks/t024_delivery_verification_evidence/`（review 报告随之移动）。落点校验：`git rev-parse --show-toplevel`（不带 `-C`，workdir 为仓库根）输出精确等于 `/home/hatch/workspace/CBrowser_t024`。本轮不重开全量评审，交付语义沿 Round 3 结论。

reviewed_scope: 831bbb2a2638ea28

## Findings（本轮新发现）

无（0 条；critical 0 / important 0 / minor 0）。

## 结论

- 增量 (1) allowlist 登记核实（AC-017）：`tests/unit/review_privacy_allowlist.txt:63-66` 共 4 条，分别为两份 review 报告在归档前路径（`docs/tasks/t024_delivery_verification_evidence/`）与归档后路径（`docs/archive/tasks/t024_delivery_verification_evidence/`）的登记，两两同指纹。reviewer 独立实算归档路径文件 sha256 并逐字比对：`review_code.md` 实算 `df03af7cc0c103146dc1c1621235ab5825e40b6733bc744c59af74aa2f150c5a` 与 `:64` 登记一致；`review_test.md` 实算 `5289df460fa709a16dd29765064b12a77fdd0b4f3b5b04c9a0c2eb08b92cc5d8`（本 Round 4 小节追加前的字节）与 `:66` 登记一致。归档前后两条登记指纹相同，证明报告字节在归档移动中未变；登记本身不改变任何被登记文件内容，纯属 AC-017 双绑定豁免的路径同步，未扩大豁免面（条目仍为具体路径+具体指纹，无目录级豁免）。
- 增量 (2) 处置表格式核实：以脚本提取双路报告全部 finding ID（code f001–f008 共 8 条、test f001–f011 共 11 条，合计 19 条）与 `note.md` 处置表行做双向集合比对——19 行一一对应、无缺失、无多余，状态列 19 条全部为「已修」。表格化未丢失或新增任何 finding 条目，内容与 Round 3 时的处置结论等价；`check_review_status.py` 对处置完整性无缺项报告（见下）。
- 增量 (3) 归档移动核实：任务目录现位于 `docs/archive/tasks/t024_delivery_verification_evidence/`（`git ls-files` 确认五件套均已按归档路径跟踪，`docs/tasks/` 下旧目录已不存在）；两份 review 报告的字节不变性由增量 (1) 的同指纹双登记直接证明。归档仅改路径，未触及任何产品代码、测试代码或断言。
- 守卫复跑（本小节追加前状态）：venv `.scratch/t024/venv`、PYTHONPATH=src/backend:tests/fixtures、TMPDIR=/tmp/cbt024-r4t，独立复跑 `tests/unit/test_repo_hygiene.py` 结果 8 passed——新增 4 条登记未使守卫失效，亦未掩盖任何泄漏（登记文件本身经守卫的双绑定判定路径核验）。
- check_review_status 现状（本小节追加前）：`code_verdict=PASS`、`test_verdict=PASS`、`overall=INCOMPLETE`、`review_scope=stale`、`round=3`——INCOMPLETE 仅因两份报告的末条 `reviewed_scope` 仍为 Round 3 指纹；reviewer 经 `.repo_template` 的 `review_scope_fingerprint` 独立重算当前 worktree 指纹为 `831bbb2a2638ea28`，与本轮规定写入值逐字一致，本小节写入后 stale 即消除（review 报告属指纹计算的流程文件排除项，本小节追加本身不改变该指纹）。
- 前轮 finding 复核：本轮定向范围为 Round 3 之后增量，Round 1–3 的 19 条 finding 处置状态经增量 (2) 的集合比对确认未回退；三项增量均未触及其实实现文件。
- 改测方向复核：无——三项增量不含任何测试代码或断言改动（allowlist 为数据登记、note.md 为流程文档、归档为路径移动）。
- 危险模式扫描（三项增量）：无恒真断言、无断言删改/弱化、无 `.skip`/`.only`、无静默错误标记、无阈值改动；allowlist 新登记均为实算指纹的事后登记，非预先放行。
- 本轮新发现：0 条
- 未进表的提示：本 Round 4 小节追加会改变 `review_test.md`（及 code 侧 Round 4 追加改变 `review_code.md`）的字节，两份报告在 allowlist 中的指纹登记将随之失效——与前几轮相同的流程后果，须由实施方在双路 Round 4 追加 settle 后按实算值重新登记（守卫的双绑定设计本就要求登记与内容同批更新）；本轮守卫 8 passed 的结论针对追加前状态，如上明示。此为流程登记义务，不构成 finding。
- 总体判断：三项流程性增量经 sha256 逐字比对、守卫复跑与处置集合比对独立核实，均未改变交付语义：报告字节不变、处置内容等价、豁免面未扩大。无未解决 critical/important，PASS。
- 系统性 follow-up：无（AC-001/AC-015 的真实构建义务仍由 p027 承载，与本轮无关）。

### AC 复验方式（Round 4，定向）

- AC-017：re_verified（本轮增量部分）——两份 review 文件归档路径 sha256 独立实算与 allowlist 登记逐字一致、守卫套件独立复跑 8 passed、双绑定豁免面未扩大；本条其余子项沿 Round 2/3 复验结论。
- 其余 AC：本轮定向范围外，未重验，沿 Round 3（全量口径沿 Round 2）结论，含 AC-001/AC-015 为 trust_prior、义务 p027。

coverage = re_verified 1 / 1（本轮定向范围内的 AC-017 增量部分；全量 18 条 AC 的复验口径沿 Round 2/3 小节）
建议合并前人工抽查 trust_prior 项（沿 Round 2/3 提示：AC-001/AC-015 须待 p027 完成后才可称验收通过）

verdict: PASS

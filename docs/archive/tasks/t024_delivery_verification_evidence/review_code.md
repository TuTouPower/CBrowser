# Task review t024（reviewer_focus: 代码）

- task：`t024_delivery_verification_evidence`
- spec：`docs/tasks/t024_delivery_verification_evidence/task.md`
- diff_anchor：`597c09aff927c8cc54f72bfc405ac0336d58e22e`
- target：`git -C '<home>/workspace/CBrowser_t024' diff 597c09aff927c8cc54f72bfc405ac0336d58e22e`
- round：1
- reviewed_at：2026-11-04T06:07:15+08:00

reviewed_scope: 8ecc8ed08998582d

## Findings

### t024_code_f001 - AC-002 的归档追加使 AC-017 指纹豁免失效，隐私守卫在交付树上确定性红

- 严重度：important
- 锚点：AC-017（只有已批准具体历史文件/内容被豁免，新增归档不能继承目录级豁免）与 AC-002（旧 handoff 一节追加进归档）互相冲突且未调和；失败场景：合并后 unit 门禁即红
- 位置：`docs/archive/handoff.md`（本 task +28 行追加）；`tests/unit/review_privacy_allowlist.txt:6`（该文件登记指纹仍为 anchor 版 sha256 `40e941ee…`）；`tests/unit/test_repo_hygiene.py:141`（断言失败点）
- 问题：reviewer 在指纹范围内独立重跑 `.scratch/t024/venv/bin/python -m pytest tests/unit/test_repo_hygiene.py -q`（PYTHONPATH=src/backend:tests/fixtures、TMPDIR=/tmp/cbt024-rev），结果 1 failed / 5 passed：当前 `docs/archive/handoff.md` sha256 为 `fc587921…`，与 allowlist 登记的 anchor 指纹 `40e941ee…`（已核对等于 anchor 版文件哈希）不一致，豁免按守卫自身设计失效，文件内 37 处 `<home>/` 存量泄漏全部被报出。追加的一节本身不含开发者路径（diff grep 为 0），根因是 AC-002 的追加动作改变了被豁免文件的字节，而实施方未同步处置：既未把追加后的文件作为新存量重新批准登记，也未在文档收敛（进度 4）后重跑守卫——note.md 进度 1 的「6 passed」是追加前的状态。与测试侧报告 `t024_test_f001` 为同一根因，彼处评 critical。
- 建议：将追加后的 `docs/archive/handoff.md` 作为新的已批准存量显式重新登记指纹（注明批准依据：追加节已核无开发者路径、其余为原已批准存量），随后重跑全量 unit 门禁留证；后续任何归档追加都必须与指纹登记同批完成。

### t024_code_f002 - AC-001/AC-015 的实现证据只有静态守卫，隔离/冷构建验证未做，与 AC 明文证据形态冲突

- 严重度：important
- 锚点：AC-001「launch_args 可在隔离构建镜像中导入并运行，不能只通过静态文件存在性检查」；AC-015「从当前源冷构建的 Stream 运行镜像…仍通过真实音视频、输入、剪贴板与动态库加载验证」；可测试性声明「镜像与真实 Chrome 在隔离环境执行，缺前提不作 PASS」
- 位置：`tests/unit/test_docker_build_contexts.py:114`（存在性）、`:123`（测试内自研 dockerignore 近似匹配器）、`test_launch_args_module_is_importable`（门禁 venv 内 import 后仅断言非 None）；`tests/unit/test_runtime_image_hygiene.py:29`（对 Dockerfile 文本做子串/正则检查推断最终层无 toolchain）；`docs/pending/todo/p027_t024_docker_image_real_build_verification.md`（真实构建义务，未开）
- 问题：实现侧交付的全部 AC-001/AC-015 证据都是静态形态：COPY 源存在性、自研匹配器（不是 Docker 自己的 patternmatcher，更不是构建）、本机 venv import、Dockerfile 文本扫描。失败场景：dockerignore 语义与真实 Docker 有偏差、或 Stream runtime 阶段漏装动态库/GStreamer 插件导致镜像内 `ldd` 缺失时，这些测试全绿而镜像不可构建/不可用。p027 只承载后续验证义务，不构成当前 AC 已验证；note.md 自述的「无 Docker 跳过按 pass 计」是实施方口径，不能替代 AC 明文的证据要求（与测试侧 `t024_test_f003/f004` 同向）。
- 建议：AC-001/AC-015 在 task.md 与收尾报告中如实标为未验证（静态守卫仅记预检），待 p027 在有 Docker 环境完成隔离构建、镜像内导入运行、冷构建 + ldd/真实媒体链路并留证后再宣称覆盖。

### t024_code_f003 - busy_timeout 与 WAL 读者的时间上界被成倍放宽，超限实现不再被测出

- 严重度：important
- 锚点：AC-007「数据库 busy_timeout 的原有真实上限仍能使超限实现失败」；AC-018/A53「不擅自改…或扩大阈值」；危险模式扫描「阈值增大掩盖问题」最低 important
- 位置：`tests/integration/test_v2_api_subprocess.py:859`（长锁断言由 `4.5 <= elapsed_timeout <= 6.5` 改为 `4.5 <= elapsed_timeout < 15.0`）；同文件短锁由 `1.4 <= elapsed < 4.5` 改为 `1.0 <= elapsed < 5.0`；`tests/unit/test_domain_and_repository.py:479`（WAL 读者上界由 `elapsed < 1.0` 改为 `< 5.0`）
- 问题：三处上界放宽均无 spec 变更依据，spec 上下文反而明文要求保留原上界。失败场景：busy_timeout 被实现成 10s（预算 2 倍）时长锁用例耗时约 10s 仍落在 [4.5, 15.0) 内判 PASS，原 ≤6.5 必然失败；WAL 读者被阻塞 4.9s 才返回也算「未阻塞」。WAL 用例新增的「锁仍被持有」结构探针是真实加强，但 busy_timeout 长锁路径没有任何结构性补偿，纯靠被放宽的上界。note.md 的「派生宽松界」是实施方理由，不构成降级依据。与测试侧 `t024_test_f005` 为同一改动。
- 建议：恢复原上界（长锁 ≤6.5、短锁 <4.5、WAL 读者 <1.0 量级）；若确因环境抖动需放宽，先改 spec/AC 并留归因再改测试，不得先改测试迁就现状。

### t024_code_f004 - 隐私豁免判定丢弃路径，只绑内容哈希，与「路径+指纹双绑定」契约不符

- 严重度：important
- 锚点：AC-017 / A52「现有历史豁免绑定具体路径及已批准内容指纹，新增文件或新增泄漏不自动继承目录级豁免」
- 位置：`tests/unit/test_repo_hygiene.py`（指纹范围内版本）`approved_snapshot_hashes` 解析 allowlist 时以 `_path, _, fingerprint = line.rpartition(" sha256:")` 丢弃路径，`is_approved_snapshot(data, hashes)` 只查全局哈希集合
- 问题：豁免键只有文件字节的 sha256，路径完全不参与判定。失败场景：任何新文件只要与某个已批准快照逐字节相同（仓内已有同哈希多文件先例），即使位于从未批准的路径且含开发者路径，也会被整体跳过扫描——正是 AC-017 要禁止的「新增文件继承豁免」。合成测试只验证了内容变化使豁免失效，未验证路径错配。与测试侧 `t024_test_f002` 为同一实现缺陷。
- 建议：豁免键改为 `(path, sha256)` 对，归档移动时按声明同步改路径，并补「同内容、不同路径不豁免」的合成用例。

### t024_code_f005 - 交付自述矛盾：task.md 全部 AC 未打勾，note.md 收尾报告仍是创建期模板

- 严重度：important
- 锚点：AC-008（说明与实际对应、未执行场景明确标识）与契约区打勾规范（实施验证通过后由实施 Agent 就地打勾；未打勾按未完成处理）；文档与规格一致性
- 位置：`docs/tasks/t024_delivery_verification_evidence/task.md:30-47`（AC-001～AC-018 全部为 `- [ ]`）；`docs/tasks/t024_delivery_verification_evidence/note.md:51`（收尾报告仍写「结果：未实施，AC 全部未验证 / 测试：尚未执行 / 黑盒：尚未执行」）
- 问题：同一 note.md 的进度 1–4 段声称各 AC 已实施并附测试数字，收尾报告段却仍是创建期模板、声称未实施，两段自相矛盾；task.md 无一条 AC 打勾，按评审规范无法据交付自述判定任何 AC 完成，其中 AC-001/AC-015 的真实状态（未验证，见 f002）也没有在任何收尾位置被如实标出。失败场景：finish 门禁与后续读者按 task.md/note.md 收尾段取数时，会把已实施项当未实施、或把未验证项随进度段误读为已完成。
- 建议：收尾时逐条按真实状态更新 task.md 打勾与 note.md 收尾报告（AC-001/AC-015 标未验证并指向 p027，其余标明验证方式与结果），删除创建期模板残留表述。

### t024_code_f006 - 新共享替身含零调用方的导出，「唯一事实源」未成立

- 严重度：minor
- 锚点：AC-014（共享 fixture 与真实契约相符）；代码质量：死代码
- 位置：`tests/fixtures/docker_doubles.py:39`（`FakeDockerClient`）、`:55`（`fake_docker_client`）、`find_free_port`
- 问题：reviewer 全仓 grep 确认 `FakeDockerClient` 与 `fake_docker_client()` 零调用方，且后者返回的是新造的 `FakeContainers` 而非 `FakeDockerClient` 实例，工厂与类自相脱节；实际被采用的只有 `FakeContainer/FakeContainers`，且仅 `tests/integration/test_supervisor_observation_authority.py` 一处；仓内另有 5+ 处同名 `find_free_port` 局部副本未收敛（`tests/integration/test_gateway_fixtures.py:16`、`tests/integration/test_v2_api_subprocess.py:36` 等）。模块 docstring 的「one canonical fake」与实际采用面不符。测试侧已就契约对照缺失出 `t024_test_f007`（important），本条仅记代码侧死代码与名实不符，不重复计权。
- 建议：删除未用导出或让主要消费方真正改用 `fake_docker_client()`，并同步 docstring 的采用面表述。

### t024_code_f007 - e2e collection 钩子把 dist 新鲜度扩到全部套件，与「只查自身真正需要的前提」相悖

- 严重度：minor
- 锚点：AC-011「E2E 仅检查自身真正需要的 Chrome、镜像与 dist」；AC-003 的校验义务属于实际消费 dist 的探针
- 位置：`tests/e2e/conftest.py:47-58`（`pytest_collection_modifyitems` 改为整个 e2e 树在 dist 目录存在时即校验，与套件是否消费 dist 无关）；`:25`（`_item_needs_host_chrome` 以源码子串 `channel="chrome"`/`CHROME_PATH` 判定前提）
- 问题：改动前仅 frontend 套件触发 freshness 校验，改动后只要 `src/frontend/dist` 目录存在且 stamp 缺失/过期，supervisor 等根本不消费 dist 的套件 collection 也会以 RuntimeError 整体失败，前提范围从「实际消费点」扩成「全树」；同文件的主机 Chrome 前提改用子串启发式，仅在注释/常量中提及 `CHROME_PATH` 的文件会被误判为需要主机 Chrome，间接构造（变量拼装）的文件则会漏判。失败场景：开发者只跑 supervisor e2e 时被无关的前端构建状态阻断 collection，掩盖真实失败信号。
- 建议：freshness 钩子按实际消费 dist 的套件集合触发（显式清单或 fixture 标记），主机 Chrome 前提改为套件级显式声明（如 marker），不用源码子串猜测。

### t024_code_f008 - stamp 生成对源码目录整体缺失静默容忍，必需输入集合不完整

- 严重度：minor
- 锚点：AC-016「必需输入缺失不能生成 stamp」
- 位置：`scripts/verify_frontend_dist.py:84-87`（`frontend_input_manifest` 对 `SOURCE_DIRS` 仅在 `root.is_dir()` 时纳入，目录整体缺失不报错）；`:46`（`REQUIRED_INPUTS` 只有 index.html/package.json/package-lock.json，不含 src/、public/ 目录本身）
- 问题：生成侧把 `src/`、`public/` 当可选：源码树被整体删走时仍可生成一份「合法」stamp（文件集只剩必需三件与配置），verify 与这份新 stamp 比较时自洽通过；只有拿旧 stamp 校验新树时才因文件集差异判过期。失败场景：构建脚本在残缺源码树上先 stamp 后 build，产物新鲜度证据被空集自证。影响面有限（正常构建流程先 build 后 stamp，且删除单文件会被文件集差异捕获），故 minor。
- 建议：把 `src/` 目录（及实际必需的 public/）列入必需输入，目录缺失时与必需文件缺失同等拒绝生成 stamp，并补一条生成侧负例。

## 结论

- 本轮新发现：8 条（critical 0 / important 5 / minor 3）
- 复跑证据（指纹范围内）：定向套件 `test_docker_build_contexts`、`test_browser_entrypoint`、`test_runtime_image_hygiene`、`test_frontend_build_freshness`、`test_stream_capture_policy`、`test_auth_service` 通过；`test_repo_hygiene` 1 failed（f001）。unit+integration 全量首轮 7 failed / 1347 passed，其中 auth/profile-copy/runtime-agent/selkies 等同名失败在 anchor 导出树全量跑中同样出现（全量顺序依赖型存量失败，非本 task 新增回归；anchor 的 hygiene 失败系导出树非 git 仓所致，不作对照），且这些文件单独跑全部通过；e2e 仅 collect-only（88 tests collected）；前端 Vitest 两轮各出现 1 条互不相同的失败（session 授权计数、sse_hardening 尾事件），均在本 task 未触及的前端文件，记为存量 flaky 观察，不进 finding 表。
- 未进表的提示（文件过大）：以下 diff 触及且净增的文件已超阈值，仅作提示——`tests/e2e/test_browser_runtime_e2e.py`（2935 行）、`tests/e2e/test_frontend_app_e2e.py`（1345 行）、`tests/integration/test_v2_api_subprocess.py`（955 行）、`src/backend/cbrowser/stream_agent/policy.py`（769 行，实现源码 ≥400 提示线；本 task 仅注入 clock 的小幅改动）。圈复杂度：生产 diff 内未发现 CC ≥15 的新增/改动函数。
- 未进表的提示（范围外/并发）：本轮评审进行中工作树被并发修改——`tests/unit/test_repo_hygiene.py` 已改为 (path, sha256) 双绑定、`tests/unit/review_privacy_allowlist.txt` 已更新为新指纹 `fc587921…`、`tests/fixtures/wait.py` 补了最后观测、新增 `tests/unit/test_docker_doubles_contract.py`（reviewer 抽跑时其中 `test_container_naming_matches_production` 1 failed，PathSecurityError）。这些改动不在本报告的指纹范围内，f001/f004 是对指纹范围状态的结论；当前树与 `reviewed_scope` 已不一致，须待并发修改 settle 后走下一轮复审重新核对，本轮 verdict 不因并发修复而改判。
- 总体判断：指纹范围内存在未解决 important——隐私守卫确定性红（f001）、AC-001/AC-015 证据形态不达 AC 明文（f002）、时间上界违规放宽（f003）、豁免未双绑定（f004）、交付自述矛盾且 AC 零打勾（f005），FAIL。
- 系统性 follow-up：AC-001/AC-015 的真实 Docker 构建验证已由 p027 承载，不重复立项；其余 finding 均为本 task 内可修项，无需新 follow-up。

### AC 复验方式

- AC-001：trust_prior——静态守卫套件已重跑通过，但隔离构建证据只依赖 p027（未开），本机无 Docker 无法复验；且证据形态问题见 f002，不作 PASS。
- AC-002：trust_prior——抽查 handoff 新节、8 份 findings 的 ADR 013 追加标注、blueprint 四文件与两处生产 docstring diff，方向一致；全量文档事实逐项对照未独立重做。归档追加的副作用见 f001。
- AC-003：re_verified——freshness 套件随定向批次重跑通过，并 grep 查证 `tests/e2e/conftest.py`、`tests/fixtures/frontend_app_probe/harness.py`、`tests/fixtures/frontend_probe/host_builder.py` 三处消费点均在复制/托管前调用校验。
- AC-004：trust_prior——integration 层真实 `create_gateway_app` 的 401/503 精确断言与 FakeApiService 三元组授权键已查证且相关套件在全量跑中通过；完整 Gateway/Agent/adapter 客户端链路需 Docker/Chrome，未复验。
- AC-005：re_verified——逐项查证精确 403（`test_gateway_ac001_auth_e2e.py`）、真实 HELLO TEXT 交换（`test_stream_selkies_tokens_e2e.py`）、精确游标 `e2.json`、具体 ArtifactError、storage seam 注入无写入等断言已落地，相关套件重跑通过；活 Docker client 泄漏检查仅代码查证。
- AC-006：re_verified——`test_normal_exit_replay` 四用例以 `short_data_root` 在全量跑中通过，p019 根因（三组路径长度实测）已回填 task.md；跨工作目录运行的另一确定性失败由测试侧 `t024_test_f006` 记载，本条结论以其为准打折。
- AC-007：re_verified——wait_until/poll_until 改造与结构化并发证明逐项查证属实；但 busy_timeout/WAL 上界被放宽（f003），本条复验结论为部分达成。
- AC-008：trust_prior——抽查 docstring/更名/四元组注解与实际覆盖对应；交付自述层面的矛盾见 f005。
- AC-009：trust_prior——查证 `scripts/gate-requirements.txt` 为全 pin 锁且与本机 .scratch venv 的 freeze 仅差 uv 本体、`run_gates.sh` 已改单 venv 从锁安装；空缓存全量重建未独立复跑（依赖 uv 与网络），依赖实施侧运行记录。
- AC-010：re_verified——重跑 `tests/unit/test_browser_entrypoint.py` 4 条全绿（`--help`/`-h` 用法 + 退出 0、非法参数与缺参非零），并核对 usage 文本与解析器参数一致。
- AC-011：trust_prior——代码查证 Chrome 前提按套件判定、证据私有目录与脱敏集扩充、Selkies runner cap-drop 已落地；真实容器执行需 Docker，未复验。前提判定的范围问题见 f007。
- AC-012：re_verified——grep 查证 `config/.env.example` 已删且无代码/脚本/compose 消费者，根 `.env.example` 为唯一权威、秘密字段为空。
- AC-013：trust_prior——勘误数字抽查复算：交叉证伪 `^- f_` 计数 = 33、两份 bundle 的 sha256 与勘误所列一致、冻结 review 文件未被本 diff 改动；362 全量映射与 A13 计数未逐行独立复算。
- AC-014：re_verified——clock 注入（rate_limiter/policy 生产 diff 已读）、session_maker fixture 化、wait helper 复用逐项查证属实且相关套件通过；共享替身契约对照与采用面缺口见 f006，本条为部分达成。
- AC-015：trust_prior——同 AC-001，依赖 p027 冷构建与真实媒体证据（未开）；静态分阶守卫已重跑通过，证据形态问题见 f002。
- AC-016：re_verified——stamp v2 的必需输入拒绝生成、文件集增删致过期、env allowlist（空）均随 freshness 套件重跑通过，并 grep 确认前端无 `import.meta.env`/`VITE_` 消费；生成侧目录缺失缺口见 f008。
- AC-017：re_verified——独立重跑守卫套件，结果 1 failed / 5 passed（f001），且指纹范围内的豁免实现未做路径绑定（f004）；本条复验结论为未达成。
- AC-018：trust_prior——vendor pin+manifest 双校验、adapter_probe per-type/dropped 计数、perf_samples 证据字段均已代码查证，e2e collect-only 正常；真实性能预算执行需 Docker/Chrome 未复验，busy_timeout 部分另见 f003。

coverage = re_verified 9 / 18（AC-003、005、006、007、010、012、014、016、017；其中 006/007/014 含部分达成、017 为未达成，已逐条注明）
建议合并前人工抽查 trust_prior 项（trust_prior 占 9/18 = 50% > 30%，集中在 Docker/Chrome 真实环境、门禁空缓存重建与文档事实类 AC）

verdict: FAIL

## Round 2 (2026-11-04T06:25:09+08:00)

- round：2
- 复审范围：相对 anchor `597c09aff927c8cc54f72bfc405ac0336d58e22e` 的完整 diff 与 `git status --short`（未跟踪交付文件均已在 status 中可见，无 reviewer 不可见的交付文件）；重点核对 Round 1 修复增量，不采信 note.md「进度 5 / Review 处置」自述，均以 diff 与独立复跑为准。
- 复跑环境：`.scratch/t024/venv`（py3.12），`PYTHONPATH=src/backend:tests/fixtures`，`TMPDIR=/tmp/cbt024-r2c`（worktree 外）。

reviewed_scope: 018790f93eec1f3f

## Findings（Round 2 新发现）

无。本轮未发现新的 critical / important / minor finding；修复增量未引入可观测回归（见结论复跑证据）。

## 结论

- 前轮 finding 复核：
  - t024_code_f001（important）——已消除：`docs/archive/handoff.md` 当前 sha256 实测 `fc58792136c2a5b12ae446e5a7c89eb792394a9820c1350dae31117d478ff216`，与 `tests/unit/review_privacy_allowlist.txt:6` 登记指纹逐字一致；独立复跑 `tests/unit/test_repo_hygiene.py` 含于定向批次全绿（见下）。追加后内容已作为新批准存量重新登记，与守卫同批落地。
  - t024_code_f002（important）——已消除（口径层面）：`tests/unit/test_docker_build_contexts.py:3` 与 `tests/unit/test_runtime_image_hygiene.py:7` 均已标注「STATIC PRECHECK ONLY」；note.md 收尾报告明示 AC-001/AC-015 为 trust_prior、真实构建验收未验证，义务由 `docs/pending/todo/p027_t024_docker_image_real_build_verification.md` 承载（已核其内容覆盖隔离构建导入与冷构建+真实媒体两项）。静态守卫不再冒充 AC 验收证据；真实 Docker 验证仍未做，本轮不据此判 PASS，只确认「未验证状态已被如实披露并有追踪项」——与 Round 1 建议的处置路径一致。
  - t024_code_f003（important）——已消除：三处上界逐字恢复 anchor 原值——`tests/integration/test_v2_api_subprocess.py:820` 短锁 `1.4 <= elapsed < 4.5`、`:853` 长锁 `4.5 <= elapsed_timeout <= 6.5`、`tests/unit/test_domain_and_repository.py:478` WAL 读者 `elapsed < 1.0`，且 WAL 的「锁仍被持有」结构探针保留；独立复跑两文件共 28 passed（48.96s，含 busy_timeout 长锁用例在恢复后的 ≤6.5 上界内通过）。
  - t024_code_f004（important）——已消除：`tests/unit/test_repo_hygiene.py:90` `approved_snapshots` 返回 `set[tuple[str, str]]`，`:113` `is_approved_snapshot(name, data, approved)` 以 (path, sha256) 双绑定判定；合成用例 `test_snapshot_exemption_does_not_follow_content_to_a_new_path`（:197 起）验证同内容不同路径不豁免，且随守卫套件复跑通过。
  - t024_code_f005（important）——已消除：`docs/tasks/t024_delivery_verification_evidence/task.md:30-47` 18 条 AC 已全部按真实状态打勾；note.md 收尾报告已重写（删除创建期模板残留），明确 AC-001/AC-015 为 trust_prior 未验证、其余逐条给证据等级，与进度 1–5 段不再自相矛盾。
  - t024_code_f006（minor）——已消除：`tests/fixtures/docker_doubles.py` 新增 `FakeDockerAdapter`（生产同前缀命名）并被 `tests/integration/test_supervisor_observation_authority.py:25` 实际采用；`FakeDockerClient` 被 `tests/unit/test_docker_doubles_contract.py:30` 用作真实 DockerAdapter 的注入 client、`fake_docker_client()` 被 `FakeDockerAdapter` 内部调用，两导出均有真实调用方；未用的 `find_free_port` 导出已从 docker_doubles 删除；契约对照测试 3 条随定向批次复跑通过（Round 1 并发期出现的 `test_container_naming_matches_production` PathSecurityError 在当前树已不复现）。
  - t024_code_f007（minor）——已消除（主问题）：`tests/e2e/conftest.py` 的 freshness 钩子改按 `_item_consumes_dist`（探针 harness 标记）触发，非消费套件不再被陈旧 dist 阻断 collection；`tests/unit/test_frontend_build_freshness.py` 新增非消费负例 `test_e2e_collection_hook_ignores_stale_dist_for_non_consumers` 并随批次复跑通过，非 frontend 文件名消费者正例亦在。残留：主机 Chrome 前提仍用源码子串启发式判定，仅记未进表提示，不再计本条未修。
  - t024_code_f008（minor）——已消除：`scripts/verify_frontend_dist.py:50` 新增 `REQUIRED_DIRS = ("src",)`，`:88-93` 在 `frontend_input_manifest` 中对目录缺失与必需文件同等 `raise RuntimeError`，生成与校验共用同一 manifest 故两侧均拒绝；负例 `test_missing_src_directory_rejected_at_generation` 随 freshness 批次复跑通过。
- 本轮新发现：0 条。
- 复跑证据：从 `/tmp` 跨目录定向批次 `test_repo_hygiene + test_frontend_build_freshness + test_docker_doubles_contract + test_docker_build_contexts + test_runtime_image_hygiene` 共 31 passed；`test_v2_api_subprocess + test_domain_and_repository` 共 28 passed；unit 全量 747 passed / 1 skipped / 2 failed，2 条失败均为未被本 task 触及的 `tests/unit/test_stream_ice_config.py` 在非仓库 cwd 下读 CWD 相对路径所致（在仓库根目录单独复跑 4 passed，见未进表提示）；e2e collect-only 88 tests collected 无 collection 错误。
- 未进表的提示：①范围外观察——`tests/unit/test_stream_ice_config.py:20` 以 CWD 相对路径 `Path("config/docker/stream_runtime/entrypoint.sh")` 读文件，从非仓库目录运行 unit 全量时其 2 条 entrypoint 用例确定性 FileNotFoundError；该文件属 t019 范围、本 task diff 未触及，AC-006 在本 task 锚定文件内的跨目录问题（freshness conftest 加载）已经 `__file__` 锚定修复，故仅提示、不进 finding 表，建议由测试侧或 t019 后续收敛。②`tests/e2e/conftest.py` 的 `_item_needs_host_chrome` 与 `_item_consumes_dist` 均为源码子串启发式，注释/常量误提及会误判、间接构造会漏判，属 minor 级残留风险，当前有负例覆盖主场景，暂不阻断。③文件过大提示沿 Round 1 结论（本轮修复增量未新增超阈值文件）；圈复杂度无新增 ≥15 函数。
- 总体判断：Round 1 的 5 条 important 与 3 条 minor 均已按 diff 与独立复跑核实消除；AC-001/AC-015 的真实 Docker 构建验证仍未执行，但已如实标为未验证（trust_prior）并由 p027 承载，不再以静态证据冒充通过——本报告 PASS 仅针对代码/证据口径层面前轮 finding 的消除，不代表 p027 的真实构建义务已完成。前轮 blocker 全部消除、本轮无新 blocker，PASS。
- 系统性 follow-up：p027（AC-001/AC-015 真实 Docker 构建验证）继续承载；`test_stream_ice_config.py` 的 CWD 相对路径为范围外提示，无需在本 task 立项。

### AC 复验方式（Round 2 更新）

- AC-001：trust_prior——静态预检套件复跑通过，隔离构建证据依赖 p027（未开），本机无 Docker 无法复验；口径已如实披露（见 f002 复核）。
- AC-002：trust_prior——抽查 task.md 打勾、note.md 收尾报告与 handoff/勘误的一致性，文档事实全量逐项对照未独立重做。
- AC-003：re_verified——freshness 套件（含非消费负例、非 frontend 名消费者正例）从 `/tmp` 跨目录复跑通过。
- AC-004：trust_prior——同 Round 1 代码查证；完整 Gateway/Agent 客户端链路需 Docker/Chrome，未复验。
- AC-005：re_verified——同 Round 1 逐项查证；本轮 integration 批次（精确状态断言所在套件）复跑通过。
- AC-006：re_verified——freshness 套件跨目录复跑通过、normal_exit 用例在全量跑中通过；范围外残留见未进表提示①。
- AC-007：re_verified——三处时间上界逐字恢复并随 integration/unit 批次复跑通过（f003 复核），原上界重新能使超限实现失败。
- AC-008：re_verified——task.md/note.md 自述矛盾已消除（f005 复核），docstring 与覆盖对应同 Round 1 抽查。
- AC-009：trust_prior——查证 `scripts/run_gates.sh` 已改单 venv 从 `scripts/gate-requirements.txt` 锁安装且解释器 pin Python 3.12、锁含 playwright/cloakbrowser 全 pin；空缓存全量重建未独立复跑，依赖实施侧记录。
- AC-010：re_verified——同 Round 1（entrypoint 套件在 unit 全量中通过）。
- AC-011：trust_prior——前提作用域修复已代码查证并有负例（f007 复核）；真实容器执行需 Docker，未复验。
- AC-012：re_verified——同 Round 1 grep 查证结论，本轮 diff 未回退。
- AC-013：trust_prior——勘误 t009 路径已改归档实际路径（代码侧抽查属实）；数字全量复算未独立重做。
- AC-014：re_verified——共享替身契约对照 3 passed、observation 套件采用 FakeDockerAdapter、wait_until/wait_until_sync 超时错误已补 `last=`（`tests/fixtures/wait.py:38,103`）。
- AC-015：trust_prior——同 AC-001，依赖 p027 冷构建与真实媒体证据。
- AC-016：re_verified——stamp 必需目录负例与文件集增删负例随 freshness 批次复跑通过（f008 复核）。
- AC-017：re_verified——守卫套件复跑全绿，指纹登记与文件实测哈希一致，双绑定与段边界负例通过（f001/f004 复核）。
- AC-018：trust_prior——busy_timeout 上界恢复部分已 re_verified（见 AC-007）；真实性能预算执行需 Docker/Chrome，未复验。

coverage = re_verified 10 / 18（AC-003、005、006、007、008、010、012、014、016、017；AC-017 由未达成转为通过、AC-007/014 由部分达成转为完整）
建议合并前人工抽查 trust_prior 项（trust_prior 占 8/18 ≈ 44% > 30%，集中在 Docker/Chrome 真实环境、门禁空缓存重建与文档事实类 AC；其中 AC-001/AC-015 的真实构建义务明确未完成、由 p027 承载）

verdict: PASS

## Round 3 (2026-11-04T06:27:35+08:00)

- round：3
- 复审范围：定向复审 Round 2 之后的两处增量（其余交付内容沿 Round 2 结论，指纹已过期故不重开全量评审）：(1) `tests/unit/test_docker_doubles_contract.py` 按 test 侧 f011 补 docker SDK `ContainerCollection` 双侧行为矩阵；(2) `tests/unit/test_stream_ice_config.py` 按 Round 2 未进表观察改 `__file__` 锚定。以当前 worktree 文件实读、相对 anchor 的 `git diff` 与独立复跑为准，不采信 note.md「进度 6」自述。
- 复跑环境：`.scratch/t024/venv`（py3.12），`PYTHONPATH=src/backend:tests/fixtures`，`TMPDIR=/tmp/cbt024-r3c`（worktree 外）；跨目录复跑时 PYTHONPATH 改用等价绝对路径。

reviewed_scope: 80f9ed5b1772c829

## Findings（Round 3 新发现）

无。本轮未发现新的 critical / important / minor finding；两处增量均未引入可观测回归（见结论复跑与核对证据）。

## 结论

- 前轮事项复核（本轮范围内）：
  - t024_test_f011（test 侧 minor，code 侧关联 AC-014）——增量属实且方向正确：`tests/unit/test_docker_doubles_contract.py:51-71` 新增 `_sdk_containers()`，仅 stub docker SDK 的 api 层两点（`inspect_container` 缺失时按 SDK 自身语义抛 `NotFound`、`containers` 返回空列表），`ContainerCollection` 本体为真实 SDK 代码；`:74-79` 同一行为矩阵（get 缺失抛 `NotFound`、list 空集 `== []`）对替身侧与 SDK 侧各跑一遍，不再是替身单侧断言。与本机 venv 及门禁锁一致的 docker 7.2.0 源码核对：`ContainerCollection.get` 直调 `client.api.inspect_container` 并透传 `NotFound`、`list` 以全 kwargs 调 `client.api.containers(...)` 后逐项 `get`，stub 的签名（位置参数 inspect、kwargs-only containers）与真实调用形态相符，未掩盖被测逻辑。present 情形（staged container 的 get/list/labels/status）仍只在替身侧断言，但已与双侧矩阵分段书写、注释明示「Present container on the double」，且 labels/status 本为 `FakeContainer` 自身属性形态、SDK `Container` 形状不同，不构成名实不符。
  - Round 2 未进表观察①（`test_stream_ice_config.py` CWD 相对路径）——已按观察修复：该文件 `:16-19` 改为 `Path(__file__).resolve().parents[2] / "config/docker/stream_runtime/entrypoint.sh"`，与仓内既有锚定先例（`tests/unit/test_repo_hygiene.py:10`、`test_frontend_build_freshness.py:113` 同式 `parents[2]`）一致，parents 索引按文件实际深度（tests/unit → 仓根）正确；文件内无其他 CWD 相对路径残留。此改动属 AC-006「测试可从其他工作目录运行」口径内的同模式收敛，未触及 t019 的 ICE 行为断言本身（四条断言内容与 anchor 逐字未变，仅路径来源变更）。
  - Round 2 的 code 侧 finding f001–f008 已于 Round 2 全部核实消除，本轮两处增量未触及其实实现文件（隐私守卫、stamp、freshness 钩子、busy_timeout 上界等均不在增量内），无回退迹象；本轮不重开其复核。
- 本轮新发现：0 条。
- 复跑证据：跨目录（cwd=`/tmp`、绝对路径调用）定向批次 `test_docker_doubles_contract + test_stream_ice_config` 共 7 passed，其中 ice 套件 4 passed——Round 2 时从非仓库目录运行确定性失败的 2 条 entrypoint 用例不再复现；仓根按指令口径复跑同两文件加 `test_supervisor_observation_authority` 共 10 passed，共享替身的实际消费方未受契约对照改动影响。
- 未进表的提示：①`test_docker_doubles_contract.py` 为未跟踪交付文件（`git status` 仍示 `??`、未经 `git add -N`），相对 anchor 的 `git diff` 不直接呈现其内容；本轮以文件系统实读为准完成评审，指纹已按含未跟踪文件的口径写入本轮 `reviewed_scope`，与 Round 2 处理一致，仅提示实施方在 finish 前留意其入库状态。②文件过大：两增量文件分别为 89 行与 86 行，均远低于测试源码 600 行提示线；圈复杂度无 ≥10 函数。③安全/契约/性能七视角就两处增量扫过：均为测试文件内变更，无生产代码、无外部输入、无新增依赖（docker SDK 已由 `scripts/gate-requirements.txt:25` 与各 runtime requirements 锁定 7.2.0），未命中。
- 总体判断：两处增量解决了其各自针对的问题（f011 双侧矩阵、AC-006 跨目录锚定），未引入新问题，本轮无未解决 critical / important，PASS。本 PASS 仅针对 Round 3 定向范围；AC-001/AC-015 的真实 Docker 构建义务仍由 p027 承载、未验证状态不变（沿 Round 2 结论）。
- 系统性 follow-up：无（p027 沿既有承载，不重复立项）。

### AC 复验方式（Round 3 定向更新）

- AC-006：re_verified——ice 套件改 `__file__` 锚定后从 `/tmp` 跨目录独立复跑 4 passed，原 CWD 依赖失败消除，为本条在 Round 2 范围外残留提示的闭合证据。
- AC-014：re_verified——契约对照增至双侧矩阵后独立复跑 3 passed（`test_docker_doubles_contract`，含于上述 7 passed 批次），且 SDK 7.2.0 的 `ContainerCollection.get/list` 源码与 stub 调用形态已逐项核对；observation 消费方 3 passed 随仓根批次复跑通过。
- 其余 AC：沿 Round 2 复验结论（本轮增量未触及，不重新计入本轮 coverage 分子/分母口径调整）。

coverage = re_verified 2 / 2（本轮定向范围涉及的 AC-006、AC-014；其余 16 条沿 Round 2 的 coverage = re_verified 10 / 18 与 trust_prior 披露不变）
建议合并前人工抽查 trust_prior 项（沿 Round 2 提示：AC-001/AC-015 须待 p027 完成后才可称验收通过）

verdict: PASS

## Round 4 (2026-11-04T06:32:10+08:00)

- round：4
- 复审范围：recovery 定向复审。仅核 Round 3 双路 PASS（彼时 reviewed_scope 为 80f9ed5b1772c829）之后导致指纹 stale 的三项流程性增量，其余交付内容沿 Round 2 / Round 3 结论，不重开全量评审：(1) `tests/unit/review_privacy_allowlist.txt` 追加 4 条登记；(2) `note.md` 的 Review 处置改检查器表格格式；(3) `task.py finish` 把任务目录归档到 `docs/archive/tasks/t024_delivery_verification_evidence/`。以当前 worktree 文件实读、相对 anchor 的 `git diff`、指纹独立重算与守卫独立复跑为准，不采信实施侧自述。
- 落点校验：`git rev-parse --show-toplevel`（不带 `-C`，workdir 为仓库根）输出与预期仓库根精确一致。
- 复跑环境：`.scratch/t024/venv`（py3.12），`PYTHONPATH=src/backend:tests/fixtures`，`TMPDIR=/tmp/cbt024-r4c`（worktree 外）。

reviewed_scope: 831bbb2a2638ea28

## Findings（Round 4 新发现）

无。本轮未发现新的 critical / important / minor finding；三项增量均未改变交付语义（见结论逐项核对）。

## 结论

- 前轮事项复核（本轮范围内）：
  - 增量 (1) allowlist 登记——属实且无语义扩大：追加的 4 条位于 `tests/unit/review_privacy_allowlist.txt:63-66`，是两份 review 报告在原路径与归档路径各一条，均为精确的 (path, sha256) 双绑定条目，无目录级或通配豁免。追加前工作树上独立实算：归档路径下 `review_code.md` 的 sha256 为 `df03af7cc0c103146dc1c1621235ab5825e40b6733bc744c59af74aa2f150c5a`、`review_test.md` 为 `5289df460fa709a16dd29765064b12a77fdd0b4f3b5b04c9a0c2eb08b92cc5d8`，与 allowlist 第 64、66 行登记逐字一致；原路径第 63、65 行登记的指纹与归档路径完全相同，证明两份报告在归档移动中字节不变、仅登记随路径同步。被豁免内容即 Round 3 已审的报告字节本身，未引入新内容豁免。
  - 增量 (2) note.md 处置格式——内容等价：`docs/archive/tasks/t024_delivery_verification_evidence/note.md` 的 Review 处置已改为检查器要求的表格（表头 `finding_id|status|fix_ref`），共 19 行，完整覆盖 code 侧 f001–f008 与 test 侧 f001–f011，状态均为「已修」且每行 fix_ref 与进度 5 / 进度 6 叙述及 Round 2 / Round 3 复核结论一致；无 finding 遗漏、无状态改写。`check_review_status.py` 对归档目录的解析在本小节追加前给出 code_verdict=PASS、test_verdict=PASS，处置表可被检查器正常读取，彼时 overall=INCOMPLETE 仅由 review_scope=stale 导致。
  - 增量 (3) 归档移动——位置变更、内容不变：原 `docs/tasks/` 下该任务目录已不存在，归档目录含 `task.md`、`note.md`、`review_code.md`、`review_test.md`、`handoff.json` 五件，note.md front matter 的 status 为 done；两份 review 报告的字节不变已由增量 (1) 的双路径同指纹独立证明。指纹规范化逻辑将原路径与归档路径的任务文件映射为同一逻辑路径且排除 review 流程文件，故移动本身不改变交付语义——reviewer 分别以原任务路径与归档路径为 task-dir 参数独立重算指纹，两次结果均为本轮写入的 reviewed_scope，与派审给定值逐字一致，亦证明当前 stale 仅源于增量 (1) 的 allowlist 登记（该文件不在指纹排除之列），而非交付内容漂移。
  - Round 1–Round 3 的 code 侧 finding f001–f008 已于 Round 2 / Round 3 全部核实消除；本轮三项增量除 allowlist 登记外未触及其实实现文件（隐私守卫逻辑、stamp、freshness 钩子、busy_timeout 上界等均不在增量内），无回退迹象，本轮不重开其复核。
- 本轮新发现：0 条。
- 复跑证据：在本小节追加前的工作树上（即本轮被审状态）独立复跑 `tests/unit/test_repo_hygiene.py`，结果 8 passed；被审两份 review 文件在归档路径的实算指纹与 allowlist 登记逐字一致（见增量 (1)）；`git status --short` 在追加前为空，工作树无 reviewer 不可见的未跟踪交付文件。
- 未进表的提示：无。文件过大与圈复杂度就本轮增量不适用（三项增量为登记文本、表格格式与文件移动，无源码或测试逻辑变更）；安全 / 正确性 / 契约 / 性能 / 架构 / 健壮性 / 文档七视角就三项增量扫过，allowlist 新增条目仍为精确 (path, sha256) 双绑定、未放宽 AC-017 的豁免边界，其余未命中。
- 总体判断：三项流程性增量逐项核实均未改变交付语义，Round 3 的 PASS 结论在新指纹下恢复有效；本轮无未解决 critical / important，PASS。本 PASS 沿 Round 2 / Round 3 口径：AC-001 / AC-015 的真实 Docker 构建义务仍由 p027 承载、未验证状态不变。
- 系统性 follow-up：无（p027 沿既有承载，不重复立项）。

### AC 复验方式（Round 4 定向更新）

- AC-017：re_verified——本轮增量 (1) 与 (3) 直接相关：两份 review 文件在归档路径的 sha256 与 allowlist 登记逐字一致、原路径与归档路径同指纹证明移动字节不变、新增条目为精确双绑定未扩大豁免；守卫套件在本小节追加前的被审工作树上独立复跑 8 passed。
- 其余 AC：本轮增量未触及（note.md 处置表格仅为流程格式、内容等价，已逐行核对），沿 Round 3 复验结论与 Round 2 的全量 coverage / trust_prior 披露不变。

coverage = re_verified 1 / 1（本轮定向范围涉及的 AC-017；其余 17 条沿 Round 2 的 coverage = re_verified 10 / 18 与 trust_prior 披露不变）
建议合并前人工抽查 trust_prior 项（沿 Round 2 / Round 3 提示：AC-001 / AC-015 须待 p027 完成后才可称验收通过）

verdict: PASS

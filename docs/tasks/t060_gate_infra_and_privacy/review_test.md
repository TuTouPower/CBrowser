# Task review t060（reviewer_focus: 测试）

- task：`t060_gate_infra_and_privacy`
- spec：`docs/tasks/t060_gate_infra_and_privacy/task.md`
- diff_anchor：`12380b25a51fc0dc51a7b00306e93684715f6b3f`
- target：`git diff 12380b25a51fc0dc51a7b00306e93684715f6b3f`（在 `<repo>` 检查完整 worktree diff，包含 intent-to-add 交付）
- round：1
- reviewed_at：2026-11-12T00:41:24+08:00

reviewed_scope: efd671641d478eb5

## Findings

### t060_test_f001 - 环境引导失败未被证据复用测试覆盖，旧 PASS 留在新运行目录

- 严重度：important
- 锚点：行为缺陷。复用含成功 manifest 的 evidence 目录，venv 创建或安装失败，新 run.json 与旧 all_passed=true 同时留存，下游读证据得到过期成功。
- 位置：`scripts/gate_run.py:122`、`scripts/gate_run.py:131`；测试缺口位于 `tests/unit/test_t028_run_gates_evidence.py:230`。
- 问题：现有 evidence 复用测试只驱动成功 bootstrap；PATH uv 桩不能返回失败。新入口先更新 run.json，随后进入 gate_environment；uv 非零抛异常，未启动 Bash，旧 manifest 清理和失败 manifest 生成均不可达。本轮独立复制当前 gate_run 与 requirements 到 `.scratch/t060/test_review_bootstrap/repo/`，预置 prior-run/all_passed=true，并让 PATH uv exit 42：入口 exit 1，但 manifest 仍为 prior-run/all_passed=true，run.json 已变为新 UUID。复现结果保存于 `.scratch/t060/test_review_bootstrap/result.json`。进程退出码失败不能消除持久证据假绿。
- 建议：在 bootstrap 前建立本轮证据生命周期，初始化或失败时写入同一 run_id 的失败 manifest；补实际入口 PATH uv 失败回归，覆盖 venv 创建与 pip 安装两阶段、空目录与含旧 PASS 的复用目录，并核对本轮非零退出与 manifest 非成功。

### t060_test_f002 - 脱敏验证只查家路径，未防止路径外历史元数据被吞

- 严重度：minor
- 锚点：测试/文档。隐私脱敏应保留路径外历史语义，当前改写损坏 branch/base 描述。
- 位置：`docs/archive/handoff.md:100`、`docs/archive/handoff.md:164`；`tests/unit/test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths`。
- 问题：对照 base，原 t005 路径后 `branch=t005_v2_supervisor，base` 已消失，新文成为 `worktree **<repo>/diff_anchor=...`；t004 同样只剩 `<repo>/diff_anchor`。这些内容不是家路径。hygiene 负向扫描只能证明路径消失，不能发现替换越过中文标点/Markdown 边界，导致历史元数据丢失。
- 建议：从 base 恢复路径外文本，仅替换路径 token；用含中文逗号、括号、Markdown 包裹的样例验证替换前后非路径文本不变，并扫同批替换。

## 验证与危险模式扫描

- 已核对完整交付清单、源码和测试 diff、未跟踪状态、契约区 13 条 AC；当前新增交付文件均可见。文档变化含家路径占位符改写、旧交接节迁移与 Markdown 格式闭环，隐私检查实际扫描完整 tracked 与未忽略新文件。
- 独立运行边界、并发、接线、hygiene、cleanup、artifact forwarder 与静态构建上下文集：`91 passed in 18.76s`。命令使用 `.scratch/gate_venv/bin/python`、`PYTHONPATH=src/backend:tests/fixtures`，basetemp 位于 `.scratch/t060/test_review_basetemp`。
- 独立运行原生 BuildKit 用例 `tests/e2e/test_native_build_contexts_e2e.py`：`5 passed in 12.07s`。每个镜像均先验证允许输入可以 COPY，再验证 bytecode、私有数据、私有配置不能 COPY；Supervisor 额外拒绝非 COPY services 文件。此证据不依赖自制 Dockerignore 匹配器。
- 独立运行 evidence、probe verdict、image identity、image packages 回归集：`48 passed in 9.46s`，basetemp 位于 `.scratch/t060/test_review_secondary`。本轮合计 `144 passed`。
- 独立 required collection：移除全部 `CBROWSER_*` 镜像变量后，`test_native_build_contexts_e2e.py` 收集成功；`test_supervisor_resource_capacity_e2e.py` exit 2，报缺少 `CBROWSER_STREAM_TEST_IMAGE`，未要求 API 镜像。单模块前置粒度与缺声明镜像失败均实际触达 collection hook。
- 核验 K/J 原始 manifest 与 JUnit：两轮 `all_passed=true`、`cleanup_exit_code=0`；各自 unit 1651、integration 196（178 passed / 18 skipped）、contract 258（257 passed / 1 策略 skip），K E2E 105（103 passed / 2 独立探针 skip）。两个 run.json 至 manifest 的时间区间重叠；不同 run_id 可核对。未重新运行全量门禁，K/J 属实施期保留证据。
- 核验 `.scratch/t060/probe_evidence_k/`：外层 2 passed / 0 skipped，内部 chain 16 passed / 0 skipped，L0–L5、L6_cdp_input、L6_xtest_input 各 5 个样本。额外 `.scratch/t060/baseline_chain_fixed/chain.xml` 为 18 passed / 0 skipped；版本证据分别为独立 Chromium 156 与目标引擎 146。补验在容器运行，不声明宿主具备 Xvfb 或普通 Chromium。
- 恒真、纯存在性冒充 AC、注释断言、独占、错误静默、条件绕过、交互赋值替代：新增或修改测试未发现相关假绿。`pytest.raises`、HTTP 请求捕获与 Docker API 桩用于边界输入，核心 forwarder、shell orchestration、文件锁、CLI verdict 与 BuildKit 实际执行。
- skip 扫描：既有 optional probe 与 Docker 条件 skip 仅加入镜像 marker，未新增跳过条件。K 中两项 optional probe 已由独立 real_engine 重跑；18 项宿主依赖 skip 有容器补验；contract 一项为既有项目验证策略不适用检查，不能算宿主已执行。
- 删除测试扫描：旧隐私豁免、名称前缀清理契约随 spec 明确删除；新测试改验无标签/未知租约不删、活跃租约保留、结束租约删除与查询失败。源码字符串接线检查改由真实脚本 PATH 桩、退出码、manifest 和前置顺序 mutation 验证；嵌套全量 collection 删除由 suite 用例下限及真实门禁 JUnit 补回。未删除关键行为覆盖。
- 既有真实链夹具改测归因可从生产契约核对：UDS 使用当前 socket_root/instance 路径，数据库绑定同一运行实例，HTTPS origin 与 Secure cookie 一致。三份 integration 链原有 235 条 assert 全部原样保留，未改预期输出。`test_runtime_coordinator_integration.py` 改为等待异步 stopped 状态写入后执行原断言，未延长既有 timeout。
- 本地 session/media profile 关闭公共 GeoIP，只隔离外部依赖；公共 GeoIP 不是这些测试目标。quota 链暂停自有 bootstrap Supervisor，避免与宿主生产 ResourceMonitor/client 同时向同一 Gateway 写 quota；pause 前校验归属，finally unpause 后 cleanup，原配额帧、恢复、几何与 CPU 策略断言保留。X11 权限测试改从真实 Linux mount 设置漂移并观察 `0700/0711 → 0750`，不再把 macOS 宿主映射视为 Linux 权限真值。
- 七视角已扫描：安全（隐私与租约）、正确性（失败封闭）、契约/Breaking（新归属契约与镜像声明）、性能/资源（锁与清理）、架构/可维护性（边界桩替代源码匹配）、健壮性/可观测（完整 manifest、Docker 错误）、测试/文档/规格（13 条 AC、用例下限、真实补验边界）；发现 bootstrap 证据复用失败路径缺口，详见 t060_test_f001；历史文档非路径文本损失见 t060_test_f002。

## 结论

- 改测方向复核：无迁就实现输出的改测；本轮变更保留真实链断言，修正过时夹具、异步观察时点与环境隔离，规格变更由新命名测试/新契约用例承接。
- 本轮新发现：2 条（important 1、minor 1）。
- 未进表的提示：K/J、真实 probe 与 quota 端到端过程未在本轮全量重跑；已独立检查原始证据与断言，报告不把这些证据误记为本轮执行记录。真实 Docker 活跃租约保护原始证据见 `.scratch/t060/final_live_lease_proof.json`；本轮另重跑实际文件锁与清理决策测试。
- 总体判断：13 条 AC 各有相应可信验证，但环境引导失败可遗留过期成功证据，存在未解决 important，本轮 FAIL。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立运行 `test_repo_hygiene.py` 全树扫描通过；diff 删除清单与 fingerprint 放行函数，安全口径覆盖 archive 与新文件。
- AC-002：TICK-VALID，re_verified。独立运行终止用户名/单双引号/路径后缀矩阵及临时 Git 仓未跟踪枚举用例，ignored 文件排除。
- AC-003：TICK-VALID，re_verified。独立运行两个真实 gate 脚本进程共享 cold venv、warm readers 与 stale rebuild 等待用例，双方完成且只重建一次；另核验 K/J 重叠运行原始证据。
- AC-004：TICK-VALID，re_verified。独立运行真实 flock 活跃租约保护与 container/network 相同归属决策用例；核验真实 Docker proof 三项为 true，无名称放行回退。
- AC-005：TICK-VALID，re_verified。独立运行仅 stream 残留负例与 Docker API 异常负例，停止 predicate 实际返回 false 或抛错；E2E 调用该 predicate。
- AC-006：TICK-VALID，re_verified。独立运行五 suite 下限边界、脚本低收集数、缺 image_packages 变量及 protocol failure 用例，核验非零退出与完整失败 manifest。
- AC-007：TICK-VALID，re_verified。独立调用 evidence main，非法 image ID 与错误 arch 均返回 1；shell 与 CLI 使用相同 preflight 函数。
- AC-008：TICK-VALID，re_verified。独立运行实际修改脚本前置位置的 mutation 用例，顺序 oracle 拒绝；diff 确认 unit 内旧嵌套全量 collection 已删除。
- AC-009：TICK-VALID，re_verified。独立 required-mode collection 核验空镜像模块可收集、stream 模块缺声明变量失败且不要求 API；未声明回退全集用例亦通过。
- AC-010：TICK-VALID，re_verified。独立运行 Node 26.0.0 与 `>26.0.0` 边界、非法 marker CLI 负例及完整目标键检查，均失败封闭。
- AC-011：TICK-VALID，re_verified。独立运行五镜像原生 BuildKit 正反例与 Supervisor services COPY 集合相等检查，5 项原生用例全通过。
- AC-012：TICK-VALID，re_verified。独立运行生产 forwarder，绝对路径/嵌套路径得到精确 `/exchange/downloads/...`；三种逃逸无 API 请求并进入 path_escape dead-letter。
- AC-013：TICK-VALID，re_verified。人工核验 `docs/handoff.md` 只有最新一个二级节；实际 branch 为 `t060_gate_infra_and_privacy`、HEAD 为 diff_anchor，与写入时记录一致。

coverage = 13 / 13

verdict: FAIL

## Round 2 (2026-11-12T05:04:10+08:00)

reviewed_scope: c899ece7b48f99a1

### Findings

本轮无新 finding。

### 前轮 finding 复核与验证

- `t060_test_f001` 已消除。`scripts/gate_run.py` 在写新 run.json 前撤掉旧 manifest，使用 ExitStack 在持 checkout/运行租约期间进入 venv 事务；venv 创建或 pip 安装失败生成本轮 run_id 的 environment failed manifest，原子替换成功文件，日志只记异常类型/退出码，不复制命令输出、路径或凭据。新增 `test_bootstrap_failure_replaces_stale_success_evidence[venv/pip]` 通过真实 Bash/Python 入口及 PATH uv 失败桩验证非零退出、all_passed=false、manifest/run.json 相同且不同于 prior-run 的 run_id、失败 suite 与可读日志；没有 mock 掉 gate_environment 或 manifest 写入逻辑。本轮两个负例均独立重跑通过。
- `t060_test_f002` 已消除。对照 base，`docs/archive/handoff.md:100` 的 `branch=t005_v2_supervisor，base/diff_anchor=...`、`:164` 的 t004 branch/base 以及中文标点、Markdown、worktree 后缀完整恢复，仅机器前缀成为占位符。独立重算 `.scratch/t060/precise_privacy_restore.json` 中 65 份 archive 当前 SHA256，全匹配；另从 Git base 重新生成精确前缀替换内容并检查非路径字节，旧交接一节按要求附加。替换只用于一次性历史修复，未增加隐私豁免逻辑。
- 新增 URL/file URI 回归可信：GitHub 源码 URL 的 `/routes/home/components/` 不再被当开发者家路径；bare home、`file://`、`file://localhost` home 仍命中。新增测试追加正反例，未修改旧路径负例预期；本轮与全树 hygiene 一起独立重跑通过。公开链接所在 `docs/reviews/review_20261108_153337/adoption_decision.md` 相对 base 无 diff，已恢复原始引用；本轮未重新访问外站，不把既有 HTTP 200 记作本轮实测。
- 本轮独立重跑完整相关 unit 合集：`142 passed in 51.61s`，涵盖 t060 boundaries/concurrency/wiring、repo hygiene、cleanup、download reconciler、Docker contexts、gate evidence、probe evidence、image identity、image package 校验。使用既有 `.scratch/gate_venv/bin/python` 与 `PYTHONPATH=src/backend:tests/fixtures`，basetemp 为 `.scratch/t060/test_review_round2_basetemp`。
- 本轮独立重跑原生 BuildKit 五镜像正反例：`5 passed in 14.90s`；允许 COPY 成功，bytecode/私有数据/私有配置及 Supervisor 非 COPY services 输入均拒绝。合计 `147 passed`。required collection 另行实跑：空镜像声明模块 exit 0，stream 声明模块无变量 exit 2，错误仅要求其 stream 镜像、没有要求 API 镜像。
- 独立读取 L/M 原始 manifest 与 JUnit：均 all_passed=true、cleanup_exit_code=0；unit 均 1654 passed，integration 均 178 passed / 18 宿主依赖 skipped，contract 均 257 passed / 1 既有策略 skipped；L E2E 103 passed / 2 optional probe skipped。两个 optional probe 在 `.scratch/t060/probe_evidence_l/` 单独实跑为 2 passed / 0 skipped，内部 chain 16 passed；L0–L5、L6_cdp_input、L6_xtest_input 各 5 个样本。此处审查实施期原始证据，本轮没有重新执行完整 L/M 或重探针。
- `.scratch/t060/baseline_chain_fixed/chain.xml` 18 passed / 0 skipped；版本分别为独立 Chromium 156 与目标 146。对 `final_source_hashes.json` 140 份生产源码/链用例独立重算，全部与当前交付一致。容器补验没有变成宿主环境验证，不宣称 Mac 安装了 Xvfb。
- 完整 diff 继续保留三份 integration 链 235 条原 assert；quota 链帧率、恢复、几何、CPU 断言与 timeout 没有放宽。修复仍为当前 UDS/实例/HTTPS 夹具、公共 GeoIP 隔离，以及归属校验后的自有 bootstrap Supervisor pause/finally unpause。bootstrap 失败修复新增测试，不改旧失败预期。
- 危险模式再次核查：无新增 skip/only、恒真、删关键断言、错误静默、容差/timeout 扩大或条件绕过。旧名称前缀清理、隐私指纹豁免用例删除对应已批准契约变更；旧源码字符串接线与嵌套全量 collection 删除，已有真实脚本 PATH 桩、mutation、用例下限及完整 JUnit 承接。Round 2 增量未改变这些替代验证。
- 七视角复扫：安全/隐私、正确性、契约、资源/并发、测试结构、失败可观测、文档/规格均已核查，未见新阻断问题。

### 结论

- 前轮 finding 复核：f001、f002 均已消除，非换形式弱化。
- 改测方向复核：无迁就当前实现输出的改测；新增 bootstrap/URI 负例触达真实入口或实际扫描实现，旧行为断言保留。
- 本轮新发现：0 条。
- 未进表的提示：完整 L/M、真实活跃 Docker 保护与容器补验过程未在本轮全量重跑；已查原始证据、生产逻辑与当前测试断言。文件锁、清理决策、bootstrap 失败及原生 BuildKit 均本轮独立重跑。
- 总体判断：前轮阻断消除，13 条 AC 有可信验证，当前无未解决 critical / important。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。当前全树 hygiene 独立通过，隐私清单和 fingerprint 豁免已删除；65 份 archive 精确脱敏结果独立核对。
- AC-002：TICK-VALID，re_verified。终止用户名、单双引号、未跟踪枚举、bare/file URI home 负例本轮通过，公开 URL home 路径正例通过。
- AC-003：TICK-VALID，re_verified。两个真实 gate 脚本进程共用 cold venv、warm reader 与 stale rebuild 等待用例本轮独立通过，锁事务未被 mock。
- AC-004：TICK-VALID，re_verified。真实 flock 活跃租约与容器/网络清理选择本轮通过；实际清理按 run_id/租约拒绝活跃和未知归属，已检查真实 Docker 保留证据。
- AC-005：TICK-VALID，re_verified。本轮 stream 单独残留返回未停止、Docker API 异常抛错负例通过，停止 E2E 调用该实际 predicate。
- AC-006：TICK-VALID，re_verified。本轮各 suite 下限、脚本低收集数、缺 image_packages 变量及 protocol failure 完整 manifest 回归通过，bootstrap 旧 PASS 负例也通过。
- AC-007：TICK-VALID，re_verified。本轮非法 ID/错误 arch CLI 负例与既有 probe evidence 集通过，共用 preflight 校验未绕过。
- AC-008：TICK-VALID，re_verified。本轮真实修改脚本前置位置的 mutation 被顺序 oracle 拒绝；diff 未恢复嵌套 unit 全量 collection。
- AC-009：TICK-VALID，re_verified。本轮独立 required collection 验证仅声明镜像前置与缺失 exit 2；未声明全集回退测试通过。
- AC-010：TICK-VALID，re_verified。本轮 Node 26.0.0 对严格 `>26.0.0` 拒绝、非法 marker CLI 非零、目标 marker 键完整性与包比较回归通过。
- AC-011：TICK-VALID，re_verified。本轮五镜像原生 BuildKit 5 passed，Supervisor services COPY 集合与字节码排除静态检查同时通过。
- AC-012：TICK-VALID，re_verified。本轮生产 forwarder 精确路径输出、嵌套路径与三类绝对路径越界零请求/dead-letter 负例通过。
- AC-013：TICK-VALID，re_verified。人工核对 handoff 单个二级节，当前 branch 与 HEAD 分别为记录分支和 `12380b25a51fc0dc51a7b00306e93684715f6b3f`，与写入时快照一致。

coverage = 13 / 13

verdict: PASS

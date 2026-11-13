# Task review t060（reviewer_focus: 代码）

- task：`t060_gate_infra_and_privacy`
- spec：`docs/tasks/t060_gate_infra_and_privacy/task.md`
- diff_anchor：`12380b25a51fc0dc51a7b00306e93684715f6b3f`
- target：`git -C '<repo>' diff 12380b25a51fc0dc51a7b00306e93684715f6b3f`
- round：1
- reviewed_at：2026-11-12T00:43:13+08:00

reviewed_scope: efd671641d478eb5

## Findings

### t060_code_f001 - 脱敏吞掉路径外历史状态与分支信息

- 严重度：minor
- 锚点：文档与规格一致性；A53 只授权将家目录路径改为占位符，路径外历史事实应保留。
- 位置：`docs/archive/handoff.md:100`、`:164`、`:217`、`:222`、`:308`、`:343`、`:359`、`:376`、`:415`、`:425`；`docs/archive/tasks/t004_v2_stream_runtime/progress.md:29`；`docs/archive/tasks/t005_v2_supervisor/progress.md:52`。
- 问题：相对 diff_anchor 的逐行对比证实，替换跨过路径边界，删除了原有元数据或状态文字。以下原句片段均已将真实家路径替换为 `<original_worktree>`，避免报告重新引入隐私。

|位置|原句片段（路径已占位）|当前片段|
|---|---|---|
|archive/handoff:100|`**<original_worktree>**，branch=t005_v2_supervisor，base/diff_anchor=84f843…`|`**<repo>/diff_anchor=84f843…`|
|archive/handoff:164|`<original_worktree>，branch=t004_v2_stream_runtime，base/diff_anchor=8ff9fd…`|`<repo>/diff_anchor=8ff9fd…`|
|archive/handoff:217|`原登记<original_worktree>已exact cleanup`|`原登记<repo> cleanup`|
|archive/handoff:222|`<original_worktree>，branch=t003_v2_browser_runtime，base/diff_anchor=226c84…`|`<repo>/diff_anchor=226c84…`|
|archive/handoff:308|`worktree=<original_worktree>）——暂停记录点`|`worktree=<repo>`|
|archive/handoff:343|`t006 WT（<original_worktree>）、E2E lane WT（<original_worktree>，分支 lane/t006_e2e2`|`t006 WT（<repo> lane WT（<repo> lane/t006_e2e2`|
|archive/handoff:359|`WT <original_worktree>，分支 lane/t006_e2e2`|`WT <repo> lane/t006_e2e2`|
|archive/handoff:376|`验证 WT <original_worktree>，候选 98 文件`|`验证 WT <repo> 98 文件`|
|archive/handoff:415|`worktree=<original_worktree>，diff_anchor=077778f；attempt1 / execution_id=`|`worktree=<repo> / execution_id=`|
|archive/handoff:425|`WT <original_worktree>，日志`|`WT <repo>`|
|archive/tasks/t004…/progress:29|`登记worktree=<original_worktree>，已claim，不重复start/reserve`|`登记worktree=<repo>/reserve`|
|archive/tasks/t005…/progress:52|`登记WT=<original_worktree>，已reserve/claim`|`登记WT=<repo>/claim`|

- 影响：历史 handoff 的分支、基准、attempt 与登记状态不再忠实于原记录；局部 Markdown 括号和加粗边界也被破坏。未观察到当前任务机器状态变化，因此不升为 blocker。
- 建议：从 diff_anchor 原文恢复这些行，按精确家目录或仓库前缀替换，仅修改实际路径，保留标点及其后全部文字。

### t060_code_f002 - venv bootstrap 失败保留上一轮 all_passed manifest

- 严重度：important
- 锚点：可观测行为缺陷；复用证据目录时，新门禁环境准备失败，证据仍显示上一轮成功，违反证据不得复用旧成功结果的既有行为。
- 位置：`scripts/gate_run.py:122`、`scripts/gate_run.py:131`；旧证据清理实际位于后续 `scripts/run_gates.sh:219`。
- 问题：venv 检查、重建和安装已移到 Python 包装器。包装器先覆盖 `run.json`，随后进入 `gate_environment`；`uv venv` 或 `uv pip install` 的 `CalledProcessError` 没有在 evidence 边界处理，shell 尚未启动，因而既不删除旧 `manifest.json`，也不生成本轮失败 manifest。原 shell 的 environment 失败证据分支已无法覆盖这类失败。
- 独立复现：在 `.scratch/t060/code_review_prepare_e8fez_z9/` 建最小临时 Git 仓库，复制交付的 `gate_run.py` 与 requirements；evidence 预置 `{"run_id":"prior-run","all_passed":true,"suites":[{"name":"unit","exit_code":0}]}`；使用全新 venv 路径，PATH 注入仅执行 `exit 9` 的 uv，再运行复制的 `gate_run.py`。结果：进程退出 1，新 `run.json` 已生成，`manifest.json` 却原样保留 `prior-run`、`all_passed=true`。这是实际执行结果，不依赖 progress 自述。
- 影响：环境准备失败后读取指定证据目录，会得到与本轮 run_id 不一致的成功结论；从空证据目录启动则缺少失败 manifest，环境错误也未进入既有脱敏日志通道。
- 建议：将本轮 evidence 初始化和失败落盘边界移到 bootstrap 之前，捕获环境准备失败，使用可用宿主解释器生成绑定本轮 run_id 的失败 manifest 与脱敏环境日志；失败时确保旧成功 manifest 不再可见。补覆盖冷 venv 创建失败、安装失败和旧证据目录复用的回归。

### t060_code_f003 - 将公开源码 URL 的 home 路径段误作家目录

- 严重度：minor
- 锚点：文档与实现不一致；A53 脱敏对象为开发者家路径，不包括公开 URL 的普通仓库目录。
- 位置：`docs/reviews/review_20261108_153337/adoption_decision.md:48`；误判入口 `tests/unit/test_repo_hygiene.py:15`。
- 问题：W3 的固定 commit GitHub 引用原先指向 `apps/web/src/routes/` + `home/components/remote-keyboard-input.tsx`，当前变成 `apps/web/src/routes%3Chome%3E/remote-keyboard-input.tsx`。同一表格说明仍写“实际路径为 routes/home/components”。目标已经换成不存在于原引用路径的占位符目录，来源链接无法再定位所引用文件；静态 diff 足以确认路径失真，无需将远端可达性作为判断前提。
- 建议：恢复原公开 URL，并收窄扫描器或脱敏输入边界，区分 URL path 与真实本机绝对路径；不能靠把公开目录名替换为占位符消除扫描误报。

## 结论

- 本轮新发现：3 条，1 important、2 minor。13 条 AC 的实现均有独立查证支撑；AC 完成不消除新增 bootstrap 失败证据缺陷。
- 总体判断：FAIL。`t060_code_f002` 已独立复现，环境准备错误会留下上一轮成功证据，修复前不能交付可信门禁入口。
- 系统性 follow-up：无；上述问题均在本 task 新引入的实现或脱敏变更内，应在本 task 修复。
- 审查范围：完整 base-to-worktree diff，包括 `git add -N` 新交付文件、生产 Docker 标签传播、门禁脚本、E2E 前置辅助、五镜像 dockerignore、归档与 review 文档脱敏。Markdown 大批变更另按空白/转义与实际内容变化区分核对；未把历史文档修改误判为其他 task 状态推进。
- 独立定向运行：hygiene、t060 boundaries/concurrency/wiring、镜像 marker、cleanup、download reconciler、Docker context 共 **99 passed / 0 failed**，证据 `.scratch/t060/code_review.xml`。另运行上述 bootstrap 失败复现；没有重跑完整重门禁。
- 已读取 K/J manifest 及实际 JUnit：K 为 contract 258（1 policy skip）、unit 1651、integration 196（18 host skips）、E2E 105（2 optional skips），失败数均为 0；J 的 contract/unit/integration 同数且失败为 0。独立容器链 `baseline_chain_fixed/chain.xml` 为 18 cases、0 skip、0 failure。以上仅作为已有门禁运行结果，未用于否定新复现的失败路径。
- 文件过大提示（物理行数 `wc -l`，仅列本 task 净增文件，不进 finding 表）：`src/backend/cbrowser/supervisor/docker_adapter.py` 2166；`tests/e2e/test_stream_selkies_tokens_e2e.py` 670；`test_supervisor_container_graph_e2e.py` 795；`test_supervisor_offline_recovery_e2e.py` 674；`test_supervisor_recovery_e2e.py` 1187；`test_supervisor_retry_e2e.py` 654；`tests/fixtures/gateway_probe/topology.py` 810；`tests/integration/test_agent_executor_chain.py` 1528；`test_automation_probe_chain.py` 1030；`test_control_attendant_chain.py` 620；`test_runtime_coordinator_integration.py` 600；`tests/unit/test_download_reconciler.py` 758。文档、生成物、vendor、lockfile 与大块 fixture 数据正文不计入源码阈值。
- 复杂度提示：按逐函数近似 McCabe 检查，`scripts/gate_run.py:96` main 约 12，`scripts/verify_image_packages.py:38` normalise 约 10；`scripts/automation_probe_evidence.py:128` evaluate_evidence 约 18（不把内嵌 `_with_status` 分支归入外层，不计纯集合/列表枚举），本轮增加身份归一与预检循环。建议后续按验证阶段简化；没有以复杂度本身认定功能故障。纯表驱动分发和测试参数枚举排除。

### 七视角检查

- 安全：核对 run_id 标签与本地租约、Docker 不可变 ID 删除、未知/活跃资源 fail-closed、代理隔离、家路径扫描与脱敏；未发现新增越权、注入或凭证泄漏。公开 URL 误脱敏见 f003。
- 正确性：核对 venv 锁降级、同 checkout 产物锁、共享读者与重建互斥、活跃运行保护、停止双角色判断、严格 Node 上界/下界、目标 marker 环境及转发路径边界；发现 f002。
- 契约与 Breaking：核对 e2e_images 声明并集、未声明全集回退、image.json ID/os/arch 校验、shell 共用预检、suite 最小数与 skip 总失败语义；文档已同步，无额外公开产品 API breaking。
- 性能与资源：核对同 checkout 串行防止 dist 相互覆盖、跨 worktree venv 共享、Docker cleanup 关闭 client、套件信号转发；未发现新增 N+1 或无界资源分配。运行租约按 UUID 留存用于遗留归属，符合当前清理设计。
- 架构与可维护性：锁与生命周期集中在 gate_run，清理从名称授权切换为运行标签授权，生产 DockerAdapter 只增加可选 gate label；规模和复杂度提示如上。
- 健壮性与可观测：检查报告缺失/损坏、归属读取失败、Docker NotFound 并发消失、进程中断与 cleanup 退出码；bootstrap 新错误边界遗漏见 f002。
- 测试、文档与规格：仅从实现验收轴查测试断言作为 AC 证据，未代替 test reviewer 审测试质量；元数据被吞及公开来源 URL 失真见 f001/f003，handoff 当前节 branch/HEAD 独立核对一致。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`tests/unit/test_repo_hygiene.py:88` 枚举 cached/others 并全量扫描，豁免文件已删除，定向 hygiene 通过；代码不存在原整文件指纹放行。
- AC-002：TICK-VALID，re_verified。`tests/unit/test_repo_hygiene.py:15` 处理用户名结尾/引号，`:88` 纳入未跟踪且未忽略文件，`test_t060_gate_boundaries.py:38`、`:42` 负例重跑通过。
- AC-003：TICK-VALID，re_verified。`scripts/gate_run.py:27` 以 preparation 排他锁和运行共享锁保护检查/安装/重建；`test_t060_gate_concurrency.py` 的共享读者、等待重建与 wiring 双进程冷 venv 用例重跑通过。
- AC-004：TICK-VALID，re_verified。`scripts/gate_container_cleanup.py:28` 检查运行租约，`:67` 对容器和网络同按运行标签决策；独立重跑活跃/未知运行保护与不可变 ID 删除用例，并核对 CLI/SDK/Supervisor 全创建链标签传播。
- AC-005：TICK-VALID，re_verified。`tests/fixtures/frontend_app_probe/harness.py:160` 分别报告角色存在性，停止用 `not any` 且不吞 Docker 异常；stream 单独残留和异常两用例重跑通过。
- AC-006：TICK-VALID，re_verified。`scripts/check_gate_count.py:13` 与门禁接线覆盖所有测试 suite 基线；缺镜像返回 77 导致总失败；protocol 失败完整 evidence、低计数、missing image_packages 三类重跑通过；f002 为协议 suite 启动之前的另一失败路径。
- AC-007：TICK-VALID，re_verified。`scripts/automation_probe_evidence.py:255` main 调用统一预检，非法 ID 与错误 arch 的 CLI 两负例重跑返回失败。
- AC-008：TICK-VALID，re_verified。PATH 驱动真实脚本并断言协议在 suite 前执行；`test_t060_gate_wiring.py:130` 真正移动脚本前置步骤的变异被顺序 oracle 拒绝；原 unit 全量嵌套收集用例已删除。
- AC-009：TICK-VALID，re_verified。`tests/fixtures/e2e_env.py:26` 合并所收集 marker，`tests/e2e/conftest.py:133` 只校验声明集合；独立核对模块声明与缺项 collection 退出路径，声明集合及未声明回退用例重跑通过。
- AC-010：TICK-VALID，re_verified。`src/frontend/scripts/check_node.mjs:39` 保存严格大于操作符；26.0.0 等号拒绝重跑通过，`scripts/verify_image_packages.py:59` marker 错误传播至失败退出，目标镜像完整环境逻辑与负例均核对。
- AC-011：TICK-VALID，re_verified。五镜像静态 context 检查与 Supervisor services COPY 等值断言重跑通过；另查 `tests/e2e/test_native_build_contexts_e2e.py:23` 原生 BuildKit 准入与拒绝实现及 K JUnit 中对应五例全通过。
- AC-012：TICK-VALID，re_verified。`tests/unit/test_download_reconciler.py:715`、`:740` 通过真实 forwarder 验证宿主绝对路径、嵌套子目录及三种越界拒绝，定向重跑全通过。
- AC-013：TICK-VALID，re_verified。`docs/handoff.md:3` 仅一节，`:7` 写入时 branch 为 t060_gate_infra_and_privacy、HEAD 为 12380b25a51fc0dc51a7b00306e93684715f6b3f，与独立 git 查询一致；旧节已迁 archive。

coverage = 13 / 13

verdict: FAIL

## Round 2 (2026-11-12T05:02:08+08:00)

- round：2（完整复审）
- target：相对 `12380b25a51fc0dc51a7b00306e93684715f6b3f` 的完整 worktree 交付；包含未跟踪交付检查，保留 Round 1 原文。
- 落点校验：不带 `-C` 的 `git rev-parse --show-toplevel` 与指定工作区一致。branch 为 `t060_gate_infra_and_privacy`，HEAD 为 `12380b25a51fc0dc51a7b00306e93684715f6b3f`。

reviewed_scope: c899ece7b48f99a1

### Findings

本轮无新 finding。

### 结论

- `t060_code_f001`：已消除。独立从 base 原文重新生成精确 repo/home 前缀替换并比对，64 份归档与预期逐字一致；另 1 份 t024 review 的差异为容器路径示例占位，未吞路径外状态。`docs/archive/handoff.md:100`、`:164`、`:217`、`:222`、`:308`、`:343`、`:359`、`:376`、`:415`、`:425` 的 branch/base/attempt、标点与状态文字均保留；`docs/archive/tasks/t004_v2_stream_runtime/progress.md:29`、t005 对应 `:52` 的 claim/reserve 状态恢复。archive 末尾只增加从原 handoff 迁入的旧节。结论基于 base 内容重建与当前文件实际比较，不只依据实施侧 SHA 清单。
- `t060_code_f002`：已消除。`scripts/gate_run.py:127` 在 bootstrap 前删除旧 manifest，`:137` 至 `:162` 捕获 venv 创建、pip 安装及文件 IO 失败，使用本轮 run_id 写失败 manifest，并原子替换目标；环境日志只包含异常类型和退出码，不复制任意原始输出。独立重跑 `tests/unit/test_t060_gate_wiring.py:232` 的 venv/pip 两个真实脚本驱动负例：退出非零，旧成功 manifest 被本轮 environment failed 记录替代，run.json 与 manifest 的 run_id 一致，日志实际存在。Round 1 复现坏结果已不再出现。
- `t060_code_f003`：已消除。`docs/reviews/review_20261108_153337/adoption_decision.md:48` 的 W3 URL 与 base 原始公开路径一致；`tests/unit/test_repo_hygiene.py:15` 加绝对路径起点边界，避免命中 URL 嵌套目录，同时显式支持 file URI authority。独立重跑 `tests/unit/test_t060_gate_boundaries.py:352`，普通公开 URL 不报泄漏，file URI 空 authority/localhost 及 `worktree=` 形式仍检出。已有 curl 状态文件为 200；PASS 不依赖该自述，恢复原 URL 与扫描行为均已直接查证。
- 本轮新发现：0 条。当前无未解决 critical / important / minor finding。
- 总体判断：PASS。13 条 AC 实现成立，前轮三项问题全部复核修复，修复未引入可复现新缺陷。
- 系统性 follow-up：无。
- 独立定向运行：Round 1 同组加 bootstrap 两负例及 file URI/URL 边界用例，共 **102 passed / 0 failed**，证据 `.scratch/t060/code_review_round2.xml`。未重跑完整重门禁。
- 既有重门禁证据复核：直接解析 L/M manifest 与 JUnit，均 all_passed=true、cleanup_exit_code=0；unit 1654、contract 258（1 policy skip）、integration 196（18 host skips）均 0 failure，L 的 E2E 为 105（2 optional skips）、0 failure。`scripts/check_gate_count.py:15` 与 `docs/blueprint/testing.md:396` 的 unit 下限同为 1654。另对独立容器链快照的 140 份 backend 源码逐份重算 SHA256，全部一致；未把 18 个 host skip 计为宿主已验。
- 完整交付复核：重新检查 gate 生命周期、CLI/SDK/Supervisor 标签传播、cleanup、suite 顺序/计数、证据校验、目标 marker 环境、五镜像准入、E2E marker/停止观测、artifact 路径与文档差异。新 bootstrap 错误边界未绕过 preparation/运行锁，也未增加产品接口。当前新增普通文件均已纳入 `git diff`；未跟踪仅两份当前 reviewer 报告，不存在审查不可见交付。
- 未进表提示：文件过大名单及计量排除口径沿 Round 1，相关文件复核未新增超阈值成员；生产 `docker_adapter.py` 2166 行，下载 reconciler 测试 758 行，新增 `gate_run.py` 214 行未达脚本阈值。近似 McCabe 仍以函数为单位；证据汇总函数复杂度与 Round 1 相同，bootstrap 错误处理未形成新的深嵌套或行为分叉。生成代码、vendor、lockfile、文档、大块 fixture 正文、纯参数枚举不计入相关规模提示。以上不作为阻断或额外重构要求。

### 七视角检查

- 安全：复核精确脱敏、无整文件隐私豁免、file URI 识别及公开 URL 边界；bootstrap 失败证据不拷贝原始异常文本。标签与租约仍对未知/活跃资源拒绝删除，无新增凭证泄漏或注入。
- 正确性：复核共享读者与重建互斥、同 checkout 产物保护、不可变 Docker ID 清理、browser/stream 双角色停止、严格 Node 边界、marker 错误传播和路径逃逸拒绝。独立回归通过。
- 契约与 Breaking：镜像 marker 并集与未声明全集回退、image.json ID/os/arch、suite 基线/skip 总失败、协议首个 suite 均保持预期。bootstrap 失败 manifest 使用既有 evidence 字段，无产品 API 变化。
- 性能与资源：venv 继续共享，重建继续等待读者；原子落盘只写失败 manifest，无新增网络重试或重复重门禁。cleanup 与子进程信号链未改变，未发现新增泄漏路径。
- 架构与可维护性：包装器统一持有环境/checkout/run 租约；ExitStack 使 bootstrap 异常退出释放已获取资源。生产变更仍限可选 gate label，规模提示不扩为额外架构要求。
- 健壮性与可观测：重点复核创建失败、安装失败、旧证据复用；三者现在均失败封闭，manifest 与本轮 run_id 一致，环境失败有可读日志。未把未知 Docker 错误当成功。
- 测试、文档与规格：仅用测试断言佐证实现 AC；逐条核对前轮文档失真恢复，归档未推进其他 task 状态，handoff 只有最新一节且 branch/HEAD 与当前独立查询相符。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。全 tracked/非忽略新文件扫描本轮重跑通过，原隐私豁免文件与整文件指纹放行均已删除；归档按精确前缀脱敏复核。
- AC-002：TICK-VALID，re_verified。用户名结尾、引号、未跟踪新文件矩阵重跑通过；新增 URL 起点边界保留 file URI authority、`worktree=` 等真实绝对路径检出。
- AC-003：TICK-VALID，re_verified。gate_environment 的 preparation 排他锁与运行共享锁直接核对；共享读者、阻塞重建、双进程共享冷 venv 三类本轮重跑通过，bootstrap 异常释放租约。
- AC-004：TICK-VALID，re_verified。cleanup 对容器和网络共同校验 UUID 标签与非阻塞租约，活跃/未知运行保护重跑通过；CLI/SDK/Supervisor 全创建链仍传播归属标签。
- AC-005：TICK-VALID，re_verified。FrontendAppTopologyHarness 分别报告 browser/stream，停止使用双角色均不存在判断；stream 残留与 Docker API 异常负例本轮通过。
- AC-006：TICK-VALID，re_verified。suite 实际计数下限、image_packages 缺变量返回 skipped 且总失败、protocol 失败完整 manifest 三类本轮重跑通过；bootstrap 失败也独立证实撤旧成功并写本轮失败证据。
- AC-007：TICK-VALID，re_verified。证据 main 与 verdict 调统一镜像预检，非法 ID 与 arch 不符两个 CLI 负例本轮仍返回失败。
- AC-008：TICK-VALID，re_verified。PATH 注入驱动脚本的调用顺序及前置步骤后移变异本轮通过；unit 内原嵌套全量 collection 用例不存在。
- AC-009：TICK-VALID，re_verified。required_e2e_names 合并已收集用例镜像声明，collection 校验只消费该集合；未声明全集回退与声明集合负例本轮通过，并直接检查缺声明镜像的退出路径。
- AC-010：TICK-VALID，re_verified。26.0.0 对严格大于被拒绝、不可解析 marker 使镜像包 CLI 失败均重跑通过；全部目标环境键由镜像内 Python 读取。
- AC-011：TICK-VALID，re_verified。五镜像 bytecode 排除与 Supervisor services COPY 等值检查本轮通过，原生 BuildKit 五用例在 L 的实际 JUnit 均成功，准入规则未因复修变化。
- AC-012：TICK-VALID，re_verified。真实 DownloadArtifactForwarder 的宿主绝对路径、嵌套子目录与三种越界拒绝本轮全部重跑通过，未改产品转发逻辑。
- AC-013：TICK-VALID，re_verified。当前 handoff 仅一节，branch 与记录 HEAD 12380b25a51fc0dc51a7b00306e93684715f6b3f 经独立 git 查询一致，原最新旧节内容完整迁入 archive。

coverage = 13 / 13

verdict: PASS

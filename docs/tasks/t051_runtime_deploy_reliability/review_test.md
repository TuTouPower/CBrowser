# Task review t051（reviewer_focus: 测试）

- task：`t051_runtime_deploy_reliability`
- spec：`docs/tasks/t051_runtime_deploy_reliability/task.md`
- diff_anchor：`3331ed3c12518849a416a0c74b6c844f033fc8c7`
- target：`git -C '/home/hatch/workspace/CBrowser_t051' diff 3331ed3c12518849a416a0c74b6c844f033fc8c7`
- round：1
- reviewed_at：2026-11-11T08:54:14+08:00

reviewed_scope: a7d514f293a543a8

## Findings

### t051_test_f001 - 脱敏委托测试的 marker 计数断言用了下界而非精确值

- 严重度：minor
- 锚点：AC-020（证据脱敏断言精度）
- 位置：`tests/unit/test_t051_shared_redaction.py:160`，`test_redact_evidence_script_delegates_to_shared_rules`
- 问题：`assert result.stdout.count("<redacted>") >= 4`。对该测试的固定样本实际输出做独立复算，marker 数确定为 4（URL userinfo 1 个 + Cookie 两值 2 个 + password 引号值 1 个；家目录路径用 `<home>` 占位，不计入 `<redacted>`），不存在不确定性。下界断言容忍规则多产 marker 的情况，弱于精确断言。但相邻的逐秘密 `not in result.stdout` 断言是严格的，任一脱敏规则失效都会使测试变红，因此该弱化不能掩盖真实失败，不构成 blocking。
- 建议：改为 `== 4`，或在注释中说明为何必须保留下界。

### t051_test_f002 - restore 无当前 release 测试用 `or` 接受两条不同分支的报错文案

- 严重度：minor
- 锚点：AC-003（restore 拒绝路径的断言精度）
- 位置：`tests/unit/test_t027_release_controller.py:1313`，`test_restore_without_current_release_refused`
- 问题：`assert "does not exist" in result.stderr or "No current release" in result.stderr`。两条文案属于 deploy.sh 的两个不同分支：`does not exist` 是备份文件缺失分支（`scripts/deploy.sh:863`），`No current release` 是无当前 release 分支（`scripts/deploy.sh:869`）；本测试同时满足两个失败条件（备份不存在且无当前 release），实际命中后者。`or` 使测试对分支检查顺序的变化不敏感。主断言 `returncode != 0` 是严格的，该弱化不能掩盖真实失败，不构成 blocking。
- 建议：只断言实际命中的文案 `"No current release" in result.stderr`；备份缺失分支另立测试覆盖。

### t051_test_f003 - AC-018 缺少部署级损坏库拒测：deploy/rollback 的不可读库拒绝只在脚本层验证

- 严重度：minor
- 锚点：AC-018
- 位置：`tests/unit/test_t051_deploy_scripts.py`（`test_db_inspect_unreadable_db_fails_closed`）与 `tests/unit/test_t027_release_controller.py`（无对应部署级测试）
- 问题：AC-018 要求 deploy 与 rollback 在数据库“存在但不可读”时都在启动或替换任何容器之前拒绝。现有证据只覆盖一半：脚本层 `test_db_inspect_unreadable_db_fails_closed` 证明 `db_inspect.py` 对不可用库 fail-closed；部署级只测了退役 stamp 拒绝（`test_deploy_refuses_legacy_generation_database`），没有用 fake Docker 向 named volume 灌入损坏/不可读库、断言 deploy 与 rollback 均在启动容器前拒绝的测试。`current_db_stamp` 的非零退出分支（`scripts/deploy.sh:273` deploy、`scripts/deploy.sh:821` rollback）因此未被部署级测试直接行使。AC 并非完全无测试（检测器 fail-closed 已钉住，门逻辑与退役拒绝路径已行使），按“还可以再加一个 case”处理，不阻断。
- 建议：在 `test_t027_release_controller.py` 补两个 fake-Docker 测试：volume 内放损坏库时 deploy 拒绝且 `_builds` 之外无容器启动、无指针移动；同条件下 rollback 拒绝。

## 结论

- 前轮 finding 复核：首轮，无前轮。
- 改测方向复核：共审查 17 处既有测试改动，均有新语义支撑，非迁就实现，接受。其中一处预期调整已逐项核对：`test_deploy_refuses_legacy_generation_database` 把 `_builds == []` 改为恰好 1 次 api 镜像构建（`tests/unit/test_t027_release_controller.py`），理由写在测试内注释中——schema 检查改为容器内执行后必须先构建 API 镜像；AC-002 不要求“不构建”，核心安全断言（数据库字节不变、无指针移动）保留。以下改动同属新语义跟随：t027 指针辅助函数改读单一 JSON 指针、`test_rollback_preserves_profile_data_and_database` 改用带 stamp 的 volume 库、t050/refactor/p058/a8/a9/docker_boundaries/doubles_contract 把运行时 id 从标签迁入容器运行时配置（与用户裁定的 `com.cbrowser.instance-id` 键语义一致，新提取器测试 `test_runtime_instance_id_reads_config_channels` / `test_runtime_instance_id_ignores_deployment_label` 钉住新通道）、`test_docker_build_contexts` 敏感路径 `data/v2` 改为 `data/instance`、t027 夹具前缀 `inst-b` 改为 `inst_b`（A22 规则）、E2E 三文件改用 `container_runtime_instance_id` 读取。无“就地改预期冒充通过”的改测。
- 本轮新发现：3 条，均为 minor，无 critical / important。
- 未进表的提示：
  - 必查项①（部署身份标签键）：全仓代码/测试/compose/scripts 中无 `com.cbrowser.deployment-id` 残留；仅 `docs/tasks/t051_runtime_deploy_reliability/progress.md`（历史叙述）与 `docs/blueprint/decisions.md:342` ADR 028（驳回记录）出现该键名，均属允许的历史叙述。`com.cbrowser.instance-id` 已在 compose 四服务、container_spec、network_spec、deploy.sh、t050/supervisor_identity/t027 测试中断言一致。
  - 必查项②（默认部署前缀）：Supervisor/runner/docker_doubles 默认值均为 `cbrowser-t005`，有测试钉住（`test_adapter_default_prefix_is_the_deployment_default`、`test_runner_main_defaults_to_t005_prefix`）；deploy.sh（`scripts/deploy.sh:64`）与 compose.yaml 的默认 `cbrowser` 经 `git show HEAD:` 核对与基线一致，progress.md 的不对称登记属实，不判 finding。
  - 危险模式全量扫描：diff 内无测试删除、无 `.skip`/`.only`、无恒真/弱化断言（除 f001/f002 两处轻微下界/析取，已单列 minor）、无 mock 被测逻辑（mock 均位于 Docker CLI/会话边界，生产逻辑均被真实触达：真实 SQLite、真实 deploy.sh + fake Docker CLI、真实 subprocess 脚本、真实 React 渲染）、无注释掉的断言、无静默错误抑制。新增测试 100 个（复跑通过），无一处只改预期造假绿。
  - 引用逐项核对：抽查全部通过——d037/d038 findings 文件存在；`docs/reviews/review_20261110_200842/adoption_decision.md` 存在；`0001_baseline.py` 存在且 revision `b7e1c9d4a2f3` 不变；hygiene 白名单三处均真实（`scripts/deploy.sh:294`、`tests/unit/test_t027_release_controller.py:1328`、`docs/specs/release_deployment.md:54` 均含 `data/v2/cbrowser.db`）；`db_inspect.py:35` 以 `mode=ro` 只读打开数据库。另发现一处 progress.md 计数口径偏差（非引用不存在，不进 finding 表）：progress.md 称 `test_t051_supervisor_identity.py` 为 29 tests，实际收集为 33 tests（参数化 6+8=14，加 19 个普通测试）；其余计数（db_errors 26、deploy_scripts 11、docker_error_detail 11、shared_redaction 18、hygiene 1、t027 46）与实测一致。
  - 环境跳过如实标注：progress.md 明确写 AC-013 整项跳过“不得记为已验”、AC-014/AC-015 真实 Docker 部分跳过，task.md 的打勾按链口径“跳过按 pass 计”执行；本报告 AC-013 标 `trust_prior`、AC-014/AC-015 在复验行中注明真实 daemon 部分为跳过。
- 总体判断：测试真实触达生产逻辑，21 条 AC 均有可信测试或符合链口径的跳过依据；仅 3 条 minor，无 blocking finding。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。compose 结构测试断言 named volume `db:/data/db` 且无 `/data/cbrowser.db`，t027 部署后 volume 可 inspect；t027 46 tests 复跑通过。
- AC-002：TICK-VALID，re_verified。退役 stamp 部署拒绝且库字节不变、指针不动，合法 head stamp 部署放行；`db_inspect.py:35` 以 mode=ro 打开；t027 复跑通过。
- AC-003：TICK-VALID，re_verified。备份+恢复往返测试经真实 deploy.sh 与 fake Docker：备份记入 manifest、恢复后 stamp 一致；t027 复跑通过。
- AC-004：TICK-VALID，re_verified。旧库提示测试断言输出含 `data/v2/cbrowser.db`、restore 指引与 NOT moved，且旧库字节不变、volume 未建库；t027 复跑通过。
- AC-005：TICK-VALID，re_verified。分级矩阵含扩展码 261/517/262/778，API 处理器断言 503 + 稳定错误码 + `retryable=true` + `Retry-After: 1`，确定性错误仍 500；26 tests 复跑通过。
- AC-006：TICK-VALID，re_verified。真实 SQLite 上登录重试测试：2 次瞬时失败后成功、持续失败 3 次后抛错、速率限制不重复计数；复跑通过。
- AC-007：TICK-VALID，re_verified。日志测试断言含 `sqlite_errorcode=5`/`SQLITE_BUSY`/方法/路径，不含 SQL 参数值与密码；复跑通过。
- AC-008：TICK-VALID，re_verified。LoginPage vitest 3 tests：503 database_busy/database_unavailable 显示本地化文案且无后端原文，401 仍透传；vitest 复跑 8 passed（含 i18n 5）。
- AC-009：TICK-VALID，re_verified。compose 字体只读挂载断言 + check_font_sets + t027 字体 preflight 正常测试；font_sets API 单测/集成测试复跑通过。
- AC-010：TICK-VALID，re_verified。字体目录缺失/无效集均警告不阻塞；compose 挂载断言 + t041 `.worktreeinclude` 注册 `data/fonts` 测试复跑通过。
- AC-011：TICK-VALID，re_verified。11 个 docker_error_detail 测试覆盖 Browser/Stream/cache/X11/策略 helper/网络创建/列举/检查，均保留原始错误文本并脱敏；复跑通过。
- AC-012：TICK-VALID，re_verified。t050 断言 `0001-browser`/`0001-stream` 且 project 仍为 `<prefix>-profiles`，browser 启动测试断言 service 标签；复跑通过。
- AC-013：TICK-VALID，trust_prior。[deploy] 真实部署无自动化测试，依链口径跳过；替代证据为 AC-001 结构断言与 t027 fake-Docker 全流程测试，progress.md 明确标注整项跳过、不得记为已验。
- AC-014：TICK-VALID，re_verified。fake-Docker 池重叠拒绝/不重叠放行测试与三 profile 并发分配不同子网测试复跑通过；同一 daemon 双实例真实 Docker 部分依链口径跳过。
- AC-015：TICK-VALID，re_verified。阻塞式 fake 下 create 挂起 0.2s 超时失败、并发 fast profile 不受阻、预留释放测试复跑通过；真实 daemon 挂起部分依链口径跳过。
- AC-016：TICK-VALID，re_verified。deploy.sh 对 4 类非法前缀零构建拒绝，runner main 对显式 --prefix 与 env 前缀拒绝、默认 `cbrowser-t005` 免检；复跑通过。
- AC-017：TICK-VALID，re_verified。单一 JSON 指针文件测试、损坏指针替换测试、共享 atomic_write 测试复跑通过。
- AC-018：TICK-VALID，re_verified。`db_inspect` 对不可用库 fail-closed 测试与 deploy/rollback 的 stamp 门逻辑复跑通过；部署级损坏库拒测缺口见 minor f003。
- AC-019：TICK-VALID，re_verified。hygiene 测试扫描 15 个模式复跑通过，白名单三处均已验证真实存在。
- AC-020：TICK-VALID，re_verified。15 行脱敏矩阵 + 幂等 + 脚本委托测试复跑通过，URL userinfo/任意 cookie/含空格引号值/家目录路径均脱敏。
- AC-021：TICK-VALID，re_verified。伪造 project + 错 instance-id 拒绝、缺标签不认领、扫描/网关/helper 清理仅认领己方、core lookup 服务端过滤测试复跑通过。

coverage = 20 / 21

verdict: PASS

## Round 2 (2026-11-11T09:49:34+08:00)

- task：`t051_runtime_deploy_reliability`
- round：2
- reviewed_at：2026-11-11T09:49:34+08:00

reviewed_scope: 591cca7ccc950238

## Findings

### t051_test_f004 - 脱敏矩阵中无引号敏感值一行断言的是输入中不存在的秘密

- 严重度：minor
- 锚点：AC-020（脱敏矩阵对无引号敏感值的覆盖精度）
- 位置：`tests/unit/test_t051_shared_redaction.py:101-105`，`test_shared_redaction_matrix` 中 `"Sensitive key, unquoted value"` 一行
- 问题：该行输入为 `"login password=<redacted>"`，`leaked` 列却写 `["hunter2"]`——`hunter2` 从未出现在输入里，`assert secret not in out` 对该行恒真；`kept` 列只断言占位符原样通过（幂等行为，`test_redact_is_idempotent_on_placeholders` 已覆盖）。生产规则本身是工作的（本轮直接验证：`redact("login password=hunter2")` 得 `"login password=<redacted>"`），因此缺口只在测试侧：矩阵中没有任何一行真正把一个无引号秘密值喂给 `_UNQUOTED_RE`（`src/backend/cbrowser/redact.py` 的无引号规则）。若该规则被删或写错，本行测试仍全绿。AC-020 正文列出的形态（URL 内嵌凭据、任意 cookie 值、含空格的引号值、家目录路径）均有真实断言，不构成 blocking，按“还可以再加一个 case”处理。
- 建议：把该行改为 `("login password=hunter2", ["hunter2"], ["login password=<redacted>"])`，即输入含真实无引号秘密、断言其消失且占位符出现。

## 结论

- 前轮 finding 复核（逐条以 diff/代码/实跑核实，不采信处置表自述）：
  - test f001（marker 计数 `>= 4`）：已消除。`tests/unit/test_t051_shared_redaction.py:178` 现为 `assert result.stdout.count("<redacted>") == 4`，附注释说明 URL userinfo 把两个秘密折叠为一个 marker；本轮实跑该测试通过，计数确为 4（userinfo 1 + Cookie 两值 2 + password 引号值 1）。
  - test f002（restore `or` 接受两分支文案）：已消除，且 Round 1 报告的一处说法经核实确为误述——修复方纠正属实。`scripts/deploy.sh` 的 `cmd_restore` 先查备份文件（`[ ! -f "$backup_file" ]` → `"does not exist"`），再查当前 release（→ `"No current release"`）；原测试两个失败条件同时满足，实际命中前者而非 Round 1 所称的后者。现拆为两测试：`test_restore_without_current_release_refused`（`tests/unit/test_t027_release_controller.py:1399`）先备好备份文件，只断言 `"No current release"`；新增 `test_restore_missing_backup_file_refused`（`:1413`）先部署一次（有当前 release）再用不存在的备份路径，只断言 `"does not exist"`。两测试各断言的分支与 deploy.sh 的检查顺序一致，本轮实跑均通过。
  - test f003（AC-018 缺部署级损坏库拒测）：已消除。新增 `test_deploy_refuses_corrupt_database`（`tests/unit/test_t027_release_controller.py:1010`）与 `test_rollback_refuses_corrupt_database`（`:1054`）：volume 库被写坏后 deploy/rollback 均拒绝（`returncode != 0`）、无 `compose up`（deploy 断言日志无 `"up -d"`；rollback 断言 `up -d` 计数不变）、指针不动（deploy 为 `""`、rollback 仍为 `"rel-002"`）、库字节不变、且恰好 1 次 API 镜像构建（stamp 检查需先构建镜像）。fake docker `run` 的 harness 改动（`tests/unit/test_t027_release_controller.py:137-140`）把 `python3 "${translated[@]}"` 的退出码原样透传（`exit $?`），与真实 `docker run` 语义一致；此前恒 `exit 0` 会吞掉 `db_inspect.py` 的 fail-closed。若仍吞退出码，stamp 检查会把空 stamp 当作“未声明代际”放行，测试的无启动/指针断言随即变红——两测试真实区分该 harness 行为。本轮实跑两测试通过。
  - code f001（同 project 冲突测试）：测试侧已补。新增 `test_prefix_conflict_same_project_wrong_instance_id_refused`（`:1346`）与 `test_prefix_conflict_same_project_matching_instance_id_allowed`（`:1364`）：同 project（`cbrowser`）容器 instance-id 不符即拒绝、相符即放行。核对基线旧逻辑（`git show 3331ed3:scripts/deploy.sh` 的 `check_prefix_conflict`：project 等于 `PROJECT` 即放行）确认：不符测试在旧逻辑下会放行、新逻辑下拒绝，真实区分；现行 `scripts/deploy.sh:527,571` 的归属判定（id 相符认领、缺失且 project 为本实例项目时认领、存在且不符一律拒绝）与测试一致。本轮实跑两测试通过。
  - code f002（compose 结构断言扩展）：测试侧已补。`test_compose_yaml_t051_db_fonts_labels_contract`（`tests/unit/test_t027_release_controller.py:924,928`）断言 Supervisor 服务块含 `CBROWSER_INSTANCE_ID: ${CBROWSER_INSTANCE_ID:?run scripts/deploy.sh first}` 与 `CBROWSER_MEDIA_SUBNET_POOL: ${CBROWSER_MEDIA_SUBNET_POOL:?run scripts/deploy.sh first}`；核对 `compose.yaml:109,110` 确有这两行。注释同时写明 `CBROWSER_DOCKER_NETWORK_TIMEOUT` 故意不透传（deploy.sh 未写入 release env，无值可传）。本轮实跑通过。
  - code f003（小写 bearer/basic 矩阵）：测试侧已补。矩阵新增 4 行（`tests/unit/test_t051_shared_redaction.py:51-65`）：小写 `bearer`、大写 `Basic`、小写 `basic`（另有既有大写 `Bearer` 行），每行同时断言秘密消失与 `scheme <redacted>` 保留；`src/backend/cbrowser/redact.py:41,42` 的 `_BEARER_RE`/`_BASIC_RE` 均带 `re.IGNORECASE`。矩阵测试函数对每行同时查 `leaked` 不在输出、`kept` 在输出，真实触达 `redact()`。本轮实跑 18 个矩阵参数全部通过。
- 改测方向复核：本轮无“迁就实现”的改测。f001 由下界改为精确值（收紧）、f002 由析取改为两条严格断言（收紧并拆分）、f003 与三处 code finding 均为新增测试；fake docker `run` 的退出码透传是让 fake 贴合真实 `docker run` 语义的 harness 修正，不改任何既有测试的预期。无“就地改预期冒充通过”。
- 本轮新发现：1 条，minor（t051_test_f004），无 critical / important。
- 未进表的提示：
  - 必查项①（部署身份标签键）：全仓 grep `com.cbrowser.deployment-id` 仅命中四处，均属允许的历史叙述/审阅记录：`docs/blueprint/decisions.md:342`（ADR 028 驳回记录）、`docs/tasks/t051_runtime_deploy_reliability/progress.md:46`（历史叙述）、`review_test.md:44`（Round 1 报告原文）、`review_code.md:61`（code 审阅原文）；代码/测试/compose/scripts 中无残留。
  - 必查项②（默认部署前缀）：Supervisor 侧默认仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/runner.py:60,585`、`tests/fixtures/docker_doubles.py:79`），相关断言一致；deploy.sh 与 compose.yaml 的默认 `cbrowser` 经 Round 1 `git show` 核对为基线既有行为，本轮未变。
  - 危险模式全量扫描：diff 内无新增 `.skip`/`.only`（命中均为既有 E2E/集成文件的环境门控，不在本次 diff 内）、无删测试、无恒真断言、无注释掉的断言、无 mock 被测逻辑（mock 仍位于 Docker CLI/会话边界，生产逻辑均被真实触达：真实 SQLite、真实 deploy.sh + fake Docker CLI、真实 subprocess 脚本、真实 `redact()`）。f004 的一行属于断言恒真边缘情形，已单列 minor，不按危险模式升 important——其 `kept` 断言仍真实，且 AC-020 核心形态另有真实覆盖。
  - 全量回归核对：本轮实跑 `tests/unit` + `tests/integration` 全量：1901 passed / 29 failed / 8 skipped / 2 errors（411.38s）。与实施方基线（不含 t027 的 1850 passed / 29 failed / 8 skipped / 2 errors）相比，passed +51 恰为 t027 单跑的 51 tests（含 Round 1 修复新增的 5 个）；29 failed 与 2 errors 的清单与 progress.md 订正版分类逐项一致、无新增失败：浏览器/运行时环境缺失 14（agent_executor_chain 7、automation_cdp_flow 2、automation_probe_chain 3、control_attendant_chain 1、unit automation_cdp 1）、工具链/解释器环境 8（t028 gates 4、t034 2、t045 2）、既有欠账 7（normal_exit_replay 4、a24 2、repo_hygiene 1）、2 errors 为 a35_recovery 与 network_apply_operations 的 teardown 期错误。
  - 改动面回归另实跑 17 文件合跑：244 passed（t027 51 + t051 六套件 103 + 相关回归 90），0 失败；8 处修复相关的 26 个测试单点复跑全部通过；前端 LoginPage vitest 单文件复跑 3 passed（AC-008）。前端其余部分本轮未动，沿用 Round 1 结果。
- 总体判断：8 处修复全部真实落地且测试侧可信；仅 1 条新增 minor，无 blocking finding。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。compose 结构测试断言 named volume 且无宿主 bind mount；t027 51 tests 与全量 1901 passed 实跑通过。
- AC-002：TICK-VALID，re_verified。退役 stamp 部署拒绝且库字节不变、指针不动，合法 head stamp 放行；`db_inspect.py` 以 mode=ro 打开；t027 实跑通过。
- AC-003：TICK-VALID，re_verified。备份+恢复往返测试经真实 deploy.sh 与 fake Docker；restore 双分支拆分后各断言其文案，两测试本轮实跑通过。
- AC-004：TICK-VALID，re_verified。旧库提示测试断言输出含 `data/v2/cbrowser.db`、restore 指引与 NOT moved，且旧库字节不变、volume 未建库；实跑通过。
- AC-005：TICK-VALID，re_verified。分级矩阵含扩展码 261/517/262/778，503 + 稳定错误码 + `retryable=true` + `Retry-After: 1`，确定性错误仍 500；db_errors 26 tests 实跑通过。
- AC-006：TICK-VALID，re_verified。真实 SQLite 登录重试测试：2 次瞬时失败后成功、持续失败 3 次后抛错；实跑通过。
- AC-007：TICK-VALID，re_verified。日志测试断言含 `sqlite_errorcode=5`/`SQLITE_BUSY`/方法/路径，不含 SQL 参数值与密码；实跑通过。
- AC-008：TICK-VALID，re_verified。本轮重跑 LoginPage vitest 单文件 3 passed：503 database_busy/database_unavailable 显示本地化文案且无后端原文，401 仍透传。
- AC-009：TICK-VALID，re_verified。compose 字体只读挂载断言 + check_font_sets + t027 字体 preflight 正常测试；实跑通过。
- AC-010：TICK-VALID，re_verified。字体目录缺失/无效集均警告不阻塞；compose 挂载断言 + t041 `.worktreeinclude` 注册测试；实跑通过。
- AC-011：TICK-VALID，re_verified。11 个 docker_error_detail 测试覆盖 Browser/Stream/cache/X11/策略 helper/网络创建/列举/检查，均保留原始错误文本并脱敏；实跑通过。
- AC-012：TICK-VALID，re_verified。t050 断言 `0001-browser`/`0001-stream` 且 project 仍为 `<prefix>-profiles`；实跑通过。
- AC-013：TICK-VALID，trust_prior。[deploy] 真实部署无自动化测试，依链口径跳过；替代证据为 AC-001 结构断言与 t027 fake-Docker 全流程测试，progress.md 明确标注整项跳过、不得记为已验。
- AC-014：TICK-VALID，re_verified。fake-Docker 池重叠拒绝/不重叠放行测试与三 profile 并发分配不同子网测试实跑通过；同一 daemon 双实例真实 Docker 部分依链口径跳过。
- AC-015：TICK-VALID，re_verified。阻塞式 fake 下 create 挂起 0.2s 超时失败、并发 fast profile 不受阻、预留释放测试实跑通过；真实 daemon 挂起部分依链口径跳过。
- AC-016：TICK-VALID，re_verified。deploy.sh 对 4 类非法前缀零构建拒绝，runner main 对显式 --prefix 与 env 前缀拒绝、默认 `cbrowser-t005` 免检；实跑通过。
- AC-017：TICK-VALID，re_verified。单一 JSON 指针文件测试、损坏指针替换测试、共享 atomic_write 测试实跑通过。
- AC-018：TICK-VALID，re_verified。部署级损坏库拒测已补：deploy 与 rollback 各一，拒绝、无 compose up、无指针移动、库字节不变；两测试本轮单点实跑通过，`db_inspect` fail-closed 脚本层测试亦通过。
- AC-019：TICK-VALID，re_verified。hygiene 测试扫描 15 个模式实跑通过，白名单三处均已验证真实存在。
- AC-020：TICK-VALID，re_verified。18 参数脱敏矩阵 + 幂等 + 脚本委托测试实跑通过，小写 bearer/basic 四行真实触达 `redact()`；无引号值一行恒真断言见 minor f004，不影响 AC 正文形态的覆盖。
- AC-021：TICK-VALID，re_verified。伪造 project + 错 instance-id 拒绝、缺标签不认领、同 project 错 id 拒绝/对 id 放行（新增两测试）、扫描/网关/helper 清理仅认领己方、core lookup 服务端过滤测试实跑通过。

coverage = 20 / 21

verdict: PASS

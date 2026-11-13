# Task review t051（reviewer_focus: 代码）

- task：`t051_runtime_deploy_reliability`
- spec：`docs/tasks/t051_runtime_deploy_reliability/task.md`
- diff_anchor：`3331ed3c12518849a416a0c74b6c844f033fc8c7`
- target：`git -C '/home/hatch/workspace/CBrowser_t051' diff 3331ed3c12518849a416a0c74b6c844f033fc8c7`
- round：1
- reviewed_at：2026-11-11T09:02:06+08:00

reviewed_scope: a7d514f293a543a8

## Findings

### t051_code_f001 - deploy.sh 同 compose 项目容器豁免归属检查：instance-id 不符也不拒绝

- 严重度：important
- 锚点：AC-021；spec 范围「deploy.sh 冲突判定与 Supervisor 扫描以『标签值 == 本实例 instance_id』为唯一归属依据，删除基于 project 名的豁免」；ADR 028「删除 project 名豁免」
- 位置：`scripts/deploy.sh:540,567-577`（`check_prefix_conflict`）
- 问题：冲突判定只在 `project != $PROJECT` 时查 `com.cbrowser.instance-id`；`project == $PROJECT` 的容器直接放行，标签值从不比对。`deploy.sh:540` 注释自认「a same-project container is always ours」。可复现场景：实例 A 以默认 prefix `cbrowser`、默认 project `cbrowser`、数据根 R1 部署后，实例 B 以同一 prefix、同一 project、不同数据根 R2 部署——B 的 instance-id 不同，但 A 的容器（名 `cbrowser-*`、project `cbrowser`）全部落入同 project 豁免；只要媒体池不重叠（63/64 概率），B 的部署不被拒绝，随后 `compose up` 以同一 project 接管 A 的容器，且两实例共享同一 named volume `cbrowser-db`（`compose.yaml:167` 的 `name: ${CBROWSER_PREFIX:-cbrowser}-db`）。task 自身的 `release_deployment.md:33` 把判定写成「project 不同时仅当 instance-id 标签等于本实例 id 才认领」，与契约区「唯一归属依据」冲突，以契约区为准。现有测试只覆盖异 project 伪造（`test_prefix_conflict_forged_project_wrong_instance_id_refused`），同 project + 标签不符无覆盖。
- 建议：同 project 容器只在 instance-id 标签缺失（早于标签的旧容器，数据根迁移重部署情形）或等于本实例 id 时认领；标签存在且不符即拒绝。

### t051_code_f002 - compose.yaml 未把 CBROWSER_INSTANCE_ID / CBROWSER_MEDIA_SUBNET_POOL 传进 Supervisor 容器

- 严重度：important
- 锚点：AC-021（Supervisor 不认领异部署沙箱）；AC-014（Supervisor 只在本实例池内分配）
- 位置：`compose.yaml:91-110`（supervisor 服务的 `environment:` 块）；`src/backend/cbrowser/supervisor/runner.py:541-547,570-573`；`src/backend/cbrowser/supervisor/docker_adapter.py:241-270,556-568`
- 问题：compose.yaml 只把两个值用作标签插值（`compose.yaml:87-88`），supervisor 容器的 `environment:` 里没有 `CBROWSER_INSTANCE_ID`、`CBROWSER_MEDIA_SUBNET_POOL`；全仓 `compose.yaml` 无 `env_file:`（`--env-file` 只供插值，不进容器环境），supervisor 入口点 `python3 -m cbrowser.supervisor` 也不读 release env。于是真实部署时 Supervisor 以 `deployment_instance_id=None`、`media_subnet_pool=None` 启动：`_owns_deployment` 在未配置时恒为 True（`docker_adapter.py:566-567`），扫描/helper 清理/Gateway 扫描/`core._lookup_browser_container` 的实例过滤全部退化为旧行为（prefix 下资源全认领），AC-021 的 Supervisor 一半在生产上不生效；媒体子网分配退回共享默认池 `10.251.0.0/16`（`address_pool.py:27`），两实例在同一默认池内分配，deploy.sh 的池重叠检查（只比标签）无法兜底。单元测试直接传参/env 注入因而全绿，掩盖了接线缺失；结构测试（`test_compose_yaml_t051_db_fonts_labels_contract`）只断言标签，不查容器环境。
- 建议：supervisor 服务的 `environment:` 增加 `CBROWSER_INSTANCE_ID: ${CBROWSER_INSTANCE_ID:?run scripts/deploy.sh first}` 与 `CBROWSER_MEDIA_SUBNET_POOL: ${CBROWSER_MEDIA_SUBNET_POOL:?run scripts/deploy.sh first}`（`CBROWSER_DOCKER_NETWORK_TIMEOUT` 可一并透传）。

### t051_code_f003 - 共享脱敏漏掉小写 bearer/basic 凭据形态

- 严重度：important
- 锚点：AC-011（Docker 原始错误中 token 等凭据值均被替换为脱敏占位）
- 位置：`src/backend/cbrowser/redact.py:41-42,51,54,60,67`
- 问题：`_BEARER_RE` / `_BASIC_RE` 未加 `re.IGNORECASE`，只匹配首字母大写的 `Bearer` / `Basic`；而键值规则的 `_SCHEME_LOOKAHEAD`（`(?![Bb]earer\b|[Bb]asic\b)`）按大小写不敏感排除 scheme 前缀值，导致小写形态两边都漏：`redact("authorization: bearer abc123XYZ")` 与 `redact("authorization: basic dXNlcjpwYXNz")` 原样返回，凭据完整进入日志/错误输出（以布尔探针验证：changed=False，token 仍在输出中；大写形态已脱敏）。HTTP 认证 scheme 大小写不敏感，Docker/代理/传输层日志常出现小写形态；旧 `redact_evidence.py` 同样只认大写，但 A58 共享模块的职责正是收敛此类形态。
- 建议：`_BEARER_RE` 与 `_BASIC_RE` 加 `re.IGNORECASE`；在脱敏矩阵测试中补小写 `bearer` / `basic` 用例。

### t051_code_f004 - .gitignore 未覆盖新指针文件与备份目录

- 严重度：minor
- 锚点：行为缺陷——部署产物（状态文件与数据库副本）可能被误提交
- 位置：`.gitignore:70-71`；`scripts/deploy.sh:66,68`
- 问题：`.gitignore` 仍只列已退役的 `config/deploy/current_release` 与 `config/deploy/previous_release`，未列新指针 `config/deploy/release_pointer.json` 与备份目录 `config/deploy/backups/`。一次 deploy 后指针文件进 git status；备份是完整数据库副本（含密码哈希与会话 token），同样以 untracked 文件出现，存在误提交风险。
- 建议：`.gitignore` 增加 `config/deploy/release_pointer.json` 与 `config/deploy/backups/`（退役的两行可留可删）。

### t051_code_f005 - t051 新增 spec 文档称默认前缀为 cbrowser，与裁定不一致

- 严重度：minor
- 锚点：文档与实现不一致——用户裁定默认部署前缀为 `cbrowser-t005`（ADR 028；`docs/blueprint/supervisor.md`；`docs/specs/browser_isolation.md`）
- 位置：`docs/specs/runtime_lifecycle.md:67`；`docs/specs/release_deployment.md:55`；另 `docs/specs/runtime_lifecycle.md:60`
- 问题：两处新增的前缀规则均写「默认 `cbrowser`」；该表述只对 deploy.sh/compose.yaml 的默认值成立，Supervisor/runner/docker_adapter 的默认是 `cbrowser-t005`，合并表述会误导为全链默认 `cbrowser`。另 `runtime_lifecycle.md:60` 保留 t050 旧句「部署 prefix 冲突检查把该派生项目识别为本实例自有资源」，t051 后该识别以 instance-id 标签为前提，原文不再成立。
- 建议：两处改为区分 deploy.sh 默认 `cbrowser` 与 Supervisor 默认 `cbrowser-t005`；`runtime_lifecycle.md:60` 补 instance-id 前提。

## 结论

- 本轮新发现：5 条（important 3 条：f001、f002、f003；minor 2 条：f004、f005）
- 未进表的提示：
  - 文件过大（结论段提示，不进表）：`src/backend/cbrowser/supervisor/docker_adapter.py` 2345 行（本 task 净增约 298 行）；`scripts/deploy.sh` 912 行（本 task 净增约 496 行）。均超 800 行阈值，项目无覆盖约定。
  - 圈复杂度（手算近似，≥10 提示）：`_ensure_media_network` 约 10（本 task 重构，锁范围与预留逻辑新增分支）；`_used_subnets` 约 13（本 task +3，预留子网循环）；`scan_active_containers` 约 12（本 task +1，`_owns_deployment` 检查）；`start_stream_container` 约 19、`start_browser_container` 约 16（均为既有复杂度，本 task 未增分支）。
  - 范围外观察：`progress.md` 的 Area F/G 小节仍以 `deployment-id` 术语描述现行实现（改名前旧实现的历史叙述除外），属流程文件滞后，未计入 finding；按任务指令，`progress.md` / ADR 028 中的被驳回偏离历史叙述本身不算偏离。
  - 必查项核对：① 全仓代码/测试/compose/scripts 中无 `com.cbrowser.deployment-id` 残留（仅 `progress.md` 与 ADR 028 历史叙述中出现）；`com.cbrowser.instance-id` 已为全部代码/测试/compose/scripts 中的唯一部署身份键。② Supervisor/runner/docker_adapter 默认前缀均为 `cbrowser-t005`（与基线一致）；deploy.sh 与 compose.yaml 的默认 `cbrowser` 经 `git show 3331ed3:` 核对确为基线既有行为，不判 finding。
  - 引用逐项核对：p059、p063、p066、p068 均存在（`docs/archive/pending/`）；d037、d038 为本 task 新增；`docs/reviews/review_20261110_200842/adoption_decision.md` 存在，A57 为措辞项（p068 根因表述与 p059 Browser 路径失实），非实现项；`tests/integration/test_api_subprocess.py` 存在；task.md 所引基线行号经 `git show 3331ed3:` 抽查属实（`container_spec.py:64`、`compose.yaml:18-27/98-105`、`app.py:391`）。
- 总体判断：实现主体完整，但三处 important 缺陷阻断 PASS：deploy.sh 同 project 豁免、compose 到 Supervisor 的身份/池接线缺失、共享脱敏小写 scheme 漏网。
- 系统性 follow-up：无（均为本 task 内修复，无需新 tid）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。compose.yaml 以 named volume `db`（`name: ${CBROWSER_PREFIX:-cbrowser}-db`）挂 `db:/data/db`，`CBROWSER_DB_PATH=/data/db/cbrowser.db`，全仓无 `/data/cbrowser.db` 引用。
- AC-002：TICK-VALID，re_verified。`db_inspect.py` 以 `mode=ro` 读 stamp、不可读返回非零；deploy.sh 先建 API 镜像再查 stamp，rollback 用目标 release 的 API 镜像查 stamp，均在启动容器前。
- AC-003：TICK-VALID，re_verified。`db_backup.py` 用 SQLite 在线备份 API（源只读），路径记入 manifest `database_backup`；`db_restore.py` 拷回备份并先删 `-wal`/`-shm`。
- AC-004：TICK-VALID，re_verified。`check_legacy_host_database` 在 volume 无库且宿主旧路径存在时打印位置与处置方式，不删除/移动/覆盖。
- AC-005：TICK-VALID，re_verified。实跑分级探针：扩展码 261/517→busy、262→locked、778→io_error，皆 transient→503（`database_busy`/`database_unavailable`，`retryable=true`）；19 约束冲突→500 `database_error`。
- AC-006：TICK-VALID，re_verified。`@retry_transient_db_errors` 覆盖全部认证/会话路径（`has_admin`、`authenticate_admin`、`create_session`、`get_valid_session`、`revoke_session`、automation token 路径），最多 3 次、有界退避，确定性错误立即抛出。
- AC-007：TICK-VALID，re_verified。`dbapi_error_handler` 只记 `sqlite_errorcode`/`sqlite_errorname`/方法/路径，`str(exc.orig)` 已删除。
- AC-008：TICK-VALID，re_verified。LoginPage 将 `database_busy`/`database_unavailable` 映射为 `loginDatabaseUnavailable`，中/英文案俱全；client 从响应 `error` 字段填充 `errorCode`。
- AC-009：TICK-VALID，re_verified。compose 以 `${CBROWSER_FONTS_DIR}:/fonts:ro` 挂载、容器内 `CBROWSER_FONTS_DIR=/fonts`；deploy.sh 默认 `$ROOT/data/fonts`。
- AC-010：TICK-VALID，re_verified。`check_font_sets.py` 恒 exit 0 并输出可执行提示，deploy preflight `|| true` 永不阻塞；`.worktreeinclude` 登记 `/data/fonts`。
- AC-011：TICK-VOID，re_verified。Docker 错误路径已统一用 `docker_error_detail`，但小写 `bearer`/`basic` 凭据经探针验证原样泄漏，AC 要求的「token 均被替换」不成立。
- AC-012：TICK-VALID，re_verified。`sandbox_compose_labels` 输出 `<NNNN>-browser` / `<NNNN>-stream`，`com.docker.compose.project` 仍为 `<prefix>-profiles`。
- AC-013：TICK-VALID，trust_prior。本机无 Docker，真实部署无法独立复验；依据链口径跳过按 pass 计，依赖 AC-001 结构断言与 fake Docker 全流程证据，真实部署仍须在用户机补验。
- AC-014：TICK-VOID，re_verified。deploy.sh 的池重叠拒绝存在，但 compose.yaml 未把 `CBROWSER_MEDIA_SUBNET_POOL` 传进 Supervisor 容器，Supervisor 实际以共享默认池 `10.251.0.0/16` 分配，不满足「Supervisor 只在本实例池内分配」。
- AC-015：TICK-VALID，re_verified。`_docker_call` 以 `network_timeout`（默认 30s）为限；分配锁只覆盖 get+分配+预留，创建在锁外；创建冲突为错误不重试，失败丢弃预留。
- AC-016：TICK-VALID，re_verified。deploy.sh 在任何 Docker 操作前以 `^[a-z0-9][a-z0-9_]*$` 校验 prefix；runner main 在持锁与任何 Docker 调用前校验显式提供的前缀。
- AC-017：TICK-VALID，re_verified。单一 JSON 指针文件；`atomic_write_text` 经查证含文件 fsync、rename 与父目录 fsync；`activate_release` 一次写出 current+previous。
- AC-018：TICK-VALID，re_verified。`db_inspect.py` 不可读库返回非零；deploy 与 rollback 的 stamp 检查均 fail-closed 且在启动/替换容器前。
- AC-019：TICK-VALID，re_verified。grep 全仓 src/scripts/docs/blueprint/docs/specs 无残留「CBrowser v2」自指；迁移文件改名、revision `b7e1c9d4a2f3` 不变。
- AC-020：TICK-VALID，re_verified。探针验证 URL 内嵌凭据、任意 cookie 值、含空格的引号敏感值、家目录路径均输出脱敏占位。
- AC-021：TICK-VOID，re_verified。异 project 伪造拒绝与 Supervisor 三处扫描过滤已实现，但 deploy.sh 同 project 容器标签不符不拒绝，且生产 Supervisor 收不到 `CBROWSER_INSTANCE_ID`，`_owns_deployment` 恒为 True。

coverage = re_verified / 21

verdict: FAIL

## Round 2 (2026-11-11T09:38:34+08:00)

- task：`t051_runtime_deploy_reliability`
- spec：`docs/tasks/t051_runtime_deploy_reliability/task.md`
- diff_anchor：`3331ed3c12518849a416a0c74b6c844f033fc8c7`
- target：`git -C '/home/hatch/workspace/CBrowser_t051' diff 3331ed3c12518849a416a0c74b6c844f033fc8c7`
- round：2
- reviewed_at：2026-11-11T09:38:34+08:00

reviewed_scope: 591cca7ccc950238

## Findings

本轮零 finding。8 处前轮修复全部经代码/探针/测试复核真实落地，无新发现、无回归。

## 结论

- 前轮 finding 复核（逐条以 diff/代码/实测为准，不采信处置表自述）：
  - t051_code_f001（important）：已消除。`scripts/deploy.sh:564-577` 现按 instance-id 判定：标签等于本实例 id 时认领（:568-570）；标签缺失且 project 为本实例项目时认领（:571-573，旧容器迁移情形）；标签存在且不符一律拒绝，包括同 project（:574-577 的拒绝分支不再有 project 豁免）。注释 `:535-543` 与新规则一致；`docs/specs/release_deployment.md:52` 与 `docs/specs/runtime_lifecycle.md:60` 的冲突判定行已同步为同一规则。新增测试 `test_prefix_conflict_same_project_wrong_instance_id_refused`（`tests/unit/test_t027_release_controller.py:1346`，同 project + 错标签拒绝、零构建）与 `test_prefix_conflict_same_project_matching_instance_id_allowed`（:1364，标签相符放行）均在复跑中通过。
  - t051_code_f002（important）：已消除。`compose.yaml:111-112`（supervisor 服务 `environment:`）现含 `CBROWSER_INSTANCE_ID: ${CBROWSER_INSTANCE_ID:?run scripts/deploy.sh first}` 与 `CBROWSER_MEDIA_SUBNET_POOL: ${CBROWSER_MEDIA_SUBNET_POOL:?run scripts/deploy.sh first}`；接线链完整：`src/backend/cbrowser/supervisor/runner.py:544,572` argparse 默认值取同名环境变量并经 `:622-623` 传入 `run_supervisor`，`src/backend/cbrowser/supervisor/docker_adapter.py:246-247,269-270` 构造时同样回落到环境变量（无值时 `deployment_instance_id=None`、池回落默认 `10.251.0.0/16`）。结构测试现断言 supervisor 环境块含两变量（`tests/unit/test_t027_release_controller.py:916-931`）。`CBROWSER_DOCKER_NETWORK_TIMEOUT` 未透传是有意决定（测试注释写明 deploy.sh 不把它写入 release env、无值可传；adapter 默认 30s，`docker_adapter.py:252-260`），不判缺口。
  - t051_code_f003（important）：已消除。`src/backend/cbrowser/redact.py:41-42` 的 `_BEARER_RE` / `_BASIC_RE` 已加 `re.IGNORECASE`。独立探针验证：`authorization: bearer abc123XYZ`、`authorization: basic dXNlcjpwYXNz`、`BEARER` / `BeArEr` / `bEaReR` 全大写与混合大小写形态及引号内形态均输出 `<redacted>` 且 token 不再泄漏（大写形态保持脱敏，scheme 原样保留）。
  - t051_code_f004（minor）：已消除。`.gitignore:72-73` 新增 `config/deploy/release_pointer.json` 与 `config/deploy/backups/`，退役的两行保留。
  - t051_code_f005（minor）：已消除。`docs/specs/runtime_lifecycle.md:67` 与 `docs/specs/release_deployment.md:55` 均已区分「默认 `cbrowser`（deploy.sh 与 compose 的默认值；Supervisor/runner/docker_adapter 的默认前缀为 `cbrowser-t005`）」；`runtime_lifecycle.md:60` 已补 instance-id 前提（标签相符或缺标签且项目相符才识别为自有资源，标签不符拒绝）。
  - test f001（minor，测试侧实现改动）：已消除。`tests/unit/test_t051_shared_redaction.py:178` 现为精确断言 `count("<redacted>") == 4`；小写 `bearer`/`basic` 矩阵用例已补（:49-64）。
  - test f002（minor，测试侧实现改动）：已消除并核实修复方纠正属实。`scripts/deploy.sh:865` 备份文件检查先于 `:871` 无当前 release 检查，Round 1 原测试（备份缺失且无当前 release）实际命中 "does not exist" 分支，Round 1 报告称其命中 "No current release" 的说法有误；现已拆为两个单分支测试：`test_restore_without_current_release_refused`（`tests/unit/test_t027_release_controller.py:1402`，备份文件存在才断言 "No current release"）与 `test_restore_missing_backup_file_refused`（:1412，有当前 release 时断言 "does not exist"），注释写明分支顺序依据。
  - test f003（minor，测试侧实现改动）：已消除。新增部署级测试 `test_deploy_refuses_corrupt_database`（`tests/unit/test_t027_release_controller.py:1010`）与 `test_rollback_refuses_corrupt_database`（:1054），均断言返回码非零、库字节不变、无新增 `up -d`、指针不动；其前提 fake docker `run` 现透传退出码（:140-142，`exit $?`，注释引 t051 review f003），否则 stamp 检查的 fail-closed 会被吞掉。
- 本轮新发现：0 条。
- 未进表的提示：
  - 文件过大（结论段提示，不进表）：`src/backend/cbrowser/supervisor/docker_adapter.py` 2345 行（R2 未增行）；`scripts/deploy.sh` 914 行（R2 净增 2 行，仍超 800 行阈值，项目无覆盖约定）。
  - 圈复杂度（手算近似）：重写后的 `check_prefix_conflict` 约 6，未达 10；其余 R2 触及函数无新增 ≥10 复杂度。
  - 必查项核对：① 全仓代码/测试/compose/scripts 中无 `com.cbrowser.deployment-id` 残留（全仓 grep 仅 `docs/tasks/t051_runtime_deploy_reliability/progress.md` 历史叙述、`docs/blueprint/decisions.md:342` ADR 028 驳回记录及两份 review 报告中出现，均属允许的历史叙述）；`com.cbrowser.instance-id` 为唯一部署身份键，compose 四服务均带该标签。② Supervisor/runner/docker_adapter 默认前缀均为 `cbrowser-t005`（`runner.py:594-595` 显式默认值；deploy.sh 与 compose.yaml 的默认 `cbrowser` 为基线既有行为，不判 finding）。
  - 引用逐项核对：测试与注释中新增的 "t051 review f001/f002/f003" 引用均真实存在于 Round 1 两份 review 报告（code f001/f002/f003、test f001/f002/f003 各三条）；`docs/specs/release_deployment.md:52,55`、`docs/specs/runtime_lifecycle.md:60,67` 行号与内容逐项核对无误。
  - 复验方式说明：本轮以探针 + 代码精读复核全部 8 处修复，并用验证 venv（`~/workspace/.cb-venv-t051`，`PYTHONPATH=<worktree>/src/backend`）复跑修复所涉 5 个测试文件（`test_t051_shared_redaction.py`、`test_t051_deploy_scripts.py`、`test_t027_release_controller.py`、`test_t051_supervisor_identity.py`、`test_t051_docker_error_detail.py`），127 passed、0 failed。其余 AC 的实现代码不在 R2 改动文件之列，沿用 Round 1 复验结论。
- 总体判断：Round 1 的 3 条 important 与 2 条 minor 均已真实消除，本轮零新发现，21 条 AC 全部成立。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。compose.yaml 以 named volume `db` 挂 `db:/data/db`，`CBROWSER_DB_PATH=/data/db/cbrowser.db`，R2 未改动该路径，Round 1 证据仍成立。
- AC-002：TICK-VALID，re_verified。`db_inspect.py` 以 `mode=ro` 读 stamp、不可读返回非零；deploy/rollback 的 stamp 门逻辑在复跑的 t027 测试中通过。
- AC-003：TICK-VALID，re_verified。备份+恢复往返测试通过；restore 两分支测试已拆分单断言（`tests/unit/test_t027_release_controller.py:1402,1412`），复跑通过。
- AC-004：TICK-VALID，re_verified。旧库提示路径在 R2 未改动，t027 旧库提示测试复跑通过。
- AC-005：TICK-VALID，re_verified。错误分级矩阵（扩展码 261/517→busy、262→locked、778→io_error）与 503/`retryable=true` 响应在 R2 未改动，Round 1 探针证据仍成立。
- AC-006：TICK-VALID，re_verified。认证路径有界重试覆盖全部会话路径，R2 未改动，Round 1 证据仍成立。
- AC-007：TICK-VALID，re_verified。错误日志只含 `sqlite_errorcode`/`sqlite_errorname`/方法/路径，R2 未改动，Round 1 证据仍成立。
- AC-008：TICK-VALID，re_verified。LoginPage 将可重试数据库错误映射为本地化文案，R2 未改动，Round 1 证据仍成立。
- AC-009：TICK-VALID，re_verified。compose 以 `${CBROWSER_FONTS_DIR}:/fonts:ro` 挂载，R2 未改动，Round 1 证据仍成立。
- AC-010：TICK-VALID，re_verified。字体 preflight 只警告不阻塞，R2 未改动，Round 1 证据仍成立。
- AC-011：TICK-VALID，re_verified。本轮独立探针验证小写/全大写/混合大小写 `bearer`/`basic` 均脱敏且无泄漏。
- AC-012：TICK-VALID，re_verified。`sandbox_compose_labels` 输出 `<NNNN>-browser` / `<NNNN>-stream`，`com.docker.compose.project` 仍为 `<prefix>-profiles`，R2 未改动。
- AC-013：TICK-VALID，trust_prior。本机无 Docker，真实部署无法独立复验；依链口径跳过按 pass 计，依赖 AC-001 结构断言与 t027 fake-Docker 全流程测试，真实部署仍须在用户机补验。
- AC-014：TICK-VALID，re_verified。compose.yaml 现把 `CBROWSER_MEDIA_SUBNET_POOL` 传进 Supervisor 环境，runner/docker_adapter 环境回落链已精读验证，结构测试断言该环境变量；同一 daemon 双实例真实 Docker 部分依链口径跳过。
- AC-015：TICK-VALID，re_verified。`_docker_call` 以 `network_timeout`（默认 30s）为限；`CBROWSER_DOCKER_NETWORK_TIMEOUT` 未透传是有意决定且有注释说明，adapter 默认值兜底。
- AC-016：TICK-VALID，re_verified。deploy.sh 与 runner 均在任何 Docker 操作前以 `^[a-z0-9][a-z0-9_]*$` 校验 prefix，R2 未改动该路径，t027 前缀测试复跑通过。
- AC-017：TICK-VALID，re_verified。单一 JSON 指针文件 + 原子写，R2 未改动，t027 指针测试复跑通过。
- AC-018：TICK-VALID，re_verified。新增部署级损坏库拒测（deploy 与 rollback 各一）已精读并复跑通过，fake docker 退出码透传使 stamp 门真实生效。
- AC-019：TICK-VALID，re_verified。`.gitignore:72-73` 新增指针与备份目录后部署产物不再进入 git status；代际标识 hygiene 在 R2 未改动。
- AC-020：TICK-VALID，re_verified。脱敏矩阵测试精确断言 `== 4` 且复跑通过；本轮探针验证 URL userinfo/cookie/引号敏感值/家目录路径形态。
- AC-021：TICK-VALID，re_verified。deploy.sh 同 project + 标签不符现拒绝（新测试复跑通过）；Supervisor 侧现真实收到 `CBROWSER_INSTANCE_ID`，`_owns_deployment` 不再恒为 True。

coverage = 20 / 21

verdict: PASS

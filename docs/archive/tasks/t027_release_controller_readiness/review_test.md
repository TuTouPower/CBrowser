# Task review t027（reviewer_focus: 测试）

- task：`t027_release_controller_readiness`
- spec：`docs/tasks/t027_release_controller_readiness/task.md`
- diff_anchor：`1e9c7ba73626ae7a00f56fa0578eb06beda98c61`
- target：`git -C '/home/hatch/workspace/CBrowser_t027' diff 1e9c7ba73626ae7a00f56fa0578eb06beda98c61`
- round：1
- reviewed_at：2026-11-04T11:29:45+08:00

reviewed_scope: b100425880c4195c

## Findings

### t027_test_f001 - AC-008 实例参数化与双实例并存完全无测试（只有冲突拒绝一条）

- 严重度：important
- 锚点：AC-008「发布实例身份可参数化，两个实例在同一 Docker daemon 并存时互不扫描、不清理对方资源」
- 位置：`tests/unit/test_t027_release_controller.py:154-195`（`_run`/`_deploy` 的 env 注入）；对照实现 `scripts/deploy_v2.sh:41-60,309`
- 问题：全仓只有 `test_t027_release_controller.py` 执行 `deploy_v2.sh`（reviewer grep 实证），而其 `_run` 只注入 `FAKE_*` 与 `CBROWSER_RELEASE_ID`，所有 deploy/rollback 用例都以默认实例身份（project/prefix=`cbrowser`、port=56661、默认 data root/secrets dir）运行；没有任何用例设置 `CBROWSER_COMPOSE_PROJECT`/`CBROWSER_PREFIX`/`CBROWSER_HTTPS_PORT`/`CBROWSER_DATA_ROOT`/`CBROWSER_SECRETS_DIR` 中的任一个，也从不断言 manifest 的 `instance` 字段（`scripts/deploy_v2.sh:309`）或 release env 中的实例字段。AC-008 相关断言仅有 `test_prefix_conflict_refused_before_build`（:354，冲突拒绝）与 compose 静态文本里的默认占位符（:436-438）。失败场景：脚本把 prefix 写死、data root/secrets 参数化写错或 manifest instance 记录错误，全部 t027 测试仍绿；t032 按 `DOCKER_DEPLOYMENT.md` 第 6 节起第二实例时才会暴露与生产共用 prefix/数据根、互扫互清的风险。AC-008 已打勾，但其核心行为（参数化生效 + 并存放行）在云端零证据。
- 建议：用 fake Docker 以非默认 project/prefix/port/data_root/secrets_dir 跑一次 deploy，断言 release env 与 manifest `instance` 字段等于所传值、secrets 与数据目录落在指定位置；并补一条同 prefix 且 `FAKE_OWN_PROJECT` 等于本项目时放行的断言（与冲突拒绝成对）。

### t027_test_f002 - AC-005「配置变化时只重建受影响服务」无测试，且触发机制（Caddy 指纹承载）从未被断言

- 严重度：important
- 锚点：AC-005 后半句「配置变化时只重建受影响服务」
- 位置：实现机制 `compose.yaml:123-124`（caddy 服务以 `CBROWSER_CADDYFILE_SHA256`/`CBROWSER_FRONTEND_SHA256` 环境变量承载指纹）；测试 `tests/unit/test_t027_release_controller.py:341-352`（`test_repeat_deploy_same_config_is_idempotent`）、`:418-438`（`test_compose_yaml_release_contract`）
- 问题：该 AC 的实现机制是「指纹写入 release env → 经 compose.yaml caddy 的 environment 承载 → 指纹变化才触发 compose 重建 caddy」。但 reviewer 对 `tests/` 全量 grep `CBROWSER_CADDYFILE_SHA256|CBROWSER_FRONTEND_SHA256` 无任何命中；`test_deploy_success_builds_once_and_pins_everything` 只核对了 manifest 的 `compose_sha256` 与 `migration_version`，从未把 `caddyfile_sha256`/`frontend_sha256` 与源文件哈希比对（写空串/写常量也能全绿）；`test_repeat_deploy_same_config_is_idempotent` 只重复发布同一配置、断言两份 manifest 相等与 docker log 无 `restart`——fake compose 的 `up` 根本不建模重建行为，这个测试无法区分「指纹变化→只重建 caddy」「任何变化→全量重建」「永不重建」。失败场景：删掉 `compose.yaml:123-124` 两行指纹承载（AC-005 后半句即刻失效、Caddy 将长期提供旧前端/旧 Caddyfile），现有全部测试仍绿。
- 建议：云端可测部分先钉住：compose 契约测试断言 caddy 服务块含两指纹环境承载；fake repo 改 Caddyfile（或 dist 内容）后 redeploy，断言 manifest `caddyfile_sha256`/`frontend_sha256` 随源变化且与源文件 sha256 相等、images 不变。真实「只重建 caddy」的行为判定留 t032 演练第 2 条（已在 `DOCKER_DEPLOYMENT.md` 第 7 节），结论中不得把本条云端部分表述为已验证选择性重建。

### t027_test_f003 - AC-006 回退的「不删除数据」与「回退验收失败不报成功」两条子句无测试

- 严重度：important
- 锚点：AC-006「回退到上一 release 恢复其全部镜像与配置，不删除当前 Browser、Profile 数据或数据库；回退后执行同一 readiness 验收，状态未知不报成功」
- 位置：`tests/unit/test_t027_release_controller.py:363-376`（`test_rollback_success_redeploys_previous_and_verifies`）、`:392-417`（两条变更前拒绝）
- 问题：回退测试只有成功路径与两种变更前拒绝（迁移过低、无 readiness 能力）。缺两类断言：(a) 数据保留——fake repo 从未在数据根预置任何 Profile/数据库文件，rollback 后也没有任何「数据仍存在」断言，脚本若在回退路径清数据根/删 Profile 目录，现有测试全绿；(b) 回退验收失败——没有 `rollback` + `FAKE_READINESS=unready` 的用例来证明回退 readiness 不收敛时非零退出、指针保持 `rel-002`、不打印成功（deploy 路径的同型失败已测，但回退走的是 `cmd_rollback` 独立代码路径，不共享断言）。AC-006 已打勾，这两条子句零证据。
- 建议：rollback 成功用例在 fake 数据根预置文件并断言回退后仍在；新增 rollback + `FAKE_READINESS=unready` 用例，断言 returncode != 0、`current_release` 仍为 `rel-002`、stdout 不含成功文案。

### t027_test_f004 - AC-001「生成中途失败不覆盖上一 release」只测了部署阶段，构建阶段失败未覆盖

- 严重度：minor
- 锚点：AC-001「生成或部署中途失败不覆盖上一份有效 release」
- 位置：`tests/unit/test_t027_release_controller.py:24-121`（FAKE_DOCKER 无 build 失败开关）；已有覆盖 `:318-339`（readiness 失败、up 失败）
- 问题：失败保留只在 up 与 readiness 两阶段被验证；构建第 N 个镜像失败（生成中途）无用例。由于指针只在验收后激活的同一机制已被其他两种失败模式覆盖，本条属同机制补 case，定 minor。
- 建议：给 FAKE_DOCKER 加 build 失败开关，断言构建失败时 returncode != 0、指针与上一 release manifest 不变。

### t027_test_f005 - AC-007 内部密钥「随机生成」只验 0600 与非空，随机性从未断言

- 严重度：minor
- 锚点：AC-007「容器间内部密钥缺失时以随机值生成并以 0600 保存」
- 位置：`tests/unit/test_t027_release_controller.py:291-305`（`test_internal_secrets_generated_0600`）、`:282-289`（不泄漏断言）
- 问题：现有断言只能区分「生成了某非空值且权限 0600」，无法区分随机值与写死常量——实现若退化为固定内部密钥，全部测试仍绿。
- 建议：在两个独立 fake repo 各 deploy 一次，断言同名内部密钥值互不相同（且长度达标）。

### t027_test_f006 - 截止时间参数与 compose 健康检查绑定只用子串/计数断言，未钉值、未绑定服务

- 严重度：minor
- 锚点：AC-003「在明确截止时间内非零退出」与三服务健康检查的 compose 接线
- 位置：`tests/unit/test_t027_release_controller.py:276-277`、`:432`
- 问题：`:276-277` 以子串断言 `"up -d --no-build --wait"` 与 `"exec -T supervisor python3 - verify"`，不钉 `--wait-timeout` 的值，也不钉传给探针的 verify 截止参数——删掉/改错截止参数仍绿（探针默认 300 与脚本默认同值更会掩盖脱落）；`:432` 的 `text.count("healthcheck:") >= 3` 加 URL 子串不把健康检查绑定到具体服务，某服务 healthcheck 指错 URL 仍可全绿。说明：这是新增静态契约测试的断言强度问题，不存在既有更强断言被弱化，不按危险模式计；Gateway 健康路由与 Supervisor 启动次序另有真实 HTTP/行为测试、真实健康行为归 t032，故定 minor。
- 建议：断言完整 up 命令含 `--wait-timeout <值>`、exec 行含 `verify <deadline>`；compose 契约按服务块分别断言各自 healthcheck URL。

## 结论

- 改测方向复核：有一处既有测试改动，经核为规格驱动的合法语义反转，非迁就实现。`tests/unit/test_supervisor_startup_recovery.py:294` 将旧 `test_initial_reconcile_failure_still_reaches_control_plane`（断言先扫描、扫描失败仍达控制面）整体替换为 `test_control_plane_created_before_initial_scan`，与 AC-003「Supervisor 存活判定不被初始扫描阻塞」的新语义一致且 note.md 记录了理由；旧场景由新增 `test_initial_scan_failure_after_control_plane_started`（:330）以新次序等价保留，且其顺序断言 `["create_app", "server_serve", "scan"]` 在旧实现下必然为红（旧次序中 scan 被 await 时 server 尚未创建），具备判别力。`tests/unit/test_docker_build_contexts.py` 中 `test_copy_sources_admitted_by_dockerignore` 把「缺失 ignore 文件跳过」改为记入 rejected 失败，是按 AC-002 的强化，合法。本轮无「让断言迁就当前实现」的改测。
- 危险模式扫描：逐项扫过且无命中——无恒真断言、无删/反转/注释 expect、无 `.skip`/`.only`、无 `eslint-disable`/`@ts-ignore`/`# type: ignore`、无阈值增大掩盖（探针集成的 deadline=1 是用例输入，`wait_for(timeout=30)` 是终止守卫且有顺序断言兜底）、无条件跳过断言、无 `.fill()`/程序赋值冒充交互（本轮无前端测试改动）。mock 边界合规：fake Docker 是系统边界（Docker CLI）的替身且生产脚本被真实执行；`test_t027_readiness_probe.py` 的 `_StubCore` 位于 SupervisorCore 依赖边界，控制面 app 与探针均为生产代码经真实 HTTP/子进程运行，并断言 `reconcile_calls == 1`，未 mock 被测逻辑本身。
- 本轮新发现：6 条（important 3、minor 3）
- 未进表的提示：`tests/unit/test_docker_build_contexts.py` 的 `Dockerignore` 是测试侧对 Docker 语义的近似实现（文件头已自声明 STATIC PRECHECK），AC-002 的真实构建上下文排除只能在 t032 的真实 Docker 上判定，云端结论不得冒充；其余可选扩展（如 deploy 脚本 `status` 子命令、显式命名回退目标）不阻断本轮。
- AC 复验方式：
  - AC-001：`re_verified`——reviewer 独立重跑 `test_t027_release_controller.py` 等 5 文件共 28 条全过（自建 venv、PYTHONPATH=src/backend）；断言六镜像 ID 固定、每镜像构建一次、指针仅验收后移动、up/readiness 失败保留上一 release。构建阶段失败子项未覆盖，见 f004（minor）。
  - AC-002：`re_verified`（云端契约层）——重跑 `test_docker_build_contexts.py`，缺失 dockerignore 即失败、敏感路径永不接纳均有真实断言；真实 Docker 上下文排除按测试策略归 t032，不据此宣称目标环境已验。
  - AC-003：`re_verified`——探针集成（deadline=1 未收敛输出逐 Profile 诊断且 exit 1、reconcile 失败 exit 1）、Gateway 健康路由真实 HTTP 集成、Supervisor 启动次序两条 unit、deploy readiness/up 失败非零退出，均经重跑核对；截止参数钉值与 healthcheck 服务绑定强度见 f006（minor）。
  - AC-004：`re_verified`——探针断言 `reconcile_calls == 1` 且只经 reconcile/readiness 两入口；fake Docker 对未知子命令 exit 1，脚本若自行编排网络或停 Browser 将直接使成功用例变红，成功 deploy 在此约束下 returncode=0。
  - AC-005：`trust_prior`——同配置幂等部分有测试（manifest 相等、无 restart），但配置变化时的选择性重建只能依赖实施侧的 compose 指纹承载机制与 t032 演练第 2 条，reviewer 未能以测试复验，见 f002。
  - AC-006：`re_verified`（主行为）——回退成功重部署上一 release 并走同一 exec 验收、两种变更前拒绝（迁移过低/无 readiness 能力且拒绝发生在任何 `up` 之前）均经重跑核对；数据保留与回退验收失败两子句未复验，见 f003。
  - AC-007：`re_verified`——缺管理员密码先失败并列缺项且零构建、内部密钥 0600、管理员哨兵值与内部密钥真值不出现在 stdout/stderr/env/manifest，均经重跑核对；随机性子项见 f005（minor）。
  - AC-008：`trust_prior`——仅 prefix 冲突拒绝子项经测试复验；参数化生效与双实例并存依赖实施侧声明与 t032 演练第 5 条，见 f001。
  - AC-009：`re_verified`——AC-009 列举的云端场景（成功、超时=探针 deadline、部分失败=up/readiness 失败、重复发布、回退拒绝与回退成功、实例冲突）均有用例且重跑全过；`DOCKER_DEPLOYMENT.md` 第 7 节含 5 项真实演练步骤与现场保存规则，reviewer 已逐行读核。
  - coverage = 7 / 9
- 总体判断：测试主体可信（生产脚本实跑、探针与健康路由走真实 HTTP、无假绿模式），但 AC-005/AC-006/AC-008 各有一条已打勾子句完全无测试支撑，其中 AC-008 的核心行为与 AC-005 的选择性重建机制存在「回归不可见」的实际风险，3 条 important 未解决，FAIL。
- 系统性 follow-up：无（f001/f002/f003 均为本 task 内可补的用例，不另立项；真实环境部分已由 t032 承接）

verdict: FAIL

## Round 2 (2026-11-04T11:36:38+08:00)

- round：2
- target：`git -C '/home/hatch/workspace/CBrowser_t027' diff 1e9c7ba73626ae7a00f56fa0578eb06beda98c61`

reviewed_scope: dadc672d2cc85ac6

### 前轮 finding 复核

- t027_test_f001（AC-008 参数化无测试）——已消除。新增 `test_instance_identity_parameterized_and_independent`（`tests/unit/test_t027_release_controller.py:515-560`）以非默认 project/prefix/https_port=56662/data_root/secrets_dir/deploy_dir 实跑生产脚本，断言 manifest `instance` 字段精确等于所传值、release env 含所传 DATA_ROOT/SECRETS_DIR、双实例指针互不移动；另有 code 路回归 `test_rollback_adopts_target_release_identity` / `test_rollback_conflict_checked_against_release_prefix`（:442-479）从回退路径成对覆盖同 prefix 同项目放行与异项目拒绝。reviewer 独立重跑通过。残余子点见本轮 f007（minor）。
- t027_test_f002（AC-005 指纹机制无测试）——已消除。`test_caddy_fingerprints_recorded_and_change_sensitive`（:563-604）断言 release env 中 `CBROWSER_CADDYFILE_SHA256` 与 Caddyfile 字节 sha256 相等、`CBROWSER_FRONTEND_SHA256` 与按 dist 清单独立重算的 sha256 相等；改 Caddyfile 后再发布断言仅该指纹变化、frontend 指纹与 API 镜像 ID 不变；`test_compose_yaml_release_contract`（:780-784）断言两指纹承载位于 caddy 服务块内。断言钉的是值与变化方向，不是存在性。真实「只重建 caddy」仍归 t032 演练第 2 条（测试策略口径），不据此宣称已验。
- t027_test_f003（AC-006 两子句无测试）——已消除。`test_rollback_preserves_profile_data_and_database`（:607-623）在默认数据根预置 Profile Cookies 与数据库文件，回退后断言内容逐字节仍在；`test_rollback_readiness_failure_reports_no_success`（:626-637）以 `FAKE_READINESS=unready` 跑 rollback，断言非零退出、stdout 不含「Rolled back」、current/previous 指针保持 rel-002/rel-001。
- t027_test_f004（构建失败未覆盖）——已消除。fake docker 新增 `FAKE_FAIL_BUILD` 开关，`test_build_failure_keeps_previous_release`（:640-649）断言构建失败非零退出、指针保持 rel-001、up 次数不增。注：该开关在第一个镜像即失败，「第 N 个镜像中途失败」与首个失败走同一「指针仅验收后激活」机制，属同机制覆盖，不另立 finding。
- t027_test_f005（密钥随机性未断言）——已消除。`test_internal_secrets_are_random_per_generation`（:652-666）断言 supervisor_key 为 64 位 hex，删除四把内部密钥后再发布断言新值与旧值不同。
- t027_test_f006（截止值/健康绑定弱断言）——已消除。`test_deadlines_are_passed_to_compose_and_probe`（:669-690）钉住默认 `--wait-timeout 600` / `verify 300` 与覆盖值 42 / 77 均到达 compose 调用记录；compose 契约改为 `_service_block` 按服务块分别断言 api/gateway/supervisor 各自 healthcheck 与各自健康 URL（:762-779）。
- code 路修复新增回归（顺带复核）：`test_rollback_refuses_when_failed_deploy_raised_db_version`（:481-512）以真实迁移文件 + 验收失败发布构造已应用版本状态，断言回退在变更前被拒且 stderr 指名 0009_drill，判别力成立；`test_probe_reconcile_uses_deadline_as_its_timeout`（:693-739）在 HTTP opener 边界断言 reconcile POST 超时等于验收截止 120.0、readiness GET 为 10.0，mock 位于系统边界、被测 `probe.run` 为生产逻辑；`test_probe_report_mode_never_reconciles`（integration）以真实 HTTP 断言 report 模式 `reconcile_calls == 0`。

## Findings

### t027_test_f007 - 实例参数化测试未断言内部密钥实际落入参数化的 SECRETS_DIR

- 严重度：minor
- 锚点：AC-008「发布实例身份可参数化」中 secrets 目录参数化的文件系统落点
- 位置：`tests/unit/test_t027_release_controller.py:515-560`（`test_instance_identity_parameterized_and_independent`）；对照实现 `scripts/deploy_v2.sh:236-248`（`ensure_internal_secrets` 按 `$SECRETS_DIR` 生成密钥）
- 问题：该测试断言了 release env 中记录的 `CBROWSER_SECRETS_DIR` 值与 manifest/指针独立性，但从不断言实例 B 的内部密钥文件实际生成在 `secrets_b` 目录下。失败场景：生成路径与记录路径分叉（env 记录参数值、密钥仍写默认目录），现有测试全绿，两实例将共用默认 secrets 目录而云端不可见。因身份记录、env 传递与 compose 挂载契约已被钉住，核心参数化行为可信，此项仅为落点断言缺口，定 minor。
- 建议：在实例 B 部署后断言 `(secrets_b / "supervisor_key")` 存在且默认 secrets 目录未被该次部署新增同名文件（或断言其 mtime/内容与实例 B 发布前一致）。

## 结论

- 前轮 finding 复核：见上逐条；f001–f006 全部已消除，无换形式弱化（f002/f006 的补测均为钉值/按块绑定的强断言，非子串放宽）。
- 改测方向复核：无。本轮 diff 相对 Round 1 的测试变更全部为新增用例与 fake docker 新增失败开关，未修改任何既有断言预期、未删测试；Round 1 已核的 supervisor 启动次序语义反转维持原判（规格驱动）。
- 危险模式扫描：逐项扫过且无命中——无恒真断言、无删/反转/注释 expect、无弱化断言、无 `.skip`/`.only`/`xfail`、无 `@ts-ignore`/`# type: ignore`、无阈值增大掩盖（探针集成的 `timeout=60` 与 supervisor 测试的 `wait_for(timeout=30)` 均为终止守卫且有顺序/退出码断言兜底）、无条件跳过断言、无程序赋值冒充交互（本 task 无前端交互测试）。mock 边界合规：fake Docker 为 Docker CLI 系统边界替身且生产脚本实跑；`_StubCore` 位于 SupervisorCore 依赖边界；f002 的探针超时测试替身位于 HTTP opener 边界。
- 本轮新发现：1 条（minor 1）
- 未进表的提示：`test_caddy_fingerprints_recorded_and_change_sensitive` 只对 Caddyfile 做了变化敏感性验证，前端 dist 变化敏感性未单独成例；但 frontend 指纹值已与独立重算的期望值精确比对（非常量/非存在性断言），属可选扩展，不阻断。
- AC 复验方式：
  - AC-001：`re_verified`——独立重跑全量 t027 测试 5 文件共 40 条全过（自建临时 venv /tmp/t027r2-venv，含新增构建失败用例 f004）；六镜像固定、每镜像构建一次、失败不激活的断言均在测试文本核对。
  - AC-002：`re_verified`（云端契约层）——缺失 dockerignore 即失败与敏感路径永不接纳两条随全量重跑通过；真实 Docker 上下文排除按测试策略归 t032。
  - AC-003：`re_verified`——截止值钉值断言（f006 补测）、按服务块绑定的 healthcheck、探针 deadline 诊断与 Gateway 健康路由均经重跑核对。
  - AC-004：`re_verified`——探针 `reconcile_calls == 1` 与 report 模式 `== 0` 两条均在重跑范围内通过，脚本只经显式收敛入口。
  - AC-005：`re_verified`（云端部分）——指纹值与源哈希精确比对、Caddyfile 变化仅指纹变化、caddy 服务块承载断言经重跑通过；真实选择性重建行为按测试策略归 t032，不在此宣称。
  - AC-006：`re_verified`——回退成功、两种变更前拒绝、已应用迁移版本拒绝、数据保留、回退验收失败不报成功五类用例均经重跑通过。
  - AC-007：`re_verified`——缺管理员密码先失败、0600、哨兵/真值不泄漏、64-hex 随机性（f005 补测）均经重跑核对。
  - AC-008：`re_verified`（云端部分）——全参数部署、manifest instance 精确断言、双实例指针独立、同 prefix 冲突成对断言经重跑通过；同 daemon 真实并存互扫归 t032 演练第 5 条。落点子点见 f007（minor）。
  - AC-009：`re_verified`——成功、超时、部分失败（up/readiness/构建）、重复发布、回退拒绝与成功、实例冲突场景均有用例且重跑全过；`DOCKER_DEPLOYMENT.md` 第 7 节 5 项真实演练步骤维持 Round 1 读核结论。
  - coverage = 9 / 9
- 总体判断：Round 1 的 3 条 important 与 3 条 minor 均已以真实钉行为的补测消除，补测无迁就实现、无弱化换形；本轮仅 1 条 minor 落点断言缺口，不阻断，PASS。真实 Docker 行为按豁免口径归 t032，不据此判 FAIL。
- 系统性 follow-up：无

verdict: PASS

## Round 3 (2026-11-04T11:41:00+08:00)

- round：3
- target：`git -C '/home/hatch/workspace/CBrowser_t027' diff 1e9c7ba73626ae7a00f56fa0578eb06beda98c61`

reviewed_scope: d7fb73e3494f6c66

### 前轮 finding 复核

- t027_test_f001–f006（Round 1，important 3、minor 3）——维持 Round 2 消除结论。本轮全量 diff 复查未见补测被删改或回退；reviewer 独立重跑 t027 相关 5 文件共 40 条全过（临时 venv，PYTHONPATH=src/backend，--basetemp 与 TMPDIR 均在仓外临时目录，仓库状态未被测试运行改动）。
- t027_test_f007（Round 2，minor，实例参数化测试未断言密钥落入参数化 SECRETS_DIR）——已消除。`test_instance_identity_parameterized_and_independent`（`tests/unit/test_t027_release_controller.py:556-561`）新增断言：实例 B 部署后四把内部密钥（supervisor_key / agent_key / gateway_key / gateway_api_key）文件实际存在于参数化 `secrets_b` 目录且权限恰为 0600。判别力成立：fake repo 的默认 secrets 目录在实例 B 部署前仅有 admin_password，若生成路径与记录路径分叉（密钥仍写默认目录），`key_file.is_file()` 即为红；0600 断言为精确等值而非存在性。重跑通过。处置表（note.md Round 2 test 路 f007 行）描述与 diff 逐项一致。
- code 路 f006 交叉复核（探针单一截止的回归断言调整）——调整合法，未弱化。实现 `scripts/supervisor_readiness_probe.py` 的 `run()` 改为单一绝对截止（deadline 在入口一次定下，reconcile 的 POST 超时取同一截止的剩余量、轮询 GET 超时同路由该截止扣减并封顶 10s）。回归测试 `test_probe_reconcile_uses_deadline_as_its_timeout`（`tests/unit/test_t027_release_controller.py:744-745`）随之把 POST 超时断言由原「恰等于 120.0」改为区间 `100.0 < timeout <= 120.0`，GET 断言仍为恰等 10.0 未动。区间不是迁就实现：新语义下 POST 超时 = 调用时刻的剩余预算，其值天然小于 120 且随执行耗时浮动，精确等值断言在正确实现下也不成立；区间两端仍有判别力——下限 100 挡住原 f002 的 10 秒写死超时回归，上限 120 挡住超时超过验收截止（另起一份预算叠加在 POST 这一跳的表现）。归因明确（code f006 的语义变更，处置表已记录），属规格/实现语义变更驱动的合法改测。
- code 路 f007 交叉复核（手册限定句）——`DOCKER_DEPLOYMENT.md:53` 已补「唯一例外是 release 存放位置本身：用了自定义 `CBROWSER_DEPLOY_DIR` 的实例回退时须带同一变量，否则命中默认实例指针」，与实现一致（`scripts/deploy_v2.sh:47` DEPLOY_DIR 在载入目标 release 身份前即由调用方环境定下）。纯文档收窄表述，不触及任何测试断言，无测试侧影响。

## Findings

本轮无新 finding（编号自 f008 起续编，未启用）。

## 结论

- 前轮 finding 复核：见上；f001–f007 全部已消除，无换形式弱化。
- 改测方向复核：本轮唯一既有断言修改即探针 POST 超时「恰等 120.0 → 剩余预算区间」，经核为单一截止语义变更的必然结果且判别力保留（见上交叉复核），非让断言迁就实现；其余测试变更为 f007 的新增断言（只增不改）。无迁就实现的改测。
- 危险模式扫描：逐项扫过且无命中——无恒真断言、无删/反转/注释 expect、无弱化断言（区间断言经上文专项核查不构成弱化）、无 `.skip`/`.only`/`xfail`、无 `eslint-disable`/`@ts-ignore`/`# type: ignore`、无阈值增大掩盖（探针单请求 1.0s 超时下限是防零/负超时的实现细节，非测试阈值放宽；测试侧 `timeout=120/60` 均为终止守卫）、无条件跳过断言、无程序赋值冒充交互（本 task 无前端交互测试）。mock 边界合规同前轮：fake Docker 为 CLI 系统边界替身且生产脚本实跑，探针超时测试的替身位于 HTTP opener 边界、被测 `probe.run` 为生产逻辑。
- 本轮新发现：0 条
- 未进表的提示：无（真实 Docker 行为按豁免口径归 t032，不据此判 FAIL，同前轮）
- AC 复验方式：
  - AC-001：`re_verified`——全量重跑范围内六镜像固定、构建一次、构建/up/readiness 失败不激活等断言通过；本轮三处小改未触及该路径。
  - AC-002：`re_verified`（云端契约层）——`test_docker_build_contexts.py` 随重跑通过；真实 Docker 上下文排除归 t032，同前轮口径。
  - AC-003：`re_verified`——单一截止实现经代码查证（deadline 一次定下、POST/GET 均从同一预算扣减），调整后的回归断言经重跑通过且判别力经专项核查保留；截止值传递、按服务块 healthcheck 绑定断言随重跑通过。
  - AC-004：`re_verified`——探针 reconcile/readiness 入口与 report 模式只读断言随重跑通过，本轮改动未新增脚本侧网络编排。
  - AC-005：`re_verified`（云端部分）——Caddy 指纹值/变化敏感性与 caddy 服务块承载断言随重跑通过；真实选择性重建归 t032，同前轮口径。
  - AC-006：`re_verified`——回退成功/拒绝/数据保留/验收失败不报成功诸用例随重跑通过；手册 DEPLOY_DIR 限定句使「裸 rollback」表述与实现一致（code f007）。
  - AC-007：`re_verified`——缺密码先失败、0600、哨兵不泄漏、随机性断言随重跑通过；f007 补断言后参数化 secrets 目录的落盘与 0600 亦经重跑复验。
  - AC-008：`re_verified`（云端部分）——全参数部署、manifest instance、双实例指针独立、四密钥落入参数化目录且 0600，均经重跑通过；同 daemon 真实并存归 t032。
  - AC-009：`re_verified`——成功、超时、部分失败、重复发布、回退拒绝与成功、实例冲突场景随重跑全过；手册演练步骤维持前轮读核结论，本轮限定句未删改演练内容。
  - coverage = 9 / 9
- 总体判断：Round 2 后三处小改（探针单一截止+回归断言调整、手册限定句、实例密钥落盘断言）均与 note.md 处置表一致，未弱化任何既有断言，f007 已真实消除；本轮零新 finding，无未解决 critical / important，PASS。
- 系统性 follow-up：无

verdict: PASS

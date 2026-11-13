# Task review t027（reviewer_focus: 代码）

- task：`t027_release_controller_readiness`
- spec：`docs/tasks/t027_release_controller_readiness/task.md`
- diff_anchor：`1e9c7ba73626ae7a00f56fa0578eb06beda98c61`
- target：`git -C '<home>/workspace/CBrowser_t027' diff 1e9c7ba73626ae7a00f56fa0578eb06beda98c61`
- round：1
- reviewed_at：2026-11-04T11:36:00+08:00

reviewed_scope: b100425880c4195c

## Findings

### t027_code_f001 - 回退时实例身份被调用方环境覆盖，目标 release 的身份配置未被恢复

- 严重度：important
- 锚点：AC-006（回退恢复其全部镜像与配置）/ AC-008（实例身份参数化、隔离）；失败场景：以非默认身份发布第二实例后按文档裸命令回退，回退实际部署到默认实例的项目/prefix/数据根/secrets/端口
- 位置：`scripts/deploy_v2.sh:55-61`、`scripts/deploy_v2.sh:158-162`、`scripts/deploy_v2.sh:345-395`
- 问题：脚本启动时无条件把 `CBROWSER_COMPOSE_PROJECT/PREFIX/HTTPS_PORT/PUBLIC_ORIGIN/DATA_ROOT/SECRETS_DIR` 从调用方环境（缺省即默认值）export 到进程环境（:55-61）。`cmd_rollback` 只把目标 release 的 `.env` 经 `--env-file` 传给 compose（`compose_with`，:158-162），从不把目标 env 里的实例身份载入自身环境。Docker Compose 插值优先级中 shell 环境高于 `--env-file`，于是 compose.yaml 的 `name:`、`container_name:`、edge 网络名、数据根/secrets 挂载、HTTPS 端口与 Supervisor 的 `CBROWSER_PREFIX/CBROWSER_DATA_ROOT` 全部取调用方身份，只有镜像 ID（未被 export）取目标 release。后果：为第二实例（prefix=cbrowser-test、独立数据根）执行文档第 4 节的裸命令 `bash scripts/deploy_v2.sh rollback` 时，旧镜像会被部署到默认实例的数据根与 secrets 上，Supervisor 按默认 prefix 扫描——既未恢复目标 release 的全部配置，又可能触达另一实例资源；且 `check_prefix_conflict` 检查的也是调用方 prefix，与实际部署 prefix 不一致，冲突门禁可被绕过或误报。现有回退测试全部在默认身份下运行，未覆盖此分叉。
- 建议：`cmd_rollback` 在任何 compose 调用与 prefix 检查之前，先解析目标 `.env` 并以其身份变量覆盖/export 自身环境（或停止在脚本头部 export 身份变量、改为显式传参），并补一条「非默认身份发布后裸命令回退仍回到该实例」的 fake-CLI 回归测试。

### t027_code_f002 - readiness 探针的 reconcile 请求被写死 10 秒超时，先于验收截止时间误判失败

- 严重度：important
- 锚点：AC-003 / AC-004；失败场景：reconcile_all 耗时超过 10 秒（Profile 多或 Docker 慢）时探针直接判不 ready，发布在 300 秒验收截止时间内本可成功却非零退出
- 位置：`scripts/supervisor_readiness_probe.py:52-60`、`scripts/supervisor_readiness_probe.py:89-95`
- 问题：`_request()` 的 HTTP 超时写死 `timeout=10.0`，`run()` 调用 POST `/supervisor/v1/reconcile` 时未传剩余截止时间。而 t026 的 `reconcile_all` 是一次全量 `scan_and_reconcile_existing()`（`src/backend/cbrowser/supervisor/core.py:659-665`），同步等待对全部存量容器的扫描与收敛，耗时随 Profile 数与 Docker 状态增长，无 10 秒保证。探针一旦在 reconcile 上超时即返回 `reconcile_request_failed` 并退出 1，`CBROWSER_VERIFY_DEADLINE_SEC`（默认 300）对这一步完全不起作用——验收语义从「截止时间内收敛即成功」退化为「收敛入口须 10 秒内返回」。轮询 readiness 的单次 GET 用 10 秒超时没问题（有重试循环），问题只在一次性的 reconcile 调用。
- 建议：reconcile 请求的超时改为取验收截止时间的剩余量（或至少一个与截止时间挂钩的独立上限），并补一条 reconcile 慢响应（>10s）但随后 readiness 收敛时探针返回 0 的集成用例。

### t027_code_f003 - 回退迁移门禁比较的是当前 release manifest，不是当前数据库的实际迁移版本

- 严重度：important
- 锚点：AC-006（目标迁移版本低于当前数据库时在变更前拒绝）；失败场景：新 release 发布中途失败但其 API 已把数据库迁移到更高版本，此后回退到低迁移 release 不被拒绝，旧代码对着更高版本数据库启动
- 位置：`scripts/deploy_v2.sh:374-384`、`src/backend/cbrowser/api/app.py:112`
- 问题：`cmd_rollback` 用当前 release manifest 的 `migration_version` 作为「当前数据库版本」的代理与目标版本做字符串比较（:374-384）。但 API 在启动时即执行 `run_database_migrations`（`api/app.py:112`）：一次带新迁移的发布只要 API 容器起来过，数据库就已升到新版本，哪怕随后 readiness 验收失败、指针按 AC-001 留在旧 release。此时 manifest 代理值仍是旧版本，回退门禁会放行一个实际低于数据库版本的 release，与 AC-006 的字面契约不符。实施笔记把该代理口径写为有意决策，但 spec 契约区写的是「当前数据库」，代理与契约的差距未在 task.md 中同步——按本区契约判定为实现缺口（若要保留代理口径，应改 spec 并说明残余风险，而不是只写在 note/spec 副本里）。另：版本比较为裸字符串序（:381），当前零填充四位序号下成立，但无任何约束保证未来序号格式不变。
- 建议：回退前读取数据库实际迁移版本（如经当前 API 容器/只读 sqlite 查询 alembic_version 表）再与目标比较；无法读取时按「状态未知」拒绝。或将 AC-006 的口径正式改写为 manifest 代理并在 task.md 中注明失败发布场景的残余风险。

### t027_code_f004 - prefix 冲突检测只看运行中且带 prefix 标签的容器，部分存活的另一实例检不出

- 严重度：minor
- 锚点：AC-008（目标 prefix 已被另一运行实例占用时启动前拒绝）
- 位置：`scripts/deploy_v2.sh:228-243`
- 问题：`check_prefix_conflict` 用 `docker ps`（仅运行中容器）按 `label=com.cbrowser.prefix=$PREFIX` 过滤。compose.yaml 中固定服务只有 gateway 显式带 `com.cbrowser.prefix` 标签；当另一实例处于部分失败状态（gateway 已退出、Supervisor 与 Browser/Stream 仍在运行）时，该检查返回空集而放行，新实例 Supervisor 仍会按同 prefix 扫描并把对方 Profile 当孤儿处理——正是 AC-008 要防的场景在部分存活时漏检。
- 建议：冲突检测改查全部状态容器（`docker ps -a`）并覆盖 Supervisor 容器，或明确在文档中把门禁口径限定为「对方 gateway 运行中」并说明残余风险。

### t027_code_f005 - up 失败后的诊断路径再跑一遍全量 verify（含 reconcile 与 300 秒轮询），失败报告无独立短截止

- 严重度：minor
- 锚点：AC-003（在明确截止时间内非零退出）
- 位置：`scripts/deploy_v2.sh:168-186`
- 问题：`deploy_up_and_verify` 在 `up --wait` 已失败后，以「best-effort 诊断」为名调用 `verify_readiness`（:175-182），而该函数会再向 Supervisor 发起一次 POST reconcile（一次全量收敛动作，不只是读诊断）并按 `VERIFY_DEADLINE`（默认 300s）轮询。结果是单次发布的总耗时可达 `--wait` 600s + 诊断 300s，两段截止各自成立但总截止未声明；且在已知部署失败的现场上再次触发收敛，超出「输出逐 Profile 诊断」的必要范围。
- 建议：诊断路径改用短独立截止（如 30s）且只读 readiness 不再 POST reconcile，或在脚本与文档中明确声明总截止为两段之和。

## 结论

- 本轮新发现：5 条（important 3、minor 2）
- 未进表的提示：
  - 文件过大（按标准只列结论段）：`scripts/deploy_v2.sh` 409 行（手写脚本 minor 阈值 400，本 task 整体重写）；`src/backend/cbrowser/supervisor/runner.py` 524 行（实现源码 minor 阈值 400，本 task 净增）；`src/backend/cbrowser/gateway/server.py` 931 行（实现源码 important 阈值 800，本 task 仅 +8 行健康路由）。均未见由体量直接导致的行为不一致，不单独出 finding。
  - 圈复杂度：本 task 新写的 shell 函数与探针函数均未达 minor 阈值；`serve_supervisor` 为存量大函数，本 task 仅移动控制面创建位置、未新增分支，不计。
  - 安全扫描（diff 路径）：未发现秘密打印/落盘——内部密钥 0600 随机生成、manifest/env 不含秘密、探针输出仅 profile id/ready/诊断码且截断 200 字符；Gateway 健康路由无鉴权但只回固定存活体，与 API 既有健康契约一致，不出 finding。真实 Docker 行为（镜像构建、compose 重建语义、双实例并存）按任务豁免口径归 t032，未据此判 FAIL。
- AC 复验方式：
  - AC-001：re_verified——核对 `build_and_record_release` 五镜像各构建一次、Caddy 以 ID 固定、manifest/env 六镜像 ID 与三指纹一迁移版本齐全、指针仅在验收后原子更新、同名 release 拒覆盖；单测断言与之逐项对应。
  - AC-002：re_verified——逐个读取五个运行时 `Dockerfile.dockerignore`（browser/stream 为本 task 新增白名单），与门禁测试「缺失即失败 + 敏感路径永不接纳」断言对照。
  - AC-003：re_verified——核对 compose 三服务健康检查、Gateway 新健康路由、runner 控制面先于初始扫描启动且健康检查在容器内读 token；但探针 reconcile 超时缺陷见 f002。
  - AC-004：re_verified——脚本验收路径只有 `up --wait` + 探针（POST reconcile + 轮询 readiness），未见脚本自建网络编排或停 Browser 的代码。
  - AC-005：trust_prior——云端只验证「无显式 restart、Caddy 指纹经 env 承载、重复发布 manifest 相等」；「未变化不重建/变化只重建受影响服务」的真实 compose 行为未在云端实跑，依赖 t032 演练判定。
  - AC-006：re_verified——回退重部署 + 同一验收 + 指针语义核对通过，但身份恢复与迁移门禁两处缺口见 f001、f003。
  - AC-007：re_verified——`check_prerequisites` 先列缺项退出、`ensure_internal_secrets` 随机生成 0600、单测以哨兵值断言输出/manifest/env 无秘密真值。
  - AC-008：re_verified——身份参数化（project/容器名/prefix/edge 网络/数据根/secrets/端口）逐项落到 compose 与 release env，冲突检查在构建前执行；缺口见 f001、f004。双实例真实并存行为归 t032。
  - AC-009：re_verified——`DOCKER_DEPLOYMENT.md` 第 7 节含五项真实演练步骤与现场保存规则，云端测试覆盖成功/超时(up 失败)/部分失败(readiness 未收敛)/重复发布/回退拒绝与成功/实例冲突。
  - coverage = 8 / 9（AC-005 为 trust_prior，占比 11%，未超 30%）
- 总体判断：发布主链（不可变 release、原子指针、验收门禁、凭证分级、构建上下文）实现与 AC 基本对齐，但回退路径有三处可观测缺口（身份被环境覆盖、迁移门禁代理失真）与探针 reconcile 超时误判，未解决 important 3 条，FAIL。
- 系统性 follow-up：无（f001–f005 均为本 task 范围内修复项；真实环境验证义务已有 t032 承接，不重复立项）

verdict: FAIL

## Round 2 (2026-11-04T11:36:20+08:00)

- round：2
- 复审范围：Round 1 五条 finding 的修复（`load_release_identity`、探针 reconcile 超时与 report 模式、`applied_migration_version` 单调记录、`check_prefix_conflict` 全量扫描）及全量 diff 复查。

reviewed_scope: dadc672d2cc85ac6

## Findings

### t027_code_f006 - 探针 verify 的总时长可达约 2 倍 VERIFY_DEADLINE，单一截止语义未成立

- 严重度：minor
- 锚点：AC-003（在明确截止时间内退出）；失败场景：reconcile 耗时接近截止（如 280s/300s）后返回，轮询再获得完整 300s，脚本可在约 580s 时才判定，甚至在超过 VERIFY_DEADLINE 后才打印成功，与 spec「超过截止时间非零退出」的单一截止口径不完全一致
- 位置：`scripts/supervisor_readiness_probe.py:99`、`scripts/supervisor_readiness_probe.py:107`
- 问题：f002 的修复把 reconcile 的 HTTP 超时改为 `max(10.0, deadline_sec)`（方向正确，不再 10s 误杀），但轮询截止 `deadline = time.monotonic() + deadline_sec` 是在 reconcile 返回**之后**才起算，两个预算串行相加，总预算约为 2×VERIFY_DEADLINE，且该总口径未在脚本输出或 `DOCKER_DEPLOYMENT.md` 中声明。总时长仍有界、不产生假成功（成功仍以 readiness 收敛为准），故为 minor 而非 blocking。
- 建议：在 `run()` 入口先定总截止，reconcile 超时取剩余量、轮询共用同一截止；或在脚本与文档中明确声明 verify 总截止为「reconcile 预算 + 轮询预算」两段之和。

### t027_code_f007 - 回退身份采纳不含 DEPLOY_DIR，手册「裸命令即可」对自定义部署目录的第二实例不成立

- 严重度：minor
- 锚点：AC-008（实例身份参数化）/ 文档与实现一致性；失败场景：按手册第 6 节以 `CBROWSER_DEPLOY_DIR=$PWD/config/deploy/test-instance` 起第二实例后，按第 4 节裸命令 `bash scripts/deploy_v2.sh rollback` 回退——脚本按缺省 `config/deploy` 读指针，命中的是默认实例的 previous（或报无 previous），不是第二实例
- 位置：`scripts/deploy_v2.sh:47`、`scripts/deploy_v2.sh:274-295`（`load_release_identity`）、`DOCKER_DEPLOYMENT.md:53`
- 问题：f001 的修复从目标 release env 采纳了项目/prefix/端口/origin/数据根/secrets 六项身份（release env 中记录的身份已全覆盖，这部分修复完整）；但 release 的定位目录 `DEPLOY_DIR` 本身只能来自调用方环境或缺省值，不在 release env 记录内（先有定位才能读 env，属固有限制）。手册第 4 节「不受你当前 shell 里环境变量的影响——直接裸命令 rollback 即可」的表述未限定此前提，与第 6 节把 DEPLOY_DIR 列为第二实例必传参数并存时，会误导操作者对错误实例执行回退。
- 建议：手册第 4 节补一句限定：以自定义 `CBROWSER_DEPLOY_DIR` 部署的实例，回退时须带同一 `CBROWSER_DEPLOY_DIR`（其余身份仍由目标 release 自动采纳）。

## 结论

- 前轮 finding 复核（以 diff、代码与独立复跑为准，不采信处置表自述；本机无 pytest/uv，复跑方式为直接以 python3 调用测试函数本体，fake Docker CLI 实跑生产脚本）：
  - f001（important）：已消除。`load_release_identity`（`scripts/deploy_v2.sh:274-295`）在 `cmd_rollback` 的冲突检查与一切 compose 调用之前，从目标 release env 采纳并 export 六项身份变量，`PROJECT/PREFIX/HTTPS_PORT/PUBLIC_ORIGIN/DATA_ROOT/SECRETS_DIR` 同步更新；独立复跑 `test_rollback_adopts_target_release_identity`、`test_rollback_conflict_checked_against_release_prefix` 均 PASS。残余定位目录问题另见本轮 f007（minor）。
  - f002（important）：已消除。探针 reconcile 超时改为 `max(10.0, deadline_sec)`（`scripts/supervisor_readiness_probe.py:99`），GET 轮询仍为 10s 单次超时；独立复跑 `test_probe_reconcile_uses_deadline_as_its_timeout` PASS（断言 POST 超时=120.0、GET=10.0）。两个预算串行相加的总口径问题另见本轮 f006（minor）。
  - f003（important）：已消除。新增 `record_applied_migration` 单调记录实际已应用的最高迁移版本：`deploy_up_and_verify` 在 up 成功后、以及 up 失败后各记录一次（覆盖「API 已启动迁移但验收失败、指针未动」场景）；`cmd_rollback` 的门禁取 `max(当前 manifest 版本, applied 记录)` 为数据库下限再与目标比较。独立复跑 `test_rollback_refuses_when_failed_deploy_raised_db_version`、`test_rollback_refuses_lower_migration` 均 PASS。注：up 失败时无条件记录属保守过记录（API 可能尚未迁移时也会抬高下限，只会过拒不会误放行，与 AC-006 的拒绝方向一致，不出 finding）；版本比较仍为字符串序，现行零填充四位序号下成立。
  - f004（minor）：已消除。`check_prefix_conflict` 改为 `docker ps -a` 全量扫描，按容器名 `$PREFIX-*` 或 prefix 标签归属、再比 compose project；部分存活（gateway 已退出、supervisor 仍在）可检出；独立复跑 `test_prefix_conflict_refused_before_build` 与 f001 的冲突回归均 PASS。复核新逻辑未误伤本实例：自有 compose 容器 project 相同放行，Supervisor 直启的 Browser/Stream 容器无 compose project 标签时不触发拒绝。
  - f005（minor）：已消除。up 失败分支改为探针只读 `report` 模式（`scripts/supervisor_readiness_probe.py:134-…`）：单次 readiness 快照、10s 超时、不再 POST reconcile、不再 300s 轮询，且部署失败结论不依赖其返回值；集成测试 `test_probe_report_mode_never_reconciles` 断言 reconcile_calls==0（已查证断言本体）。
- 本轮新发现：2 条（minor 2：f006 探针总预算约为 2 倍截止未声明、f007 DEPLOY_DIR 定位不属身份采纳且手册表述过宽）
- 未进表的提示：
  - 文件过大（按标准只列结论段）：`scripts/deploy_v2.sh` 478 行（手写脚本 minor 阈值 400，本轮修复后自 409 行续增）；`tests/unit/test_t027_release_controller.py` 789 行（测试 minor 阈值 600）；`src/backend/cbrowser/supervisor/runner.py` 524 行、`src/backend/cbrowser/gateway/server.py` 931 行（同 Round 1，本轮 diff 未再触及出新问题）。均未见由体量直接导致的行为不一致，不单独出 finding。
  - 圈复杂度：探针 `run()` 与 shell 新增/修改函数均未达 minor 阈值。
  - 安全复扫（修复路径）：`load_release_identity` 只接受六个白名单键的名值对 export，不 eval env 文件内容，无注入面；`applied_migration_version` 只存迁移版本号、无秘密；report 模式输出仍仅 profile id/ready/诊断码。无新安全问题。
  - 真实 Docker 行为（compose 重建语义、双实例并存实跑）按豁免口径归 t032，未据此判 FAIL。
- AC 复验方式：
  - AC-001：re_verified——指针仅验收后原子更新、同名 release 拒覆盖、六镜像 ID 与三指纹一迁移版本记录，代码与断言逐项对照（同 Round 1）；本轮修复未触及该路径。
  - AC-002：re_verified——五个运行时 `Dockerfile.dockerignore` 与缺失即失败的门禁断言未被本轮修复改动（同 Round 1 核对结论）。
  - AC-003：re_verified——三服务健康检查、Gateway 健康路由、Supervisor 控制面先于初始扫描均在位；探针超时缺陷（f002）已修、up 失败诊断已改只读快照（f005 已修）；总截止口径残余见 f006（minor）。
  - AC-004：re_verified——验收路径仍只有 `up --wait` + 探针 verify（POST reconcile + 轮询 readiness）；report 模式仅用于失败诊断且不改变失败结论，脚本无自建网络编排或停止 Browser 的代码。
  - AC-005：trust_prior——云端仍只验证 Caddy 指纹承载与重复发布 manifest 相等；真实 compose「未变化不重建/变化只重建受影响服务」行为依赖 t032 演练判定（同 Round 1）。
  - AC-006：re_verified——回退身份覆盖（f001）与迁移门禁实际应用版本下限（f003）两处缺口均已修并独立复跑回归 PASS；回退仍走同一 readiness 验收、指针仅验收后移动、不删除数据（新增 `test_rollback_preserves_profile_data_and_database` 等断言已查证）。
  - AC-007：re_verified——前提缺项先失败列全、内部密钥随机 0600、输出/manifest/env 无秘密真值的哨兵断言未被本轮修复改动（同 Round 1 核对结论）。
  - AC-008：re_verified——身份参数化落点与冲突门禁（f004 全量扫描）已复核，`test_instance_identity_parameterized_and_independent` 独立复跑 PASS；定位目录 DEPLOY_DIR 的手册表述残余见 f007（minor）。双实例真实并存归 t032。
  - AC-009：re_verified——手册第 7 节五项演练与现场保存规则在位；云端用例覆盖成功/超时/部分失败/重复发布/回退拒绝与成功/实例冲突，本轮新增回归（身份采纳、冲突对象、已应用迁移下限、report 只读、reconcile 超时）均已查证，其中 9 个关键用例由 reviewer 独立复跑 PASS。
  - coverage = 8 / 9（AC-005 为 trust_prior，占比 11%，未超 30%）
- 总体判断：Round 1 五条 finding（important 3、minor 2）均已真实修复并有回归测试、独立复跑通过，未发现修复引入的 blocking 新问题；本轮仅 2 条 minor（总截止口径未声明、回退定位目录的手册表述过宽），不阻断，PASS。
- 系统性 follow-up：无（f006/f007 均为本 task 范围内处置项；真实环境验证义务已有 t032 承接）

verdict: PASS

## Round 3 (2026-11-04T11:39:20+08:00)

- round：3
- 复审范围：Round 2 遗留的两条 minor 修复（t027_code_f006 探针单一绝对截止、t027_code_f007 手册第 4 节 DEPLOY_DIR 限定句），test 路 t027_test_f007 补断言的交叉核对，以及最终 scope 与处置表的一致性、全量 diff 其余维度复查。

reviewed_scope: d7fb73e3494f6c66

## Findings

本轮无新 finding（编号自 f008 起续编，未启用）。

## 结论

- 前轮 finding 复核（以 diff、代码与独立复跑为准，不采信处置表自述；本机无 pytest，以 PYTHONDONTWRITEBYTECODE=1 直接调用测试函数本体复跑）：
  - f001–f005（Round 1，important 3、minor 2）：Round 2 已逐条确认消除，本轮全量 diff 复查未见回退，结论维持。
  - f006（minor）：已消除。`scripts/supervisor_readiness_probe.py:94` 在 `run()` 入口先定单一绝对截止 `deadline = time.monotonic() + max(0.0, deadline_sec)`；reconcile 的 HTTP 超时取同一截止的剩余量（:100 `max(1.0, deadline - time.monotonic())`），轮询每次 GET 的超时同样由该截止扣减（:120 `min(10.0, deadline - time.monotonic())`），循环退出与睡眠均以同一 `deadline` 判定（:131、:138），文件头注释（:7-10）与实现一致——不存在 Round 2 所述的第二份串行预算。回归断言已同步更新（`tests/unit/test_t027_release_controller.py:740-745`：POST 超时为剩余预算、≤120 且 >100），独立复跑 `test_probe_reconcile_uses_deadline_as_its_timeout` PASS。残余：单次请求超时有 1.0s 下限（防零/负超时），仅在截止前最后不足 1 秒的窗口内可能让单个在途请求在截止后约 1 秒内返回，量级与 f006 的约 280 秒预算叠加不可比，不构成新 finding。
  - f007（minor）：已消除。`DOCKER_DEPLOYMENT.md:53` 第 4 节已补限定：默认实例直接裸命令 `rollback` 即可；唯一例外是 release 存放位置本身——发布时用了自定义 `CBROWSER_DEPLOY_DIR` 的实例，回退时须带同一 `CBROWSER_DEPLOY_DIR`，否则会命中默认实例的指针；与第 6 节（:71 把 DEPLOY_DIR 列为第二实例参数）的表述一致，不再过宽。
  - test 路 f007（交叉核对）：`tests/unit/test_t027_release_controller.py:556-561` 已在实例参数化用例中补断言——四个内部密钥文件实际生成于参数化 `CBROWSER_SECRETS_DIR` 且权限为 0600，不只是 env 记录；独立复跑 `test_instance_identity_parameterized_and_independent` PASS。
  - 处置表一致性：`note.md` 中 Round 2 code 路两行（f006/f007）与 test 路 f007 一行的修复描述与最终 diff 内容逐项对得上，未发现处置表与 scope 不一致之处；另独立复跑 `test_deadlines_are_passed_to_compose_and_probe` PASS。
- 本轮新发现：0 条
- 未进表的提示：
  - 文件过大（按标准只列结论段）：`scripts/deploy_v2.sh` 478 行（手写脚本 minor 阈值 400）、`tests/unit/test_t027_release_controller.py` 798 行（测试 minor 阈值 600）、`src/backend/cbrowser/supervisor/runner.py` 524 行、`src/backend/cbrowser/gateway/server.py` 931 行——与 Round 2 复核时一致，本轮两处修复未使体量恶化（探针仍 191 行），未见由体量直接导致的行为不一致，不单独出 finding。
  - 圈复杂度：探针 `run()` 改动后分支数未达 minor 阈值；手册改动为纯文档。
  - 安全复扫（本轮触及路径）：探针改动未引入新的输入面或输出面，输出仍仅 profile id/ready/诊断码；手册新增文字不含秘密。无新安全问题。
  - 真实 Docker 行为（镜像构建、compose 重建语义、双实例并存实跑）按豁免口径归 t032，未据此判 FAIL。
- AC 复验方式：
  - AC-001：re_verified——同 Round 2 核对结论（六镜像 ID、三指纹一迁移版本、指针仅验收后原子更新、同名 release 拒覆盖）；本轮修复未触及该路径，diff 复查无回退。
  - AC-002：re_verified——五个运行时 `Dockerfile.dockerignore` 与缺失即失败的门禁断言未被本轮修复改动（同 Round 2）。
  - AC-003：re_verified——三服务健康检查、Gateway 健康路由、Supervisor 控制面先于初始扫描均在位；本轮 f006 修复后 verify 为单一绝对截止（探针 :94/:100/:120 代码查证 + 回归独立复跑 PASS），「明确截止时间内退出」的口径已成立（1 秒级单请求下限除外，见 f006 复核）。
  - AC-004：re_verified——验收路径仍只有 `up --wait` + 探针 verify（POST reconcile 后轮询 readiness，共用同一截止）；report 模式仍仅用于失败诊断，脚本无自建网络编排或停止 Browser 的代码。
  - AC-005：trust_prior——云端仍只验证 Caddy 指纹承载与重复发布 manifest 相等；真实 compose「未变化不重建/变化只重建受影响服务」行为依赖 t032 演练判定（同前轮）。
  - AC-006：re_verified——回退身份采纳、已应用迁移版本下限、同一 readiness 验收、指针仅验收后移动、不删除数据等结论同 Round 2；本轮 f007 的手册限定句使「裸命令回退」表述与 DEPLOY_DIR 固有限制一致。
  - AC-007：re_verified——前提缺项先失败列全、内部密钥随机 0600、输出/manifest/env 无秘密真值的哨兵断言未被本轮修复改动；test 路 f007 补断言后，参数化 secrets 目录的密钥落盘与 0600 亦有断言覆盖并独立复跑 PASS。
  - AC-008：re_verified——身份参数化落点与 prefix 冲突全量扫描结论同 Round 2，本轮独立复跑实例参数化用例 PASS；DEPLOY_DIR 定位限定的手册表述已补齐（f007）。双实例真实并存归 t032。
  - AC-009：re_verified——手册第 7 节五项演练与现场保存规则在位；云端用例覆盖成功/超时/部分失败/重复发布/回退拒绝与成功/实例冲突，本轮三条关键回归（单一截止、实例参数化含密钥落盘、截止值传递）由 reviewer 独立复跑 PASS。
  - coverage = 8 / 9（AC-005 为 trust_prior，占比 11%，未超 30%）
- 总体判断：Round 2 的两条 minor（f006 单一截止、f007 手册限定句）均已真实修复并有回归断言、独立复跑通过，修复未引入新问题；最终 scope 内容与 note.md 处置表一致，当前无未解决的 critical / important，本轮零新 finding，PASS。
- 系统性 follow-up：无（真实环境验证义务已有 t032 承接，不重复立项）

verdict: PASS

# Task review t054（reviewer_focus: 代码）

- task：`t054_deploy_time_network_config`
- spec：`docs/tasks/t054_deploy_time_network_config/task.md`
- diff_anchor：`e9320341a8b5c93d136fca64b1aad25825ec2898`
- target：`git -C '/home/hatch/workspace/CBrowser_t054' diff e9320341a8b5c93d136fca64b1aad25825ec2898`
- round：1
- reviewed_at：2026-11-11T19:18:40+08:00

## Round 1 (2026-11-11T19:18:40+08:00)

审查范围：相对 `e9320341a8b5c93d136fca64b1aad25825ec2898` 的完整 worktree diff（99 文件，+823/−11286 行；实施 handoff 所称“+815/−5565”只统计了未暂存部分，已暂存删除 5715 行未计入，内容本身无问题）。逐项核对：删除完整性（`lan_` / `network_service` / `publication` / `rebuild-edge` / `converge-streams` / `root-ca` / `applied_network` 全树复查）、单端口常量、指纹与回退、Origin 派生、受信代理接线、命名锁死、Dockerfile 白名单、迁移链、文档闭环；独立实跑新 t054 测试集与改写文件批。

## Findings

### t054_code_f001 - 显式 CBROWSER_EDGE_SUBNET 覆盖被派生值无条件覆盖，冲突提示的第三条出路失效

- 严重度：important
- 锚点：行为缺陷 + 任务风险区「deploy.sh 预检子网冲突并给出可执行提示」——提示本身不可执行。部署因 edge 子网冲突被拒后，操作员按提示设置显式子网再部署，仍被同一冲突拒绝，陷入死循环；不改 prefix / 数据根就无法部署。
- 位置：`scripts/deploy.sh:148-150`（`derive_instance_identity` 内 `CBROWSER_EDGE_SUBNET="$(...派生值...)"` 无条件赋值）；`scripts/deploy.sh:178`（冲突提示文案含“or set an explicit CBROWSER_EDGE_SUBNET”）；同款承诺另见 `.env.example`（“do not set them by hand unless overriding the derived subnet after a conflict refusal”）与 ADR 031（`docs/blueprint/decisions.md:382` 起“重叠即拒绝并提示改 prefix / 数据根或显式指定子网”）。
- 问题：`cmd_deploy` 先调 `derive_instance_identity` 再调 `check_edge_subnet_conflict`，显式值在检查前即被覆盖；回退路径 `load_release_identity` 从目标 release env 取值，同样不认 shell 显式值。实测复现：抽取 `derive_instance_identity` 函数单独运行，预设 `CBROWSER_EDGE_SUBNET=172.30.0.0/16`、`PREFIX=cbrowser-t005`，运行后变为派生值 `172.23.0.0/16`。对照：媒体子网池的冲突提示（`scripts/deploy.sh:576`）只给“改 prefix / 数据根”两条出路，没有该问题；本 task 给 edge 子网加的第三条出路未实现。无测试覆盖该覆盖路径（`tests/unit/test_t027_release_controller.py:652/1547` 只断言派生值被记录）。
- 建议：`derive_instance_identity` 内改为有条件赋值（已显式设置时保留显式值，仅未设置时派生）；显式值仍走 `check_edge_subnet_conflict` 校验（非法 CIDR 由 `check_edge_subnet.py` exit 2 兜底拒绝）；补 deploy.sh 测试：预设显式子网时部署采用该值、冲突预检针对该值、记录进 release env 的也是该值；回退路径沿用目标 release 记录值即可，不必另改。

### t054_code_f002 - 回退先渲染后校验：被拒回退仍改写盘上 Caddyfile，注释称“不碰磁盘”与事实不符

- 严重度：minor
- 锚点：行为缺陷（轻微）——`cmd_rollback` 自身“Refuse BEFORE changing anything”原则被局部违反。
- 位置：`scripts/deploy.sh:876-892`（`cmd_rollback` 末段）。
- 问题：`eval "$(network_config render --network-dir "$DATA_ROOT/network" --https-port "$HTTPS_PORT")"` 先把目标端口的 Caddyfile 写进 `$DATA_ROOT/network`，随后才比对 `CADDYFILE_SHA256` 与目标 manifest 的 `caddyfile_sha256`；sha 不符 `exit 1` 时，盘上 Caddyfile 已被改写为目标端口渲染，与当前 release 的 manifest `caddyfile_sha256` 不一致。注释称“This runs after the conflict checks so a refused rollback leaves the disk untouched”与事实不符。影响有限：Caddyfile 是纯派生产物（端口的确定性函数），运行中容器不受影响（挂载文件只在启动/重载时读），每次部署/回退都会重渲染，且 `deploy_up_and_verify` 不比对盘上文件，故无 live 后果。
- 建议：渲染到临时目录、比对 sha 通过后再移入 `$DATA_ROOT/network`；或把注释改为“被拒回退只改写派生产物 Caddyfile，运行中容器与指针不受影响”。

## 结论

- 本轮新发现：2 条（1 important，1 minor）。
- 未进表的提示：
  - 文件过大：`scripts/deploy.sh` 914→960 行（+46），超手写脚本 400 行阈值；属既有大文件继续增大，未造成可观测缺陷，按降级规则只列结论，不进 finding 表。其余触及文件均净减（`core.py` 3137 行、`docker_adapter.py` 2576 行、`app.py` 628 行均为既有规模且本 task 净删）。
  - 复杂度提示：`cmd_rollback` 分支关键词 13→15（新增 2 个 `if` 守卫）；函数本就庞大，新增为线性守卫，未产出缺陷，不进表。新增函数 `check_edge_subnet_conflict` 与 `scripts/check_edge_subnet.py`（166 行）分支均在个位数。
  - 命名锁死通过：`com.cbrowser.deployment-id` 全树零命中（仅 `docs/blueprint/decisions.md:342` 历史叙述中提及被驳回的偏离）；默认部署前缀仍为 `cbrowser-t005`（`src/backend/cbrowser/supervisor/runner.py:60/585`、`docker_adapter.py:234`）；deploy.sh 与 compose 的 `${CBROWSER_PREFIX:-cbrowser}` 为 main 即有的既有默认值（`git show HEAD:scripts/deploy.sh:48` 同值），非本 task 引入，不属本次偏离。
  - 实施 handoff 数字口径：所称 diff“+815/−5565”只统计了未暂存部分；相对 `e932034` 的完整 worktree diff 为 +823/−11286（99 文件），内容本身无问题。
  - 范围外观察：无。删除面与契约一致，未发现范围外功能或顺手改进；`check_edge_subnet.py` 的 IPv6 子网 `overlaps()` 经实测返回 `False`（不抛错），无问题。
- 总体判断：删除完整、接线正确，但 edge 子网冲突的显式覆盖出路是死的（f001），须修复后重审。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。OpenAPI 两文件实测零 network 路径/标签；`network_router.py`、`network_service.py` 已删，全树无残留引用。
- AC-002：TICK-VALID，re_verified。设置页网络区块只剩 `window.location.origin` / `window.location.port` 只读展示与 `networkDeployTimeNote`，表单/保存/应用/弹窗/root-ca 全删；前端 3 文件 5 测试自跑通过。
- AC-003：TICK-VALID，re_verified。compose caddy 端口为 `127.0.0.1:${PORT}:443`；`stream_ports` 硬编码 `("127.0.0.1", port)`，`stream_labels` 已删 bind/advertised 标签，`CBROWSER_WEBRTC_PUBLIC_IP` 硬编码 `127.0.0.1`。
- AC-004：TICK-VALID，re_verified。端口只从 `CBROWSER_HTTPS_PORT` 来（deploy.sh 默认值直接运行常量得出；API `_deploy_https_port` 与 Gateway `GatewayConfig` 读同一变量）；t027 51 测试自跑通过，含端口变更指纹变化；旧端口真实探测侧属 AC-010，见 AC-010。
- AC-005：TICK-VALID，re_verified。`56661` 字面量只剩 `network_config.py:15` 一处定义与 `.env.example` 示例值；`main.py` 默认值改引常量。
- AC-006：TICK-VALID，re_verified。指纹改为渲染产物 `$DATA_ROOT/network/Caddyfile` 的 sha256（`deploy.sh:676`）；回退按目标端口重渲染并校验 sha（`deploy.sh:876-892`，校验后写盘顺序见 f002 minor）。
- AC-007：TICK-VALID，re_verified。Supervisor 两端点、`rebuild_edge_proxy` / `restore_edge_proxy` / `converge_network_streams` / `rebuild_caddy_container`、Gateway 发布协议、日志网络收据 8 方法、8 个网络模型、repository 网络方法全删且无残留引用；迁移 0008（`3751fed02a4a`，down_revision 与 0007 的 `1a8db6b91744` 一致）删 `network.%` 行，迁移测试自跑通过。
- AC-008：TICK-VALID，re_verified。API 与 Gateway 同读 `CBROWSER_TRUSTED_PROXY_CIDRS`，经共享 `resolve_client_ip` 按来源限流；Caddy 发出 XFF 的真实侧属 AC-010。
- AC-009：TICK-VALID，re_verified。`client_ip` 唯一共享模块 `cbrowser/shared/client_ip.py`（原两副本逐字节相同，`git mv` 搬移）；API 三路由与 Gateway 同调同一函数；不可信对端 XFF 不被采信（peer 不在可信 CIDR 内即返回 peer_ip）；共享模块测试自跑通过。
- AC-010：TICK-VALID，trust_prior。[deploy] 真实部署：本机无 Docker/真实引擎，无法独立复验；依赖实施侧证据——fake Docker 全流程部署（t027，51 passed）+ 集成 Origin 测试 + 前端全量。须在用户机按 t032 演练补验，progress.md 已写明“本机未验证、不得记为已验”。

coverage = 9 / 10

实跑（只报实数）：新 t054 测试集 8 文件 38 passed；改写文件批 21 文件 226 passed；前端 SettingsPage 3 文件 5 passed。均用验证 venv（`PYTHONPATH=src/backend:tests`）与 Node 26.13.0 实跑。

reviewed_scope: 57822b5d09726b8e

verdict: FAIL

## Round 2 (2026-11-11T19:57:25+08:00)

审查范围：相对 `e9320341a8b5c93d136fca64b1aad25825ec2898` 的完整 worktree diff（113 文件，+2259/−11290 行）。本轮复核对象是 Round 1 修复：修复改动只涉 5 个代码/测试文件（`scripts/deploy.sh`、`tests/unit/test_t027_release_controller.py`、`tests/unit/test_t054_check_edge_subnet.py`、`tests/unit/test_t054_shared_client_ip.py`、`src/frontend/src/features/settings/SettingsPage.network.test.tsx`）加 progress.md 流程文件（以全 diff 文件名逐个 grep `t054 R1` 标记确认），未触及其他实现路径，故 Round 1 对 AC-001/002/003/005/007/008/009 的核实结论仍成立；本轮对修复点做独立实跑与变异验证，不采信处置表自述。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核：
  - **t054_code_f001（important）——已消除**。`scripts/deploy.sh:148-152` 的 `derive_instance_identity` 改为有条件赋值：`CBROWSER_EDGE_SUBNET` 为空时才取派生值（`sed -n '3p'`），已显式设置时保留；显式值仍走 `check_edge_subnet_conflict`（`scripts/deploy.sh:176-188`，非法 CIDR 由 `check_edge_subnet.py` exit 2 兜底拒绝），并照常记入 release env 与 manifest（`scripts/deploy.sh:692-693`、`735`），回退经 `load_release_identity`（`scripts/deploy.sh:606-636`，从目标 release env export 覆盖 shell 值）沿用目标记录值，`cmd_rollback` 不调用 derive。独立复现 R1 原场景：抽取函数单独运行，预设 `CBROWSER_EDGE_SUBNET=172.30.0.0/16`、`PREFIX=cbrowser-t005`，运行后仍为 `172.30.0.0/16`（R1 时被改写为 `172.23.0.0/16`）。变异验证：把条件赋值临时改回 R1 的无条件赋值，`test_deploy_uses_explicit_edge_subnet_when_set` 与 `test_deploy_refuses_when_explicit_edge_subnet_overlaps` 均变红（2 failed），改回后全绿；变异后 `deploy.sh` 以 sha256 校验恢复为修复前字节一致。新增 3 例 t027 行为测试与 5 例 `check_edge_subnet.py` 单测均真实判别（172.40.0.0/16 不可能等于派生值 172.18–31.0.0/16）。`.env.example:9-13` 与 ADR 031（`docs/blueprint/decisions.md:388`“重叠即拒绝并提示改 prefix / 数据根或显式指定子网”）的措辞与修复后实现一致，无需改动。
  - **t054_code_f002（minor）——已消除**。`cmd_rollback`（`scripts/deploy.sh:883-907`）先把目标端口 Caddyfile 渲染进 `mktemp -d` 临时目录、比对 `caddyfile_sha256` 通过后才 `cp` 进 `$DATA_ROOT/network`；sha 不符时删临时目录后 `exit 1`，注释“被拒回退不碰磁盘”修后属实。变异验证：把渲染目标临时改回 R1 的 `$DATA_ROOT/network` 直写并去掉 `cp`，`test_rollback_refuses_on_caddyfile_sha_mismatch_without_touching_disk` 变红（1 failed），改回后全绿；变异后 `deploy.sh` 以 sha256 校验恢复为修复前字节一致。`test_rollback_restores_target_port_not_current_port`（rel-001 56661 / rel-002 56662，回退后首行含 `https_port 56661` 且 sha 等于 rel-001 manifest 值）判别真实。
- 本轮新发现：0 条。
- 未进表的提示：
  - 文件过大：`scripts/deploy.sh` 现 977 行（Round 1 时 960 行，修复 +17 行；既有大文件继续增大，未造成可观测缺陷，按降级规则只列结论，不进 finding 表）。其余触及文件均净减。
  - 复杂度提示：修复未给 `cmd_rollback` 增加分支（sha 校验分支 Round 1 已有），不进表。
  - 极小观察（不进表）：`cmd_rollback` 中若 `network_config render` 本身失败，`eval` 执行其输出的 `exit N` 会使脚本直接退出，来不及 `rm -rf "$tmp_network_dir"`，残留一个空 mktemp 目录在 /tmp（tmpfs、随重启消失）。无盘上状态影响，不构成 finding。
  - 命名锁死复核通过：`com.cbrowser.deployment-id` 在 src/scripts/compose.yaml/config 全树零命中；`56661` 字面量只剩 `network_config.py:15` 一处定义（`.env.example` 示例值除外，Round 1 已核实）。
  - 变异实验的临时文件（`/tmp/deploy_r2_backup.sh`、`/tmp/r2_f001_repro.sh`）已删；`git status` 无计划外新增文件。
- 总体判断：Round 1 两条 finding 均已真实修复并经独立变异验证，修复未引入新问题；删除完整、接线正确。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。Round 1 核实仍成立（修复未触 OpenAPI/路由删除路径）；OpenAPI 两文件零 network 路径/标签。
- AC-002：TICK-VALID，re_verified。修复未触设置页实现；前端 SettingsPage 两文件 4 测试本轮自跑通过（Node 26.13.0）。
- AC-003：TICK-VALID，re_verified。Round 1 核实仍成立（修复未触 compose/Stream 绑定路径）。
- AC-004：TICK-VALID，re_verified。新 t027 显式子网测试本轮自跑通过，端口只从 `CBROWSER_HTTPS_PORT` 来、显式子网记入 release env 与 manifest。
- AC-005：TICK-VALID，re_verified。`56661` 字面量本轮全树复查只剩 `network_config.py:15` 一处定义。
- AC-006：TICK-VALID，re_verified。回退端口判别测试与 sha 篡改测试本轮自跑通过并经变异验证；指纹仍为渲染产物 sha。
- AC-007：TICK-VALID，re_verified。Round 1 核实仍成立（修复未触端点/协议/迁移删除路径）；迁移 0008 链未变。
- AC-008：TICK-VALID，re_verified。Round 1 核实仍成立（修复未触限流/来源识别路径）；Caddy 发出 XFF 的真实侧属 AC-010。
- AC-009：TICK-VALID，re_verified。共享 `client_ip` 新防御分支测试本轮自跑通过；API 与 Gateway 同调同一函数。
- AC-010：TICK-VALID，trust_prior。[deploy] 真实部署：本机无 Docker/真实引擎，无法独立复验；依赖实施侧证据——fake Docker 全流程部署（t027 本轮 98 测试集内含 56 例，见实跑）+ 集成 Origin 测试 + 前端全量。须在用户机按 t032 演练补验，progress.md 已写明“本机未验证、不得记为已验”。

coverage = 9 / 10

实跑（只报实数）：新/改写测试集 18 passed（`test_t054_check_edge_subnet.py` 5 + `test_t054_shared_client_ip.py` 8 + t027 新增 5）；t027 全文件（56 例）+ 8 个 t054 测试文件 98 passed；前端 SettingsPage 两文件 4 passed；变异实验两组（f001 两测试变红、f002 一测试变红）均按预期失败并恢复。均用验证 venv（`PYTHONPATH=src/backend:tests`）与 Node 26.13.0 实跑。

reviewed_scope: 6842bf304600a6d0

verdict: PASS

## Round 3 (2026-11-11T20:30:05+08:00)

审查范围：相对 `e9320341a8b5c93d136fca64b1aad25825ec2898` 的完整 worktree diff（113 文件，+2656/−11289 行）。本轮复核对象是 Round 2 test f005 的修复：生产侧改动只涉 `scripts/check_edge_subnet.py` 与 `scripts/deploy.sh` 的 `check_edge_subnet_conflict`（以全 diff grep `--exclude-network` 确认仅此两文件），测试侧改动只涉 `tests/unit/test_t027_release_controller.py`（fake docker 加 `FAKE_OWN_EDGE_SUBNET` 建模自有网络 + 3 例新测试）与 `tests/unit/test_t054_check_edge_subnet.py`（4 例新单测）加 progress.md 流程文件；其余实现路径未触，故 Round 1/2 对 AC-001/002/003/005/007/008/009 的核实结论仍成立。本轮对 f005 修复做独立实跑与变异验证，不采信处置表自述；另复核 Round 1 两条 finding 仍消除。

## Findings

### t054_code_f003 - check_edge_subnet.py 的 main() 圈复杂度约 23，建议拆分参数解析

- 严重度：minor
- 锚点：代码质量 / 圈复杂度标准（CC ≥ 15 且本 task 仍增加该函数分支）——非行为缺陷，无可观测坏结果
- 位置：`scripts/check_edge_subnet.py:151-226`（`main()`，76 行）
- 问题：按提示词手算规则（基数 1，每个 if/elif/for/while/except/短路 && / || 约 +1）McCabe 约 23：while 参数循环 1、--exclude-network 分支 1、非法参数分支 1 + or 1、elif 分支 1 + or 1、候选缺失 1、两个 except 各 1、冲突循环 1、重叠判断 1、名与子网双条件排除 1 + and 2、同名陈旧判断 1 + and 1、宿主接口生成式 for 1 + if 1、无冲突判断 1 + and 1、两处报错循环各 1。函数同时承担 CLI 参数解析、冲突分类、报错输出三项职责；f005 修复新增双条件排除分支与 stale_own 打印循环又增约 6 分支（新建时即约 17，已超 15 阈值）。9 例单测覆盖了各分支（本轮自跑 9 passed），故只是可维护性建议，不是缺陷；Round 1“分支均在个位数”的说法按本规则是误算。
- 建议：把 CLI 参数解析抽为 `_parse_args(argv)`（约 −6 分支），`main()` 只留冲突判定与输出；或把 stale/conflict 分类抽为小函数。不阻断。

## 结论

- 前轮 finding 复核：
  - **t054_code_f001（important）——仍消除**。`scripts/deploy.sh:155` 的有条件赋值未变；显式子网测试与回退端口测试本轮在 7 例定向集内自跑通过。
  - **t054_code_f002（minor）——仍消除**。`scripts/deploy.sh:906` 的 `mktemp -d` 临时渲染未变；`test_rollback_refuses_on_caddyfile_sha_mismatch_without_touching_disk` 本轮自跑通过。
  - **t054_test_f005（important，test 路）——生产侧修复已核实消除**。`scripts/check_edge_subnet.py` 新增 `--exclude-network <name>` 参数（`:151` 起解析，重复/缺值 exit 2）；`scripts/deploy.sh:176-196` 的 `check_edge_subnet_conflict`（deploy 与 rollback 共用同一函数，调用点 `:751` 与 `:890` 一次覆盖）传入 `--exclude-network "$PREFIX-edge"`。回退路径在调用预检前已由 `load_release_identity`（`:809`）从目标 release env 导出 `CBROWSER_EDGE_SUBNET` 并设定 `PREFIX`，故排除名与候选值均为目标 release 记录值，与 R1 f001“回退沿用目标记录值”的决定一致。fail-closed 未变：Docker 枚举失败 exit 2、非法候选 exit 2、排除名不匹配时重叠仍拒绝（均有单测）。
  - **偏离评估（名与子网双条件排除）——成立，无新缺口**。审阅建议是纯按名排除，实施方改为仅当网络名与子网同时与候选值一致时才排除，理由是：运营方改换显式子网后遗留的同名不同子网陈旧网络，纯按名排除会放行、再由 compose 以不透明方式失败；双条件判据下陈旧网络仍被拒并给出专属提示（`docker network rm <name>`）。推理成立：同名同子网的网络按定义即本实例自己的 edge 网络（子网由 prefix + 数据根派生；同 prefix 不同数据根的另一实例派生子网不同，不会被误排除，且另有 `check_prefix_conflict` 守前缀冲突）；外来网络永不排除（Name 为 None 的记录也按外来处理）。脚本级独立复现审阅者原场景（fake docker 只返回自有网络 `cbrowser-t005-edge` / `172.23.0.0/16`）：不带 flag 时真实脚本 exit 1 且 stderr 与 R2 报告原文一致（修前行为），带 `--exclude-network cbrowser-t005-edge` 时 exit 0，带不匹配的排除名时 exit 1。部署级变异验证：临时去掉 deploy.sh 的排除参数，3 例新测试中 (a) 连续部署与 (b) 部署后回退均变红、(c) 外来重叠仍绿；恢复后 sha256 与变异前字节一致，7 例定向测试复绿。
- 本轮新发现：1 条（minor f003，圈复杂度建议）。
- 未进表的提示：
  - 文件过大：`scripts/deploy.sh` 现 984 行（Round 2 时 977 行，f005 修复 +7 行；既有大文件继续增大，未造成可观测缺陷，按降级规则只列结论，不进 finding 表）。`scripts/check_edge_subnet.py` 230 行，未超手写脚本 400 行阈值。
  - 复杂度提示：`_docker_networks` CC 约 13、`_host_interface_networks` CC 约 10，均未达 15 的 minor 阈值，只列结论。`main()` 的 CC 约 23 已按表进 f003（minor）。
  - 已知边界（progress.md 已如实记录，接受）：改数据根致派生子网变化而前缀不变时，旧同名网络与新候选子网不重叠（/16 互不相交）故预检放行，compose 对已存在同名不同子网网络的处理属部署侧行为，本机无 Docker 未验证；显式子网改换后旧网络仍在时，若新旧子网重叠则预检以陈旧网络为由拒绝（须先 `docker network rm`），若不重叠则放行、由 compose 侧决定。该边界是预检职责（子网重叠）之外的名字冲突类问题，非本次修复引入，且失败形态为部署时可见报错而非静默错服，故不进表。
  - 命名锁死复核通过：`com.cbrowser.deployment-id` 在 src/scripts/compose.yaml/config 全树零命中；`56661` 字面量只剩 `network_config.py:15` 一处定义（`.env.example` 示例值除外，Round 1 已核实）。
  - 变异实验的临时文件（`/tmp/r3probe/*`）已删；`git status` 无计划外新增文件；变异后 `deploy.sh` 以 sha256 校验恢复为变异前字节一致。
- 总体判断：f005 的生产侧修复真实有效（双条件排除的偏离理由成立），Round 1 两条 finding 仍消除；仅剩 1 条 minor（圈复杂度建议），不阻断。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。f005 修复未触 OpenAPI/路由删除路径（生产改动仅预检两文件）；R1 核实仍成立。
- AC-002：TICK-VALID，re_verified。f005 修复未触前端；R2 核实（SettingsPage 两文件 4 测试）仍成立。
- AC-003：TICK-VALID，re_verified。f005 修复未触 compose/Stream 绑定路径；t054 compose 结构测试在本轮 105 例集内通过。
- AC-004：TICK-VALID，re_verified。连续部署测试（同一实例二次部署成功）本轮自跑通过；端口只从 `CBROWSER_HTTPS_PORT` 来、显式子网记入 release env 与 manifest 未变。
- AC-005：TICK-VALID，re_verified。`56661` 字面量本轮全树复查只剩 `network_config.py:15` 一处定义。
- AC-006：TICK-VALID，re_verified。回退端口判别测试（56661/56662）与 sha 篡改测试本轮自跑通过并经变异验证；指纹仍为渲染产物 sha。
- AC-007：TICK-VALID，re_verified。f005 修复未触端点/协议/迁移删除路径；R1 核实仍成立。
- AC-008：TICK-VALID，re_verified。f005 修复未触限流/来源识别路径；共享 client_ip 测试在本轮 105 例集内通过。
- AC-009：TICK-VALID，re_verified。共享 `client_ip` 仍为唯一模块，API 与 Gateway 同调同一函数；防御分支测试在本轮 105 例集内通过。
- AC-010：TICK-VALID，trust_prior。[deploy] 真实部署：本机无 Docker/真实引擎，无法独立复验；依赖实施侧证据——fake Docker 全流程部署（t027 本轮 59 例全绿，含连续部署与部署后回退成功）+ 集成 Origin 测试 + 前端全量。须在用户机按 t032 演练补验，progress.md 已写明“本机未验证、不得记为已验”。

coverage = 9 / 10

实跑（只报实数）：`test_t054_check_edge_subnet.py` 9 passed；t027 全文件（59 例）+ 8 个 t054 测试文件共 105 passed；定向 7 例（3 例 f005 + 2 例 f001 + 2 例 f002）变异前全绿、变异时 (a)(b) 变红 (c) 仍绿、恢复后复绿；脚本级复现 3 次（无 flag exit 1 / 正确排除 exit 0 / 错名排除 exit 1）。均用验证 venv（`PYTHONPATH=src/backend:tests`）实跑。

reviewed_scope: 2c64edb35387bb4a

verdict: PASS

## Round 4 (2026-11-11T21:01:57+08:00)

审查范围：相对 `e9320341a8b5c93d136fca64b1aad25825ec2898` 的完整 worktree diff（113 文件，+2817/−11289 行；较 Round 3 的 +2656 增加 161 行，来自 f003 重构净增与 progress.md / review 文件的过程记录，无新增实现文件）。本轮复核对象是 Round 3 code f003 的修复：改动只涉 `scripts/check_edge_subnet.py`（mtime 2026-11-11 20:42 CST）与 progress.md 流程文件（20:55 CST），deploy.sh 与全部测试文件 mtime 均停在 f005 修复轮，未被本轮修复触及；故 Round 1–3 对 AC-001/002/003/005/007/008/009 的核实结论仍成立。本轮对 f003 修复做独立实跑与行为比对，不采信处置表自述。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核：
  - **t054_code_f003（minor）——已消除**。`scripts/check_edge_subnet.py` 按建议拆分：CLI 参数解析抽为 `_parse_args(argv)`（`:155-179`，非法参数抛 `_UsageError`，`main()` 统一打印 usage 并 return 2），冲突分类抽为 `_classify_overlaps(existing, candidate, exclude_network)`（`:182-216`，返回 `(conflicts, stale_own)`），`main()`（`:219-258`）只留解析调用、候选校验、枚举、宿主接口合并与报错输出。圈复杂度以提示词手算规则独立复核（另以 AST 计数器交叉验证，两者一致，除 `_docker_networks` 一处）：`main()` **10**（Round 3 时 23），`_parse_args` **8**，`_classify_overlaps` **8**，均低于 15 的 minor 阈值；`_docker_networks` **14**（修复方称 13，系漏计 `ids` 推导式的 `if line.strip()` 守卫；仍低于 15，无结论变化）、`_host_interface_networks` **10**。双条件排除逻辑逐行比对 Round 3 描述原文照搬：名与子网同时一致才排除（`name == exclude_network and net == candidate`），同名不同子网进 `stale_own`、外来网络进 `conflicts`，无 Name 的记录按外来处理；`_parse_args` 的重复 flag / 缺值 / 未知 flag / 第二位置参数 / 缺候选分支与旧内联解析语义一致（含 flag 在候选之前也可解析）。
  - **行为同一性独立实测**：以 fake docker（自有网络 `cbrowser-t005-edge` / `172.23.0.0/16`）跑 12 个 CLI 场景，exit 码与 stderr 文本全部符合预期——无 flag 时 exit 1 且 stderr 与 Round 2 报告原文逐字一致（`edge subnet 172.23.0.0/16 overlaps Docker network subnet 172.23.0.0/16`）；正确排除 exit 0；错名排除 exit 1；陈旧同名不同子网（`172.23.128.0/17`）exit 1 且含 `docker network rm cbrowser-t005-edge` 专属提示；无重叠 exit 0；重复 flag / 缺值 / 未知 flag / 第二位置参数 / 缺候选均 exit 2 且 usage 行逐字一致；非法候选 exit 2；flag 在候选之前 exit 0。9 例单测全部通过且仍覆盖各分支（重构未新增测试，行为未变，无需新增）。
  - **t054_code_f001（important）——仍消除**。`scripts/deploy.sh:154-157` 的有条件赋值未变（`if [ -z "${CBROWSER_EDGE_SUBNET:-}" ]` 才取派生值）；显式子网测试本轮在 105 例集内通过。
  - **t054_code_f002（minor）——仍消除**。`scripts/deploy.sh:906` 的 `mktemp -d` 临时渲染未变；sha 篡改拒绝测试本轮在 105 例集内通过。
  - **t054_test_f005（important，test 路）——生产侧修复仍消除**。`scripts/deploy.sh:189` 的 `check_edge_subnet_conflict` 仍传入 `--exclude-network "$PREFIX-edge"`；连续部署与部署后回退测试本轮在 105 例集内通过。
- 本轮新发现：0 条。
- 未进表的提示：
  - 文件过大：`scripts/deploy.sh` 仍 984 行（本轮修复未触，未再增大；既有大文件，未造成可观测缺陷，按降级规则只列结论，不进 finding 表）。`scripts/check_edge_subnet.py` 230→262 行（+32），未超手写脚本 400 行阈值。
  - 复杂度提示：`main()` CC 10 与 `_host_interface_networks` CC 10 达结论段提示线（≥10），不进 finding 表；`_docker_networks` CC 14 未达 15 的 minor 阈值，只列结论。
  - 命名锁死复核通过：`com.cbrowser.deployment-id` 在 src/scripts/compose.yaml/config 全树零命中；`56661` 字面量只剩 `network_config.py:15` 一处定义（`.env.example` 示例值除外，Round 1 已核实）。
  - 探针临时文件（`/tmp/r4probe/*`）已删；`git status` 无计划外新增文件（无未跟踪文件）。
- 总体判断：f003 的重构真实完成且行为同一性经独立实测证实，Round 1–3 的 finding 均仍消除；本轮 0 新发现。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。f003 修复只触预检脚本，未触 OpenAPI/路由删除路径；Round 1 核实仍成立。
- AC-002：TICK-VALID，re_verified。f003 修复未触前端；Round 2 核实（SettingsPage 两文件 4 测试）仍成立。
- AC-003：TICK-VALID，re_verified。f003 修复未触 compose/Stream 绑定路径；t054 compose 结构测试在本轮 105 例集内通过。
- AC-004：TICK-VALID，re_verified。连续部署测试本轮自跑通过；端口只从 `CBROWSER_HTTPS_PORT` 来、显式子网记入 release env 与 manifest 未变。
- AC-005：TICK-VALID，re_verified。`56661` 字面量本轮全树复查只剩 `network_config.py:15` 一处定义。
- AC-006：TICK-VALID，re_verified。回退端口判别测试（56661/56662）与 sha 篡改测试本轮自跑通过；指纹仍为渲染产物 sha。
- AC-007：TICK-VALID，re_verified。f003 修复未触端点/协议/迁移删除路径；Round 1 核实仍成立。
- AC-008：TICK-VALID，re_verified。f003 修复未触限流/来源识别路径；共享 client_ip 测试在本轮 105 例集内通过。
- AC-009：TICK-VALID，re_verified。共享 `client_ip` 仍为唯一模块，API 与 Gateway 同调同一函数；防御分支测试在本轮 105 例集内通过。
- AC-010：TICK-VALID，trust_prior。[deploy] 真实部署：本机无 Docker/真实引擎，无法独立复验；依赖实施侧证据——fake Docker 全流程部署（t027 本轮 59 例全绿，含连续部署与部署后回退成功）+ 集成 Origin 测试 + 前端全量。须在用户机按 t032 演练补验，progress.md 已写明“本机未验证、不得记为已验”。

coverage = 9 / 10

实跑（只报实数）：`test_t054_check_edge_subnet.py` 9 passed；t027 全文件（59 例）+ 8 个 t054 测试文件共 105 passed；12 个 CLI 场景探针（fake docker，自有网络 `cbrowser-t005-edge` / `172.23.0.0/16`）exit 码与 stderr 全部符合预期；圈复杂度 AST 计数器交叉验证（main 10、`_parse_args` 8、`_classify_overlaps` 8、`_docker_networks` 14、`_host_interface_networks` 10）。均用验证 venv（`PYTHONPATH=src/backend:tests`）实跑。

reviewed_scope: e5c994e577897427

verdict: PASS

## Round 5 (2026-11-11T21:32:41+08:00)

审查范围：相对 `e9320341a8b5c93d136fca64b1aad25825ec2898` 的完整 worktree diff（113 文件，+2974/−11289 行）。本轮复核对象是 Round 4 test f006 的修复：mtime 核实改动只涉 `tests/unit/test_t054_check_edge_subnet.py`（13:13 CST，新增 1 例参数化测试）与 progress.md 流程文件（13:28 CST）；`scripts/deploy.sh`（12:28 CST）与 `scripts/check_edge_subnet.py`（12:42 CST）mtime 均停在 f005 / f003 修复轮，本轮未触生产代码；故 Round 1–4 对 AC-001/002/003/005/007/008/009 的核实结论仍成立。本轮对 f006 修复做独立实跑与行覆盖探针，不采信处置表自述。本轮为最后一轮（限额 5）。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核：
  - **t054_test_f006（minor，test 路）——已消除**。`tests/unit/test_t054_check_edge_subnet.py:253` 新增 1 例参数化测试 `test_parse_args_usage_errors_return_two`，4 个入参：重复 `--exclude-network`、flag 缺值、未知 `--bogus`、第二位置参数，各断言 exit 2 且 stderr 含 usage 文本；另以 guard（`subprocess.run` 被 monkeypatch 为必抛错的桩）断言解析失败前不触 subprocess。未改任何生产代码。
  - **行覆盖探针独立核实（`sys.settrace`，/tmp 一次性探针，已删）**：4 例与两处 `raise _UsageError` 的映射与测试注释逐字一致——重复 flag 与缺值均走到 `scripts/check_edge_subnet.py:169`（仅 :169），未知 flag 与第二位置参数均走到 `:173`（仅 :173），`:178`（缺候选）均未走到；4 例均为 exit 2 且 stderr 含 `usage: check_edge_subnet.py <candidate-cidr>`。测试注释所称行号与 `grep -n "raise _UsageError"` 实测一致（:169 / :173 / :178）。
  - **断言非空转**：usage 文本只在 `main()` 的 `except _UsageError` 分支打印（`scripts/check_edge_subnet.py:219-226`）；exit 2 也出现在非法候选路径，但其 stderr 为 `invalid candidate subnet ...` 而非 usage，故“exit 2 + 含 usage”组合可判别，不会把其他 exit 2 误认作解析失败。
  - **guard 真实**：`main()` 先调 `_parse_args` 再调 `_docker_networks()` / `_host_interface_networks()`（`scripts/check_edge_subnet.py:219-242`），枚举只在解析成功后发生；4 例执行中 guard 从未触发，证实解析失败前无 subprocess 调用。`module.subprocess` 即标准库 `subprocess` 模块，monkeypatch 只在单测内生效、由 pytest 固件还原，无跨测试污染。
  - **t054_code_f001（important）——仍消除**。`scripts/deploy.sh:155` 的有条件赋值未变；显式子网测试本轮在 109 例集内通过。
  - **t054_code_f002（minor）——仍消除**。`scripts/deploy.sh:906` 的 `mktemp -d` 临时渲染、sha 比对通过后才 `cp` 进 `$DATA_ROOT/network` 未变；sha 篡改拒绝测试本轮在 109 例集内通过。
  - **t054_test_f005（important，test 路）——生产侧修复仍消除**。`scripts/deploy.sh:189` 的 `check_edge_subnet_conflict` 仍传入 `--exclude-network "$PREFIX-edge"`；连续部署与部署后回退测试本轮在 109 例集内通过。
  - **t054_code_f003（minor）——仍消除**。`scripts/check_edge_subnet.py` 的 `_parse_args` / `_classify_overlaps` / `main()` 拆分未变（本轮零生产改动）；圈复杂度与 Round 4 核实值一致（`main()` 10、`_parse_args` 8、`_classify_overlaps` 8、`_docker_networks` 14、`_host_interface_networks` 10，均低于 15 的 minor 阈值）。
- 本轮新发现：0 条。
- 未进表的提示：
  - 文件过大：`scripts/deploy.sh` 仍 984 行（本轮未触，未再增大；既有大文件，未造成可观测缺陷，按降级规则只列结论，不进 finding 表）。`scripts/check_edge_subnet.py` 262 行、`tests/unit/test_t054_check_edge_subnet.py` 265 行，均未超阈值。
  - 复杂度提示：`main()` CC 10、`_docker_networks` CC 14、`_host_interface_networks` CC 10，均未达 15 的 minor 阈值，只列结论。
  - 命名锁死复核通过：`com.cbrowser.deployment-id` 在 src/scripts/compose.yaml/config 全树零命中；`56661` 字面量只剩 `network_config.py:15` 一处定义与 `.env.example:3` 示例值。
  - `git status` 无未跟踪文件（无 `??` 项），无 reviewer 看不到的未跟踪交付文件。探针临时文件（`/tmp/r5probe/*`、`/tmp/r5probe-basetemp*`）已删。
  - 已知流程事项（test 路 Round 4 已记录，不进表）：`test_repo_hygiene.py` 的违规集合含各轮审阅报告（报告内含 `/home/hatch/` 绝对路径，系本提示词格式要求）；该测试在基线中已红，属流程文件问题，不影响任务交付物。
- 总体判断：f006 的回归防护缺口已真实补齐（4 种错误分支均有回归测试且经行覆盖证实），Round 1–4 的 finding 均仍消除；本轮 0 新发现，最后一轮收口。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本轮零生产改动，Round 1 核实（OpenAPI 零 network 路径/标签、网络模块全删）仍成立。
- AC-002：TICK-VALID，re_verified。本轮零生产改动，Round 2 核实（设置页只读展示、表单全删）仍成立。
- AC-003：TICK-VALID，re_verified。本轮零生产改动；t054 compose 结构测试在本轮 109 例集内通过。
- AC-004：TICK-VALID，re_verified。本轮零生产改动；连续部署测试本轮在 109 例集内通过；端口只从 `CBROWSER_HTTPS_PORT` 来未变。
- AC-005：TICK-VALID，re_verified。`56661` 字面量本轮全树复查只剩 `network_config.py:15` 一处定义与 `.env.example` 示例值。
- AC-006：TICK-VALID，re_verified。本轮零生产改动；回退端口判别测试（56661/56662）与 sha 篡改测试本轮在 109 例集内通过；指纹仍为渲染产物 sha。
- AC-007：TICK-VALID，re_verified。本轮零生产改动，Round 1 核实（端点/协议/迁移删除）仍成立。
- AC-008：TICK-VALID，re_verified。本轮零生产改动；共享 client_ip 测试在本轮 109 例集内通过。
- AC-009：TICK-VALID，re_verified。本轮零生产改动；共享 `client_ip` 仍为唯一模块，防御分支测试在本轮 109 例集内通过。
- AC-010：TICK-VALID，trust_prior。[deploy] 真实部署：本机无 Docker/真实引擎，无法独立复验；依赖实施侧证据——fake Docker 全流程部署（t027 本轮 59 例全绿，含连续部署与部署后回退成功）+ 集成 Origin 测试 + 前端全量。须在用户机按 t032 演练补验，progress.md 已写明“本机未验证、不得记为已验”。

coverage = 9 / 10

实跑（只报实数）：`test_t054_check_edge_subnet.py` 13 passed（9 既有 + 4 新增）；t027 全文件（59 例）+ 8 个 t054 测试文件共 109 passed；行覆盖探针 4 例（`sys.settrace`）映射与测试注释逐字一致、exit 码与 stderr 全部符合预期。均用验证 venv（`PYTHONPATH=src/backend:tests`）实跑。

reviewed_scope: 1e4028e691635540

verdict: PASS

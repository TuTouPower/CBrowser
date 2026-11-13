# 测试

CBrowser 质量门禁与测试契约规范。章节名 `verification_policy` / `verification_notes` / `doctor_cmd` / `test_cmd` / `blackbox_verify` 是 preflight 与 skill 的机械锚点，不得改名；命令写在对应章节的代码块内，严格按 Bash 的 `-e -o pipefail` 执行。

## verification_policy

project_configured

## verification_notes

当前项目采用多层验证体系与专项技术探针机制：

1. **模板与工作流工具链契约**：通过运行 `.repo_template/tests`（带 `-m contract` 标记）验证 task 状态机、文档解析及仓库整洁度，通过数量以实际输出为准；
2. **业务后端单元测试基线**：通过 `uv` 运行 `src/backend/tests`，涵盖现有 API 接口、鉴权、下载捕获、数据库及生命周期，通过数量以实际输出为准；
3. **前端测试基线与 Node 26 LTS 门禁**：
    - 宿主构建 Node 固定为 26 LTS（仓库 `.mise.toml` 固定 26.13.0，`src/frontend/package.json` 的 `engines.node=">=26.0.0 <27"`）；前端门禁 `npm test` 的 `pretest` 与 `npm run build` 的 `build` 链首先执行 `node scripts/check_node.mjs`，版本不满足即失败并输出所需范围（t033 AC-004）。
    - jsdom 30.1.3 + Vitest 5.1.0 下不再需要 `NODE_OPTIONS=--no-experimental-webstorage`：jsdom 30 + Vitest 5 的 SPIKE 在 Node 24.21 实测 1 项 smoke 通过，完整门禁在 Node 26.13 下 216 项 Vitest 全绿（t033 SPIKE 结论，替代 d001 早期的 `--no-experimental-webstorage` 变通）。`scripts/run_gates.sh` 两处 `NODE_OPTIONS` 已移除；
    - `npm test` 内含 `test:types` 前置门禁：`tsconfig.test.json` 以与生产相同的严格选项（含 `noUncheckedIndexedAccess`）检查全部测试文件（node 内置模块类型来自 devDependency `@types/node`）；测试夹具、桩与事件字面量必须满足生成类型的完整线形状，不完整或名实不符的测试在该门禁下直接失败；
    - 严格禁止在业务代码或测试中就地弱化断言，禁止引入隐式不可见的环境改动；
4. **容器黑盒与健康检查**：通过 curl 检查运行中的容器健康探针 `http://127.0.0.1:56661/api/health`，并支持通过 ego-browser 执行端到端网页交互自动化验证；
5. **专项运行时技术验证探针规范**：
    - 规则与前置：严禁就地修改或运行 `docs/archive/spikes/` 下的代码；必须将归档脚本复制到自身专属的 `.scratch/<probe_name>/` 目录下执行；
    - 命名冲突防御：运行容器必须使用专属防冲突前缀（如 `probe-t001-*`），探针执行结束后必须执行清理，彻底销毁临时容器、网络与独立卷；
    - 独立执行：无需也不能编写庞大的全量探针大一统运行脚本（No giant all-probes runner needed），各技术专题保持完全独立的测试入口；
6. **环境基准与豁免声明**：
    - 运行硬件基准：MacBook Pro M1 Max（10核 CPU，64 GiB 统一内存，macOS 26.5.2，arm64），OrbStack Docker 引擎（10 CPU，~15.66 GiB 内存配额，CPU 纯软件编码无 GPU 预算）；
    - 公网候选可达性与原生 Linux x86_64 环境验证正式记为 `NOT_RUN / USER_WAIVED`（用户明确指示豁免）；
    - 后续第 19 章 10 并发流容量、8 小时稳定性及 1000 次 IME/剪贴板压力测试属于后续任务验收范围，本文不做虚假的 P95 性能承诺。

- t022 故障矩阵（本机已验，真实环境义务见 p024）：CDP rearm ACK 分类、事件投递三态与死信游标、生命周期冲突真实 HTTP 三态、双族网络策略失败 DROP 兜底、注册双预算（429/窗口恢复/在途释放/网关重启）、SSE 快照私有化与基点交接并发、缓存代次封存与篡改重验、Selkies ABI 适配层契约、配额严格拒绝与 stop 幂等、search-defaults 路由与围栏映射。真实 Docker/Chrome 拓扑、keymap 真实调用顺序与多 Agent 集群恢复为黑盒条款，按用户豁免口径跳过并立 p024 追踪，不以本机替代验证冒充真实运行证据。

- t026 reconciliation 故障矩阵（本机已验，真实环境义务归 t032 AC-009）：Gateway 替换重附着（unit 收敛双测 + adapter 双测）、网络事件唤醒扫描（runner 代码路径，真实事件流归 t032）、API 离线只恢复附着（unit）、协议拒绝结构化与不可修复分类（真实 Gateway 集成）、地址冲突与池耗尽（adapter 双测按 d029 行为建模 + e2e 真实 Docker 用例）、规格迁移 Stream-only 替换（unit）、策略漂移 Stream 替换/Browser fail-closed（unit + network_policy 渲染-校验全等单测）、并发与幂等（收敛预算与 fail-close 单次语义 unit）、恢复失败预算耗尽（unit）。真实 Docker 用例在 `tests/e2e/test_supervisor_reconciliation_e2e.py`（daemon 与 `CBROWSER_RUNTIME_TEST_IMAGE` 门控，本机无 Docker 时跳过、不得记为已验）；全栈场景（真实 Gateway 镜像拒绝、容器内 netns 漂移、API 进程离线）在 t032 以 REQUIRED_E2E_ENV 镜像集与 supervisor_recovery_probe fixtures 实跑。

- t027 发布验收矩阵（云端已验，真实环境义务归 t032 AC-009）：生产脚本 `scripts/deploy.sh` 由 fake Docker CLI 在仓库副本中实跑（`tests/unit/test_t027_release_controller.py`），覆盖每镜像只构建一次、六镜像 ID 与指纹/manifest 固定、缺管理员密码先失败列缺项、内部密钥 0600 生成且秘密不出现在输出/manifest/env、up 失败与 readiness 未收敛时上一 release 保持 current、相同配置重复发布幂等且无 restart、prefix 异项目冲突启动前拒绝（全量 ps -a 按名/标签归属）、回退成功与回退拒绝（迁移版本过低/无 readiness 能力时零 up 调用）、回退采用目标 release 身份而非调用方 shell 环境、失败发布已应用迁移版本抬高回退下限、探针 reconcile 以验收截止为超时且 report 模式只读不触发 reconcile；readiness 探针 `scripts/supervisor_readiness_probe.py` 对真实 Supervisor 控制面（stub core）走真实 HTTP 集成（`tests/integration/test_t027_readiness_probe.py`）；Gateway 健康路由走真实 Gateway harness 集成；构建上下文门禁对任一运行时镜像缺失 ignore 规则失败、且断言 data/secrets/.scratch 永不被任一白名单接纳。真实冷构建、重复发布、回退与双实例并存演练在 t032 按 `DOCKER_DEPLOYMENT.md` 的演练步骤实跑，云端 fake 结果不得记为真实部署 PASS。

## doctor_cmd

环境前置检查：契约测试可成功收集；另需 `md_kx` 在 PATH。预览帧的严格 JPEG 校验（`jpeginfo --check -`，d040）由门禁唯一入口 `scripts/run_gates.sh` 在环境准备阶段确定性提供：复用 PATH 内或 `.scratch/jpeginfo/` 缓存的二进制，并按 d040 契约实测（合法帧退出 0、补回 EOI 的截断帧非零），不满足即 fail closed。不做系统安装、不联网、不在 doctor 阶段人工提供。

```bash
export TMPDIR="$(mktemp -d)"
mkdir -p "$TMPDIR"
pytest .repo_template/tests -q --collect-only -m contract
command -v md_kx
```

## test_cmd

本仓不使用 GitHub Actions CI。日常全量门禁的唯一入口是 `scripts/run_gates.sh`；`test_cmd` 中的模板契约命令行仅为模板门禁标记，实际执行以脚本为准；它依次运行模板契约、后端单元、后端集成、前端测试与生产构建。

```bash
pytest .repo_template/tests -q -m contract
# 全量门禁：scripts/run_gates.sh
```

## blackbox_verify

真实 Docker/Chrome 黑盒通过同一入口的 E2E 必需模式执行；缺少镜像、缓存或 Chrome 时在会话开始即失败并列出缺项。必需模式下，镜像类环境变量还须通过不可变身份校验（`tests/fixtures/e2e_env.py` 的 `image_identity_problems`）：值必须是 `sha256:<64 位十六进制>` 的镜像 ID、本地存在且可解析，tag、短摘要或本地不存在一律在收集期失败封闭并逐项列出，不得降级为跳过。

```bash
CBROWSER_RUN_E2E=1 scripts/run_gates.sh
```

门禁证据模式：设置 `CBROWSER_GATE_EVIDENCE_DIR=<dir>` 运行 `scripts/run_gates.sh` 时，各 suite 逐个执行到底（单 suite 失败不中止后续 suite），每 suite 的脱敏日志（`scripts/redact_evidence.py` 处理 token/password/secret/api_key/authorization 与 Bearer/会话 Cookie）、JUnit XML（pytest suite）与退出码保留在证据目录，并生成 `manifest.json`：含逐 suite 的名称、完整命令、退出码、log 与 junit 路径、运行镜像的不可变身份（`image_identity` 字段，取自同一身份校验）与总判定 `all_passed`；任一 suite 非零时总退出码非零。未设置该变量时保持默认 fail-fast 行为。

## gate_timeout_seconds

1800

## Stream Runtime 组件验证

运行 t004/t015 组件验收前，按照 docs/guides/stream_runtime_validation.md 提供 Browser/Stream 不可变镜像 ID 和只读引擎缓存。完整媒体测试通过官方 Mac Google Chrome，覆盖双 Peer、复制标签、刷新、关闭首 tab、可见性暂停/恢复、Viewer 断线 resume、共享策略、真实组合输入与 Browser 生存性；媒体为同机直连，无 coturn/TURN。

```bash
# 统一入口：scripts/run_gates.sh；E2E 使用 CBROWSER_RUN_E2E=1 scripts/run_gates.sh
```

会话建立时延与候选类型（t019）：真实 Chrome 黑盒须断言新建会话的 ICE 候选集仅含 `host` 类型、远端候选地址恒为 `127.0.0.1`（不出现 `srflx`/`relay`/`prflx`），且侧边栏切换已运行 Profile 与同 Profile 刷新重建会话到首帧均不超过 5 秒；用例在 `tests/e2e/test_frontend_app_e2e.py`（`test_t019_switch_and_refresh_first_frame_within_5s_host_only`），经 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 执行。Stream entrypoint 的 ICE-lite 启动参数由 unit 门禁 `tests/unit/test_stream_ice_config.py` 守护，防止回退 Selkies 默认外部 STUN/TURN。

先创建允许写域内 TMPDIR，不能依赖不存在的目录让 pytest 回退系统 /tmp。

## 门禁依赖与证据完整性（t024）

- 门禁依赖由 `uv.lock` 单一来源导出：`scripts/generate_requirements.sh` 以 PEP 735 依赖组（api / gateway / supervisor / browser / stream / gate）分别 `uv export --only-group`，生成各镜像 `requirements.txt` 与 `scripts/gate-requirements.txt`；`tests/unit/test_t034_dependency_lock.py` 在 unit suite 中逐组比对生成物与锁文件，手改或锁过期即失败（t034 AC-002）。`scripts/run_gates.sh` 以 `GATE_PYTHON_MINOR=3.15`（与全部运行时镜像一致）建单一 venv 从导出锁安装后依次执行契约/unit/integration/前端/构建；本地无 3.15 时 uv 明确失败，unit suite 同时断言解释器主次版本（t034 AC-003）。
- 前端构建戳为 v2 格式：必需输入（index.html、package.json、package-lock.json）缺失拒绝生成；配置五件套的 present/absent、src/ 与 public/ 全量文件哈希、声明的环境值（allowlist）共同决定新鲜度；所有实际消费 dist 的探针（浏览器 harness、frontend probe、E2E collection 钩子）在复制/托管前校验，dist 存在即校验、与测试文件命名无关。
- 测试等待统一走 `tests/fixtures/wait.py` 的 deadline + 最后观测助手；时间敏感逻辑用注入 clock，不 patch 标准库 time 模块对象。共享 Docker 替身在 `tests/fixtures/docker_doubles.py`，与真实 DockerAdapter 的命名/集合契约由 `tests/unit/test_docker_doubles_contract.py` 对照。
- E2E 证据目录每次运行私有（mkdtemp），证据脱敏覆盖 token/secret/password/cookie/resume_key/session；性能预算保持原硬阈值（首帧 8000ms、输入 3000ms、SQLite busy_timeout 原上界），证据记录完整样本而非仅判定。

## 专项技术验证探针

代码为不可变归档快照，先完整复制到专属scratch再运行；下表列出入口和依赖，具体正负例与清理契约见各spike报告。固定前缀/端口同一时刻只能运行一份，不能只改容器名忽略脚本内部引用。归档历史报告里的旧docs/spikes路径按docs/archive/spikes读取。

|专题|归档代码目录|入口与宿主依赖|资源范围|
|---|---|---|---|
|跨容器UDS/下载|s003_selkies_control/code/container_uds|python3 run_cross_container.py --case override_control，再无参数运行；宿主标准库|cbrowser-spike-cdp-uds|
|进程恢复|s003_selkies_control/code/recovery_probe|test_orchestration.py；依赖以report/recovery_review为准|独立API/Supervisor/Browser夹具|
|多页面媒体/输入|s004_media_connections/code|start_containers.sh → uv run --no-project --with playwright python media_e2e_probe.py → stop_containers.sh|HTTP18081/UDP30006|
|捕获/真实visibility|s005_capture_policy/code|只复制当前六文件（包括html和sh），Core用playwright+websockets，Native用websockets；不运行revision_03旧用例|HTTP18084/UDP30008|
|Gateway恢复|s006_gateway_media_recovery/code|完整复制probe及media_fixture，uv run --no-project --with aiohttp --with playwright python probe/run_verification.py|HTTP18082/18083、UDP30007|
|IPC/认证/真实音频|s007_profile_isolation/code|完整复制含fixture，python3 run_isolation_probe.py|cbrowser-spike-isolation；finally清理|
|IME/clipboard哨兵|s009_native_ime_input/code|start_containers.sh → uv run --no-project --with playwright python ime_native_probe.py及verify_extra_harness.py → stop_containers.sh|HTTP18095/UDP30018|

这些探针需要s001构建的cbrowser-spike-runtime-browser:test和cbrowser-spike-runtime-stream:test镜像（身份见s001/image_manifest.json）；清理放finally/trap，不能因负例预期非零而漏清理。合成音频仅可用于测量器校准，不能充当真实浏览器媒体证明。公网和原生x86环境没有执行，不计实测PASS。

模板测试临时目录不能放在已登记Git worktree内：现有fake_repo测试会受真实worktree发现逻辑影响，出现两个.env隔离误报。上面的TMPDIR采用允许写域内、独立于Git仓库的目录，保持原测试与断言不改。归档保留原始源码/报告字节（含历史行尾空格），活跃变更执行git diff --check -- . ':(exclude)docs/archive/\*\*'；完整检查结果及归档例外在task笔记披露，不通过改历史快照掩盖问题。

## Schema / codegen 验证

项目涉及 OpenAPI 导出及前端类型。

- 触发路径：`src/backend/cbrowser/api/`、`src/backend/cbrowser/domain/models.py`、`scripts/export_openapi.py`。
- 生成命令：在 `scripts/run_gates.sh` 设置的 TMPDIR / UV_CACHE_DIR 下，运行 `PYTHONPATH=src/backend uv run --no-project --python ">=3.12" --with fastapi --with pydantic --with "sqlalchemy[asyncio]" --with aiosqlite --with alembic --with argon2-cffi python scripts/export_openapi.py`，输出 `schemas/openapi/cbrowser_v1.json`。
- 验证命令：`scripts/run_gates.sh` 的 unit 层运行 `test_exported_openapi_schema_matches_live_app` 深度比较导出与实际应用；integration 层使用导出 JSON schema 校验真实 HTTP 响应。
- 合并后动作：运行上述验证，确认导出文件随接口实现一同合入。OpenAPI 变更后必须 `npm run generate:api --prefix src/frontend` 重生成 `src/frontend/src/shared/api/generated/cbrowser_v1.d.ts`，禁止手写补充类型。
- migration 窗口：t002 仅对全新隔离数据库执行 Alembic upgrade head；现有用户库迁移由 t010 验收，不在导出命令中执行迁移。
- 协议 schema 文档（t021）：`schemas/runtime/*.json` 与 `schemas/stream/*.json` 统一为「`$defs` 规范定义 + `messages` 按名索引（`$id` + `$ref`）+ 文档 `version`」约定，不再有顶层 `anyOf`；三个导出脚本（`export_supervisor_protocol.py`、`export_runtime_agent_protocol.py`、`export_stream_protocol.py`）同形生成，测试按消息入口逐条校验报文，不得退回整文档 union 校验。

## 契约行为验证要求（t021）

- 控制 API 与文件交换的验收必须走真实入口：内部面用真实 HTTP（服务令牌矩阵、未配置 503），协议用导出文档的消息入口逐条校验，文件用例覆盖故障注入（删除中途失败后意图保留、跨重启续跑）与幂等重放（同 operation_id 并发/删后重放）。
- 密码等慢操作须有事件循环不阻塞探针（慢哈希期间 ticker 推进断言），不接受仅测返回值的覆盖。
- 政策变更类断言（如内容类型由拒绝改为放行）必须整体替换旧测试并在测试内注明裁决来源，禁止就地把旧预期改成实现输出。

## 门禁类别清单

|类别|必须覆盖|常见盲区|
|---|---|---|
|**单元测试**|pytest 后端业务测试与前端 Vitest（Node 26 LTS，无需 `NODE_OPTIONS` 变通）；数量以实际输出为准|mock 掉真实逻辑、在业务代码中弱化测试断言|
|**契约测试**|pytest 模板轻量契约测试（`-m contract`）；数量以实际输出为准|路径或状态机格式不匹配、specs_index 缺失条目|
|**文档格式**|`python3 .repo_template/scripts/md_format.py --check`|Markdown 表格未 compact 或标题语法错误|
|**容器黑盒**|容器健康检查探针与本地技术验证专项探针|只看进程存活、未验证实际双向媒体与数据完整性|

## Gateway 阶段验证

t006 认证信令 Gateway 的真实拓扑 E2E：Caddy（`tls internal`）HTTPS 入口、API、Supervisor 容器经 API 运行意愿创建 Browser/Stream、正式 Gateway 镜像，官方 Mac Google Chrome **无头**访问（禁止弹窗或抢前台）；媒体同机直连，无 coturn。镜像全部为当前源构建的不可变 sha256 ID：

```bash
# 统一入口：scripts/run_gates.sh；E2E 使用 CBROWSER_RUN_E2E=1 scripts/run_gates.sh
```

页面可见性在无头 Chrome 中不会因切标签变化，AC-007 用例在页面内覆盖 `document.visibilityState` 并派发 `visibilitychange` 触发官方客户端 STOP_VIDEO/START_VIDEO；浏览器真实标签切换的事件发出见 d013/s005，不在本用例重证。

## Supervisor 阶段验证

Profile 编号与沙箱分组（t050）：迁移回填/新分配/不复用由 unit 覆盖；容器名与标签（`<prefix>-<NNNN>-browser|stream`、`profile-number`、`<prefix>-profiles`）由 adapter 单测与真实拓扑 inspect 验证；部署 prefix 冲突对自有伪项目的放行与异项目拒绝由 fake Docker CLI 驱动 `scripts/deploy.sh` 覆盖；前端 Profile 列表展示编号由组件测试验证。真实部署后需重建一次沙箱以应用新命名。

带载升级自愈：`tests/e2e/test_supervisor_upgrade_recovery_e2e.py` 在 Profile 运行中强制重建 Gateway 与 Supervisor（`GatewayTopologyHarness.rebuild_gateway_and_supervisor`），断言 300s 部署 readiness 预算内恢复 ready、无 `session_instance_mismatch` / `gateway_not_attached_at_fixed_endpoint` / `agent_not_registered` 诊断，并由新的 headless viewer 重新解出视频帧（t049 AC-007）。

按照 [Supervisor 验证](../guides/supervisor_validation.md) 提供当前源构建的不可变镜像及缓存。统一运行 `scripts/run_gates.sh` 或 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`，不直接调用裸 pytest。

生命周期与恢复组件分别运行，避免以单个容器图用例替代全部异常路径：

```bash
# 统一入口：scripts/run_gates.sh；E2E 使用 CBROWSER_RUN_E2E=1 scripts/run_gates.sh
```

运行前必须设置允许写域内 TMPDIR、UV_CACHE_DIR、pytest basetemp/cache_dir，并仅为本地测试进程清除代理环境；这不会关闭 OrbStack 透明代理。测试前提存在但无效须失败，不能把镜像拉取/进程启动失败作为网络拒绝证据。跨 Profile 网络负例必须使用不做对端地址过滤的服务，同网正例成功；普通桥未隔离事实见 d020；Runtime 内核策略须通过无过滤监听器正负对照，不能以应用按来源拒绝连接冒充网络隔离。

网络与启动清理专项还须运行 `test_supervisor_namespace_policy_e2e.py`、`test_supervisor_ipv6_policy_e2e.py`、`test_supervisor_policy_failure_e2e.py` 和 `test_supervisor_orphan_helpers_e2e.py`。仅在持有 CoordinatorLock 的启动阶段回收遗留 helper，周期扫描不得调用该清理。

资源策略与配额链验证分三层：资源算法与状态机由 unit 层 `test_supervisor_resource_policy.py`、`test_supervisor_resource_aggregation.py`、`test_resource_fault_isolation.py` 及 integration 层对应文件覆盖；真实 Docker CPU 采样与 monitor/policy 决策由 `test_supervisor_resource_policy_e2e.py`、`test_supervisor_resource_capacity_e2e.py`、`test_supervisor_resource_monitor_e2e.py` 覆盖，其中 monitor 用例的投递腿是本地回调，只证明决策与采样、不证明 Gateway 投递；真实配额投递链由 `tests/e2e/test_supervisor_quota_chain_e2e.py` 在真实 Gateway 拓扑中经生产控制客户端（`GatewayControlClient.set_quota`，与 Supervisor `ResourceMonitor` 相同的投递路径）下发配额，以 Viewer 页实际解码帧数与帧几何判定生效、客户端越权不生效与配额清除后恢复；CPU policy 腿复用 `tests/fixtures/supervisor_resource_probe/stream_monitor.py`，其配额投递同样走生产控制客户端（该探针原先的自建 mock Gateway socket 投递已由 t028 替换，未复活）。保存实际 CPU counter、quota、采样窗口、配额下发与 Chrome 帧数；资源算法、真实采样、实际画面各自证据不互相替代。

Supervisor 控制契约导出使用：

```bash
# 统一入口：scripts/run_gates.sh；E2E 使用 CBROWSER_RUN_E2E=1 scripts/run_gates.sh
```

导出 `schemas/runtime/supervisor_protocol.json` 必须随 DTO 更新；停止请求必须包含目标实例与操作 ID，不允许旧 schema 继续宣称二者可省略。API 内部白名单路由继续通过原 OpenAPI 导出及真实 HTTP schema 验证。

## 前端阶段验证

t007 前端门禁：`npm run build` 的 `prebuild` 自动拉取并校验官方 Selkies 资源（清单 `config/selkies/selkies_web_sha256.txt`），构建同时产出 `dist/selkies/selkies_adapter.js`，`postbuild` 校验 dist 的 adapter、资源哈希与加载顺序。构建会改写已入库的 `src/frontend/tsconfig.tsbuildinfo`，提交前还原。

```bash
# 统一入口：scripts/run_gates.sh；E2E 使用 CBROWSER_RUN_E2E=1 scripts/run_gates.sh
```

E2E 镜像变量同“Gateway 阶段验证”，且 API/Supervisor/Stream 必须用当前源重建（旧 API 镜像缺 `/api/v1/events` 与 Runtime Coordinator，旧 Supervisor 镜像不写 Selkies token 文件）。`test_frontend_app_*` 用构建产物经 Caddy 托管，API 启用 Runtime Coordinator（`CBROWSER_REQUIRE_SUPERVISOR=1`），Profile 启停只经界面/`/api/v1`。测试代码不得自带编排互斥锁或引用 `.scratch` 编排目录；多路并行跑 Docker E2E 时由外层调度互斥。

t025 前端残余回归（Vitest，云端已验）：出站同源矩阵覆盖 ApiClient/SSE/下载链接三入口的绝对、协议相对、反斜杠与混合变体（`client.sameorigin.test.ts`、`sse.sameorigin.test.ts`）；真实 HTTP 夹具改为注入 fetch 按 origin 转发到测试服务器（客户端已无 baseUrl/url 配置项）；注销失败处置走生产 AppProviders + 实现 `setOnUnauthorized` 的真实 SSE 客户端断言回调路径（`providers.unauthorized.test.tsx`），AppProviders 默认 QueryClient retry 接线由 `providers.defaults.test.tsx` 守卫；跨 Profile 动作隔离由三页面的 `*.isolation.test.tsx` 覆盖，apply 阶段续跑由 `useProfilesQuery.applyresume.test.tsx` 以服务端幂等重放模型覆盖。真实 Docker/Chrome 拓扑下的会话回归（真实 401 注销、跨 Profile 切换与应用并重启）不在云端执行，统一由 t032 在目标环境判定。

### t036 设计门禁与产物扫描

设计门禁三条命令接入 `scripts/run_gates.sh` 前端阶段，顺序在 `frontend_test` 之前：`npm run design:lint`（`DESIGN.md` 官方 lint，error / warning 任一非零即失败）、`npm run design:check`（入库 `design_tokens.css` 与重新生成结果比对，不一致即失败）、`npm run design:tokens`（幂等写回）。`design_tokens.test.mjs` 覆盖三条生成前校验（`light-*` / `dark-*` 角色集合不等、未解析引用、既非 `primary` 又无模式前缀的颜色 token）与确定性生成；`design:check` 失败路径以追加 stale marker 验证（退出 1）。

AC-003 扫描：20 个业务文件（外壳、`shared/ui`、登录页、设置页、手写 `globals.css`、占位页）中 Tailwind 默认调色板类、旧 `surface-*` / `primary-foreground` 类与颜色字面量命中 0；构建产物 CSS 中 `bg-red-500` / `text-gray-100` / `bg-emerald-500` / `bg-blue-500` / `text-slate-900` / `bg-surface-0` 均不产生样式，语义变量（`--color-background` / `--color-surface` / `--color-accent` / `--font-ui` / `--font-mono` / `--text-body-md` / `--radius-md` / `--spacing-md`）、`.bg-primary` 与 `.dark` 覆盖均存在。AC-009 扫描：`dist/index.html` 与 `dist/assets/*.css` 中 `https?://` 仅命中 Tailwind MIT license 注释，无外部字体 / 图标 CDN 引用；自托管 `*.woff2` 13 个；`index.html` 内联脚本数 0。

### t039 全局颜色门禁

全局颜色门禁由 `npm run design:lint` 的 `--lint` 分支承载（`src/frontend/scripts/design_tokens.mjs`）：`runLintSources(sources)` 合并执行尺寸断言（`assertNoSizeTokenHijack`）与颜色断言（`assertNoColorViolations`），一次扫描同时覆盖 Tailwind 默认调色板类（含 `/透明度` 变体）、`white` / `black` 类、旧 `surface-0..4` / `primary-foreground` 类与 hex / rgb / hsl / oklch 颜色字面量，**发现即失败、无豁免**，日志 `size+color scan: N files clean`。源集沿用 t036 口径：`collectSources("src")` 递归收集 `.ts` / `.tsx`，排除 `generated` / `styles` 目录与 `*.test.*` / `*.spec.*` / `test_setup.ts`。门禁零改 `scripts/run_gates.sh`——`design_lint` suite 已调用 `design:lint`，接入即生效。

`design_tokens.test.mjs` 覆盖 3 例纯函数断言（`assertNoColorViolations` 颜色正则的命中与放行）与 2 例集成测试（`mkdtempSync` 临时目录 + `collectSources` 走真实门禁路径，违规文件使 `runLintSources` 抛错、干净目录通过）。`doctor_cmd` / `test_cmd` / `blackbox_verify` / `gate_timeout_seconds` 章节名与命令形式不变。

## 历史实跑覆盖矩阵（t028）

下表把 p016 原行为与 p021–p024、p026、p027 的逐项义务映射到现行入口：只引用既有或 t028 新建入口，不为凑行数新造。云端结果为 t028 执行环境（无 Docker）实测；「skip」指 collect-only 通过、因无 Docker 未实跑，不得记为已验。

|来源|原行为|现行入口|触达组件|证据层级|云端结果|t032 待执行项|
|---|---|---|---|---|---|---|
|p016|网络保护真实行为|`test_supervisor_browser_network_e2e.py`（出口/媒体独立桥）、`test_supervisor_network_ownership_e2e.py`（归属/幂等/精确清理）、`test_supervisor_namespace_policy_e2e.py`、`test_supervisor_ipv6_policy_e2e.py`、`test_supervisor_policy_failure_e2e.py`（内核策略）；附网/回滚另见 `test_supervisor_reconciliation_e2e.py`|Supervisor reconcile/attach、Stream 策略安装|真实拓扑|skip|AC-008、AC-009|
|p016|Supervisor 真实配额实际生效|`test_supervisor_quota_chain_e2e.py`；CPU 腿 `supervisor_resource_probe/stream_monitor.py`|`ResourceMonitor` → `GatewayControlClient.set_quota` → Gateway `SUPERVISOR_QUOTA` → Agent/Selkies|真实拓扑 + Viewer 解码帧|skip（collect-only）|AC-008|
|p016|Agent 替换关闭旧 Viewer|`test_gateway_signaling.py::test_agent_replacement_closes_old_viewers`|Gateway 会话替换（close 1001、新 conn_id、下行回复、旧 Agent 退出后续传）|集成（真实 Gateway）|已实跑通过（t028 恢复 251fa0f 精确断言）|随 AC-014 复验|
|p021（t019）|无外部 STUN/TURN、ICE-lite 与首帧时延|`test_stream_ice_config.py`（unit）；`test_frontend_app_e2e.py` t019 用例|Stream entrypoint ICE-lite 参数、前端会话建立|unit + 真实 Chrome|unit 已跑通过；e2e skip|AC-003|
|p022（t020）|字体包三档贯通（t041 已删除 `font_bundle`，本行为废止）|`test_font_bundles.py`（unit）；`test_profile_font_bundle_api.py`（integration）；`test_browser_font_bundles_e2e.py`|API font_bundle 字段、Supervisor 注入、Browser 渲染|unit/integration + 真实拓扑|unit/integration 已跑通过；e2e skip|已废止（t041 替代，见下节）|
|p023（t021）|控制 API/文件交换/OpenAPI 契约|`tests/contract/` 与 schemas 导出校验|API 路由、协议 schema、文件交换契约|契约|已跑通过|AC-005|
|p023（t021）|Origin 变体授权|unit origin 授权测试 + integration 真实 HTTP|API 授权中间件|unit/integration|已跑通过|AC-005|
|p023（t021）|工件下载全链|`test_artifact_download_chain_e2e.py`（t028 新建）|浏览器下载捕获 → ArtifactService 入库 → API 下载字节/sha256 比对|真实拓扑|skip（collect-only）|AC-002、AC-005|
|p023（t021）|删除意图跨重启续跑|`test_artifact_delete_resume_e2e.py`（t028 新建）|`ArtifactService.delete` 意图持久化、启动 `resume_pending_deletions`|真实 API 子进程（两段启停）|已实跑通过|随 AC-014 复验|
|p023（t021）|打包 import 契约|`test_exit_reason_allowlist.py`（import `cbrowser.runtime_event_log` / `emit_runtime_event_log`）|打包后模块路径|unit|已跑通过|—|
|p024（t022）|X11 helper 权限收敛|`test_x11_helper_permissions_e2e.py`（t028 新建）；另见 `test_supervisor_orphan_helpers_e2e.py`|`DockerAdapter.setup_x11_permissions`|真实 Docker|skip（collect-only）|AC-006|
|p024（t022）|缓存代次|`test_supervisor_cache_generations.py`|Supervisor 缓存代次封存/重验|unit|已跑通过|随 AC-014 复验|
|p024（t022）|双族网络策略 DROP|`test_supervisor_namespace_policy_e2e.py`、`test_supervisor_ipv6_policy_e2e.py`、`test_supervisor_policy_failure_e2e.py`|netns 策略安装与失败封闭|真实拓扑|skip|AC-006|
|p024（t022）|keymap 调用顺序|`test_stream_keymap_abi.py`、`test_stream_binding_guards.py`|Stream keymap ABI 适配层|unit|已跑通过|AC-006（真实调用顺序）|
|p024（t022）|多 Agent 注册预算|`test_gateway_registration_budget_e2e.py`（t028 新建）；集成层见 `test_gateway_signaling.py`|Gateway `RegistrationThrottle`（在途 4、失败 20/60s、重启恢复）|真实拓扑 + 集成|e2e skip（collect-only）；集成已跑|AC-006|
|p024（t022）|search-defaults 真链|`test_search_defaults_retry_live_e2e.py`（t028 新建）；`test_api_search_defaults_routes.py`、`test_runtime_coordinator_integration.py`（integration）|API retry 路由（CSRF/幂等键）→ RuntimeCoordinator → Supervisor → 状态围栏|真实进程链 + 集成|e2e skip（collect-only）；集成已跑|AC-006|
|p026（t023）|前端会话/请求语义与构建链|src/frontend Vitest（含 t025 残余回归）；`frontend_probe` harness（镜像身份只经 REQUIRED_E2E_ENV 注入，t028 删除 `.scratch` 旁路读取）|前端 ApiClient/SSE、host_builder 构建|前端 + 契约|已跑通过|AC-007|
|p027（t024）|Supervisor/Stream 镜像真实构建|`config/docker/` 各 Dockerfile；run_gates 证据模式 manifest 的 `image_identity`|镜像构建与身份固定|构建证据|manifest 机制 unit 已验；真实构建未跑|AC-002|

## t032 运行映射（t028）

t032 执行者按本表运行，不需要回读 t028 的执行过程。所有 E2E 先按 `config/docker/` 的 Dockerfile 构建镜像并以 `docker image inspect` 的 `.Id` 固定身份；预算为 M1 Max 基准的预留量，以目标机实测为准。结果 artifact 字段以证据模式 `manifest.json` 为准：`suites[].name/command/exit_code/log/junit`、`image_identity`、`all_passed`；AC-015 最终验收报告逐项引用实际镜像 ID、退出码、逐 suite 计数（以 junit 为准）与 JUnit 路径，不得以云端结果替代。

|t032 待执行项|指令|所需镜像与环境变量|资源/时间预算|结果 artifact 字段|
|---|---|---|---|---|
|AC-002 镜像构建与身份固定|逐个 `docker build -f config/docker/<name>/Dockerfile` 后 `docker image inspect` 取 `.Id` 写入 env 文件；再以 `CBROWSER_E2E_REQUIRED=1` 收集校验|全部 REQUIRED_E2E_ENV 镜像变量 + 引擎/GeoIP 缓存|首次全量构建为主要耗时，预留半天（含缓存预热）|`image_identity`；报告记录实际镜像 ID|
|AC-003 ICE/首帧|`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 或单跑 `test_frontend_app_e2e.py` 的 t019 用例|RUNTIME/STREAM/API/CADDY 镜像 + 官方 Chrome|单用例数分钟|`suites[].exit_code/log/junit`；报告含候选类型与首帧样本|
|AC-004 字体三档（t041 删除 `font_bundle`，本项废止）|单跑 `test_browser_font_bundles_e2e.py`|RUNTIME 镜像|数分钟|同上；附三档渲染证据路径|
|AC-005 契约真实拓扑|必需模式全量 E2E（见 AC-014 指令）|全镜像集|完整 E2E 按小时级预留、分批执行|manifest 全部字段|
|AC-006 运行时恢复|单跑 `test_x11_helper_permissions_e2e.py`、`test_gateway_registration_budget_e2e.py`、`test_search_defaults_retry_live_e2e.py` 与 namespace/ipv6/policy_failure 三件|SUPERVISOR/GATEWAY/API/RUNTIME/STREAM 镜像|每件数分钟|`suites[]` 逐项退出码与 log|
|AC-007 前端部署|部署产物上单跑 frontend app/session E2E|部署 release + 全镜像集|数十分钟|同上|
|AC-008 p016 配额/网络|单跑 `test_supervisor_quota_chain_e2e.py`、`test_supervisor_browser_network_e2e.py`、`test_supervisor_network_ownership_e2e.py`|全镜像集 + 引擎缓存|配额链含 CPU 采样窗口，约 10 分钟级|stream_monitor proof JSON（windows/deliveries）+ manifest|
|AC-009 附网/回滚与发布演练|单跑 `test_supervisor_reconciliation_e2e.py`；发布演练按 `DOCKER_DEPLOYMENT.md` 步骤|全镜像集|数十分钟 + 演练人工步骤|同上|
|AC-014 required + 证据模式全跑|`CBROWSER_E2E_REQUIRED=1 CBROWSER_RUN_E2E=1 CBROWSER_GATE_EVIDENCE_DIR=<dir> scripts/run_gates.sh`|全镜像集与缓存|全量门禁 + 完整 E2E，预留半天|manifest.json（逐 suite 计数以 junit 为准、`all_passed`、`image_identity`）|

## 自动化兼容性探针矩阵（t029）

探针在 `tests/fixtures/automation_probe/`，结论 spec 为 `docs/specs/automation_compatibility.md`。证据分级：云端已验（目标引擎 linux-x64 + Xvfb）≠ 真实镜像已验；真实 arm64 镜像、容器化 X11/Stream、Mac Chrome Viewer 只在 t032 判定，云端结果不得记为其 PASS。

|探针|入口|层级|云端状态|
|---|---|---|---|
|探针机制与判定规则（阈值、脱敏、命令分类）|`tests/unit/test_automation_probe_harness.py`|unit|已跑|
|全链矩阵 + 下载归属/恢复 + 授权拒绝|`test_automation_probe_chain.py::test_probe_chain_target_engine_matrix_and_disconnect`、`::test_probe_chain_ordinary_chromium_matrix`|integration|已跑|
|Dialog 基线（普通 Chromium 全链 / 目标引擎直连）|`::test_probe_chain_dialog_contract`、`::test_probe_target_engine_dialog_contract`|integration|已跑|
|外部 Browser.close 停 Profile|`::test_probe_chain_external_browser_close_stops_profile`|integration|已废止：t030 隧道策略变更为拒绝，测试整体替换为 `test_probe_chain_external_browser_close_rejected`（见下节）|
|L0–L6 增量与 CDP/XTEST 输入比较|`tests/fixtures/automation_probe/run_levels.py`（env：CBROWSER_T029_ENGINE_CACHE、CBROWSER_T029_REPORT_DIR、T029_XTE、T029_SAMPLES）|采样驱动|已跑（每级 5 样本）|
|t032 真实镜像复核|`tests/e2e/test_automation_compatibility_probe_e2e.py`（`CBROWSER_T029_PROBE_E2E=1` 门控）|e2e|默认 skip，t032 执行|

预登记判定：L0–L6 每级 ≥5 个独立进程样本；字段值落在 L0 全部样本之外且该级 ≥4/5 复现才记新增变化。输入比较的采用规则：只有 CDP 出现可复现新增变化或坐标误差 >1 CSS px 才判定 XTEST 有采用收益。采样样本目录在样本结束后自清理（小 tmpfs 上 profile 目录堆积会撑爆磁盘）。外站检测器（BrowserLeaks/CreepJS/Pixelscan）不可达记 NOT_RUN，不以总分或 isTrusted 证明不可检测。

## Agent 执行器验证（t030）

执行器测试在 `tests/unit/test_agent_executor_*.py`（账本、ref、Dialog、
CLI、隧道过滤、跨调用状态）与
`tests/integration/test_agent_executor_chain.py`（真实 Chromium +
目标引擎链路）。证据分级与 t029 相同：云端已验 ≠ 真实镜像已验；
真实 arm64 镜像、容器化 X11/Stream、Mac Chrome Viewer 只在 t032 判定。

|用例|入口|云端状态|
|---|---|---|
|CLI 端到端（用户页快照、agent 页 popup 归属、输入提取、清理）|`test_executor_cli_chromium_end_to_end`|已跑|
|Dialog pending 与遗留（应答、消解结果）|`test_executor_dialog_pending_and_legacy`|已跑|
|ref 导航失效与节点替换失效|`test_executor_ref_stale_after_navigation_and_replace`|已跑|
|隧道拒绝与会话下载捕获|`test_tunnel_rejections_and_session_download_capture`|已跑|
|隧道脚本登记与断开清理|`test_tunnel_script_registration_cleaned_on_disconnect`|已跑|
|目标引擎核心流|`test_executor_target_engine_core_flow`|已跑|
|t029 策略变更替换：外部 close 被拒、no_defaults=False 连接被拒|`test_probe_chain_external_browser_close_rejected` 及矩阵测试的 False 分支（t030 裁决来源）|已跑（引擎缓存检测：`CBROWSER_T029_ENGINE_CACHE` 优先，其次包默认 `~/.cloakbrowser`，再其次 `~/.cache/cloakbrowser`；三处皆无则 skip 并在 skip 信息中明示该变量）|
|prompt 对话框 accept + promptText 真实浏览器验证|`test_executor_dialog_prompt_accepts_text`|已跑|
|文件选择独立步骤（跨调用会话先请求 document）|`test_executor_set_input_files`（integration）+ `test_cli_set_input_files_step`（unit fake）|已跑|
|超时/取消可区分（step_timeout、dialog_timeout、dialog_not_open、cancelled、失败后清理）|`test_cli_timeout_codes_are_distinguishable`、`test_cli_program_timeout_and_cancel_are_distinguishable`|已跑|
|安装入口与 --help 冒烟|`test_cli_help_smoke_and_entrypoint_declaration`|已跑|

云端实测修正的 t029 结论（t032 不必复测旧语义）：AX 树只在 frame 根节点
带 frameId（快照 frame 归属改以 DOM 映射为准）；`addScriptToEvaluateOnNewDocument`
须先 `Page.enable` 否则注册成功但脚本不运行；无认领会话时 Chrome 在打开
时即自动 dismiss dialog（遗留消解为 false）；lingering 处理会话滞留的
dialog 属 Chrome 层限制（新会话无法启用 Page 也无法应答），见执行器规约。

## 真人优先控制权验证（t031）

控制权测试在 `tests/unit/test_control_service.py`（状态机、代次、
reclaim、身份匹配矩阵）、`test_stream_takeover_classifier.py`（分类表与
前台判定）、`test_tunnel_registry.py`（注册表与代次围栏）、
`test_tunnel_filter_autoattach.py`（自动挂接 backstop）、
`test_dialog_attendant.py`（状态机与服务连接应答）、
`test_agent_executor_control.py`（CLI 控制面）、`test_control_migration.py`
（0009 隔离库升级与备份恢复），集成在 `test_control_api.py`（端点全流程
与隧道关闭）、`test_control_supervisor_close.py`（Supervisor 关闭端点与围栏）、
`test_control_http_clients.py`（CLI/Gateway 客户端对 stub 服务）、
`test_stream_takeover_report.py`（Stream 上报 envelope 与 pending 语义）与
`test_control_attendant_chain.py`（真实 Chromium 链）。

|用例|入口|云端状态|
|---|---|---|
|attendant 滞留 dialog 跨会话 peek 与应答、release 后默认消解|`test_attendant_holds_dialog_and_release_restores_default`|已跑|
|控制认领/交接/恢复全流程与隧道关闭|`test_control_claim_handoff_restore_flow`、`test_control_handoff_closes_registered_api_tunnels`|已跑|
|Supervisor 关闭端点与代次围栏|`test_close_tunnels_closes_and_fences`|已跑|
|CLI 控制往返与 stale 代次围栏|`test_cli_claim_handoff_round_trip_and_stale_fence`|已跑|

链实测修正的 t031 结论（t032 不必复测）：dialog 打开后才 attach 的新会话
无法观测或应答它（Page.enable 在 modal dialog 后挂起、handleJavaScriptDialog
报无 dialog），滞留 dialog 只能由 attendant 会话经控制面应答；接管 release
后 dialog 回归 Chrome 默认处置。目标 WebRTC/X11 来源的接管、原生权限交接
用例与真实拓扑下的接管/恢复只在 t032 判定。

## t032 Linux arm64 探针入口

目标引擎默认为 `146.0.7680.177.3`，可用 `CBROWSER_T029_TARGET_ENGINE_VERSION` 显式选择；缓存查找、BrowserRunner 启动和报告使用同一版本。云端 `.5` 仅作跨版本参考。

在宿主用不可变 Browser 镜像 ID 核对本地 tag 后，构建独立探针镜像；不重建生产镜像：

```bash
docker tag "$CBROWSER_RUNTIME_TEST_IMAGE" cbrowser-probe-base:local
docker build -f config/docker/automation_probe/Dockerfile \
  --build-arg BROWSER_IMAGE=cbrowser-probe-base:local -t cbrowser-probe:local .
export CBROWSER_PROBE_TEST_IMAGE="$(docker image inspect --format '{{.Id}}' cbrowser-probe:local)"
export CBROWSER_T029_ENGINE_CACHE="${HOME}/kar/code/.cbrowser/engine-cache"
export CBROWSER_T029_REPORT_DIR="$PWD/.scratch/t032/probe-evidence"
bash scripts/run_automation_probe.sh
```

入口要求 Linux arm64 镜像、可执行目标引擎和空证据目录。仓库及引擎只读挂载，独立容器不挂 Docker socket 或生产数据；提供 Xvfb/XTEST；链路 Dialog 与执行器测试的显式浏览器路径同样指向选中目标引擎。容器中的生产 Python 组件通过 loopback 建立 API → Supervisor → Agent → CDP 链路；这不替代独立 Stream/Viewer 容器 E2E。子测试 JUnit 不得含 skip，报告和镜像身份留在证据目录。AC-012 外站不可达或样本不足记 `INCONCLUSIVE`；AC-013 人工项按用户决定记 `OUT_OF_SCOPE_BY_USER`。

## t041 指纹平台与平台字体集验收映射

下表把 t041 的 AC-001~009 映射到测试与证据入口；契约全文见 `docs/tasks/t041_fingerprint_platform_fonts/task.md`，需求级 spec 见 `docs/specs/fingerprint_platform.md`。证据引用：正式 spike `docs/spikes/s014_fingerprint_platform_fonts/report.md`、findings `d032` / `d033`。

|AC|行为|测试 / 证据|
|---|---|---|
|AC-001|导入工具生成带 manifest（来源、来源系统版本、逐文件 sha256）的不可变字体集；相同内容重复导入同一 `set_id`，内容变化得新 `set_id`，已有集不被修改|导入工具 / 内容寻址 unit|
|AC-002|`GET /api/v1/font-sets` 需登录会话，列出平台、来源、版本、静态完整性与 `used_by_count`；文件被篡改或缺失时完整性显示不一致|integration API 用例 + manifest 完整性检查|
|AC-003|`fingerprint_platform` / `font_set_id` 可经创建与 PATCH 设置；引用不存在或平台不一致的集被拒绝；新建 Profile 默认用平台最新集；修改任一生成新配置版本；启动参数取自绑定快照|unit（校验、默认选择、fontconfig 生成）+ integration（API / 配置版本快照）|
|AC-004|两平台 `navigator.platform`、UA、UA-CH `platform` / `platformVersion` 与所选平台一致|真实引擎 E2E（离线探测页，`http://127.0.0.1` / HTTPS 安全上下文）；CH `architecture` 不做半套覆盖（`d032` + `p045`），文本不改|
|AC-005|windows 检出 Windows 检测字体清单、检不出 Mac 专有字体，macos 反之；两平台都检不出 Liberation 等 Linux 字体；可见字体只来自基础字体与绑定集|真实引擎 E2E 离线字体探测页；spike `fc-list` 隔离实测（`d033`）|
|AC-006|绑定集缺失或与 manifest 不一致时启动失败封闭 `font_set_unavailable`；null 时正常启动并报告平台字体未配置|unit + 真实引擎 E2E 失败封闭|
|AC-007|runtime 响应与 SSE 含实际 `font_set_id` 与 `missing_fonts`，与 Agent 用该 Profile fontconfig 的检查结果一致|integration（runtime 响应 / SSE 字段）+ Agent fontconfig 复核|
|AC-008|镜像层与 git 仓库无平台字体；部署 / 发布脚本不复制字体目录；task worktree 经 `.worktreeinclude` 共享同一字体目录|`docker save` 镜像层扫描 + 仓库扫描 + 脚本静态检查|
|AC-009|`font_bundle` 字段、镜像字体包、代码与文档引用一并删除，扫描为空|全仓 grep 为空 + 增量迁移 `0002_fingerprint_platform.py` 删除列|

## t051 运行时与部署可靠性验收映射

下表把 t051 的 AC-001~021 映射到测试与证据入口；契约全文见 `docs/tasks/t051_runtime_deploy_reliability/task.md`，需求级 spec 见 `docs/specs/runtime_lifecycle.md` / `release_deployment.md` / `fingerprint_platform.md` / `access_control.md`。本机无 Docker、无真实部署环境：AC-013 真实部署、AC-014 双实例真实 Docker、AC-015 真实 Docker 挂起三项按链口径跳过按 pass 计，替代验证见表内，真实环境验证须在用户机按 t032 演练补验，不得记为已验。

|AC|行为|测试 / 证据|
|---|---|---|
|AC-001|数据库文件（含 `-wal` / `-shm`）不位于任何宿主 bind mount 上|compose 结构测试（`test_t027_release_controller.py` 的 compose 断言）|
|AC-002|schema 代际检查在新存储位置上仍按原语义放行/拒绝，且不以写模式打开数据库|fake Docker 驱动 `deploy.sh`（旧代拒绝、合法代际放行）；`db_inspect.py` 单元测试|
|AC-003|部署前备份产生宿主可取得的数据库副本；用该副本恢复后 API 正常启动且数据一致|fake Docker 备份+恢复往返测试；`db_backup.py` / `db_restore.py` 单元测试|
|AC-004|volume 无库而宿主旧路径存在 `cbrowser.db` 时部署提示位置与处置方式，旧文件不被删除/覆盖|fake Docker 旧库提示测试|
|AC-005|瞬时数据库错误（BUSY/LOCKED/IOERR 含扩展码）返回 503、稳定错误码、`retryable=true`；确定性错误响应不变|`test_t051_db_errors.py`（分级矩阵、API 503 形状）|
|AC-006|登录建会话遇有限次瞬时故障后恢复则成功；持续超限返回可重试错误，不返回 500|真实 SQLite 库上的登录重试恢复 + 持久失败测试；`test_api_subprocess.py` 真实 busy 超时用例|
|AC-007|数据库错误日志含 SQLite 错误码名、方法与路径，不含 SQL 参数值、密码、会话 token|`test_t051_db_errors.py`（日志断言）；`str(exc.orig)` 永不记入日志|
|AC-008|登录页收到可重试数据库错误时显示当前界面语言的本地化文案，不显示后端英文原文|`LoginPage.test.tsx`（503 两类错误码 + 401 透传对照）|
|AC-009|默认部署时 API 与 Supervisor 看到主仓 `data/fonts` 中的字体集；`CBROWSER_FONTS_DIR` 可覆盖|fake Docker 字体 preflight 测试；compose 结构测试|
|AC-010|字体目录缺失或无有效集时部署输出可执行提示；字体路径一致性由测试断言|fake Docker 字体警告/有效集测试；`check_font_sets.py` 单元测试|
|AC-011|Browser、Stream 及辅助容器启动失败时异常与日志含 Docker 原始错误信息，凭据类内容已脱敏|`test_t051_shared_redaction.py`、`test_t051_docker_error_detail.py`（脱敏形态矩阵）|
|AC-012|两不同编号 Profile 的 Browser/Stream 的 `com.docker.compose.service` 分别为 `<NNNN>-browser` / `<NNNN>-stream`，project 仍为 `<prefix>-profiles`|`test_t050_sandbox_grouping.py`、`test_refactor_behavior_equivalence.py`|
|AC-013|真实部署后登录、Profile 出图、named volume、设置页字体集、OrbStack 分组|**跳过（本机无 Docker）**；替代：AC-001 结构断言 + fake Docker 全流程测试；真实部署须在用户机验证|
|AC-014|同一 daemon 两实例媒体子网池互不重叠，池重叠部署失败并提示；两实例并发启动 Profile 不因子网冲突失败|fake Docker 池重叠拒绝/放行测试；并发三 Profile 分配不同子网测试；**真实双实例 Docker 部分跳过**，须在用户机验证|
|AC-015|Docker 网络 API 挂起超超时时该次启动明确失败，其它 Profile 网络创建不被阻塞|阻塞式 fake client 超时测试（0.2s 超时、并发 fast 成功、预留释放）；**真实 Docker 挂起部分跳过**，须在用户机验证|
|AC-016|prefix 含大写、空格、斜杠或 `-` 时 deploy.sh 与 Supervisor 启动均在任何 Docker 操作前失败并提示|fake Docker prefix 校验测试；`test_t051_supervisor_identity.py`（校验矩阵、runner main 拒绝）|
|AC-017|deploy.sh 写发布指针任意步骤中断后 current/previous 仍一致，rollback 可执行|fake Docker JSON 指针 + 损坏指针替换测试|
|AC-018|数据库文件存在但不可读时 deploy 与 rollback 都在启动/替换任何容器前拒绝|fake Docker 不可读库 fail-closed 测试（`db_inspect.py` 单元测试）|
|AC-019|默认数据根、现行文档、源码与脚本不含产品代际标识；新增时 hygiene 测试失败|`test_t051_generation_hygiene.py`（15 模式全仓扫描）|
|AC-020|证据脱敏与 Docker 错误脱敏对 URL 内嵌凭据、任意 cookie 值、含空格敏感值与家目录路径均输出脱敏占位|`test_t051_shared_redaction.py`（参数化矩阵）|
|AC-021|容器 project 标签伪造为本实例分组但 instance-id 不符时 deploy.sh 拒绝、Supervisor 不认领；缺 instance-id 标签不被认领|fake Docker 伪造 project 拒绝测试；`test_t051_supervisor_identity.py`（三处扫描过滤、helper 清理、core lookup 过滤器）|

## t044 门禁并行化与验证工具

本节的机械锚点仍是上文 `doctor_cmd` / `test_cmd` / `blackbox_verify` 章节命令；日常全量门禁唯一入口 `scripts/run_gates.sh`，E2E 必需模式入口 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`，命令形式不变。需求级契约见 `docs/specs/gate_verification.md`。

### suite 并行与串行标注

- unit / integration / E2E 由 `run_gate_suite` 分两阶段执行：并行 `-n "$WORKERS" -m "not serial"`（`WORKERS` 由 `CBROWSER_GATE_WORKERS` 覆盖，默认 4）与串行 `-n 0 -m "serial"`；两阶段 JUnit 由 `scripts/merge_junit.py` 合并为单一 `junit/<suite>.xml`，用例集合与改造前一致。
- 时序敏感、固定宿主端口、嵌套 pytest 或 sqlite 竞争的用例以模块级 `pytestmark = pytest.mark.serial` 标注，在单进程阶段执行，期间不与任何其它用例并发。`pyproject.toml` 注册 `serial` marker。
- 每个 xdist worker 由 `PYTEST_XDIST_WORKER` 经 `tests/fixtures/e2e_env.py::worker_resource_offsets` 派生独立 UDP / HTTP 端口区间与 media 子网；basetemp 按阶段与 worker 隔离；容器 / 网络名沿用随机前缀。suite 结束不残留本轮资源。

### 并发分组与证据

- evidence 模式下后端组（contract / unit / integration）与前端组（design_lint / design_check / frontend_test / frontend_build）并发执行，E2E 在两组 `wait` 完成后开始；逐 suite 写 `suites.d/*.tsv` 片段，按固定 `SUITE_ORDER` 合并为 `suites.tsv`，manifest / junit / 脱敏日志格式不变，任一 suite 非零则总退出码非零。默认模式保持串行 fail-fast。
- `design:tokens` 是生成命令（会重写受跟踪的 `design_tokens.css`），已从门禁移除；门禁只做只读 `design:lint` / `design:check`。`design_tokens.css` 过期时 `design:check` 使门禁失败，且完整门禁前后受跟踪文件内容不变。
- 环境准备复用持久共享 uv 缓存（`CBROWSER_GATE_UV_CACHE`）与 gate venv（`CBROWSER_GATE_VENV`），以 `gate-requirements.txt` 哈希戳判定复用；缓存就绪时 `logs/environment.log` 仅记录 `reuse cached venv`，无依赖下载。

### 必跑模式前置封闭

- `require_e2e_env` / `require_e2e_available` 统一收口前置检查；必跑模式 `CBROWSER_E2E_REQUIRED=1` 缺失即 `pytest.fail` 并列出缺失项，非必跑 skip。镜像变量还须通过 `image_identity_problems` 的 `sha256:<64hex>` 不可变身份与本地存在校验。
- 指纹平台 E2E 从 `CBROWSER_E2E_FONTS_DIR` 持久字体目录读取经 `scripts/import_font_set.py` 导入的内容寻址字体集（windows 来自微软官方 Windows 11 企业评估版 ISO 的 `sources/install.wim` → `Windows/Fonts`，macos 来自本机系统目录），不依赖 worktree 私有 `.scratch`；字体不入库、不进镜像。conftest 在必跑模式 collection 期额外校验字体集、引擎 / GeoIP 缓存与 Docker daemon。
- 该变量是 E2E 专用：产品 `CBROWSER_FONTS_DIR` 若在门禁环境存在，API 会给新建 Profile 绑定默认字体集，而 E2E 的 Supervisor 容器看不到宿主目录会 `font_set_unavailable` 失败封闭；`scripts/run_gates.sh` 对该产品变量全程 `unset`，只向 E2E 进程提供 `CBROWSER_E2E_FONTS_DIR`。
- E2E suite 先跑单进程 `--collect-only -n 0` preflight，前置缺失时一次干净 `pytest.exit(2)` 列出缺项，不让每个 xdist worker 各自失败。模块级开关启用的探针用例为显式可选用例外。

### 验证工具与弃用策略

- `requirements_check` suite 运行 `scripts/generate_requirements.sh --check`，锁与导出 requirements 漂移即失败；E2E 必跑模式 `image_packages` suite 对 browser / stream / gateway / supervisor / api 五个运行镜像运行 `scripts/verify_image_packages.py`，镜像内已安装包集合与依赖锁不一致即失败。
- `pyproject.toml` 的 `filterwarnings` 以 `error::DeprecationWarning` 兜底，仅精确登记忽略三条第三方来源（httpx per-request cookies、aiohttp bare functions、jsonschema RefResolver）；产品源码弃用用法从根因修正，不靠忽略掩盖：`status.HTTP_422_UNPROCESSABLE_CONTENT`、SQLAlchemy `lazy="raise"`、`aiohttp.ClientWSTimeout(ws_receive=...)`、Alembic `path_separator=os`、`asyncio_default_fixture_loop_scope`。
- 门禁新增 `scripts/merge_junit.py`；`tests/unit/test_t028_run_gates_evidence.py` 的 stub 契约随 suite 列表同步（去 `design_tokens`、加 `requirements_check`）。

## t045 门禁稳定性与 E2E 遗留缺陷收口

需求级契约见 `docs/specs/gate_verification.md` 第 9 节；`doctor_cmd` / `test_cmd` / `blackbox_verify` 机械锚点命令形式不变。

- `run_gate_suite` 两阶段对 pytest exit 5 对称：并行阶段用例全标 `serial` 时不再假失败，两阶段皆空判失败并列出缺项，junit 仍合并串行结果（`scripts/run_gates.sh`）。
- 门禁启动与 `EXIT` / `INT` / `TERM` 中断经同一套 trap 调用 `scripts/gate_container_cleanup.py`：仅按 `com.cbrowser.gate-run` 标签与本地运行租约清理已结束运行资源；容器和网络使用同一归属规则，无标签、未知租约或活跃租约一律不删，不再按名称放行；删除使用 Docker 不可变资源 ID，避免 sparse 列表缺少名称造成漏清理（`tests/unit/test_t045_gate_container_cleanup.py`）。
- 前端 E2E 同文件共享一套容器栈：`test_frontend_session_e2e.py` 改 module-scope `SharedContainerStack`，用例间以 `reset_profile_state`（stop + delete profile）只重置状态；`test_frontend_app_e2e` / `test_frontend_media_e2e` / `test_frontend_display_apply_e2e` / `test_frontend_app_auth_e2e` 核实本就是 module-scope 共享栈、天然满足，不重复改造。隔离语义由 `tests/unit/test_t045_e2e_shared_stack.py` 覆盖。
- Selkies wheel：`CBROWSER_SELKIES_WHEEL_CACHE` 指向已锁定 SHA256 的本地缓存；`vendor_selkies_web(..., allow_download=False)` 与 E2E 用例不发起公网请求；必跑模式 collection 期校验缓存存在与哈希，缺失时失败封闭列出缺项（`tests/e2e/conftest.py`、`test_frontend_adapter_build.py`、`tests/unit/test_t045_selkies_wheel_cache.py`）。
- 负载下时序判定改就绪条件驱动：`tests/fixtures/wait.py` 的 `poll_until` / `wait_until_sync`（deadline + 最后观测），不靠固定 sleep 或上调超时。ac007 媒体帧以「stage 文案 + RTP 增长 + worker 已丢弃编码帧」复合就绪谓词判定；supervisor dual_profile 的 API / Supervisor health 以就绪条件收敛后再 POST。

## t046 E2E 基础设施重构与协议探针模型归一

- **全仓唯一 Docker E2E Harness 铁律**：`tests/e2e/test_runtime_coordinator_e2e.py` 彻底重构接入标准的 `FrontendAppTopologyHarness`；彻底移除测试用例内私有 API 子进程、私有 Docker 启动与自建 `finally` 遍历删除逻辑。所有测试容器、网络、卷的分配、运行、观察与清理严格收敛于 `GatewayTopologyHarness` / `FrontendAppTopologyHarness` 与 `cleanup_prefixed_resources`，受 `CBROWSER_E2E_DELETION_LOG` 统一结构化审计。
- **协议探针异步事件流模型**：`tests/e2e/test_stream_selkies_tokens_e2e.py` 中被驱逐旧连接的客户端使用后台并发任务异步监听 Close Frame，确保实时响应服务端 RFC 6455 关闭握手，消除底层 Transport 提早掐断导致的 `1006 ABNORMAL_CLOSURE` 假失败；严格维持 `close_code == 4001` 与 `Superseded by a new connection.` 精确断言。

## t060 门禁运行归属、用例下限与隐私扫描

- `scripts/gate_run.py` 在 venv 父目录持排他 preparation 锁完成检查、重建和安装；运行锁在重建期排他、suite 执行期共享。热门禁可同时读取同一 venv，requirements 变化后的重建必须等全部运行读者退出。macOS 与 Linux 均通过 `fcntl.flock`，不依赖外部 `flock` CLI。
- 同一 checkout 的门禁持独占锁直至全部产物消费者退出，防止 Vite 清空另一轮正在验证的 dist；不同 worktree 仍可共享 venv 并发运行。接线单测在独立仓库副本执行，避免嵌套门禁竞争父进程工作区。
- Docker SDK 禁用 `use_config_proxy`，CLI adapter 显式清空注入代理并设置内部网络直连，避免本机 Docker 配置向测试容器注入代理。显式 Profile 代理配置仍由产品 API 管理，不改宿主 Docker 配置。
- 每轮生成 UUID run_id，在共同 Git 目录 `gate_runs/` 持文件租约。Docker CLI adapter、测试 SDK fixture 和 Supervisor 创建路径传播 `com.cbrowser.gate-run` 标签。启动清理只删本机登记且租约已结束的资源；缺少标签或租约、租约仍活跃、归属查询异常均不授权删除。中断后继承描述符的子进程继续受租约保护。退出清理失败保留非零退出码并写入 manifest。
- `protocol_drift_check` 是 evidence 首个 suite，按 Supervisor 协议、Stream 协议、OpenAPI 前端类型顺序执行。它失败时仍产生全部 suite 的脱敏日志和完整 manifest；默认模式保持 fail-fast。
- 下表是当前测试收集基线。pytest 按合并 JUnit 的实际 testcase 数校验（不能拿 XML 声明总数冒充）；Vitest 按 JSON 报告 `numTotalTests` 校验。任一报告缺失、损坏或低于下限即失败。测试集合变化必须重新收集并同步代码与本表，不降低阈值掩盖漏跑。

|suite|最小用例数|计数来源|
|---|---|---|
|contract|258|pytest JUnit|
|unit|1654|并行与 serial 合并 JUnit|
|integration|196|并行与 serial 合并 JUnit|
|frontend_test|499|Vitest JSON|
|e2e|105|并行与 serial 合并 JUnit|
|real_engine|2|必需 node ID 与 probe JUnit 双向核对|

- 命令型 suite 不存在 pytest 收集数：`protocol_drift_check`、`requirements_check`、`design_lint`、`design_check`、`frontend_build` 最小为一次完整成功执行，任一内部命令失败即 suite 失败；`image_packages` 必须完整校验五个运行镜像，缺少任何变量返回 skipped（77），完整门禁视为失败。缺少 suite 结果仍由 `finish_evidence` 拒绝，不以旧 TSV 补齐。

- E2E 模块用 `pytest.mark.e2e_images(*names)` 声明镜像依赖；必跑模式只检查所收集用例的声明并集，未声明用例退回全部前置。需要 Browser 的用例同时要求引擎和 GeoIP 缓存。非消费者不要求额外镜像；实际 fixture 仍通过 `require_e2e_env` / `require_e2e_available` 失败封闭。

- Browser / Stream 存在性分别观测。停止须两者都不存在；单个残留与 Docker API 错误均不得归一为已停止。

- 真实引擎 shell 预检与 evidence CLI 共用 `preflight_problems`，CLI 及 verdict 均检查不可变 image ID 和本轮预期 os/arch；伪造或缺失镜像元数据不能得到 all_passed。

- `verify_image_packages.py` 在目标镜像读取完整 PEP 508 环境（含 platform_machine），不从 Mac 宿主补缺省键；不可解析 marker 与不完整目标环境直接失败。

- 隐私扫描覆盖当前全部 tracked 树（含 archive）与未跟踪且未忽略的新文件；用户名后紧跟结尾或引号仍检出。不保留隐私豁免清单或整文件指纹放行，口径见 `security.md`。

- t060 review 收口：bootstrap 在环境准备前撤销旧 manifest；venv 创建或 pip 安装失败生成绑定当前 run_id 的失败 manifest 与非敏感环境日志，不能遗留上一轮 PASS。隐私匹配只识别绝对 home 根，不把公开 URL 中的 routes/home 路径段当作机器目录；file URI 中的真实家路径仍检出。

## t068 本地指纹基线与引擎升级回归门禁

- 引擎制品完整性是测试前置：`cbrowser.engine_artifacts` 的批准清单在
    unit（`test_t068_engine_artifact_pinning.py`）与真实 Docker E2E
    （`tests/e2e/test_t068_fingerprint_gate_e2e.py::test_ac003_*`）两处复验；
    `cache_init` helper 与 `BrowserRunner` 的拒绝路径（损坏文件、ELF 不符、
    marker、绕过环境变量、未批准 build）均有负向用例，不以只读缓存冒充已验。
- 指纹探针 `cbrowser.fingerprint_verification` 走真实 `BrowserRunner` +
    Xvfb + 同机受控 HTTPS（TLS `MSG_PEEK` 抓 `ClientHello`），采集
    main/iframe/Worker/ServiceWorker 四上下文 18 项 API、请求头与 JA3/JA4。
    unit 用合成 ClientHello 验证 GREASE 过滤、扩展洗牌下 `ja4`/`ja3_sorted`
    稳定而 raw `ja3` 变化，并用真实 HTTPS server 回归 `get_request` 解析。
- 门禁默认阻断：`compare_reports` 对未批准漂移、缺测、上下文支持翻转、
    未获批非确定方差、`inconclusive` 一律 `blocked`；同制品重复须显式
    `tls_extension_shuffle_via_ja4` 规则才 `approved`。E2E 覆盖
    strict / approved / HTTP-only（TLS 不可判定）/ seed 漂移四场景。
- 报告干净性：探针证据不得把临时路径/时间戳等运行元数据混进信号样本；
    已由 `fontconfig_file` → `fontconfig_present` 的根因修正回归守护。
- 本机只有一套已获准 `linux-arm64` 制品，故不跑真实跨版本升级放行；
    完整测量数据与未能验证项见
    `docs/tasks/t068_profile_fingerprint_verification/measurement_report.md`。

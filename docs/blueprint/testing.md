# 测试

CBrowser 质量门禁与测试契约规范。章节名 `verification_policy` / `verification_notes` / `doctor_cmd` / `test_cmd` / `blackbox_verify` 是 preflight 与 skill 的机械锚点，不得改名；命令写在对应章节的代码块内，严格按 Bash 的 `-e -o pipefail` 执行。

## verification_policy

project_configured

## verification_notes

当前项目采用多层验证体系与专项技术探针机制：

1. **模板与工作流工具链契约**：通过运行 `.repo_template/tests`（带 `-m contract` 标记）验证 task 状态机、文档解析及仓库整洁度，通过数量以实际输出为准；
2. **业务后端单元测试基线**：通过 `uv` 运行 `src/backend/tests`，涵盖现有 API 接口、鉴权、下载捕获、数据库及生命周期，通过数量以实际输出为准；
3. **前端测试基线与 Node 26 环境标记**：
    - 在 Node v26+ 环境下，运行前端测试因 Node 默认开启的实验性 WebStorage 会在 `localStorage.getItem` 处抛出异常（参见 d001，直接运行会导致大量失败）；
    - 运行前端测试必须显式设置环境变量：`NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend`，通过数量以实际输出为准；
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

## doctor_cmd

环境前置检查：契约测试可成功收集；另需 `md_kx` 在 PATH。

```bash
export TMPDIR="$(mktemp -d)"
mkdir -p "$TMPDIR"
pytest .repo_template/tests -q --collect-only -m contract
command -v md_kx
```

## test_cmd

本仓不使用 GitHub Actions CI。日常全量门禁的唯一入口是 `scripts/run_gates.sh`；`test_cmd` 中的模板契约命令行仅为模板门禁标记，实际执行以脚本为准；它依次运行模板契约、legacy 后端、v2 unit、v2 integration、前端测试与生产构建。

```bash
pytest .repo_template/tests -q -m contract
# 全量门禁：scripts/run_gates.sh
```

## blackbox_verify

真实 Docker/Chrome 黑盒通过同一入口的 E2E 必需模式执行；缺少镜像、缓存或 Chrome 时在会话开始即失败并列出缺项。

```bash
CBROWSER_RUN_E2E=1 scripts/run_gates.sh
```

## Stream Runtime 组件验证

运行 t004/t015 组件验收前，按照 docs/guides/stream_runtime_validation.md 提供 Browser/Stream 不可变镜像 ID 和只读引擎缓存。完整媒体测试通过官方 Mac Google Chrome，覆盖双 Peer、复制标签、刷新、关闭首 tab、可见性暂停/恢复、Viewer 断线 resume、共享策略、真实组合输入与 Browser 生存性；媒体为同机直连，无 coturn/TURN。

```bash
# 统一入口：scripts/run_gates.sh；E2E 使用 CBROWSER_RUN_E2E=1 scripts/run_gates.sh
```

会话建立时延与候选类型（t019）：真实 Chrome 黑盒须断言新建会话的 ICE 候选集仅含 `host` 类型、远端候选地址恒为 `127.0.0.1`（不出现 `srflx`/`relay`/`prflx`），且侧边栏切换已运行 Profile 与同 Profile 刷新重建会话到首帧均不超过 2 秒；用例在 `tests/e2e/test_frontend_app_e2e.py`（`test_t019_switch_and_refresh_first_frame_within_2s_host_only`），经 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 执行。Stream entrypoint 的 ICE-lite 启动参数由 unit 门禁 `tests/unit/test_stream_ice_config.py` 守护，防止回退 Selkies 默认外部 STUN/TURN。

先创建允许写域内 TMPDIR，不能依赖不存在的目录让 pytest 回退系统 /tmp。

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
|**单元测试**|pytest 后端业务测试与前端 Vitest（`NODE_OPTIONS=--no-experimental-webstorage`）；数量以实际输出为准|mock 掉真实逻辑、在业务代码中弱化测试断言|
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

按照 [Supervisor 验证](../guides/supervisor_validation.md) 提供当前源构建的不可变镜像及缓存。统一运行 `scripts/run_gates.sh` 或 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`，不直接调用裸 pytest。

生命周期与恢复组件分别运行，避免以单个容器图用例替代全部异常路径：

```bash
# 统一入口：scripts/run_gates.sh；E2E 使用 CBROWSER_RUN_E2E=1 scripts/run_gates.sh
```

运行前必须设置允许写域内 TMPDIR、UV_CACHE_DIR、pytest basetemp/cache_dir，并仅为本地测试进程清除代理环境；这不会关闭 OrbStack 透明代理。测试前提存在但无效须失败，不能把镜像拉取/进程启动失败作为网络拒绝证据。跨 Profile 网络负例必须使用不做对端地址过滤的服务，同网正例成功；普通桥未隔离事实见 d020；Runtime 内核策略须通过无过滤监听器正负对照，不能以应用按来源拒绝连接冒充网络隔离。

网络与启动清理专项还须运行 `test_supervisor_namespace_policy_e2e.py`、`test_supervisor_ipv6_policy_e2e.py`、`test_supervisor_policy_failure_e2e.py` 和 `test_supervisor_orphan_helpers_e2e.py`。仅在持有 CoordinatorLock 的启动阶段回收遗留 helper，周期扫描不得调用该清理。

资源压力验证继续运行 `test_supervisor_resource_policy_e2e.py`、`test_supervisor_resource_capacity_e2e.py`、`test_supervisor_resource_monitor_e2e.py`，以及 Stream Runtime 的真实 Chrome CPU 降帧用例。保存实际 CPU counter、quota、采样窗口、配额下发与 Chrome 帧数；资源算法、真实采样、实际画面各自证据不互相替代。

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

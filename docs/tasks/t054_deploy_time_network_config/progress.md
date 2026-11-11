---
tid: "t054"
slug: "deploy_time_network_config"
title: "网络配置回到部署期：删除运行时网络应用与 LAN，接入可信代理来源"
status: "done"
branch: "t054_deploy_time_network_config"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "e9320341a8b5c93d136fca64b1aad25825ec2898"
depends_on: "t051"
conflicts_with: "t055,t056"
note: "来源 review_20261110_200842 adoption_decision A61 A14"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 现场核实（2026-11-11，实施前）

- 运行时链路全貌：`NetworkService`（815 行，publication prepare/ACK/revoke + Supervisor rebuild/converge + fencing + 恢复循环）→ `api/v1/network_router.py`（settings PUT / apply / operations / check-disconnect / root-ca）→ Gateway publication 端点（`gateway/server.py:459` + `NetworkPublicationAuthority`）→ Supervisor `rebuild-edge` / `converge-streams`（`control_server.py:609/803`）+ `core.py:rebuild_edge_proxy` / `restore_edge_proxy` / `converge_network_streams` / `_get_applied_network_config`（零调用）+ `docker_adapter.rebuild_caddy_container`（仅上述两方法调用）+ `operation_journal` 网络回执（`record_network_execution` 等 8 个方法）+ repository 网络方法（`settings` 表 `network.*` 键，无独立表）+ 迁移 0003（`network.*` 键的种子/回填）。
- `client_ip` 两副本逐字节相同（`auth/client_ip.py` 与 `gateway/client_ip.py` 各 57 行）；`auth/__init__.py` 导入重型 `AuthService`，故共享模块不放在 `auth` 包下，另建无依赖的 `cbrowser/shared/client_ip.py`，Gateway 镜像按文件白名单纳入。
- 指纹现状：`deploy.sh:653` 以 `sha256(network_config.py)` 作 `caddyfile_sha256`（哈希生成器源码，审阅第 32 项）；rollback 只校验 compose 指纹，不重生成 Caddyfile（第 33 项）。
- 默认端口字面量（代码内）：`network_config.py:DEFAULT_HTTPS_PORT = 56661`（唯一定义，保留）、`domain/models.py:904`（随 `NetworkAccessConfig` 删除）、`api/main.py:16`（`CBROWSER_PORT` 默认值，改引常量）、`scripts/deploy.sh:65`（`:-56661`，改为从常量派生）、`SettingsPage.tsx:72`（`useState(56661)`，随表单删除）。`.env.example:3` 与文档中的 56661 为示例值，不属定义，不纳入负向断言范围。
- edge 子网决策：A14 只要求「compose 的 edge 网络固定 IPAM 子网」，未指定值。单值固定会破坏 t032 双实例并存（Docker 拒绝重叠子网的第二个 bridge 网络），故按媒体子网池同款做法——deploy.sh 从实例身份摘要派生每实例固定子网 `172.(18 + digest mod 14).0.0/16`（避开 Docker 默认 172.17.0.0/16），写入 release env（`CBROWSER_EDGE_SUBNET`），compose 以 IPAM 固定该子网；`CBROWSER_TRUSTED_PROXY_CIDRS` 与 edge 子网同值，由 deploy.sh 推导注入 API 与 Gateway。deploy.sh 增加子网冲突预检（已有 Docker 网络子网 + 宿主接口地址重叠即拒绝，给出改 `CBROWSER_PREFIX`/`CBROWSER_DATA_ROOT` 或显式 `CBROWSER_EDGE_SUBNET` 的可执行提示）。
- 迁移 0008 的 downgrade：只能是 no-op（删除的 `network.*` 行无数据恢复路径；旧代码随本 task 一并删除，降级后无消费方）。`test_control_migration.py` 的 `command.downgrade(cfg, "a35c0f1e7b42")` 会经过 0008 的 downgrade，raising 会破坏该测试，故不 raise，注释写明。
- 前缀/标签锁死：deploy.sh 与 compose 的默认前缀仍为 `cbrowser`（t051 已登记的不对称：deploy.sh 按 A22 校验自身输入，改默认会自拒；不属本次偏离，不动）。Supervisor 编译内默认 `cbrowser-t005` 与 `com.cbrowser.instance-id` 键名不受影响。

### TDD 红基线（2026-11-11）

- 先写 8 个新测试文件、后写实现：红基线 26 failed / 3 passed（前 6 个文件）。红基线期两次测试修正：字面量扫描测试 `partition(":")` → `split(":", 2)`；compose 结构测试由 PyYAML（门禁 venv 无此包）改写为文本断言；迁移测试用 `INSERT OR REPLACE`（迁移 0003 已种子部分 `network.*` 行）。

### 后端实现（2026-11-11）

- 共享 `client_ip`：`git mv src/backend/cbrowser/auth/client_ip.py src/backend/cbrowser/shared/client_ip.py`（原文照搬），删除 Gateway 副本，新建 `shared/__init__.py`；`api/app.py`、`api/v1/auth_router.py`、`automation_router.py`、`control_router.py`、`gateway/server.py` 改引共享模块。
- `network_config.py` 瘦身：保留 `DEFAULT_HTTPS_PORT = 56661`、`generate_caddyfile(https_port, ...)`、`derive_origin_whitelist`、`compute_caddyfile_sha256`、`CADDYFILE_FILENAME`；删除 `validate_lan_ip`、`build_applied_network_version`、双文件读写、`APPLIED_VERSION_FILENAME`、`_bind_host` 与网络模型导入。`generate_caddyfile` 在产物首行嵌入 `# CBrowser deploy Caddyfile — https_port {port} (rendered by deploy.sh; do not edit)`，使端口变化必然改变产物与指纹（AC-006）；`_format_origin` 对默认端口（https/443）省略端口号，与 `normalize_origin` 保持一致。
- `network_config_cli.py` 重写：只剩 `render` 子命令（`--network-dir`、`--https-port`），确定性写出部署端口的 Caddyfile 并打印 `BIND_HOST=127.0.0.1` / `HTTPS_PORT` / `PUBLIC_ORIGIN` / `CADDYFILE_SHA256`；非法端口 exit 2；旧 `init` / `read` 删除。
- Gateway：`gateway/config.py` 重写——只保留真实字段（host、port、token 文件、api_url、心跳超时 + 校验、`build_id`）与新增 `https_port`（`CBROWSER_HTTPS_PORT` 环境回落，默认 `DEFAULT_HTTPS_PORT`，范围校验）；`allowed_origins` 改为按端口派生的 property；恢复 `from_env`（`gateway/__main__.py:22` 调用）；删除 `NetworkPublicationAuthority`、`network_state_dir`、基线导入与发布方法。注意：`trusted_proxy_cidrs` 不是 config 字段，`server.py:191` 直接读环境变量；自造字段（`log_dir`、`session_cookie_secret`、`allowed_browser_origins`、viewer/stream 上限）经核查从未存在，已一并清除。`gateway/server.py` 删除 `_PublicationRequest`、`_check_publication_auth`、`handle_network_publication`、路由注册与发布 token 加载；viewer 信令路由直接查 `config.allowed_origins`。
- API：`api/app.py` 删除整块 t042 NetworkService 代码（构造、发布 authority、恢复循环、`caddy_ca_dir`、`include_router(create_network_router())`）；新增 `_deploy_https_port()`（严格解析 `CBROWSER_HTTPS_PORT`，畸形即启动时 loud ValueError，不静默回落）；lifespan 内 `app.state.allowed_origins = derive_origin_whitelist(_deploy_https_port())`。**遗漏修复**：初版漏删 lifespan teardown 里的 `recovery_task.cancel()`（恢复循环已删，变量不存在），`test_auth_api.py` 的 Origin 测试以 `NameError` 失败暴露，已删该三行，复跑 15 绿。
- 删除模块：`git rm src/backend/cbrowser/api/v1/network_router.py`、`src/backend/cbrowser/services/network_service.py`（另清 stale `services/__pycache__/network_service.cpython-312.pyc`）。
- 领域模型：`domain/models.py` 删除 8 个网络模型（94 行）。
- Repository：`adapters/database/repository.py` 删除 5 个模型导入、`NetworkTransaction` + `_load_transaction`、pydantic 导入（仅该处用）、`_network_transaction_lock`、`asyncio` 导入（0 剩余引用）与整节 t042 代码（节注释至文件尾）。
- Supervisor：`api/runtime_coordinator.py` 删除 `_network_operation_headers` / `rebuild_edge` / `converge_network_streams` / `restore_network_snapshot`（150 行，至文件尾）；`supervisor/control_server.py` 删除 `_write_execution_receipt` 与两个端点（243 行）及已无用的 `DockerSandboxError`、协议模型、`compute_caddyfile_sha256` 导入；`supervisor/core.py` 删除 `_get_applied_network_config` 至 `converge_network_streams` 的网络块（410 行）与网络导入，`_replace_stream_only` 去掉 `bind_host` / `advertised_ip` 参数；`supervisor/docker_adapter.py` 删除 `rebuild_caddy_container`（111 行，文件尾方法）与 `start_stream_container` 的 `bind_host` / `public_ip` 参数；`supervisor/container_spec.py` 的 `stream_labels` 去掉两参数与两标签键、`stream_ports` 硬编码 `127.0.0.1`、`stream_environment` 去掉 `public_ip` 参数（`CBROWSER_WEBRTC_PUBLIC_IP` 硬编码 `"127.0.0.1"`）；`supervisor/protocol.py` 删除 `RebuildEdgeRequest` / `ConvergeStreamsRequest`（21 行）与 Union 条目；`supervisor/network_policy.py` 删除 `allow_lan_media` 字段、校验分支与 `media_lan` 列表（核查：Stream 媒体 ACCEPT 只剩链路本地 `169.254.0.0/16` / `fe80::/10`，`10.0.0.0/8` 只出现在 DROP）；`supervisor/operation_journal.py` 删除 8 个网络收据方法（107 行）。
- `api/main.py`：`CBROWSER_PORT` 默认值改为 `str(DEFAULT_HTTPS_PORT)`（引常量）。
- 迁移 0008：`src/backend/migrations/versions/0008_drop_network_transaction.py`，revision `3751fed02a4a`，down_revision `1a8db6b91744`（0007）；upgrade 为 `DELETE FROM settings WHERE key LIKE 'network.%'`，downgrade 为有文档说明的 no-op。

### deploy.sh / compose.yaml / .env.example（2026-11-11）

- deploy.sh：`NET_CONFIG_PY` 解析移至端口默认值之前；`DEFAULT_HTTPS_PORT` 直接运行 Python 常量得出；`HTTPS_PORT="${CBROWSER_HTTPS_PORT:-$DEFAULT_HTTPS_PORT}"`。`derive_instance_identity` 多输出一行 edge 子网 `172.(18 + digest mod 14).0.0/16`，导出为 `CBROWSER_EDGE_SUBNET`。新增 `check_edge_subnet_conflict()`（调 `scripts/check_edge_subnet.py`；重叠即拒绝并提示改 `CBROWSER_PREFIX` / `CBROWSER_DATA_ROOT` 或显式 `CBROWSER_EDGE_SUBNET`）。`network_config()` 包装简化为 render only（失败以 CLI 退出码拒绝部署；rc 3/4 缺失/损坏分支删除）。`load_release_identity` 白名单加 `CBROWSER_EDGE_SUBNET` / `CBROWSER_TRUSTED_PROXY_CIDRS`、删 `CBROWSER_BIND_HOST`。`build_and_record_release` 的 `caddyfile_sha` 改为渲染产物 `$DATA_ROOT/network/Caddyfile` 的 sha256；release env 删 `CBROWSER_BIND_HOST`、加 `CBROWSER_EDGE_SUBNET` 与 `CBROWSER_TRUSTED_PROXY_CIDRS=$CBROWSER_EDGE_SUBNET`；manifest `instance` 加 `"edge_subnet"`。`cmd_deploy` 在 `check_prefix_conflict` 后调 `check_edge_subnet_conflict`；单次 `eval "$(network_config render --network-dir "$DATA_ROOT/network" --https-port "$HTTPS_PORT")"`；导出 `CBROWSER_HTTPS_PORT` 与 `CBROWSER_TRUSTED_PROXY_CIDRS`。`cmd_rollback` 在冲突检查后按目标 release 记录端口重渲染 Caddyfile，渲染 sha 与目标 manifest `caddyfile_sha256` 不符即拒绝（检查在前，被拒回退不碰磁盘）。`bash -n` 通过；除前提提示中点名生成器路径外，无 `BIND_HOST` / `56661` / `init` / `read` 残留。
- 新增 `scripts/check_edge_subnet.py`：exit 0 无重叠、1 重叠（详情 stderr）、2 Docker 枚举失败（fail closed）。Docker 网络子网经 `docker network ls --format {{.ID}}` + `inspect`（JSON `IPAM.Config[].Subnet`）枚举；宿主接口经 `ip -j addr`（Linux）或 `ifconfig` 解析（macOS/BSD 与 Linux 两种 `netmask` 写法），best-effort。本机接口 `lo 127.0.0.1/8`、`host0 198.19.0.2/30`，与 172.18–172.31 无重叠；用户 Mac 为 192.168.31.x + Tailscale 100.x，同样无重叠。
- compose.yaml：caddy 端口改为 `"127.0.0.1:${CBROWSER_HTTPS_PORT:?run scripts/deploy.sh first}:443"`；`networks.edge` 加 `ipam.config: [{subnet: ${CBROWSER_EDGE_SUBNET:?run scripts/deploy.sh first}}]`；api + gateway 环境加 `CBROWSER_HTTPS_PORT` 与 `CBROWSER_TRUSTED_PROXY_CIDRS`（均 `:?run scripts/deploy.sh first`）；gateway 删 `CBROWSER_NETWORK_STATE_DIR` 环境与 `/data/network` 只读挂载。保留说明：`CBROWSER_GATEWAY_HOST: 0.0.0.0` 与 supervisor `--host 0.0.0.0` 是容器内 edge 网络监听、非宿主绑定；通配绑定测试已改为只断言已发布 `ports:` 映射。
- `.env.example` 按 t054措辞重写；`CBROWSER_EDGE_SUBNET` / `CBROWSER_TRUSTED_PROXY_CIDRS` 注明为 deploy.sh 输出（注释示例值 `172.18.0.0/16`）。

### 前端（2026-11-11）

- `SettingsPage.tsx` 重写网络区块为只读：显示 `window.location.origin`（`data-testid="network-current-address"`）与 `window.location.port || "443"`（`data-testid="network-current-port"`）及 `t("networkDeployTimeNote")`；删除 LAN 开关/IP/端口输入、保存/应用按钮、应用弹窗、root-ca 区块与全部网络 state/handler/effect、`useNetworkSettingsQuery` / `useNetworkOperationPolling` 导入、`useRef` / `useQueryClient`、`Download` 图标。主题/语言/健康/字体集区块未动。
- 删除 `useNetworkOperationPolling.ts`、`useNetworkQueries.ts`（git rm）；`client.ts` 删除 `readonly network` 块与 6 个网络类型导入；`types.ts` 删除 8 个网络类型重导出。
- `i18n.tsx`：两 locale 的 t042 块替换——保留 `networkAccess`、`networkAccessDesc`（改写为只读措辞）、`httpsPort`，新增 `currentAccessAddress` 与 `networkDeployTimeNote`（两 locale 同键；`TranslationKey = keyof typeof en` 强制对等）；删除 `lanAccessToggle`、`lanAdvertisedIp`、`lanAdvertisedIpPlaceholder`、`invalidIpError`、`pendingChanges`、`appliedStatus`、`appliedLan`、`appliedLocal`、`savePending`、`savedSuccess`、`applyChanges`、`applying`、`applySuccess`、`applyFailed`、`adminPasswordPrompt`、`adminPassword`、`confirmApply`、`disconnectWarningTitle`、`disconnectWarningDesc`、`downloadRootCa`、`rootCaDesc`、`rootCaInstructions`、`httpsPortInvalid`（两 locale）；通用 `saving` 保留。全部被删键经 grep 核查只在 SettingsPage.tsx 使用。
- 前端测试：重写 `SettingsPage.network.test.tsx`（只读展示 + 8 个表单 testId 全不存在 + 无 `/api/v1/network` 请求；断言 live `window.location` 值，不硬编码端口）；整删 `a19_polling_hook.test.tsx`、`a19_settings_polling.test.tsx`、`a21_network_client.test.ts`；`SettingsPage.test.tsx` 删 client 中已死的 `network` stub；`a21_settings_contract.test.tsx` 删两个网络契约用例 + 网络 stub/helper + 未用的 `flush` helper，只保留字体查询错误测试。
- Schema 重生成：`scripts/export_openapi.py`（`schemas/openapi/cbrowser_v1.json` + `cbrowser_internal.json`）与 `scripts/export_supervisor_protocol.py`（`schemas/runtime/supervisor_protocol.json`）；`npm run generate:api` 重生成 `src/frontend/src/shared/api/generated/cbrowser_v1.d.ts`——0 处 network 引用。Node：worktree 无 `node_modules`，复制主仓的（188M）缺 `@radix-ui/*`（过期），故跑 `npm ci`（已完成：added 289 packages）。

### Dockerfile 白名单（2026-11-11）

- Gateway 镜像：保留 `network_config.py` 拷贝（需 `derive_origin_whitelist` + `DEFAULT_HTTPS_PORT`），新增 `cbrowser/shared/__init__.py` + `client_ip.py` 拷贝；`Dockerfile.dockerignore` 同步加三行白名单。
- Supervisor 镜像：删除 `network_config.py` 拷贝（核查：supervisor 树内源码已无任何 `network_config` 导入；仅剩的 grep 命中是已删 `network_service.py` 的 stale `.pyc`，已清除）；`Dockerfile.dockerignore` 删对应白名单行。`test_docker_build_contexts.py` 通用测试（扫描全部 Dockerfile）6 绿。

### 测试整删与改写（2026-11-11）

- 整删（git rm，理由：整题材材为已删的 router / service / repository / publication / fencing / LAN 测试；见各文件题头或本节记录）：`tests/unit/test_network_config.py`、`test_network_router.py`、`test_network_service.py`、`test_network_repository.py`、`test_a24_network_config_cli.py`、`test_supervisor_core_network.py`、`test_supervisor_network_endpoints.py`、`test_a35_gateway_ack.py`、`test_a35_network_transaction.py`、`test_a1_network_rpc.py`、`test_a2_network_prefix.py`、`test_a21_network_contract.py`（整题材材为已删 router）、`tests/integration/test_network_apply_operations.py`、`test_a29_network_rpc.py`、`test_a35_recovery.py`、`test_ac007_origin_whitelist_sync.py`（由 `test_t054_origin_whitelist_deploy.py` 替代）、`tests/e2e/test_network_access_lan_e2e.py`、`tests/integration/test_a35_supervisor_receipt.py`（整题材材为经 `rebuild_edge_proxy` 的网络执行收据）。
- 新增 8 个 t054 测试文件（见“测试结果”）。
- 改写：`test_network_policy.py`（删 LAN-adds 测试；scoping 测试去参数化；新增 `test_allow_lan_media_field_is_rejected`，断言 pydantic `extra="forbid"` 拒绝该字段）与 `test_a10_stream_egress.py`（删 `lan` 参数/`V4_LAN`/`V6_LAN` 与 LAN 测试）；`test_gateway_config.py` 按环境端口派生重写；`test_control_migration.py` 删两个网络测试 + `_legacy_applied_payload` helper + 4 个模型导入 + `NetworkPublicationAuthority` 导入，保留 `test_0003_drops_terminal_or_orphan_active_operation`（0008 删光其断言缺失的行，仍通过）与 `_legacy_operation_payload`；`test_a16_protocol_drift.py` 从 `SUPERVISOR_OMISSIONS` 与 packets 字典删两个协议模型；`test_a28_daemon_host_port.py` 的 `test_daemon_port_propagates_to_origin_env_and_network_state` 改名为 `..._and_deploy_port`，删已应用状态文件读取，改为断言 gateway 记录的环境同样有 `CBROWSER_HTTPS_PORT == "41234"`（新增 `_gateway_record` helper；`json` 导入随之删除）。
- Fixture 改写（均为真实 Docker 的 e2e 夹具，本机环境跳过）：`tests/fixtures/gateway_probe/topology.py`（Caddyfile 改由 `generate_caddyfile(DEFAULT_HTTPS_PORT)` 渲染；删已应用状态写与 `data/network` 子目录创建；gateway 环境删 `CBROWSER_NETWORK_STATE_DIR` 与 `/data/network` 挂载，加 `CBROWSER_HTTPS_PORT: str(self.caddy_host_port)`，因宿主端口由 Docker 动态分配；`DEFAULT_HTTPS_PORT` 导入供渲染用）；`tests/fixtures/supervisor_recovery_probe/gateway_service.py`（删 `network_state_dir` 参数与种子块；GatewayConfig 不再传该字段）；`tests/integration/test_gateway_fixtures.py`（删种子块；GatewayConfig 加 `https_port=8443`，与 harness 的 viewer origin `https://localhost:8443` 对齐）；`tests/e2e/test_supervisor_container_graph_e2e.py`（删 `data/network` 子目录与已应用状态种子；gateway 环境删 state dir 与挂载，加 `CBROWSER_HTTPS_PORT: "56661"`，与测试 auth 上下文 origin `https://127.0.0.1:56661` 对齐）；`tests/unit/test_baseline_fixture_regressions.py` 的 `test_caddyfile_generator_uses_authoritative_gateway_port` 改为 `generate_caddyfile(DEFAULT_HTTPS_PORT)` 调用。
- `test_auth_api.py`：`test_applied_network_origin_single_source_and_unlisted_rejected` 改名为 `test_deploy_port_origin_single_source_and_unlisted_rejected`，注释改为部署端口派生；行为本身不变（默认端口 56661）。
- `test_auth_client_ip.py` / `test_a4_control_plane.py`：导入路径改为 `cbrowser.shared.client_ip`。`test_a4_viewer_throttle.py`：两导入合为共享模块；按 A14 删除双导入漂移测试 `test_gateway_client_ip_matches_existing_auth_rules`（单模块守卫在 `test_t054_shared_client_ip.py`：旧模块 `importlib` 导入必 `ModuleNotFoundError`、API 与 Gateway 的函数 `__module__` 均为 `cbrowser.shared.client_ip`）；其余两测试改名 `test_shared_*`。
- `test_a24_deploy_network_source.py` 按 render 协议重写：entrypoint 断言改为 `render --network-dir "$DATA_ROOT/network"` + `eval "$(network_config render`，并断言无 `init` / `read --network-dir`；权威值断言改为 `CBROWSER_HTTPS_PORT` + `CBROWSER_TRUSTED_PROXY_CIDRS="$CBROWSER_EDGE_SUBNET"`，无 `CBROWSER_BIND_HOST`；rc 断言改为 render 失败以 CLI 退出码拒绝部署（无 rc 3/4 区分、无 `case "$rc" in`）；隔离部署测试：PY_STUB 改为 `render` 失败（`STUB_RENDER_RC`）、fake docker 加 `build` / `image` / `run` / `network` 分支（render 在 `build_api_image` 之后，故隔离部署须先走通 build 与 schema 检查）、fake 仓复制 `scripts/check_edge_subnet.py`、环境显式设 `CBROWSER_HTTPS_PORT=56661`（stub 的 `-c` 不输出，默认端口推导为空）。
- `test_t027_release_controller.py`：fake docker 加 `network` 分支（`ls` 输出 `FAKE_NETWORK_IDS` 或空；`inspect` 输出 `FAKE_NETWORK_SUBNETS` JSON）；fake 仓复制 `check_edge_subnet.py`；`_instance_identity` 改为 3 元组（加 edge 子网 `172.{18 + digest mod 14}.0.0/16`），instance-B 断言与确定性断言同步加 `edge_subnet` / `CBROWSER_EDGE_SUBNET` / `CBROWSER_TRUSTED_PROXY_CIDRS`；`test_caddy_fingerprints_recorded_and_change_sensitive` 重写——指纹改为渲染产物 `$DATA_ROOT/network/Caddyfile` 的 sha256（生成器源码追加 `# drill change` 后、经 `PYTHONPATH=<fake>/src/backend:<real>/src/backend` 用改过的生成器渲染，指纹**不变**；端口改为 56662 后指纹**变化**；前端 sha 与 API 镜像不变）。
- `test_refactor_behavior_equivalence.py`：`stream_environment` 调用删 `public_ip="203.0.113.1"`，新增断言 `env["CBROWSER_WEBRTC_PUBLIC_IP"] == "127.0.0.1"`。`test_gateway_endpoint.py` 未动（`normalize_origin` / `normalize_origins` 仍存在，18 绿中已覆盖）。

### 文档（2026-11-11）

- 新增 ADR 031（`docs/blueprint/decisions.md`，替代 ADR 026 的运行时边缘重建部分，记录 p053 前提变化；ADR 013 媒体直连回到仅回环）。
- `docs/specs/release_deployment.md`：实例 env 列表加 edge 子网与 TRUSTED_PROXY_CIDRS；回退约束加“按目标端口重渲染并校验 sha”；「确定性 Caddyfile 生成与边缘端口重建（t042）」整节按 t054 重写。
- `docs/blueprint/gateway.md`：Origin 门禁改为部署端口派生。`docs/blueprint/security.md`：会话 Origin 白名单改为部署端口派生；root-ca 段改写（端点已删，CA 私钥隔离保留）。`docs/specs/access_control.md`：LAN 整节按 t054 重写。`docs/blueprint/frontend.md` §9 按只读重写。`docs/blueprint/architecture.md`：已应用版本行按 t054 重写。`docs/specs/webrtc_remote_display.md`：局域网直连整节按 t054 重写（回环直连 + 链路本地放行）。`DOCKER_DEPLOYMENT.md`：指纹措辞由“生成器”改为“渲染后 Caddyfile”。
- `docs/specs_index.md` 登记 t054：`release_deployment`、`access_control`、`webrtc_remote_display` 三行。`docs/blueprint/supervisor.md` 无运行时网络应用描述，无需改动；`docs/archive/plans/plan_v2_architecture_.md` 已归档，不动。
- 全树复查：`lan_` / `network_service` / `publication` / `rebuild-edge` / `converge-streams` / `root-ca` / `applied_network` 在 `src` / `tests` / `scripts` / 文档中的剩余命中均为有意历史注释、测试断言中的反向引用（断言其不存在）、`node_modules` 供应商文件或无关概念（媒体网络 `plan_for_subnet`、automation probe 的 runner_info publication）。

### 全量回归首轮发现 8 个新增失败（2026-11-11，均已修）

- 首轮后端全量：**33 failed / 2006 passed / 8 skipped**（433s，日志 `.scratch/t054-backend-regression.log`）。按名比对 t053 基线 27 失败：25 个与基线一致；a24 的 2 个基线失败已随测试重写消失（旧 read rc3/rc4 测试删除，render 测试通过）；新增 8 个，根因逐个查实如下（非 flaky，全部可复现）：
    1. `test_stream_ice_config.py` 2 个 + `test_stream_clipboard_policy.py` 1 个 + `test_selkies_file_transfers.py` 1 个：调用 `stream_environment(public_ip="127.0.0.1")`，参数已按 task 契约删除（`TypeError`）。四处调用传的都是 `127.0.0.1`，恰为新硬编码值；删 kwarg，测试意图（ICE-lite 开启、无 STUN/TURN、剪贴板锁定策略、文件传输禁用）不变。复测 21 passed（含 a6 与 t035 的修复）。
    2. `test_t035_openapi_contract.py::test_public_openapi_groups_are_resource_scoped`：期望的 `PUBLIC_GROUPS` 含 `'network'`，实际 OpenAPI 已无 network 组（AC-001 意图）；从测试的 `PUBLIC_GROUPS` 删 `'network'`。
    3. `test_a6_error_contract.py::test_real_422_and_404_are_structured`：404 探针打的是已删路由 `GET /api/v1/network/operations/does-not-exist`，无路由时 Starlette 返回默认 `{"detail": "Not Found"}`（无 `error` 键）。改探针为登录后 `GET /api/v1/profiles/does-not-exist`（实测返回结构化 `{'error': 'not_found', ...}`），意图（真实 404 结构化）不变。
    4. `test_t045_selkies_wheel_cache.py` 2 个：worktree 的 `.scratch/selkies_wheels/` 缺 pinned wheel `selkies-2.2.1-py3-none-any.whl`（`.scratch` 为 gitignored，不随 worktree 复制；主仓只有 2.1.0 旧 wheel）。按仓库既定规则 out-of-band 补齐：用仓库自带 `scripts/vendor_selkies_web.py::download_wheel` 从 PyPI 下载并校验 SHA-256（`18503b5c…a3cd`，与 pin 一致）后写入 worktree 缓存；复测 4 passed。此为环境缺口，非代码回归。
- 基线 2 errors（`test_a35_recovery.py` 与 `test_network_apply_operations.py` 的 flaky teardown）随两文件整删而消失。
- 修复后第二轮全量回归（日志 `.scratch/t054-backend-regression-2.log`）：**2014 passed / 25 failed / 8 skipped / 0 errors**（427s）。25 个失败按名与基线剩余 25 个一致（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1；与首轮 33 个失败逐名 comm 比对，第二轮 25 个全在首轮集合内，新增 0 个，消失的恰为修复的 8 个）；errors 归零（基线 2 个 flaky teardown 随整删文件消失）。passed 由 2089 降至 2014：整删 18 个文件含 48 个测试定义、改写文件删减用例（a4 双导入漂移 7 例等），新增 t054 测试 36 个定义 / 38 个用例，余差为参数化展开数。

### 测试结果

- 新 t054 测试集（8 文件）：**38 passed**（`test_t054_deploy_network_config.py`、`test_t054_network_config_cli.py`、`test_t054_no_default_port_literal.py`、`test_t054_shared_client_ip.py`、`test_t054_compose_deploy_structure.py`、`test_t054_migration.py`、`test_t054_openapi_no_network.py`、`tests/integration/test_t054_origin_whitelist_deploy.py`）。
- 改写文件分批：`test_a24_deploy_network_source.py` 8 passed；`test_t027_release_controller.py` 51 passed；`test_auth_api.py` 15 passed；`test_auth_client_ip.py` + `test_a4_viewer_throttle.py` + `test_a4_control_plane.py` + `test_auth_service.py` + `test_t054_shared_client_ip.py` 合计 44 passed；`test_refactor_behavior_equivalence.py` + `test_gateway_endpoint.py` 合计 18 passed；`test_docker_build_contexts.py` 6 passed；`test_a28_daemon_host_port.py` 6 passed；`test_network_policy.py` + `test_a10_stream_egress.py` 合计 19 passed；`test_control_migration.py` 7 passed；`test_a16_protocol_drift.py` 15 passed；`test_baseline_fixture_regressions.py` 的 caddyfile 生成器测试 1 passed。
- 前端：**538 passed / 0 failed**（74 个文件，vitest；t053 基线 556/0，减少 18 项为整删的 3 个网络测试文件与 2 个网络契约用例）。
- 后端全量回归（`tests/unit` + `tests/integration`，验证 venv，`PYTHONPATH=src/backend:tests`）：首轮 **33 failed / 2006 passed / 8 skipped**（433s），其中 8 个为本 task 新增失败（见“全量回归首轮发现”）；修复后第二轮 **2014 passed / 25 failed / 8 skipped / 0 errors**（427s），25 个失败按名与 t053 基线剩余 25 个一致（基线 27 个减 a24 的 2 个，后者随测试重写消失），无新增失败，errors 归零。t053 基线：2089 passed / 27 failed / 8 skipped / 2 errors。 Round 1 修复后第三轮 **2026 passed / 25 failed / 8 skipped / 0 errors**（407s，日志 `.scratch/t054_r1fix_backend_full.log`），25 个失败按名与第二轮 25 个一致，无新增（+12 为本轮新增测试：t027 5 + check_edge_subnet 5 + client_ip 2）；repo_hygiene 失败单跑核实违规全在 t051–t053 旧 review 文件与归档文件，零 t054 文件。

### 环境跳过项（按链规则 3：跳过计 pass，不呈报用户、不记待裁定）

- AC-010（[deploy]）：真实部署验证。本机无 Docker、无真实引擎，无法执行真实部署、登录、出图、外部接口探测与改端口重部署。替代验证：fake Docker CLI 驱动的 `deploy.sh deploy` 全流程（t027，51 passed，含端口变更指纹变化与回退路径）+ 集成 Origin 测试 + 前端 538 绿。须在用户机按 t032 演练补验。**本机未验证、不得记为已验。**
- AC-004 的“旧端口不可访问”真实侧：结构上 Caddy 只绑定新端口（compose 单端口映射 `127.0.0.1:${PORT}:443`），旧端口无监听；真实探测属 AC-010 的一部分，见上。
- AC-006 的“Caddy 重建触发”真实侧：机制为 Caddy 服务环境携带 `CBROWSER_CADDYFILE_SHA256` / `CBROWSER_FRONTEND_SHA256` 指纹变量，指纹变化时 `docker compose up` 仅重建 Caddy；真实 `up` 行为须在用户机部署中确认（fake docker 只断言记录与 env，不执行真实 compose）。
- AC-008 的“Caddy 发出 XFF”一半：Caddy `reverse_proxy` 默认追加 `X-Forwarded-For`，为 Caddy 默认行为；本机无 Docker 无法以真实 Caddy 验证，API/Gateway 侧的解析与按来源限流已有单测与集成测试覆盖。真实端到端属 AC-010。
- e2e 夹具（gateway_probe topology、supervisor container graph、supervisor reconciliation 等）均为真实 Docker 测试，本机跳过；本次只做了源码级改写与解析校验，未执行。
- 字体名：各平台真实字体名（微软雅黑/宋体/苹方等）为 t053 遗留，宿主测试用 NotoSansCJK 占位；与本 task 无关，未动。

### 遗留

- 无新增 pending 项。t053 遗留 p070（Radix pointermove 提交间隙）与本 task 无关，未动。
- 已知非阻塞债务：历史观测行仍累积（t052 f007 只给列表查询加了 bound，未做 retention 清理）；与本 task 无关，未动。

### Round 1 修复（2026-11-11）

Round 1 双路 FAIL（code 2 条：f001 important + f002 minor；test 4 条：f001 important + f002/f003/f004 minor）。按规矩先撤回 task.md 全部 10 个 AC 打勾，修复并重验后再重打勾。

- f001（code + test 同根）：`derive_instance_identity` 无条件覆盖显式 `CBROWSER_EDGE_SUBNET`，冲突提示的第三条出路是死的。修为有条件赋值（仅未显式设置时派生）；显式值仍走 `check_edge_subnet_conflict` 校验（非法 CIDR 由 `check_edge_subnet.py` exit 2 兜底拒绝），并照常记入 release env 与 manifest，rollback 沿用目标 release 记录值（无需另改）。`.env.example` 与 ADR 031 的措辞本就承诺显式覆盖，修后与实现一致，无需改动。测试：t027 新增 3 例——(a) 派生子网重叠即拒、无 release 记录、stderr 含可执行提示；(b) 显式 `172.40.0.0/16` 部署成功且 release env 与 manifest 均记显式值（172.40 不可能等于派生值 172.18–31，审阅建议的 172.25 可能与派生值重合，未采用）；(c) 显式子网重叠即拒（证明预检针对显式值）。另 `test_t054_check_edge_subnet.py` 新文件 5 例单测（无重叠 / Docker 重叠 / 宿主接口重叠 / Docker 枚举失败 exit 2 / 非法候选 exit 2，`subprocess.run` 伪造）。
- f002（code）：`cmd_rollback` 先把目标端口 Caddyfile 渲染进 `$DATA_ROOT/network` 再校验 sha，被拒回退仍改写磁盘。修为先渲染进 `mktemp -d` 临时目录、sha 通过后再 `cp` 进 `$DATA_ROOT/network`，被拒时删临时目录、磁盘不动；注释“被拒回退不碰磁盘”修后属实。
- test f002：回退端口一致性缺判别测试。t027 新增 2 例——rel-001 用 56661、rel-002 用 56662、rollback 后 Caddyfile 首行含 `https_port 56661` 且 sha 等于 rel-001 manifest 值；篡改目标 manifest `caddyfile_sha256` 后 rollback 被拒且磁盘 Caddyfile 与指针均不动。注：端口判别例在修前即绿（回退本就按目标端口重渲染），属覆盖固定而非缺陷复现；sha 篡改例修前红（磁盘被改写），修后绿。
- test f003：共享 `client_ip` 两条防御分支（peer 为 None → `"unknown"`、畸形 XFF hop 跳过）补覆盖：`test_t054_shared_client_ip.py` 新增 2 例（None peer；畸形 hop 跳过取其余最左非可信 hop，及全畸形链回落 peer）。行为未变，属覆盖补齐。
- test f004：设置页“无网络请求”断言空转（`client.request` mock 从未被调用）。删死 mock，改为断言页面实际走的数据路径 `health.check` 与 `fontSets.list` 各至少调用一次。
- 另修 progress.md 笔误：前端全量文件数为 74（非 77），538 passed / 0 failed 不变。
- TDD 先红验证：新 t027 5 例中应红的 3 例在修前确为红（f001(b)(c) 与 sha 篡改例），修后全绿；其余 2 例（派生重叠拒、端口判别）修前即绿，属行为固定。

### Round 2 修复（2026-11-11）

Round 2 test FAIL（1 条 important 新 finding f005；code 路 PASS 0 新 finding）。按规矩先撤回 task.md 全部 10 个 AC 打勾，修复并重验后再重打勾。

- f005：edge 子网冲突预检把本实例自有 edge 网络当冲突，首次部署成功后同一实例的任何二次部署与回退都会被预检拒绝。生产侧：`scripts/check_edge_subnet.py` 新增 `--exclude-network <name>` 参数；`scripts/deploy.sh` 的 `check_edge_subnet_conflict`（deploy 与 rollback 共用同一函数，两个调用点一次覆盖）传入 `--exclude-network "$PREFIX-edge"`。排除判据比审阅建议的纯按名排除更严：仅当网络名与子网同时与候选值一致时才排除（名 + 子网双条件）；同名不同子网的陈旧网络（改换显式子网后遗留）仍被拒，并给出专属提示（`docker network rm <name>`），外来网络永不排除。fail-closed 不变：Docker 枚举失败 exit 2、非法候选 exit 2、排除名不匹配时重叠仍拒绝。测试侧：t027 fake docker 加 `FAKE_OWN_EDGE_SUBNET` 变量——`network ls` 多返回 `own-edge-net`，`inspect` 在记录中追加自有网络（Name 为 `${CBROWSER_PREFIX}-edge`，由 deploy.sh 导出继承）；新增 3 例——(a) 同一实例连续部署两次成功；(b) 部署后 rollback 成功；(c) 自有网络存在时外来同子网网络仍被拒。`test_t054_check_edge_subnet.py` 新增 4 例单测——自有网络排除、外来同子网仍拒、陈旧同名不同子网仍拒且提示移除命令、排除名不匹配仍拒；`_fake_run_factory` 加 `docker_names` 参数（无 Name 的记录仍按外来网络处理）。
- 先红验证：脚本级按审阅者原场景复现——fake docker 只返回自有网络时，不带 flag 的真实脚本 exit 1（修前行为），带 `--exclude-network cbrowser-t005-edge` 时 exit 0，带不匹配的排除名时 exit 1；部署级回退探针——临时去掉 deploy.sh 的排除参数，t027 新 3 例中 (a)(b) 变红、(c) 仍绿，恢复后 sha256 校验字节一致、3 例复绿。
- 已知边界：改数据根致派生子网变化而前缀不变时，旧同名网络与新候选子网不重叠（/16 互不相交）故预检放行，compose 对已存在同名不同子网网络的处理属部署侧行为，本机无 Docker 未验证；显式子网改换后旧网络仍在时，若新旧子网重叠则预检以陈旧网络为由拒绝（须先 `docker network rm`），若不重叠则放行、由 compose 侧决定。
- 前端全量两遍一致：74 文件、538 passed / 0 failed。

### Round 3 修复（2026-11-11）

Round 3 code PASS（1 条 minor 新 finding f003；test 路 PASS 0 新 finding）。按规矩先撤回 task.md 全部 10 个 AC 打勾，修复并重验后再重打勾。

- f003：`scripts/check_edge_subnet.py` 的 `main()` 圈复杂度约 23。按审阅建议拆分：CLI 参数解析抽为 `_parse_args(argv)`（非法参数抛 `_UsageError`，`main()` 统一打印 usage 并 return 2），冲突分类抽为 `_classify_overlaps(existing, candidate, exclude_network)`（返回 `(conflicts, stale_own)`，名与子网双条件排除逻辑原文照搬）；`main()` 只留解析调用、候选校验、枚举、宿主接口合并与报错输出。行为未变：退出码 0/1/2、全部 stderr 文本（含 usage、invalid candidate、stale 专属提示、冲突提示）与重构前逐字一致。圈复杂度（AST 手算，同审阅规则）：`main()` 23 → 10、`_parse_args` 8、`_classify_overlaps` 8，均低于 15 的 minor 阈值；`_docker_networks` 13、`_host_interface_networks` 10 未变。
- 验证：CLI 级 10 个场景逐项核实（自有网络无 flag exit 1 / 正确排除 exit 0 / 错名排除 exit 1 / 重复 flag、缺值、未知 flag、第二位置参数、缺候选均 exit 2 + usage / 非法候选 exit 2 / 无重叠 exit 0），exit 码与 stderr 文本与重构前一致；受影响批 86 passed（check_edge_subnet 9 + t027 59 + a24 8 + compose 结构 10）；后端全量第五轮 **2033 passed / 25 failed / 8 skipped / 0 errors**（515.32s，日志 `.scratch/t054_r3fix_backend_full.log`），25 个失败与 R2 修复轮日志逐名完全一致，无新增，零 t054/check_edge_subnet 相关失败；前端全量 74 文件、538 passed / 0 failed。未新增测试：抽出的分支行为未变，9 例既有单测经 `main()` 全覆盖。
- /tmp 探针与 pytest basetemp 已清（45%）。


### Round 4 修复（2026-11-11）

Round 4 test PASS（1 条 minor 新 finding f006；code 路 PASS 0 新 finding）。按规矩先撤回 task.md 全部 10 个 AC 打勾，修复并重验后再重打勾。

- f006：`_parse_args` 的 5 种 `_UsageError` 情形中有 4 种（重复 `--exclude-network`、flag 缺值、未知 `--flag`、第二位置参数）在提交测试里零覆盖——仅缺候选有测试；R3 修复方的 10 场景 CLI 验证是一次性探针，未落为回归测试。`tests/unit/test_t054_check_edge_subnet.py` 新增 1 例参数化测试（4 个入参：重复 flag / 缺值 / 未知 flag / 第二位置参数），各断言 exit 2 且 stderr 含 usage 文本；另以 guard 断言解析失败前不触 subprocess（`subprocess.run` 被 monkeypatch 为必抛错的桩，若 `main()` 试图枚举网络即失败），核实 brief 中的说法。行覆盖探针（`sys.settrace`）证实：重复/缺值走 `_parse_args` :169，未知 flag/第二位置参数走 :173。行为本身正确，未改生产代码。
- 验证：check_edge_subnet 13 passed（9 既有 + 4 新增）；受影响批 117 passed（R4 的 113 + 4 新增）；后端全量第六轮 **2037 passed / 25 failed / 8 skipped / 0 errors**（520.95s，日志 `.scratch/t054_r4fix_backend_full.log`），2037 = 2033 + 4 新增；25 个失败另以 9 个失败文件子集重跑逐名核对，与 R3 日志 `FAILED` 行逐行完全相同，无新增，零 t054/check_edge_subnet 相关失败；前端全量 74 文件、538 passed / 0 failed。
- /tmp 自有 basetemp 已清（7%）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-11T19:31:42+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t054_code_f001|important|已修|derive_instance_identity 改为有条件赋值：显式 CBROWSER_EDGE_SUBNET 保留，仅未设置时派生；显式值仍走冲突预检并记入 release env 与 manifest。t027 新增 3 例行为测试（派生重叠拒、显式部署成功记显式值、显式重叠拒），修前 f001(b)(c) 先红后绿|scripts/deploy.sh:148；tests/unit/test_t027_release_controller.py:505；tests/unit/test_t054_check_edge_subnet.py:1|
|t054_code_f002|minor|已修|cmd_rollback 先渲染进 mktemp 临时目录、sha 通过后再 cp 进 $DATA_ROOT/network，被拒回退磁盘不动；注释“被拒回退不碰磁盘”修后属实。sha 篡改例先红后绿|scripts/deploy.sh:876|
|t054_test_f001|important|已修|与 code f001 同根：t027 补 3 例 fake-docker 行为测试（见 code f001 行），check_edge_subnet.py 补 5 例单测（无重叠 / Docker 重叠 / 宿主接口重叠 / 枚举失败 exit 2 / 非法候选 exit 2）|tests/unit/test_t027_release_controller.py:505；tests/unit/test_t054_check_edge_subnet.py:1|
|t054_test_f002|minor|已修|回退端口一致性补判别测试：rel-001 用 56661、rel-002 用 56662、rollback 后 Caddyfile 首行含 https_port 56661 且 sha 等于目标 manifest；篡改目标 caddyfile_sha256 后被拒且磁盘与指针不动|tests/unit/test_t027_release_controller.py:585|
|t054_test_f003|minor|已修|共享 client_ip 两条防御分支补覆盖：peer 为 None → "unknown"、畸形 XFF hop 跳过取其余最左非可信 hop、全畸形链回落 peer|tests/unit/test_t054_shared_client_ip.py:82|
|t054_test_f004|minor|已修|设置页断言改断页面实际走的数据路径：删从未被调用的 client.request 死 mock，断言 health.check 与 fontSets.list 各至少调用一次|src/frontend/src/features/settings/SettingsPage.network.test.tsx:45|

### Round 2 (2026-11-11T20:19:36+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t054_test_f005|important|已修|edge 子网预检排除本实例自有网络：check_edge_subnet.py 新增 --exclude-network 参数（仅名与子网同时与候选值一致时排除；同名不同子网的陈旧网络仍拒并提示 docker network rm；外来网络永不排除），deploy.sh 的 check_edge_subnet_conflict（deploy 与 rollback 共用）传入 --exclude-network "$PREFIX-edge"；t027 fake docker 加 FAKE_OWN_EDGE_SUBNET 建模自有网络，新增 3 例行为测试（连续部署成功、部署后 rollback 成功、外来同子网仍拒），check_edge_subnet.py 新增 4 例单测。先红验证：脚本级审阅者原场景无 flag 时 exit 1、有正确排除时 exit 0；部署级去掉排除参数后 (a)(b) 变红、(c) 仍绿，恢复后 sha256 校验字节一致、3 例复绿|scripts/check_edge_subnet.py:151；scripts/deploy.sh:176；tests/unit/test_t027_release_controller.py:588；tests/unit/test_t054_check_edge_subnet.py:123|

### Round 3 (2026-11-11T20:41:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t054_code_f003|minor|已修|check_edge_subnet.py 的 main() 圈复杂度 23 → 10：CLI 参数解析抽为 _parse_args(argv)（非法参数抛 _UsageError，main() 统一打印 usage 并 return 2），冲突分类抽为 _classify_overlaps（返回 (conflicts, stale_own)，名与子网双条件排除逻辑原文照搬）；main() 只留解析调用、候选校验、枚举、宿主接口合并与报错输出。行为未变：CLI 级 10 个场景 exit 码与 stderr 文本与重构前逐字一致；受影响批 86 passed（check_edge_subnet 9 + t027 59 + a24 8 + compose 结构 10）；后端全量第五轮 2033/25/8/0，25 个失败与 R2 修复轮逐名一致，无新增|scripts/check_edge_subnet.py:151；scripts/check_edge_subnet.py:155；scripts/check_edge_subnet.py:182；scripts/check_edge_subnet.py:219|


### Round 4 (2026-11-11T21:11:29+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t054_test_f006|minor|已修|_parse_args 的 4 种 _UsageError 情形（重复 --exclude-network、flag 缺值、未知 --flag、第二位置参数）在提交测试里零覆盖：test_t054_check_edge_subnet.py 新增 1 例参数化测试（4 个入参），各断言 exit 2 且 stderr 含 usage 文本，并以 guard 断言解析失败前不触 subprocess；行覆盖探针证实重复/缺值走 :169、未知 flag/第二位置参数走 :173。行为本身正确，未改生产代码；check_edge_subnet 13 passed，受影响批 117 passed，后端全量第六轮 2037/25/8/0（25 个失败与 R3 日志逐名一致），前端 538/0|tests/unit/test_t054_check_edge_subnet.py:253|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（10/10 AC 已打勾；AC-010 为 [deploy]，按链规则环境跳过计 pass，本机未验证、不得记为已验）
- 测试：后端全量第六轮 2037 passed / 25 failed / 8 skipped / 0 errors（520.95s，日志 `.scratch/t054_r4fix_backend_full.log`；25 个失败另以 9 个失败文件子集重跑逐名核对，与 R3 日志 `FAILED` 行逐行完全相同，按组：agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1，无新增，零 t054/check_edge_subnet 相关失败）；前端全量 538 passed / 0 failed（74 文件）；新 t054 测试集 53 passed（原 49 + check_edge_subnet 参数解析 4），另 t027 新增 8 例（R1 5 + R2 f005 3）；改写文件分批见“测试结果”
- 黑盒：无（本机无 Docker、无真实引擎；真实部署与真实引擎验证属 AC-010，须用户机按 t032 演练补验）
- review：Round 1 双路 FAIL（code 2 条：f001 important + f002 minor；test 4 条：f001 important + f002/f003/f004 minor），6 条已修并重验（见「Review 处置」Round 1 表）；Round 2 code PASS（0 新 finding，f001/f002 核实消除）、test FAIL（1 条 important 新 finding f005），f005 已修并重验（见「Review 处置」Round 2 表）；Round 3 双路 PASS（code 1 条 minor 新 finding f003，test 0 新 finding；f005 核实消除，AC-004/006/010 打勾依据恢复），f003 已修并重验（见「Review 处置」Round 3 表）；Round 4 双路 PASS（code 0 新 finding，test 1 条 minor 新 finding f006），f006 已修并重验（见「Review 处置」Round 4 表），待 Round 5 复审
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 局域网与运行时网络应用整链删除：后端 `NetworkService` / network router / Gateway publication / Supervisor `rebuild-edge` / `converge-streams` / 恢复围栏 / 日志网络收据 / 双文件已应用状态 / 8 个网络模型 / repository 网络方法 / 迁移 0008 删 `network.*` 行；前端设置页网络区块只读；deploy.sh 只剩 `render`，指纹改哈希渲染产物，回退按目标端口重渲染校验；edge 子网按实例摘要派生并注入 `CBROWSER_TRUSTED_PROXY_CIDRS`；`client_ip` 合并为唯一共享模块。diff 净删约 4750 行（72 个已改文件 + 11 个新文件，另 26 个文件整删）。
- 遗留：无新增 pending 项；环境跳过项见“环境跳过项”一节（AC-010 真实部署为首要）；t053 遗留 p070 与本 task 无关，未动。

### 长期文档闭环

- specs_index：已登记 t054（`release_deployment`、`access_control`、`webrtc_remote_display` 三行，2026-11-11）。
- ADR 031 新增（替代 ADR 026 运行时边缘重建部分，记录 p053 前提变化）；`release_deployment.md`、`access_control.md`、`webrtc_remote_display.md`、`gateway.md`、`security.md`、`frontend.md`（§9）、`architecture.md`、`DOCKER_DEPLOYMENT.md` 已同步更新；`supervisor.md` 无相关描述，无需改动；归档 plan 文档不动。

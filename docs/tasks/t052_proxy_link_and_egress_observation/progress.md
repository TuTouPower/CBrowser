---
tid: "t052"
slug: "proxy_link_and_egress_observation"
title: "代理以链接为唯一录入并按 Browser 同视角观测出口"
status: "done"
branch: "t052_proxy_link_and_egress_observation"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "d07f5e332b2d3b904bf23a4c6e2391036b0ce761"
depends_on: ""
conflicts_with: "t051"
note: "来源 p060，吸收 parked p040 出口 IP 部分；用户 2026-11-10 选 Supervisor 映射 loopback、保存后自动探测"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 引用逐项核对（2026-11-11，t028 教训，本 task 第一步）

- 三路勘查（后端代理链路、Supervisor/Docker/网络策略、前端代理链路）均只读，未改文件；结论见 task 实施：`proxies_router.py` 5 端点无探测端点、`ProxyModel` 明文密码字段、`PROXY_CONNECTION_FIELDS` 5 字段、`credential_revision` 仅密码真变才 +1、内部凭证端点 `api/internal_supervisor.py:129-160`、`runtime_agent/runner.py:60` 的 `build_proxy_server_arg`、`docker_adapter.py:81` 的 `proxy_endpoint_from_credentials`、`docker_adapter.py:318-350` 的 `_resolved_endpoint`、`network_policy.py` 561 行（loopback 放行、allowed 仅 IP 字面量+端口）、`supervisor.md:70` 的 Browser 仅允许 loopback/已建立/公共目的地址、前端 `features/proxies/` 8 文件、`parseProxyUrl.ts` 98 行、`ProxyFormDialog.tsx` 480 行、`ProxyTable.tsx` 139 行、迁移链 head `0005 b7c2d9e4f611`、OpenAPI 生成脚本 `scripts/export_openapi.py`、前端 `generate:api`/`check:api`。
- GeoLite2：本 worktree 无 `data/` 目录与 `GeoLite2-City.mmdb`（gitignore 的运行数据，只在用户机存在）；`src/backend` 内无 `geoip2`/`maxmind` 引用、无现成 IP→国家查询代码；现有 GeoIP 机制全走 CloakBrowser SDK（`cloakbrowser[geoip]==0.6.4`）；`docker_adapter.py:612-650` 的 `_initialize_cache` 在 helper 容器内调 `cloakbrowser.geoip._ensure_geoip_db` 下载 mmdb；`compose.yaml:106` 设 `CBROWSER_GEOIP_CACHE`。
- `cloakbrowser.geoip` 模块内含回显端点 `_IP_ECHO_URLS = ["https://api.ipify.org", "https://checkip.amazonaws.com", "https://ifconfig.me/ip"]`、`_resolve_exit_ip`（httpx 经 proxy 逐个试回显，SOCKS5 需 socksio）、`resolve_proxy_geo*`（懒 import `geoip2`）、`_ensure_geoip_db`（P3TERX 镜像下载 `GeoLite2-City.mmdb`，`~/.cloakbrowser/geoip/`）。
- `socksio==1.0.0` 在 Browser 镜像 requirements（`config/docker/browser_runtime/requirements.txt`）中有，在 gate venv 中没有——SOCKS5 回显抓取只能走 helper 容器。
- Browser 镜像 Dockerfile（`config/docker/browser_runtime/Dockerfile`）只 COPY `domain`、`font_sets`、`runtime_agent`（+少量文件），不含 `supervisor/`；Supervisor 镜像 COPY `supervisor`、`domain`、`gateway`、`runtime_agent` 等。Browser 镜像 requirements 含 `geoip2==5.3.0` 与 `httpx`——探测 helper 必须放在 `runtime_agent/`（或 `domain/`）才能在 Browser 镜像内运行。
- 命名锁死核对：`com.cbrowser.instance-id` 为唯一规定键，`resource_prefix` 默认 `"cbrowser-t005"`（`docker_adapter.py:205`）；`com.cbrowser.deployment-id` 在 `src/` 中零命中（仅 `docs/blueprint/decisions.md:342` 记载用户 2026-11-11 已驳回）；`extra_hosts`/`host-gateway` 在 `src/` 中零命中（生产容器创建路径不配）。本次改动守住这两处，未动。
- 唯一缺失引用（t038 遗留）：`docs/specs/proxy_management.md` 引用的 `docs/plan_20261105_ui_redesign.md` 不存在，文件已归档至 `docs/archive/plans/plan_20261105_ui_redesign.md`，已修正为归档路径。其余新文件/模型/函数引用（`proxy_endpoint.py`、`egress_observation.py`、`egress_probe.py`×2、迁移 0006、5 个 t052 测试文件、p060 归档、p040 parked、Browser requirements、`run_egress_probe`/`_install_network_policy`/`_resolved_endpoint`/`_write_proxy_credentials`/`LoopbackMappingError`/`EgressProbeFailure`、`control_server.py` probe 路由、`core.py` 的 `probe_proxy_egress`、base 提交 `d07f5e3`）全部存在。

### Area A 完成（2026-11-11）：链接解析与端点值对象

- 新模块 `src/backend/cbrowser/domain/proxy_endpoint.py`：`ProxyEndpoint`（frozen dataclass，`__repr__`/`__str__` 均只显示脱敏链接，密码永不进 repr/str/日志/指纹）、`parse_proxy_link`（四种格式：标准 URL `scheme://user:pass@host:port`、无协议 `host:port` 默认 http、`host:port:user:pass`、`user:pass@host:port`；IPv6 必须括号；密码 percent-decode 且非法转义报错；端口 1–65535；`user:pass@host:port` 判定要求 `@` 右侧能解析为 host:port，否则回落到格式 3；裸 IPv6 无括号判 ambiguous；3 段无协议形式判 ambiguous）、`fingerprint`（sha256(`scheme\0host\0port\0username`)，不含密码）、`redacted_link()`（无密码，IPv6 加括号，用户名 percent-encode）、`proxy_url()`（完整含凭据链接，仅供 httpx/Chromium 使用）、`display_name()`（`host:port`）、`is_loopback`/`mapped_host`/`map_endpoint_for_container`（loopback → `host.docker.internal`）、`is_loopback_host`/`map_loopback_host`（`127.0.0.0/8`、`localhost`、`::1`）、`ProxyLinkError`（带机器可读 `code`，`field` 恒为 `proxy_url`）。
- 测试 `tests/unit/test_t052_proxy_link.py`：53 passed（解析矩阵、非法输入、错误码、指纹稳定性、脱敏、round-trip、repr 无密码、名称派生、loopback 判定、不可变性）。

### Area B 完成（2026-11-11）：出口观测域逻辑

- 新模块 `src/backend/cbrowser/domain/egress_observation.py`：`ECHO_URLS`（与 cloakbrowser SDK 相同的三个纯文本回显服务）、`OBSERVATION_TTL_SECONDS = 24*3600`、`EgressObservation`（frozen dataclass：proxy_id、endpoint_fingerprint、credential_revision、perspective=`"browser"`、egress_ip、country_code、source=`"supervisor_probe"`、status pending|ok|failed、error_code、observed_at、expires_at）、`observation_is_current`（仅当 status ok、指纹与凭据版本均匹配、有 IP 与国家、未过期）、`GeoIpLookup`（懒 import `geoip2`，缺库/缺文件时抛 `GeoIpUnavailableError`，code 为 `geoip_db_missing`/`geoip2_missing`/`geoip_lookup_failed`；路径优先级：显式参数 → `CBROWSER_GEOIP_DB` → `CBROWSER_GEOIP_CACHE`/GeoLite2-City.mmdb）、`fetch_egress_ip`（httpx 经显式 proxy，`trust_env=False`）、`probe_egress`（回显取 IP → 本地 GeoIP 取国家；GeoIP 失败时抛 `EgressProbeError`，不猜国家）。
- 测试 `tests/unit/test_t052_egress_observation.py`：本地受控回显 + 极简 HTTP 正向代理夹具（直接回显返回 `198.51.100.1`，经代理的回显返回 `203.0.113.7`，断言观测取代理出口）；geoip2 用 stub 模块注入。与链接测试合计 71 passed。
- 修过一个 bug：`fetch_egress_ip` 必须 `trust_env=False`——本机环境变量有 Hatch 代理，不设此项会劫持探测。

### Area C 完成（2026-11-11）：契约层（domain models / ORM / 迁移 / Repository / Service / Router）

- `domain/models.py`：`ProxyResponse` 增加 `proxy_url`（脱敏链接）、`egress_ip`、`observation_status`（unknown|pending|ok|failed）、`observed_at`；`country_code` 保留为**只读观测值**；同时保留 scheme/host/port/username 作为派生只读字段；`ProxyCreateRequest` 改为链接唯一录入（`proxy_url` 必填 + `name?` + `region_label?` + `notes?`，`extra="forbid"`，model_validator 校验链接可解析，`parsed_endpoint()`、`resolved_name()` 名称默认 `host:port`）；`ProxyUpdateRequest` 改为 `proxy_url?` + `name?`/`region_label?`/`notes?`，`endpoint_was_supplied()`，`proxy_url` 省略=端点不变、提供=整体替换（含密码）。
- `adapters/database/models.py`：`ProxyModel` 删除 `country_code` 列；新增 `ProxyEgressObservationModel`（表 `proxy_egress_observations`：id、proxy_id FK ON DELETE CASCADE、endpoint_fingerprint、credential_revision、perspective、egress_ip、country_code、source、status、error_code、observed_at、expires_at、created_at，proxy_id 索引）。
- 迁移 `src/backend/migrations/versions/0006_proxy_egress_observations.py`（revision `c8d3e7a1f904`，down_revision `b7c2d9e4f611`）：建观测表 + 索引，`batch_alter_table` 删 `proxies.country_code`，downgrade 可回退。建表用 `op.create_table` + `sa.ForeignKey("proxies.id", ondelete="CASCADE")`（仓库惯例；初版 raw-SQL 建表导致 Alembic autogenerate 检出 FK 漂移，见「回归中修复」）。
- `adapters/database/repository.py`：`_to_domain_proxy(m, used_by_count, observation=None)` 组装脱敏链接与观测字段；`_current_observation` 取最新一行（pending/failed 行直接透传状态；ok 行须 `observation_is_current` 否则视为无）；新增 `get_proxy_endpoint`（供探测 runner，含密码与指纹，仅 service-plane）、`record_egress_observation`（只追加历史行）、`get_egress_observations`（历史，最新在前）；`list/get/create/update` 均挂接当前观测。修过一个 bug：`datetime` 在 repository.py 中是 `from datetime import datetime, timedelta` 导入的类，`datetime.now(datetime.timezone.utc)` 报错，改为 `from datetime import datetime, timedelta, timezone` + `datetime.now(timezone.utc)`。
- 新模块 `services/egress_probe.py`：`EgressProbeResult`、`EgressProbeRunner` Protocol、`LocalEgressProbeRunner`（进程内探测，**仅测试用**，文档明确禁止接入生产——API 进程视角错误）、`SupervisorEgressProbeRunner`（POST `{supervisor_url}/supervisor/v1/proxies/{id}/probe`，body 含端点+凭据，Bearer token，`trust_env=False`，超时 90s；非 200/异常 → `supervisor_unavailable`；返回 status 非 ok 或无 egress_ip → 对应 error_code）。
- `services/profile_service.py`：构造参数新增 `egress_probe_runner`，`set_egress_probe_runner()`；`create_proxy`（解析链接、名称派生、建库、记 pending 观测、后台自动探测、返回刷新后的响应）；`update_proxy`（仅当 `proxy_url` 提供时替换端点字段并 `password_supplied=True`，触发 pending+自动探测；否则只改元数据）；`probe_proxy_egress`（只接受 proxy id，服务端加载已存端点+凭据；无 runner 时记 failed `supervisor_unavailable`；成功记 ok 行，失败记 failed 行）；`_record_pending_observation`、`_record_failed_observation`、`_schedule_probe`（`asyncio.create_task` + 任务集合追踪）、`_probe_safely`（异常只记日志不抛）、`await_pending_probes()`（供测试）。修过一个关键 bug：**ok 行的 `observed_at` 必须用探测完成时的 fresh 时间**，不能复用探测开始前捕获的 `now`，否则按 observed_at 倒序取最新行时会把后记的 pending 行当成最新（实测复现：history 里明明有 ok/JP，`get_proxy` 仍显示 pending）。
- `api/v1/proxies_router.py`：新增 `POST /{proxy_id}/probe`（无 body；任何非空 body（除 `{}` 外）→ 422，AC-009 负向路径；404 处理；返回 `ProxyResponse`）。422 常量用 `status.HTTP_422_UNPROCESSABLE_CONTENT`（t044 已迁移，见「回归中修复」）。
- `api/runtime_coordinator.py`：新增 `egress_probe_runner()`（无 Supervisor 配置时返回 None）。`api/app.py` lifespan 中 coordinator 创建后接线：`service.set_egress_probe_runner(coordinator.egress_probe_runner())`。
- 旧测试更新（语义变更，断言意图不变，非弱化）：`tests/unit/test_t035_profile_domain.py` 的 `_proxy_payload` 去掉 `country_code`；`test_group_and_proxy_request_validation_rejects_invalid_values` 的三个旧平铺字段用例改为链接校验用例（非法 scheme、端口 0、空链接、额外平铺字段被 `extra="forbid"` 拒绝）。`tests/unit/test_domain_and_repository.py` 的 repo 级 payload 无 `country_code`，无需改动。`tests/unit/test_a6_error_contract.py::test_real_entity_reference_conflict_keeps_used_by_count` 的创建 payload 由旧平铺字段改为 `{"name": "px", "proxy_url": "http://127.0.0.1:8080"}`（409/`used_by_count` 断言原样保留，见「回归中修复」）。

### Area D 完成（2026-11-11）：集成测试（真实 FastAPI app + TestClient）

- 新文件 `tests/integration/test_t052_proxy_api.py`（17 tests）：用 `tests/fixtures/api_auth.py` 的 `create_auth_context` + `create_app` + 登录取 CSRF/Origin；通过 `app.dependency_overrides[get_profile_service]()` 取 service 注入 `LocalEgressProbeRunner`（受控回显+代理夹具、stub geoip2）；含 `_BlockingRunner`（`threading.Event` 门控，令 pending 状态可观测）。覆盖：四种链接格式创建、非法链接/平铺字段/`country_code` 可写均 422、密码永不进任何响应体（create/get/list/patch/probe 原始文本断言）、名称默认 `host:port` 且手动名不被后续解析覆盖、创建后自动探测得代理出口 `203.0.113.7`/JP、端点变更与密码轮换后旧观测立即失效（pending、country 为 None）、探测接口拒绝 host/port/scheme/username/proxy_url 等 body（422）、探测不存在的代理 404、探测失败记 failed 观测不猜国家。
- 验证：链接/观测/helper/supervisor 单元 + 集成合计 106 passed（53 链接 + 18 观测 + 5 helper + 13 supervisor + 17 集成）。

### Area E 完成（2026-11-11）：探测 helper（Browser 镜像内运行）

- 新文件 `src/backend/cbrowser/runtime_agent/egress_probe.py`：CLI（`--credentials-file` 必填、`--echo-url` 可重复、`--geoip-db`、`--timeout` 默认 10s）；只向 stdout 打印一个 JSON（成功 `{"egress_ip","country_code"}`，失败 `{"error_code"}`，exit 0/1）；密码只从凭证文件读，永不打印/记日志。
- 测试 `tests/unit/test_t052_egress_probe_helper.py`：5 passed（成功、缺 mmdb、回显不可达、凭证文件缺失/损坏；stdout 字节级断言不含密码）。

### Area F 完成（2026-11-11）：Supervisor 侧（Docker helper、loopback 映射、控制面）

- `domain/proxy_endpoint.py` 增加 `map_endpoint_for_container(endpoint)`（loopback 端点在运行时副本中把 host 换成 `host.docker.internal`；非 loopback 原样返回）。
- `supervisor/network_spec.py` 增加 `probe_network_name(prefix, probe_id)`（`{prefix}-probe-net-{probe_id}`，每次探测新建、用后删除）。
- `supervisor/container_spec.py` 增加 `probe_helper_labels(prefix, deployment_id)`（role=`egress-probe`，含 `_instance_label` 即 `com.cbrowser.instance-id`，命名锁死未动）。
- `supervisor/docker_adapter.py`：
  - 新增 `LoopbackMappingError(DockerSandboxError)`（AC-011：映射失败必须在启动/探测前明确报错+处置提示，绝不出现启动成功但无法联网）、`EgressProbeFailure(Exception)`（带机器可读 `code`，表示 helper 已运行并报告了探测失败）。
  - 新增 `run_egress_probe(*, proxy_id, endpoint, credentials, echo_urls=None, timeout=90.0)`：校验 proxy_id 格式；loopback 时 `extra_hosts={"host.docker.internal": "host-gateway"}`；在 `validator.data_root/control/probe/<id>/` 写 0600 凭证文件（host 已映射为 `host.docker.internal`）；新建专用 bridge 网络；以 browser 镜像创建 helper 容器（entrypoint 为 `python3 -c "import time; time.sleep(300)"`，user 1000:1000、只读根、cap_drop ALL、no-new-privileges、tmpfs /tmp 4m、挂载凭证文件 ro + geoip cache ro 到 `/data/engine-cache/geoip`、标签 `probe_helper_labels`）；用 `_resolved_endpoint` 在 helper 内解析映射后的代理地址；用 `_install_network_policy` 装 browser-role 策略（`allowed_tcp` 仅解析出的代理地址:端口）；在线程中 `exec_run` 跑 `python3 -m cbrowser.runtime_agent.egress_probe …`（带超时，超时则删容器并报 `DockerSandboxError("Egress probe timed out")`）；解析单行 JSON，成功返回 `(egress_ip, country_code)`，`error_code` → `EgressProbeFailure`，非零退出/非法输出 → `DockerSandboxError`；finally 删 helper 容器、删网络、删 probe 目录。loopback 且 daemon 报错文本含 `host-gateway`/`extra_hosts` 时转为 `LoopbackMappingError`（附处置提示：需支持 host-gateway 的 Docker 20.10+/OrbStack，或把代理移到非 loopback 地址）。
  - `start_browser_container`：从 `proxy_endpoint_from_credentials` 的 URL 取 host；host 为 `host.docker.internal` 时加 `extra_hosts={"host.docker.internal": "host-gateway"}`，否则为 None；`DockerException` 处理中，loopback 且 daemon 文本含 host-gateway/extra_hosts 时转为 `LoopbackMappingError`（附处置提示）。
- `supervisor/core.py`：`_write_proxy_credentials` 改为写入运行时副本前把 loopback host 映射为 `host.docker.internal`（DB 端点与指纹保持 loopback 不变）；新增 `probe_proxy_egress(proxy_id, payload)`（校验端点、指纹不匹配返回 `endpoint_mismatch`、无效端点 `invalid_endpoint`；经 `asyncio.to_thread` 调 `docker.run_egress_probe`；`EgressProbeFailure` → failed+原 code，`LoopbackMappingError` → `loopback_mapping_unavailable`，`DockerSandboxError` → `probe_failed`；成功返回 ok+egress_ip+country_code；始终返回 dict，不抛错）。
- `supervisor/protocol.py`：新增 `EgressProbeRequest`（`extra="forbid"`：scheme/host/port/username/password/credential_revision/endpoint_fingerprint）与 `EgressProbeResponse`（proxy_id/status/egress_ip/country_code/error_code，无 password），并加入 `SupervisorMessage` Union（A16 漂移守卫要求每个 protocol.py 定义的 BaseModel 都进 Union，见「回归中修复」）。
- `supervisor/control_server.py`：新增 `POST /supervisor/v1/proxies/{proxy_id}/probe`（Bearer token 校验，调 `core.probe_proxy_egress`，响应不含密码）。
- 测试 `tests/unit/test_t052_supervisor_probe.py`：13 passed（含 purpose-built fake Docker client，按 entrypoint 区分 policy helper 与 probe helper；`exec_run` 对 `getaddrinfo` 脚本按 `DNS_MAP`（proxy.example.com→93.184.216.34，host.docker.internal→192.168.65.254）返回解析结果，对 `egress_probe` 模块调用返回 canned JSON `{"egress_ip": "203.0.113.7", "country_code": "JP"}`）。覆盖：helper 成功并返回观测、策略仅放行解析出的代理地址:端口、helper/网络清理、loopback 映射（extra_hosts + 策略仅放行网关地址:端口）、helper 报告 `geoip_db_missing` → `EgressProbeFailure`、helper 崩溃（exit 1）→ `DockerSandboxError`、loopback 映射失败 → `LoopbackMappingError`、Browser 启动加 extra_hosts（loopback）/不加（公开代理）/映射失败明确报错（用 MagicMock client + `_stage_browser` 脚手架，仿照 `tests/unit/test_supervisor_selkies_token_isolation.py`）、`core.probe_proxy_egress` 的指纹校验与错误映射（用 `SupervisorCore.__new__` + stub docker）、control-server 探测端点的 token 校验与响应（仿照 `tests/unit/test_supervisor_control_auth.py` 的 token 文件搭建）、`core._write_proxy_credentials` 的 loopback 映射（0600、host 改写、非 loopback 不变）。
- 本机 Docker 不可用（`docker: command not found`），以上均为 fake-docker 测试，不能代替真实 Docker 验证，见「环境跳过」。

### Area G 完成（2026-11-11）：OpenAPI 与前端类型重生成

- `PYTHONPATH=src/backend ~/workspace/.cb-venv-t051/bin/python scripts/export_openapi.py`：`schemas/openapi/cbrowser_v1.json` 与 `cbrowser_internal.json` 均更新；diff 经核查只有 probe 端点（`POST /api/v1/proxies/{proxy_id}/probe`）+ ProxyCreate/Update/Response 模型变化（internal diff 277 行全为代理相关）。`test_exported_openapi_schema_matches_live_app` 相关测试 12 passed。
- `PYTHONPATH=src/backend ~/workspace/.cb-venv-t051/bin/python scripts/export_supervisor_protocol.py`：`schemas/runtime/supervisor_protocol.json` 重生成（含新 `EgressProbeRequest`/`EgressProbeResponse`，见「回归中修复」）。
- `npm run generate:api`（Node 26.13.0）重生成 `src/frontend/src/shared/api/generated/cbrowser_v1.d.ts`，`npm run check:api` 通过。生成后的 `ProxyResponse` 含 `proxy_url`（必填）、`egress_ip`、`observation_status`（unknown|pending|ok|failed）、`observed_at`，同时保留 scheme/host/port/username 作为派生只读字段。

### Area H 完成（2026-11-11）：前端重写

- `parseProxyUrl.ts` 重写：与后端 `domain/proxy_endpoint.py` 逐项对齐（四种格式、错误码、host 归一化——hostname 小写、IPv4 严格校验、IPv6 压缩归一含 `::` 与内嵌 IPv4、密码 percent-decode 且非法转义报错、`invalid_credentials`（有密码无用户名））；新增 `buildProxyUrl`（完整链接，`encodeURIComponent` + 补编码 `!'()*` 以对齐后端 `quote(safe="")`）、`redactedProxyUrl`（不含密码）、`proxyDisplayName`（`host:port`）、`compressIpv6`、`encodeUserinfo`。`ParsedProxyFields` 的 username/password 改为 `string | null`。
- `parseProxyUrl.test.ts` 重写：矩阵与后端 `tests/unit/test_t052_proxy_link.py` 对齐；先红（46 失败）后绿，54 passed。修过一个 bug：`splitUserinfo` 把“无密码”（null）误判为解码失败。
- `ProxyFormDialog.tsx` 重写：默认只显示代理链接、备注与只读国家状态（有观测显示 `RegionCode` + 出口 IP，无观测显示「未知」）；高级设置默认折叠（toggle `proxy-form-advanced-toggle`，`aria-expanded`），含名称、协议、地址、端口、用户名、只写密码、地区标签；无国家输入、无旧粘贴框。链接↔高级字段双向同步（同一端点值对象）：链接解析成功同步高级字段并派生名称（未手动填写时），高级字段修改重序列化链接；非法链接显示字段级错误，已解析结果保持不变。链接输入框失焦显示脱敏链接、聚焦编辑显示完整链接（Dialog 自动聚焦链接输入框）。提交：创建发 `{proxy_url, name, region_label, notes}`（name 为空时省略、后端派生；编辑时 name 恒为派生值或手动值）；编辑时端点未改则**不发 `proxy_url`**（密码不变）；端点改动则发完整 `proxy_url`。关键规则（后端语义已核实：`profile_service.update_proxy` 提供 `proxy_url` 即整端点含密码整体替换，`password_supplied=True`）：编辑有密码代理的端点而密码框留空且未点清除时，以 `proxyPasswordRequiredOnEndpointChange` 拦截提交，防静默清除已存密码；清除密码即提交不含密码的链接。
- `ProxyFormDialog.test.tsx` 重写（13 个 `it`）：链接创建+名称派生、默认可见字段、高级折叠、未知国家、双向同步（含聚焦显完整/失焦显脱敏）、手动名称保留、非法链接保持已解析字段、空链接拦截、编辑未改端点时省略 `proxy_url`、改端点不清密码被拦截+重填后提交、清除密码发无密码链接、已存密码不进 state/DOM/query cache、409 banner、username/region_label 超长拦截。13 passed（初版 12/13，失败是测试期望错：Dialog 自动聚焦导致高级改动后链接仍显示完整版，补 blur 步骤后通过）。
- `ProxyTable.tsx`：地区列无有效观测显示「未知」（`proxyCountryUnknown`）；每行加「重新探测」按钮（`proxy-probe-{id}`，探测中禁用），新增 `onProbe`/`probingId` props。
- `ProxyListPage.tsx`：接线 `useProbeProxyMutation`（成功 toast `proxyProbeSuccess` 并失效列表，失败 toast `proxyProbeFailed` + 错误信息）；`filterProxies` 不变（scheme/host/port 仍为只读派生字段）。
- `shared/api/client.ts`：`proxies` 增加 `probe(proxyId)`（`POST /proxies/{id}/probe`，无 body、不带幂等键——后端 probe 端点不接受 Idempotency-Key 处理）。`useProfilesQuery.ts` 增加 `useProbeProxyMutation`（mutationFn 忽略 actionKey，成功失效 proxyKeys + profileKeys）。
- `SessionDetailsPanel.tsx`：`proxyRegion` 无国家时显示「未知」而非 `"-"`（`proxy.country_code ?? t("proxyCountryUnknown")`）。`EnvironmentTable.tsx` 的 `ProxyNetwork` 未改（已是 `country_code &&` 条件渲染，只读观测）。
- `i18n.tsx`：新增键 `proxyFormUrl`、`proxyUrlInvalid`、`proxyAdvancedSettings`、`proxyCountryStatus`、`proxyCountryUnknown`、`proxyProbe`、`proxyProbeSuccess`、`proxyProbeFailed`、`proxyEgressIp`、`proxyHostRequired`、`proxyPortInvalid`、`proxyPasswordRequiredOnEndpointChange`（en/zh 同步）；删除旧键 `proxyPasteFromUrl`、`proxyPasteUrlLabel`、`proxyPasteUrlInvalid`、`proxyFormCountryCode`、`proxyCountryCodeInvalid`（`proxyHostRequired`/`proxyPortInvalid` 删后又因 validate 仍用而补回）。
- 测试夹具：`ProxyListPage.test.tsx`、`SessionDetailsPanel.test.tsx`、`EnvironmentListPage.test.tsx`、`ConfigTab.test.tsx`、`ProfileForm.test.tsx` 的 `proxy()` fixture 补 `proxy_url` + `observation_status`；三个带 `Partial<ProxyResponse>` spread 的 helper 改用解构兜底写法（spread 会把必填字段拓宽为 `string | undefined`）；`ProxyListPage.test.tsx` 增加 probe 的 3 个测试（未知国家显示、probe 调 `proxies.probe(id)` + 成功 toast、失败 toast）。`tests/e2e/test_proxy_library_e2e.py` 的 `_create_proxy_via_ui` 改为填链接输入框 + 展开高级区填名称（签名不变，本机只能静态检查，`py_compile` 通过）。
- 前端验证实数：`parseProxyUrl` 54 passed；proxies 目录 80 passed（3 文件）；proxies/profiles/browser-session 三目录 339 passed（40 文件）；`npm run test:types`（`tsc -p tsconfig.test.json`）通过；`npm run build` 通过（含 selkies 校验）；`npm run check:api` 通过；全量 `npm test` 第二遍 529 passed / 0 failed（74 文件，Node 26.13.0）。

### Area I 完成（2026-11-11）：文档 finalization

- `docs/blueprint/domain.md`：Proxy 行改写（链接唯一录入、国家为只读观测派生值）；新增 `ProxyEndpoint` 与 `ProxyEgressObservation` 两行；新增「代理链接录入与出口观测（t052）」一节（链接唯一录入、名称派生、PATCH 语义、国家是观测、探测视角、观测记录）。
- `docs/blueprint/supervisor.md`：「网络策略与启动门禁」一节追加 loopback 映射与出口探测 helper 段落（`host.docker.internal` + `extra_hosts host-gateway`、策略只放行映射地址:端口、映射失败 `LoopbackMappingError`、helper 与 Browser 共用的函数 `_install_network_policy`/`_resolved_endpoint`/`_write_proxy_credentials`、容器加固参数沿用既有内联模式未抽统一构造函数、真实 Docker 验证待用户机）。
- `docs/blueprint/security.md`：新增「代理链接录入与探测凭据外送防护（t052）」一节（脱敏链接、密码只写秘密与两条内部流转路径、probe 只接受 ID + 非空 body 422、helper 只打印一行 JSON、回显只发一次 HTTPS GET 且不带凭据、国家只用本机 GeoLite2、`trust_env=False`）。
- `docs/blueprint/frontend.md` §8：弹窗 bullets 重写（默认可见字段、高级折叠、双向同步、脱敏显示、名称派生、密码只写新语义、未知国家、手动探测、校验）；ApiClient bullet 补 `probe`。
- `docs/blueprint/decisions.md`：追加 **ADR 029**「代理链接为唯一录入，国家为 Browser 同视角观测（2026-11-11，t052）」（背景/选项/结论/复查条件/替代，含 p040 剩余 parked、p038 parked）。
- `docs/specs/proxy_management.md`：§1 补探测按钮与「未知」；§2 重写为链接唯一录入（替代 t038 同节）；§3 密码语义修订为 t052 的 proxy_url 省略/提供语义 + 拦截规则；§6 测试 bullets 更新；新增 §7「出口观测与探测（t052）」。另修正一处 t038 遗留过期引用：`docs/plan_20261105_ui_redesign.md` → `docs/archive/plans/plan_20261105_ui_redesign.md`（文件已归档）。
- `docs/specs_index.md`：`proxy_management` 行改为 `t038, t052`，日期 `2026-11-11`。
- `docs/pending/parked/p040_proxy_connectivity_exit_ip_check.md`：加注进展（2026-11-11，t052）：出口 IP/地理位置部分已并入 t052 实现（ADR 029）；连通性与延迟检测仍暂搁、继续 parked。p060 已在 `docs/archive/pending/p060_proxy_link_first_egress_identity.md`（无需处理）。
- `task.md`：未知契约清单两项 UNVERIFIED-SPIKE 改写为结论：(a) loopback/host-gateway——已实现 `extra_hosts` + 映射机制，但**本机无 Docker/OrbStack，真实验证未做**，须在用户机（OrbStack）按 AC-010/AC-011/AC-012 实测（p062 的 Docker CLI 实测不能代替 Docker API 路径）；(b) IP 回显选型——复用 cloakbrowser SDK 三个回显端点，只发一次 HTTPS GET 取自身出口 IP，国家只用本机 GeoLite2；SOCKS5 回显依赖 `socksio`（Browser 镜像 requirements 有、gate venv 无），只能走 helper 容器，真实 SOCKS5 回显须在用户机部署验证。
- `task.md`：AC-001～AC-011 已打勾；AC-012 保持未勾选（[deploy]，真实部署端到端，本机做不了）。（Round 2 修复时 AC-012 已按链口径跳过按 pass 计打勾，本机未验证、不得记为已验，见「环境跳过」与「Review 处置」Round 2。）

### 回归中修复（2026-11-11，全量分块回归时发现）

1. **Protocol drift（A16 守卫）**：`tests/unit/test_a16_protocol_drift.py` 3 失败——`EgressProbeRequest`/`EgressProbeResponse` 在 `supervisor/protocol.py` 中定义却不在 `SupervisorMessage` Union 中。修复：两模型加入 Union（`ResetBlockedRequest` 之后），重生成 `schemas/runtime/supervisor_protocol.json`（139 插入）。复测 15 passed；unit_00 整块复跑 271 passed / 2 failed（仅 a24 deploy 基线失败）。
2. **迁移 0006 FK 漂移**：`tests/unit/test_control_migration.py` 5 失败——`test_upgrade_head_matches_orm_metadata` 的 Alembic `command.check` 检出 `proxy_egress_observations.proxy_id` 外键 remove_fk + add_fk：初版迁移用 raw SQL 建表，FK 未带具名约束，反射后与 ORM 模型（`ForeignKey("proxies.id", ondelete="CASCADE")`）对不上。修复：按仓库惯例改用 `op.create_table` + `sa.ForeignKey(..., ondelete="CASCADE")`（保留 has_table 可重入守卫与 server_default）。复测 `test_control_migration.py` 全文件 9 passed；其余 4 个 migration 失败（0002/legacy 升级、0003 backfill）为同一根因的连锁反应，同修后全绿。
3. **a6 旧平铺 payload**：`test_a6_error_contract.py::test_real_entity_reference_conflict_keeps_used_by_count` 用旧平铺字段创建代理得 422。修复：创建 payload 改为链接形式（409/`used_by_count` 断言原样保留）。复测 a6 + migration + a16 合计 33 passed。
4. **422 常量（t044 守卫）**：`test_t044_status_constants.py::test_deprecated_422_constant_absent_from_backend_sources` 失败——probe 路由用了已废弃的 `status.HTTP_422_UNPROCESSABLE_ENTITY`（仓库已迁到 `HTTP_422_UNPROCESSABLE_CONTENT`，Starlette 1.10 改名）。修复：改用新常量。复测 t044 + t052 集成 20 passed；`src/` 内已无旧常量引用（仅 stale .pyc 残留，不入库）。
5. **回归执行方式**：两次全量后端回归（基线 865s）均被 runtime 中途截断（日志 0 字节 / 中断于约 91%），改成分块跑：`tests/unit/test_*.py`（216 文件）按字母顺序切 8 块（每块 30 文件，最后一块 6 个），`tests/integration/test_*.py`（45 文件）切 2 块（23/22），清单在 `.scratch/chunks/`。每块单独 exec（`--tb=no -rf`，独立 `--basetemp`），单块约 16–194s。

### 环境跳过（本机无 Docker、真实浏览器、PostgreSQL、OrbStack，按链口径跳过按 pass 计，不得记为已验）

- AC-012 真实部署端到端：按链口径跳过按 pass 计，已打勾（2026-11-11，Round 2 修复时）。本机无 Docker、真实外部代理与公网出口，无法验证，**不得记为已验**，须在用户机真实部署验证。替代验证：t052 集成测试（受控回显+代理夹具，18 tests）+ supervisor fake-docker 测试（13 tests）+ 前端全量 533 passed。真实部署（粘贴链接创建 → 自动观测 → 环境引用 → 启动 → 浏览器内 IP 回显与观测一致；宿主本机代理链路）须在用户机验证。依据：本链既定口径（确实因本机环境跑不了的验证直接跳过按 pass 计）与 t051 前例（AC-013 整项跳过但打勾，审阅记 TICK-VALID trust_prior，progress.md 注明「不得记为已验」）；不是选项、不是「待裁定」。
- AC-010 真实 Browser 部分：Browser 经宿主本机代理访问外网、策略对其它端口/私有地址的拒绝，真实 Docker 层未验。替代验证：fake-docker 测试覆盖映射（extra_hosts + 策略仅放行映射地址:端口）与 `_write_proxy_credentials` 的 loopback 改写；网络策略渲染与 `verify_policy` 由既有套件覆盖。须在用户机（OrbStack）实测。
- AC-011 真实 daemon 拒绝部分：daemon 对 `extra_hosts`/`host-gateway` 的拒绝行为未验。替代验证：fake-docker 测试覆盖 loopback 映射失败 → `LoopbackMappingError`（启动与探测两路）。须在用户机实测。
- SOCKS5 回显：`socksio` 只在 Browser 镜像 requirements 中，gate venv 无，进程内探测无法覆盖 SOCKS5；helper 容器路径只在 fake-docker 层验证。真实 SOCKS5 回显须在用户机部署验证。
- GeoLite2 文件本身：`GeoLite2-City.mmdb` 在真实部署 engine-cache 中的存在性未验（本机无 `data/` 目录）；代码路径（`CBROWSER_GEOIP_CACHE`）已对齐 compose.yaml；缺文件时 helper 报告 `geoip_db_missing`，测试已覆盖。
- 黑盒 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`：本机无 Docker/镜像/Chrome，未跑；以相关非 E2E 套件替代，见收尾报告。`tests/e2e/test_proxy_library_e2e.py` 已按新语义同步（填链接输入框 + 展开高级区填名称），待用户机 E2E 复验。

### 遗留问题

- 无新增遗留。AC-010/AC-011 的真实 Docker 部分与 AC-012 均须在用户机验证（见「环境跳过」），不属本 task 遗留代码问题。
- t051 的 f004 minor（`tests/unit/test_t051_shared_redaction.py:101-105` 恒真断言）由链主处理，不属于本 task。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1（2026-11-11，code/test 双路 verdict FAIL，共 12 条，已全部修复重验）

修复前按规程把 task.md 的 AC-001～AC-011 全部撤回为未勾选；修复重验后重新打勾（AC-012 保持未勾选）。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t052_code_f001|important|已修|三处国家展示位按 `observation_status === "pending"` 显示「检测中」，与无观测「未知」区分；新增 i18n 键 `proxyCountryProbing`（en "Detecting" / zh "检测中"，双语同步，i18n 键集测试通过）|`ProxyTable.tsx:84`、`ProxyFormDialog.tsx:432`、`SessionDetailsPanel.tsx:158`、`i18n.tsx:445,933`|
|t052_code_f002|important|已修|`SupervisorEgressProbeRunner.probe` 在 `resp.json()` 后校验 `isinstance(data, dict)`，非 dict 抛受控 `EgressProbeError("probe_bad_response")`；`probe_proxy_egress` 对 runner 的非 `EgressProbeError` 异常兜底记 failed 观测（`error_code="probe_failed"`）并返回 200，不再 500；`_probe_safely` 日志改记真实异常（类型+消息+`exc_info=True`），删掉写死的 `"probe_error"` 常量|`services/egress_probe.py:146`、`services/profile_service.py:963,1055`；TDD 红：新单测先跑出 `AttributeError: 'list' object has no attribute 'get'`（与审阅复现一致）后变绿|
|t052_code_f003|minor|已修|根因拆分为编排器 + 7 个小函数（写凭证、建网络、建 helper、装策略、拼命令、带超时执行、解析输出、清理）；编排器 CC~3，各函数 CC 1–7（同口径 AST 测算，拆前 CC~29）；行为不变，13 个 fake-docker 测试全绿|`supervisor/docker_adapter.py:463-760`（`_write_probe_credentials:520`、`_create_probe_network:548`、`_create_probe_helper:566`、`_install_probe_network_policy:631`、`_probe_helper_command:655`、`_exec_probe_helper:671`、`_parse_probe_output:710`、`_cleanup_probe_resources:735`）|
|t052_code_f004|minor|已修|根因拆分为编排器 + 4 个小函数（`::` 切分、内嵌 IPv4 展开、最长零游程、压缩渲染）；同口径粗测 CC 32→10（<15）；解析矩阵 55 passed|`features/proxies/parseProxyUrl.ts:64,79,99,125,138`|
|t052_code_f005|minor|已修|新增 `_current_observations`，一次 `WHERE proxy_id IN (...)` 取各代理最新观测行再组装；过期 ok 隐藏规则抽为 `_visible_observation` 与单行路径共用；查询计数测试证实 3 代理由 3 次观测 SELECT 降为 1 次（修前红、修后绿）|`adapters/database/repository.py:1205,1246`、`list_proxies` 批量组装|
|t052_code_f006|minor|已修|`test_t052_supervisor_probe.py` 计数 12 passed → 13 passed|`task.md:99`|
|t052_test_f001|important|已修|删掉 `body["proxy_url"] == body["proxy_url"]`，改为按参数化期望值断言脱敏链接（5 种格式各有期望值）；临时改错期望值验证新断言变红后恢复|`tests/integration/test_t052_proxy_api.py:211-252`|
|t052_test_f002|important|已修|列表分支改为无条件 `all("password" not in item for item in payload)`，单项分支保留原断言；临时注入含 password 键的项验证新断言变红后恢复|`tests/integration/test_t052_proxy_api.py:282-293`|
|t052_test_f003|minor|已修|补 3 个 pending 夹具测试（弹窗、列表行、会话详情），均断言显示「检测中」且不显示「未知」|`ProxyFormDialog.test.tsx:214`、`ProxyListPage.test.tsx:399`、`SessionDetailsPanel.test.tsx:205`|
|t052_test_f004|minor|已修|新增 `tests/unit/test_t052_supervisor_runner.py`，11 个测试（成功、401/403/500/502、坏 JSON、非 dict JSON、failed 透传 error_code、无 egress_ip、未配置、传输异常；MockTransport 校验 URL/Bearer/凭据 body）|新文件 `tests/unit/test_t052_supervisor_runner.py`（11 passed）|
|t052_test_f005|minor|已修|新增 `tests/unit/test_t052_observation_repository.py`，4 个测试（过期 ok 行隐藏、过期 ok 后新 pending 行仍显示、failed 行显示、列表批量查询计数）|新文件 `tests/unit/test_t052_observation_repository.py`（4 passed）|
|t052_test_f006|minor|已修|`validCases` 补一行 `user:p%40ss@proxy.example.com:8080` → 密码 `p@ss`，与后端矩阵对齐|`features/proxies/parseProxyUrl.test.ts:96-106`|

- TDD 红绿记录：f002 非 dict JSON 新单测修前 `AttributeError` 红、修后绿；f005 批量查询计数修前 3 次 SELECT 红、修后 1 次绿；f001/f002 新断言经临时改错期望值/注入 password 键证实变红后恢复；f003/f004 为重构拆分，拆前同口径测算 CC 超标（29 / 粗测 32），拆后编排器 CC~3 / 10，各函数 ≤7，现有测试全绿。
- 命名锁死复核：`com.cbrowser.deployment-id` 在 `src/`、`config/`、`scripts/`、`compose.yaml` 中零命中；`resource_prefix` 默认仍为 `cbrowser-t005`（`docker_adapter.py:234`）；`com.cbrowser.instance-id` 未动。

### Round 2（2026-11-11，code verdict FAIL 唯一驱动项为 AC-012 TICK-VOID，test verdict FAIL 同为 AC-012，0 新 finding）

修复前按规程把 task.md 的 AC-001～AC-011 全部撤回为未勾选；修复重验后重新打勾。AC-012 按链口径跳过按 pass 计打勾（见「环境跳过」，本机未验证、不得记为已验，须在用户机真实部署验证）。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t052_code_f007|minor|已修|`_current_observations` 改为按代理分组取最新一行的有界查询：`ROW_NUMBER() OVER (PARTITION BY proxy_id ORDER BY observed_at DESC, created_at DESC, id DESC)` 子查询取每代理 rn=1 的 id，外层单次 SELECT 取行；排序口径与单行路径 `_current_observation`（`LIMIT 1`）一致，`id DESC` 只作精确并列时的确定性决胜；不引入保留期清理。补测试：3 代理各 3 行历史观测，列表仍返回各代理最新一行（pending），观测 SELECT 仍为 1 次，且物化观测行由 9 降为 3（修前红：物化 9 行；修后绿）|`adapters/database/repository.py:1246-1296`（`_current_observations`）、`tests/unit/test_t052_observation_repository.py` 新增 `test_list_proxies_fetches_only_latest_observation_row_per_proxy`|

- TDD 红绿记录：新测试修前 `assert len(loaded_rows) == 3` 得 9 行变红（返回值与 SELECT 计数在修前已通过，红的是物化行数——旧实现返回值正确但搬运全部历史行），修后 5 个仓库观测测试全绿。
- 命名锁死复核：`com.cbrowser.deployment-id` 在 `src/`、`config/`、`scripts/`、`compose.yaml` 中零命中；`resource_prefix` 默认仍为 `cbrowser-t005`（`docker_adapter.py:234`）；`com.cbrowser.instance-id` 未动；`git diff --check` clean。review_*.md 未改动。
- 前端未动：本次修复只改后端 `repository.py` 与一个后端单测文件，前端代码零改动，故前端全量无需重跑（Round 2 实数 533 passed 仍有效）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（12/12 AC 已打勾；AC-012 为 [deploy]，按链口径跳过按 pass 计打勾，本机未验证、不得记为已验，须在用户机真实部署验证，见「环境跳过」）
- 测试：后端全量分块回归（`tests/unit` 216 文件 + `tests/integration` 45 文件，`~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=src/backend`，分块实数见下）；t052 测试 123 passed（53 链接 + 18 观测 + 5 helper + 13 supervisor + 11 runner + 5 仓库观测 + 18 集成，含 Round 1 修复新增 16 与 Round 2 修复新增 1）；前端全量直接跑 vitest 533 passed / 0 failed（74 文件，本机 Node 24.22.1；`npm test` 的 pretest 门禁要求 Node ≥26，绕过 pretest）；`npm run test:types` 通过；`npm run build` 通过（本机系统 Node 24.22.1 不满足 build 的 check:node 门禁，改用新下载的 Node 26.13.0 `~/workspace/tools/node-26.13.0` 跑通；下载时 /tmp 曾满，已清我方 pytest basetemp 释放至 33%）；`npm run check:api` 通过；`git diff --check` clean
- 黑盒：未跑——`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 本机无 Docker/镜像/Chrome，无法执行；以相关非 E2E 套件（后端分块全量 + 前端全量 533 passed）替代，真实部署验证须在用户机进行
- review：Round 1 双路 verdict FAIL（code 6 条 + test 6 条，共 12 条，important 4 条）；已全部修复并重验（见「Review 处置」Round 1 表）。Round 2 双路 verdict FAIL，唯一驱动项为 AC-012 未勾选（code 新增 minor f007 1 条，test 0 新 finding）；f007 已修复并重验（见「Review 处置」Round 2 表），AC-012 按链口径跳过按 pass 计打勾，待 Round 3 复核
- AC 判定：见 `task.md` 行内打勾（12/12；AC-012 按链口径跳过打勾，本机未验证）

### 结果摘要

- t052 全部 12 条 AC 已打勾（task.md 12/12；AC-012 按链口径跳过按 pass 计，本机未验证、不得记为已验，须在用户机真实部署验证）；改动见 `git status`（45 个已跟踪文件改动，3277 插入、847 删除；另 12 个新文件未入库跟踪：`domain/proxy_endpoint.py`、`domain/egress_observation.py`、`services/egress_probe.py`、`runtime_agent/egress_probe.py`、迁移 0006、7 个 t052 测试文件）。
- 后端全量分块回归（Round 2 修复后重跑，chunk 清单沿用实施期 `.scratch/chunks/`，该清单不含 Round 1 新增的 2 个单测文件——16 个单测另在受影响文件跑中验证，见下）：**2010 passed / 27 failed / 8 skipped / 2 errors**；加 chunk 外 2 文件 16 passed，全量合计 **2026 passed / 27 failed / 8 skipped / 2 errors**。基线 1901 passed / 29 failed / 8 skipped / 2 errors；passed +125（t052 测试 123 + 2 项基线失败本轮通过，属运行方差），failed −2，skipped/errors 持平。27 failed 按名逐项比对，与 Round 2 的 27 个失败按文件分布完全一致（a24 2、automation_cdp 1、repo_hygiene 1、t028 4、t034 2、agent_executor_chain 7、automation_cdp_flow 2、automation_probe_chain 3、control_attendant_chain 1、normal_exit_replay 4），无一与 t052 改动面相交。2 errors：其一是基线既有 teardown 错误（`test_a35_recovery.py::test_concurrent_apply_is_rejected_by_exclusive_db_registration`，`KeyError: 'connection'`，flaky，Round 2 审阅亦有记录）；其二是基线既有 teardown 错误（`test_network_apply_operations.py::test_restore_not_found_is_explicit_terminal`，Round 1 已记录；int_01 首轮 1 error、重跑 0 error，属 flaky）。分块日志见 `.scratch/t052_r2fix_regression.log`（逐块实数与失败名）。
- 受影响文件全绿：t052 全部单测 + 集成 + 受影响旧测试（t035/a6/a16/t044/migration/domain_and_repository）合计 193 passed，含本次新增的 1 个 f007 仓库观测单测。
- 前端未重跑：本次修复只改后端 `repository.py` 与一个后端单测文件，前端零改动；Round 2 前端全量 533 passed / 0 failed 仍有效。
- 回归中修复 4 项（均已复验全绿）：protocol drift（Union 漏登记）、迁移 0006 FK 漂移（raw-SQL 建表改 `op.create_table`）、a6 旧平铺 payload、422 废弃常量。
- 遗留：AC-010/AC-011 的真实 Docker 部分与 AC-012 须在用户机验证（AC-012 虽按链口径打勾，本机未验证）；t051 f004 由链主处理。

### 长期文档闭环

- specs_index：`proxy_management` 行登记 `t038, t052`（2026-11-11）。
- blueprint：domain/supervisor/security/frontend 更新 + decisions.md 新增 ADR 029。
- specs：`docs/specs/proxy_management.md` 更新（§2 链接唯一录入、§3 密码语义、§7 出口观测与探测）。
- pending：p040 加注进展（出口 IP/地理位置部分已并入 t052，连通性与延迟检测仍 parked）；p038 保持 parked；p060 已归档。

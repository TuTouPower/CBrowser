# t074 真实部署、代理批量导入与 AC-006 补验（2026-11-17）

## 范围与授权

- 用户授权：重新部署、把 `../temp123/mihomo_proxy` 的 88 个真实节点通过 API 导入 CBrowser 代理管理、提交并 push。
- 部署前置按用户裁决选择「直接部署，仅用 `deploy.sh` 自带数据库单件备份」：未停止 `cbrowser-0021` Profile、未创建环境恢复点。
- 已知回退限制：0010 升版后 `rollback` 到 0009 release 会被文档规则拒绝（migration_version 不匹配）。

## 部署

|项|部署前|部署后|
|---|---|---|
|current release|`20261116015449-e88205a`|`20261117133551-8e1bd9b`|
|previous release|`20261115214648-406e3e5`|`20261117130835-8e1bd9b`|
|数据库 alembic stamp|`796adb0bf159`（0009）|`8c3f1d0a7b92`（0010）|
|health|`{"status":"ok"}`|`{"status":"ok"}`|

- 两次发布均 `deploy.sh deploy` exit 0、`readiness-verified`：首次 `20261117130835-8e1bd9b` 落地 t074 全部改动与 0010 迁移；二次 `20261117133551-8e1bd9b` 落地下述 Supervisor 响应字段修复。
- 0010 为 `proxy_egress_observations` 增加 `country_name` / `city` / `latency_ms` 三列，部署后容器内核验列存在。
- 数据库单件备份：`config/deploy/backups/cbrowser-20261117131040.db`、`cbrowser-20261117133809.db`。
- `cbrowser-0021-browser/stream`（已运行 39 小时）在两次发布中均未被重启，会话保持。

## 冒烟发现与修复

- 现象：首次部署后小规模试跑（21001 / 21002）的 `ok` 观测只有 `egress_ip` / `country_code`，`country_name` / `city` / `latency_ms` 全为 NULL。
- 根因：`supervisor/control_server.py` 的 `probe_proxy` 构造 `EgressProbeResponse` 时只传 5 个字段，漏传 t074 新增的 3 个；`core.probe_proxy_egress` 与 Browser helper 均已产出完整 dict。
- 修复：补齐 `country_name` / `city` / `latency_ms`；新增 `test_probe_response_exposes_full_observation_fields`，先红（断言 `country_name is None`）后绿。
- 验证：相关单测 35 passed；全量门禁 9 suite `all_passed=true`（`.scratch/deploy_t074/gate_evidence_fix/manifest.json`，`run_id=8f36602ef5d949b9b20354c17ac5050a`）；二次部署后重探 21001 得 `country_name=Japan` / `city=Tokyo` / `latency_ms=436`。

## 代理导入

- 源：`../temp123/mihomo_proxy/config/node_port_mapping.json`，其中 `single_node` 且端口 21000–21087 共 88 条；Mixed HTTP/SOCKS5，宿主机 `127.0.0.1:<port>`，loopback 端点由 Supervisor 映射为 `host.docker.internal`。
- 脚本：`scripts/import_mihomo_proxies.py`。从 `config/deploy/secrets/admin_password` 读管理员密码（不打印、不进命令行、不入库），登录取会话 Cookie + CSRF + Origin；按 `proxy_url` 幂等去重；每批 8 个并轮询探测收敛，避免 88 个 helper 容器并发压垮 daemon。
- 结果：`created=85` / `updated=1` / `skipped=2` / `failed=0` / `unsettled=0`。证据 `.scratch/deploy_t074/import_full.json` 与 `import_full.log`。

## AC-006 真实部署端到端补验

原 `p112`（`transferred`，转入部署阶段现场验收）所述内容已于本次在真实部署环境完成，归档条目结论保留原貌不改。

- 可用代理：88 个节点中 84 个 `ok`；`latency_ms` 418–7349 ms、中位 592 ms，仅 helper 内经代理的 HTTP 往返，不含容器/网络/策略建立与销毁；`country_name` 与 `city` 84/84 填充，覆盖 29 个国家码。
- 不可用代理：4 个节点 `failed` 且带结构化 `echo_unreachable`（非通用 `probe_failed`）；另建临时 `http://127.0.0.1:21999` → `failed` + `echo_unreachable`，验证 `exit_code=1` JSON 错误码透传与红色失败态，随后删除（204）。
- 刷新持久化：84 个 `ok` 代理间隔 4 秒两次 `GET /api/v1/proxies`，`observation_status` / `egress_ip` / `country_code` / `country_name` / `city` / `latency_ms` 全部稳定。
- 隔离边界：沿用 `docs/archive/spikes/s024_t074_lightweight_probe_isolation/` 的真实 Docker 容器原型结论（私有/保留地址 fail-closed、精确动态白名单、凭据不进 argv）；本次未重跑内核负例，如实记录，不冒充已验。
- 证据：`.scratch/deploy_t074/verification.json`、`verify.log`、`deploy.log`、`deploy_r2.log`、`gate_fix.log`。

## 剩余风险

- 0010 升版后现有两份 0009 release 的 `rollback` 会被拒绝；本次未创建环境恢复点，回退只剩数据库单件 `deploy.sh restore`，不覆盖 Profile 数据。
- 4 个节点当前不可达（`echo_unreachable`），属真实代理网络状况，非代码缺陷。
- 最大延迟 7349 ms 来自个别真实节点慢响应，不是容器建毁开销（该开销已从计时口径剥离）。

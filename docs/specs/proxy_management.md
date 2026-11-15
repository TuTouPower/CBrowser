# 代理库界面

需求级 spec，累积 t038、t052、t065 及单用户代理界面精简与测速重构。权威交互与视觉约束见 `DESIGN.md` 与 `docs/blueprint/frontend.md` 第 8 节；后端代理 API 契约见 `docs/specs/profile_management.md`（t035 分组库 / 代理库 / 配置版本三分）。本文定义界面行为契约。

## 1. 列表、卡片视图与测速（t038，t052+）

- `/proxies` 代理管理页面支持列表（6 列）与卡片网格两种视图，由工具栏右侧图标按钮切换：列表列包含名称（备注以感叹号图标悬浮 Tooltip 展示）、协议、地址（`host:port`，mono）、位置（国家码 + 地区标签 + 可用性与延迟徽标，无有效观测时显示「未知」）、使用环境数、操作（闪电测速 / 编辑 / 删除图标按钮）。**不展示「认证」列**，避免向用户暴露冗余认证方式细节。
- 工具栏：搜索（名称、host、地区标签，大小写不敏感）、协议筛选（http / https / socks5 / 全部协议）、位置筛选（按国家码或地区标签过滤）、右上角批量闪电测速按钮（`Zap` 图标，一键测试当前列表全部代理可用性与延迟）、列表/卡片图标切换器、主按钮「添加代理」。搜索、协议筛选与位置筛选可自由组合；结果随输入即时更新；全量客户端过滤、无分页。
- 空列表显示空状态。每视图最多一个主按钮。
- 单行/单卡片闪电测速按钮（`Zap` 图标）调用 `POST /api/v1/proxies/{id}/probe`（只接受代理 ID，无 body），记录测速耗时并展示「可用 · XXms」状态徽标，成功 toast 提示测速完成并刷新列表，失败 toast 提示测速失败与错误信息。

## 2. 添加 / 编辑（t052，替代 t038 同节）

- 默认只显示「代理链接」「备注」与只读位置状态（有有效观测显示国家码 + 出口 IP，无有效观测显示「未知」）；高级设置默认折叠，展开后可编辑名称、协议、地址、端口、用户名、只写密码、地区标签；**没有国家输入**。
- 链接是唯一录入：`ProxyCreateRequest.proxy_url` / `ProxyUpdateRequest.proxy_url`。四种格式：标准 URL `scheme://user:pass@host:port`、无协议 `host:port`（默认 http）、`host:port:user:pass`、`user:pass@host:port`；scheme 白名单、IPv6 必须括号、端口 1..65535、密码 percent-decode 且非法转义报错。解析器与后端 `domain/proxy_endpoint.py` 逐项对齐（错误码一致），前端实现见 `features/proxies/parseProxyUrl.ts`。
- 链接与高级字段双向同步、始终一致：链接解析成功即同步高级字段，高级字段修改即重序列化链接。非法链接显示字段级错误，**已解析结果保持不变**。链接输入框失焦时显示脱敏链接（不含密码），聚焦编辑时显示完整链接。
- 名称未手动填写时由 `host:port`（IPv6 加括号）派生；手动修改后不被后续解析覆盖。创建时 name 为空则省略该键，后端派生。
- 校验与后端一致：链接可解析、name ≤ 255、username / region_label ≤ 255、port 1..65535 整数。错误在对应字段旁显示，底部有汇总；校验不过不提交。
- 保存成功后代理列表即时更新；改连接字段会使 Profile 列表失效（后端生成新配置版本）。
- 旧「从 URL 粘贴」框与国家输入已删除；旧平铺字段（scheme/host/port/username/password/country_code）不再作为请求字段，`extra="forbid"` 下一律 422。

## 3. 密码只写（t038，t052 修订）

- `ProxyResponse` 不含 password；编辑态只凭 `has_password` 布尔显示「已设置，留空不修改」，并提供「清除密码」。
- 提交语义（t052）：`proxy_url` 省略 = 端点（含密码）不变；提供 = 整端点（含密码）整体替换。编辑端点而密码框留空且未点清除时，前端拦截提交并提示须重填密码或清除密码（否则会静默清除已存密码）；清除密码即提交不含密码的链接。
- 已保存的密码绝不出现在前端表单 state、react-query 查询缓存、DOM 与 URL；弹窗关闭清空本地 state。
- 密码只进一次请求体，不进日志、不回显。

## 4. 删除与被引用保护（t038）

- `used_by_count > 0` 时代理删除按钮禁用并提示先改绑。
- 后端删除返回 409 时响应体为统一 `ErrorResponse`：`{"error":"proxy_in_use","message":"Conflict","details":{"used_by_count":N},"retryable":false}`；前端以 `errorCode === "proxy_in_use"` 判码、从 `ApiError.details` 取引用数并展示。
- 使用环境数为链接，跳 `/?proxy=<id>`；环境列表的 `useEnvironmentFilters` 已支持 `proxy` URL 参数按代理筛选。

## 5. 带认证 SOCKS5（t038 / AC-007）

- 依据 `docs/findings/d031_authenticated_socks5_supported.md`、spike s013 报告与 ADR 023（`docs/blueprint/decisions.md:280`）：CloakBrowser 0.6.4 / Chromium 146 **支持**带认证 SOCKS5；`src/backend` **不存在任何 socks5 拒绝分支**，API 永远不会返回该 422（`proxies_router.py` 的 409 仅 `proxy_in_use` / `proxy_name_in_use`）。
- 带认证 SOCKS5 为**直接支持**：表单默认允许 `socks5` + 用户名/密码提交，前端无阻止、**无降级路径、无「引擎不支持」提示**。任何 422 或其它后端错误统一走 `describeError()` 的结构化错误展示（`ApiError.details` / `.data`）。

## 6. 文案与测试（t038+）

- en / zh 文案键同步补入 `i18n.tsx`，键集相等与双语文案非空由 `i18n.test.tsx` 兜底。
- Vitest 在 ApiClient 边界注入每例独立 stub、走真实 hooks；链接解析用表驱动纯函数测试（与后端矩阵对齐）；页面测试覆盖 6 列展示（不含认证列）、搜索 + 协议 + 位置筛选组合、列表/卡片切换、密码不残留、409 引用数、使用环境数跳转、单条与批量闪电测速调用及 toast。
- 真实栈 E2E（无头 Chrome）覆盖「UI 新建代理 → 环境引用该代理 → 启动 → 浏览器出站经该代理」，用本地记录代理不依赖公网。

## 7. 出口观测与探测（t052）

- 国家码是观测，不是配置：`ProxyResponse.country_code` / `egress_ip` / `observation_status` / `observed_at` 由当前有效观测派生（status 为 ok、端点指纹与凭据版本均与现端点一致、未过期，TTL 24 小时）。无有效观测时全部展示位显示「未知」：代理列表位置列、代理弹窗只读位置状态、会话详情代理位置。
- 代理保存或端点 / 凭据变更后自动探测：先记 pending 行（界面显示测速中），后台探测完成后刷新为国家或未知；失败记 failed 行、不猜国家。端点指纹或凭据版本变化、观测过期时旧观测立即失效，不再显示旧国家，并自动重新探测。
- 探测在 Browser 同视角执行：Supervisor 的短生命周期 helper（Browser 镜像、browser-role 网络策略、0600 凭证文件）访问 IP 回显端点取出口 IP，本机 GeoLite2 判定国家；出口 IP 不发往第三方地理库。手动探测 `POST /api/v1/proxies/{id}/probe` 只接受代理 ID，任何非空请求体（除 `{}` 外）返回 422。
- 宿主本机端点（`127.0.0.0/8` / `localhost` / `::1`）由 Supervisor 映射为 `host.docker.internal` 并单端口放行；映射失败时启动与探测在执行前明确报错并给出处置提示，不出现启动成功但无法联网。
- 观测记录只追加历史行（`proxy_egress_observations`）；`GET /api/v1/proxies` 与单条响应均返回当前有效观测派生值。

## 8. 密码变更影响集、幂等与引用事件（t056）

- **密码变更只影响当前引用者（A17）**：改代理密码（或任一连接字段）时，只有当前配置引用该代理的 Profile 生成新配置版本；仅被运行中绑定版本引用（当前配置已改绑他处）的 Profile 不生成新版本，只收到运行事件。只改 name / region / notes 不生成新版本。绑定快照冻结的 `proxy_credential_revision` 取该快照实际引用的代理的当前修订；凭据变更后旧绑定版本重启按冻结修订校验、失败封闭 `proxy_credentials_changed`，应用新版本后启动成功。
- **分组与代理写操作幂等（A23）**：group / proxy 的 create / update / delete 支持 `Idempotency-Key` / `X-Operation-ID` / `operation_id`，与 Profile 同一审计语义（同一键 + 同一目标 + 同一载荷重放既有结果；键复用于不同目标 / 动作 / 载荷返回 409 `idempotency_conflict`）。重放不重复触发探测等副作用。`POST /groups/reorder` 不带幂等键。
- **引用变更事件（A31）**：分组或代理写成功后服务端经 SSE 推送 `groups_changed` / `proxies_changed`（`entity_id` 为变更实体、重排时为 null），前端使对应列表查询与 Profile 列表查询失效重取；手动探测不发事件。

## 9. 运行时凭据与 SDK 代理直连（ADR 037 / ADR 038）

- 凭据文件唯一为 `proxy_credentials.json`：Supervisor 写 Profile secret 目录（`data_root/runtime/.secrets/{profile_id}/proxy_credentials.json`，0600，chown runtime_uid:runtime_gid），字段 `{scheme,host,port,username,password,credential_revision}`；仅以只读 bind 挂进 Browser 容器 `/run/cbrowser/proxy_credentials.json`。升级前写在 runtime 目录的旧凭据文件在每次 `start_profile` 无条件删除（`unlink(missing_ok=True)`，旧版遗留清理）。
- Runner 通过统一出站规划 `cbrowser/shared/egress_plan.py`（`resolve_runtime_egress_plan`）读取凭据文件并生成规范化代理 URL（IPv6 字面量自动加方括号、userinfo 以 `urllib.parse.quote(s, safe="")` 百分号编码），传给 CloakBrowser SDK `launch_persistent_context_async(proxy=...)`（`d046`）：`http`、`https`（含 TLS-to-proxy）与 `socks5` 全部统一支持用户名/密码认证（包括含 `@`/`%`/`!` 等特殊字符密码）与 `geoip=True` 同路代理探测；原手工拼装 `--proxy-server=` 及 `proxy_http_auth_unsupported` 拒绝分支已彻底删除。有代理时统一注入 `--disable-quic` 与 `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`（无 `proxy_id` 时 `proxy=None` 且不注入代理加固参数）。凭据绝不进日志、异常消息与上报状态。
- 校验与失败封闭：读文件/字段校验（scheme ∈ {http,https,socks5}、bare 主机名、port 1..65535、整型 `credential_revision`）或 `credential_revision` 与绑定快照不符，任一异常即 `ProxyCredentialsChangedError()`，固定消息 `PROXY_CREDENTIALS_CHANGED`。
- 网络策略（`proxy_enforced=True`）：有代理 Browser 与出口探测 helper 均通过同一出站规划设置 `proxy_enforced=True`（IPv4/IPv6 `OUTPUT` 尾规则均为 `-A OUTPUT -j DROP`），仅放行上游代理解析地址:端口（`scheme://host:port`，容器内 `_resolved_endpoint` 解析，域名代理时仅附加 Docker DNS `127.0.0.11:53/udp`）；严禁 WebRTC UDP、QUIC、外部 DNS 与直连公网逃逸（`d047`）。loopback 上游映射为 `host.docker.internal` 并加 `extra_hosts`，归 Browser 承担。
- 每 Profile 只有两个沙箱容器（browser/stream），启动顺序为网络 → Browser → Stream；无代理凭据或凭据异常即失败封闭、Browser 不启动，巡检 `browser_policy_spec` 漂移触发 `fail_close_container`。

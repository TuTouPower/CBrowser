# Task spec

## 背景

全仓持久化机制、“设置”交互与代理管理全链路存在根因同源的架构分裂与临时补丁缺陷（聚合 `p104`、`p105` 设置弹窗与代理表单部分、`p106`、`p110` 与 `p111`）：

1. **后端持久化死表 + 前端设置/筛选/会话静音散落临时态（`p111`）**：
    - `migrations/versions/0001_baseline.py` 与 `adapters/database/models.py:316` 已建立 `settings` 表与 `SettingModel`（甚至被 `repository.py:20` 导入），但全仓零读写/API！主题（`theme.tsx`）与语言（`i18n.tsx`）被迫只存在 `localStorage`，换浏览器或清缓存即失；
    - `ProxyListPage.tsx:84-87` 把搜索词 `query`、协议 `scheme`、位置 `region` 与 `layout` 全放组件 `useState` 中，一刷新即归零（与 `EnvironmentListPage` 不一致）；
    - `useBrowserSession.ts:59` 的 `audioMuted` 仅存 `useState(false)`，刷新当前会话标签页立刻恢复有声（注意需按标签页隔离持久化于 `sessionStorage`，确保双标签页打开同 Profile 时互不串扰——满足 `test_frontend_session_e2e.py` 双页独立静音规则）。
2. **设置页面窄长拥挤、信息混乱且不是弹窗（`p105`）**：当前 `/settings` 独立路由将内容框在 `max-w-panel`（`28rem`）单列漂浮在宽屏中央，字体包卡片将 `source` / `source_version` / `file_count` / `used_by_count` 拥挤 2×2 堆叠展示技术源码哈希。用户明确要求重新设计设置界面并将其彻底升级为宽弹窗。
3. **代理测速结果仅存组件临时态、忽略 `failed` 误报可用、把 Docker 建毁耗时当延迟高达 `1759ms`+（`p110`）**：
    - `ProxyEgressObservationModel` 与 `ProxyResponse` 只有 `egress_ip`、`country_code`、`observation_status`、`observed_at`，无 `latency_ms` 字段且未暴露 `error_code`；
    - `ProxyListPage.tsx` 用 `useState(speedResults)` 与 `Date.now() - startedAt` 测量整个 HTTP 探测请求耗时，一刷新清空，且当后端探测失败返回 HTTP 200 `{observation_status: "failed"}` 时 `onSuccess` 直接误报成可用 `ok` 与成功 toast；
    - 后端 `docker_adapter.run_egress_probe` 每次测速同步「建 bridge 网 → 起 helper 容器 → 起 policy 容器写 iptables → 冷启动 Python → 请求外部 echo → 强删容器与网络」（本机实测仅容器周期即达 **5579.66ms**），且 `docker_adapter._exec_probe_helper` 在 `exit_code != 0` 时直接抛错跳过 `_parse_probe_output`，吞掉 `egress_probe.py` 输出的结构化 `error_code`！
4. **缺少国家 + 城市精细化定位与网络服务接入（`p106`）、代理列表展示与“使用环境”弹窗缺口（`p104`）**：
    - `shared/egress.py` 对 `GeoLite2-City.mmdb` 调用 `reader.city(ip)` 却直接丢弃 `country.names` 与 `city.names`，用户明确要求位置拆分为「国家」与「城市」、筛选拆分为「国家筛选」与「城市筛选」、并接入相应的 IP 地理网络服务查询国家与城市；
    - 代理列表“位置+状态”混为一列，“使用环境”带有“查看环境”文字且点击直接跳列表筛选，未做到“可用绿色仅显示延迟 / 不可用红色报错 / `0 个`禁点 / `1 个`直进 / `2 个+`先弹窗再点选”。

遵循“开发铁律（架构至上、拒绝妥协、零兼容性负担）”，在一个高内聚全栈交付中：启用 `settings` 表、将设置重构为高质感宽弹窗、将代理观测 Schema / 测速计时 / 轻量隔离探针 / 国家城市 GeoIP 服务 / OpenAPI & TS 类型 / 代理列表与筛选持久化一次性彻底重构，不打任何前端补丁或保留残缺旧字段。

## 契约区

### 范围

- **系统设置全栈持久化 + 设置宽弹窗重构（`p111`、`p105`）**：
    - **后端 `settings` API**：在 `domain/models.py` 定义强类型 `UserSettingsResponse`（至少包含 `theme: Literal["system", "light", "dark"]`、`locale: Literal["en", "zh"]`）与 `UserSettingsUpdateRequest`（`extra="forbid"`，未知键返回 422）；在 `repository.py` 实现基于 `SettingModel` 的读写事务（`BEGIN IMMEDIATE`）；在 `api/v1/settings_router.py` 暴露 `GET /api/v1/settings`（需会话鉴权）与 `PATCH /api/v1/settings`（需会话鉴权 + `require_csrf_and_origin`）。
    - **前端设置同步与标签页静音持久化**：登录后通过 `GET /api/v1/settings` 同步 `theme` 与 `locale`（切换时写服务端 + 同步更新 `localStorage` 首帧防闪烁镜像，未登录页如 `/login` 仅读写本地不发 401 请求）；`useBrowserSession.ts` 将 `audioMuted` 持久化至当前浏览器标签页隔离的 `sessionStorage`（刷新本标签页保持静音，同时保证双标签页打开同 Profile 互不串扰）。
    - **`SettingsDialog` 宽弹窗替代孤立 `/settings` 窄页**：复用 `t073` 的 `<Dialog size="lg">`，在 `AppLayout.tsx` 侧栏底部“设置”按钮直接打开弹窗（不离开当前工作上下文），整理 `/settings` 路由为重回主页打开弹窗或移除孤立窄页并同步路由/鉴权单测；弹窗内部重设计为清晰分块（外观与语言切换、服务健康状态+退出登录+只读网络访问摘要、精简平台字体包列表默认隐去冗长 `source_version` 仅异常时展开 `problems`）。
- **代理观测数据库 & 领域 & Supervisor 协议破坏性升级（`p110`、`p106`）**：
    - 新增 Alembic 增量迁移 `0010`（`down_revision = "796adb0bf159"`，严格遵照只进不退规范）：向 `proxy_egress_observations` 新增 `country_name`（可空字符串）、`city`（可空字符串）、`latency_ms`（可空整数，毫秒）。
    - 升级 `EgressObservation`、`EgressProbeResult`、`EgressProbeResponse`（`supervisor/protocol.py`）、`ProxyResponse`（`domain/models.py`）与仓储读写方法，持久化并统一暴露 `observation_status`、`latency_ms`、`egress_ip`、`country_code`、`country_name`、`city`、`observation_error_code`（脱敏可读错误码，绝不泄漏密码/宿主路径）、`observed_at`、`expires_at`；确保代理端点/凭据变更或过期时 `observation_is_current` 立即失效并清除/失效旧位置与延迟。
- **测速精准计时、消除 Docker 建毁瓶颈、错误码透传与国家/城市 GeoIP 服务（`p110`、`p106`）**：
    - **计时内移与去重**：`latency_ms` 仅测量“实际经由代理发起探测 HTTP 请求至收到完整响应”的真实网络耗时（`time.monotonic()`），严禁包含容器/网络/策略建立与销毁耗时；
    - **轻量隔离探测架构**：在**严格保留与 Browser 同网络隔离边界**（拒绝私有/保留/回环地址、只放行精确映射端点、凭据不进命令行、`trust_env=False`）的前提下，重构 `docker_adapter.py` / `supervisor/core.py` 的单次与批量测速执行架构（先完成下方 `UNVERIFIED-SPIKE`，消除“每次测速必重建新网络与两只容器”导致的数秒级阻塞）；
    - **修复 `exit_code=1` 吞错缺陷**：改造 `docker_adapter._exec_probe_helper`（或新执行器），当 helper 子进程输出合法 JSON `{"error_code": ...}` 并以非零退出时，正确解析出结构化 `error_code` 落盘 `failed` 观测，不再退化为通用 `probe_failed`；
    - **IP → 国家 + 城市网络服务与本地兜底**：改造 `shared/egress.py`（并同步更新 `docs/blueprint/decisions.md` ADR 029 与 `docs/blueprint/security.md`）：先完成下方 GeoIP Spike，按主备优先级通过代理请求白名单只读 HTTPS IP 地理服务同时获取出口 IP、国家名/码与城市名并计单次网络 RTT；若外部服务限流/缺失城市/不可达，则回落 IP 回显 + 完整读取本地 `GeoLite2-City.mmdb`（提取 `country` 与 `city`）保障可用性。
- **契约导出 + 前端代理列表 / 卡片 / 筛选持久化 / 弹窗全翻新（`p104`、`p106`、`p110`、`p111`）**：
    - 导出最新 OpenAPI（`scripts/export_openapi.py`）、Supervisor/Runtime 协议 JSON 与前端 TS 类型（`npm run generate:api --prefix src/frontend`）；
    - **彻底删除 `ProxyListPage.tsx` 中的 `speedResults` state 与 `Date.now() - startedAt` 伪测速**；单条/批量测速完毕后直接读取后端持久化的 `ProxyResponse`，当返回 `observation_status === "failed"` 时展示失败错误与错误 toast，不再误报成功；
    - **列表列与卡片结构升级**：拆分为独立「名称 | 协议 | 地址 | 国家 | 城市 | 状态 | 使用环境 | 操作」（`ProxyTable.tsx` 与卡片视图一致，且 `ProxyFormDialog.tsx` 采用 `Dialog size="lg"` 统一宽样式并在只读观测区适配国家、城市、延迟与失败态，`SessionDetailsPanel.tsx` 同步适配）；
    - **状态列规则**：`pending` 展示探测中；`ok` **不显示额外状态数字**，直接以绿色语义文字展示延迟（如 `128ms`）；`failed` 以红色语义文字展示错误原因；`unknown` 展示中性未测速提示；
    - **使用环境列与弹出列表**：文本去掉“查看环境”，仅渲染 `0 个`、`1 个`、`2 个`（英文对应单复数）；`0 个` 禁止点击；`1 个` 点击直接进入对应环境（打开关联工作台或详情页面）；`2 个及以上` 点击先打开 `ProxyUsedByPopover` 小弹窗列出使用该代理的全部环境（含环境名称与绿色/灰色运行状态点），再点击某环境才进入；
    - **独立国家/城市筛选 + URL/本地持久化**：`ProxyListToolbar.tsx` 拆出独立「国家筛选」与「城市筛选」（支持联动去重）；新增 `useProxyFilters.ts`（`q`、`scheme`、`country`、`city` 存 URL SearchParams）与 `useProxyLayout.ts`（`list`/`card` 存 `localStorage`），刷新网页后筛选、视图、国家、城市、延迟、状态全部完整保留；删除图标按钮使用 `t073` 的红色 `IconButton variant="danger"`。

### 非范围

- 不实现内置 Mihomo / 全局 egress broker（`docs/pending/parked/p038_builtin_mihomo_proxy_nodes.md` 维持 parked）。
- 不修改环境管理主列表与卡片的时区隐藏/图标按钮（已由上游 `t073` 覆盖）；不放开部署期端口/TLS 代理运行期修改（保持 `t054` 只读）。
- 不操作 `docs/pending/parked/p040_proxy_connectivity_exit_ip_check.md` 目录归属。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：系统设置（外观主题与界面语言）持久化于控制面数据库并通过受认证与 CSRF 保护的接口读写，清缓存或重新登录后依然保持；侧栏“设置”触发宽弹窗打开当前设置而不离开原有页面上下文，信息分区清晰、默认不堆砌技术哈希且字体异常时展开明细。
- [x] AC-002：浏览器工作台会话标签页开启静音并刷新当前标签页后保持静音；同一浏览器同时打开两个会话标签页时，各自静音互不干扰。
- [x] AC-003：对代理触发测速后，控制面经由代理探测并持久化真实网络往返延迟（毫秒）、出口 IP、国家与城市及状态与结构化错误原因；刷新网页后上述数据以及代理页搜索、协议、国家、城市筛选与视图布局依然保留；修改代理端点/凭据或观测过期后旧位置与延迟立即失效。
- [x] AC-004：代理延迟仅计算经由代理完成探测网络请求的耗时，不含沙箱容器或网络创建/清理开销；当代理不可达、鉴权失败或探针报错时稳定落盘结构化失败状态与原因，前端以红色错误提示展示且不再误报成功。
- [x] AC-005：代理管理列表与卡片独立展示「国家」「城市」「状态」与「使用环境」，工具栏拆分为独立的「国家筛选」与「城市筛选」；状态可用时仅以绿色数值显示延迟、不可用时以红色字样报错；“使用环境”列仅展示 `0 个` / `1 个` / `2 个` 等计数（`0` 禁点、`1` 点击直进、`>=2` 点击先弹环境清单再点选进入）；全部接口契约、迁移与自动化测试门禁通过。
- [x] AC-006：[deploy] 真实部署端到端验证：新建与编辑表单及设置弹窗整体呈现宽大清晰布局；使用真实可用代理与不可用代理实测单条及批量测速，返回符合真实网络状况的毫秒级延迟、准确国家与城市及红色失败原因，刷新后持久化保留，且容器网络隔离与私有地址阻断边界依然成立。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001..005：可自动测试（Alembic 0010 迁移检查、后端 Settings API 鉴权/CSRF/422 集成测试、Supervisor probe 错误码与隔离/计时单测、受控上游代理+受控 GeoIP 夹具集成测试、OpenAPI/Protocol 一致性检查、Vitest 前端弹窗/路由/刷新持久化/`0/1/2+` 交互/会话独立静音测试）。
- AC-006：依赖真实宿主 Docker/OrbStack 与公网代理及在线 GeoIP 网络服务；替代验证为构建重部署后通过真实浏览器与控制面接口实测可用与不可用代理，留存延迟、国家/城市及隔离规则实测记录。

## 上下文区

- 来源与根因线索（已完成静态定位与 `.scratch/` 复现）：
    - `p111`：`SettingModel` 在 `adapters/database/models.py:316` 建表且被 `repository.py:20` 导入但全仓零读写；`theme.tsx` / `i18n.tsx` 依赖 `localStorage`；`useBrowserSession.ts:59` `audioMuted` 仅在内存 `useState`；`ProxyListPage.tsx:84-87` 筛选与布局全在 `useState`。
    - `p105`：`/settings` 被 `max-w-panel`（448px）窄列限宽且字体卡片 2×2 堆叠 `source_version`；`ProxyFormDialog` 需同步统一宽弹窗尺寸。
    - `p110`：`.scratch/proxy_probe_latency_and_persistence_notes.md`、`.scratch/repro_proxy_probe_persistence_and_failed_status.test.tsx`（复现 `speedResults` 刷新丢 + HTTP 200 `failed` 误报可用）、`.scratch/repro_proxy_probe_timing_breakdown.py`（实测每次容器+网络+iptables 生命周期耗 **5579.66ms**；`_exec_probe_helper` 在 `exit_code != 0` 直接丢弃 JSON `error_code`）。
    - `p106`：`shared/egress.py` 已打开 `GeoLite2-City.mmdb` 调用 `reader.city(ip)` 却丢弃 `city` 与 `country_name`；用户要求拆国家/城市并接入网路服务（候选免 Key HTTPS JSON：`https://ipwho.is/`、`https://api.ip.sb/geoip`、`https://freeipapi.com/api/json`）。
    - `p104`：`ProxyTable.tsx` 与 `ProxyListPage.tsx` 混合位置/状态、“使用环境”带“查看环境”文字且缺少 `0/1/2+` 分级直达与弹窗。

### 实施蓝图与文件改造清单（给执行者的精确步骤）

1. **Step 1 — 前置 Spike（先消除下方 2 项 `UNVERIFIED-SPIKE` 并写入 `docs/findings/`）**：
    - 使用 `python3 .repo_template/scripts/spikes.py new` 建立实验，实测两件事：
        1. **GeoIP 网络服务对比**：经真实代理访问 `https://ipwho.is/`、`https://api.ip.sb/geoip`、`https://freeipapi.com/api/json` 及本地 `GeoLite2-City.mmdb`，确认各自返回的 `ip`、`country_code`、`country_name`、`city` 字段稳定性、中/英文规范化、单次 RTT 与限流表现，定型主备优先级 + 回落策略；
        2. **轻量探针隔离复用设计**：验证在 `docker_adapter.py` 中通过“单/批池化受控轻量 probe helper（与 Browser 完全一致的私有地址禁止+唯一动态白名单+凭据不入命令行+禁用跨请求 `httpx` 连接池）”能否稳定将普通单测/批量测速降到网络真实毫秒/百毫秒级且完全通过既有隔离测试。
    - 将结论通过 `findings.py` 记入 `docs/findings/`，并把本 `task.md` 下方未知契约更新为已验证结论。
2. **Step 2 — 后端 `settings` API 与 `0010` 代理观测迁移 & 领域扩展**：
    - **Settings 全链路**：
        - `src/backend/cbrowser/domain/models.py`：定义 `UserSettingsResponse`（`theme: Literal["system", "light", "dark"] = "dark"`, `locale: Literal["en", "zh"] = "zh"`）与 `UserSettingsUpdateRequest`（`model_config = ConfigDict(extra="forbid")`）。
        - `src/backend/cbrowser/adapters/database/repository.py`：基于 `SettingModel` 实现 `get_settings()` 与 `update_settings()`（按 key `"ui.theme"` / `"ui.locale"` 读写，使用 `BEGIN IMMEDIATE`）。
        - 新增 `src/backend/cbrowser/api/v1/settings_router.py`（`GET /api/v1/settings`、`PATCH /api/v1/settings` + 鉴权与 `require_csrf_and_origin`）并挂载到 `api/v1/router.py`。
    - **Proxy Observation 全链路**：
        - 新增 `src/backend/migrations/versions/0010_proxy_observation_city_latency.py`（`down_revision = "796adb0bf159"`，仅加列不做 destruct/downgrade 依赖）：为 `proxy_egress_observations` 新增 `country_name`（`String(128)`, nullable）、`city`（`String(128)`, nullable）、`latency_ms`（`Integer`, nullable）。
        - 同步更新 `adapters/database/models.py`、`domain/egress_observation.py`、`domain/models.py`（`ProxyResponse` 增加 `country_name`, `city`, `latency_ms`, `observation_error_code`）、`adapters/database/repository.py`（入库与读回新字段，错误码严格脱敏）。
        - 更新 `supervisor/protocol.py`（`EgressProbeResponse` 新增 `country_name`, `city`, `latency_ms`）、`services/egress_probe.py`、`services/profile_service.py`（成功写完整字段，失败保留具体 `error_code`）。
3. **Step 3 — 后端探测计时、错误码解析与 GeoIP 服务重构**：
    - `src/backend/cbrowser/shared/egress.py`：
        - 按 Spike 结论接入白名单只读 HTTPS GeoIP 服务顺序表 + `httpx.Client(..., trust_env=False)`；用 `time.monotonic()` 对单次成功代理请求精确计算 `latency_ms = max(1, round((t1 - t0) * 1000))`；若在线 GeoIP 缺城市或全部限流/失败，结合 IP 回显 + 完整 `GeoLite2-City.mmdb` 读取 `country.names` 与 `city.names` 作为本地兜底（绝不覆盖有效在线结果或伪造位置）。
        - 同步更新 `docs/blueprint/decisions.md`（修订 ADR 029 边界）与 `docs/blueprint/security.md`（明确白名单 HTTPS Geo 服务只读无凭据外连）。
    - `src/backend/cbrowser/supervisor/docker_adapter.py`：
        - 修复 `_exec_probe_helper`：当 `exit_code == 1` 且 stdout 是含 `error_code` 的合法 JSON 时，交由 `_parse_probe_output` 精准抛出对应 `EgressProbeFailure(code)`，不再被一律覆盖成 `"probe_failed"`；
        - 按 Step 1 Spike 落地轻量/复用探针生命周期，将 Docker 建毁剥离出正常测速热路径（同时保持私有/回环阻断与 `test_t052_supervisor_probe.py` / `tests/fixtures/docker_doubles.py` 兼容更新）。
4. **Step 4 — 导出契约与生成前端类型**：
    - 执行 `python3 scripts/export_openapi.py`、`python3 scripts/export_supervisor_protocol.py`、`python3 scripts/export_runtime_agent_protocol.py`；
    - 执行 `npm run generate:api --prefix src/frontend`，确认 `shared/api/cbrowser_v1.d.ts` 包含 `settings` 接口与 `ProxyResponse` 新字段。
5. **Step 5 — 前端 API 接入、设置弹窗重构、会话页静音与代理全量重构**：
    - `src/frontend/src/shared/api/client.ts`：新增 `settings: { get, update }`。
    - `src/frontend/src/theme.tsx` & `i18n.tsx`：已认证后从 `/api/v1/settings` 拉取并回填偏好，修改时调 `PATCH /api/v1/settings` + 更新 `localStorage`（仅作 `theme_boot.js` 首帧防闪烁镜像）；未登录状态不调 API。
    - `src/frontend/src/features/browser-session/useBrowserSession.ts`：按当前标签页唯一 key（如结合每页签初始化生成的 tab id + `profileId` 存 `sessionStorage`）读写 `audioMuted`，保证本页刷新保留静音，且 `test_frontend_session_e2e.py` 双页签独立静音继续成立。
    - **设置宽弹窗与路由整理**：
        - 创建 `src/frontend/src/features/settings/SettingsDialog.tsx`（使用 `t073` `<Dialog size="lg">`）：分三大视觉块（外观与语言；Control API 健康状态/退出登录+网络接入只读地址端口；平台字体包清爽卡片默认隐去 `source_version` 哈希，仅 `!integrity.ok` 展开异常明细），彻底摆脱窄列堆砌；
        - 更新 `src/frontend/src/app/AppLayout.tsx` 侧栏底部“设置”触发打开 `<SettingsDialog>`（检查 `AppLayout.shell.test.tsx`）；清理/重定 `app/router.tsx` 中 `/settings` 孤立路由（同步迁移 `router.test.tsx`、`auth_guard.test.tsx`、`redirect.test.ts` 中曾以 `/settings` 为示例路径的测试用例）。
    - **代理管理全量重设计**：
        - 新增 `src/frontend/src/features/proxies/useProxyFilters.ts`（URL SearchParams 存 `q`、`scheme`、`country`、`city`）与 `useProxyLayout.ts`（`localStorage` 存 `list`/`card`）；
        - 改造 `ProxyListPage.tsx`：**彻底删掉 `speedResults` state 与 `Date.now() - startedAt`**；点击单测/批测仅驱动后端 `probe`，根据后端返回 `observation_status` 处理完成提示（`failed` 提示错误并按真实错误码展示，不误报成功；`pending` 等待/失效后拉取最新响应）；卡片视图同步拆出国家/城市/延迟绿色/`failed` 红色报错与使用环境交互；
        - 改造 `ProxyListToolbar.tsx`：原「地区筛选」拆为独立「国家筛选」与「城市筛选」（城市下拉选项可根据所选国家联动过滤）；
        - 改造 `ProxyTable.tsx` & 新增 `ProxyUsedByPopover.tsx`：独立列「国家」「城市」「状态」「使用环境」；状态列 `ok` 仅以 `text-success` 绿字展示 `{latency_ms}ms`，`failed` 以 `text-danger` 红字展示可读错误原因；操作列删除改用 `t073` `<IconButton variant="danger">`；使用环境仅展示 `0 个`/`1 个`/`2 个`（不含“查看环境”），`0` 禁用、`1` 点击直接进入对应环境（工作台或详情页）、`>=2` 点击弹出 `ProxyUsedByPopover` 列出各环境及运行绿/灰点再点选进入；
        - `ProxyFormDialog.tsx`（升级 `<Dialog size="lg">` 或适配宽弹窗样式）与 `SessionDetailsPanel.tsx` 同步更新只读国家、城市、延迟与失败原因展示。
6. **Step 6 — 全链路测试补全（先红后绿，旧过时测试按规则写明替换理由）**：
    - 后端：`tests/integration/test_t074_settings_api.py`（401 / 403 CSRF / 422 extra field / GET 默认值 / PATCH 回读）、`tests/unit/` 补齐 `0010` 迁移检验、`Latency` 计时边界、`exit_code=1` JSON 解析、受控 HTTPS GeoIP 夹具多服务降级+防 SSRF 负向校验与凭证不进错误码验证。
    - 前端：重构 `SettingsDialog.test.tsx`（替代旧 `SettingsPage.test.tsx`）并同步 `AppLayout.shell.test.tsx`、`router.test.tsx`、`auth_guard.test.tsx`、`redirect.test.ts`；新增 `session_audio` 标签页刷新保静音与双页隔离测试；重写 `ProxyListPage.test.tsx`（写明删除旧 `"查看环境"` 与老列断言理由，新增刷新不丢延迟/国家/城市、HTTP 200 返回 `failed` 标红不误报、国家/城市独立筛选及 URL 持久化、`0/1/2+` 使用环境三态弹窗进入测试）。

### 有意不测

- 第三方公网 GeoIP 服务实时在线率与外部地理库数据主观准确度（自动化测试通过受控本地 HTTP 夹具模拟多国多城/429/超时与 `GeoLite2-City.mmdb` 回落全路径；真实公网服务表现于 `[deploy]` AC-006 验证）。

### 测试策略

- 运行全套仓库门禁 `bash scripts/run_gates.sh`（覆盖 `export_*_protocol.py --check`、`test_exported_openapi_schema_matches_live_app`、后端全部 unit & integration、`frontend` `test:types` / Vitest / `design:lint` / `design:check` / `build`）。
- `[deploy]`：在宿主 Docker/OrbStack 环境重打包部署后实测真实可用代理与不可用代理，留存 API 响应、页面刷新持久截图与容器隔离校验记录。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 候选外部免 Key HTTPS IP 地理服务（`ipwho.is`、`api.ip.sb/geoip`、`freeipapi.com`）在实际代理出口下的 JSON 结构稳定性、字段规范、单次耗时、限流（429）策略及与 `GeoLite2-City.mmdb` 的覆盖互补关系：结论（s023 已用 `spikes.py new` 在真实代理出口实测，见 `docs/spikes/s023_t074_geoip_service_contract/report.md` 与 `docs/findings/d048_t074_geoip_service_reliability_and_ratelimit.md`）——`ipwho.is` / `api.ip.sb/geoip` 经 5 个不同出口全部 TLS 握手失败不可用；`freeipapi.com` 需跟随 307，字段为 `ipAddress` / `countryCode` / `countryName` / `cityName`，RTT 中位 749.7ms，同出口连续第 10 次起 429；IP 回显 `api.ipify.org` 稳定（RTT 中位 473.2ms、12 次无 429）；本地 `GeoLite2-City.mmdb` 可解析 country/city 且与在线城市粒度互补。定型为「IP 回显 + 本地 mmdb 主链，在线服务仅作可选城市补充并处理 307 / 429 / TLS 失败回落」，单一国家多个城市多个落地 IP 只作观测值不参与等价判定。验证方式：s023 `code/geoip_probe.py` + `code/results.json` 的 5 端口矩阵、429 burst 与 Browser 容器 mmdb 查询。真实公网服务在线率与地理库主观准确度按「有意不测」口径归 AC-006 `[deploy]` 验证，不冒充已验。
- Supervisor 若使用池化/常驻轻量探针 helper 时的热切换网络白名单与隔离边界（确保不放宽私有/回环/保留地址拦截，且不跨代理复用 TCP 连接池）：结论（s024 已用 `spikes.py new` 在真实 Docker 容器原型验证，见 `docs/spikes/s024_t074_lightweight_probe_isolation/report.md` 与 `docs/findings/d049_t074_lightweight_probe_isolation_and_timing.md`）——每请求新建 `httpx.Client(trust_env=False)` + `ipaddress` 私有/保留地址 fail-closed + 精确动态白名单，可热切换代理目标且无跨代理连接池串扰；`time.monotonic()` 只包实际 HTTP 往返（390–520ms），与容器生命周期解耦；凭据只从环境变量文件读取不进 `argv`。定型为「池化轻量 helper + 每请求短生命周期 client + 计时内移 + 动态白名单」，既有 `test_t052_supervisor_probe.py` / `docker_doubles.py` 与内核双族 OUTPUT DROP 边界不得放宽。验证方式：s024 `code/probe_isolation_prototype.py` + `code/results.json` 的私有地址守卫、热切换双出口、独立 RTT 记录。真实部署拓扑下的完整隔离与毫秒级延迟按链口径归 AC-006 `[deploy]` 验证，不冒充已验。

### 风险与回退

- 风险：外部 GeoIP 服务在特定出口 IP 被限流（HTTP 429）或城市字段缺省；处置：按顺序尝试多免 Key HTTPS 服务并在缺城市或失败时自动回落 IP 回显 + 本地 `GeoLite2-City.mmdb` 解析，保证测速主链不瘫痪。
- 风险：复用/池化探针网络或容器若清理不彻底，可能导致前一代理规则或连接残留；处置：强约束每次探针使用全新短生命周期 `httpx.Client(trust_env=False)`（禁跨请求 keep-alive 复用），切换代理目标前严格重置单一出口白名单或按隔离会话执行。
- 风险：移除 `/settings` 独立页面会影响以 `/settings` 作示例回跳目标的旧单测（`auth_guard.test.tsx`、`router.test.tsx`、`redirect.test.ts`）以及 `Environment` / `Settings` 导航断言；处置：改用 `/proxies` 等有效受保护路由作为登录回跳测试用例，同时验证侧栏触发设置弹窗跨路由不丢失当前视图上下文。
- 风险：Alembic `0010` 只进不退；处置：严格校验空库及含历史数据测试库从 `796adb0bf159` 升级至新 head；生产重部署前按规程依赖 `deploy.sh` 自动备份库。
- 回退：代码侧单任务 commit 可整笔回退；若实部署需回退库结构则使用 `deploy.sh restore` 恢复升级前数据库备份。

### 依赖与约束

- `depends_on`: `t073`（依赖 `t073` 先合入主干，直接复用其 `success` / `danger` 语义色、`StatusBadge`、`IconButton variant="danger"` 与 `Dialog size="lg"`）。
- 严格遵守 `docs/blueprint/security.md` 与 `docs/blueprint/supervisor.md`（探针禁止由 API 进程直连代理或放行私网/回环、密码严禁写入命令行/日志/错误响应）、`docs/blueprint/conventions.md`（OpenAPI 与协议单源导出、统一 `ErrorResponse`）及 `docs/blueprint/persistence.md`（只进不退 Alembic + `BEGIN IMMEDIATE` 单写者）。

### Finalization 时更新的 blueprint

- `docs/blueprint/decisions.md`：修订 ADR 029（纳入轻量准确延迟观测、国家+城市提取及白名单只读 HTTPS GeoIP 服务策略）。
- `docs/blueprint/domain.md`：新增 `UserSettings` 契约，扩展 `ProxyResponse` 与 `EgressObservation` 字段（`latency_ms`、`country_name`、`city`、`observation_error_code`）。
- `docs/blueprint/persistence.md`：记录 `settings` 表实际读写用法与 `0010` `proxy_egress_observations` 迁移及字段。
- `docs/blueprint/supervisor.md` & `docs/blueprint/security.md`：记录轻量探针隔离/计时口径、`exit_code=1` JSON 错误码解析与白名单只读 HTTPS GeoIP 外连边界。
- `docs/blueprint/frontend.md`：更新设置宽弹窗与偏好同步、`audioMuted` 每页签 `sessionStorage`、代理国家/城市列与独立筛选 URL 持久化、`ok` 绿色延迟/`failed` 红色错误、`0/1/2+` 使用环境弹出交互。

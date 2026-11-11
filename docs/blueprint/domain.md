# 领域模型

本文档定义 CBrowser 核心领域概念与术语。开发与设计命名以此为准。

## 术语与实体对照表

|领域实体 / 术语|英文标识|含义与职责说明|
|---|---|---|
|**浏览器配置**|`Profile`|独立浏览器身份的元数据聚合，包括名称、分组引用（`group_id`）、代理引用（`proxy_id`）、指纹种子、语言、时区及存储路径。不再含业务 Tag 或内嵌 proxy 字符串（t035）。|
|**分组**|`ProfileGroup`|Profile 的命名分组库条目（名称唯一、颜色取自调色板、可排序）。删除分组后引用它的 Profile 的 `group_id` 置 null。|
|**代理**|`Proxy`|可复用的代理连接库条目。录入唯一入口是代理链接（t052，见下）；密码只存于代理库，版本号 `credential_revision` 随密码变更递增；被任一 Profile 引用时删除返回 409 `proxy_in_use`。国家码不再是可写字段，是出口观测的只读派生值。|
|**代理端点**|`ProxyEndpoint`|代理连接的值对象（t052）：`scheme` / `host` / `port` / `username` + 只写秘密 `password`。端点指纹由 scheme/host/port/username 派生（sha256，不含密码）；密码轮换不改变指纹。|
|**出口观测**|`ProxyEgressObservation`|一次出口探测的结果（t052）：代理、端点指纹、凭据版本、视角（`browser`）、出口 IP、国家码、来源、状态（`pending` / `ok` / `failed`）、错误码、观测时间与过期时间（TTL 24 小时）。观测只追加历史行；当前有效观测须 status 为 ok、指纹与凭据版本均与现端点一致、未过期。|
|**运行配置版本**|`ProfileConfigVersion`|不可变的运行参数快照。只有运行配置字段值变化才生成新版本，需重启运行时才能生效；配置版本快照只存 `proxy_id` 与 `proxy_credential_revision`，不含密码（t035）。|
|**期望状态**|`DesiredState`|用户或系统声明的目标运行态（如 `running` 或 `stopped`）。持久化于数据库。|
|**观测状态**|`ObservedState`|运行时容器与进程的真实观测状态（`stopped` / `starting` / `running` / `stopping` / `error`）。|
|**查看连接**|`ViewerConnection`|外部 Google Chrome 标签页与 BrowserRuntime 之间的实时显示与输入连接；所有连接均为 `controller` 角色，无排他锁与租约（ADR 007）。|
|**运行时沙箱**|`BrowserRuntime`|托管单个 Profile 的隔离容器实例，生命周期受 Supervisor 调度。|
|**运行时代理**|`RuntimeAgent`|运行在容器内部的 Python 守护进程，负责输入代理、下载监听、GTK 书签注入与健康汇报。|
|**容器协调器**|`RuntimeSupervisor`|宿主端容器调度器，唯一定义容器模板、分配媒体 UDP 端口池并执行生命周期操作。|
|**文件归档**|`Artifact`|用户上传到浏览器环境或浏览器内下载完成的文件元数据记录，包含 SHA-256、体积与配额信息。|
|**文件交换区**|`ExchangeDirectory`|宿主机与容器共享的持久化上传/下载暂存目录，按 Profile 严格隔离。|
|**指纹平台**|`ProfileConfig.fingerprint_platform`|Profile 绑定的反指纹目标平台，取值 `windows`（默认）/ `macos`；CloakBrowser 只支持这两种，无 Linux 平台。属运行配置，变更产生新 `ProfileConfigVersion`（t041）。|
|**平台字体集**|`ProfileConfig.font_set_id`|对同平台、按内容寻址的不可变字体集的引用；null 表示未配置平台字体。字体集只在运行时只读挂载，不进镜像与仓库；属运行配置，变更产生新 `ProfileConfigVersion`（t041）。|
|**语言**|`ProfileConfig.locale`|Profile 的浏览器语言，封闭枚举 `zh-CN` / `en-US`（新建默认 `en-US`）。属运行配置，变更产生新 `ProfileConfigVersion`，重启后生效（t053）。|
|**时区**|`ProfileConfig.timezone`|Profile 的时区，合法 IANA 时区名或 null（null 表示自动、随出口 IP）；非法时区在写入边界 422 拒绝。时区只决定语言联动的输入，不直接决定浏览器时区以外的行为（t053）。|

## 状态转换规则

1. **Profile 生命周期状态机**：
    ```text
    stopped ──(start)──> starting ──(ready)──> running
                               │                  │
                               ▼                  ▼
                            error              stopping ──> stopped
    ```
2. **无租约并发控制（ADR 007）**：
    - 不设排他控制租约、`ControlSession` 实体、租约代次或抢占接管等待；同一 Profile 可同时接纳多个 `ViewerConnection`。
    - 连接身份由官方 `client_tab_id` 维护，页面刷新保留该身份并生成新 `resume_key`；仅连接内断线重连复用原 `resume_key`。
    - 关闭任一外部标签页不影响同一 Profile 的其他连接，也不关闭底层浏览器进程。

## 字段校验、null 与时间语义（t021）

- **更新请求的校验时机**：Profile 更新 DTO（`ProfileUpdateRequest`）对 `launch_args` / `extension_paths` 只做严格校验（条数、单条长度、危险参数拒绝），不在校验阶段过滤或改写合法条目；历史数据的读取侧过滤（`ProfileConfig`）保持不变，继续保证旧数据可读。
- **PATCH 三态语义**：列表字段缺失（absent）表示不变；显式 `null` 表示清空为 `[]`；给出列表表示整体替换。`ProfileConfig` 对显式 null 的 `launch_args` / `extension_paths` 归一为 `[]`，仓储合并路径不得把 null 直接送入领域模型（曾导致 500）。
- **时间语义**：全仓唯一的当前时间实现是 `cbrowser.domain.models.utc_now_iso`；适配层模型不得再定义同名本地实现，SQLAlchemy 列默认值直接引用领域实现。
- **期望/观测状态词汇**：内部 runtime 响应与事件 DTO 的 `desired_state` / `observed_state` 使用领域枚举 `DesiredState` / `ObservedState`，OpenAPI 中呈现为封闭 enum，未知状态值在 DTO 边界即被拒绝，不再以自由文本透传。

## 分组、代理与配置版本三分（t035）

- **引用代替内嵌**：Profile 通过 `group_id` / `proxy_id` 引用分组库与代理库；引用不存在的分组或代理在写入边界被拒绝。业务 Tag 与 `ProfileConfig.proxy` 内嵌字段已移除（AC-012）。
- **引用校验是字段级 422（t056 A28）**：创建或更新 Profile 时引用不存在的分组 / 代理，返回 422 `validation_error`，`details` 列出每个缺失字段的 `loc` / `msg` / `type`（两个字段同时缺失时一次报出两个）；PATCH 只校验请求中出现的引用键，显式 null 清除引用不查库。分组重排（`POST /groups/reorder`）必须提交全集：缺失、未知或重复 id 一律 422。
- **配置版本三分**：修改分为「元数据」（`name` / `notes` / `sort_order` / `group_id`，即时生效且不生成新版本）、「即时策略」（`capture_preview`，不生成新版本）、「运行配置」（其余字段；值变化才生成新版本，运行中产生待应用版本）。提交与当前值相同的运行配置也不生成。
- **代理连接变更的联动（t056 A17 修订）**：`update_proxy` 改连接字段（scheme/host/port/username/password）时，在同一事务内只为**当前配置**引用它的 Profile 生成新版本并广播 SSE；只改 name/region/notes 不生成。仅被运行中绑定版本引用（当前配置已改绑他处）的 Profile 不生成新版本，只收到运行事件。快照中的 `proxy_credential_revision` 与代理库 `credential_revision` 对齐，Runner 据此判定凭据是否变更并失败封闭 `proxy_credentials_changed`。**冻结修订取实际引用者**：绑定快照冻结的修订号取该快照实际引用的代理的当前修订，不是被改代理的修订；凭据变更后旧绑定版本重启仍按冻结修订校验、失败封闭，应用新版本后启动成功。

## 代理链接录入与出口观测（t052）

- **链接为唯一录入**：`ProxyCreateRequest` / `ProxyUpdateRequest` 只接受 `proxy_url`（`extra="forbid"`，平铺字段与 `country_code` 一律 422）。四种格式：标准 URL `scheme://user:pass@host:port`、无协议 `host:port`（默认 http）、`host:port:user:pass`、`user:pass@host:port`；scheme 白名单 http/https/socks5、IPv6 必须括号、端口 1..65535、密码 percent-decode 且非法转义报错；裸 IPv6 与三段无协议形式判 ambiguous。`ProxyResponse` 返回脱敏链接（不含密码）与派生只读字段（scheme/host/port/username），密码永不进响应。
- **名称派生**：创建时 name 省略或为空由 `host:port`（IPv6 加括号）派生；前端手动填写后不被后续解析覆盖。
- **PATCH 语义**：`proxy_url` 省略 = 端点（含密码）不变；提供 = 整端点（含密码）整体替换，`password_supplied=True`，触发新配置版本、pending 观测与自动探测。编辑端点而密码框留空时，前端拦截提交（否则会静默清除已存密码），须重填密码或显式清除。
- **国家是观测，不是配置**：`proxies.country_code` 列由迁移 `0006` 删除（无真实用户，不做数据迁移）；`ProxyResponse.country_code` / `egress_ip` / `observation_status` / `observed_at` 均由当前有效观测派生。端点指纹或凭据版本变化、观测过期（TTL 24 小时）时旧观测立即失效，界面显示未知；探测失败记 failed 行、不猜国家。
- **探测视角**：观测的视角恒为 `browser`——探测由 Supervisor 在 Browser 同视角的短生命周期 helper 内执行（见 [Supervisor](supervisor.md)），不用 API 进程直连结果。出口 IP 取自 IP 回显端点（复用 cloakbrowser SDK 的 `api.ipify.org` / `checkip.amazonaws.com` / `ifconfig.me/ip`，只发一次 HTTPS GET 取自身出口 IP）；国家由本机 GeoLite2（`CBROWSER_GEOIP_CACHE/GeoLite2-City.mmdb`）判定，出口 IP 不发往第三方地理库。
- **观测记录**：表 `proxy_egress_observations`（proxy_id FK ON DELETE CASCADE + 索引）；创建与端点/凭据变更后先记 pending 行再后台自动探测，手动探测 `POST /api/v1/proxies/{id}/probe` 只接受代理 ID（无 body，任何非空 body 除 `{}` 外 422），服务端加载已存端点与凭据执行。
- **运行态扩展字段**：`ProfileRuntime` 增加 `last_started_at` / `last_stopped_at`（ISO 8601 带时区）、`browser_product` / `browser_user_agent`（来自容器内 CDP `Browser.getVersion`）；未运行时两浏览器字段为 null，进入 stopped/error 时清空。
- **删除约束**：desired=running 或 observed 为 starting/running/stopping、或仍绑定实例的 Profile 删除返回 409 `profile_running`；observed=error 且无实例可删除。删除成功后 DB 行、Artifact 与全部 Profile 专属目录都不存在。
- **schema 代际**：迁移目录只有一个 baseline 修订 `b7e1c9d4a2f3`；旧代（0001-0009）DB 在 API 启动与部署时失败封闭并输出重建指引，发布回退按修订链判定下限。详见 ADR 023。

## 显示编号必填（t056 A21）

- `Profile.display_number: int` 为必填、无默认值；数据库列 NOT NULL（迁移 `0009`，增量回填后改约束）。读到 NULL 行时仓储抛明确错误，不静默补默认值；创建时仍由服务端分配部署内唯一编号（0001…），删除不复用。

## 语言、时区与高级选项默认值（t053）

- **语言是封闭枚举**：`ProfileConfig.locale` / `ProfileCreateRequest.locale` / `ProfileUpdateRequest.locale` / `ProfileResponse.locale` 的类型为 `ProfileLocale = Literal["zh-CN", "en-US"]`，OpenAPI 呈现为封闭 enum，非法值在 DTO 边界即 422 拒绝（字段级错误）。数据库层迁移 `0007_profile_locale_enum_defaults.py`（revision `1a8db6b91744`）追加 `CHECK (locale IS NULL OR locale IN ('zh-CN', 'en-US'))`；存量行的 `locale` 一律不改写（历史遗留 null 照常读取，仍可通过 PATCH 改为枚举值）。
- **时区校验**：`timezone` 只接受合法 IANA 时区名或 null（null 表示自动、随出口 IP）；非法时区名在写入边界 422 拒绝。校验以 `zoneinfo` 为准（`domain/profile_locale.py` 的 `validate_timezone`）。
- **时区 → 语言规则**：中文地区时区集合 `{Asia/Shanghai, Asia/Chongqing, Asia/Urumqi, Asia/Harbin, Asia/Hong_Kong, Asia/Macau, Asia/Taipei}` → `zh-CN`，其余合法时区 → `en-US`；时区为空时语言保持当前值。规则由后端 `domain/profile_locale.py` 的 `locale_for_timezone` 定义，前端 `features/profiles/profile_locale.ts` 逐项镜像，两侧单测保证一致（同一规则来源的两种实现，不存在第三份真相）。
- **新建默认值**：`humanize` 与 `portable_cookies` 默认开启；其余高级选项默认值不变——`transparent_proxy` / `auto_launch` 关闭，`allow_3p_cookies` / `set_google_default` / `clipboard_sync` / `restore_session` / `capture_preview` 开启。三端一致：后端 `ProfileConfig` / `ProfileCreateRequest` / `ProfileResponse`、ORM（Python 默认 + `server_default`）、前端 `DEFAULT_PROFILE_CREATE_VALUES`；由后端单测与前端提交单测固定。迁移 `0007` 只改 server default，不改写既有 Profile 的已存值。
- **语言属运行配置**：`locale` 变更生成新 `ProfileConfigVersion`，重启后字体可见性与 `navigator.language` 按新语言生效。`geoip` 默认开启，但语言恒为显式值，不被出口 IP 推断覆盖（CloakBrowser 显式 `locale` 是否优先于出口 IP 推断，仍待真实引擎验证，见 t053 未知契约清单）。

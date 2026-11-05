# 领域模型

本文档定义 CBrowser 核心领域概念与术语。开发与设计命名以此为准。

## 术语与实体对照表

|领域实体 / 术语|英文标识|含义与职责说明|
|---|---|---|
|**浏览器配置**|`Profile`|独立浏览器身份的元数据聚合，包括名称、分组引用（`group_id`）、代理引用（`proxy_id`）、指纹种子、语言、时区及存储路径。不再含业务 Tag 或内嵌 proxy 字符串（t035）。|
|**分组**|`ProfileGroup`|Profile 的命名分组库条目（名称唯一、颜色取自调色板、可排序）。删除分组后引用它的 Profile 的 `group_id` 置 null。|
|**代理**|`Proxy`|可复用的代理连接库条目（协议/host/端口/可选凭据）。密码只存于代理库，版本号 `credential_revision` 随密码变更递增；被任一 Profile 引用时删除返回 409 `proxy_in_use`。|
|**运行配置版本**|`ProfileConfigVersion`|不可变的运行参数快照。只有运行配置字段值变化才生成新版本，需重启运行时才能生效；配置版本快照只存 `proxy_id` 与 `proxy_credential_revision`，不含密码（t035）。|
|**期望状态**|`DesiredState`|用户或系统声明的目标运行态（如 `running` 或 `stopped`）。持久化于数据库。|
|**观测状态**|`ObservedState`|运行时容器与进程的真实观测状态（`stopped` / `starting` / `running` / `stopping` / `error`）。|
|**查看连接**|`ViewerConnection`|外部 Google Chrome 标签页与 BrowserRuntime 之间的实时显示与输入连接；所有连接均为 `controller` 角色，无排他锁与租约（ADR 007）。|
|**运行时沙箱**|`BrowserRuntime`|托管单个 Profile 的隔离容器实例，生命周期受 Supervisor 调度。|
|**运行时代理**|`RuntimeAgent`|运行在容器内部的 Python 守护进程，负责输入代理、下载监听、GTK 书签注入与健康汇报。|
|**容器协调器**|`RuntimeSupervisor`|宿主端容器调度器，唯一定义容器模板、分配媒体 UDP 端口池并执行生命周期操作。|
|**文件归档**|`Artifact`|用户上传到浏览器环境或浏览器内下载完成的文件元数据记录，包含 SHA-256、体积与配额信息。|
|**文件交换区**|`ExchangeDirectory`|宿主机与容器共享的持久化上传/下载暂存目录，按 Profile 严格隔离。|
|**中文字体包**|`ProfileConfig.font_bundle`|Profile 级 CJK 字体可见性开关：`none`（默认，容器内无中文字体）、`wqy-microhei`（文泉驿微米黑）、`wqy-zenhei`（文泉驿正黑）；属于运行配置，变更产生新 `ProfileConfigVersion`。|

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
- **配置版本三分**：修改分为「元数据」（`name` / `notes` / `sort_order` / `group_id`，即时生效且不生成新版本）、「即时策略」（`capture_preview`，不生成新版本）、「运行配置」（其余字段；值变化才生成新版本，运行中产生待应用版本）。提交与当前值相同的运行配置也不生成。
- **代理连接变更的联动**：`update_proxy` 改连接字段（scheme/host/port/username/password）时，在同一事务内为每个引用它的 Profile 生成新版本并广播 SSE；只改 name/region/notes 不生成。快照中的 `proxy_credential_revision` 与代理库 `credential_revision` 对齐，Runner 据此判定凭据是否变更并失败封闭 `proxy_credentials_changed`。
- **运行态扩展字段**：`ProfileRuntime` 增加 `last_started_at` / `last_stopped_at`（ISO 8601 带时区）、`browser_product` / `browser_user_agent`（来自容器内 CDP `Browser.getVersion`）；未运行时两浏览器字段为 null，进入 stopped/error 时清空。
- **删除约束**：desired=running 或 observed 为 starting/running/stopping、或仍绑定实例的 Profile 删除返回 409 `profile_running`；observed=error 且无实例可删除。删除成功后 DB 行、Artifact 与全部 Profile 专属目录都不存在。
- **schema 代际**：迁移目录只有一个 baseline 修订 `b7e1c9d4a2f3`；旧代（0001-0009）DB 在 API 启动与部署时失败封闭并输出重建指引，发布回退按修订链判定下限。详见 ADR 023。

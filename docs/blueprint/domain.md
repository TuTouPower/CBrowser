# 领域模型

本文档定义 CBrowser 核心领域概念与术语。开发与设计命名以此为准。

## 术语与实体对照表

|领域实体 / 术语|英文标识|含义与职责说明|
|---|---|---|
|**浏览器配置**|`Profile`|独立浏览器身份的元数据聚合，包括名称、标签、指纹种子、语言、时区、代理及存储路径。|
|**运行配置版本**|`ProfileConfigVersion`|不可变的运行参数快照。修改指纹或网络配置将生成新版本，需重启运行时才能生效。|
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
                            failed             stopping ──> stopped
    ```
2. **无租约并发控制（ADR 007）**：
    - 不设排他控制租约、`ControlSession` 实体、租约代次或抢占接管等待；同一 Profile 可同时接纳多个 `ViewerConnection`。
    - 连接身份由官方 `client_tab_id` 维护，页面刷新保留该身份并生成新 `resume_key`；仅连接内断线重连复用原 `resume_key`。
    - 关闭任一外部标签页不影响同一 Profile 的其他连接，也不关闭底层浏览器进程。

# 领域模型

本文档定义 CBrowser 核心领域概念与术语。开发与设计命名以此为准。

## 术语与实体对照表

|领域实体 / 术语|英文标识|含义与职责说明|
|---|---|---|
|**浏览器配置**|`Profile`|独立浏览器身份的元数据聚合，包括名称、标签、指纹种子、语言、时区、代理及存储路径。|
|**运行配置版本**|`ProfileConfigVersion`|不可变的运行参数快照。修改指纹或网络配置将生成新版本，需重启运行时才能生效。|
|**期望状态**|`DesiredState`|用户或系统声明的目标运行态（如 `running` 或 `stopped`）。持久化于数据库。|
|**观测状态**|`ObservedState`|运行时容器与进程的真实观测状态（`created` / `starting` / `running` / `stopping` / `stopped` / `failed`）。|
|**控制会话**|`ControlSession`|外部 Google Chrome 标签页建立的远程操控会话实体，持有独立会话标识与短期鉴权状态。|
|**控制租约**|`ControlLease`|每个 Profile 的排他性写控制权限。同一 Profile 同一时间仅存在一个有效租约，防输入冲突。|
|**流媒体票据**|`StreamTicket`|用于与 Selkies 建立 WebRTC 信令连接的一次性短期校验凭据（TTL 30s）。|
|**运行时沙箱**|`BrowserRuntime`|托管单个 Profile 的隔离容器实例，生命周期受 Supervisor 调度。|
|**运行时代理**|`RuntimeAgent`|运行在容器内部的 Python 守护进程，负责输入代理、下载监听、GTK 书签注入与健康汇报。|
|**容器协调器**|`RuntimeSupervisor`|宿主端容器调度器，唯一定义容器模板、分配媒体 UDP 端口池并执行生命周期操作。|
|**文件归档**|`Artifact`|用户上传到浏览器环境或浏览器内下载完成的文件元数据记录，包含 SHA-256、体积与配额信息。|
|**文件交换区**|`ExchangeDirectory`|宿主机与容器共享的持久化上传/下载暂存目录，按 Profile 严格隔离。|

## 状态转换规则

1. **Profile 生命周期状态机**：
    ```text
    stopped ──(start)──> starting ──(ready)──> running
                               │                  │
                               ▼                  ▼
                            failed             stopping ──> stopped
    ```
2. **控制租约状态流**：
    - 活跃状态：客户端周期性（5s）上报心跳。
    - 离线保护：丢失心跳超过 15s 进入断开状态，启动 30s 重连恢复窗口。
    - 租约释放：超时未恢复或主动退出则释放租约，允许其他外部标签页申请接管。

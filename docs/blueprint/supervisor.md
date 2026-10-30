# Runtime Supervisor

本模块实现 t005 生命周期协调。正式 v2 入口、用户鉴权与 Gateway 交付分别由 t006/t012 集成；当前旧服务入口尚未切换。阶段验收状态以 t005 task、review 和交接记录为准。

## 权限与数据所有权

Supervisor 是唯一挂载 Docker Socket 的服务，不挂载元数据 SQLite，不导入数据库实现。API 是唯一业务数据库写入者；Supervisor 经 `/api/v1/internal/supervisor` 认证 RPC 读取 Profile、不可变配置版本及运行状态，上报实例绑定、观测与事件。

API/Supervisor 控制面使用外部文件提供的 Bearer 凭证，至少 32 UTF-8 字节。Gateway 控制面使用独立凭证文件。Agent 主密钥保留在 Supervisor/Gateway；每个 Stream 只挂载从 Profile 与 runtime_instance_id 派生的认证文件，不能获得主密钥或其他实例凭证。所有控制端口只用于内部网络，不直接公开。

`PathValidator` 约束统一数据根及 Profile 归属：用户数据、runtime、事件、Artifact、引擎与 GeoIP 缓存不得逃逸。固定 Profile 目录不能用符号链接替换为其他 Profile 目录。快照、派生凭证、操作日志与事件文件采用原子替换、文件与目录 fsync；写入目标本身为符号链接时替换链接，不跟随其写入目标。此约束不构成对恶意宿主机并发修改目录或任意 Docker Socket 使用者的安全承诺。

## 容器与网络

每个 Profile 创建 Browser/Stream 两个容器，均非 root、只读根、cap-drop ALL、restart policy `no`。Browser 提供 shareable IPC 和 1 GiB `/dev/shm`；Stream 只共享对应 Browser IPC/hostname，挂载 X11 socket 文件、Xauthority、Pulse 目录及实例凭证。Stream 不挂载用户数据、Browser Agent socket 或 Docker Socket。

Browser 只加入所属 egress bridge；Stream 只加入所属媒体 bridge。共享 Gateway/coturn 动态加入媒体网络，实际地址明确传给 Stream。网络复用与删除要求名称和 managed-by/profile/prefix 标签匹配。清理遇未知端点必须失败，不能强制断开；失败回滚只撤销本次新建连接。

引擎初始化通过临时 helper 完成，然后以只读挂载交付 Browser。SDK 初始化显式 pin `get_chromium_version()`，与 Runtime 使用相同引擎版本；不在 helper 失败后用盲目重试掩盖初始化错误。

## 生命周期与恢复

API 保存 `desired_state`、实例、失败计数与阻断状态。启动前必须已有 running 意愿并读取不可变配置；配置请求失败不能猜测默认配置继续启动。按 Profile 串行创建，分配 30000–30991 范围独立 UDP mux 端口，容器内外端口一致。

停止命令携带 `operation_id` 与目标 `runtime_instance_id`。操作日志允许同一请求重放；相同操作 ID 配不同请求返回冲突。旧实例停止重放不能终止新实例。停止顺序为标记 unavailable/stopping、Gateway 断开 Viewer、停止 Stream、停止 Browser、移除所属网络，最后回收端口；清理失败不释放仍占用的端口。

Native 事件按目录归属、Profile 与实例核对后进入持久 spool。事件 ID 只作为协议身份，文件名使用哈希，不能充当路径。API 按事件 ID 去重并核对实例/配置代际；ACK 日志跨重启保留，已送达事件不反复上传。API 离线时保持健康运行容器，恢复后重放。

`RecoveryCoordinator` 根据 API 状态与 Docker 扫描协调异常重试。首次异常之后分别等待 2/10/30 秒，共三次自动重试；三次均失败时，原始异常总数 `failure_count=4` 并阻断。调度以 API 持久时间为依据，Supervisor 重启不能重新开始完整等待。正常退出和用户 stopped 意愿不重试；手动解除阻断经 API 幂等意愿事务执行。启动失败由 Core 上报一次稳定事件，协调器不重复计数。

Supervisor 控制目录持进程级 flock，SIGKILL 由内核释放。Supervisor 正常退出仅取消自身后台任务，不终止健康 Runtime；重启时核对 API 意愿、实例及 Docker 标签和实际端口，再恢复本地会话。单纯看到容器对象或端口配置不等于 Runtime 已就绪。Browser 就绪还须核对当前 Profile、实例、配置版本和 PID，Stream 必须完成 Gateway 注册。

API 已绑定但尚无对应 Browser 的启动中断，通过稳定 missing_runtime 事件收敛后进入正常退避。Profile 锁持有期间不合成退出；已读取 Native 退出 journal 时优先等待其送达，避免首次 API 503 后被合成异常抢先覆盖。手动重开先移除旧自有 Browser 容器，再清理指向旧 hostname/PID 的 Chromium singleton 链接；不跟随链接修改目标。

## 资源限制

`ResourcePolicyService` 使用 Linux `/proc/stat` 和 Docker CPU counter，识别 NanoCpus、CFS quota/period、cpuset 的最紧实际预算。缺失、重复和重置 counter 不能被当作新的低负载窗口。Profile 聚合 Browser/Stream 压力，结合真实前台连接状态决定是否下发 8 FPS cap；恢复后解除 cap，由 Stream 自身活动策略决定 8/30 FPS。全后台状态不因 CPU 高负载误触发前台限制。

`ResourceMonitor` 在线程中采集阻塞 Docker stats，在事件循环内串行更新策略。控制端点 `/supervisor/v1/profiles/{profile_id}/resources` 返回决策与对应测量窗口。Viewer 心跳不建立独占控制租约。

实际 CPU 到 Chrome 降帧证明、完整 Supervisor 容器拓扑证明和正式整套部署验收属于不同范围，不能互相替代。当前机型、Docker 配额、性能场景与仅两项环境豁免见 [架构](architecture.md)。

## 网络策略与启动门禁

当前 OrbStack 普通 bridge 跨网可达，单靠网络名字和 IPAM 不能提供隔离，事实见 [d020](../findings/d020_orbstack_bridge_reachability.md)。Supervisor 在每个 Runtime 自有 network namespace 安装 IPv4/IPv6 filter 规则，不修改宿主机、Docker 全局规则或 OrbStack 配置。

策略安装使用同一不可变 Supervisor 镜像的短生命周期 helper，只授予 NET_ADMIN，加入指定 Runtime 网络命名空间，不挂 Docker Socket、宿主目录或用户数据。Browser/Stream 自身仍保持非 root、只读根、cap-drop ALL。启动 gate 在业务进程执行前等待匹配实例、角色和 ready 状态的原子标记；安装失败不开放 gate。已存在规则时拒绝覆盖，避免误接管未知网络策略。

Browser 仅允许 loopback、已建立连接及公共目的地址，私有与保留地址默认拒绝；配置代理只按明确解析的地址和端口例外放行。Stream 仅额外允许实际 Gateway、coturn 地址/端口及本实例 UDP mux。IPv6 仅放行带 hop-limit 255 的必要邻居发现类型，不全量放行 ICMPv6。端点 DNS 在 gated Runtime 内解析，私密代理 URL 不传入 helper。

Supervisor 重启仅接管拥有可信策略标签、所属只读 gate 挂载和匹配 ready 标记的 Runtime。启动独占锁内先清理严格匹配 prefix、managed-by、角色及随机名称的遗留 cache-init/network-policy helper；周期扫描不执行此清理，避免中断当前安装。

真实无过滤 TCP 正负对照、IPv6 私有 echo 拒绝、策略重复安装拒绝及双 Profile 容器拓扑已取得定向证明。完整阶段状态仍以最终源门禁、独立 review 和 task 验收为准，不能以历史候选镜像通过代替当前源验证。

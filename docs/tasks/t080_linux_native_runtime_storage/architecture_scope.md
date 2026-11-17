# 运行资源与稳态控制重构：立项依据和跨 task 边界

## 授权与状态

- 核验日期：2026-11-18，时区 Asia/Shanghai；用户先要求核验三类资源问题与架构根因，随后明确要求详细创建 task。
- 创建基线：main，HEAD `0445346`；运行 API/Supervisor 的相关 coordinator、manifest、runner、core、recovery、DockerAdapter 文件摘要与当时工作区一致。
- 本文是本批 task 的上下文设计和现场证据摘要，不是已经生效的 blueprint/ADR，不表示业务 AC 已完成。
- 本批只维护 t080–t083 和复用的 t075 task 文档；不 start、不实现、不迁移生产数据、不部署、不自动 commit/push。

## 已验证事实及因果边界

|对象|现场证据|可以得出的结论|不能扩大为的结论|
|---|---|---|---|
|字体集合|143 文件，362217650 bytes，即约 362.2 MB / 345.4 MiB|每次完整扫描都会处理数百 MB|不是“只有几 KB manifest 元数据读取”|
|生产函数复现|对隔离进程中的实际 RuntimeCoordinator.get_font_runtime 连续读取两次：286 次文件 SHA-256、724435300 bytes、约 0.45 秒|该状态路径确实每次全量哈希，最终只使用 detection|不能由该独立进程的耗时推定所有硬件/请求时延|
|API 约 60 秒采样|59.7727 秒，rchar 增加 34584781300 bytes，约 578.6 MB/s；syscr 增加 69303，read_bytes 增加 5775360 bytes|存在持续的大量逻辑读取和哈希成本|rchar 不是 VirtioFS 实际传输或 SSD 物理读取；FUSE/跨系统 I/O 也不能只靠 read_bytes 反推|
|API 其他观测|另一次瞬时 CPU 86.88%；另一个 60 秒日志窗口有 107 次内部 runtime GET|缺陷持续存在，内部状态消费频繁|不是稳定 CPU 平均值，不能把不同窗口直接组成精确模型|
|policy helper|同一采样窗口创建 16 次、销毁 16 次，对应 4 Profile、8 Runtime、约 30 秒扫描|稳态观测依赖重复容器生命周期，过滤自激事件尚未消除成本|不是仍然存在已修复的 helper 事件自激循环|
|exec|剔除采样自身 1 条后，34 次基础设施健康执行、8 次 Browser 代理域名解析|5 秒 healthcheck 与 30 秒策略推导是 exec 主要来源|recovery.tick 的 Agent 健康读取走 UDS，并不直接 docker exec；create/start/die 事件不能累加为执行次数|
|当前 OrbStack 日志|以本次 16 个 policy 容器精确 ID 关联：2 次 failed to mount rootfs、6 次 proc dirfd is dead、7 次 unable to get container|短生命周期 policy 容器与相关竞态现象有直接关联|不能证明产品是 OrbStack 所有错误的唯一来源|
|历史 vmgr.1.log|5129 次 rootfs、2644 次 proc dirfd、1702 次 unable to get container、9021 次 adding network 均核实|历史有高频资源管理活动和竞态记录|日志跨多个项目；adding network 为信息，不能计为错误；同类上下文消息也不能全作独立故障|
|Profile 挂载|0022/0023/0024/0026 的 userDataDir 都是 macOS 宿主目录 rw bind mount|Chromium 热数据和文件锁进入宿主/VM 文件共享路径|挂载本身不能证明已经发生数据损坏|
|诊断报告|包含最高 137.44 GB file-backed memory dirtied 和 pwritev、\_\_fcntl 栈|OrbStack Helper 存在大量写入/文件操作|dirty bytes 不是 SSD 实际落盘；\_\_fcntl 不能单独归属 Chromium SQLite；全部 Helper 写入不能归给这 4 个 Profile|

原始材料位于 `.scratch/runtime_io_review/`，其中 summary.json、events.jsonl、io.json、mounts.json、reproduction.json 和镜像源码摘要是一次性证据，不入库、不含成功修复结论；本文保留必要脱敏事实，避免 task 依赖 scratch 长期存在。原始事件文件含本地端点信息，不直接复制到长期文档。

指标定义参考 Linux 官方 `/proc/<pid>/io` 文档：<https://docs.kernel.org/filesystems/proc.html>。Docker volume 生命周期与高性能 I/O 适用范围参考：<https://docs.docker.com/engine/storage/volumes/>。正式实现仍须针对当前 SDK/Engine 实测，官方通用说明不能代替项目实际挂载/隔离验收。

## 根因与目标边界

1. 不可变字体身份和任意可写宿主目录并存；API 要求每次读取立即发现变化，Agent 又按内容身份缓存。完整性审计、检测覆盖与运行观测没有分层。
2. 内部协调接口复用 UI 聚合响应，GET 内下游 RPC、字体审计和逐 Profile 轮询叠加。读取数量决定重型工作量。
3. 实际网络规则验证依赖新建临时执行环境，重复 DNS 没有与策略修订绑定。观测本身制造生命周期和事件。
4. 数据归属按路径方便性决定，macOS 导入/导出路径被当成 Linux 容器热数据盘；控制面 DB 已迁卷，Chromium 用户状态尚未迁移。

目标是受管 Linux 存储、受控不可变资产发布、常驻最小权限策略观测和纯状态投影。正常浏览器写入与 VM 虚拟磁盘宿主写入依旧存在；通过更换存储边界减少逐文件/逐锁跨系统往返，不承诺 I/O 归零。

## 目标存储职责（由 t080 正式验证并写 ADR）

|类别|目标归属|授权消费与生命周期|
|---|---|---|
|控制面 DB/WAL/SHM|既有独立 DB named volume|API 唯一写者；沿用在线备份与 schema 验证|
|Profile userDataDir|部署 data 卷内精确 Profile 子目录|API/受控存储操作按业务权限读写；Browser 仅自身子目录；Stream 不挂载|
|Artifact/预览/事件/outbox/快照|部署 data 卷内有限已定义子目录|对应生产组件按最小范围消费；终态与投递状态持久化，不随 socket 清理|
|引擎/GeoIP 缓存|Linux 管理的受控缓存目录|初始化写入、运行时只读；不再从 macOS 热路径加载大二进制|
|字体集合|独立 fonts 卷|t081 发布者受控写入；Supervisor 按验证职责读取；Browser 精确集合只读；Stream 不挂载|
|UDS/X11/Pulse/运行期 gate|独立 Linux runtime 卷及按实例隔离目录|存活沙箱引用期间保留；Supervisor 重启不清空；最终释放按归属与活跃性校验|
|Policy Agent 控制 socket/凭据|runtime 中专属控制目录|仅对应 Agent 与 Supervisor 挂载，业务容器不可见|
|宿主导入/导出/备份交付|显式一次性边界|只在受控操作中使用；不成为正式运行资源的读写权威|

优先以 named volume 的精确 subpath 保留当前有限目录布局。SDK 对 subpath 的编码、缺目录行为、只读挂载和跨容器 UDS 需要正式 spike；未实测不宣布可用，也不为绕过 SDK 难点读写 daemon 私有卷物理路径。可恢复快照与 outbox 属 durable 数据，不能因为名称带 runtime 而丢弃。

## 字体生命周期（t081）

- 来源导入 → 安全 staging → 完整内容/平台验证 → 原子发布 → 目录记录可用；重复导入幂等。
- 目录元数据说明验证状态、时间与资源修订；普通 runtime/list/SSE 不读取字体正文。
- 启动验证针对实际挂载内容，并围栏到资源修订和运行实例；同实例健康读取复用结论。t075 继续完成最低字形/过滤后能力与实际渲染证明。
- 显式审计发现损坏则撤销可用性并阻止新启动，绑定状态不能伪报已验证；受控修复以新修订恢复。审计迟到结果不能覆盖已修复资源。
- 不支持绕过发布者直接修改正式资源。删除“任意宿主篡改后下一次 GET 立即扫描发现”的旧读契约，保留显式审计的可证伪检测能力；不靠 TTL/mtime 猜内容未变。
- 现有 t053/t041 历史 AC 不回写；新 ADR 说明替代关系。失效测试整体处理并注明原因，不就地把原预期改为新输出。

## 网络策略与故障边界（t082）

- 每个目标 netns 的策略 Agent 随目标生命周期常驻，通过精确 Docker ID 加入目标 netns；不需要 host PID/SYS_ADMIN/任意 setns。先验证能力，不能为实现方便默增权限。
- 实际规则与预期采用同一 DNS/策略修订；真实检查保留，普通 inspect 不拉起容器或 docker exec。
- 漂移检查/安全隔离预算为 30 秒。Browser 确认双栈 DROP；无法确认则由 Supervisor 围栏暂停精确目标。Agent 不可用不能当合规，也不能无限留在未知且不执行已定义隔离。
- 只恢复由本机制暂停、规则已重新验证且仍为当前运行意愿的目标；用户主动暂停/停止、新实例不被旧回执恢复。既有 API 离线保留 Browser 语义不变。
- Stream 漂移走已有有界 Stream-only；用户主动代理探测仍可创建短生命周期探针，不池化代理容器，不将其混入无操作稳态窗口。

## 控制与健康职责（t083）

- Supervisor 消费最小状态和变化通知，按批次对齐；本地 tick 推进截止时间，不遍历 N 个 HTTP。
- 正常意愿变化 5 秒内进入协调；通知遗漏通过 30 秒兜底与单轮处理恢复；恢复不假定现有内存 SSE 为持久日志。
- UI runtime、列表和 SSE 是已有观测投影；普通读取无同步 RPC、字体正文读取、Docker 操作或清错副作用。
- API 协调器通过内部 HTTP 观察 Supervisor；Supervisor 通过 HTTP 观察 API/Gateway；健康请求返回已有结果，不互相同步调用。服务死亡/假活按截止时间变为未就绪，不增加自动破坏 Browser 的行为。
- Docker Python healthcheck 的移除必须与启动/readiness/回退等待一同完成；service_started 或固定 sleep 不能替代 ready。

## task 分工、依赖与冲突

|task|单一交付|硬依赖|与既有 task 的职责边界|
|---|---|---|---|
|t080|Linux 原生存储及可恢复迁移|无|替代 t075 旧宿主同路径挂载技术方案；Profile 删除业务意愿仍归 t078|
|t081|字体发布/审计/目录元数据与实例验证|t080|不重复 t075 的 GPU/CJK/locale/配色与渲染能力验收|
|t082|常驻最小权限网络策略执行/观测|t080|保留已有出站安全与 Stream-only 语义；不改前端状态文案|
|t083|最小状态协调、健康职责与联合稳态验收|t081、t082|不重复 t076 的列表分页/候选/代理引用查询|
|复用 t075|运行身份、最低字体能力与真实渲染就绪|新增 t081|原 AC-001–009 保留；资产来源改为 t080/t081 受管引用|

t081/t082 没有虚构数据依赖，但共享 DockerAdapter、镜像/release 和蓝图修改，登记并发冲突。t075/t076/t078 与新任务共享模型、生成协议、路径或生命周期代码，冲突通过 task.py 字段表达，不为排序方便全部串成硬依赖链。原 t077/t079 的 UI 行为仍由原队列负责；通过已有冲突与依赖连接，不扩写无关 UI 范围。

每个 task 一个有工程意义的实现 commit，全部 full review。创建期只维护本批 task，长期 specs/blueprint/ADR 在对应实施 finalization 更新；新 task 不提前写成生效长期真相。

## 联合验收与证据合同

- 创建期只验证结构/门禁；业务 AC 全部保持未勾选。正式 spike 在实施期通过工具创建、入 findings 并回填结论，不把创建通过当作外部能力验证。
- 4 个隔离真实 Profile，使用真实字体、生产 Compose、容器化 Supervisor 和官方 Chrome；先完成暖机，再取连续 10 分钟无人工变更窗口。
- 确定性门禁：API 字体正文读取/哈希为零，临时 policy 创建/销毁为零，正式栈巡检/健康 docker exec 为零，运行实例不重启；用户数据/页面/下载结果正确。
- CPU、rchar、read_bytes、dirty writes 各按定义记录完整样本。比较窗口、镜像、活跃 Profile、网页内容、Viewer/前后台状态一致；不要求没有依据的固定 CPU 百分比或声称 SSD 物理写入归零。
- Docker exec_create 按实际 exec ID 计一次，start/die 是阶段；测量器命令单列。基础设施 healthcheck 是产品开销，不能假称测量噪声扣除。
- 把策略漂移、Agent 失败、API/Gateway/Supervisor 重启、通知丢失、单 Profile 慢响应分别置于故障窗口，记录恢复与安全结果，不与无变化零 churn 窗口混算。
- OrbStack 日志按本轮容器 ID 与时间关联，无法读取就记录未观测，不用“无日志”推导零错误；历史跨项目总数仅作背景。
- 0/1/100/1000 条元数据验证批量 HTTP/SELECT，不创建 1000 个 Browser。已有首帧/输入/SQLite 门禁阈值保持。
- 本批各 task 都运行相应项目门禁；联合稳态验收归 t083，不另建只有报告而没有实现结果的测试任务。

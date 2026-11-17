# Task spec

## 背景

内部 supervisor runtime GET 直接复用 UI 聚合处理函数，读取时同步刷新 transport/search-defaults 并扫描字体。RecoveryCoordinator 每轮先列全部 Profile，再逐个请求 runtime。现场另一个 60 秒窗口出现 107 次内部 runtime GET。recovery.tick 的健康读取走 UDS，并不直接 docker exec。

采样排除测量器命令后，约一分钟 42 次实际 exec 中，34 次来自三个服务的 5 秒 Docker healthcheck，8 次来自巡检代理 DNS。t081/t082 分别消除重型字体读取和策略/DNS churn；本 task 交付最小状态协调、纯读取投影及联合稳态闭环，明确包含健康责任迁移，不能只修一处就宣称整个控制面安静。

## 契约区

### 范围

- 定义独立、服务鉴权的 Supervisor 最小批量状态 DTO/接口，仅含意愿、绑定实例/配置、终态事件和重试/封锁所需字段及一致性围栏；不复用 ProfileRuntimeResponse，不含字体覆盖、transport、search-defaults、control 或 UI 信息。core/control_server/recovery 等旧内部逐 Profile runtime 消费方一并迁移，删除旧路由。
- 使用既有持久意愿和事件设施完成初始快照、按变化失效/增量刷新、重连及 30 秒完整兜底；内部通知使用服务鉴权，不挪用用户会话或另造通用事件平台。API epoch/修订、实例/配置围栏处理快照与事件竞争，未读完/版本冲突不能充当完整权威。
- 集合读取按明确上限分批，DB往返按批次增长；无变化 steady tick 只推进本地到期重试和脏 Profile，不每秒发起 N 个 HTTP。失败有界退避，重连只有一个在途快照，避免请求风暴。
- runtime GET、列表投影和 SSE 组装只读取已维护结果；transport/search-defaults/Agent/字体观察由有界后台更新，普通 GET 不串行下游 RPC，不形成 API→Supervisor→API 聚合依赖环。观测含实例/修订/新鲜度；未确认不报 ready，读取不清错误、不改意愿、不重建容器。
- 保留 Docker/网络事件和 30 秒拓扑兜底；策略观测、事件/下载转发、到期重试与基础设施健康各自有界，单 Profile 慢操作不阻塞其他 Profile 停止、事件重放和健康读取，复用已有锁/错误契约。
- 将 API/Gateway/Supervisor 周期健康观察移到既有控制组件的 HTTP/UDS，移除 Compose 5 秒启动 Python 的 Docker healthcheck。Compose 依赖与 deploy/rollback 等待统一为有截止时间的真实 readiness，不用固定 sleep 或仅 service_started 代替就绪。API 协调器观察 Supervisor，Supervisor 观察 API/Gateway；健康读取返回已有观测，不互相同步探测形成死锁。
- unknown、服务假活/挂起、API离线在 release readiness 显式未就绪；保留 API离线健康 Browser 不被 teardown、正常退出不误重启、Native退出优先、退避/封锁和 Stream-only 修复语义。健康读取失败本身不新增任意自动生命周期动作。
- 把生产逻辑稳态探针纳入本次交付：记录 API I/O/CPU、字体正文读字节/哈希、内部 HTTP/SELECT、Docker生命周期/exec、策略修订及 OrbStack日志ID关联；覆盖4 Profile/10分钟和0/1/100/1000元数据，测量器自身 exec 单独标记。
- 同步内部协议/schema/生成类型及 readiness/操作指南；t076 继续负责 UI列表分页/候选/引用，本 task 不复制产品查询接口，SSE/投影共享修改通过任务图串行。

### 非范围

- 不引入 Kubernetes、独立消息队列、第二查询 DB 或通用调度框架；不要求 1000 个真实 Browser 同时运行。
- 不以延长间隔、放宽超时、屏蔽日志、把哈希移到线程或缓存旧ready布尔值交付；不承诺正常浏览器写入、macOS dirty writes或SSD I/O归零。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：Supervisor 初始恢复、周期协调、控制操作和退出重试只用最小批量状态协议，旧内部 UI聚合 runtime 路由不存在；鉴权、错误、缺失 Profile 与实例围栏严格校验。
- [ ] AC-002：稳定无变更 tick 不触发逐 Profile HTTP；完整状态对齐不超过每30秒一轮，0/1/100/1000状态下每轮 HTTP/SELECT 按声明批次增长，无N个独立runtime GET或逐版本查询。
- [ ] AC-003：正常变更通知下，启动/停止意愿5秒内进入协调；丢通知/断连后在下一30秒兜底及一轮处理内恢复。API重启/修订重置、快照竞争和迟到旧实例事件不覆盖新状态或误执行生命周期动作。
- [ ] AC-004：普通 runtime GET、状态列表投影和SSE组装不执行同步下游RPC、字体正文读取/哈希或Docker操作；报告当前绑定实例有效观测，未确认项标未知，读取不清错误、不改意愿。
- [ ] AC-005：单Profile慢响应或不可达Agent不阻断其他Profile到期重试、停止和健康推进；API断线保留既有Browser，恢复后正常退出只结算一次且不误重启，既有退避/封锁不变。
- [ ] AC-006：三个服务稳态健康检测不产生Docker exec；未就绪、假活、挂起、不可达在声明截止时间内变为未就绪，部署/回退不因进程已启动就宣布成功。
- [ ] AC-007：启动/重连只有有界在途快照和探测，无每Profile重试风暴；重复/重放通知不造成额外生命周期动作，重连后状态与持久权威一致。
- [ ] AC-008：全后台、无Viewer时健康环境继续运行；打开/关闭UI或读取更多详情不增加控制循环字体审计、策略临时建毁或Docker exec，既有媒体/交互验收阈值不放宽。
- [ ] [deploy] AC-009：4个隔离真实Profile稳态10分钟，正式栈产生的policy临时建毁、巡检/健康Docker exec、API字体正文读取均为零；实例不重启，Cookie/localStorage、页面、下载完整，计数与测量器开销可复核。
- [ ] [deploy] AC-010：同一隔离栈分别注入API/Supervisor/Gateway重启、事件丢失、策略漂移和单Profile慢响应，业务/安全恢复及计数边界均满足；保存CPU/rchar/宿主日志前后样本，仅按本轮容器ID归属OrbStack错误，缺日志不冒充零错误。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- 全部AC可自动测试；[deploy]必须穿过隔离真实Docker/Chrome/固定引擎。正式环境测量不能被mock、skip或历史证据替代，创建授权不包含生产发布。

## 上下文区

- 关联 spec：docs/specs/runtime_lifecycle.md
- 受影响 spec：docs/specs/runtime_persistence.md、docs/specs/gate_verification.md、docs/specs/release_deployment.md、docs/specs/profile_management.md；finalization同步。
- 来源：2026-11-18用户现场报告、同会话只读核验及详细立项授权；脱敏事实、指标口径与职责见docs/tasks/t080_linux_native_runtime_storage/architecture_scope.md。t076负责前端请求放大，本task负责服务端协调，不能互相替代验收。

### 有意不测

- 用户生产栈停止/重启/发布与真实账号内容：不执行，以隔离真实部署和合成状态完成。
- 公网/TURN/原生Linux x86_64实机沿用既有验证边界，不标记为PASS，不把元数据规模替代真实沙箱容量。

### 测试策略

- 通过真实内部HTTP和生产SQL监听建立旧N+1/rich DTO/GET→RPC红测试；使用注入clock验证调度和截止时间，不patch标准库time或仅靠长sleep证明。
- 真实API/独立Supervisor覆盖bootstrap、分批快照、epoch/修订、重连/重复事件、绑定新旧版本、删除/创建竞争、API离线、Native退出优先及封锁；计数排除造数阶段。
- 对读取helper装配拒绝执行的RPC/hash/Docker spy，验证REST/SSE/列表及重连快照均不进入重型路径；t076查询/SSE产品测试复用其真实交付，不创建第二套投影。
- 正式稳态探针用生产Compose、容器化Supervisor、真实字体和Chrome；暖机与10分钟窗口分开。exec_create代表一次执行，exec_start/exec_die为阶段事件，不能累加成三次；测量器、人工操作、显式代理探测单列，业务健康检查不得静默扣除。
- 保留首帧/输入/SQLite硬阈值。以零冗余I/O/churn计数作确定性门禁，CPU/rchar/read_bytes/dirty writes保留原始口径与分布，不设没有基线的固定CPU百分比承诺。
- 使用scripts/run_gates.sh及CBROWSER_RUN_E2E=1 scripts/run_gates.sh，按testing.md保留脱敏证据、完整命令、镜像身份、退出码与本轮资源范围。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无新增未核实第三方协议。epoch/修订、通知和快照属于本task自有契约，须通过真实进程重启/故障注入验证；现有内存SSE不能被假定为持久事件日志。
- 4 Profile/10分钟CPU和物理I/O基线尚未建立；rchar为逻辑读取，不能视为VirtioFS实际流量/SSD读取。该未知不阻塞零正文读取、零policy临时建毁、零稳态exec的确定性行为验收。

### 风险与回退

- 风险：快照竞争回填旧实例；最小DTO漏字段破坏退出/恢复；健康互相同步调用导致假死；仅删Docker healthcheck而未补readiness会让发布误报成功。
- 回退：隔离服务和真实栈先验证新协议/健康职责，失败回退匹配release与状态schema；不同时保留旧rich内部路由或每秒逐Profile轮询。生产发布须另行明确授权，健康unknown不自动拆除健康Browser。

### 依赖与约束

- 硬依赖t081与t082：分别提供只读资产投影/实例验证和无churn策略观测，传递依赖t080。
- 与t075/t076/t078共享运行模型、SSE、内部状态及生命周期，登记冲突而非虚构数据依赖；t076负责列表产品行为，本task统一观测写入和读取纯度。
- 4 Profile/10分钟联合验收属于本task实现交付，不另建空泛测试task；安全、并发、跨服务协议使用full review。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：最小内部状态、纯读投影、快照/变更及健康职责。
- `docs/blueprint/supervisor.md`：批量恢复、有界调度、增量/兜底和故障边界。
- `docs/blueprint/domain.md`：观测围栏、新鲜度、epoch/修订和最小协调字段。
- `docs/blueprint/testing.md`：稳态计数、4 Profile/10分钟、元数据规模和故障矩阵；同步关联specs与替代旧内部聚合读取的ADR。

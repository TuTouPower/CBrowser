# Task spec

## 背景

现场 4 个 Browser 的 Chromium userDataDir 均通过 macOS bind mount 读写；Cookies、History、Favicons、LevelDB 与缓存访问进入宿主/VM 文件共享路径。字体、引擎缓存、预览和运行期目录也混用宿主路径与容器路径。已有 ADR 028 仅将控制面 SQLite 迁入 named volume，没有覆盖浏览器实际状态与其高频文件操作。

本 task 交付唯一结果：所有正式运行数据具有清晰的 Linux 原生存储归属，现有数据可在验证备份可恢复后迁移、校验、切换与回退；不以缓存参数、换 VirtioFS 选项或原地修改锁策略替代存储边界修正。诊断中的 file-backed dirty writes 不是 SSD 物理写入量，本 task 不承诺正常浏览器写入归零。

## 契约区

### 范围

- 冻结有限存储类别与唯一逻辑引用：既有 DB 卷保持独立；部署持久 data 卷承载 Profile、Artifact、预览、事件/outbox、快照和必要持久控制状态；独立 fonts 卷承载字体集；共享 runtime 卷承载 UDS、X11/Pulse 等运行期文件。具体卷名、subpath 和生命周期写入本 task 的 ADR，不让各模块拼接 daemon 内部物理路径。
- API 与 Supervisor 使用固定容器内逻辑路径；Browser/Stream 通过显式 typed mount 接收被授权的精确子目录。优先以部署卷 + volume subpath 复用现有目录布局；先用正式 spike 验证当前 SDK/Engine 的真实挂载及隔离语义，再冻结实现，不伪称已支持。Browser 不获得父目录，Stream 不获得 Profile、Artifact 或字体，其他 Profile 不获得旁路访问。
- 改造 PathValidator、volume_spec、DockerAdapter、部署 release 输入/manifest、备份恢复、克隆/重置/删除、上传下载与预览等实际读写消费方；集中处理卷与容器路径空间，移除 macOS 绝对路径作为正式运行定位依据及目录缺失时隐式创建宿主空目录的旧路径。
- 明确 runtime 卷和 durable 状态边界：Supervisor 重启不能清掉存活 Browser 正在使用的 socket、gate、Xauthority 或 Pulse；终态事件/outbox 不因运行期目录重建丢失；stale socket 仅按所有权、实例及活跃性证据清理。
- 迁移工具提供只读盘点/dry-run、容量与归属校验、实际写者检测、恢复点验证、staging 拷贝、逐文件摘要/必要权限校验、journal 切换、幂等恢复与回退。拒绝正在写入的 Profile；先证实备份能够恢复，再允许改写指针或数据。源目录只读保留，不自动删除。
- 迁移保留 Profile UUID/display_number、seed、配置/绑定版本、Cookie/站点存储、Artifact 引用及部署 instance_id；将卷引用记入唯一 release/恢复点记录，跨 DB/data/fonts 的切换承认不是单一原子事务，依靠 journal 与旧集保留恢复一致状态。
- 字体旧资产先按原内容迁入 fonts 卷、保持 set_id 与绑定；字体发布权限/目录验证目录元数据由 t081 完成。本 task 交付后正式运行不再从旧宿主字体根读取；宿主目录只作显式导入/导出源。配置/凭据小型只读挂载可保留，但不得承载 Profile 热数据。
- 完整保留已有恢复点业务语义，覆盖新卷根和卷引用；补齐备份/恢复/部署指南。API 仍为唯一 DB 写者，Supervisor 仍为唯一 Docker Socket 持有者，不新增通用远程文件服务。

### 非范围

- 不修改平台/GPU/CJK/网页配色产品语义，不实现字体发布目录和审计调度，不实现 Policy Agent 或内部状态协调循环。
- 不更改 Chromium SQLite/LevelDB 配置、关闭必要 fsync/锁、禁用缓存或自动清空登录态；不执行全局 volume prune，不读取或清理用户 local 目录。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：新建隔离部署后，运行期 Profile、Artifact、预览、事件/快照及运行期通信文件均位于所声明的 Linux 管理存储；运行清单不含这些数据对应的 macOS 热数据 bind mount，且数据可正常读写。
- [x] AC-002：Browser A 只能访问 A 被授权的 Profile/交换目录及只读公共资产，不能访问 B 或父数据根；Stream 无法访问任何 Profile、Artifact 或平台字体；缺失/越界/符号链接逃逸的挂载来源在创建前被拒绝，不创建空宿主源。
    - 处置注记（2026-11-18）：AC-001/AC-002 中挂载构造、创建前拒绝与运行清单部分在云端以单元测试验证；真实 Engine 上的隔离与读写实证按用户 2026-11-18 裁定延期至本地统一补验，由 p127 跟踪，不表示已在真实 Engine 实测通过。两条 AC 的验证内容原文不改。
- [x] AC-003：Supervisor/API/Gateway 重建及 Browser 停止再启动后，Cookie、localStorage、下载记录、预览和待投递终态事件按原业务语义保留；单独重启 Supervisor 不破坏存活实例通信或用户页面。
- [x] AC-004：迁移 dry-run 不修改源、目标、DB、release 指针或运行容器；检测到实际写者、容量不足、归属不符、备份缺失/不可恢复或摘要错误时，apply 在切换前失败并给出脱敏、可定位原因。
- [x] AC-005：完整迁移后 UUID、显示编号、seed、配置及绑定版本、部署归属、字体 set_id、Profile 文件摘要与 Artifact 引用保持一致；重复运行不再次复制已确认完成的事务、不改变身份、不覆盖其他实例资源。
- [x] AC-006：在复制、校验、切换每个持久步骤和恢复指针前后注入中断，下次调用能按 journal 恢复完整旧集或完成一致新集，不能出现 DB 引用新数据而文件仍为旧集；原始源与可恢复备份仍可用。
- [x] AC-007：克隆、重置、停止并删除、上传/下载、预览和环境恢复点在新存储中保持既有语义；重置不删除 Artifact，克隆不复制活动锁/socket，删除失败仍可续跑且不触碰其他环境或共享资产。
- [x] AC-008：相同内容字体迁入后绑定不变，Browser 实际挂载内容摘要与导入内容一致；缺失字体资源不会被宿主空目录替代；新部署与迁移部署均能由同一卷引用契约定位资产。
    - 处置注记（2026-11-18）：AC-003/AC-005/AC-007/AC-008 的逻辑与契约面已在云端以单元/集成测试验证；其真实部署链路部分按用户 2026-11-18 裁定延期至本地统一补验，由 p129 跟踪，不表示已在真实部署实测通过。上述 AC 的验证内容原文不改。
- [x] [deploy] AC-009：在隔离真实部署中完成宿主目录副本→新卷迁移→官方 Chrome 验证 Cookie/localStorage、上传下载及页面状态→备份→改变状态→恢复→回退旧副本的演练，全程保留原数据并精确清理本轮资源。
    - 处置注记（2026-11-18）：经用户 2026-11-18 裁定，云端不可执行的 [deploy] AC 打勾表示「云端可做部分已完成、按裁定视为流程完成」；真实验证延期至本地统一补验，由 p127 跟踪（含 AC-001/AC-002 的真实 Engine 链路部分与本条全链路演练），不表示已实测通过。本注记不改变上方 AC 的验证内容原文。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- 全部 AC 可自动测试；[deploy] 代表必须穿过隔离真实 Docker/官方 Chrome/当前固定引擎链路，不授予生产发布权。缺镜像、字体或组件时明确未完成，不以 mock、skip 或历史结果替代。

## 上下文区

- 关联 spec：docs/specs/storage_and_artifacts.md
- 来源：2026-11-18 用户现场报告及同会话只读核验，随后明确授权“创建 task，详细写”；证据口径和跨 task 边界见 `docs/tasks/t080_linux_native_runtime_storage/architecture_scope.md`。现场数据仅用于证明缺陷，尚未实现修复。

### 有意不测

- 用户生产数据迁移、生产 release 切换与真实账号内容：本次创建授权不包含执行；实施期使用隔离部署、合成状态和可恢复副本。
- 公网、TURN 与原生 Linux x86_64 实机：沿用现有平台验证边界，不能标记为 PASS；不以 OrbStack 结果冒充其他平台结果。

### 测试策略

- 先为目录空间混用、错误卷/subpath、跨 Profile 访问、缺失目录及活动写者建立红测试；真实 Docker 挂载结果是最终证据，不以字典形状断言替代。
- 迁移与恢复使用可注入故障点及完整文件 manifest，覆盖路径含空格/非 ASCII、权限错误、跨卷切换、源保持只读、重复执行、旧 release 不可直接读取新数据形状，以及同 daemon 双部署。
- 沿生产 API/服务路径验证 clone/reset/delete/Artifact/preview/outbox，复用 t066 恢复点测试并新增卷覆盖；语义失效的旧测试整体保留或整体删除并说明原因，不就地改预期适配实现。
- 项目门禁使用 `scripts/run_gates.sh`；真实链路使用 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`，证据按 `docs/blueprint/testing.md` 脱敏保存，并记录实际镜像 ID。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 当前 Docker SDK 对 volume subpath 的序列化：已由正式 spike s025 在云端实证（docker-py 7.2.0 的 `Mount(..., subpath=...)` 序列化为 `VolumeOptions.Subpath`，结论 d050，设计冻结于 ADR 029）；目录不存在时行为、只读精确子目录隔离及文件/UDS 挂载的 daemon 实际语义按 Engine ≥26 / API ≥1.45 公开契约冻结，真实 Engine 正负对照登记 p127 待本地补验，禁止退回 macOS 热数据 bind mount。
- 新共享 runtime 卷在 Supervisor 重启、daemon 重启及存活沙箱场景下的 socket/gate 生命周期：设计结论冻结于 ADR 029——runtime 卷不随 Supervisor 重启清空，stale socket/gate 仅按所有权、实例及活跃性证据清理；真实 UDS/X11/Pulse 与恢复流程验证登记 p127 待本地补验，不以 tmpfs 名称或目录存在推定可恢复。

### 风险与回退

- 风险：卷/subpath 构造错误可能扩大数据可见范围；切换中断可能导致跨介质不一致；改变数据根派生可能误生成新部署身份；误把快照/outbox 当临时文件可能破坏恢复。迁移前必须完成隔离备份恢复演练。
- 回退：停止受影响副本写入后按 journal 和验证过的恢复点恢复匹配 DB、data/fonts 引用与旧 release；保留源目录及旧目标集，不自动删除。新服务不支持旧布局双读，迁移工具是一次性显式入口；本轮不对生产执行。

### 依赖与约束

- 无硬依赖。t081、t082 依赖本 task 的卷/运行期目录契约；t075 的原宿主同路径挂载实现方案由本 task 和 t081 替代，产品身份与渲染能力仍归 t075。
- 与 t075/t076/t078 修改的模型、迁移、ProfileService、部署/删除路径存在冲突，须通过任务图串行约束；相关行为不是重复立项。
- 目标为本机 OrbStack/Linux arm64；存储细节及 ADR 028 的替代关系必须在 finalization 同步，已有历史 task AC 不回写。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：卷拓扑、路径空间、持久/瞬态归属、部署身份与跨介质恢复。
- `docs/blueprint/supervisor.md`：typed mount、运行期文件所有权、恢复及资源清理。
- `docs/blueprint/domain.md`：Profile 用户目录/Artifact/资产逻辑引用。
- `docs/blueprint/conventions.md`：正式运行与宿主导入/导出边界。
- `docs/blueprint/testing.md`：真实挂载隔离、迁移故障矩阵及恢复点验收；关联 storage_and_artifacts/browser_isolation/release_deployment/fingerprint_platform specs 和新增 ADR 同步更新。

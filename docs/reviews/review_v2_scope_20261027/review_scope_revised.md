# CBrowser v2.3 架构规划与 Task 契约覆盖度独立评审报告（第二轮·修订复核）

## 评审结论 (Verdict)

### **双维度裁定结果**：

1. **文档与契约覆盖度判定 (Document Coverage & Contract Review)**：**PASS**
2. **工程实现状态与执行门禁判定 (Implementation Gate & Operational Status)**：**GATED / OPEN（实现进行中，正式架构尚未冻结）**

### **判定理由与关键事实**：

1. **契约覆盖度全项闭环 (Contract PASS)**：
    本轮对已修订的 14 个 Task 契约及架构规划进行了逐项核验。初审报告指出的 11 项缺陷与范围缺口已全部得到妥善处置与纠正：
    - 具名文件与结构（`src/backend/diagnostics.py` 结构化日志、`config/docker/entrypoint.sh` 真实 VNC/进程残留清理、`/data/engine-cache/` 统一挂载）已完整纳入范围与契约，未臆造无意义的 API 缓存写者；
    - 运行时模型恢复字段（`failure_count`, `restart_blocked`, `last_exit_event_id`）与 Gateway 连接活动聚合协议（`t006` AC-007）完整就位；
    - CPU 过载削峰降帧责任链路清晰打通：由 Supervisor（`t005` AC-007）采集负载并下发限额，Stream Runtime（`t004` AC-003）动态降低 Profile FPS，未引入未经规划的数值阈值；
    - 依赖、配置、路径与版本（SQLite WAL、`busy_timeout=5000`、`/dev/shm 1GiB`、Xvfb 扩展、Selkies 2.1.0 commit hash）严格按 AGENTS.md 规范置于【范围】与【依赖与约束】（上下文区），未将底层技术选型及配置值充当行为 AC；
    - 原 `t008` 成功拆分为 `t008`（文件与自动化）、`t013`（Profile 复制与重置）、`t014`（受控剪贴板与组合输入）三个独立交付 Task，彻底纠正初审关于“任务内多 commit 提交”的违规建议，满足“单个 Task 执行期仅一个实现 commit”红线；
    - 架构规划全部 58 个需求点在 14 个 Task 契约中达成 100% 映射覆盖（57 项 FULL，1 项 GATED/OPEN），无需求丢失，无未经批准的臆造特性。
2. **第一阶段技术门禁严守未闭环状态 (Hard Gate OPEN)**：
    必须严格区分**契约文档覆盖度达标**与**生产实现完成**。作为第一阶段技术验证的 `t001_v2_runtime_validation` 仍处于 `active` 状态：
    - 6 项验收标准中，AC-002、AC-003、AC-005 已闭环，但 **AC-001 (PulseAudio 采样偏差 404/808Hz 未定位)、AC-004 (真实公网 candidate 与公网 relay-to-relay 未完成)、AC-006 (原生 Linux x86_64 16vCPU/32GiB 实验未运行)** 仍处于 OPEN 状态；
    - **本评审仅证明 14 个 Task 契约具备完备性与可开工规格，绝不代表生产功能已通过验证**；
    - 在 `t001` 全项 17 个技术实验独立复核通过前，正式架构不得冻结，后续正式代码重写（`t002`–`t014`）一律保持阻塞，严禁提前 start 或合并。

______________________________________________________________________

## 1. 冻结输入资产校验和 (Source Hashes of Inputs)

本轮审计基于严格冻结于本地 `.scratch/plan_scope_review_r2/inputs` 的 29 份权威文档与 Task 契约：

|资产文件路径|SHA-256 校验和|属性与状态|
|---|---|---|
|`inputs/v2_architecture_plan.md`|`0dd1a8677527717c08d60df1391805aa141a46bb7a350ae729bf046933c981d0`|权威架构规划基准（1104 行）|
|`inputs/t001_v2_runtime_validation/note.md`|`35b9efe80e0446d84bf016e13353efc6c8b2ead3a4dd58a12c220e1926283896`|登记 Active Worktree 账本 (Active)|
|`inputs/t001_v2_runtime_validation/task.md`|`396a97561c6463ed9514c17f66503b0589b13c1b50577810126664f464cbe035`|登记 Active Worktree 契约 (Active)|
|`inputs/t002_v2_backend_foundation/note.md`|`244e5fb2ed75599c69bad294cbe77cc5b72b9a86cb3e5f544a36f1f0dcba3ac7`|R2 修订总账 (Backlog)|
|`inputs/t002_v2_backend_foundation/task.md`|`673696cb23e84c57c8b9126b8e43c6cadba29b35f626b84e4eac64d016afc9fa`|R2 修订契约 (Backlog)|
|`inputs/t003_v2_browser_runtime/note.md`|`b6d46aee575636e4acab89fb522bc181cf37d82fa453bfab416f05dfbafb757e`|R2 修订总账 (Backlog)|
|`inputs/t003_v2_browser_runtime/task.md`|`242e913f89b7c3ac8e448a23354154f03c052ab6af55d5039996618c34f93677`|R2 修订契约 (Backlog)|
|`inputs/t004_v2_stream_runtime/note.md`|`91a6c3feae86f3155eaa1edb4fca39da0237c0c6379f4c76023d7129da0b261a`|R2 修订总账 (Backlog)|
|`inputs/t004_v2_stream_runtime/task.md`|`cf14c3cf720f74d33381ec0ba0d69926073d97bd58d030e912c58e50807b3dfc`|R2 修订契约 (Backlog)|
|`inputs/t005_v2_supervisor/note.md`|`a45902fb29ff99e472e4d02c9e511ad9d381a8675570d6d0f823e887084224da`|R2 修订总账 (Backlog)|
|`inputs/t005_v2_supervisor/task.md`|`93b7fae0d4392481615f5081bd3de63d768c661973eed27656496c103029e613`|R2 修订契约 (Backlog)|
|`inputs/t006_v2_gateway_auth_rtc/note.md`|`3ece36bc5918d1f9a24520ee53dd6c591a8771eaef978897e4aa8cb788dae66d`|R2 修订总账 (Backlog)|
|`inputs/t006_v2_gateway_auth_rtc/task.md`|`64e03b826bc45be4bf527ecddcd50585d0669fa492dd80fc62864c0a72f099b0`|R2 修订契约 (Backlog)|
|`inputs/t007_v2_frontend_sessions/note.md`|`988c09399c2194c1db269e88840dacb29a5c02f9c1cfce0f9d608f96aef3a14e`|R2 修订总账 (Backlog)|
|`inputs/t007_v2_frontend_sessions/task.md`|`5ca8f1b5fc79e98cdec2cea22ed9d2d5b8d97d8b1754e7f8eca4428b270ec3a8`|R2 修订契约 (Backlog)|
|`inputs/t008_v2_artifacts_automation/note.md`|`8afbb5177e7b74ee500b5ef39ea30320d2c7cf76c1a33f1a71416c749460746c`|R2 瘦身后总账 (Backlog)|
|`inputs/t008_v2_artifacts_automation/task.md`|`26d87945990ef003e1c99c7e389c2d4e612b5facbf8b59267eaa18a3fc87de29`|R2 瘦身后契约 (Backlog)|
|`inputs/t009_v2_full_acceptance/note.md`|`7100d516d16cd4600d5d233bde07700f8eedf850261469129ae8799b81c54a69`|R2 修订总账 (Backlog)|
|`inputs/t009_v2_full_acceptance/task.md`|`e2edb1d8fb7b6bd65077f1653a6c5fe608c513522bb207d4e4cdb4fe24ec9244`|R2 修订契约 (Backlog)|
|`inputs/t010_v2_data_migration/note.md`|`9193f2f781a4a6a679f6961f770057771568b4b6df8343612b732c76359dc37a`|权威数据迁移总账 (Backlog)|
|`inputs/t010_v2_data_migration/task.md`|`848665e2c15f444183086620289c86435f39b8302bddaee29015021e91533c5c`|权威数据迁移契约 (Backlog)|
|`inputs/t011_v2_remove_legacy/note.md`|`35515f8cdbc193fe9a590d59cebd06b3ae2e2edd883a9368dd32eac99a03af60`|R2 修订总账 (Backlog)|
|`inputs/t011_v2_remove_legacy/task.md`|`5f1e117d4c422e7274f19b16571cb5e60e9f5842cea860226691577f8427f0eb`|R2 修订契约 (Backlog)|
|`inputs/t012_v2_docker_release/note.md`|`82e3b50cdbdc7ef0622a3885d2367ca0beef0baf54b1b0487c5bba1c6def8d85`|权威发布总账 (Backlog)|
|`inputs/t012_v2_docker_release/task.md`|`f5ab6351eed99c36c46e6ad48e78eea1106151e237634e137f3828a4998a6103`|权威发布契约 (Backlog)|
|`inputs/t013_v2_profile_copy_reset/note.md`|`ca5c3f2d82f59738ac5fcdeab188006f85e5a12d1c0cb07482c651348a8a8bf7`|R2 新增独立总账 (Backlog)|
|`inputs/t013_v2_profile_copy_reset/task.md`|`daf68776675afc29f0513c733ebe313558d303ac24ccb7fe7e15492005a13532`|R2 新增独立契约 (Backlog)|
|`inputs/t014_v2_clipboard_input/note.md`|`007f607aa9e538d68ed4200d1efb5f7f7a9a4d14e1d87d20f50788b8301c73ef`|R2 新增独立总账 (Backlog)|
|`inputs/t014_v2_clipboard_input/task.md`|`e1ed5f57d52aa792118f55c668983d5d82c35f4342c707cdca673cd9758d9935`|R2 新增独立契约 (Backlog)|

______________________________________________________________________

## 2. 初审 11 项缺陷处置逐项复核 (Evaluation of the 11 Dispositions)

下表对初审报告所列全部 11 项缺陷的处置方案进行逐一技术复核：

|缺陷编号与名称|初审识别问题|R2 处置方式与具体位置|规范对齐与技术实质评估|复核结论|
|---|---|---|---|---|
|**缺陷 1：`diagnostics.py` 改造遗漏**|规划第 17 章具名保留并增加结构化运行时日志，各 Task 遗漏|`t002` 范围加入 `src/backend/diagnostics.py`，新增行为 `AC-006` 断言日志机器解析、Profile/实例/事件关联与敏感信息脱敏|行为与范围分离。行为 AC-006 专注可观察诊断输出与敏感信息防护，符合 AGENTS.md 规范|**有效闭环 (PASS)**|
|**缺陷 2：`entrypoint.sh` 旧 VNC 清理遗漏**|规划第 17 章要求删除旧 VNC 和清理逻辑，`t011` 遗漏|`t011` 范围与 `AC-002` 显式加入 `config/docker/entrypoint.sh` 旧 VNC 与遗留进程清理逻辑移除|实际代码核验显示文件含 `pkill -f 'Xvnc :[0-9]'` 等逻辑（非初审误称的 x11vnc），处置精准对齐实际源码|**有效闭环 (PASS)**|
|**缺陷 3：`/data/engine-cache/` 目录契约**|规划第 3.3 节具名引擎缓存目录，各生命周期未纳入|`t003` 范围声明缓存遵循统一数据根 `/data/engine-cache/` 且与用户数据隔离；`t005` 范围声明初始化与挂载权限|引擎缓存属运行时共享资源，由 Supervisor 挂载并由 Browser 访问，未臆造无依据的 API 缓存写者，职责清晰|**有效闭环 (PASS)**|
|**缺陷 4：Gateway 连接活动聚合协议**|规划第 9.3 节要求 Gateway 维护活动表并聚合下发 Stream Agent，`t006` 遗漏|`t006` 范围加入连接活动表与聚合协议；新增行为 `AC-007` 断言记录 `connection_id, visible, last_activity, last_heartbeat` 并聚合下发，活跃前台不被后台降需|补充核心信令聚合行为，明确心跳仅作存活与资源统计、不形成控制锁，闭环信令链路|**有效闭环 (PASS)**|
|**缺陷 5：Artifact 返回 `container_path`**|规划第 6.2 节要求 API 返回容器内路径而非宿主物理路径，`t008` 未断言|`t008` AC-001 显式断言 API 返回 Artifact ID 和容器内 `container_path` (`/exchange/uploads/...`)，严禁泄露宿主路径|明确防御宿主路径泄露，保障容器内浏览器与自动化正确寻址|**有效闭环 (PASS)**|
|**缺陷 6：SQLite WAL 与 `busy_timeout=5000`**|规划第 12.1 节要求 WAL 模式与 `busy_timeout=5000`，未在基础契约中固化|置于 `t002` 上下文【依赖与约束】中显式锁定，要求测试实际读取 PRAGMA 并结合并发 HTTP 验证|严格遵循 AGENTS.md“技术选型/配置不写进行为 AC”红线，置于约束区并通过行为验证|**有效闭环 (PASS)**|
|**缺陷 7：运行时状态模型恢复字段**|规划第 12.2 节具名 `failure_count`, `restart_blocked`, `last_exit_event_id`，`t002` 遗漏|`t002` 范围中显式具名数据模型包含该三项运行时恢复字段|消除 `t005` Supervisor 实施时被迫修改 `t002` 数据模型的下游契约摩擦|**有效闭环 (PASS)**|
|**缺陷 8：Browser Runtime `/dev/shm` 与 Xvfb 扩展**|规划第 4.2 节要求 `/dev/shm 1GiB` 及 Xvfb 启用 MIT-SHM/XTEST/XFIXES|置于 `t003` 上下文【依赖与约束】中显式锁定，要求测试实际查询 X 扩展与捕获 XShm 证据|遵循规范置于约束区，杜绝启动参数假象，确保 Selkies 不发生退化至慢速 XGetImage|**有效闭环 (PASS)**|
|**缺陷 9：Selkies 2.1.0 Commit 与标准环境变量**|规划第 1.1 与 8.1 节要求锁定官方 commit `6ee68a7` 及 4 项核心环境变量|置于 `t004` 上下文【依赖与约束】中显式锁定 commit 及 `MODE=webrtc`, `DUAL_MODE=false`, `SHARING=true`, `COLLAB=false`, `FRAMERATE=8,8-30`|规范治理配置参数。约束区完整覆盖上游依赖防漂移要求，行为 AC 专注媒体传输质量|**有效闭环 (PASS)**|
|**缺陷 10：前端 files 与 automation 路由断层**|规划第 13.1 节独立子路由，`t007` 移交但 `t008` 未断言导航与渲染|`t008` AC-001 显式加入 `/profiles/:profileId/files` 页面管理；AC-002 显式加入 `/automation/:profileId` 页面加载与刷新会话保持|`t007` 与 `t008` 职责边界严丝合缝，独立子路由实现与测试断言彻底闭合|**有效闭环 (PASS)**|
|**缺陷 11：CPU 过载削峰降帧责任孤岛**|规划第 19.1 节要求过载按规则降帧，但前置实现 Task 均未承接责任|`t005`（Supervisor）AC-007 承接真实主机/容器 CPU 负载采集与 Profile 级限制下发；`t004`（Stream）AC-003 承接接收限额并降低 Profile FPS|责任明确：Supervisor 负责主机监控与决策下发，Stream Runtime 负责执行编码限额。未臆造非规划的具体数值阈值|**有效闭环 (PASS)**|

______________________________________________________________________

## 3. 任务拆解与提交粒度合规性审计 (Task Splitting & Commit Rules)

### 3.1 纠正初审错误建议

初审报告第 4.4 节曾建议在 `t008` 内部“按文件服务 -> CDP/下载 -> 剪贴板/IME -> 复制重置顺序自测提交”。该建议**违反了 AGENTS.md 与项目全局约定的核心原则**：

> “task 执行期一个实现 commit；创建期和状态维护 commit 分开……每个 commit 必须独立可验证，有工程意义。”

主控未采纳该违规建议，而是采取了完全符合工程规范的重构方案：**将职责过载的 `t008` 拆分为三个各自拥有独立单一执行 commit 的 Task**。

### 3.2 拆分后任务边界与 AC 规范

1. **`t008_v2_artifacts_automation`（文件与自动化）**：
    - 范围：Artifact Service/Repository/API、Supervisor UDS 转发、下载事件入库、受控 CDP 代理、`/profiles/:profileId/files` 与 `/automation/:profileId` 页面及组件。
    - 契约：保留 `AC-001`（上传/下载/路径防泄露/files页面）与 `AC-002`（CDP代理/下载恢复/automation页面）。
    - 规范：移出的原 AC-003、AC-004、AC-005 编号**原样作废不复用**，防止追溯歧义。
2. **`t013_v2_profile_copy_reset`（Profile 复制与重置）**：
    - 范围：承接原 AC-005 拆出的 Profile 配置复制、状态复制（源停止校验、用户数据完整性、Artifact 独立）与指纹种子重置语义。
    - 契约：独立定义 `AC-001` 至 `AC-004`，覆盖纯配置复制、状态复制、重置语义及前端 UI 事务闭环。
    - 依赖与冲突：`depends_on: "t008"`, `conflicts_with: "t014"`。
3. **`t014_v2_clipboard_input`（受控剪贴板与输入场景）**：
    - 范围：承接原 AC-003/004 拆出的 `ClipboardBridge`、浏览器权限提示、必要受控输入 RPC 与完整中文组合输入（地址栏/普通/受控/富文本）。
    - 契约：独立定义 `AC-001` 至 `AC-004`，覆盖剪贴板脱敏与单向性、IME 键盘提交、双页并发输入与独立测试夹具隔离。
    - 依赖与冲突：`depends_on: "t008"`, `conflicts_with: "t013"`。

### 3.3 拓扑图与并发隔离审计 (DAG & Conflict Symmetry)

```text
t001 (Spike, active)
  │
  ├──> t002 (Backend Foundation) ──┐
  │                                │
  └──> t003 (Browser Runtime)     │
         │                         │
         v                         │
       t004 (Stream Runtime) ──────┤
                                   │
                                   v
                                 t005 (Supervisor)
                                   │
                                   v
                                 t006 (Gateway/Auth/RTC)
                                   │
                                   v
                                 t007 (Frontend Sessions)
                                   │
                                   v
                                 t008 (Artifacts & CDP)
                                   │
                 ┌─────────────────┴─────────────────┐
                 │                                   │
                 v                                   v
       t013 (Profile Copy/Reset) <──conflicts──> t014 (Clipboard & Input)
                 │                                   │
                 └─────────────────┬─────────────────┘
                                   │
                                   v
                                 t009 (Full Acceptance)
                                   │
                                   v
                                 t010 (Data Migration)
                                   │
                                   v
                                 t011 (Remove Legacy)
                                   │
                                   v
                                 t012 (Docker Release)
```

- **对称冲突声明**：`t013` 与 `t014` 因共享 OpenAPI 规范 (`schemas/openapi/`) 及前端 API 生成类型文件，在 `note.md` 中各自显式声明了对称的 `conflicts_with`（`t013` 声明 `t014`，`t014` 声明 `t013`），调度引擎将严格串行分派，避免并发写入冲突。
- **验收汇聚完整性**：`t009`（完整安全与压力验收）的 `depends_on` 已更新为 `"t013,t014"`，确保在进入第 19 章 1000 次输入、剪贴板测试与 8 小时基准测试前，`t013` 与 `t014` 的代码均已完工合并。
- **删除与发布顺序**：`t011`（删除旧链路）严格依赖 `t010`（数据迁移），而 `t010` 严格依赖 `t009`（全体验收通过），完全保全了“旧链路仅在通过完整验收后才删除”的铁律。

______________________________________________________________________

## 4. AGENTS.md 与全局规范遵循审计

1. **规范与结构分离（范围/上下文 vs 行为 AC）**：
    - AGENTS.md 明确要求：“需求拆分为可独立验证的 task，填写 task.md（契约区行为 AC 须非空）；版本号、底层库选型、目录结构不写进行为 AC”。
    - R2 严格落实了这一准则：环境参数（如 `/dev/shm 1GiB`、SQLite PRAGMA、Selkies commit、环境变量默认值）全部配置在【范围】或【依赖与约束】（上下文区），并以“测试必须读取真实状态/PRAGMA/扩展，不以配置值代替行为”作为门禁要求。行为 AC 全部聚焦于可观测的外部交互与协议断言。
2. **守卫措辞（无臆造规则或归属）**：
    - CPU 降帧：方案仅规定“CPU 超过阈值时按规则降低 Profile 级 FPS”，R2 未凭空编造“80%”或“95%”等未授权的固定硬编码数字，而是由调度决策动态测量并关联测量窗口；
    - 引擎缓存：方案仅具名 `/data/engine-cache/`，R2 仅将其纳入 Supervisor 与 Browser Runtime 容器挂载契约，未臆造无意义的 API 数据写入逻辑。
3. **真实授权与反虚假满足原则**：
    - 全套 14 个 Task 的【可测试性声明】均设立铁律：“需要真实部署/用户数据/原生平台的行为必须具备对应环境和授权，缺失时保持未通过，不用模拟替代”。
    - `t010`（数据迁移）与 `t012`（Docker 发布）严禁伪造用户数据授权或模拟外部发布。

______________________________________________________________________

## 5. 技术门禁执行状态与后续实施提醒 (Implementation Gate & Next Steps)

虽然 14 个 Task 的契约文档已获得 **PASS** 评定，但主干工程与技术门禁的实际状态必须保持绝对清醒：

1. **`t001` 技术验证 Spike 尚未闭环 (GATED / OPEN)**：
    - 当前已勾选 AC-002（双 Chrome 观看输入）、AC-003（可见性帧率调节）、AC-005（UDS 自动化与防重启）；
    - **未勾选项状态**：
        - **AC-001**：非 root / IPC / Xauthority 真实有效，但 WebAudio 峰值 404/808 Hz 偏离目标 440/880 Hz，时钟漂移根因尚未闭环；
        - **AC-004**：本地 Docker 短周期凭证轮换通过，但真实公网 IP 候选、独立公网/私网 TURN URL 与公网 relay-to-relay 尚未在公网环境测试；
        - **AC-006**：本地仅覆盖 macOS OrbStack arm64，原生 Linux x86_64（16 vCPU 32 GiB）基准机器尚未接入测试（经只读核查，当前备用测试机仅 1.7GB 内存且禁止堆重服务，不符合硬件基准）。
2. **实施硬门禁禁令**：
    - 严禁任何人或 Agent 以“Task 契约已 PASS 审查”为由提前冻结正式架构；
    - 严禁提前 start 或编写 `t002` 至 `t014` 的任何生产代码；
    - 必须等待 `t001` 实施 Agent 彻底闭环 AC-001、AC-004、AC-006 并由 Reviewer 独立核销后，方可启动正式实现链条。

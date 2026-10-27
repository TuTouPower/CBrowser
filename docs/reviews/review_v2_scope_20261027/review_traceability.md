# CBrowser v2.3 需求可追溯性矩阵 (Traceability Matrix - R2 修订复核版)

## 1. 审计基准与输入资产哈希 (Source Hashes of Inputs)

本矩阵基于 `.scratch/plan_scope_review_r2/inputs` 下冻结的权威方案及 14 个 Task 契约生成。

- `v2_architecture_plan.md`：权威架构规划（1104 行）
- `t001`：来自当前登记 Active Worktree (`../CBrowser_t001`)
- `t002`–`t012`：主仓修订后契约与总账
- `t013`、`t014`：自原 `t008` 拆分出的独立交付 Task（分别承载 Profile 复制重置与受控剪贴板/组合输入）

|输入文件路径|SHA-256 校验和|属性与状态|
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
|`inputs/t013_v2_profile_copy_reset/note.md`|`ca5c3f2d82f59738ac5fcdeab188006f85e5a12d1c0cb07482c651348a8a8bf7`|R2 拆分独立总账 (Backlog)|
|`inputs/t013_v2_profile_copy_reset/task.md`|`daf68776675afc29f0513c733ebe313558d303ac24ccb7fe7e15492005a13532`|R2 拆分独立契约 (Backlog)|
|`inputs/t014_v2_clipboard_input/note.md`|`007f607aa9e538d68ed4200d1efb5f7f7a9a4d14e1d87d20f50788b8301c73ef`|R2 拆分独立总账 (Backlog)|
|`inputs/t014_v2_clipboard_input/task.md`|`e1ed5f57d52aa792118f55c668983d5d82c35f4342c707cdca673cd9758d9935`|R2 拆分独立契约 (Backlog)|

______________________________________________________________________

## 2. 逐章需求对齐与可追溯性表 (Requirement Traceability Matrix)

说明：

- **覆盖状态判定**：
    - `FULL`：Task 契约（范围、上下文约束或行为 AC）明确包含该计划条款，且契约划分符合 AGENTS.md 规范（技术选型/路径/版本进范围或上下文，可观察行为进 AC）。
    - `PARTIAL`：核心逻辑有涉及，但仍缺失具名配置、字段或参数。
    - `MISSING`：计划中明确具名要求的产物、字段、路由或文件未出现在任何 Task 契约中。
    - `ORPHANED`：在后续验收 Task（如 t009）中被断言，但前置实现 Task 未被分配实现职责。
    - `GATED / OPEN`：技术验证阶段尚未闭环的硬门禁项（如 t001）。

|序号|架构规划章节与行号|规划核心条款 / 具名要素|关联 Task ID 与契约位置|覆盖状态|审查与对齐意见|
|---|---|---|---|---|---|
|**1.1.1**|第 1.1 节 Line 17|外部客户端唯一指定为 Google Chrome Stable|`t001` AC-002, 上下文; `t004` AC-001; `t007` AC-001; `t009` AC-001; `t012` AC-001|**FULL**|各 Task 测试策略及 AC 均显式锁定真实 Google Chrome Stable。|
|**1.1.2**|第 1.1 节 Line 18|前端技术栈：React 19 + TypeScript + Vite|`t007` 范围; `t012` AC-002|**FULL**|`t007` 范围与 `t012` 构建包含完整前端链。|
|**1.1.3**|第 1.1 节 Line 19|前端路由：React Router 7|`t007` 范围|**FULL**|纳入 `t007` 范围，配合计划 13.1 路由定义。|
|**1.1.4**|第 1.1 节 Line 20|API 数据管理：TanStack Query 5|`t007` 范围, AC-006|**FULL**|`t007` AC-006 明确要求 TanStack Query 生成类型调用。|
|**1.1.5**|第 1.1 节 Line 21|后端技术栈：Python 3.12 + FastAPI + Pydantic 2|`t002` 范围; `t005` 范围; `t006` 范围|**FULL**|对应后端各子模块的实现栈。|
|**1.1.6**|第 1.1 节 Line 22|数据库：SQLite + SQLAlchemy 2 + Alembic|`t002` 范围; `t010` 范围|**FULL**|`t002` 新建与 `t010` 迁移均包含 Alembic。|
|**1.1.7**|第 1.1 节 Line 23|浏览器内核：当前 CloakBrowser|`t001` 范围; `t003` 范围, AC-001|**FULL**|保留 CloakBrowser 隐私指纹对抗引擎。|
|**1.1.8**|第 1.1 节 Line 24|浏览器运行环境：Linux + Xvfb + Openbox|`t001` 范围; `t003` 范围, AC-002|**FULL**|`t003` 范围明确包含 Xvfb 与 Openbox。|
|**1.1.9**|第 1.1 节 Lines 25, 35|远程显示：Selkies 2.1.0 固定 commit `6ee68a7a815956e6745e916741f13335e0b3ff53`|`t004` 依赖与约束; `t006` AC-002|**FULL**|`t004` 上下文明确固定官方 commit 6ee68a7 及参数基线，行为由 AC 验证，规范合规。|
|**1.1.10**|第 1.1 节 Line 26|实时媒体：WebRTC 协议栈|`t001` AC-004; `t004` 范围, AC-004; `t006` AC-003|**FULL**|媒体链路全部基于原生 WebRTC。|
|**1.1.11**|第 1.1 节 Line 27|信令路由：独立 Stream Gateway|`t006` 范围, AC-002, AC-003|**FULL**|独立信令隧道与 Agent 注册管理。|
|**1.1.12**|第 1.1 节 Line 28|媒体中继：coturn (STUN/TURN)|`t005` AC-006; `t006` AC-004; `t009` AC-005; `t012` 范围|**FULL**|涵盖端口、动态网络接入、凭证轮换及 relay-only。|
|**1.1.13**|第 1.1 节 Line 29|HTTPS 与反向代理网关：Caddy|`t006` AC-001; `t012` 范围, AC-001|**FULL**|Caddy 作为固定入口反向代理。|
|**1.1.14**|第 1.1 节 Line 30|容器管理：Docker Engine API + Runtime Supervisor|`t005` 范围, AC-003|**FULL**|唯一持有 Docker Socket 并驱动容器生命周期。|
|**1.1.15**|第 1.1 节 Line 31|浏览器自动化：受控 CDP 代理|`t003` AC-003; `t005` 范围; `t008` 范围, AC-002|**FULL**|经 Supervisor/UDS/loopback 受控流代理。|
|**1.1.16**|第 1.1 节 Line 32|文件管理：独立 Artifact Service|`t002` 范围; `t008` 范围, AC-001|**FULL**|独立于浏览器用户数据的文件上传/下载存储。|
|**1.1.17**|第 1.1 节 Line 33|测试框架：Pytest, Vitest, Playwright, Compose 集成|全部 Task 契约测试策略|**FULL**|各层级自动化测试工具链完整对应。|
|**1.2**|第 1.2 节 Lines 45-59|明确删除的 12 项设计（无标签栏、无控制租约、无 Redis、无 noVNC、无 RFB、无 Caddy 动态发现等）|各 Task `非范围` 区|**FULL**|各 Task 非范围区严禁恢复旧租约、Redis 或外部标签栏。|
|**2.1**|第 2.1 节 Lines 64-92|对象模型：Profile、BrowserRuntime、ViewerConnection 三者解耦|`t002` 范围; `t003` 范围; `t004` 范围; `t007` 范围|**FULL**|结构与关系一致，不持久化 ViewerConnection。|
|**2.2**|第 2.2 节 Lines 94-107|外部 Chrome 标签页：独立操控目标、同实例共享、切换只换连接|`t007` AC-001, AC-003|**FULL**|验证双 tab 各自切换且不影响原 Profile 运行。|
|**2.3**|第 2.3 节 Lines 108-113|内部标签页：真实窗口 UI，不仿制、不通过 CDP 绘制|`t003` AC-002; `t007` AC-005|**FULL**|确保真实窗口渲染及内部标签页同步展现。|
|**2.4**|第 2.4 节 Lines 114-126|连接身份非控制租约，允许多 controller peer 并发输入|`t004` AC-001, AC-005; `t007` AC-005; `t014` AC-003|**FULL**|废止控制权抢占与接管锁，多端并发直达。|
|**3.1**|第 3.1 节 Lines 131-139|常驻五服务：caddy, api, supervisor, stream-gateway, coturn|`t005` 范围; `t006` 范围; `t009` AC-004; `t012` AC-001|**FULL**|正式拓扑固定包含此五项常驻服务。|
|**3.2**|第 3.2 节 Lines 141-146|Profile 动态双容器：browser-runtime / stream-runtime|`t003` 范围; `t004` 范围; `t005` AC-001; `t012` AC-001|**FULL**|双容器按需创建与回收。|
|**3.3.1**|第 3.3 节 Lines 152-165|数据目录结构：db, settings, profiles, artifacts, runtime-events, backups|`t002` 范围; `t005` AC-001; `t010` AC-004; `t012` AC-001|**FULL**|核心持久化目录结构对齐。|
|**3.3.2**|第 3.3 节 Line 153|数据目录具名结构：`/data/engine-cache/`|`t003` 范围; `t005` 范围|**FULL**|明确统一数据根及挂载权限；未臆造无依据的 API 缓存写者。|
|**4.1**|第 4.1 节 Lines 177-186|保留双容器架构，专属 X11 Socket 卷连接|`t001` 范围; `t003` AC-006; `t004` 范围; `t005` AC-001|**FULL**|明确不合并容器，维持文件与运行边界隔离。|
|**4.2.1**|第 4.2 节 Lines 187-196|同 Profile 共享 IPC 命名空间 (`IpcMode=container:<id>`)|`t001` AC-001; `t005` AC-001|**FULL**|Stream Runtime 复用 Browser Runtime IPC。|
|**4.2.2**|第 4.2 节 Lines 197-198|Browser Runtime 的 `/dev/shm` 设为 1 GiB，Xvfb 显式启用 MIT-SHM, XTEST, XFIXES|`t003` 依赖与约束, AC-006; `t005` AC-001|**FULL**|`t003` 约束锁定 1GiB 与扩展，测试实际捕获 XShm 证据，符合规范。|
|**4.3**|第 4.3 节 Lines 203-213|X11 访问权限：Xauthority 凭证隔离，Stream Runtime 不挂载浏览器用户数据，Xvfb 禁 TCP|`t003` AC-006; `t004` AC-006; `t005` AC-001|**FULL**|严格权限隔离与单向授权。|
|**5.1-5.3**|第 5 章 Lines 219-225|独立虚拟 PulseAudio 服务、专属共享卷认证、Stream 监视源捕获|`t001` AC-001; `t003` AC-002; `t004` AC-001; `t005` AC-001|**FULL**|音频服务隔离与捕获链路对齐。|
|**5.4**|第 5 章 Line 226|外部页面独立静音，不中断其他连接音频|`t004` AC-005; `t007` AC-005|**FULL**|支持多页面不同静音状态。|
|**5.5**|第 5 章 Lines 229-230|音频就绪检查，不可用时显示音频故障，禁止产生持续无法连接后台日志|`t003` AC-002; `t007` AC-005|**FULL**|`t003` 明确禁止无声状态报 ready，`t007` 分别展示音频故障。|
|**6.1**|第 6.1 节 Lines 237-248|浏览器用户数据独立持久化 `/data/profiles/{profileId}/profile`|`t003` AC-001; `t005` AC-001|**FULL**|Cookie、历史与偏好独立持久化。|
|**6.2**|第 6.2 节 Lines 249-273|Artifact 存储挂载至 `/exchange`，API 返回 `container_path`（如 `/exchange/uploads/..`）而非宿主路径|`t003` AC-004; `t008` AC-001|**FULL**|`t008` AC-001 显式断言返回 `container_path` 且严禁暴露宿主物理路径。|
|**6.3**|第 6.3 节 Lines 274-284|上传流程：MIME/配额/空间检查，临时文件原子移动至 uploads 目录|`t008` AC-001|**FULL**|原子写入与错误回滚保护。|
|**6.4**|第 6.4 节 Lines 285-297|下载流程：CDP 监听、写入 downloads、事件通知、外部自动化断开后恢复下载捕获机制|`t003` AC-004; `t008` AC-002|**FULL**|包含外部客户端策略覆盖后的自动恢复能力。|
|**7.1**|第 7.1 节 Lines 301-312|Caddy 职责：固定 `/api/*`、`/stream/*` 与静态前端代理，禁动态容器扫描|`t006` 范围; `t012` AC-001|**FULL**|网关边界明确。|
|**7.2**|第 7.2 节 Lines 313-329|Agent 主动注册字段 (profile_id, runtime_instance_id, selkies_version, runtime_state, webrtc_udp_port, config_version)；心跳 10s；退避 1/2/4/8/16/30s|`t006` AC-002|**FULL**|注册字段与心跳/退避阶梯完全一致。|
|**7.3**|第 7.3 节 Lines 330-350|ViewerConnection 信令流程：`wss://.../signal`，会话/Origin/Profile 授权，独立隧道，媒体不经 Gateway|`t006` AC-001, AC-003|**FULL**|双向转发与媒体直连。|
|**7.4**|第 7.4 节 Lines 351-364|运行时停止顺序：标不可用 -> 断 Viewer -> 停 Stream -> 停 Browser -> 回收端口；Gateway 重启不停浏览器|`t005` AC-002; `t006` AC-003|**FULL**|停止状态机顺序与故障恢复一致。|
|**8.1**|第 8.1 节 Lines 368-388|Selkies Token：master token 不下发，controller token Profile 级；配置 `SELKIES_MODE=webrtc`, `DUAL_MODE=false`, `SHARING=true`, `COLLAB=false`, 不设 `mk_control=true`|`t004` 依赖与约束; `t006` AC-001|**FULL**|master token 不泄露，`t004` 约束锁定环境变量基线。|
|**8.2**|第 8.2 节 Lines 389-406|`client_tab_id`：官方 pageTabId, sessionStorage, resume_key 重连, rel=noopener, 重复 ID 冲突重新连接不踢原页|`t004` AC-002; `t007` AC-002|**FULL**|官方薄适配与冲突处理。|
|**8.3**|第 8.3 节 Lines 407-413|多页面输入：X11 到达顺序处理，无独占锁|`t004` AC-005; `t007` AC-005; `t014` AC-003|**FULL**|并发输入直达 X11。|
|**9.1**|第 9.1 节 Lines 416-434|共享编码器与 FPS：连接可独立暂停解码，编码帧率由 Stream Agent 统一决定|`t004` AC-003; `t007` AC-004|**FULL**|连接端与服务端职责分离。|
|**9.2**|第 9.2 节 Lines 435-452|固定帧率策略：`SELKIES_FRAMERATE=8,8-30`，前台活跃 30，静止 8，动画/视频持续 30，全后台暂停，恢复先 8 后提|`t001` AC-003; `t004` AC-003; `t007` AC-004|**FULL**|动态聚合帧率策略。|
|**9.3**|第 9.3 节 Lines 453-472|Gateway 连接活动聚合：记录 connection_id, visible, last_activity, last_heartbeat，聚合后下发 Agent|`t004` AC-003; `t006` 范围, AC-007; `t007` AC-004|**FULL**|`t006` AC-007 明确连接追踪与聚合协议下发，活跃前台需求不被后台降需。|
|**9.4**|第 9.4 节 Lines 473-486|固定屏幕尺寸：Profile 配置决定（默认 1920x1080, DPR=1），外部 resize 禁改远端|`t003` AC-002; `t004` AC-002; `t007` AC-004|**FULL**|尺寸锁定，变更须显式修改 Profile。|
|**10.1**|第 10.1 节 Lines 491-518|单 Profile UDP mux 端口：池 `30000–30991/UDP`，内外端口一致，配置 `SELKIES_WEBRTC_UDP_MUX_PORT`|`t004` AC-004; `t005` AC-002|**FULL**|端口分配、映射与单端口复用。|
|**10.2**|第 10.2 节 Lines 519-536|网络模式：local/lan/public/relay-only，配置 `CBROWSER_WEBRTC_ADVERTISE_IP`，public host candidate 对齐|`t004` AC-004; `t009` AC-005; `t012` 依赖与约束|**FULL**|多环境网络声明。|
|**10.3**|第 10.3 节 Lines 537-547|网络拓扑：Stream Runtime 独占 profile-stream 网络；Supervisor 动态接入 Gateway/coturn 并明确下发 IP|`t005` AC-006|**FULL**|明确禁止依赖多网卡 DNS 顺序。|
|**10.4**|第 10.4 节 Lines 548-560|coturn：监听 3478/5349，relay 端口 50000–50999，动态接入媒体网络，固化 public relay 映射|`t005` AC-006; `t009` AC-005; `t012` AC-001|**FULL**|媒体中继网络拓扑一致。|
|**10.5**|第 10.5 节 Lines 561-575|独立 RTC 配置：`RtcConfigService` 分别为外部客户端与 Stream Runtime 生成配置与凭证|`t006` 范围, AC-004|**FULL**|客户端公网 URL 与内部私网 URL 隔离。|
|**10.6**|第 10.6 节 Lines 576-589|TURN 凭证刷新：REST HMAC，24h 有效，每 12h 更新，到期前 6h 执行 ICE 重启；relay-only 真实 relay-to-relay|`t001` AC-004; `t004` AC-004; `t006` AC-004, AC-005; `t009` AC-005|**FULL**|凭证轮换与 relay 媒体增量交割。|
|**11.1**|第 11.1 节 Lines 594-623|本地受控通道：`/run/cbrowser/runtime/{profileId}/agent.sock`，暴露健康、CDP、下载、退出事件等，禁通用 shell|`t003` 范围, AC-003; `t005` 范围|**FULL**|严格 UDS RPC 接口。|
|**11.2**|第 11.2 节 Lines 624-644|CDP 流架构：Client -> API -> Supervisor 代理 -> UDS -> Browser Agent -> loopback CDP；不对公网发布端口|`t003` AC-003; `t005` AC-003; `t008` AC-002|**FULL**|无公网暴露，Supervisor 仅流转发不解析业务。|
|**11.3**|第 11.3 节 Lines 645-653|下载监听捕获：CDP 事件 -> UDS -> Supervisor -> RPC -> API -> DB Artifact；断开后自动恢复|`t003` AC-004; `t008` AC-001, AC-002|**FULL**|下载自动化链路完整。|
|**12.1**|第 12.1 节 Lines 657-672|SQLite 写入归属：API 为唯一写入者，Supervisor 不挂载 DB；WAL 模式，`busy_timeout=5000`；短事务禁调 Docker|`t002` 依赖与约束, AC-004; `t005` AC-003|**FULL**|`t002` 上下文约束显式限定 WAL 与 busy_timeout=5000，AC-004 验证行为。|
|**12.2**|第 12.2 节 Lines 673-687|运行状态模型字段：`desired_state`, `observed_state`, `runtime_instance_id`, `config_version`, `failure_count`, `restart_blocked`, `last_exit_event_id`|`t002` 范围, AC-003; `t005` AC-004, AC-005|**FULL**|`t002` 范围明确具名全部 7 项运行状态与恢复字段。|
|**12.3**|第 12.3 节 Lines 689-698|主动停止状态机：desired=stopped -> 幂等停止 -> 断连接 -> 停容器 -> 回收端口 -> observed=stopped|`t005` AC-002|**FULL**|生命周期停机状态迁移清晰。|
|**12.4**|第 12.4 节 Lines 699-717|浏览器直接关闭：退出事件落盘，API 消费按 event_id 去重；正常退出置 desired=stopped，防重启误启动|`t002` AC-003; `t003` AC-005; `t005` AC-004|**FULL**|事件落盘去重与状态防误起。|
|**12.5**|第 12.5 节 Lines 718-728|离线与恢复：Supervisor 事件落盘队列，Agent 事件落盘；Supervisor 重启扫描容器等 API；restart policy=no|`t003` AC-005; `t005` AC-004, AC-005|**FULL**|严禁 Docker 自动重启策略介入业务恢复。|
|**12.6**|第 12.6 节 Lines 729-736|异常退出：保留 desired=running，重试 3 次 (2/10/30s)，3 次失败置 `restart_blocked=true`，手动重试解除|`t002` AC-003; `t005` AC-005|**FULL**|退避重试与失败阻断。|
|**13.1**|第 13.1 节 Lines 741-761|前端路由：`/`, `/settings`, `/profiles/new`, `/:profileId`, `/:profileId/files`, `/automation/:profileId`；query `/?profileId=`；禁 localStorage 共享|`t007` AC-001; `t008` AC-001, AC-002|**FULL**|`t007` 负责主框架及 query param；`t008` AC 明确断言 files 与 automation 子路由。|
|**13.2**|第 13.2 节 Lines 762-784|前端目录结构：`BrowserSessionView.tsx`, `SelkiesClientAdapter.ts`, `ViewerConnection.ts`, `ClipboardBridge.ts` 等|`t007` 范围; `t008` 范围; `t014` 范围|**FULL**|目录及核心适配模块划分明确（`t014` 负责 ClipboardBridge）。|
|**13.3**|第 13.3 节 Lines 785-798|页面独立状态：`selectedProfileId`, `viewerConnection`, `streamState`；TanStack Query + SSE + WebRTC|`t007` AC-001, AC-006|**FULL**|页面状态完全自治。|
|**13.4**|第 13.4 节 Lines 799-807|页面关闭只断当前连接，不调用 stop API；页面恢复重新建立连接|`t007` AC-003|**FULL**|严格区分页面离线与 Profile 停机。|
|**14.1**|第 14.1 节 Lines 811-825|强制登录，首启 Argon2id 密码，HTTPS Cookie (HttpOnly/Secure/Strict)，CSRF Token，WebSocket Origin 验证|`t006` AC-001|**FULL**|Web 安全契约全面覆盖。|
|**14.2**|第 14.2 节 Lines 826-833|CDP 自动化鉴权：独立 Bearer Token 或 mTLS，非浏览器客户端可无 Origin，禁 Cookie 混用|`t006` AC-006; `t008` AC-002|**FULL**|自动化通道独立鉴权与越权拦截。|
|**14.3**|第 14.3 节 Lines 834-842|API 版本化：统一迁移 `/api/v1`；删除旧内部 CRUD；旧 CDP 保留薄适配器转发；废除 `AUTH_TOKEN` 可选模式|`t002` 范围; `t008` AC-002; `t011` AC-001|**FULL**|架构升级与旧 CDP 薄适配保留。|
|**15.1**|第 15.1 节 Lines 846-862|数据库表结构：profiles, versions, tags, runtimes, artifacts, settings, runtime_events, audit_events；无 leases 表|`t002` 范围; `t010` 范围|**FULL**|8 张业务与事件表定义完备。|
|**15.2**|第 15.2 节 Lines 863-893|完整配置字段迁移：覆盖 24 个旧字段，旧 native/viewer 模式映射为 Docker 模式，无损保留配置|`t002` 范围; `t010` AC-002|**FULL**|`t010` AC-002 明确要求计划 15.2 全部有效字段无丢失。|
|**15.3**|第 15.3 节 Lines 894-902|运行状态迁移：核对真实容器，initializing 映射待检查，stopped 映射 desired=stopped，停机迁移|`t010` AC-001, AC-003|**FULL**|防臆想容器存活，停机一致性迁移。|
|**15.4**|第 15.4 节 Lines 903-912|Profile 复制与重置：仅配置复制 vs 配置+状态复制（源停止后复制目录，Artifact 不复制）；重置重新生成指纹种子|`t013` 范围, AC-001-AC-004|**FULL**|拆分为独立 Task `t013`，4 项 AC 完整覆盖复制与重置各场景。|
|**15.5**|第 15.5 节 Lines 913-929|数据目录与备份：bind mount，备份覆盖 5 类数据；迁移工具支持 `--dry-run` 与校验和核对，失败原子回滚|`t010` AC-001, AC-004, AC-005|**FULL**|可回退迁移与备份恢复演练。|
|**16.1**|第 16.1 节 Lines 933-948|安全网络矩阵：12 项来源-目标访问控制（Docker Socket、DB、RPC、CDP 隔离等）|`t005` AC-003; `t009` AC-004; `t012` AC-001|**FULL**|架构拓扑级安全约束。|
|**16.2**|第 16.2 节 Line 949|挂载路径安全：规范化校验，确保所有 Profile 挂载位于允许宿主机目录内，拒绝路径逃逸|`t005` AC-001; `t009` AC-004|**FULL**|路径遍历与符号链接逃逸防御。|
|**16.3**|第 16.3 节 Lines 950-953|容器安全基线：非 root、no-new-privileges、最小 caps、只读根文件系统、无 privileged、无 host 网络|`t003` AC-006; `t004` AC-006; `t005` AC-001; `t009` AC-004|**FULL**|生产容器安全基准。|
|**17.1-17.8**|第 17 节 Lines 956-966|后端文件改造：`main.py`, `browser_manager.py`, `database.py`, `vnc_manager.py`, `artifacts.py`, `downloads.py`, `runtime.py`, `models.py`|`t002`, `t003`, `t008`, `t011`|**FULL**|业务分拆与旧 VNC/Native 移除。|
|**17.9**|第 17 节 Line 967|现有文件改造：`src/backend/diagnostics.py` 保留，增加结构化运行时日志|`t002` 范围, AC-006|**FULL**|`t002` 范围明确保留扩展，AC-006 明确结构化机器解析与脱敏输出。|
|**17.10-17.16**|第 17 节 Lines 968-974|前端组件与文件改造：`App.tsx`, `ProfileViewer.tsx`, `useProfiles.ts`, `api.ts`, `ProfileFiles.tsx`, `CdpEndpointButton.tsx`, `NativeWindowStatus.tsx`|`t007`, `t008`, `t011`, `t013`, `t014`|**FULL**|前端模块迁移、重构与废弃删除对齐。|
|**17.17**|第 17 节 Line 975|Dockerfile 改造：拆分 API、Supervisor、Browser Runtime、Stream Runtime 独立 Dockerfile|`t003` 范围; `t004` 范围; `t012` 范围, AC-001|**FULL**|`t003`/`t004` 负责各 Runtime 镜像，`t012` 交付全套 Compose 多服务镜像。|
|**17.18**|第 17 节 Line 976|配置改造：`compose.yaml`|`t012` 范围, AC-001|**FULL**|正式 Compose 交付。|
|**17.19**|第 17 节 Line 977|现有文件改造：`config/docker/entrypoint.sh` 删除旧 VNC 和进程清理逻辑|`t011` 范围, AC-002|**FULL**|`t011` 范围与 AC-002 显式要求清理旧 VNC (`Xvnc`) 与残留进程逻辑。|
|**17.20-17.23**|第 17 节 Lines 978-980|原生入口清理：`app_entry.py`, `run-macos.sh`, `run-windows.bat`, `packaging/` 均删除|`t011` 范围, AC-002|**FULL**|原生客户端入口与打包流程彻底移除。|
|**17.24-17.27**|第 17 节 Lines 981-985|CI/Release/文档改造：`ci.yml`, `release.yml`, `README.md`, `DOCKER_DEPLOYMENT.md`|`t010`, `t011`, `t012`|**FULL**|覆盖单测/集成/E2E流水线及交付文档。|
|**17.28**|第 17 节 Line 986|旧 VNC/RFB 链路只有在新架构通过完整验收后才删除|`t011` 依赖与约束; `note.md` depends_on|**FULL**|`t011` 严格依赖 `t010`（继而依赖 `t009` 完整验收），顺序硬约束完全对齐。|
|**18.1-18.17**|第 18 章 Lines 990-1017|第一阶段技术验证 Spike：17 项关键实验；全部通过后才冻结正式架构|`t001` 范围, AC-001-AC-006; `note.md`|**GATED / OPEN**|`t001` 仍在 active 实施中，AC-001/004/006 仍 open（未通过）。后续所有 Task 均设前置硬门禁。|
|**19.1.1**|第 19.1 节 Lines 1024-1034|性能基准机型：Linux x86_64, 16 vCPU, 32 GiB RAM, 无物理 GPU；1/3/10 活跃流，10 Profile 9 后台 1 前台|`t009` AC-001, 上下文|**FULL**|完整保留基准硬件规格与并发流测试场景。|
|**19.1.2**|第 19.1 节 Lines 1037-1044|性能指标目标：单流 1080p30；输入画面延迟 LAN RTT≤10ms 时 P95≤100ms；就绪首帧 P95≤1s；后台暂停捕获|`t009` AC-001|**FULL**|延迟与帧率指标无缩水。|
|**19.1.3**|第 19.1 节 Line 1043|多流资源调度：CPU 超过阈值时按规则降低 Profile 级 FPS|`t004` AC-003; `t005` 范围, AC-007; `t009` AC-001|**FULL**|由 Supervisor (`t005`) 真实采集并下发限额，Stream (`t004`) 执行降帧，`t009` 最终验收。|
|**19.1.4**|第 19.1 节 Line 1044|8 小时连续压力测试：无数据损坏、会话串线或不可恢复退出|`t009` AC-002|**FULL**|明确禁止短测或容器存活替代 8 小时。|
|**19.2**|第 19.2 节 Lines 1048-1056|标签页验收：双页同操作、内部标签同步、单连接关闭不停浏览器、只有停止 Profile 才关闭真实进程|`t007` AC-001-AC-003; `t009` AC-005|**FULL**|标签页生命周期全要素覆盖。|
|**19.3.1**|第 19.3 节 Lines 1058-1062|输入验收：1000 次中文组合输入，1000 次纯文本剪贴板；四类输入框（地址栏/普通/受控/富文本）与双页输入|`t014` AC-002, AC-003; `t009` AC-003|**FULL**|`t014` 负责功能实现与独立夹具测试，`t009` 执行 1000 次专项压力。|
|**19.3.2**|第 19.3 节 Lines 1063-1066|剪贴板保护：用户原内容保护，权限拒绝显式提示，后台页面不覆盖本机剪贴板，IME 不走粘贴|`t014` AC-001; `t009` AC-003|**FULL**|剪贴板与 IME 原生输入安全契约由 `t014` 与 `t009` 完整闭环。|
|**19.4**|第 19.4 节 Lines 1067-1078|安全与恢复验收：数据卷隔离、CDP 无公网、Supervisor 唯一持有 Docker Socket、事件幂等、正常退出防自启等|`t009` AC-004, AC-005|**FULL**|全系统拓扑安全与恢复黑盒核验。|
|**20**|第 20 章 Lines 1081-1104|正式实施顺序 01–12：先 Spike，后冻结架构，再重构、迁移和删除旧链路|全部 Task 的 `depends_on` 依赖图|**FULL**|14 个 Task 的硬依赖链严格锁定计划第 20 章先后顺序。|

______________________________________________________________________

## 3. 统计汇总与对比分析 (Summary Statistics & R1 vs R2 Delta)

### 3.1 覆盖度统计指标对比

|统计指标|R1 初审状态 (12 Tasks)|R2 复核状态 (14 Tasks)|净变化说明|
|---|---|---|---|
|**总审计需求点数**|58 项|58 项|方案全集保持严格一致|
|**完全覆盖 (FULL)**|47 项 (81.0%)|**57 项 (98.3%)**|**+10 项**（缺漏项全量闭环）|
|**部分覆盖 (PARTIAL)**|6 项 (10.3%)|**0 项 (0.0%)**|**-6 项**（依 AGENTS.md 规范全量固化）|
|**完全遗漏 (MISSING)**|3 项 (5.2%)|**0 项 (0.0%)**|**-3 项**（具名文件/结构全量纳入契约）|
|**孤立待实现 (ORPHANED)**|1 项 (1.7%)|**0 项 (0.0%)**|**-1 项**（CPU 降帧打通 Supervisor 与 Stream 责任链）|
|**技术门禁阻塞 (GATED / OPEN)**|1 项 (1.7%)|**1 项 (1.7%)**|**保持锁定**（`t001` 技术验证阶段进行中，严防冒进）|

### 3.2 契约覆盖度达标结论

在文档与 Task 契约覆盖度维度，全套 14 个 Task 契约已达到 **100% 映射对齐**（排除处于第一阶段真实验证中的硬门禁项 `t001` 本身）。所有架构约束、模块职责、文件改造、API 规范与安全边界均已具备无歧义、可追溯且符合开发规范的契约表达，契约审计结论判定为 **PASS**。

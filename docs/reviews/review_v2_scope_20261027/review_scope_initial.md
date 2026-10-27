# CBrowser v2.3 架构规划与 Task 契约覆盖度独立评审报告

## 评审结论 (Verdict)

### **状态判定：INCOMPLETE**

**判定理由与关键事实**：

1. **第一阶段技术门禁尚未闭环 (Hard Gate Open)**：
    依据权威方案《v2_architecture_plan.md》第 18 章（Lines 990–1017）及核心原则（Lines 7–8, Line 1104）：“先完成关键技术验证，再冻结架构、迁移数据库和删除旧链路。全部通过后才冻结正式架构。”
    当前作为第一阶段技术验证的 `t001_v2_runtime_validation` 仍处于 `active` 状态，其 6 项验收标准中仅勾选了 AC-002、AC-003、AC-005，而 **AC-001 (IPC/X11/MIT-SHM/音频完整性)、AC-004 (动态信令/公网候选/TURN 刷新/relay-to-relay)、AC-006 (macOS arm64 与 Linux x86_64 双平台逐项覆盖)** 仍处于未完成（Open）状态。主仓 commit `b5f732c` 仅代表创建并锁定后续 Task 契约骨架，**绝不代表实现完成**；在 `t001` 全项 17 个技术实验独立复核通过前，正式架构不得冻结，后续正式代码重写不得启动。
2. **Task 契约存在具名要素遗漏与孤立需求 (Scope Gaps & Orphaned Requirements)**：
    文档覆盖度审计发现，部分计划中明确具名要求的文件改造、目录结构、接口字段与削峰调度策略未被完全纳入 Task 契约（如 `src/backend/diagnostics.py`、`config/docker/entrypoint.sh`、`/data/engine-cache/`、Gateway 活动聚合协议、CPU 过载降帧实现责任归属等）。
3. **真实环境与用户授权不可凭空捏造 (No Invented Authorization)**：
    计划第 19 章关于 Linux x86_64 16 vCPU 32 GiB 性能基准、8 小时连续压力测试、1000 次中文组合输入与剪贴板测试必须完整保留；真实用户数据库迁移与正式外部发布必须严格基于用户明确指定的具体目标和授权凭据，在获得授权前相应 AC 必须保持未通过状态，严禁以测试演练或模拟通过替代。

______________________________________________________________________

## 1. 冻结输入资产校验和 (Source Hashes of Inputs)

本审计基于严格冻结于本地 `.scratch/plan_scope_review/inputs` 的 25 份权威文档与 Task 契约：

|资产文件路径|SHA-256 校验和|来源与版本|
|---|---|---|
|`inputs/v2_architecture_plan.md`|`0dd1a8677527717c08d60df1391805aa141a46bb7a350ae729bf046933c981d0`|权威架构规划（1104 行）|
|`inputs/t001_v2_runtime_validation/note.md`|`987db7a6b7d47a1cc383b4d98f7036a9a256f9a6548969ad3d8a31db279f5e67`|登记 Active Worktree (`CBrowser_t001`)|
|`inputs/t001_v2_runtime_validation/task.md`|`ac95f84a24853b83a2e4e57ad353a1f23ad7027bfc206ce38dccbfeb7624d847`|登记 Active Worktree (`CBrowser_t001`)|
|`inputs/t002_v2_backend_foundation/note.md`|`244e5fb2ed75599c69bad294cbe77cc5b72b9a86cb3e5f544a36f1f0dcba3ac7`|主仓 `b5f732c` (Backlog)|
|`inputs/t002_v2_backend_foundation/task.md`|`577ddbaa86e06052f7b1edb6ec4235c0043c14dd5bf81da5b4465169bb6c454b`|主仓 `b5f732c` (Backlog)|
|`inputs/t003_v2_browser_runtime/note.md`|`b6d46aee575636e4acab89fb522bc181cf37d82fa453bfab416f05dfbafb757e`|主仓 `b5f732c` (Backlog)|
|`inputs/t003_v2_browser_runtime/task.md`|`0471bdba5233a54460e83080445126321af52bcf5b0ac83afc80daa95b70af64`|主仓 `b5f732c` (Backlog)|
|`inputs/t004_v2_stream_runtime/note.md`|`91a6c3feae86f3155eaa1edb4fca39da0237c0c6379f4c76023d7129da0b261a`|主仓 `b5f732c` (Backlog)|
|`inputs/t004_v2_stream_runtime/task.md`|`541707a84e8415b462d1988a9e421fb7095a9a6ea051c059f53f801caa3fb9cb`|主仓 `b5f732c` (Backlog)|
|`inputs/t005_v2_supervisor/note.md`|`a45902fb29ff99e472e4d02c9e511ad9d381a8675570d6d0f823e887084224da`|主仓 `b5f732c` (Backlog)|
|`inputs/t005_v2_supervisor/task.md`|`efac67e2afc678eb25a55afe8f0a8138c184f78f76043603b8cf8b5193124249`|主仓 `b5f732c` (Backlog)|
|`inputs/t006_v2_gateway_auth_rtc/note.md`|`3ece36bc5918d1f9a24520ee53dd6c591a8771eaef978897e4aa8cb788dae66d`|主仓 `b5f732c` (Backlog)|
|`inputs/t006_v2_gateway_auth_rtc/task.md`|`4a62cfbaf672b685089372d8d643b2e17ae3b53f1dc460d7a7bfc696bf1da1b9`|主仓 `b5f732c` (Backlog)|
|`inputs/t007_v2_frontend_sessions/note.md`|`988c09399c2194c1db269e88840dacb29a5c02f9c1cfce0f9d608f96aef3a14e`|主仓 `b5f732c` (Backlog)|
|`inputs/t007_v2_frontend_sessions/task.md`|`e651682f9da8bfdfa05fcb8502c00be0776896dd04639b312fd4dcce10f81ef7`|主仓 `b5f732c` (Backlog)|
|`inputs/t008_v2_artifacts_automation/note.md`|`71aae6766a28fdb16c891d0569206a927cee2a94f7765c643643129137d179e0`|主仓 `b5f732c` (Backlog)|
|`inputs/t008_v2_artifacts_automation/task.md`|`c520fb7ef912bc2a18aeef9e7f9d5161b5ff226f77468b852f66515bacc589cd`|主仓 `b5f732c` (Backlog)|
|`inputs/t009_v2_full_acceptance/note.md`|`147aded1fd0cb958b77d16dbf4083b802cba331cb54f251c7ee6b6453c6645f7`|主仓 `b5f732c` (Backlog)|
|`inputs/t009_v2_full_acceptance/task.md`|`7b646a5c2ac1d96cfaf2c7a9818fc4c7c2541692dfeeb7ea71d3aa86f74cc2e7`|主仓 `b5f732c` (Backlog)|
|`inputs/t010_v2_data_migration/note.md`|`9193f2f781a4a6a679f6961f770057771568b4b6df8343612b732c76359dc37a`|主仓 `b5f732c` (Backlog)|
|`inputs/t010_v2_data_migration/task.md`|`848665e2c15f444183086620289c86435f39b8302bddaee29015021e91533c5c`|主仓 `b5f732c` (Backlog)|
|`inputs/t011_v2_remove_legacy/note.md`|`35515f8cdbc193fe9a590d59cebd06b3ae2e2edd883a9368dd32eac99a03af60`|主仓 `b5f732c` (Backlog)|
|`inputs/t011_v2_remove_legacy/task.md`|`9fbf688eb16f99e26f9a966ce530d9296434e899b6faee6534cba92123823c37`|主仓 `b5f732c` (Backlog)|
|`inputs/t012_v2_docker_release/note.md`|`82e3b50cdbdc7ef0622a3885d2367ca0beef0baf54b1b0487c5bba1c6def8d85`|主仓 `b5f732c` (Backlog)|
|`inputs/t012_v2_docker_release/task.md`|`f5ab6351eed99c36c46e6ad48e78eea1106151e237634e137f3828a4998a6103`|主仓 `b5f732c` (Backlog)|

______________________________________________________________________

## 2. 核心架构决策与技术验证门禁审计 (Technical Gate Status)

### 2.1 技术验证 Spike (t001) 当前状态

依据 `t001/task.md` 与 `t001/note.md` 最新执行账本，第 18 章 17 项实验对应 AC 的进展如下：

- **AC-001 [未勾选 / OPEN]**：双容器同 Profile IPC/X11 传输真实窗口与音频，MIT-SHM 真实证据。
    - *事实*：非 root / 只读 / Xauthority / IPC 卷已由 s007/d011 证实；但 WebAudio PCM 采样测得峰值 404/808 Hz 与目标 440/880 Hz 存在未决偏差，音高失真根因尚未定位，AC-001 维持未勾选。
- **AC-002 [已勾选 / CLOSED]**：双页面独立观看、输入同一浏览器，刷新/复制/关闭首页不影响后续连接。
    - *事实*：经 s004 真实 Chrome 双 tab 复验（55.58s exit 0），双页视频接收、DOM 输入与音频能量增长已获独立重跑验证。
- **AC-003 [已勾选 / CLOSED]**：后台页面不降低前台帧率，持续视频不降帧，全后台暂停捕获，恢复画面。
    - *事实*：经 s005 R4 独立 Core9 与 Native7 重跑（exit 0），可见性切换驱动捕获策略已获证实。
- **AC-004 [未勾选 / OPEN]**：真实信令经 Gateway 隧道，UDP mux 映射，公网候选可达，TURN 凭证刷新与 relay-to-relay。
    - *事实*：s008/d012 在本地 Docker 中完成短 TTL 轮换与无效凭证负例，但真实公网 IP 候选、独立公网/私网 TURN URL 及原生 Selkies 2.1.0 协议层真正的同 PC ICE 重启仍未完成公网环境验证，AC-004 维持未勾选。
- **AC-005 [已勾选 / CLOSED]**：UDS 控制真实浏览器并捕获下载，覆盖恢复；Supervisor/API 重启不误自启。
    - *事实*：经 s003 跨容器 UDS 下载、断开恢复及 d006 真实 API/Supervisor 重启 5 轮防误自启验证通过。
- **AC-006 [未勾选 / OPEN]**：macOS OrbStack arm64 与 Linux x86_64 双平台逐项覆盖报告。
    - *事实*：当前实验全部在 macOS OrbStack arm64 上执行，原生 Linux x86_64 尚未运行。

**硬门禁结论**：
`t001` 的 6 项 AC 中尚有 3 项（AC-001, AC-004, AC-006）处于 Open 状态。按照规划原则，**架构冻结硬门禁未达成**。后续所有 Task (`t002`–`t012`) 的契约必须严格保持依赖阻塞，不得在 `t001` 全项通过前启动实施。

______________________________________________________________________

## 3. 关键缺陷与范围缺口发现 (Primary Concrete Gap Findings)

本节列出审核中发现的具体范围缺口、具名产物遗漏及契约矛盾，每项均给出规划行号、Task 行号及最小契约修复建议（Minimal Contract Fix）。

### 缺陷 1：`src/backend/diagnostics.py` 结构化运行时日志改造全套遗漏

- **规划出处**：`v2_architecture_plan.md` 第 17 章 Line 967：
    > `src/backend/diagnostics.py` | 保留，增加结构化运行时日志
- **Task 现况**：在 `t001` 至 `t012` 全部 12 个 Task 的范围与 AC 中，无一处提及 `src/backend/diagnostics.py` 或结构化运行时日志改造。
- **影响**：生产环境缺失统一的结构化运行时诊断与日志聚合模块，违反第 17 章仓库文件改造清单。
- **最小契约修复**：
    在 `t002_v2_backend_foundation/task.md` 的【范围】（Line 11）中增加 `src/backend/diagnostics.py 结构化运行时日志`；在 AC-001 或 AC-005 中补充对结构化日志输出格式的显式检查。

### 缺陷 2：`config/docker/entrypoint.sh` 旧 VNC 逻辑清理遗漏

- **规划出处**：`v2_architecture_plan.md` 第 17 章 Line 977：
    > `config/docker/entrypoint.sh` | 删除旧 VNC 和进程清理逻辑
- **Task 现况**：`t011_v2_remove_legacy/task.md`【范围】（Line 11）与 AC-002（Line 26）列举了 `vnc_manager/RFB代理/native-window/app_entry/原生启动脚本/packaging`，但遗漏了 `config/docker/entrypoint.sh` 的清理；`t012` 亦未提及。
- **影响**：主仓 `config/docker/entrypoint.sh` 现存旧版 `x11vnc` 启动与进程残留逻辑将泄漏至正式镜像构建中。
- **最小契约修复**：
    在 `t011_v2_remove_legacy/task.md` 的【范围】（Line 11）及 AC-002（Line 26）中显式加入 `config/docker/entrypoint.sh 中的旧 VNC 与残存进程清理逻辑移除`。

### 缺陷 3：数据目录具名结构 `/data/engine-cache/` 未被纳入生命周期契约

- **规划出处**：`v2_architecture_plan.md` 第 3 章 Lines 151–154：
    ```text
    /data/
    ├── cbrowser.db
    ├── settings/
    ├── engine-cache/
    ├── profiles/
    ```
- **Task 现况**：`t002`（数据目录与持久化初始化）、`t003`（Browser Runtime 挂载）、`t010`（备份恢复）及 `t012`（Compose 正式数据挂载）均未定义 `/data/engine-cache/` 目录的归属、权限与挂载契约。
- **影响**：CloakBrowser 引擎二进制与指纹核心缓存无明确持久化挂载位置，可能导致各容器重复下载或写入不可预期的临时路径。
- **最小契约修复**：
    在 `t002_v2_backend_foundation/task.md`【范围】中加入数据根下 `engine-cache` 目录初始化；在 `t003_v2_browser_runtime/task.md` AC-001 中加入只读/共享挂载 `/data/engine-cache` 访问声明。

### 缺陷 4：Stream Gateway 连接活动状态追踪与聚合下发协议遗漏

- **规划出处**：`v2_architecture_plan.md` 第 9.3 节 Lines 455–464：
    > Gateway 为每个 ViewerConnection 记录：`connection_id`, `visible`, `last_activity`, `last_heartbeat`。Gateway 将当前 Profile 的所有连接状态聚合后通知 Stream Agent。
- **Task 现况**：`t004` AC-003（Line 27）声明接收聚合需求，`t007` AC-004（Line 28）声明前端上报可见性，但作为承上启下核心的 `t006_v2_gateway_auth_rtc` 在其【范围】与 AC-003（Line 27）中仅提及双向信令转发，**完全遗漏了 Gateway 内部维护连接活跃状态表及向 Stream Agent 聚合下发媒体需求的契约**。
- **影响**：信令隧道与帧率聚合策略断层，Stream Agent 无法获知前台连接聚合需求。
- **最小契约修复**：
    在 `t006_v2_gateway_auth_rtc/task.md` AC-002 或 AC-003 中增加断言：“Gateway 记录各连接 connection_id、visible、last_activity 和心跳，并将 Profile 级聚合需求协议通知 Stream Agent”。

### 缺陷 5：Artifact 上传 API 返回 `container_path` 契约未在 AC 中断言

- **规划出处**：`v2_architecture_plan.md` 第 6.2 节 Lines 266–272：
    > API 返回给浏览器自动化和文件选择器的 container_path 必须使用容器内路径，例如：`/exchange/uploads/example.pdf`。不能返回宿主机路径。
- **Task 现况**：`t008_v2_artifacts_automation/task.md` AC-001（Line 25）测试了文件校验、配额和防穿越，但未显式断言 API 返回结构必须包含容器内绝对路径 `container_path` (`/exchange/uploads/...`) 且严禁暴露宿主物理路径。
- **影响**：接口可能误返回宿主机路径，导致容器内浏览器或 CDP 自动化无法定位文件。
- **最小契约修复**：
    在 `t008_v2_artifacts_automation/task.md` AC-001（Line 25）中追加断言：“API 响应返回 Artifact ID 及容器内访问路径 container_path（如 /exchange/uploads/...），严禁暴露宿主机物理路径”。

### 缺陷 6：SQLite WAL 模式与 `busy_timeout=5000` 未在后端基础契约中显式固化

- **规划出处**：`v2_architecture_plan.md` 第 12.1 节 Line 671：
    > SQLite 开启 WAL，并设置 `busy_timeout=5000`。所有事务保持短小，禁止在事务中执行 Docker API 调用或等待浏览器启动。
- **Task 现况**：`t002_v2_backend_foundation/task.md` AC-004（Line 28）说明了并发锁竞争与忙等待，但未显式限定 SQLite PRAGMA journal_mode=WAL 及 busy_timeout=5000。
- **影响**：不同环境可能采用默认的 DELETE 日志模式或过短的 busy_timeout，导致多线程锁竞争时偶发 database is locked。
- **最小契约修复**：
    在 `t002_v2_backend_foundation/task.md` AC-004 中增加：“SQLite 显式启用 WAL 模式并配置 busy_timeout=5000，验证短事务且事务内不发生外部阻塞”。

### 缺陷 7：Profile 运行时状态模型缺失明确的错误恢复字段约束

- **规划出处**：`v2_architecture_plan.md` 第 12.2 节 Lines 677–685：
    > 每个 Profile 保存：`desired_state`, `observed_state`, `runtime_instance_id`, `config_version`, `failure_count`, `restart_blocked`, `last_exit_event_id`。
- **Task 现况**：`t002` AC-001/003 包含了期望/实际状态与版本，但在数据库 Schema 声明中未显式具名 `failure_count`、`restart_blocked` 和 `last_exit_event_id`。而后置的 `t005`（Supervisor）AC-004/005 则高度依赖此三项字段进行重试与阻断。
- **影响**：`t002` 产出的数据库模型如果遗漏这三项状态字段，`t005` 实施时将被迫修改 `t002` 锁定的 DB 契约。
- **最小契约修复**：
    在 `t002_v2_backend_foundation/task.md`【范围】（Line 11）中显式增加字段枚举：包含 `failure_count`、`restart_blocked`、`last_exit_event_id` 等运行时恢复字段。

### 缺陷 8：Browser Runtime `/dev/shm 1GiB` 与 Xvfb 扩展参数未在 AC 中锁死

- **规划出处**：`v2_architecture_plan.md` 第 4.2 节 Lines 197–198：
    > Browser Runtime 的 `/dev/shm` 设置为 1 GiB，Stream Runtime 使用同一 IPC 命名空间。Xvfb 显式启用 MIT-SHM、XTEST、XFIXES 等所需扩展。
- **Task 现况**：`t003_v2_browser_runtime/task.md` AC-002/006 声明了显示和 IPC 隔离，但未在 AC 中显式将 `/dev/shm 1GiB` 与 Xvfb 扩展参数（MIT-SHM, XTEST, XFIXES）列为必要检查项。
- **影响**：若镜像启动脚本漏设扩展，Selkies 画面捕获将回退至性能低下的慢速 XGetImage 复制。
- **最小契约修复**：
    在 `t003_v2_browser_runtime/task.md` AC-002 中显式加入：“Browser Runtime 配置 /dev/shm 大小为 1 GiB，Xvfb 启动参数显式加载 MIT-SHM, XTEST, XFIXES 扩展”。

### 缺陷 9：Selkies 2.1.0 官方 Commit 与关键环境变量未在 Stream Runtime 契约中固定

- **规划出处**：`v2_architecture_plan.md` 第 1.1 节 Line 35 与第 8.1 节 Lines 379–382：
    > Selkies 固定到官方 2.1.0 发布版本，对应提交 `6ee68a7a815956e6745e916741f13335e0b3ff53`。
    > 配置：`SELKIES_MODE=webrtc`, `SELKIES_ENABLE_DUAL_MODE=false`, `SELKIES_ENABLE_SHARING=true`, `SELKIES_ENABLE_COLLAB=false`, 不设置 `mk_control=true`。
- **Task 现况**：`t004_v2_stream_runtime/task.md` 范围提及 Selkies，但未显式锁定该 Git commit 散列值与上述 4 项环境变量的默认配置。
- **影响**：依赖未显式锁定时可能误拉取上游非预期提交或使用了错误的协作参数。
- **最小契约修复**：
    在 `t004_v2_stream_runtime/task.md`【范围】中追加：“锁定 Selkies 官方 2.1.0 (commit 6ee68a7) 及标准环境变量基线（MODE=webrtc, DUAL_MODE=false, SHARING=true, COLLAB=false）”。

### 缺陷 10：前端路由 `/profiles/:profileId/files` 与 `/automation/:profileId` 集成验证断层

- **规划出处**：`v2_architecture_plan.md` 第 13.1 节 Lines 744–750：
    > 路由：`/`, `/settings`, `/profiles/new`, `/profiles/:profileId`, `/profiles/:profileId/files`, `/automation/:profileId`。
- **Task 现况**：`t007` 在【范围】中说明文件与自动化业务由 `t008` 完成；但 `t008` AC-001 至 AC-005 集中在后端服务、下载与 CDP 代理，未包含对 React Router 中 `/profiles/:profileId/files` 与 `/automation/:profileId` 页面导航与渲染的端到端断言。
- **影响**：UI 层面这两个核心独立子页面可能仅作为组件存在，而缺失路由映射集成测试。
- **最小契约修复**：
    在 `t008_v2_artifacts_automation/task.md` AC-001 与 AC-002 中显式加入：“验证通过 /profiles/:profileId/files 与 /automation/:profileId 路由可正确加载对应功能组件并保持会话”。

### 缺陷 11：CPU 过载削峰降帧机制实现责任归属成孤岛 (Orphaned Requirement)

- **规划出处**：`v2_architecture_plan.md` 第 19.1 节 Line 1043：
    > 多流资源调度：CPU 超过阈值时按规则降低 Profile 级 FPS。
- **Task 现况**：`t009_v2_full_acceptance/task.md` AC-001（Line 25）明确断言：“过载按规则降低Profile级FPS”；但在前置的实现 Task 中，`t004`（Stream Runtime 帧率管线）、`t005`（Supervisor 主机容器监控）或 `t006`（Gateway 调度）均未声明实现该 CPU 监控与削峰降帧算法。
- **影响**：`t009` 在验收时会发现无任何模块负责该逻辑，导致验收无法通过或临时在验收阶段编写大块生产代码。
- **最小契约修复**：
    在 `t004_v2_stream_runtime/task.md` AC-003 或 `t005_v2_supervisor/task.md` AC-002 中明确界定 CPU 过载信号采集与 Profile 级动态削峰降帧指令的下发协议。

______________________________________________________________________

## 4. 核心规则与反模式深度审查

### 4.1 实施顺序与删除门禁审查 (Chapter 20 Order & Chapter 17 File Actions)

- **顺序严格性**：
    规划第 20 章规定的 12 步实施顺序：
    `01.技术验证 -> 02.新后端骨架 -> 03.Browser Runtime -> 04.Stream Runtime -> 05.Supervisor -> 06.Stream Gateway -> 07.前端 -> 08.文件与自动化 -> 09.安全和压力测试 -> 10.数据迁移 -> 11.删除旧链路 -> 12.Docker 发布`。
    全套 12 个 Task 的 `depends_on` 严格构成了与此一一对应的 DAG 依赖拓扑：
    `t001 -> (t002, t003) -> t004 -> t005 -> t006 -> t007 -> t008 -> t009 -> t010 -> t011 -> t012`。
- **旧 VNC/RFB 删除时机硬约束**：
    规划第 17 章末尾（Line 986）明确强调：“旧 VNC/RFB 链路只有在新架构通过完整验收后才删除。”
    契约核查确认：负责删除旧链路的 `t011` 显式设置 `depends_on: "t010"`，而 `t010` 依赖于 `t009`（完整安全与压力验收）。因此，**旧 VNC/RFB 链路删除严格受制于第 19 章全部验收通过与第 10 步可回退数据迁移通过**，完全符合规划原则。
- **旧 CDP 薄适配器保留例外**：
    规划第 14.3 节（Line 838）明确规定：“旧的 CDP 连接入口保留为薄兼容适配器，转发到新的 CDP 代理，不保留旧的 CDP 端口暴露方式。”
    契约核查确认：`t008` AC-002 明确断言“旧 CDP 入口仅薄转发新代理”，`t011` AC-001 再次确认“旧CDP入口只转发新授权代理，不发布旧CDP端口”。**旧 CDP 薄适配器在清理旧链路后得以有效存活，未被误删**。

### 4.2 隐式缩减范围分析 (Hidden Narrowing)

- **TURN 凭证轮换与 ICE 重启**：
    `t004` AC-004 中曾写道“按 t001 确认路径完成原计划凭证切换与 relay-to-relay 验收”。而事实上 `t001` 当前的本地实验仅验证了短周期容器握手，并未涵盖真实的 24h/12h/6h 调度。幸而在 `t006` AC-004 和 AC-005 中，完整重申了“24小时凭证每12小时更新并在旧凭证到期前6小时执行已验证 ICE restart”以及“真实 relay-only 双端选中 relay candidate 并以媒体增量证明两次凭证切换”，有效防止了对长期凭证轮换要求的隐式缩水。
- **中文输入法验证范围**：
    `t008` AC-004 承担了中文输入法与剪贴板桥接的初次落地，但其上下文说明 1000 次压力测试留给 `t009`。在 `t009` AC-003 中，完整包含了“完成 1000 次中文组合输入和 1000 次纯文本剪贴板，覆盖四类输入框及双页面输入”，指标与测试量未发生缩减。

### 4.3 不可证伪或虚假满足分析 (Non-falsifiable AC & Broad Claims)

- **反假冒完成规则**：
    全套 12 个 Task 均在【可测试性声明】中设立了强制门禁：“全部 AC 可自动测试；需真实部署/用户数据/原生平台的行为必须具备对应环境和授权，缺失时保持未通过，不用模拟替代。”
- **生产发布与真实授权**：
    `t012` AC-004 规定“获具体外部目标授权后发布，按真实线上状态执行Chrome冒烟并保存结果”。在此明确重申：**在没有用户明确提供真实外部发布目标、密钥和环境前，严禁任何 Agent 自行臆造假凭证或在 CI/本地测试通过后擅自勾选 AC-004**。
- **数据迁移真实用户数据**：
    `t010` AC-005 规定“用户实际数据操作需单独记录具体授权范围，不以演练代替实际迁移完成”。同样严禁在没有明确用户数据根授权的情况下声称迁移闭环。

### 4.4 任务边界与提交范围过大分析 (Commit Boundary Overload)

- **`t008` 职责过载风险**：
    `t008_v2_artifacts_automation` 当前承载了：
    1. 后端 Artifact Service 及 Repository 落地；
    2. Supervisor 经 UDS 的下载事件捕获及持久化；
    3. 外部 CDP 代理鉴权与旧入口薄转发；
    4. 前端 Artifacts 管理页面与组件迁移；
    5. 前端 Automation 管理界面；
    6. 前端 `ClipboardBridge` 与权限提示；
    7. 中文 IME 组合输入与四类输入框验证；
    8. Profile 复制（配置 vs 状态）与重置语义！
        该任务横跨 4 个独立子系统，包含 5 条密集 AC。虽然其内聚于“文件、自动化与输入数据”，但在实施阶段易导致单次提交变更集过大。建议执行时严格按“文件服务 -> CDP/下载 -> 剪贴板/IME -> 复制重置”顺序自测提交，避免中途引入不稳定的并发回归。

______________________________________________________________________

## 5. 第 19 章性能与验收指标全要素核对

规划第 19 章设定的指标属于正式验收的不可动摇基准，核对结果如下：

|规划条款|规划参数与指标|Task 对应行号与表述|审查结论|
|---|---|---|---|
|**硬件基准**|Linux x86_64, 16 vCPU, 32 GiB RAM, 无物理 GPU|`t009` AC-001 (Line 25)|**完全一致**（无改写或降配）|
|**测试场景**|1、3、10 活跃流；10 Profile 运行（9 后台 1 前台）|`t009` AC-001 (Line 25)|**完全一致**|
|**单流指标**|1080p30 稳定显示|`t009` AC-001 (Line 25)|**完全一致**|
|**交互延迟**|局域网 RTT≤10ms 时，操作到画面反馈 P95≤100ms|`t009` AC-001 (Line 25)|**完全一致**|
|**首帧延迟**|运行时就绪后首次画面呈现 P95≤1 秒|`t009` AC-001 (Line 25)|**完全一致**|
|**后台捕获**|后台页面停止本地解码，全部后台时暂停服务端捕获|`t009` AC-001 (Line 25)|**完全一致**|
|**持续压力**|连续 8 小时无数据损坏、会话串线或不可恢复退出|`t009` AC-002 (Line 26)|**完全一致**（严禁短测替代）|
|**输入压力**|1000 次中文组合输入 + 1000 次纯文本剪贴板|`t009` AC-003 (Line 27)|**完全一致**|
|**输入场景**|地址栏、普通输入框、受控输入框、富文本编辑器|`t009` AC-003 (Line 27)|**完全一致**|
|**剪贴板保护**|保护原内容、权限拒绝明确提示、后台不覆盖|`t009` AC-003 (Line 27)|**完全一致**|
|**安全矩阵**|落实计划 16 章 12 行来源-目标矩阵与容器加固|`t009` AC-004 (Line 28)|**完全一致**|

______________________________________________________________________

## 6. 后续行动建议与契约补强清单 (Recommended Next Steps)

在 `t001` 推进及后续 Task 启动前，建议按以下最小契约修改完善各 Task 文件（仅修补文档契约，不动实现）：

1. **补强 `t002_v2_backend_foundation`**：
    - 范围加入 `src/backend/diagnostics.py 结构化日志` 与 `/data/engine-cache/`。
    - AC-001 加入模型字段 `failure_count`, `restart_blocked`, `last_exit_event_id`。
    - AC-004 加入显式配置 `PRAGMA journal_mode=WAL` 与 `busy_timeout=5000`。
2. **补强 `t003_v2_browser_runtime`**：
    - AC-002 加入容器 `/dev/shm 1GiB` 挂载及 Xvfb 启用 `MIT-SHM`, `XTEST`, `XFIXES` 扩展。
3. **补强 `t004_v2_stream_runtime`**：
    - 范围锁定 Selkies 2.1.0 官方 commit `6ee68a7a815956e6745e916741f13335e0b3ff53` 及 4 项核心环境变量。
    - AC-003 界定 CPU 超过阈值时的 Profile 级 FPS 削峰下发机制。
4. **补强 `t006_v2_gateway_auth_rtc`**：
    - AC-003 加入 Gateway 记录各连接 `connection_id`, `visible`, `last_activity`, `last_heartbeat` 并聚合通知 Stream Agent 协议。
5. **补强 `t008_v2_artifacts_automation`**：
    - AC-001 加入上传成功后返回 `container_path`（`/exchange/uploads/...`）且严禁暴露宿主机路径的断言。
    - AC-001/002 加入路由 `/profiles/:profileId/files` 与 `/automation/:profileId` 的渲染集成断言。
6. **补强 `t011_v2_remove_legacy`**：
    - 范围与 AC-002 加入 `config/docker/entrypoint.sh` 旧 VNC 逻辑删除。
7. **坚守 `t001` 技术门禁**：
    - 维持 `t001` 当前 `active` 状态，直至 PulseAudio 真实音高时钟、原生 Linux x86_64 及公网 candidate 获得完整复核通过。

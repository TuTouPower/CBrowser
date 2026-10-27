# Task spec

## 背景

v2.3 Browser Runtime 负责真实 CloakBrowser、显示、音频和受控本地 Agent；浏览器数据不得与媒体处理或宿主调试端口混用。本 task 仅在 t001 全部技术验证通过后实施。

## 契约区

### 范围

- config/docker/browser_runtime/ 独立镜像与启动配置、src/backend/cbrowser/runtime_agent/ Browser Agent、独立运行时协议 schemas/runtime/ 及本 task 新测试；引擎缓存遵循统一数据根 /data/engine-cache/，与用户数据分离，缓存初始化/访问权限通过 Supervisor 挂载契约明确，不把镜像内调试路径视为正式数据布局。运行真实浏览器、Xvfb、Openbox、Profile 音频、agent.sock 与退出事件。主写域不包含 API、数据库、Stream Runtime、共享 pyproject.toml 或正式 compose。

### 非范围

- Supervisor 编排、业务 API/数据库写入、Stream Runtime 编码和前端界面、现有用户数据迁移、旧链路删除。不得直接发布 CDP TCP 或把 Browser Runtime 接入 API 管理网络。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：同一 Profile 的浏览器用户数据跨容器重建后仍存在；两个 Profile 的 Cookie、文件、显示与音频互不污染，容器内不能读取其他 Profile 数据。
- [ ] AC-002：运行时就绪前检查显示、真实浏览器与虚拟音频；任一子系统失败时返回明确故障，不能在无声或无显示状态报告 ready；浏览器完整 UI 按 Profile 分辨率及 DPR1 显示。
- [ ] AC-003：经受控 Unix Socket 取得健康、配置版本、CDP 双向流和下载事件；未知操作和通用 shell/任意文件访问请求被拒绝，容器网络及宿主不能直接连接 CDP。
- [ ] AC-004：真实 HTTP 下载写入 /exchange/downloads 并产生完整事件；外部自动化覆盖下载策略后断开，Agent 自动恢复捕获，之后第二次下载仍被捕获且文件内容正确。
- [ ] AC-005：真实浏览器正常关闭和异常终止产生可跨 Agent 重启恢复的退出事件，包含实例与配置版本；正常退出不会被 Agent 或 Docker 自动重启；事件不混入浏览器用户数据。
- [ ] AC-006：以非 root、只读根文件系统和最小权限运行；无法访问 Docker Socket、宿主 X11、其他 Profile IPC 或数据，获授权的同 Profile Stream 客户端才能接入 X11 与音频。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；需要真实 Docker、Chrome 和相应已验证网络环境，缺失时不得勾选部署行为。

## 上下文区

- 来源：docs/v2_architecture_plan.md（2026-10-27 核对）；t001 为技术验证硬门禁，尚未完成

### 有意不测

- 迁移现有用户数据与正式环境发布：由后续独立迁移/发布 task 验收，本 task 只在全新隔离测试目录运行

### 测试策略

- 独立 Docker 容器启动真实 CloakBrowser，使用本地 HTTP 测试站点产生 Cookie/下载和音频；真实 UDS/CDP、进程退出/重启、文件校验与跨 Profile 负例。单测覆盖协议校验和事件写入，Docker E2E 证明挂载、权限与数据持久。禁止 mock 被测 Browser Agent 或只检查容器存活。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- UNVERIFIED-SPIKE：以 t001 最终确认的 Xauthority、共享 IPC、音频认证、CDP 和退出事件契约为前提；t001 未完成前不得根据原型假定正式协议。

### 风险与回退

- 风险：挂载路径、权限、退出事件丢失或 CDP 暴露可能泄漏 Profile 数据；禁止调试挂载真实数据目录。
- 回退：实验和新模块通过独立 worktree、数据目录及容器前缀验证；不覆盖现有用户数据、不切换旧正式运行入口。失败保留证据和当前分支，不迁移或删除旧链路。

### 依赖与约束

- t001 全部通过并冻结技术结论，且t002提供已验证配置版本快照/字段契约后才能start；Browser Agent消费该快照，不另建配置真相。实现约束：Browser独立shareable IPC、/dev/shm为1GiB，Stream使用container:<browser-id> IPC；Xvfb显式启用MIT-SHM/XTEST/XFIXES且不监听TCP，测试实际查询扩展并捕获XShm，不以启动参数代替证据。公共索引与跨模块总览由主控在各 task 收尾阶段串行更新，实现 agent 只写本模块，不并发改公共控制面。

### Finalization 时更新的 blueprint

- docs/blueprint/browser_runtime.md：进程、UDS、音频和事件边界；docs/specs/browser_isolation.md：双容器下 Browser Runtime 行为，移除该 spec 中失效单容器/旧 exchange 约定。公共 specs_index 由主控在 task worktree 收尾时串行更新。

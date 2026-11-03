# Task spec

## 背景

2026-11-02 intensive review（docs/reviews/review_20261102_201727）在 v2 后端（API 控制面、数据模型、Supervisor、Runtime Agent、存储）发现一批边界、健壮性与契约问题：Supervisor 上报端点挂在用户会话面、/health 阻塞事件循环、下载产物路径可越界、对账单点异常拖垮全部 Profile、全局可写的权限回退、启动参数黑名单可穿透、OpenAPI 未声明认证与错误码、blueprint 与代码多处矛盾等。用户以“最好的架构、最少的技术债”为标准全部采纳。

## 契约区

### 范围

- API 控制面：Supervisor 上报只走内部面；认证与事件流加固；OpenAPI 与内部 API 契约完整化。
- 数据模型：删除单值死字段 runtime_mode/viewer_mode；仓储测试基于真实迁移。
- Runtime Agent：探活不阻塞事件循环；CDP 事件监听单帧隔离与自愈；启动参数白名单。
- Supervisor：对账按 Profile 隔离；下载产物转发越界拒绝与失败留痕；各项健壮性与一致性修正。
- 文件所有权：统一运行时数据归属，删除全局可写回退。
- 后端相关 blueprint/spec 与代码对齐。

### 非范围

- 不改 Gateway、Stream Agent、TURN/ICE 机制与前端浏览器会话层（归 t015）；不改前端外壳与客户端（归 t017，但本 task 负责重新生成前端 API 类型）；不做测试体系整体整改（归 t018）；不迁移用户数据、不删除 legacy 栈（归 t010）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [x] AC-001：运行时绑定、observed 状态与运行事件上报只能经 Supervisor 服务凭证的内部面调用；用户会话请求这些路径被拒绝；架构测试枚举全部路由，断言上报类路径只出现在服务面。
- [x] AC-002：Runtime Agent 健康探活期间，CDP 隧道与其他端点的响应不被阻塞；CDP 事件流中单个非法或异常帧不影响后续事件与命令，连接断开后自动重连并恢复下载捕获。
- [x] AC-003：下载产物：越出该 Profile 下载目录的路径被拒绝并隔离；无法解析的事件留下日志并进入可人工恢复的隔离区、修复后可重试；磁盘事件信封带版本并按版本兼容或隔离；ingest 失败返回明确原因；超长文件名被正确截断并登记，不被静默丢弃。
- [x] AC-004：Supervisor 对账中单个 Profile 的异常不影响其他 Profile 的会话恢复与孤儿清理；启动对账失败时控制面仍可用并后台重试；资源采集、状态查询、标签与 token 读取的异常和格式问题按约定映射（单 Profile 隔离、503、启动即报错）。
- [x] AC-005：认证与事件流：伪造的自动化令牌不产生数据库写入且被限流；Retry-After 反映真实等待时间；服务未配置时返回 503 而非 500；自动化令牌可设置过期并按期拒绝；过期会话被清理；API 文档端点默认关闭；SSE 订阅的初始快照与实时事件不乱序，断线续传语义明确且有测试。
- [x] AC-006：公开 OpenAPI 与新增的内部 API 契约声明全部认证方式（会话 Cookie、CSRF 头、服务 Bearer）与实现实际可达的错误码；守卫测试保证实现可达响应码包含于契约；前端生成类型与契约同步。
- [x] AC-007：数据模型、API 响应、配置快照与契约中不再包含 runtime_mode/viewer_mode；数据库迁移可从现有 schema 升级；仓储测试在真实迁移建出的 schema 上运行，且模型与迁移的一致性受测试守护。
- [x] AC-008：运行时数据统一归属运行用户（uid 1000），任何代码路径都不产生全局可写的文件或目录，所有权设置失败即报错；配置快照、Pulse cookie、Xauthority 仅属主可读写，Browser 与 Stream 双容器在此权限下正常工作。
- [x] AC-009：Profile 启动参数按白名单在 API 层校验，非法参数返回 422；Runtime 启动前再次校验；用户参数不能覆盖内置参数或指纹参数；绕过类参数（扩展加载、JS 引擎参数、位置参数、指纹参数）均被拒绝且有测试。
- [x] AC-010：其余加固：内部 URL 中的标识符正确转义；控制面 CDP WebSocket 在接受连接前鉴权；操作日志损坏时隔离并降级处理；阶段指标区分累计值与区间值；下载事件有界保留且去重不丢；Artifact 配额在并发上传下不被突破；Runner 的运行路径与环境变量不跨实例共享；artifact_id 经单组件校验；Profile 锁与幂等回放各只有一处实现。
- [x] AC-011：后端相关 blueprint 与 spec 与代码和已落地决策一致（第 4 次异常阻断、runtime_events 随 Profile 级联删除、旧库迁移工具归 t010 且 AC 未勾、schema 落点表、ObservedState 枚举、settings 表、t001 spec 时点标注），blueprint 文首声明与代码冲突时以代码与生效 spec 为准。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-008：双容器权限需真实 Docker 运行验证，以现有 Browser/Stream E2E 在新权限下通过为证据。
- AC-011：文档一致性以人工复核为主，辅以 grep 与 spec 中 AC 勾选状态检查。
- 其余 AC 可自动测试。

## 上下文区

- 来源：docs/reviews/review_20261102_201727/adoption_decision.md 的 A1、A2、A3、A4、A5、A6、A7、A13、A14、A23、A26（OpenAPI 与内部契约部分）、A28、A29、A31、A32、A33、A35（下载截断部分）、A45（用户决策 A，白名单）；对应 finding 见该文件映射。2026-11-02 核实。

### 有意不测

- 无。

### 测试策略

- 每个缺陷先写失败测试（红）再修复（绿）；契约变更后重新导出 schemas 并运行漂移守卫；权限模型改动以单元测试断言精确 mode，并在真实 Docker 下跑 Browser/Stream E2E。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- Browser 与 Stream 容器在 uid 1000 + 仅属主权限下共享 Xauthority 与 Pulse cookie：已验证。真实 Gateway/Supervisor 拓扑下用当前源码镜像启动双容器并通过 `test_frontend_session_e2e.py::test_frontend_session_dual_tab_identity_refresh_copy_no_kick_and_close`（真实 Chrome、媒体、输入、复制/刷新），X11 目录 0750、Xauthority 0600；ADR 014。

### 风险与回退

- 风险：删除字段与契约变更影响前端生成类型与既有测试；权限收紧可能破坏开发期在 macOS 主机直接运行 API 的路径。
- 回退：在独立 worktree 实施，迁移可降级；开发路径改为容器内或匹配 uid 运行，失败则保留分支不合入。

### 依赖与约束

- 无硬前置；与 t015 同改 docs/blueprint 与 schemas/，串行执行；契约改动须在 t017 之前合入。

### Finalization 时更新的 blueprint

- `docs/blueprint/persistence.md`、`domain.md`、`conventions.md`、`security.md`、`supervisor.md`、`browser_runtime.md`、`artifacts.md`、`decisions.md`（文件所有权 ADR）
- `docs/specs/storage_and_artifacts.md`、`runtime_persistence.md`、`access_control.md`、`v2_runtime_validation.md`

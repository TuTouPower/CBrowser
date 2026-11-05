# Task spec

## 背景

控制 API 的配置校验、异步鉴权、服务身份说明与文件交换存在多处契约差异；Artifact 文件/DB 操作失败后缺乏可继续处理的明确状态。将本组收敛为统一控制与数据交换契约，在同一可独立验证的执行 commit 中交付。

## 契约区

### 范围

- 控制 API、鉴权、Profile/Artifact 仓储与服务、内部文件报告、相关 DTO/错误与日志导入。
- 协议/OpenAPI 导出入口、服务身份与生成类型；本组行为回归、文件操作故障注入及迁移测试随实现完成。

### 非范围

- 不整改、转报或同步 repo_template，不修改其脚本、hook、契约测试、模板规则或账本示例；不创建已拒绝 A36/R10 的后续任务。
- 不建设已拒绝 A37/R11 的正式备份、恢复、迁移演练、生产切换闭环；不执行生产停服、数据删除或外部发布。
- 不重开 t009/t010/t012，不恢复 legacy，不扩大单机/同机 Chrome 的部署包络，不恢复 TURN。
- 现有 t019 的 ICE 建链延迟、t020 的字体配置各自保持范围；本 task 不重复实现或把其验收顺带标为完成。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001（A2）：创建与更新请求均拒绝越界 launch_args 并返回 422；更新未提供字段、显式 null 与合法参数分别符合当前 PATCH 契约，历史配置读取仍按既有过滤规则处理。
- [x] AC-002（A4）：Profile 普通读取返回原有 DTO，不读取不可变版本与 Artifact 历史集合；存在性与下载去重只读取其判断所需数据，历史集合增长不使普通读取额外加载完整历史。
- [x] AC-003（A5）：合法与错误密码的实际 Argon2 运算期间，事件循环仍能处理其他请求；鉴权结果、哑元验证、限速顺序与脱敏行为保持一致。
- [x] AC-004（A6）：Supervisor、Gateway、Artifact 服务缺配置时返回独立错误码且 retryable=false；数据库锁忙保留可重试响应；内部写端点对无/错服务令牌拒绝且不泄露内部状态。
- [x] AC-005（A7）：持有效会话与 CSRF token、仅携 Referer 的请求，同源允许，外站和畸形 Referer 拒绝；用例能证明请求确实进入来源校验分支。
- [x] AC-006（A12）：一次完整成功扫描后消失实例的下载游标被清除；读取失败不误删游标，重启后仍可正确重放；恢复扫描与单例保护采用相同锁文件身份。
- [x] AC-007（A31）：导出 OpenAPI 对每条内部路由声明真实所需 Supervisor/Gateway 身份；Artifact 使用 Supervisor 身份；HTTP 与 SSE 运行状态仅允许实际领域枚举，生成前端类型与应用一致。
- [x] AC-008（A40）：Artifact 删除在文件或 DB 操作失败、进程重启后可按持久化意图继续且重复调用幂等；合法可信历史实例的迟到下载可接纳，未知/伪造实例或越界路径拒绝；非法 token 拒绝有有界脱敏审计，成功请求不抹除其他失败记录。
- [x] AC-009（A41）：每种实际 HTTP/WS 协议消息均能定位并通过自身导出 schema 入口校验；错误消息按对应入口拒绝；导出确定、包含一致文档元数据与尾换行，不把文档版本误作线上协商版本。
- [x] AC-010（A42）：运行事件日志在打包后的 cbrowser 包内可正常导入和写入；无生产消费者的 automation-authorize 路由及其契约不再可用，实际 CDP 授权仍通过统一权限入口；canonical Origin 与秘密读取沿真实 Gateway→API 链路保持一致。
- [x] AC-011（A46）：创建、更新及提交竞争后的相同幂等请求得到一致结果，不同签名冲突被拒绝，目标已删除时结果可预测；领域与持久化时间输出使用同一语义和格式。
- [x] AC-012（A54）：用户上传与浏览器下载均允许可执行内容，声明 MIME 不被当作安全证明；两条入口采用相同规范化与缺省规则并拒绝非法头值；取回文件始终为 attachment 且带 nosniff，身份、路径、配额与完整性保护不放宽。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；真实 Docker/Chrome、数据库与 HTTP 调用使用隔离数据根及受控故障注入，缺前提明确未验证，不将静态检查或 skip 作为真实运行证据。

## 上下文区

- 来源：用户 2026-11-03 明确要求为全部采纳项合并立项；[review_20261103_185924 决策](../../reviews/review_20261103_185924/adoption_decision.md)；本组 A2、A4、A5、A6、A7、A12、A31、A40、A41、A42、A46、A54。原 D1=B、原 D2=A 已按用户选择写回；本轮仅创建 backlog，不授权实施或提交。

### 采纳项承接与设计边界

|采纳项|主验收|来源 finding|
|---|---|---|
|A2|AC-001|f_backend_api_auth_01, f_backend_api_auth_09, f_global_architecture_07|
|A4|AC-002|f_backend_runtime_adapters_01, f_backend_runtime_adapters_08, f_backend_runtime_adapters_09|
|A5|AC-003|f_backend_api_auth_04|
|A6|AC-004|f_backend_api_auth_06, f_backend_api_auth_11|
|A7|AC-005|f_backend_api_auth_10|
|A12|AC-006|f_backend_supervisor_08, f_backend_supervisor_10|
|A31|AC-007|f_contracts_deploy_09, f_contracts_deploy_10|
|A40|AC-008|f_backend_runtime_adapters_13, f_backend_api_auth_07, f_backend_api_auth_08|
|A41|AC-009|f_contracts_deploy_07, f_contracts_deploy_08, f_contracts_deploy_16|
|A42|AC-010|f_backend_api_auth_03, f_backend_runtime_adapters_11|
|A46|AC-011|f_backend_runtime_adapters_10|
|A54|AC-012|f_backend_runtime_adapters_07|

以下为已采纳修复边界；具体结构选择以满足当前需求的最简单长期实现为准，不以开发时间或改动规模降级。

- **A2 · 更新 DTO 仅保留严格 launch_args 校验并补负例**：删除更新 DTO 的 normalize_launch_arguments，保留严格 validate；历史读取仍在 ProfileConfig 过滤。按现行 PATCH 契约明确未提供与 explicit null 语义，补 PUT/PATCH 越界参数 422、合法值、null 的真实 HTTP 回归。
- **A4 · Profile 查询只加载调用方需要的数据**：models.py/repository.py 对普通查询显式只加载 tags/必要 runtime，版本与产物由专用方法查询；ArtifactRepository 增加标量存在性查询替代返回 ORM；下载去重把 storage_path 放入 SQL WHERE。验证返回 DTO 不变及查询不读取历史集合。
- **A5 · 卸载 async 登录路径中的 Argon2 同步运算**：auth/service.py 将真实和哑元 verify 放入 asyncio.to_thread，保留同等失败行为、限速顺序与脱敏；hash 调用按所在 async 路径同样处理。使用阻塞探针验证事件循环仍可推进；密码长度上限不在本项擅自变更。
- **A6 · 区分配置缺失与数据库忙，并覆盖内部面拒绝**：在 app.py 与内部依赖抛出点使用明确 service_not_configured 错误码和 retryable=false，保留数据库锁忙专用响应；对 Supervisor/Gateway/Artifact 未配置、无/错令牌及三条状态写端点补负向 HTTP 断言。同步生成 OpenAPI 与前端类型。
- **A7 · 补 CSRF Referer 回退路径行为测试**：tests/integration/test_auth_api.py 补允许来源 Referer-only 放行、外站 Referer 拒绝、畸形 Referer 拒绝；保留正确 CSRF token，避免测试在更早鉴权层失败。
- **A12 · 修剪失效下载游标并复用单例锁文件名**：artifact_forwarder.py 以完整事件树实例集合识别消失项，在一次完整成功扫描后删除过期游标；读取失败不得当作空树。recovery_coordinator.py 导入 SINGLETON_LOCK_NAMES。补实例消失/扫描失败不丢游标回归。
- **A31 · OpenAPI 正确描述服务身份与运行状态枚举**：app.py 按 internal router 实际 require_supervisor/require_gateway 选择对应 security scheme，Artifact 归 Supervisor；ProfileRuntimeResponse 与 SSE DTO 复用现有 DesiredState/ObservedState。由源生成 schemas 与 TS 类型并同步原失效测试，补独立错误令牌矩阵，不手改生成文件。
- **A40 · 跨文件与数据库操作具备可恢复状态机**：Artifact 删除先在 DB 事务登记删除意图/待清理状态，严格校验受管路径，在受控工作单元删除文件后完成元数据删除；失败/进程重启可继续，重复调用幂等，拒绝对异常目录直接递归删除。下载报告下传 runtime_instance_id，验证 Profile 的可信历史实例与文件归属、校验和，不仅校验当前绑定；合法离线重放可接纳，伪造/未知实例拒绝。审计统一记录拒绝类别与来源，未知/非法 token 采用有界聚合而不保存 token/hash；配置限速不得被成功请求清掉其他失败。补边界故障注入、跨重启恢复、历史实例和审计脱敏测试；同步迁移与契约。
- **A41 · 导出契约使用明确消息入口与一致元数据**：三个 export\_\*\_protocol.py 采用一致 JSON Schema 文档约定，按消息名暴露可直接引用的 $defs/$id 入口，说明每条 HTTP/WS 消息使用哪个 schema；有 action discriminator 的线上 envelope 保留其判别规则。若保留文档 revision，所有导出器使用同形字段但值按各协议独立来源维护，不冒充线上协商；OpenAPI 与协议导出统一尾换行和确定性序列化。消费者针对消息入口校验；现有全量生成一致性测试继续守卫。
- **A42 · 安全归一化有明确入口，删除无消费者授权面**：将运行事件日志能力移入 cbrowser 包，所有调用使用明确包导入并更新镜像打包/入口，删除旧导入布局，不留兼容转发层。确认 automation-authorize 的生产调用与现行 spec 范围后移除无消费者路由/DTO/导出项及仅验证该旧面的测试；保留实际 automation CDP 入口并以统一 AuthService 授权。Origin 在 Gateway 入口归一化、API 内部面明确接受 canonical Origin，补链路契约测试；read_secret_file 已 strip 的冗余调用统一，不重复实现规则。
- **A46 · 幂等恢复与时间格式由单一实现定义**：repository.py 将审计签名匹配、结果查询和提交竞争恢复收敛为仓储内明确 helper，调用方传清 action/target/result，不用通用回调框架；统一已删除结果的幂等契约并补并发测试。models.py 使用 domain 的 utc_now_iso 唯一实现，列默认与显式写入同一格式；不保留旧 helper 别名。
- **A54 · Artifact 允许任意内容，统一传输与 MIME 语义（原 D2）**：移除按可执行 MIME 名单拒绝上传的内容限制及下载侧对应强制重标分支；上传与浏览器下载共用 MIME 规范化规则，缺失类型使用 application/octet-stream，继续拒绝非法头值。用户下载统一 attachment 与 nosniff；保留身份、Profile/instance、路径、配额与完整性校验。同步生效 spec 与产品说明，明确不做恶意代码扫描；以真实调用路径覆盖可执行内容上传/下载一致性及附件响应头。过时的“必须拒绝可执行 MIME”测试整体删除并说明政策变更，新增验证新政策的测试，不就地改旧预期冒充原契约通过。

### 有意不测

- repo_template 整改、正式备份恢复/切换与已拒绝项：用户明确排除，不新建相关测试。
- 公网/跨主机媒体与原生 x86 环境：不扩大现行单机包络，沿用已记录用户豁免，不宣称实测。

### 测试策略

- 按行为先红后绿：真实 HTTP 覆盖 launch_args/null、Referer 回退、错误码与服务令牌矩阵；实际 Argon2 阻塞探针证明事件循环继续推进。
- 使用隔离 SQLite 与文件树，在删除各边界/进程重启注入故障；覆盖可信旧实例迟到下载、重放、非法路径、配额、内容类型及 attachment/nosniff。
- 创建/更新并发幂等竞争、普通读取 SQL 集合、日志镜像导入和每消息 schema 入口验证；实现改契约时从源重新导出 OpenAPI/协议及前端类型。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

无未核实外部契约；均为当前源码中的内部行为与现有依赖调用。新删除意图字段、报告身份与错误码需在本 task 定义并通过迁移和生产调用链验证，不靠兼容分支保留两套语义。

### 风险与回退

- 风险：持久化删除意图与迟到实例判断可能误删文件或拒绝合法重放；身份与 schema 变更可能与调用方不同步。
- 回退：只在隔离数据根验证可逆迁移与故障重放；任何真实数据操作先遵循已有批准与保护。失败保留原文件及未完成意图，不吞错误；以经验证的代码版本恢复服务，不移除已写状态或伪造完成。

### 依赖与约束

- 不依赖 t019/t020 的新功能；与 t020 共改 Profile 模型、repository、迁移及生成契约，执行须串行或基于已整合结果，不能并行编辑相同文件。
- 后继运行时 task 使用本组导出消息入口、服务身份与持久化契约；本组自身回归不得推给后继验证 task。
- p017/p018/p019 仅作为既有重叠证据引用，保持原文件；仅本组明确采纳的部分纳入，不宣称整条 pending 已闭环。

### Finalization 时更新的 blueprint

- `docs/blueprint/domain.md`：更新字段校验、null、幂等及时间语义。
- `docs/blueprint/artifacts.md`：允许任意内容、附件传输、删除意图与可信历史实例接纳。
- `docs/blueprint/persistence.md`：新的删除状态/实例证据迁移与查询加载边界。
- `docs/blueprint/security.md`：服务身份、日志/审计脱敏与 canonical Origin 边界。
- `docs/blueprint/automation.md`：移除无消费者授权面，保留实际 CDP 授权事实。
- `docs/blueprint/testing.md`：真实 HTTP/消息入口、文件故障及幂等验证要求。

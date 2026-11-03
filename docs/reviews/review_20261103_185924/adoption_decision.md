# 审阅结果决策

## 目录

docs/reviews/review_20261103_185924

## 报告来源

- 已读：根目录全部 44 份 bundle（22 局部、4 全局、16 精查、1 仓库汇总、1 交叉证伪）；聚合 review_intensive.md 按全部 finding ID 与 bundle 全量核对。下列文件为来源全集：
    - bundle_cross_validation.md
    - bundle_followup_q_architecture_01.md
    - bundle_followup_q_architecture_02.md
    - bundle_followup_q_architecture_03.md
    - bundle_followup_q_architecture_04.md
    - bundle_followup_q_evolution_01.md
    - bundle_followup_q_evolution_02.md
    - bundle_followup_q_evolution_03.md
    - bundle_followup_q_evolution_04.md
    - bundle_followup_q_strategy_01.md
    - bundle_followup_q_strategy_02.md
    - bundle_followup_q_strategy_03.md
    - bundle_followup_q_strategy_04.md
    - bundle_followup_q_system_properties_01.md
    - bundle_followup_q_system_properties_02.md
    - bundle_followup_q_system_properties_03.md
    - bundle_followup_q_system_properties_04.md
    - bundle_global_architecture.md
    - bundle_global_evolution.md
    - bundle_global_strategy.md
    - bundle_global_system_properties.md
    - bundle_local_archive_reviews.md
    - bundle_local_archive_spikes.md
    - bundle_local_archive_tasks.md
    - bundle_local_backend_api_auth.md
    - bundle_local_backend_core.md
    - bundle_local_backend_runtime_adapters.md
    - bundle_local_backend_stream_gateway.md
    - bundle_local_backend_supervisor.md
    - bundle_local_backend_tests.md
    - bundle_local_contracts_deploy.md
    - bundle_local_docs_current.md
    - bundle_local_frontend_features.md
    - bundle_local_frontend_shell.md
    - bundle_local_template_scripts_ops.md
    - bundle_local_template_scripts_state.md
    - bundle_local_template_support.md
    - bundle_local_template_tests.md
    - bundle_local_tests_e2e_stream_frontend.md
    - bundle_local_tests_e2e_supervisor.md
    - bundle_local_tests_integration_fixtures.md
    - bundle_local_tests_unit_stream_api.md
    - bundle_local_tests_unit_supervisor_runtime.md
    - bundle_repository_summary.md
    - review_intensive.md
- 缺失：无。未进入任何子目录，未读取 \_meta 或历史 adoption 原文。
- 合并说明：300 条原始 finding（HIGH 9、MEDIUM 67、LOW 173、INFO 51）全部且仅映射一次；局部 268 + 全局 30 + 精查新增 2 = 300。聚合无独有或遗漏 finding。族归并表示共同处置方向，不把不同位置误称同一根因；各原项覆盖范围与去向见文末逐项映射。Info 在决策优先级归 LOW，原严重度保留在映射。
- 本轮为 intensive 单源多视角，重复来源不是多模型互证。跨 bundle 主项全部列于各决策“来源”；无新 finding 的精查通过补充来源与反证说明关联。

## 评估标准

- 用户本轮明确指定：以架构、设计与最少长期技术债为目标；开发时间、改动大小、开发消耗不作拒绝理由。本标准优先于 skill 中“修复成本低”的默认采纳条件。
- 采纳依据：职责正确、单一权威、明确数据与安全边界、可恢复状态机、可演进契约和真实验证。运行资源、认知复杂度、安全风险与新增维护负担仍是设计指标，不等同开发预算。
- 不采纳仅限：前提已失效/误报；修复建议破坏现行正确不变量；重复已有权威或引入无需求机制；违反历史不可变等写权规则。现有契约需要改变时明确替代，不靠兼容层维持两套路径。
- 用户明确排除 repo_template 全部整改，以及正式备份、恢复与切换闭环；不以其他 A 项转报、登记或变相承接。Artifact 内容政策已按用户原 D2=A 确定；搜索引擎按用户原 D1=B 确定为失败不阻断浏览器、明确提示并支持重试。

## 本次重评与编号变化

- 保留已讨论编号，不重排后续项。原 A36 → R10；原 A37 → R11；原 D2（用户已填 A）→ A54；原 D1（用户明确选 B）→ A55。无待决定项。
- 原 A38 中账本模板残留两条 finding 转 R10；其他产品事实与证据勘误保留。A52 仅针对 CBrowser 自有隐私守卫与历史隐私边界，不修改 repo_template 工具链、测试或流程。
- 300 条 finding 仍逐条恰映射一次。用户已授权为全部采纳项分组立项；本轮创建 backlog task，不实施代码、不启动任务，不将立项请求推定为 review 归档提交授权。

## 基线与验证边界

- review 快照：b47340828820960adc6725407df72c6e11ee348c。远程报告提交：4f78524；本次通过 merge 7e55493 合入，保留原有本地提交。
- 源码复核 HEAD：0ad2e0247eb76d2dd27e90e2e5a687582ba25915（main）。本次决策修订时 HEAD 为 0ad91a2；其间 165bf31/0ad91a2 为并行任务归档与创建，不属于本次 adoption。本地 000aab3/d591781 已新增部署工件、移除 legacy；复核期间新增 1a073e6/3eb8578/0ad2e02 的入口、Origin 与 Caddy 重载变更也纳入比较。未据 commit 标题认定已实测部署、迁移或完成 task。
- 验证：通读全部 bundle；解析并核对 300 finding、原始严重度和聚合来源；定点核对当前源码、Dockerfile/ignore、Compose、schema 守卫、实例 stop 测试、ADR 与 pending。证据等级为静态核对。未跑业务测试、镜像构建、生产探针或真实迁移；未打开/输出秘密文件。
- 交叉证伪 9 条：8 agree、1 partial（f_global_strategy_01）；按当前代码复核后，agree 不能覆盖基线变化。PARTIAL 的 legacy 停用、冻结不修口径已吸收。Origin/鉴权/连接方向/seed 精查反证已吸收；注册自愈只有静态组合证据，insufficient 保留。
- 工作区范围：任务归档、p020 与 t019/t020 等并行工作不属于本次 adoption，保持不动；现有任务与并行工作保持不动；本轮新增 t021–t024、由工具派生 tasks_index，并更新当前 review 决策。t009/t010/t012 已进入归档，不再按旧路径视为 backlog。
- 当前阶段按用户明确要求创建分组 backlog task 并更新本决策；不实施代码、归档改写、生产运行或 push；repo_template 整改行动已明确拒绝。A 项均有确定结论。已有 p017/p018/p019 复用承接，不能重复登记。

## 统计

- 采纳：53 项
- 不采纳：11 项
- 待决定：0 项

## 立项承接

用户 2026-11-03 授权为全部采纳项合并立项。现有 t019/t020 不等价，保留原范围；新增 4 个 backlog task，当前共 6 个。新任务均为 full review，每个 A 项只有一个主承接及一条主 AC，设计边界与配套测试一并纳入。

|task|统一交付结果|采纳项数|硬依赖|文件/验证冲突|
|---|---|---|---|---|
|[t021](../../tasks/t021_control_api_artifact_contracts/task.md)|统一控制 API 与文件交换契约|12|无|t020|
|[t022](../../tasks/t022_runtime_gateway_reliability/task.md)|修正运行时恢复、隔离与信令状态|16|t021|t019、t020|
|[t023](../../tasks/t023_frontend_session_consistency/task.md)|统一前端会话、请求与交互语义|7|t022|t020|
|[t024](../../tasks/t024_delivery_verification_evidence/task.md)|收敛产品交付与验证证据体系|18|t023|t019、t020|

硬依赖按新契约消费顺序设置：t021 → t022 → t023 → t024。现有两项只登记实际冲突，不添加无关功能前置。全量串行参考：`/task-run t019 -> t020 -> t021 -> t022 -> t023 -> t024`；此行仅为后续执行入口，不代表本轮 start/实施授权。

|采纳项|唯一主承接|主验收|
|---|---|---|
|A2|t021|AC-001|
|A4|t021|AC-002|
|A5|t021|AC-003|
|A6|t021|AC-004|
|A7|t021|AC-005|
|A12|t021|AC-006|
|A31|t021|AC-007|
|A40|t021|AC-008|
|A41|t021|AC-009|
|A42|t021|AC-010|
|A46|t021|AC-011|
|A54|t021|AC-012|
|A3|t022|AC-001|
|A8|t022|AC-002|
|A9|t022|AC-003|
|A10|t022|AC-004|
|A11|t022|AC-005|
|A13|t022|AC-006|
|A14|t022|AC-007|
|A15|t022|AC-008|
|A16|t022|AC-009|
|A34|t022|AC-010|
|A39|t022|AC-011|
|A44|t022|AC-012|
|A45|t022|AC-013|
|A47|t022|AC-014|
|A48|t022|AC-015|
|A55|t022|AC-016|
|A17|t023|AC-001|
|A18|t023|AC-002|
|A19|t023|AC-003|
|A20|t023|AC-004|
|A21|t023|AC-005|
|A22|t023|AC-006|
|A49|t023|AC-007|
|A1|t024|AC-001|
|A23|t024|AC-002|
|A24|t024|AC-003|
|A25|t024|AC-004|
|A26|t024|AC-005|
|A27|t024|AC-006|
|A28|t024|AC-007|
|A29|t024|AC-008|
|A30|t024|AC-009|
|A32|t024|AC-010|
|A33|t024|AC-011|
|A35|t024|AC-012|
|A38|t024|AC-013|
|A43|t024|AC-014|
|A50|t024|AC-015|
|A51|t024|AC-016|
|A52|t024|AC-017|
|A53|t024|AC-018|

立项只转交采纳项，不登记 R10/R11 的被拒绝范围。前序功能 task 自带回归，不把测试债务留给 t024；t024 负责跨层 fixture、门禁、镜像及证据整合。现有 pending 不在创建期自动归档。

## 待决定项

无。原 D1 已按用户选择 B 转 A55；原 D2 已按用户选择 A 转 A54。

## 采纳项

### A1. 补齐 Supervisor 镜像构建白名单

- 来源：bundle_cross_validation, bundle_local_contracts_deploy
- 位置：config/docker/supervisor_runtime/Dockerfile.dockerignore
- 优先级：HIGH
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-001
- 覆盖：f_contracts_deploy_01
- 详细判断理由：当前 Dockerfile 仍 COPY launch_args.py，Dockerfile.dockerignore 仍以 \*\* 排除且未放行该文件。新增正式 Compose 没有消除此确定性构建缺陷；交叉核对 agree。只修构建输入，不据此声称镜像已完成运行验收。
- 修复说明：在 config/docker/supervisor_runtime/Dockerfile.dockerignore 放行 src/backend/cbrowser/launch_args.py；增加 COPY 来源与上下文匹配检查，并在隔离构建中验证 Supervisor 镜像。

### A2. 更新 DTO 仅保留严格 launch_args 校验并补负例

- 来源：bundle_global_architecture, bundle_local_backend_api_auth
- 位置：src/backend/cbrowser/domain/models.py:307-352；tests/integration/test_v2_api_subprocess.py:188（仅创建路径）；更新路径无对应用例；src/backend/cbrowser/domain/models.py:307-352；src/backend/cbrowser/launch_args.py
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-001
- 覆盖：f_backend_api_auth_01, f_backend_api_auth_09, f_global_architecture_07
- 详细判断理由：ProfileUpdateRequest 同时存在 validate 与 filter，注释却把后者限定为旧数据读取。当前严格校验先执行，报告“顺序不确定”过强；真正问题是重复策略及 explicit null 可能进入不接受 None 的 filter。p017 已登记，应复用该承接而非重复立项。
- 修复说明：删除更新 DTO 的 normalize_launch_arguments，保留严格 validate；历史读取仍在 ProfileConfig 过滤。按现行 PATCH 契约明确未提供与 explicit null 语义，补 PUT/PATCH 越界参数 422、合法值、null 的真实 HTTP 回归。

### A3. CDP 重连后仅在 rearm ACK 成功时报告健康

- 来源：bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/runtime_agent/cdp_proxy.py:190-253
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-001
- 覆盖：f_backend_runtime_adapters_03
- 详细判断理由：重连路径确实发出命令后立即置 \_last_rearm_ok=True，响应 ID 未进入待处理映射；初次 arm 则等待 ACK。健康声明与实际证据不一致，p017 已承接。
- 修复说明：在 cdp_proxy.py 记录重连 rearm 命令 ID，发送时保持不健康，唯一 reader 收到匹配 result 后才置 True；error、断线和超时保持 False。禁止在唯一 reader 内同步等待自己消费 ACK；补成功/error/无 ACK 测试。

### A4. Profile 查询只加载调用方需要的数据

- 来源：bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/adapters/database/models.py:75-100；src/backend/cbrowser/adapters/database/artifact_repository.py:34-36；src/backend/cbrowser/adapters/database/artifact_repository.py:63-84
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-002
- 覆盖：f_backend_runtime_adapters_01, f_backend_runtime_adapters_08, f_backend_runtime_adapters_09
- 详细判断理由：ProfileModel 的 versions/artifacts 默认 selectin，普通 Profile 查询只消费 tags 却加载整段历史；ArtifactService 只需存在性却取得脱离 session 的 ORM 对象。属于数据库读职责不清；查询成本应随返回数据而非累积历史增长。不可变历史不能为性能被任意删除。
- 修复说明：models.py/repository.py 对普通查询显式只加载 tags/必要 runtime，版本与产物由专用方法查询；ArtifactRepository 增加标量存在性查询替代返回 ORM；下载去重把 storage_path 放入 SQL WHERE。验证返回 DTO 不变及查询不读取历史集合。

### A5. 卸载 async 登录路径中的 Argon2 同步运算

- 来源：bundle_local_backend_api_auth
- 位置：src/backend/cbrowser/auth/service.py:100-141
- 优先级：LOW
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-003
- 覆盖：f_backend_api_auth_04
- 详细判断理由：authenticate_admin 在事件循环中直接调用 PasswordHasher.verify，真实与哑元分支均会阻塞 SSE/协调器。限速先行降低暴露，但不消除合法登录阻塞。
- 修复说明：auth/service.py 将真实和哑元 verify 放入 asyncio.to_thread，保留同等失败行为、限速顺序与脱敏；hash 调用按所在 async 路径同样处理。使用阻塞探针验证事件循环仍可推进；密码长度上限不在本项擅自变更。

### A6. 区分配置缺失与数据库忙，并覆盖内部面拒绝

- 来源：bundle_followup_q_architecture_02, bundle_followup_q_system_properties_01, bundle_local_backend_api_auth
- 位置：src/backend/cbrowser/api/app.py:296-348；src/backend/cbrowser/api/internal_supervisor.py:36、internal_gateway.py:36-37、internal_artifacts.py:23
- 优先级：LOW
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-004
- 覆盖：f_backend_api_auth_06, f_backend_api_auth_11
- 详细判断理由：HTTPException 503 被统一标为 database_busy/retryable，服务令牌未配置也是此状态；DatabaseLockError 已有独立处理器。配置缺失不能误导客户端重试数据库事务。路由依赖传播已被精查证伪，不再按“内部面无鉴权”处理。
- 修复说明：在 app.py 与内部依赖抛出点使用明确 service_not_configured 错误码和 retryable=false，保留数据库锁忙专用响应；对 Supervisor/Gateway/Artifact 未配置、无/错令牌及三条状态写端点补负向 HTTP 断言。同步生成 OpenAPI 与前端类型。

### A7. 补 CSRF Referer 回退路径行为测试

- 来源：bundle_local_backend_api_auth
- 位置：src/backend/cbrowser/auth/dependencies.py:65-67（require_csrf_and_origin 的 Referer 回退分支）
- 优先级：LOW
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-005
- 覆盖：f_backend_api_auth_10
- 详细判断理由：现有测试覆盖 Origin 和双缺头部，没有经过 Referer-only 分支。安全回退分支有独立输入面，补真实依赖链测试收益明确。
- 修复说明：tests/integration/test_auth_api.py 补允许来源 Referer-only 放行、外站 Referer 拒绝、畸形 Referer 拒绝；保留正确 CSRF token，避免测试在更早鉴权层失败。

### A8. 统一事件投递结果并终结永久拒绝事件

- 来源：bundle_global_architecture, bundle_global_system_properties, bundle_local_backend_supervisor
- 位置：src/backend/cbrowser/supervisor/core.py:640-682；src/backend/cbrowser/supervisor/event_forwarder.py:175-196；src/backend/cbrowser/supervisor/event_forwarder.py:175-196；src/backend/cbrowser/supervisor/core.py:640-682；src/backend/cbrowser/supervisor/event_forwarder.py:190；src/backend/cbrowser/supervisor/artifact_forwarder.py:22；local_backend_supervisor.json（f_backend_supervisor_01/02）；local_backend_api_auth.json（f_backend_api_auth_06）；src/backend/cbrowser/api/internal_supervisor.py（require_supervisor 的 503）
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-002
- 覆盖：f_backend_supervisor_01, f_backend_supervisor_02, f_global_architecture_04, f_global_system_properties_03
- 详细判断理由：emit_event 的 bool 抹掉 REJECTED/UNAVAILABLE 差异，磁盘消费因此对永久拒绝反复重投；两 forwarder 对 401/403/408/429 分类不同也属实。收窄报告影响：文件事件只作诊断，运行状态与失败核算由 Supervisor 观测控制，不能宣称必然破坏 lifecycle 收敛。
- 修复说明：EventForwarder 暴露明确三态结果并保留既有调用契约的单一路径；401/403/408/429 与 5xx 留待重试，确定语义拒绝入死信。consume_disk_events 对永久拒绝隔离原文件、推进并持久化游标；暂不可用保持待投递。测试单次死信、重启重放、暂失败后成功；不允许诊断事件推进业务状态。API 503 分类由 A6 处理。

### A9. 收紧 X11 权限辅助容器权限

- 来源：bundle_local_backend_supervisor
- 位置：src/backend/cbrowser/supervisor/docker_adapter.py:494-510
- 优先级：LOW
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-003
- 覆盖：f_backend_supervisor_04
- 详细判断理由：setup_x11_permissions 当前 root helper 未带其他 helper 已有的 cap_drop/no-new-privileges/read_only。其用途仅目录权限修正，应约束权限并标明所有权，避免扩散默认权限模板。
- 修复说明：docker_adapter.py 的 helper 设置 cap_drop ALL、仅实测 chmod 必需 capabilities、read_only 与 no-new-privileges，加受管理标签；验证权限修正成功、失败明确报错与 helper 清理，不照抄多余 CHOWN 权限。

### A10. 异常 Docker 标签只隔离当前资源

- 来源：bundle_local_backend_supervisor
- 位置：src/backend/cbrowser/supervisor/docker_adapter.py:1040-1052
- 优先级：LOW
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-004
- 覆盖：f_backend_supervisor_06
- 详细判断理由：scan_active_containers 返回 config_version=None，恢复分类 int(None) 可中断整轮。对未知标签猜默认版本会削弱实例围栏，应显式标记并跳过有风险动作。
- 修复说明：扫描边界校验缺失/非数值 config-version，记录脱敏诊断并逐资源拒绝使用；恢复循环继续处理其他 Profile。补缺失、畸形、有效标签混合扫描测试，确保未知身份不被采用或批量删除。

### A11. 生命周期冲突返回明确 HTTP 409

- 来源：bundle_local_backend_supervisor
- 位置：src/backend/cbrowser/supervisor/control_server.py:118-160
- 优先级：LOW
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-005
- 覆盖：f_backend_supervisor_07
- 详细判断理由：start 对缺 running 意图、重试阻断、等待清理等预期冲突均落 generic 500，stop 已区分 409；调用方无法正确理解人工重试与服务故障。
- 修复说明：core.py 使用明确生命周期冲突异常，control_server.py 映射 409；保留端口耗尽 503、意外故障 500；补 HTTP 状态与无内部数据泄漏断言，避免匹配 RuntimeError 文案。

### A12. 修剪失效下载游标并复用单例锁文件名

- 来源：bundle_local_backend_supervisor
- 位置：src/backend/cbrowser/supervisor/artifact_forwarder.py:262-281；src/backend/cbrowser/supervisor/recovery_coordinator.py:520-540
- 优先级：LOW
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-006
- 覆盖：f_backend_supervisor_08, f_backend_supervisor_10
- 详细判断理由：游标只对本轮出现事件的实例求交，消失实例历史永不退出；重复锁文件清单也会使正常启动与恢复分叉。修剪状态与规则单一来源必须闭环；缓存验证另由 A44 建立受控代次，不能靠 mtime 跳过。
- 修复说明：artifact_forwarder.py 以完整事件树实例集合识别消失项，在一次完整成功扫描后删除过期游标；读取失败不得当作空树。recovery_coordinator.py 导入 SINGLETON_LOCK_NAMES。补实例消失/扫描失败不丢游标回归。

### A13. Agent 元数据缺字段时明确拒启动

- 来源：bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/runtime_agent/agent.py:440-460
- 优先级：LOW
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-006
- 覆盖：f_backend_runtime_adapters_05
- 详细判断理由：有效 JSON 缺 browser_ws_url 时 runner_info 非空，当前守卫通过后 KeyError；错误诊断不准确。无需增加兼容旧格式或默认 URL。
- 修复说明：agent.py 在轮询结束后校验必需字段与类型，再构造 CDP manager；缺字段统一抛脱敏元数据错误。补非空缺字段、非法类型、完整记录路径。

### A14. 无法证明过期的 X11 锁不得删除

- 来源：bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/runtime_agent/runner.py:225-242
- 优先级：LOW
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-007
- 覆盖：f_backend_runtime_adapters_12
- 详细判断理由：锁文件存在但解析/读取失败时 holder=None，代码仍删除锁与 socket；未知所有权不能等同死进程。收紧失败方向符合既有 fail-closed 契约。
- 修复说明：runner.py 仅在可解析 PID 且已确认不存在时清理；存在但不可读/不可解析则拒绝并给出明确错误；补有效活进程、死 PID、损坏锁、读失败测试，验证 socket 保留。

### A15. 统一隧道数据与 envelope 上限，受控处理超限

- 来源：bundle_local_backend_stream_gateway
- 位置：src/backend/cbrowser/gateway/server.py:585-605; src/backend/cbrowser/stream_agent/protocol.py:62-67; src/backend/cbrowser/stream_agent/agent.py:41-43,607-617
- 优先级：LOW
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-008
- 覆盖：f_backend_stream_gateway_02
- 详细判断理由：data 的 UTF-8 字节限制与 Agent 原始 JSON 上限均为 1MiB，转义后 envelope 可以超过后者；Gateway 构造模型失败也未受控关闭。正常边界数据可能被静默丢弃。
- 修复说明：protocol.py 明确原始 envelope、data、WS 三层预算；Gateway 构造前检查并捕获校验错误，以 1009 关闭超限连接；Agent 使用同一预算。覆盖 JSON 转义膨胀与边界值，不把数据上限简单提高到无界。

### A16. Gateway 控制操作逐目标完成清理

- 来源：bundle_local_backend_stream_gateway
- 位置：src/backend/cbrowser/gateway/server.py:221-222,266-288；src/backend/cbrowser/gateway/registry.py:12-24; src/backend/cbrowser/gateway/server.py:455-463
- 优先级：LOW
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-009
- 覆盖：f_backend_stream_gateway_03, f_backend_stream_gateway_07
- 详细判断理由：quota 发送竞态会直接 500；disconnect 单个 close/send 错误会跳过余下 viewer。心跳 runtime_state 又未更新，注册表保存过期信息。
- 修复说明：server.py 对各 viewer close/send 独立处理并继续后续目标；Agent 不在线/发送失败返回明确 503；心跳同步 runtime_state。补第一个 viewer 失败其余仍关闭、Agent 发送失败和心跳更新测试。

### A17. 消除登录 next 回环并准确呈现会话错误

- 来源：bundle_local_frontend_features
- 位置：src/frontend/src/features/auth/redirect.ts:9-11；src/frontend/src/features/profiles/BrowserSessionPage.tsx:22-25；src/frontend/src/features/browser-session/useBrowserSession.ts:194-200
- 优先级：LOW
- 结论：采纳
- 承接：[t023](../../tasks/t023_frontend_session_consistency/task.md) / AC-001
- 覆盖：f_frontend_features_02, f_frontend_features_03, f_frontend_features_09
- 详细判断理由：登录回环清洗仅排除精确 /login，路由却接受大小写与尾斜杠；runtime 查询失败被当作停止态；语言切换可重复运行启动检查并回退 stage。均有明确用户可见错误，修复不改产品功能范围。
- 修复说明：redirect.ts 仅比较规范化 pathname，排除 /LOGIN、/login/、query/hash 变体；BrowserSessionPage 区分 loading/error/unknown/stopped 并提供重试；useBrowserSession 不因 t 函数身份变化重置已连接状态。补对应行为回归。

### A18. SSE 连接代次隔离，区分取消与超时

- 来源：bundle_local_frontend_shell
- 位置：src/frontend/src/shared/api/sse.ts:74-77；src/frontend/src/shared/api/client.ts:118-145
- 优先级：LOW
- 结论：采纳
- 承接：[t023](../../tasks/t023_frontend_session_consistency/task.md) / AC-002
- 覆盖：f_frontend_shell_01, f_frontend_shell_02
- 详细判断理由：共享 isClosed 在 stop/start 之间被复用，旧请求 catch/finally 可重新安排重连；外部 abort 也被误报 retryable timeout。p018 已承接，按原条目处理，取消路径当前尚无生产调用者但公共 API 契约应准确。
- 修复说明：sse.ts 每次 start/stop 推进 generation，旧 await/catch/finally 不得投递事件或重连；重复 start 不增加连接。client.ts 区分外部取消与内部超时并释放监听，取消不可重试。用可控 fetch/stream 验证立即 stop/start、登出后零重连和取消行为。

### A19. 每次逻辑 mutation 独立分配幂等键

- 来源：bundle_global_architecture, bundle_global_system_properties, bundle_local_frontend_features
- 位置：src/frontend/src/features/profiles/useProfilesQuery.ts:60-77, src/frontend/src/features/artifacts/useArtifacts.ts:35-53；src/frontend（profiles 数据层 hook）；src/backend/cbrowser/adapters/database/repository.py（audit-row sig_hash 幂等）；src/frontend/src/features/profiles/useProfilesQuery.ts:60-77；src/frontend/src/features/artifacts/useArtifacts.ts:35-53；src/backend/cbrowser/adapters/database/repository.py:52-56,88-100；src/backend/cbrowser/api/app.py:229-236；local_frontend_features.json（f_frontend_features_01）
- 优先级：LOW
- 结论：采纳
- 承接：[t023](../../tasks/t023_frontend_session_consistency/task.md) / AC-003
- 覆盖：f_frontend_features_01, f_global_architecture_08, f_global_system_properties_06
- 详细判断理由：hook 级 ref 确实让并发异参调用共享 key；后端 sig_hash 会明确返回 409，不是静默吞掉。应保留同一逻辑动作内部重试复用 key，同时隔离不同调用。
- 修复说明：profiles/artifacts mutations 在每次 mutate/mutateAsync 调用边界建立动作 key，重试继续使用该 key，settle 不得清除另一动作 key；不要把新 key 直接放进每次 retry 调用的 mutationFn。补同实例并发异参、单动作重试及 stop/start 复合动作测试；后端冲突语义保持。

### A20. 前端文案只声明已有健康证据并显示上传部分成功

- 来源：bundle_local_frontend_features
- 位置：src/frontend/src/features/settings/SettingsPage.tsx:12-16；src/frontend/src/features/artifacts/ProfileFilesPage.tsx:44-54
- 优先级：LOW
- 结论：采纳
- 承接：[t023](../../tasks/t023_frontend_session_consistency/task.md) / AC-004
- 覆盖：f_frontend_features_10, f_frontend_features_12
- 详细判断理由：单 API health 无法表示 Gateway/整个服务链健康；多文件上传中断时已有部分成功，纯失败提示容易引发重复选择。页面只陈述可证明事实；若将来提供整体健康，应由后端拥有组件健康契约，前端不得拼猜。
- 修复说明：SettingsPage/i18n 将状态名称收窄为控制 API；ProfileFilesPage 失败文案带成功数、失败文件和未处理数。补健康文案与部分成功页面测试，不输出私密文件内容。

### A21. 生成类型覆盖 SSE，编译约束双语键集

- 来源：bundle_local_frontend_shell
- 位置：src/frontend/src/i18n.tsx:328；src/frontend/src/shared/api/sse.ts:1-10
- 优先级：LOW
- 结论：采纳
- 承接：[t023](../../tasks/t023_frontend_session_consistency/task.md) / AC-005
- 覆盖：f_frontend_shell_06, f_frontend_shell_11
- 详细判断理由：en/zh 当前对齐但 Record\<string,string> 无法阻止漏键；SSE 手写类型已与生成类型可选性不同。复用现有类型系统即可消除两个漂移面。
- 修复说明：i18n 从 en 精确键集派生 TranslationKey，zh 用 satisfies Record\<TranslationKey,string>；types.ts 导出生成 ProfileRuntimeStatusEvent，sse.ts 在验证真实事件语义后引用该类型，不用 Partial 掩盖不一致。运行 tsc 与 SSE/i18n 测试。

### A22. 前端测试验证真实接线并恢复 mock 隔离

- 来源：bundle_local_frontend_features, bundle_local_frontend_shell
- 位置：src/frontend/src/features/profiles/BrowserSessionPage.test.tsx:8-32, src/frontend/src/features/profiles/ProfileDetailPage.test.tsx:16-25；src/frontend/src/features/browser-session/media_controls.test.tsx:32-44；src/frontend/tsconfig.json:23；src/frontend/src/shared/api/client.test.ts:71-82；src/frontend/src/app/auth_guard.test.tsx:67-107
- 优先级：LOW
- 结论：采纳
- 承接：[t023](../../tasks/t023_frontend_session_consistency/task.md) / AC-006
- 覆盖：f_frontend_features_05, f_frontend_features_11, f_frontend_shell_05, f_frontend_shell_07, f_frontend_shell_08
- 详细判断理由：页面层只测局部案例，单例方法普通赋值又不会被 restoreAllMocks 还原；credentials/retry 测试名超出断言，postMessage origin 断言过宽。测试类型被整体排除是事实。修复范围限定这些具体接线与隔离缺口。
- 修复说明：页面在 ApiClient 边界注入每例独立 stub，补 running/启动/保存/删除/复制/重置/apply 关键流程；spyOn 或注入替代单例普通赋值。断言 credentials=include、真实 retry、具体 target origin；增加测试 tsconfig noEmit 类型门禁，清除因此暴露的签名错误，不重写旧预期迎合实现。

### A23. 同步当前文档与 ADR，刷新交接事实

- 来源：bundle_global_evolution, bundle_global_system_properties, bundle_local_backend_runtime_adapters, bundle_local_backend_supervisor, bundle_local_docs_current
- 位置：docs/handoff.md:5,9,26,29,31；docs/findings/d003_selkies_ice_restart_gap.md:11; docs/findings/d019_turn_loopback_mapping.md:9; docs/findings/d021_selkies_ice_restart_commit_is_async.md:7; docs/findings/d022_selkies_rtc_config_url_contract.md:7（另 d009、d010、d012、d018 同类）；docs/blueprint/artifacts.md:14；docs/tasks/t009_v2_full_acceptance/task.md:29,71；docs/v2_architecture_plan.md:§3 固定常驻服务清单; §7.5 内部协议边界表; §10.4–10.6; §16 安全与网络矩阵; §19.4；docs/blueprint/architecture.md:19,31；docs/specs/webrtc_remote_display.md:26；docs/blueprint/domain.md:12,27；docs/findings/；docs/blueprint/；docs/specs/；docs/v2_architecture_plan.md；docs/handoff.md；docs/tasks/t009_v2_full_acceptance/；docs/specs_index.md（在表即生效规则）；local_docs_current.json（f_docs_current_01/02/03/05/06）；local_archive_reviews.json（f_archive_reviews_05）；local_archive_tasks.json（f_archive_tasks_01/02）；src/backend/cbrowser/adapters/database/migrations.py:24-38；src/backend/cbrowser/supervisor/port_allocator.py:1-6
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-002
- 覆盖：f_docs_current_01, f_docs_current_02, f_docs_current_03, f_docs_current_04, f_docs_current_05, f_docs_current_06, f_docs_current_07, f_docs_current_08, f_global_evolution_04, f_global_system_properties_05, f_backend_runtime_adapters_15, f_backend_supervisor_12
- 详细判断理由：ADR 013/014 与 findings、Artifact 权限、状态图、验收 AC 存在真实冲突；当前架构说明又未跟进本地 legacy 删除。修正文档事实有明确收益。全局项中要求提交 \_meta 或修改冻结报告的部分不采纳；历史证据由 A38 追加勘误承接。
- 修复说明：当前 blueprint/spec 对齐同机直连、0750/0640、chown 失败报错与 error 枚举；findings 追加 ADR 013 替代状态，保留原实验事实；plan 明示被替代范围。handoff 新节写实际 branch/head、完成/未验收边界和 p016–p019，旧节只追加归档；pending 按更新时实际目录核对，不把 p016–p019 当完整静态清单；t009 等已归档任务不改原 AC，仅在独立勘误中指向现行直连验收与替代关系。修正 migration pragma 与 PortAllocator 单事件循环说明。任务状态以当前登记位置为准，不据旧报告重开已归档任务或擅改未完成任务状态。

### A24. 在 dist 实际消费点校验构建新鲜度

- 来源：bundle_local_tests_e2e_stream_frontend, bundle_local_tests_integration_fixtures
- 位置：tests/e2e/conftest.py:32；tests/fixtures/frontend_probe/host_builder.py:19
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-003
- 覆盖：f_tests_e2e_stream_frontend_01, f_tests_integration_fixtures_04
- 详细判断理由：当前含 frontend 文件名的 suite 已被 collection gate 保护，报告“现有 lanes 都可测旧 dist”过强。真实缺口是 harness 可被不含该文件名的调用方复用，且自身 docstring 承诺未兑现。
- 修复说明：frontend_app_probe 与 host_builder 在复制 dist 前调用现有 verify_frontend_build_freshness；保留或简化 collection 入口，避免重复构建。补非 frontend 文件名消费者、缺 stamp、源码变化与有效产物用例。

### A25. 测试替身不替代被声明验证的生产链

- 来源：bundle_global_evolution, bundle_local_tests_e2e_stream_frontend, bundle_local_tests_integration_fixtures
- 位置：tests/e2e/test_stream_selkies_tokens_e2e.py:341；tests/e2e/test_stream_runtime_e2e.py:94；tests/fixtures/supervisor_resource_probe/stream_monitor.py:27；tests/fixtures/gateway_probe/selkies_assets.py:22；tests/integration/test_gateway_fixtures.py:93；tests/integration/test_supervisor_gateway_client.py:13；tests/fixtures/；tests/e2e/；tests/integration/
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-004
- 覆盖：f_tests_e2e_stream_frontend_03, f_tests_e2e_stream_frontend_04, f_tests_integration_fixtures_01, f_tests_integration_fixtures_02, f_tests_integration_fixtures_03, f_tests_integration_fixtures_08, f_global_evolution_05
- 详细判断理由：真实 Gateway 已进入多个 harness，不能泛称全部是假实现。剩余问题集中于手写配额投递、两套身份 shim、不对称 API fake 与被命名为 Agent 注入的服务端测试。叶子传输 stub 本身合理，不要求取消全部替身。
- 修复说明：资源探针经 GatewayControlClient 和真实 Gateway 下配额；Gateway lane 加载实际构建 adapter；API fake 按 Origin/cookie/Profile 显式授权、默认拒绝 automation。将 HELLO 注入/重连/标签共存核心场景接生产 Agent；仅服务端协议探针正确命名。wire stub 限于超时/坏响应，授权与 fence 用真实 create_gateway_app。

### A26. 收紧行为断言，避免失败也算成功

- 来源：bundle_local_tests_e2e_stream_frontend, bundle_local_tests_e2e_supervisor, bundle_local_tests_unit_stream_api, bundle_local_tests_unit_supervisor_runtime
- 位置：tests/e2e/test_stream_selkies_tokens_e2e.py:204；tests/e2e/test_gateway_ac001_auth_e2e.py:197；tests/e2e/test_supervisor_container_graph_e2e.py:371-380；tests/e2e/test_supervisor_ipv6_policy_e2e.py:150-154；tests/unit/test_artifact_service.py:396；tests/unit/test_gateway_config.py:73；tests/unit/test_supervisor_event_cursor.py:34；tests/unit/test_runtime_persistence_guards.py:144
- 优先级：LOW
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-005
- 覆盖：f_tests_e2e_stream_frontend_05, f_tests_e2e_stream_frontend_06, f_tests_e2e_supervisor_08, f_tests_e2e_supervisor_09, f_tests_unit_stream_api_05, f_tests_unit_stream_api_06, f_tests_unit_supervisor_runtime_04, f_tests_unit_supervisor_runtime_06
- 详细判断理由：接收 CLOSE 算正向信令、授权允许 503、凭证 mount 不存在即跳过、游标接受多个位置都弱化契约。closed-client 和依赖验证顺序的 fixture 也可造成假红。chmod 失败注入在 root 环境无效，需测试 seam 而非放宽结果。
- 修复说明：用真实 HELLO TEXT 证明信令；已就绪后未授权 Profile 精确断言契约状态，不接受 503。强制凭证 mount 存在且只读；用活 Docker client 做泄漏检查；具体 ownership 异常与精确游标位置断言；fixture 提供有效其他 secret；调用方管理 HTTP client 生命周期；存储 seam 注入失败并验证无写入。

### A27. 测试资源使用局部临时目录与系统分配端口

- 来源：bundle_local_tests_integration_fixtures, bundle_local_tests_unit_stream_api, bundle_local_tests_unit_supervisor_runtime
- 位置：tests/integration/test_normal_exit_replay.py:1；tests/integration/test_v2_api_subprocess.py:24；tests/unit/test_stream_selkies_tokens.py:253；tests/unit/test_stream_transport_hardening.py:303；tests/unit/test_automation_cdp.py:51；tests/unit/test_runtime_protocol.py:23
- 优先级：LOW
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-006
- 覆盖：f_tests_integration_fixtures_05, f_tests_integration_fixtures_12, f_tests_unit_stream_api_01, f_tests_unit_stream_api_03, f_tests_unit_stream_api_07, f_tests_unit_supervisor_runtime_05
- 详细判断理由：硬编码端口、未回收短 UDS 路径、CWD 相对读取与 collection 时创建共享目录均有明确隔离与所有权缺陷。normal_exit_replay 的路径依赖已登记 p019，不能直接换路径后放宽 desired_state 断言。
- 修复说明：路径读取锚定 __file__；WS bind 0 后读取实际端口；短 UDS 根用带 finalizer 的 fixture，所有生成位置在允许写域；API subprocess scratch 延迟至 fixture；复用现有 parsed OpenAPI。先定位 p019 的路径依赖，再迁移 normal_exit_replay 数据根并保留原行为断言。

### A28. 以可观测条件替代等待猜测，保留真实时间预算

- 来源：bundle_local_frontend_features, bundle_local_tests_e2e_stream_frontend, bundle_local_tests_e2e_supervisor, bundle_local_tests_unit_supervisor_runtime
- 位置：src/frontend/src/features/browser-session/BrowserSessionView.test.tsx:253-303；tests/e2e/test_browser_runtime_e2e.py:1032；tests/fixtures/wait.py:1-8；tests/unit/test_runtime_agent.py:306
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-007
- 覆盖：f_frontend_features_04, f_tests_e2e_stream_frontend_07, f_tests_e2e_supervisor_02, f_tests_unit_supervisor_runtime_02
- 详细判断理由：多处真实 sleep 后立即断言易依赖宿主速度；报告把所有轮询都视为缺陷则过度。只替换明确用于等待就绪/重载的固定等待，负向“持续未发生”观察窗与性能 AC 不可因此删除。
- 修复说明：会话宽限测试用注入时钟或 fake timers；健康/rearm 等用 deadline+last-observation 条件等待；Supervisor 重复等待复用现有 wait helper。并发性用事件栅栏证明，不靠 0.6s 绝对耗时；保留响应延迟、数据库 busy_timeout 的行为与时间上界。

### A29. 测试说明与实际覆盖范围一致

- 来源：bundle_local_tests_e2e_supervisor, bundle_local_tests_unit_supervisor_runtime
- 位置：tests/e2e/test_supervisor_startup_recovery_e2e.py:15-21；tests/e2e/test_supervisor_retry_e2e.py:7-14；tests/e2e/test_supervisor_policy_failure_e2e.py:59；tests/unit/test_supervisor_core.py:1
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-008
- 覆盖：f_tests_e2e_supervisor_01, f_tests_e2e_supervisor_05, f_tests_e2e_supervisor_11, f_tests_unit_supervisor_runtime_01
- 详细判断理由：重放磁盘诊断不应修改 runtime，却有 docstring 声称收敛 stopped；容器 harness 被写成独立进程且承诺未检查的 -9；supervisor_core 头部也列出文件没有的用例。修正文案不改测试语义。
- 修复说明：对应模块 docstring 写清实际行为与覆盖文件；real_api_server 注释为四元组；不改历史 task AC 勾选或把未执行验证称已通过。

### A30. 门禁依赖使用可重建的锁定环境

- 来源：bundle_global_evolution, bundle_local_contracts_deploy
- 位置：scripts/run_gates.sh:19；scripts/run_gates.sh:19；src/backend/requirements.txt 与 pyproject.toml；.env.example 与 config/.env.example
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-009
- 覆盖：f_contracts_deploy_06, f_global_evolution_08
- 详细判断理由：run_gates.sh 当前用未 pin 的 --with 列表，结果随解析时间变化。全局项混入已删 legacy 声明及两 env 内容必然同义的假设，均不照搬；只锁实际门禁环境。
- 修复说明：以 pyproject 与现有 runtime requirements 盘点生成门禁依赖锁，固定受支持 Python 与执行依赖；run_gates.sh 从该锁安装。验证空缓存可重建与各门禁加载，保留平台差异；不强行把所有服务的可兼容 patch 版本统一；不修改 repo_template 内部依赖、脚本或契约测试。

### A31. OpenAPI 正确描述服务身份与运行状态枚举

- 来源：bundle_local_contracts_deploy
- 位置：schemas/openapi/cbrowser_internal.json；schemas/openapi/cbrowser_v1.json
- 优先级：LOW
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-007
- 覆盖：f_contracts_deploy_09, f_contracts_deploy_10
- 详细判断理由：内部 OpenAPI 的后处理把真实不同令牌依赖盖为通用 serviceBearer，报告据此推导运行期令牌可互换不成立；契约表达仍需对齐实现。运行态 DTO 裸 str 与已有枚举也不一致。
- 修复说明：app.py 按 internal router 实际 require_supervisor/require_gateway 选择对应 security scheme，Artifact 归 Supervisor；ProfileRuntimeResponse 与 SSE DTO 复用现有 DesiredState/ObservedState。由源生成 schemas 与 TS 类型并同步原失效测试，补独立错误令牌矩阵，不手改生成文件。

### A32. Browser 镜像默认帮助调用正常退出

- 来源：bundle_local_contracts_deploy
- 位置：config/docker/browser_runtime/Dockerfile
- 优先级：LOW
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-010
- 覆盖：f_contracts_deploy_15
- 详细判断理由：默认 CMD 为 --help，entrypoint 未识别时退出 1，造成无参数镜像自检假失败。支持 help 不改变实际启动参数约束。
- 修复说明：entrypoint.sh 加 --help/-h 用法说明与 exit 0；非法参数仍非零。用隔离 shell/镜像命令验证默认、帮助与非法参数三态。

### A33. E2E 前提按实际套件声明，测试容器沿用最小权限

- 来源：bundle_local_tests_e2e_stream_frontend, bundle_local_tests_e2e_supervisor, bundle_local_tests_integration_fixtures
- 位置：tests/e2e/conftest.py:22-28；tests/e2e/test_supervisor_container_graph_e2e.py:83；tests/e2e/test_supervisor_namespace_policy_e2e.py:530；tests/fixtures/gateway_probe/topology.py:137；tests/fixtures/gateway_probe/evidence.py:14；tests/e2e/test_stream_selkies_tokens_e2e.py:96
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-011
- 覆盖：f_tests_e2e_supervisor_03, f_tests_e2e_supervisor_06, f_tests_e2e_supervisor_07, f_tests_integration_fixtures_10, f_tests_integration_fixtures_11, f_tests_e2e_stream_frontend_11
- 详细判断理由：Docker-only tests 不需要宿主 Mac Chrome，required 全局检查过宽。公共出口正例若离线只反映环境，不可冒充策略阻断。多处 0777、共享 tmp 证据路径及较弱容器 capabilities 也未复制生产最小权限。单纯 session_id 并非独立授权凭据，修证据落盘不是宣称已泄漏可用会话。
- 修复说明：按实际 fixtures/markers 声明 Chrome、镜像、dist 前提；离线出口先建立同条件正向基线，缺失时明确该子场景未验证，不把整份隔离测试算 PASS。数据目录精确 UID/GID/0750 或受保护父目录，SHM 0600；证据每次私有目录并脱敏标识。Selkies 测试 runner 采用 cap_drop ALL/no-new-privileges，实测必要例外单列。

### A34. 网络策略失败保留受限诊断与关闭默认值

- 来源：bundle_local_backend_supervisor
- 位置：src/backend/cbrowser/supervisor/network_policy.py:230-259
- 优先级：LOW
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-010
- 覆盖：f_backend_supervisor_09
- 详细判断理由：IPv4/IPv6 restore 失败当前丢弃失败工具及 stderr，妨碍定位；启动 gate 已确保失败时不运行沙箱，不能为“回滚”而 flush 为开放网络。
- 修复说明：network_policy.py 错误记录失败 family/tool/exit_code 与受限脱敏 stderr；明确第二 family 失败时保持 DROP 并由现有 teardown 清理，不 flush 放行。补 IPv6 失败时 gate 未放行与错误来源准确测试。

### A35. 环境示例只保留当前部署权威入口

- 来源：bundle_local_contracts_deploy
- 位置：.env.example
- 优先级：LOW
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-012
- 覆盖：f_contracts_deploy_11
- 详细判断理由：原报告两份示例相同；当前根示例已改成 v2，config/.env.example 仍是 legacy。实际漂移已经发生，不能再增加相等检查强行同步旧身份配置。
- 修复说明：核对 config/.env.example 的全部消费者；若无消费者则移除并更新必要引用，有消费者则由根权威模板生成。只保留 v2 变量及来源说明，示例秘密保持空且由用户提供。

### A38. 历史证据追加勘误与现行承接，不重写快照

- 来源：bundle_local_archive_reviews, bundle_local_archive_spikes, bundle_local_archive_tasks, bundle_local_docs_current
- 位置：docs/reviews/review_20261102_201727/adoption_decision.md（卷首基线表、「基线与现场」段 vs「合并说明」第 1 条）；docs/reviews/review_20261102_201727/bundle_local_backend_core.md；bundle_local_backend_supervisor.md；bundle_local_backend_runtime_adapters.md；bundle_local_backend_stream_gateway.md（均为 evidence 节的 viewfix 段落）；docs/reviews/review_20261102_201727/adoption_decision.md（A13 行、「合并说明」第 3 条、文末附表 backend_core 节）；docs/reviews/review_20261102_201727/bundle_global\_\*.md（question_decisions 的 followup_sha256）；bundle_cross_validation.md（finding_sha256）；bundle_repository_summary.md（synthesis 绑定说明）；docs/reviews/review_20261102_201727/adoption_decision.md（R2 行 vs A26 行）；docs/archive/tasks/t018_v2_test_gates_hygiene/task.md:43；docs/archive/tasks/t018_v2_test_gates_hygiene/note.md:53；docs/archive/tasks/t015_v2_media_link_simplification/note.md:58；docs/archive/tasks/t015_v2_media_link_simplification/note.md:105；docs/archive/pending/p011_t007_test_minor_followups.md:9；docs/archive/pending/p001_supervisor_recovery_tick_complexity.md:5；docs/archive/tasks/t006_v2_gateway_auth_rtc/note.md:147；docs/archive/tasks/t011_v2_remove_legacy/note.md:46；docs/archive/specs/chrome_external_tabs.md:1；docs/archive/tasks/t008_v2_artifacts_automation/note.md:41；docs/spikes/s011_direct_media_validation/code/direct_media_probe.py:976；docs/spikes/s011_direct_media_validation/code/direct_media_probe.py:30；docs/reviews/review_20261102_201727/bundle_local_backend_core.md（f_backend_core_01）；bundle_followup_q_system_properties_02.md；adoption_decision.md「基线与现场」段；docs/reviews/review_20261102_201727/review_intensive.md（卷首 Coverage 行、Gaps 节、Limitations 节）；docs/reviews/review_20261102_201727/adoption_decision.md（决策表「finding」列与文末附表定位列）；docs/reviews/review_local_benchmark_20261027/review_benchmark.md:78
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-013
- 覆盖：f_archive_reviews_01, f_archive_reviews_03, f_archive_reviews_04, f_archive_reviews_05, f_archive_reviews_07, f_archive_tasks_01, f_archive_tasks_02, f_archive_tasks_03, f_archive_tasks_04, f_archive_tasks_05, f_archive_tasks_06, f_archive_tasks_07, f_archive_tasks_10, f_archive_spikes_11, f_archive_spikes_21, f_archive_reviews_02, f_archive_reviews_06, f_archive_reviews_09, f_docs_current_10
- 详细判断理由：审计记录自洽是长期设计质量，不能因属于历史或修正面大而放弃。原始快照不可改仍成立；正确架构是不可变原记录加可导航的勘误/替代关系。不同阶段的证据等级不是相互证伪，须明确时间链；缺失旧运行日志或审批不得补编。
- 修复说明：新增独立勘误文件及引用入口：复算 33/30、A13 覆盖与全量映射数量；用报告路径+finding ID 消除跨轮裸编号歧义；标注截断来源和可取得的 Markdown 指纹；说明 Gaps 指单元覆盖、Limitations 指方法限制。逐项核实 task 最终轮次、trust_prior/NOT_RUN、遗留承接、产品交付承接与 spec 替代；已不存在旧证据如实标未知，以现行测试补证并区分时间，不改变原勾选冒充当时执行。补明 s011 合成 visibility 与外部 fixture 依赖范围，当前仍有意义的媒体/真实可见性场景在现行套件复验。只新增允许位置的产品事实勘误文件，归档原文件字节不变；不改 repo_template 流程、账本模板规则或生成器，模板残留问题已转 R10 拒绝。 冻结 benchmark 通过旁注指向 ADR 012 与现行手动输入/剪贴板验收，不改写原测试历史。

### A39. 注册防滥用与合法恢复分别建模

- 来源：bundle_followup_q_system_properties_03, bundle_local_backend_stream_gateway
- 位置：src/backend/cbrowser/gateway/server.py:313-315; src/backend/cbrowser/gateway/registry.py:104-130；tests/unit/test_gateway_registry.py; tests/unit/test_stream_agent_lifecycle.py; tests/integration/test_gateway_signaling.py; tests/e2e/test_supervisor_recovery_e2e.py
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-011
- 覆盖：f_backend_stream_gateway_01, f_followup_q_system_properties_03_01
- 详细判断理由：按来源防攻击与可信 Agent 恢复不应共用成功也消耗的长期失败额度；“目前未超过 20 个”不能证明模型正确。保留来源安全边界，同时将已认证身份与失败尝试分开核算，避免按未认证声称身份建无限桶。精查静态自愈结论保留，必须增加运行组合证据。
- 修复说明：registry.py/server.py 将来源限流拆为有界在途握手及失败尝试记录；成功只释放本次预留，不清除其他失败历史；所有结束/超时/取消路径释放资源。身份验证成功后以 API 确认的 Profile/instance 做有界注册替换与恢复控制，不能按攻击者提供的字符串扩展桶。agent 保留有界退避并加入可测试 jitter，避免同步重试波；真实 Gateway+多个真实 Agent 小桶测试覆盖 429、窗口过期、取消和最终全部恢复，另测网关重启。新容量值依据测量，无任意提高阈值。

### A40. 跨文件与数据库操作具备可恢复状态机

- 来源：bundle_local_backend_api_auth, bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/services/artifact_service.py:168-176；src/backend/cbrowser/api/internal_artifacts.py:24-53；src/backend/cbrowser/auth/service.py:322-397
- 优先级：LOW
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-008
- 覆盖：f_backend_runtime_adapters_13, f_backend_api_auth_07, f_backend_api_auth_08
- 详细判断理由：数据库与文件无法靠操作顺序获得原子提交；先删行、再删文件且失败不可追踪属于真实一致性债务。迟到下载需要验证产生该文件的实例身份，不能简单等同必须当前实例。未知令牌拒绝仅有日志而无审计聚合，也使取证不完整。
- 修复说明：Artifact 删除先在 DB 事务登记删除意图/待清理状态，严格校验受管路径，在受控工作单元删除文件后完成元数据删除；失败/进程重启可继续，重复调用幂等，拒绝对异常目录直接递归删除。下载报告下传 runtime_instance_id，验证 Profile 的可信历史实例与文件归属、校验和，不仅校验当前绑定；合法离线重放可接纳，伪造/未知实例拒绝。审计统一记录拒绝类别与来源，未知/非法 token 采用有界聚合而不保存 token/hash；配置限速不得被成功请求清掉其他失败。补边界故障注入、跨重启恢复、历史实例和审计脱敏测试；同步迁移与契约。

### A41. 导出契约使用明确消息入口与一致元数据

- 来源：bundle_local_contracts_deploy
- 位置：schemas/runtime/supervisor_protocol.json；scripts/export_openapi.py
- 优先级：LOW
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-009
- 覆盖：f_contracts_deploy_07, f_contracts_deploy_08, f_contracts_deploy_16
- 详细判断理由：anyOf 并非现有运行端点的鉴权或路由漏洞，但消费方不应把多端点目录联合当作具体消息校验器。统一导出约定、稳定消息入口与确定格式可以消除歧义，无须给 HTTP 消息强加无用途线上 type。协议版本应分别演进，不能因为统一格式而把各协议绑成一个版本。
- 修复说明：三个 export\_\*\_protocol.py 采用一致 JSON Schema 文档约定，按消息名暴露可直接引用的 $defs/$id 入口，说明每条 HTTP/WS 消息使用哪个 schema；有 action discriminator 的线上 envelope 保留其判别规则。若保留文档 revision，所有导出器使用同形字段但值按各协议独立来源维护，不冒充线上协商；OpenAPI 与协议导出统一尾换行和确定性序列化。消费者针对消息入口校验；现有全量生成一致性测试继续守卫。

### A42. 安全归一化有明确入口，删除无消费者授权面

- 来源：bundle_local_backend_api_auth, bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/api/internal_gateway.py:115-125；src/backend/cbrowser/services/profile_service.py:29
- 优先级：LOW
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-010
- 覆盖：f_backend_api_auth_03, f_backend_runtime_adapters_11
- 详细判断理由：当前路径可运行不代表分层合理：v2 service 依赖包外 diagnostics，使包边界与镜像布局耦合；Gateway automation-authorize 没有生产调用方，常量来源限流是无消费者接口留下的债务。最佳设计应删除无需求面并明确授权输入边界，不靠扩大可伪造 client_ip 结构修补。
- 修复说明：将运行事件日志能力移入 cbrowser 包，所有调用使用明确包导入并更新镜像打包/入口，删除旧导入布局，不留兼容转发层。确认 automation-authorize 的生产调用与现行 spec 范围后移除无消费者路由/DTO/导出项及仅验证该旧面的测试；保留实际 automation CDP 入口并以统一 AuthService 授权。Origin 在 Gateway 入口归一化、API 内部面明确接受 canonical Origin，补链路契约测试；read_secret_file 已 strip 的冗余调用统一，不重复实现规则。

### A43. 共享测试基础设施与可控时间承担唯一事实源

- 来源：bundle_global_system_properties, bundle_local_tests_e2e_supervisor, bundle_local_tests_integration_fixtures, bundle_local_tests_unit_stream_api, bundle_local_tests_unit_supervisor_runtime
- 位置：tests/e2e/test_supervisor_startup_recovery_e2e.py:246；tests/e2e/test_supervisor_policy_failure_e2e.py:127；tests/fixtures/e2e_env.py:41-57；tests/integration/test_normal_exit_replay.py:811；tests/integration/test_supervisor_observation_authority.py:57；tests/unit/test_auth_client_ip.py:47；tests/unit/test_auth_service.py:192；tests/unit/test_download_reconciler.py:33；tests/unit/test_profile_copy_reset.py:88；tests/unit/test_runtime_coordinator_background_tasks.py:48；tests/unit/test_supervisor_normal_exit_observation.py:316；local_template_tests.json（f_template_tests_01）；local_tests_integration_fixtures.json（f_tests_integration_fixtures_02/03/04）；local_tests_e2e_stream_frontend.json（f_tests_e2e_stream_frontend_01/03/04）；local_backend_api_auth.json（f_backend_api_auth_09/10/11/12）；local_contracts_deploy.json（f_contracts_deploy_06）；local_template_scripts_state.json（f_template_scripts_state_17/18）
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-014
- 覆盖：f_tests_e2e_supervisor_04, f_tests_e2e_supervisor_10, f_tests_e2e_supervisor_12, f_tests_integration_fixtures_06, f_tests_integration_fixtures_07, f_tests_unit_stream_api_02, f_tests_unit_stream_api_04, f_tests_unit_stream_api_09, f_tests_unit_stream_api_10, f_tests_unit_supervisor_runtime_03, f_tests_unit_supervisor_runtime_07, f_global_system_properties_04
- 详细判断理由：有行为断言不抵消多个 fake 各自定义权限/生命周期、测试直接访问非职责私有布局或污染全进程时钟的维护债务。测试应在真实边界构造条件，公共 fixture 统一契约；不是把测试注入开关加入产品流程，也不是为了复用强抽象不同故障模型。
- 修复说明：tests/fixtures 建唯一 DockerAdapter 契约替身与 API/auth/端口/进程生命周期支持，每个测试只描述自身故障；与真实适配器做行为契约对照。保留必要故障 seam，其他 session/state 通过现有服务构造与公开观测读取，原始 SQL 仅迁移/损坏场景使用并标明原因。限速/捕获策略依赖局部 clock callable，不修改 stdlib 模块对象；长授权测试按独立行为拆分。异步等待统一 deadline 与最后观测，端口 probe 明确不预留并在实际 bind 失败时有受限重建，不能吞产品失败。去除重复赋值/import，以 fixture 保存 session_maker，不穿透 repository 私有属性。同步真实 test_cmd/黑盒命令测试，保留负例强度。

### A44. SSE 快照不占用实时历史，缓存验证绑定受控代次

- 来源：bundle_global_system_properties, bundle_local_backend_api_auth, bundle_local_backend_supervisor, bundle_local_tests_unit_stream_api
- 位置：src/backend/cbrowser/api/runtime_coordinator.py:73-131；src/backend/cbrowser/supervisor/docker_adapter.py:210-214；local_backend_runtime_adapters.json（f_backend_runtime_adapters_01）；local_backend_supervisor.json（f_backend_supervisor_05/08）；local_backend_api_auth.json（f_backend_api_auth_05）；local_backend_core.json（f_backend_core_07）；tests/unit/test_api_models_and_sse.py:64
- 优先级：LOW
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-012
- 覆盖：f_backend_api_auth_05, f_backend_supervisor_05, f_global_system_properties_07, f_tests_unit_stream_api_08
- 详细判断理由：锁内快照本来用于保证无缺口，不能简单移到锁外；但私有快照挤占共享回放历史、N 次查询和每次启动重复递归校验都是真实成本耦合。应改变数据与生命周期模型，给不必要工作消除根因；不能削弱安全校验或删除用户不可变版本历史。已有 live/replay 测试保留，另补 fanout/溢出覆盖。
- 修复说明：runtime_coordinator.py 用一次一致数据库读生成私有 snapshot 事件，携带明确 live 基点，不把 N 条私有快照写入全局历史；订阅注册、基点与缓冲回放定义同一顺序，实时发布只持短锁。先用并发测试证明 snapshot/live 无缺口、无倒退、双订阅不互相挤压，再改变前端 snapshot 消费与生成契约；历史窗口不足时显式重建，不静默丢事件。引擎/GeoIP 缓存由 Supervisor 初始化、校验后作为不可变代次只读挂载，更新创建新代次并原子切换；每次启动验证受信代次和根身份，未知/改变仍完整校验，禁止仅用根 mtime 跳过后代检查。版本/产物读开销由 A4，游标淘汰由 A12 处理。

### A45. 过期 stop 是明确的命令结果，不伪装成已观测停止

- 来源：bundle_global_architecture, bundle_local_backend_supervisor
- 位置：src/backend/cbrowser/supervisor/core.py:1090-1102
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-013
- 覆盖：f_backend_supervisor_03, f_global_architecture_05
- 详细判断理由：保护替代实例的 no-op 是正确不变量，原稿因此把整条拒绝过宽；“未检查目标却 durable stopped”仍是语义债务。应明确区分请求处理结果与 observed 真相，而不是照报告按 Profile 批量 teardown。
- 修复说明：StopProfileResponse/OperationJournal 明确 stopped、already_absent、superseded_noop 等命令结果：只有实际停止或确认目标不存在才声明 stopped/absent，session 已替代时返回 superseded_noop，旧请求重放返回该命令结果且绝不触碰新实例。API coordinator/recovery 显式消费结果并继续按权威观测收敛，不把 HTTP 200 等同“目标已停止”。同步导出 schema；旧测试整体替换并记录旧 contract 被新语义取代，新增新 session 保留、幂等重放与不虚报观测用例。残留容器定向回收只有精确 Profile+instance 归属证据才可执行。

### A46. 幂等恢复与时间格式由单一实现定义

- 来源：bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/adapters/database/repository.py:190-208
- 优先级：LOW
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-011
- 覆盖：f_backend_runtime_adapters_10
- 详细判断理由：create/update 的事务内重放和 IntegrityError 恢复重复，会让冲突、实体已删除等边界独立演进；utc_now_iso 同义双定义也属于事实源重复。不存在当前事故不构成保留理由。
- 修复说明：repository.py 将审计签名匹配、结果查询和提交竞争恢复收敛为仓储内明确 helper，调用方传清 action/target/result，不用通用回调框架；统一已删除结果的幂等契约并补并发测试。models.py 使用 domain 的 utc_now_iso 唯一实现，列默认与显式写入同一格式；不保留旧 helper 别名。

### A47. SDK 私有接口集中适配，升级能力有可执行证据

- 来源：bundle_followup_q_evolution_02, bundle_local_backend_runtime_adapters, bundle_local_backend_stream_gateway, bundle_local_tests_integration_fixtures
- 位置：src/backend/cbrowser/runtime_agent/runner.py:744-752；tests/fixtures/stream_probe/clipboard_oracle.py:1；src/backend/cbrowser/stream_agent/x11_keymap.py:71-77
- 优先级：LOW
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-014
- 覆盖：f_backend_runtime_adapters_06, f_tests_integration_fixtures_13, f_backend_stream_gateway_05
- 详细判断理由：固定版本限制是现有契约，但不是永久忽略上游演进的理由。没有等价公开 owner-loss 证据时不能直接删私有探针；应集中耦合、在调用前检查 ABI，并区分不支持接口与进程死亡。keymap None 路径未运行确证，须先以固定 SDK 验证调用序列，不把零房间改成无限。
- 修复说明：将 Playwright/SDK driver 读取与 Selkies keymap/入口适配分别封装在各自职责模块，做版本与所需结构/签名检查，unsupported ABI 明确拒启动并脱敏诊断，不能静默当作 driver dead。真实固定镜像覆盖 owner-loss、正常退出、\_spare_keycodes 尚未初始化及 text_room/prebind 顺序；若 None 可达，按 SDK 原规则初始化同一备用键池后计算，不伪造容量。probes 复用受约束适配能力但使用独立外部行为 oracle；形成可重跑升级矩阵与隔离演练流程，不因本项自动升级 Selkies/CloakBrowser 版本。

### A48. Stream 策略不变量和关闭职责只有一个入口

- 来源：bundle_local_backend_stream_gateway, bundle_local_backend_supervisor
- 位置：src/backend/cbrowser/stream_agent/policy.py:263-291; src/backend/cbrowser/stream_agent/protocol.py:83-92；src/backend/cbrowser/stream_agent/agent.py:1055-1062（close 方法，文件末尾 run_standalone_service 之前）；src/backend/cbrowser/stream_agent/messaging.py:17-18; src/backend/cbrowser/stream_agent/policy_rules.py:33-34,64-68; src/backend/cbrowser/stream_agent/policy.py:608-616; src/backend/cbrowser/stream_agent/protocol.py:43-67,109-127,156-169；src/backend/cbrowser/gateway/server.py:343-349；src/backend/cbrowser/gateway/server.py:68-683；src/backend/cbrowser/supervisor/resource_policy.py:36-73
- 优先级：LOW
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-015
- 覆盖：f_backend_stream_gateway_04, f_backend_stream_gateway_06, f_backend_stream_gateway_08, f_backend_stream_gateway_09, f_backend_stream_gateway_10, f_backend_supervisor_11
- 详细判断理由：线协议校验不能代替策略对象自身不变量；两个关闭方法承诺不同却无清晰调用边界，重复 verb/时间/身份规则会漂移。闭包本身不是问题，纯判定不应被 I/O 装配隐藏。无生产消费者的 CPU 算法不应因为自身旧测试而永久保留。
- 修复说明：policy.py 与协议使用同一 FPS 规则，公开 set_supervisor_quota 严格拒绝低于 min、非有限和上界越界值；None 仅表示解除限制。StreamAgent 只保留可 await 的完整 stop，移除无消费者 close，取消/等待所有后台任务并释放 viewers/detached upstream。合并 verb 判定、身份字段类型/校验与 ISO 时间来源，删除冗余 Exception 元组；纯 fence/授权输入判定模块化，handler 保留 I/O。确认无外部契约消费者后删未用 calculate_cpu_percent 及仅验证旧函数的原测试，保留实际 quota 算法的独立行为覆盖与删除理由，不改旧预期伪装原测试仍有效。

### A49. 前端层次、组件契约与样式源一致

- 来源：bundle_local_frontend_features, bundle_local_frontend_shell
- 位置：src/frontend/src/features/browser-session/clipboard_bridge.ts:22-38；src/frontend/src/features/browser-session/types.ts:48；src/frontend/src/features/browser-session/host_entry.tsx:11-24；src/frontend/src/styles/globals.css:44-66；src/frontend/src/shared/components/BrowserSessionMount.tsx:1-9；src/frontend/src/app/AppLayout.tsx:65；src/frontend/tailwind.config.ts:21-28
- 优先级：LOW
- 结论：采纳
- 承接：[t023](../../tasks/t023_frontend_session_consistency/task.md) / AC-007
- 覆盖：f_frontend_features_06, f_frontend_features_07, f_frontend_features_08, f_frontend_shell_03, f_frontend_shell_04, f_frontend_shell_09, f_frontend_shell_10
- 详细判断理由：没有生产调用者的重复函数、未实现回调和测试宿主入口混在业务树里都是可消除债务；shared 反向依赖 feature 及重复 props 是明确分层问题。品牌色同值不必维护两份定义。修复着眼职责和唯一来源，不做无收益全仓命名变更。
- 修复说明：移除 readClipboardPermission 及其独立旧测试，保留实际 watcher 的权限行为测试；删未实现 onSessionError prop，若后续确有消费者再按需求定义。host_entry 移入测试 fixture，更新构建入口与 import，验证生产 bundle 不含测试 globals。BrowserSessionMount 移至 browser-session feature，并从真实组件导入 props；删除零消费者 CSS 组件块，不为保留其定义反向迁移全部页面。primary 为品牌色权威，删除无消费者 accent 或从同一 token 派生语义色，避免重复字面量；标签回调使用 tag，不遮蔽翻译函数。

### A50. Stream 镜像只交付运行依赖，共用依赖声明可追溯

- 来源：bundle_local_contracts_deploy
- 位置：config/docker/stream_runtime/Dockerfile；config/docker/stream_runtime/requirements.txt
- 优先级：LOW
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-015
- 覆盖：f_contracts_deploy_12, f_contracts_deploy_13
- 详细判断理由：生产镜像携带编译器和开发头文件是交付边界不清，与是否当前发生事故无关。相同协议的基础验证库独立解析则易产生无意差异；不应强迫所有服务锁文件完全一致，需让共有约束与平台专有依赖各有权威。
- 修复说明：stream_runtime/Dockerfile 使用 builder 阶段生成 native wheels/产物，runtime 只安装实际共享库、GStreamer 插件和程序，compiler/-dev 不入最终层；用真实音视频/输入/clipboard 及 ldd/导入检查证明依赖齐全。共有 Python 协议依赖从唯一 constraints/声明解析，各镜像保留按其平台与职责生成的独立完整锁；同协议 Pydantic patch 对齐为经测试版本，差异若必要须有明确契约证据。生成器与冷构建回归保证不靠手动复制锁文件。

### A51. 前端构建指纹覆盖完整且受控的输入集合

- 来源：bundle_local_tests_e2e_stream_frontend
- 位置：scripts/verify_frontend_dist.py:42
- 优先级：LOW
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-016
- 覆盖：f_tests_e2e_stream_frontend_02
- 详细判断理由：删除已入 hash 的文件会改变摘要，原报告该因果链不成立；但“可生成缺必要输入的 stamp”及新根构建文件未纳入指纹仍是闭环缺口。最佳设计应让构建和 freshness 共用输入定义，不泛读私有 .env 或仅增加更多手工漏项。
- 修复说明：构建戳生成与校验共用明确输入清单，区分必需文件/可选缺失状态，必需输入缺失拒绝生成 stamp；包含影响构建的配置及允许环境值摘要，Vite 根环境输入由声明边界控制而不散扫秘密。stamp 记录文件集合与内容摘要；新增/删除配置、源码变更及环境变更均使产物过期。补缺必需文件时无法 stamp、已存文件删除、新配置输入及有效构建测试。

### A52. 隐私规则按真实开发环境覆盖，历史豁免精确到存量

- 来源：bundle_local_archive_tasks, bundle_local_template_tests
- 位置：tests/unit/test_repo_hygiene.py:9-33；docs/archive/handoff.md:289
- 优先级：LOW
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-017
- 覆盖：f_template_tests_04, f_archive_tasks_09
- 详细判断理由：容器固定路径与开发者家目录要区分，不能简单把所有 /root 当秘密；但扫描器只看固定正则、整体跳过 archive，允许未来新增归档继续带开发者路径，属于规则实现债务。历史原文不能为此批量覆盖，需冻结现有豁免边界。
- 修复说明：test_repo_hygiene 识别 macOS/Linux/Windows 开发者路径，容器固定用户路径有明确例外；按已跟踪文本类型和完整读取校验，不以首 8192 字节任意 NUL 静默放弃整份文本。现有历史豁免绑定具体路径及已批准内容指纹，新增文件或新增泄漏不自动继承 archive 豁免；新归档写入前脱敏。存量快照不批量改写，在独立勘误/隐私索引说明已公开范围与适用限制，不把会话 ID 自动当凭据值。

### A53. 量测保留真实预算，证据缓冲与正向验证可检查

- 来源：bundle_local_tests_e2e_stream_frontend, bundle_local_tests_integration_fixtures
- 位置：tests/e2e/test_frontend_app_e2e.py:685；tests/e2e/test_frontend_session_vendor.py:13；tests/fixtures/frontend_probe/adapter_probe.py:45；tests/integration/test_v2_api_subprocess.py:793
- 优先级：LOW
- 结论：采纳
- 承接：[t024](../../tasks/t024_delivery_verification_evidence/task.md) / AC-018
- 覆盖：f_tests_e2e_stream_frontend_08, f_tests_e2e_stream_frontend_09, f_tests_e2e_stream_frontend_12, f_tests_integration_fixtures_09
- 详细判断理由：性能预算不能因测试不稳放宽；也不能仅因当前短会话未溢出就让证据静默丢失。常量冻结报警与真实 vendor 完整性是不同证据，应在同一验证入口明确关联。
- 修复说明：性能测试在已记录硬件/资源前提下同步触发并记录完整样本，继续按现行 first-frame/input/SQLite busy_timeout 上界判断，不擅自改中位数、重试掩盖超标或扩大阈值。锁等待测试用事件协调真实释放/超时，排除准备阶段耗时但不排除被测耗时。adapter_probe 保留有界日志并记录 dropped_count/序号，关键控制类别用计数/独立证据，溢出导致证据不足须明确失败而非误报产品行为。vendor 验证入口同时执行 pin 报警及实际 vendored manifest 校验，现有同等真实校验复用，不重复联网下载。

### A54. Artifact 允许任意内容，统一传输与 MIME 语义（原 D2）

- 来源：bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/adapters/filesystem/artifact_store.py:95-103；src/backend/cbrowser/api/v1/artifact_router.py；Artifact 上传与下载入库调用方
- 优先级：LOW
- 结论：采纳
- 承接：[t021](../../tasks/t021_control_api_artifact_contracts/task.md) / AC-012
- 覆盖：f_backend_runtime_adapters_07
- 详细判断理由：用户已在原 D2 的“用户决策”字段填写 A，采用允许任意内容的文件交换政策，不再重复询问。MIME 仅作元数据，声明类型无法证明文件是否安全；上传拒绝、浏览器下载重标的双轨语义应统一。迟到实例、删除补偿与审计仍由 A40 处理。
- 修复说明：移除按可执行 MIME 名单拒绝上传的内容限制及下载侧对应强制重标分支；上传与浏览器下载共用 MIME 规范化规则，缺失类型使用 application/octet-stream，继续拒绝非法头值。用户下载统一 attachment 与 nosniff；保留身份、Profile/instance、路径、配额与完整性校验。同步生效 spec 与产品说明，明确不做恶意代码扫描；以真实调用路径覆盖可执行内容上传/下载一致性及附件响应头。过时的“必须拒绝可执行 MIME”测试整体删除并说明政策变更，新增验证新政策的测试，不就地改旧预期冒充原契约通过。

### A55. 默认搜索初始化失败不阻断浏览器，明确提示并支持重试（原 D1=B）

- 来源：bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/runtime_agent/runner.py:564-569；src/backend/cbrowser/runtime_agent/profile_defaults.py；Profile 初始化状态、API 与前端展示/重试入口
- 优先级：MEDIUM
- 结论：采纳
- 承接：[t022](../../tasks/t022_runtime_gateway_reliability/task.md) / AC-016
- 覆盖：f_backend_runtime_adapters_02
- 详细判断理由：用户明确选择原 D1 的 B：默认搜索设置为 best-effort，失败不影响浏览器运行，界面明确呈现失败并可手动重试。浏览器运行状态与搜索初始化结果分别表达，不能通过吞异常虚报设置成功。此决定仅放宽该非关键设置的启动阻断，不改变实际浏览器启动故障与元数据错误的失败语义。
- 修复说明：把默认搜索初始化从浏览器 readiness 的成功条件中分离；为初始化设置有界执行时间与条件等待，失败记录脱敏、可观察的独立状态，不改变浏览器可用性。状态经类型化契约呈现到 Profile 页面，提供受现有身份权限保护、绑定目标实例且可幂等调用的重试操作；重试不重启浏览器、不干扰已有标签页，只有验证 Google 成为默认后才写成功 marker。set_google_default=false 不执行；成功 marker 保持首次初始化语义，正常启动不覆盖用户后续手动选择。补超时/异常不阻断启动、界面提示、拒绝越权/过期实例重试、重试成功与失败状态、用户后续选择保留的真实调用路径回归；不新增任意搜索引擎配置功能。

## 不采纳项

### R1. legacy 缺陷与缺少 v2 部署路径已被本地更新取代

- 来源：bundle_cross_validation, bundle_followup_q_architecture_01, bundle_followup_q_evolution_01, bundle_followup_q_strategy_03, bundle_followup_q_system_properties_04, bundle_global_architecture, bundle_global_evolution, bundle_global_strategy, bundle_global_system_properties, bundle_local_backend_core, bundle_local_backend_tests, bundle_local_contracts_deploy, bundle_local_docs_current
- 位置：src/backend/main.py:1301；src/backend/main.py:1835-1843；src/backend/main.py:143-147；src/backend/main.py:1171-1183；src/backend/database.py:122；src/backend/main.py:909-937；src/backend/database.py:66-76；src/backend/models.py:13-44；src/backend/browser_manager.py:56-71；src/backend/artifacts.py:22-24；src/backend/requirements.txt:1-9；src/backend/main.py:1560-1600；src/backend/settings_store.py:22-29；src/backend/main.py:1690-1705；src/backend/main.py:1171（open-external）、src/backend/main.py:1220（shutdown）；src/backend/main.py:583（test-proxy）、:1184（update-check）、:1335（center-window）、:1622（screenshot）；src/backend/main.py:1434（vnc_proxy）；src/backend/env_file.py；src/backend/tests/test_api.py:143；src/backend/tests/test_api.py:599；src/backend/tests/test_api.py:748；src/backend/tests/test_browser_manager.py:216；src/backend/tests/test_auth.py:133；src/backend/tests/test_auth.py:17；config/docker/Dockerfile:2；.env.example:15；compose.yaml；DOCKER_DEPLOYMENT.md；compose.yaml；config/docker/（五个 Dockerfile）；docs/blueprint 与 AGENTS.md 声明的 v2 架构；src/backend/database.py（legacy 手写 DDL）；src/backend/cbrowser/adapters/database/（v2 SQLAlchemy/Alembic）；src/backend/artifacts.py 与 src/backend/cbrowser/adapters/filesystem/artifact_store.py；src/backend/main.py:143-147（AuthMiddleware）；src/backend/cbrowser/auth/（v2 身份域）；.env.example:15；docs/tasks_index.json；compose.yaml；config/docker/supervisor_runtime/Dockerfile.dockerignore；src/backend/database.py:122；src/backend/cbrowser/adapters/database/migrations.py；compose.yaml；docs/tasks_index.json（t012/t009/t010）；src/backend/main.py 提交历史；compose.yaml；config/docker/Dockerfile:2；config/docker/supervisor_runtime/Dockerfile:18 与其 Dockerfile.dockerignore；docs/reviews/review_20261103_185924/\_meta/local_contracts_deploy.json（f_contracts_deploy_01/02/04）；src/backend/main.py:112-165（AUTH_TOKEN 逻辑）；.env.example:17 与 config/.env.example:17；DOCKER_DEPLOYMENT.md:12-27；compose.yaml 端口绑定；local_backend_core.json（f_backend_core_01/03/04）、local_contracts_deploy.json（f_contracts_deploy_03/05）；CHANGELOG.md:7
- 优先级：HIGH
- 结论：不采纳
- 覆盖：f_backend_core_01, f_backend_core_02, f_backend_core_03, f_backend_core_04, f_backend_core_05, f_backend_core_06, f_backend_core_07, f_backend_core_08, f_backend_core_09, f_backend_core_10, f_backend_core_11, f_backend_core_12, f_backend_core_13, f_backend_core_14, f_backend_core_15, f_backend_core_16, f_backend_core_17, f_backend_core_18, f_backend_core_19, f_backend_tests_01, f_backend_tests_02, f_backend_tests_03, f_backend_tests_04, f_backend_tests_05, f_backend_tests_06, f_contracts_deploy_02, f_contracts_deploy_03, f_contracts_deploy_04, f_contracts_deploy_05, f_global_architecture_01, f_global_architecture_02, f_global_architecture_03, f_global_evolution_01, f_global_evolution_02, f_global_strategy_01, f_global_system_properties_01, f_global_system_properties_02, f_docs_current_09
- 详细判断理由：报告基于 b473408；000aab3/d591781 已加入正式部署工件、删除 legacy 后端及测试、替换环境模板、更新 README/部署手册/CHANGELOG，并新增迁移脚本。1a073e6 又调整 HTTPS 入口。因此不恢复旧代码修复，不新增双栈共用抽象。报告对旧漏洞的静态确证与 cross-validation agree 均保留为历史事实；PARTIAL 中“旧容器已停用、不逐项修 legacy”亦吸收。仍存在的 Supervisor 构建漏项由 A1 独立处理；部署是否已实测不由 commit 标题或任务归档状态推断。 此拒绝仅因对象/前提已失效，与修复成本无关。正式备份、恢复与切换闭环已按用户要求拒绝，见 R11。

### R2. 保留已有 schema 新鲜度门禁，不增重复权威

- 来源：bundle_global_architecture, bundle_global_evolution
- 位置：schemas/（openapi/cbrowser_v1.json、cbrowser_internal.json，runtime/ 与 stream/ 协议 schema）；scripts/export\_\*.py；scripts/run_gates.sh；scripts/run_gates.sh；scripts/export_openapi.py 等四个导出脚本；schemas/
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：f_global_architecture_06, f_global_evolution_03
- 详细判断理由：源码全量生成一致性已有 unit 门禁并经 run_gates.sh 调用，“完全没有契约新鲜度门禁”被直接反证。再加一套 exporter+git diff 不是更好架构，反而重复权威；保留现有门禁并补真实执行/覆盖证据。消息入口与生成元数据单列 A41，OpenAPI 身份/状态修正 A31，不给 HTTP RPC 增加无需求线上 type。

### R3. 已证伪线索与正确的现行信任边界

- 来源：bundle_followup_q_architecture_02, bundle_followup_q_architecture_03, bundle_followup_q_architecture_04, bundle_followup_q_strategy_02, bundle_followup_q_system_properties_01, bundle_followup_q_system_properties_02, bundle_global_architecture, bundle_global_system_properties, bundle_local_backend_api_auth, bundle_local_backend_runtime_adapters, bundle_local_contracts_deploy
- 位置：src/backend/cbrowser/auth/service.py:298-320；tests/integration/test_auth_api.py::test_internal_gateway_endpoints（viewer-authorize 用例组）；src/backend/cbrowser/secret_files.py:25；src/backend/cbrowser/gateway/server.py:80-84；src/backend/cbrowser/gateway/api_client.py:22-24；src/backend/cbrowser/secret_files.py:8-29；src/backend/cbrowser/gateway/server.py:73-80；src/backend/cbrowser/gateway/api_client.py:22-24；src/backend/cbrowser/supervisor/gateway_client.py:16；src/backend/cbrowser/supervisor/agent_credentials.py:15；src/backend/cbrowser/runtime_agent/agent.py:296-460；config/docker/supervisor_runtime/Dockerfile
- 优先级：LOW
- 结论：不采纳
- 覆盖：f_backend_api_auth_02, f_backend_api_auth_12, f_global_architecture_09, f_global_system_properties_08, f_backend_runtime_adapters_14, f_contracts_deploy_14
- 详细判断理由：Gateway 在唯一生产 viewer 链已规范化 Origin，read_secret_file 已 strip；路由依赖传播与网络连接方向已由精查证伪。重复逐层规范化不是消除债务，应定义 canonical 输入边界并以契约测试覆盖（A42）。UDS 文件权限是成文容器信任模型，Supervisor 持 Docker socket 的高权限也有真实职责，不因为缺 USER 单独改为无法完成工作。这些结论不因开发预算改变；未来信任模型变化须另评，不增无用途认证层。

### R4. 损坏运行事件继续 fail-closed

- 来源：bundle_followup_q_evolution_02, bundle_local_backend_runtime_adapters
- 位置：src/backend/cbrowser/runtime_agent/event_storage.py:130-144
- 优先级：LOW
- 结论：不采纳
- 覆盖：f_backend_runtime_adapters_04
- 详细判断理由：运行事件完整性失败不能静默跳过并继续声称状态可信。下载诊断可隔离不意味着运行状态恢复也可任意容错。保留明确错误、原始损坏证据与显式恢复步骤，已有 SDK/缓存/幂等重复问题分别转 A44/A46/A47。历史 TURN 投入已由 ADR 013 正式删除，不恢复已废弃机制；沉没投入本身无需再写生产代码。

### R5. 保留 required 模式门禁及真实预算

- 来源：bundle_local_tests_e2e_stream_frontend
- 位置：tests/e2e/test_runtime_profile_defaults_e2e.py:444
- 优先级：LOW
- 结论：不采纳
- 覆盖：f_tests_e2e_stream_frontend_10
- 详细判断理由：非 required 模式缺前提可明确 skip、required 模式拒绝缺前提，是当前已生效的分层验证契约。它不把未执行记为 PASS；required 模式缺前提仍须明确失败；不新增已被用户拒绝的备份恢复或切换验收范围。不得因为追求更多绿灯而使所有本地默认命令强制启动外部资源；也不放宽性能门槛。

### R6. 冻结历史复现记录不等于秘密泄漏

- 来源：bundle_local_archive_reviews
- 位置：docs/reviews/review_20261102_201727/adoption_decision.md「基线与现场」段
- 优先级：LOW
- 结论：不采纳
- 覆盖：f_archive_reviews_08
- 详细判断理由：安全审阅保存有授权复现路径不是凭据值泄漏，且旧运行入口已删除。本轮不重写历史利用描述，也不新增用户未要求的披露审批流程；状态、证据与编号可追溯性由 A38 解决。

### R7. 冻结归档实验不回改为生产实现

- 来源：bundle_global_strategy, bundle_local_archive_spikes
- 位置：docs/archive/spikes/s001_selkies_runtime/code/run_spike.sh:231；docs/archive/spikes/s008_turn_generation_media/code/stage2_stream_runner.py:139；docs/archive/spikes/s003_selkies_control/code/recovery_probe/roles.py:26；docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_verification.py:140；docs/archive/spikes/s007_profile_isolation/code/entry_browser.sh:47；docs/archive/spikes/s003_selkies_control/code/container_uds/container_cdp_probe.py:83；docs/archive/spikes/s003_selkies_control/code/recovery_probe/roles.py:1；docs/archive/spikes/s006_gateway_media_recovery/code/probe/gateway_core.py:198；docs/archive/spikes/s008_turn_generation_media/code/stage2_adapter.py:92；docs/archive/spikes/s005_capture_policy/code/test_e2e_real_pipeline.py:86；docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_verification.py:268；docs/archive/spikes/s001_selkies_runtime/code/test_mitshm.c:1；docs/archive/spikes/s009_native_ime_input/code/test_blank_cdp.py:1；docs/archive/spikes/s010_cloakbrowser_exit_observation/code/probe.py:500；docs/archive/spikes/s008_turn_generation_media/report_same_url.md:1；docs/archive/spikes/s007_profile_isolation/code/run_isolation_probe.py:3；docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_gateway_server.py:37；docs/archive/spikes/s003_selkies_control/code/test_cdp_real.py:1；docs/archive/spikes/s003_selkies_control/code/container_uds/browser_agent.py:1；docs/archive/spikes/s002、s005、s008；docs/spikes/s011；blueprint/decisions.md ADR 013
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：f_archive_spikes_01, f_archive_spikes_02, f_archive_spikes_03, f_archive_spikes_04, f_archive_spikes_05, f_archive_spikes_06, f_archive_spikes_07, f_archive_spikes_08, f_archive_spikes_09, f_archive_spikes_10, f_archive_spikes_12, f_archive_spikes_13, f_archive_spikes_14, f_archive_spikes_15, f_archive_spikes_16, f_archive_spikes_17, f_archive_spikes_18, f_archive_spikes_19, f_archive_spikes_20, f_global_strategy_04
- 详细判断理由：归档是不可变实验快照，修正旧代码、统一旧副本或改变原测试再沿用原 PASS 会污染证据；这不是生产技术债修复。父 README 已规定仅复制到隔离 scratch 运行。复用时按当前安全边界重新验证；证据范围及过时指针由 A38 追加勘误承接，现行生产同类问题照 A 项解决。不将更多逐文件重复警告当作更好设计。

### R8. 不按代码行数或单个覆盖缺口否定整体质量体系

- 来源：bundle_followup_q_strategy_01, bundle_followup_q_strategy_02, bundle_followup_q_strategy_04, bundle_global_strategy
- 位置：tests/unit、tests/integration、tests/e2e；src/backend/tests；tests/e2e/conftest.py required 门禁
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：f_global_strategy_02
- 详细判断理由：五服务隔离有最小权限与崩溃域依据，行数和单人包络不能直接推导过度设计；legacy 已删，旧验证配比前提失效。不按历史投入规模裁撤安全边界，也不把未发生的多租户/公网需求加入当前架构。产品文档漂移、测试事实源和缓存问题分别由 A23/A38/A43/A44 承接；模板治理已按用户要求拒绝（R10），不再以影响小或改动大拒绝。

### R9. slug 校验已有单一权威，不重复验证

- 来源：bundle_local_template_scripts_state
- 位置：.repo_template/scripts/pending.py:141-153、findings.py:51-62、spikes.py:38-48
- 优先级：LOW
- 结论：不采纳
- 覆盖：f_template_scripts_state_07
- 详细判断理由：\_id_scan.allocate/allocate_dir 已在落盘前用 SLUG_RE 校验并在锁内分配。new 未在入口重复同一正则不是漏洞；重复校验会产生双权威。本轮不新增重复校验；用户进一步明确拒绝全部 repo_template 相关整改，不安排补测、源仓转报或同步。

### R10. 用户明确拒绝 repo_template 相关整改（原 A36）

- 来源：bundle_followup_q_evolution_04, bundle_followup_q_strategy_01, bundle_global_architecture, bundle_global_evolution, bundle_global_strategy, bundle_local_template_scripts_ops, bundle_local_template_scripts_state, bundle_local_template_support, bundle_local_template_tests, bundle_local_archive_tasks
- 位置：.repo_template/scripts/repo_cleanup.py:114-124,158-172；.repo_template/scripts/repo_sync.py:1606,1682,1969-2011；.repo_template/scripts/repo_sync.py:823-838,2063-2073；.repo_template/scripts/repo_sync.py:1096-1097,1919；.repo_template/scripts/repo_sync.py:761-768,812-819；.repo_template/scripts/md_format.py:195；.repo_template/scripts/repo_sync.py:1990-2002；.repo_template/scripts/skill_registry.py:40-46；.repo_template/scripts/repo_hygiene.py:65-76；.repo_template/tests/test_repo_sync.py:119；.repo_template/scripts/repo_sync.py:1096；.repo_template/scripts/repo_sync.py:2063；.repo_template/tests/test_repo_cleanup.py:148；.repo_template/scripts/repo_sync.py:819；.repo_template/tests/test_repo_hygiene.py:50；.repo_template/scripts/repo_state.py:44-57,86-101,156-186；.repo_template/scripts/repo_task/lifecycle.py:838-854 (cmd_show)；.repo_template/scripts/repo_task/view_server.py:61-67,285-303；.repo_template/scripts/repo_task/view_static/chain_plan.js:36-94 与 .repo_template/scripts/repo_task/plan.py:1-7；.repo_template/scripts/repo_task/integration.py:157-158 (cmd_start)；.repo_template/scripts/repo_task/attempts.py:74-75 (project_attempts)；.repo_template/scripts/repo_state.py:93-101,120-121,166-172；.repo_template/scripts/repo_task/lifecycle.py:614-615,806-822；.repo_template/scripts/repo_task/documents.py:55-75 (parse_front_matter_text)；.repo_template/scripts/pending.py:262-272 (cmd_park) 对比 237-259 (cmd_archive)；.repo_template/scripts/track_worktree.py:16-19,139-152,186-196；.repo_template/scripts/repo_task/cli.py:246-253 与 documents.py:97-124；.repo_template/scripts/repo_task/ledger.py:44-56 (\_read_unlocked)；.repo_template/tests/test_repo_state.py:22-30；.repo_template/scripts/repo_task/view_static/board.js:1-1135；.repo_template/tests/test_view_server.py:55；.repo_template/scripts/repo_task/ledger.py:29-66；.repo_template/scripts/repo_task/attempts.py:34-96；.repo_template/scripts/repo_task/view_server.py（serve/\_Handler）；.repo_template/tests/test_view_server.py；.repo_template/tests/pytest.ini:3；.repo_template/skills/bug-to-pending/SKILL.md:20；.repo_template/docs/usage.md:51；.repo_template/hooks/pre-commit:18；.repo_template/hooks/pre-commit:31；.repo_template/docs/spike_report_template.md:27；.repo_template/tests/review_support.py:13-35；.repo_template/tests/test_task_start_flow.py:1234-1265；.repo_template/tests/test_contract_suite.py:99-105；.repo_template/tests/test_check_review_status.py:351；.repo_template/scripts/repo_sync.py（sync_opencode_commands、sync_dir/sync_skill、\_ensure_symlink）；.repo_template/scripts/repo_task/（lifecycle start 与 ledger/attempts）；.repo_template/scripts/repo_task/ledger.py:13-58；.repo_template/scripts/repo_task/attempts.py:36-46；.repo_template/scripts/repo_sync.py:496-509（强制迁移范围仅 task 目录）；.repo_template/scripts/\_id_scan.py:199-216,232-273；.repo_template/scripts/repo_sync.py:78-80；.repo_template/scripts/check_review_status.py:13-37；.repo_template/scripts/repo_task/view_static/board.js:renderDag 与 pointermove 处理（bindEvents）；.repo_template/scripts/repo_task/store.py:244-308 (scan_tasks_at_ref / \_discover_effective_entries)；.repo_template/tests/test_workflow_contracts.py:7-10；.repo_template/；docs/（blueprint、findings 登记、handoff.md、archive 账本）；docs/archive/tasks/；docs/archive/reviews/；docs/archive/pending/
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：f_template_scripts_ops_01, f_template_scripts_ops_02, f_template_scripts_ops_03, f_template_scripts_ops_04, f_template_scripts_ops_05, f_template_scripts_ops_06, f_template_scripts_ops_07, f_template_scripts_ops_08, f_template_scripts_ops_09, f_template_scripts_ops_13, f_template_scripts_ops_14, f_template_scripts_ops_15, f_template_scripts_ops_16, f_template_scripts_ops_17, f_template_scripts_ops_18, f_template_scripts_ops_19, f_template_scripts_state_01, f_template_scripts_state_02, f_template_scripts_state_03, f_template_scripts_state_04, f_template_scripts_state_05, f_template_scripts_state_06, f_template_scripts_state_08, f_template_scripts_state_09, f_template_scripts_state_10, f_template_scripts_state_11, f_template_scripts_state_14, f_template_scripts_state_15, f_template_scripts_state_16, f_template_scripts_state_17, f_template_scripts_state_18, f_template_scripts_state_19, f_template_scripts_state_20, f_template_support_01, f_template_support_02, f_template_support_03, f_template_support_04, f_template_support_05, f_template_tests_01, f_template_tests_02, f_template_tests_03, f_template_tests_06, f_global_evolution_06, f_global_architecture_10, f_followup_q_evolution_04_01, f_template_scripts_ops_10, f_template_scripts_ops_11, f_template_scripts_ops_12, f_template_scripts_state_12, f_template_scripts_state_13, f_template_tests_05, f_global_strategy_03, f_global_evolution_07, f_archive_tasks_08, f_archive_tasks_11
- 详细判断理由：用户明确要求 repo_template 相关问题全部拒绝行动，撤销原 A36。此为范围决定，不把报告中的技术判断改写为误报。相关工具链、同步、hook、流程规则、模板测试、账本模板残留均不整改，也不转报源仓、登记后续任务或安排同步。原 A38 中 dropped 账本模板与示例行清理一并拒绝，避免换入口带回同一范围。已有 R9 保持拒绝。

### R11. 用户不需要正式备份、恢复与切换闭环（原 A37）

- 来源：bundle_followup_q_evolution_01, bundle_followup_q_evolution_03
- 位置：scripts/migrate_legacy.py；DOCKER_DEPLOYMENT.md；docs/blueprint/persistence.md；t009/t010/t012 契约及验收证据
- 优先级：MEDIUM
- 结论：不采纳
- 覆盖：精查附加风险，不计入 300 条 finding
- 详细判断理由：用户明确放弃原 A37，不建设正式备份、恢复、迁移演练与切换闭环，不新增恢复工具、runbook 或对应任务。此决定不移除现有保护，也不授权删除数据、实际迁移、停服或生产切换。其他条目不再引用 A37 承接验收。

## finding 逐项映射

定位基于本次冻结报告；finding ID 为稳定主键，L 行号为本次落笔时辅助定位。每条只列一个主决策；全局条目包含多个子论点时，具体不同处置在该决策理由中链接 A/D 项。

|来源定位|Finding ID|原严重度|决策|原问题|
|---|---|---|---|---|
|bundle_followup_q_evolution_04.md:L9|f_followup_q_evolution_04_01|Low|R10|dispatch ledger 行格式不在成文兼容政策与 sync 强制迁移覆盖内：无 version 字段、无迁移分支，旧格式行靠投影 skip 静默容忍，与 usage.md『不保留双轨解析、直接拒绝旧字段』口径不一致|
|bundle_followup_q_system_properties_03.md:L9|f_followup_q_system_properties_03_01|Low|A39|批量重注册组合场景（>20 profile 撞 Gateway 注册节流）在三层测试中零覆盖，自愈性只有静态推演、无任何执行证据|
|bundle_global_architecture.md:L9|f_global_architecture_01|High|R1|可部署工件只交付 legacy 一代：v2 五服务架构在仓库内没有可达的部署拓扑，被部署的系统与被设计的系统不是同一个|
|bundle_global_architecture.md:L15|f_global_architecture_02|Medium|R1|两套数据权威同仓并存且互不感知：legacy profiles.db 与 v2 cbrowser.db 各自演进，配额、文件名净化、下载捕获等跨切面策略双份实现并已分叉|
|bundle_global_architecture.md:L21|f_global_architecture_03|Medium|R1|两代信任边界基调断裂：v2 全链 fail-closed 与 legacy 的 opt-in 鉴权分属两个互不相认的身份域，产品整体信任姿态由较弱一代决定|
|bundle_global_architecture.md:L27|f_global_architecture_04|Medium|A8|事件投递语义无单一权威：两个 forwarder 对 API 4xx 的失败分类口径矛盾，runtime 事件被拒后游标不推进、每秒无限重试|
|bundle_global_architecture.md:L33|f_global_architecture_05|Medium|A45|持久化操作日志可为未检查、未拆卸的实例记下 'stopped' 终局，与『observed 权威须源于实际观测』的设计原则相悖|
|bundle_global_architecture.md:L39|f_global_architecture_06|Medium|R2|契约层是单向生成物而非权威：导出 schema 无新鲜度门禁，且导出形式丢失判别力，与实现各自漂移无从察觉|
|bundle_global_architecture.md:L45|f_global_architecture_07|Low|A2|launch_args 白名单的『拒绝还是丢弃』策略权威不单一：更新 DTO 同时注册严格与宽松两个校验器，语义取决于 pydantic 校验器执行顺序|
|bundle_global_architecture.md:L51|f_global_architecture_08|Low|A19|幂等键契约的键作用域两端无主：前端按 hook 实例共享 Idempotency-Key，后端按『一 key 对应一逻辑操作』校验 sig_hash，合法异参并发会被判为幂等冲突|
|bundle_global_architecture.md:L57|f_global_architecture_09|Info|R3|线索核对闭环：read_secret_file 内部已做 strip，Gateway 控制令牌『恒不匹配』不成立，残留仅为同一函数两处调用约定不一致|
|bundle_global_architecture.md:L63|f_global_architecture_10|Info|R10|repo_task 双权威链上 start 事件为 best-effort 写入，是执行权威中唯一的非 fail-closed 环节，完整性依赖事后 import 重建|
|bundle_global_evolution.md:L9|f_global_evolution_01|High|R1|legacy→v2 切换链全部停留在 backlog 且链首前置条件未就绪，双轨并存期无收敛时点|
|bundle_global_evolution.md:L15|f_global_evolution_02|Medium|R1|唯一生产面的数据层无版本化迁移：列集相等整表重建静默丢列、无日志无备份，与 v2 Alembic 形成演进双轨|
|bundle_global_evolution.md:L21|f_global_evolution_03|Medium|R2|入库契约无新鲜度门禁：导出脚本靠人工重跑，门禁不做重导出 diff，漂移既无检测也难协商|
|bundle_global_evolution.md:L27|f_global_evolution_04|Medium|A23|架构决策向下游文档的传播全靠人工且已在 ADR 013 一役多面漏改，后续每次架构变更都要重复支付全额传播成本|
|bundle_global_evolution.md:L33|f_global_evolution_05|Medium|A25|测试资产以『重实现生产语义』的 fixture 为主要形态，同步负担随生产演进持续放大且漂移方向是假绿|
|bundle_global_evolution.md:L39|f_global_evolution_06|Medium|R10|模板分发同步机制的失败模式集中在演进中间态，且失败后留悬挂事务需人工善后|
|bundle_global_evolution.md:L45|f_global_evolution_07|Low|R10|归档只追加纪律的纠正机制未被实际执行，记录可信度随轮次单调衰减且编号空间随轮次必然碰撞|
|bundle_global_evolution.md:L51|f_global_evolution_08|Low|A30|版本基线多处不锁定或双份维护，长期复现性随上游与时间漂移|
|bundle_global_strategy.md:L9|f_global_strategy_01|High|R1|交付倒挂：唯一可部署产物是已冻结的 legacy，五服务 v2 无部署路径且发布链已解锁仍未启动|
|bundle_global_strategy.md:L15|f_global_strategy_02|Medium|R8|验证投入与已交付风险成反比：最重测试资产压在未部署的 v2 与单一宿主锁定的 E2E，交付面高危点零覆盖|
|bundle_global_strategy.md:L21|f_global_strategy_03|Medium|R10|治理与文档体系已与产品本体同体量，其人工维护流在当前规模下已被多处漂移实证跟不上|
|bundle_global_strategy.md:L27|f_global_strategy_04|Info|R7|协议层验证投入曾集中于后被 ADR 013 删除的 TURN/ICE 路线，且最深投入落在上游私有内部结构上|
|bundle_global_system_properties.md:L9|f_global_system_properties_01|High|R1|冷启动部署链对两代系统都不闭合：仓库工件无法从零部署任一代系统，现网可运行依赖仓外状态|
|bundle_global_system_properties.md:L15|f_global_system_properties_02|High|R1|系统有效安全边界由部署约定而非代码决定：唯一可部署的 legacy 面鉴权 opt-in、模板默认空令牌、部署文档又宣称局域网绑定|
|bundle_global_system_properties.md:L21|f_global_system_properties_03|Medium|A8|事件投递层没有统一的永久/暂时故障分类：同一状态码在不同组件下分别被永久隔离、无限重试与误报可重试，desired/observed 收敛在故障窗口内不成立|
|bundle_global_system_properties.md:L27|f_global_system_properties_04|Medium|A43|「测试/门禁通过」的证明力被多层组合折损：生产恒走分支被恒绕、fixture 重实现生产语义且互不一致、PASS 证据可合成、门禁环境未钉版|
|bundle_global_system_properties.md:L33|f_global_system_properties_05|Medium|A23|文档权威链组合后不自洽：生效规则指向的长期真相与决策层直接冲突且无 superseded 标记，含文件权限安全参数|
|bundle_global_system_properties.md:L39|f_global_system_properties_06|Low|A19|幂等契约两端键作用域不一致：组合行为已可静态闭环——合法并发写会被 409 响亮拒绝，而非静默吞掉或回放|
|bundle_global_system_properties.md:L45|f_global_system_properties_07|Low|A44|多子系统成本随累积历史单调增长且无一处有保留上限：长期运行实例会持续变慢，与当前负载无关|
|bundle_global_system_properties.md:L51|f_global_system_properties_08|Info|R3|正向确认：内部凭据读取链为单一实现、全链一致，局部阶段悬置的 Gateway 控制令牌 strip 疑点经源码核对不成立|
|bundle_local_archive_reviews.md:L50|f_archive_reviews_01|Medium|A38|adoption_decision.md 对交叉证伪条数自相矛盾：同文件内 33 条与 30 条两种口径|
|bundle_local_archive_reviews.md:L56|f_archive_reviews_02|Medium|A38|同一穿越漏洞的核实等级在记录集内有三档（suspected / 静态确认 / 现网实测 200），从未对齐|
|bundle_local_archive_reviews.md:L62|f_archive_reviews_03|Medium|A38|多份 local bundle 的 evidence 段被截断在词中/句中，归档记录静默丢失 viewfix 补审证据|
|bundle_local_archive_reviews.md:L68|f_archive_reviews_04|Low|A38|adoption 的决策项覆盖计数与文末附表映射不一致（A13 自称 6 条、附表实际映射 ≥8 条；「62 条子项」与附表 362 条规模不符）|
|bundle_local_archive_reviews.md:L74|f_archive_reviews_05|Low|A38|归档记录中的审计哈希链指向未入库的 \_meta 产物，仓内读者无法复算验证|
|bundle_local_archive_reviews.md:L80|f_archive_reviews_06|Low|A38|review_intensive.md 宣告「Gaps: None」与同文件的 completed_with_limitations 及长 Limitations 列表并存|
|bundle_local_archive_reviews.md:L86|f_archive_reviews_07|Low|A38|adoption 内的跨轮编号碰撞：R2 理由引用的「A26」是上一轮编号，与本文自己的 A26 指向不同事项|
|bundle_local_archive_reviews.md:L92|f_archive_reviews_08|Low|R6|adoption 在修复落地前，把对当时现网部署可直接使用的未授权穿越请求路径写进了公开仓记录|
|bundle_local_archive_reviews.md:L98|f_archive_reviews_09|Info|A38|adoption 附表以 bundle 行号作为 finding 定位锚点，生成产物行号不稳定|
|bundle_local_archive_spikes.md:L74|f_archive_spikes_01|Medium|R7|Spike entry scripts disable display/stream/audio authentication with no in-file warning|
|bundle_local_archive_spikes.md:L80|f_archive_spikes_02|Medium|R7|Spike control planes accept unauthenticated state-changing commands|
|bundle_local_archive_spikes.md:L86|f_archive_spikes_03|Low|R7|Bearer tokens compared with plain string equality; one session token passed via process argv|
|bundle_local_archive_spikes.md:L92|f_archive_spikes_04|Low|R7|Run secrets persist in the probe working tree; s006 token file gets default permissions and is never deleted|
|bundle_local_archive_spikes.md:L98|f_archive_spikes_05|Low|R7|s007 Xauthority and PulseAudio cookies are world-readable inside the shared volumes|
|bundle_local_archive_spikes.md:L104|f_archive_spikes_06|Low|R7|s003 CDP-over-UDS proxy: orphaned listener task, unlocked re-arm race, unbounded event buffer|
|bundle_local_archive_spikes.md:L110|f_archive_spikes_07|Low|R7|s003 recovery roles: unbounded request body, silent no-op success, unlocked shared event file|
|bundle_local_archive_spikes.md:L116|f_archive_spikes_08|Low|R7|s006 gateway: viewer registration race and one malformed frame tears down the agent|
|bundle_local_archive_spikes.md:L122|f_archive_spikes_09|Low|R7|s008 adapter: failed prepare_restart leaves the transport monitor-less and leaks the new gatherer; runtime invariants use assert|
|bundle_local_archive_spikes.md:L128|f_archive_spikes_10|Low|R7|UDS state queries truncate at 16 KiB while the returned action history grows unboundedly|
|bundle_local_archive_spikes.md:L134|f_archive_spikes_11|Medium|A38|s011 visibility pause/resume is validated with a synthetic visibility signal, not a real hidden tab|
|bundle_local_archive_spikes.md:L140|f_archive_spikes_12|Low|R7|s006 verification contains weak or logically-implied checks presented as independent items|
|bundle_local_archive_spikes.md:L146|f_archive_spikes_13|Low|R7|Low-level capture positive checks assert success codes, not captured content|
|bundle_local_archive_spikes.md:L152|f_archive_spikes_14|Low|R7|Observation-only scripts exit 0 with no assertions and no in-file warning|
|bundle_local_archive_spikes.md:L158|f_archive_spikes_15|Low|R7|s010 owner-loss check asserts the outcome its own criteria say must not be presupposed|
|bundle_local_archive_spikes.md:L164|f_archive_spikes_16|Low|R7|s008 keeps two same-title reports that both claim to describe the final code|
|bundle_local_archive_spikes.md:L170|f_archive_spikes_17|Low|R7|Stale revision and design descriptions inside spike code|
|bundle_local_archive_spikes.md:L176|f_archive_spikes_18|Low|R7|s006 gateway static proxy serves the Selkies UI without auth, strips CSP, and hardcodes one profile|
|bundle_local_archive_spikes.md:L182|f_archive_spikes_19|Low|R7|Substantial code duplicated across spikes, so fixes cannot propagate|
|bundle_local_archive_spikes.md:L188|f_archive_spikes_20|Low|R7|Prototype-grade resource churn: 50 ms fsync status writes, per-request HTTP sessions, unbounded packet queue|
|bundle_local_archive_spikes.md:L194|f_archive_spikes_21|Info|A38|s011 is coupled to live production code and re-implements the gateway protocol as a test mock|
|bundle_local_archive_tasks.md:L48|f_archive_tasks_01|Medium|A38|t018 的 AC-004 在从未执行其自声明必需验证的情况下打勾关闭（trust_prior）|
|bundle_local_archive_tasks.md:L54|f_archive_tasks_02|Medium|A38|t018 的 Review 处置表退化为样板文本，且 19 轮审查超出记录上限 5 轮无授权留痕、attempt 2 无记录|
|bundle_local_archive_tasks.md:L60|f_archive_tasks_03|Low|A38|t015 两条 test finding 在处置表标「已修」，但测试审查者连续三轮记录残余未消除且无后续去向|
|bundle_local_archive_tasks.md:L66|f_archive_tasks_04|Low|A38|t015 的 note 收尾与 handoff.json 仍称「Round 2 PASS」，与实际 6/5 轮、且 Round 3 曾推翻该 PASS 的过程不符|
|bundle_local_archive_tasks.md:L72|f_archive_tasks_05|Low|A38|p011 以 resolved 关闭，但其 f012 子项自认未做且在 live 文档中无任何承接|
|bundle_local_archive_tasks.md:L78|f_archive_tasks_06|Low|A38|p001 的关闭理由与 p005 逐字相同，是以 p005 为主语的批量关闭文本|
|bundle_local_archive_tasks.md:L84|f_archive_tasks_07|Low|A38|t006 的 AC-001 在其 master-token 条款为空满足时整条打勾关闭|
|bundle_local_archive_tasks.md:L90|f_archive_tasks_08|Low|R10|两个 dropped 任务的自有账本仍是未填写的模板，t014 还缺 handoff.json|
|bundle_local_archive_tasks.md:L96|f_archive_tasks_09|Low|A52|公开仓库的归档区集中留存开发者环境痕迹，且 t018 的路径隐私守卫按设计把归档区排除在外|
|bundle_local_archive_tasks.md:L102|f_archive_tasks_10|Info|A38|归档 spec chrome_external_tabs 的 5 条 AC 全部未勾且文件内无 superseded 标记|
|bundle_local_archive_tasks.md:L108|f_archive_tasks_11|Info|R10|多份归档账本保留模板示例行，污染 finding id 空间|
|bundle_local_backend_api_auth.md:L67|f_backend_api_auth_01|Low|A2|ProfileUpdateRequest 对 launch_args 同时注册严格拒绝与静默丢弃两个校验器，更新语义自相矛盾|
|bundle_local_backend_api_auth.md:L73|f_backend_api_auth_02|Low|R3|authorize_viewer 用未规范化的 Origin 原字符串与已规范化的 allowed_origins 精确比对，与 CSRF 路径的 Origin 校验口径不一致|
|bundle_local_backend_api_auth.md:L79|f_backend_api_auth_03|Low|A42|Gateway 内部 automation 授权把 client_ip 硬编码为常量，per-source 限速桶被全体客户端共享|
|bundle_local_backend_api_auth.md:L85|f_backend_api_auth_04|Low|A5|Argon2 口令校验在 async 登录路径上同步执行，阻塞事件循环|
|bundle_local_backend_api_auth.md:L91|f_backend_api_auth_05|Low|A44|SSE 订阅在广播锁内构建全量快照且快照事件挤占历史环，订阅/重连会短暂阻塞全体事件发布|
|bundle_local_backend_api_auth.md:L97|f_backend_api_auth_06|Low|A6|统一错误处理器把全部 503 标为 database_busy 且 retryable=true，永久性配置错误被误报为可重试|
|bundle_local_backend_api_auth.md:L103|f_backend_api_auth_07|Low|A40|下载 artifact 上报携带的 runtime_instance_id 从未被校验，内部入库路径不对当前实例设围栏|
|bundle_local_backend_api_auth.md:L109|f_backend_api_auth_08|Info|A40|自动化授权拒绝的审计覆盖不对称：高频猜测路径不留痕，部分拒绝路径每次写一条审计记录|
|bundle_local_backend_api_auth.md:L115|f_backend_api_auth_09|Medium|A2|更新路径（PUT/PATCH）的 launch_args 白名单校验零测试覆盖，与 f_01 的双校验器矛盾叠加后更新语义无任何回归网|
|bundle_local_backend_api_auth.md:L121|f_backend_api_auth_10|Low|A7|CSRF/Origin 依赖的 Referer 回退分支无任何测试覆盖|
|bundle_local_backend_api_auth.md:L127|f_backend_api_auth_11|Low|A6|内部 RPC 未配置令牌时的 503 fail-closed 分支无测试覆盖|
|bundle_local_backend_api_auth.md:L133|f_backend_api_auth_12|Low|R3|viewer-authorize 的 Origin 规范化变体（尾斜杠等）无测试，f_02 的比对口径不一致无回归网|
|bundle_local_backend_core.md:L63|f_backend_core_01|High|R1|剪贴板正文被写入 manager.log，与 diagnostics 的脱敏承诺直接冲突|
|bundle_local_backend_core.md:L69|f_backend_core_02|High|R1|serve_spa 兜底路由无路径包含校验，疑似可未授权穿越读取应用文件|
|bundle_local_backend_core.md:L75|f_backend_core_03|Medium|R1|legacy 应用鉴权为代码级 opt-in：AUTH_TOKEN 未设置时全部 /api/\* 无条件放行|
|bundle_local_backend_core.md:L81|f_backend_core_04|Medium|R1|/api/open-external 缺少 /api/shutdown 已有的同源 CSRF 防护，可被跨站简单请求触发打开宿主浏览器|
|bundle_local_backend_core.md:L87|f_backend_core_05|Medium|R1|init_db 整表重建静默丢弃列集之外的全部列数据，无日志无备份|
|bundle_local_backend_core.md:L93|f_backend_core_06|Medium|R1|产物配额检查与建行分离，并发上传可绕过每-profile 数量与总量上限|
|bundle_local_backend_core.md:L99|f_backend_core_07|Low|R1|同步 sqlite 与文件系统调用遍布 async handler，且 list_profiles 为 N+1 标签查询|
|bundle_local_backend_core.md:L105|f_backend_core_08|Low|R1|ProfileCreate/Update 缺数值范围与长度校验，异常值直达 Xvnc 几何与 Chromium 参数|
|bundle_local_backend_core.md:L111|f_backend_core_09|Low|R1|\_normalize_proxy 以冒号切分启发式解析，含冒号/＠的凭据与 IPv6 主机会被误解析|
|bundle_local_backend_core.md:L117|f_backend_core_10|Low|R1|\_env_int 对畸形环境变量未捕获 ValueError，模块导入期即崩溃且报错不指向配置项|
|bundle_local_backend_core.md:L123|f_backend_core_11|Low|R1|requirements.txt 与 pyproject.toml 依赖声明漂移：同一包版本约束冲突且集合互不一致|
|bundle_local_backend_core.md:L129|f_backend_core_12|Low|R1|VNC 代理以 WebSocket 帧数而非 RFB 字节流计数握手，前 3 帧假设与分片方式耦合|
|bundle_local_backend_core.md:L135|f_backend_core_13|Info|R1|settings_store 对损坏 JSON 静默回退为空设置，license key 无声失效且无日志|
|bundle_local_backend_core.md:L141|f_backend_core_14|Info|R1|跨模块私有成员耦合：main.py 直读 vnc.\_allocated 并回写 browser_mgr.\_auto_launch_task|
|bundle_local_backend_core.md:L147|f_backend_core_15|Medium|R1|serve_spa 与剪贴板日志行为在本单元自有测试落点中零覆盖（据定点 grep）|
|bundle_local_backend_core.md:L153|f_backend_core_16|Medium|R1|宿主机控制端点测试缺口：/api/open-external 零测试，/api/shutdown 只测了拒绝路径|
|bundle_local_backend_core.md:L159|f_backend_core_17|Low|R1|四个 legacy 路由在 backend_tests 中零覆盖：test-proxy、update-check、center-window、screenshot|
|bundle_local_backend_core.md:L165|f_backend_core_18|Low|R1|VNC 代理转发回路无端到端测试：纯函数层覆盖扎实，接线层空白，与 CDP 代理覆盖不对称|
|bundle_local_backend_core.md:L171|f_backend_core_19|Info|R1|env_file.py 在全部测试树中零覆盖|
|bundle_local_backend_runtime_adapters.md:L83|f_backend_runtime_adapters_01|Medium|A4|Every profile read eager-loads the full config-version history and artifact rows via selectin relationships|
|bundle_local_backend_runtime_adapters.md:L89|f_backend_runtime_adapters_02|Medium|A55|Cosmetic default-search-engine setup sits on the critical launch path and can fail an otherwise healthy browser start|
|bundle_local_backend_runtime_adapters.md:L95|f_backend_runtime_adapters_03|Medium|A3|After a CDP reconnect, download capture is reported healthy without the rearm command ever being acknowledged|
|bundle_local_backend_runtime_adapters.md:L101|f_backend_runtime_adapters_04|Low|R4|One corrupt runtime event file hard-fails all runtime-event reads, unlike download events which are quarantined|
|bundle_local_backend_runtime_adapters.md:L107|f_backend_runtime_adapters_05|Low|A13|Agent startup crashes with KeyError when runner_info.json exists but never gains browser_ws_url|
|bundle_local_backend_runtime_adapters.md:L113|f_backend_runtime_adapters_06|Low|A47|Exit classification depends on Playwright/SDK private internals; any shape change silently flips clean exits to observation-lost errors|
|bundle_local_backend_runtime_adapters.md:L119|f_backend_runtime_adapters_07|Low|A54|Executable-type blocking is declared-metadata only, and the two ingest paths enforce it inconsistently|
|bundle_local_backend_runtime_adapters.md:L125|f_backend_runtime_adapters_08|Low|A4|ArtifactRepository.get_profile leaks the SQLAlchemy ORM model across the repository boundary|
|bundle_local_backend_runtime_adapters.md:L131|f_backend_runtime_adapters_09|Low|A4|find_download_duplicate fetches all (profile, sha256) rows and filters storage_path in Python despite a composite index|
|bundle_local_backend_runtime_adapters.md:L137|f_backend_runtime_adapters_10|Low|A46|Idempotency commit-race recovery is copy-pasted between create_profile and update_profile; utc_now_iso is also defined twice|
|bundle_local_backend_runtime_adapters.md:L143|f_backend_runtime_adapters_11|Low|A42|profile_service imports a top-level 'diagnostics' module, unlike every other import in the unit|
|bundle_local_backend_runtime_adapters.md:L149|f_backend_runtime_adapters_12|Low|A14|Stale-X11 cleanup unlinks the lock and socket unconditionally when the lock file content is unparseable|
|bundle_local_backend_runtime_adapters.md:L155|f_backend_runtime_adapters_13|Low|A40|Artifact delete removes the database row before deleting the file, and a directory-valued storage_path raises after the row is gone|
|bundle_local_backend_runtime_adapters.md:L161|f_backend_runtime_adapters_14|Info|R3|Agent control and CDP endpoints have no per-request authentication; the UDS file permissions are the entire trust boundary|
|bundle_local_backend_runtime_adapters.md:L167|f_backend_runtime_adapters_15|Info|A23|Migration docstring overstates busy_timeout configuration; the pragma is set on a throwaway connection|
|bundle_local_backend_stream_gateway.md:L80|f_backend_stream_gateway_01|Medium|A39|Agent 注册节流仅按来源地址计数，同机所有 Agent 共享一个额度桶，批量重启时合法注册会被 429 拒绝|
|bundle_local_backend_stream_gateway.md:L86|f_backend_stream_gateway_02|Low|A15|隧道帧大小上限三层不一致：viewer 超 1MB 文本帧使 Gateway 转发循环抛 ValidationError 突然断连，Agent 侧原始 envelope 1MB 上限会静默丢弃转义膨胀后的合法帧|
|bundle_local_backend_stream_gateway.md:L92|f_backend_stream_gateway_03|Low|A16|Supervisor 控制端点对下游发送/关闭失败无防护，quota 与 disconnect 在 Agent/viewer 套接字异常时以未处理 500 中断且后续 viewer 不再处理|
|bundle_local_backend_stream_gateway.md:L98|f_backend_stream_gateway_04|Low|A48|LiveCapturePolicyAgent.set_supervisor_quota 只校验正数与 \<=max_fps，接受低于 8 FPS 下限的配额，与协议层 [8.0, 30.0] 约束不一致|
|bundle_local_backend_stream_gateway.md:L104|f_backend_stream_gateway_05|Low|A47|x11_keymap 的 text_room 回退路径在 \_spare_keycodes 尚未赋值时可能对 None 求和抛 TypeError|
|bundle_local_backend_stream_gateway.md:L110|f_backend_stream_gateway_06|Low|A48|StreamAgent.close() 只置 \_running 并关 Gateway WS，不停心跳与策略后台循环，作为终止手段使用时会泄漏后台任务|
|bundle_local_backend_stream_gateway.md:L116|f_backend_stream_gateway_07|Info|A16|Gateway 注册表中的 runtime_state 在注册后永不更新，心跳携带的 runtime_state 被处理代码丢弃|
|bundle_local_backend_stream_gateway.md:L122|f_backend_stream_gateway_08|Info|A48|同义逻辑多处重复实现：iso_now 双定义、身份校验器在四个协议模型中复制、客户端 verb 拦截存在两套实现|
|bundle_local_backend_stream_gateway.md:L128|f_backend_stream_gateway_09|Info|A48|Agent 注册包解码处 except (ValidationError, Exception) 冗余捕获，掩盖预期的窄异常分类|
|bundle_local_backend_stream_gateway.md:L134|f_backend_stream_gateway_10|Info|A48|Gateway 全部路由处理器为 create_gateway_app 内的闭包，无法独立导入或单测，本单元亦无任何测试文件|
|bundle_local_backend_supervisor.md:L70|f_backend_supervisor_01|Medium|A8|API-rejected disk runtime events are retried every second forever: consume_disk_events never advances the cursor when EventForwarder reports REJECTED|
|bundle_local_backend_supervisor.md:L76|f_backend_supervisor_02|Medium|A8|EventForwarder classifies every non-200 status below 500 (including 401/403/429) as permanently REJECTED and quarantines the event, unlike the artifact forwarder's retryable-4xx set|
|bundle_local_backend_supervisor.md:L82|f_backend_supervisor_03|Medium|A45|stop_profile journals a durable 'stopped' result for a requested instance it never inspected or tore down when the in-memory session tracks a different instance|
|bundle_local_backend_supervisor.md:L88|f_backend_supervisor_04|Low|A9|X11 permission helper container runs as root with default capabilities, bypassing the hardening every other helper container gets|
|bundle_local_backend_supervisor.md:L94|f_backend_supervisor_05|Low|A44|Every Browser launch recursively revalidates the entire engine cache tree, making start latency grow with cache size|
|bundle_local_backend_supervisor.md:L100|f_backend_supervisor_06|Low|A10|scan_active_containers emits config_version=None for label-less containers, and downstream int(None) conversions abort recovery classification for all profiles in the tick|
|bundle_local_backend_supervisor.md:L106|f_backend_supervisor_07|Low|A11|Control start endpoint maps lifecycle conflicts to HTTP 500 while the stop endpoint maps its conflict to 409|
|bundle_local_backend_supervisor.md:L112|f_backend_supervisor_08|Low|A12|Processed download-event IDs are only pruned for instances seen in the latest scan, so the persisted cursor set grows without bound across instance churn|
|bundle_local_backend_supervisor.md:L118|f_backend_supervisor_09|Low|A34|apply_policy discards iptables-restore diagnostics and can leave a half-installed policy (IPv4 applied, IPv6 failed) with no rollback or family identification|
|bundle_local_backend_supervisor.md:L124|f_backend_supervisor_10|Low|A12|Chromium singleton-lock filename list is maintained in three places; recovery hardcodes its own copy instead of importing SINGLETON_LOCK_NAMES|
|bundle_local_backend_supervisor.md:L130|f_backend_supervisor_11|Info|A48|calculate_cpu_percent appears to be dead code: no caller exists in the backend package; the live path uses calculate_quota_normalized_percent|
|bundle_local_backend_supervisor.md:L136|f_backend_supervisor_12|Info|A23|PortAllocator docstring claims thread-safety but the implementation is guarded only by an asyncio.Lock|
|bundle_local_backend_tests.md:L54|f_backend_tests_01|Medium|R1|Tests replace the global browser_mgr singleton's launch/stop by direct assignment and never restore them, making suite outcomes order-dependent|
|bundle_local_backend_tests.md:L60|f_backend_tests_02|Medium|R1|Cross-origin WebSocket rejection tests accept any exception, so they would still pass if the CSWSH origin guard were deleted|
|bundle_local_backend_tests.md:L66|f_backend_tests_03|Low|R1|Settings tests use a full-format license-key-shaped literal as fixture data in a public repository|
|bundle_local_backend_tests.md:L72|f_backend_tests_04|Low|R1|Launch-args tests perform the production append inside the test body instead of exercising BrowserManager.launch|
|bundle_local_backend_tests.md:L78|f_backend_tests_05|Low|R1|test_logout_clears_cookie never verifies the cookie is actually cleared|
|bundle_local_backend_tests.md:L84|f_backend_tests_06|Info|R1|Auth fixtures duplicate conftest app_client's lifespan-neutralising patches instead of reusing it|
|bundle_local_contracts_deploy.md:L67|f_contracts_deploy_01|High|A1|Supervisor image build is broken: Dockerfile COPYs launch_args.py but its dockerignore whitelist excludes it|
|bundle_local_contracts_deploy.md:L73|f_contracts_deploy_02|High|R1|Legacy production Dockerfile is self-referential: FROM cbrowser:latest is the same tag compose assigns to its own output|
|bundle_local_contracts_deploy.md:L79|f_contracts_deploy_03|Medium|R1|AUTH_TOKEN defaults to empty (authentication disabled) while its own template comment calls it 'Required'|
|bundle_local_contracts_deploy.md:L85|f_contracts_deploy_04|Medium|R1|Four v2 runtime images have no deployment path: compose.yaml never references them|
|bundle_local_contracts_deploy.md:L91|f_contracts_deploy_05|Medium|R1|DOCKER_DEPLOYMENT.md contradicts the actual deployment: bind address, exposure, prerequisites, and architecture are all stale|
|bundle_local_contracts_deploy.md:L97|f_contracts_deploy_06|Medium|A30|run_gates.sh assembles its test environment from unpinned packages, so the local gate is not reproducible|
|bundle_local_contracts_deploy.md:L103|f_contracts_deploy_07|Low|A41|Exported protocol schemas are undiscriminated anyOf unions, so validation cannot distinguish message types|
|bundle_local_contracts_deploy.md:L109|f_contracts_deploy_08|Low|A41|Protocol schema versioning is inconsistent: runtime agent schema has a version field, supervisor and stream schemas have none|
|bundle_local_contracts_deploy.md:L115|f_contracts_deploy_09|Low|A31|Internal OpenAPI defines per-service bearer schemes that nothing uses: all operations collapse to one generic serviceBearer|
|bundle_local_contracts_deploy.md:L121|f_contracts_deploy_10|Low|A31|v1 OpenAPI leaves profile runtime states as bare strings while the supervisor protocol enums the same fields|
|bundle_local_contracts_deploy.md:L127|f_contracts_deploy_11|Low|A35|Environment template is duplicated byte-for-byte at repo root and config/ with no sync mechanism|
|bundle_local_contracts_deploy.md:L133|f_contracts_deploy_12|Low|A50|Stream runtime production image ships a full build toolchain and -dev packages|
|bundle_local_contracts_deploy.md:L139|f_contracts_deploy_13|Info|A50|Cross-image dependency drift: stream runtime pins a different pydantic patch version than the other three runtimes|
|bundle_local_contracts_deploy.md:L145|f_contracts_deploy_14|Info|R3|Supervisor runtime image runs as root with no USER directive and no documented privilege rationale|
|bundle_local_contracts_deploy.md:L151|f_contracts_deploy_15|Info|A32|Browser runtime's default CMD asks for --help but its entrypoint rejects unknown arguments with exit 1|
|bundle_local_contracts_deploy.md:L157|f_contracts_deploy_16|Info|A41|export_openapi.py omits the trailing newline that the other three export scripts all write|
|bundle_local_docs_current.md:L37|f_docs_current_01|Medium|A23|handoff.md 已整体过期一轮：仍称下一步 t015、head fc38a1d、pending 为空|
|bundle_local_docs_current.md:L43|f_docs_current_02|Medium|A23|findings 登记表未随 ADR 013 修订：8 篇 TURN/ICE 类 finding 仍标『有效』且含已失效指令|
|bundle_local_docs_current.md:L49|f_docs_current_03|Medium|A23|blueprint/artifacts.md 仍写 chown 失败回退 0755/0644，与 ADR 014 及 security.md 直接冲突|
|bundle_local_docs_current.md:L55|f_docs_current_04|Low|A23|t009 AC-005 仍要求验证已删除的 coturn/凭证切换，AC 正文未按其自注改写|
|bundle_local_docs_current.md:L61|f_docs_current_05|Low|A23|v2_architecture_plan.md 未记录 ADR 013 修订：正文仍以 coturn/TURN 轮换为现行设计且无替代标注|
|bundle_local_docs_current.md:L67|f_docs_current_06|Low|A23|blueprint/architecture.md 两处表述与现状自相矛盾（t011 移除旧 UI、Selkies 凭证轮换依赖行）|
|bundle_local_docs_current.md:L73|f_docs_current_07|Low|A23|specs/webrtc_remote_display.md 仍称适配层处理 RTC 配置，与 frontend.md 的现行职责矛盾|
|bundle_local_docs_current.md:L79|f_docs_current_08|Low|A23|blueprint/domain.md 状态图用 failed，与同文件 ObservedState 枚举的 error 不一致|
|bundle_local_docs_current.md:L85|f_docs_current_09|Info|R1|CHANGELOG 未跟进 v2：最新条目止于 [0.1.9] 2026-10-16|
|bundle_local_docs_current.md:L91|f_docs_current_10|Info|A38|benchmark 冻结报告的『1000 次验收未减免』结论已被 2026-11-02 用户决定覆盖（冻结原文，仅提示）|
|bundle_local_frontend_features.md:L61|f_frontend_features_01|Low|A19|Idempotency-Key 按 hook 实例共享：同一实例的并发异参调用会复用同一把 key|
|bundle_local_frontend_features.md:L67|f_frontend_features_02|Low|A17|sanitizeNextPath 只拦截精确的 /login，/login/ 与大小写变体可造成登录页自跳转循环|
|bundle_local_frontend_features.md:L73|f_frontend_features_03|Low|A17|runtime 查询失败被当作「未运行」：会话页对 runtime 端点错误无任何呈现|
|bundle_local_frontend_features.md:L79|f_frontend_features_04|Low|A28|会话视图测试多处依赖真实定时器与多秒睡眠，慢且在负载下易抖|
|bundle_local_frontend_features.md:L85|f_frontend_features_05|Low|A22|两个页面测试整体 mock 掉 useProfilesQuery 模块，页面主要流程无测试覆盖|
|bundle_local_frontend_features.md:L91|f_frontend_features_06|Info|A49|readClipboardPermission 已无生产调用方，仅被自身测试引用|
|bundle_local_frontend_features.md:L97|f_frontend_features_07|Info|A49|BrowserSessionViewProps.onSessionError 声明后从未被消费|
|bundle_local_frontend_features.md:L103|f_frontend_features_08|Info|A49|测试宿主页入口 host_entry.tsx 位于生产 feature 源码树内且无 test-only 标识|
|bundle_local_frontend_features.md:L109|f_frontend_features_09|Low|A17|runtime 检查 effect 依赖 t（i18n 函数），语言切换会重跑检查并回退会话 stage|
|bundle_local_frontend_features.md:L115|f_frontend_features_10|Info|A20|设置页以单个 /api/v1/health 探活结果冒充「网关与服务」整体状态|
|bundle_local_frontend_features.md:L121|f_frontend_features_11|Low|A22|音频 pipelineControl 测试未钉住 postMessage 的目标 origin|
|bundle_local_frontend_features.md:L127|f_frontend_features_12|Info|A20|多文件上传中途失败时已上传文件无部分成功提示|
|bundle_local_frontend_shell.md:L68|f_frontend_shell_01|Low|A18|ProfileEventsClient 无连接代次防护，stop 后快速 start 可能留下双读循环|
|bundle_local_frontend_shell.md:L74|f_frontend_shell_02|Low|A18|调用方主动 abort 被统一误报为可重试的「Request timed out」|
|bundle_local_frontend_shell.md:L80|f_frontend_shell_03|Low|A49|globals.css 的 @layer components 组件类（.btn/.input/.label 等）全仓零使用，是死 CSS|
|bundle_local_frontend_shell.md:L86|f_frontend_shell_04|Low|A49|shared 层反向依赖 features 层，且 BrowserSessionMount 本地重声明 props 类型造成漂移面|
|bundle_local_frontend_shell.md:L92|f_frontend_shell_05|Low|A22|测试文件被 tsconfig 整体排除，构建与测试链路均不类型检查测试代码|
|bundle_local_frontend_shell.md:L98|f_frontend_shell_06|Low|A21|i18n 无 en/zh 键对齐的自动守卫，zh 字典的开放 Record 类型使缺键对 tsc 不可见|
|bundle_local_frontend_shell.md:L104|f_frontend_shell_07|Low|A22|client.test.ts 两条用例的标题声称了未被断言的行为（credentials 与 retries）|
|bundle_local_frontend_shell.md:L110|f_frontend_shell_08|Low|A22|外壳测试以直接赋值方式 monkey-patch 共享 defaultApiClient 单例且从不还原|
|bundle_local_frontend_shell.md:L116|f_frontend_shell_09|Info|A49|AppLayout 中标签回调参数命名为 t，遮蔽了 i18n 的 t() 函数|
|bundle_local_frontend_shell.md:L122|f_frontend_shell_10|Info|A49|tailwind 色板中 accent 与 primary 是同值双名，代码在两名之间分裂使用|
|bundle_local_frontend_shell.md:L128|f_frontend_shell_11|Info|A21|SSE 事件类型 ProfileRuntimeEvent 为手写重复定义，未复用生成的 ProfileRuntimeStatusEvent|
|bundle_local_template_scripts_ops.md:L62|f_template_scripts_ops_01|Medium|R10|cleanup 主 walk 的剪枝按仓库根相对路径匹配，嵌套 node_modules 与 bulk 目录树不被剪枝，与 docstring 的防误删承诺不符|
|bundle_local_template_scripts_ops.md:L68|f_template_scripts_ops_02|Medium|R10|user_prompts 编号在 status/plan 与 prompt list/revoke 之间不是同一编号空间，revoke 可能作废错误条目|
|bundle_local_template_scripts_ops.md:L74|f_template_scripts_ops_03|Medium|R10|link-skills 路径下 \_ensure_symlink 对宿主位真实目录直接 rmtree 且报告谎称『原内容入回滚栈』，该路径根本没有事务|
|bundle_local_template_scripts_ops.md:L80|f_template_scripts_ops_04|Medium|R10|sync_opencode_commands 对 registry.json 用 roles[name] 硬下标，registry 缺登记时 KeyError 穿透 apply 的回滚例外集|
|bundle_local_template_scripts_ops.md:L86|f_template_scripts_ops_05|Low|R10|sync_dir/sync_skill 复制普通文件时不处理目标侧文件软链，copy2 跟随软链写出树外|
|bundle_local_template_scripts_ops.md:L92|f_template_scripts_ops_06|Low|R10|md_format CLI 对点名传入的黑名单路径静默过滤，与 format_paths 的显式拒绝契约不一致|
|bundle_local_template_scripts_ops.md:L98|f_template_scripts_ops_07|Low|R10|prompt add 按 tag 交集静默作废既有站立指令且不汇报|
|bundle_local_template_scripts_ops.md:L104|f_template_scripts_ops_08|Low|R10|skill_registry 在 usage.md 缺注册表标记时以裸 ValueError 崩溃，无诊断信息|
|bundle_local_template_scripts_ops.md:L110|f_template_scripts_ops_09|Low|R10|archive-handoff 按任意行首『## 』切节，不识别 fenced code block 内的伪标题|
|bundle_local_template_scripts_ops.md:L116|f_template_scripts_ops_10|Low|R10|每次 allocate 在全局 ID 锁内对全部本地分支逐个 ls-tree 并扫描全部 worktree，锁持有时间随分支数线性增长|
|bundle_local_template_scripts_ops.md:L122|f_template_scripts_ops_11|Info|R10|AGENTS_INTRO_HEADING 常量与 MERGE 标题同值且从未被引用，是误导性死常量|
|bundle_local_template_scripts_ops.md:L128|f_template_scripts_ops_12|Info|R10|check_review_status.py 从 repo_task.review 导入十余个未在本文件使用的名字，掩盖真实依赖面|
|bundle_local_template_scripts_ops.md:L134|f_template_scripts_ops_13|Medium|R10|prompt 编号双空间缺陷（f_template_scripts_ops_02）无任何回归测试：显示编号路径从未被驱动|
|bundle_local_template_scripts_ops.md:L140|f_template_scripts_ops_14|Medium|R10|registry.json 角色过滤分支在测试套件中从未执行：sync_opencode_commands 的 roles[name] 硬下标（f_04）与状态侧 .get 的分岔零覆盖|
|bundle_local_template_scripts_ops.md:L146|f_template_scripts_ops_15|Low|R10|cmd_link_skills（唯一无事务入口，f_03 的实际暴露面）从未被测试调用，\_ensure_symlink 的『入回滚栈』报告真实性亦无断言|
|bundle_local_template_scripts_ops.md:L152|f_template_scripts_ops_16|Low|R10|md_format CLI 点名路径的黑名单静默过滤（f_06）无测试：main() 在套件中只被以 --check 全量模式调用过|
|bundle_local_template_scripts_ops.md:L158|f_template_scripts_ops_17|Low|R10|repo_cleanup 嵌套未点名目录树（f_01 的确切形状）无测试：防误删承诺的回归网只覆盖仓库根深度 1|
|bundle_local_template_scripts_ops.md:L164|f_template_scripts_ops_18|Low|R10|sync_dir/sync_skill 目标侧单个文件软链（f_05 的 copy2 跟随位点）无测试：软链覆盖只测了目录根与 cleanup 侧|
|bundle_local_template_scripts_ops.md:L170|f_template_scripts_ops_19|Low|R10|repo_hygiene archive-handoff 对 fenced code block 内伪标题（f_09）无测试：同仓另两个解析器都有围栏用例、独此一切节器没有|
|bundle_local_template_scripts_state.md:L62|f_template_scripts_state_01|Medium|R10|repo_state.py 混用 CWD 相对与仓库根相对的路径基准，在子目录运行时静默给出错误结果|
|bundle_local_template_scripts_state.md:L68|f_template_scripts_state_02|Low|R10|cmd_show 输出的 task_md 字段实际指向 note.md|
|bundle_local_template_scripts_state.md:L74|f_template_scripts_state_03|Low|R10|/task-doc 的会话 token 随看板首页下发给任何可达客户端，不构成访问控制|
|bundle_local_template_scripts_state.md:L80|f_template_scripts_state_04|Low|R10|chain_plan.js 仍复刻了 Python 的链停止原因算法，与『看板 JS 不复刻算法』的声明矛盾|
|bundle_local_template_scripts_state.md:L86|f_template_scripts_state_05|Low|R10|cmd_start 手工拆分 depends_on/conflicts_with，不 strip 空格也不校验 tid 格式|
|bundle_local_template_scripts_state.md:L92|f_template_scripts_state_06|Low|R10|project_attempts 对 execution_claimed 事件直接下标取 owner_id，结构不合法的账本行会以 KeyError 崩溃而非 fail-closed|
|bundle_local_template_scripts_state.md:L98|f_template_scripts_state_07|Low|R9|三个条目脚本的 new 子命令对 --slug 无本地校验，与 rename 的严格校验不一致|
|bundle_local_template_scripts_state.md:L104|f_template_scripts_state_08|Low|R10|repo_state.py 把 baseline 作为裸位置参数传给 git，未防以短横线开头的选项注入|
|bundle_local_template_scripts_state.md:L110|f_template_scripts_state_09|Low|R10|cmd_finish 与 list --rebuild 未持控制面锁，与同类变更命令不一致|
|bundle_local_template_scripts_state.md:L116|f_template_scripts_state_10|Low|R10|front matter 结束分隔符用子串查找，会把以 --- 开头的任意行误判为结束|
|bundle_local_template_scripts_state.md:L122|f_template_scripts_state_11|Low|R10|pending park 接受空 --reason，与 archive 的非空校验口径不一致|
|bundle_local_template_scripts_state.md:L128|f_template_scripts_state_12|Low|R10|board.js 在每次 pointermove/mouseenter 时整表重建 SVG，规模大时拖拽与悬停明显卡顿|
|bundle_local_template_scripts_state.md:L134|f_template_scripts_state_13|Low|R10|有效状态发现对每个未合并分支/每个 worktree 做全量扫描，git 子进程数量随 task 数线性放大|
|bundle_local_template_scripts_state.md:L140|f_template_scripts_state_14|Low|R10|track_worktree 的 tid 提取与校验弱于其 docstring 声明|
|bundle_local_template_scripts_state.md:L146|f_template_scripts_state_15|Low|R10|CLI 统一异常出口漏掉 ValueError，个别路径会裸 traceback|
|bundle_local_template_scripts_state.md:L152|f_template_scripts_state_16|Info|R10|账本损坏错误信息恒指默认账本路径，与实际读取的自定义路径不符|
|bundle_local_template_scripts_state.md:L158|f_template_scripts_state_17|Medium|R10|repo_state.py 的测试从未在子目录 CWD 下运行，恰好绕开本单元 f_01 的缺陷面|
|bundle_local_template_scripts_state.md:L164|f_template_scripts_state_18|Medium|R10|board.js 1135 行前端逻辑零行为测试，仅有路径字符串存在性断言|
|bundle_local_template_scripts_state.md:L170|f_template_scripts_state_19|Low|R10|账本内容损坏（非 JSON 行/结构非法事件）无任何测试，f_06 的 KeyError 路径正落在该空白区|
|bundle_local_template_scripts_state.md:L176|f_template_scripts_state_20|Low|R10|view_server 无任何真实 HTTP 端到端测试，首页与静态资源路由连 handler 级测试也没有|
|bundle_local_template_support.md:L61|f_template_support_01|Low|R10|bug-to-pending 声称 task-work 是其 analysis-only 模式的内部调用方，但注册表无此调用边且 task-work 正文从不引用它|
|bundle_local_template_support.md:L67|f_template_support_02|Low|R10|usage.md 称 commit 由 pre-commit hook「强制」执行 md 格式门禁，但本仓未启用 hooksPath，门禁实际未生效|
|bundle_local_template_support.md:L73|f_template_support_03|Low|R10|pre-commit 在模块顶层无条件 import md_format，模块缺失或导入失败时将阻断全部提交（含不涉及 .md 的提交）|
|bundle_local_template_support.md:L79|f_template_support_04|Low|R10|pre-commit 的 staged 文件选择用 --diff-filter=ACM，纯重命名或重命名加修改的 .md 会绕过格式门禁|
|bundle_local_template_support.md:L85|f_template_support_05|Info|R10|spike 报告模板用「如 t001」作后续 task 示例编号，与 usage.md「占位示例不得占用真实 tid」的命名规则相冲突|
|bundle_local_template_tests.md:L59|f_template_tests_01|Medium|R10|真实 git 端到端套件的 review PASS 证据由测试支持代码合成、项目验证门禁被整体关闭，生产侧『审阅产出证据+执行项目验证命令』路径从未被端到端执行|
|bundle_local_template_tests.md:L65|f_template_tests_02|Medium|R10|test_drop_keeps_archived_state_when_index_rebuild_fails 未驱动 cmd_drop 本身且最终断言为析取式，标题声称的回归实际未被覆盖|
|bundle_local_template_tests.md:L71|f_template_tests_03|Low|R10|用 __code__.co_names 字节码名字表断言 repo_sync.\_run_tests 引用了 CONSUMER_TEST_COMMAND，是白盒脆弱断言|
|bundle_local_template_tests.md:L77|f_template_tests_04|Low|A52|开发者 home 路径隐私守卫的覆盖边界多处收窄：仅匹配 /(Users\|home)/<name></name>/、二进制判定只看前 8192 字节、docs/archive/ 整体豁免|
|bundle_local_template_tests.md:L83|f_template_tests_05|Low|R10|测试模块间直接 import 另一测试模块的私有 helper 与 fixture，且 test_task_start_flow 另有一份近重复脚手架，双份维护易漂移|
|bundle_local_template_tests.md:L89|f_template_tests_06|Info|R10|check_review_status 的 CLI/main 路径用例大面积 monkeypatch current_scope_fingerprint，CLI 层从不与真实指纹联跑（真实指纹在另一模块单独覆盖）|
|bundle_local_tests_e2e_stream_frontend.md:L58|f_tests_e2e_stream_frontend_01|Medium|A24|Dist freshness gate is keyed on test filename containing 'frontend', not on actual dist consumption|
|bundle_local_tests_e2e_stream_frontend.md:L64|f_tests_e2e_stream_frontend_02|Low|A51|Source hash silently skips missing allowlisted inputs and ignores non-allowlisted build inputs at the frontend root|
|bundle_local_tests_e2e_stream_frontend.md:L70|f_tests_e2e_stream_frontend_03|Medium|A25|AC-010 'agent token injection' test re-implements the StreamAgent in the test instead of exercising production agent code|
|bundle_local_tests_e2e_stream_frontend.md:L76|f_tests_e2e_stream_frontend_04|Medium|A25|Stream runtime suite validates tab/media semantics against an in-test GatewayMockServer and a Web Locks shim, not the production gateway/adapter|
|bundle_local_tests_e2e_stream_frontend.md:L82|f_tests_e2e_stream_frontend_05|Low|A26|AC-008 'positive' WebRTC signaling check accepts any message type, including connection close|
|bundle_local_tests_e2e_stream_frontend.md:L88|f_tests_e2e_stream_frontend_06|Low|A26|Unauthorized-profile viewer WebSocket assertion accepts 503, conflating correct rejection with gateway unavailability|
|bundle_local_tests_e2e_stream_frontend.md:L94|f_tests_e2e_stream_frontend_07|Low|A28|Immediacy and rearm assertions in the browser runtime suite rest on fixed sleeps instead of polling|
|bundle_local_tests_e2e_stream_frontend.md:L100|f_tests_e2e_stream_frontend_08|Low|A53|Hard wall-clock latency budgets (input \<= 3000ms, first frame \<= 8000ms) asserted on shared CI hardware|
|bundle_local_tests_e2e_stream_frontend.md:L106|f_tests_e2e_stream_frontend_09|Low|A53|Selkies vendor test asserts only that two imported constants equal literal strings|
|bundle_local_tests_e2e_stream_frontend.md:L112|f_tests_e2e_stream_frontend_10|Low|R5|Profile-defaults suite still skips on missing prerequisites by default, unlike fail-closed siblings in the same unit|
|bundle_local_tests_e2e_stream_frontend.md:L118|f_tests_e2e_stream_frontend_11|Info|A33|Selkies test runner container omits the capability hardening sibling suites in this unit apply|
|bundle_local_tests_e2e_stream_frontend.md:L124|f_tests_e2e_stream_frontend_12|Info|A53|Adapter probe retains only the last 500 DataChannel messages, silently evicting early messages tests may assert on|
|bundle_local_tests_e2e_supervisor.md:L56|f_tests_e2e_supervisor_01|Medium|A29|Module docstring states the opposite of the asserted A1 semantics for native-exit spool replay|
|bundle_local_tests_e2e_supervisor.md:L62|f_tests_e2e_supervisor_02|Medium|A28|Shared bounded-polling helpers are unused by this unit; waits are ad-hoc loops and fixed sleeps, including before contract assertions|
|bundle_local_tests_e2e_supervisor.md:L68|f_tests_e2e_supervisor_03|Medium|A33|Required-mode gate demands the macOS Chrome app path for the whole E2E session, blocking the Docker-only supervisor suite on any non-macOS host|
|bundle_local_tests_e2e_supervisor.md:L74|f_tests_e2e_supervisor_04|Low|A43|Assertions and driving hooks coupled to private internals of SupervisorCore/RecoveryCoordinator|
|bundle_local_tests_e2e_supervisor.md:L80|f_tests_e2e_supervisor_05|Low|A29|Retry suite docstring describes a subprocess harness and a -9 returncode check that the test does not contain|
|bundle_local_tests_e2e_supervisor.md:L86|f_tests_e2e_supervisor_06|Low|A33|Topology test chmods data and metadata directories to 0777 while elsewhere asserting strict 0600/0700 hygiene|
|bundle_local_tests_e2e_supervisor.md:L92|f_tests_e2e_supervisor_07|Low|A33|Hard assertion on live public Internet egress (1.1.1.1:80) makes the policy suite fail in offline environments|
|bundle_local_tests_e2e_supervisor.md:L98|f_tests_e2e_supervisor_08|Low|A26|Stream secret-mount read-only guarantee is conditional; disappearance of the mount would pass silently|
|bundle_local_tests_e2e_supervisor.md:L104|f_tests_e2e_supervisor_09|Low|A26|Zero-leak assertion runs on the Docker client after the finally block has closed it|
|bundle_local_tests_e2e_supervisor.md:L110|f_tests_e2e_supervisor_10|Info|A43|Dummy gateway endpoints and image-digest strictness drift across files, obscuring which values are contractual|
|bundle_local_tests_e2e_supervisor.md:L116|f_tests_e2e_supervisor_11|Info|A29|Stale fixture type annotation: real_api_server annotated as a 3-tuple while conftest yields 4 values|
|bundle_local_tests_e2e_supervisor.md:L122|f_tests_e2e_supervisor_12|Info|A43|free_udp_port_span probes then releases the ports, so the returned span is not reserved (TOCTOU)|
|bundle_local_tests_integration_fixtures.md:L53|f_tests_integration_fixtures_01|Medium|A25|Resource probe re-implements the production supervisor->gateway->agent quota delivery instead of exercising it|
|bundle_local_tests_integration_fixtures.md:L59|f_tests_integration_fixtures_02|Medium|A25|Two divergent test-local Selkies client shims re-implement the production adapter's tab-identity semantics, and disagree with each other|
|bundle_local_tests_integration_fixtures.md:L65|f_tests_integration_fixtures_03|Medium|A25|Two divergent fakes of the same Gateway->API internal surface; the HTTP fake unconditionally allows automation authorization and ignores viewer origin|
|bundle_local_tests_integration_fixtures.md:L71|f_tests_integration_fixtures_04|Medium|A24|Frontend build freshness is claimed but not checked: lanes can silently test a stale dist|
|bundle_local_tests_integration_fixtures.md:L77|f_tests_integration_fixtures_05|Low|A27|Module docstring promises an offline-API recovery scenario the file does not implement; tests write into the working tree instead of tmp_path|
|bundle_local_tests_integration_fixtures.md:L83|f_tests_integration_fixtures_06|Low|A43|Integration tests assert and seed production objects' private internals|
|bundle_local_tests_integration_fixtures.md:L89|f_tests_integration_fixtures_07|Low|A43|The Supervisor Docker boundary is re-faked in at least four divergent hand-rolled forms inside the unit|
|bundle_local_tests_integration_fixtures.md:L95|f_tests_integration_fixtures_08|Low|A25|Gateway-control client wire tests run against a stub that re-implements the gateway's auth/fence semantics|
|bundle_local_tests_integration_fixtures.md:L101|f_tests_integration_fixtures_09|Low|A53|AC-004 verifies SQLite busy_timeout behavior with wall-clock windows that are load-sensitive|
|bundle_local_tests_integration_fixtures.md:L107|f_tests_integration_fixtures_10|Low|A33|Topology harness makes profile-bearing data directories world-writable (0o777)|
|bundle_local_tests_integration_fixtures.md:L113|f_tests_integration_fixtures_11|Info|A33|Evidence redaction does not cover session identifiers, and the default evidence directory is a predictable shared tmp path|
|bundle_local_tests_integration_fixtures.md:L119|f_tests_integration_fixtures_12|Info|A27|Module-level scratch directory is created at import time and the OpenAPI spec is re-read on every validation call|
|bundle_local_tests_integration_fixtures.md:L125|f_tests_integration_fixtures_13|Info|A47|Stream probes depend on private internals of the vendored selkies library|
|bundle_local_tests_unit_stream_api.md:L56|f_tests_unit_stream_api_01|Low|A27|Entrypoint-content tests read config/docker/stream_runtime/entrypoint.sh via a cwd-relative path, unlike the __file__-anchored pattern used in the same unit|
|bundle_local_tests_unit_stream_api.md:L62|f_tests_unit_stream_api_02|Low|A43|Two files monkeypatch the stdlib time module itself (time.time / time.monotonic), so every in-process clock reader sees the fake clock during those tests|
|bundle_local_tests_unit_stream_api.md:L68|f_tests_unit_stream_api_03|Low|A27|Real-WebSocket hardening test binds a hard-coded port 18491 instead of an ephemeral port|
|bundle_local_tests_unit_stream_api.md:L74|f_tests_unit_stream_api_04|Low|A43|test_viewer_and_automation_authorize packs nine distinct authorization behaviors into one sequentially stateful test|
|bundle_local_tests_unit_stream_api.md:L80|f_tests_unit_stream_api_05|Low|A26|Ownership-failure test asserts with pytest.raises(Exception), the broadest possible exception class|
|bundle_local_tests_unit_stream_api.md:L86|f_tests_unit_stream_api_06|Low|A26|Short-secret gateway config test points two token-file env vars at files that are never created, coupling the test to validation order|
|bundle_local_tests_unit_stream_api.md:L92|f_tests_unit_stream_api_07|Low|A27|\_short_root ignores the tmp_path fixture, hand-rolls a /tmp directory, and never cleans it up|
|bundle_local_tests_unit_stream_api.md:L98|f_tests_unit_stream_api_08|Info|A44|SSE broadcaster coverage stops at the initial snapshot chunk|
|bundle_local_tests_unit_stream_api.md:L104|f_tests_unit_stream_api_09|Info|A43|Dead duplicate code in tests: repeated function-local 'import asyncio' and a duplicated consecutive assignment|
|bundle_local_tests_unit_stream_api.md:L110|f_tests_unit_stream_api_10|Info|A43|Profile copy/reset tests reach into ProfileRepository's private \_session_maker to build the artifact repository|
|bundle_local_tests_unit_supervisor_runtime.md:L48|f_tests_unit_supervisor_runtime_01|Low|A29|Module docstring claims AC-004/AC-005 tests that do not exist in this file|
|bundle_local_tests_unit_supervisor_runtime.md:L54|f_tests_unit_supervisor_runtime_02|Low|A28|Residual wall-clock timing assertions can flake under load|
|bundle_local_tests_unit_supervisor_runtime.md:L60|f_tests_unit_supervisor_runtime_03|Low|A43|Fixed-interval polling loops remain in a few async tests|
|bundle_local_tests_unit_supervisor_runtime.md:L66|f_tests_unit_supervisor_runtime_04|Low|A26|Test helper returns a SupervisorCore whose API client is already closed; cursor assertion accepts two values|
|bundle_local_tests_unit_supervisor_runtime.md:L72|f_tests_unit_supervisor_runtime_05|Low|A27|Schema validity test depends on CWD via a relative path|
|bundle_local_tests_unit_supervisor_runtime.md:L78|f_tests_unit_supervisor_runtime_06|Low|A26|Storage-failure injection via chmod 0o500 is environment-dependent (root bypasses it)|
|bundle_local_tests_unit_supervisor_runtime.md:L84|f_tests_unit_supervisor_runtime_07|Low|A43|Suite-wide coupling to private internals as test seams|

## 来源文件指纹

下列 SHA-256 对象是本目录可取得的原始 Markdown 字节，不含本决策文件；不把报告内 \_meta 哈希冒充可复算的公开证据。

|文件|SHA-256|
|---|---|
|bundle_cross_validation.md|65ca3a5ac7022a6854210de42fcdedf650552c285b718393662d7ad887833591|
|bundle_followup_q_architecture_01.md|add914299589c61aa8be714cf41858c340e93a8ec05d5bbd615848612dddd0de|
|bundle_followup_q_architecture_02.md|4f9b835fe028d39c25dbe61681a3fbe360135a8830475214b8bdcdc3914d5551|
|bundle_followup_q_architecture_03.md|4db08cba38d29752370f8da679fa9a8758b2883e371d5cf63a6a541776781ae3|
|bundle_followup_q_architecture_04.md|4ebb25195f0d8367bc40d2c85e4fc903665cbb80dba2ec2a151538fe33dfd651|
|bundle_followup_q_evolution_01.md|4380beb4ae4ea45ca800d0c16e0d054c9a353ce63eec88c48f02d3ce0caca1c1|
|bundle_followup_q_evolution_02.md|7ea4f0268a8816a689f3f52315fe3b9f75c2f4668e52f5254903a35e37f550f6|
|bundle_followup_q_evolution_03.md|ce304978f5278d3c312aab842c5532407f38ce0cd543da2e3b1855a6f9e49b2e|
|bundle_followup_q_evolution_04.md|84882c349be13dda22651dbda44f3b69f91df950f98913e8e99da7b80492c1bd|
|bundle_followup_q_strategy_01.md|d64fc156c57bc276a703dd850d910d84ef454ae4e002e2f2b48bfb148f325a82|
|bundle_followup_q_strategy_02.md|f0b595d8e69eabd7682622ee6582c951bed33c975262a7dc4de2c18efa1072c8|
|bundle_followup_q_strategy_03.md|27f2e565c43ee558e760102d58fac7077e52d9c14e2db0ec4e347793aca03b9c|
|bundle_followup_q_strategy_04.md|27c91ba3a808bad94cf8cedcebd7b4b0eb16327f3e7eb6cd25f4d851e7e54701|
|bundle_followup_q_system_properties_01.md|9618e61bf8654aca1610af5e304e7dfc1a7c3c21a234e5092475a61d83b10a09|
|bundle_followup_q_system_properties_02.md|e8111fb30020ec092f93a538c2eec986ae4841e609636914cc654135ae14508e|
|bundle_followup_q_system_properties_03.md|3ec0115b727de36f61da01eb5eea24eea9ad4125fd2f29d4d0b472892796d061|
|bundle_followup_q_system_properties_04.md|d4d366e806e0e2c022a32e44eae1fd1b723df8065b4d0fbb2305b7ae2d67cd21|
|bundle_global_architecture.md|db5ce9517fbbbb0f572445b7cc889ce33c8950492bec047a0bc9281a9f29f24d|
|bundle_global_evolution.md|63a940c7e251bab3df38b1a64a6819c2b7c9ae1b6fd35cf4789f7807955cb292|
|bundle_global_strategy.md|6e441595a99b8c7eea840ac26ca1c5cd1cb0e453669d6383210acd2c58837379|
|bundle_global_system_properties.md|a6ea3b50876a868f5195cacf84a1adf5286b84507709bf8d24a7a3cb87404cab|
|bundle_local_archive_reviews.md|e28dce18459fb30fd80403399ab12f5dbb5f8b12ee433fc8ea25124a4ee578a7|
|bundle_local_archive_spikes.md|b336d568b711bd2f8d4c728150c4161429c81ce030a9349b3e6d985a50c4619f|
|bundle_local_archive_tasks.md|ac95646b539044970c7fc3fa2990a488caafb2d0ab7ca93fb0bb5e169089a89d|
|bundle_local_backend_api_auth.md|09df402c06eba029d7e218960cf79902568a17635b362b815e6394f5e9810d41|
|bundle_local_backend_core.md|e632529662c2b71f3f6a2ead17e36cdfd11d0847841951769f3c0fcbcec01f18|
|bundle_local_backend_runtime_adapters.md|67886852711f10cbe087ea07b1c0f348d1d7a6ccfcebaa78f9d01a4c9c5bb4ab|
|bundle_local_backend_stream_gateway.md|da9c05ce84a9482da268ad0e32e7a61e7a4adbdf875dd5f5c0cc70f792d1fd15|
|bundle_local_backend_supervisor.md|172d3bf0cba0189f2564021414a9fe0811713bbe195f46a12feea1c46e630756|
|bundle_local_backend_tests.md|c708bbb97988b4ccd14ee688494f9845f657db4cf89228724921cfc05737b3e1|
|bundle_local_contracts_deploy.md|33490280ad2c78d0b7a74b2668579d3c02077f0aa2052fbf5d379a8c066f1605|
|bundle_local_docs_current.md|79f68d3ccf7f5cdc2c0d3db4dc43b99504538b99e8fe0b084117b99d7cffee10|
|bundle_local_frontend_features.md|08220c4d9f1b512f3fea9775e30499d259a72fc5a127cebcbef68f1bc399a1b0|
|bundle_local_frontend_shell.md|067ec8da98762948f1e07d8e5e11519bad96ef7e5ae5f70902c2bd5108042555|
|bundle_local_template_scripts_ops.md|0fd8d06d0c58afb9dc4741186d738e5a0f5c98c2932ca502ba5d9b934316b2c9|
|bundle_local_template_scripts_state.md|6d3102099692b2ee1bce772192161184d6fa7ac5f380c69e24776f5a05acc034|
|bundle_local_template_support.md|0e0682ad700e17b15796ea3b11155c66190b1dc6e9f1e1c570f9ec3e3707428b|
|bundle_local_template_tests.md|38107f028072f8c6fd1640ca5595119016de02ac9a66690953ed0b9475ef9d6c|
|bundle_local_tests_e2e_stream_frontend.md|ee19f62cd610ed7a366af59d1c6667c20f596e19940af113ce77a95743e2986c|
|bundle_local_tests_e2e_supervisor.md|1bc6979be148060a375e83d084e9bf39297ff326efba257fe523a35fad281701|
|bundle_local_tests_integration_fixtures.md|bd649703e335fd36000900d55a049eccfa98f36fde71739c101ed5614415b994|
|bundle_local_tests_unit_stream_api.md|ae36f1c7748853af3d90f899a8e81c64f0a8b2dbefda9c36d73e2e2cbc137391|
|bundle_local_tests_unit_supervisor_runtime.md|eb45d51770897373d05542df648946655043a08f0e5005df20dfaa7c802f7831|
|bundle_repository_summary.md|7240f9024afbbba3a83189cc119e1792a278c5787164d64caa2d0090944184fe|
|review_intensive.md|44ec385a0e7fbe38ea45382242d3e41115a3d53d6d81033264c07f355bbce79a|

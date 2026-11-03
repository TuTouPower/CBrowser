# Task spec

## 背景

产品镜像/依赖、构建 freshness、测试替身与时间/资源管理形成多处验证事实源，且长期文档仍混用旧基线。本组以统一且可重建的产品交付验证体系形成可追溯证据，不重开已取消的正式切换项目。

## 契约区

### 范围

- 产品 Dockerfile/entrypoint/requirements、门禁锁定依赖、前端构建 stamp 与实际消费点。
- 产品 tests/fixtures、unit/integration/E2E 的真实链路、确定性等待、权限/前提与性能/证据完整性。
- 生效 blueprint/spec/handoff 与独立产品历史勘误；CBrowser 自有 tests/unit/test_repo_hygiene.py 的隐私边界（即使 finding 来源名含 template，也不修改模板工具链）。

### 非范围

- 不整改、转报或同步 repo_template，不修改其脚本、hook、契约测试、模板规则或账本示例；不创建已拒绝 A36/R10 的后续任务。
- 不建设已拒绝 A37/R11 的正式备份、恢复、迁移演练、生产切换闭环；不执行生产停服、数据删除或外部发布。
- 不重开 t009/t010/t012，不恢复 legacy，不扩大单机/同机 Chrome 的部署包络，不恢复 TURN。
- 现有 t019 的 ICE 建链延迟、t020 的字体配置各自保持范围；本 task 不重复实现或把其验收顺带标为完成。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [x] AC-001（A1）：Supervisor 当前 Dockerfile 声明的 COPY 源均进入受控构建上下文，launch_args 可在隔离构建镜像中导入并运行，不能只通过静态文件存在性检查。
- [x] AC-002（A23）：生效 blueprint/spec、ADR 替代说明与新 handoff 对同机直连、文件权限、error 状态及 legacy 删除描述一致；handoff 含实际 branch/head 与未验证边界，已归档任务不被重开或改写为当时已通过。
- [x] AC-003（A24）：所有实际消费 dist 的探针在复制/托管前拒绝缺 stamp 或过期构建，即使测试文件名不含 frontend；有效产物通过，避免无变更反复构建。
- [x] AC-004（A25）：声明验证资源控制、HELLO、重连、标签共存或授权/fence 的用例实际触达对应生产 Gateway/Agent/构建 adapter；替身仅模拟声明的边界故障且不能默认绕过授权；证据明确区分服务端协议与完整客户端链路。
- [x] AC-005（A26）：关键行为发生退化时对应测试必然失败：包括真实 HELLO TEXT、精确鉴权状态、必需只读凭证 mount、活 Docker client 泄漏检查、具体 ownership 异常、精确游标与存储失败无写入；不再以允许成功或失败的析取断言宣称通过。
- [x] AC-006（A27）：测试可从其他工作目录运行，端口由实际 bind 分配，临时 UDS/子进程数据在允许写域并随 fixture 清理；normal_exit_replay 保留原退出收敛行为且不依赖固定仓库 scratch，路径依赖有定位证据。
- [x] AC-007（A28）：宽限期、rearm、健康与并发测试靠受控时间或可观测条件稳定判断，产品失败不会被任意 sleep 或重试掩盖；响应延迟与数据库 busy_timeout 的原有真实上限仍能使超限实现失败。
- [x] AC-008（A29）：测试名称、模块说明与 fixture 返回说明对应实际覆盖与返回结构；缺失或未执行场景明确标识，不改历史 AC 勾选冒充当时已验证。
- [x] AC-009（A30）：产品门禁从声明的支持 Python 与锁定依赖在空缓存重建，执行依赖可追溯；各服务的平台差异保留，不再依赖随时间变化的临时 --with 解析结果。
- [x] AC-010（A32）：Browser 镜像默认帮助调用及 --help/-h 返回用法且退出 0，非法参数明确非零；原有合法启动参数行为保持。
- [x] AC-011（A33）：E2E 仅检查自身真正需要的 Chrome、镜像与 dist；环境缺失/无效不伪装 PASS，网络拒绝有同条件正向基线；测试容器与证据目录符合最小权限，敏感标识脱敏并使用每次私有证据目录。
- [x] AC-012（A35）：部署环境示例仅有一处当前变量权威；所有消费者读取或由该权威生成，未用副本被移除；只保留 v2 所需变量，秘密字段为空且不引入默认凭据。
- [x] AC-013（A38）：独立产品勘误可从现行入口定位到原报告/任务与替代关系，报告数量、finding 映射和证据等级可核对；缺失旧证据标未知，所有冻结归档原文件字节不变，不修模板账本残留或伪造历史审批。
- [x] AC-014（A43）：产品测试共享 fixture 与真实 DockerAdapter 的行为契约相符，各故障仍能独立注入；测试不修改进程全局时钟、不穿透无关私有布局，资源等待使用 deadline 与最后观测，端口竞争重建不吞产品失败。
- [x] AC-015（A50）：从当前源冷构建的 Stream 运行镜像不包含编译器与开发头文件，仍通过真实音视频、输入、剪贴板与动态库加载验证；共用协议依赖从唯一约束产生，各服务完整锁可重建且平台差异有明确依据。
- [x] AC-016（A51）：构建戳生成与校验对必需输入、文件集合和允许环境值一致；必需输入缺失不能生成 stamp，新增/删除影响构建的文件或变更声明环境使旧产物过期，扫描不读取未声明私密环境文件。
- [x] AC-017（A52）：CBrowser 自有路径隐私守卫识别 macOS/Linux/Windows 开发者路径及候选文本后段泄漏，固定容器路径有精确例外；只有已批准具体历史文件/内容被豁免，新增归档或新增泄漏不能继承目录级豁免，存量原文保持不变。
- [x] AC-018（A53）：性能证据保存完整样本且继续执行原首帧/输入/SQLite 等待预算；缓冲溢出可观察，丢失关键证据明确失败；vendor pin 报警与实际 manifest 完整性校验共同运行，不以放宽门槛或缺正向基线通过。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

AC-002、AC-008、AC-013、AC-017 的产品文档事实、历史关系与隐私例外批准边界不能仅凭自动测试判断；由 reviewer 对照源码、ADR、源报告与实际证据逐项复核，辅以引用/计数/归档字节自动核对。其他 AC 全部可自动测试；镜像与真实 Chrome 在隔离环境执行，缺前提不作 PASS。

## 上下文区

- 来源：用户 2026-11-03 明确要求为全部采纳项合并立项；[review_20261103_185924 决策](../../reviews/review_20261103_185924/adoption_decision.md)；本组 A1、A23、A24、A25、A26、A27、A28、A29、A30、A32、A33、A35、A38、A43、A50、A51、A52、A53。原 D1=B、原 D2=A 已按用户选择写回；本轮仅创建 backlog，不授权实施或提交。

### 采纳项承接与设计边界

|采纳项|主验收|来源 finding|
|---|---|---|
|A1|AC-001|f_contracts_deploy_01|
|A23|AC-002|f_docs_current_01, f_docs_current_02, f_docs_current_03, f_docs_current_04, f_docs_current_05, f_docs_current_06, f_docs_current_07, f_docs_current_08, f_global_evolution_04, f_global_system_properties_05, f_backend_runtime_adapters_15, f_backend_supervisor_12|
|A24|AC-003|f_tests_e2e_stream_frontend_01, f_tests_integration_fixtures_04|
|A25|AC-004|f_tests_e2e_stream_frontend_03, f_tests_e2e_stream_frontend_04, f_tests_integration_fixtures_01, f_tests_integration_fixtures_02, f_tests_integration_fixtures_03, f_tests_integration_fixtures_08, f_global_evolution_05|
|A26|AC-005|f_tests_e2e_stream_frontend_05, f_tests_e2e_stream_frontend_06, f_tests_e2e_supervisor_08, f_tests_e2e_supervisor_09, f_tests_unit_stream_api_05, f_tests_unit_stream_api_06, f_tests_unit_supervisor_runtime_04, f_tests_unit_supervisor_runtime_06|
|A27|AC-006|f_tests_integration_fixtures_05, f_tests_integration_fixtures_12, f_tests_unit_stream_api_01, f_tests_unit_stream_api_03, f_tests_unit_stream_api_07, f_tests_unit_supervisor_runtime_05|
|A28|AC-007|f_frontend_features_04, f_tests_e2e_stream_frontend_07, f_tests_e2e_supervisor_02, f_tests_unit_supervisor_runtime_02|
|A29|AC-008|f_tests_e2e_supervisor_01, f_tests_e2e_supervisor_05, f_tests_e2e_supervisor_11, f_tests_unit_supervisor_runtime_01|
|A30|AC-009|f_contracts_deploy_06, f_global_evolution_08|
|A32|AC-010|f_contracts_deploy_15|
|A33|AC-011|f_tests_e2e_supervisor_03, f_tests_e2e_supervisor_06, f_tests_e2e_supervisor_07, f_tests_integration_fixtures_10, f_tests_integration_fixtures_11, f_tests_e2e_stream_frontend_11|
|A35|AC-012|f_contracts_deploy_11|
|A38|AC-013|f_archive_reviews_01, f_archive_reviews_03, f_archive_reviews_04, f_archive_reviews_05, f_archive_reviews_07, f_archive_tasks_01, f_archive_tasks_02, f_archive_tasks_03, f_archive_tasks_04, f_archive_tasks_05, f_archive_tasks_06, f_archive_tasks_07, f_archive_tasks_10, f_archive_spikes_11, f_archive_spikes_21, f_archive_reviews_02, f_archive_reviews_06, f_archive_reviews_09, f_docs_current_10|
|A43|AC-014|f_tests_e2e_supervisor_04, f_tests_e2e_supervisor_10, f_tests_e2e_supervisor_12, f_tests_integration_fixtures_06, f_tests_integration_fixtures_07, f_tests_unit_stream_api_02, f_tests_unit_stream_api_04, f_tests_unit_stream_api_09, f_tests_unit_stream_api_10, f_tests_unit_supervisor_runtime_03, f_tests_unit_supervisor_runtime_07, f_global_system_properties_04|
|A50|AC-015|f_contracts_deploy_12, f_contracts_deploy_13|
|A51|AC-016|f_tests_e2e_stream_frontend_02|
|A52|AC-017|f_template_tests_04, f_archive_tasks_09|
|A53|AC-018|f_tests_e2e_stream_frontend_08, f_tests_e2e_stream_frontend_09, f_tests_e2e_stream_frontend_12, f_tests_integration_fixtures_09|

以下为已采纳修复边界；具体结构选择以满足当前需求的最简单长期实现为准，不以开发时间或改动规模降级。

- **A1 · 补齐 Supervisor 镜像构建白名单**：在 config/docker/supervisor_runtime/Dockerfile.dockerignore 放行 src/backend/cbrowser/launch_args.py；增加 COPY 来源与上下文匹配检查，并在隔离构建中验证 Supervisor 镜像。
- **A23 · 同步当前文档与 ADR，刷新交接事实**：当前 blueprint/spec 对齐同机直连、0750/0640、chown 失败报错与 error 枚举；findings 追加 ADR 013 替代状态，保留原实验事实；plan 明示被替代范围。handoff 新节写实际 branch/head、完成/未验收边界和 p016–p019，旧节只追加归档；pending 按更新时实际目录核对，不把 p016–p019 当完整静态清单；t009 等已归档任务不改原 AC，仅在独立勘误中指向现行直连验收与替代关系。修正 migration pragma 与 PortAllocator 单事件循环说明。任务状态以当前登记位置为准，不据旧报告重开已归档任务或擅改未完成任务状态。
- **A24 · 在 dist 实际消费点校验构建新鲜度**：frontend_app_probe 与 host_builder 在复制 dist 前调用现有 verify_frontend_build_freshness；保留或简化 collection 入口，避免重复构建。补非 frontend 文件名消费者、缺 stamp、源码变化与有效产物用例。
- **A25 · 测试替身不替代被声明验证的生产链**：资源探针经 GatewayControlClient 和真实 Gateway 下配额；Gateway lane 加载实际构建 adapter；API fake 按 Origin/cookie/Profile 显式授权、默认拒绝 automation。将 HELLO 注入/重连/标签共存核心场景接生产 Agent；仅服务端协议探针正确命名。wire stub 限于超时/坏响应，授权与 fence 用真实 create_gateway_app。
- **A26 · 收紧行为断言，避免失败也算成功**：用真实 HELLO TEXT 证明信令；已就绪后未授权 Profile 精确断言契约状态，不接受 503。强制凭证 mount 存在且只读；用活 Docker client 做泄漏检查；具体 ownership 异常与精确游标位置断言；fixture 提供有效其他 secret；调用方管理 HTTP client 生命周期；存储 seam 注入失败并验证无写入。
- **A27 · 测试资源使用局部临时目录与系统分配端口**：路径读取锚定 __file__；WS bind 0 后读取实际端口；短 UDS 根用带 finalizer 的 fixture，所有生成位置在允许写域；API subprocess scratch 延迟至 fixture；复用现有 parsed OpenAPI。先定位 p019 的路径依赖，再迁移 normal_exit_replay 数据根并保留原行为断言。
- **A28 · 以可观测条件替代等待猜测，保留真实时间预算**：会话宽限测试用注入时钟或 fake timers；健康/rearm 等用 deadline+last-observation 条件等待；Supervisor 重复等待复用现有 wait helper。并发性用事件栅栏证明，不靠 0.6s 绝对耗时；保留响应延迟、数据库 busy_timeout 的行为与时间上界。
- **A29 · 测试说明与实际覆盖范围一致**：对应模块 docstring 写清实际行为与覆盖文件；real_api_server 注释为四元组；不改历史 task AC 勾选或把未执行验证称已通过。
- **A30 · 门禁依赖使用可重建的锁定环境**：以 pyproject 与现有 runtime requirements 盘点生成门禁依赖锁，固定受支持 Python 与执行依赖；run_gates.sh 从该锁安装。验证空缓存可重建与各门禁加载，保留平台差异；不强行把所有服务的可兼容 patch 版本统一；不修改 repo_template 内部依赖、脚本或契约测试。
- **A32 · Browser 镜像默认帮助调用正常退出**：entrypoint.sh 加 --help/-h 用法说明与 exit 0；非法参数仍非零。用隔离 shell/镜像命令验证默认、帮助与非法参数三态。
- **A33 · E2E 前提按实际套件声明，测试容器沿用最小权限**：按实际 fixtures/markers 声明 Chrome、镜像、dist 前提；离线出口先建立同条件正向基线，缺失时明确该子场景未验证，不把整份隔离测试算 PASS。数据目录精确 UID/GID/0750 或受保护父目录，SHM 0600；证据每次私有目录并脱敏标识。Selkies 测试 runner 采用 cap_drop ALL/no-new-privileges，实测必要例外单列。
- **A35 · 环境示例只保留当前部署权威入口**：核对 config/.env.example 的全部消费者；若无消费者则移除并更新必要引用，有消费者则由根权威模板生成。只保留 v2 变量及来源说明，示例秘密保持空且由用户提供。
- **A38 · 历史证据追加勘误与现行承接，不重写快照**：新增独立勘误文件及引用入口：复算 33/30、A13 覆盖与全量映射数量；用报告路径+finding ID 消除跨轮裸编号歧义；标注截断来源和可取得的 Markdown 指纹；说明 Gaps 指单元覆盖、Limitations 指方法限制。逐项核实 task 最终轮次、trust_prior/NOT_RUN、遗留承接、产品交付承接与 spec 替代；已不存在旧证据如实标未知，以现行测试补证并区分时间，不改变原勾选冒充当时执行。补明 s011 合成 visibility 与外部 fixture 依赖范围，当前仍有意义的媒体/真实可见性场景在现行套件复验。只新增允许位置的产品事实勘误文件，归档原文件字节不变；不改 repo_template 流程、账本模板规则或生成器，模板残留问题已转 R10 拒绝。 冻结 benchmark 通过旁注指向 ADR 012 与现行手动输入/剪贴板验收，不改写原测试历史。
- **A43 · 共享测试基础设施与可控时间承担唯一事实源**：tests/fixtures 建唯一 DockerAdapter 契约替身与 API/auth/端口/进程生命周期支持，每个测试只描述自身故障；与真实适配器做行为契约对照。保留必要故障 seam，其他 session/state 通过现有服务构造与公开观测读取，原始 SQL 仅迁移/损坏场景使用并标明原因。限速/捕获策略依赖局部 clock callable，不修改 stdlib 模块对象；长授权测试按独立行为拆分。异步等待统一 deadline 与最后观测，端口 probe 明确不预留并在实际 bind 失败时有受限重建，不能吞产品失败。去除重复赋值/import，以 fixture 保存 session_maker，不穿透 repository 私有属性。同步真实 test_cmd/黑盒命令测试，保留负例强度。
- **A50 · Stream 镜像只交付运行依赖，共用依赖声明可追溯**：stream_runtime/Dockerfile 使用 builder 阶段生成 native wheels/产物，runtime 只安装实际共享库、GStreamer 插件和程序，compiler/-dev 不入最终层；用真实音视频/输入/clipboard 及 ldd/导入检查证明依赖齐全。共有 Python 协议依赖从唯一 constraints/声明解析，各镜像保留按其平台与职责生成的独立完整锁；同协议 Pydantic patch 对齐为经测试版本，差异若必要须有明确契约证据。生成器与冷构建回归保证不靠手动复制锁文件。
- **A51 · 前端构建指纹覆盖完整且受控的输入集合**：构建戳生成与校验共用明确输入清单，区分必需文件/可选缺失状态，必需输入缺失拒绝生成 stamp；包含影响构建的配置及允许环境值摘要，Vite 根环境输入由声明边界控制而不散扫秘密。stamp 记录文件集合与内容摘要；新增/删除配置、源码变更及环境变更均使产物过期。补缺必需文件时无法 stamp、已存文件删除、新配置输入及有效构建测试。
- **A52 · 隐私规则按真实开发环境覆盖，历史豁免精确到存量**：test_repo_hygiene 识别 macOS/Linux/Windows 开发者路径，容器固定用户路径有明确例外；按已跟踪文本类型和完整读取校验，不以首 8192 字节任意 NUL 静默放弃整份文本。现有历史豁免绑定具体路径及已批准内容指纹，新增文件或新增泄漏不自动继承 archive 豁免；新归档写入前脱敏。存量快照不批量改写，在独立勘误/隐私索引说明已公开范围与适用限制，不把会话 ID 自动当凭据值。
- **A53 · 量测保留真实预算，证据缓冲与正向验证可检查**：性能测试在已记录硬件/资源前提下同步触发并记录完整样本，继续按现行 first-frame/input/SQLite busy_timeout 上界判断，不擅自改中位数、重试掩盖超标或扩大阈值。锁等待测试用事件协调真实释放/超时，排除准备阶段耗时但不排除被测耗时。adapter_probe 保留有界日志并记录 dropped_count/序号，关键控制类别用计数/独立证据，溢出导致证据不足须明确失败而非误报产品行为。vendor 验证入口同时执行 pin 报警及实际 vendored manifest 校验，现有同等真实校验复用，不重复联网下载。

### 有意不测

- repo_template 整改、正式备份恢复/切换与已拒绝项：用户明确排除，不新建相关测试。
- 公网/跨主机媒体与原生 x86 环境：不扩大现行单机包络，沿用已记录用户豁免，不宣称实测。

### 测试策略

- 产品门禁使用空缓存重建，隔离构建 Supervisor/Browser/Stream；检查 COPY 上下文、默认/帮助/非法参数、最终层编译器/动态库及实际音视频/输入/剪贴板。
- 构建 stamp 从唯一输入集合生成，在非 frontend 命名的真实消费点校验；删除/新增配置、环境变化、缺必需输入均有负例，私密 env 不被泛扫。
- 产品 fixture 与真实 adapter 对照，所有关键断言让故障实现必然失败；normal_exit_replay 先定位路径依赖后迁移，用事件/局部时钟取代猜测等待，真实性能上限不变。
- E2E 在完整镜像/Chrome 前提下验证真实 Gateway/Agent/adapter；缺前提或关键证据溢出明确失败/未执行，不扩展用户已豁免的公网/x86 实测。
- 自动核对引用/映射/源指纹、归档字节、路径隐私新旧样本及文档格式；由 reviewer 对照源码、当前 ADR 与实际证据复核文档事实，不拿静态检查代替实测。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- SPIKE 已核实（t024 实施期定位，p019 根因）：normal_exit_replay 的短路径依赖是 AF_UNIX sun_path 长度上限。测试经 `_run_uds_server` 以 CWD 相对路径绑定 `<data_root>/runtime/<profile-uuid>/agent.sock`；仓库 `.scratch` 相对路径长 89 字符可绑定，pytest tmp_path 相对路径长 151 字符时 bind 报 `AF_UNIX path too long`，Agent 静默未启动，Supervisor 健康探测无 socket，退出事件不收敛（desired_state 停留 running、last_exit_event_id=None）。验证方式：同机实测三种数据根的相对路径长度与 bind 结果（89 成功 / 151 失败 / 短临时根 91 成功）；迁移后以带 finalizer 的 `short_data_root` fixture（系统临时域短根）在仓外运行，四用例保留原收敛断言全绿。其余为当前依赖下可直接验证的产品边界。

### 风险与回退

- 风险：共享 fixture 抽象可能弱化独立故障模型；精简镜像可能漏动态库；stamp 扩围可能读入秘密；历史勘误可能误写冻结档案。
- 回退：保留原行为断言与原始证据，先对照隔离构建/fixture 再替换；回退仅针对本组源与未发布产物，不改原始归档字节、不放宽预算或权限、不清除运行数据。

### 依赖与约束

- 依赖前端 task（传递依赖控制 API 与运行时 task）完成整合后的生产链路，再收敛全局 fixture/门禁与证据；前序 task 的功能回归仍须在各自 task 完成。
- 与 t019 的 Stream 配置/媒体回归、t020 的 Browser 构建/字体测试有交叉；两者不作为无关功能硬前置，实际执行通过冲突关系串行，镜像以当时整合基线为准。
- 只改产品门禁调用环境与产品测试，不修改 repo_template 内依赖、内部测试或治理规则；已存在模板契约执行命令沿用，不扩展模板整改。
- A38 只追加独立产品事实勘误；原档案中的模板示例/账本残留明确属于 R10，不承接。p019 不在创建期改状态，按实施证据收尾。

### Finalization 时更新的 blueprint

- `docs/blueprint/testing.md`：当前产品门禁层次、支持环境、真实前提、fixture/时间与证据完整性。
- `docs/blueprint/architecture.md`：消除 legacy 与交付现状漂移，保留五服务与同机边界。
- `docs/blueprint/artifacts.md`：与前序 task 交付的权限/内容/删除语义一致。
- `docs/blueprint/domain.md`：运行状态和 Profile 字段的当前真相。
- `docs/blueprint/stream_runtime.md`：现行镜像运行依赖与测试证据边界。
- `docs/blueprint/decisions.md`：ADR 替代链接、产品历史勘误入口及隐私历史例外边界。

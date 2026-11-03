# bundle_global_system_properties

## Summary

组合视角下，这套系统的整体性质呈三段式：v2 多服务在代码层确实共享同一套 fail-closed 设计语言（唯一 DB 写者、唯一 Docker socket 持有者、授权失败关闭、令牌只存哈希、启动失败关闭），其状态权威与幂等栅栏设计扎实，凭据读取链经源码核对为单一实现、全链一致（见 f_global_system_properties_08）；但系统级承诺在三个组合点上落空。其一，部署链不闭合：仓库工件既不能干净冷启动 legacy（生产 Dockerfile 与 compose 输出同名标签自引用），也不能部署 v2（四个运行时镜像无部署路径、Supervisor 镜像构建即缺文件），现网可运行依赖仓外既有镜像与本地状态，因此系统的实际安全水位由唯一可部署的 legacy 面决定，而该面的鉴权是代码级 opt-in、部署文档又与 compose 的回环绑定矛盾，安全边界实质是部署约定而非代码性质（f_01、f_02）。其二，v2 的可靠性承诺在事件投递层断裂：同一进程内的两个转发器与 API 错误契约对同一 HTTP 状态给出三种互相矛盾的永久/暂时分类，组合结局同时包含运行事件被永久隔离丢失与被每秒无限重试，desired/observed 收敛在故障窗口内不成立（f_03）。其三，仓库的自我证明体系（测试绿灯、文档权威链、归档证据链）组合后证明力显著低于其各自宣称：生产恒走分支被测试恒绕、fixture 重实现生产语义且互相漂移、PASS 证据可由测试支持代码合成、dist 新鲜度按文件名判定、门禁环境未钉版（f_04）；文档权威链在文件权限这一安全参数上直接自相矛盾且无 superseded 标记（f_05）。其余组合结论为低severity：幂等键两端作用域不一致的组合行为已可静态闭环为「合法并发写被 409 响亮拒绝」而非静默吞掉（f_06）；多子系统成本随累积历史单调增长且无一处有保留上限，在单机单人包络内影响有限（f_07）。四条需运行或跨单元证据才能定谳的问题已列入 questions，其中 Supervisor 内部 RPC 面的框架依赖传播（q_01）与已部署 legacy 面的 serve_spa 穿越可达性（q_04）若结论反转，将分别抬升 v2 与 legacy 的整体安全评级。

## Findings

- [High][85] compose.yaml；config/docker/Dockerfile:2；config/docker/supervisor_runtime/Dockerfile:18 与其 Dockerfile.dockerignore；docs/reviews/review_20261103_185924/_meta/local_contracts_deploy.json（f_contracts_deploy_01/02/04） — 冷启动部署链对两代系统都不闭合：仓库工件无法从零部署任一代系统，现网可运行依赖仓外状态
  - ID: f_global_system_properties_01; verification: static
  - Evidence: compose.yaml 只有一个服务：build config/docker/Dockerfile、image 为 cbrowser:latest、端口 127.0.0.1:${CBROWSER_PORT:-56661}:8080；config/docker/Dockerfile 首行 FROM cbrowser:latest，与 compose 给自身输出的标签同名自引用——全新机器上该基础镜像不存在，构建无从开始（f_contracts_deploy_02）; Supervisor 运行时 Dockerfile COPY src/backend/cbrowser/launch_args.py，但其 Dockerfile.dockerignore 白名单未放行该文件，按当前组合构建即缺文件失败（f_contracts_deploy_01，本轮已回查 Dockerfile:18 的 COPY 行确认）; v2 的四个运行时镜像（browser/stream/gateway/supervisor runtime）在 compose.yaml 中从未被引用，无任何部署路径（f_contracts_deploy_04）; 三条局部结论组合后才显现的整体性质：legacy 的唯一部署路径自引用、v2 的部署路径缺失且关键镜像不可构建——仓库自身工件对两代系统都不构成可复现的冷启动路径；任何现网实例能运行，必然依赖构建机上先行存在的同名镜像或其他仓外状态
  - Impact: 「从仓库重新部署」这一基本系统性质不成立：新机器、灾难恢复、换机迁移时按仓库文档与工件操作无法把任一代系统干净地跑起来；同时意味着审阅与测试所验证的代码状态与现网运行的二进制之间没有可复现的对应关系，现网镜像的真实内容不可由仓库单独证明。
  - Fix: legacy Dockerfile 改为基于钉版的基础镜像或多阶段自包含构建，消除与 compose 输出标签的自引用；补齐 supervisor_runtime 的 dockerignore 白名单并在门禁中实际构建四镜像；为 v2 增加可用的 compose/部署工件（或明确标注 v2 未交付部署），并加一条 CI 冷构建校验保证部署链持续闭合。

- [High][75] src/backend/main.py:112-165（AUTH_TOKEN 逻辑）；.env.example:17 与 config/.env.example:17；DOCKER_DEPLOYMENT.md:12-27；compose.yaml 端口绑定；local_backend_core.json（f_backend_core_01/03/04）、local_contracts_deploy.json（f_contracts_deploy_03/05） — 系统有效安全边界由部署约定而非代码决定：唯一可部署的 legacy 面鉴权 opt-in、模板默认空令牌、部署文档又宣称局域网绑定
  - ID: f_global_system_properties_02; verification: static
  - Evidence: main.py:116 AUTH_TOKEN = os.environ.get("AUTH_TOKEN") or None；中间件在 AUTH_TOKEN is None 时对全部请求放行（main.py:145 起）——鉴权是代码级 opt-in，未配置即全开放（f_backend_core_03）; .env.example:17 的 AUTH_TOKEN 模板默认空，而其自身注释称其为 Required（f_contracts_deploy_03）；compose 仅透传该变量，不提供强制校验; DOCKER_DEPLOYMENT.md:13/16/27 宣称网络监听绑定 0.0.0.0:56661 并给出局域网访问方式，与 compose.yaml 实际的 127.0.0.1 回环绑定直接矛盾（f_contracts_deploy_05）——照文档口径理解部署的操作者会以为局域网暴露是预期姿态; 同一 legacy 面上另有：剪贴板正文前 60 字符写入 manager.log（f_backend_core_01，High，与 diagnostics 脱敏承诺冲突）、/api/open-external 缺 /api/shutdown 已有的同源 CSRF 防护（f_backend_core_04）; 组合结论：默认 compose 路径（回环+空令牌）下风险被回环绑定兜住；但令牌默认空、代码默认放行、文档宣称局域网绑定三者叠加后，只要部署按文档口径改为局域网绑定且未另行注入 AUTH_TOKEN，宿主机控制端点（shutdown/open-external）、profile 数据与 VNC/CDP 代理即构成无鉴权局域网控制面——是否暴露完全取决于部署者是否同时做对两件代码不强制的事
  - Impact: 系统的安全性质无法由代码与默认工件推出，只能由每个部署现场的约定推出；文档与默认值还在向不安全方向引导。任何依据「仓库默认部署是安全的」作出的整体安全结论都不成立。
  - Fix: legacy 启动时在绑定非回环地址且 AUTH_TOKEN 未设置的情况下拒绝启动（把 v2 的 fail-closed 基调下沉到 legacy）；.env.example 与 compose 增加令牌非空校验；修正 DOCKER_DEPLOYMENT.md 的绑定地址与暴露面描述与 compose 一致；剪贴板日志改为只记元数据。

- [Medium][85] src/backend/cbrowser/supervisor/event_forwarder.py:190；src/backend/cbrowser/supervisor/artifact_forwarder.py:22；local_backend_supervisor.json（f_backend_supervisor_01/02）；local_backend_api_auth.json（f_backend_api_auth_06）；src/backend/cbrowser/api/internal_supervisor.py（require_supervisor 的 503） — 事件投递层没有统一的永久/暂时故障分类：同一状态码在不同组件下分别被永久隔离、无限重试与误报可重试，desired/observed 收敛在故障窗口内不成立
  - ID: f_global_system_properties_03; verification: static
  - Evidence: event_forwarder.py:190：非 200 且 <500 一律 REJECTED 并隔离进 quarantine（本轮已回查源码），401/403/429 这类典型暂时故障（令牌轮换窗口、限速）会被当作永久拒绝，运行事件永久丢失; artifact_forwarder.py:22 恰恰相反：RETRYABLE_4XX = {401, 403, 408, 429}，同一进程内的产物转发器把同一组状态码判为可重试——两个转发器对同一故障给出相反分类（f_backend_supervisor_02）; 磁盘事件路径 consume_disk_events 在 EventForwarder 报告 REJECTED 时不推进游标，被判永久拒绝的事件反而被每秒无限重试（f_backend_supervisor_01）——同一「API 说不」在 spool 路径是永久丢弃、在磁盘路径是活锁式重试; 另一端同样错位：内部 RPC 未配置令牌时返回 503（永久性配置错误），而统一错误处理器把全部 503 标为 database_busy 且 retryable=true（f_backend_api_auth_06），永久错误被呈现为暂时故障诱导无限重试; 组合后果：运行事件是 API 侧 observed 状态的权威输入；故障窗口（如令牌文件轮换、API 短暂 403/429）内的退出/状态事件一部分被永久隔离、一部分无限重试，窗口过后 desired/observed 无法靠事件自愈收敛，且两种失败模式都不向操作者呈现为可区分的告警
  - Impact: v2 的核心可靠性承诺（状态权威 + 幂等事件 → 最终收敛）在恰恰最需要它的故障窗口内不成立：会出现浏览器实例实际已退出而 API 长期显示运行中（或反之）的静默漂移，且投递子系统整体没有单一可述的投递语义（at-least-once / at-most-once 均不成立）。
  - Fix: 在 supervisor 侧定义一份共享的投递分类契约（哪些状态码可重试、退避上限、隔离条件），event/artifact 两个转发器与磁盘消费游标共用；REJECTED 必须推进游标并落可观测的死信记录；API 错误契约区分永久配置错误（503 不标 retryable）与暂时不可用。

- [Medium][80] local_template_tests.json（f_template_tests_01）；local_tests_integration_fixtures.json（f_tests_integration_fixtures_02/03/04）；local_tests_e2e_stream_frontend.json（f_tests_e2e_stream_frontend_01/03/04）；local_backend_api_auth.json（f_backend_api_auth_09/10/11/12）；local_contracts_deploy.json（f_contracts_deploy_06）；local_template_scripts_state.json（f_template_scripts_state_17/18） — 「测试/门禁通过」的证明力被多层组合折损：生产恒走分支被恒绕、fixture 重实现生产语义且互不一致、PASS 证据可合成、门禁环境未钉版
  - ID: f_global_system_properties_04; verification: static
  - Evidence: 恒绕层：PUT/PATCH 的 launch_args 校验、CSRF 的 Referer 回退分支、内部 RPC 未配令牌的 503 分支、viewer-authorize 的 Origin 规范化变体四处生产必经分支零测试覆盖（f_backend_api_auth_09/10/11/12）；repo_state.py 的子目录 CWD 调用、board.js 1135 行零行为测试（f_template_scripts_state_17/18）；宿主机控制端点成功路径零覆盖（f_backend_core_16）; 重实现层：集成 fixture 的两套 Selkies 客户端 shim 重实现生产适配器的标签身份语义且彼此不一致（f_tests_integration_fixtures_02）；Gateway→API 假面有两套、其中 HTTP 假面无条件放行 automation 授权且忽略 viewer origin（f_tests_integration_fixtures_03）；E2E 侧 AC-010 在测试内重实现 StreamAgent、流运行时套件对着测试内 GatewayMockServer 验证（f_tests_e2e_stream_frontend_03/04）——这些套件通过证明的是替身的行为，不是生产代码的行为; 证据合成层：模板真实 git E2E 套件的 review PASS 证据由测试支持代码合成、项目验证门禁被整体关闭，生产侧「审阅产出证据 + 执行项目验证命令」路径从未被端到端执行（f_template_tests_01）; 新鲜度与可复现层：前端 dist 新鲜度门禁按测试文件名含 'frontend' 判定而非实际消费、多条 lane 可静默测旧 dist（f_tests_e2e_stream_frontend_01、f_tests_integration_fixtures_04）；run_gates.sh 从未钉版包组装测试环境，本地门禁结果不可复现（f_contracts_deploy_06）; 组合结论：单看每一层都是局部缺口；叠加后，一次全绿的套件/门禁运行无法区分「生产代码正确」与「替身自洽 + 证据合成 + 旧产物 + 恰好未绕开的分支没出错」，与仓规 AGENTS.md 自述的 TDD 纪律（测试须触达生产逻辑）之间存在系统级落差
  - Impact: 仓库工作流把测试与门禁绿灯当作 task 闭环与发布判断的主要依据；该依据的实际证明范围明显小于其被使用的范围，尤其在授权、CSRF、令牌未配置等安全分支上绿灯不提供任何保证。后续任何「已通过测试」的结论都需要逐项核对触达的是生产代码还是替身。
  - Fix: 为恒绕清单逐项补真实覆盖（内部 503、Referer 回退、Origin 变体、PUT/PATCH launch_args、子目录 CWD）；fixture 假面改为复用生产实现或做契约一致性测试钉住分歧点，authorization 假面禁止无条件放行；dist 新鲜度按实际消费判定并 fail-closed；run_gates.sh 钉版依赖；模板 E2E 至少保留一条不合成证据、不关闭项目门禁的端到端路径。

- [Medium][85] docs/specs_index.md（在表即生效规则）；local_docs_current.json（f_docs_current_01/02/03/05/06）；local_archive_reviews.json（f_archive_reviews_05）；local_archive_tasks.json（f_archive_tasks_01/02） — 文档权威链组合后不自洽：生效规则指向的长期真相与决策层直接冲突且无 superseded 标记，含文件权限安全参数
  - ID: f_global_system_properties_05; verification: static
  - Evidence: blueprint/artifacts.md 仍写 chown 失败回退 0755/0644，与 ADR 014（统一 uid 1000、目录 0750/文件 0640、chown 失败即报错、删除全局可写回退）及 blueprint/security.md 直接冲突（f_docs_current_03）——按「blueprint 是长期真相」行事的实现者会重新引入 ADR 明确删除的全局可读回退; findings 登记表未随 ADR 013 修订：8 篇 TURN/ICE 类 finding 仍标『有效』且正文含已失效指令（f_docs_current_02）；v2_architecture_plan.md 与 blueprint/architecture.md 亦保留 coturn/凭证轮换为现行设计的表述且无替代标注（f_docs_current_05/06）; docs/handoff.md 整体过期一轮：仍称下一步 t015、head 为旧提交、pending 为空（f_docs_current_01），而 AGENTS.md 规定 handoff 是项目级交接面; 归档证据层同病：上一轮审阅归档中的审计哈希链指向未入库的 _meta 产物，仓内读者无法复算验证（f_archive_reviews_05）；t018 账本出现 AC 在自声明必需验证从未执行时打勾关闭、Review 处置表样板化（f_archive_tasks_01/02）; 组合结论：仓库的权威规则（specs_index 在表即生效、blueprint 为长期真相、findings 为已验证事实登记、archive 为只追加证据层）各自单看成立，但层与层之间没有一致性维护机制——新决定（ADR）落盘后不回写旧层、旧层不标 superseded，于是按自家规则查阅的读者与自动化会被系统性引向已废止口径，其中至少一处是安全参数
  - Impact: 文档体系作为事实来源的整体可信度受损：任何单篇文档的陈述都不能默认与当前决定一致，跨文档结论必须逐条核对 ADR 日期与替代关系；更实际的风险是后续实现或运维按 blueprint/findings 的过期口径落地安全相关行为。
  - Fix: 建立 ADR 落盘时的连带修订清单（受影响的 blueprint/specs/findings 条目同步改写或加 superseded 标注并指向新 ADR）；findings 登记表按 ADR 013 批量修订状态；handoff.md 纳入 task 收尾的强制更新点；归档审计链改为只引用已入库产物或把被引 _meta 一并入库。

- [Low][85] src/frontend/src/features/profiles/useProfilesQuery.ts:60-77；src/frontend/src/features/artifacts/useArtifacts.ts:35-53；src/backend/cbrowser/adapters/database/repository.py:52-56,88-100；src/backend/cbrowser/api/app.py:229-236；local_frontend_features.json（f_frontend_features_01） — 幂等契约两端键作用域不一致：组合行为已可静态闭环——合法并发写会被 409 响亮拒绝，而非静默吞掉或回放
  - ID: f_global_system_properties_06; verification: static
  - Evidence: 前端全部 mutation hooks 以单个 useRef 保存 actionKey，mutationFn 不区分 variables、仅在 onSettled 时清零：同 hook 实例在前一次未 settle 时发起的异目标/异载荷并发调用会复用同一 Idempotency-Key（f_frontend_features_01）; 后端以 operation_id 为审计记录主键全局查存（repository.py:89 session.get(AuditEventModel, operation_id)），sig_hash = sha256(action, target, payload)（repository.py:52-56）；同 key 异签名即抛 IdempotencyConflictError（repository.py:92-95）; 该异常在 API 层映射为 HTTP 409、error=idempotency_conflict（app.py:229-236，本轮已回查）; 组合闭环：前端复用 key + 后端全局键空间 + 签名校验三者叠加后，用户可见行为是确定的——第二个合法写操作收到 409 冲突错误，不会被当作第一个操作的重试静默吞掉、也不会回放首个响应；汇总阶段悬置的『冲突报错还是静默回放』之问就此静态定谳。残余问题是可用性层面的误拒（触发窗口为同实例并发异参调用，现有 UI 多以 isPending 禁用按钮缓解，但属调用点约定而非 hook 契约）
  - Impact: 数据完整性不受损（后端响亮失败），但用户在快速连续操作不同 profile 时可能遇到莫名 409；且该行为未被任何一端的测试钉住（前端 retry 测试只锁定同一次调用的 React Query 重试复用 key），未来任一端修改键作用域都可能把误拒变成静默回放而无回归网。
  - Fix: 前端改为按每次 mutate 调用生成 key（仅在 React Query 内部重试间复用，把 key 存入 mutation meta/context 而非 hook 级 ref）；补一条跨端契约测试：同 key 异载荷必须 409、同 key 同载荷必须回放首响应。

- [Low][75] local_backend_runtime_adapters.json（f_backend_runtime_adapters_01）；local_backend_supervisor.json（f_backend_supervisor_05/08）；local_backend_api_auth.json（f_backend_api_auth_05）；local_backend_core.json（f_backend_core_07） — 多子系统成本随累积历史单调增长且无一处有保留上限：长期运行实例会持续变慢，与当前负载无关
  - ID: f_global_system_properties_07; verification: static
  - Evidence: 每次 profile 读取 eager-load 全部配置版本历史与产物行（selectin），而配置版本是不可变只追加的——读成本随版本数线性增长（f_backend_runtime_adapters_01）; 每次 Browser 启动递归重验整个引擎缓存树，启动延迟随缓存规模增长（f_backend_supervisor_05）; 已处理下载事件 ID 集只按最近一次扫描中出现的实例剪枝，持久化游标集随实例 churn 无界增长（f_backend_supervisor_08）; SSE 订阅在广播锁内构建全量快照且快照事件挤占历史环，重连时刻会短暂阻塞全体事件发布（f_backend_api_auth_05）；legacy 侧 list_profiles 为 N+1 标签查询且同步 IO 遍布 async handler（f_backend_core_07）; 组合性质：四处分属不同子系统、各自 Low，但共享同一形态——成本耦合于累积状态（版本数、缓存大小、历史实例数）而非当前请求量，且没有任何一处有保留期、分页或剪枝上限；在单机单人部署包络内短期无感，长期不重启、不清理的实例会单调衰减
  - Impact: 性能承诺无下限保证：同一部署用得越久越慢，且衰减与用户行为（频繁改配置、频繁启停短命实例）正相关；由于无一处设上限，无法给出任何「规模 X 以内性能 Y」式的整体陈述。
  - Fix: profile 读取改分页/懒加载版本史；引擎缓存校验改增量或按需；下载事件 ID 集按时间或总量剪枝；SSE 快照移出广播锁。至少为四处各设一个明确上限或保留策略，使成本重新耦合于当前负载。

- [Info][95] src/backend/cbrowser/secret_files.py:8-29；src/backend/cbrowser/gateway/server.py:73-80；src/backend/cbrowser/gateway/api_client.py:22-24；src/backend/cbrowser/supervisor/gateway_client.py:16；src/backend/cbrowser/supervisor/agent_credentials.py:15 — 正向确认：内部凭据读取链为单一实现、全链一致，局部阶段悬置的 Gateway 控制令牌 strip 疑点经源码核对不成立
  - ID: f_global_system_properties_08; verification: static
  - Evidence: secret_files.py:23：read_secret_file 对文件内容统一 .strip() 后再校验最小长度，且强制拒绝 group/other 可读（stat.st_mode & 0o077 检查）——全仓内部凭据只有这一个读取实现; gateway/server.py 将 read_secret_file(gateway_token_file) 的返回值直接 .encode() 作控制令牌比对；因函数内部已 strip，尾随换行不会造成不匹配——backend_stream_gateway 单元留给跨单元核对的 uncertainties[0] 就此消解; gateway/api_client.py:22-24 对同一函数结果再调 .strip() 属冗余但无害；supervisor 侧 gateway_client、agent_credentials、control_server、core、event_forwarder、runner 六处调用点全部经同一 read_secret_file 读取各自令牌/密钥文件（本轮 grep 回查）; 组合结论：Supervisor↔Gateway 控制令牌、Gateway→API 令牌、Agent 凭据三条跨服务凭据链在读取与规范化这一环是单一事实源，不存在各服务各自解析凭据文件的漂移面；这是 v2 fail-closed 基调中经组合核对仍成立的一环
  - Impact: 无负面影响。记录此项为的是关闭一条跨单元悬置线索，避免后续审阅重复怀疑；api_client 的冗余 .strip() 可保留（防御性）或清理，不影响正确性。
  - Fix: 无需修复。可选：删除 api_client.py 中冗余的 .strip() 或加注释说明 read_secret_file 已保证规范化，避免后来者误以为各调用点需自行处理。

## questions

```json
[
  {
    "counterevidence": "无令牌请求三条 add_api_route 路由均返回 401（或未配置时 503）、正确令牌返回 2xx 的运行记录，即可推翻怀疑。",
    "evidence_needed": "运行证据：启动真实 API 进程，分别以无 Authorization、错误令牌、正确令牌请求 POST /api/v1/internal/supervisor/runtimes/observed 与 /runtimes/events，记录状态码（预期 401/503/401/2xx）；或以随仓钉版的 FastAPI 版本写一条最小路由传播验证测试并执行。",
    "id": "q_system_properties_01",
    "question": "Supervisor 内部 RPC 面（/api/v1/internal/supervisor 的 bind/observed/events 等经 add_api_route 复用的 v1 handler）在运行时是否真的受 router 级 dependencies=[Depends(require_supervisor)] 保护？静态上 router 已声明该依赖（internal_supervisor.py:51），但 add_api_route 注册的路由是否继承 router 级依赖取决于 FastAPI 版本的具体传播语义，本轮未运行验证。若传播不成立，该面是 v2 状态权威的无鉴权写入口，整体安全评级需下调。",
    "units": [
      "backend_api_auth",
      "tests_integration_fixtures"
    ]
  },
  {
    "counterevidence": "证明 Stream 容器的全部 TCP 入站均为已建立连接的回程或回环（如 Agent↔Selkies 走回环、Gateway 只经 Agent 的既有 WS 隧道通信），且有策略测试覆盖此拓扑，即可推翻怀疑。",
    "evidence_needed": "Stream 容器内全部入站连接发起方清单：核对 stream_agent 与 vendored Selkies 的连接发起代码（谁连谁、端口、协议），并与 supervisor/network_policy.py 的 INPUT 规则逐条对照；或运行期在真实拓扑下抓取 Stream 容器新建连接记录。",
    "id": "q_system_properties_02",
    "question": "Gateway 是否会主动向 Stream 容器内的 Selkies 新开 TCP 连接？Stream 侧 INPUT iptables 策略只接受回环、已建立连接与 UDP mux 端口；本轮静态核对显示 Stream Agent 主动向 Gateway 发起注册 WebSocket（stream_agent/agent.py:262）、Gateway 代码内无 Selkies 端口（18096）引用，方向看似自洽，但 Selkies 服务端自身与 Agent 的本地连接关系未核尽，两侧局部单元都把此问留给了对方。若 Gateway 或其他组件确会新开连接进 Stream 容器，媒体/信令会在策略下被静默丢弃，组合承诺（启动门禁后媒体可用）不成立。",
    "units": [
      "backend_supervisor",
      "backend_stream_gateway"
    ]
  },
  {
    "counterevidence": "Agent 对 429 有指数退避重试且 e2e 有批量重启后全部 profile 在有限时间内恢复 running 的断言，即可推翻怀疑。",
    "evidence_needed": "StreamAgent 注册失败路径的代码核对（429/连接失败后的重试与退避策略）、Gateway 注册节流的桶参数与窗口、以及 e2e 中是否存在多 profile 同时重启恢复的用例及其断言。",
    "id": "q_system_properties_03",
    "question": "全机重启或批量恢复时，多个 Stream Agent 同时向 Gateway 重新注册、被按来源地址节流 429 后（同机 Agent 共享一个额度桶，f_backend_stream_gateway_01），Agent 侧是否有退避重试、Supervisor 恢复协调是否会放大或平滑这股注册突发？这决定批量恢复是自愈还是需要人工介入，是单机部署下最现实的整体可用性场景。",
    "units": [
      "backend_stream_gateway",
      "backend_supervisor",
      "tests_e2e_supervisor"
    ]
  },
  {
    "counterevidence": "全部编码变体均返回 404/SPA 兜底页、无一读出目标文件的运行记录，即可推翻怀疑并将 f_backend_core_02 降为不可达。",
    "evidence_needed": "隔离复现：在不连通现网的本地实例上以未授权请求发送 /%2e%2e%2f 等编码变体访问应用目录外文件，记录响应状态与内容；同时记录随仓 Starlette/uvicorn 的确切版本。",
    "id": "q_system_properties_04",
    "question": "legacy 的 serve_spa 兜底路由路径穿越（f_backend_core_02，suspected）在随仓钉版的 Starlette/uvicorn 组合下运行期是否真实可达？这是唯一可部署面上唯一一条可能未授权读任意应用文件的疑点，其成立与否直接决定 legacy 面的整体安全评级；本轮静态审阅未复现，归档记录集内对同一漏洞的核实等级表述亦不一致。",
    "units": [
      "backend_core"
    ]
  }
]
```

## question_decisions

```json
{
  "q_system_properties_01": {
    "followup_sha256": "846bfc3e65a83557b121e88052d0d7c36a4c0b0eb2ded30ba2ce0f8423a56534",
    "reason": "接受精查 refuted。裁决依据有二：其一，怀疑的全部不确定性系于 add_api_route 是否合并 router 级 dependencies 这一确定性框架代码路径，精查已在钉版 FastAPI 0.162.0 的 routing.py 逐行核实（add_api_route 以 self.dependencies.copy() 为基合并依赖并构造 APIRoute，L5794/L5798/L5824），声明下限 0.115.0 同行同样成立，路由依赖集在导入注册时即被固定，运行同一钉版的进程没有偏离空间，『传播不成立』在代码层被排除，语义问题无需运行复现来裁决；其二，仓内既存的真实 uvicorn 子进程集成套件 test_supervisor_rpc.py 已把本问要求的无/错/对三态检查编码为断言（/health 无令牌与错令牌均 401 且 WWW-Authenticate 为 Bearer、正确令牌 200，并含两条 add_api_route 注册路由的无令牌 401），若传播失效这些断言必然失败。据此撤销本问对 v2 内部面的无鉴权担忧，summary 中『q_01 若结论反转则下调 v2 安全评级』的条件不触发，v2 侧 fail-closed 组合判断维持。残余仅属执行状态确认与覆盖补强、非语义缺口：本轮未复跑该套件、其当前绿灯未经本轮确认；bind/observed/events 三条写路径未见各自的负向 401 断言、require_supervisor 的 503 未配置分支无断言——此点与 f_global_system_properties_04 的恒绕主题同向，建议补齐负向用例并在 CI 留存该套件结果，但不重开本问。",
    "result": "refuted"
  },
  "q_system_properties_02": {
    "followup_sha256": "b336dde987f08548d5e0b38b55b3af1704f710a2d597c5d322e1429ff298556e",
    "reason": "接受精查 refuted。精查独立复核了 Stream 容器全部入站连接发起方：Gateway 是纯 aiohttp 服务端、只接受连接，下行全部复用 Agent 主动建立的注册 WebSocket 隧道（agent.py:253-262），唯一外呼是指向 API 的授权/运行时查询（gateway/api_client.py），全目录无 ws_connect 等外呼；StreamAgent 与 Selkies 同容器同进程、以 ws://127.0.0.1 回环互连（agent.py:745,1049-1084），Selkies 被 entrypoint 钉死 --addr 127.0.0.1 仅绑回环；Browser 与 Stream 之间走共享 UDS（X11/Pulse bind mount）与共享 IPC 命名空间，非 TCP；媒体仅走 INPUT 明示放行的 UDP mux 端口，Stream 容器无任何 TCP 端口发布。故连接方向与 network_policy 的 INPUT『仅回环+已建立+UDP mux』（默认 DROP）逐条自洽，不存在信令/媒体被策略静默丢弃的组合缺口，『启动门禁后媒体可用』的组合承诺在这一点上成立，architecture 审阅者的同向结论亦经此独立复核确认，本路 summary 与 findings 无需调整。残余缺口一项：Selkies 服务端为 pip 包 selkies==2.1.0、源码不在仓内，其内部连接发起无法逐行核尽；但其绑定地址、媒体端口与无 TURN 配置均由仓内启动参数钉死，且 INPUT 默认 DROP 使任何未配置的非回环入站监听同样不可达，该缺口不改变裁决，仅记为静态核对的固有边界。",
    "result": "refuted"
  },
  "q_system_properties_03": {
    "followup_sha256": "3bb279da7a0b26d3798aa275807b4a25cf2d4794673c94a37654841f8b4c8620",
    "reason": "维持精查 insufficient，并分两层记录。行为层静态成立：Agent 的 connect_and_run 为无上限 while 重试循环（agent.py:253-370），429 握手拒绝与连接失败、ACK 拒绝同路落入确定性退避（1/2/4/8/16/30 秒、封顶 30 秒、成功后重置），无特殊退出分支；Gateway 注册节流为每来源 20 次/60 秒滑动窗口且 allow() 桶满时直接返回 False 而不记录被拒尝试（registry.py:89-105），重试不烧额度，P 个 profile 最迟约 ceil(P/20) 个窗口内分波完成注册；Supervisor 启动对账按 profile 串行 await、恢复重试为 per-profile 独立退避/冷却、容器 restart_policy=no，不放大也不经手注册。故『批量恢复自愈、无需人工介入』的证据等级为：代码机制静态推演成立、无任何执行证据。证据层不足：该组合场景在 unit/integration/e2e 三层零覆盖——节流与退避只被分开单测（退避用例用 MockGateway 的 ACK 级拒绝而非真实 429 握手拒绝），integration 唯一的 429 断言属 viewer 授权节流，e2e 恢复用例最多 2 个 profile 且不重启 Gateway；本问自设的反证条件（批量重启后全部 profile 在有限时间内恢复 running 的断言）不存在，按关闭标准不能判 refuted。精查另立的 Low finding f_followup_q_system_properties_03_01 已记录该覆盖缺口。本问作为限制保留：单机部署最现实的整体可用性场景（全机/Gateway 重启后画面恢复）目前只有静态保证，且恢复时长随 profile 数线性增长（与 f_backend_stream_gateway_01 的影响口径一致）；本路其余判断不受影响。",
    "result": "insufficient"
  },
  "q_system_properties_04": {
    "followup_sha256": "1bfad78ea85b837e7b1eb31c67066f67d41b6cd9ca37f9fd814541c510c551f1",
    "reason": "接受精查 confirmed。精查按钉版框架源码把可达链逐跳钉死、无剩余语义不确定性：uvicorn 0.54.0 的 httptools 与 h11 两种协议实现均先 unquote 再写 scope['path']，/%2e%2e%2f 等编码点段到达路由即字面 ../；Starlette 1.10.0 的 PathConvertor 正则为 .* 且 convert 恒等、routing.py 全文无点段规范化，full_path 逐字进入 handler；serve_spa（main.py:1835-1843）以 FRONTEND_DIR / full_path 拼接后仅判 exists()/is_file()，无 resolve/commonpath/包含校验，pathlib 不折叠 ..，镜像内上溯两级达 /app 源码、三级达 / 与 /data 卷；AuthMiddleware 对一切非 /api/ 路径直接放行、与 AUTH_TOKEN 是否设置无关，entrypoint 直连 uvicorn、无代理规范化层。据此 f_backend_core_02 由 suspected 升为静态确证可达（本轮未做运行复现，所缺仅为隔离实例的请求/响应存档，不改变判定；所依赖的三项框架语义在 legacy 的版本区间内恒定——附带修正本问前提：legacy 自身只钉下限，精查所据钉版 fastapi==0.162.0/starlette==1.10.0/uvicorn==0.54.0 属 v2 runtime 镜像）。对本路判断的影响：f_global_system_properties_02 的支撑显著加强——legacy 面除鉴权 opt-in、模板默认空令牌、剪贴板正文入日志、open-external 缺 CSRF 外，现再加一条在唯一可部署面上确证的未授权任意文件读；只要部署按 DOCKER_DEPLOYMENT.md 的局域网绑定口径落地，暴露的就不只是控制端点而是未授权文件读，『系统有效安全边界由部署约定而非代码决定』的结论维持但风险下限更低；summary 中『q_04 若结论反转则抬升 legacy 安全评级』的条件不触发，legacy 整体安全评级维持低位。另注意 src/backend/tests 对 serve_spa 零覆盖，与 f_global_system_properties_04 的恒绕清单同向。",
    "result": "confirmed"
  }
}
```

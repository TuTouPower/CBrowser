# bundle_local_contracts_deploy

## responsibilities

- schemas/ 持有四份机器可读跨服务契约：v1 HTTP API 的 OpenAPI（由 scripts/export_openapi.py 从 FastAPI app 生成）、runtime agent UDS 协议、supervisor 控制 RPC 协议、stream agent 与 gateway 的线协议（后三者由 scripts/export_*_protocol.py 从 Pydantic 模型经 TypeAdapter 生成）
- config/docker/ 持有两代部署产物：旧单容器生产镜像（config/docker/Dockerfile + entrypoint.sh，服务 legacy backend.main）与 v2 四个独立 runtime 镜像（browser/stream/gateway/supervisor）
- compose.yaml 只编排旧单容器服务；.env.example（根与 config/ 两份）声明用户侧环境变量契约；DOCKER_DEPLOYMENT.md 是唯一的部署运维文档，描述旧单容器形态
- scripts/vendor_selkies_web.py 以固定 SHA-256 下载/解包官方 Selkies 2.1.0 wheel 的 web 资源并注入 adapter 标签；scripts/verify_frontend_dist.py 在主镜像构建时对 dist 做 fail-closed 校验（资源存在性、adapter 形态、config/selkies/selkies_web_sha256.txt 清单比对）

## interfaces

- OpenAPI schemas/openapi/cbrowser_v1.json：29 个 /api/v1 操作（profiles CRUD/duplicate/reset/versions/runtime、runtimes bind/observed/events、artifacts、automation、auth login/logout/session、automation tokens、health、events SSE），与 src/backend/cbrowser/api/v1 实际路由面 29/29 逐项一致（静态比对）
- 内部 RPC 路由（/api/v1/internal/*，supervisor/gateway/artifacts）经 include_in_schema=False 有意排除在公开契约外（提交 40c4088 A17）
- 三份协议 JSON 的 $defs 与各自导出脚本列出的模型集合逐项一致（runtime agent 7、supervisor 7、stream 4 信封 + 嵌套枚举 AgentAction）；字段约束抽样与源码模型一致（如 StartProfileResponse.udp_mux_port 30000-30991、extra=forbid → additionalProperties:false）
- 前端通过 package.json 的 generate:api（openapi-typescript）从 schemas/openapi/cbrowser_v1.json 生成类型，契约文件是前端类型的上游权威

## dependencies

- v2 runtime 镜像基础镜像均为 digest 固定的 python:3.12-slim-bookworm / debian:bookworm-slim；四份 requirements.txt 均为 == 全量锁定版本
- 主生产镜像依赖仓库外预先存在的 cbrowser:latest 基础镜像（见 finding f_contracts_deploy_01）
- stream 镜像依赖 PyPI selkies==2.1.0；vendor 脚本依赖 files.pythonhosted.org 上固定路径 + 固定 SHA-256 的 wheel
- compose 依赖宿主机 .env / shell 环境提供 AUTH_TOKEN、CBROWSER_LICENSE_KEY 等 6 个变量

## flows

- 部署流（文档声明）：cp config/.env.example .env → docker compose up --build → 单容器在 0.0.0.0:56661 提供 legacy /api 与前端静态文件，数据卷 ~/.cbrowser → /data
- 契约生成流：改 Pydantic/FastAPI 定义 → 运行 scripts/export_*.py → 提交 schemas/ → 单元测试以深比较/重跑导出守住漂移（OpenAPI 见 tests/unit/test_domain_and_repository.py 的 live_schema == exported_schema 断言；三份协议各有 export 对比测试）
- stream 容器启动流：entrypoint.sh 对必填 env 与 secret 文件 fail-fast 校验 → 生成/读取 Selkies 0600 凭据文件 → 有界等待 X11/Pulse 边界 → 校验屏幕几何 → exec stream_agent

## constraints

- AUTH_TOKEN 为空即无认证（.env.example 明示 'Blank = open'），且 compose 默认把端口发布到 0.0.0.0（见 f_contracts_deploy_02）
- config/caddy 与 config/coturn 目录只有 .gitkeep 占位：仓库内不存在 Caddy/coturn/Chrome 策略配置文件，五服务正式 compose 与 TLS/TURN 属于未实施的 t012 范围，部署面当前只有明文 HTTP
- 四份 schemas 均为生成产物，手改 schemas 而不改生成源会被漂移测试发现；反之导出脚本覆盖的模型集合决定契约完备性（见 f_contracts_deploy_04）
- src/frontend/dist/ 被 .gitignore 排除、不入库，主镜像构建前必须先有前端构建产物（见 f_contracts_deploy_05）

## decisions

- v2 runtime 镜像采用白名单式 COPY 与（gateway/supervisor 的）专属 .dockerignore 缩小构建上下文；browser/stream/gateway 以非 root 用户（1000）运行
- 内部 RPC 不进公开 OpenAPI 契约（A17），改由三份协议 JSON 承担跨服务契约
- Selkies web 资源不用 CDN 运行时拉取，而是按固定哈希 vendoring 入仓并在镜像构建时强制校验

## evidence

- schemas/openapi/cbrowser_v1.json:1572-1985 路径与组件清单；与 src/backend/cbrowser/api/v1/*.py 路由的静态集合比对 29/29 无差异
- config/docker/Dockerfile:1-2 FROM cbrowser:latest；compose.yaml:5-9 输出镜像同名 cbrowser:latest
- compose.yaml:10-11 端口 0.0.0.0:${CBROWSER_PORT:-56661}:8080；src/backend/main.py:116,145,269 AUTH_TOKEN 为空时中间件放行（部署实际服务的 legacy 应用）
- src/backend/cbrowser/api/v1/auth_router.py 登录处理抛出 401/429；src/backend/cbrowser/api/v1/artifact_router.py:42,44,86 抛出 413/507；schemas/openapi/cbrowser_v1.json 中对应操作仅声明 200/422 与 201/422
- src/backend/cbrowser/stream_agent/protocol.py:154-171 ProtocolEnvelope.payload 为 dict[str, Any]；同文件 188-330 的 AgentRegisterPayload/RtcConfigPayload/IceServer 等类型化 payload 未被 scripts/export_stream_protocol.py:15-25 导出
- DOCKER_DEPLOYMENT.md:64-76 快速上手只有 cp 与 compose up 两步；config/docker/Dockerfile:11 COPY src/frontend/dist/；.gitignore 含 src/frontend/dist/ 且 git ls-files 无该路径
- tests/unit/test_domain_and_repository.py:530-545 OpenAPI 深比较漂移测试；tests/unit/test_supervisor_schema.py、test_stream_protocol_schema.py、test_runtime_agent_protocol_export.py 为协议导出对比测试
- config/selkies/selkies_web_sha256.txt 共 2007 条 sha256+相对路径记录，格式与 scripts/vendor_selkies_web.py:37-64 的 verify_manifest 消费方式一致
- git log 显示 schemas/ 与 src/backend/cbrowser/api/ 最近两次同提交变更（6d28f59、986d3e2），且 git 历史中从未提交真实 .env（git log --all -- .env 无记录）

## uncertainties

- schemas/openapi/cbrowser_v1.json（3612 行生成 JSON）与 config/selkies/selkies_web_sha256.txt（2007 行哈希清单）按 key 级覆盖：已核对全部路径/操作/组件/$defs 与清单格式，未逐行核对生成 JSON 的每个字段细节；字段级漂移由仓库自带深比较测试兜底（本次为静态审阅，未运行测试）
- cbrowser:latest 基础镜像的实际内容（基础 OS、预装内容、默认用户）不在仓库内，无法静态核对；仅能确认其不受版本/摘要固定且与产物同名
- supervisor 以 root 运行是否属硬需求（docker.sock + iptables）未见 Dockerfile 内注释说明，按 suspected 记录于 f_contracts_deploy_09
- 未验证 dist 构建产物与当前前端源码的一致性（dist 不入库，属 frontend 单元与构建流水线范围）

## Findings

- [High][88] config/docker/Dockerfile:1-2 — 生产镜像 FROM cbrowser:latest 自引用且未固定：基础镜像不在仓库内定义，构建不可复现
  - ID: f_contracts_deploy_01; verification: static
  - Evidence: config/docker/Dockerfile:2 为 `FROM cbrowser:latest`，注释自称 'based on verified cbrowser foundation'，但全仓没有任何 Dockerfile/脚本/compose 服务产出这个基础镜像; compose.yaml:5-9 把构建产物镜像也命名为 cbrowser:latest：同一 tag 既是输入又是输出，本机残留的旧镜像会被静默当作基础层; 干净环境构建时 Docker 会尝试从公共仓库拉取同名 cbrowser:latest（不受本项目控制的可变 tag），而 v2 四个 runtime 镜像均已做 digest 固定（python:3.12-slim-bookworm@sha256:e697c8…），唯独生产主镜像没有; docs/archive/spikes/s001 报告亦记载该基线只是'本机既有 cbrowser:latest 镜像'；docs/handoff.md:22 记载正在运行的 cbrowser:latest 是旧版 VNC 容器
  - Impact: 全新机器/CI 上部署结果取决于本机或公共仓库里碰巧存在的同名镜像：构建可能直接失败，也可能把过期或无关内容（包括其 root 默认用户与旧依赖）带入生产镜像，且无法审计基础层内容与来源。
  - Fix: 把基础镜像的构建定义收回仓库（多阶段构建或独立 foundation Dockerfile），FROM 改为带 digest 的公开基础镜像；compose 输出镜像改用独立版本化 tag，避免输入输出同名。

- [High][85] compose.yaml:10-17 — 默认部署无认证且绑定 0.0.0.0：AUTH_TOKEN 留空时局域网内任何人可完全控制 Manager
  - ID: f_contracts_deploy_02; verification: static
  - Evidence: .env.example:15-16 明示 AUTH_TOKEN 'Blank = open'，且文件给出的就是留空默认值；compose.yaml:17 透传 AUTH_TOKEN=${AUTH_TOKEN:-}（默认空）; compose.yaml:10-11 将端口发布到 0.0.0.0:${CBROWSER_PORT:-56661}，DOCKER_DEPLOYMENT.md:16-18 把局域网访问列为正式入口; 该镜像实际服务的 legacy 应用 src/backend/main.py:116,145,269 在 AUTH_TOKEN 为 None 时认证中间件整体放行；其路由包含 profiles 文件读写（浏览器 Cookies/下载文件）、POST /api/shutdown、POST /api/open-external 等高权限端点（main.py:851-993,1171,1220）
  - Impact: 按官方文档默认部署后，同一局域网的任何设备无需凭据即可读取各 Profile 的 Cookies 与文件、启停浏览器、调用关机/外部打开端点；对一款以隔离保存多账号会话为卖点的产品等于默认敞开全部身份数据。
  - Fix: 默认改为拒绝启动或强制生成/设置令牌（fail-closed），或至少默认只绑定 127.0.0.1 并在文档中把 0.0.0.0+空令牌标为不安全组合并给出告警；.env.example 不应以留空作为推荐默认。

- [Medium][92] schemas/openapi/cbrowser_v1.json:1572-1700; schemas/openapi/cbrowser_v1.json:1805-1900 — 导出的 OpenAPI 漏报已实现的错误响应：登录的 401/429 与 artifact 上传的 413/507 不在契约中
  - ID: f_contracts_deploy_03; verification: static
  - Evidence: 登录操作在 schema 中只声明 200/422，但 src/backend/cbrowser/api/v1/auth_router.py 的登录处理明确抛出 429（限流）与 401（凭据错误）; artifact 上传操作在 schema 中只声明 201/422，但 src/backend/cbrowser/api/v1/artifact_router.py:42,44,86 明确抛出 413（单文件超限）与 507（数量/总量超限）; .env.example:20-24 已把 413/507 写成对用户承诺的行为契约，说明这两个状态码是正式语义而非偶然实现细节; 全 schema 的响应码分布中 401 仅出现 1 次、429/413/507 完全缺失，而其他操作普遍声明了 404/409/503，属局部遗漏而非整体风格
  - Impact: 按契约生成的客户端（前端 generate:api 类型与任何外部集成方）无法预知登录失败/限流与上传超限的正式响应，错误处理只能靠猜测；契约深比较测试只能保证 schema 与 FastAPI 自动生成结果一致，掩盖了路由未声明 responses 的源头问题。
  - Fix: 在 auth_router 登录与 artifact_router 上传端点上显式声明 responses={401/429/413/507: ErrorResponse}，重新运行 scripts/export_openapi.py 更新契约，并让 .env.example 的 413/507 承诺与契约互相引用。

- [Medium][90] schemas/stream/agent_protocol.json:229-300 — Stream 线协议契约只覆盖信封：payload 为 dict[str, Any]，含 TURN 凭据的类型化 payload 全部不在导出契约内
  - ID: f_contracts_deploy_04; verification: static
  - Evidence: scripts/export_stream_protocol.py:15-25 只导出 ProtocolEnvelope、GatewayRegisterResponse、GatewayTunnelEnvelope、GatewayControlEnvelope 四个信封模型; src/backend/cbrowser/stream_agent/protocol.py:169 ProtocolEnvelope.payload 定义为 dict[str, Any]，导出的 schema 中 payload 相应为无结构对象; 同文件的 AgentRegisterPayload、SupervisorQuotaPayload、ICERestartOfferPayload/AnswerPayload、AgentHeartbeatPayload、RtcConfigPayload 与 IceServer（protocol.py:188-330）都是实际在线上传输的类型化模型，但均未进入 schemas/stream/agent_protocol.json 的 $defs; IceServer.credential 是 TURN 凭据（SecretStr），RtcConfigPayload 决定 relay_only 等安全语义——契约中最敏感、最需要跨实现对齐的部分恰好无 schema 约束
  - Impact: gateway 与 stream agent 两侧对 payload 的理解只能靠源码默契，任何一侧改字段都不会被契约测试发现；外部复现/审计该协议时无法从 schemas/ 得知 register/rtc_config/ice_restart 的真实报文形状。
  - Fix: 把 payload 按 action 的判别联合（discriminated union）建模或至少把上述 payload 模型一并加入 export_stream_protocol.py 的 TypeAdapter 集合并重新导出；漂移测试随之覆盖。

- [Medium][90] DOCKER_DEPLOYMENT.md:64-76 — 文档化的 Docker 快速上手在干净克隆上无法完成：缺少前端构建步骤且基础镜像无来源
  - ID: f_contracts_deploy_05; verification: static
  - Evidence: DOCKER_DEPLOYMENT.md:67-72 的全部步骤只有 `cp config/.env.example .env` 与 `docker compose up --build -d`; config/docker/Dockerfile:11 `COPY src/frontend/dist/ ...`，而 src/frontend/dist/ 被 .gitignore 排除、git ls-files 无记录，克隆后不存在；生成它需要前端 npm 构建与 Selkies vendoring（scripts/vendor_selkies_web.py），部署文档只字未提; 叠加 f_contracts_deploy_01：基础镜像 cbrowser:latest 同样不是该流程能产出的; 文档 3.2 节还提示用 `docker compose ps` 看'健康检查'，但 compose.yaml 与主 Dockerfile 均未定义任何 healthcheck
  - Impact: 新部署者按手册操作必然在构建阶段失败（缺 dist 或缺基础镜像），且文档没有给出排障路径；'可直接执行'的部署承诺与仓库事实不符。
  - Fix: 在 DOCKER_DEPLOYMENT.md 补齐前置步骤（前端构建 + vendor_selkies_web + 基础镜像来源/构建），或把这些步骤收进 Dockerfile 多阶段构建使 compose 一条命令真正自包含；删除无 healthcheck 支撑的表述或补上 healthcheck 定义。

- [Medium][82] DOCKER_DEPLOYMENT.md:9-30 — 部署文档把 legacy 单容器形态表述为'当前实际架构'，与 schemas/呈现的 v2 契约并存且无状态区分
  - ID: f_contracts_deploy_06; verification: static
  - Evidence: DOCKER_DEPLOYMENT.md:9 自称记录'当前 CBrowser 的实际容器化部署架构'，内容为单容器 + legacy /api/* + /api/health（:90）; schemas/openapi/cbrowser_v1.json 的 info.version 为 2.0.0、健康检查在 /api/v1/health；config/docker/ 下另有四个 v2 runtime 镜像，但 compose.yaml 完全不引用它们，config/caddy、config/coturn 只有 .gitkeep 占位; docs/tasks/t012_v2_docker_release/task.md 表明五服务正式 compose、Caddy/coturn 配置与完整部署文档是未实施的未来任务；docs/handoff.md:22 亦确认 v2 栈未运行; 文档未在任何位置标注'当前为 legacy 形态、v2 部署待 t012'的状态说明（文档规范的三态划分缺失）
  - Impact: 读者无法判断部署时应以哪套契约/镜像为准：按 schemas 与 v2 镜像准备会发现没有编排入口，按部署文档操作得到的却是没有 /api/v1 的旧应用；两套事实互相矛盾且都不声明状态。
  - Fix: 在 DOCKER_DEPLOYMENT.md 开头加状态段：当前正式部署=legacy 单容器（对应 legacy API），v2 五服务部署未落地（指向 t012 与 blueprint）；schemas 的 README/索引位置同步标注 v2 契约的生效状态。

- [Low][95] config/.env.example:1-4 — .env.example 根目录与 config/ 两份逐字节重复，且 config 份的复制说明指向错误位置；compose 的两个用户旋钮未进示例
  - ID: f_contracts_deploy_07; verification: static
  - Evidence: 根 .env.example 与 config/.env.example 内容完全相同（均为 25 行 1201 字节），双份维护必然漂移; config/.env.example:2-3 写 'Copy this file to .env (in this same directory)'，照做会生成 config/.env；但 compose 的变量插值与 DOCKER_DEPLOYMENT.md:67 用的都是仓库根 .env（cp config/.env.example .env），src/backend/env_file.py 的默认查找路径也不是 config/ 目录; compose.yaml:11,15 暴露给用户的 CBROWSER_PORT、CBROWSER_DATA_DIR 两个变量在两份 .env.example 中均未出现、无默认值说明
  - Impact: 用户按 config 份文件头说明操作会把配置放到无人读取的位置，表现为'改了配置不生效'；两份示例后续修改易只改一份造成契约分叉。
  - Fix: 只保留一份权威 .env.example（根目录），config/ 份改为指针说明或删除；把 CBROWSER_PORT、CBROWSER_DATA_DIR 补进示例并注明 compose 专用。

- [Low][90] schemas/openapi/cbrowser_v1.json:1986-3612 — OpenAPI 契约未声明任何 securityScheme，认证/CSRF 要求对契约消费者不可见
  - ID: f_contracts_deploy_08; verification: static
  - Evidence: 导出的 components 中 securitySchemes 为空对象，全文无顶层或操作级 security 字段; 实际 v1 profile 路由挂有会话认证与 Depends(require_csrf_and_origin)（src/backend/cbrowser/api/v1/router.py:56），登录/会话端点也表明存在 cookie 会话机制; 内部 RPC 被有意排除在 schema 外（A17），但公开 API 自身的认证方式同样没有以 securityScheme 形式留下契约
  - Impact: 用该 schema 生成的客户端/SDK 不会携带认证与 CSRF 头信息，集成方只能逆向源码或前端代码才知道如何调用受保护端点；契约作为'公开接口说明书'不完整。
  - Fix: 在 FastAPI app 上注册会话 cookie / bearer 的 security scheme 并给受保护路由加 security 依赖声明，重新导出；或在契约旁注文档中明确声明认证不由 OpenAPI 描述及其权威位置。

- [Low][70] config/docker/supervisor_runtime/Dockerfile:1-25 — supervisor 镜像以 root 运行且未注明特权需求，主镜像同样继承 root 默认用户
  - ID: f_contracts_deploy_09; verification: suspected
  - Evidence: supervisor_runtime/Dockerfile 全文无 USER 指令，ENTRYPOINT 直接以 root 启动控制服务；同文件还安装 iptables 并复制 supervisor/domain/gateway/runtime_agent 四个包; 对照同仓 gateway/browser/stream 三个 runtime 镜像均显式切换到 UID 1000 非 root 用户，supervisor 是唯一例外且 Dockerfile 内无任何注释解释; 主生产镜像 config/docker/Dockerfile 同样无 USER，其基础镜像 cbrowser:latest 的默认用户经 t013 评审证据确认为空（root）; supervisor 确实可能需要 docker.sock 与网络管理权限，但'需要挂载 docker.sock'与'进程必须 root'并非同一件事，文件未做区分说明
  - Impact: 持有 docker.sock 的 root 进程一旦被攻破即等价宿主机 root；缺少特权需求说明使部署者无法做最小权限评估，也使后续收敛权限时无据可依。
  - Fix: 在 Dockerfile 注释中写明所需 capability/挂载与为何需要 root；可拆分时让控制 HTTP 服务以非 root 运行、仅特权操作走窄接口；主镜像在基础镜像收回仓库后显式设置 USER。

- [Low][85] config/docker/stream_runtime/Dockerfile:1-59 — browser/stream/主镜像缺少 .dockerignore，构建上下文包含 .env 与 .git，与 stream 指南的上下文声明不符
  - ID: f_contracts_deploy_10; verification: static
  - Evidence: 全仓只有 gateway_runtime 与 supervisor_runtime 有专属 Dockerfile.dockerignore（find 结果共 2 个生产用），browser_runtime、stream_runtime 与 config/docker/Dockerfile 均无，仓库根也没有 .dockerignore; 以仓库根为上下文构建时，本地 .env（.gitignore 排除但磁盘存在）、.git、docs、tests 等全部发送给 daemon；当前 COPY 均为显式路径，暂未把秘密带入镜像层，但任何后续 COPY . 都会直接泄漏; docs/guides/stream_runtime_validation.md:8 声称'Stream 构建上下文只包含 Dockerfile、entrypoint、__init__.py 和 stream_agent 包'，在缺少 stream 的 .dockerignore 时该声明并不成立
  - Impact: 构建变慢且秘密文件进入构建上下文的攻击面长期存在；文档声明与实际隔离强度不一致，审计者会高估供应链卫生。
  - Fix: 按 gateway/supervisor 的白名单模式为 browser_runtime、stream_runtime 与主 Dockerfile 补齐 Dockerfile.dockerignore，至少排除 .env、.git、.scratch、数据目录。

- [Low][65] scripts/vendor_selkies_web.py:104-152 — Selkies 资源解包无路径穿越防护且清单校验不拒绝未列出的额外文件
  - ID: f_contracts_deploy_11; verification: suspected
  - Evidence: extract_from_wheel:118-126 直接以 zip 条目名拼 dest_dir / rel 写盘，未校验 rel 是否含 '..' 或绝对路径；extract_from_stream_image:135-152 对 tar member.name 同样直接拼路径; verify_manifest:37-64 只逐条核对清单内文件的存在与哈希，目标目录中存在清单外文件不会报错（verify_frontend_dist 的 allow_patched 路径同样只查清单内文件）; wheel 策略在解包前有固定 SHA-256 校验，降低了 wheel 路径的风险；但 --image 策略从本地镜像取 tar 流，无哈希校验，校验环节又只看清单内文件
  - Impact: 若所用镜像/wheel 来源被污染，解包可写出 dest_dir 之外的路径，或在 dist 中留下清单外的额外脚本而不被构建校验发现，绕过'固定哈希 vendoring'的完整性承诺。
  - Fix: 解包时拒绝含 '..'/绝对路径的条目名并断言最终路径位于 dest_dir 内；verify_manifest 增加'目录文件集合与清单集合相等'检查（index.html 补丁备份等白名单除外）。

- [Info][88] config/docker/browser_runtime/requirements.txt:1-39 — 四份 requirements.txt 只锁版本不锁哈希，pip 未启用 --require-hashes
  - ID: f_contracts_deploy_12; verification: static
  - Evidence: browser/gateway/stream/supervisor 四份 requirements.txt 均为 name==version 形式，无 --hash 条目，各 Dockerfile 的 pip install 也未加 --require-hashes; 对照同仓对 Selkies wheel 与基础镜像 digest 的严格固定，Python 依赖这一层的完整性强度明显低一档
  - Impact: 同一版本 artifact 在仓库端被替换时构建不会察觉；与项目其他环节的供应链固定标准不一致。
  - Fix: 用 pip-compile --generate-hashes 重新生成四份 requirements.txt 并在 Dockerfile 中启用 --require-hashes，或在文档中明确接受版本级固定的风险决定。

- [Info][85] config/docker/stream_runtime/Dockerfile:16-41 — stream 最终镜像保留完整编译工具链（build-essential 与多个 -dev 包），无多阶段剥离
  - ID: f_contracts_deploy_13; verification: static
  - Evidence: stream_runtime/Dockerfile 为单阶段构建，apt 安装 build-essential、libx11-dev、libpulse-dev、libgstreamer*-dev 等开发包后直接作为最终镜像运行; 同仓 browser_runtime 镜像用多阶段把 test_mitshm 的编译隔离在 builder 阶段，证明团队有此模式，stream 未采用
  - Impact: 最终镜像体积与攻击面增大（编译器可被利用于容器内现场编译恶意代码），且与 browser 镜像的构建卫生标准不一致。
  - Fix: 把原生扩展编译拆到 builder 阶段，最终阶段只拷贝运行时库与已构建产物；或记录保留工具链的具体理由。

## views

```json
{
  "contracts": {
    "reviewer": "ade21d2b-0c90-4cad-b497-96a6914d1221",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "ade21d2b-0c90-4cad-b497-96a6914d1221",
    "status": "completed"
  },
  "design": {
    "reviewer": "ade21d2b-0c90-4cad-b497-96a6914d1221",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "ade21d2b-0c90-4cad-b497-96a6914d1221",
    "status": "completed"
  },
  "performance": {
    "reviewer": "ade21d2b-0c90-4cad-b497-96a6914d1221",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "ade21d2b-0c90-4cad-b497-96a6914d1221",
    "status": "completed"
  },
  "security": {
    "reviewer": "ade21d2b-0c90-4cad-b497-96a6914d1221",
    "status": "completed"
  },
  "tests": {
    "reviewer": "ade21d2b-0c90-4cad-b497-96a6914d1221",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  ".env.example",
  "DOCKER_DEPLOYMENT.md",
  "compose.yaml",
  "config/.env.example",
  "config/docker/Dockerfile",
  "config/docker/browser_runtime/Dockerfile",
  "config/docker/browser_runtime/entrypoint.sh",
  "config/docker/browser_runtime/requirements.in",
  "config/docker/browser_runtime/requirements.txt",
  "config/docker/entrypoint.sh",
  "config/docker/gateway_runtime/Dockerfile",
  "config/docker/gateway_runtime/Dockerfile.dockerignore",
  "config/docker/gateway_runtime/requirements.in",
  "config/docker/gateway_runtime/requirements.txt",
  "config/docker/stream_runtime/Dockerfile",
  "config/docker/stream_runtime/entrypoint.sh",
  "config/docker/stream_runtime/requirements.in",
  "config/docker/stream_runtime/requirements.txt",
  "config/docker/supervisor_runtime/Dockerfile",
  "config/docker/supervisor_runtime/Dockerfile.dockerignore",
  "config/docker/supervisor_runtime/requirements.in",
  "config/docker/supervisor_runtime/requirements.txt",
  "config/selkies/selkies_web_sha256.txt",
  "schemas/openapi/cbrowser_v1.json",
  "schemas/runtime/agent_protocol.json",
  "schemas/runtime/supervisor_protocol.json",
  "schemas/stream/agent_protocol.json",
  "scripts/export_openapi.py",
  "scripts/export_runtime_agent_protocol.py",
  "scripts/export_stream_protocol.py",
  "scripts/export_supervisor_protocol.py",
  "scripts/vendor_selkies_web.py",
  "scripts/verify_frontend_dist.py"
]
```

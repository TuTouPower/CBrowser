# bundle_global_system_properties

## Summary

At HEAD 5136766 this repository contains two systems with opposite property profiles, and only the worse one is real. The deployed system — the only compose file in the repo (root compose.yaml), whose entrypoint execs the legacy backend.main:app — is a single container published on 0.0.0.0:56661 with AUTH_TOKEN defaulting to blank, a state in which the legacy auth layer passes every request through (src/backend/main.py:145). For an application whose entire purpose is holding logged-in browser identities, the default deployment therefore hands any LAN peer full control (profile cookies/files, launch/stop, /api/shutdown, /api/open-external) with no credential at all, persists clipboard contents to manager.log despite its own diagnostics promising the opposite, and sits behind a launch-argument sanitizer that is a penetrable prefix blacklist. The intended v2 system (Argon2 session auth + CSRF/Origin, file-based secrets, supervisor fencing/spool recovery, digest-pinned runtime images) is genuinely better engineered at component level, but it is not deployable from this repo at this HEAD: no shipped artifact wires its five services together (the only compose file is the legacy one), t010/t011/t012 are unfinished, and even v2 carries live defects (supervisor reconcile crash-loop, gateway heartbeat eviction, wedged ICE restart) that cap its availability below its design claims. Around both stacks, the delivery system cannot currently detect its own breakage: CI references pre-reorganization paths in both jobs and runs nothing, the Docker-heavy E2E layers skip silently when image env vars are absent (CI never supplies them), frontend E2E tests whatever stale dist happens to be on disk, security-negative assertions are sleep-based, and this review's principal defects have zero regression coverage in four independently-checked units. Operability compounds this: the production image builds FROM an undefined, self-tagged cbrowser:latest, release.yml points at deleted packaging scripts and a nonexistent root Dockerfile, the documented quickstart cannot complete from a clean clone, and the repo's own status surfaces (an effective spec claiming an unimplemented migration as delivered with its AC checked, blueprint 'current truths' contradicting ADRs/code, a CHANGELOG frozen before v2, gate commands hardcoding one developer's home paths) diverge from reality in at least four independently verified places — so neither the software nor its operators can presently know the system's true state. Privacy follows the same split: the running product leaks user clipboard data into logs and retains DataChannel input payloads in page memory, while the public fork permanently publishes the developer's machine paths and session traces. Verdict on properties as they ARE: security posture of the default deployment is unacceptable for the product's purpose; reliability is single-container with a silent data-loss upgrade hazard; detectability is near zero; the v2 design shows these properties are achievable, but none of its guarantees are in force today.

## Findings

- [Critical][90] compose.yaml:6-17; config/docker/entrypoint.sh:27; src/backend/main.py:145,1171-1172,1220-1222 — 默认部署即无认证的局域网远程控制面：唯一可部署形态把身份存储应用的全部控制权开放给同网段任何主机

    - ID: f_global_system_properties_01; verification: static
    - Evidence: compose.yaml 是全仓唯一的 compose 文件：单服务 cbrowser，端口发布 0.0.0.0:${CBROWSER_PORT:-56661}:8080，环境 AUTH_TOKEN=${AUTH_TOKEN:-}（默认空）; config/docker/entrypoint.sh:27 实际执行 uvicorn backend.main:app——部署现实是 legacy 栈，v2 的 Argon2/CSRF/Origin 认证不在运行路径上; src/backend/main.py:145 \_check_auth 在 AUTH_TOKEN 为 None 时对所有请求返回 True；f_contracts_deploy_02 与 f_backend_core_05 两个单元独立得出同一结论; 无认证可达的后果面包括 profile 的 Cookie/文件、launch/stop，以及 POST /api/open-external（main.py:1171）与 POST /api/shutdown（main.py:1220）; 叠加项：SPA catch-all 路径穿越经定向精查静态确认可达（followup_q_system_properties_02：uvicorn 解码 %2e%2e%2f 入 scope、Starlette 不折叠点段、serve_spa 无 resolve/包含校验），按生产镜像布局可读 ../../backend/main.py、../../../etc/passwd 及数据卷文件等 frontend/dist 之外文件（f_backend_core_01，精查确认见 followup_q_system_properties_02）；launch 参数清洗为可穿透前缀黑名单（f_backend_runtime_adapters_01）；剪贴板正文进日志（f_backend_core_02）; README.md:40 把 AUTH_TOKEN 写成可选项（『若配置了 AUTH_TOKEN』），快速上手路径不提示必须设置；且不存在任何受支持的 v2 部署路径可供用户改选（全仓无第二个 compose 文件，t012 未完成）
    - Impact: 按文档默认方式部署后，同一局域网（咖啡店/公司/宿舍网络、被攻陷的同网设备）中的任何主机无需任何凭据即可读取全部浏览器身份的登录态与文件、操控浏览器实例、关闭 Manager。用户无法通过选择『正确』部署形态规避：仓库当前只提供这一种部署形态。这是该隐私隔离产品核心价值的直接反面。
    - Fix: 前提：先决定 legacy 栈的存续（t011）。可执行方向：(1) compose 默认将端口绑定 127.0.0.1，绑定 0.0.0.0 必须显式 opt-in；(2) AUTH_TOKEN 为空时 legacy 应用拒绝启动或仅监听回环，删除『空=开放』语义，README 同步改为必填并给出生成方式；(3) 在 t012 完成前，部署文档顶部明确标注当前唯一部署形态的安全边界；(4) serve_spa 穿越已由 q_system_properties_02 精查静态确认可达，随同一批修复一并处置（resolve 后包含校验或改走 StaticFiles)。

- [High][92] config/docker/Dockerfile:1-2; compose.yaml:6-9; .github/workflows/release.yml; docs 快速上手（f_contracts_deploy_05） — 发布与升级链断裂：从干净克隆出发不存在一条可走通的构建/发布/升级路径，产物不可复现、无回滚语义

    - ID: f_global_system_properties_02; verification: static
    - Evidence: config/docker/Dockerfile:1-2 为 FROM cbrowser:latest：基础镜像在仓内无任何定义、无 digest 钉版（f_contracts_deploy_01）；compose.yaml:6-9 又把构建产物打上同一 tag cbrowser:latest，自引用闭环——干净机器构建失败或静默用本机残留的同名旧镜像; release.yml 三个原生安装包 job 引用已按架构决定删除的 packaging/ 脚本，release job 依赖它们，打 v\* tag 走不到建 Release；两处 build-push-action 未指定 file:，默认根目录 Dockerfile 不存在（f_repo_ops_02、f_repo_ops_03）; 文档化的 Docker 快速上手在干净克隆上无法完成：缺前端构建步骤且基础镜像无来源（f_contracts_deploy_05）; 与之对照，v2 runtime 镜像为 digest 钉版、依赖版本锁定、release 侧有 manifest 回读校验——能力存在，但只覆盖未接管部署的组件
    - Impact: 任何人（包括作者在新机器上）无法从仓库重建出当前部署的产物；『升级』只能是原地覆盖同一 tag，回滚无定义；一旦现有机器上的 cbrowser:latest 基础镜像丢失或被污染，部署不可恢复。发布 tag 流程必然失败且失败点在流程深处。
    - Fix: 前提：t012 正式发布任务落地或先行最小修复。可执行方向：(1) 把基础镜像的构建定义纳入仓库并 digest 钉版，产物 tag 与基础 tag 分名；(2) release.yml 删除已废弃的原生安装包 job、为 Docker 构建显式指定 file: config/docker/Dockerfile；(3) 在 CI 中加一条干净环境 quickstart 冒烟（clone→按 README 构建→健康检查），让文档路径本身成为被测对象。

- [High][95] .github/workflows/ci.yml:21-36; tests/e2e（env 门控）; docs/blueprint/testing.md:34-58 — 可探测性属性缺失：门禁系统性静默变绿，本仓目前无法知道自己何时坏掉

    - ID: f_global_system_properties_03; verification: static
    - Evidence: CI 两个 job 全部引用重组前路径（backend/requirements.txt、frontend 工作目录与 package-lock），根 pyproject 三处 testpaths 一处未覆盖——两个单元独立确认仓库实际无 CI 门禁（f_repo_ops_01、f_frontend_shell_02；本审阅亦直查 ci.yml:21-36 属实）; supervisor 与 stream 两组 E2E 以 CBROWSER\_\*\_TEST_IMAGE 等环境变量缺失即 pytest.skip 为前提，CI 从不提供这些变量，整层可零覆盖报绿（f_tests_e2e_supervisor_01、f_tests_e2e_stream_frontend_01，均为 High）; 前端 E2E 从不构建、直接消费磁盘上既有的 gitignored dist，源码变更后可对着过期产物全绿（f_tests_e2e_stream_frontend_02）; 安全负断言靠固定 sleep 后查状态（0.05–0.1s），回归可真空通过（tests_unit_stream_api Medium 簇）；本轮四个 viewfix 单元一致结论：各单元的主要生产缺陷（对账异常隔离、serve_spa、清洗器穿透、/health 阻塞、ICE restart_pending 楔死、心跳单 try、信令无代次分支）全部没有能抓住它们的回归测试（f_backend_core_18、f_backend_runtime_adapters_18、f_backend_supervisor_14、f_backend_stream_gateway_18/19）; 权威门禁命令把开发者个人路径写死为 TMPDIR（docs/blueprint/testing.md:34-58），换机器照抄即失败——门禁连『按文档运行』这一层都不成立; 集成夹具与生产分叉（SupervisorGatewayFixture 的 visibility 语义与生产 Gateway 不同，f_tests_integration_fixtures_01；tab 仲裁测的是已与生产分叉的 web_lock_shim），部分绿灯证明的是替身而非系统
    - Impact: 测试资产总量大且多为行为级，但作为『系统健康信号』的属性已失效：绿灯与系统完好之间无可靠关联。本轮 21 条 High 中多条能在现有测试下长期存续，正是这一属性的实证。对一个单人维护、以文档门禁为流程核心的项目，这是所有其他缺陷得以积累的机制性原因。
    - Fix: 前提：承认门禁目标是『红绿可信』而非『测试数量』。可执行方向：(1) 先修 ci.yml 到当前布局，让每次 push 至少跑单元+契约层；(2) E2E 的 env 门控改为分层显式标记并在 CI 汇总中单独报告 skipped 数，关键层 skip 即黄灯；(3) 前端 E2E 前置构建步骤或校验 dist 与源码的 hash 一致；(4) 安全负断言改事件驱动等待（等到已处理信号再断言状态未变）；(5) testing.md 门禁命令去个人路径，改仓内相对 .scratch 路径。

- [High][93] docs/specs/storage_and_artifacts.md:25-29; docs/blueprint/persistence.md:42,73; CHANGELOG.md; src/backend/main.py 剪贴板日志（f_backend_core_02） — 状态面失真：仓库对自身的四处关键叙述与代码/决策相互矛盾，按文档运维必然得到错误前提

    - ID: f_global_system_properties_04; verification: static
    - Evidence: 生效 spec 把 t010 才交付的旧库迁移工具写成已交付行为且 AC-002 已勾选通过，而 v2 代码内无任何迁移工具、ADR 008 明言迁移归 t010（f_docs_current_01，High）; blueprint 自称『当前长期真相』，但 failure_count 阻断阈值仍写 >=3（ADR/代码/spec 均为第 4 次），runtime_events 级联删除口径与已落地的 D1 决策相反（docs_current Medium）; 部署文档把 legacy 单容器形态表述为『当前实际架构』，与 schemas/ 呈现的 v2 契约并存且无状态区分（f_contracts_deploy_06）；CHANGELOG 停在 v2 重构之前的 0.1.9; diagnostics 宣称绝不记录剪贴板内容，实际代码把剪贴板正文写入 manager.log（f_backend_core_02）——连运行时自述（日志策略）都是假的; 本仓工作流以文档为权威驱动（仓根 AGENTS.md 要求写代码前读 blueprint 作为当前真相），失真文档会直接转化为错误实现与错误运维决策
    - Impact: 运维者与后续 agent 会基于错误前提行动：以为迁移工具存在而直接升级 legacy 数据、以错误阈值判断阻断行为、以『当前架构』文档排查错误的一套栈、以日志脱敏承诺判断泄漏面。三态纪律（当前/过时/未来分离）正是本仓自设的规矩，此处是成串的自违。
    - Fix: 可执行方向：(1) 立即修订 storage_and_artifacts.md 的迁移段落为未实施状态并取消 AC 勾选，或把该 spec 降级标注为目标态；(2) blueprint 两处按 ADR 008/D1 就地改正，并给 blueprint 增加『与代码冲突时以何为准』的显式声明；(3) 部署文档与 CHANGELOG 补 v2 状态分界（哪套在跑、哪套未交付）；(4) 把『spec 声称已交付』纳入收尾检查：AC 勾选必须能指向代码路径。

- [High][90] src/backend/main.py:1301,1399（f_backend_core_02）; src/frontend adapter.ts:77-95（frontend_features） — 运行期隐私泄漏为默认行为：剪贴板正文落盘日志、会话输入报文在页面内存中全量留存

    - ID: f_global_system_properties_05; verification: static
    - Evidence: legacy 后端在剪贴板 SET 与 GET 两处把正文前 60 字符以 INFO 级写入轮转的 manager.log（f_backend_core_02，置信 95，static）；剪贴板是密码/一次性验证码的典型中转通道，该日志随 /data 卷持久化; 同一产品的 diagnostics 模块明文承诺不记录剪贴板内容，说明这是实现与自身隐私契约的背离而非设计取舍; v2 前端 adapter.ts 把全部 DataChannel 发送报文原文存入 window.\_\_sentDataChannelMessages（上限 500 条、无通道过滤），其中包含远端会话的键入/剪贴板类输入，扩大敏感输入在 iframe 内存中的留存与可读面（frontend_features Medium）; 剪贴板测试只断言 HTTP 结果，对日志安全性无任何断言，该泄漏在测试下可任意存续（f_backend_core_17）
    - Impact: 一个以隐私隔离为卖点的产品，在默认部署下把用户最敏感的瞬时数据（剪贴板）写进持久日志；任何能读日志的人（或日志被打包进诊断/反馈材料时）即获得凭据片段。前端侧的报文留存则使任一能执行页面脚本的上下文可回读近期全部输入。
    - Fix: 可执行方向：(1) 删除两处剪贴板正文日志，改为仅记录长度/方向/结果，并补一条日志内容断言测试（canary 字符串不得出现在日志中）；(2) adapter 的报文记录改为默认关闭的显式调试开关，开启时过滤输入类通道；(3) 全仓 grep 同类『正文进日志』模式（代理 URL、token、表单字段）做一次性清查。

- [Medium][88] compose.yaml:3-23; src/backend/database.py（f_backend_core_06）; supervisor 对账（f_backend_supervisor_01）; gateway 心跳/ICE（f_backend_stream_gateway_02/03） — 可用性剖面：运行系统是单容器单点且升级可静默丢数据；被精心设计的恢复语义属于未部署的栈且自身仍有单点

    - ID: f_global_system_properties_06; verification: static
    - Evidence: 部署形态为单服务单容器（compose.yaml），restart: unless-stopped 之外无健康检查、无冗余；进程级故障即全量不可用，恢复语义只有『容器重启后 legacy 应用自行起来』; legacy database.py 按列集差异自动重建表、只复制相交列，旧表含新列集外列时静默丢弃且该方向零测试（f_backend_core_06、f_backend_core_19）——升级动作本身构成数据丢失通道，profiles.db 里是用户全部身份配置; 运行时 /health 在 async handler 内同步跑 subprocess+HTTP 探活，最坏阻塞事件循环数秒，连健康信号本身都会拖住业务面（f_backend_runtime_adapters_02）; v2 的恢复设计（事件 spool、实例围栏、2/10/30 退避）不在运行路径上；且 v2 自身仍有可用性单点：对账循环无 per-profile 异常隔离，一个遗留容器可使 Supervisor 启动崩溃循环（f_backend_supervisor_01）；心跳循环单 try 包裹全程，任一瞬时错误永久停跳、健康 Agent 被误驱逐（f_backend_stream_gateway_02）；ICE restart 失败后 restart_pending 永不复位、轮换永久楔死（f_backend_stream_gateway_03）；RTC 时序参数无有限性/次序校验，一个 env 错值可使网关离线或轮换静默失效（f_backend_stream_gateway_04）
    - Impact: 今天部署的系统可用性上限就是单容器进程的存活，且最危险的时刻是升级（静默丢列）。即使明天切换到 v2，其恢复故事也会被上述三个单点封顶：单个坏 profile 拖垮全部会话恢复、单次瞬时错误断开全部 viewer、单次轮换失败永久关闭轮换。两代系统的可用性都低于其文档给人的印象。
    - Fix: 前提：先处置 f_01 的部署形态决策。可执行方向：(1) legacy 自动重建表改为显式迁移脚本+重建前备份，重建丢列时报错中止而非静默继续；(2) v2 三个单点按单元 fix 逐项收敛（对账 per-profile 隔离、心跳 per-iteration try、restart_pending 失败复位、RTC 参数启动期校验 fail-fast）；(3) compose 增加 healthcheck 并把 /health 探活移出事件循环。

- [Medium][87] src/backend/main.py:116,551-558; v2 auth（f_backend_api_auth_01/02）; schemas stream 契约（f_contracts_deploy_04）; .repo_template/scripts/repo_task/view_server.py:49-56 — 秘密生命周期呈双轨制：运行轨是永不过期的单点万能令牌，严格轨未在运行且自身留有放大与错位

    - ID: f_global_system_properties_07; verification: static
    - Evidence: legacy 侧：AUTH_TOKEN 同时是登录口令、cookie 值与 Bearer 凭据（main.py:551-558 把令牌原文写入 cookie，httponly+samesite=strict，但 secure 仅在反代声明 https 时置位，而文档部署为明文 HTTP），无过期、无轮换、无按客户端区分——令牌一泄即全权且无法单独吊销; v2 侧纪律明显更好（secret 文件 0600+最小长度、compare_digest、内部 RPC 分钥），但：被拒的自动化授权每次都写一条审计 DB 行，未认证请求可放大为无界 DB 写入（f_backend_api_auth_01）；supervisor 上报端点自身无鉴权、授权完全取决于 router 挂载位置（f_backend_api_auth_02）；TURN 凭据走 stream 线协议的 payload，而导出契约里 payload 只是 dict[str, Any]，凭据流向不在契约视野内（f_contracts_deploy_04）; 工具链侧：任务看板把会话 token 嵌进未鉴权首页 HTML，--allow-non-loopback 时 task 正文实际无访问控制（template_scripts_state，view_server.py:49-56）; 模板状态机的账本在读 OSError 时静默返回空事件列表，attempt 号从 1 重新分配，破坏其自身 fail-closed 不变量（f_template_scripts_state_01，High）——流程秘密/状态的完整性同样受影响
    - Impact: 系统没有统一的秘密姿态：跑着的那套是『一个永不过期的万能钥匙』，设计严格的那套既未运行、也还有未认证写放大与挂载位置即边界的脆弱点。任何按组件逐个看的结论（『v2 秘密处理合格』）都会高估整系统的实际姿态。
    - Fix: 可执行方向：(1) legacy 若续命，至少给令牌加文档化的轮换步骤并在 README 标注其万能属性，或在 compose 层强制要求设置（与 f_01 联动）；(2) v2 审计写放大改为限速/聚合计数，supervisor 上报端点在 handler 内显式校验其专属凭据、不依赖挂载；(3) stream 契约把含 TURN 凭据的 payload 类型化并声明其保密要求；(4) 看板 token 改为仅回环免鉴权、非回环必须校验且不进 HTML。

- [Medium][90] docs/archive/handoff.md（32 处本机绝对路径）; docs/blueprint/testing.md:34-58; docs/archive/spikes（f_archive_spikes_01/02/03） — 公开仓的隐私与卫生剖面：开发者机器布局与操作痕迹随 fork 永久公开，归档区含可执行的关鉴权代码

    - ID: f_global_system_properties_08; verification: static
    - Evidence: 归档 handoff 全文含 32 处开发者本机绝对路径（<home>/kar/code/...），并遍布 OpenCode session id、PID 等运维标识；仓库源头是公开 fork，归档随仓公开（archive_tasks Low）; 权威门禁命令把同一开发者的个人目录写死进 docs/blueprint/testing.md:34-58，当前文档同样在公开面暴露本机目录结构（与 f_03 的可运行性问题同源）; 归档 spike 代码含关闭 X11/PulseAudio/Selkies 访问控制的容器入口与可变更 live 媒体会话的无认证控制面（f_archive_spikes_01/02）——作为历史是记录，作为可运行代码被任何人（含照仓文档工作的 agent）执行即是现行风险; 归档 harness 曾把 live secret 写进自身源码目录且那些路径未被 gitignore（f_archive_spikes_03）；q_system_properties_01 定向精查已核：三个 harness 写出文件在当前树与全部可达 git 历史中均出现 0 次，其余凭据形状命中均为占位符、fixture 哨兵、弱测试词或运行时派生表达式——无真实 secret 值已入库，前瞻性风险未实际发生（followup_q_system_properties_01，refuted）
    - Impact: 开发者本机用户名、目录布局、工作节奏（session/PID 痕迹）对任何克隆者可见，为针对性攻击提供素材；归档中的关鉴权入口若被误当现行参考运行，会直接产生无认证的远程桌面/控制面暴露。原设『q_01 若证实有真实 secret 值入库则升级为 High』的条件已由精查否定（refuted）：secret 值升级路径关闭，本项维持 Medium。
    - Fix: 可执行方向：(1) 对已公开历史做一次定向清查（路径/标识/secret 值三类），路径类做文档层替换（仓库内统一用相对路径与占位符），已泄漏的真实凭据按已泄漏处理（轮换而非仅删文件）；(2) 归档 spike 的可执行入口加显式『归档、勿运行』头注或剥离可执行位与入口脚本；(3) 模板层加一条提交前检查：绝对家目录路径与 secret 形状值拦截（pre-commit 已有基建可扩展）。

- [Info][85] src/backend/cbrowser/（supervisor/gateway/runtime）; schemas/; config/docker/\*\_runtime/ — 正面属性记录：v2 组件级工程质量足以支撑目标姿态，缺口在接线与完成度而非设计

    - ID: f_global_system_properties_09; verification: static
    - Evidence: v2 核心的实例围栏、OperationJournal 幂等、事件 spool+去重、2/10/30 退避与第 4 次阻断经多单元交叉核对与契约基本一致，且归档中有真实 Docker E2E 证据链; 契约面扎实：OpenAPI 路由与实现 29/29 对齐、三份协议 schema 与生成脚本逐字一致且有漂移守卫；v2 runtime 镜像 digest 钉版+版本锁定、除 supervisor（有据）外非 root; 前端 v2：i18n 291/291 键对齐、生成类型与 OpenAPI 路径集 22/22 无漂移、postMessage 双向 origin+source 校验、无 XSS sink; 归档纪律总体良好（t001–t008/t013 的 AC、处置表、handoff 链完整可核），问题集中在少数假闭环（p011）
    - Impact: 判断校准：本系统的目标属性（认证、隔离、恢复、契约一致性）在 v2 设计与大部分实现中已经成立，f_01–f_08 的修复路径主要是完成迁移接线、修门禁、改默认值，不需要推倒重来。把资源投向 t010/t011/t012 的收尾与门禁可信度，收益大于继续在任一栈上加功能。
    - Fix: 无直接修复项；作为其余 findings 的处置前提引用：优先完成迁移与发布链（t010/t011/t012），而非扩功能面。

## questions

```json
[
  {
    "counterevidence": "扫描仅命中占位符/示例值，或写出路径从未被提交（文件不在任何可达提交中）——则 f_08 维持 Medium 的卫生问题定性，不升级",
    "evidence_needed": "对 spike 目录及 git 历史做凭据形状扫描（只报位置/种类/计数，不抄值）：命中文件、所在提交、当前 .gitignore 是否覆盖 harness 的写出路径",
    "id": "q_system_properties_01",
    "question": "docs/archive/spikes 下是否已有真实 secret 值（而非占位符/运行时生成）进入当前工作树或可达 git 历史？f_archive_spikes_03 只证实 harness 会把 live secret 写进未被 gitignore 的源码目录，未核对实际落盘内容。",
    "units": [
      "archive_spikes"
    ]
  },
  {
    "counterevidence": "框架在进 handler 前已折叠穿越段，或 FileResponse/静态层实际拒绝越界路径——则 f_01 的文件读取分量撤销（其无认证控制面结论不依赖此项，仍然成立）",
    "evidence_needed": "锁定依赖版本（pyproject/requirements 中的 fastapi/starlette 版本）、该版本对 full_path 的解码/规范化行为、catch-all 路由的注册顺序与 FileResponse 是否做 resolve 后包含校验",
    "id": "q_system_properties_02",
    "question": "f_backend_core_01 的 SPA catch-all 路径穿越在随仓发布的 FastAPI/Starlette 版本下是否真实可达？框架在路由前对 %2e%2e、..%2f 等编码段的规范化行为决定该疑点成立与否。",
    "units": [
      "backend_core"
    ]
  },
  {
    "counterevidence": "存在这样一条完整且与当前代码一致的拉起路径——则『v2 不可部署』修正为『v2 可部署但未文档化/未受门禁覆盖』，f_01 中『无从选择安全部署形态』的分量相应下调",
    "evidence_needed": "全仓检索引用 v2 runtime 镜像（config/docker/*_runtime）与 v2 API 入口的非测试编排物：scripts/、docs/guides/、config/ 下的启动脚本或文档化步骤，并核对其完整性（五服务齐全、含数据卷与 secret 注入）",
    "id": "q_system_properties_03",
    "question": "仓库内是否存在 fixtures 之外、可供用户实际执行的 v2 五服务（api/supervisor/gateway/coturn/caddy）拉起路径（脚本、隐藏 compose、guide 步骤）？本审阅只确认根 compose.yaml 为唯一 compose 文件且入口为 legacy。",
    "units": [
      "contracts_deploy",
      "docs_current",
      "tests_integration_fixtures"
    ]
  }
]
```

## question_decisions

```json
{
  "q_system_properties_01": {
    "result": "refuted",
    "reason": "精查对当前工作树与全部 265 个可达提交做了凭据形状扫描（secret 命名赋值、裸高熵 token、写出文件名三路）：harness 的三个写出文件（agent_token.secret、turn_secret.txt、turnserver.conf）在当前树与任何可达提交中均出现 0 次；其余命中全部是占位符、fixture 哨兵、弱测试词或运行时派生表达式（含两处初筛『像真实值』的 TURN REST 口令，结构复核证明是 base64.b64encode(hmac 派生) 表达式而非字面量）。s006 一处 26 字符 base64 形字面量无凭据命名绑定、位于含 URL 的探针代码行，证据不足以认定为已识别的真实 secret 值，不改变结论。.gitignore 确实未覆盖三个写出路径，f_archive_spikes_03 的前瞻性风险成立，但从未实际落盘。 Effect: f_global_system_properties_08 维持 Medium 定性不变；其 impact 中『q_01 若证实有真实 secret 值入库将升级为 High』的条件式升级路径就此关闭，evidence 第四条已改为精查后的否定结论。此后不得再以 secret 值已入库为由重开本项升级，除非出现新的历史证据。",
    "followup_sha256": "b09a5a64e860bb99b640b7b8ee5b4674924a9fc334ee70c16fe5c3217be04d1a",
    "decision": "upheld",
    "followup": "followup_q_system_properties_01.json"
  },
  "q_system_properties_02": {
    "result": "confirmed",
    "reason": "精查从代码与镜像布局构造性确认可达：serve_spa（main.py:1835-1843）以 FRONTEND_DIR / full_path 拼接后仅判 exists/is_file 即裸 FileResponse，无 resolve、无包含校验（做包含校验的 StaticFiles 只挂 /assets，不经手 catch-all）；部署路径无反代，uvicorn（h11/httptools 均同）以 unquote 后路径填充 scope['path'] 且不折叠点段，Starlette Router 直接正则匹配，%2e%2e%2f 在进 handler 前已解码为字面 '../'；按生产镜像布局，../../backend/main.py 与 ../../../etc/passwd、../../../data/... 均可达。仓内无 legacy 的精确版本 pin（只有下界、无 lock），但下界可解析的全部版本线在这三项行为上一致，版本不确定性不改变结论。反斜杠向量不成立仅缩小向量集合，不构成反证。 Effect: f_global_system_properties_01 中路径穿越分量的『疑似/suspected』限定已删除：evidence 第五条改为『经定向精查静态确认可达』并写入可达目标示例，fix 第 (4) 项由『核实后一并处置』改为直接处置。Critical 定级与无认证控制面结论不变（后者本就不依赖此项）；该分量自此按已确认的文件读取暴露计入，不再以 suspected 折价。结论性质仍为静态构造性确认，未做运行期实测，此限制保留在案。",
    "followup_sha256": "fbc6135a84903708331174291f350b07fd2e133f2c6f2a3aacbc52bc4bba46e3",
    "decision": "upheld",
    "followup": "followup_q_system_properties_02.json"
  },
  "q_system_properties_03": {
    "result": "confirmed",
    "reason": "精查全仓（含 git log --all 删除记录）检索非测试编排物：根 compose.yaml 是唯一 compose 文件且入口为 legacy；config/docker/*_runtime 四个生产镜像无任何非测试引用方；五服务完整形态（五服务+数据卷+五类 secret 注入）仅存在于 tests/fixtures/gateway_probe/topology.py；Caddyfile 仅有 fixture 生成器、turnserver.conf 在非测试非归档路径不存在；.env.example 无任何 v2 服务变量；README/DOCKER_DEPLOYMENT 只有 legacy 一条路径，guides 四份均为单镜像 validation 指南。t012 任务自述该交付物（正式 compose/五服务镜像/Caddy/coturn 配置）仍为 backlog，与检索结果一致。『手工 docker run 拼装』的反证不成立：API 服务连生产 Dockerfile 都没有（仅 fixture 定义），不构成仓库提供的拉起路径。 Effect: f_global_system_properties_01 中『不存在任何受支持的 v2 部署路径可供用户改选』与 summary 中『no shipped artifact wires its five services together』的表述维持原样，无需下调为『可部署但未文档化』；findings 本身不作改动。本问关闭，后续若 t012 落地需以新证据重开。",
    "followup_sha256": "bc1365e36b6ce8cece1814b27b4031815ba9ec66c52f6be3b356b77617ce77c9",
    "decision": "upheld",
    "followup": "followup_q_system_properties_03.json"
  }
}
```

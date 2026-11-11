# bundle_local_tests_e2e_supervisor

## responsibilities

- 本单元是 supervisor 域的真实 Docker 端到端门禁：以真实 Docker daemon、真实镜像（sha256 钉扎）、真实 API/Supervisor/Gateway 进程或容器，验证容器图拓扑、网络所有权与隔离、网络策略（namespace/IPv6/基础设施附着）、缓存初始化、孤儿 helper 回收、资源采样与限流策略、启动恢复/重试退避/离线 spool 回放，以及 Supervisor CLI 的 SIGTERM 优雅退出。
- 多数用例直接驱动生产代码（DockerAdapter、SupervisorCore、RecoveryCoordinator、ResourcePolicyService/ResourceMonitor、control_server）或以独立进程/容器运行生产入口（cbrowser.supervisor CLI、RealSupervisorContainer、container_graph 全容器拓扑），不是重写的假 harness；例外是 infrastructure_network 的策略探针直接调用 adapter 私有方法（见 f_tests_e2e_supervisor_06）与若干 stand-in 容器（infra 用 python 监听脚本冒充 gateway/coturn/runtime）。
- 共享装配来自 tests/fixtures/：supervisor_recovery_probe/offline_fixture.py（RealApiProcess、RealSupervisorContainer、RealBrowserActionProbe、SandboxContainerTracker、SpoolDirectoryWatcher、get_e2e_prerequisites）、supervisor_recovery_probe/gateway_fixture.py（SupervisorGatewayFixture）、gateway_probe/topology.py（cleanup_prefixed_resources）、fixtures/api_auth.py；各测试文件通过 importlib 按路径加载并注册 sys.modules，无 tests/conftest.py。

## interfaces

- 环境变量契约：CBROWSER_RUNTIME_TEST_IMAGE / CBROWSER_STREAM_TEST_IMAGE / CBROWSER_SUPERVISOR_TEST_IMAGE / CBROWSER_API_TEST_IMAGE / CBROWSER_GATEWAY_TEST_IMAGE / CBROWSER_INVALID_POLICY_TEST_IMAGE（须 sha256 摘要）、CBROWSER_RUNTIME_ENGINE_CACHE / CBROWSER_RUNTIME_GEOIP_CACHE（目录）、CBROWSER_TURN_TEST_IMAGE（可选，缺省回退到硬编码摘要）、CBROWSER_RECORD_DIR（可选证据输出）。
- 生产接口：Supervisor control HTTP（/supervisor/v1/profiles/start|stop|status、/supervisor/v1/health、/supervisor/v1/profiles/{id}/resources）、API（/api/v1/profiles、/api/v1/internal/supervisor/\*）、Docker label 契约（com.cbrowser.prefix / managed-by / role / profile-id / instance-id）、磁盘契约（runner_info.json、ready.json gate、spool 目录、runtime_events SQLite 表）。

## dependencies

- Docker daemon（docker-py from_env）；pyproject 中 pytest asyncio_mode=auto。
- 跨测试文件耦合：policy_failure 与 startup_recovery 以 importlib 执行 test_supervisor_core_e2e.py 以复用其 real_api_server fixture（见 f_tests_e2e_supervisor_07）。
- 宿主机资源：UDP mux 端口 30000 起、回环临时端口、host.docker.internal 解析（见 f_tests_e2e_supervisor_09/10）、公网出口（namespace_policy 断言 1.1.1.1:80 可达）。

## flows

- 典型重型用例：生成随机 prefix 与 0600 token 文件 → 启动真实 API（uvicorn 子进程或容器）→ 启动 Supervisor（子进程/容器）→ 经 control RPC 启动 Profile 双容器 → 注入故障（SIGKILL 容器、API 离线、503 代理、非法 policy 镜像、杀 browser）→ 轮询 API/Docker 状态收敛 → 按 prefix 清理并断言零泄漏。
- 轻型用例（network_ownership、orphan_helpers、cache_initialization、resource\_\*）：直接实例化 DockerAdapter/ResourcePolicyService 对真实 daemon 操作，finally 中按 label 回收。

## constraints

- 全部用例要求外部预置镜像与引擎缓存，仓内 CI workflow 不提供这些变量（仅 docs/blueprint/testing.md 记录手动门禁命令），缺失即 skip（见 f_tests_e2e_supervisor_01）。
- retry 用例按设计消耗真实 2s/10s/30s 退避，单文件墙钟以分钟计；全套件为串行重型门禁，不适合快速反馈环。
- 多文件断言 UDP mux 端口恰为 30000/30001，隐含同一 daemon 上独占运行、不可并行（见 f_tests_e2e_supervisor_09）。

## decisions

- 镜像一律要求 sha256 不可变摘要，防标签漂移；token/key 文件一律 0600 并在部分用例中显式断言权限位。
- 清理策略按随机 prefix + 归属 label 限定范围，多处在 finally 中做零泄漏断言或 cleanup 失败上抛（其掩盖原始失败的副作用见 f_tests_e2e_supervisor_08）。
- 归档 p002（policy failure 条件断言）已按无条件断言修复，当前 policy_failure 的 ready/runner_info 残留检查为无条件 glob 断言；但同类条件断言模式在 namespace_policy 的 IPv6 检查中仍存在（见 f_tests_e2e_supervisor_04）。
- 归档 p009 的固定 sleep 问题发生在 stream 单元（不在本单元）；本单元多数等待已改为带上限轮询，但 resource_policy 与 startup-gate 用例仍保留固定 sleep 编排（见 f_tests_e2e_supervisor_02/03）。

## evidence

- tests/e2e/test_supervisor_container_graph_e2e.py:1-685（全容器真实拓扑、docker.sock 仅 supervisor 持有断言、SIGKILL 后端口/实例不变性）
- tests/e2e/test_supervisor_recovery_e2e.py:1-1202（三条恢复链：SIGKILL 对账、双 Profile 端口不变性、诊断 spool 不改变 live runtime）
- tests/e2e/test_supervisor_retry_e2e.py:300-560（2/10/30s 退避下限断言与第四击阻断）
- tests/fixtures/supervisor_recovery_probe/offline_fixture.py:55-95（get_e2e_prerequisites 的 skip/fail 语义）
- src/backend/cbrowser/supervisor/docker_adapter.py:96,161（\_prepare_policy_gate/\_install_network_policy 生产定义，被 infrastructure 测试直接调用）
- .github/workflows/ci.yml 与 docs/blueprint/testing.md:62,125 对 CBROWSER_RUNTIME_TEST_IMAGE 的引用对照（CI 未提供、文档手动提供）

## uncertainties

- 未实际运行任何用例（静态审阅），所有时序/环境类判断基于代码结构；host.docker.internal 在目标门禁机（疑似 OrbStack/Docker Desktop，见 docs/findings/d020）上可用，本机 Linux daemon 行为未实测。
- RealSupervisorContainer 是否在镜像/入口层面对 host.docker.internal 另有处理未逐行核对（仅确认 offline_fixture.py 无 extra_hosts/host-gateway 配置）。
- CBROWSER_TURN_TEST_IMAGE 的硬编码回退摘要当前指向何镜像、是否仍可拉取，未联网核对。

## Findings

- [High][85] tests/e2e/test_supervisor_browser_network_e2e.py:15-27 — 全单元以环境变量缺失即 skip 为门禁前提，变量缺失时整套 supervisor E2E 静默变绿

    - ID: f_tests_e2e_supervisor_01; verification: static
    - Evidence: 几乎每个文件在用例开头检查 CBROWSER_RUNTIME_TEST_IMAGE 等变量，缺失即 pytest.skip：browser_network:17-27、core_e2e:165-186、retry:83-105、startup_recovery:57-84、offline_fixture.get_e2e_prerequisites:76-77 被 recovery/offline 复用。; .github/workflows/ci.yml 未提供这些镜像/缓存变量（grep 无命中），仅 docs/blueprint/testing.md:62,125 以 ${VAR:?} 形式记录手动门禁命令；即例行 CI 中本单元全部 skip。; skip 发生在用例体内而非收集期配置错误，报表上与通过难以区分；门禁环境一旦漏配一个变量，受影响用例无声消失而非失败。
    - Impact: supervisor 容器/网络/恢复链路可以在长时间内实际零覆盖而门禁显示绿色，回归（包括安全相关的网络隔离回归）不被发现。
    - Fix: 在门禁运行器层面对缺失变量 fail-fast（收集期统一 fixture 校验并 pytest.exit/明确报错），普通本地运行才允许 skip；或在 CI 报表中对本目录 skip 数设上限断言。至少把「门禁模式」与「本地可选模式」用显式开关（如 CBROWSER_E2E_REQUIRED=1）区分。

- [Medium][85] tests/e2e/test_supervisor_resource_policy_e2e.py:88-228 — 资源策略 E2E 用固定 sleep 编排与 3.5 秒容器 burn 窗口对齐，负载下采样相位错位即偶发失败

    - ID: f_tests_e2e_supervisor_02; verification: static
    - Evidence: 容器内 burn 固定 3.5 秒（:65-72），宿主机以 time.sleep(0.5)/1.0/1.0 采样三次断言 d3 已 throttle（:92-150），再 sleep(2.0) 后采样断言恢复（:153-207）；注释明说 'Burner loop ended at t=3.5s' 并假定 sleep 后负载已归零。; 采样本身经 Docker stats API 有可变延迟，慢机上 sample_3 可能落在 burn 结束后、或 sample_4/5 仍在统计窗口内，导致 observed_cpu_pct 与 is_throttled 断言随机失败。; 与归档 p009 记录的固定 sleep 偶发失败模式同类；p009 已在 stream 单元改为条件轮询，本文件未改。
    - Impact: 门禁偶发红/绿摇摆，掩盖真实资源策略回归或制造无效排查成本。
    - Fix: 改为带超时的条件轮询：循环采样直到 decision.is_throttled 为 True（或超时失败）再断言，同理等待 recovery；burn 时长改为显著大于采样窗口（如 15s）并以容器内标记文件/日志确认 burn 相位，而非以宿主机墙钟推断。

- [Medium][80] tests/e2e/test_supervisor_namespace_policy_e2e.py:165-301 — startup gate 子进程用例以固定短 sleep 推断进程状态，与 gate 自身 3 秒超时竞速

    - ID: f_tests_e2e_supervisor_03; verification: static
    - Evidence: 用例以 --timeout 3.0 启动 gate 后 time.sleep(0.3) 即断言 proc.poll() is None（:174）；后续各步 sleep(0.1)/0.2 后写 marker 并 proc.wait(timeout=2.0)（:193,210,227,246）。; 高负载 CI 上子进程启动、gate 轮询（0.05s）与 marker 写入的相对时序不可控：步骤 1 中若调度延迟超过 3s，gate 会因超时自行退出使 '仍在等待' 断言误报；marker 在 gate 首次轮询前/后落盘也影响拒绝路径的归因。
    - Impact: 该用例是 policy failure 之外唯一的 startup gate 黑盒覆盖，偶发失败会侵蚀对 gate 哨兵行为的信任。
    - Fix: 先轮询确认 gate 已进入等待（如其日志/状态输出或短暂存活窗口的多次 poll），再写 marker；'仍在等待' 断言改为在 timeout 的一小部分（如 0.5s 上限内多次 poll 均存活），并将 gate timeout 放宽到 10s 以拉开竞速窗口。

- [Medium][90] tests/e2e/test_supervisor_namespace_policy_e2e.py:541-557 — IPv6 fail-closed 断言被 if v6_b / if v6_c 条件包裹，无 IPv6 地址时整段检查静默消失

    - ID: f_tests_e2e_supervisor_04; verification: static
    - Evidence: :547 'if v6_c:' 与 :552 'if v6_b:' 包裹仅有的两条 IPv6 ULA 阻断断言；primary 网络虽 enable_ipv6=True 并配 ULA IPAM，但代码未先断言 GlobalIPv6Address 必然分配。; 当 Docker 环境未分配 GlobalIPv6Address（IPAM/daemon 配置差异）时，两条断言不执行且用例仍通过，IPv6 绕过隔离的回归不可见。; 与归档 p002 已修复的 'if 包裹断言' 模式同类：p002 在 policy_failure 中改为无条件断言，本文件同模式未处理。
    - Impact: 文件头契约声称的 'Real dual-stack / ULA IPv6 fail-closed verification' 可在无任何 IPv6 验证的情况下通过，属验证假行为。
    - Fix: 将 v6_b/v6_c 的存在性改为前置断言（assert v6_b and v6_c，附 attrs 诊断输出），再无条件执行阻断探针；环境确实不支持 IPv6 时应整体 skip 并在门禁报表可见，而不是局部跳过断言。

- [Medium][80] tests/e2e/test_supervisor_namespace_policy_e2e.py:525-540 — 公网出口断言硬依赖 1.1.1.1:80 可达，且阻断类探针以任意失败推断 '已被阻断'

    - ID: f_tests_e2e_supervisor_05; verification: static
    - Evidence: :533-540 断言容器可达公网 1.1.1.1:80 并返回响应；离线/受限出口的门禁机上该断言直接失败（非 skip）。; :528-531 对 100.64.1.1、198.18.1.1 的阻断验证以 probe 退出码非 0 为据（timeout=0.8），无路由、DNS/代理差异、目标主机静默丢弃等与策略阻断不可区分，存在假阳性通过。
    - Impact: 门禁环境网络条件变化会产生与策略实现无关的失败或假通过，削弱该黑盒用例的归因价值。
    - Fix: 公网出口改为可配置的探针目标（环境变量，缺省才用 1.1.1.1），不可达时区分 '环境无出口' 并 skip 该子项；阻断探针应结合策略侧证据（如 helper 日志/规则计数或同命名空间对照探针）确认失败源于策略而非环境。

- [Medium][90] tests/e2e/test_supervisor_infrastructure_network_e2e.py:141-185 — 隔离负向探针直接调用 DockerAdapter 私有方法并手工复刻沙箱装配，生产启动路径变更可与之漂移

    - ID: f_tests_e2e_supervisor_06; verification: static
    - Evidence: \_probe_tcp_connection 的 secured 路径调用 secured_adapter.\_prepare_policy_gate（:161）与 \_install_network_policy（:176），二者为 docker_adapter.py:96,161 的私有实现细节。; 探针容器由测试自行 create/start（sleep 30、自行拼 labels 与 resource_prefix 命名，:163-174），未走 DockerAdapter 的浏览器容器创建路径；生产侧若改变 gate 准备/策略安装的调用顺序或参数，该用例仍可能对自建装配通过。; 该负向探针承担 '跨 Profile 流量被生产策略阻断' 的关键断言（:395-410），其保真度直接决定隔离结论可信度。
    - Impact: 测试与生产实现以私有契约耦合：重构私有方法即破坏测试；更危险的是装配漂移时测试继续绿而真实浏览器容器的隔离已变化。
    - Fix: 优先用生产路径创建探针（如经 adapter 的容器创建入口或真实 Profile 容器内 exec 探针，container_graph_e2e 已有真实容器内 exec 模式可循）；若必须复用装配步骤，将 \_prepare_policy_gate/\_install_network_policy 提升为受测的内部 API 并在单元层锁定其契约，E2E 只做结果断言。

- [Medium][90] tests/e2e/test_supervisor_policy_failure_e2e.py:41-52 — 多个测试文件以 importlib 执行 test_supervisor_core_e2e.py 盗用其 fixture，且同一 fixture 文件被注册为不同 sys.modules 名

    - ID: f_tests_e2e_supervisor_07; verification: static
    - Evidence: policy_failure:41-52 与 startup_recovery:38-58 均以 spec_from_file_location('supervisor_core_e2e_module', test_supervisor_core_e2e.py) 执行整个测试模块，仅为取 real_api_server fixture；core 文件改名/移动将同时打破两个文件。; 同一 gateway_fixture.py 在 core_e2e 中注册为 'supervisor_gateway_fixture'、在 recovery_e2e 中注册为 'gateway_fixture'；offline_fixture.py 在 retry/offline/recovery 中统一为 'offline_fixture' 但与 pytest 自身收集的模块名不同，同一文件可被加载多份，模块级状态（如有）不共享。; real_api_server 是定义在测试模块中的 function-scope fixture，每次使用都拉起一个真实 uvicorn 子进程，被盗用后其来源与生命周期对使用者不透明。
    - Impact: 测试间隐性耦合与重复加载使重构成本和偶发状态问题上升；fixture 的真实进程开销与失败模式难以集中维护。
    - Fix: 把 real_api_server 及各 probe fixture 的加载收敛到 tests/fixtures 下的共享模块（或 tests/e2e/conftest.py），统一 sys.modules 名与导入方式，各测试文件正常 import。

- [Medium][90] tests/e2e/test_supervisor_ipv6_policy_e2e.py:146-156 — 多处在 finally 中执行断言/抛错，清理校验失败会掩盖用例本体的原始失败

    - ID: f_tests_e2e_supervisor_08; verification: static
    - Evidence: ipv6_policy finally 在清理后 assert 无残留容器（:152-154）；core_e2e finally 断言 scan_active_containers()==0（:427-428）；container_graph finally 对 ownership_violations 断言并在 cleanup_errors 非空时 raise RuntimeError（:672-685）；policy_failure finally 断言 cleanup_errors 为空（文件末尾）。; 当用例本体已失败时，finally 中的 AssertionError/RuntimeError 成为 pytest 报告的主错误，原始断言上下文被链式异常淹没，排障需额外展开 __context__。; ipv6_policy 的 finally 还先执行 network.remove() 再断言，若 remove 因端点残留抛错，容器列表断言根本不执行，泄漏信息丢失。
    - Impact: 失败归因成本上升；个别情况下清理断言的红会覆盖产品缺陷的红，导致误判为环境/清理问题。
    - Fix: finally 只做尽力清理并记录问题，把零泄漏校验移到用例末尾的显式步骤（或独立的 teardown 校验 fixture 以 addfinalizer 报告为独立错误），保证主体断言失败时先呈现主体错误。

- [Medium][85] tests/e2e/test_supervisor_core_e2e.py:323-348 — 多文件断言 UDP mux 端口恰为 30000/30001 且分配器区间重叠，套件不可并行且对残留分配敏感

    - ID: f_tests_e2e_supervisor_09; verification: static
    - Evidence: core_e2e:323,348 断言 session 端口恰为 30000/30001；recovery_e2e:669,683,720 同样断言 30000/30001 不变性。; PortAllocator 区间在 core/startup_recovery/recovery 为 30000-30010、policy_failure 为 30000-30005（core_e2e.py:272、policy_failure:127、startup_recovery:199），彼此重叠。; 任一先行用例崩溃遗留的端口占用、或以 pytest-xdist/双门禁同机并行运行，都会使后续用例的精确端口断言失败，与被测行为无关。
    - Impact: 套件被隐性约束为单机串行独占运行；扩展并行或同机多任务时出现与产品无关的失败，精确端口断言的信号被环境噪声污染。
    - Fix: 为每个用例分配互不重叠的端口区间（由 prefix/run_id 派生基址），断言改为 '落在分配区间且两 Profile 不同/重启后与首次分配一致'，仅在专门用例中验证从区间起点分配的语义。

- [Medium][70] tests/e2e/test_supervisor_retry_e2e.py:217-224 — Supervisor 容器以 host.docker.internal 访问宿主机 API/Gateway，fixture 未配置 host-gateway 映射，隐含 Docker Desktop/OrbStack 环境

    - ID: f_tests_e2e_supervisor_10; verification: suspected
    - Evidence: retry:217-224、offline_recovery:183-190、recovery_e2e 多处把 api_url/gateway_url 拼为 host.docker.internal 供 RealSupervisorContainer 内的 supervisor 使用。; 对 tests/fixtures/supervisor_recovery_probe/offline_fixture.py 的 grep 未见 extra_hosts / host-gateway 配置；原生 Linux Docker Engine 默认不解析 host.docker.internal。; 仓库 docs/findings/d020 记录的是 OrbStack bridge 可达性，侧面说明开发/门禁环境为 macOS 虚拟化 Docker，与 Linux CI 的默认行为不同。
    - Impact: 在原生 Linux Docker 上运行时，重型恢复类用例会在 supervisor 连不上 API 处整体失败，错误形态与产品逻辑无关，且与 f01 的 skip 机制叠加后容易被误归因。
    - Fix: 在 RealSupervisorContainer 创建容器时显式 extra_hosts={'host.docker.internal': 'host-gateway'}（Linux 生效、Desktop 无害），或改走专用 bridge 网络上的 API 容器地址（如 container_graph 的做法），消除对宿主机魔法域名的依赖。

- [Low][85] tests/e2e/test_supervisor_startup_recovery_e2e.py:262-296 — 恢复用例断言与场景设置深入 SupervisorCore/RecoveryCoordinator 私有状态

    - ID: f_tests_e2e_supervisor_11; verification: static
    - Evidence: 场景设置直接 core.\_get_profile_lock(profile_id) 并手动 acquire（:262）；断言 coordinator.\_in_flight_tasks 含 profile（:296）、native_inst 不在 coordinator.\_reported_dead_instances（:470）。; 同文件的主要结果已同时以 API 运行时状态（failure_count、last_exit_event_id、desired_state）做了可观察断言，私有断言属重复且更易碎的第二重耦合。
    - Impact: 内部重构（锁实现、任务登记结构）会打破 E2E 而行为未变；私有断言通过也不能独立证明外部可观察语义。
    - Fix: 锁场景保留私有锁作为设置手段可以接受，但断言层尽量改为可观察后果（如等待一个退避周期后 API 状态/新容器出现）；\_in_flight_tasks 断言可由 '退避到期后确实产生重试' 的行为断言替代，或下沉到单元测试层。

- [Low][90] tests/e2e/test_supervisor_startup_recovery_e2e.py:14-22 — 模块 docstring 的 Case 3 预期与用例实际断言的 A1 诊断语义矛盾（文档过时）

    - ID: f_tests_e2e_supervisor_12; verification: static
    - Evidence: docstring:20-22 称 spool 回放后 'converging the profile runtime to stopped with no restart'。; 用例本体断言回放后 desired_state 仍为 'running'、observed_state 为 'starting'、runtime_instance_id 不变、failure_count=0（:476-495），注释亦明言 'Disk events are diagnostics and must not converge lifecycle state'。; docstring 描述的是被 A1 权威观察架构取代的旧语义，未同步更新。
    - Impact: 读者按 docstring 理解契约会得出与实现/断言相反的结论，后续维护可能按错误契约 '修' 测试或实现。
    - Fix: 更新模块 docstring 的 Case 3 段落为当前诊断事件语义（回放只入 runtime_events 诊断记录、不收敛生命周期状态），与 offline_recovery/recovery 的 A1 表述对齐。

- [Low][90] tests/e2e/test_supervisor_offline_recovery_e2e.py:569 — Supervisor 二次重启后 Profile A 状态断言接受 stopped/inactive/idle 三者任一，断言强度不足

    - ID: f_tests_e2e_supervisor_13; verification: static
    - Evidence: :569 assert stat_a['observed_state'] in ('stopped', 'inactive', 'idle')；该检查是 '已关闭 Profile 不被错误重启' 场景的主要状态断言之一。; 三种状态语义不同，若实现把状态机改成返回 idle/inactive，该用例无声放行；同文件其他位置对 observed_state 均做精确断言（:372-380 等），此处为孤例。
    - Impact: 状态机词汇漂移或回归可能在此场景下漏检。
    - Fix: 与 supervisor status 接口的契约对齐后收紧为确切期望值；若三种取值确为契约允许，应在注释中引用契约来源并同时断言无运行中容器（已有 Docker 侧断言可保留为辅证）。

- [Low][85] tests/e2e/test_supervisor_recovery_e2e.py:434-443 — 多处就绪轮询在超时后静默穿透，不立即失败，后续步骤以更含糊的错误代替就绪超时

    - ID: f_tests_e2e_supervisor_14; verification: static
    - Evidence: recovery_e2e 三个用例的 supervisor health 等待均为 for range(100) + break 模式（:434-443、:650-659、第三个用例同构），循环耗尽不抛错，随即执行 start RPC 或 status 查询。; real_api_and_sup fixture 的 API 就绪等待同为 range(100) 穿透后直接 login_sync（:198-209），API 未起来时失败点是登录异常而非就绪诊断（且不附 api.log 内容，core_e2e 的同名 fixture 则会 pytest.fail 并带日志，行为不一致）。
    - Impact: 就绪失败的排障信息差，且同一模式在文件内复制三处以上，易继续扩散。
    - Fix: 抽取 wait_ready 辅助：超时抛 AssertionError 并附最近一次状态/进程日志路径；全文件统一使用。

- [Low][90] tests/e2e/test_supervisor_core_e2e.py:193-197 — TURN 测试镜像在 6 处硬编码同一回退 sha256 摘要，未设环境变量时以 ImageNotFound 形式报错且摘要可 silently 腐烂

    - ID: f_tests_e2e_supervisor_15; verification: static
    - Evidence: 同一回退摘要出现在 core_e2e:196、retry:150、offline_recovery:129、recovery_e2e:302,557,839，均写作 os.environ.get('CBROWSER_TURN_TEST_IMAGE', 'sha256:e2bca2f7…')。; 缺省路径随后 d_client.images.get(turn_image) 在本地无此镜像时抛 ImageNotFound，错误不指向 '需要设置 CBROWSER_TURN_TEST_IMAGE 或预拉取 coturn 镜像'；摘要对应的镜像身份（仓库/版本）无任何注释记录。
    - Impact: 新环境搭建时以含糊错误中断重型用例；摘要失效或被 GC 后所有恢复类用例同时不可运行。
    - Fix: 收敛为共享 prerequisites 辅助：回退摘要集中一处并注释镜像来源与版本，缺失时给出明确 skip/fail 信息（与 f01/f18 的统一门禁一并处理）。

- [Low][85] tests/e2e/test_supervisor_namespace_policy_e2e.py:84-137 — resource_tracker 清理失败仅记 debug 日志且无泄漏后置校验，本文件泄漏不可见

    - ID: f_tests_e2e_supervisor_16; verification: static
    - Evidence: resource_tracker fixture teardown 对 stop/remove/network.remove 的非 NotFound 异常仅 logger.debug 后继续（:103-137），且没有任何 '清理后按 prefix 复查为零' 的断言。; 对照同单元其他文件（core、policy_failure、ipv6）均有零泄漏断言或 cleanup 错误上抛，本文件的容器/网络若因端点占用 remove 失败，将静默残留并污染后续用例（随机 prefix 使其不被其他用例的按 prefix 检查发现）。
    - Impact: 泄漏的 bridge 网络/容器长期残留在门禁机上，且因 prefix 随机化难以追溯来源。
    - Fix: teardown 末尾按名称前缀复查残留并以警告级以上日志+收集错误呈现（可配合 f08 的处理把断言移出 finally 语义，改为独立校验步骤）。

- [Low][85] tests/e2e/test_supervisor_core_e2e.py:198-205 — 生成的 TURN static-auth-secret 写入 0644 的 turn.conf，与同套件 token 文件 0600 的规范不一致

    - ID: f_tests_e2e_supervisor_17; verification: static
    - Evidence: core_e2e:198-205 以 secrets.token_hex(32) 生成 static-auth-secret 写入 turn.conf 并 chmod(0o644)；container_graph:174、retry:159、offline_recovery:138、recovery_e2e:311,566,848 同样 0644。; 同批用例中 supervisor/agent/gateway token 文件一律 0600 并有权限断言，显示更严规范已存在；turn.conf 位于 tmp_path 虽属临时目录，但 0644 使同机其他用户可读该共享密钥（其有效期覆盖整个用例且被 coturn 实际用于 TURN 认证）。
    - Impact: 测试凭据的本地暴露面与套件自身宣示的密钥文件规范不一致；在多用户门禁机上可被同机进程读取并冒用 TURN 中继。
    - Fix: turn.conf 改为 0600（coturn 容器以 bind 只读挂载读取，宿主侧 0600 不影响容器内 root/运行用户读取时需确认属主映射；若因容器用户问题必须放宽，应在注释中写明理由）。

- [Low][90] tests/e2e/test_supervisor_orphan_helpers_e2e.py:19-24 — 环境前置校验逻辑在各文件重复实现且严格度漂移（skip/fail/KeyError 三种语义并存）

    - ID: f_tests_e2e_supervisor_18; verification: static
    - Evidence: orphan_helpers:21-24 变量缺失只 skip 且摘要校验允许 'sha256:' 前缀或 '@sha256:' 两种形式；browser_network:30-37 只允许 startswith('sha256:')；cache/core/retry 等又各自复制一份。; event_shutdown 对缺失 Docker/镜像用 pytest.fail（:48-82），与全单元 skip 语义相反；container_graph 干脆 os.environ[...] 直接 KeyError（:80-100）。; 同一组变量在不同文件中出现至少四种处理方式，后续新增变量（如 CBROWSER_INVALID_POLICY_TEST_IMAGE 仅 policy_failure 使用）难以保持一致。
    - Impact: 门禁行为不可预测：同一环境下部分文件 skip、部分 fail、部分以 KeyError 崩溃，报表解读和 f01 的治理都被复杂化。
    - Fix: 抽取共享 prerequisites 模块（offline_fixture.get_e2e_prerequisites 已是雏形），统一 '缺失=skip、格式错=fail、门禁模式=硬失败' 的语义并被全部文件复用。

- [Low][80] tests/e2e/test_supervisor_retry_e2e.py:355-530 — 退避时序断言只有下限没有上限，退避被放大（如 10 倍）时用例仍通过

    - ID: f_tests_e2e_supervisor_19; verification: static
    - Evidence: 三击断言分别为 delay_1 >= 2.0（:355）、delay_2 >= 10.0（:449）、delay_3 >= 30.0（:530），均无上限；delay 由 Docker Created 时间戳减 API updated_at 得到。; 若恢复逻辑把退避错误地放大（配置漂移、单位错误），只要不低于阈值该用例就判定通过，'退避时长正确' 的契约只验证了一半。
    - Impact: 退避过长会显著拉长真实故障恢复时间，此类回归在本门禁中不可见。
    - Fix: 增加宽松上限断言（如 target + max(5s, target\*0.5)），容忍调度抖动的同时拦截数量级错误；上限值可依据门禁机历史数据标定并注释。

- [Info][85] tests/e2e/test_supervisor_event_shutdown_e2e.py:186-210 — event_shutdown 就绪判定耦合确切日志文案；多文件以 bind-关闭方式取空闲端口存在 TOCTOU 窗口

    - ID: f_tests_e2e_supervisor_20; verification: static
    - Evidence: event_shutdown 以日志行 'Docker events stream subscribed for prefix={prefix}' 的出现作为 watcher 就绪证据（:194 及轮询段），日志措辞变更即使用例误报。; 空闲端口获取在 event_shutdown（\_get_free_port:31-35）、offline_fixture.get_free_port、core_e2e/recovery_e2e 的 fixture 中均为 bind(0) 后立即关闭再复用，关后到真正监听之间可被同机其他进程抢占（本机串行门禁下概率低）。
    - Impact: 日志文案重构会误伤 E2E；端口抢占偶发时失败形态为地址占用，与被测行为无关。
    - Fix: 就绪判定优先用可观察状态（如控制接口暴露 watcher 状态或事件计数）；端口改为由被测进程绑定 0 端口后回读实际地址（接口不支持时保留现法并接受低概率窗口）。

## views

```json
{
  "contracts": {
    "reviewer": "dad09ca2-fdae-4e61-a088-ee77ee401918",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "dad09ca2-fdae-4e61-a088-ee77ee401918",
    "status": "completed"
  },
  "design": {
    "reviewer": "dad09ca2-fdae-4e61-a088-ee77ee401918",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "dad09ca2-fdae-4e61-a088-ee77ee401918",
    "status": "completed"
  },
  "performance": {
    "reviewer": "dad09ca2-fdae-4e61-a088-ee77ee401918",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "dad09ca2-fdae-4e61-a088-ee77ee401918",
    "status": "completed"
  },
  "security": {
    "reviewer": "dad09ca2-fdae-4e61-a088-ee77ee401918",
    "status": "completed"
  },
  "tests": {
    "reviewer": "dad09ca2-fdae-4e61-a088-ee77ee401918",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "tests/e2e/test_supervisor_browser_network_e2e.py",
  "tests/e2e/test_supervisor_cache_initialization_e2e.py",
  "tests/e2e/test_supervisor_container_graph_e2e.py",
  "tests/e2e/test_supervisor_core_e2e.py",
  "tests/e2e/test_supervisor_event_shutdown_e2e.py",
  "tests/e2e/test_supervisor_infrastructure_network_e2e.py",
  "tests/e2e/test_supervisor_ipv6_policy_e2e.py",
  "tests/e2e/test_supervisor_namespace_policy_e2e.py",
  "tests/e2e/test_supervisor_network_ownership_e2e.py",
  "tests/e2e/test_supervisor_offline_recovery_e2e.py",
  "tests/e2e/test_supervisor_orphan_helpers_e2e.py",
  "tests/e2e/test_supervisor_policy_failure_e2e.py",
  "tests/e2e/test_supervisor_recovery_e2e.py",
  "tests/e2e/test_supervisor_resource_capacity_e2e.py",
  "tests/e2e/test_supervisor_resource_monitor_e2e.py",
  "tests/e2e/test_supervisor_resource_policy_e2e.py",
  "tests/e2e/test_supervisor_retry_e2e.py",
  "tests/e2e/test_supervisor_startup_recovery_e2e.py"
]
```

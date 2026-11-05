# Task spec

## 背景

t015 删 TURN 时误删与 TURN 无关的端到端断言；后续 task 的真实环境债也缺可执行入口，t032 无法按现有门禁产出证据。已核实缺口：

- Agent 替换：`tests/integration/test_gateway_signaling.py:436-495` 只断言旧 Viewer 收到任意 CLOSE；`251fa0f` 原有 close=1001、新旧 conn_id 不同、下行回复与新 Viewer 存活四项断言。
- 配额：`test_supervisor_resource_monitor_e2e.py:52` 用内存回调替代 GatewayControlClient；`test_stream_runtime_e2e.py:94` 的 GatewayProtocolMockServer 不含 quota 路由；`tests/fixtures/supervisor_resource_probe/stream_monitor.py` 无任何引用；`docs/blueprint/testing.md:147` 与两份 validation guide 仍声称存在真实 CPU 降帧/帧数证据。
- 镜像身份：E2E required 模式只检查镜像变量存在，不要求不可变 `sha256:` ID；`frontend_probe/harness.py` 静默读取 `.scratch/images_env.txt`，旧 tag 可冒充当前镜像。
- 门禁证据：`scripts/run_gates.sh` 为 `set -euo pipefail`，首个 suite 失败即停；默认 scratch 由 trap 删除；没有逐 suite 命令、退出码与 JUnit/evidence 清单。
- 历史实跑入口（审阅指出，实施时先核对）：Artifact 下载只覆盖到 DownloadArtifactForwarder 组件，未经真实 Supervisor 进程；删除续跑以新 service 对象模拟；X11 helper 权限只有 mock；多 Agent 注册 429/恢复只有 integration fake；search-defaults 重试只有 stub。

新拓扑下的 Gateway 附网、未知 endpoint 保护与附着后失败回滚用例由 t026 交付（旧 coturn 中途失败场景已随 t015 删除），本 task 只在覆盖矩阵中引用。

## 契约区

### 范围

- 覆盖矩阵：逐项列出 p016 原行为与 p021–p024、p026、p027 历史真实环境项的现行入口、触达组件、证据层级与 t032 待执行项；复用现有 namespace/IPv6/policy/container_graph 测试。
- 恢复 Agent 替换精确断言。
- 建立 Supervisor→Gateway→Agent→Stream/Chrome 配额真实探针：接线或删除孤儿 `stream_monitor.py`，不以内存回调或缺路由的 mock 替代链路环节。
- 为矩阵确认缺失的历史项补可收集的真实 E2E 入口。
- E2E required 模式镜像身份 fail-closed；`run_gates.sh` 增加证据模式。
- 修正 testing.md 与 validation guide 中高于实际证据层级的表述。

### 非范围

- 不恢复 coturn/TURN 或旧架构文件；不重写已有效覆盖，不把多个组件单测合成 E2E PASS；不重复 t026 的新拓扑附网与回滚用例。
- 不承担生产自愈、配额新算法、发布脚本或本地压力执行。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：覆盖矩阵逐项列出 p016 原行为与 p021–p024、p026、p027 历史项的现行入口、触达组件、证据层级（unit/integration/真实 E2E）、云端结果与 t032 待执行项；已覆盖条目引用具体断言，t026 负责的新拓扑条目引用其用例，缺口均有可收集执行入口。
- [x] AC-002：Agent 替换用例断言旧 Viewer close=1001、新旧 conn_id 不同、新连接上下行回复正确、旧 Agent 退出不误关新 Viewer；仅收到任意 CLOSE、宽泛超时或异常均不能通过。
- [x] AC-003：真实配额探针观测链贯通 Supervisor、Gateway、Agent、Stream 和 Chrome，记录投递值、CPU counter/采样窗、限帧值与实际帧数；客户端抬高 FPS 不突破 cap，布局保持，motion/static 与 CPU policy 分别有证据；链路任一环节不以内存回调或 mock 服务替代。
- [x] AC-004：矩阵确认缺失的历史项各有可收集的真实 E2E 入口与明确断言：真实 Chrome 下载经 Agent、Supervisor 进程到 API Artifact 全链；删除意图跨真实进程重启续跑；真实容器内 X11 helper 权限；真实 Gateway 上多 Agent 注册预算/429/恢复；活 context 上 search-defaults 重试。
- [x] AC-005：E2E required 模式只接受本机存在的不可变 `sha256:` 镜像 ID，缺失、非 ID 形式或无法解析即明确失败；不静默读取 `.scratch` 等旁路文件；evidence 记录实际镜像 ID；普通收集不能冒充已运行。
- [x] AC-006：`run_gates.sh` 证据模式跑完全部 suite，在保留的证据目录记录逐 suite 命令、退出码、JUnit 与脱敏 evidence 路径，任一 suite 失败时总退出码非零；默认模式行为不变。
- [x] AC-007：每次探针资源与证据独立，正常/失败路径均只清理本轮资源并脱敏；运行指令、预算和 artifact 字段逐项映射到 t032。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、可用的普通 Chromium 测试，以及可收集的真实环境用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- 来源：p016；2026-11-04，main@c6a9322 核实，同日按三方审阅修订。现有 namespace、IPv6、policy failure、资源 monitor、container_graph 与 Gateway control 测试仍在；t024 的 callback 投递断言不能代替实际媒体证据。审阅补充：新拓扑附网用例与 t026 重叠（移交 t026）、配额孤儿探针与文档失真、required 模式镜像身份、门禁证据产出能力与历史入口覆盖被高估。

### 有意不测

- 宿主 Mac/OrbStack、目标 CloakBrowser、真实媒体/X11/指纹站点：当前 task 执行端为云端 Muse，统一由 t032 执行；不得记为 PASS。

### 测试策略

- AC-002 为 integration 级，在云端完整执行；先用现有 fixture/生产组件验证新增断言确实观察对应行为，运行相关 unit/integration、E2E collect-only 和证据脱敏测试。
- required 模式与证据模式以缺失镜像、非 sha256 变量、suite 失败等负例验证 fail-closed。
- 真实 Docker、CPU 采样、Chrome 帧率与历史真实链入口由 t032 实跑；不降低旧预算、不用 mock 帧数作为媒体证明。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无（测试交付契约）；目标环境是否满足各行为由 t032 运行，本 task 不认领真实执行 PASS。

### 风险与回退

- 风险：测试只是验证替身或因环境错误产生假负例；强行复原旧文件可能回退拓扑；与 t026 并行修改 Gateway 信令测试文件。
- 回退：回退新增测试/探针 commit，不改生产配置；失败现场保留并列真实执行缺口。

### 依赖与约束

- 无未完成硬依赖；与 t027 互斥（共用 E2E 夹具与镜像身份校验）。与 t026 可并行，Gateway 信令测试只改 Agent 替换用例以降低合流冲突。
- 已知基线失败 `tests/integration/test_api_search_defaults_routes.py::test_retry_route_requires_csrf_and_maps_outcomes` 归 t026 修复；t026 合入前本 task 门禁按同 ID 存量对照，不重复修复，不得新增其他失败。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/testing.md：覆盖矩阵、证据层级、required/证据模式与新运行入口；修正配额证据失真表述。
- docs/guides/stream_runtime_validation.md、docs/guides/supervisor_validation.md：按实际证据层级修正表述。

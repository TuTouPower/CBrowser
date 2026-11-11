---
tid: "t060"
slug: "gate_infra_and_privacy"
title: "门禁与测试基础设施、隐私扫描收口"
status: "done"
branch: "t060_gate_infra_and_privacy"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "12380b25a51fc0dc51a7b00306e93684715f6b3f"
depends_on: ""
conflicts_with: ""
note: "来源 review_20261110_200842 adoption_decision A9 A45-A54 A56"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-11T17:35:14+08:00：`run-begin t060 --owner-id local_t060_20261111` 完成；base=main@12380b25a51fc0dc51a7b00306e93684715f6b3f，分支 t060_gate_infra_and_privacy，独立 worktree `<repo>_t060`。preflight=PASS。

- 原执行环境沙箱阻止 Docker socket，未执行 Docker 验证、未记 PASS。用户切换 unrestricted 后恢复；`docker info` 实测 linux/aarch64，Chrome 可执行文件存在。

- 引用核对：task 目录、来源 review_intensive/adoption_decision、p051/p063、t047/t049/t050 归档、gate_verification spec 与 testing/security blueprint 均存在；`5dcb11d`、`1ff4721`、`18e343f` 已用 Git 对象核实。来源报告自述缺 bundle\_\*.md，仅采用现存 intensive，不虚构 bundle。task 中短文件名均对应 scripts/ 或 tests/unit/ 现存文件。

- AC-001/002/005/007/010 边界回归先红：19 failed / 9 passed（`.scratch/t060/red_boundaries.log`）。实现后相关测试 57 passed。隐私扫描删整文件指纹豁免；归档仅作隐私脱敏，不改 Git 历史；固定容器用户与产品路径继续按语义识别。

- AC-003/004：新进程锁与运行租约回归先红 2 failed；实现后 2 passed。完整并发门禁与真实 Docker 资源保护尚待执行。

- AC-009：marker 范围测试先红 2 failed / 26 passed；实现后 28 passed。各 E2E 模块已声明镜像消费者，未声明仍按全集失败封闭；真实 collection 待执行。

- AC-011：五镜像 bytecode 与 supervisor services 精确 COPY 范围测试通过。镜像真实构建进行中。

- AC-012：5dcb11d 已包含换算实现；补宿主绝对路径、嵌套目录和越界事件端到端 forwarder 回归，不改已有正确生产逻辑。相关测试通过。

- 删除旧测试理由：静态前缀清理契约已被 A47 明确废弃，原用例整体替换为标签/租约保护用例；接线字符串断言与内嵌 unit/E2E 全量收集用例按 A50 删除，以实际脚本调用顺序与门禁用例下限替代；旧固定 suite 清单测试整体扩展为 protocol-first 契约，保留失败传播、脱敏与 evidence 完整性断言。

- 用户后续明确要求继续修复本轮全部门禁失败；授权在 t060 分支闭环显示编号夹具、健康检查、X11 权限、媒体/下载与同 checkout 并发产物问题，不改其它 task 状态或云端分支。

- 前两轮真实并发普通门禁 A/B：unit 各 1634 passed / 3 failed，integration 各 178 passed / 18 skipped，frontend 各 499 passed。unit 两项接线调整已定向修复，协调器用例单跑通过。

- 后两轮 C/D：unit 各 1641 passed；integration 各 177 passed / 1 failed / 18 skipped（stop RPC 已记录但状态尚未收敛）；frontend 各 499 passed。同 checkout 同时构建造成 C 的 Selkies adapter 被 D 的构建删除，C frontend_build 失败，D 通过。

- 真实 E2E C：parallel 28 passed / 10 failed / 1 error / 2 skipped；serial 中止前 3 passed / 5 failed，其余未运行。已知错误包括 HTTPS health 30 秒未就绪、旧夹具缺显示编号、清理端口未释放、X11 权限 0711 未恢复 0750，以及音频静音/WebAudio/CDP/下载断言失败。收到继续修复授权后按根因逐类定位。

- 专项验证：两轮真实启动清理保留首轮活跃容器与网络（`.scratch/t060/concurrency_resources.json`）；scoped E2E collection 仅提供 Stream 镜像时收集 3 项，缺该镜像退出 2；五个镜像真实构建完成且 /app 无 bytecode，Supervisor services 恰为两个 COPY 文件；image_packages 五镜像真实校验通过。

- 新接线/并发脚本测试 11 passed；含实际脚本顺序变异、用例下限负例、protocol 失败完整 evidence、缺镜像 skipped 使总门禁失败，以及两个实际 gate 进程共享冷 venv（PATH 注入依赖桩）仅重建一次并均完成。

- 环境跳过：Mac 宿主缺 Xvfb，integration 的 18 项真实引擎测试跳过；E2E 默认关闭的两项 container probe 不计已验，独立 real_engine suite 尚未执行。后续以容器探针补充，不冒充宿主 Xvfb 已验。

- 根因已验：Docker config 自动注入 HTTP/HTTPS 代理使 Caddy 内部转发返回 HTTP 400，同时破坏 Browser HTTP 夹具访问，表现为 WebAudio/音频/下载/CDP 多项失败。SDK 关闭 use_config_proxy，CLI 清空代理；不修改本机 Docker 配置。代理注入新回归先红，修复后 boundaries 32 passed；原失败定向三组分别 3 / 5 / 5 passed，覆盖健康链、音频/WebAudio、下载、CDP、权限、端口清理与真实双 Profile。

- 显示编号：所有直接 Supervisor RPC 夹具从创建 Profile 的真实 API 响应读取 display_number 并传 profile_number；直接 DockerAdapter 网络清理夹具显式登记其固定测试编号。保留生产编号约束，未加兼容默认值。

- X11：旧用例把 Mac/virtiofs 宿主 stat 缓存当成目标权限；整体替换为 Linux 挂载命名空间先制造 0700/0711 漂移、验证恢复 0750，原权限预期不变，生产 helper 不变。

- 同 checkout 并发：新独占 checkout 锁保护 dist 及消费者；不同 worktree 的 venv 仍共享读锁。锁用例先红，修复后 checkout/venv/接线集合 26 passed。嵌套接线门禁使用独立仓库副本，避免与父门禁死锁。

- 集成 stop 断言：等待真实 observed_state=stopped 后保留原断言，不把“已记录 RPC”当作已收敛。原失败已保存，修复后定向 1 passed，未延长超时。

- 普通门禁 F 已完整通过：contract 257 passed / 1 policy skipped，unit 1647 passed，integration 178 passed / 18 skipped，frontend 499 passed，design lint/check、类型检查、生产构建均通过；manifest all_passed=true、cleanup_exit_code=0。此结论保留，不因后续真实探针失败撤销。

- 全仓 Markdown --check 最初发现历史报告和三份现行文档格式漂移，已通过现有 md_format --all 规范格式（archive 仍按工具黑名单不格式化），再次 --check 格式一致；其它 task 文件状态未修改。

- 门禁 E 的真实镜像前置拒绝旧 Supervisor ID：在重建完成前绑定了旧 tag 身份。已在重建完成后刷新不可变 ID 并再次预检 PASS；未把该轮记为通过。

- 独立真实引擎探针 E：2 项中 1 passed / 1 failed，失败内部链 15 failed / 1 passed，首个确定性错误为 Managed socket identity unavailable。三份旧集成夹具仍假设 runtime/agent.sock；修复为 prepare_socket_dir + agent_socket_path，显式 UDS 与 Supervisor PathValidator 一致，同时登记真实运行实例并使用现行 HTTPS Origin。保留原断言与超时，重验进行中。

- 真实探针修复第一阶段已验：chain 子套件 16 passed（原先 15 failed / 1 passed），包括目标引擎矩阵、dialog、真实 CLI/CDP 下载与控制链；原断言和超时未变。L0–L6 采样仍在运行。

- AC 勾选：已有独立证据的 AC-001/002/004..012 共 11 项打勾；AC-003 等待最终两进程门禁均完成，AC-013 等待最终交接写入。未完成项保持未勾选。

- 独立真实引擎探针 socket_fix 轮完整通过：2 passed，内部 chain 16 passed，L0–L6 完整采样且 evidence all_passed=true；定向 E2E parallel 39 passed / 2 skipped。G 完整门禁与 H 第二进程已并发启动，H 按 checkout 锁等待 G 释放工作区。

- 收口新增两项边界：两个清理器同时删除同一已结束运行时，对明确的 Docker NotFound 按已完成处理，其余错误继续失败；两个负例先红，修复后 cleanup 7 passed。中断旧 wrapper 只通知 Bash、遗留 suite 子进程，真实进程回归先红（10 秒收不到退出），改为独立进程组并向全组转发信号后，终止与清理集合 8 passed。新增 3 个回归使 unit 当前收集下限为 1650；原先 1647 全绿结论保留。

- AC-011 撤回重验：原生 Docker 证明原静态 matcher 将目录否定误当遍历门，未声明 services 文件实际可 COPY。修正 matcher 后旧规则测试先红 2 failed / 5 passed；改用叶子白名单后 38 passed，原生五镜像上下文测试 5 passed（5 正例 / 26 反例）。完整镜像重建完成后再勾 AC-011。跨任务事实登记 d037。

- 完整门禁 G：普通套件保持全绿，真实引擎 2 passed（chain 16 passed、L0–L6 all_passed=true）；E2E 为 96 passed / 2 failed / 2 skipped。失败分别为共享会话第三个 Profile 的 Browser 就绪超时，以及直接 15 fps 配额观测到 57 帧 / 2 秒（原上限 40）。继续保留原断言与超时定位，不记 G 为通过。新增原生上下文五项后 E2E 收集下限同步为 105。

- 2026-11-11T23:56:42+08:00：五个 runtime 镜像与 probe 按叶子白名单全部重建成功；刷新不可变 ID 后 image_identity 预检 PASS，五镜像 /app 无 bytecode，Supervisor services 恰为 __init__.py/tunnel_registry.py。AC-011 重新打勾；旧 handoff 已迁 archive，新 handoff 单节与写入时 branch/HEAD 一致，AC-013 打勾。

- 诊断重跑原 E2E 四项 4 passed，确认存在外部依赖与双配额写入者竞争：Browser GeoIP 默认查询公网 IP echo（SDK 总预算 20 秒，实测请求可耗时 10 秒）；本地会话/媒体夹具显式 geoip=false，新增请求回归先红后绿，搜索默认行为不变。配额探针在宿主执行真实 Supervisor client/ResourceMonitor 时暂停其专属 bootstrap Supervisor 容器，消除另一资源循环覆盖配额，结束必恢复；生产配额逻辑、断言与超时均未修改。定向复验进行中。

- H 普通门禁全部通过：unit 1650 passed、integration 178 passed / 18 skipped、frontend 499 passed、contract 257 passed / 1 policy skipped，构建、类型与设计检查通过，manifest all_passed=true / cleanup_exit_code=0。本次新增 GeoIP 回归后 unit 下限为 1651。

- 修复后专项 4 passed（会话三项与完整 quota 链），原断言及超时保留。冻结实现后启动 I 完整门禁（含 105 项 E2E 与独立真实引擎）和 J 并发普通门禁，后者按 checkout 锁等待；两者 scratch/TMPDIR 显式放在本 task .scratch 内。全仓 Markdown check 与新增代码 Ruff check 均通过；补充扫描旧 topology 的 5 项既有 Ruff 风格问题未扩大修复范围，项目声明门禁不包含全仓 Ruff。

- 容器补充验证安装独立 Playwright Chromium 156.0.8078.4（未用目标引擎冒充基线），三份真实集成链 17 passed / 1 failed / 0 skipped。attendant restore 的两个旧请求头仍为 HTTP Origin，POST 被现行 HTTPS 校验拒绝为 403，原断言 200 失败。修复请求头，不改断言/超时。I 此时普通门禁全绿、E2E parallel 44 passed / 2 skipped，但因继续修夹具主动中断，不计完整通过；后续将从头重跑全部门禁。

- 2026-11-12T00:06:17+08:00：attendant HTTPS Origin 修复后，容器内三份完整真实集成链 18 passed / 0 failed / 0 skipped；包含独立 Playwright Chromium 156.0.8078.4 基线与 CloakBrowser 146.0.7680.177.3 目标引擎。宿主原 18 skips 仍如实保留，容器补验结果不冒充 Mac Xvfb 已安装。J 普通门禁全绿（unit 1651、integration 178/18 skipped、frontend 499、contract 257 passed / 1 policy skipped，lint/类型/构建通过），K 已取得锁继续全量。

- 2026-11-12T00:36:48+08:00：K 完整门禁结束，manifest all_passed=true、cleanup_exit_code=0；与并发启动的 J 均完整成功，AC-003 打勾，13/13 AC 全部已验证。K：unit 1651 passed / 0 failed；integration 178 passed / 0 failed / 18 skipped；frontend 499 passed / 0 failed；E2E parallel 44 passed / 2 skipped、serial 59 passed，总计 103 passed / 0 failed / 2 skipped；独立 real_engine 2 passed（chain 16 passed / 0 skipped，L0–L6 all_passed=true）。设计 lint/check、TypeScript 检查、构建、协议/requirements 检查、五镜像包验证均通过。全仓 Markdown check、新增/重写脚本与回归 Ruff check、git diff --check 均通过。

- 用例数更正：复核 JUnit 后确认 contract 收集 258 项，其中 257 passed / 1 policy skipped；前文曾将收集数误写为通过数，已校正。该项跳过理由为“项目已显式选择验证策略，跳过模板默认命令检查”，属于不适用检查，不冒充通过。

- 原失败配额链全量复验：baseline 44 帧 / 2 秒，15 fps 配额下 31 帧，客户端突破尝试后 30 帧（原上限 40），解除后 58 帧；真实 CPU 配额下 16 帧（原上限 24），恢复 60 帧。会话 freeze/resume 原失败项同轮已通过。

- 环境跳过：K 宿主 integration 18 项中，11 项报告未安装 Playwright full Chromium，4 项报告无 Xvfb，3 项报告需目标引擎和 Xvfb；容器使用真正独立 Chromium 与目标引擎补验这 18 项，全为 passed / 0 skipped。E2E 2 项默认容器探针 skip 已由独立 real_engine suite 的 2 passed 补验。宿主 Xvfb 从未记为已安装或已验。

- 证据保留：`.scratch/t060/` 对应材料同步到主仓忽略目录 `<main_repo>/artifacts/t060/`，含 J/K manifest、JUnit、脱敏日志、独立探针报告、原生上下文与双引擎补验证据；`evidence_index.json` 记录 SHA256，收尾前再次刷新。测试缓存、引擎与真实环境文件不入提交。

- 2026-11-12T04:20:16+08:00：Round 1 修复完成。新增 venv / pip 引导失败与公开 URL 路径边界 3 项回归先红 3 failed，修复后 3 passed；边界/并发/接线/隐私/evidence 合集 69 passed。引导阶段先撤旧 manifest，安装失败以当前 run_id 写失败 manifest 和非敏感日志；失败不再复用旧 PASS。

- 历史脱敏修正：74 份文档从 base 原文按精确 repo/home 前缀替换，54 份恢复路径外文字或原路径后缀，逐文件 SHA256 守恒核对见 `.scratch/t060/precise_privacy_restore.json`；handoff 保留本轮旧节迁移。公开 GitHub URL 恢复原文，扫描器不误报嵌套 home 段，真实 file URI / 绝对家路径仍检出。未修改任何其它 task 状态。新增回归后 unit 下限同步 1654，待完整 L/M 门禁后重新勾 AC。

- 补充隐私根边界回归：`file://localhost` 家路径在 URL 误报修复下先红，保留 file authority 的 home 根匹配后隐私/边界 40 passed；普通绝对路径和无 authority file URI 均保留检测。未新增用例数，unit 仍为1654。此改动只在单元测试模块，产品源码与E2E代码不变；等待中的M会在改动后完整重跑全部普通套件，L继续验证相同产品代码的真实E2E。

- 2026-11-12T05:00:00+08:00：修复后的完整L门禁与最终M普通门禁均 all_passed=true / cleanup_exit_code=0。L E2E 103 passed / 0 failed / 2 optional skips，独立真实probe 2 passed（chain16、L0–L6完整）；最后一次file URI边界改动后，M全部普通套件重跑通过：unit1654、integration178 / 18 host skips、frontend499、contract257 / 1 policy skip，全部0 failed。两进程同机并发启动并完整结束，venv/checkout未互相破坏。重新逐项复核并勾选13/13 AC，准备Round2独立review。

## Review 处置

### Round 1 (2026-11-12T00:43:13+08:00)

- code/test 均 FAIL，原 scope efd671641d478eb5；共 1 类 important 与 2 类 minor，详见两份独立报告。代码轴独立 99 passed，测试轴独立 144 passed；全部 13 AC 原有验证成立，但 bootstrap 证据复用仍阻断交付。

- 修复前撤回全部 13 项 AC；修复、重验后重新逐项打勾，再派 Round 2。
|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t060_code_f001|minor|已修|精确前缀替换恢复路径外字段，65份归档SHA256守恒核对通过|docs/archive/handoff.md:100；.scratch/t060/precise_privacy_restore.json|
|t060_code_f002|important|已修|进入bootstrap前撤旧manifest，venv/pip失败写当前run_id失败证据，两个负例通过|scripts/gate_run.py；tests/unit/test_t060_gate_wiring.py|
|t060_code_f003|minor|已修|恢复公开GitHub原URL；路径根边界负例通过且file URI仍检出|tests/unit/test_repo_hygiene.py；docs/reviews/review_20261108_153337/adoption_decision.md:48|
|t060_test_f001|important|已修|同代码轴f002，实际门禁入口先红后绿，无旧PASS遗留|scripts/gate_run.py；.scratch/t060/green_review_findings.log|
|t060_test_f002|minor|已修|同代码轴f001，74文档按base精确替换并核对路径外守恒|.scratch/t060/precise_privacy_restore.json|

- 修复真实验证：3项先红后绿，相关合集69 passed；完整L/M门禁进行中，修复是否闭环仍待Round2独立复核。无finding遗留。

### Round 2 (2026-11-12T05:02:08+08:00)

- code PASS：102项独立定向验证通过，原3条finding已独立确认消除，无新finding；13/13 AC均TICK-VALID/re_verified。
- test PASS：147项独立验证通过（142项定向unit与5项原生BuildKit），required collection正负例另通过；原2条finding已消除，无新finding；13/13 AC均TICK-VALID/re_verified。
- 两份报告末轮scope均为c899ece7b48f99a1，保留Round1完整FAIL记录。65份archive守恒、140份backend/真实链源码一致性、L/M全部证据和宿主跳过边界均已独立复核。所有finding闭环，无遗留。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足。13/13 AC完成，完整门禁L、最终普通门禁M与code/test最终独立review均通过。
- 测试：L 与最终并发 M 均通过；后端 unit 1654 passed / 0 failed，integration 178 passed / 0 failed / 18 host skips，frontend 499 passed / 0 failed，contract 257 passed / 0 failed / 1 policy skip；设计 lint/check、类型与构建、协议、requirements、五镜像包检查通过。全仓 Markdown、新增/重写脚本与回归 Ruff、diff whitespace 检查通过。
- 黑盒：真实 Docker/Chrome E2E 103 passed / 0 failed / 2 optional probe skips；独立真实引擎 2 passed / 0 skipped，内部 chain 16 passed，L0–L6 完整；独立 Chromium 与目标引擎容器补充集成链 18 passed / 0 skipped。五镜像原生上下文 5 passed，双进程锁与真实活跃容器/网络保护已验。
- review：Round1 code/test均FAIL，5条finding全部修复；Round2 code/test均PASS，无新finding，两轴13/13 AC独立复核成立。代码轴102、测试轴147项独立验证通过，最终scope=c899ece7b48f99a1。
- AC 判定：见 `task.md` 13 项逐条打勾。

### 结果摘要

- 完成门禁 venv/checkout 锁、运行归属与安全清理、用例下限、evidence 接线、镜像身份与平台 marker、按需镜像前置、严格停止断言、原生 Dockerignore 白名单、artifact 路径边界与隐私扫描。
- 真实探针修正旧 socket / instance / HTTPS Origin 夹具；真实 E2E 修复 Docker 配置代理污染、本地 GeoIP 外部依赖与双配额生产者竞争。保留原断言与超时。
- 当前 tracked 树及未忽略新文件无开发者家路径；历史文档仅脱敏，不重写 Git 历史，无隐私豁免。
- 环境跳过：宿主 integration 18 项（容器 18 项全部补验）；默认 E2E 两项探针（独立 real_engine 全部补验）。另 contract 1 项因项目显式策略不适用而跳过，不属于环境失败。
- 无未闭环来源 pending；p051/p063 原已归档，保持状态。未执行其它 task，未合入 main。

### 长期文档闭环

- `docs/specs/gate_verification.md` 累积 t060 行为，`docs/specs_index.md` 已登记 t060。
- `docs/blueprint/testing.md` 更新锁、归属、收集下限、镜像前置与目标环境；`security.md` / `conventions.md` 声明隐私口径。
- 原生 Dockerignore 结论登记 `docs/findings/d037_dockerignore_leaf_allowlists.md`；无新 spike。
- `docs/handoff.md` 旧节迁入 archive，仅保留本轮一节，branch 与 head_commit 经写入时 Git 查询核对。

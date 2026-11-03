---
tid: "t024"
slug: "delivery_verification_evidence"
title: "收敛产品交付与验证证据体系"
status: "done"
branch: "t024_delivery_verification_evidence"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "597c09aff927c8cc54f72bfc405ac0336d58e22e"
depends_on: "t023"
conflicts_with: "t019,t020"
note: "review_20261103_185924：A1/A23-A30/A32/A33/A35/A38/A43/A50-A53；仅产品工具和测试，不整改 repo_template"
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

2026-11-03：用户授权按职责合并立项，本 task 为 53 项采纳结论中 18 项的唯一主承接；完整范围与 AC 对应见 task.md。现有 t019/t020 保留，原 A36/A37 拒绝；本轮未 start、未实现、未跑业务测试。

创建验证：`task.py preflight t024 --creation` 为 PASS；工作区未提交提示属于本批新建文档。另有 A27/p019 路径依赖标为 `UNVERIFIED-SPIKE`，须保留原断言定位根因再回填。

2026-11-04 执行（attempt 1 / execution_id ec541ab6 / owner exec-main-20261104-t024，base=t023 分支 597c09a）：

- 环境：本机无 uv、无 Docker；用 .scratch/t024/venv（py3.12 + 与 run_gates 相同的依赖集合）跑 pytest；模板契约的 TMPDIR 必须在已登记 worktree 之外（testing.md 既有警告），用 /tmp/cbt024-tmp。
- 基线（改动前）：模板契约 169 passed（TMPDIR 在 worktree 内时有 2 条 .env 隔离伪报，移出后全过）；unit/integration/前端基线见收尾报告（与前序口径一致的存量失败同 ID 对照）。
- 用户既定指令：Docker/真实 Chrome/用户局域网依赖的黑盒确实跑不了时跳过按 pass 计，真实环境义务立 pending（p021–p026 先例）；本 task 的镜像构建与真实媒体类验证按此办理并逐条注明。
- 实施顺序：AC-001/010/012 快速项 → AC-016/003 stamp 与探针接线 → AC-017 隐私守卫 → unit/integration 测试收敛（A25/A26/A27/A28/A29/A43 可本机验证部分）→ e2e 代码收敛（A25/A26/A28/A33/A43/A53，collect-only 验证）→ AC-015 Stream 镜像分阶与 pydantic 对齐 → AC-009 门禁锁 → AC-002/013 文档与勘误（含 p019 spike 定位回填）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

Round 1（双路 FAIL，code 8 条 / test 10 条）+ Round 2（双路 PASS，test 新发现 f011）+ Round 3（双路定向 PASS），逐条处置：

|finding_id|status|fix_ref|
|---|---|---|
|t024_code_f001|已修|handoff 归档追加后重新登记指纹，守卫复跑通过|
|t024_code_f002|已修|AC-001/AC-015 标未验证（trust_prior），静态套件标注预检，义务 p027|
|t024_code_f003|已修|busy_timeout 长锁上界恢复 anchor 原值|
|t024_code_f004|已修|隐私豁免改 (path, sha256) 双绑定加路径错配合成用例|
|t024_code_f005|已修|18 条 AC 按真实状态打勾，收尾报告重写|
|t024_code_f006|已修|FakeDockerAdapter 落地并被采用，契约对照新增，死导出删除|
|t024_code_f007|已修|freshness 钩子按实际消费套件触发，加非消费负例|
|t024_code_f008|已修|REQUIRED_DIRS 拒绝 src 缺失，加生成侧负例|
|t024_test_f001|已修|同 t024_code_f001，守卫复跑 8 passed|
|t024_test_f002|已修|同 t024_code_f004|
|t024_test_f003|已修|同 t024_code_f002（AC-001 部分）|
|t024_test_f004|已修|同 t024_code_f002（AC-015 部分）|
|t024_test_f005|已修|三处时间上界逐字恢复 anchor 原值|
|t024_test_f006|已修|conftest 加载改 __file__ 锚定，仓外复跑 12 passed|
|t024_test_f007|已修|同 t024_code_f006（契约对照 3 passed）|
|t024_test_f008|已修|勘误 t009 路径改归档实际路径|
|t024_test_f009|已修|wait_until/wait_until_sync 超时补 last 观测|
|t024_test_f010|已修|容器路径例外改段边界匹配，加负例|
|t024_test_f011|已修|契约对照改经 SDK ContainerCollection 双侧断言，Round 3 确认|

Round 2 复审见 review_code.md / review_test.md 的 Round 2 段（最终结论以 check_review_status 为准）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：已实施，18 条 AC 全部打勾；其中 AC-001、AC-015 为 trust_prior（静态预检通过、真实构建验收未验证，义务 p027），其余 16 条有本机实测证据（见下）。
- 测试：模板契约 169 passed；unit 749 passed / 1 skipped / 0 failed（基线两条失败 repo_hygiene、terminal_storage_failure 已由本 task 的 AC-017/AC-005 修复消除，属基线改善）；integration 114 passed / 2 failed（test_api_search_defaults_routes::test_retry_route_requires_csrf_and_maps_outcomes 为改动前基线同 ID 存量失败；test_runtime_coordinator_integration::test_ac009 为全量负载旋转失败、单独重跑通过——与干净 base 同 ID 对照零新增）；前端 Vitest 162 passed、test:types 零错误、生产 build 通过且 postbuild freshness 校验通过；E2E collect-only 102 tests；git diff --check 干净；改动 Markdown 经 md_format --check 一致（md_kx 以 uv tool 装于 worktree scratch 后执行）。
- 黑盒：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 依赖 Docker/真实拓扑，本机无 Docker，按用户 2026-11-03 口径跳过按 pass 计；义务由 p021–p024、p026 与本 task 新立 p027 承载。
- review：full review 三轮——Round 1 双路 FAIL（code 8 / test 10）→ 全部处置（进度 5）；Round 2 双路 PASS（test 新发现 minor f011）；Round 3 定向双路 PASS（f011 与 ice_config 锚定增量确认）；check_review_status overall=PASS、review_scope=ok（round=3）。
- AC 判定：见 `task.md` 行内打勾；逐条证据等级：AC-001 trust_prior（p027）、AC-002 re_verified（文档逐项对照 + reviewer 抽查）、AC-003 re_verified（freshness 12 passed + 三消费点）、AC-004 re_verified（integration 真实 gateway app 断言；完整客户端链 trust_prior 于拓扑套件）、AC-005 re_verified（精确断言逐项落地；E2E 实跑 trust_prior）、AC-006 re_verified（normal_exit 4 用例 + 跨目录复跑）、AC-007 re_verified（deadline 等待改造 + 原时间上界恢复后复跑）、AC-008 re_verified（docstring/注解与覆盖逐项对应）、AC-009 re_verified（run_gates 以锁 + Python 3.12 空缓存全量重建实测：契约 169、unit 749）、AC-010 re_verified（entrypoint 4 passed）、AC-011 re_verified（前提作用域/权限/脱敏代码与用例；真实容器执行 trust_prior）、AC-012 re_verified（唯一权威 + 无消费者 grep）、AC-013 re_verified（勘误数字双路复算一致）、AC-014 re_verified（clock 注入/共享替身契约对照 3 passed/wait 最后观测）、AC-015 trust_prior（p027）、AC-016 re_verified（stamp v2 用例全绿 + build 后 freshness 实证）、AC-017 re_verified（守卫 8 passed 含双绑定与边界负例）、AC-018 re_verified（pin+manifest 双校验实跑通过、计数器与样本字段落地；真实性能 E2E trust_prior）。

### 结果摘要

- 交付：门禁依赖锁（gate-requirements + Python 3.12 pin）、stamp v2 与三消费点校验、隐私守卫重写（双绑定豁免）、Stream 镜像分阶、测试等待/时钟/替身收敛、文档同步与独立勘误、p019 根因定位（d027）并关闭。
- 遗留：p027（AC-001/AC-015 真实 Docker 构建验证）；p017 余两项代码清理未开；p016/p018/p025 未动；t019–t023 真实环境义务 p021–p024/p026 未验收。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

### 2026-11-04 实施进度 1（AC-001/010/012/003/016/017/015 静态侧）

- AC-001（A1）: supervisor Dockerfile.dockerignore 补 `!src/backend/cbrowser/launch_args.py`；新增 tests/unit/test_docker_build_contexts.py（存在性 + dockerignore 准入近似匹配器），4 passed。
- AC-010（A32）: browser entrypoint 新增 `--help|-h` usage（任何副作用前）；tests/unit/test_browser_entrypoint.py 4 passed。
- AC-012（A35）: 核对消费者后 `git rm config/.env.example`（无代码/脚本/compose 消费者；deploy_v2.sh 自生成 config/deploy/compose.env；引用仅存于冻结 review 报告）；根 .env.example 为唯一权威。
- AC-016（A51）+AC-003（A24）: scripts/verify_frontend_dist.py stamp 升 v2——记录声明输入集（REQUIRED index.html/package.json/package-lock.json 缺失即拒绝生成；CONFIG 五件套 present/absent 均入集；src/+public/ 全量逐文件 sha256；Vite 根 .env\* 按其加载约定入集；进程 env 仅 ENV_VALUE_ALLOWLIST（当前为空）记哈希）。verify 比较文件集+逐文件哈希+env+组合摘要。conftest 改为 e2e 树内 dist 存在即校验（不再按文件名）；frontend_app_probe 与 frontend_probe/host_builder 在复制/托管前调用 verify。freshness 测试扩至 10 条全绿。
- AC-017（A52）: test_repo_hygiene 重写——模式扩 macOS/Linux/Windows（双分隔符）+/root/ 全路径 token；固定容器路径精确例外 `/root/.config/google-chrome`；文本分类改全量 UTF-8 解码（NUL 不再整份豁免，未知二进制后缀 fail-toward-scan）；删除 docs/archive/ 目录级跳过；豁免改为内容指纹绑定（review_privacy_allowlist.txt 57 条 `path sha256:<hex>`，含 20261103 两份基线文件——原基线失败 test_tracked_files_do_not_leak_developer_home_paths 转绿）；合成样本以片段拼接避免守卫自指。6 passed。
- AC-015（A50）静态侧：stream Dockerfile 改 builder/runtime 分阶（toolchain 与 -dev 只在 builder，venv 整体 COPY；runtime 仅运行时库）；stream requirements pydantic 2.14.1→2.14.2、pydantic-core 2.50.1→2.50.2 与其余 runtime 对齐；新增 tests/unit/test_runtime_image_hygiene.py（分阶守卫 + 全 runtime pydantic 一致性 + stream 锁覆盖 stream_agent 第三方 import）4 passed。冷构建与真实媒体/输入/剪贴板验证属 Docker 门禁，按用户口径跳过并立 pending（收尾时建）。
- 前端依赖：worktree 内 `npm ci` 已完成（node_modules 就绪），前端门禁收尾统一跑。

### 2026-11-04 实施进度 2（AC-009 门禁锁、AC-006 spike、测试收敛 unit/integration 批）

- AC-009（A30）: 新增 scripts/gate-requirements.txt（61 行全 pin 锁：CPython 3.12 下以 run_gates 原 --with 并集解析后 pip freeze，含重生成命令注释）；run_gates.sh 改为单 venv 从锁安装后依次跑契约/unit/integration/前端/E2E，不再临时解析未 pin 包组。新脚本空缓存全量验证在 .gate-t024（盘上 scratch；/tmp 为 512MB tmpfs，uv 解压 playwright 时曾爆盘，属环境限制）后台执行中，契约层已回 169 passed。
- AC-006（A27/p019）spike 已定位并回填 task.md 未知契约清单：根因是 AF_UNIX sun_path 上限——agent 经 CWD 相对路径 bind，.scratch 相对路径 89 字符可绑定、tmp_path 151 字符 bind 报 "AF_UNIX path too long" 静默失败、短临时根 91 字符可绑定（同机实测三组数字）。test_normal_exit_replay 改带 finalizer 的 short_data_root fixture（dir=/tmp 短根），四用例原收敛断言全绿；模块 docstring 场景 3 改为实际的双 Profile 隔离、补场景 4。
- AC-004（A25）integration 部分：FakeApiService 授权键改 (cookie, origin, profile_id) 默认拒绝、与恢复 lane 的 FakeGatewayApiClient 同契约（生产已无 automation-authorize 端点，该半项按当前生产面收敛）；test_supervisor_gateway_client 新增对真实 create_gateway_app 的 401/503 精确断言，wire stub 明确降为传输层用例。gateway control/signaling 22 passed。
- AC-005（A26）部分：event cursor 的 \_core 改 asynccontextmanager（客户端在测试期保持打开）、游标断言改精确 e2.json；artifact ownership 改具体 ArtifactError 类型断言；gateway_config 短密钥测试先建 valid-length dummy.txt；terminal storage failure 改 seam 注入（save_state/save_runtime_event 打桩抛 StorageError），chmod 变体仅 euid!=0 时跑——本机为 root，该基线失败由此消除；busy_timeout（AC-018/A53）改结果断言+派生宽松界（短锁 \[1.0,5.0)、长锁 \[4.5,15.0)）。
- AC-006（A27）其余：entrypoint/schema 读取改 __file__ 锚定（selkies tokens、file transfers、runtime protocol 三处）；transport hardening 固定端口 18491 改 bind 0；test_v2_api_subprocess 的 SCRATCH_DIR 改 module fixture（导入期零副作用）+ OpenAPI 解析缓存；\_short_root（automation_cdp）改带 finalizer 的 fixture。
- AC-014（A43）部分：LoginRateLimiter 与 LiveCapturePolicyAgent 增加注入 clock（默认 time.time/time.monotonic，生产行为不变），两测试改局部 callable、不再 patch stdlib time 模块对象；auth 大测试 test_viewer_and_automation_authorize 拆为 9 个独立行为测试（共享 \_profile_with_session 工厂、删中段重复 import）；profile copy 的 \_context 返回 session_maker（23 处解包同步更新），不再穿透 repo.\_session_maker；recovery snapshot 的 dict-as-callable 改显式 \_CoreStub；download_reconciler 删 4 处局部重 import、stream_resume 删重复赋值。
- AC-007（A28）：三处固定次数轮询改走 tests/fixtures/wait.py 的 wait_until/poll_until（deadline+最后观测）；runtime_agent 健康并发改区间重叠结构化证明；WAL 读并发改“锁仍被持有”结构断言+busy_timeout 派生界。
- AC-008（A29）部分：test_supervisor_core docstring 只列本文件实际两条、其余指向真实覆盖文件；normal_exit docstring 已同步。

### 进度 3（2026-11-04，e2e 细目与共享替身）

- AC-011（A33）收尾：gateway_probe topology 给 harness work_dir 加 0o700 父级封顶（data/metadata 子目录因容器异 uid 挂载保留 0777 并注明）；test_mitshm.c 的 IPC_CREAT 0777 改 0600；evidence.py 脱敏标记集加 session、默认证据目录改每次运行私有 mkdtemp（保留 CBROWSER_E2E_EVIDENCE_DIR 覆盖）。
- AC-004（A25）收尾：stream_monitor 的 quota 投递改经生产协议类型 GatewayControlEnvelope/SupervisorQuotaPayload 构造（不再手搓信封）；web_lock_shim.js 缺 tab id 行为与生产 adapter 对齐为创建+持久化（原 1008 关闭与 adapter.ts 相悖），两 shim 均加「协议探针、非 adapter 覆盖」标注；GatewayMockServer 更名 GatewayProtocolMockServer 并注明真实 Gateway 由拓扑套件覆盖；AC-010 emulated 测试更名为 server-side semantics 并在 docstring 写明不覆盖生产 Agent 转发链。
- AC-005（A26）收尾：AC-008 正向检查改走最小有效 HELLO 交换（先 /api/tokens 建 controller token，断言 TEXT HELLO server 帧），不再接受 CLOSE/CLOSED；ac001 case 3c 改精确 403（已认证未授权的生产语义，503 不再可满足该用例）。
- AC-007（A28）收尾：browser_runtime 两处健康检查 sleep(1.0) 改 poll_until（5s 上界）等 degraded 实际到达；rearm 的 sleep(1.5) 删除，由恢复下载落地断言自证；supervisor_core_e2e 两处 range(50) 注册等待、offline_recovery 的 range(50) 收敛等待均改 poll_until（deadline+description）；startup_recovery 模块 docstring Case 3 已按 A1 实际语义改写；retry suite 与 policy_failure 的 real_api_server 四元组注解已同步。
- AC-014（A43）收尾：新建 tests/fixtures/docker_doubles.py 为唯一共享 DockerAdapter 契约替身，test_supervisor_observation_authority.py 的极简 \_FakeDocker 已迁移（保留其 PathValidator 接线）；test_normal_exit_replay.py 与 unit 的 \_FakeDockerAdapter 为带真实状态机/PathValidator 的特化模型，保留并以本条说明。
- AC-018（A53）收尾：test_frontend_session_vendor.py 在保留 pin 字面断言（变更报警）之外新增 vendored 树对参考 manifest 的实际 verify_manifest 校验（allow_patched=True，vendored index.html 为设计内注入）；adapter_probe 增加 per-type 计数 \_\_sentDataChannelCounts 与 \_\_droppedDataChannelMessages，app e2e 的 no-resize 断言加计数器伴随断言（键 'r'）；性能预算保持原硬阈值（first frame 8000ms、input 3000ms，不改中位数/不重试），证据补完整 perf_samples 与 datachannel_counts。

### 核实不适用清单（以现行树复核为准）

- A43_12（policy failure 的 dummy 端点注入）：全仓 grep 无 /trigger-policy、/dummy-category、/dummy-type 端点；现行政策失败路径由专用测试镜像 CBROWSER_INVALID_POLICY_TEST_IMAGE 驱动，无可标注的注入端点。
- f_int_03（test_v2_api_receipts 的 FakeDockerAdapter）：该文件已不存在于现行树，无残留同名替身（unit 的 \_FakeDockerAdapter 属 normal-exit 特化模型，见 AC-014 说明）。
- A53/f_sf_10（wiring 测试 fake npm）：现行 test_frontend_build_wiring.py 已按 finding 处方断言 package.json 脚本的精确字符串，无 PATH shim。
- f_int_06 余项：normal_exit 对 core.ports.\_allocated/core.\_sessions 的私有断言无公开状态面可替代（SupervisorCore 未暴露等价只读视图），保留并在此记为部分处置；unit_sup_07 的私有 seam 耦合除已完成的 wait/clock 注入外，其余断言级耦合保留，理由同上（无公开面）。

### 进度 4（2026-11-04，文档收敛与勘误）

- AC-002（A23）：docs/handoff.md 旧节已追加到 docs/archive/handoff.md，新节按实况重写（main c7ec89b、t019–t023 分支与 commit、p016–p019/p021–p026 状态）；findings d003/d009/d010/d012/d018/d019/d021/d022 各追加「ADR 013 已删除该机制、仅作历史事实」标注（原文不改）；artifacts.md 删 chown 回退改 ADR 014 口径、domain.md 状态图 failed 改 error（同为 p017 文档项，p017 已注记进展、余两项代码清理仍未开）；v2_architecture_plan.md 文首加 ADR 013 修订条目并在 §3/§7.5/§10.4–10.6/§16/§19.4 逐节加「已被替代」标注；architecture.md 旧 UI 移除归属改 t017（注 t011 已并入 t010）、Selkies 依赖行改同机直连口径；webrtc_remote_display.md 删适配层「处理 RTC 配置」表述；生产 docstring 两处已改（run_database_migrations 的 WAL/busy_timeout 归属、PortAllocator 的 asyncio-safe 与快照语义）。
- AC-013（A38）：新增 docs/reviews/review_20261102_201727_errata.md，全部数字实算：交叉证伪 33 条（bundle_cross_validation.md 逐行计数，30 为合并说明笔误）；adoption 附表主映射复算 362 条全量、A13 主映射 4 + 组合 1 = 5 条（f_archive_reviews_04 所述 6/≥8 在该文件无法复现、「62 条子项」无出处，均标未知）；serve_spa 核实等级以静态确认为准（reproduced 陈述无独立证据标未知）；4 份截断 bundle 列路径+sha256 指纹；Gaps=单元覆盖、Limitations=方法限制的用语说明；t009 AC-005 coturn 项在勘误 §6 指向 ADR 013 替代关系（原 AC 不改）；s011 合成 visibility 与外部 fixture 依赖范围、冻结 benchmark 指向 ADR 012 的旁注均在勘误内。decisions.md 已加「产品历史勘误入口与 ADR 传播约定」。
- 账本：p019 经 pending.py archive 关闭（resolution=resolved，根因 d027）；新建 findings d027（AF_UNIX sun_path 长度上限实测结论）；新建 pending p027 承载 AC-001 隔离 Docker 构建与 AC-015 Stream 镜像冷构建+真实媒体验证义务（本机无 Docker 跳过，按用户口径立项追踪）。

### 进度 5（2026-11-04，full review 第一轮处置）

第一轮双路 review 均为 FAIL（review_code.md 8 条、review_test.md 10 条，多条同根）。逐项处置：

- 守卫失效（code f001 / test f001，critical）：AC-002 的 handoff 归档追加改变了 docs/archive/handoff.md 字节、其指纹豁免按设计失效而未同步登记。已把追加后内容作为新的已批准存量重新登记指纹（批准依据：追加节经 grep 核对不含开发者路径、其余字节为原已批准存量），守卫复跑 8 passed（见下条双绑定后的口径）。
- 豁免双绑定（code f004 / test f002，important）：豁免键改为 (path, sha256) 对，路径错配不再豁免；补「同内容、不同路径不豁免」合成用例。归档移动时须在同一变更内同步改登记路径（守卫 docstring 已写明）。
- 容器路径例外边界（test f010，minor）：/root/.config/google-chrome 例外改路径段边界匹配（token == prefix 或 prefix + "/" 前缀），补两条同前缀异目录负例。
- busy_timeout 阈值（code f003 / test f005，important）：进度 2 的「派生宽松界」处置撤回——三处时间上界（短锁 1.4\<=elapsed\<4.5、长锁 4.5\<=elapsed_timeout\<=6.5、WAL 读者 \<1.0）已逐字恢复 anchor 原值，WAL 的结构性锁持有探针保留；test_v2_api_subprocess 单独复跑 9 passed。
- AC-006 跨目录失败（test f006，important）：test_frontend_build_freshness 的 collection-hook helper 以 CWD 相对路径 runpy 加载 e2e conftest，改 __file__ 锚定；从 /tmp 以绝对路径复跑该文件 12 passed。
- AC-001/AC-015 证据等级（code f002 / test f003、f004，important）：两处静态套件 docstring 已标注「STATIC PRECHECK ONLY，非 AC 验收证据」；AC-001/AC-015 在收尾报告中如实标为未验证（trust_prior），验收义务由 p027 承载，不以静态守卫冒充。
- 共享替身契约（test f007 / code f006）：docker_doubles 补齐 FakeDockerAdapter（生产同前缀命名 cbrowser-t005），observation_authority 改用之（3 passed）；新增 tests/unit/test_docker_doubles_contract.py 把共享替身与真实 DockerAdapter 做命名/集合语义对照（3 passed，真实 adapter 以 FakeDockerClient 注入构造）；FakeDockerClient 与 fake_docker_client() 现均有真实调用方，未用的 find_free_port 导出已删。
- collection 钩子范围（code f007，minor）：freshness 钩子改按实际消费 dist 的套件触发（源码含探针 harness 标记判定，与文件名无关），非消费套件不再被陈旧 dist 阻断；freshness 套件补非消费负例（12 passed）。
- stamp 必需目录（code f008，minor）：verify_frontend_dist 增加 REQUIRED_DIRS=("src",)，源码目录整体缺失与必需文件缺失同等拒绝生成/校验；补生成侧负例。
- wait 最后观测（test f009，minor）：wait_until/wait_until_sync 的超时错误补 last= 最后观测值，与 poll_until 同口径。
- 勘误路径（test f008，minor）：勘误 §6 的 t009 路径改归档实际路径 docs/archive/tasks/t009_v2_full_acceptance/task.md。
- 门禁解释器（test 侧未进表提示）：run_gates.sh 的门禁 venv 改 pin Python 3.12（与 gate-requirements 锁的冻结解释器一致），不再用 ">=3.12" 浮动。
- 文档格式：本机原缺 md_kx（doctor_cmd 前提），已以 uv tool 在 worktree scratch 内装好并对全部改动 Markdown 跑 md_format --check；我引入的 4 个文件格式漂移已格式化修正，anchor 版式未动。

### 进度 6（2026-11-04，Round 2 后增量）

- Round 2：双路 PASS（code 0 新发现；test 新发现 minor f011 一条，已修见 Review 处置）。code 侧未进表观察：tests/unit/test_stream_ice_config.py（t019 交付）仍以 CWD 相对路径读 entrypoint，仓外运行 2 条失败——与 AC-006「测试可从其他工作目录运行」的口径直接相关，已按同模式改 __file__ 锚定，从 /tmp 复跑与契约对照合计 7 passed。此增量与 f011 修复均在 Round 2 指纹之后，Round 3 定向复审只核这两处增量。

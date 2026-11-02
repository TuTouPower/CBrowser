# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T08:01:12+08:00 最终完整门禁仅协调器清理失败，保持源码未提交

### 状态与授权

- branch main；head_commit `950891fe6e4d7bdbc0b2f95079535c2d22c1a7ed`（本文单独提交）。完整附件目标 active，用户“不需要创建task 直接改”“继续”授权持续。本地 merge 已授权，不 push，不创建新 canonical task。
- t001–t007 done/integrated；t008 → t013 → t014 → t009 → t010 → t011 → t012 仍 backlog 无 attempt。基线全绿后才启动 t008。自有八 worktree，base/diff_anchor a673edf；源码尚未 commit/merge。
- Master 为 baseline_fix，validation 为独立实跑环境，主仓证据 `.scratch/v2_baseline_20261101/`。

### 本轮完整门禁实际结果

- final_round1 已自然结束，driver PID 62095 已退出；66 步中唯一失败 test_runtime_coordinator_e2e，所有其它步骤 PASS。validation 完整 binary diff 与 combined_candidate_r6.patch 字节一致，冻结校验通过。
- 六个新镜像、四入口 import、契约169、unit445、integration66、legacy384、Vitest112、vendor/build/verify、四 schema 与前端类型零漂移、完整默认 Ruff 联合 E/F/W/I、md_format、旧服务健康全部 PASS。
- 实际 E2E 覆盖完整42模块清单：Runtime13 PASS；全部 Stream、Supervisor、Gateway 与 frontend 模块 PASS，唯 runtime_coordinator 模块失败。frontend app5/203.30s、media4/92.28s、session3/89.64s PASS；本机 TURN relay 正负例 PASS，公网穿透仍 USER_WAIVED。
- 协调器 E2E 所有业务断言完成，finally 清理 stream/browser 时各收到一次 Docker APIError，汇总 RuntimeError 使测试失败；当前日志只有异常类型，尚未确认 status_code/是否并发删除。不得将推测当根因或忽略异常制造绿。原始完整日志 final_round1/test_runtime_coordinator_e2e.log；下一步实际调用透明探针记录规范化 Docker 错误元数据。
- driver 没有检测到新标签容器/网络残留；结束后 docker ps -a 按 com.cbrowser.prefix 标签检查无对象，旧生产与其它项目未动。失败阶段日志保留，不覆盖重跑。
- unit 初跑 1 条 Python3.14 asyncio transport 析构警告（另6条旧 Starlette 弃用警告）；root 开启 asyncio debug、将 Unraisable warning 转错误，focused40 与 full445 都 PASS，未复现。保留原警告，不宣称根因已修复。

### 最终测试维护增量与独立核查

- Master 当前 combined_candidate_r8.patch，SHA `fa2a5d451ada2d51e8ab261eca92a6be0310a831d7f209e497dd012eea225920`。相对完整实跑 R6，仅 tests/e2e/test_supervisor_container_graph_e2e.py 改动，生产与其它测试字节不变。
- root 全范围 AST 审计发现容器图清理重写移除原动态资源归属断言，且旧 node 就地替换18097预期。已明确替换新 node，保留R6所有48条assert，新增归属校验。校验识别已知基础设施；其余动态对象须 cache-init 或 profile-id 属当前集合。未知归属跳过日志读取/stop/remove，继续清理其它自有对象后统一失败。
- actor 两轮 CLI 均真实0，范围外无 untracked；R1 报告哈希未计算且与现场不符，root 不采信，审计 container_graph_report_hash_audit.json；R2 真实 hashlib 计算与 root 一致，最终单文件 SHA `b175b7d2f94b63966b669f33bcdd4e5a4758429f5880ca46ea1b7dcadd969c2b`。报告均保留；source R7→R8 严格只有一行 continue。
- root 最终容器图实跑 driver PID 68906，fix_dispatch/verify_container_graph_r8.py，输出 focused_container_graph_r8/，正在运行。外层Docker互斥，使用R6新不可变镜像（生产字节一致），含完整Ruff、diff与源码冻结、新标签资源检查。尚未宣称 PASS。
- control_plane_final_r8：doctor contract collect、md_kx、task list、repo_sync status 均 exit0。没有改队列或工具链。
- 34 production 文件组件仍 `ec55eddb322960a243fad109e7536411c1c3c362def265eaf951825bda533fd0`，独立 review R2 PASS。root 修正证据边界：元数据探针仅验证无效内容等待/取消，不证明延迟有效 Producer/live-CDP 转换；该精确转换 NOT_RUN，普通真实启动由 Runtime E2E另证。纠正在 backend_review_r2_controller_evidence_correction.json。

### 下一步

- 等最终容器图实跑结束；在同一外层锁下重现协调器清理失败并记录实际 Docker APIError status/规范化原因，定位后只修相关 fixture 生命周期，保持业务断言。root 主控复跑与增量 review；禁止把清理错误直接吞掉。
- 全绿后才 baseline 单执行 commit、本地 merge；备份各自 scratch、规范 worktree remove/prune 后再既有 t008。全部外部actor当前终止；不覆盖 validation 的R6冻结现场。
- 既往配置缺陷与工具审计详见前节及 scratch：wrapper exit、不覆盖新增文件的 SHA guard、意外 uv.lock、报告权限拒绝后绕写、复制代码伪证、database locked 有限重试；未改 .repo_template 或工具链。
- 剩余七 task、容量/P95、8小时/1000次 IME/1000次 clipboard、旧链路移除、正式Compose部署与Chrome黑盒均未完成；仅公网TURN/原生Linux x86 USER_WAIVED。

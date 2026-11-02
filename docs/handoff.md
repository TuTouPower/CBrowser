# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T08:06:31+08:00 清理竞争真实RED确认，限定两处fixture停机顺序修复

### 目标与状态

- branch main；head_commit `bdf13b37aa850929e890ea1be30cf978ab849827`（本文单独提交）。完整附件目标 active，用户直接改/继续授权持续，不创建新 canonical task、不 push。本地 merge 预授权。
- t001–t007 done/integrated；t008 → t013 → t014 → t009 → t010 → t011 → t012 仍 backlog 无 attempt。基线完整绿后才 t008。八自有 worktree，base/diff_anchor a673edf，源码仍未 commit/merge。
- Master baseline_fix 仍R8，SHA `fa2a5d451ada2d51e8ab261eca92a6be0310a831d7f209e497dd012eea225920`；validation 保留R6完整门禁冻结快照。证据均在主仓 `.scratch/v2_baseline_20261101/`。

### 完整门禁与补充失败证据

- final_round1 自然结束：66步唯一 runtime_coordinator E2E 清理阶段失败。六新镜像/四import、契约169、unit445、integration66、legacy384、Vitest112、完整前端build/vendor/verify、schema/TS零漂移、Ruff全默认联合E/F/W/I、md、旧服务健康全部PASS；42个E2E模块中其余41模块PASS，所有源码冻结校验通过。
- 补跑R8容器图（仅测试维护增量，生产不变）失败：全部业务断言完成，finally报 network_not_empty；留下当前profile Browser一个、其网络一个。root核对exact prefix、managed-by、role、profile目录、网络端点，先保存 owned_residual_before_cleanup.json 与日志，再精确清除两对象。保留 manual_owned_cleanup.json，未碰其它资源。R8完整Ruff0、source_unchanged=true。
- root透明观测真实DockerSDK调用复现协调器原失败：focused_runtime_coordinator_probe_r1，真实remove两次APIError均 status409，规范化标记 already in progress/removal。调用时序证明先删除Browser/Stream，后停止Supervisor，和活控制器并发删除。该探针无返回替换/无业务mock，异常原样重抛，rc1，资源最终全部消失。原始 docker_calls.jsonl 与 e2e.log 保留。
- 根因范围为测试fixture停机顺序：控制器尚活时就枚举/拆除动态资源，既可撞正在删除，也可漏后续新建资源。修复只限两测试文件，不能吞409或放宽断言。
- 前一阶段unit析构警告保留：asyncio debug+Unraisable warning转错误的focused40/full445复跑均PASS，仅旧Starlette弃用警告；不宣称警告根因修复。

### 唯一活跃actor

- fixture_quiesce_round1 dispatch PID69883，lane normal_exit_fix，wt CBrowser_normal_exit_fix，session ses_e673e0f0effe9KPUz1QJsFoZ3B。实际CLI PID见wrapper日志，不以外层exit推断成功。
- 仅写 tests/e2e/test_supervisor_container_graph_e2e.py、tests/e2e/test_runtime_coordinator_e2e.py 与自身scratch报告。两文件派发前与MasterR8字节相同；其它源码受SHA guard保护，新文件另核untracked。
- 指令：枚举清理前先有序停止已跟踪且prefix/role核对的API/Supervisor控制器；等待真实停机，阻塞SDK offloop；未知归属仍保留并最后报错；尽力清理其它自有资源并传播错误。若仅API意愿ACK，须等待实际NotFound才算删除完成。禁止固定sleep、忽略409、改业务预期、生产改动或扩展工具框架。
- actor禁止Docker/Chrome（root独占外层锁），实际跑限定Ruff/compile/AST保留检查，真实E2E标NOT_RUN。报告 `.scratch/normal_exit_fix/fixture_quiesce_report.md`；所有哈希必须真实计算。日志 fix_dispatch/fixture_quiesce_round1.\*。
- 当前root Docker driver全部终止；下一次先核标签残留为空、锁可取得，再实跑最终两文件。禁止改validation旧冻结现场或覆盖失败日志。

### 仍有效的审查与后续

- R8节点替换及归属校验保留全部R6的48条assert，新增一条；未知动态role/profile跳过日志读取/stop/remove。R1报告编造哈希未采信，R2真实hash与root一致，单文件b175b7d2f94b63966b669f33bcdd4e5a4758429f5880ca46ea1b7dcadd969c2b。
- 后端34文件组件ec55eddb322960a243fad109e7536411c1c3c362def265eaf951825bda533fd0独立review R2 PASS。元数据探针只证无效内容等待/取消，精确延迟有效Producer/liveCDP转换NOT_RUN；普通Docker启动有Runtime13实跑另证。修正backend_review_r2_controller_evidence_correction.json。
- control_plane_final_r8四项doctor/control-plane检查均0。既往工具缺陷审计保留于前节/scratch，未改 .repo_template、guard或wrapper。
- actor交付后只按两文件base核对采纳，root独立review/实际串行E2E，必要时透明Docker观测确认无竞争；最终生产未变可使用本轮不可变镜像，须明确新测试候选SHA与增量证据。
- 全绿后baseline单执行commit、本地merge、备份scratch并规范worktree remove/prune，仅main后再既有t008。剩余七task、8小时、1000次IME/clipboard、容量/P95、旧路径移除、Compose正式部署/Chrome黑盒仍未完成；公网TURN/原生Linux x86仅两项USER_WAIVED。

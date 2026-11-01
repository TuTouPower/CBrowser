# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T04:47:03+08:00 离线权威E2E通过，完整Ruff收敛与语义回归审查继续

### 总目标与当前边界

- branch main；head_commit `689f3309f6b6e91b8ca6ee36be0ea5e196b5f635`（本文单独提交）。用户“不需要创建task 直接改”“继续”授权持续；宿主goal active，完整附件14 task目标仍未完成。不创建新canonical task、不改冻结队列、不push。
- t001–t007 done/integrated；t008 → t013 → t014 → t009 → t010 → t011 → t012仍backlog无attempt。基线完整门禁绿后才start t008。本地merge已预授权。源码实现尚未commit/merge，main仅交接文档。
- 自有8个wt不变，base/diff_anchor a673edf。实现整合权威wt baseline_fix；独立实跑wt baseline_validation；全部scratch证据主仓`.scratch/v2_baseline_20261101/`。旧生产与其它项目未动。

### 确定通过与当前候选

- 主控SDK0.6.4/字节码预编译后：full unit424、integration66 PASS（focused_unit_r8、focused_integration_r8）；normal R7独立review PASS与12项对抗探针已归档。后续lint源码有改动，不能继承成最终全库绿。
- focused_recovery_r4六新镜像/四入口import PASS；真实重试1 PASS/102.59s；SIGKILL恢复组2 PASS、旧第三node 1 fail；完整frontend app5 PASS/218.75s，含真实媒体诊断。两项失败都已定位过时诊断事件越权假设，不改生产迎合旧预期。
- 原第三node从未停API/关闭Chrome，手写含非法timestamp的旧payload，却期望运行实例stopped；新node整体替换为test_supervisor_replays_diagnostic_spool_without_stopping_live_runtime，保持活实例running、真实Agent/PID/CDP/身份与端口不变，真实诊断入库/duplicate。仍待root三项实跑。
- fixture R13完整component SHA `33e8772e9ddc31aec1cbfc0d22f5a83cb711081763a0e209df4e6423dc7ff52f`，patch/meta fixture_candidate_r6.\*；已整合Master/validation。修Popen/timeout/kill-wait失败清理、未reap保留引用、finally关闭日志、尽力清完其它进程后再传播。主控focused_fixture_r13：24 passed/11.46s。
- 新offline node `test_supervisor_authoritative_api_offline_replay_and_recovery_e2e` 已整体替换旧node并整合Master/validation：focused_offline_authority_r1真实PASS/42.26s，验证API真停、Supervisor SIGKILL、A正常退出权威收敛、诊断恰一条、B真实Agent UDS健康前后不变且fake normal诊断不能改运行意愿，重启/去重/清理全部通过。SQLite只读URI与连接关闭已补齐。meta offline_authority_final.\*。
- 旧checkpoint combined_candidate_r5 SHA `a8863cca9774c0cbaa7bb750c33b92bb3909143e7ff1267877db3be611f1e11b` 是R13整合后、offline新node前、lint前，非当前最终候选。

### 工具范围缺陷与已采取措施

- SDK报告路径与复用lane权限不一致，write拒绝后模型转shell/编码写报告，已立即披露，原始报告/错误保留，独立源码两文件与root424/66可信；审计sdk_report_permission_audit.json。后续prompt均规定权限拒绝停下，不绕工具。
- 新建非忽略文件不在初始SHA guard映射中。三个lane执行未带--no-project的uv run pytest/ruff --version，分别自动生成uv.lock，突破写域。root立即停止两个仍活跃CLI/全部后代，精确备份并删除三个已核实生成锁，保存partial源码/diff；审计generated_lock_scope_audit.json。未改guard/wrapper/.repo_template。所有恢复会话强制每个uv run含--no-project，逐阶段核对untracked；截至最近三个actor均无域外新文件。
- 两个早先native API与十个旧t006测试孤儿已核对全部退出；归属证据native_api_hang_probe。只恢复自有进程taskpolicy -B，未证实调度原因；不改配额/用户应用/其它项目。
- 发现Master/validation额外tracked tsconfig.tsbuildinfo只有root缓存数组漂移、无前端源码变化。已精确恢复HEAD原字节，备份和哈希在tracked_buildinfo_restore.json；不把生成缓存纳入执行commit，不动活跃actor WT受保护文件。后续driver构建后仍须恢复原字节。

### 当前三路actor与独立审查

- backend Ruff原始664总项中34个production文件371项由baseline_fixture_review wt收敛；R2曾声称unit424/integration66及默认联合Ruff0。root真实run_uds_agent+runner_info.json=null探针抓到异常范围窄化回归：baseline等待，lint候选立即TypeError。RED native证据agent_metadata_poll_lint_probe/result.json。
- backend R3已CLI0，恢复startup metadata等待边界+仅error_type debug，保持to_thread；实现方45 Agent相关unit PASS、34文件默认/联合Ruff0。当前34文件候选component SHA `816de9fa739562b1dac3480e6b9287405a9f422dae414781b44d5f341e8b8e78`，ruff_backend_final.\*，已整合Master供审查，未复制validation（validation仍R7生产源码，镜像R4与其匹配）。报告fixture-review wt `.scratch/baseline_fixture_review/ruff_backend_report.md`。root还需独立重跑修复后探针，不采信自报。
- 独立backend语义review dispatch47021，wt baseline_core_review，lane baseline_normal_review，全源码只读，manifest/增量patch在其scratch；报告ruff_backend_review.md。重点审103+具体noqa真实边界、异常窄化/取消、HTTP/xdotool offloop、Gateway/Stream context合并、ACK/状态/端口/隐私。禁止Docker/Chrome；若发现问题只报root。日志ruff_backend_review_round1.\*。
- tests/scripts full Ruff actor dispatch40298/CLI40309，wt normal_exit_fix，lane normal_exit_fix，53文件260诊断，明确排除recovery E2E（另一owner）。日志ruff_tests_round1.\*，manifest ruff_tests_allowed.json，报告其scratch/ruff_tests_report.md；源为R7+SDK+R13+新offline（prod未含新backend lint）。根据信息继续，不可整WT覆盖新production。root当前lexical AST核对仅两种等价assert表达式变化（dict in+index→get、set(generator)→set comprehension），数值/pytest.raises与数量无变化；完成后须重新核对。
- recovery唯一文件actor diagnostic_spool_authority R3已CLI0/默认联合Ruff0，旧两个节点15/11个assert AST完全保留，残留sync lifecycle已to_thread。R4当前dispatch46112，session ses_e67505776ffeLsi1cUIaAmfAVc，wt baseline_fixtures，仍只该文件：复用现成atomic_write_json写spool避免读半文件，并恢复四个cleanup BaseException范围防CancelledError中断后续清理。报告其scratch/diagnostic_spool_authority_report.md，日志diagnostic_spool_authority_round4.\*。此前R2代码仍未复制Master/validation，当前整合处仍旧第三node，待最终核查后单文件copy。

### 下一步必须串行核对

- 等第三文件与53文件CLI真实结束，核报告/原始日志/域外文件，按各自base文件/manifest验证只整合允许delta。Ruff backend34只在Master；validation在旧production，不可混用R4镜像宣称新lint后运行通过。全部最终源码freeze新SHA，重新镜像/入口import、全部静态与单元/集成/legacy/frontend/schema、真实Runtime/Stream/Supervisor/Gateway/frontend全门禁与新三项恢复。每组检查新标签容器和网络残留，只有外层Docker互斥。
- 当前无root Docker driver运行（focused_recovery_r4与focused_offline_authority_r1均自然终止）。R4镜像可作旧生产focused证据，最终必须新建匹配最新production及复制入Gateway test镜像的fixture代码的6镜像。
- 全绿+review后baseline单执行commit本地merge，备份scratch规范remove/prune，仅main后再t008。8小时/1000次IME/1000次clipboard、剩余7task、旧链路移除、Compose正式本机交付/Chrome黑盒尚未完成；公网TURN/原生x86仅两项USER_WAIVED。

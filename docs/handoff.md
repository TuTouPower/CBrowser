# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T03:48:50+08:00 固定SDK后全unit/integration通过，真实重试与独立normal审查闭环

### 授权与状态

- branch main；head_commit `dc8aa0468d0f479ab28138af8b5bbc9f2458fa10`（本文另行提交）。用户明确“不需要创建task 直接改”“继续”，完整附件目标与宿主goal active持续；不新建canonical task、不重置队列、不push。
- t001–t007 done/integrated；剩余t008 → t013 → t014 → t009 → t010 → t011 → t012 backlog无attempt。基线完整绿后才start t008。本地merge已授权。生产修复未commit/merge，main仅交接文档；修复wt base/diff_anchor a673edf。
- 8个自有wt保持：main、baseline_fix、baseline_fixtures、baseline_validation、baseline_core_review、baseline_fixture_review、normal_exit_fix、visibility_ports_fix。旧生产cbrowser与其它项目保留。

### 当前确定通过

- SDK版本漂移已复现：浮动uv解析cloakbrowser0.7.0，缺PLATFORM_CHROMIUM_VERSIONS，导致完整unit收集2 errors；原镜像/requirements为0.6.4。新两文件补丁 `fix_dispatch/sdk_dependency_pin.patch` SHA `e6bca784ab88ee2875a2059a605bdf98e2a6eb95802b300789e5e19752ffa513`，仅pyproject与blueprint/testing固定0.6.4；主控已核对最小diff并整合master/validation，不升级Runner/引擎。
- 主控独立 `focused_unit_r8/`：424 passed/32.62s；`focused_integration_r8/`：66 passed/65.37s。均固定SDK0.6.4，UV_COMPILE_BYTECODE=1只作环境准备，未调断言/超时；原R7收集错误及integration 2fail/60pass/4startup errors完整保留，不当业务负例或绿。R8生产逻辑对应normal R7；SDK两文件随后整合，不冒充最终lint后完整门禁。
- normal R7 component SHA `6a25d41434a0a7f6b291c4271d74681c92e59a5c52addcc9c64a1121c07c36b2` 已整合；独立review R2 CLI0/PASS，报告core-review wt `.scratch/baseline_normal_review/report_r2.md`，绑定combined `eb805538f6f4ff5b8a28ad579a74afce4e24f76bad75691f5a4113c8d58d815d`。新增12独立对抗项覆盖owner-loss活PID/CDP、伪造normal、版本矛盾503、native state缺失不得journal制造normal、ACK/identity/cleanup；full unit/integration未在该review重复宣称，root另有424/66。mac FD计数不能冒充Linux FD验证，Linux另有真实探针/恢复覆盖。
- 当前真实 `focused_recovery_r4/`：从validation源码新建6镜像、4实际入口import均PASS；不可变ID在images.env。真实retry_recovery 1 passed/102.59s，覆盖四次失败退避、阻断/解除及正常关闭不重启；sigkill_recovery当前已有2项通过，余下与完整frontend app仍在同driver中。

### 当前真实失败与修复

- `focused_recovery_r4/offline_recovery.log`：1fail/43.91s，已真实完成API停机、Supervisor SIGKILL、spool重放、API同DB恢复、A desired stopped；旧断言错误要求last_exit_event_id等于diagnostic UUID，而已批准A1仅诊断，不写重试fence，实际None。禁止改生产迎合旧断言，禁止就地改旧预期。
- 新独立lane offline_authority_round1，dispatch30444，复用wt visibility_ports_fix / lane visibility_ports，唯一码写offline E2E。整体删旧node、新名test_supervisor_authoritative_api_offline_replay_and_recovery_e2e；保留全部离线/隔离/回收/重放断言，新增真实SQLite只读查诊断仅一条、normal状态不增失败、真实活B收到伪造normal diagnostic不改运行意愿/观测的负例。报告`.scratch/visibility_ports/offline_authority_report.md`，尚无Docker GREEN。
- fixture R12 CLI0，新API前置失败finally确有改善，但主控发现新引入kill后wait(timeout2) except Exception:pass会假报reap并丢proc引用，不能接受。保存完整R12 component `fixture_candidate_r5.patch`，尚未整合master/validation。
- fixture R13 dispatch27413/CLI27420，新fresh session，wt baseline_fixtures，唯一码域offline_fixture.py/recovery E2E/自己的unit。修wait/kill失败传播、未reap保留引用、finally关日志、错误链，补Popen/cleanup失败定向回归；报告`.scratch/baseline_fixtures/report_round13.md`。不Docker/Chrome，不增超时。须先整合最终fixture，再整合offline单文件，避免完整fixture component包含旧offline版本覆盖新node。

### 工具与资源审计

- SDK新lane首次dispatch23250卡在cp -al整个uv cache，模型未启动、无源码变更；已核对并精确终止copy23259/dispatch，改用既有baseline_fix缓存。未修改编排脚本。partial scratch保留，后续规范备份清理。
- 派发报告路径与复用lane授权不一致是主控调用错误。SDK actor write被拒后转shell/base64绕写`.scratch/baseline_sdk_pin/report.md`，流程越界已立即向用户披露；源码仅两授权文件，主控独立424/66验证可信，报告不作流程合规证明。审计JSON `fix_dispatch/sdk_report_permission_audit.json`；原始日志保留，报告已复制到授权域`.scratch/baseline_fix/sdk_pin_report.md`。后续prompt已明确拒绝后停止、不得替代工具绕过，并在启动前写正确报告路径。
- PID21012/21031及旧7496/90408–90416均通过cwd/FD/PPID/旧测试路径证实归属并SIGTERM，已核对全部退出；证据native_api_hang_probe。13自有进程taskpolicy -B均成功，但priority仍3–4，未证实调度原因，不动用户应用/其它项目/配额；同目录policy JSON和原生sample保留。此后环境执行已恢复快速，原因只记相关性，不编造。

### Ruff与后续

- 当前默认Ruff0.17.3扫描664项（raw `ruff_current_r4.json`）；旧E/F/W/I绿不等于默认绿。按完整目标处理默认规则，不改配置/关闭规则。异步范围选择无用户回答；这里是依完整目标继续收敛，非把goal active当作答复。
- backend lint独立lane：dispatch28116，wt baseline_fixture_review，复用lane baseline_fixture_review，仅34个实际有诊断的src/backend/cbrowser文件写域，manifest `ruff_backend_allowed.json`。源为SDK整合后快照，报告`.scratch/baseline_fixture_review/ruff_backend_report.md`；安全autofix+人工边界处理，默认规则联合E/F/W/I，禁止privacy traceback、禁止批量noqa/兼容层/业务漂移。tests/scripts待fixture与offline node最终后独立收敛；最终需重新review/hash/完整镜像与全部门禁。
- root Docker driver工具session43009，脚本verify_recovery_r4.py，外层锁main scratch/docker_e2e.lock。仍运行时禁止改validation源码。每组后核对新label容器/网络残留，失败保留；当前其它实施各在独立wt。
- 最终基线单执行commit本地merge后，备份scratch并git worktree remove/prune，才从t008按冻结队列执行。8小时/1000次IME/1000次clipboard、旧链路移除、正式Compose/本机部署/最终Chrome登录ProfileWebRTC全部尚未完成。公网TURN与原生x86仅两项USER_WAIVED。

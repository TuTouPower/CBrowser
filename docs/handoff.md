# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-01T21:31:03+08:00 联合门禁R2已终止，按实际失败修复

### 授权与状态

- branch：main；head_commit：`3a6f8674e837c88d6ff9469ca14e411016b6c9f4`（本文另行提交）。用户明确“不需要创建task 直接改”，再次“继续”；基线直接修复、不建task、不改冻结队列、不push，本地合并已获授权。
- t001–t007 done/integrated；冻结队列仍t008 → t013 → t014 → t009 → t010 → t011 → t012，无attempt。基线全门禁通过前不start t008。8小时与1000次输入/剪贴板仍待后续真实验证；公网TURN、原生Linux x86_64为USER_WAIVED。
- main只有交接文档推进；生产修复尚未commit/merge。全部修复基准/diff_anchor `a673edf`。

### 真实联合门禁R2

- 独立验证wt `/Users/karson/kar/code/CBrowser_baseline_validation`，旧联合patch SHA256 `6f36cb5c8bff5876df38ca132653bcc41be464cc79ea481557e6dbe3e303a49a`。
- 驱动 `.scratch/v2_baseline_20261101/fix_dispatch/verify_candidate.py`，日志 `fix_dispatch/verify_candidate_r2.out`，逐项退出码、镜像ID、失败日志与basetemp在 `fix_round2/`。进程已自然退出1，非观察超时，禁止重启旧候选冒充新验证。
- 6镜像构建、3实际import、contract169、unit399、integration62、legacy384、Vitest112、前端build、4schema+TS无漂移、Ruff E/F/W/I、md全部通过。Runtime13通过，Stream真实多viewer完整媒体通过。
- 失败：Selkies tokens链路18097/18080未闭合；Supervisor容器图测试Gateway内部仍监听18097而发布18080；新SIGTERM用例漏实际Browser/Stream镜像env；offline recovery真实正常关闭后仍desired running；recovery三处inline CLI缺--gateway-port。
- 驱动在recovery泄漏coturn后停止，后续resource/capacity/retry/startup、Gateway、frontend尚未执行，不能声称完整通过。
- 泄漏容器7d5e0146fbd0（t005-rec-090ffe-coturn）已主控inspect核对完整ID、prefix/role后精确删除；该prefix无网络。证据 `fix_round2/verified_resource_cleanup.json`。旧生产cbrowser及其它服务未动。

### 当前修复与进程

- core wt `/Users/karson/kar/code/CBrowser_baseline_fix`，branch `fix/v2_baseline_gates`，已整合旧fixture patch。session `ses_e6a911a65ffe3Y0VZs5R3JTF9x`；round7 exit0，补镜像env、权威端口与确定性订阅INFO；round8补门禁先决条件fail而非skip、关闭探测client，状态看 `fix_dispatch/core_round8_launch.json` 与wrapper实际cli_exit。写域不含fixture。
- fixture wt `/Users/karson/kar/code/CBrowser_baseline_fixtures`，branch `fix/v2_baseline_fixtures`；session `ses_e6a7c7e18ffeNQzGW5g1MCQkco`；round4 exit0，闭合Gateway listener/publish/control/Caddy端口链，新增11项回归通过。round5修三个inline CLI与必要异常清理，状态看 `fixtures_round5_launch.json` 与wrapper。不要改offline recovery正确期望。
- 正常退出独立lane wt `/Users/karson/kar/code/CBrowser_normal_exit_fix`，branch `fix/v2_normal_exit_observation`，session `ses_e68b60e1cffetua70w4uOzZVnU`；首轮dispatch31033/CLI31218，状态看 `normal_exit_wrapper.log` 与JSONL。仅core.py/recovery_coordinator.py/recovery_rules.py/runtime_agent/agent.py及两个新测试；与其它lane写域独立。
- 生产根因线索：Chrome正常关闭后Agent/Xvfb容器仍running，core仅Docker exited/dead认可normal_exit；同instance恢复短路未读取Agent真实进程状态。修复须用既有UDS健康与实际进程监督核对身份/配置，磁盘事件仅诊断，不恢复裸exit0文件驱动意愿。API唯一DB写者、owner-loss误0错误语义保持。
- 所有外部OpenCode使用已授权cpa/gemini-3.8-flash high，XDG/tmp/cache位于各scratch；外层wrapper exit0不是成功，以cli_exit、JSON错误、report核对。长JSONL触发OpenCode grep 64KiB限制，已披露，使用窄读/Python解析，未修改工具配置。

### Review与下一步

- 旧core review R2 PASS scope `c2ae3b3e027338ea0e5e8784084a3e2b1e4f613714f68faa416d337503642466`；旧fixture review PASS scope `46b544e4b5f92c7f4decd1354034c51fc18fcf0212d5b06d0dd9d06be73ba9ae`。新修复使scope过时，须独立增量复核。
- review wt：`CBrowser_baseline_core_review`、`CBrowser_baseline_fixture_review`；报告在各自scratch。旧patch与证据均已主仓scratch保存。
- 等core进程终止才替换其wt里的旧fixture patch；先reverse --check旧fixture_candidate.patch，再正向新patch --check，防交叉覆盖。正常退出patch需核对路径交集后整合。
- 创建新的不可变validation候选，驱动新输出目录R3，保留R2所有失败证据；重建最终6镜像，完整重跑真实门禁，尤其未执行Gateway/frontend。主控持Docker互斥锁，失败不得弱化断言，精确回收测试资源。
- 基线最终review+全门禁通过后，一个生产修复commit本地merge main，备份自有wt证据后规范清理，再按task-run执行冻结队列。禁止push、改.repo_template、扩大Docker配额或动其它项目。

# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-01T20:59:12+08:00 基线候选已整合，独立完整门禁运行中

### 授权与队列

- branch：main；head_commit：`9f9de5d47a853e0941751d5459a1a0d05e71b0b5`（本文另行提交）。用户已明确“不需要创建task 直接改”，并再次“继续”；基线修复不建task、不改冻结队列、不push，无需重复询问。
- t001–t007 done/integrated；冻结队列仍2/9 closed，剩余t008 → t013 → t014 → t009 → t010 → t011 → t012，无attempt。须先通过当前基线门禁才start t008。
- main仅交接文档推进；生产修复尚未commit/merge，全部位于独立worktree。

### 当前候选与工作区

- 基准/diff_anchor：`a673edf`。core实现：`/Users/karson/kar/code/CBrowser_baseline_fix`，branch `fix/v2_baseline_gates`；fixture实现：`/Users/karson/kar/code/CBrowser_baseline_fixtures`，branch `fix/v2_baseline_fixtures`。两路原始写域无重叠，fixture patch已经git apply --check后整合进core实现worktree。
- 联合候选：主仓 `.scratch/v2_baseline_20261101/fix_dispatch/combined_candidate.patch`，SHA256 `6f36cb5c8bff5876df38ca132653bcc41be464cc79ea481557e6dbe3e303a49a`。
- 独立validation：`/Users/karson/kar/code/CBrowser_baseline_validation`（detached a673edf），完整patch哈希已与联合候选核对一致；3个新增测试已git add -N纳入diff。主控验证使用独立数据/进程/容器，不复用实现lane环境证据。
- review worktree：`CBrowser_baseline_core_review`（core最终快照）、`CBrowser_baseline_fixture_review`（fixture最终快照）。均只读源码，报告写自身scratch；源码patch副本在主仓保存，最终清理前须备份证据并核对所有权。

### 已修复与实际证据

- core/build：补齐Supervisor/Gateway/API/测试Gateway模块COPY及对应Docker ignore清单；Gateway包顶层lazy导出避免endpoint引入整个服务依赖；API fixture固定版本沿本轮旧镜像实测版本，无无理由降级。
- 90项E/F/W/I问题修复；AST检查5个核心文件运行时字符串完全不变，保留原错误脱敏信息。
- Supervisor watcher作用域NameError已修复；进一步主控真实CLI探针发现SIGTERM后20秒挂起（`shutdown_probe_r4/result.json`，ready=true，SIGKILL仅用于结束该测试PID）。显式关闭Docker事件流并把同步close移出loop后，真实probe R5为ready=true、SIGTERM后0.2387秒、rc0，源runner SHA `64d835dd24e6584ead8309b6fa9fa6592602e645f5dcfe5694eab66e03c40f5f`。
- probe早期Python发现、缓存路径、缺镜像参数是准备错误，原始日志保留，不计业务RED；R4/R5为有效真实API+Supervisor CLI+Docker证据，无用户Profile数据。
- fixture：统一权威/动态Gateway端口显式一致、token0600、启动失败/取消清理、精确标签保护、非空网络拒删及清理失败传播；原只检查手工Docker配置的低价值新测试已删除，安全断言置于真实媒体/实际Supervisor容器图。
- 旧Stream/恢复/基础设施测试按新语义node替换并加强覆盖，替代映射在fixture报告；未通过就地弱化旧断言假绿。
- core前轮390 unit、62 integration、E/F/W/I、schema与字符串比对通过；新增shutdown回归另有RED/GREEN，联合候选所有检查以当前主控全门禁为最终依据。
- fixture最终组件回归8 passed、原基准全unit391 passed（383+8）、E/F/W/I通过；未执行Docker/Chrome，报告明确NOT_RUN/PENDING_CONTROLLER。
- 主控core整镜像6构建+API/Supervisor/生产Gateway/测试Gateway实际import全部exit0：证据`.scratch/v2_baseline_20261101/core_images/`。该轮镜像早于shutdown最后修复，不能冒充最终镜像，当前全门禁重新构建。
- 主控实际Gateway UID1000读取0600测试bind文件成功（OrbStack映射file_uid1000）：`core_images/secret_owner_probe/result.json`，随机测试key已删除，无秘密输出。

### 独立review与在飞进程

- 所有OpenCode均使用已授权cpa/gemini-3.8-flash high，XDG data/cache/state位于主仓scratch；不改.repo_template或观察wrapper。wrapper的外层exit0不作成功依据，以cli_exit、JSON错误与报告核对。
- core session `ses_e6a911a65ffe3Y0VZs5R3JTF9x`已完成，原始日志`fix_dispatch/core_round3..6.jsonl`；后续不复用旧PID。core报告实现wt `.scratch/baseline_fix/report.md`。
- fixture session `ses_e6a7c7e18ffeNQzGW5g1MCQkco`已完成，原始日志`fixtures_round1..3.jsonl`，报告实现wt `.scratch/baseline_fixtures/report.md`。
- fixture独立review：PASS，scope `46b544e4b5f92c7f4decd1354034c51fc18fcf0212d5b06d0dd9d06be73ba9ae`，报告fixture-review wt `.scratch/baseline_fixture_review/report.md`，实际cli_exit0。
- core旧review：PASS+EOF Minor，但仅对应旧4bac快照，不能冒充最新scope。最新core review R2运行中，dispatch25471，session与实际CLI看`fix_dispatch/core_review_r2_launch.json`及wrapper日志；新scope `c2ae3b3e027338ea0e5e8784084a3e2b1e4f613714f68faa416d337503642466`。
- 主控完整门禁：工具session87188，命令`CBROWSER_GATE_ROOT=...CBrowser_baseline_validation python3 .../fix_dispatch/verify_candidate.py`，输出`fix_dispatch/verify_candidate_r2.out`，逐项日志/退出码与最终镜像在`.scratch/v2_baseline_20261101/fix_round2/`。
- 门禁持`.scratch/docker_e2e.lock`外层互斥；模板basetemp在登记worktree外。每个Docker E2E文件后核对新建标签容器，发现残留立即停止后续套件，保留泄漏元数据，不将端口污染造成的失败算安全负例。

### 下一步与限制

- 观察当前同一session87188与core-review R2实际状态，不能因观察超时重启。失败先归因，不放宽断言；新修改则重算候选/review范围并重跑相关门禁。
- 全门禁与review完成后，主控复核最终源码/镜像一致，基线修复独立commit并本地合入main；备份各wt证据后规范清理，只留main，再从t008继续冻结队列。
- 旧生产cbrowser及kkmail/haiwa等服务保留，未扩大Docker配额、未重启OrbStack、未改生产secret。公网穿透与原生Linux x86_64始终NOT_RUN / USER_WAIVED；8小时和1000次输入/剪贴板仍待后续task真实运行。

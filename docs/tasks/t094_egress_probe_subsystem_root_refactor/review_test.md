# Task review t094（reviewer_focus: 测试）

- task：`t094_egress_probe_subsystem_root_refactor`
- spec：`docs/tasks/t094_egress_probe_subsystem_root_refactor/task.md`
- diff_anchor：`b1f979ba5e7ea2ee3a1bfb22d9d5d52703834434`
- target：`git diff b1f979ba5e7ea2ee3a1bfb22d9d5d52703834434`
- round：4
- reviewed_at：2026-11-20T17:41:43+08:00

## Findings

### t094_test_f007 - filter-scope 漂移用例的「精确 ID 集合」与 country/city 维度断言仍偏弱

- 严重度：minor
- 锚点：AC-006（混有不匹配项时精确 ID 集合；country/city 取自观测，测速追加观测导致归属变化时目标集合不漂移）
- 位置：`tests/integration/test_t052_proxy_api.py`（`test_probe_job_filter_scope_freezes_exact_ids_and_ignores_drift`）
- 问题：用例已把 socks5 不匹配项混入夹具并断言 `frozen.isdisjoint(socks_ids)`，且用 `after == frozen` 证明追加作业后集合不漂移；但「精确 ID 集合」只断言 `http_ids[0] in frozen`，未断言 `frozen == set(http_ids)`；漂移用例 filter 为 `{"scheme": "http"}`，追加观测不改变 scheme，故不验证 country/city 观测维度归属变化时的不漂移。
- 建议：把 `assert http_ids[0] in frozen` 收紧为 `assert frozen == set(http_ids)`；另补一条以 `country_code`/`city` 为 filter 的作业，提交后改写 GeoIP 观测再断言冻结集合不变。
- 处置：沿用 Round 3，`progress.md` 处置表标遗留 `p151`；AC-006 主体已由 scheme 过滤器 + 冻结集合主路径覆盖，本轮维持遗留，不阻断。

### t094_test_f008 - 断线超窗只测了 broadcaster 机制，未触达 router 把在途作业写入快照的装配

- 严重度：minor
- 锚点：AC-005（首读快照与断线超窗由快照重建/`resync-required` 补齐）、AC-004（刷新/重连恢复进度）
- 位置：`tests/unit/test_runtime_sse_snapshot_handoff.py`（`test_typed_probe_job_snapshot_survives_out_of_window_reconnect`）、`src/backend/cbrowser/api/v1/router.py:239-251`
- 问题：新用例用 `provider()` 手写返回 `TypedSseEvent`，直接调用 `broadcaster.subscribe(...)`，验证 `runtime_coordinator.py` 的 typed 快照格式化机制；但 `router.py:239-251` 的 `service.list_unfinished_probe_jobs()` → `TypedSseEvent(event="probe_job_progress")` 装配代码无测试经 `/api/v1/events` 触达。若装配漏接，超窗机制测试仍 PASS，而生产首读快照缺在途作业。
- 建议：补一条走真实 `/api/v1/events` 的集成用例：建 running 作业、用超窗 `Last-Event-ID` 重连，断言首读流含 `event: probe_job_progress` 且带该 `job_id`。
- 处置：沿用 Round 3，`progress.md` 处置表标遗留 `p151`；AC-005 通用 `resync-required`/环形缓冲机制已有集成用例覆盖，本轮维持遗留，不阻断。

## 结论

- 前轮 finding 复核（以当前 diff 为准）：相对基准 `b1f979ba` 的交付内容与代码自 Round 3 起未变，本轮为最终确认。当前真实指纹 `e79f445344eca869` 已用 `repo_task.review_scope_fingerprint` 独立复算确认；相对 Round 3 记录的 `bcf255f2af65bd0d` 的差值来自 `task.md` 契约区漂移（AC 打勾 + `[deploy]` 处置注记），非代码/测试改动。
    - f001（刷新/多标签/断线恢复零测试）：已消除（主体），残留 router 装配专项为 minor（f008，遗留 p151）。
    - f002（loopback 映射 + 三协议零测试）：已消除，三协议透传/无直连回退测试保留且触达生产 runner；socks5 真实出口由 `[deploy]` AC-008 承担。
    - f003（环境批量进度/汇总零测试）：已闭环，`profileBatchJobs` stub + 三条 frozen-scope 用例 + `env-batch-job-status` 断言保留。
    - f004（filter-scope 弱断言）：已消除（主体），残留精确集合与 country/city 维度专项为 minor（f007，遗留 p151）。
    - f005（important，读模型收敛零测试）：已消除，4 类子行为均触达生产实现：`test_pending_members_converge_on_driver_fault`、`test_terminal_member_is_not_overwritten_by_late_result`、`test_resume_recovers_unfinished_job_after_restart`、`test_concurrent_subset_probes_do_not_interleave`。
    - f006（important，混不匹配项/并发上限/漂移）：已消除（主体），残留为 minor（f007，遗留 p151）。
    - f007/f008（Round 3 minor）：仍存在，维持遗留 `p151` 处置，不阻断 PASS。
- 改测方向复核：本轮代码与测试未变（最终确认轮）；既有旧测重写（同步 `/probe` 删除、`useBatchActions` 客户端串行改服务端作业）有 spec/架构归因，无「把旧预期改成当前实现输出」的就地改测，无迁就实现的新改测。
- 本轮新发现：0 条（finding 编号 f001~f008 沿用前轮，本轮无 f009+）。
- 未进表的提示：
    - `[deploy]` AC-008/AC-009 按处置注记与 `p151`（USER_WAIVED）判 TICK-VALID（处置型）；本机因 `REQUIRED_E2E_ENV` 不可变镜像 ID 未配置未实测，不作 VOID 依据；E2E 用例改写仍触达生产策略路径。
    - 契约区 drift 仅 AC 打勾、`[deploy]` 处置注记与实现补强，AC 原文一字未改，按用户判定视为正常收尾，不出 blocking finding。
    - 全量门禁 EXIT=0（contract 388 / unit 2410 / integration 216 / frontend 730 + 生产构建）；已扫全量 test diff，无 `.skip`/`.only`/恒真断言/删或反转 expect/注释断言/静默错误/mock 被测逻辑等危险模式；`toMatchObject`（事件多带 `event` 字段）、`>=55`（55>50 区分当前页）、`latency_ms>=1`、`peak<=1` 均有正当理由，不构成弱化断言。
- 总体判断：9 条 AC 全部 TICK-VALID（AC-001~007 re_verified，AC-008/009 trust_prior），仅 2 条 minor 遗留 p151，无未解决 critical/important，判 PASS。
- 系统性 follow-up：无（真实 Docker/Chrome E2E 延期与 test f007/f008 增量优化由 `p151` 跟踪）。

reviewed_scope: e79f445344eca869

### AC 复验方式

- AC-001：TICK-VALID，re_verified。diff 中 blueprint/spec/i18n/UI 文案限定探针为测速与出口展示，防泄露由 AC-008/009 测试承担；E2E 探针链改写后仍触达生产策略路径。
- AC-002：TICK-VALID，re_verified。loopback→host.docker.internal 映射、http/https/socks5 透传无降级、无直连回退与显式 proxy + `trust_env=False` 测试保留（`test_in_process_runner_supports_all_three_schemes_without_downgrade`、`test_in_process_runner_never_falls_back_to_direct_egress`、`test_fetch_egress_ip_passes_explicit_proxy_and_disables_trust_env`）；并发隔离由 `test_concurrent_subset_probes_do_not_interleave` 覆盖；socks5 真实出口由 `[deploy]` AC-008 承担。
- AC-003：TICK-VALID，re_verified。`test_probe_job_submission_immediate_and_scope_frozen` 用阻塞夹具证明 202 先于单项完成并冻结 ID 集；`test_probe_job_empty_scope_converges_to_done` 断言零匹配 `total==0` 且终态收敛。
- AC-004：TICK-VALID，re_verified。读模型回读（`test_probe_job_read_model_survives_read_after_done`）、刷新恢复 UI 断言、`test_resume_recovers_unfinished_job_after_restart`、`test_pending_members_converge_on_driver_fault`、`test_terminal_member_is_not_overwritten_by_late_result` 分别覆盖回读/刷新/重启/收敛/围栏；router 快照装配专项为 minor（f008，遗留 p151）。
- AC-005：TICK-VALID，re_verified。即时反馈/SSE 进度/汇总/按钮禁用有测试，刷新恢复 `2/4`、多标签共享 key、超窗 typed 快照、`parseProbeJobProgressEvent` 围栏与 `Last-Event-ID` 重放已补；稳态进度写入共享 key 不靠 refetch；router 装配专项为 minor（f008，遗留 p151）。
- AC-006：TICK-VALID，re_verified。跨页（55>50）、socks5 不匹配项排除、并发上限（`peak<=1`）、追加观测不漂移均有测试；精确集合断言与 country/city 维度专项为 minor（f007，遗留 p151）。
- AC-007：TICK-VALID，re_verified。三条 frozen-scope 提交用例断言 action/ids/group_id 与一次提交；服务端 `test_t094_profile_batch_jobs.py` 覆盖冻结集合、逐成员部分失败、非法 action/空集合；进度复用 `probeJobKeys.detail` 共享 key 与同一 SSE handler。
- AC-008：TICK-VALID，trust_prior。依 `[deploy]` 打勾处置注记与 p151（USER_WAIVED）判处置型有效；依赖云端契约/E2E 用例改写与全量门禁证据，本机未执行真实 Docker 链，不独立复验。
- AC-009：TICK-VALID，trust_prior。依 `[deploy]` 打勾处置注记与 p151（USER_WAIVED）判处置型有效；Browser 双栈 `OUTPUT DROP` 与监听代理日志链依赖云端证据，本机未执行真实 Chrome 链，不独立复验。

coverage = 7 / 9

verdict: PASS

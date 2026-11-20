# Task review t095（reviewer_focus: 测试）

- task：`t095_probe_job_progress_realtime_and_concurrency`
- spec：`docs/tasks/t095_probe_job_progress_realtime_and_concurrency/task.md`
- diff_anchor：`94ec7cdff9ca62309367ce984d20db4595189852`
- target：`git diff 94ec7cdff9ca62309367ce984d20db4595189852`
- round：2
- reviewed_at：2026-11-20T21:21:37+08:00

reviewed_scope: ebe33b906c8aebb4

## Findings

### t095_test_f001 - AC-005 环境批量「失败计入进度」缺直接断言

- 严重度：minor
- 锚点：AC-005（「代理测速与环境批量三动作共用同一进度语义…失败均计入已处理进度，终态汇总一致」）。若环境批量成员失败不推进 `processed`，现有测试不会失败。
- 位置：`tests/integration/test_t094_profile_batch_jobs.py:79`（`test_profile_batch_job_partial_failure_is_per_member`）、`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:979`（`shows the batch job progress bar after submission`）
- 问题：本轮新增的后端用例（`tests/unit/test_t095_probe_job_progress.py`）全部走代理测速路径，未覆盖环境批量。AC-005 的「失败计入已处理进度」在环境批量侧只有间接证据：t094 集成测试仅断言成员态与 `completed + failed == total`（`test_t094_profile_batch_jobs.py:76,91-92`），未触及新字段 `processed`；前端环境批量只断言初始文案 `"0/2"`（`EnvironmentListPage.test.tsx:987-989`），未验证失败成员被计入运行中进度。共享 `_drive_members` 与 computed `processed` 使实现成立，但缺少一条能直接挡住「环境批量失败不计进度」回归的测试。
- 建议：补一条环境批量用例——提交含失败成员（如 `missing-env`）的批次，断言终态 `job["processed"] == job["total"] == 2` 且运行中展示文案按失败计入的已处理数；可在 `test_t094_profile_batch_jobs.py` 或 `test_t095_probe_job_progress.py` 增加。

## 结论

- 前轮 finding 复核（Round 2）：t095_test_f001（minor）——仍存在。相对 `94ec7cdff9ca62309367ce984d20db4595189852` 的交付代码自 Round 1 起未变，AC-005 环境批量侧仍只有共享 `_drive_members` + computed `processed` 的间接证据，缺直接断言；维持 minor，非阻断，遗留由 p151 跟踪。无 blocker 需撤回，亦无「修不彻底 / 换形式弱化」情形。
- 改测方向复核：本轮无新增「迁就实现」的改测。相对基准的既有改测已逐条复核：`{completed}` → `{processed}` 占位符替换与 stub 新增 `processed` 字段由 i18n / OpenAPI 契约变更驱动，断言强度未降低；删除 `tests/unit/test_t094_probe_job_convergence.py::test_concurrent_subset_probes_do_not_interleave` 有明确归因（其 `peak <= 1` 编码「驱动串行」旧语义，与 AC-003 冲突），由 `test_t095_probe_job_progress.py::test_parallel_jobs_keep_member_results_isolated` 在新语义下等价替代，合法。
- 本轮新发现：0 条。
- 未进表的提示：
    - `docs/blueprint/testing.md` 与 `progress.md` 称 `useProfilesQuery.test.tsx` 覆盖「SSE 事件→列表重取」，但该文件 `probe_job_progress` 用例（`useProfilesQuery.test.tsx:1033`）仅断言作业缓存写入，未断言列表失效；AC-002 的决定性证据是 `ProxyListPage.test.tsx:958` 的进度事件→`listCollection` 重取用例。属自述与证据口径偏差，不影响覆盖判定。
    - `test_members_run_within_concurrency_and_faster_than_serial` 用墙钟阈值（`elapsed < delay * total * 0.6`）证明并行，阈值未掩盖问题，但负载波动的 CI 上有轻微 flaky 风险，建议后续观察。
- 总体判断：代码自 Round 1 未变；全量门禁 EXIT=0。AC-001~005 均有触达生产逻辑的真实测试（全失败进度推进、SSE 事件驱动刷新、并发耗时对照、读模型权威与观测 TTL），无恒真断言 / 删 expect / 跳过 / mock 被测逻辑等危险模式；AC-005 仅次要覆盖缺口（t095_test_f001，minor），AC-006 为 [deploy] 处置型按注记判 TICK-VALID（p151 跟踪）。无未解决 critical / important。PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`tests/unit/test_t095_probe_job_progress.py:61` 注入全失败探测桩，经 `set_probe_job_progress` 捕获 `processed` 逐次推进且终值 4、`completed=0/failed=4`；`src/frontend/src/features/proxies/ProxyListPage.test.tsx:958` 以 `completed=0/failed=3` 的 SSE 事件断言展示「3/4」。
- AC-002：TICK-VALID，re_verified。`src/frontend/src/features/proxies/ProxyListPage.test.tsx:958` 经真实 `SseBridge→useProfileEventsSync→invalidateProxyLists` 发射 `probe_job_progress` 后断言 `listCollection` 调用数增加（`ProxyListPage.test.tsx:995-999`），证明事件驱动刷新而非轮询。
- AC-003：TICK-VALID，re_verified。`tests/unit/test_t095_probe_job_progress.py:135` 以 9 成员 / limit 3 / 延迟 0.06 对照断言 `peak<=3`、`peak>=2`、`elapsed<0.324`（串行需 0.54）；`:157` 断言超限排队全收敛，`:193` 断言慢成员不阻塞其他成员，`:167` 断言多作业结果隔离。
- AC-004：TICK-VALID，re_verified。`tests/unit/test_t095_probe_job_progress.py:85` 在观测表为空时断言 `processed==2` 且两代理观测均为空，证明进度只取读模型；`:106` 断言 3 行观测历史保留且 `expires_at` 随行写入。
- AC-005：TICK-VALID，re_verified。`_drive_members` 被代理测速与环境批量共用（`src/backend/cbrowser/services/profile_service.py:1950` 起），环境批量端点返回含 `processed` 的 `ProxyProbeJob`（`schemas/openapi/cbrowser_v1.json:1513`），t094 集成测试断言环境批量失败按成员收敛且 `completed+failed==total`（`tests/integration/test_t094_profile_batch_jobs.py:76,91-92`）；直接断言缺口记为 t095_test_f001（minor）。
- AC-006：TICK-VALID，trust_prior。[deploy] AC-006 需真实 88 代理 Docker/Chrome 拓扑与公网出口，本机不可实测；依契约区「[deploy] AC 打勾处置注记」，云端可做的契约 / 实现 / 单元集成前端门禁与并发进度 SSE 测试均完成，真实验证延期由 pending `p151`（`docs/pending/p151_t094_deploy_e2e_verification.md` 第 4 项）跟踪，属处置型有效，非 TICK-VOID。

coverage = 5 / 6

verdict: PASS

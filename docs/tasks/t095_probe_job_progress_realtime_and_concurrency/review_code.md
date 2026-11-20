# Task review t095（reviewer_focus: 代码）

- task：`t095_probe_job_progress_realtime_and_concurrency`
- spec：`docs/tasks/t095_probe_job_progress_realtime_and_concurrency/task.md`
- diff_anchor：`94ec7cdff9ca62309367ce984d20db4595189852`
- target：`git diff 94ec7cdff9ca62309367ce984d20db4595189852`
- round：2
- reviewed_at：2026-11-20T21:16:45+08:00

reviewed_scope: ebe33b906c8aebb4

## Findings

### t095_code_f001 - 驱动 docstring 把「不会 BUSY」归因于 BEGIN IMMEDIATE，与真实机制不符

- 严重度：minor
- 锚点：行为缺陷（文档/实现不一致）——注释断言「SQLite 不会 BUSY」由 BEGIN IMMEDIATE 保证，但观察到的抑制机制是 `busy_timeout=5000`，且并发观测写入并未被该锁串行化
- 位置：`src/backend/cbrowser/services/profile_service.py:1962`
- 问题：`_drive_members` docstring 写「计数在 `counter_lock` 内串行推进，写库仍走 write_transaction 的 BEGIN IMMEDIATE，因此 SQLite 不会 BUSY，也不会出现计数竞态」。实际 SQLite 写者靠 `adapters/database/session.py:57` 的 `PRAGMA busy_timeout=5000` 等待序列化；BEGIN IMMEDIATE 本身只负责抢写锁，正是它制造写者竞争。更关键的是，并发成员在 `run()` 内各自调用 `record_egress_observation`（`profile_service.py:2123/2150/2177`），这些写入发生在 `counter_lock` 之外、彼此并行，并非「写库经同一锁串行」。该断言在默认 8 并发下因写入极短而不易触发 BUSY，但作为不变量表述过强，会误导后续维护者移除 busy_timeout 或误判高并发下的 BUSY 风险。
- 建议：改 docstring 为「计数在 `counter_lock` 内串行，作业成员写经 `write_transaction` 的 BEGIN IMMEDIATE；包括观测写在内的所有写者由 SQLite `busy_timeout=5000` 等待串行化，避免计数竞态并在短写场景内避免 BUSY」，不要宣称「不会 BUSY」。
- 本轮状态：前轮遗留。相对 diff_anchor 的交付内容自 Round 1 未变，`profile_service.py:1962` docstring 仍为原文，f001 仍存在；minor 非阻断，不要求本轮修复。

## 结论

- 前轮 finding 复核（Round 2）：逐条以当前 diff 为准复核——f001 仍存在（实现/docstring 未改），维持 minor、非 blocking；无前轮 critical / important 需消除或撤回。其余改动与 Round 1 所见一致（进度 computed_field、受配额并发 `_drive_members`、SSE 列表失效刷新、i18n `{processed}`、读模型权威），未发现修复过程引入的新问题。
- 本轮新发现：0 条。
- 未进表的提示：文件过大（按结论段列路径与行数，不进 finding 表）——`src/backend/cbrowser/services/profile_service.py` 2232 行（实现源码，≥800 important 阈值，本 task 净增约 +101 行）；`src/backend/cbrowser/domain/models.py` 1188 行（≥800，本 task 净增 +13 行）；`src/frontend/src/features/profiles/useProfilesQuery.ts` 1218 行（≥800，本 task 净增约 +9 行）；`src/frontend/src/features/proxies/ProxyListPage.tsx` 642 行（≥400 minor 阈值，本 task 净增约 +56 行）。均为本 task 前已超阈值的存量大文件，无不可拆硬约束说明，建议后续按职责拆分，不阻断本 task。圈复杂度未达阈值（无工具，McCabe 手算 `_drive_members`/`_probe_job_concurrency` 均 \<10）。范围外观察：环境批量终态展示沿用 t094 的 `envBatchJobDone`/`envBatchJobPartial`，未设独立「全失败」文案，而代理测速有 `proxyProbeJobAllFailed`；属存量差异且未落入本 task diff，AC-005「终态汇总一致」按成功/失败分列语义成立，不记 finding。契约区自基准起的变更仅为 AC-001~006 打勾及 `[deploy]` 处置注记，属用户确认的需求处置（p152/p151），原文一字未改，非未授权 drift。
- 总体判断：无未解决 critical / important，全部 AC 打勾成立（AC-006 为 `[deploy]` 处置型），唯一 minor f001 为注释准确性、非阻断，可 PASS。全量门禁 EXIT=0。
- 系统性 follow-up：AC-006 `[deploy]` 生产规模真实验证由 pending `p151`（`docs/pending/p151_t094_deploy_e2e_verification.md`，status=todo）跟踪，按契约注记判处置型 TICK-VALID，不因本机缺不可变镜像 ID 冒充实测、不阻断本机 PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`ProxyProbeJob.processed` 为 computed_field=completed+failed（`domain/models.py:1162`），`_drive_members` 对 ok/failed/gone/异常均累加 failed（`profile_service.py:1981`），全失败时逐条推进到 N/N；终态 `ProxyListPage.tsx:143` 以 total-failed 派生成功数并分列成功/部分失败/全失败，已复核。
- AC-002：TICK-VALID，re_verified。成员写库后 `_publish_probe_job_progress`（`profile_service.py:1998`）经 `app.py:365` 推 `probe_job_progress`；`useProfilesQuery.ts:941` 同一处理器写读模型缓存并 `invalidateProxyLists`；列表查询无 `refetchInterval`（仅批量删除 `useDeletionBatchQuery:336` 有轮询，属范围外），已复核无固定间隔轮询。
- AC-003：TICK-VALID，re_verified。`_drive_members` 用共享 `asyncio.Semaphore(self._probe_concurrency)` 限流排队（`:1971`）、`counter_lock` 串行计数与写库（`:1980`）、成员异常就地收敛 failed（`:1974`）；上限由 `CBROWSER_PROBE_JOB_CONCURRENCY` 配置并校验 ≥1（`profile_service.py:66`）；生产 runner 以 `asyncio.to_thread(..., timeout=10.0)` 有界（egress_probe.py:134），慢成员不占死配额；计时/排队/隔离测试逻辑已查证。
- AC-004：TICK-VALID，re_verified。`get_probe_job` 只读 `proxy_probe_jobs`/`proxy_probe_job_members`（repository.py:2944），无观测反推；`record_egress_observation` 仅追加单次结果、保留历史与 expires_at（repository.py:2430、test 断言 TTL 不变）；读模型 `processed` 与观测表无数据流耦合，已复核。
- AC-005：TICK-VALID，re_verified。代理测速 `_drive_probe_job:2029` 与环境批量 `_drive_profile_batch_job:2072` 共用 `_drive_members`；`ProxyListPage.tsx:139`、`EnvironmentListPage.tsx:437` 均以 `processed` 展示运行中进度，i18n 四键统一改 `{processed}`（i18n.tsx:694/703/860/1080），失败均计入已处理数，已复核。
- AC-006：TICK-VALID，trust_prior。[deploy] 生产约 88 代理拓扑本机缺全部不可变镜像 ID 与真实代理/GeoIP 环境不可实测；按契约注记的处置型口径，云端可做的契约、实现、单元/集成/前端门禁与并发/进度/SSE 测试已完成，真实验证延期由 pending `p151` 跟踪，依赖该 pending 记录而非本机实测，不冒充实测、不因本机缺失判作废。

coverage = 5 / 6

verdict: PASS

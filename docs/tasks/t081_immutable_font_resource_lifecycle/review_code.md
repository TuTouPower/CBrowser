# Task review t081（reviewer_focus: 代码）

- task：`t081_immutable_font_resource_lifecycle`
- spec：`docs/tasks/t081_immutable_font_resource_lifecycle/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：1
- reviewed_at：2026-11-18T12:14:00+08:00

reviewed_scope: 24f07c7638df453f

## Findings

### t081_code_f001 - 目录验证不查 manifest 平台，跨平台 manifest 的集会被记录为 verified 并可绑定

- 严重度：important
- 锚点：AC-001（错误平台不能被发布为可用）、AC-005（显式审计应发现 manifest 异常）；同时回退了 t053 A20「manifest 平台与目录不一致标为完整性失败」的既有行为
- 位置：`src/backend/cbrowser/services/font_set_catalog.py:76`（`_verify_directory`）；`src/backend/cbrowser/font_sets/manifest.py:302`（`check_font_set`）
- 问题：`_verify_directory` 的 `ok` 只取 `check_font_set(directory)` 的结果，而 `check_font_set` 全函数没有任何平台比对（已逐行核对，函数内无 `platform` 引用）；同函数第 77 行调用的 `get_font_set` 在 manifest 平台与目录平台不一致时返回 `None`，但返回值仅被用来取 source/source_version，`found is None` 不影响 `ok`。结果：一个放在 `windows/<set_id>` 目录、manifest 声明 `platform: macos`、文件哈希全部正确的集，会被接管/审计记录为 `verified`，`ProfileService._validate_font_set_binding` 据此放行 windows 绑定——而 Supervisor 侧用 `get_font_set` 会拒绝同一集，两条校验路径结论分叉。旧 `list_font_sets` 路径曾显式追加该 mismatch 为 integrity 失败（A20），新目录路径把这条检查丢了。失败场景：导入/恢复把 macos 集放错平台目录（或恢复旧 DB+卷组合错位）→ 目录标 verified → 可绑定、可出现在默认集候选，直到 Supervisor 启动才被拒，API 层呈现「可用」假象。
- 建议：`_verify_directory` 在 `found is None`（含平台不一致、manifest 缺失/不可解析）时强制 `ok=False` 并把原因写入 integrity problems；或把平台比对下沉进 `check_font_set` 的调用参数。补一条目录级测试：manifest 平台与目录不一致的集接管后为 failed 且不可绑定。

### t081_code_f002 - coordinator 取不到绑定配置快照时回退到当前配置，把待应用配置冒充运行实例字体

- 严重度：important
- 锚点：AC-006（运行状态须报告实际实例绑定的字体与验证结论，旧实例结论不套用到新实例、当前配置与运行观测可区分）
- 位置：`src/backend/cbrowser/api/runtime_coordinator.py:445-460`（`get_font_runtime`）
- 问题：当 `runtime.config_version != profile.current_config_version` 时，代码尝试 `get_config_version` 取快照；快照查询抛异常或返回缺失（`get_config_version` 在版本不存在时抛 `ProfileNotFoundError`，在此被 `except Exception` 吞掉置 `snapshot = None`）后，不做任何区分地 fall through 到 `profile.config`（当前待应用配置）并按运行实例口径返回。失败场景：运行实例绑定的配置版本行缺失或 DB 瞬时错误 → REST/SSE 把新配置的 font_set_id 报告成在跑实例的字体，正是 AC-006 禁止的混淆；且该回退无日志、无标记，外部不可观测。快照命中路径本身实现与测试均正确，问题只在未命中回退方向选错（应 fail-safe 报告未知/空，而不是报告另一份配置）。
- 建议：快照未命中时返回 `(None, [])` 或等价的「未知」结果并记录日志，不要回退当前配置；补一条快照缺失时不冒充当前配置的测试。

### t081_code_f003 - 默认集按目录记录 created_at 排序，不符合「最近接管/验证者胜出」的既定口径

- 严重度：important
- 锚点：关联 spec `docs/specs/fingerprint_platform.md` §2.1（本 task 同步改定的口径：「只取目录中 verified 的集，其中最近接管/验证的胜出」）与 ADR 030「默认集 = 目录中 verified 集按目录记录时间最新者」中「最近接管/验证」的表述；属任务范围声明的「默认集选择」行为缺陷
- 位置：`src/backend/cbrowser/services/font_set_catalog.py:143`（`default_set_id` 的 `records.sort(key=lambda record: (record.created_at, record.set_id))`）
- 问题：`created_at` 是目录行首次插入时间，审计/修复恢复只更新 `verified_at`/`updated_at`、永不更新 `created_at`（`font_repository.py` 的 `apply_audit_verdict` 已核对）。失败场景一：集 A 先接管、集 B 后接管（默认 B），随后 A 被受控修复并重新审计 verified——按 spec 口径「最近验证」应是 A 胜出，代码仍选 B，新建 Profile 默默绑到未修复的旧集。失败场景二：启动接管对多个未记录集并发审计（上限 2），`created_at` 由回执落库顺序决定而非接管/发布时间顺序，同一批集在不同机器上默认集可不同。函数 docstring 自称「most recently cataloged」，与 spec 的「最近接管/验证」不是同一语义。
- 建议：排序键改为最近验证时间（如 `verified_at`，空值垫底）并以 set_id 破平；或若有意改口径，先改 spec 与 ADR 的措辞再改实现——两者须一致。补测试：后修复/后审计的集成为默认。

### t081_code_f004 - record_verified 为无调用方的死代码，且其 docstring 声称的「发布/修复推进 state_seq」在发布路径上不存在

- 严重度：minor
- 锚点：行为缺陷（文档与实现不一致 + 死代码）
- 位置：`src/backend/cbrowser/adapters/database/font_repository.py:96`（`record_verified` 全仓 grep 零调用，生产与测试均无）；对照 `src/backend/cbrowser/font_sets/manifest.py` 的发布路径不写目录
- 问题：接管实际走 `apply_audit_verdict`（expected_seq=None 插入），`record_verified` 从未被调用，其 docstring 却写「Used by adoption」；更重要的是它与 `FontSetRepository` 类 docstring 声称审计围栏能防「迟到的回执覆盖更新的 publish/repair」——但发布/修复（`import_font_set`）根本不触碰目录、不推进 `state_seq`，围栏只对「回执 vs 回执」成立。实际风险被修复流程兜住（运维指南定义修复 = 重导入 + 审计，审计本身推进 seq，且迟到坏回执的方向是 fail-closed），故定 minor；但 docstring 的过强声称会误导后续维护者以为发布侧也有围栏。另外服务层 `_write_lock` 只覆盖 `apply_audit_verdict`，与该死代码无关。
- 建议：删除 `record_verified`，或接管改走它并删除重复的插入逻辑（二选一，只留一条写路径）；把类 docstring 的围栏声称改准为「回执之间」的围栏，发布侧无围栏的事实写进 ADR/指南。

### t081_code_f005 - Supervisor 启动验证围栏键缺 revision/config_version/profile_id，且缓存集合无界增长

- 严重度：minor
- 锚点：行为缺陷（与 spec 范围声明的围栏构成不完全一致：每运行实例/资源修订验证一次，并与 profile_id、runtime_instance_id、config_version、set_id 围栏关联）
- 位置：`src/backend/cbrowser/supervisor/core.py:255`（`_font_verified` 集合定义）、`src/backend/cbrowser/supervisor/core.py:2638`（fence 构造）
- 问题：缓存键只有 `(runtime_instance_id, platform, set_id)`。新实例必换 instance id、内容寻址又保证同 set_id 同内容，故当前不构成可观测的错误放行（同实例重试跳过的是同一挂载内容的重复校验）；但与 spec 声明的围栏构成不一致，未来若 instance id 复用或同实例换配置版本重试，结论会被错误复用。此外该集合只增不减，Supervisor 进程生命周期内每个启动过的实例留一条元组，长期运行缓慢增长。
- 建议：围栏键补上 `config_version`（调用点已有），并在实例停止/删除时清除对应条目，或在 ADR 中明确改定围栏构成并同步 spec 措辞。

### t081_code_f006 - lifespan 接管任务的失败不可观测

- 严重度：minor
- 锚点：行为缺陷（健壮性/可观测：后台任务异常被静默吞没）
- 位置：`src/backend/cbrowser/api/app.py:323`（`app.state.font_adopt_task = asyncio.create_task(font_catalog.adopt_all())`）
- 问题：接管任务只被创建并存入 state，全仓无 await、无 done callback、无关停时取消。单集审计内部异常已被 `_run_audit` 吞并记录，但 `adopt_all` 自身枚举阶段（根目录/平台目录 `iterdir` 的 OSError 等）抛错时，任务以「Task exception was never retrieved」结束，所有未记录集保持不可绑定且无任何日志线索，运维只能从「绑定被拒」反推。`wait_idle` 也从未被 lifespan 调用。
- 建议：给接管任务加 done callback 记录异常（或在 lifespan 关停段 await 并记录），至少保证接管整体失败在日志中可见。

## 结论

- 本轮新发现：6 条（important 3、minor 3、critical 0）
- 未进表的提示：文件过大（仅结论提示，不进 finding 表）——`src/backend/cbrowser/supervisor/core.py` 3261 行、`src/backend/cbrowser/api/runtime_coordinator.py` 1324 行、`src/backend/cbrowser/services/profile_service.py` 1222 行均为存量大文件，本 task 仅小幅净增（分别约 +25/+40/+40 行），未达「本 task 堆大」的不可信程度，但后续 task 不宜再往这三个文件加新职责；本 task 新建文件（font_set_catalog.py 241 行、font_repository.py 201 行、0011 迁移 52 行）均在阈值内。圈复杂度：本 task 新增/修改函数无一达到 15。删除的两个测试文件（test_a5_font_scan_offload.py、test_t053_coordinator_font_runtime.py）系任务测试策略明令整体删除且 ADR 030 写明理由，废止的是「每请求审计/实时读取禁止缓存」旧语义，其存续属性（离线执行、并发有界、零读路径哈希）已由 test_t081_font_catalog.py 在新语义上重新证明，不构成隐藏仍需行为。其余生产读路径复核：coordinator、font_sets_router、ProfileService 绑定校验均已切目录；runtime Agent 的 /health 按 (platform, set_id) 进程内缓存（ADR 030 已改定其围栏为实例生命周期，与 Agent 进程同生灭，可接受）；指纹验证探针 collect_offline_font_evidence 的 check_font_set 属显式离线证据采集、非运行读路径，不计入 AC-003 的零读取范围。门禁证据复核：.scratch/t081_gate_evidence_final 的 unit junit 恰为 15 条坏（t063×12、t068×2、a16×1，与实施侧自述一致，属存量基线），contract/integration/frontend 等其余套件 exit 0；本 reviewer 独立重跑 test_t081_font_catalog.py + test_font_sets_api.py（unit+integration）24 条全过。
- 总体判断：目录化不可变资源的主链（接管/审计/零读取/围栏）真实落地且有计数门禁锁定，但平台一致性校验在目录路径上丢失（f001）、快照未命中时运行口径冒充（f002）、默认集排序键与既定口径不符（f003）三项均为可观测行为缺陷，AC-001/AC-005/AC-006 打勾不成立，FAIL。
- 系统性 follow-up：无（三项 important 均为本 task 范围内直接修复项，不另立 follow-up）

### AC 复验方式

- AC-001：TICK-VOID，re_verified。导入校验与接管后可绑定已实测（test_t081 首二条 + 本人重跑通过），但目录验证不查 manifest 平台一致性，跨平台 manifest 集会被记录 verified 并可绑定（f001），「错误平台不能被发布为可用」不成立。
- AC-002：TICK-VALID，re_verified。发布 staging+rename 为存量原子机制，接管对 staging 残留不采纳、重复接管不升修订，由 test_adoption_recovers_interrupted_publish_and_is_idempotent 证明且本人重跑通过。
- AC-003：TICK-VALID，re_verified。test_reads_never_touch_font_bytes 以生产 helper 计数锁定 100 次 runtime 解析 + 100 次列表的 check/sha 均为零，REST 与 SSE 共用同一 get_font_runtime 目录路径，本人重跑通过。
- AC-004：TICK-VALID，re_verified。普通读取只读目录（多 Profile 共用不重验）、Supervisor 每实例验证一次由 test_supervisor_verifies_once_per_instance 证明且本人重跑通过；围栏键构成的小缺口见 f005（minor，不推翻本条主语义）。
- AC-005：TICK-VOID，re_verified。删除/额外文件/内容破坏的审计撤销、修复恢复与迟到回执围栏均实测通过（test_audit_detects_damage_repair_restores_and_late_verdict_fenced，本人重跑），但 manifest 平台异常这一类 manifest 异常审计发现不了（f001），「manifest 异常能发现」的打勾不完整成立。
- AC-006：TICK-VOID，re_verified。快照命中时按实例绑定版本报告已实测通过（test_runtime_reports_instance_bound_set_not_pending_config），但快照未命中/查询失败时回退当前配置冒充运行口径（f002），AC 的区分要求在该路径被违反。
- AC-007：TICK-VALID，re_verified。test_audit_concurrency_bounded_deduped_and_reads_progress 证明并发峰值 ≤2、同集去重返回 in_flight、审计阻塞期间读取推进、完成后槽位释放，本人重跑通过。
- AC-008：TICK-VALID，re_verified。宿主源目录变更不泄漏进目录、显式再导入走完整验证由 test_host_source_changes_do_not_leak_until_reimport 证明且本人重跑通过；卷只读/Browser 精确挂载/Stream 无字体挂载为 t080 MountPlanner 存量行为，本 task 未改动该代码。
- AC-009：TICK-VALID，trust_prior。按用户 2026-11-18 裁定与 task.md 处置注记，打勾仅表示云端可做部分完成、真实容器链路验证延期至 pending p131 本地补验；本人核对了处置注记与 p131 文件存在，不作为已实测通过判定。

coverage = 8 / 9

verdict: FAIL

## Round 2 (2026-11-18T12:23:55+08:00)

- task：`t081_immutable_font_resource_lifecycle`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`

reviewed_scope: ee44960870ed1ed0

## Findings

### t081_code_f007 - state_seq 围栏的过强声称仍残留在 repository 与 catalog 两处模块 docstring（f004 修不彻底部分）

- 严重度：minor
- 锚点：行为缺陷（文档与实现不一致）；Round 1 f004 的残留部分
- 位置：`src/backend/cbrowser/adapters/database/font_repository.py:9`（类 docstring 仍称迟到回执「can never overwrite a newer publish, repair or verdict」）；`src/backend/cbrowser/services/font_set_catalog.py:12`（模块 docstring 仍称回执在「a newer publish/repair/verdict」之后会被丢弃）；对照 `docs/blueprint/decisions/20261118_font_asset_lifecycle.md:35`（「发布/修复/更新的回执都会推进 state_seq」同类措辞）
- 问题：发布/修复（`import_font_set`）至今不写目录、不推进 `state_seq`（本轮已复核发布路径无目录写入），围栏实际只在「回执 vs 回执」之间成立。f004 的修复只改实了 `models.py` 的 `FontSetAssetModel` docstring（已写明 publishing/repair writes files only and takes effect through a subsequent audit），处置表声称的 repository/models/catalog 三处改实未全部落地。实际风险仍为 fail-closed 方向（修复后迟到的坏回执至多把已修复集误标 failed、需再审计，不会误标 verified），故维持 minor；但过强声称会继续误导维护者以为发布侧也有围栏。
- 建议：把上述两处 docstring 与 ADR 第 35 行改成与 `models.py` 一致的口径：发布/修复只写文件、经后续审计生效，`state_seq` 只围栏回执之间。

### t081_code_f008 - ADR 030 与 Supervisor 函数 docstring 的默认集/围栏措辞未随 f003/f005 的代码修复同步

- 严重度：minor
- 锚点：行为缺陷（文档与实现不一致）；Round 1 f003、f005 的文档残留
- 位置：`docs/blueprint/decisions/20261118_font_asset_lifecycle.md:68`（后果仍写「默认集 = 目录中 verified 集按目录记录时间最新者」，代码已改为最近验证时间胜出）；`docs/blueprint/decisions/20261118_font_asset_lifecycle.md:45`（消费节仍写 Supervisor 每 `(runtime_instance_id, platform, set_id)` 只验一次，代码围栏已扩为五元组）；`src/backend/cbrowser/supervisor/core.py:2632`（`_validate_font_set` docstring 仍写 once per (runtime_instance_id, platform, set_id)，与同文件第 251 行起的五元组围栏注释不一致）
- 问题：f003/f005 的行为修复本身已落地（见下方复核），spec `docs/specs/fingerprint_platform.md` §2.1 的默认集口径也已对齐「最近一次验证通过的胜出」；但 ADR 030 作为长期真相仍保留旧措辞，后续读者按 ADR 会得到与代码不同的默认集与围栏构成。纯文档滞后，不影响当前行为，故 minor。
- 建议：ADR 第 68 行改为「按最近一次验证通过时间（verified_at）最新者、set_id 破平」，第 45 行与 `core.py` 函数 docstring 的围栏构成同步为 (profile_id, runtime_instance_id, config_version, platform, set_id)。

## 结论

- 前轮 finding 复核：
    - t081_code_f001：已消除。`src/backend/cbrowser/services/font_set_catalog.py:76` 起 `_verify_directory` 在 `get_font_set` 返回 None（manifest 缺失/不可解析或平台不一致）时强制 `integrity.ok=False` 并追加明确 problem，返回的 `ok` 随之为 False；新增 `test_adoption_rejects_platform_and_manifest_defects` 覆盖 foreign-platform、无 manifest、重复条目冲突三案且随套件通过。本 reviewer 另以独立探针直接调用 `_verify_directory`：foreign-platform manifest（文件哈希自洽）→ `ok=False` 且 problems 含平台说明；无 manifest → `ok=False`。
    - t081_code_f002：已消除。`src/backend/cbrowser/api/runtime_coordinator.py:457` 快照查询抛异常或返回 None 时直接 `return None, []`，不再回退当前配置。本 reviewer 以桩服务独立探针复核两条未命中路径（`get_config_version` 抛错、返回 None）均得 `(None, [])`。注记：套件内尚无专门锁定「快照缺失」路径的回归测试，本条以代码核查 + 探针判定已修，测试侧覆盖归 test reviewer 轴。
    - t081_code_f003：已消除（行为）。`src/backend/cbrowser/services/font_set_catalog.py:156` `default_set_id` 排序键改为 `(verified_at or created_at, set_id)`；`apply_audit_verdict` 在每次 ok 回执时刷新 `verified_at`，修复/重验会推进排序。本 reviewer 以桩目录记录独立探针复核：先建后验的集压过后建先验的集成为默认。spec 口径已同步；ADR 措辞残留见 f008（minor）。
    - t081_code_f004：修不彻底（降为残留 minor，见 f007）。`record_verified` 已删除（src/tests 全仓 grep 零引用，仅 progress.md 处置表提及）；`models.py` 的 `FontSetAssetModel` docstring 已改实。但 repository 与 catalog 两处模块 docstring 的围栏过强声称仍在。另复核删除后的 state_seq 语义：接管走 `apply_audit_verdict` 的插入路径（expected_seq=None 且行不存在才插入、并发插入撞 IntegrityError 回滚并返回 False 丢弃），围栏语义自洽，无新问题。
    - t081_code_f005：已消除（行为）。`src/backend/cbrowser/supervisor/core.py:2646` 围栏为 (profile_id, runtime_instance_id, config_version, platform, set_id) 五元组，`start_profile` 在第 2753 行起透传 profile_id/config_version；增长上界已在第 251 行起的注释中写明（按本进程内启动次数计）。函数 docstring 措辞残留见 f008（minor）。
    - t081_code_f006：已消除。`src/backend/cbrowser/api/app.py:326` 起 lifespan 接管任务加 done callback：取消时跳过、异常时以 `cbrowser.api` logger 记录完整异常，接管整体失败（如枚举期 OSError）不再静默。
- 本轮新发现：2 条（minor 2、important 0、critical 0），均为文档与实现不一致的残留，不影响行为正确性。
- 未进表的提示：文件过大同 Round 1——`src/backend/cbrowser/supervisor/core.py` 3276 行、`src/backend/cbrowser/api/runtime_coordinator.py` 1329 行、`src/backend/cbrowser/services/profile_service.py` 1222 行均为存量大文件，本轮修复仅小幅触及；新建文件仍在阈值内（font_set_catalog.py 259 行、font_repository.py 158 行）。圈复杂度：修复涉及函数无一达到 15。`_font_verified` 的类型标注 `set[tuple[str, str, int, str, str]]` 与直接调用时可为 None 的 profile_id/config_version 元素不完全吻合（生产路径 start_profile 恒传实值），属标注精度问题，归入 f008 一并修 docstring 时可顺手收紧。本轮独立复跑：test_t081_font_catalog.py 14/14、test_font_sets_api.py（unit+integration）与 test_t053_font_sets_chain.py 合计 24/24、fontconfig/migration 子集 41/41 全过（gate venv，TMPDIR 指到 workspace 磁盘）。
- 总体判断：Round 1 的三条 important（f001 平台校验、f002 快照冒充、f003 默认集排序）均已真实修复并经独立探针复核，三条 minor 中 f005/f006 行为已修、f004 仅剩 docstring 残留；本轮新发现两条 minor 文档滞后（f007/f008），不构成阻断，PASS。
- 系统性 follow-up：无（f007/f008 均为本 task 内文档同步项，由 implementer 写入 progress.md 处置表即可）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。f001 已修：`_verify_directory` 对 manifest 缺失/平台不一致强制失败，新增接管级测试覆盖 foreign-platform/无 manifest/重复条目三案随套件通过，本人独立探针复核 foreign 与 missing 两案均 `ok=False`。
- AC-002：TICK-VALID，re_verified。发布原子机制未变，接管幂等与目录提交失败不留 ready 由 test_adoption_recovers_interrupted_publish_and_is_idempotent 与 test_adoption_db_commit_failure_leaves_no_ready_record 证明，本人复跑通过。
- AC-003：TICK-VALID，re_verified。test_reads_never_touch_font_bytes 已补 100 次 SSE 装配与 100 次 runtime 视图装配，计数仍恒零，本人复跑通过；读路径仍只读目录。
- AC-004：TICK-VALID，re_verified。双 Profile 共用一集零重验（test_two_profiles_share_one_set_without_reverification）与 Supervisor 每实例验证一次均通过；Supervisor 围栏已扩为含 profile_id/config_version 的五元组，新实例/新版本必重验。
- AC-005：TICK-VALID，re_verified。删除/额外文件/内容破坏/manifest 损坏审计矩阵（test_audit_detects_deletion_extra_file_and_manifest_damage）与 manifest 平台异常（f001 修复）均能发现并标 failed，修复恢复与迟到回执围栏测试通过，本人复跑通过。
- AC-006：TICK-VALID，re_verified。快照命中按实例绑定版本报告（含量 missing 列表断言）测试通过；快照未命中路径已改为返回 (None, [])，本人以桩服务探针复核抛错与返回 None 两路均不冒充当前配置。
- AC-007：TICK-VALID，re_verified。并发上限/去重/读取推进之外，新增 test_audit_failure_and_cancellation_free_the_slot 证明验证抛错与在途取消均释放槽位且目录不变，本人复跑通过。
- AC-008：TICK-VALID，re_verified。宿主源目录变更不泄漏、显式再导入走完整验证的测试通过；卷只读/Browser 精确挂载/Stream 无字体挂载为 t080 存量行为，本轮 diff 未改动。
- AC-009：TICK-VALID，trust_prior。按用户 2026-11-18 裁定与 task.md 处置注记，打勾仅表示云端可做部分完成、真实容器链路验证延期至 pending p131 本地补验；本人核对处置注记与 p131 文件存在，不作为已实测通过判定。

coverage = 8 / 9

verdict: PASS

## Round 3 (2026-11-18T12:29:52+08:00)

- task：`t081_immutable_font_resource_lifecycle`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`

reviewed_scope: 1f25991583e7e71c

## Findings

### t081_code_f009 - architecture.md 本 task 新增段落仍含 state_seq 围栏过强声称（f007 同类残留）

- 严重度：minor
- 锚点：行为缺陷（文档与实现不一致）；Round 2 f007 的同类残留，本轮按要求对 `src/backend` 与 `docs/blueprint` 全量 grep「publish/repair 围栏声称」时新发现
- 位置：`docs/blueprint/architecture.md:98`（本 task diff 新增的字体资源段落：「回执按 `state_seq` 围栏条件写入，迟到回执不覆盖新发布/修复」）
- 问题：发布/修复只写文件、不推进 `state_seq`（本轮已复核发布路径无目录写入，与 f007 结论一致），围栏只在回执之间成立；修复后、后续审计生效前，调度在先的迟到坏回执仍可落库把已修复集标 failed（方向封闭、需再审计恢复，但并非「不覆盖修复」）。该句与已改实的 `models.py`、`font_repository.py`、`font_set_catalog.py`、ADR 030 口径不一致，长期真相文件仍会误导维护者以为发布侧受围栏保护。纯文档问题，不影响行为，故 minor。
- 建议：改为与 ADR 030 一致的口径：回执按 `state_seq` 围栏条件写入、迟到回执不覆盖更新的已应用回执/接管结论；发布/修复只写文件、经后续审计回执生效。

### t081_code_f010 - browser_runtime.md 的 A16 默认集口径仍为旧「最新导入（created_at 最大）胜出」（f008 同类残留）

- 严重度：minor
- 锚点：行为缺陷（文档与实现不一致）；Round 2 f008 的同类残留，本轮按要求 grep「旧默认集措辞」时新发现
- 位置：`docs/blueprint/browser_runtime.md:71`（「只取完整性通过的集，其中最新导入（`created_at` 最大）的胜出」）
- 问题：默认集实现已改为目录 verified 集按最近验证通过时间（`verified_at`，空值以 `created_at` 垫底）胜出、set_id 破平（`src/backend/cbrowser/services/font_set_catalog.py:146` 起 `default_set_id`，docstring 与实现一致），spec `docs/specs/fingerprint_platform.md` §2.1 与 ADR 030 第 71 行均已同步为新口径；唯独 browser_runtime.md 的 A16 段落仍按旧扫描语义描述默认集选择，读者按此会得到与代码不同的默认集。该段为 t053 历史段落、本 task diff 未触及此行，但 blueprint 是当前长期真相且本 task 的 finalization 范围含 browser_runtime.md，故在本轮指出。纯文档滞后，不影响行为，故 minor。
- 建议：把该句的默认集胜出规则改为「只取目录中 verified 的集，其中最近一次验证通过的胜出」，或在该段标注默认集口径以 ADR 030 为准。

## 结论

- 前轮 finding 复核：
    - t081_code_f007：已消除。`src/backend/cbrowser/adapters/database/font_repository.py` 模块 docstring 现写明回执「can never overwrite a newer applied verdict or adoption」，且「Publishing and repair write font files only (never the catalog), so they do not move the fences; a repair takes effect through a subsequent audit verdict」；`src/backend/cbrowser/services/font_set_catalog.py` 模块 docstring 现写明回执在「a newer applied verdict or adoption」之后被丢弃、「Publishing/repair writes files only and takes effect through a subsequent audit」，并注明失败方向封闭（stale verdict 至多标不可用、永不验证损坏内容）；ADR 030 第 34-38 行同口径：「已应用的回执与接管都会推进 `state_seq`；发布/修复只写文件、不推进围栏……修复经其后新的审计回执生效（失败方向封闭……）」。三处均与代码一致。同类残留在 architecture.md 的新发现见 f009。
    - t081_code_f008：已消除。ADR 030 第 71-72 行默认集已改为「目录中 verified 集按最近一次验证通过时间最新者（set_id 字典序破平）」，与 `font_set_catalog.py:161` 的 `(verified_at or created_at, set_id)` 排序键及 spec §2.1 一致；ADR 030 第 47-48 行消费节围栏已改为五元组 `(profile_id, runtime_instance_id, config_version, platform, set_id)`；`src/backend/cbrowser/supervisor/core.py` 的 `_validate_font_set` docstring（第 2633-2636 行）已写明「once per (profile_id, runtime_instance_id, config_version, platform, set_id)」，与同函数第 2647 行起实际构造的 fence 五元组逐项一致。同类残留在 browser_runtime.md 的新发现见 f010。
    - Round 1 的 f001-f006 在 Round 2 已逐条复核消除，本轮 diff 相对 Round 2 仅文档措辞变更（指纹 ee44960870ed1ed0 → 1f25991583e7e71c），行为代码未再变动；本轮独立复跑 test_t081_font_catalog.py + test_font_sets_api.py（unit+integration）+ test_t053_font_sets_chain.py 合计 38/38 全过（gate venv），无回归。
- 本轮新发现：2 条（minor 2、important 0、critical 0），均为 f007/f008 同类的文档口径残留，位于本轮指定 grep 范围（docs/blueprint）内、非 Round 2 点名的三处，不影响行为正确性。
- 未进表的提示：文件过大与圈复杂度同前两轮，无变化；本轮 grep 另确认 `src/backend` 内已无旧三元组围栏字面（`(runtime_instance_id, platform, set_id)` 零命中）、无「most recently cataloged」类旧默认集措辞，`models.py:453` 起的 `FontSetAssetModel` docstring 维持 Round 2 已改实的口径。
- 总体判断：Round 2 的两条 minor（f007/f008）在点名位置已全部真实修复，措辞与代码、spec、fingerprint_platform 规格一致；本轮仅新发现同类文档残留两处（f009/f010，minor），不构成阻断，PASS。
- 系统性 follow-up：无（f009/f010 为本 task 内文档同步项，由 implementer 写入 progress.md 处置表即可）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。f001 修复维持：目录验证对 manifest 缺失/平台不一致强制失败，接管级测试随本轮复跑套件通过（38/38）。
- AC-002：TICK-VALID，re_verified。发布原子机制与接管幂等/目录提交失败不留 ready 的测试随本轮复跑通过，本轮文档变更未触及该路径。
- AC-003：TICK-VALID，re_verified。零字体正文读取计数门禁测试（100 次 runtime/SSE/列表）随本轮复跑通过，读路径仍只读目录。
- AC-004：TICK-VALID，re_verified。双 Profile 共用零重验与 Supervisor 每实例验证一次测试通过；Supervisor 围栏五元组代码与 docstring 本轮逐项核对一致。
- AC-005：TICK-VALID，re_verified。审计发现删改/额外文件/manifest 异常矩阵、修复恢复与迟到回执围栏测试随本轮复跑通过；围栏口径文档已改实（f007 消除）。
- AC-006：TICK-VALID，re_verified。快照命中按实例绑定版本报告、未命中返回 (None, []) 不冒充当前配置，Round 2 探针结论维持，本轮代码未变动。
- AC-007：TICK-VALID，re_verified。并发上限/去重/失败与取消释放槽位测试随本轮复跑通过。
- AC-008：TICK-VALID，re_verified。宿主源变更不泄漏、显式再导入完整验证测试通过；卷只读与挂载边界为 t080 存量行为，本轮未改动。
- AC-009：TICK-VALID，trust_prior。按用户 2026-11-18 裁定与 task.md 处置注记（注记存在且表述准确：打勾仅表示云端可做部分完成、真实验证延期本地补验），本人复核处置注记与 `docs/pending/p131_verify_t081_deploy_chain.md` 文件存在，不作为已实测通过判定，不要求云端 Docker 证据。

coverage = 8 / 9

verdict: PASS

## Round 4 (2026-11-18T12:32:39+08:00)

- task：`t081_immutable_font_resource_lifecycle`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`

reviewed_scope: 69f046775b93e50b

## Findings

无（本轮 0 条新发现；f009/f010 已消除，见结论复核）。

## 结论

- 前轮 finding 复核：
    - t081_code_f009：已消除。`docs/blueprint/architecture.md:98`（§3.5）现写明「回执按 `state_seq` 围栏条件写入，迟到回执不覆盖已应用的新回执/接管（发布/修复只写文件、经后续审计生效）」，与 ADR 030 第 34-36 行、`src/backend/cbrowser/adapters/database/models.py:453` 起 docstring（「a late audit can never overwrite a newer applied verdict or adoption (publishing/repair writes files only and takes effect through a subsequent audit)」）、`src/backend/cbrowser/adapters/database/font_repository.py:9` 起 docstring（「Publishing and repair write font files only (never the catalog), so they do not move the fences」）口径逐项一致，不再声称迟到回执「不覆盖新发布/修复」。
    - t081_code_f010：已消除。`docs/blueprint/browser_runtime.md:71`（A16）现写明默认集「只取验证通过（verified）的集，其中最近一次验证通过时间最新（`verified_at` 最大）的胜出」，与 `src/backend/cbrowser/services/font_set_catalog.py` 的 `default_set_id` 实现（verified 集按 `(verified_at or created_at, set_id)` 胜出）、spec §2.1 与 ADR 030 第 71 行一致，不再按「最新导入（created_at 最大）」描述。
    - 本轮最终 grep 扫查（范围 `src/backend` 与 `docs/blueprint`，两类残留）：① 围栏类——`state_seq` 全部命中点（`models.py`、`font_repository.py`、`font_set_catalog.py:12`、ADR 030 第 34-36/53 行、`architecture.md:98`、`testing.md:513`）均为「围栏只约束回执之间、发布/修复只写文件不推进围栏」的正确口径，「不覆盖新发布/修复」类措辞零命中；② 默认集类——「created_at 最大 / 最新导入 / most recently imported / most recently cataloged / import order」类措辞零命中，默认集选择点（`font_sets_router.py:116`、`profile_service.py:475`）均走目录 `default_set_id`。无同类残留。
    - 本轮独立复跑 test_t081_font_catalog.py + test_font_sets_api.py（unit+integration）+ test_t053_font_sets_chain.py 合计 38/38 全过（gate venv），与 Round 3 一致，无回归；Round 3 以来交付内容仅 f009/f010 两处文档措辞变更，行为代码未变动。
- 本轮新发现：0 条。
- 未进表的提示：无。
- 总体判断：Round 3 的两条 minor（f009/f010）已全部真实修复，最终 grep 扫查未发现同类残留，无未解决 critical / important，PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。目录验证与接管级测试随本轮复跑套件通过（38/38），本轮变更仅文档措辞、未触及该路径。
- AC-002：TICK-VALID，re_verified。发布原子机制与接管幂等/目录提交失败不留 ready 的测试随本轮复跑通过。
- AC-003：TICK-VALID，re_verified。零字体正文读取计数门禁测试（100 次 runtime/SSE/列表）随本轮复跑通过，读路径仍只读目录。
- AC-004：TICK-VALID，re_verified。双 Profile 共用零重验与 Supervisor 每实例验证一次测试随本轮复跑通过，围栏五元组口径维持 Round 3 核对结论。
- AC-005：TICK-VALID，re_verified。审计故障矩阵、修复恢复与迟到回执围栏测试随本轮复跑通过；f009 修复后 blueprint 围栏口径与代码/ADR 030 一致。
- AC-006：TICK-VALID，re_verified。运行状态按实例绑定版本报告的测试随本轮复跑通过，本轮代码未变动。
- AC-007：TICK-VALID，re_verified。并发上限/去重/失败与取消释放槽位测试随本轮复跑通过。
- AC-008：TICK-VALID，re_verified。宿主源变更不泄漏、显式再导入完整验证测试随本轮复跑通过；卷只读与挂载边界为 t080 存量行为，本轮未改动。
- AC-009：TICK-VALID，trust_prior。按用户 2026-11-18 裁定与 task.md 处置注记，打勾仅表示云端可做部分完成、真实验证延期至本地补验并由 pending p131 跟踪，不作为已实测通过判定。

coverage = 8 / 9

verdict: PASS

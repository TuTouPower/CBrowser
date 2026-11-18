# Task review t080（reviewer_focus: 代码）

- task：`t080_linux_native_runtime_storage`
- spec：`docs/tasks/t080_linux_native_runtime_storage/task.md`
- diff_anchor：`dffadb298c123ae77a8e8b1f224731ba59030076`
- target：`git diff dffadb298c123ae77a8e8b1f224731ba59030076`
- round：1
- reviewed_at：2026-11-18T08:47:18+08:00

reviewed_scope: 27586567a2b49a22

## Findings

### t080_code_f001 - 删除 Profile 时 API 删的是 data 卷的影子 runtime 目录，runtime 卷中的真实运行期目录永不删除

- 严重度：important
- 锚点：AC-007（删除在新存储中保持既有语义；删除须清掉该 Profile 的私有目录且不触碰其他环境）
- 位置：`src/backend/cbrowser/services/profile_service.py:576`；`compose.yaml:51`；`compose.yaml:155`
- 问题：删除路径只有 API 服务执行（`delete_profile` 对 `profiles`、`runtime`、`runtime-events` 三个子目录做 rmtree），而 t080 后 API 容器只挂 data/db/fonts 三卷（compose.yaml:51-53），其 `/data/runtime/<profile_id>` 是 data 卷里的普通目录；Supervisor 视图中真正的运行期目录是 runtime 卷挂在 `${CBROWSER_DATA_ROOT}/runtime`（compose.yaml:155-166），装着该 Profile 的 snapshot.json、Xauthority、x11/pulse 等文件。两者是不同物理内容：API 的删除对 runtime 卷毫无作用，Supervisor 侧也没有任何按 Profile 清理 runtime 卷目录的路径（core 只有孤儿容器清理）。结果是被删 Profile 的运行期文件（包括 Xauthority 这类凭据性材料）永久残留在 runtime 卷，与既有删除语义（私有目录删净、失败可续跑）不符；deploy.sh 里「API 看到的是普通目录，无害」的注释与此事实矛盾。失败场景：创建并运行 Profile → 停止 → 经 API 删除 → DB 行与 profiles/runtime-events 已删，但 runtime 卷 `<profile_id>/…` 完整保留且无人再清。
- 建议：给 API 服务增加 runtime 卷的精确挂载（如仅挂 runtime 卷并按 Supervisor 同路径删除 `<profile_id>` 子树），或把 runtime 子树删除改为经 Supervisor 执行；同时处理 `runtime/.secrets/<profile_id>` 的归属清理，并在新存储下补删除后 runtime 卷为空的断言。

### t080_code_f002 - 迁移盘点对缺失的源根目录 fail-open：不存在的源被当成空清单并可一路「成功」完成迁移

- 严重度：important
- 锚点：AC-004 / AC-005（apply 前置校验失败须在切换前中止；完整迁移后文件摘要与引用保持一致）
- 位置：`src/backend/cbrowser/supervisor/storage_migration.py:113`（`_walk_records`）；`src/backend/cbrowser/supervisor/storage_migration.py:162`（`build_plan`）
- 问题：`_walk_records` 在 `root.is_dir()` 为假时直接返回空列表，不报错；`build_plan` 对数据根与字体根都如此。审阅者实测：`build_plan(Path("/tmp/definitely-missing-data-xyz"), Path("/tmp/definitely-missing-fonts-xyz"))` 返回 0 条记录的合法 plan（digest 4f53cda1…）。于是操作者把 `--source-fonts-dir` 写错一位时，`inventory` 以退出码 0 打印「files: 0」，`run` 在恢复点验证通过后 stage/switch 零文件并把 journal 置 `done`——字体集（或整个数据根）静默丢失，事后无任何信号。同函数 `os.walk(..., followlinks=False)` 未传 `onerror`，目录枚举错误同样被默认吞掉，盘点可静默不完整。
- 建议：`build_plan`/`_walk_records` 对源根不存在或不是目录直接抛 `MigrationError`（CLI 的 rollback 空 plan 构造应改走独立的空 plan 入口，不要靠缺失目录的副作用）；给 `os.walk` 传 `onerror` 把枚举错误汇入 problems 失败封闭。

### t080_code_f003 - AC-004 明列的「归属不符」校验在迁移工具中不存在：工具不接收也不核对任何部署/卷身份

- 严重度：important
- 锚点：AC-004（检测到归属不符时 apply 在切换前失败）；范围区「迁移工具提供……容量与归属校验」
- 位置：`scripts/storage_migration.py:54`（CLI 参数全集）；`src/backend/cbrowser/supervisor/storage_migration.py:342`（`_check_writers`）；`src/backend/cbrowser/supervisor/storage_migration.py:361`（`_check_capacity`）
- 问题：切换前校验只有写者检测与容量两项。`MigrationRunner` 与 CLI 都没有任何部署身份输入（无 instance_id、无 prefix、无 release 记录、无目标卷名/标签），因此无法发现「目标卷属于另一部署」「源树属于另一实例」这类归属不符：把另一部署的空卷误传为 `--data-volume` 时，迁移会正常把数据拷入并置 done；同路径同内容时还会走 adopt 分支。`docs/blueprint/architecture.md` 3.4 与 ADR 029 却宣称迁移含「归属校验」，文档与实现不一致。AC-004 打勾声明包含归属不符检测，实际缺失。
- 建议：给 CLI/runner 增加期望的部署身份（如 instance_id 或卷名集合），切换前核对目标卷身份/既有 release 记录与源树归属，不符即失败并给出脱敏可定位原因；或若决定不做，必须先修订契约区 AC-004 与 blueprint 口径，不得以现状打勾。

### t080_code_f004 - 经正式 CLI 入口回退时 run_id 被空 plan 重派生，staging 残留清不掉且 journal 身份被覆写

- 严重度：important
- 锚点：行为缺陷——回退是迁移工具的正式入口（scripts/storage_migration.py rollback），失败场景见下
- 位置：`scripts/storage_migration.py:129`（rollback 构造空 plan）；`src/backend/cbrowser/supervisor/storage_migration.py:257`（`__post_init__` run_id 派生）；`src/backend/cbrowser/supervisor/storage_migration.py:293`（`_staging_dir`）；`src/backend/cbrowser/supervisor/storage_migration.py:455`（`rollback`）
- 问题：CLI rollback 用不存在的源路径构造空 plan 再建 runner，`run_id` 由 plan digest 派生，与原运行必然不同。审阅者实测同一 journal 下原 run_id `c42342848d60`、CLI rollback runner 的 run_id 为 `3e94b0257a53`，其 `_staging_dir` 指向 `.migration-staging-3e94b0257a53`，而真实残留是 `.migration-staging-c42342848d60`。后果有二：(1) 在 staged/verified/部分 switched 阶段回退（正是最需要回退的时点）时，staging 里可达全量数据副本的残留不会被清，静默留在目标卷；(2) `rollback` 末尾 `_save_journal("rolled_back")` 把 journal 的 run_id 与 plan_digest 覆写成空 plan 的值，journal 与原运行的对应关系被破坏。现有 unit 测试用同一个 runner 对象回退，恰好掩盖了此缺陷。
- 建议：rollback 应以 journal 中记录的 run_id/plan_digest 为准（加载 journal 后采用其 run_id 定位 staging），或 CLI rollback 要求并校验原 plan；补一条经 CLI 入口（空 plan 路径）回退并断言 staging 已清、journal run_id 不变的测试。

### t080_code_f005 - detect_writers 忽略 lsof 退出码，lsof 执行失败被当作「无写者」放行

- 严重度：minor
- 锚点：AC-004（实际写者检测）
- 位置：`src/backend/cbrowser/supervisor/storage_migration.py:182`（`detect_writers`）
- 问题：`subprocess.run(["lsof", ...])` 未检查 `returncode`，lsof 非零退出（枚举失败/权限问题）且 stdout 为空时返回空列表，`_check_writers` 据此判定无写者继续迁移；与「lsof 缺失时必须显式确认停栈」的 fail-closed 设计相比，lsof 存在但失败反而 fail-open。
- 建议：非零退出时返回 None（走显式确认路径）或抛 `MigrationError`，并在 stderr 非空时记录脱敏原因。

### t080_code_f006 - 迁移只搬文件：空目录被丢弃、目录权限不保留

- 严重度：minor
- 锚点：AC-005（迁移后文件摘要一致之外的结构保持）
- 位置：`src/backend/cbrowser/supervisor/storage_migration.py:113`（`_walk_records` 只记录文件）；`src/backend/cbrowser/supervisor/storage_migration.py:384`（`_copy_file` 仅对文件 copymode）；`src/backend/cbrowser/supervisor/storage_migration.py:440`（`_switch` 中 `destination.parent.mkdir` 用默认权限）
- 问题：plan 只含文件记录，源树中的空目录（如尚无内容的 Artifact 子目录、字体集空目录）在目标卷中不会出现；目录本身的权限位也不迁移，目标目录一律按进程 umask 新建。文件摘要不受影响，但「目录在位」被个别消费方以 is_dir 判定的场景（如 engine-cache/geoip 空目录）在迁移后与源不一致，需靠其他路径重建才恢复。
- 建议：在 plan 中记录目录条目（含空目录与 mode），stage/switch 时一并创建并恢复权限；或在 ADR/指南中明确声明目录结构不迁移并列出依赖重建的消费方。

## 结论

- 本轮新发现：6 条（important 4、minor 2）
- 未进表的提示：文件过大（仅结论提示，不进 finding 表）——`src/backend/cbrowser/supervisor/docker_adapter.py` 2737 行、`scripts/deploy.sh` 1257 行均早已超 800 行且本 task 仍净增（分别 +18、+96 行）；新建 `src/backend/cbrowser/supervisor/storage_migration.py` 480 行，超实现源码 400 行 minor 阈值、未超 800 行。圈复杂度手算提示：`storage_migration.py` 的 `_walk_records` 约 10–11，建议后续拆分盘点与分类。范围外观察：无。
- 总体判断：挂载构造（MountPlanner/volume_spec/compose/deploy 卷接线）与迁移 journal 主干真实落地且 t080 五个测试文件经审阅者复跑 39 passed，但删除语义在新卷拓扑下被影子目录打断（f001）、迁移盘点与归属校验存在 fail-open/缺失（f002/f003）、正式 CLI 回退路径有身份错位缺陷（f004），存在未解决 important，FAIL。
- 系统性 follow-up：无（真实 Engine/部署补验已由 p127、p129 跟踪；上述 finding 均为本 task 内修复项，不另立 follow-up）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。compose.yaml 已把 data/fonts 改为 named volume、Supervisor 以 runtime 卷 subpath 挂 runtime/gates/sockets，代码层无热数据 bind mount 残留（grep 全仓 containers.run/create 挂载点均经 MountPlanner）；真实 Engine 部分按契约区处置注记延期 p127，不表示已实测。
- AC-002：TICK-VALID，re_verified。MountPlanner 对受管根外/卷根来源构造期抛 PathSecurityError（storage_layout.py:65-100），Browser/Stream 挂载集合经审阅者复跑 test_t080_adapter_mounts 与 test_t080_storage_layout 通过，Stream 挂载 Source 仅 runtime 卷；真实 Engine 隔离实证按处置注记延期 p127。
- AC-003：TICK-VALID，re_verified。Profile/Artifact/预览/runtime-events/spool 位于 data 卷、socket/gate 位于 runtime 卷，diff 内无 Supervisor 重启清 runtime 卷的路径，init-layout 仅幂等建目录；真实重启链路按处置注记延期 p129。
- AC-004：TICK-VOID，re_verified。写者/容量/备份/摘要四项有实现且测试通过，但盘点对缺失源根 fail-open（f002，审阅者实测空 plan）和归属校验完全缺失（f003），打勾声明与实现不符。
- AC-005：TICK-VALID，re_verified。迁移按相对路径+SHA-256 搬运、冲突拒绝覆盖、同内容 adopt 不改身份，审阅者复跑 test_t080_storage_migration（含 happy path/冲突/回退用例）通过；DB 与身份字段不被迁移工具改写。
- AC-006：TICK-VALID，re_verified。journal 分阶段推进、\_switch 逐文件记 placed 后落盘、复制故障注入后按 journal 续跑的用例经审阅者复跑通过，源树全程不改写；f004 为回退 CLI 的行为缺陷，另行锚定，不改变本条「中断后恢复旧集或新集」的判定。
- AC-007：TICK-VOID，re_verified。克隆/重置/上传下载/预览/恢复点路径在 data 卷上语义保持，但删除 Profile 时 API 删的是 data 卷影子 runtime 目录、runtime 卷真实目录永不删除（f001），删除语义在新存储下未完整保持。
- AC-008：TICK-VALID，re_verified。字体文件按原相对路径迁入 fonts 卷（set_id 即目录名，staging 阶段逐文件摘要校验），Browser 以 subpath `<platform>/<set_id>` 只读挂载，缺失集由 Supervisor core 的 \_validate_font_set 在启动前失败封闭；真实挂载摘要按处置注记延期 p129。
- AC-009：TICK-VALID，trust_prior。云端可做部分（迁移工具、deploy harness 的备份/回退演练）经审阅者复跑 test_t080_deploy_harness 通过；真实 Chrome 全链路演练无法在云端独立复验，按契约区处置注记依赖 p127 本地统一补验，不表示已实测通过。

coverage = 8 / 9

verdict: FAIL

## Round 2 (2026-11-18T09:11:13+08:00)

- task：`t080_linux_native_runtime_storage`
- round：2
- reviewed_at：2026-11-18T09:11:13+08:00

reviewed_scope: a8d79f03413c0e9d

## Findings

### t080_code_f007 - 回退后再次 run 是静默空转：journal 停在 rolled_back、CLI 退出码 0、零文件迁移

- 严重度：important
- 锚点：行为缺陷（与 AC-006 的 journal 恢复语义相邻）——回退是迁移工具的正式终态之一，回退后修正问题再重跑是自然恢复路径；失败场景见下
- 位置：`src/backend/cbrowser/supervisor/storage_migration.py:399`（`run` 的 phase 分发无 `rolled_back` 分支）；`src/backend/cbrowser/supervisor/storage_migration.py:662`（`rollback` 落盘 `rolled_back`）；`scripts/storage_migration.py:128`（run 分支无条件 `return 0`）
- 问题：`run()` 只分发 `""`/`planned`/`inventoried`/`backup_verified`/`staged`/`verified`/`switched`/`done` 各 phase，`rolled_back` 不匹配任何分支，函数直接返回 `"rolled_back"`，CLI 据此打印该 phase 并以退出码 0 结束。审阅者实测（隔离合成树）：run→`done` 且文件就位 → 经 CLI 式空 plan runner rollback→`rolled_back` 且文件移除 → 用同一 plan/journal 新建 runner 再 run→返回 `rolled_back`，目标文件仍不存在，journal phase 不变。即操作者回退后想重做迁移时，工具不报错、不迁移、还报成功退出；全仓无任何文档/提示说明须先删 journal 才能重跑。数据不丢失（源树保留、旧集完整），但这是与 f002 同类的假成功信号，且堵死回退后的重做路径。
- 建议：`run()` 对 `rolled_back` phase 明确处置——或视为新事务起点（在校验 plan_digest 一致后重置 phase 并完整重跑各阶段检查），或抛 `MigrationError` 明确要求更换/删除 journal；CLI 对未达 `done` 的返回值不得以 0 退出。补一条「run→rollback→run 同 plan 应完成迁移或显式失败」的测试。

### t080_code_f008 - f006 的 placed_dirs 只在首个文件落盘时才入 journal：\_switch 在建目录后、首文件前失败时回退清不掉新建目录

- 严重度：minor
- 锚点：行为缺陷——f006 处置自述「journal 记录 placed_dirs，rollback 清理本轮新建且已空的目录」，该承诺在失败路径不成立
- 位置：`src/backend/cbrowser/supervisor/storage_migration.py:576`（`placed_dirs` 仅写入内存 `self._journal`）；`src/backend/cbrowser/supervisor/storage_migration.py:613`（首次 `_save_journal` 在文件 replace 之后；adopt 分支不落盘）；`src/backend/cbrowser/supervisor/storage_migration.py:652`（rollback 只按 journal 中的 `placed_dirs` 清理）
- 问题：`_switch` 先建全部目录、再逐文件处理；若在第一个非 adopt 文件落盘前失败——典型即目标同名异内容冲突（`storage_migration.py:600` 附近的 designed 拒绝路径）——journal 里没有 `placed_dirs`，随后经 CLI 回退也删不掉本轮新建的空目录。审阅者实测：verified 阶段 journal + 预置冲突文件 → `_switch` 已建 `artifacts/p1/empty-dir` 后抛错，journal 仍无 `placed_dirs` → CLI 式 rollback 后 `artifacts/p1/empty-dir` 与 `artifacts/p1` 仍在目标卷。后果仅为空目录残留，无数据错误，故 minor；完成路径的目录/权限迁移本身正确（见 f006 复核）。
- 建议：目录创建后立即 `_save_journal` 一次（或把目录创建与首个落盘合并为一个 journal 写入点之前的最小单元），使任何 `_switch` 失败点上 journal 都完整记录已建目录。

### t080_code_f009 - f003 源归属校验与 CLI 自带文档示例的挂载路径不一致：按 docstring 挂载时迁移必然在 backup_verified 失败

- 严重度：minor
- 锚点：AC-004（归属校验已落地，但其路径比对与工具自身文档的调用方式互斥）；文档与实现不一致
- 位置：`src/backend/cbrowser/supervisor/storage_migration.py:465`（`_check_source_ownership` 以 resolve 后的绝对路径比对 manifest `data_root` 与 plan 源根）；`scripts/storage_migration.py:8`（docstring 示例把源挂在 `/source-data`）；`scripts/restore_point.py:349`（manifest 记录创建时传入的 `--data-root` 原值，`deploy.sh env-backup` 恒传 `/data`）
- 问题：项目自身 `env-backup` 产出的恢复点 manifest 里 `data_root` 恒为 `/data`（旧版 deploy.sh 亦然：宿主数据根挂到容器 `/data` 再以 `--data-root /data` 创建）。操作者若按迁移 CLI docstring 示例把旧宿主树挂到 `/source-data` 并以此为 `--source-data-root`，`_check_source_ownership` 必然判定「restore point was taken from a different data root」而中止——校验本身 fail-closed、无数据风险，且存在未文档化的绕法（把源挂到 `/data`），故 minor；但 f003 的源归属一半按文档路径不可达，属修复引入的可用性缺口。
- 建议：在 CLI docstring/迁移指南中明示「源树在迁移容器中的挂载路径必须与恢复点 manifest 记录的 `data_root` 一致（env-backup 产出为 `/data`）」，或把源归属比对改到不依赖容器内挂载路径的身份（如 manifest 记录的相对结构/DB 身份）。

## 结论

- 前轮 finding 复核：
    - t080_code_f001：已消除。`compose.yaml:55` 给 api 增加 `runtime:/data/runtime`，API 与 Supervisor 的 runtime 视图为同一物理卷；`src/backend/cbrowser/services/profile_service.py:581` 起删除时一并清理 `runtime/.secrets/<profile_id>`；deploy.sh 的错误注释已更正为准确的 shadow 说明。审阅者复跑 `test_t080_deploy_wiring`（含 api 挂载断言）与 `test_t035_profile_domain`（含 .secrets 清理断言）在内的 61 条测试全过。
    - t080_code_f002：已消除。`storage_migration.py` 的 `_walk` 对源根缺失/非目录直接抛 `MigrationError`，`os.walk` 传 `onerror` 汇入 problems 失败封闭；`test_build_plan_refuses_missing_source_roots` 通过（审阅者复跑）。
    - t080_code_f003：已消除（校验本体）。CLI run 必填 `--expected-prefix`（`scripts/storage_migration.py:64`），`MigrationRunner._check_ownership`（`storage_migration.py:446`）切换前逐卷核对 `deploy_volume_ops.py` 的 `_stamp_volume_identity` 标记，`_check_source_ownership`（`storage_migration.py:465`）核对恢复点来源；两条新增拒绝测试通过。但该修复另引入文档路径互斥的 minor，见本轮 f009，不改变本条已修判定。
    - t080_code_f004：已消除。CLI rollback 改用 `MigrationPlan.empty()`（`scripts/storage_migration.py:137`），`rollback` 从 journal 采纳原 run_id 定位 staging（`storage_migration.py:628` 起），`_save_journal` 身份字段为 setdefault 写一次语义（`storage_migration.py:368`）；`test_cli_style_rollback_adopts_journal_identity` 通过，审阅者独立探针亦确认回退后 journal 的 run_id/plan_digest/total_bytes 不变。
    - t080_code_f005：已消除。`detect_writers`（`storage_migration.py:244`）检查 lsof 退出码与 stderr，失败/超时返回 None 走显式确认路径；`test_detect_writers_treats_lsof_failure_as_unavailable` 通过。
    - t080_code_f006：主体已修、残留 minor。完成路径下空目录与目录 mode 经 DirRecord 在 `_switch` 建目录并在文件就位后深→浅恢复，`test_migration_preserves_empty_directories_and_modes` 通过；但 placed_dirs 的 journal 落盘时机有缺口，见本轮 f008。
- 本轮新发现：3 条（important 1、minor 2）
- 未进表的提示：文件过大（仅结论提示）——`src/backend/cbrowser/supervisor/storage_migration.py` 现 663 行，超实现源码 400 行 minor 阈值、未超 800 行；`docker_adapter.py` 2737 行、`scripts/deploy.sh` 1261 行仍超 800 行（存量，本 task 仍净增）。圈复杂度手算提示：`storage_migration.py` 的 `_walk` 约 13–15，建议后续拆分。范围外观察：`_check_ownership` 只在全新 `planned` 前执行、resume 不复检——与写者/容量检查的既有一次性语义一致，本轮不另出 finding；真实 Engine/部署补验仍由 p127/p129 跟踪。
- 总体判断：round 1 的 4 条 important 与 f005 已真实修复、f006 主体修复，但修复轮在 journal 终态处理上留有新 important（f007：回退后重跑静默空转且退出码 0），本轮 FAIL。
- 系统性 follow-up：无（f007–f009 均为本 task 内修复项；真实部署补验已由 p127、p129 跟踪）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。compose.yaml 已把 data/fonts/runtime 改为 named volume、API 新增 runtime 卷挂载、Supervisor 以 runtime 卷 subpath 挂 runtime/gates/sockets，挂载构造与运行清单无 macOS 热数据 bind mount；审阅者复跑 test_t080_adapter_mounts/test_t080_storage_layout/test_t080_deploy_wiring 通过；真实 Engine 部分按契约区处置注记延期 p127，不表示已实测。
- AC-002：TICK-VALID，re_verified。MountPlanner 对受管根外/卷根来源构造期抛 PathSecurityError，Browser/Stream 挂载集合经审阅者复跑通过，Stream 不获 Profile/Artifact/字体；真实 Engine 隔离实证按处置注记延期 p127。
- AC-003：TICK-VALID，re_verified。Profile/Artifact/预览/runtime-events 位于 data 卷、socket/gate 位于 runtime 卷，diff 内无 Supervisor 重启清 runtime 卷的路径，init-layout 仅幂等建目录与盖身份标记；真实重启链路按处置注记延期 p129。
- AC-004：TICK-VALID，re_verified。dry-run 只读不变性、写者（f005 已修）/容量/归属（f003 已落地：卷标记 + 恢复点来源双校验）/备份可恢复/摘要校验均有实现且新增测试经审阅者复跑通过；f009 为文档挂载路径互斥的 minor，不使校验本体失效。
- AC-005：TICK-VALID，re_verified。迁移按相对路径 + SHA-256 搬运、身份字段不被工具改写、冲突拒绝覆盖、同内容 adopt 不改身份，完成路径新增目录/权限保持（f006）；审阅者复跑 test_t080_storage_migration 全套通过。
- AC-006：TICK-VALID，re_verified。journal 分阶段推进、复制故障注入后按 journal 续跑、CLI 式回退采纳原身份并清 staging 均经审阅者复跑/独立探针确认，源树全程不改写；f007 为回退终态后「新事务重跑」的行为缺陷，另行锚定，不改变本条「中断后恢复旧集或完成新集」的判定。
- AC-007：TICK-VALID，re_verified。f001 已修：API 删除的是 runtime 卷真实目录并清理 .secrets（compose 挂载 + profile_service 代码 + 两处断言经审阅者复跑通过）；克隆/重置/上传下载/预览/恢复点路径在 data 卷上语义保持；真实部署链路按处置注记延期 p129。
- AC-008：TICK-VALID，re_verified。字体按原相对路径迁入 fonts 卷、set_id 目录名不变、Browser 以 subpath 只读挂载、缺失集启动前失败封闭；真实挂载摘要按处置注记延期 p129。
- AC-009：TICK-VALID，trust_prior。云端可做部分（迁移工具、deploy harness 的备份/回退演练）经审阅者复跑 test_t080_deploy_harness 通过；真实 Chrome 全链路演练无法在云端独立复验，按契约区处置注记依赖 p127 本地统一补验，不表示已实测通过。

coverage = 8 / 9

verdict: FAIL

## Round 3 (2026-11-18T09:17:34+08:00)

- task：`t080_linux_native_runtime_storage`
- round：3
- reviewed_at：2026-11-18T09:17:34+08:00

reviewed_scope: 212f0d9c8bd704e5

## Findings

### t080_code_f010 - done 终态绕过 plan_digest 校验：异 plan 复用已完成 journal 时静默返回 done、零文件迁移、CLI 退出码 0

- 严重度：important
- 锚点：行为缺陷（与 AC-005「重复运行不改变身份」及 AC-006 的 journal 恢复语义相邻）——`done` 是迁移工具的正式终态，异 plan 复用同一 journal 是可达的操作者错误；失败场景见下
- 位置：`src/backend/cbrowser/supervisor/storage_migration.py:402`（`run` 在 plan_digest 校验前对 `done` 提前返回）；`src/backend/cbrowser/supervisor/storage_migration.py:415`（通用异 plan 拒绝分支对 `done` 不可达）；`scripts/storage_migration.py:127`（run 分支对返回 phase 无条件 `return 0`）
- 问题：`run()` 的顺序是先 `_load_journal()`、见 `done` 立即 `return "done"`，其后的异 plan 拒绝（415 行）永远轮不到 `done` 终态执行；`rolled_back` 分支反而有自己的 digest 校验（410 行），两终态处理不一致。审阅者独立探针实测（隔离合成树）：plan A run→`done` → 源树新增 Profile p2 后以异 plan B、同一 journal 再 run→返回 `done`，p2 文件未迁移，journal phase 不变，CLI 层据此以退出码 0 报成功。与 f007 同类的假成功信号：同 plan 重跑 `done` 空转是 AC-005 要求的幂等，但异 plan 时工具不报错、不迁移、还报成功，操作者会误以为第二批数据已迁入。数据不丢失（源树保留），但堵死了「同 journal 路径迁第二批/改源后重跑」的发现路径。
- 建议：把 plan_digest 一致性校验提到 `done` 提前返回之前（同 plan `done` 仍直接返回、保持幂等；异 plan 抛 `MigrationError` 明确拒绝复用 journal）；补一条「run→done 后异 plan 同 journal 再 run 应显式失败且 journal 不变」的测试。

### t080_code_f011 - f009 内容锚定源归属校验只做单向比对：零 Profile 恢复点与 subset 恢复点均可通过，源 Profile 实际未被该恢复点覆盖

- 严重度：important
- 锚点：AC-004（检测到归属不符、备份缺失时 apply 在切换前失败）；范围区「先证实备份能够恢复，再允许改写指针或数据」
- 位置：`src/backend/cbrowser/supervisor/storage_migration.py:476`（`_check_source_ownership`）；`src/backend/cbrowser/supervisor/storage_migration.py:490`（只遍历 manifest 记录的 profiles/files，源树一侧无覆盖集合比对）；`src/backend/cbrowser/supervisor/storage_migration.py:486`（docstring 明示 zero-Profile point 无锚点时以其自身完整性验证为准）
- 问题：内容锚定只证明「manifest 记录的每个文件都在源树中且摘要一致」（manifest ⊆ 源），不证明反向覆盖：(1) 审阅者独立探针实测，源树含 Profile p1 时，换入一个他部署的、自洽可验证但 `profiles` 为空的恢复点，`run()` 一路 `done`——该点对源树零锚定、零覆盖，归属不符未被检出；(2) 源树含 p1+p2、恢复点只记录 p1（同源旧点或他部署恰含 p1 同内容文件的点）时同样 `run()`→`done`，p2 实际没有可恢复备份却照常切换。f009 的路径互斥已消除、他部署自洽点在记录内容不同时确被拒绝（见复核），但校验完整性只及单向：AC-004 要求的「归属不符/备份缺失在切换前失败」对这两类可达输入不成立。
- 建议：做双向覆盖比对——由 plan 记录（`profiles/<id>/…`）得出源树 Profile 集合，要求与 manifest 的 profile `dir` 集合一致，源有 Profile 而恢复点无对应锚点（或集合不一致）即在切换前失败并给出脱敏可定位原因；补两条测试：零 Profile 外来恢复点被拒、subset 恢复点（源多一个 Profile）被拒。

## 结论

- 前轮 finding 复核：
    - t080_code_f007：已消除。`run()`（`storage_migration.py:404` 起）对 `rolled_back` 先验 plan_digest、异 plan 抛 `MigrationError` 且不清空 journal，同 plan 清空 journal 后从头执行全部阶段检查。审阅者独立探针实测：run→`done`→rollback→`rolled_back` 后，异 plan 再 run 被拒且 journal 逐字节不变；同 plan 再 run 返回 `done` 且目标文件就位。写一次身份与重启的交互亦核实无误：rollback（CLI 式空 plan runner）采纳原 run_id 落盘，回退后同 plan 重跑前后 journal 的 run_id/plan_digest 一致（探针三段 journal 对比相同），`_save_journal` 的 setdefault 写一次语义在清空重跑后以派生 run_id 重建、同路径同 plan 下与原值相同，未见误清或覆写。新增测试 `test_run_after_rollback_starts_over_and_completes` 经审阅者复跑通过。
    - t080_code_f008：已消除。`_switch`（`storage_migration.py:607`）先把 `placed_dirs` 写进内存 journal 并在首个文件落盘前 `_save_journal("verified")`（611 行）。审阅者独立探针实测 round 2 的原失败场景：verified 阶段预置同名异内容冲突文件→`_switch` 建出 `artifacts/p1/empty-dir` 后被拒→经 CLI 式空 plan runner rollback 后该目录及其父 `artifacts/p1` 均被清除。新增测试 `test_rollback_after_switch_failure_removes_created_directories` 经审阅者复跑通过。另核 `_switch` 其余落盘时机：非 adopt 文件逐个落盘后即 `_save_journal`，中断后按 journal 的 `placed` 跳过已落盘文件续跑；adopt 分支不立即落盘但 adopt 文件本就不由 rollback 删除且续跑会重新 adopt，无可观测不一致。
    - t080_code_f009：已消除。源归属校验已改为内容锚定（`storage_migration.py:476` 起），不再比对容器内挂载路径：审阅者独立探针实测 manifest `data_root` 为 `/data`（env-backup 在 API 容器内的产出形态）、源树挂在任意路径时 run 正常 `done`，CLI docstring 的 `/source-data` 示例路径不再互斥；改写后的 `test_run_refuses_restore_point_from_another_data_root`（他部署自洽恢复点、记录内容不同）经审阅者复跑通过。但该校验的覆盖完整性另有缺口，见本轮 f011，不改变本条「路径互斥已修」的判定。
    - t080_code_f001–f006：本轮未见回归；审阅者复跑 t080 五个测试文件共 74 条全过（`test_t080_storage_migration`、`test_t080_storage_layout`、`test_t080_adapter_mounts`、`test_t080_deploy_wiring`、`test_t080_deploy_harness`）。
- 本轮新发现：2 条（important 2）
- 未进表的提示：文件过大（仅结论提示，不进 finding 表）——`src/backend/cbrowser/supervisor/storage_migration.py` 现 698 行，超实现源码 400 行 minor 阈值、未超 800 行；`src/backend/cbrowser/supervisor/docker_adapter.py` 2737 行、`scripts/deploy.sh` 1261 行仍超 800 行（存量，本 task 仍净增）。圈复杂度手算提示：`storage_migration.py` 的 `_walk` 约 13–15、`_switch` 分支密集，建议后续拆分。范围外观察：`run()` 续跑不像 `rollback()` 那样从 journal 采纳 run_id，staging 定位靠 run_id 由 plan digest+journal 路径确定性派生——同路径续跑经探针证实一致；若操作者两次调用间改写 journal 路径的表示形式（相对/绝对），派生 run_id 不同会使旧 staging 失联，属操作面观察、本轮未实测出可达缺陷，不出 finding。真实 Engine/部署补验仍由 p127、p129 跟踪。
- 总体判断：f007/f008/f009 均真实修复，但全量复审在 `run()` 终态处理与内容锚定完整性上发现 2 条新 important（f010：`done` 终态异 plan 静默空转；f011：源归属校验单向、零/subset 恢复点可通过），本轮 FAIL。
- 系统性 follow-up：无（f010、f011 均为本 task 内修复项；真实部署补验已由 p127、p129 跟踪）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。compose.yaml 已把 data/fonts/runtime 改为 named volume、API 挂 runtime 卷、Supervisor 以 runtime 卷 subpath 挂 runtime/gates/sockets，挂载构造与运行清单无 macOS 热数据 bind mount；审阅者复跑 test_t080_adapter_mounts/test_t080_storage_layout/test_t080_deploy_wiring 通过；真实 Engine 部分按契约区处置注记延期 p127，不表示已实测。
- AC-002：TICK-VALID，re_verified。MountPlanner 对受管根外/卷根来源构造期抛 PathSecurityError，Browser/Stream 挂载集合经审阅者复跑通过，Stream 不获 Profile/Artifact/字体；真实 Engine 隔离实证按处置注记延期 p127。
- AC-003：TICK-VALID，re_verified。Profile/Artifact/预览/runtime-events 位于 data 卷、socket/gate 位于 runtime 卷，diff 内无 Supervisor 重启清 runtime 卷的路径，init-layout 仅幂等建目录与盖身份标记；真实重启链路按处置注记延期 p129。
- AC-004：TICK-VOID，re_verified。写者/容量/卷归属/恢复点可恢复/摘要校验均有实现且测试通过，f009 的内容锚定亦已落地；但源归属校验只做单向比对，零 Profile 外来恢复点与 subset 恢复点经审阅者独立探针实测均可一路 `done`（f011），「归属不符/备份缺失在切换前失败」的打勾声明对这两类输入不成立。
- AC-005：TICK-VALID，re_verified。迁移按相对路径 + SHA-256 搬运、身份字段不被工具改写、冲突拒绝覆盖、同内容 adopt 不改身份、目录/权限保持（f006）与回退后同 plan 重跑完成（f007）均经审阅者复跑/独立探针确认；f010 为 `done` 终态对异 plan 的行为缺陷，另行锚定，不改变本条「完整迁移后身份与摘要一致、重复运行不重复复制」的判定。
- AC-006：TICK-VALID，re_verified。journal 分阶段推进、复制故障注入后按 journal 续跑、CLI 式回退采纳原身份并清 staging、rolled_back 异 plan 不误清 journal（探针实测 journal 逐字节不变）均经审阅者复跑/独立探针确认，源树全程不改写；f010 的 `done` 异 plan 静默返回不产生「DB 引用新数据而文件仍为旧集」的跨介质不一致，另行锚定。
- AC-007：TICK-VALID，re_verified。f001 已修且本轮未回归：API 删除的是 runtime 卷真实目录并清理 .secrets（compose 挂载 + profile_service 代码 + 断言经审阅者复跑通过）；克隆/重置/上传下载/预览/恢复点路径在 data 卷上语义保持；真实部署链路按处置注记延期 p129。
- AC-008：TICK-VALID，re_verified。字体按原相对路径迁入 fonts 卷、set_id 目录名不变、Browser 以 subpath 只读挂载、缺失集启动前失败封闭；真实挂载摘要按处置注记延期 p129。
- AC-009：TICK-VALID，trust_prior。云端可做部分（迁移工具、deploy harness 的备份/回退演练）经审阅者复跑 test_t080_deploy_harness 通过；真实 Chrome 全链路演练无法在云端独立复验，按契约区处置注记依赖 p127 本地统一补验，不表示已实测通过。

coverage = 8 / 9

verdict: FAIL

## Round 4 (2026-11-18T09:26:22+08:00)

- task：`t080_linux_native_runtime_storage`
- round：4
- reviewed_at：2026-11-18T09:26:22+08:00

reviewed_scope: c459794e3798e595

## Findings

无（本轮零新发现；前轮 f010/f011 复核结论见结论段，探针实测的 resume/done 参数身份观察未达 finding 阈值、仅作未进表提示）。

## 结论

- 前轮 finding 复核：
    - t080_code_f010：已消除。`run()`（`src/backend/cbrowser/supervisor/storage_migration.py:399`）在 `_load_journal()` 后、任何终态捷径之前先做 plan_digest 一致性校验（405 行：journal 非空且 digest 不符即抛 `MigrationError`），`done` 捷径（409 行）与 `rolled_back` 分支（411 行）均在其后；中间 phase（如 verified）的异 plan journal 同样被该前置校验拦截。审阅者独立探针实测：plan A run→`done` 后同 plan 重跑仍幂等返回 `done`；源树新增 Profile 后异 plan 同 journal 再 run 被拒且 journal 逐字节不变；手工置 verified phase 的异 plan journal 亦被拒。新增测试 `test_done_journal_refuses_a_different_plan` 含于审阅者复跑通过的集合内（见下）。
    - t080_code_f011：已消除。`_check_source_ownership`（`storage_migration.py:475`）在原单向内容锚定之后新增双向覆盖比对（519–543 行）：源 Profile 集合由 plan 的文件记录与目录记录共同得出（`source_root == "data"` 且 `source_rel` 形如 `profiles/<id>/…`，取第二段），manifest Profile 集合由各条目 `dir` 以同一规则得出，两集合不相等即在切换前抛 `MigrationError` 并脱敏列出未覆盖/多余项。审阅者独立探针逐项实测边界：(1) 零 Profile 恢复点对含 p1 的源被拒；(2) subset 恢复点（源 p1+p2、点仅 p1）被拒；(3) 点内多出一个 files 为空的 Profile 条目（单向锚定无从发现）被双向比对以「not in source」拒；(4) 空目录 Profile（源 `profiles/p2/profile/` 无任何文件）：plan 目录记录确含 `profiles/p2` 与 `profiles/p2/profile`，未被点覆盖时被拒、点含 dir 条目（files 为空）时正常 `done` 且目标空目录就位；(5) 仅含 SingletonLock 的 Profile 同样经目录记录进入源集合、未覆盖被拒；(6) `dir=None` 条目不进 manifest 集合——与 `scripts/restore_point.py:298` 的既有语义一致（user_data_dir 不存在时该 Profile 无目录数据可备份、DB 本身另经摘要校验）：点含 dir=None 条目且 p1 被覆盖时正常 `done`，仅有 dir=None 条目而源有 p1 时被拒；(7) 源与点均零 Profile（data 根含控制文件）时正常 `done`，无误拒；(8) manifest `dir` 为 `profiles/p1`（无 `/profile` 后缀）时集合得出不依赖后缀、正常通过。新增测试 `test_run_refuses_zero_profile_restore_point_for_profile_source`、`test_run_refuses_subset_restore_point` 含于复跑通过集合内。
    - t080_code_f001–f009：本轮未见回归；审阅者复跑 t080 五个测试文件共 52 条全过（`test_t080_storage_migration` 21 条含本轮 3 条新测试、`test_t080_storage_layout`、`test_t080_adapter_mounts`、`test_t080_deploy_wiring`、`test_t080_deploy_harness`）。
- 本轮新发现：0 条
- 未进表的提示：文件过大（仅结论提示，不进 finding 表）——`src/backend/cbrowser/supervisor/storage_migration.py` 现 728 行，超实现源码 400 行 minor 阈值、未超 800 行；`src/backend/cbrowser/supervisor/docker_adapter.py` 2737 行、`scripts/deploy.sh` 1261 行仍超 800 行（存量，本 task 仍净增）。圈复杂度手算提示：`storage_migration.py` 的 `_walk` 约 13–15、`_switch` 与 `_check_source_ownership` 分支密集，建议后续拆分。范围外观察（探针实测、不出 finding）：journal 不记录目标卷与恢复点身份——`done` 后以同一 journal、同 plan、不同（空）目标卷再 run 仍返回 `done` 而新卷无文件；自 `backup_verified` phase 续跑时换入零 Profile 恢复点也不复检源归属、径直完成切换。两者均属 round 2 已记录的「阶段检查一次性语义」（写者/容量/卷归属检查同此），且 CLI 文档口径中 journal 位于 data 卷内（`scripts/storage_migration.py` docstring 示例 `--journal /vol-data/…`），换卷通常同时换 journal 路径，探针场景须偏离该口径或在中断后改写调用参数才可达；迁移数据本身始终按 plan 摘要在 staging 阶段逐文件校验，不产生数据错误或跨介质不一致，故按既有处置一致性仅作观察，若未来要收紧可把 targets/restore-point 身份一并记入 journal 并在 resume/done 时核对。真实 Engine/部署补验仍由 p127、p129 跟踪。
- 总体判断：f010/f011 均真实修复且边界探针全数符合预期，全量 diff 复审未发现新的 critical/important，AC 打勾全部成立，本轮 PASS。
- 系统性 follow-up：无（真实部署补验已由 p127、p129 跟踪）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。compose.yaml 已把 data/fonts/runtime 改为 named volume、API 挂 runtime 卷、Supervisor 以 runtime 卷 subpath 挂 runtime/gates/sockets，挂载构造与运行清单无 macOS 热数据 bind mount；审阅者复跑 test_t080_adapter_mounts/test_t080_storage_layout/test_t080_deploy_wiring 通过；真实 Engine 部分按契约区处置注记延期 p127，不表示已实测。
- AC-002：TICK-VALID，re_verified。MountPlanner 对受管根外/卷根来源构造期抛 PathSecurityError，Browser/Stream 挂载集合经审阅者复跑通过，Stream 不获 Profile/Artifact/字体；真实 Engine 隔离实证按处置注记延期 p127。
- AC-003：TICK-VALID，re_verified。Profile/Artifact/预览/runtime-events 位于 data 卷、socket/gate 位于 runtime 卷，diff 内无 Supervisor 重启清 runtime 卷的路径，init-layout 仅幂等建目录与盖身份标记；真实重启链路按处置注记延期 p129。
- AC-004：TICK-VALID，re_verified。dry-run 只读不变性、写者/容量/卷归属/恢复点可恢复/摘要校验均有实现；f011 的单向比对缺口已修为双向覆盖（plan 文件+目录记录 vs manifest dir 集合），零 Profile 点、subset 点、多余空 files 条目点经审阅者独立探针实测均在切换前被拒，空目录 Profile 与 dir=None 条目边界行为与 restore_point 既有语义一致。
- AC-005：TICK-VALID，re_verified。迁移按相对路径 + SHA-256 搬运、身份字段不被工具改写、冲突拒绝覆盖、同内容 adopt 不改身份、目录/权限保持（f006）与回退后同 plan 重跑完成（f007）均经审阅者复跑/独立探针确认；f010 已修——`done` 终态不再绕过 plan 身份校验，异 plan 复用 journal 显式失败且 journal 不变，同 plan 仍幂等。
- AC-006：TICK-VALID，re_verified。journal 分阶段推进、复制故障注入后按 journal 续跑、CLI 式回退采纳原身份并清 staging、rolled_back/done 异 plan 均不误清不误认 journal（探针实测），源树全程不改写。
- AC-007：TICK-VALID，re_verified。f001 已修且未回归：API 删除的是 runtime 卷真实目录并清理 .secrets（compose 挂载 + profile_service 代码 + 断言经审阅者复跑通过）；克隆/重置/上传下载/预览/恢复点路径在 data 卷上语义保持；真实部署链路按处置注记延期 p129。
- AC-008：TICK-VALID，re_verified。字体按原相对路径迁入 fonts 卷、set_id 目录名不变、Browser 以 subpath 只读挂载、缺失集启动前失败封闭；真实挂载摘要按处置注记延期 p129。
- AC-009：TICK-VALID，trust_prior。云端可做部分（迁移工具、deploy harness 的备份/回退演练）经审阅者复跑 test_t080_deploy_harness 通过；真实 Chrome 全链路演练无法在云端独立复验，按契约区处置注记依赖 p127 本地统一补验，不表示已实测通过。

coverage = 8 / 9

verdict: PASS

## Round 5 (2026-11-18T09:41:02+08:00)

- task：`t080_linux_native_runtime_storage`
- round：5
- reviewed_at：2026-11-18T09:41:02+08:00

reviewed_scope: db0d10e046b053d2

## Findings

无（本轮为范围确认轮：零新发现；测试审阅 round 1 的修复未触碰生产代码、未弱化既有断言，复核证据见结论段）。

## 结论

- 前轮 finding 复核：
    - t080_code_f001–f011：round 4 已判定全部消除且本轮未见回归（生产代码未变化的证据见下条），本轮不重复逐条复核结论。
    - 测试审阅 round 1 finding（t080_test_f001–f003）的修复处置，本轮仅从代码轴确认其未引入生产行为变化、未弱化断言：①t080_test_f001——`tests/unit/test_t080_deploy_wiring.py:86` 的 `test_compose_api_mounts_runtime_volume_at_data_runtime` 已改用自 `test_t027_release_controller` 导入的 `_service_block` 限定 api 服务块，并以 strip 后的整行精确成员匹配断言 `- runtime:/data/runtime`（94–96 行），严于原整文件子串匹配，未改 compose 本身；②t080_test_f002——`tests/unit/test_t080_storage_migration.py:542` 新增容量测试（monkeypatch `storage_migration.shutil.disk_usage` 返回 free=0，断言 `MigrationError` 且目标文件未落盘）与 `:567` 新增 dry-run 测试（源/字体树前后摘要快照比对 + CLI `inventory` 子进程返回码与文件数断言），均为新增覆盖，无既有断言删改；`progress.md` 中 AC-004 覆盖自述已同步修正，属流程文件、不影响代码判定；③t080_test_f003——`tests/unit/test_t080_adapter_mounts.py:354` 补回 `stream_ports(30006) == {"30006/udp": ("127.0.0.1", 30006)}` 整值相等断言；`tests/unit/test_t027_release_controller.py:687` 与 `tests/unit/test_refactor_behavior_equivalence.py:173` 两处 NOTE 已分别声明「fonts directory」文案不沿用与 stream_ports 断言去向，NOTE 为注释、无断言变化；`tests/unit/test_t080_deploy_harness.py:165` 的字体预检测试保留 `WARNING` 断言并新增 `"no valid font set found" in result.stdout`（175 行），为增补而非替换弱化。
- 生产代码未变化确认（本轮核心项 ①）：与 round 4 记录逐项对照一致——`src/backend/cbrowser/supervisor/storage_migration.py` 仍 728 行，`run()` 位于 399 行、plan_digest 前置校验位于 405 行、`_check_source_ownership` 位于 475 行且双向覆盖比对在位；`compose.yaml:55` 仍为 api 服务的 `- runtime:/data/runtime`；`src/backend/cbrowser/services/profile_service.py:582` 起仍为删除时清理 `runtime/.secrets/<profile_id>`；`scripts/deploy.sh` 仍 1261 行、`src/backend/cbrowser/supervisor/docker_adapter.py` 仍 2737 行。指纹变化仅由测试文件与 `progress.md` 自述修正解释，重点抽查的 storage_migration.py / compose.yaml / profile_service.py / deploy.sh 均未被测试修复轮触碰。
- 测试运行证据：审阅者复跑 t080 五个测试文件共 55 条全过（round 4 的 52 条 + 本轮新增 3 条：容量、dry-run、stream_ports），另复跑 `test_refactor_behavior_equivalence.py` 与 `test_t035_profile_domain.py` 共 26 条全过；t080 测试文件内无 `.skip` / 恒真断言类弱化模式（grep 仅命中 SingletonLock fixture 的文件名内容）。本轮按任务约束未做变异验证（属测试审阅职责）、未跑全量门禁。
- 本轮新发现：0 条
- 未进表的提示：文件过大（仅结论提示，不进 finding 表）——与 round 4 相同：`src/backend/cbrowser/supervisor/storage_migration.py` 728 行超实现源码 400 行 minor 阈值、未超 800 行；`docker_adapter.py` 2737 行、`scripts/deploy.sh` 1261 行仍超 800 行（存量）。圈复杂度与 round 4 的 resume/done 参数身份观察均无变化，不重复登记。真实 Engine/部署补验仍由 p127、p129 跟踪。
- 总体判断：生产代码相对 round 4 PASS 时未变化，测试侧改动仅为断言加强与覆盖补齐、未引入生产行为变化、未弱化任何既有断言，AC 打勾全部成立，本轮 PASS。
- 系统性 follow-up：无（真实部署补验已由 p127、p129 跟踪）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。生产挂载构造与 round 4 PASS 时逐项一致（compose named volume、API 挂 runtime 卷、Supervisor runtime 卷 subpath，见结论段行数/锚点对照），审阅者复跑 test_t080_adapter_mounts/test_t080_storage_layout/test_t080_deploy_wiring 通过；真实 Engine 部分按契约区处置注记延期 p127，不表示已实测。
- AC-002：TICK-VALID，re_verified。MountPlanner 与 Browser/Stream 挂载集合代码未变化、相关测试复跑通过，Stream 不获 Profile/Artifact/字体；真实 Engine 隔离实证按处置注记延期 p127。
- AC-003：TICK-VALID，re_verified。data/runtime 卷归属与 Supervisor 重启不清空 runtime 的路径未变化、相关测试复跑通过；真实重启链路按处置注记延期 p129。
- AC-004：TICK-VALID，re_verified。迁移校验生产代码未变化（写者/容量/卷归属/源双向覆盖/恢复点/摘要锚点行号与 round 4 一致）；测试侧新增的容量不足与 dry-run 不变性用例经审阅者复跑通过，补齐的是测试覆盖、不改变实现判定。
- AC-005：TICK-VALID，re_verified。迁移搬运、身份保持、冲突拒绝与 `done` 异 plan 拒绝（405 行前置校验）代码未变化，test_t080_storage_migration 全套复跑通过；真实部署身份逐项比对按处置注记延期 p129。
- AC-006：TICK-VALID，re_verified。journal 分阶段推进、故障续跑与回退身份采纳代码未变化，相关用例复跑通过，源树全程不改写。
- AC-007：TICK-VALID，re_verified。f001 修复点未变化：compose.yaml:55 的 api runtime 挂载与 profile_service.py:582 起的 .secrets 清理在位，其防线断言已按整行精确匹配加强（test_t080_deploy_wiring.py:86），克隆/重置/删除等用例复跑通过；真实部署链路按处置注记延期 p129。
- AC-008：TICK-VALID，re_verified。字体迁入与 subpath 只读挂载代码未变化；字体预检测试新增「no valid font set found」断言后复跑通过；真实挂载摘要按处置注记延期 p129。
- AC-009：TICK-VALID，trust_prior。云端可做部分（迁移工具、deploy harness 备份/回退演练）经审阅者复跑 test_t080_deploy_harness 通过；真实 Chrome 全链路演练无法在云端独立复验，按契约区处置注记依赖 p127 本地统一补验，不表示已实测通过。

coverage = 8 / 9

verdict: PASS

## Round 6 (2026-11-18T09:53:22+08:00)

- task：`t080_linux_native_runtime_storage`
- round：6
- reviewed_at：2026-11-18T09:53:22+08:00

reviewed_scope: c2fd594e7f30587d

## Findings

无（本轮为格式化确认轮：零新发现；核实证据见结论段）。

## 结论

- 前轮 finding 复核：t080_code_f001–f011 已于 round 4 判定全部消除、round 5 确认无回归；本轮核实自 round 5 PASS 以来生产代码与测试代码字节未变（证据见下条），故前轮复核结论在本轮范围内继续成立，本轮不重复逐条复核。
- 生产/测试代码未变化确认（本轮核心项 ①）：相对 round 5 PASS 时的工作区，当前未暂存变更（`git diff --name-only`）恰为 4 个文件且全为 Markdown——`docs/tasks/t080_linux_native_runtime_storage/task.md`、`progress.md`、`review_code.md`、`review_test.md`；对 `src`、`tests`、`scripts`、`compose.yaml` 的未暂存 diff 为空，即生产代码与测试代码的工作区内容与 round 5 审过的暂存内容逐字节一致。重点锚点与 round 5 记录逐项对照一致：`src/backend/cbrowser/supervisor/storage_migration.py` 仍 728 行，`run()` 位于 399 行、plan_digest 前置校验在其后（405 行起）、`_check_source_ownership` 位于 475 行且双向覆盖比对在位；`compose.yaml:55` 仍为 api 服务的 `- runtime:/data/runtime`；`src/backend/cbrowser/services/profile_service.py` 删除时清理 `runtime/.secrets/<profile_id>` 的代码在位；`scripts/deploy.sh` 仍 1261 行、`src/backend/cbrowser/supervisor/docker_adapter.py` 仍 2737 行。审阅者复跑 t080 五个测试文件共 55 条全过，与 round 5 的复跑数（55）一致。本轮按任务约束未做变异验证（不得与测试审阅并发）、未跑全量门禁。
- md 格式化语义核查（本轮核心项 ②）：`task.md` 的未暂存 diff 仅 3 处——AC-002、AC-008、AC-009 下处置注记子项的缩进由 2 空格改为 4 空格；审阅者以去除全部空白后逐字比对暂存版与工作区版，结果完全一致，即 AC-001–AC-009 的文本、`[x]` 打勾状态、三条处置注记的含义（真实 Engine/部署链路按用户 2026-11-18 裁定延期本地统一补验、由 p127/p129 跟踪、不表示已实测通过、AC 验证内容原文不改）均未改变。`review_code.md` 与 `review_test.md` 的未暂存 diff 仅为下划线转义（`_switch`→`\_switch`、`_validate_font_set`→`\_validate_font_set`、`_start_browser`→`\_start_browser`，渲染语义不变）与嵌套列表缩进 2→4 空格，两份报告的历史 verdict、reviewed_scope 与 finding 文本未被改动。`progress.md` 除表格空格、列表项间空行与下划线转义等格式化外，front matter 的 `review_limit` 由 `"5"` 改为 `"7"` 且 `note` 追加了该上限调整与 md_format 漂移的说明——属流程元数据，与本轮派审背景（finish 时格式化使指纹变化、审阅上限已提高）一致；处置表中 f001–f011 与 test f001–f003 的 status 未变，实施自述正文语义未变。
- 本轮新发现：0 条
- 未进表的提示：文件过大（仅结论提示，不进 finding 表）——与 round 4/5 相同：`src/backend/cbrowser/supervisor/storage_migration.py` 728 行超实现源码 400 行 minor 阈值、未超 800 行；`docker_adapter.py` 2737 行、`scripts/deploy.sh` 1261 行仍超 800 行（存量）。真实 Engine/部署补验仍由 p127、p129 跟踪，本轮判定按 task.md 契约区处置注记据实处理，不表示已在真实 Engine/部署实测通过。
- 总体判断：自 round 5 PASS 以来生产代码与测试代码字节未变，4 个 Markdown 文件的变更为格式化（及 progress.md 的审阅上限流程元数据），未改变 task.md 的 AC 文本语义与处置注记含义，AC 打勾全部成立，本轮 PASS。
- 系统性 follow-up：无（真实部署补验已由 p127、p129 跟踪）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。生产挂载构造与 round 5 PASS 时逐字节一致（未暂存 diff 不含任何生产/测试文件，锚点对照见结论段），审阅者复跑 test_t080_adapter_mounts/test_t080_storage_layout/test_t080_deploy_wiring 通过；task.md 本条文本与处置注记经去空白逐字比对未变，真实 Engine 部分按处置注记延期 p127，不表示已实测。
- AC-002：TICK-VALID，re_verified。MountPlanner 与 Browser/Stream 挂载集合代码未变化、相关测试复跑通过，Stream 不获 Profile/Artifact/字体；task.md 本条文本与处置注记语义未变，真实 Engine 隔离实证按处置注记延期 p127。
- AC-003：TICK-VALID，re_verified。data/runtime 卷归属与 Supervisor 重启不清空 runtime 的路径未变化、相关测试复跑通过；task.md 本条文本未变，真实重启链路按处置注记延期 p129。
- AC-004：TICK-VALID，re_verified。迁移校验生产代码未变化（写者/容量/卷归属/源双向覆盖/恢复点/摘要锚点行号与 round 5 一致），test_t080_storage_migration 全套复跑通过；task.md 本条文本未变。
- AC-005：TICK-VALID，re_verified。迁移搬运、身份保持、冲突拒绝与 `done` 异 plan 拒绝代码未变化，相关用例复跑通过；task.md 本条文本未变，真实部署身份逐项比对按处置注记延期 p129。
- AC-006：TICK-VALID，re_verified。journal 分阶段推进、故障续跑与回退身份采纳代码未变化，相关用例复跑通过，源树全程不改写；task.md 本条文本未变。
- AC-007：TICK-VALID，re_verified。f001 修复点未变化（compose.yaml:55 的 api runtime 挂载与 profile_service 的 .secrets 清理在位），克隆/重置/删除等用例复跑通过；task.md 本条文本未变，真实部署链路按处置注记延期 p129。
- AC-008：TICK-VALID，re_verified。字体迁入与 subpath 只读挂载代码未变化，字体预检等用例复跑通过；task.md 本条文本与处置注记语义未变，真实挂载摘要按处置注记延期 p129。
- AC-009：TICK-VALID，trust_prior。云端可做部分（迁移工具、deploy harness 备份/回退演练）经审阅者复跑 test_t080_deploy_harness 通过；task.md 本条文本与处置注记经去空白逐字比对未变，真实 Chrome 全链路演练无法在云端独立复验，按处置注记依赖 p127 本地统一补验，不表示已实测通过。

coverage = 8 / 9

verdict: PASS

# Task review t066（reviewer_focus: 代码）

- task：`t066_profile_identity_state`
- spec：`docs/tasks/t066_profile_identity_state/task.md`
- diff_anchor：`680d850067075caf9356ee6c71771f6dc779c543`
- target：基线 HEAD 680d850 之上的全部未提交改动（`git diff` 14 文件 + 未跟踪新文件 `scripts/restore_point.py`、`tests/unit/test_t066_*.py` ×3、`docs/pending/todo/p093_t066_local_deploy_verification.md`，逐个直读审阅）
- round：1
- reviewed_at：2026-11-14（CST）

reviewed_scope: ddf4e39bbe9db6fc

## Findings

### t066_code_f001 - 恢复回滚不处理 DB 的 -wal/-shm sidecar，中断回滚后旧 DB 集不完整

- 严重度：important
- 锚点：AC-010「成套切换每个中断点都能恢复旧完整版本或完成新版本，不遗留 DB 与目录版本错配」
- 位置：`scripts/restore_point.py:442-488`（`_recover_interrupted` 全函数无任何 sidecar 处理）；对照切换侧 `scripts/restore_point.py:588-592`（switch 时对 `sidecars: True` 的 DB 项把 live 的 `-wal`/`-shm` 一并 rename 到 previous 旁）
- 问题：切换侧明确知道 DB 带 sidecar 并成套移动，但回滚侧完全不移动 sidecar。后果分两种中断点：①journal 已记 `switched` 后回滚：旧 DB 主文件被 `previous.replace(live)` 恢复，但旧 `-wal`/`-shm` 仍以 `.pre-restore-<id>-wal` 名字留在旁边，live DB 丢了 WAL 中已提交未 checkpoint 的事务——恢复出的不是「旧完整版本」；②切换第一步 rename 后、sidecar rename 后、staged rename 前中断（journal 仍 `pending`）：回滚分支（`:471-482`）同样只恢复主文件，`-wal` 已被移到 previous 旁、永不归位。本 reviewer 以伪造 journal + sidecar 实文件定向实测复现①：`_recover_interrupted` 返回 True、live 主文件内容恢复为旧值，但 `live-wal exists: False`、`prev-wal still orphaned: True`（证据脚本为一次性探针，已删，结论可按上述布置复跑）。现有测试 `test_interrupted_switch_rolls_back_then_rerun_completes` 只伪造 Profile 目录项中断，未覆盖 DB 项与 sidecar——该中断类无测试守护。
- 建议：回滚逻辑对 `sidecars: True` 的项与切换侧对称处理：`switched` 回滚时把 previous 的 `-wal`/`-shm` 一并 rename 回 live 旁，`pending` 回滚分支同理；补 DB 项带 WAL 的中断回滚用例（含 sidecar 已移/未移两个中断点）。

### t066_code_f002 - create 只在开始时查一次写者，目录复制期间新启动的写者可撕裂「同一恢复点」

- 严重度：important
- 锚点：AC-009 及 task 范围「停机并验证无实际写者后取得同一恢复点」；AC-005 的互斥口径
- 位置：`scripts/restore_point.py:254`（`read_writer_offenders` 唯一调用点，在 DB 快照之前）；`scripts/restore_point.py:284-307`（随后逐 Profile 复制目录，全程不再复查）
- 问题：`deploy.sh env-backup` 不停栈（只要求各 Profile 已停止），备份期间经 API 启动某个 Profile 完全可能：DB 快照已在 `:269` 按「stopped」取走，之后该 Profile 的目录在浏览器进程并发写下被逐文件复制，得到的恢复点里 DB 记录与目录内容不属于同一静默时刻，且目录本身可能撕裂（逐文件 sha 只保证与复制瞬间一致，不保证跨文件一致）。同 task 的 duplicate/reset 都采用「操作后二次复查」模式（`profile_service.py:758`、`:845` 在复制/建目录后重查 `_require_fully_stopped`），唯独 create 没有收尾复查，与本 task 自己确立的防线不一致。
- 建议：全部目录复制完成后、写 manifest/发布 staging 之前再查一次 `read_writer_offenders`（并复核各 Profile 的 config_version 未变），出现写者即弃点报错（staging 已有 `except BaseException` 清理，弃点成本为零）。

### t066_code_f003 - 文档宣称 duplicate/reset/delete/备份「共用同一写者判定」，实现实为两个谓词（error 态口径不同）

- 严重度：minor
- 锚点：AC-005 的文档一致性（行为本身无缺陷，duplicate/reset 更严不构成风险）
- 位置：`docs/blueprint/domain.md:76`、`docs/blueprint/security.md:113`、`docs/specs/profile_management.md:119`（均称共用同一判定，列举条件为 desired=running / observed 迁移态 / 实例绑定）；实现 `src/backend/cbrowser/services/profile_service.py:155-167`（`_runtime_has_writer`：observed=error 且 desired=stopped、无实例绑定时返回 False，delete 放行）与 `:170-181`（`_require_fully_stopped`：observed != stopped 即拒绝，error 态 duplicate/reset 拒绝）；`scripts/restore_point.py:59,132-152` 的备份门禁与前者一致、与后者不一致
- 问题：三处文档把口径写成单一判定，与实现的两谓词事实不符；后续维护者按文档把任一侧「对齐」到另一侧都会改变行为（尤其把 delete 改严会让 error 态 Profile 删不掉，把 reset 改松会放宽状态改写门禁）。
- 建议：文档改述为两个谓词及其分工：`_runtime_has_writer`（delete/备份：有实际写者才拒绝，error 态可处置）与 `_require_fully_stopped`（duplicate/reset：必须完全 stopped），或有意统一实现并补 error 态用例后保留现表述。

### t066_code_f004 - staging 阶段中断遗留的 `.restore-staging-*` 残留无任何回收路径

- 严重度：minor
- 锚点：AC-010 的整洁性（不影响版本正确性：活集从未被触碰，无错配）
- 位置：`scripts/restore_point.py:511-512`（DB staging 文件名带每轮唯一 switch_id）、`:545`（Profile staging 目录存在性清理只针对本轮同名目录，而 switch_id 每轮新生成、恒不命中）；journal 在 staging 全部完成之后才写（`:578`），故 staging 期崩溃不触发 `_recover_interrupted`，残留永久留在目标旁
- 问题：恢复在校验/复制阶段被杀（或磁盘满，见空间检查后复制仍可能因他方占用失败）会留下整份 Profile 数据量级的孤儿目录/文件，后续每次 restore 用新 switch_id、永不清理旧残留，运维也无文档提示。回滚路径同理把新集停在 staged 路径后不清理（`_recover_interrupted` 的 switched 分支把 live 移回 staged 即结束）。
- 建议：restore 开始（journal 回滚检查之后、staging 之前）顺带清除目标旁早于本轮的 `.restore-staging-*` 残留，或在回滚/完成路径上清理 staged 残留；并在 DOCKER_DEPLOYMENT.md 注明残留的手工清理方式（与 `.pre-restore-*` 的保留说明并列）。

### t066_code_f005 - 切换 rename 未对目标父目录 fsync，「任一中断点收敛」只覆盖进程崩溃、不覆盖掉电

- 严重度：minor
- 锚点：AC-010 原子性论证的边界（进程级中断已由 journal 正确处理，此项仅为耐久性口径）
- 位置：`scripts/restore_point.py:585-596`（switch 循环内的 `live.replace(previous)` / `staged.replace(live)` 后无 `_fsync_dir`）；对照 `scripts/restore_point.py:87-97`（`_atomic_write_json` 写后 fsync 文件与父目录）、`:324-326`（create 发布时 fsync staging 与父目录）
- 问题：journal 本身落盘可靠，但 DB 文件与各 Profile 目录所在父目录在 rename 后从未 fsync，掉电时 rename 结果可能丢失或乱序，journal 记录的进度与磁盘事实可不一致（例如 journal 记 switched 而 live 的 rename 未落盘）。blueprint `architecture.md` 的 t066 节表述为「保证任一中断点收敛为完整旧集或完整新集」，未区分进程崩溃与掉电。
- 建议：switch 每项 rename 后对 live/previous/staged 的共同父目录各 fsync 一次（成本可忽略），或在 blueprint/docstring 中把保证范围明确限定为进程中断、掉电不在保证内。

### t066_code_f006 - restore 默认 journal 落在 data_root 的父目录，直调 CLI 且跨容器/跨挂载时回滚凭据丢失

- 严重度：minor
- 锚点：AC-010 的可达性（经 `deploy.sh env-restore` 的正式路径不受影响）
- 位置：`scripts/restore_point.py:427-428`（`_default_journal = data_root.parent / (name + ".restore-journal.json")`）；docstring 用法示例（`:15-17`）未带 `--journal`
- 问题：data_root 为 `/data`（deploy 容器内挂载点）时默认 journal 是 `/data.restore-journal.json`，位于一次性容器根文件系统，容器 `--rm` 后即消失；按 docstring 直调 CLI 的运维者中断后重跑将找不到 journal、无法触发回滚（live 处于半切换状态而工具无感知）。`deploy.sh env-restore` 显式传 `--journal /data/restore-journal.json`（`scripts/deploy.sh` cmd_env_restore），正式路径正确，故仅 minor。
- 建议：默认 journal 改放 data_root 之内（如 `data_root / ".restore-journal.json"`，与 deploy.sh 口径一致），或在 docstring 示例中显式带 `--journal` 并注明必须落在持久路径。

## 结论

- 本轮新发现：6 条（0 critical、2 important、4 minor）
- 未进表的提示：`scripts/restore_point.py` 660 行在脚本类文件可接受范围；`profile_service.py` 本 task 净增约 30 行，新增两谓词均为平直逻辑，无高圈复杂度函数。reset 在 DB 更新已成功、仅备份目录 `rmtree` 失败时抛错且新状态已生效（`profile_service.py:865-879`）——该块为基线既存行为、非本 task 改动，且错误如实上报不吞错，不立 finding。`DOCKER_DEPLOYMENT.md` 的 verify 示例用 `<api-image>`/`<point-dir>` 占位符，与该指南既有占位风格一致，不立 finding。
- 复验摘要（实现层，本 reviewer 独立执行）：落点校验在 worktree 内 `pwd` 与 `git rev-parse --show-toplevel` 均为 `<home>/workspace/CBrowser_t066`、基线 `680d850`、分支 `t066_profile_identity_state`。seed 单一性全仓核对：后端仅 `domain/models.py:24-37` 一处声明空间与推导（`generate_fingerprint_seed` 随机路径 + `derive_fingerprint_seed` 确定性路径同空间），五位公式 `10000 + hash % 90000` 已删净、全仓无 `90000` 生成残留（frontend 命中均为 node_modules/构建产物噪声）；router 创建路径 `ProfileConfig().fingerprint_seed` 走同一 default_factory。写入互斥：duplicate/reset 在操作前与复制/建目录后双查 `_require_fully_stopped`，delete 走 `_runtime_has_writer`，三者与 set_desired_state/bind_runtime_instance 共用同一 per-profile 锁，交错由锁 + 二次复查双层防线覆盖。clone 全程不删 Local State（服务层与 restore_point 均无 Local State 特殊处理，grep 实测），失败/取消经 `except BaseException` 清理克隆目录。restore_point 主协议逐段读毕：create 的在线 backup + integrity_check + schema stamp + 逐文件 sha256 manifest + 凭据只记名、staging 目录发布后 rename；restore 的 validate 全量校验（哈希/完整性/stamp 与活库比对/空间）在任何活字节移动之前完成，journal 逐项记进度、`.pre-restore-<switch-id>` 保留旧集、退出码 3 的回滚-重跑协议成立（f001 的 sidecar 缺口除外）。deploy.sh 两子命令与 restore_point CLI 参数逐项对齐（create 的 --db/--data-root/--out/--secrets-dir/--label、restore 的 --point/--db/--data-root/--journal /data/restore-journal.json、named volume 与 /data 挂载、env-restore 先 compose down），DOCKER_DEPLOYMENT/README/blueprint/specs 所述命令名、子命令与路径与实现一致（f003 的判定表述除外）。
- 总体判断：seed 统一（AC-008）与服务层写者守卫（AC-001/003/004/005 云端部分）实现干净、根因性成立，无临时补丁、无第二处 seed 生成；但恢复点协议有两处 important 缺口——回滚漏 sidecar 使 AC-010「每个中断点恢复旧完整版本」存在实测反例，create 无收尾写者复查使 AC-009「同一恢复点」在备份窗口内不设防。两条 AC 打勾据此判 TICK-VOID，本轮 verdict FAIL；其余六条打勾成立（[deploy] 切片均以 p093 为顺延凭据，该 pending 实存且 6 项一一覆盖 AC-001/003/004/005/011 的本地补验与 findings 补录）。
- 系统性 follow-up：无（[deploy] 顺延已登记 `docs/pending/todo/p093_t066_local_deploy_verification.md`；f001/f002 为本 task 内修复项，不另立 pending）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。[deploy] 云端部分成立：`update_profile` 只写配置与版本、全程不触碰 user_data_dir（直读实现），守卫测试断言配置保存后 `_manifest` 与 seed 不变且复跑通过；真实引擎身份参数一致性切片顺延 p093 第 1 项。
- AC-003：TICK-VALID，re_verified。[deploy] 云端部分成立：task.md 未知契约清单的 spike 结论要素齐全（引擎 CloakBrowser Chromium 146.0.7680.177.5、Local State 无 `os_crypt.encrypted_key`、逐字复制后 Cookie/localStorage 可读、删 Local State 后仍可读），「无可复制密钥根 ⇒ 独立根条件不成立」的推论与 AC 文本的条件句吻合；实现侧 include-state clone 逐字复制 + manifest 全等校验 + 双查停机 + 失败清理、不删 Local State（grep 实测）；真实引擎两态往返顺延 p093 第 2 项。
- AC-004：TICK-VALID，re_verified。[deploy] 云端部分成立：reset 以整目录 rename 让位 + 新建空目录实现全清、仅 patch `fingerprint_seed`（配置与独立 Artifact 不在目录内、不受影响）、失败路径 `_cleanup_copy` 新目录后 `os.replace` 恢复旧目录且 DB 更新在目录恢复之后才可能已提交的顺序经直读核对、既有 copy/reset 套件复跑通过；真实 Profile 全清与故障注入顺延 p093 第 3 项。
- AC-005：TICK-VALID，re_verified。[deploy] 云端部分成立：残留 `runtime_instance_id` 拒绝 duplicate/reset 有专门用例（ghost 绑定下两操作均抛 `ProfileRunningError` 且目录/seed/无残留经断言）并复跑通过，delete 经 `_runtime_has_writer` 同查绑定，备份 create 经 `read_writer_offenders` 同口径拒绝；本 task 未新增任何 viewer/连接数触发停止或清理的路径（diff 全量直读）；真实拓扑交错顺延 p093 第 4 项。
- AC-008：TICK-VALID，re_verified。单一声明空间 100000..999999、确定性推导同操作同 seed、五位路径删净、全仓无第二处 seed 生成（grep 全量核对），守卫测试（200 次随机/推导范围与确定性、reset 带 operation_id 五轮范围）复跑通过；已保存 seed 不被改写（推导只用于新操作，`update` 路径不碰 seed）。
- AC-009：TICK-VOID，re_verified（部分）。成套内容与往返一致性本身成立（真实迁移 DB 往返用例复跑通过：config_version/seed/Cookie 字节回到恢复点、named volume DB 在点内、凭据只记名且内容不入点的断言齐全）；但 f002 的窗口使「同一静默时刻的成套」在备份期间被启动写者时不成立，打勾按整体口径作废，待补收尾复查后重派复审。
- AC-010：TICK-VOID，re_verified（部分）。损坏 payload/损坏 DB/sha 与 size 不符/schema 跨代/空间不足均在触碰活数据前拒绝且有用例复跑通过，Profile 项中断回滚-重跑协议成立；但 f001 以实测证明 DB 项带 WAL 时回滚后旧集不完整，「每个中断点」口径存在反例，打勾作废。
- AC-011：TICK-VALID，re_verified。[deploy] 云端部分成立：指南（DOCKER_DEPLOYMENT §8、README）所列 `env-backup [point-dir]`/`env-restore <point-dir>` 与实现子命令名、参数、默认路径（`data/backups/restore-points/point-<时间>`）、named volume 取 DB 的挂载方式逐项一致，接线测试复跑通过；隔离真实部署往返顺延 p093 第 5 项。

coverage = 8 / 8

verdict: FAIL

______________________________________________________________________

## Round 2 (2026-11-14)

- task：`t066_profile_identity_state`
- spec：`docs/tasks/t066_profile_identity_state/task.md`
- diff_anchor：`680d850067075caf9356ee6c71771f6dc779c543`
- target：基线 HEAD 680d850 之上的全部已暂存改动（`git diff --cached 680d850`，22 文件，含新文件）
- round：2
- reviewed_at：2026-11-14（CST）

reviewed_scope: git diff --cached sha256 `9a2eb1088d72b87b`；git status --porcelain sha256 `6ca0ce32d7a0c6b5`

落点校验（本 reviewer 每条命令前均执行）：worktree 内 `git rev-parse --show-toplevel` = `<home>/workspace/CBrowser_t066`、`git log --oneline -1` = `680d850`、分支 `t066_profile_identity_state`、交付全部已暂存（`git status --short` 22 项均为暂存态，无未跟踪漏项，Round 1 test 轴 f010 的口径问题在 code 轴范围内亦已消除）。

### Finding 逐条复核

|finding_id|Round 1 严重度|复核结论|证据|
|---|---|---|---|
|t066_code_f001|important|FIXED|`scripts/restore_point.py` 新增 `_move_sidecars(source, target)`（对 `-wal`/`-shm` 逐个 `exists()` 后 replace 到目标旁）；`_recover_interrupted` 的 `switched` 分支两步均对称调用（live→staged 后 `_move_sidecars(live, staged)`、previous→live 后 `_move_sidecars(previous, live)`），`pending` 视同 switched 分支（live 在而 staged 不在）与 pending 真回滚分支（live 不在）同样两处调用——与切换侧成套移动对称，Round 1 指出的两个中断点（一：switched 后旧 sidecar 留在 `.pre-restore-*-wal` 旁；二：第一步 rename 后 sidecar 已移、journal 仍 pending）均被覆盖。新用例 `test_interrupted_mixed_switch_rolls_back_db_and_profile` 构造 DB 项 switched（含旧 `-wal`/`-shm` 实文件断言：回滚后 live 旁字节分别为 `old-wal`/`old-shm`、seed 回旧值 999999）+ Profile 项 pending 的双项伪造态，断言整套回旧、重跑后整套回恢复点（seed 123456、Cookie `cookie-v1`），本 reviewer 实跑通过。另有执行期真实崩溃注入用例 `test_restore_crash_after_db_switch_rolls_back_on_next_run`（journal 落后于文件系统时 pending 视同 switched 的回滚）同轮通过，pending 分支的 sidecar 路径有真实形态守护。|
|t066_code_f002|important|FIXED|`create_point` 在全部 Profile 目录复制完成后、manifest 写入与 staging 发布之前新增收尾复查：重查 `read_writer_offenders(db_path)`，非空以 `WriterActiveError` 弃点（退出码 2，staging 由既有 `except BaseException` 清理）；并逐 Profile 以 `{id: config_version}` 字典全等比对起点 `read_profiles` 快照与活库重读结果（含新增/删除 Profile 的键集变化），不一致同样弃点。与 duplicate/reset 的「操作后二次复查」模式一致，Round 1 的备份窗口撕裂面已封。新用例 `test_create_aborts_when_writer_appears_during_copy` 以 monkeypatch `_copy_tree_manifest` 在首次复制中途注入两场景（绑定 runtime 实例、bump config_version 至 99），两场景均断言退出码 2 且恢复点未发布，本 reviewer 实跑通过。|
|t066_code_f003|minor|FIXED|三处文档逐处核对均已改述为两档判定且与实现一致：`docs/blueprint/domain.md` t066 节明述 `_runtime_has_writer`（delete 与备份取点共用；desired=running / observed 迁移态 / 实例绑定任一成立即拒绝；observed=error 且 desired=stopped、无绑定不算写者）与 `_require_fully_stopped`（duplicate 带状态与 reset 共用；desired/observed 均须 stopped 且无绑定，error 态拒绝）；`docs/blueprint/security.md` 恢复点节表述为「备份门禁与 delete 共用实际写者判定」并指向 domain 两档节、且补述 create 收尾复查；`docs/specs/profile_management.md` t066 节以两档分工表述（duplicate/reset 完全停止、delete 实际写者）。与实现直读对照：`profile_service.py` 中 delete 走 `_runtime_has_writer`、duplicate/reset 走 `_require_fully_stopped`，`restore_point.py` 的 `read_writer_offenders` 判据与前者逐项相同——文档不再宣称单一判定。|
|t066_code_f004|minor|FIXED|`restore_point` 在 `_recover_interrupted` 检查之后、`validate_point` 与 schema stamp 比对之后、staging 之前新增清扫：DB 侧 glob `db_path.name + ".restore-staging-*"`（文件 unlink、目录 rmtree），各 Profile 侧在其 live 目录的父目录 glob `.restore-staging-*` 并 rmtree 目录；清扫模式只匹配 `.restore-staging-*`，不触碰 `.pre-restore-*` 保留集。时序正确：带 journal 的中断先走回滚并以退出码 3 停止，不会误扫尚被 journal 引用的 staged 路径；无 journal 的 staging 残留（switch_id 已随进程丢失、不可恢复）才被清。`DOCKER_DEPLOYMENT.md` §8 已注明下次恢复自动清扫、亦可手工删除、且不属于任何完整集，与 `.pre-restore-*` 的保留说明并列。新用例 `test_restore_sweeps_stale_staging_leftovers` 伪造 DB 侧残留文件与 Profile 侧残留目录，断言恢复后两者均消失、活集正确恢复、`.pre-restore-*` 保留集仍在，本 reviewer 实跑通过。|
|t066_code_f005|minor|FIXED|切换循环：每项以 `moved` 标记本项是否真发生 rename（live→previous 或 staged→live 任一发生即置真，含 sidecar 移动），`moved` 为真时在 item 记 `switched` 并写 journal **之前**执行 `_fsync_dir(live.parent)`——DB 与 Profile 的 live/previous/staged 三路径同父目录，一次 fsync 覆盖本项全部 rename（含 sidecar），顺序满足「rename 落盘先于 journal 记录」。无 live 且恢复点无目录的 Profile 项不发生 rename、不做无谓 fsync，与修复口径「仅本项真发生 rename 时」一致。回滚路径 `_recover_interrupted` 每项处理末尾对 `live.parent` 执行 `_fsync_dir`（父目录存在时），回滚 rename 同样在 journal 归档写之前落盘。架构文档「任一中断点收敛」表述自此有掉电耐久性支撑（journal 自身经 `_atomic_write_json` 的文件+父目录 fsync、create 发布经 staging 与父目录 fsync，既有部分不变）。|
|t066_code_f006|minor|FIXED|`_default_journal` 改为 `data_root / ".restore-journal.json"`，落在与受保护集同一持久卷内；函数注释已说明理由（容器挂载点父目录是一次性文件系统、journal 丢失会使半切换集无回滚触发），模块 docstring 同步注明默认落点为 `<data-root>/.restore-journal.json` 且 `--journal` 须同为持久路径。`deploy.sh env-restore` 的显式 `--journal /data/restore-journal.json` 同在 data root 内，两条入口各自路径内自洽；显式 journal 布局另有功能用例 `test_restore_with_explicit_journal_inside_data_root` 守护（test 轴 f003 的修复，本轮实跑通过）。Round 1 的「直调 CLI 默认落点在一次性根文件系统」问题消除。|

- 本轮新发现：0 条（无新 finding，编号不续排）。
- 未进表的提示：`_default_journal` 注释称 deploy.sh 传「same location」，实为同一目录/持久卷、文件名不同（默认 `.restore-journal.json` vs deploy 显式 `restore-journal.json`）；两条入口各自始终使用自己的 journal 路径、中断重跑均经同一入口续行，不构成回滚凭据丢失，不立 finding，仅记措辞层面的不精确。

### 实跑数字（本 reviewer 独立执行）

环境：worktree 内 `~/workspace/CBrowser/.scratch/gate_venv/bin/python -m pytest <file> -q`。

|文件|结果|
|---|---|
|`tests/unit/test_t066_restore_point.py`|18 passed，0 failed（14.01s）——含 Round 2 新增/相关用例：混合中断双项回滚、create 复制中途写者/版本漂移弃点、staging 残留清扫、执行期崩溃注入回滚、显式 journal、过渡态拒绝、双卷空间分别注入|
|`tests/unit/test_t066_profile_state_guards.py` + `tests/unit/test_t066_deploy_restore_point_wiring.py`（抽跑）|8 passed，0 failed（9.99s；guards 5 + wiring 3）|

未跑全量门禁（按派发要求，主会话并行在跑第三轮）。

### 结论

- Round 1 的 6 条 finding（2 important + 4 minor）逐条复核全部 FIXED，证据均为直读实现 + 本 reviewer 实跑新用例，无一靠实施侧自报；无新引入问题。
- AC-009 / AC-010 在 Round 1 被 f002 / f001 击穿的两处缺口（备份窗口同一静默时刻、DB 带 WAL 中断回滚旧集完整性）已分别由收尾复查与 sidecar 对称回滚封堵且有用例守护，两条 AC 恢复 TICK-VALID；其余 6 条 AC 的实现与证据自 Round 1 未发生回归（本轮抽跑 guards/wiring 全绿佐证），维持 TICK-VALID。
- 总体判断：恢复点协议的成套性论证现已闭环——create 同一静默时刻有首尾双查、restore 全量校验前置、journal 逐项进度 + sidecar 成套 + rename 后 fsync 父目录再记 journal、中断回滚旧集完整、staging 残留有回收、默认 journal 在持久卷内。code 轴 Round 2 verdict PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。[deploy] 云端部分与 Round 1 结论一致（配置保存不触 user_data_dir、守卫用例断言 manifest 与 seed 不变），本轮抽跑 guards 5 passed 无回归；真实引擎身份参数一致性切片顺延 p093 第 1 项（pending 实存）。
- AC-003：TICK-VALID，re_verified。[deploy] 云端部分与 Round 1 一致（逐字复制、不删 Local State、双查停机、失败清理）；真实引擎两态往返顺延 p093 第 2 项。
- AC-004：TICK-VALID，re_verified。[deploy] 云端部分与 Round 1 一致（reset 整目录全清、仅 patch seed、失败成套恢复）；真实 Profile 全清与故障注入顺延 p093 第 3 项。
- AC-005：TICK-VALID，re_verified。[deploy] 云端部分成立且本轮有增益：f002 修复使备份侧在取点窗口内同样拒绝新出现写者，f003 修复使两档判定文档与实现一致；残留实例绑定拒绝 duplicate/reset/delete/备份的口径不变。真实拓扑交错顺延 p093 第 4 项。
- AC-008：TICK-VALID，re_verified。seed 单一声明空间与确定性推导自 Round 1 未改动，guards 抽跑通过，无回归。
- AC-009：TICK-VALID，re_verified。f002 已修：create 目录复制后重查实际写者并逐 Profile 比对 config_version 与起点快照，不一致弃点且不发布，「同一恢复点/同一静默时刻」在备份窗口内成立；成套内容与往返一致性（config_version/Cookie/Preferences 回到恢复点、named volume DB 在点内、凭据只记名）由往返与 manifest 契约用例实跑通过。（Round 1 曾判 TICK-VOID，本轮恢复。）
- AC-010：TICK-VALID，re_verified。f001 已修：`_move_sidecars` 使 switched 与 pending 两类中断点的回滚均恢复 DB 主文件 + `-wal`/`-shm` 旧集，混合中断双项用例与执行期崩溃注入用例实跑通过；f004/f005/f006 的整洁性、掉电耐久性与 journal 可达性缺口一并消除。损坏/校验失败/跨代 stamp/空间不足在触碰活数据前拒绝的 Round 1 结论不变。（Round 1 曾判 TICK-VOID，本轮恢复。）
- AC-011：TICK-VALID，re_verified。[deploy] 云端部分与 Round 1 一致（指南命令与实现子命令、参数、默认路径、named volume 挂载逐项一致），wiring 3 passed 抽跑通过；隔离真实部署往返顺延 p093 第 5 项。

coverage = 8 / 8

verdict: PASS

## Round 3 (2026-11-14)

- round：3（确认轮：Round 2 后登记增量与最终指纹确认）
- reviewed_at：2026-11-14（CST）

reviewed_scope: 2d41c54dcc846658

增量逐项核对（本 reviewer 直读文件与 `git diff --cached 680d850`，交付仍为 22 文件全部暂存、分支 `t066_profile_identity_state`、基线 HEAD `680d850`，未见清单外变化）：

- 增量 1（guards 补断言）：`tests/unit/test_t066_profile_state_guards.py` 的 `test_config_save_preserves_browser_state_directory` 已补 5 行生效断言，逐项为 `screen_width == 1280`、`screen_height == 900`、`locale == "en-US"`、`timezone == "America/New_York"`、`humanize is False`，与登记一致，t066_test_f011 的字段级缺口已闭合。
- 增量 2（journal 注释）：直读 `scripts/restore_point.py` 的 `_default_journal`，注释已改述为 deploy.sh 同样传入 data root 内的显式 journal 路径 `/data/restore-journal.json`，函数返回值仍为 `data_root / ".restore-journal.json"`，仅注释措辞修正、无逻辑变化。
- 增量 3（md_kx 规范化）：抽查两文件 diff，`docs/blueprint/security.md` 既有列表项之间补入空行、文字内容未改，其 t066 节与 Round 2 核对内容一致；`docs/specs/profile_management.md` 既有正文未改，其 t066 节内容与 Round 2 核对一致，均为格式规范化、无内容变化。
- 增量 4（过程文件重排）：`review_code.md` 与 `review_test.md` 均已以 `## Round 2` 分节，test 轴文件含判定表与行式「AC 复验方式」小节，`progress.md` 已登记 t066_test_f011 行与 Round 2 双轴 PASS 段；内容与判定与本文件 Round 2 节自洽，未变。
- 抽跑实数（本 reviewer 独立执行，`TMPDIR=.scratch/tmp`）：三文件合并实跑 26 passed、0 failed（87.21s），收集计数逐文件为 `test_t066_restore_point.py` 18、`test_t066_profile_state_guards.py` 5、`test_t066_deploy_restore_point_wiring.py` 3，与期望 18/5/3 逐项吻合。
- 指纹核对（本 reviewer 亲自执行指定命令）：输出 `2d41c54dcc846658`，与期望值一致，故落章。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本轮抽跑 guards 五项全过且保存用例新增的五项字段生效断言已直读在位。
- AC-003：TICK-VALID，re_verified。本轮核对最终指纹一致且交付文件清单未变，逐字复制与不删 Local State 的云端结论无回归。
- AC-004：TICK-VALID，re_verified。本轮核对最终指纹一致且 guards 与 restore_point 抽跑全绿，reset 全清与成套恢复的云端结论无回归。
- AC-005：TICK-VALID，re_verified。本轮抽跑 guards 与 restore_point 全绿，残留实例拒绝与 create 收尾复查用例均通过。
- AC-008：TICK-VALID，re_verified。本轮抽跑 guards 中 seed 单一空间与确定性推导用例全过。
- AC-009：TICK-VALID，re_verified。本轮抽跑 restore_point 十八项全过，往返一致性与 create 收尾复查用例均通过。
- AC-010：TICK-VALID，re_verified。本轮抽跑 restore_point 十八项全过，混合中断回滚与执行期崩溃注入用例均通过。
- AC-011：TICK-VALID，re_verified。本轮抽跑 wiring 三项全过，指南命令与 deploy 接线的云端结论无回归。

coverage = 8 / 8

verdict: PASS

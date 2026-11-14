# Task review t066（reviewer_focus: 测试）

- task：`t066_profile_identity_state`
- spec：`docs/tasks/t066_profile_identity_state/task.md`
- diff_anchor：`680d850067075caf9356ee6c71771f6dc779c543`
- target：基线 HEAD 680d850 之上的全部未提交改动（14 改 + 5 新增，含未跟踪新文件直读）
- round：1
- reviewed_at：2026-11-14T00:09:00+08:00

reviewed_scope: git diff sha256 `6c7800846279d8`；git status --porcelain sha256 `3976161907f2ac`

## 复跑实数（本 reviewer 独立执行，非引用实施侧自报）

环境：worktree 内以 `~/workspace/CBrowser/.scratch/gate_venv/bin/python -m pytest <file> -q`（Python 3.15.2，`TMPDIR=.scratch/tmp`）逐文件实跑。

|文件|结果|
|---|---|
|`tests/unit/test_t066_profile_state_guards.py`|5 passed，0 failed（30.31s）|
|`tests/unit/test_t066_restore_point.py`|10 passed，0 failed（71.55s）|
|`tests/unit/test_t066_deploy_restore_point_wiring.py`|3 passed，0 failed（0.79s）|
|`tests/unit/test_profile_copy_reset.py`|23 passed，0 failed（151.68s）|
|`tests/unit/test_t051_deploy_scripts.py`|11 passed，0 failed（9.46s）|
|合计|52 passed，0 failed|

另亲验：`bash -n scripts/deploy.sh` 通过；`git diff --name-only` 中无任何既有测试文件（唯一名字含 test 的是 `docs/blueprint/testing.md` 文档），三个 t066 测试文件与 `scripts/restore_point.py`、p093 均为新增未跟踪文件——不存在「就地把旧测试预期改成当前实现输出」的改测。progress 实施笔记的数字核对：guards 5、restore 10、wiring 3 + t051 11 = 14 与本轮实跑逐项吻合；笔记称 guards「连同既有 copy/reset 套件 34 passed」，本轮两文件实跑为 5 + 23 = 28，该 34 应含笔记语境中的其他套件，本轮定向范围无法复现此合计（仅数字口径差异，不影响用例级结论）。

## Findings

### t066_test_f001 - AC-010 跨介质切换中断只有单项（仅 Profile）伪造态用例，DB 项回滚与 DB/目录混合中断态无任何覆盖

- 严重度：important
- 锚点：AC-010「成套切换每个中断点都能恢复旧完整版本或完成新版本，不遗留 DB 与目录版本错配」；task.md 测试策略「跨 DB/目录阶段故障注入，不仅测 rename」
- 位置：`tests/unit/test_t066_restore_point.py:261-313`（`test_interrupted_switch_rolls_back_then_rerun_completes`）；对照 `scripts/restore_point.py:458-495`（`_recover_interrupted`）、`scripts/restore_point.py:565-590`（切换循环，DB 项带 sidecars 先行切换）
- 问题：唯一的中断用例是手工拼装的事后状态（把 live 目录改名到 `.pre-restore-*`、预置 staging 副本、手写 journal），且 journal 的 `items` 里只有 1 个 profile 项、状态为 `pending`。它真实验证了「pending 项回滚 + 重跑完成」这一条路径（断言回滚后 Cookie 与 seed 均为变异值、重跑后均为恢复点值，具体值比对成立），但 AC-010 的核心风险——DB 项与 Profile 项分属两种介质、切换逐项进行——没有任何用例触达：① journal 中 DB 项处于 `switched` 态时的回滚分支（含 `-wal`/`-shm` sidecar 处理）从未被执行；② 「DB 已切换、Profile 未切换」（或反之）的混合中断态，即 AC 所称「DB 与目录版本错配」的确切场景，无用例构造，本用例中 DB 根本不在 journal 内、回滚前后 seed 都是 999999，等于假设了 DB 从未切换；③ 全部中断证据均为伪造态，没有一例在 restore 执行过程中真实注入故障（如让第二次 `replace` 抛错）验证 journal 落盘形态与伪造态一致，与测试策略「故障注入，不仅测 rename」的自述不符。用同一伪造手法补一个含 DB 项（switched）+ profile 项（pending）的双项 journal 完全是云端可测的，不属 [deploy] 顺延范围。
- 建议：补双项混合中断用例（DB 项 `switched`、profile 项 `pending`，断言回滚后 DB seed 与 Profile Cookie 同时回到旧集、重跑后同时回到恢复点）；再补一例执行期注入（monkeypatch `Path.replace` 或 `_atomic_write_json` 在第 N 次调用抛错），断言真实产生的 journal 可被下一次调用回滚。

### t066_test_f002 - AC-010「版本」校验只测了 schema stamp，恢复点 format 版本与 DB integrity_check 失败分支无独立用例

- 严重度：minor
- 锚点：AC-010「数据库校验失败」
- 位置：`tests/unit/test_t066_restore_point.py:200-227`（损坏 DB 与 stamp 不符两例）；`scripts/restore_point.py:382-390`（`load_manifest` 的 format/kind 校验）、`scripts/restore_point.py:405-411`（sha256 先于 integrity_check）
- 问题：`test_restore_refuses_corrupt_point_database` 在偏移 100 处写入 `GARBAGE`，恢复时先命中的是 sha256 不符，`PRAGMA integrity_check` 失败这条判定分支实际未被单独触达（sha 相符而 integrity 失败在现协议下近乎不可达，属纵深防御，可接受但应明示）；manifest 的 `format != 1` / `kind` 不符拒绝路径（`load_manifest`）无任何用例，改坏 manifest 的 format 字段时恢复是否拒绝未验。stamp 不符用例本身真实（改 live 库 `alembic_version` 后断言拒绝码 1）。
- 建议：补 manifest format/kind 篡改拒绝用例；integrity 分支可在测试 docstring 中注明由 sha256 校验遮蔽、属纵深防御。

### t066_test_f003 - 中断回滚只走工具默认 journal 路径，deploy 实际使用的显式 `--journal` 路径从未被功能测试执行

- 严重度：minor
- 锚点：AC-010、AC-011 的 journal 落点一致性
- 位置：`tests/unit/test_t066_restore_point.py:117-130`（`_restore` 不传 `--journal`，走 `_default_journal`）；`scripts/deploy.sh` 的 `cmd_env_restore` 传 `--journal /data/restore-journal.json`；`tests/unit/test_t066_deploy_restore_point_wiring.py:36-38` 仅源码字符串断言该参数存在
- 问题：功能测试覆盖的 journal 路径是工具默认值（data_root 同级 `<name>.restore-journal.json`），而真实部署经 deploy.sh 时 journal 在 `/data/restore-journal.json`（data_root 之内），两者不是同一文件。显式 `--journal` 分支（`restore_point.py:505-507`）在任何功能用例中都没被执行过；若该参数解析或路径处理有误，现有测试全绿也发现不了。
- 建议：中断或往返用例中至少一例显式传 `--journal` 指向与 deploy 相同的相对布局（如 data_root 内），断言回滚/完成行为一致。

### t066_test_f004 - deploy 接线测试的 env-backup 断言未按函数分段，全文件子串匹配有假阳性空间

- 严重度：minor
- 锚点：AC-011 云端部分的接线证据可信度
- 位置：`tests/unit/test_t066_deploy_restore_point_wiring.py:24-30`（`test_env_backup_runs_restore_point_create_with_volume_and_data_root`）
- 问题：restore 侧断言做了函数分段（`split("cmd_env_restore()")` 后在段内断言），backup 侧四条断言（`restore_point.py create`、`-v "$(db_volume_name):/db"`、`-v "$DATA_ROOT:/data"`、`--secrets-dir /secrets`）都是对整个 deploy.sh 全文做子串匹配。`$(db_volume_name):/db` 这类挂载串在 deploy.sh 其他既有命令中也出现；若 `cmd_env_backup` 自身丢了卷挂载、只剩别处的同名串，用例仍会绿。接线测试本身不执行 deploy.sh（与 t051 既有源码级测试同风格，本轮 `bash -n` 已亲验通过），故定 minor。
- 建议：backup 侧同样按 `cmd_env_backup()` 函数体分段后再断言四条。

### t066_test_f005 - AC-001 云端用例的配置字段未覆盖代理与指纹参数，保存路径只验了 update_profile 一条

- 严重度：minor
- 锚点：AC-001「不因代理、分辨率、时区、语言或指纹参数变化自动清理」
- 位置：`tests/unit/test_t066_profile_state_guards.py:124-145`（`test_config_save_preserves_browser_state_directory`）
- 问题：该用例是真实生产逻辑证据（真 DB + 真 `ProfileService.update_profile`，断言 `_manifest` 全等、seed 保持 123456、Cookie 字节不变），但 patch 字段只有 notes/screen_width/locale/timezone，未含 AC 点名第一位的代理（如 proxy_id 变更），也未含指纹参数字段。update 的合并逻辑对各字段同路，故风险低；「配置不变时重复启动使用同一身份参数」在云端无任何用例，属 [deploy] 切片，已登记 p093 第 1 项，不在本 finding 内重复计较。
- 建议：patch 字段补 proxy_id 与一个指纹类字段各一例即可闭合云端部分。

### t066_test_f006 - AC-003 的 Local State 逐字复制在单测层无断言，clone 夹具未放置 Local State 文件

- 严重度：minor
- 锚点：AC-003「不以盲删 Local State 通过测试」
- 位置：`tests/unit/test_profile_copy_reset.py:60-67`（`_write_state` 只写 Cookies、Default/Preferences 与三个 Singleton 链接，无 `Local State`）；对照 `tests/unit/test_t066_profile_state_guards.py:44-49`（guards 侧夹具含 Local State，但只用于 reset/保存用例）
- 问题：带状态 clone 的核心断言 `_manifest(clone_dir) == _manifest(profile_dir)` 本可证明 Local State 被逐字复制，但夹具里根本没有这个文件，断言对它恒空。引擎侧「无 OSCrypt 密钥根、整目录复制 Cookie 可用」的结论来自 task.md 回填的一次性 spike（脚本在 `.scratch/engine_spike/`，gitignore 不入库），test 轴无法从仓库内复验，该部分证据属 trust_prior；真实引擎往返已登记 p093 第 2 项。
- 建议：copy/reset 夹具的 `_write_state` 补一个带可辨识内容的 `Local State` 文件，manifest 全等断言即自动覆盖逐字复制。

### t066_test_f007 - AC-004 的 reset 后 Artifact 保留在 reset 用例中无断言

- 严重度：minor
- 锚点：AC-004「环境 ID、名称、代理等配置和独立 Artifact 保留」
- 位置：`tests/unit/test_profile_copy_reset.py:144-175`（reset 用例断言了目录清空、配置字段保留、版本递增、seed 重掷、他人 Profile 不受影响，但未建 Artifact）；Artifact 断言只存在于 clone 侧用例（`test_duplicate_does_not_copy_artifacts`、`test_config_only_duplicate_*` 中 clone 的 Artifact 列表为空）
- 问题：reset 实现按构造只替换 user_data_dir、Artifact 存于独立目录，风险低；但 AC 明文要求 reset 后 Artifact 保留，云端本可一例断言（建 Artifact → reset → 列表与内容不变），目前该行为零覆盖，[deploy] 侧 p093 第 3 项也只写「配置与独立 Artifact 保留」的真实 Profile 验证，未点名单测缺口的替代关系。
- 建议：在既有 reset 用例中加建一个 Artifact 并断言 reset 后仍可列出且内容不变。

### t066_test_f008 - AC-009 往返用例未让 config_version 发生分歧，恢复后版本一致只验了 seed 与 Cookie 两个代理量

- 严重度：minor
- 锚点：AC-009「恢复后 Profile 配置版本、cookie/localStorage 和登录态与该恢复点一致」
- 位置：`tests/unit/test_t066_restore_point.py:166-183`（`test_restore_roundtrip_returns_to_point_state`）；`tests/unit/test_t066_restore_point.py:141-163`（manifest 契约断言记录了 `config_version == 3`）
- 问题：往返用例变异的只有 Cookie 字节与 DB 中的 seed，恢复后也只断言这两项回到恢复点值；manifest 侧断言了版本被记录，但没有任何用例让 live 库的 `current_config_version` 在备份后改变再断言恢复回 3。DB 是整文件替换、seed 已证明文件确实被换回，故版本不一致在机制上不可能单独发生，定 minor；同理 localStorage 类文件（Preferences/Local State）在往返中未被变异，只由 manifest 树校验与整目录 rename 机制间接保证。
- 建议：往返用例顺手变异 `current_config_version` 与 Preferences 内容，恢复后一并断言，成本近零。

### t066_test_f009 - 恢复点 create 侧故障面覆盖不全：observed 过渡态拒绝、create 空间失败清理、restore 两处空间检查的区分均未测

- 严重度：minor
- 锚点：AC-005（备份须无实际写者）、AC-010（空间不足）
- 位置：`tests/unit/test_t066_restore_point.py:186-198`（create 拒绝只测 runtime_instance_id 与 desired=running 两态）；`tests/unit/test_t066_restore_point.py:240-254`（空间用例把 `disk_usage` 全局 patch 为 free=0，DB 卷与 data root 两处检查同时失效，无法区分哪处生效）
- 问题：`read_writer_offenders` 对 observed 处于 starting/running/stopping 的拒绝分支无用例；create 过程中途失败（如拷贝时空间耗尽）的 staging 清理只有代码路径（`except BaseException` 后 rmtree staging）无测试；restore 的空间拒绝只证明了「free=0 时拒绝且 live 不变」这一总效果，两处独立检查（DB 卷、data root）未分别注入。空间模拟方法本身可信：patch 的是生产代码实际调用的 `shutil.disk_usage`，且断言了拒绝码与 live Cookie 不变，不是自证。
- 建议：create 拒绝补 observed=starting 一例；空间用例按 patch 目标路径区分两次注入（仅 DB 卷不足、仅 data root 不足）。

### t066_test_f010 - 新增交付文件全部未暂存（未跟踪），规定的 diff 口径单独执行看不到核心交付

- 严重度：minor
- 锚点：review scope 完整性
- 位置：`git status --short` 的 `??` 项：`scripts/restore_point.py`、`tests/unit/test_t066_{profile_state_guards,restore_point,deploy_restore_point_wiring}.py`、`docs/pending/todo/p093_t066_local_deploy_verification.md`
- 问题：本轮全部新增实现与测试仍是未跟踪状态，仅跑 `git diff 680d850` 的复核者会漏掉恢复点工具与全部新测试（本轮靠文件系统直读才看到完整交付，与 t062 的 f005 同型）。指纹已覆盖未跟踪内容、文件可读，不构成 INCOMPLETE。
- 建议：实施方对新交付文件执行 `git add -N`（或暂存）后再派下一轮审阅。

## 结论

- 改测方向复核：`git diff` 中既有测试文件零修改，不存在违反「禁止就地改旧测试预期」的情况；三个 t066 测试文件均为新建。既有 `test_profile_copy_reset.py`（23 passed）与 `test_t051_deploy_scripts.py`（11 passed）原样复跑全绿，与新实现相容。
- 测试真实性总评：新用例总体触达生产逻辑而非自证——guards 侧走真迁移 DB + 真 `ProfileService`（残留实例以替换 `get_runtime` 返回值注入，属数据边界替身，被测的 `_require_fully_stopped` 为生产代码，且断言了拒绝后目录、DB 行、seed 三者均无残余）；restore_point 侧 import 的是 `scripts/restore_point.py` 本体、跑真迁移 DB 与真文件树，损坏用例真改字节（点内 DB 偏移 100 写 `GARBAGE`、Profile 载荷整文件替换）、stamp 用例真改 `alembic_version`、往返用例断言了具体值（Cookie `cookie-v1`、seed 123456、旧集保留且 seed 为 999999）。故障注入中可信度最高的是损坏与 stamp；空间为 monkeypatch `disk_usage` 总量注入（可信但不分卷，见 f009）；中断为伪造态注入（单项可信、跨介质未覆盖，见 f001）。
- seed 专项核查（AC-008）：三个 seed 用例真实存在——单一声明范围（常量恰为 100000/999999 + 200 次生成抽样）、`derive_fingerprint_seed` 确定性与分布（200 个随机 operation_id、>150 个不同值）、带 operation_id 的 reset 五连均落六位范围（旧五位公式下必然全灭，变异敏感成立）；幂等重放的 seed 具体值比对在既有套件 `test_duplicate_and_reset_are_idempotent_with_operation_id` 与并发版用例中（两次 reset 返回 seed 严格相等）；本 reviewer 另 grep 全仓 `src/` 确认五位生成路径已不存在、创建走 `ProfileConfig` 默认工厂同一函数。
- AC-005 残留实例专项：新用例覆盖 duplicate（带状态）与 reset 两条状态改写路径在 desired/observed 均 stopped 但 `runtime_instance_id` 残留时的拒绝，是本 task 的核心新行为，证据成立；启动交错的跨进程围栏与 viewer 不授权停止属 [deploy] 切片，p093 第 4 项已登记（含 viewer 条款逐字对应）。
- 本轮新发现：10 条（1 important、9 minor），无 critical。
- 总体判断：52 条定向用例独立复跑全绿，多数 AC 的云端测试证据真实且断言具体；但 AC-010 最具区分度的条款——DB 与目录跨介质成套切换在各中断点不留版本错配——只有一个仅 Profile 单项的伪造态用例，DB 项回滚与混合中断态零覆盖（f001，important），该 AC 的打勾证据不足。存在未解决 important，test 轴 verdict FAIL。
- 系统性 follow-up：[deploy] 切片已统一登记 p093（6 项，逐项对应 AC-001/003/004/005/011 与 findings 补录），不重复建议；f001 的补测属云端可完成项，不应顺延 p093。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。[deploy] 条。task.md 已打勾；云端部分（普通配置保存后 `_manifest` 全等、seed 不变、Cookie 字节保留）经自跑 guards 5 passed 内成立，字段覆盖缺口见 f005（minor）；真实重启身份一致与代理/指纹全字段保存切片顺延 p093 第 1 项（pending 实存、内容逐字对应）。
- AC-003：TICK-VALID，re_verified。[deploy] 条。task.md 已打勾；云端部分由既有 copy/reset 套件 23 passed 支撑（两态 clone、源不受影响、失败/取消不残留目录或 DB 行、manifest 全等），Local State 夹具缺口见 f006（minor）；引擎无可复制密钥根的 spike 结论已回填 task.md（脚本不入库，属 trust_prior），真实引擎 Cookie 可用往返顺延 p093 第 2 项。
- AC-004：TICK-VALID，re_verified。[deploy] 条。task.md 已打勾；云端部分证据强：reset 后目录整体清空（`list(profile_dir.iterdir()) == []`，强于逐类断言）、配置与版本保留、DB 更新失败时旧目录与 seed 成套恢复（真注入失败）均在 23 passed 内；Artifact 保留断言缺口见 f007（minor）；真实 Profile 全类数据清
    ...[truncated 2085 chars]

______________________________________________________________________

## Round 2 (2026-11-14)

- task：`t066_profile_identity_state`
- round：2（复审 Round 1 的 10 条 finding 修复与 AC 重新打勾）
- reviewed_at：2026-11-14（CST）
- 落点校验（worktree 内实测）：`git rev-parse --show-toplevel` = `<home>/workspace/CBrowser_t066`，`git log --oneline -1` = `680d850`，分支 `t066_profile_identity_state`；审阅范围 = `git diff --cached 680d850`，共 22 个文件（与任务口径一致），`git status --short` 中未跟踪项为 0。

### 复跑实数（本 reviewer 独立执行，非引用实施侧自报）

环境：worktree 内以 `~/workspace/CBrowser/.scratch/gate_venv/bin/python -m pytest <file> -q`（`TMPDIR=.scratch/tmp`）逐文件实跑；未跑全量门禁（主会话并行第三轮）。

|文件|结果|
|---|---|
|`tests/unit/test_t066_restore_point.py`|18 passed，0 failed（120.49s）|
|`tests/unit/test_t066_profile_state_guards.py`|5 passed，0 failed（22.63s）|
|`tests/unit/test_t066_deploy_restore_point_wiring.py`|3 passed，0 failed（0.52s）|
|`tests/unit/test_profile_copy_reset.py`|23 passed，0 failed（133.51s）|
|`tests/unit/test_t051_deploy_scripts.py`|11 passed，0 failed（8.54s）|
|合计|60 passed，0 failed|

restore_point 由 Round 1 的 10 项增至 18 项（新增：tampered manifest、显式 journal、observed 过渡态、空间分卷、混合中断、执行期崩溃注入，及 code 轴 f002/f004 的 create 收尾复查与 staging 清扫两项）；其余四文件用例数与 Round 1 一致（copy_reset 为既有用例内补夹具/扩断言，不增用例数）。实施侧 progress 自报「restore_point 18、guards 5、wiring 3、copy_reset 23 全绿」与本轮实跑逐项吻合。

### Finding 复核表

|finding_id|Round 1 严重度|复核结论|证据|
|---|---|---|---|
|t066_test_f001|important|FIXED|见下方 f001 专项复核：双项混合伪造态用例与执行期真实崩溃注入用例均成立，断言为具体值比对，18 passed 内实跑通过|
|t066_test_f002|minor|FIXED|`test_restore_refuses_tampered_manifest_format_or_kind`：format 改 999、kind 改篡改值两次均断言 restore 返回 1 且 live Cookie（cookie-v2）未动；损坏 DB 用例 docstring 已明示 integrity 分支被 sha256 遮蔽、属纵深防御|
|t066_test_f003|minor|FIXED|`test_restore_with_explicit_journal_inside_data_root`：显式传 data_root 内 `--journal`（与 deploy 的 `/data/restore-journal.json` 同布局）往返成功，断言该路径 journal `phase == "complete"`、默认落点文件不存在、Cookie 与 seed 回到恢复点值|
|t066_test_f004|minor|FIXED|wiring 测试 backup 侧已按 `cmd_env_backup()` 函数体分段（`split("cmd_env_backup()")[1].split("cmd_env_restore()")[0]`）后在段内断言 create/双卷挂载/`--secrets-dir` 四条，假阳性空间消除|
|t066_test_f005|minor|FIXED（另见新 f011）|guards 保存用例 patch 已补 proxy_id、gpu_family、humanize、screen_height（另含 screen_width/locale/timezone/notes），且 proxy_id 与 gpu_family 均断言在返回 config 中生效——达到 Round 1 建议的闭合标准（代理 + 指纹各一代表字段断言生效）|
|t066_test_f006|minor|FIXED|性质复核见下方专项：`_write_state` 仅新增 Local State 夹具文件，既有断言零改动，manifest 全等自动覆盖逐字复制|
|t066_test_f007|minor|FIXED|性质复核见下方专项：reset 用例仅新增 Artifact 建立与保留断言，既有预期零改动|
|t066_test_f008|minor|FIXED|往返用例已同步变异 `current_config_version`（3→7）与 Preferences（`{}`→`{"mutated": true}`），恢复后断言版本回到 3、Preferences 回到 `{}`，与 Cookie/seed 并列具体值比对|
|t066_test_f009|minor|FIXED|`test_create_refuses_transitional_observed_state`：仅 observed=`starting` 即断言 create 返回 2 且恢复点未发布；`test_restore_space_checks_are_per_volume`：以 resolved 路径匹配的 fake `disk_usage` 分别仅封 DB 卷、仅封 data root，两次均断言返回 1 且 live Cookie/seed 不变，两处检查已被区分|
|t066_test_f010|minor|FIXED|交付 22 文件全部暂存，`git diff --cached 680d850` 可见全部交付（含新文件），未跟踪项为 0（本轮落点校验实测）|

#### f001 专项复核（测试有效性）

- 混合伪造态的忠实度（`test_interrupted_mixed_switch_rolls_back_db_and_profile`）：journal 的 items 顺序（DB 先行、profile 在后）、`state` 组合（DB=`switched`、profile=`pending`）、`sidecars` 标记（DB=true、profile=false）、staged/previous 路径命名（`cbrowser.db.restore-staging-<id>` / `cbrowser.db.pre-restore-<id>` / 目录侧 `.restore-staging-<id>` / `.pre-restore-<id>`）均与正向 switch 的落盘形态逐项对照一致；DB 项的布置忠实于正向 rename 语义的终态——旧主文件与旧 `-wal`/`-shm` 位于 previous 旁、live 为恢复点副本、live 旁无 sidecar。profile 项的 previous_path 已在 journal 中预记但实体尚不存在，亦与正向 journal 先记名、后 rename 的形态一致。
- 混合用例断言具体性：回滚后断言 `-wal`/`-shm` 字节分别为 `b"old-wal"`/`b"old-shm"`（文件级恢复断言）、DB seed=999999、Profile Cookie=`cookie-v2`（双介质同时回到旧集）；再跑后断言 seed=123456、Cookie=`cookie-v1`（双介质同时完成新集）。哨兵 sidecar 字节在 seed 读取前被显式 unlink 并注明原因（避免伪造 WAL 字节干扰 SQLite 读取），不影响字节级移动断言的成立。该用例对 `_move_sidecars` 对称移动具备变异敏感性：回滚侧漏移 previous 的 sidecar 时，live 旁 `-wal`/`-shm` 字节断言必然失败——与实施侧自报「该用例实测暴露实现缺口」互相印证。
- 执行期真实注入（`test_restore_crash_after_db_switch_rolls_back_on_next_run`）：monkeypatch 的是生产代码自身调用的 `rp._atomic_write_json`，在第 2 次调用（初始 journal 落盘为第 1 次、DB 项 switched 回写为第 2 次）抛错，注入点精确落在「DB rename 已发生、journal 回写未落盘」的窗口。用例先断言盘上 journal 的 DB 项仍为 `pending`（journal 落后于文件系统这一关键形态由真实执行产生，非手工拼装），再断言下一次调用返回 3 并回滚至旧集（seed=999999、Cookie=`cookie-v2`）、再下一次返回 0 完成新集（seed=123456、Cookie=`cookie-v1`）。与伪造态用例互补：伪造态覆盖 journal 已记 switched 的分支，注入用例覆盖 journal 未及回写的分支，AC-010「每个中断点」的两类 journal/文件系统相对状态均有真实证据。

#### f006 / f007 性质复核（既有测试改动是否属「改预期追随输出」）

- 结论：两处均为「补夹具 / 扩展断言」，不属改测追随输出。证据：`git diff --cached` 中 `tests/unit/test_profile_copy_reset.py` 为纯新增行（25 行新增、0 行删除/修改），没有任何既有断言或预期值被改写。
- f006：`_write_state` 新增 `Local State` 文件（内容 `{"os_crypt": {}}`，与 Preferences 的 `{}` 可辨识区分）。`_manifest` 的实现只跳过三个 Singleton 链接、对 Local State 按 sha256+大小入册（直读 `profile_service.py` 确认），故既有的 `_manifest(clone_dir) == _manifest(profile_dir)` 全等断言在夹具补入后自动变为对 Local State 逐字复制的真实检验——断言未动、检验变严；且 duplicate 生产路径本身亦以同一 manifest 全等做失败回滚，双层成立。
- f007：reset 用例在 reset 前经 `ArtifactRepository` 真建 Artifact（`a1`/`keep.csv`，内容 `b"keep-me"`），reset 后新增断言列表恰为 `["a1"]` 且文件字节不变。新增断言的方向是 AC-004 的原文要求（独立 Artifact 保留），不是把既有预期放宽；既有断言（目录清空、配置/版本保留、他人 Profile 不受影响）逐字未动。

#### 新 finding

##### t066_test_f011 - guards 保存用例中 patch 的多数标量字段未断言生效（humanize/screen_height 等仅入参）

- 严重度：minor（不阻断）
- 锚点：AC-001 云端证据的字段级强度
- 位置：`tests/unit/test_t066_profile_state_guards.py` 的 `test_config_save_preserves_browser_state_directory`
- 问题：patch 已扩为 8 个字段（notes、proxy_id、screen_width=1280、screen_height=900、locale、timezone、gpu_family、humanize=False），但返回 config 的生效断言只覆盖 notes、proxy_id、gpu_family 三项；screen_height（默认 1080）、humanize（默认 True，被 patch 为 False，属 falsy 值、正是合并层最易静默丢失的一类）等仅出现在入参中。若仓储合并层对某个未断言字段静默丢弃，用例仍会绿。本 AC 的核心主张（保存不清理状态目录）由 `_manifest` 全等、seed 不变、Cookie 字节不变三项断言充分支撑，且代理与指纹的代表字段已断言生效，故不影响 AC-001 的 TICK-VALID，仅记字段级覆盖的收尾缺口。
- 建议：对 patch 中其余标量字段各补一行 `updated.config.<field> == <patch 值>` 断言，成本近零；可随后续维护顺手补，不必为此单开一轮。

### AC 判定表（test 轴，Round 2）

|AC|判定|依据|
|---|---|---|
|AC-001|TICK-VALID|guards 5 passed：保存后 manifest 全等、seed 与 Cookie 不变，patch 覆盖代理/分辨率/时区/语言/指纹字段类（字段级断言缺口见 f011，minor 不阻断）；[deploy] 切片顺延 p093 第 1 项|
|AC-003|TICK-VALID|copy/reset 23 passed：两态 clone、源不受影响、失败/取消不残留；Local State 已入夹具且由 manifest 全等覆盖逐字复制（f006 已修）；[deploy] 切片顺延 p093 第 2 项，spike 结论属 trust_prior 的口径不变|
|AC-004|TICK-VALID|reset 全清（目录整体清空断言）、配置与版本保留、DB 失败时成套恢复均在 23 passed 内；reset 后 Artifact 保留断言已补（f007 已修）；[deploy] 切片顺延 p093 第 3 项|
|AC-005|TICK-VALID|残留 runtime_instance_id 拒绝 duplicate/reset（guards）+ create 侧拒绝 runtime 绑定/desired=running/observed 过渡态（f009 已修）+ create 复制期写者出现即弃点（code 轴 f002 的新用例，spy 注入 `_copy_tree_manifest` 后改 DB、断言返回 2 且未发布，从测试角度成立）；[deploy] 切片顺延 p093 第 4 项|
|AC-008|TICK-VALID|seed 三用例（单一声明范围、确定性推导与分布、reset 带 operation_id 五连范围）随 guards 5 passed 复跑通过，Round 1 的专项核查结论不变|
|AC-009|TICK-VALID|成套内容与往返一致性：往返断言已扩至 config_version 与 Preferences（f008 已修）；同一静默时刻由 create 收尾复查用例守护（写者出现/版本变化两种变异均弃点）；凭据只记名、内容不入点的断言在 manifest 契约用例内复跑通过|
|AC-010|TICK-VALID|Round 1 的 VOID 理由已消除：混合中断伪造态（DB switched + profile pending，含 sidecar 文件级恢复）与执行期崩溃注入（journal 落后于文件系统）两用例补齐跨介质中断覆盖（f001 已修）；损坏/篡改/stamp/空间分卷拒绝均在触碰活数据前返回且有用例（f002/f009 已修）；显式 journal 布局往返成立（f003 已修）|
|AC-011|TICK-VALID|接线断言已按函数分段（f004 已修），子命令分发、卷挂载、journal 路径与先停栈均在段内断言；[deploy] 隔离真实部署往返顺延 p093 第 5 项|

coverage = 8 / 8

### AC 复验方式

（下行与上方判定表同源，为工具链行式口径转写，判定与依据一致。）

- AC-001：TICK-VALID，re_verified。guards 5 passed：保存后 manifest 全等、seed 与 Cookie 不变，patch 覆盖代理/分辨率/时区/语言/指纹字段类（字段级断言缺口见 f011，minor 不阻断）；[deploy] 切片顺延 p093 第 1 项。
- AC-003：TICK-VALID，re_verified。copy/reset 23 passed：两态 clone、源不受影响、失败/取消不残留；Local State 已入夹具且由 manifest 全等覆盖逐字复制（f006 已修）；[deploy] 切片顺延 p093 第 2 项，spike 结论属 trust_prior 的口径不变。
- AC-004：TICK-VALID，re_verified。reset 全清（目录整体清空断言）、配置与版本保留、DB 失败时成套恢复均在 23 passed 内；reset 后 Artifact 保留断言已补（f007 已修）；[deploy] 切片顺延 p093 第 3 项。
- AC-005：TICK-VALID，re_verified。残留 runtime_instance_id 拒绝 duplicate/reset（guards）+ create 侧拒绝 runtime 绑定/desired=running/observed 过渡态（f009 已修）+ create 复制期写者出现即弃点（code 轴 f002 的新用例，测试角度成立）；[deploy] 切片顺延 p093 第 4 项。
- AC-008：TICK-VALID，re_verified。seed 三用例（单一声明范围、确定性推导与分布、reset 带 operation_id 五连范围）随 guards 5 passed 复跑通过，Round 1 的专项核查结论不变。
- AC-009：TICK-VALID，re_verified。成套内容与往返一致性：往返断言已扩至 config_version 与 Preferences（f008 已修）；同一静默时刻由 create 收尾复查用例守护（写者出现/版本变化两种变异均弃点）；凭据只记名、内容不入点的断言在 manifest 契约用例内复跑通过。
- AC-010：TICK-VALID，re_verified。Round 1 的 VOID 理由已消除：混合中断伪造态（DB switched + profile pending，含 sidecar 文件级恢复）与执行期崩溃注入（journal 落后于文件系统）两用例补齐跨介质中断覆盖（f001 已修）；损坏/篡改/stamp/空间分卷拒绝均在触碰活数据前返回且有用例（f002/f009 已修）；显式 journal 布局往返成立（f003 已修）。
- AC-011：TICK-VALID，re_verified。接线断言已按函数分段（f004 已修），子命令分发、卷挂载、journal 路径与先停栈均在段内断言；[deploy] 隔离真实部署往返顺延 p093 第 5 项。

### 结论

- Round 1 的 10 条 finding：10 条全部 FIXED（f005 附带新记 1 条 minor f011，为字段级断言收尾缺口，不属 f005 的 NOT-FIXED）。
- 本轮新发现：1 条 minor（t066_test_f011），无 critical、无 important。
- 改测方向复核：本轮唯一的既有测试文件改动 `test_profile_copy_reset.py` 为纯新增（补夹具 + 扩展断言、既有预期零改写），不违反「禁止就地改旧测试预期」；其余 t066 测试文件为新建后在本轮扩充用例。
- 总体判断：60 条定向用例独立复跑全绿；AC-010 的跨介质中断证据已由「仅 Profile 单项伪造态」补强为「双项混合伪造态 + 执行期真实注入」两路互补证据，Round 1 唯一的 important 已闭合；8 条 AC 的打勾从测试证据角度全部成立。test 轴 verdict：PASS。

verdict: PASS

## Round 3 (2026-11-14)

- round：3（确认轮：Round 2 后登记增量与最终指纹确认）
- reviewed_at：2026-11-14（CST）

reviewed_scope: 2d41c54dcc846658

增量逐项核对结论（本 reviewer 在最终指纹状态下直读文件与 git diff --cached 亲核，未发现清单外变化）：

- 增量 1（f011 修复）：直读 `tests/unit/test_t066_profile_state_guards.py` 的 `test_config_save_preserves_browser_state_directory`，patch 共 8 个字段（notes、proxy_id、screen_width、screen_height、locale、timezone、gpu_family、humanize），现已全部有生效断言——原有 notes、proxy_id、gpu_family 三项之外，本轮新增的 5 行断言逐字在位：`screen_width == 1280`、`screen_height == 900`、`locale == "en-US"`、`timezone == "America/New_York"`、`humanize is False`，另有 seed 保持 123456、manifest 全等与 Cookie 字节不变断言；Round 2 新记的 minor t066_test_f011 至此闭合。
- 增量 2（restore_point 注释）：`scripts/restore_point.py` 的 `_default_journal` 注释已改述为 deploy 显式 journal 同在 data root 内（`/data/restore-journal.json`），函数体仍仅 `return data_root / ".restore-journal.json"`，无逻辑变化，与测试无关。
- 增量 3（文档格式规范化）：抽查 `git diff --cached` 确认 `docs/blueprint/security.md` 的增量为列表项间补空行的 md_kx 规范化（既有文字零改动、零删除），`docs/specs/profile_management.md` 仅在 t066 节标题前补空行；两文件实质文字均为 Round 2 已审的 t066 节，无内容变化。
- 增量 4（过程文件）：两份 review 文件与 progress.md 的结构重排与 md_kx 规范化属过程文件、不在指纹范围内，判定与内容未变；progress.md 的 Review 处置表已有 t066_test_f011 一行（minor、已修），表述为补 screen_width/screen_height/locale/timezone/humanize 五项生效断言、复跑 5 passed，与本轮直读与实跑事实相符。
- 范围完整性：交付仍为 22 文件全部暂存，`git status --short` 无未跟踪项、无未暂存改动；本 reviewer 亲算指纹为 `2d41c54dcc846658`，与期望值一致。
- 抽跑实数（本 reviewer 独立执行，`TMPDIR=.scratch/tmp`）：`tests/unit/test_t066_restore_point.py` 18 passed、`tests/unit/test_t066_profile_state_guards.py` 5 passed、`tests/unit/test_t066_deploy_restore_point_wiring.py` 3 passed、`tests/unit/test_profile_copy_reset.py` 23 passed、`tests/unit/test_t051_deploy_scripts.py` 11 passed，合计 60 passed、0 failed，与期望逐项吻合。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本轮 guards 5 passed 且保存用例 8 个 patch 字段已全部断言生效、manifest 与 seed 与 Cookie 不变，f011 闭合后字段级证据完整。
- AC-003：TICK-VALID，re_verified。本轮 copy/reset 23 passed，Local State 已入夹具并由 manifest 全等断言覆盖逐字复制。
- AC-004：TICK-VALID，re_verified。本轮 copy/reset 23 passed，reset 全清与配置保留及 Artifact 保留断言均在其中通过。
- AC-005：TICK-VALID，re_verified。本轮 guards 5 passed 与 restore_point 18 passed 共同覆盖残留实例拒绝与 create 侧写者及过渡态拒绝。
- AC-008：TICK-VALID，re_verified。本轮 guards 5 passed 内 seed 单一范围与确定性推导与 reset 范围三用例复跑通过。
- AC-009：TICK-VALID，re_verified。本轮 restore_point 18 passed 内往返用例断言 config_version 与 Preferences 与 Cookie 与 seed 均回到恢复点值。
- AC-010：TICK-VALID，re_verified。本轮 restore_point 18 passed 内混合中断伪造态与执行期崩溃注入及损坏与篡改与空间分卷拒绝用例复跑通过。
- AC-011：TICK-VALID，re_verified。本轮 wiring 3 passed 与 t051 11 passed，接线断言按函数分段且子命令与卷挂载与 journal 路径均在段内成立。

coverage = 8 / 8

verdict: PASS

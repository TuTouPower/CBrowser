---
tid: "t066"
slug: "profile_identity_state"
title: "环境数据保留、复制重置与备份恢复"
status: "done"
branch: "t066_profile_identity_state"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "680d850067075caf9356ee6c71771f6dc779c543"
depends_on: "t062"
conflicts_with: "t061,t062,t065,t069"
note: "合并 t070；p074/p089/p080 有效范围；保存配置保留数据、reset 全清、完整备份；取消身份模型与配额"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-13 审阅修订：原 AC-006 转 t070 AC-001..004；原 AC-007 配额退出本批实施，p080 原建议保留待产品评估，编号不复用；新增 AC-008 统一 seed。

- 本次仅维护 backlog；不 start、不实现；旧归档来源只追加转办链，不改写历史。

- 调度字段经 task.py edit 写入；plan 的 runnable 只指依赖/冲突候选，不代表产品 BLOCKING 已解决。

- 调度依据：消费 t062 的公共服务/原子写边界；备份恢复已在本 task 内，与数据操作共用排他与回退协议，不再依赖已合入的 t070；与 t061/t065/t069 重叠。

- 用户已确认：修改配置参数保留 Cookie、浏览器内部存储与登录态；清状态只能来自明确确认的独立操作。reset 保留书签等属于待解释的新增建议，不代表现行能力。

- 用户最新裁决：改配置保留数据；reset 全清书签/偏好/Cookie/存储，保留环境配置与独立 Artifact。原 AC-002 身份轮换退出且编号退休；AC-004 定稿全清。取消全部产品 BLOCKING，仅保留技术 spike。

- 合并确认：用户已明确批准 t070 合入 t066；t070 AC-001/002/003/004 分别映射到本 task AC-009/005/010/011。保留配置数据、reset 全清，不做身份模型或配额。

- 2026-11-13 云端实施（attempt 1，基线为 t062 finish 提交 680d850 的叠栈分支，含 shared/atomic_write 与 shared/profile_locks 唯一实现）。实施状态按「已完成 / 进行中 / 待建」三态分列，文件名逐项核对过 worktree 实存；未建的文件不写成已交付。截至 2026-11-13 23:38 实查：worktree HEAD 仍为 680d850，未提交改动 14 改 + 5 新增（含本 progress.md 自身），尚无实现 commit。

    - 已完成①服务层（AC-005/AC-008，测试已绿）：
        - `src/backend/cbrowser/domain/models.py`：新增 `FINGERPRINT_SEED_MIN/MAX = 100000/999999` 与 `derive_fingerprint_seed(operation_id)`（SHA-256 确定性推导）；`generate_fingerprint_seed()` 改用该常量。
        - `src/backend/cbrowser/services/profile_service.py`：新增 `_runtime_has_writer(runtime)` 与 `_require_fully_stopped()`；delete 走前者，duplicate 与 reset（含状态的两处检查）走后者；`_seed_for_operation` 改为委托 `derive_fingerprint_seed`（删五位公式 `10000 + hash % 90000`）。
        - `tests/unit/test_t066_profile_state_guards.py`（新建，5 项）：seed 空间/确定性/范围、reset 带 operation_id 的范围、残留实例绑定拒绝 duplicate/reset 且不留残余、普通配置保存后 `_manifest` 与 seed 不变；连同既有 copy/reset 套件 34 passed。
    - 已完成② spike（结论已回填 task.md，实验脚本不入库）：
        - OSCrypt/portable_cookies spike：真实引擎 CloakBrowser Chromium `146.0.7680.177.5` 实测——Local State 无 `os_crypt.encrypted_key`，include-state clone 逐字复制即保持 Cookie 可用，不盲删 Local State；脚本在 `.scratch/engine_spike/spike.py`（gitignore）。
        - 现有 DB backup/restore 演练：`db_backup.py` 可用；`db_restore.py` 无校验直接覆盖（改坏 7 字节后活库不可读、原数据已毁），正是 AC-010 要根治的缺陷。
    - 已完成③备份恢复（AC-009/AC-010，测试已绿）：
        - `scripts/restore_point.py`（新建，stdlib only，create/verify/restore）：写者静默检查、SQLite 在线 backup + integrity_check + schema stamp、Profile 目录逐文件 SHA-256 manifest、凭据只记文件名/大小、staging + 原子 rename 发布；恢复先全量校验再带 journal 成套切换，中断由下次调用回滚旧集（旧集保留在 `.pre-restore-<switch-id>`）。
        - `scripts/deploy.sh`：新增 `env-backup [point-dir]` / `env-restore <point-dir>` 子命令（一次性 API 镜像容器挂载 named volume `db`、DATA_ROOT 挂到 `/data`、journal 固定 `/data/restore-journal.json`；env-restore 先 `compose down`）；`bash -n` 通过。
        - `tests/unit/test_t066_restore_point.py`（新建，10 项，10 passed）；`tests/unit/test_t066_deploy_restore_point_wiring.py`（新建，3 项源码级接线断言；连同既有 t051 脚本测试 14 passed）。
    - 已完成④文档与登记：
        - `docs/tasks/t066_profile_identity_state/task.md`：两条 spike 结论已回填；`docs/pending/todo/p093_t066_local_deploy_verification.md`（新建）：[deploy] 本地补验 6 项。
        - `docs/blueprint/domain.md`、`docs/blueprint/security.md`、`docs/blueprint/architecture.md`、`docs/blueprint/testing.md`：各增 t066 节。
        - `DOCKER_DEPLOYMENT.md` §8 重写（恢复点命令；旧 `tar data/instance` 废止为环境备份）、`README.md` 停用与备份节改走 env-backup/env-restore。
        - `docs/specs/profile_management.md`、`docs/specs/release_deployment.md` 各增 t066 节；`docs/specs_index.md` 两行已加 t066（2026-11-13）。
    - 待建/计划变更——`scripts/env_backup.py`、`scripts/env_restore.py`：这两个文件不存在、未建。它们只是计划阶段的暂定名，已收敛为单一实现 `scripts/restore_point.py` + `scripts/deploy.sh` 的 `env-backup`/`env-restore` 子命令（task.md 第 82 行行内已定稿该协议）；不再单独建这两个文件，如后续要拆分须另立项。不要把它们当作已交付或待建缺口。
    - 进行中/待办：task.md 按 AC 打勾、收尾报告、全量门禁、full 级双路独立审阅（review_code.md/review_test.md）、finish + run-close，均未开始。

- 2026-11-14 接续收尾（同一 attempt 1，接手前任未提交状态：14 改 + 5 新增，逐项复核与笔记一致）。新测试数字全部实跑复核：restore_point 10、wiring 3、guards 5、copy_reset 23、t051_deploy_scripts 11，与笔记逐项吻合（笔记「guards 连同 copy/reset 34」口径含其他套件，定向复跑为 5+23=28，不影响用例级结论）。

    - 全量门禁定性（两轮实跑 + 基线对照）：unit 仅 3 条失败在 pristine 680d850 同签名复现（t060 topology 既存基线、fontconfig 的 `os` 属性、repo_hygiene 对 t062 自身 review 文件家路径的检出），均属叠栈基线继承、非本 task 引入；integration 两轮各 12–15 个 error 全为隔离 API 子进程 10 秒启动超时，串行批量复跑 12/12 全过；frontend_test 8 条 5 秒级超时失败，6 文件单跑 67/67 全过；其余套件（protocol_drift、requirements、contract、design_lint、design_check、frontend_build）全绿。e2e/real_engine 云端无 Docker 按口径跳过记 pass。
    - Round 1 双轴审阅均 FAIL（test 轴 1 important、code 轴 2 important），AC 打勾曾按规矩全部撤回；16 条 finding 全部在本 task 内修复（见 Review 处置表），要点：混合中断伪造态用例实测暴露 `_recover_interrupted` 回滚漏移 DB 的 -wal/-shm（旧集不完整），已补 `_move_sidecars` 对称处理并由新用例守护；create 在目录复制后增加写者 + 配置版本收尾复查（AC-009 同一静默时刻）；默认 journal 改入 data_root 内（`.restore-journal.json`）；restore 开始清扫 `.restore-staging-*` 残留；switch/回滚 rename 后 fsync 父目录；三处文档改述为两档写者判定。修复后定向复跑：restore_point 18、guards 5、wiring 3、copy_reset 23 全绿，AC 8 条重新打勾，等 Round 2 复审。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-14T00:09:00+08:00 test 轴 / 2026-11-14 code 轴)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t066_code_f001|important|已修|回滚漏移 DB -wal/-shm，旧集不完整（与 test_f001 同根）|scripts/restore_point.py `_move_sidecars`；tests/unit/test_t066_restore_point.py 混合中断用例|
|t066_code_f002|important|已修|create 仅开始时查写者，复制窗口内新写者可撕裂同一恢复点|scripts/restore_point.py create 收尾复查；test_create_aborts_when_writer_appears_during_copy|
|t066_code_f003|minor|已修|文档称单一写者判定，实现实为两档谓词|docs/blueprint/domain.md、security.md、docs/specs/profile_management.md 改述|
|t066_code_f004|minor|已修|staging 中断残留 .restore-staging-\* 无回收路径|scripts/restore_point.py restore 开始清扫；DOCKER_DEPLOYMENT.md §8 注明；test_restore_sweeps_stale_staging_leftovers|
|t066_code_f005|minor|已修|switch rename 后未 fsync 父目录，掉电耐久性缺口|scripts/restore_point.py switch/回滚 rename 后 \_fsync_dir|
|t066_code_f006|minor|已修|默认 journal 落 data_root 父目录，直调 CLI 时回滚凭据易失|scripts/restore_point.py `_default_journal` 改入 data_root 内|
|t066_test_f001|important|已修|AC-010 中断仅 Profile 单项伪造态，DB 项回滚与混合中断态零覆盖|新增双项混合伪造态 + 执行期真实崩溃注入两用例（后者守护 journal 落后于文件系统的形态）|
|t066_test_f002|minor|已修|manifest format/kind 拒绝无用例；integrity 分支被 sha256 遮蔽未明示|test_restore_refuses_tampered_manifest_format_or_kind；损坏 DB 用例加注 docstring|
|t066_test_f003|minor|已修|显式 --journal（deploy 布局）从未被功能测试执行|test_restore_with_explicit_journal_inside_data_root|
|t066_test_f004|minor|已修|接线测试 env-backup 断言未按函数分段，有假阳性空间|tests/unit/test_t066_deploy_restore_point_wiring.py 按 cmd_env_backup 函数体分段|
|t066_test_f005|minor|已修|AC-001 保存用例未覆盖代理/指纹字段|guards 保存用例补 proxy_id、gpu_family、humanize、screen_height|
|t066_test_f006|minor|已修|clone 夹具无 Local State，逐字复制无断言|tests/unit/test_profile_copy_reset.py `_write_state` 补 Local State，manifest 全等自动覆盖|
|t066_test_f007|minor|已修|reset 后 Artifact 保留无 reset 侧断言|reset 用例建 Artifact 并断言 reset 后仍在且内容不变|
|t066_test_f008|minor|已修|AC-009 往返未让 config_version/Preferences 分歧|往返用例同步变异 config_version 与 Preferences 并断言恢复|
|t066_test_f009|minor|已修|create observed 过渡态拒绝、restore 两处空间检查未分别注入|test_create_refuses_transitional_observed_state；test_restore_space_checks_are_per_volume|
|t066_test_f010|minor|已修|新增交付文件未暂存，git diff 口径漏核心交付|finish 前交付文件全量 git add（含本轮 review 文件）|
|t066_test_f011|minor|已修|（Round 2 新记）保存用例 patch 8 字段仅断言 3 项生效，falsy 字段静默丢失无守护|guards 保存用例补 screen_width/screen_height/locale/timezone/humanize 五项生效断言，复跑 5 passed|

Round 1 复核过程（散文）：test 轴 verdict FAIL（f001 important，AC-010 判 TICK-VOID，其余 7 条 TICK-VALID）；code 轴 verdict FAIL（f001/f002 important，AC-009/AC-010 判 TICK-VOID，其余 6 条 TICK-VALID）。实施侧按规矩撤回全部打勾，逐条修复后以定向实跑复验（restore_point 18、guards 5、wiring 3、copy_reset 23 全绿）重新打勾 8/8。

Round 2 复核（2026-11-14）：code 轴 verdict PASS——Round 1 六条 finding 逐条 FIXED（reviewer 亲跑 restore_point 18、guards+wiring 8 全绿），AC 8/8 TICK-VALID，零新 finding（仅一处注释措辞不精确，已顺手改准：`_default_journal` 注释由「same location」改述为 deploy 显式 journal 同在 data root 内）。test 轴 verdict PASS——Round 1 十条 finding 逐条 FIXED（reviewer 亲跑五文件合计 60 用例全绿），AC 8/8 TICK-VALID；新记 minor 一条 t066_test_f011，已当场补断言闭合（见上表）。至此双轴两轮审阅全部 PASS，无未解决 finding。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：全量门禁（云端直跑分支，三轮实跑 + 定向复跑定性）：protocol_drift_check、requirements_check、design_lint、design_check、frontend_build 全 PASS；contract 257 passed / 1 skipped；unit 并行 2038 passed / 1 skipped / 3 failed + 串行 64 passed——3 条失败（t060 topology、fontconfig `os` 属性、repo_hygiene 对 t062 review 文件家路径的检出）均在 pristine 680d850 同签名复现，属叠栈基线继承、非本 task 引入；integration 并行 174 passed / 7 skipped / 14 errors + 串行 4 passed——14 个 error 全为隔离 API 子进程 10 秒启动超时，串行整批复跑 14/14 全过；frontend_test 621 passed / 2 failed——2 条 5 秒级超时，单文件复跑 18/18 全过。本 task 定向套件：restore_point 18、guards 5、wiring 3、copy_reset 23、t051_deploy_scripts 11。
- 黑盒：e2e / real_engine 云端无 Docker，按本仓口径跳过记 pass 并记录在案；[deploy] 真实部署切片（AC-001/003/004/005/011 的真实引擎与 named volume 往返）顺延 p093 于本地合入前补验。
- review：full 级双轴。Round 1 双轴均 FAIL（code 2 important + 4 minor；test 1 important + 9 minor），实施侧撤回全部打勾逐条修复（含回滚 sidecar、create 收尾复查两处实现级修复）；Round 2 双轴均 PASS，AC 8/8 TICK-VALID，Round 2 新记 minor 一条（t066_test_f011）已当场补断言闭合。共 17 条 finding 全部已修，无遗留 finding。
- AC 判定：见 `task.md` 行内打勾（8/8；[deploy] 条以云端可验部分成立 + p093 顺延为凭据）

### 结果摘要

- 服务层：seed 单一空间与确定性推导（domain/models.py）；duplicate/reset 完全停止判定与 delete 实际写者判定两档守卫（services/profile_service.py），残留 runtime 实例绑定在状态改写与备份取点均被拒绝。
- 备份恢复：新增 scripts/restore_point.py 恢复点协议（同一静默时刻成套取点、全量校验前置、journal 成套切换与中断回滚、旧集保留）+ deploy.sh env-backup/env-restore 子命令；db_restore 无校验覆盖的旧路径退出环境恢复入口（演练实证回填 task.md）。
- 两条 spike 结论已回填 task.md 未知契约清单（OSCrypt 无密钥根、db_restore 毁库实证）；findings.py 因 main 既存 d037/d038 编号重复拒绝分配新号（工具链缺陷，前任已报告），结论暂存 task.md，未入库 findings。
- 遗留只写引用：[deploy] 本地补验见 `docs/pending/todo/p093_t066_local_deploy_verification.md`（6 项）。

### 长期文档闭环

- specs_index：`profile_management` 与 `release_deployment` 两行均已登记 t066（2026-11-13）。
- blueprint：domain.md / security.md / architecture.md / testing.md 各增 t066 节；DOCKER_DEPLOYMENT.md §8 与 README 备份指南改走恢复点命令。
- 正式 spike：OSCrypt 与 DB backup/restore 两条以云端一次性样本完成，实验脚本留 worktree `.scratch/engine_spike/`（gitignore 不入库），结论与采纳（不盲删 Local State、以恢复点协议取代 tar + db_restore 为环境恢复契约）已回填 task.md；findings 入库因工具链编号缺陷受阻（见结果摘要），后续 tid 以 p093 承接本地复核。

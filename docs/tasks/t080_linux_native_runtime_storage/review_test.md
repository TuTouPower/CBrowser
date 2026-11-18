# Task review t080（reviewer_focus: 测试）

- task：`t080_linux_native_runtime_storage`
- spec：`docs/tasks/t080_linux_native_runtime_storage/task.md`
- diff_anchor：`dffadb298c123ae77a8e8b1f224731ba59030076`
- target：`git diff dffadb298c123ae77a8e8b1f224731ba59030076`
- round：1
- reviewed_at：2026-11-18T09:35:30+08:00

reviewed_scope: c459794e3798e595

## Findings

### t080_test_f001 - api runtime 卷挂载断言是整文件子串匹配，挂载目标写错也全绿（f001 回归防线失效）

- 严重度：important
- 锚点：AC-007（删除语义依赖 API 与 Supervisor 看到同一 runtime 物理树，即 code f001 的修复点）；弱化断言（子串包含代替精确匹配）
- 位置：`tests/unit/test_t080_deploy_wiring.py:88`（`test_compose_api_mounts_runtime_volume_at_data_runtime`）
- 问题：该测试是 code f001 修复（compose 给 api 服务挂 `runtime:/data/runtime`）的唯一防线，但断言只是对整份 compose.yaml 做 `"- runtime:/data/runtime" in text` 子串匹配：既不限定 api 服务块，也不是整行精确匹配。变异验证（本轮实测）：把 compose.yaml 中 api 服务的挂载行改成 `- runtime:/data/runtime-mut` 后，test_t080_deploy_wiring.py 8 条测试全部通过——API 把 runtime 卷挂到错误路径、删 Profile 时删的不是真实 runtime 树这一原始缺陷形态不会被任何测试抓到。同理，把该行从 api 块挪到别的服务、只要文件里还留一行同样的字串，测试照样通过。
- 建议：用仓库已有的 `_service_block`（test_t027_release_controller 已提供同类助手）把断言限定在 api 服务块内，并对整行做精确匹配（行级相等或带行尾锚点的匹配），使目标路径或所属服务变化必红。

### t080_test_f002 - AC-004 的「容量不足」与 dry-run 不变性无任何直接测试

- 严重度：minor
- 锚点：AC-004（容量不足时 apply 在切换前失败；迁移 dry-run 不修改源/目标/DB/指针）
- 位置：`tests/unit/test_t080_storage_migration.py`（全文件无容量与 dry-run 用例）；实现位于 `src/backend/cbrowser/supervisor/storage_migration.py:563`（`_check_capacity`）与 `scripts/storage_migration.py`（inventory 入口）
- 问题：变异验证（本轮实测）：把 `_check_capacity` 的 `if free < bytes_needed:` 中和为恒假后，test_t080_storage_migration.py 21 条测试全部通过——容量校验分支零覆盖。dry-run（inventory）一侧同样只有 build_plan 的分类断言，没有任何测试断言盘点后源/目标文件系统不变；progress.md 称 AC-004「由迁移核心单元测试完整覆盖（dry-run 不变性……）」与实际测试内容不符（属自述夸大，不影响其余 AC-004 子条件的真实覆盖：写者、归属、恢复点缺失/篡改、摘要不符均有切换前失败测试，且写者门禁经本轮变异验证被抓）。
- 建议：补两条小测试：monkeypatch `shutil.disk_usage` 返回不足空间断言 run() 在落盘前抛 MigrationError；对源/目标目录做前后快照（路径+摘要）断言 inventory/build_plan 后完全一致。并修正 progress.md 的覆盖自述。

### t080_test_f003 - 整体删除的替代覆盖有两处未在 NOTE 中声明的断言丢失

- 严重度：minor
- 锚点：AC-009/AC-010 字体预检场景（t027 删除清单）；`docs/tasks/t080_linux_native_runtime_storage/progress.md` 删除清单与 NOTE 的等价性声明
- 位置：`tests/unit/test_t080_deploy_harness.py:172`（`test_fonts_preflight_warns_and_continues`）；`tests/unit/test_refactor_behavior_equivalence.py` 的 t080 NOTE
- 问题：逐条比对被删原测试与替代测试后发现两处断言静默丢失且 NOTE 未声明：①原 `test_fonts_preflight_warns_and_continues` 断言 `"WARNING" in stdout` 且 `"fonts directory" in stdout`，替代测试只剩 WARNING 一条（场景已变为「卷存在但为空」，check_font_sets.py 此时输出的是 "no valid font set found"，原断言确已不适用，但 harness docstring 称行为断言 unchanged、NOTE 亦未说明这一处删减）；②test_refactor_behavior_equivalence 删除的 `test_container_spec_stream_specs` 中 `stream_ports(30006) == {"30006/udp": ("127.0.0.1", 30006)}` 一条无任何现存测试覆盖（NOTE 只声明 label 契约由 test_t050 覆盖、卷部分由 t080 新文件覆盖，未提 stream_ports；stream_environment 的其余断言经核对确由 test_stream_ice_config / test_stream_display_config / test_stream_agent_lifecycle 等既有测试覆盖）。两处均为低风险纯函数/文案断言，不影响任何 AC 的整体支撑。
- 建议：在 t027 与 refactor 两处 NOTE 中补记这两条断言的去向（有意不补或补回 stream_ports 的一行断言），使删除清单与实际覆盖严格一致。

## 结论

- 改测方向复核：无「迁就实现」的就地改预期。被改的既有测试只有三类，均已逐 hunk 核对：①语义失效的 bind-mount `volumes` 字典断言整体删除并留 NOTE，场景以 typed `mounts` 表示在新文件重写；②5 个文件的 fixture 把 gate/x11 stub 路径移到生产同款受管根（test_a9_stream_residue、test_t051_docker_error_detail、test_t051_supervisor_identity、test_t052_supervisor_probe、test_supervisor_docker_boundaries），断言逐行未动，progress.md 的「断言未动」自述属实；③test_t027 的 fake repo 脚本清单补入 deploy_volume_ops.py（harness 维护性改动，NOTE 与 progress 均有记录）。另 test_t035_profile_domain 新增 .secrets 清理断言是 code f001 修复的新行为覆盖，方向正确。
- 删除清单一致性：progress.md 记录的删除与 diff 逐项一致——整体删除共 20 条测试函数（test_refactor_behavior_equivalence 2、test_t066 1、test_t054 1、test_t027 6、test_t068 1、test_a36 1、test_supervisor_selkies_token_isolation 2、test_supervisor_selkies_tokens 1、test_t035_proxy_runtime 1、test_t041_font_runtime 2（连同专用辅助 \_start_browser）、test_t052_supervisor_probe 1、test_a24 1），每处均在原文件留 NOTE 指向替代文件；替代等价性逐条核对通过（selkies 两条 stream-token 测试合并为一条且断言无丢失；t052 probe 的 policy/cleanup 断言完整搬运；t041 字体「根不挂载」以「FONTS_VOL 挂载 subpath 恒非空」等价表达），仅 f003 两处小断言丢失未声明。
- 变异验证（本轮实测，均已逐字节恢复并以 sha256 与复跑确认）：①volume_spec 浏览器 gate 挂载 ro→rw，被 test_browser_volumes_are_exact_subpath_mounts 抓到；②storage_migration SKIP_NAMES 去掉 SingletonLock，被 test_plan_classification 抓到；③_check_writers 写者门禁中和，被 test_run_refuses_writers 抓到；④compose api runtime 挂载目标改名，未被抓到（f001）；⑤_check_capacity 中和，未被抓到（f002）。变异后三文件 sha256 与变异前一致，t080 五文件复跑 52 passed。
- 测试运行证据：t080 五文件 52 passed；全部被改既有测试文件 + test_t050_sandbox_grouping + test_stream_ice_config 共 268 条中 266 passed，2 条失败为 test_t068_engine_artifact_pinning 的 cache-init 用例，失败原因是本机 linux-x64 不在 ADR 021 批准清单（`unapproved_engine_build`），与 progress.md 记录的纯净基线失败族一致，与本 task 测试改动无关（已当场复现确认报错文本）。
- 本轮新发现：3 条（important 1、minor 2）
- 未进表的提示：scripts/storage_migration.py 与 scripts/deploy_volume_ops.py 两个新 CLI/运维脚本无直接测试（核心逻辑均经 storage_migration 模块测试与 deploy harness 间接覆盖），属可选覆盖扩展，不阻断。
- 总体判断：测试整体可信——新语义覆盖真实触达生产实现（MountPlanner/volume_spec/DockerAdapter 真实 start 路径/MigrationRunner 真实文件系统），删除替代基本等价且清单诚实；但 f001 的弱断言使 code f001 的回归防线形同虚设，须修后重审。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。storage_layout/adapter_mounts/deploy_wiring 测试本轮复跑全绿，断言覆盖卷拓扑、typed subpath mounts 与 compose 无 macOS 热数据 bind mount；真实 Engine 读写部分按契约区处置注记延期 p127。
- AC-002：TICK-VALID，re_verified。MountPlanner 越界/卷根拒绝、Browser 精确子目录挂载、Stream 无 Profile/Artifact/字体挂载、secret 目录不挂载均有断言且复跑通过，变异①被抓；真实 Engine 隔离实证按处置注记延期 p127。
- AC-003：TICK-VALID，re_verified。迁移分类断言终态事件相关路径（control/events-cursor 等）落 data 卷而非 runtime 卷，既有恢复点与 Profile 语义测试（t035/t066 等被改文件）复跑通过；真实重启持久链路按处置注记延期 p129。
- AC-004：TICK-VALID，re_verified。实际写者、归属不符、恢复点缺失/篡改/外来点、目标冲突均有切换前失败测试且复跑通过，写者门禁经变异③验证有效；容量不足与 dry-run 不变性缺直接测试见 f002（minor，不推翻本条整体支撑）。
- AC-005：TICK-VALID，re_verified。迁移 happy path 逐文件内容保持、重跑幂等（done 返回且不重复复制）、异 plan journal 拒绝均有测试且复跑通过；真实部署身份逐项比对按处置注记延期 p129。
- AC-006：TICK-VALID，re_verified。copy 故障注入后 journal 恢复、switch 被拒后 rollback 清理已建目录、rollback 只删本轮落盘文件且采纳文件保留、CLI 式 rollback 采纳 journal 身份均有测试且复跑通过，变异②被抓。
- AC-007：TICK-VALID，re_verified。test_t035_profile_domain 新增 .secrets 清理断言与既有 clone/reset/delete 语义测试复跑通过，迁移计划排除 Singleton 锁/socket 经变异②验证；但 compose api runtime 挂载的防线断言偏弱见 f001（important），真实部署链路按处置注记延期 p129。
- AC-008：TICK-VALID，re_verified。adapter_mounts 断言字体集以 fonts 卷精确 subpath 只读挂载且字体根不挂载，迁移测试断言字体文件内容保持，deploy harness 覆盖字体预检两场景；真实挂载摘要比对按处置注记延期 p129。
- AC-009：TICK-VALID，trust_prior。[deploy] 全链路演练云端不可执行，按用户 2026-11-18 裁定打勾表示云端可做部分完成；其分段行为（rollback 恢复目标端口、sha 不符拒绝且不动盘、指纹哈希渲染产物、损坏缓存拒绝）已由 deploy_harness 在 fake docker 下复跑通过，真实演练依赖 p127 本地补验登记。

coverage = 8 / 9

verdict: FAIL

## Round 2 (2026-11-18T09:46:35+08:00)

- task：`t080_linux_native_runtime_storage`
- round：2

reviewed_scope: db0d10e046b053d2

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：
    - t080_test_f001（important）已消除。`tests/unit/test_t080_deploy_wiring.py:88-96` 的 `test_compose_api_mounts_runtime_volume_at_data_runtime` 已改用 `test_t027_release_controller._service_block` 限定 api 服务块，并把块内行 strip 后做整行精确匹配（`"- runtime:/data/runtime" in lines`）。本轮变异复现（均用事先保存的副本逐字节还原，sha256 复核一致）：①把 compose.yaml 第 55 行 api 挂载目标改名为 `- runtime:/data/runtime-mut` → 该测试红（1 failed, 7 passed），旧子串断言形态下此变异会放行；②在 api 行保持改名的同时把精确行 `- runtime:/data/runtime` 插入 gateway 服务块（文件内存在该整行但不在 api 块）→ 该测试仍红，证明服务块限定真实生效。变异后 compose.yaml sha256 恢复为 9e312c179efe3476…，与变异前一致。
    - t080_test_f002（minor）已消除。容量：`tests/unit/test_t080_storage_migration.py:542` 的 `test_run_refuses_when_target_capacity_insufficient` 以 monkeypatch 把 `storage_migration.shutil.disk_usage` 置为 free=0（系统边界 mock），经 `MigrationRunner.run()` 真实触达 `_check_capacity`（`src/backend/cbrowser/supervisor/storage_migration.py:421,563`），断言 MigrationError 且目标文件未落盘。本轮变异：把 `_check_capacity` 的 `if free < bytes_needed:`（:571）中和为恒假 → 恰该新测试红、其余 22 条绿（1 failed, 22 passed），证明分支真实覆盖；变异后 sha256 恢复一致。dry-run：同文件 `:567` 的 `test_inventory_dry_run_changes_nothing` 对源 data/fonts 树做前后「路径+SHA-256」快照，先直调 `build_plan` 再以子进程跑 `scripts/storage_migration.py inventory` 入口，断言 returncode=0、输出 files 数与 plan 一致且源快照不变。本轮变异：在 CLI inventory 分支插入向源根写标记文件的语句 → 该测试红；变异后 sha256 恢复一致。dry-run 的目标/journal 一侧：inventory 入口与 build_plan 签名均不接受目标或 journal 参数，无可写句柄，此点经代码核对成立，不构成缺口。progress.md 的 AC-004 覆盖自述已按实际覆盖面修正，与测试内容相符。
    - t080_test_f003（minor）已消除。①stream_ports 断言已补回：`tests/unit/test_t080_adapter_mounts.py:354` 的 `test_stream_ports_map_udp_mux_to_loopback` 直调生产 `cbrowser.supervisor.container_spec.stream_ports`，断言 `stream_ports(30006) == {"30006/udp": ("127.0.0.1", 30006)}`，与被删原断言逐字一致，随本轮全量复跑通过。②两处 NOTE 声明均到位：`tests/unit/test_refactor_behavior_equivalence.py:173-182` 的 NOTE 明记 stream_ports 断言由上述新测试承载（含来源与轮次）；`tests/unit/test_t027_release_controller.py:687-702` 的 NOTE 明记「fonts directory」文案断言不沿用、替代为卷场景的警告；替代测试 `tests/unit/test_t080_deploy_harness.py:166` 同时断言 `"WARNING" in result.stdout` 与 `"no valid font set found" in result.stdout`，与 NOTE 声明一致，harness docstring 的 unchanged 表述与该 NOTE 合读无矛盾。
- 改测方向复核：无「迁就实现」的改测。本轮修复均为新增/加强断言（f001 整行精确匹配、f002 两条新测试、f003 补回 stream_ports 与补强 fonts 警告断言），无删断言、无反转、无弱化；危险模式全量扫描（skip/only/xfail/恒真断言/type: ignore/条件跳过断言）对 t080 新文件与本轮被改文件无命中。
- 变异验证（本轮实测，全部以事先保存的副本逐字节还原并 sha256 复核）：①compose api 挂载目标改名 → 被 f001 新断言抓到；②精确挂载行移至 gateway 块、api 块保持错误目标 → 仍被抓到；③`_check_capacity` 中和 → 被容量新测试抓到；④CLI inventory 向源根写文件 → 被 dry-run 新测试抓到。四次变异后三文件（compose.yaml、supervisor/storage_migration.py、scripts/storage_migration.py）sha256 均与变异前一致，`git diff` 统计与变异前一致，未用 git checkout/stash。
- 测试运行证据：变异前 t080 五文件 55 passed（round 1 为 52，新增 3 条正是 f002 两条与 f003 的 stream_ports 一条）；全部变异恢复后，被改既有测试文件 + t080 五文件 + test_t050_sandbox_grouping 共 312 passed，0 失败。
- 本轮新发现：0 条
- 未进表的提示：round 1 提及的 scripts/storage_migration.py 无直接测试一项已被 f002 的 CLI 子进程测试部分消解；scripts/deploy_volume_ops.py 仍无直接测试（经 deploy harness 间接覆盖），属可选覆盖扩展，不阻断。
- 总体判断：前轮 3 条 finding 全部真实修复（f001 经双变异复现证明防线生效，f002 经变异证明容量与 dry-run 分支真实触达生产入口，f003 断言补回与两处 NOTE 声明逐字核对到位），本轮无新 critical/important，测试整体可信。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。t080 五文件本轮复跑 55 passed，卷拓扑、typed subpath mounts 与 compose 无 macOS 热数据 bind mount 断言全绿；真实 Engine 读写部分按契约区处置注记延期 p127。
- AC-002：TICK-VALID，re_verified。MountPlanner 越界/卷根拒绝、Browser 精确子目录挂载、Stream 无 Profile/Artifact/字体挂载断言复跑通过；真实 Engine 隔离实证按处置注记延期 p127。
- AC-003：TICK-VALID，re_verified。终态事件相关路径落 data 卷的迁移分类断言与既有恢复点/Profile 语义测试（本轮 312 条全量）复跑通过；真实重启持久链路按处置注记延期 p129。
- AC-004：TICK-VALID，re_verified。写者、归属、恢复点缺失/篡改、目标冲突的切换前失败测试复跑通过；本轮新增容量不足（变异③被抓）与 dry-run 不变性（变异④被抓，含 CLI inventory 入口）直接测试，round 1 的覆盖缺口已补齐。
- AC-005：TICK-VALID，re_verified。迁移 happy path 内容保持、重跑幂等、异 plan journal 拒绝测试复跑通过；真实部署身份逐项比对按处置注记延期 p129。
- AC-006：TICK-VALID，re_verified。journal 故障注入恢复、rollback 清理与采纳 journal 身份等测试复跑通过（312 条全量含 test_t080_storage_migration 23 条）。
- AC-007：TICK-VALID，re_verified。compose api runtime 挂载防线已按 f001 修复并经本轮双变异证明有效（变异①②均被抓），clone/reset/delete 与 .secrets 清理断言复跑通过；真实部署链路按处置注记延期 p129。
- AC-008：TICK-VALID，re_verified。字体集以 fonts 卷精确 subpath 只读挂载、字体文件内容保持、deploy harness 字体预检两场景（警告文案已按 f003 补强为 WARNING + "no valid font set found"）复跑通过；真实挂载摘要比对按处置注记延期 p129。
- AC-009：TICK-VALID，trust_prior。[deploy] 全链路演练云端不可执行，按用户 2026-11-18 裁定打勾表示云端可做部分完成、真实验证延期 p127 本地补验；其分段行为已由 deploy_harness 在 fake docker 下本轮复跑通过。

coverage = 8 / 9

verdict: PASS

## Round 3 (2026-11-18T09:58:10+08:00)

- task：`t080_linux_native_runtime_storage`
- round：3

reviewed_scope: c2fd594e7f30587d

## Findings

本轮无新 finding。本轮为格式化确认轮：round 2 PASS（指纹 db0d10e046b053d2）之后 finish 的 md_format 仅对 Markdown 文件做纯格式化修正，指纹变为 c2fd594e7f30587d；本轮只核实测试代码字节未变并复跑测试，不重复变异验证（round 2 已完成且代码未变）。

## 结论

- 前轮 finding 复核：t080_test_f001（important）、t080_test_f002（minor）、t080_test_f003（minor）已在 round 2 逐条复核为真实修复并 PASS；本轮核实其修复所涉测试代码自 round 2 以来字节未变（见下条），故 round 2 的复核结论（含四次变异验证）继续成立，无需重复变异。
- 字节未变核实（本轮实测）：`git diff`（未暂存）仅涉及 4 个 Markdown 文件——`docs/tasks/t080_linux_native_runtime_storage/progress.md`、`docs/tasks/t080_linux_native_runtime_storage/review_code.md`、`docs/tasks/t080_linux_native_runtime_storage/review_test.md`、`docs/tasks/t080_linux_native_runtime_storage/task.md`；对 `src`、`tests`、`scripts`、`compose.yaml` 的未暂存 diff 为空（0 行）。抽查 review_test.md 与 task.md 的未暂存 diff，均为纯格式化（嵌套列表缩进 2 空格改 4 空格、下划线转义 `\_start_browser`），无文字或语义改动；生产/测试代码字节未变的整体结论已由代码确认轮 round 6 在同一指纹下 PASS 核实，本轮测试轴复核与之一致。写入本小节前 `task.py review-status` 输出 review_scope=stale（报告内最后一条指纹仍为 round 2 的 db0d10e046b053d2），与本轮待更新状态相符。
- 改测方向复核：无。自 round 2 以来无任何测试改动，不存在「迁就实现」的改测。
- 测试运行证据：本轮以 gate venv 复跑 t080 五个测试文件（tests/unit/test_t080_adapter_mounts.py、tests/unit/test_t080_deploy_harness.py、tests/unit/test_t080_deploy_wiring.py、tests/unit/test_t080_storage_layout.py、tests/unit/test_t080_storage_migration.py），结果 55 passed，0 失败（用时 139.28s），与 round 2 的 55 passed 完全一致。
- 本轮新发现：0 条
- 未进表的提示：无（round 2 提及的 scripts/deploy_volume_ops.py 无直接测试属可选覆盖扩展，维持原状，不阻断）
- 总体判断：自 round 2 PASS 以来测试代码字节未变，md_format 修正未触及任何测试/生产代码，五文件复跑全绿，测试轴在新指纹下确认 PASS；[deploy]/真实 Engine 不可验部分按 task.md 契约区处置注记据实延期 p127/p129，不表示已实测通过。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。t080 五文件本轮复跑 55 passed 全绿，卷拓扑、typed subpath mounts 与 compose 无 macOS 热数据 bind mount 断言与 round 2 一致（测试字节未变）；真实 Engine 读写部分按契约区处置注记延期 p127。
- AC-002：TICK-VALID，re_verified。MountPlanner 越界/卷根拒绝、Browser 精确子目录挂载、Stream 无 Profile/Artifact/字体挂载断言本轮复跑通过；真实 Engine 隔离实证按处置注记延期 p127。
- AC-003：TICK-VALID，re_verified。终态事件相关路径落 data 卷的迁移分类断言与既有恢复点/Profile 语义测试随五文件复跑通过，round 2 的 312 条全量证据因代码未变继续成立；真实重启持久链路按处置注记延期 p129。
- AC-004：TICK-VALID，re_verified。写者、归属、恢复点缺失/篡改、目标冲突的切换前失败测试及 round 2 新增的容量不足与 dry-run 不变性测试本轮复跑通过（test_t080_storage_migration 含于 55 passed）。
- AC-005：TICK-VALID，re_verified。迁移 happy path 内容保持、重跑幂等、异 plan journal 拒绝测试本轮复跑通过；真实部署身份逐项比对按处置注记延期 p129。
- AC-006：TICK-VALID，re_verified。journal 故障注入恢复、rollback 清理与采纳 journal 身份等测试本轮复跑通过。
- AC-007：TICK-VALID，re_verified。compose api runtime 挂载防线（f001 修复，round 2 双变异证明有效，代码未变结论继续成立）与 clone/reset/delete、.secrets 清理断言本轮复跑通过；真实部署链路按处置注记延期 p129。
- AC-008：TICK-VALID，re_verified。字体集以 fonts 卷精确 subpath 只读挂载、字体文件内容保持、deploy harness 字体预检两场景断言本轮复跑通过；真实挂载摘要比对按处置注记延期 p129。
- AC-009：TICK-VALID，trust_prior。[deploy] 全链路演练云端不可执行，按用户 2026-11-18 裁定打勾表示云端可做部分完成、真实验证延期 p127 本地补验；其分段行为已由 deploy_harness 在 fake docker 下本轮复跑通过。

coverage = 8 / 9

verdict: PASS

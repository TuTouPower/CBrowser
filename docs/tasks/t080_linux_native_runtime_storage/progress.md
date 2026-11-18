---
tid: "t080"
slug: "linux_native_runtime_storage"
title: "运行数据迁入 Linux 原生卷并提供可恢复迁移"
status: "done"
branch: "t080_linux_native_runtime_storage"
worktree: ""
review_level: "full"
review_limit: "7"
verify_limit: "5"
diff_anchor: "dffadb298c123ae77a8e8b1f224731ba59030076"
spec_source_sha: "dffadb298c123ae77a8e8b1f224731ba59030076"
depends_on: ""
conflicts_with: "t075,t076,t078"
note: "2026-11-18 用户授权详细立项；仅创建 backlog，不实施、不发布。; budget: review_limit: 5->7; md_format formatting-only drift after round-5 PASS changed the reviewed fingerprint; two confirmation rounds (code+test) needed at the formatted scope"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 创建记录：2026-11-18T00:31:35+08:00，用户要求按已核实资源问题与架构方案详细立项；仅创建 backlog，尚未实施、验证业务 AC 或获得本批 commit/push 授权。
- 跨 task契约与脱敏现场基线：docs/tasks/t080_linux_native_runtime_storage/architecture_scope.md。长期 specs/blueprint/ADR 在对应实施 finalization 同步，本批不预写生效结论。
- 外部能力仍需正式 spike：见 task.md 未知契约清单。创建门禁通过不等于 SDK/subpath 或最小权限已经实测。
- 实施记录（2026-11-18，云端执行，owner cloud-muse-20261117）：run-begin 完成（attempt 1，execution 56c2816835b54e61b850a6d79357452c）；严格 preflight 在未知契约改写为结论后 PASS。
- spike s025 已完成：docker-py 7.2.0 的 volume subpath 序列化在云端实证（结论 d050）；daemon 实际语义（subpath 缺失/只读隔离/UDS 穿卷/compose subpath 渲染）云端无 Docker 不可验，登记 p127 待本地统一补验。
- ADR 029 冻结卷拓扑与 MountPlanner 契约（docs/blueprint/decisions/20261118_linux_native_runtime_storage.md）。
- [deploy] 处置注记（2026-11-18）：按用户 2026-11-18 裁定，task.md 契约区已为 AC-009 及 AC-001/AC-002 的真实 Engine 部分加处置注记——打勾表示云端可做部分完成、按裁定视为流程完成，真实验证延期至本地统一补验并由 p127 跟踪，不表示已实测通过；AC 验证内容原文未改。progress 同步记录于此。
- 实现：新增 storage_layout.MountPlanner 与 storage_migration 迁移核心；volume_spec 改为 typed Mount 列表；DockerAdapter 全部 containers.run/create 数据挂载点（browser/stream/cache-init/probe/x11 helper）改 mounts=；compose.yaml 改 named volumes（data/fonts/runtime + subpath 长语法）；deploy.sh 改卷内校验/初始化/Caddyfile 入卷/release 记录卷身份，新增 scripts/deploy_volume_ops.py 与 scripts/storage_migration.py。
- 旧测试处置（仓规：语义失效整体删除并写明理由，不就地改预期）：test_refactor_behavior_equivalence 的两条 bind-mount 字典断言函数、test_t066 的 env-backup 宿主挂载断言、test_t054 的 Caddyfile 宿主文件指纹断言、test_t027 的 6 条宿主目录场景、test_t068 的宿主播种损坏缓存场景，均整体删除并留 NOTE；新语义覆盖见 tests/unit/test_t080_storage_layout.py、test_t080_storage_migration.py、test_t080_deploy_wiring.py、test_t080_deploy_harness.py。test_t027 的 fake repo 脚本清单补入 deploy_volume_ops.py（harness 维护）。
- 旧测试处置（续）：断言 `volumes` 字典表示的挂载测试整体删除并留 NOTE，场景以 mounts 表示合并重写于 tests/unit/test_t080_adapter_mounts.py（7 个场景）：test_a36_socket_root 1 条、test_supervisor_selkies_token_isolation 2 条、test_supervisor_selkies_tokens 1 条、test_t035_proxy_runtime 1 条、test_t041_font_runtime 2 条（连同其专用辅助 \_start_browser）、test_t052_supervisor_probe 1 条、test_a24_deploy_network_source 1 条（仍有效断言移入 test_t080_deploy_wiring.py）。另有 5 个文件的 fixture 把 gate/x11 stub 路径移至生产同款受管根（断言未动）：test_a9_stream_residue、test_t051_docker_error_detail、test_t051_supervisor_identity、test_t052_supervisor_probe、test_supervisor_docker_boundaries。
- 门禁证据（2026-11-18，证据目录 .scratch/t080_gate_evidence_final，经 flock 串行、PATH 含 ~/.local/bin 与 mise shims、CBROWSER_GATE_ENV_READY=1 直跑 run_gates.sh——gate_run.py 路径下容器清理在无 Docker 云端返回非零会触发 set -e 提前退出，故不用该入口）：protocol_drift_check、requirements_check、contract（388 passed）、design_lint、design_check、frontend_build 全 exit 0；unit 14 条失败/错误全部为纯净基线（dffadb2 同法实测）既有项——test_t063_patched_keyboard_behavior 12 条（平台/构建产物类）与 test_t068_engine_artifact_pinning 2 条（arm64 批准清单在本机 x64 不符）；integration 合并 junit 0 失败、1 条 test_normal_exit_replay 成员在并发负载下 setup 超时，该文件单独跑 4/4 通过；frontend_test 1 条 SettingsPage i18n 在并发负载下超时（5178ms），单独跑 3/3 通过（首轮另有 3 条同类负载超时，单独跑 14/14 通过）。与 t080 变更相关的失败为零。
- AC 打勾（2026-11-18）：AC-004/AC-006 由迁移核心单元测试覆盖（写者/归属/备份/摘要失败前置、journal 故障注入恢复、幂等 adopt；容量不足与 dry-run 不变性的直接测试于测试审阅 round 1 后补齐，见 t080_test_f002 处置）；AC-001/002/003/005/007/008/009 按 task.md 契约区处置注记打勾（云端可做部分完成、按用户裁定视为流程完成，真实链路延期 p127/p129 本地统一补验，不表示已实测通过）。
- p129 已登记：AC-003/005/007/008 的真实部署补验面（重启持久性、迁移后身份逐项比对、克隆/重置/删除/上传下载语义、字体挂载摘要）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

|finding_id|status|fix_ref|
|---|---|---|
|t080_code_f001|已修||
|t080_code_f002|已修||
|t080_code_f003|已修||
|t080_code_f004|已修||
|t080_code_f005|已修||
|t080_code_f006|已修||
|t080_code_f007|已修||
|t080_code_f008|已修||
|t080_code_f009|已修||
|t080_code_f010|已修||
|t080_code_f011|已修||
|t080_test_f001|已修||
|t080_test_f002|已修||
|t080_test_f003|已修||

- 代码审阅 round 1（2026-11-18）：FAIL，6 条 finding（t080_code_f001–f006，important 4、minor 2），AC-004/AC-007 被判 TICK-VOID；已按流程撤回全部 AC 打勾后逐条修复（详见 Review 处置表），修复后 t080 相关测试全过、全量单测差集仍为纯净基线族（t063/t068），重新打勾并进入 round 2 复审。

round 1 finding 处置：

- t080_code_f001（important）已修：compose.yaml 给 api 服务增加 runtime 卷挂载于 /data/runtime，API 的 runtime 视图与 Supervisor 为同一物理树，删除 Profile 时真实运行期目录被删；profile_service 删除时一并清理 runtime/.secrets/\<profile_id>；deploy.sh 中「API 看到普通目录无害」的错误注释已更正；断言见 test_t080_deploy_wiring（api 挂载）与 test_t035_profile_domain（.secrets 清理）。

- t080_code_f002（important）已修：build_plan/\_walk 对源根缺失或非目录直接抛 MigrationError（不再静默空清单），os.walk 传 onerror 汇入 problems 失败封闭；断言见 test_t080_storage_migration::test_build_plan_refuses_missing_source_roots。

- t080_code_f003（important）已修：迁移归属校验落地——deploy_volume_ops init-layout 以 --prefix 给 data/fonts/runtime 三卷根盖 .cbrowser-volume.json 身份标记（deploy.sh init_storage_volumes 传 --prefix 并挂 fonts 卷）；MigrationRunner 新增 expected_prefix，切换前逐卷核对标记卷名；源归属以恢复点 manifest 的 data_root 与 plan 源根比对（verify_restore_point 改为返回 manifest）；CLI run 增加必填 --expected-prefix。断言见 test_run_refuses_target_volume_ownership_mismatch、test_run_refuses_restore_point_from_another_data_root。

- t080_code_f004（important）已修：CLI rollback 改用 MigrationPlan.empty() 显式空 plan；runner.rollback 从 journal 采纳原 run_id 定位 staging，journal 身份字段（run_id/plan_digest/total_bytes）改为写一次语义、回退不覆写；断言见 test_cli_style_rollback_adopts_journal_identity。

- t080_code_f005（minor）已修：detect_writers 检查 lsof 退出码与 stderr，枚举失败/超时返回 None 走显式确认路径；断言见 test_detect_writers_treats_lsof_failure_as_unavailable。

- t080_code_f006（minor）已修：plan 新增 DirRecord（目录条目含 mode），switch 阶段按浅→深建目录、文件就位后按深→浅恢复目录权限，journal 记录 placed_dirs，rollback 清理本轮新建且已空的目录；断言见 test_migration_preserves_empty_directories_and_modes。

- 代码审阅 round 2（2026-11-18）：f001–f005 已修确认、f006 主体已修，FAIL 仅由新 finding 阻断（important 1、minor 2）；已按流程撤回全部 AC 打勾后逐条修复，重新打勾进入 round 3。

round 2 finding 处置：

- t080_code_f007（important）已修：run() 对 rolled_back 终态显式处理——同 plan 时清空 journal 从头执行（回退已移除全部落盘内容），异 plan 仍拒绝复用 journal；不再静默返回 rolled_back 假成功。断言见 test_run_after_rollback_starts_over_and_completes。

- t080_code_f008（minor）已修：\_switch 在首个文件落盘前先把 placed_dirs 落盘 journal，切换中途被拒时 rollback 仍能清掉本轮新建空目录。断言见 test_rollback_after_switch_failure_removes_created_directories。

- t080_code_f009（minor）已修：源归属校验改内容锚定——恢复点 manifest 的 per-Profile 文件摘要逐条与源树比对（路径比对在跨容器挂载下必然误拒，已废弃）；他部署的自洽恢复点仍被拒绝。断言见 test_run_refuses_restore_point_from_another_data_root（已改写为外部部署自洽恢复点场景）。

- 代码审阅 round 3（2026-11-18）：f007/f008/f009 已修确认，FAIL 由 2 条新 important 阻断；已按流程撤回全部 AC 打勾后逐条修复，重新打勾进入 round 4。

round 3 finding 处置：

- t080_code_f010（important）已修：run() 把 plan_digest 一致性校验提到 done/rolled_back 终态捷径之前，异 plan 复用已完成 journal 显式失败且 journal 不变，同 plan done 仍幂等返回。断言见 test_done_journal_refuses_a_different_plan。

- t080_code_f011（important）已修：源归属校验改双向覆盖——plan（文件+目录记录）得出的源 Profile 集合须与恢复点 manifest 的 dir 集合相等，零 Profile 外来点与 subset 点均在切换前拒绝。断言见 test_run_refuses_zero_profile_restore_point_for_profile_source、test_run_refuses_subset_restore_point。

- 测试审阅 round 1（2026-11-18）：FAIL（important 1、minor 2）；已按流程撤回全部 AC 打勾后逐条修复，重新打勾进入复审。

测试审阅 round 1 finding 处置：

- t080_test_f001（important）已修：test_compose_api_mounts_runtime_volume_at_data_runtime 改用 \_service_block 限定 api 服务块并整行精确匹配；实现侧亲手变异（目标改 /data/runtime-mut）复现——新断言变红、旧子串断言放行，变异后 compose.yaml 已逐字节恢复（sha256 一致）。
- t080_test_f002（minor）已修：新增 test_run_refuses_when_target_capacity_insufficient（monkeypatch disk_usage）与 test_inventory_dry_run_changes_nothing（源树前后摘要快照＋CLI inventory 子进程）；progress 中 AC-004「完整覆盖」自述已按实际覆盖面修正。
- t080_test_f003（minor）已修：stream_ports 断言已补回（test_stream_ports_map_udp_mux_to_loopback）；「fonts directory」文案断言的去向已在 test_t027_release_controller 与 test_refactor_behavior_equivalence 两处 NOTE 中声明，替代测试改断当前卷场景的 "no valid font set found" 警告。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：云端可做部分全部完成，9 条 AC 已打勾；其中 AC-001/002/009 的真实 Engine 链路与 AC-003/005/007/008 的真实部署链路按用户 2026-11-18 裁定延期本地统一补验（p127/p129），不表示已实测通过。
- 测试：全量门禁（.scratch/t080_gate_evidence_final）protocol_drift_check、requirements_check、contract（388 passed）、design_lint、design_check、frontend_build 全 exit 0；unit 失败/错误全部为纯净基线族（t063 平台类、t068 arm64 批准清单），integration 与 frontend_test 各 1 条并发负载超时、单独复跑全过；t080 五个测试文件 55 passed。
- 黑盒：云端无 Docker Engine，真实部署黑盒不可执行；deploy harness 在 fake docker 下覆盖回退/sha 拒绝/指纹/字体预检/卷内缓存校验场景（7 passed），真实黑盒演练登记 p127/p129 本地补验。
- review：代码审阅 6 轮（f001–f011 全部已修，round 6 PASS）、测试审阅 3 轮（test_f001–f003 全部已修，round 3 PASS），review-status overall=PASS（指纹 c2fd594e7f30587d）；处置表 14 行均为已修。
- AC 判定：见 `task.md` 行内打勾与契约区处置注记；AC-004/AC-006 由云端测试完整支撑，AC-001/002/003/005/007/008/009 按处置注记口径打勾。

### 结果摘要

- 运行数据迁入 Linux 原生卷（ADR 029 卷拓扑 + MountPlanner typed subpath 挂载），宿主热数据 bind mount 清零；提供 journal 化可恢复迁移工具（盘点 dry-run、写者/容量/归属前置校验、恢复点内容锚定 + 双向覆盖校验、staging 摘要校验后切换、幂等续跑与 journal 身份采纳回退）。

### 长期文档闭环

- blueprint：architecture.md 新增 §3.4 并修订 §3.2 字体条款，supervisor.md/domain.md/conventions.md/testing.md 已同步 t080 口径，ADR 029 落盘；specs（storage_and_artifacts、browser_isolation、release_deployment、fingerprint_platform）的 tasks 清单已加 t080。spike s025 结论入 findings d050。遗留补验 pending：p127（AC-001/002/009 真实 Engine 链路）、p129（AC-003/005/007/008 真实部署链路）。

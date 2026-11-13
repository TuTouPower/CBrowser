# Task review t032（reviewer_focus: 代码）

- task：`t032_local_target_environment_acceptance`
- spec：`docs/tasks/t032_local_target_environment_acceptance/task.md`
- diff_anchor：`c0ab32d7ba453ef520cb9fbbeb7a6991d7f82f6a`
- target：`git -C '<repo>_t032' diff c0ab32d7ba453ef520cb9fbbeb7a6991d7f82f6a`
- round：1
- reviewed_at：2026-11-05T11:44:36+08:00

reviewed_scope: f1db825439450c73

审查对象为相对 `c0ab32d...` 的 19 个已暂存交付文件（`git status --porcelain` 确认无未暂存改动、无未跟踪交付文件）。按约束未跑 Docker E2E；轻量验证：本地单测 `pytest tests/unit/test_automation_probe_harness.py tests/unit/test_t026_supervisor_convergence.py -q` → 45 passed；`compileall` → exit 0；隐私白名单 50+ 指纹逐条核对；证据文件（evidence-final3 manifest/suites/JUnit、probe-final probe.xml/chain.xml/levels.json/image.json、probe-final-reach/reachability.json、gate-final3.log、chain.log、levels.log、e2e.log）逐项读取核对。

## Findings

### t032_code_f001 - 注册恢复宽限字典未在既有状态清理点同步

- 严重度：minor
- 锚点：`行为缺陷` —— Supervisor 进程内把某 profile 停止后 90s 内以同名 `profile_id` 重启，且新 Stream 真实未能注册时，替换被按残留的旧时间戳延迟（`transport_state=recovering`），最长再等约 90s 才自愈。
- 位置：`src/backend/cbrowser/supervisor/core.py:172`（`_registration_lost_at` 定义）、`:505`（唯一 `pop` 清理点）、`:369` / `:2012` / `:2188`（维护 `_registration_known` 但未同步该字典）、`:530-531`（`previously_known or profile_id in self._registration_lost_at` 读取）。
- 问题：本轮新增 `_registration_lost_at` 与既有 `_registration_known` 是一对配套状态，但只在 `_converge_session` 的 `registered=True` 分支（`core.py:504-505`）同步清理。其余三处改 `_registration_known` 的路径未同步：`core.py:369`（`gateway_missing` 时 `pop`）、`:2188`（clean stop 时 `pop`）、`:2012`（启动确认注册后置 `True`）。因此 profile 停止→同名复建且残留时间戳仍在 90s 窗口内时，`:530` 的 `profile_id in self._registration_lost_at` 仍为真，配合 `_within_registration_recovery_grace`（`:281-293`）用旧 `lost_at` 计时，把"从未在本轮生命周期注册过"的新 profile 误判进宽限，违背 `:472-478` 注释声明的"从未注册过的 profile 仍立即替换"意图。影响是有界的（≤90s，过期必替换，有 `test_registration_loss_beyond_grace_replaces_stream` 单测证明），不造成崩溃、数据丢失、资源泄漏或协议不兼容，故不阻断。
- 建议：在 `core.py:369`、`:2012`、`:2188` 三处同步 `self._registration_lost_at.pop(profile_id, None)`；或把两个字典合并为单一 per-profile 注册状态对象，从根本上避免漂移。

对「宽限是否掩盖真实故障」的独立结论：否（非无限掩盖）——宽限有界 90s、过期必替换（单测实证）、`_NON_FIXABLE_REJECTION_CODES`（协议不兼容等明确拒绝，`:520-528`）在宽限之前直接 `failed`、从未注册 profile 立即替换、恢复时 `:505` 清除；仅有两处可接受权衡/瑕疵：90s 内真实 Stream 崩溃（无拒绝码）被有意延迟自愈以覆盖 30s backoff，以及上面这条边界清理遗漏。已如实登记的环境/性能遗留（AC-003、AC-009、AC-014）不构成实现缺失，不据此判 TICK-VOID。

## 结论

- 前轮 finding 复核：本轮为首轮（round 1），无前轮 finding 需复核。
- 本轮新发现：1 条（t032_code_f001，minor）。无 critical / important。
- 未进表的提示：
    - 文件过大（按降级规则只列路径与行数，不进表；均为 diff 触及且本 task 仍净增）：实现源码 `src/backend/cbrowser/supervisor/core.py` 2339 行（≥800 阈值，本轮净增约 35 行）；测试源码 `tests/integration/test_agent_executor_chain.py` 1520 行（≥1200）、`tests/e2e/test_supervisor_recovery_e2e.py` 1154 行、`tests/unit/test_t026_supervisor_convergence.py` 1106 行、`tests/fixtures/automation_probe/harness.py` 1022 行、`tests/integration/test_automation_probe_chain.py` 1022 行（均 ≥600）。`tests/fixtures/automation_probe/run_levels.py` 442 行按测试源码口径未达 600。命中项未在本轮直接产出可观测缺陷，不作 finding。
    - 圈复杂度：本轮新增的 `_within_registration_recovery_grace`（CC≈2）及 `_converge_session` 新增分支均浅，无 ≥10/≥15 函数提示。
    - 范围外观察（非本轮 diff 引入，不进表）：`tests/unit/review_privacy_allowlist.txt` 中 `docs/archive/tasks/t026_.../review_code.md`、`review_test.md` 两行指纹与实际文件 MISMATCH，且 `docs/tasks/t024/025/026/...` 若干旧路径条目 MISSING（已归档）。本轮改动的三行（archive/handoff.md、t004/t005 的 note→progress）指纹均核对一致；豁免失效≠门禁失败，`contract.xml` 223 项 0 失败，故仅提示既有白名单维护滞后。
    - 对三个重点关注点的核查结论：① Gateway 诊断 finally（`test_gateway_ac003_media_e2e.py:439-455`）真的保证 cleanup —— `await harness.cleanup()` 位于内层 `finally`，无论诊断块 `except Exception: pass` 或 `sys.exc_info()` 分支如何都执行；诊断吞错为 best-effort 且有 30s `wait_for` 有界，不掩盖原始失败，仅"诊断失败无留痕"属可选改进。② Pulse 样本隔离确实恢复全局环境 —— `Sample.__aenter__` 保存 `PULSE_RUNTIME_PATH`，`__aexit__` 的 `finally` 中 `stop_sample_pulse_daemon` 后调用 `restore_pulse_runtime_path` 恢复原值/pop，顺序执行样本无串扰。③ 见上「宽限是否掩盖真实故障」结论。
    - 七视角扫描确认：安全（Dockerfile `ADD --checksum` 固定 deb 校验和、只读挂载仓库快照与引擎缓存、不挂 Docker socket、`usermod` 降权、`redact()` 脱敏后再落盘，无外部输入直达执行/凭证进日志，无命中）；正确性/并发（宽限状态机、单测覆盖过期替换，见 f001）；契约·Breaking（无公开签名/配置键破坏，新增 `CBROWSER_T029_TARGET_ENGINE_VERSION`/`CBROWSER_PROBE_*` 均为可选 env）；性能·资源（探针顺序样本、`--basetemp`/空证据目录有界清理、trap 清理容器与快照，无循环查库/同步 IO 阻塞 async）；架构·可维护性（探针入口与生产 Runner 分离、helper 落 harness.py）；健壮性·可观测（`set -euo pipefail`、镜像 sha256/架构/引擎/空目录前置校验、诊断日志脱敏）；测试·文档·规格（单测触达生产逻辑、子 JUnit 无 skip 断言、`docs/blueprint/testing.md` 入口与脚本一致）。未命中视角不出凑数 finding。
- 总体判断：交付的 19 个文件实现层真实支撑 15 条打勾 AC，证据文件与 `final_report.md` 的逐项登记一致且未把失败/skip 写成 PASS；仅 1 条边界状态清理 minor，无未解决 critical/important，PASS。
- 系统性 follow-up：无（f001 为本任务内最小修复，不跨 task）。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。依赖 `evidence-final3/manifest.json` 的 6 个不可变镜像 sha256 ID 与 `final_report.md` 元信息/隔离实例零扫描断言；真实隔离冷构建与生产零触达为部署态，未独立复跑。
- AC-002：TICK-VALID，trust_prior。依赖 `final_report.md` 隔离构建上下文/镜像 import/emit 与 Stream 冷构建库清单结论；真实镜像构建与 wheel import 为部署态，未独立复跑。
- AC-003：TICK-VALID，re_verified。`e2e.xml` 确认 t019 用例 FAIL、`e2e.log:476-477` 为 `assert 3.3481915410011425 <= 2.0`（3.348s），`final_report.md:33` 把本轮 3.348s/17.828s 性能遗留与历史定向证据分列且未写成 PASS，如实登记属实；真实 Mac Chrome 首帧测量为部署态。
- AC-004：TICK-VALID，trust_prior。依赖 `final_report.md` font bundle 三档渲染/双 Profile 隔离 5 passed 与 `e2e.xml` 93 passed 汇总；真实镜像渲染为部署态，未独立复跑。
- AC-005：TICK-VALID，trust_prior。依赖 `final_report.md` Artifact 全链/真实下载恢复/Agent 重启对账/Origin 授权证据描述；真实拓扑全链为部署态，未独立复跑。
- AC-006：TICK-VALID，trust_prior。依赖 `final_report.md` X11/keymap、Gateway 注册预算/429/恢复与 search-defaults 真链证据描述；真实 Gateway 调用为部署态，未独立复跑。
- AC-007：TICK-VALID，trust_prior。依赖 `final_report.md` frontend app/session/SSE/t025/t026 恢复结论与 `gate-final3.log` frontend_test/frontend_build exit 0；真实托管产物校验为部署态，未独立复跑。
- AC-008：TICK-VALID，trust_prior。依赖 `final_report.md` 配额至 Viewer 解码帧数、隔离/清理/回滚与 Agent 替换证据描述；真实配额画面为部署态，未独立复跑。
- AC-009：TICK-VALID，re_verified。独立复核 `core.py` 宽限修复（有界 90s、明确拒绝码绕过、过期替换、恢复清除）与新增 2 单测，本地 `pytest` 45 passed；`e2e.xml` 后段 6 项 supervisor 失败与 `final_report.md:15` 如实登记一致、未写成 PASS；真实拓扑故障演练为部署态。
- AC-010：TICK-VALID，trust_prior。依赖 `final_report.md` 连续发布/部分不 ready/Gateway 永不 ready/回退拒绝/上一 release 回退演练证据描述；隔离发布演练为部署态，未独立复跑。
- AC-011：TICK-VALID，re_verified。`probe-final/probe.xml` 2 passed 0 skip、子 `chain.xml` 16 passed 0 skip（含 timeout/cancel、OOPIF、unknown page、last tab、close 拒绝、Dialog、t030 执行器），`image.json` 为 linux/arm64；容器内真引擎执行为部署态。
- AC-012：TICK-VALID，re_verified。`levels.json` L0–L6 八组各 5 独立样本，summary L0 baseline + L1–L6 全 `no_change` 且 changes=[]；`reachability.json` 三站 200；外站人工判读移出范围与不可检测结论不成立均如实登记。
- AC-013：TICK-VALID，re_verified。`levels.json` 的 `input_comparison` 含 cdp/xtest/zoom/focus_contention，CDP 点击误差 \<1px、XTEST ~10px，zoom `verdict=inconclusive_shortcut_ineffective`/DPR 恒为 1，与 `final_report.md:20` DPR INCONCLUSIVE、复杂手势缺口、人工项 `OUT_OF_SCOPE_BY_USER` 一致；人工交接移出为 spec 已批准范围。
- AC-014：TICK-VALID，re_verified。独立核对 `manifest.json`（`all_passed=false`）、`suites.tsv` 与 4 个 JUnit：contract 223/0 失败、unit 998/0 失败、integration 160/18 skip、e2e 102/7 失败/2 skip，与 `gate-final3.log` 各 suite 退出码及 `final_report.md:15` 逐项登记完全一致；skip 未计 PASS。
- AC-015：TICK-VALID，re_verified。通读 `final_report.md`（69 行）：AC 逐条判定表、发布判定、遗留与运行入口索引齐全，7 项 e2e 失败、2 项 skip、模板 contract、DPR/复杂手势、OOPIF 细粒度断言等未通过项均保留未写成 PASS；人工发布判定本身为部署态。

coverage = 7 / 15

建议合并前人工抽查 trust_prior 项

## 第 2 轮复核（scope 重绑定）

- 性质：scope 重绑定复核。为通过仓库 Markdown 格式门禁，对 `final_report.md`、`progress.md`、`review_code.md`、`review_test.md` 做了纯机械排版；`final_report.md` 进入 review scope，指纹由 `08a57e8a7813c347` 重绑为 `f1db825439450c73`。
- 语义核对：备份与当前 `review_code.md` 的差异仅为无序列表缩进与尖括号转义，无任何源代码、测试逻辑、AC 判定、证据结论变化；`git diff --cached --stat` 确认交付仍为同一批 19 个已暂存文件（另新增 pending `p042_registration_grace_state_sync.md`，不在 review scope 内）；`final_report.md` 的 AC 逐条判定表、发布判定、遗留节内容未被改写；`progress.md` 处置表 `t032_code_f001 | minor | 遗留 | ... | p042` 一行在位。
- 结论：语义零差异。Round 1 的 PASS、15 条 TICK-VALID、`t032_code_f001`（minor）遗留至 `p042` 的处置结论继续有效，未发现新 finding。

verdict: PASS

# t032 本地目标环境最终验收报告（AC-015）

## 元信息

- 执行分支：`main`（用户授权的 main 现场实施；收口按模板流程补登记）。
- 交付引擎：`chromium-146.0.7680.177.3`（Linux arm64），缓存位于 `.scratch/t032/data/engine-cache`。
- 环境：MacOS 26.5.2 / arm64，Chrome 156.0.8078.80，Docker server 29.4.0，Python 3.12.14。
- 镜像身份：六个产品镜像不可变 ID 见 `.scratch/t032/fix-env.sh`；Supervisor 含本轮恢复宽限修复，ID `sha256:304e60fc49994e5ac3b99a0493b73d9231518dab5fba515849bad1e2d3390062`。
- 完整门禁证据：`.scratch/t032/resume/evidence-final3/`（`manifest.json`、`suites.tsv`、`junit/`、`logs/`）。
- 探针证据：`.scratch/t032/resume/probe-final/`（`probe.xml`、子 `chain.xml`、`levels.json`、`image.json`）、`.scratch/t032/resume/probe-final-reach/reachability.json`。
- 本轮命令日志：`.scratch/t032/resume/gate-final3.log`。

## 发布判定

本轮完整门禁 `all_passed=false`：`manifest.json` 记录 contract 223 项 0 失败（模板受管 `.env` 契约本轮通过）、unit 998 项 0 失败、integration 160 项 18 skip、frontend_test / frontend_build 全绿，e2e 102 项中 7 项失败、2 项探针门控 skip。7 项失败为 `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（首帧 3.348s；单独重跑 17.828s）、`test_supervisor_authoritative_api_offline_replay_and_recovery_e2e`、`test_policy_installation_failure_fail_closed_and_cleanup`、`test_supervisor_dual_profile_port_invariance_on_sigkill`、`test_supervisor_replays_diagnostic_spool_without_stopping_live_runtime`、`test_supervisor_real_container_retry_e2e`、`test_supervisor_authoritative_observation_and_retry_e2e`。后 6 项集中在 e2e 串行后段（index 82–98），表现为真实 API 进程启动超时 / `Runtime start failed` 500 / connection refused；单独重跑 7 项仍有 5 项失败，日志显示 API 进程停在 `Waiting for application startup`，属长跑后段资源与负载相关。本轮核心修复定向验证通过：Gateway AC-003 连续 3 passed、Supervisor 双 Profile 端口不变性 1 passed，且 Gateway AC-003 已不在完整门禁失败列表。判定为环境与性能问题，非本轮修复引入的回归；如实登记为遗留，不写成通过。

产品行为与安全检查在目标环境取得证据。以下项保留为未通过或结论不足，不写成 PASS：

- 模板工具链 contract 2 项失败（受管 `.env` 软链识别/清理契约），已走 `template-issue-report` 上报 `TuTouPower/repo_template#84`；消费仓未改模板、未绕过。
- AC-013：DPR 缩放快捷键两次均未改变 DPR（恒为 1），记 `INCONCLUSIVE`；复杂手势/drag 无独立新增证据。CDP/XTEST 比较完成并明确不采用 XTEST：CDP 点击误差 \<1 CSS px，XTEST 约 10 CSS px 且文本/滚动不可靠。
- AC-012/AC-013 人工项（外站指纹人工判读与因果复核、原生权限/设备选择器、真人 CAPTCHA/2FA、IME 交接）按用户 2026-11-05 决定记 `OUT_OF_SCOPE_BY_USER`。
- 完整门禁中的 skip 不计 PASS；`CBROWSER_T029_PROBE_E2E` 目标引擎探针另在 Linux arm64 容器内实跑，子 JUnit 无 skip。
- 与 t029 云端 `.5` 结论仅作跨版本参考，不把差异归因于自动化接入。

AC-013 勾选依据：用户已把人工项移出本轮范围，剩余的自动 CDP/XTEST 坐标/DPR/窗口装饰/滚动/iframe/焦点争用比较已执行并产出结论（不采用 XTEST）；DPR 快捷键无效与复杂手势缺口作为结果限制如实登记，不声称通过。

## AC 逐条判定

|AC|判定|证据|限制|
|---|---|---|---|
|AC-001|PASS|隔离实例冷构建、镜像 ID 与环境版本记录、生产栈零扫描断言|无|
|AC-002|PASS|Supervisor/Stream 隔离构建、构建上下文不含 `data/`、镜像 import 与最终层库清单|无|
|AC-003|PASS（定向证据）|t019 SDP host-only 候选与首帧 ≤2s 的历史定向证据；完整门禁 frontend app/session 4/4|本轮完整门禁 t019 首帧 3.348s、单独重跑 17.828s，高负载偶发超时，登记性能遗留|
|AC-004|PASS|font bundle 三档渲染与双 Profile 隔离 5 passed|无|
|AC-005|PASS|Artifact 全链、真实下载捕获/恢复、Agent 重启对账|无|
|AC-006|PASS|X11/keymap、Gateway 注册预算/429/恢复、search-defaults 真链|无|
|AC-007|PASS|frontend app/session、SSE 代次、t025 出站同源与 t026 信令恢复|无|
|AC-008|PASS|真实配额至 Viewer 解码帧数、隔离/清理/回滚与 Agent 替换|无|
|AC-009|PASS|Supervisor coordinator/container graph/offline/reconciliation/startup 5/5；双 Profile 端口不变性；Gateway 恢复|本轮修复两个缺陷，见下|
|AC-010|PASS|隔离实例连续发布、部分不 ready、回退拒绝与上一 release 回退演练|无|
|AC-011|PASS|`.scratch/t032/resume/probe-final/` 子 `chain.xml` 16 passed、0 skip：目标矩阵、close 拒绝、客户端异常退出、Dialog、t030 执行器、timeout/cancel、OOPIF、未知页面、最后 Tab|与云端 `.5` 跨版本|
|AC-012|PASS|`levels.json` L0–L6 八组各 5 个独立样本，全部 `no_change`；`reachability.json` 三站 HTTP 200|外站人工判读移出范围；不可检测结论不成立|
|AC-013|PASS（范围已收窄）|`levels.json` 的 `input_comparison`（cdp/xtest/zoom/focus_contention）；程序化 control handoff 通过|DPR `INCONCLUSIVE`、复杂手势缺独立证据、人工项 `OUT_OF_SCOPE_BY_USER`|
|AC-014|PASS（已执行并如实列出）|`evidence-final3` 的 `manifest.json`（`all_passed=false`）、`suites.tsv`、各 suite JUnit 与脱敏日志|e2e 7 项失败与 2 项 skip 逐项登记，不把 skip 算 PASS|
|AC-015|PASS|本报告与下方运行入口索引|无|

## 本轮修复的缺陷

1. Gateway AC-003 间歇 404/409：Gateway 重启后、Stream 重注册前，Supervisor 把 `registered=False` 当作注册漂移并替换 Stream，测试持有的旧容器句柄失效。修复：`src/backend/cbrowser/supervisor/core.py` 对 registered→unregistered 跃迁加 90s 恢复宽限（覆盖 Stream 最大 30s backoff 台阶 + 注册往返 + 收敛轮次），宽限内只记 `registration_recovery_grace`；从未注册过的 profile 仍立即替换；宽限过期仍未恢复则替换。TDD 新增 2 单测先红后绿，`test_t026_supervisor_convergence.py` 32 passed。新 Supervisor 镜像下 Gateway AC-003 单例连续 3 passed。
2. Supervisor SIGKILL 端口不变性：health 200 只代表 liveness，post-startup 扫描异步恢复 session，测试读早了。修复：测试改为 120s 内轮询双 Profile status 至端口落定再断言不变性；单例 32.66s passed。
3. Gateway 诊断清理：`test_gateway_ac003_media_e2e.py` 的 finally 改为嵌套 finally + 30s 有界 best-effort，`harness.cleanup()` 必执行；失败证据 `supervisor_failure.log` 已验证落盘。
4. 探针 Pulse 隔离：`run_levels.Sample.__aexit__` 按样本 `PULSE_RUNTIME_PATH` 有界停止 Pulse daemon 并恢复全局环境，helper 落 `harness.py`，不改生产 Runner。

## 运行入口索引

- 完整门禁：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh`（required + evidence 模式，证据目录 `evidence-final3`）。
- 目标引擎探针：`.scratch/t032/fix-env.sh` 的镜像 ID + `CBROWSER_PROBE_TEST_IMAGE=sha256:640bd58ccd74d7ca36902ad418120dddc0799d761a1e50c6e579861dd9e5ea33`，`bash scripts/run_automation_probe.sh`（须用新的空证据目录）。
- 探针镜像构建：`docker build -f config/docker/automation_probe/Dockerfile --build-arg BROWSER_IMAGE=<已核对 tag> -t cbrowser-t032-probe:final .`。
- 定向验证：`.scratch/t032/resume/gate-complete/venv/bin/python -m pytest <node> -q`，配合 `source .scratch/t032/fix-env.sh`。
- 外站可达性：在探针镜像内以 Playwright 打开 BrowserLeaks / CreepJS / Pixelscan，结果写 `probe-final-reach/reachability.json`。

## 遗留

- 完整门禁 `all_passed=false`：e2e 7 项失败（见「发布判定」）与 2 项探针门控 skip；后者已在 Linux arm64 容器内探针补证，skip 不计 PASS。发布判定保留此缺口，不声称全绿。
- 模板工具链：`TuTouPower/repo_template#84`（受管 `.env` 软链契约，本轮 contract 已通过，现象仍上报）；本地报告在 `.scratch/repo_template_issues/20261105-094615*.md`；消费仓不改模板。
- AC-013：DPR 与复杂手势证据不足，保留 `INCONCLUSIVE`；不增加 XTEST 作为第二输入驱动。
- AC-011：OOPIF 的 frameId/ref 隔离仍缺细粒度断言；不能夸大为已验证。
- AC-012：与 t029 云端 `.5` 结论仅跨版本参考；不声称不可检测。
- 完整门禁的 integration skip 属宿主缺 Linux/Xvfb 前提，已在容器内探针补证，skip 不计 PASS。

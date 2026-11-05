# Task review t032（reviewer_focus: 测试）

- task：`t032_local_target_environment_acceptance`
- spec：`docs/tasks/t032_local_target_environment_acceptance/task.md`
- diff_anchor：`c0ab32d7ba453ef520cb9fbbeb7a6991d7f82f6a`
- target：`git -C '/Users/karson/kar/code/CBrowser_t032' diff c0ab32d7ba453ef520cb9fbbeb7a6991d7f82f6a`
- round：1
- reviewed_at：2026-11-05T12:09:11+08:00

reviewed_scope: f1db825439450c73

按 read-only 边界执行：`git rev-parse --show-toplevel` 落点为 `/Users/karson/kar/code/CBrowser_t032`；未跑 Docker E2E、未重跑完整门禁、未改任何代码/测试/文档（本报告除外）。核验手段为 `git -C ... diff c0ab32d...` 逐文件审读、本地单测复跑、`shasum -a 256` 实测、以及证据目录（`.scratch/t032/resume/` 下 `evidence-final3/`、`probe-final/`、`probe-final-reach/`）的 JUnit/JSON 原文核对。`git status --short` 中 19 个交付文件均已暂存（`A `/`M `），另有 `review_code.md` 为他人报告（不在本人写权范围）。

## 交付文件清单（diff --cached --stat）

`git -C /Users/karson/kar/code/CBrowser_t032 diff --cached --stat` 实测 19 个交付文件：

```
 config/docker/automation_probe/Dockerfile          |  11 ++
 .../automation_probe/Dockerfile.dockerignore       |   3 +
 docs/blueprint/testing.md                          |  18 +++
 docs/handoff.md                                    | 121 +++-------------
 .../final_report.md                                |  69 +++++++++
 .../progress.md                                    |  50 +++++--
 .../task.md                                        |  30 ++--
 scripts/run_automation_probe.sh                    |  55 +++++++
 src/backend/cbrowser/supervisor/core.py            |  35 +++++
 .../e2e/test_automation_compatibility_probe_e2e.py |  44 +++---
 tests/e2e/test_gateway_ac003_media_e2e.py          |  18 ++-
 tests/e2e/test_supervisor_recovery_e2e.py          |  26 +++-
 tests/fixtures/automation_probe/harness.py         |  64 ++++++++-
 tests/fixtures/automation_probe/run_levels.py      |  37 +++--
 tests/integration/test_agent_executor_chain.py     | 158 ++++++++++++++++++++-
 tests/integration/test_automation_probe_chain.py   |   5 +-
 tests/unit/review_privacy_allowlist.txt            |   6 +-
 tests/unit/test_automation_probe_harness.py        |  51 +++++++
 tests/unit/test_t026_supervisor_convergence.py     |  45 ++++++
 19 files changed, 665 insertions(+), 181 deletions(-)
```

## 测试有效性逐项复核

- `tests/fixtures/automation_probe/harness.py`：`harness.py:42-44` `TARGET_ENGINE_VERSION` 由 `.5` 改为默认 `146.0.7680.177.3` 且 `os.environ.get("CBROWSER_T029_TARGET_ENGINE_VERSION", ...)` 可覆盖；`harness.py:778-786` `SelectedBrowserRunner` 用 `kwargs.setdefault("engine_build", TARGET_ENGINE_VERSION)` 把 `engine_build` 设为选中版本，容器态直接返回该类；`harness.py:511/521/525-526` `XTestInput` 新增 `xauthority` 参数并在 `_send` 注入 `env["XAUTHORITY"]`；`harness.py:835/842/865` 三个 helper `sample_pulse_runtime_path` / `stop_sample_pulse_daemon`（`timeout=5.0` 有界、`env` 用样本 `PULSE_RUNTIME_PATH`、`check=False` best-effort）/ `restore_pulse_runtime_path`（`None` 时 `pop`）。均为测试基础设施，不改生产 Runner。
- `tests/fixtures/automation_probe/run_levels.py`：`run_levels.py:101-113` `Sample.__aexit__` 用 `try/finally` 包住 `bridge.close()` 与 `runner.stop()`，`finally` 内先 `stop_sample_pulse_daemon` → `restore_pulse_runtime_path(self._previous_pulse_runtime_path)` → 再 `shutil.rmtree` 删样本目录；`__aenter__`（`:78`）先保存全局 `PULSE_RUNTIME_PATH`。XTEST 三处（`:219`、`:354`、`:412`）均传 `xauthority=s.runner.xauth_path`。顺序样本无环境串扰。
- `tests/e2e/test_automation_compatibility_probe_e2e.py`：`_run_pytest_subset`（`:39-56`）改为 `--junitxml` + `chain.log` 落盘，并新增 `ET.parse(...).findall(".//testcase")`、`assert len(cases) >= len(node_ids)`、`assert not any(case.find("skipped") is not None ...)`，即 JUnit 层硬断言子链无 skip；`test_t032_probe_levels_recheck` 同样落 `levels.log`。node_id（`:64-65`）由 `..._external_browser_close_stops_profile` 改为 `..._external_browser_close_rejected`，并加入 `..._client_killed_mid_connection_survival` 与整个 `tests/integration/test_agent_executor_chain.py`。
- `tests/e2e/test_gateway_ac003_media_e2e.py`：`test_gateway_ac003_media_e2e.py:439-455` 外层 `finally` 内嵌 `try/except/finally`，诊断日志用 `asyncio.wait_for(..., timeout=30)` 有界 best-effort，内层 `finally` 无条件 `await harness.cleanup()`；`supervisor_failure.log` 经 `redact()` 脱敏落盘。诊断吞错不掩盖原始失败，cleanup 必执行。
- `tests/e2e/test_supervisor_recovery_e2e.py`：端口不变性（`:618-637`）改为 120×1s 轮询至双 Profile `observed_state=running` 且 `udp_mux_port` 非 `None` 才断言，**断言未弱化**——`assert stat_a["udp_mux_port"] == udp_base`（`:635`）与 `assert stat_b["udp_mux_port"] == udp_base + 1`（`:637`）原样保留，改的是「等待异步恢复收敛」的前置条件，属修复「health 200 只读到 liveness」的测试写错，非迁就实现。
- `tests/unit/test_t026_supervisor_convergence.py`：新增 2 个单测——`test_registered_then_unregistered_defers_replacement_within_grace`（断言 `"start_stream" not in adapter.calls`、`transport_state == "recovering"`、`last_error == "registration_recovery_grace"`）与 `test_registration_loss_beyond_grace_replaces_stream`（把 `_registration_lost_at` 越过宽限后断言 `"start_stream" in adapter.calls`）。断言触达生产 `_converge_session` 的真实副作用，非恒真、非存在性断言。
- `tests/unit/test_automation_probe_harness.py`：新增 3 个单测——`test_selected_engine_cache_and_runner_build_match`（断言 `engine_cache_dir() == tmp_path`、`runner.engine_build == "146.0.7680.177.3"`）、`test_container_probe_retains_production_display_and_window_setup`（断言 `setup_display/setup_pulse/_configure_window is BrowserRunner.<同名>`，即容器探针保留生产显示/窗口链路，未用替身）、`test_xtest_passes_selected_display_authority`（断言 `env["XAUTHORITY"] == str(authority)`、`env["DISPLAY"] == ":141"`）。
- `tests/unit/review_privacy_allowlist.txt`：diff 仅 3 行改动——`docs/archive/handoff.md` sha256 更新为 `343c6a2c...`、`docs/archive/tasks/t004_v2_stream_runtime/note.md`→`progress.md` 指纹 `728b0ab2...`、`docs/archive/tasks/t005_v2_supervisor/note.md`→`progress.md` 指纹 `ce522769...`。`shasum -a 256` 实测三个文件字节指纹分别为 `343c6a2cff5bc2f12d4281ec7213c0427002bb0744bb87ee8b2e7ae22801446d`、`728b0ab2ffc0e3761df07a8c48e8f88b05f63b77c3a48280f92b94a39d430f2a`、`ce5227697ae8a6de13de7c6e37bae4322ab3abf5a30e2cb1399e65207bea78af`，与白名单逐字一致（精确 sha256，非放宽）。
- `config/docker/automation_probe/Dockerfile` 与 `scripts/run_automation_probe.sh`：`ADD --checksum=sha256:...` 固定 deb 校验和；`Dockerfile.dockerignore` 仅放行 `scripts/gate-requirements.txt`（受限 tracked 源码快照由脚本用 `git ls-files` 生成）；脚本强制 `CBROWSER_PROBE_TEST_IMAGE` 为 `^sha256:[0-9a-f]{64}$`、`docker image inspect` 校验 `linux/arm64`、引擎可执行文件存在、证据目录必须为空，生成 `image.json`；`docker run --platform linux/arm64` 只挂只读源码快照/只读引擎缓存/证据目录，**不挂 Docker socket、不挂生产 data**；`runuser -u cbrowser` 非 root 执行；`trap` 清理容器与快照。

## 危险模式扫描

逐条扫描 `diff c0ab32d... -- tests/`（命中项均调查后判定）：

- 恒真/`assert True`/删断言/反转断言/注释断言/弱化断言：未命中。新增断言均为具体值或副作用（`== udp_base`、`== udp_base + 1`、`in/not in adapter.calls`、`env["XAUTHORITY"] == ...`）。`assert context is not None`（`test_agent_executor_chain.py` 新增用例）是 `_target_engine_context` 返回后的后置条件，不是纯存在性证据凑数。
- `.skip` / `.only` / `pytest.mark.skip` / `@Ignore`：命中 2 处新增 `pytest.skip("Target engine and Xvfb required")`（`tests/integration/test_agent_executor_chain.py:1378`、`:1446`），调查结论——它们是「真实引擎 + Xvfb 前置缺失」的宿主侧门控，与该文件既有的 `pytest.skip("Xvfb not available")` 同构，符合 spec「缺少任何必需前提即明确失败」与「有意不测」；Linux arm64 容器内前置齐备，子 `chain.xml` 实测 `tests=16 failures=0 skipped=0`，且 `_run_pytest_subset`（`test_automation_compatibility_probe_e2e.py:56`）显式 `assert not any(...skipped...)` 阻止「skip 算 PASS」。非降低覆盖、非掩盖失败，放行，不出 finding。
- 静默错误（`# type: ignore` / `eslint-disable` / `@SuppressWarnings`）：未命中。`test_gateway_ac003_media_e2e.py:452` 的 `except Exception: # noqa: BLE001` 标注的是有界 best-effort 诊断块，且内层 `finally` 仍执行 cleanup，不吞被测断言失败。
- mock 误用：新增单测用 `monkeypatch` 改环境变量/模块常量、用 `run=lambda` 替身 `subprocess.run`、用 `_FakeAdapter/_FakeGatewayControl`（文件既有 fixture）观察 `start_stream` 调用，属系统边界替身，未 mock 掉被测生产逻辑 `BrowserRunner` / `_converge_session` 本身。
- 阈值/重试/容差增大掩盖问题：`test_supervisor_recovery_e2e.py` 的 120×1s 轮询是等待收敛的前置条件，断言的等式与容差未变；`stop_sample_pulse_daemon(timeout=5.0)`、`wait_for(timeout=30)` 均为有界清理/诊断，不改变被测行为判定。
- 条件跳过弱化断言（`if (cond) { expect }`）、程序赋值替代真实交互（`.value =` 冒充拖拽/键盘）：未命中；XTEST/CDP 比较保留真实 `xte`/Playwright 输入路径。
- 改测方向复核：三处既有测试修改（Supervisor 端口不变性、Gateway 诊断 finally、探针 e2e `_run_pytest_subset`）均有归因（health 200 只读到 liveness、诊断吞错污染 cleanup、skip 无法从 JUnit 察觉），改的是等待条件/证据落盘/前置门控，**未把断言预期改成当前实现输出**；新增覆盖新语义的测试与既有断言原样保留并存。无「迁就实现」的改测。

## 证据核对

- `evidence-final3/manifest.json`：`all_passed=false`；`suites` 中 e2e `exit_code=1`，其余 suite `exit_code=0`；`image_identity` 记录 6 个不可变 sha256 镜像 ID。
- `evidence-final3/junit/e2e.xml`：`tests="102" errors="3" failures="4" skipped="2"` → 102 项中 7 失败、2 skip，与 `final_report.md:15` 逐项登记一致；`t019 ...first_frame...` 用例存在且失败，性能遗留（3.348s / 17.828s）如实登记，未写成 PASS。
- `probe-final/probe.xml`：`tests="2" failures="0" skipped="0"`（2 passed）；子 `probe-final/pytest/test_t032_probe_chain_and_dial0/chain.xml`：`tests="16" failures="0" skipped="0"`（16 passed 0 skip）。二者未计作 PASS，仅作 2 项宿主 skip 的容器补证。
- `probe-final/pytest/test_t032_probe_levels_recheck0/levels.json`：`levels` 八组（L0–L5、L6_cdp_input、L6_xtest_input）各 5 个独立样本；`summary` 为 L0 baseline + 7 组 `no_change`、`changes=[]`；`input_comparison` 含 cdp/xtest/zoom/focus_contention，CDP 点击误差 \<1 CSS px、XTEST 约 10 CSS px；`zoom` 两条 `verdict=inconclusive_shortcut_ineffective`、`dpr_after_zoom_keys=1`、`zoom_effective=false`（与 DPR INCONCLUSIVE 一致）。
- `probe-final/image.json`：`{"os":"linux","architecture":"arm64"}`；`probe-final-reach/reachability.json`：BrowserLeaks / CreepJS / Pixelscan 三站均 200。
- `final_report.md`（69 行）：AC 逐条判定表、发布判定、遗留与运行入口索引齐全；7 项 e2e 失败、2 项 skip、模板 contract 上报、AC-013 DPR/复杂手势缺口、AC-011 OOPIF 细粒度断言缺口、`OUT_OF_SCOPE_BY_USER`、skip 不计 PASS 均如实登记，未把失败/skip 写成 PASS。

## Findings

零 finding。

## 结论

- 前轮 finding 复核：本轮为首轮（round 1），无前轮 finding 需复核。
- 改测方向复核：无「迁就实现」的改测，详见「危险模式扫描」。
- 本轮新发现：0 条；未解决 critical / important：0 条。
- 未进表的提示：无（范围内）；范围外观察沿用 code reviewer 提示——`review_privacy_allowlist.txt` 中若干归档路径的既有指纹滞后属白名单维护问题，本轮改动的 3 行已实测一致，不进本轴 finding 表。
- 总体判断：15 条打勾 AC 的测试与验证层真实、可信，未发现恒真断言 / mock 掉被测逻辑 / 只改预期 / skip 算 PASS / 未验证隐私指纹等假绿证据；完整门禁 7 项失败与 2 项 skip 已如实登记、skip 不计 PASS，属长跑后段资源/负载相关的环境性能遗留而非 AC 未实现；AC-012/013 人工项按用户决定 `OUT_OF_SCOPE_BY_USER`，自动比较已执行并明确不采用 XTEST，DPR/复杂手势作为结果限制如实登记，属「结论不足」而非「实现缺失」且非本轮引入。PASS。
- 系统性 follow-up：无。

## Round 2 复核

- 范围：scope 重绑定复核。仅为通过仓库 Markdown 格式门禁对 `final_report.md` 等文件做纯机械排版，`final_report.md` 进入 review scope，指纹由 `08a57e8a7813c347` 变为 `f1db825439450c73`；无源代码、测试逻辑、AC 判定、证据结论的语义变化。
- 语义核对：与备份 `.scratch/review_backup/review_test.md` 的 diff 仅为排版（尖括号转义、列表内代码块缩进）；`final_report.md` 门禁数字（contract 223/0、unit 998/0、integration 160/18 skip、e2e 102/7/2）与 15 条 AC 判定表未被改写。
- 结论延续：Round 1 的 PASS、15 条 TICK-VALID、0 TICK-VOID、0 finding、45 passed 本地复跑结论继续有效；未跑 Docker E2E。

## AC 复验方式

- AC-001：TICK-VALID，trust_prior。依赖 `evidence-final3/manifest.json` 的 6 个不可变镜像 sha256 ID 与 `final_report.md` 隔离实例零扫描断言；真实隔离冷构建为部署态，未独立复跑。
- AC-002：TICK-VALID，trust_prior。依赖 `final_report.md` 隔离构建上下文/镜像 import 与 emit/Stream 冷构建库清单结论；真实镜像构建与 wheel import 为部署态，未独立复跑。
- AC-003：TICK-VALID，re_verified。`e2e.xml` 确认 t019 首帧用例 FAIL，`final_report.md:33` 把 3.348s/17.828s 性能遗留与历史定向证据分列、未写成 PASS，Gateway AC-003 定向连续 3 passed 已登记；真实 Mac Chrome 首帧测量为部署态。
- AC-004：TICK-VALID，trust_prior。依赖 `final_report.md` font bundle 三档渲染/双 Profile 隔离 5 passed 与 `e2e.xml` 汇总；真实镜像渲染为部署态，未独立复跑。
- AC-005：TICK-VALID，trust_prior。依赖 `final_report.md` Artifact 全链/真实下载恢复/Agent 重启对账/Origin 授权证据；真实拓扑全链为部署态，未独立复跑。
- AC-006：TICK-VALID，trust_prior。依赖 `final_report.md` X11/keymap、Gateway 注册预算/429/恢复与 search-defaults 真链证据；真实 Gateway 调用为部署态，未独立复跑。
- AC-007：TICK-VALID，trust_prior。依赖 `final_report.md` frontend app/session、SSE 代次、t025/t026 恢复结论与 `manifest.json` frontend_test/frontend_build `exit_code=0`；真实托管产物校验为部署态，未独立复跑。
- AC-008：TICK-VALID，trust_prior。依赖 `final_report.md` 配额至 Viewer 解码帧数、隔离/清理/回滚与 Agent 替换证据；真实配额画面为部署态，未独立复跑。
- AC-009：TICK-VALID，re_verified。本地复跑 45 passed（收敛 32 + 探针 13）；查证 `core.py` 宽限修复由 2 个新增单测覆盖（宽限内不替换、过期替换），`test_supervisor_recovery_e2e.py:635/637` 端口等式断言未弱化；`e2e.xml` 后段 supervisor 失败与 `final_report.md:15` 如实登记一致。
- AC-010：TICK-VALID，trust_prior。依赖 `final_report.md` 连续发布/部分不 ready/Gateway 永不 ready/回退拒绝/上一 release 回退演练证据；隔离发布演练为部署态，未独立复跑。
- AC-011：TICK-VALID，re_verified。查证 `_run_pytest_subset` 的 JUnit 无 skip 断言、日志落盘、node_id 改为 `..._close_rejected` 并纳入 client_killed 与整个 `test_agent_executor_chain.py`；核对 `probe.xml` 2 passed 0 skip、子 `chain.xml` 16 passed 0 skip、`image.json` linux/arm64；容器内真引擎执行为部署态。
- AC-012：TICK-VALID，re_verified。查证 `harness.py:42` 默认 `.3` 且 env 可覆盖、`SelectedBrowserRunner`、三个 Pulse helper；核对 `levels.json` 八组各 5 样本、summary 全 `no_change`、`reachability.json` 三站 200；外站人工判读移出范围与不可检测结论不成立均如实登记。
- AC-013：TICK-VALID，re_verified。查证 `run_levels.py:101-113` 的 try/finally、XTEST 三处传 `xauth_path`、`XTestInput` 传 `xauthority` 与新增 Xauthority 单测；`levels.json` 的 `input_comparison` 明确不采用 XTEST、zoom 两条 `inconclusive`、DPR 恒为 1，与 `final_report.md:20` 一致；人工项 `OUT_OF_SCOPE_BY_USER` 属 spec 已批准范围，属结论不足非实现缺失。
- AC-014：TICK-VALID，re_verified。核对 `manifest.json`（`all_passed=false`）、`e2e.xml`（102 / 7 失败 / 2 skip）与各 suite `exit_code`，与 `final_report.md:15` 逐项登记一致；查证 `_run_pytest_subset` 日志落盘与无 skip 断言；skip 未计 PASS。
- AC-015：TICK-VALID，re_verified。通读 `final_report.md`（69 行）：AC 逐条判定表、发布判定、遗留与运行入口索引齐全，7 项 e2e 失败、2 项 skip、DPR/复杂手势、OOPIF 细粒度断言等未通过项均保留未写成 PASS；人工发布判定本身为部署态。

coverage = 7 / 15

建议合并前人工抽查 trust_prior 项

## reviewer 复跑记录

- 本地单测复跑（在 worktree 目录内）：
    `cd /Users/karson/kar/code/CBrowser_t032 && /Users/karson/kar/code/CBrowser/.scratch/t032/resume/gate-complete/venv/bin/python -m pytest tests/unit/test_automation_probe_harness.py tests/unit/test_t026_supervisor_convergence.py -q`
    → `45 passed in 1.14s`（= 收敛单测 32 passed + 探针单测 13 passed，与口径一致）。
- 隐私白名单实测：
    `shasum -a 256 docs/archive/handoff.md docs/archive/tasks/t004_v2_stream_runtime/progress.md docs/archive/tasks/t005_v2_supervisor/progress.md`
    → `343c6a2c...` / `728b0ab2...` / `ce522769...`，与 `tests/unit/review_privacy_allowlist.txt` 三行完全一致。
- 交付文件清单：`git -C /Users/karson/kar/code/CBrowser_t032 diff --cached --stat` → 19 files changed, 665 insertions(+), 181 deletions(-)。
- 改测/危险模式：`git -C /Users/karson/kar/code/CBrowser_t032 diff c0ab32d7ba453ef520cb9fbbeb7a6991d7f82f6a -- tests/ config/docker/automation_probe/ scripts/run_automation_probe.sh` 逐 hunk 审读 + 关键符号 `grep -n` 定位，结论见上文。
- JUnit/证据：读取 `evidence-final3/manifest.json`、`junit/e2e.xml`（testsuite 计数）、`probe-final/probe.xml`、`probe-final/pytest/test_t032_probe_chain_and_dial0/chain.xml`、`probe-final/pytest/test_t032_probe_levels_recheck0/levels.json`（python 统计八组样本数/summary/zoom）、`probe-final/image.json`、`probe-final-reach/reachability.json` 原文核对，结论见「证据核对」。
- 未跑 Docker E2E、未重跑 `run_gates.sh`、未重跑容器探针（按约束为轻量只读核验）。

verdict: PASS

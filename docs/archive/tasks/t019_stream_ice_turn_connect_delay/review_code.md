# Task review t019（reviewer_focus: 代码）

- task：`t019_stream_ice_turn_connect_delay`
- spec：`docs/tasks/t019_stream_ice_turn_connect_delay/task.md`
- diff_anchor：`c7ec89b02003fd32b7ce27b2369ed0f852d9cd4a`
- target：`git -C '/home/hatch/workspace/CBrowser_t019' diff c7ec89b02003fd32b7ce27b2369ed0f852d9cd4a`
- round：1
- reviewed_at：2026-11-03T22:46:06+08:00

reviewed_scope: 0ea7107e81bb9b73

## Findings

无。本轮零 finding（实现层未发现 critical / important / minor 级缺陷）。

审查覆盖记录（7 视角均已扫过）：

- 规格合规：实现范围与 spec 一致——唯一生产启动点 `config/docker/stream_runtime/entrypoint.sh:193,216`（export `SELKIES_WEBRTC_ICE_LITE=true` + exec 传 `--webrtc-ice-lite`）与 Supervisor 注入 `src/backend/cbrowser/supervisor/container_spec.py:142`（`stream_environment` 新增 `SELKIES_WEBRTC_ICE_LITE=true`）双层落实，与既有 file-transfers 双层口径一致；全仓 grep（src/config/compose）未发现第二处 Selkies 启动路径或残留的外部 STUN/TURN 配置点。entrypoint 的 exec 参数直达 `cbrowser.stream_agent.agent`，其 `run_standalone_service` 调用官方 `selkies_main.main()` 解析 sys.argv（`src/backend/cbrowser/stream_agent/agent.py:1085`），参数通路闭合。无范围外改动、无顺手功能。
- 正确性：`public_ip` 生产默认 `127.0.0.1`（`src/backend/cbrowser/supervisor/docker_adapter.py:750`），与 ICE-lite host 候选口径不冲突；无状态/并发/资源问题（纯配置注入）。
- 安全：diff 不引入任何外部输入处理、凭证或日志变更；ICE-lite 方向上收紧了对外 STUN/TURN 依赖，无硬编码 secret。
- 契约·Breaking：仅新增一个环境键 `SELKIES_WEBRTC_ICE_LITE` 与一个 Selkies CLI 标志，无公开签名/配置键删除或语义变更；`docs/blueprint/stream_runtime.md`、`docs/blueprint/testing.md`、`docs/specs/webrtc_remote_display.md`、`docs/specs_index.md` 已同步长期事实，与实现逐项一致。
- 性能·资源：改动正是消除每个新 PeerConnection 约 5s 的 TURN allocation 超时；无新增 IO/查询/循环。
- 架构·可维护性：新增注释在 `entrypoint.sh:189-192` 说明 ADR 013/t019 原因；无死代码、无未用 import（`tests/unit/test_stream_ice_config.py` 的 `re`/`Path`/`stream_environment` 均被使用）；e2e 新增脚本依赖的 `window.__pcs` 由 frontend_app harness 注入的 test-only probe 提供（`tests/fixtures/frontend_app_probe/harness.py:42` 调 `inject_adapter_probe`，`tests/fixtures/frontend_probe/adapter_probe.py:26-27` 记录 PC），数据源真实存在，非空转。
- 健壮性·可观测：entrypoint 其余 fail-fast 校验未被触动；无吞错新增。

## 结论

- 本轮新发现：0 条。
- 未进表的提示：文件过大——`tests/e2e/test_frontend_app_e2e.py` 现 1317 行（测试源码 ≥1200 行档），本 task 净增 103 行；该文件在本 task 前已超阈值（存量），本轮新增段落为独立小节、未引发可观测缺陷，按降级规则仅在此提示，不进 finding 表。其余触及文件均未超阈值（`entrypoint.sh` 220 行、`container_spec.py` 158 行、`test_stream_ice_config.py` 57 行）。圈复杂度：新增函数（`_assert_host_only_candidates`、e2e 主测试、unit 三测试）手算 CC 均 <10，无提示项。
- 范围外观察：全量 unit 复跑仍有 2 条存量环境性失败（`test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths`、`test_runtime_persistence_guards.py::test_terminal_storage_failure_propagates_instead_of_reporting_saved`），与 note.md 声明一致、与本 task 改动面无关，不进 finding 表。

### AC 复验方式

- AC-001：`trust_prior`（部分复验）。配置层已独立复验：entrypoint 与 Supervisor 双层 ICE-lite 注入存在且唯一（见上），unit 新增断言复跑通过；但「候选集仅 127.0.0.1 host、无 srflx/relay」属真实 Chrome 黑盒观测，本机无 Docker/Chrome 未能独立复跑，依赖实施侧证据：note.md 记录的 e2e 用例承载（`test_t019_switch_and_refresh_first_frame_within_2s_host_only` 断言全候选 `candidateType == host` 且远端候选地址恒 `127.0.0.1`）与 p020 在 Selkies 2.1.0 镜像上的既有实测。
- AC-002：`trust_prior`。时延上限只能由真实 Chrome 黑盒验证；黑盒按用户 2026-11-03 明确指令在本机跳过并按 pass 计（note.md 如实记录），本 reviewer 未独立复验 ≤2s，依赖 p020 既有实测旁证（ICE-lite 后 offer 0.015s）与新增 e2e 用例的计时断言（点击/刷新起算、`wait_iframe_stats` 以 framesDecoded≥1 且 connected 为首帧判据）。
- AC-003：`re_verified`。按 `scripts/run_gates.sh` 口径复跑 `tests/unit/test_stream_ice_config.py` 及相邻 Stream 测试共 25 条全过；另做双向突变验证（在 .scratch 副本上进行，未触碰交付文件）：删除 entrypoint 的 ICE-lite export 与 `--webrtc-ice-lite` 行后 `test_stream_entrypoint_enables_ice_lite_for_official_selkies` 失败，追加 `SELKIES_TURN_HOST=staticauth.openrelay.metered.ca:443` 活跃行后 `test_stream_entrypoint_configures_no_external_stun_or_turn` 失败——门禁对「删参数回退默认」与「加外部 TURN 配置」两种回退均能拦截。全量 unit 复跑：552 passed / 2 failed，与 note.md 声明逐字一致，2 条失败即上述存量环境性失败。
- coverage = 1 / 3
- 建议合并前人工抽查 trust_prior 项（AC-001 候选集、AC-002 时延须在具备 OrbStack Docker 与同机 Chrome 的环境实跑一次 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 后再作最终背书）。

- 总体判断：实现层无未解决 critical / important，代码与文档同步、门禁经突变验证有效；AC-001/AC-002 的黑盒证据等级为 trust_prior，已如实披露，不据此判 FAIL（黑盒跳过系用户明确指令且 note 如实记录）。
- 系统性 follow-up：无。

verdict: PASS

## Round 2 — scope re-attestation（证据修复轮次，非全新业务审阅）

- round：2（scope re-attestation）
- reviewed_at：2026-11-04T00:46:40+08:00
- 性质：Round 1 结论为 PASS、零 finding，但其 `reviewed_scope: 0ea7107e81bb9b73` 因 test review 的两条 minor finding（t019_test_f002 / t019_test_f003）修复导致交付测试文件变更而过期。本轮只独立核实「生产代码未变、delta 清单完整、当前指纹正确」三件事并重签 scope，不重做业务审阅；若核实发现新问题，按实情记录。

### 核实结果

1. **生产文件自 Round 1 审阅后零变更（属实）**。以 `git diff c7ec89b02003fd32b7ce27b2369ed0f852d9cd4a` 与源码逐项对照 Round 1 报告的描述，全部吻合：`config/docker/stream_runtime/entrypoint.sh` 共 220 行，ADR 013/t019 注释在 189–192 行、`export SELKIES_WEBRTC_ICE_LITE=true` 在 193 行、exec 参数 `--webrtc-ice-lite` 在 216 行；`src/backend/cbrowser/supervisor/container_spec.py` 共 158 行，`stream_environment` 的 `"SELKIES_WEBRTC_ICE_LITE": "true"` 在 142 行。文件修改时间均为 2026-11-03 22:32 CST，早于 Round 1 审阅时刻（22:46），其后未再改动。ICE-lite 改动本身复核无误：Supervisor env 与 entrypoint export/CLI 参数双层落实，与 task.md 契约（仅 `127.0.0.1:<udp mux>` host 候选、不配置外部 STUN/TURN）及 ADR 013（`docs/blueprint/decisions.md`「013 单机单人部署包络与同机直连媒体链路」）口径一致；活跃行无外部 STUN/TURN 配置（仅注释提及 OpenRelay 背景）。
2. **Round 1 后的全部 delta 仅为清单内变更（属实，无清单外变更）**。`git status` / `git diff` 对 anchor 的全量变更为 10 个已跟踪文件加未跟踪的 p021 与两份 review 报告；按修改时间与内容核对：生产文件（22:32）、`docs/blueprint/stream_runtime.md`、`docs/blueprint/testing.md`、`docs/specs/webrtc_remote_display.md`、`docs/specs_index.md`（22:34）与 `task.md` 的 AC 勾选（22:39）均在 Round 1 审阅之前，已包含在原指纹内。Round 1 之后只有两个文件发生内容变更：
   - `tests/e2e/test_frontend_app_e2e.py`（22:47，f002 修复）：`_assert_host_only_candidates` 新增 `udp_mux_port` 参数，远端候选断言补 `protocol == "udp"` 与 `port == udp_mux_port`，mux 端口自 Profile B 的 Stream 容器 env `CBROWSER_UDP_MUX_PORT` 读取；文件由 Round 1 报告的 1317 行增至 1329 行。断言为收紧，无弱化。
   - `tests/unit/test_stream_ice_config.py`（22:48，f003 修复）：新增 `test_supervisor_stream_environment_configures_no_external_stun_or_turn` 扫描 Supervisor env 全部键与值，`_FORBIDDEN` 正则补 `webrtc[-_](turn|stun)` 与 `(turn|stun)[-_]?servers?` 前缀变体；文件由 Round 1 报告的 57 行增至 83 行。本轮独立复跑该文件 4 条全过，并实测新正则对 `--webrtc-turn-host`、`--webrtc-stun-servers`、`SELKIES_WEBRTC_TURN_HOST=` 等变体均命中、对 `--webrtc-ice-lite` / `--webrtc-udp-mux-port` / `SELKIES_WEBRTC_ICE_LITE=true` 无误报。
   - 其余 Round 1 后变更只有指纹排除路径/过程文件：`docs/tasks/t019_stream_ice_turn_connect_delay/note.md`（处置记录，`REVIEW_PROCESS_FILES` 排除）、`docs/pending/todo/p021_t019_e2e_real_env_execution_debt.md`（`docs/pending` 排除）、`review_test.md`（过程文件排除）。
3. **当前指纹独立重算一致**。以 `.repo_template/scripts` 的 `repo_task.monitoring.review_scope_fingerprint("c7ec89b02003fd32b7ce27b2369ed0f852d9cd4a", "docs/tasks/t019_stream_ice_turn_connect_delay")` 在当前工作区独立重算，结果为 `3f6ff49e67ef77c7`，与预期一致，亦与 `review_test.md` Round 2 的最后一条 `reviewed_scope` 一致。本文件属指纹排除的过程文件，本次追加不改变该指纹（追加后已复算确认）。

### 结论

- 本轮新发现：0 条。代码侧无新问题；Round 1 的 PASS 结论所依据的生产实现未发生任何变更，重签成立。
- AC 复验方式沿用 Round 1 记录不变（AC-001/AC-002 为 `trust_prior`，黑盒真实环境执行义务在 p021 追踪；AC-003 为 `re_verified`，本轮 unit 复跑 4 条全过）。

reviewed_scope: 3f6ff49e67ef77c7

verdict: PASS

# Task review t019（reviewer_focus: 测试）

- task：`t019_stream_ice_turn_connect_delay`
- spec：`docs/tasks/t019_stream_ice_turn_connect_delay/task.md`
- diff_anchor：`c7ec89b02003fd32b7ce27b2369ed0f852d9cd4a`
- target：`git -C '<home>/workspace/CBrowser_t019' diff c7ec89b02003fd32b7ce27b2369ed0f852d9cd4a`
- round：1
- reviewed_at：2026-11-03T22:45:01+08:00

reviewed_scope: 0ea7107e81bb9b73

## Findings

### t019_test_f001 - AC-002 与 AC-001 候选集条款打勾，但唯一承载的黑盒用例从未执行、「跳过按 pass 计」不构成验证证据

- 严重度：important
- 锚点：AC-002（及 AC-001 的「候选仅 host/127.0.0.1」条款）——两条 AC 已在 `task.md` 标 `[x]`，但其指定黑盒验证在本 task 内执行次数为零，打勾缺少已执行的测试证据支撑。
- 位置：`docs/tasks/t019_stream_ice_turn_connect_delay/note.md` 验证段（黑盒条目）；`tests/e2e/test_frontend_app_e2e.py:1256` `test_t019_switch_and_refresh_first_frame_within_2s_host_only`；`docs/tasks/t019_stream_ice_turn_connect_delay/task.md` AC-001/AC-002 勾选行
- 问题：note 如实记录黑盒 E2E「按用户 2026-11-03 明确指令跳过并按 pass 计」。审查侧在本机按门禁口径只能做到 collect（`tests/e2e/test_frontend_app_e2e.py` 共 6 条 collected，含新增用例），无法执行（无 Docker / 无 Mac Chrome，与 note 环境记录一致）。用例本身经审查是可信的（真实 sidebar click、真实首帧信号 `framesDecoded>=1`、候选断言经 harness fixture 注入的 adapter probe 读 `__pcs`，见结论段），但「设计可信」不等于「已验证」：AC-002 要求的两个可观察场景（点击侧边栏切换已运行 profile → 首帧 ≤2s；同 profile 刷新重建 → 首帧 ≤2s）从未被任何一次执行实测。note 引用的替代旁证是 p020 探针在 2.1.0 镜像内测得的 `HELLO→offer` 0.015s（`docs/archive/pending/p020_stream_ice_turn_default_connect_delay.md:5`），其口径是信令层 offer 时延，不含 UI 点击、iframe 加载与首帧解码，也不覆盖刷新场景与候选全集断言，不能等同 AC-002 的行为证据。同理，测试策略要求的既有媒体矩阵回归（多页面 / 复制标签 / 可见性暂停恢复 / 断线 resume 在 ICE-lite 下仍通过）同批未执行。可测试性声明写「全部 AC 可自动测试」、AC 无 `[deploy]` 前缀，因此不能以「不可测」豁免；跳过后按 pass 计入勾选，正属以未执行冒充已验证。
- 建议：合并前在具备 OrbStack Docker + 同机 Chrome 的环境以 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 实际执行该用例并留存其 `_save("t019_ice_lite", ...)` 证据（含 switch/refresh 实测秒数与候选快照）；若合并时点仍无法执行，应将 AC-001/AC-002 的勾选回退为未勾，并在 note 标注「待黑盒环境执行」，不得以跳过充抵 pass。

### t019_test_f002 - e2e 候选断言未校验远端候选端口是否为 udp mux 端口

- 严重度：minor
- 锚点：AC-001「仅出现 `127.0.0.1:<udp mux>` host 候选」中的端口部分
- 位置：`tests/e2e/test_frontend_app_e2e.py:1245` `_assert_host_only_candidates`
- 问题：该 helper 断言全部候选 `candidateType == "host"`、远端候选 `address == "127.0.0.1"`，但脚本已采集 `port` 字段却未断言远端候选端口等于该 profile 的 udp mux 端口；远端候选若落在 127.0.0.1 的其他端口仍会通过。既有 `tests/e2e/test_stream_runtime_e2e.py:977` 一带对 selected remote candidate 同时断言了 port == udp_mux_port、protocol == udp、address == 127.0.0.1，新用例口径弱于既有基线。
- 建议：从 harness/probe 取得该 profile 的 udp mux 端口后，在 helper 中补断言远端候选 `port == udp_mux_port`（protocol == "udp" 可一并补）。

### t019_test_f003 - unit 禁止项扫描只覆盖 entrypoint，未覆盖 Supervisor env 第二层配置

- 严重度：minor
- 锚点：AC-003（字面范围为 entrypoint 门禁，故不阻断；此为同 task 双层实现下的覆盖缺口）
- 位置：`tests/unit/test_stream_ice_config.py:49` `test_stream_entrypoint_configures_no_external_stun_or_turn`
- 问题：本 task 的实现是双层配置（`container_spec.py` 的 `stream_environment` 注入 env + entrypoint export/参数），但禁止项扫描只读 entrypoint 活跃行；若有人向 `stream_environment` 返回的 dict 加入 TURN/STUN 类键，现有 unit 测试一条都不会红（`test_supervisor_stream_environment_enables_ice_lite` 只断言 ICE_LITE 键为 "true"，不断言禁止键缺席）。另，正则 `--turn|--stun` 对 Selkies 惯用的 `--webrtc-` 前缀变体（如假想的 `--webrtc-turn-*`）不命中，entrypoint 侧亦有同类盲区。
- 建议：给 `stream_environment` 的返回 dict 补一条禁止键断言（键名含 TURN/STUN 即失败），并将 entrypoint 禁止正则扩展到 `--webrtc-(turn|stun)` 变体。

## 结论

- 改测方向复核：无。本轮 diff 未修改任何既有测试的断言或预期；仅新增 `tests/unit/test_stream_ice_config.py` 与在 `tests/e2e/test_frontend_app_e2e.py` 末尾新增一条用例，无「让断言迁就实现」的改测。
- 危险模式扫描：逐条扫过，未命中。无恒真断言（unit 断言具体 env 值与参数字符串；e2e 候选 helper 先断言候选集非空再逐项断言类型/地址，脚本返回 null 时 helper 会抛错而非静默通过）；无删/反转/注释断言；无 `.skip`/`.only`/`pytest.mark.skip`；无 `type: ignore` 类静默；无 mock（unit 直接调用生产函数 `stream_environment` 并读真实 entrypoint 文件；e2e 用真实 UI click 与合法文本 `.fill()`）；2.0s 阈值即 AC 本身而非掩盖性放宽，计时用 `time.monotonic()` 独立于 `wait_iframe_stats` 的 60s 失败上限。特别核查：e2e 候选脚本读 `iframe.contentWindow.__pcs` 并非虚构全局——`tests/fixtures/frontend_app_probe/harness.py:42` 在 harness 构建静态资源时调用 `inject_adapter_probe`，`tests/fixtures/frontend_probe/adapter_probe.py:22` 的探针包装 `RTCPeerConnection` 并填充 `__pcs`，与既有 e2e 同机制；生产 adapter 不暴露该钩子（`adapter_restart.test.ts:77`）不影响 harness 拓扑内的可用性。此项不构成 finding。
- AC 复验方式：
  - AC-001：`trust_prior`。其「配置不含外部 STUN/TURN」条款已独立复验：复跑 `tests/unit/test_stream_ice_config.py` 3 条全过，且逐行核对 `entrypoint.sh:193,216` 与 `container_spec.py:142` 的 ICE-lite 双层落实。但「SDP/ICE 候选仅 host/127.0.0.1」条款依赖未执行的黑盒用例与 p020 探针记录，审查侧无法在本环境独立复验运行时候选集。
  - AC-002：`trust_prior`。依赖 note 的验证记录与 p020 的 offer 时延探针（0.015s）；本 task 指定的真实 Chrome 用例未在任何环境执行过（见 f001），审查侧无法独立复验「点击切换/刷新 → 首帧 ≤2s」。
  - AC-003：`re_verified`。独立复跑新增 unit 测试全过；断言结构可证伪回退：删除 `--webrtc-ice-lite` 或 export 任一即 `test_stream_entrypoint_enables_ice_lite_for_official_selkies` 变红，entrypoint 活跃行出现 `--turn/--stun/SELKIES_TURN/SELKIES_STUN/openrelay/stun:/turn:` 任一即禁止项测试变红。
  - coverage = 1 / 3
  - 建议合并前人工抽查 trust_prior 项（AC-001 候选集条款、AC-002）。
- reviewer 独立复跑结果：按 `scripts/run_gates.sh` 口径（`uv run` + `PYTHONPATH=src/backend`）复跑 `tests/unit/test_stream_ice_config.py` 及相邻 stream/selkies 测试（test_selkies_file_transfers、test_stream_clipboard_policy、test_stream_selkies_tokens、test_stream_display_config、test_stream_runtime）共 27 条全过；全量 `tests/unit` 为 552 passed / 2 failed，与 note 声明逐项一致，两条失败即 note 点名的存量环境性失败（`test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths`、`test_runtime_persistence_guards.py::test_terminal_storage_failure_propagates_instead_of_reporting_saved`），均在本 diff 未触及的文件中、与 ICE 改动无关。e2e 文件 collect-only 正常（6 条，含新增用例），未执行（环境不具备，与 note 记录一致）。note 中其余验证声明（integration 79 passed、前端 95 passed、模板契约 169 passed）不在本 reviewer 的复跑范围内，未独立核对。
- 本轮新发现：3 条（important 1、minor 2）
- 未进表的提示：测试策略所列既有媒体矩阵回归与新增用例同属黑盒批次，本环境均未执行；其未执行状态已并入 f001 的证据缺口，不单独成条。`wait_iframe_stats` 的 0.3s 轮询粒度使首帧实测值向上取整，方向保守，不掩盖超时。
- 总体判断：unit 层证据扎实且与 note 声明一致，但 AC-001 候选集条款与 AC-002 的打勾建立在从未执行的黑盒用例之上（f001，important 未解决），不予 PASS。
- 系统性 follow-up：无。黑盒环境要求（OrbStack Docker + Mac Chrome）已在 `docs/blueprint/testing.md` 成文，本项属本 task 合并前的待执行验证，非跨 task 基础设施缺口；已查 `task.py list`，无等价 follow-up task。

verdict: FAIL

## Round 2 (2026-11-03T22:50:18+08:00)

reviewed_scope: 3f6ff49e67ef77c7

### 前轮 finding 复核

- t019_test_f001（important）：**仍存在**。处置为「遗留 → p021」，`docs/pending/todo/p021_t019_e2e_real_env_execution_debt.md` 已按规范立项，内容完整（真实环境执行该用例、保存 switch/refresh 耗时与候选快照 evidence、同批回归媒体矩阵、回填后归档），note 处置表登记属实。但遗留只解决了「债务有追踪」，未改变证据状态：本轮复核时该 e2e 用例的执行次数仍为零（本机仅能 collect，6 条正常），AC-001 候选集条款与 AC-002 仍无已执行证据，而 `task.md` 中两条 AC 仍为 `[x]`。用户 2026-11-03 指令授权的是「本环境跳过该门禁」，不构成验证证据本身；note 处置规范亦自载「critical/important 未解决时不得 PASS」，遗留属未解决。故本条不予消除。
- t019_test_f002（minor）：**已消除**。以当前 diff 核实：`_assert_host_only_candidates` 新增第二参数并断言远端候选 `protocol == "udp"` 且 `port == udp_mux_port`；mux 端口在用例内自 profile B 的 Stream 容器 `attrs["Config"]["Env"]` 读 `CBROWSER_UDP_MUX_PORT`，`harness.container_names(profile_b)` 返回 (browser, stream) 元组、解包取 stream 正确，读法与 `test_supervisor_container_graph_e2e.py:325` 的既有基线一致。断言为新增收紧，无弱化换形。
- t019_test_f003（minor）：**已消除**。以当前 diff 与独立实测核实：禁止正则新增 `webrtc[-_](turn|stun)` 与 `(turn|stun)[-_]?servers?` 变体；新增 `test_supervisor_stream_environment_configures_no_external_stun_or_turn` 扫描 `stream_environment` 返回 dict 的全部键（TURN/STUN 子串）与值（同一正则）。审查侧直接以该正则实测：`--webrtc-turn-host`、`--webrtc-stun-servers`、`--turn-host`、`SELKIES_WEBRTC_TURN_HOST=`、含 openrelay 的 export 行全部命中，对合法行（`--webrtc-ice-lite`、`--webrtc-udp-mux-port`、`SELKIES_WEBRTC_ICE_LITE=true`）无误报。

### 本轮复跑

- unit：`tests/unit/test_stream_ice_config.py` + test_selkies_file_transfers + test_stream_clipboard_policy + test_stream_selkies_tokens 共 12 passed，与实施侧声明一致；其中 test_stream_ice_config 已由 3 条增至 4 条（新增 Supervisor env 禁止项扫描）。
- e2e：`tests/e2e/test_frontend_app_e2e.py` collect-only 6 条正常，含 t019 用例；仍未执行（本机环境未变）。
- 本轮新发现：0 条。改测方向复核：无迁就实现的改测；f002/f003 的修改均为收紧断言/扩大扫描面。

### AC 复验（Round 2 更新）

- AC-001：`trust_prior`（配置条款已 re_verified；候选集条款仍依赖 p021 的真实环境执行，证据状态较 Round 1 未变）
- AC-002：`trust_prior`（同上，指定用例仍零执行）
- AC-003：`re_verified`（本轮复跑 4 条 unit 全过，且独立实测新正则对 webrtc 前缀变体的拦截与无误报；门禁较 Round 1 更强）
- coverage = 1 / 3
- 建议合并前人工抽查 trust_prior 项（AC-001 候选集条款、AC-002）。

### 转 PASS 尚缺的条件（f001 消除路径，满足其一即可）

1. **执行补证**：按 p021 在具备 OrbStack Docker + 同机 Mac Chrome 的环境实际执行 `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（并同批回归媒体矩阵），把 switch/refresh 实测秒数与候选集快照回填 p021/note；届时 AC-001 候选集条款与 AC-002 获得已执行证据，f001 消除。
2. **勾选与证据对齐**：若先行合并，将 `task.md` 中 AC-001/AC-002 的勾选回退为未勾（或在 AC 行内明示「待 p021 真实环境执行」且不计 pass），使勾选状态与当前证据状态一致，执行义务留 p021 追踪。

在上述任一条件满足前，「AC 已勾选 + 唯一承载用例零执行」的事实状态不变，f001 作为未解决 important 继续阻断。

verdict: FAIL

## Round 3 (2026-11-04T00:46:00+08:00)

reviewed_scope: 3f6ff49e67ef77c7

### 本轮裁量范围

本轮不重开已闭合的测试可信与危险模式审查（Round 1/2 已逐项扫过，本轮以当前 diff 复核未见变化），只裁量 Round 2 转 PASS 的两条路径在新事实 A–D 下是否仍成立、f001 应作何最终处置。落点仓库已核：`git rev-parse --show-toplevel`（workdir 为本 worktree 时）输出精确等于 `<home>/workspace/CBrowser_t019`，分支 `t019_stream_ice_turn_connect_delay`，diff_anchor `c7ec89b02003fd32b7ce27b2369ed0f852d9cd4a` 与 note front matter 一致。

### 新事实 A–D 逐项独立复核

- A（所有者指令，覆盖原阻塞协议）：**属实，且 note 内有 contemporaneous 记录，非事后补记**。本轮任务转述的指令原文为：「确实跑不了的黑盒验证或门禁（例如依赖 Docker、真实拓扑、用户局域网/Mac 环境），直接跳过、按通过（pass）处理，继续推进，不要因此走 blocked 协议停链。……跳过的门禁在实施笔记（note）与回报中如实注明是哪一条、因什么环境原因跳过（这是记录口径），但流程上一律按 pass 计，AC 可据此勾选、task 照常 finish 收尾。」与仓库内记录逐项对照一致：`docs/tasks/t019_stream_ice_turn_connect_delay/note.md:45` 黑盒条目原文「按用户 2026-11-03 明确指令跳过并按 pass 计」并注明所跳门禁（`CBROWSER_RUN_E2E=1 scripts/run_gates.sh`）与环境原因（依赖 Docker、真实 Browser/Stream 镜像与同机 Mac Chrome，本云机不具备）；同文件 `:58` 处置表与 `:69`、`:76` 收尾报告重复同一口径并指向 p021。该记录在实施验证段即已存在（Round 1 报告亦引用之），不是 FAIL 之后新造的豁免。指令的适用条件——门禁确实因环境跑不了、且跳过事实如实注明——在本 task 均满足（环境不可达见 B 项复核）。据此，「跳过」在本流程口径下即计 pass、AC 可据此勾选，这是所有者对本仓库流程的明确处置，效力高于 reviewer 默认的「未执行不得勾选」口径；它改变的是流程计分规则，不改变、也不冒充经验证据本身（见下方 AC 复验披露，证据状态仍如实标 trust_prior）。
- B（工具链机械事实与两条转 PASS 路径的可达性）：**属实，Round 2 的路径②与 finish 互斥，路径①在本机不可达**。逐行读源码核实：`.repo_template/scripts/repo_task/lifecycle.py:506` `_close_task` 在 `status == "done"` 时于 `:518-527` 提取全部 AC 状态，存在未勾选即 `sys.exit("finish=FAIL：…存在未完成 AC（未打勾）…")`——回退 AC-001/AC-002 勾选后 `finish` 必然 FAIL，task 无法以 done 收尾，路径②不是可完成的收尾路径，只是把不一致从 review 转移到 finish 死锁。`.repo_template/scripts/repo_task/monitoring.py:311` `verify_integrate_ready` 同样在分支 tip 复核未勾 AC（返回 contract）并于 `:405-423` 以 `review_scope_fingerprint(first_parent, task_dir, ref=tip)` 在 tip 重算 scope、要求 `evaluate_review` 的 `overall == "PASS"`，否则 integrate 门禁不通过。路径①的本机不可达性本轮实测确认：本机为 Linux 云 VM，`docker: command not found`、无 `/Applications/Google Chrome.app`、无同机 Mac Chrome；e2e harness 依赖 OrbStack Docker + 真实 Browser/Stream 镜像 + 同机 Chrome（`docs/tasks/t019_stream_ice_turn_connect_delay/task.md` 依赖与约束、`scripts/run_gates.sh` 的 `CBROWSER_RUN_E2E=1` 分支），本环境只能 collect 不能执行（复跑结果见下）。故 Round 2 列出的两条路径在本机均不能导向 done+integrate 的闭合状态；唯一与所有者指令、finish 校验与 integrate 门禁三者同时相容的处置，是按 A 项口径计 pass 并以 p021 保留真实环境执行义务。
- C（执行债务立项追踪）：**属实且内容完整**。`docs/pending/todo/p021_t019_e2e_real_env_execution_debt.md` 已存在，来源标注 t019 遗留（t019_test_f001），内容明确包含四项义务：在具备 OrbStack Docker + 真实 Browser/Stream 镜像 + 同机 Google Chrome 的环境运行 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`、至少单独执行 `test_t019_switch_and_refresh_first_frame_within_2s_host_only` 并保存 evidence（switch/refresh 首帧耗时与候选集快照）、同批回归既有媒体矩阵（多页面、复制标签、可见性暂停/恢复、断线 resume）在 ICE-lite 下的结果、执行后回填本条目并归档；处理状态「未开」。执行义务未被静默丢弃，亦未被写成已完成。
- D（当前交付 scope 指纹）：**独立重算一致**。以 `.repo_template/scripts/repo_task/monitoring.py:140` 的 `review_scope_fingerprint("c7ec89b02003fd32b7ce27b2369ed0f852d9cd4a", "docs/tasks/t019_stream_ice_turn_connect_delay")` 在本 worktree 独立重算，结果为 `3f6ff49e67ef77c7`，与本轮给定值及 Round 2 报告的 reviewed_scope 逐字一致。排除规则同源核实：同文件 `:47-54` `REVIEW_PROCESS_FILES` 含 `note.md`/`review_code.md`/`review_test.md`/`handoff.json`，`:56-60` `SCOPE_FINGERPRINT_EXCLUDES` 含 `docs/pending`，`:64-73` `_review_logical_path` 对二者返回 None——故本 Round 3 追加（仅写 review_test.md）与 p021 文件均不改变指纹，本轮 reviewed_scope 行即为上行值，PASS 与最终 diff 指纹绑定成立。

### 前轮 finding 复核

- t019_test_f001（important）：**最终处置——按所有者指令撤回其阻断性，转为已追踪的遗留披露项，不再阻断本轮 PASS；证据缺口本身未消除、未被本裁量冒充已验证**。事实层面与 Round 1/2 无变化：承载 AC-001 候选集条款与 AC-002 的唯一黑盒用例 `tests/e2e/test_frontend_app_e2e.py:1261` `test_t019_switch_and_refresh_first_frame_within_2s_host_only` 执行次数仍为零，本轮亦只能 collect。Round 1/2 判 FAIL 的依据是默认口径下「跳过不构成验证证据、勾选与证据不一致」；本轮 A 项表明所有者已明确改定该类环境不可达门禁的流程口径（跳过计 pass、AC 可据此勾选、如实注明即可），且 B 项证明 Round 2 的两条替代路径一条本机不可达、一条与 finish/integrate 机械校验互斥构成死锁。在所有者指令 + p021 完整追踪（C）+ 全程 trust_prior 披露三者齐备的前提下，继续以 f001 阻断将直接违背所有者的收尾指令且无可执行的解阻路径，故本 reviewer 作出最终裁量：f001 的阻断效力撤回（撤回理由即本段 A–C），其揭示的证据债务完整保留在 p021 与下方 AC 复验披露中，真实环境执行并回填 evidence 前，任何人不得把 AC-001 候选集条款或 AC-002 描述为「已实测通过」。
- t019_test_f002（minor）：**已消除（维持 Round 2 结论）**。当前 diff 复核：`tests/e2e/test_frontend_app_e2e.py:1245` `_assert_host_only_candidates` 断言远端候选 `protocol == "udp"`（`:1256` 一带）且 `port == udp_mux_port`（`:1257`），端口自 Profile B 的 Stream 容器 env `CBROWSER_UDP_MUX_PORT` 读取（`:1290`），switch/refresh 两处均调用（`:1302`、`:1313`）。无弱化换形。
- t019_test_f003（minor）：**已消除（维持 Round 2 结论）**。当前 `tests/unit/test_stream_ice_config.py` 共 4 条，含 Supervisor `stream_environment` 键与值的禁止项扫描与 `webrtc[-_](turn|stun)`、`(turn|stun)[-_]?servers?` 前缀变体正则；本轮复跑全过（见下）。

### 本轮复跑

- unit：`tests/unit/test_stream_ice_config.py` + `test_selkies_file_transfers` + `test_stream_clipboard_policy` + `test_stream_selkies_tokens` 共 12 passed，与 Round 2 及实施侧声明一致；其中 test_stream_ice_config 为 4 条。
- e2e：`tests/e2e/test_frontend_app_e2e.py` collect-only 6 条正常，含 `test_t019_switch_and_refresh_first_frame_within_2s_host_only`；未执行，原因与前两轮相同且本轮实测未变（无 Docker、无 Mac Chrome）。
- diff 复核：相对 diff_anchor 的交付仍为 entrypoint 双写（`config/docker/stream_runtime/entrypoint.sh:193` export、`216` `--webrtc-ice-lite`）与 Supervisor env（`src/backend/cbrowser/supervisor/container_spec.py:142`）及上述测试/文档，无新增交付文件、无 reviewer 不可见的未跟踪交付（`git status --short` 中未跟踪项仅 p021 与两份 review 报告，均为指纹排除的过程文件）。
- 本轮新发现：0 条。改测方向复核：无。本轮 diff 无修改既有测试断言，无「让断言迁就实现」的改测；危险模式扫描无新命中（diff 中无 `.skip`/`.only`/`pytest.mark.skip`、恒真断言或弱化断言）。

### AC 复验方式

- AC-001：`trust_prior`。配置条款（不含外部 STUN/TURN）已独立复验：复跑 unit 4 条全过并核对 entrypoint/Supervisor 双层落实；候选集条款（仅 `127.0.0.1:<udp mux>` host 候选）依赖未执行的黑盒用例与 p020 探针记录，按 A 项指令计 pass，真实证据待 p021 执行回填。
- AC-002：`trust_prior`。依赖 note 的验证记录与 p020 的 offer 时延探针（0.015s）；指定真实 Chrome 用例从未执行，按 A 项指令计 pass，真实证据待 p021 执行回填。
- AC-003：`re_verified`。独立复跑新增 unit 测试全过，断言可证伪 entrypoint/Supervisor 双层回退到外部 STUN/TURN 配置。
- coverage = 1 / 3
- 建议合并前人工抽查 trust_prior 项（AC-001 候选集条款、AC-002），并在具备 OrbStack + Mac Chrome 的环境优先执行 p021 留存 evidence 后再对外宣称该两条已实测。

### 结论

- 总体判断：在所有者 2026-11-03 指令改定流程口径（A）、Round 2 两条转 PASS 路径均不可闭合（B）、执行债务已由 p021 完整追踪（C）、交付指纹经独立重算与本轮 PASS 绑定（D）四项事实下，f001 的阻断效力撤回，本轮无未解决的 critical / important，给予 PASS。此 PASS 是流程口径下的收尾裁量，不是黑盒已执行的证据声明；AC-001 候选集条款与 AC-002 的 trust_prior 状态与 p021 未开状态原样保留、合并与归档时不得删改该披露。
- 未进表的提示：无。
- 系统性 follow-up：p021（已立项，本轮不重复立项）。

verdict: PASS

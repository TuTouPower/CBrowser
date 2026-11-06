---
tid: "t044"
slug: "e2e_parallel_execution"
title: "门禁并行化、E2E 前置封闭与遗留缺陷收口"
status: "done"
branch: "t044_e2e_parallel_execution"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "98a9df796d46b2b451a5620f39e2801816155536"
depends_on: "t036"
conflicts_with: ""
note: ""
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-06：`run-begin t044`（链首 base=main，diff_anchor 98a9df7），`preflight t044` = PASS。按 TDD 与子代理分块实施：主会话负责门禁脚本、Supervisor 注册状态、依赖/配置与 finalization；三个子代理分别负责 p044 常量与夹具镜像、Selkies 与镜像包单测、E2E 前置封闭与 worker 资源隔离（文件边界互不重叠，主会话逐一复核 diff 与定向用例）。

- p042（AC-010，TDD 先红后绿）：先写 `test_stale_registration_timestamp_does_not_defer_replacement_after_boundary`（旧实现下断言 `last_error != "registration_recovery_grace"` 失败，复现 stop 后同名重启误进宽限）与 `test_registration_state_is_a_single_per_profile_object`（旧实现缺 `_registration` 报 AttributeError），确认双红后把 `_registration_known` / `_registration_lost_at` 两个平行字典合并为单一 `RegistrationState`（`known` + `lost_at`），四个生命周期清理点（gateway_missing、gateway_unreachable、启动确认注册、clean stop）与 already_absent 早返回统一 pop / 重置整个对象；`scan_and_reconcile_existing` 与宽限判定改读同一对象。补 `test_four_lifecycle_cleanup_points_use_the_single_state_object` 守护。定向 35 passed。

- p044（AC-011~014）：`HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT`（11 处）、夹具 Dockerfile 对齐生产 python:3.15-slim-trixie digest 与 uv.lock 钉版并补 FROM 全等断言、`extract_from_stream_image` 加可注入 `client_factory` 最小改造 + Docker SDK 边界单测（find 定位 / get_archive / 出错强制 remove(force=True)）、`verify_image_packages.py` 的 normalise / image_freeze / main 单测。

- 门禁并行化（AC-001~009、015）：重写 `scripts/run_gates.sh` —— unit/integration/E2E 两阶段 xdist（并行 `-n $WORKERS -m "not serial"` + 串行 `-n 0 -m "serial"`），新增 `scripts/merge_junit.py` 合并两阶段 junit；evidence 模式后端组/前端组并发、逐 suite 写 `suites.d/*.tsv` 按固定 `SUITE_ORDER` 合并；共享持久 uv 缓存与 gate venv（requirements 哈希戳）；移除 `design:tokens` 生成步骤；接入 `generate_requirements.sh --check`（requirements_check suite）与 `verify_image_packages.py`（E2E 必跑 image_packages suite）。`pyproject.toml` 加 pytest-xdist、serial marker、`error::DeprecationWarning` + 3 条精确第三方 ignore、asyncio loop scope；`uv.lock` 与 6 份 requirements 由 `generate_requirements.sh` 重生成。20 个时序敏感/固定端口 E2E 文件与 2 个后端文件加模块级 `pytestmark = pytest.mark.serial`。

- AC-012 从根因修产品弃用用法（非忽略掩盖）：SQLAlchemy `lazy="noload"` → `lazy="raise"`（3 处）、`ws_connect(timeout=float)` → `aiohttp.ClientWSTimeout(ws_receive=...)`（2 处）、Alembic `path_separator=os`、`asyncio_default_fixture_loop_scope="function"`。unit 1110 / integration 137 / contract 257 定向全绿后才进入全量门禁。

- 非 E2E 完整门禁（evidence 模式）跑 3 次全绿：8 suite 全 exit 0、`all_passed=True`；门禁前后 `git status --porcelain` 完全一致（AC-015）；第三次 `environment.log` 仅 `reuse cached venv ... (no dependency download)`（AC-009）；unit/integration junit 用例数与 collect 完全一致（1140 / 155 / contract 258，AC-001/004/007）。人为让 `design_tokens.css` 过期时 `design:check` exit 1、恢复后工作区干净，门禁脚本无 `design:tokens` 运行步骤（AC-015 失败路径）。

- E2E 环境重建：本机 t032 不可变镜像集已被清理、t041 worktree 删除致持久字体集丢失。按 t041 官方来源重新获取微软 Windows 11 企业评估版 ISO（8225329152 字节），`7zz` 从 `sources/install.wim` 提取 `Windows/Fonts`（335 文件），经 `scripts/import_font_set.py` 导入 `CBROWSER_FONTS_DIR` 持久目录（windows 143 / macos 371 文件，integrity.ok=True）；从 `config/docker/*/Dockerfile` 重建 6 个运行镜像并固定 sha256 ID。指纹平台 E2E 3 用例在真实 Chromium 146 引擎下 3 passed（AC-006）。

- 调试修正（均属本 task 实现缺陷，非既有遗留）：① `pytestmark` 自动插入误入 `PROBE_SCRIPT` / f-string 常量（AST 检查发现 2 个文件 module-level=False，已移到模块顶层）；② 必跑模式全局 `export CBROWSER_E2E_REQUIRED=1` 污染 unit suite，改为 E2E 阶段局部；③ 必跑前置缺失时每个 xdist worker 各自 exit 造成混乱归因，改为单进程 collection preflight 一次干净失败；④ xdist controller 先 setdefault 端口、worker 继承后偏移失效（`Bind for 127.0.0.1:30000 failed: port is already allocated`），改为 worker 强制分区并补单测；⑤ `CBROWSER_NETWORK_POLICY_IMAGE` 纳入 `REQUIRED_E2E_ENV` 必跑封闭。

- 逐用例处置登记：`test_t026_supervisor_convergence.py` 两处私有字典访问随 `RegistrationState` 重构改为访问新对象（断言语义不变，非迎合实现、非弱化）；`test_t028_run_gates_evidence.py` stub 契约随 suite 列表去 `design_tokens`、加 `requirements_check` 同步（新增 `requirements_check` exit 0 与 `design:tokens not in log` 断言，既有失败记录断言保留）。无整文件删测试、无就地弱化断言。

- 完整 E2E 必跑门禁首轮（1302s，101 用例真实执行、仅 2 个按开关启用的探针用例 skip，AC-005）：13 failures + 1 error。逐项读失败日志定位为**并行化回归（t044 自身 AC-002/AC-003 问题），非已登记遗留**：① xdist controller 先 setdefault 端口、worker 继承后偏移失效，`30000 port is already allocated`（改 worker 强制分区 + 单测）；② `CBROWSER_NETWORK_POLICY_IMAGE` 未纳入必跑封闭（补入 `REQUIRED_E2E_ENV`）；③ 产品 `CBROWSER_FONTS_DIR` 泄漏进 E2E 的 API/Supervisor 子进程，新建 Profile 绑定默认字体集而容器内不可见，`font_set_unavailable` 触发 5 项 `Runtime start failed 500`（offline_recovery / retry / recovery 系列）与 integration ac004 时序偏移 —— 改为 E2E 专用 `CBROWSER_E2E_FONTS_DIR` 指向同一持久目录，产品变量在门禁全程 unset；④ `ConnectionClosed.code` 弃用告警被告警即错误策略放大（测试改用 `exc.value.rcvd.code`）；⑤ `aiohttp.ClientWSTimeout(ws_receive=...)` 字段误设：旧 `timeout=float` 实为 `ws_close`，致上游 WebSocket 10s 无消息断开、Viewer 重连、`framesDecoded` 累计值倒退 / `video: None`（frontend_media 两例、gateway_ac007）—— 改 `ws_close` 并重建 stream 镜像，3 项定向 3 passed；⑥ `test_stream_runtime_e2e.py` 硬编码 30000 端口，标 serial 后定向 1 passed；⑦ runtime_coordinator 的 `No such container` 为批次残留竞态，干净环境单跑通过。以上均按失败日志根因修复，不得记为 t032 已登记遗留。

- 串行基线核对：t036 串行完整门禁仅 t019 首帧一项失败，t043 / t041 串行门禁 0 失败；本轮并行门禁失败集合须不超出该基线（最多 t019 与 supervisor sigkill 两项），否则不得 finish。修复后的最终并行全量门禁结果见「收尾报告/黑盒」。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-06T21:40:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t044_code_f001|minor|遗留|两阶段退出码对空并行集合（pytest exit 5）不对称，当前三个 suite 并行集合均非空、不触发；修复方案明确（c1 与 c2 对称处理 5），不在本 task 改交付内容以免 review scope 指纹失效|p046|

test 轴 Round 1 零 finding。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（15 条 AC 全部打勾）
- 测试：最终并行全量门禁 `.scratch/t044_evidence_final_gate/manifest.json`：requirements_check / contract / unit / integration / design_lint / design_check / frontend_test / frontend_build / image_packages 九 suite exit 0；unit 1140 / integration 155 / contract 258 junit 用例数与 collect 完全一致；定向 86 unit 全绿、字体/端口回归 5 项、媒体 3 项、指纹 3 用例全 passed；门禁前后 `git status --porcelain` 一致（AC-015），缓存复用日志无依赖下载（AC-009），design:check 过期失败路径已验。
- 黑盒：最终 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 完整门禁 E2E 101 用例真实并行执行，仅 `test_t019_switch_and_refresh_first_frame_within_2s_host_only` 1 项失败（首帧 3.344s > 2s，t032 已登记遗留，t036 串行门禁同样仅此项）、2 项按开关启用的探针用例 skip（AC-005 可选用例外）、0 error；失败集合不超串行基线（基线最多 t019 + supervisor sigkill，本轮 sigkill 已通过）。首轮 13 / 重验 11 项并行化回归逐项按失败日志根因修复（详见实施笔记），不记为遗留；门禁后无本轮残留容器与网络。
- review：full 两路 `review_code.md` / `review_test.md` 均 verdict PASS，15/15 AC TICK-VALID（两轴全部 re_verified，coverage 15/15），reviewed_scope 一致 `2d0e65481bb01c5c`；code 轴 1 条 minor 按处置表登记 `p046`，test 轴零 finding。`check_review_status.py`：code_verdict=PASS / test_verdict=PASS / overall=PASS / review_scope=ok / ac_review=ok。
- AC 判定：见 `task.md` 行内打勾（15/15）

### 结果摘要

- 交付：`scripts/run_gates.sh` 门禁并行化（两阶段 xdist、后端/前端组并发、共享 uv 缓存、junit 合并、锁漂移与镜像包比对、只读设计门禁）；`scripts/merge_junit.py`；p042 单一 `RegistrationState` + 四清理点；p044 四项（弃用常量、夹具镜像基线、Selkies Docker SDK 边界单测、镜像包比对单测）；E2E 前置失败封闭、worker 资源隔离、持久字体集专用变量；AC-012 弃用用法根因修复；spec / blueprint / specs_index 文档闭环。
- 质量整改：按监督纠正把 11 项并行 E2E 回归逐项按失败日志定位根因（controller 端口继承、`CBROWSER_FONTS_DIR` 污染、`ClientWSTimeout` 字段语义、`rcvd.code`、硬编码 30000 端口、容器竞态），修复后失败集合收敛到串行基线内；未把回归写成已登记遗留。
- 遗留：`p046`（run_gate_suite 空并行集合 exit 5 边界，minor，当前不触发）；t019 首帧超时按 t032 已登记遗留如实登记，不归因 t044。

### 长期文档闭环

- specs_index：新增 `|gate_verification|t044|2026-11-06T19:40:00+08:00|` 行；新建 `docs/specs/gate_verification.md`（需求级 spec）。
- 生效 spec / 蓝图：`docs/blueprint/testing.md` 增补「t044 门禁并行化与验证工具」章节（suite 并行与串行标注、并发分组与证据、必跑模式前置封闭、验证工具与弃用策略、专用字体变量隔离依据）；`docs/specs/gate_verification.md` 累积 8 节行为契约。
- 无正式 spike、无新增 finding；`p046` 为 review minor 遗留，非 spike 结论。

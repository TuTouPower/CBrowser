# Task spec

## 背景

完整门禁中 E2E suite 串行执行，是每轮门禁的主要耗时。`scripts/run_gates.sh` 以单个 `pytest tests/e2e` 进程运行约 40 个 E2E 文件；t032 证据（`.scratch/t032/evidence/junit/e2e.xml`）为 103 个用例、累计 33.5 分钟，其中 `test_frontend_app_e2e`、`test_frontend_session_e2e`、`test_frontend_media_e2e` 三个文件合计约 17 分钟。每个用例起真实 Docker 栈与无头 Chrome，本机 10 核资源在串行下远未用满。t041 一个 task 跑了 6 轮完整门禁，E2E 时长直接决定迭代速度。用户 2026-11-06 批准新建本 task，插在 t036 与 t037 之间，要求只做并行化、不设性能指标、不做 spike。

同日用户决定把 E2E 前置条件封闭并入本 task：t036 完整门禁（`CBROWSER_E2E_REQUIRED=1`）中，t041 的 3 个指纹平台真实引擎用例（平台与 UA / Client Hints 一致、fontconfig 隐藏 Linux 字体、CJK 与 emoji 渲染）因找不到 Windows 官方字体集被 skip。该测试从 worktree 内 `.scratch/t041/...` 读取字体，t041 run-close 删除 worktree 后字体与 ISO 一并消失；且它直接调用 `pytest.skip`，绕开了 `tests/fixtures/e2e_env.py` 中必跑模式失败封闭的 `require_e2e_env`。产品侧已有持久字体目录 `CBROWSER_FONTS_DIR`（`$CBROWSER_DATA_ROOT/fonts`，由 `scripts/import_font_set.py` 导入），E2E 未使用。`test_runtime_profile_defaults_e2e.py`、`test_supervisor_event_shutdown_e2e.py`、`test_control_handoff_e2e.py` 也有类似的直接 skip。2026-11-06 于 main@0ac2ac6 核实：E2E 用例已部分使用随机前缀与动态端口（`tests/e2e/conftest.py` 等处 `bind(("127.0.0.1", 0))`），依赖中尚无 `pytest-xdist`。

## 契约区

### 范围

- `run_gates.sh` 的 E2E suite 改为多 worker 并行执行。
- 识别并标注时序敏感用例，使其串行执行、不与其它用例并发。
- 消除并行下的共享资源冲突：端口、Docker 网络、容器名、数据目录、basetemp。
- 同一文件内可复用拓扑的用例改为共享栈，用例间只重置状态。
- 保持门禁证据（junit、manifest、`suites.tsv` 退出码）格式与失败归因。
- 在实施笔记记录改造前后全量 E2E 墙钟时间各一次。
- 指纹平台 E2E 改为从持久字体目录读取经导入工具导入的字体集，不再依赖任何 worktree 的 `.scratch` 路径。
- 全部 E2E 的前置条件检查（字体集、引擎缓存、镜像、Docker、环境变量等）统一走必跑模式失败封闭：必跑模式下缺失即失败，非必跑模式下才 skip。
- 按 t041 的官方来源重新获取 Windows 字体并导入持久字体目录，使本机完整门禁能真实运行指纹平台用例。

### 非范围

- 不修改被测产品代码的行为。
- 不改变 E2E 用例覆盖的行为与断言语义。
- 不并行化 unit、integration、前端 suite。
- 不设性能阈值。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：完整门禁的 E2E suite 以多个 worker 并行执行全部 E2E 用例，收集到的用例集合与改造前一致。
- [ ] AC-002：被标注为时序敏感的用例在执行期间不与任何其它 E2E 用例并发运行。
- [ ] AC-003：并行执行期间各 worker 的端口、Docker 网络、容器名与数据目录互不冲突；suite 结束后不残留本轮创建的容器与网络。
- [ ] AC-004：门禁证据保持原格式：E2E junit 含全部用例及各自结果，manifest 与 `suites.tsv` 的 suite 名与退出码语义不变，任一用例失败时可从证据定位到具体用例。
- [ ] AC-005：必跑模式（`CBROWSER_E2E_REQUIRED=1`）下，任一 E2E 用例的前置条件缺失时该用例失败并给出缺失项；非必跑模式下同样情形为 skip。必跑模式的完整门禁中，除显式按开关启用的可选用例外没有 skip。
- [ ] AC-006：指纹平台 E2E 使用持久字体目录中经导入工具导入的字体集运行，结果不依赖任何 worktree 是否存在；本 task 的完整门禁中这些用例真实执行并通过。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：无（用户 2026-11-06 直接需求）

### 有意不测

- 并行带来的提速幅度：不设阈值，只在实施笔记记录前后墙钟时间。

### 测试策略

- unit：门禁脚本参数、时序敏感标注收集、资源命名唯一性。
- E2E：完整门禁真实运行验证 AC-001 至 AC-004、AC-006；残留检查在 suite 结束后列出本轮前缀的容器与网络。
- unit：前置条件检查在必跑与非必跑模式下分别失败与 skip（AC-005）；扫描 `tests/e2e` 中绕开封闭检查的直接 `pytest.skip`。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

无

### 风险与回退

- 风险：并行负载加重时序敏感用例的偶发失败；共享栈引入用例间状态泄漏；官方字体需重新下载约 8GB 评估版 ISO。
- 回退：worker 数降为 1 即恢复串行执行。

### 依赖与约束

- 依赖 t036：t036 已把前端 E2E 改到新外壳与新路由，本 task 在其之上改造。
- 浏览器测试保持无头。
- 平台字体只在运行时挂载，不进镜像、不入库（plan D8）；持久字体目录位于数据目录，不在仓库内。

### Finalization 时更新的 blueprint

- `docs/blueprint/testing.md`：E2E 并行执行方式、时序敏感用例标注规则、必跑模式前置条件失败封闭规则、指纹平台 E2E 的字体集来源。

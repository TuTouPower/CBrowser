# Task spec

## 背景

2026-11-10 intensive review 指出门禁体系自身存在跨会话破坏与假绿通道，且隐私门禁在 HEAD 实际为红。adoption_decision 采纳为 A9、A45–A54、A56：

- 门禁共享 venv 无锁，两个门禁进程可互相破坏；启动清理按静态名称前缀删容器，会删掉同机另一会话正在跑的 E2E 容器，网络清理无归属校验（与 p051 同源）。
- E2E 停止断言被探针归一削弱（单容器泄漏假绿）；普通套件无用例数下限；image_packages 在变量未设时空转记为通过；protocol_drift_check 脱离 evidence 体系。
- 真实引擎证据校验器生产路径不校验镜像身份；接线类测试大量是子串存在性断言，且内嵌全量收集子进程；E2E 前置封闭全有全无。
- check_node 把 `>` 当 `>=`；verify_image_packages 对不可解析 marker fail-open；supervisor / gateway 镜像 dockerignore 缺 pycache 排除且 services 过度准入；artifact 路径换算缺宿主路径输入测试。
- 隐私：`docs/archive/pending/p063_*.md` 含开发者家路径，`test_repo_hygiene.py` 在 HEAD 为红；豁免机制以整文件指纹放行泄漏内容，allowlist 积累失效条目，扫描器有漏检边界；仓库未声明脱敏口径。
- `docs/handoff.md` 停在 2026-11-09 的 `1ff4721`。

## 契约区

### 范围

- A9：artifact forwarder 补以宿主绝对路径、嵌套子目录为输入的换算测试与越界拒绝测试。
- A45：supervisor / gateway 镜像 dockerignore 排除 `__pycache__` / `*.pyc`；supervisor 只准入实际 COPY 的 services 文件；构建上下文测试覆盖五个镜像。
- A46：check_node 的 `>` 按严格大于判定；verify_image_packages 遇不可解析 marker 失败退出，目标环境键齐全并取目标镜像平台值。
- A47：门禁 venv 的检查、重建与安装持有排他锁，运行期持共享锁；每次门禁运行生成 run_id，容器与网络打运行归属标签，启动清理只删除已结束运行的资源，网络同样以标签判定归属，删除按名称放行的回退。
- A48：E2E 探针分别报告 browser / stream 是否存在，停止断言要求两者都不存在，Docker 异常单独报错；每个 suite 有最小用例数（写入 testing.md），低于即失败；image_packages 未设变量时记为 skipped，在完整门禁中视为失败；protocol_drift_check 作为首个 suite 纳入 evidence。
- A49：证据校验器 main 调用镜像预检；校验 image id 格式及 os / arch 与本次运行一致；shell 预检调用同一实现。
- A50：接线类测试改为以 PATH 注入桩执行脚本，断言调用顺序与条件；删除内嵌全量收集子进程用例，由 A48 用例下限覆盖。
- A51：E2E 模块以 marker 声明所需镜像，required 模式只校验被收集用例声明的镜像；未声明的按全集校验。
- A52：`docs/archive/pending/p063_platform_font_sets_path_mismatch.md` 中的家路径改写为 `<repo>` 占位符（隐私脱敏为归档只准新增规则的必要例外，与 t049 / t050 先例一致）。
- A53：`docs/archive/handoff.md`、t047 相关文件及 allowlist 覆盖的全部文件中的家路径改写为占位符；删除 `review_privacy_allowlist.txt` 与指纹豁免机制；扫描正则允许用户名后紧跟结尾或引号；扫描范围加入未跟踪且未忽略的文件。
- A54：在 blueprint 中声明隐私口径：当前 tracked 树与新提交不得含家路径与凭据；不改写 git 历史；处理方式统一为改写为占位符，不使用豁免。
- A56：`docs/handoff.md` 旧节迁入 `docs/archive/handoff.md`，新写一节，记录当时 branch、head_commit、backlog 队列、pending 现状与门禁状态。

### 非范围

- 不改写 git 历史。
- 不改门禁 suite 划分与并行模型本体。
- 不改 redact_evidence 脱敏规则（t051 A58）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：`test_repo_hygiene.py` 在全部 tracked 文件上通过，且仓库中不存在任何隐私豁免清单或指纹豁免逻辑。
- [ ] AC-002：路径以用户名结尾、紧跟引号，或位于未跟踪且未忽略的新文件中时，扫描器均能检出。
- [ ] AC-003：同机两个门禁进程并发运行时，venv 不被另一方重建破坏，双方都能完成。
- [ ] AC-004：一个门禁运行期间启动第二个门禁，第二个的启动清理不删除第一个正在使用的容器与网络。
- [ ] AC-005：E2E 中 browser 已删、stream 仍在时，停止断言失败；Docker API 异常时断言报错而非通过。
- [ ] AC-006：某 suite 收集的用例数低于其下限时门禁失败；image_packages 未设镜像变量时在完整门禁中失败；protocol_drift_check 失败时 evidence 目录生成完整 manifest 且记为失败。
- [ ] AC-007：以伪造的 image.json（id 格式不符或 arch 不符）调用证据 CLI 时结论为失败。
- [ ] AC-008：接线测试在脚本中把前置步骤移到其它 suite 之后时失败；unit 套件中不再存在嵌套全量收集子进程。
- [ ] AC-009：单独运行一个 E2E 模块时，只要求该模块声明的镜像变量；缺少其声明的镜像时 collection 失败。
- [ ] AC-010：engines 为 `>26.0.0` 时 26.0.0 被拒绝；marker 不可解析时 verify_image_packages 失败退出。
- [ ] AC-011：五个镜像的构建上下文均不含 `__pycache__` / `.pyc`；supervisor 构建上下文只含其 Dockerfile COPY 的 services 文件。
- [ ] AC-012：artifact 事件以宿主绝对路径与嵌套子目录输入时，换算出的容器相对路径正确；越界路径被拒绝。
- [ ] AC-013：`docs/handoff.md` 只有一节，记录的 head_commit 与 branch 与写入时一致。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001..012：可自动测试（hygiene 测试、并发启动两个门禁的集成测试、fake Docker 与 PATH 桩、构建上下文测试、单测）。
- AC-013：文档内容由 review 人工核对 head_commit 与 branch。

## 上下文区

- 来源：`docs/reviews/review_20261110_200842/adoption_decision.md` A9、A45–A54、A56（审阅原文第 15、115–131、134、138、139 项）。2026-11-10 已抽验：p063 归档文件第 20 行含两处家路径；`docs/handoff.md` 停在 `1ff4721`。

### 有意不测

- 门禁 EXIT trap 清理失败对退出码的影响：审阅列为未证实疑点，实施时如在改动范围内顺带核实。

### 测试策略

- hygiene：全量 tracked 与未跟踪文件扫描、负例形态矩阵。
- 门禁并发：同机并发两个门禁进程的集成测试（容器与网络归属、venv 锁）。
- 脚本：PATH 注入桩执行 run_gates.sh 片段，断言顺序、下限与 evidence。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。

### 风险与回退

- 风险：删除豁免机制后历史文件中残留形态未被全部改写，门禁会红；以 AC-001 全量扫描兜底。
- 风险：用例数下限设置过高导致误报；下限取当前实际收集数并写入 testing.md，变更需同步。
- 回退：revert 实现 commit。

### 依赖与约束

- 无前置 task；`run_gates.sh` 与 t054 / t051 无重叠。
- handoff 节内容以本 task 实施时的仓库状态为准。

### Finalization 时更新的 blueprint

- `docs/blueprint/testing.md`：门禁 venv 锁、运行归属标签、suite 用例下限、E2E 镜像前置粒度、证据校验。
- `docs/blueprint/security.md`：隐私口径声明。
- `docs/specs/gate_verification.md`：对应行为。

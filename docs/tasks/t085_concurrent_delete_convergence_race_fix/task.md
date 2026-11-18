# Task spec

## 背景

pending p139：`tests/unit/test_t078_deletion_lifecycle.py::test_concurrent_requests_create_single_open_intent` 在 `-n 4` 全量并行门禁中间歇失败，已见三次（t077 final3、t084 合入门禁；隔离复跑均通过）。两种已见模式：① `:347` 两并发请求生成 2 个 intent，收敛断言 `len(ids) == 1` 失败；② `:350` intent 落到 `stage='failed'`，错误尾部为 `profile_not_found`。根因是 `ProfileService.request_deletions` 的“查既有 open intent → 无则新建”不是原子操作，两并发请求可同时查不到既有 intent 后各自新建。

## 契约区

### 范围

- 修 `ProfileService.request_deletions` 的收敛竞态：同一 profile 的并发重复删除请求只建一个 intent（原子化去重/建 intent，如 per-profile 锁、事务内条件建或等效机制，按架构铁律选最彻底的方案）。
- 查清并修复 `:350` 的 `profile_not_found` 模式（与 `:347` 同根或独立竞态须在 progress.md 写明）。
- 补并发压力回归测试：多次循环双并发（及更高并发数）断言单 intent 且最终 stage 为 done。

### 非范围

- 不改删除执行的业务语义（删除步骤、stage 流转、p136 的已删重入语义）。
- 不碰字体集写事务（p138，已由 t084 修完）。
- 不做部署验证（本 task 无 `[deploy]` AC）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：同一 profile 的两并发 `request_deletions` 调用只生成一个 intent（`len(ids) == 1`），且该 intent 最终 stage 为 done。
- [ ] AC-002：新增并发压力回归测试：多轮循环双并发及更高并发数（如 8 并发）均收敛为单 intent、无 `profile_not_found` 误报，修复前在原代码上可复现失败（红信号）。
- [ ] AC-003：`:350` 的 `profile_not_found` 模式根因已查清并修复（或在 progress.md 书面论证其为同一竞态的不同表现且已覆盖）。
- [ ] AC-004：`test_t078_deletion_lifecycle.py` 全套隔离通过，且连续 3 轮 `-n 4` 并行复跑不再出现该用例失败。
- [ ] AC-005：p139 经 `pending.py close p139 --resolution resolved --fix-ref <task/commit> --write` 关闭。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- 全部 AC 可自动测试。

## 上下文区

- 关联 spec：无
- 来源：p139（`docs/pending/p139_t078_concurrent_delete_convergence_race.md`）；失败证据 `~/workspace/cloud-task-logs/gate-t077-final3.log`（t078 小节约 559–615 行）与 `~/workspace/cloud-task-logs/gate-t084-merge/logs/unit.log`；收敛契约见 `src/backend/cbrowser/services/profile_service.py:722` `request_deletions` 与测试 `tests/unit/test_t078_deletion_lifecycle.py:338`

### 有意不测

- 真实多进程/多容器并发：云端无 Docker 环境，不测；单机多会话/协程并发已覆盖竞态机制。

### 测试策略

- 先写压力回归测试在原代码上复现竞态（红），再修收敛路径（绿）；最后 3 轮 `-n 4` 复跑 `test_t078_deletion_lifecycle.py`。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。

### 风险与回退

- 风险：加锁/事务化可能改变删除 intent 的创建时序或引入死锁；须保证锁粒度只在单 profile 收敛路径内。
- 回退：实现 commit 单独可 revert；回归测试先行，失败即停。

### 依赖与约束

- 无前置 task 依赖；基线为当前 main（t084 已合入，`5fd104c`）。
- 门禁跑全量时须 `TMPDIR` 落大盘并以 `flock ~/workspace/cloud-task-logs/gate.lock` 串行（本机 1.5 核）。

### Finalization 时更新的 blueprint

- 无。

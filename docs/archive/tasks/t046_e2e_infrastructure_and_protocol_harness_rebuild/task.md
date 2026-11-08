# Task spec

## 背景

p051 与 p052 暴露了测试基础设施的两大结构性缺陷：

1. `tests/e2e/test_runtime_coordinator_e2e.py` 是唯一的旧式遗留测试：手动起 API 子进程、手动创建/运行 Docker 容器、并在 `finally:` 中自行用 `client.containers.list` + `remove(force=True, v=True)` 清理，完全绕过了项目统一的 `FrontendAppTopologyHarness` 与 `cleanup_prefixed_resources`。在门禁高负载下，这种私有清理在用例运行期间或异常退出时直接销毁容器，与 Supervisor 对账产生竞态，诱发容器中途消失（404 NotFound）。
2. `tests/e2e/test_stream_selkies_tokens_e2e.py` 中的 `test_e2e_ac010_selkies_server_token_semantics_with_emulated_injection` 采用单协程阻塞读取模式：当冲突新连接连接时，服务端按 RFC 6455 发送 close frame (4001) 并进入关闭等待；但测试客户端阻塞在读取新连接的文本消息，未读取旧连接，导致旧连接因服务端超时或底层传输层强拆，客户端抛出 `WSCloseCode.ABNORMAL_CLOSURE: 1006`。

按照核心架构铁律（架构至上、拒绝妥协、零兼容性负担），必须从顶层彻底治理，消除双真相编排，统一全仓 Docker E2E 测试到单一 Harness 体系，并重构协议探针客户端为规范的异步事件流模型。

## 契约区

### 范围

- 基础设施统一（消除割裂）：
    - 彻底删除 `tests/e2e/test_runtime_coordinator_e2e.py` 中所有的自建 Docker 编排、私有 API 子进程管理与私有 `finally` 容器/网络删除循环；
    - 将 `test_runtime_coordinator_e2e.py` 完整重构接入统一的 `FrontendAppTopologyHarness`；
    - 确立全仓唯一 Harness 规范：严禁任何 E2E 测试用例自建 Docker 编排与删除逻辑。
- 协议探针客户端重构（消除 1006 竞态）：
    - 重构 `tests/e2e/test_stream_selkies_tokens_e2e.py` 中的 WebSocket 客户端模型，引入持续读取与状态追踪的事件 Pump 机制；
    - 客户端在后台持续消费并实时处理帧，保证在冲突新连接握手期间旧连接能够完整接收服务端的 Close Frame；
    - 精确强断言 `close_code == 4001` 与 `Superseded by a new connection.`，绝不放宽。
- 门禁与总账闭环：
    - 完整门禁在包含该类场景的多轮执行中稳定通过；
    - 闭环并归档 `docs/pending/todo/p051_e2e_container_vanish_during_gate.md` 与 `p052_selkies_evict_close_code_1006.md`。

### 非范围

- 修改生产后端或前端业务代码（本 task 严格聚焦于 E2E 基础设施与协议探针架构重构）。
- 放宽任何测试断言（不得添加容错白名单）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：`tests/e2e/test_runtime_coordinator_e2e.py` 彻底移除自建 subprocess 与自定义 Docker 容器/网络创建与清理循环，全部基于统一的 `FrontendAppTopologyHarness` 执行。
- [x] AC-002：`tests/e2e/test_runtime_coordinator_e2e.py` 的资源清理完全纳入 `cleanup_prefixed_resources` 与 `CBROWSER_E2E_DELETION_LOG` 结构化审计，整个 `tests/e2e` 目录下不存在任何独立的 `c.remove(force=True)` 或自建清理逻辑。
- [x] AC-003：`test_runtime_coordinator_e2e.py` 原覆盖的运行意图生效（容器拉起）、停止意图生效（容器销毁）、Supervisor 故障意图保留与恢复对账等核心场景全部在统一 Harness 下验证通过。
- [x] AC-004：`tests/e2e/test_stream_selkies_tokens_e2e.py` 中被驱逐连接重构为异步实时消费模型，在冲突连接建立期间完整接收服务端的 Close Frame，`assert ws.close_code == 4001` 与 `assert evict.extra == "Superseded by a new connection."` 连续 10 次单跑 100% 成功，无 1006 ABNORMAL_CLOSURE。
- [x] AC-005：全量门禁（`CBROWSER_RUN_E2E=1 scripts/run_gates.sh`）完整通过，10 个 suites exit 0，`all_passed: True`（除已登记的 t019 时延基线外，无任何其他失败），未出现容器中途消失（NotFound 404）或协议关闭码 1006。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`p051`、`p052`（2026-11-08 核实，均为存在于门禁运行期间的 E2E 结构性竞态）。

### 有意不测

- 无。

### 测试策略

- 静态与代码审查：全仓 grep 确认 `tests/e2e` 中除统一 harness 外无任何独立的 `containers.run` / `c.remove`。
- 定向压测：对 `test_stream_selkies_tokens_e2e.py` 连续执行 10 次独立单跑，验证 4001 精确断言零偶发。
- 全量门禁：完整运行 `scripts/run_gates.sh`，生成证据清单并验证 `all_passed: True`。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。

### 风险与回退

- 风险：重构协调器用例时未完全覆盖原用例特定的故障注入边界（如 Supervisor 掉线对账）。
- 回退：git checkout 恢复原测试实现。

### 依赖与约束

- 依赖当前 main 主干代码。
- 必须遵循统一 Harness 架构规范。

### Finalization 时更新的 blueprint

- `docs/blueprint/testing.md`：更新 E2E 测试拓扑唯一来源规范，记录 `FrontendAppTopologyHarness` 对协调器测试的统摄。

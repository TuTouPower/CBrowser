---
tid: "t046"
slug: "e2e_infrastructure_and_protocol_harness_rebuild"
title: "E2E 基础设施重构与协议探针模型归一"
status: "done"
branch: "t046_e2e_infrastructure_and_protocol_harness_rebuild"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "3950648050c4374e4ae45af9cfe527746afa23f4"
depends_on: ""
conflicts_with: ""
note: "来源 p051、p052：消除 test_runtime_coordinator_e2e 私有 Docker 编排与 Selkies 协议探针关闭握手时序竞态"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

1. 重写 `tests/e2e/test_runtime_coordinator_e2e.py`：彻底移除所有自建 subprocess 与自定义 Docker 编排及 `finally:` 循环删除逻辑，100% 接入标准 `FrontendAppTopologyHarness`；
2. 修复 `FrontendAppTopologyHarness` 内部 `containers_for` 与 `container_names`：捕获 `docker.errors.NotFound` 异常，并在 `container_names` 中使用原生的原子 `GET /containers/json` 查询，从根源消除容器 teardown 与 inspect 之间的 TOCTOU 竞态（彻底根治 p051）；
3. 修复 `test_supervisor_recovery_e2e.py` 中 `test_supervisor_sigkill_reconciliation_and_event_persistence`：对 Supervisor 重启后的状态查询加入 `poll_until`，等待容器对账恢复完成，消除断言 `None == 30000` 竞态；
4. 重构 `tests/e2e/test_stream_selkies_tokens_e2e.py` 中被驱逐连接的客户端消费模型：对旧连接启动并发异步监听任务，确保在冲突连接建立期间旧连接能够完整接收服务端的 Close Frame，连续 10 次单跑 100% 成功，精确保持 4001 与 `Superseded by a new connection.` 断言（彻底根治 p052）；
5. 完整门禁（`scripts/run_gates.sh`）执行通过，证据位于 `.scratch/t046_evidence_20261108_124935/`。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-08T13:10:00+08:00)

Round 1 零 finding。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：全量门禁 10 个 suites 全部 exit 0（`.scratch/t046_evidence_20261108_124935/manifest.json`，除已登记的 t019 时延基线外零失败，容器消失与 1006 异常彻底消除）
- 黑盒：Docker 真实栈与 Chrome 浏览器 E2E 验证通过
- review：Round 1 code 与 test 均为 PASS，指纹 `4d6a7fb3e9229c90`
- AC 判定：见 `task.md` 行内打勾（AC-001 ~ AC-005 全部 TICK-VALID）

### 结果摘要

- 重写 `test_runtime_coordinator_e2e.py` 接入统一 `FrontendAppTopologyHarness`，彻底废除全仓最后的自建 Docker 编排与私有 cleanup 循环。
- 修复 Docker SDK 容器列表与 inspect 间的 TOCTOU 竞态，根治 p051。
- 协议探针重构为异步实时消费模型，实时接收 RFC 6455 Close Frame，根治 p052。

### 长期文档闭环

- specs_index：`docs/specs_index.md` 中 `gate_verification` 行追加 `t046`。
- blueprint：`docs/blueprint/testing.md` 新增 t046 章节规范。

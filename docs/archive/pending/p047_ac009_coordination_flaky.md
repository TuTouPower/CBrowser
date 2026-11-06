# p047 ac009 协调类 integration 用例反复偶发失败

- 来源：t035 / t041 / t037 三个 task 完整门禁中先后出现的同类 integration 协调用例失败（技术债自查，需从根因修）。
- 内容：`tests/integration/test_runtime_coordinator_integration.py` 的 ac009 协调类用例在三个 task 的门禁中先后偶发失败，反复出现本身即缺陷，不能每次以「已登记遗留」放过：
    - t035 最终门禁：`test_ac009_api_supervisor_start_and_stop_coordination` 失败（t035 实现改过 `runtime_coordinator.py`，当时被怀疑引入时序回归）。
    - t041 全量 integration：`test_ac009_api_supervisor_start_and_stop_coordination` 失败；t041 做过对比实验 `.scratch/t041/ac009_experiment.json`——在 `t043_tip` 与 `t041` 两版各跑「目标文件单跑 12 次、全量 integration 3 次、3 目标文件并发 3 轮（9 进程）、门禁式前置负载 1 次」共每版 19 次目标运行，**两版失败率均 0/19、无差异**。该实验只证明「不是 t035 引入的回归」，**没有证明它不是缺陷**；历史各 1 次失败在 38 次对照运行中未复现，被登记为有败率数据支撑的低频门禁负载时序项。
    - t037 v3 门禁：`test_ac009_supervisor_unreachable_intent_preserved_and_recovers` 失败，断言 `assert rt["last_coordinator_error"] is None` 实得 `'Supervisor start failed (503): Mock supervisor failure'`（恢复后 `last_coordinator_error` 未清空/残留）。
    - 已知证据：失败集中在「门禁负载下」（后端组/前端组并发 + E2E 环境变量下 integration 与前端组并发），单跑通常通过；t041 对比实验数据 0/19 说明低频但真实存在。需从根因定位：协调器恢复路径的 `last_coordinator_error` 清理时机、或 mock supervisor 故障注入后的状态收敛竞态，并用确定性测试（注入时钟/受控并发）复现后修复。
- 处理：t037；resolution=resolved；reason=t037 从根因修复：Supervisor 恢复后 observed_state=running 由独立事件驱动，与 coordinator clear_last_error 存在竞态导致 last_coordinator_error 残留；get_last_error 增加收敛感知，GET runtime 与 SSE publish 在权威 runtime 收敛时清空残留。确定性红测 test_runtime_coordinator_error_settle.py 先红后绿，ac009 integration 连续 5 次通过。

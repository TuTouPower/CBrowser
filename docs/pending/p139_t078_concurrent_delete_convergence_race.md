---
pid: "p139"
slug: "t078_concurrent_delete_convergence_race"
status: "closed"
resolution: "resolved"
reason: "t085 修复并发删除收敛竞态：per-profile 锁原子化收敛判定、IntegrityError 重试回退、accepted 守卫 sibling 标 done；压力测试与 3 轮 -n 4 复跑全绿"
fix_ref: "t085"
---
# p139 t078 并发删除收敛竞态：两并发请求偶发生成 2 个 intent

- 现象：`tests/unit/test_t078_deletion_lifecycle.py::test_concurrent_requests_create_single_open_intent` 在 `-n 4` 全量并行门禁中间歇失败（t077 第 3 轮门禁 final3 出现，第 4 轮与合入门禁均未复现；隔离复跑 1 passed）。两种已见失败模式：① `:350` intent 落到 `stage='failed'`，错误尾部为 `profile_not_found`（与同文件 `:167` 的 `error == "profile_not_found"` 一致）；② `:347` 两并发请求生成 2 个 intent，收敛断言 `len(ids) == 1` 失败。
- 影响：删除 intent 的并发收敛契约（同一 profile 的并发重复删除请求只建一个 intent）在并行负载下偶发不成立；生产触发面为用户/自动化短时间内对同一 profile 重复提交删除，重复 intent 可能导致重复删除执行。
- 根因：待查。收敛路径（`ProfileService.request_deletions` 的去重/建 intent）存在竞态窗口：两请求同时查不到既有 open intent 后各自新建。注意与 p138 的关系：p138 是字体审计写路径缺写事务导致的 `database is locked`；本条的 `:350` 模式曾被误归因为 t068 引擎 pin（`EngineArtifactError: unapproved_engine_build`），经第 2 轮审阅逐行核查 final3.log 证实该报错全部属于 t068 两条测试小节，与本测试无关——读失败日志须按小节标题划界，不能只看 grep 上下文。
- 测试缺口：现有用例只做一次 `asyncio.gather` 双并发；未覆盖高并发次数、重复运行稳定性（stress 循环）与收敛失败后的可观测断言。应补并发压力回归测试（多次循环双并发断言单 intent）与竞态根因修复后的回归用例。
- 线索：证据日志 `~/workspace/cloud-task-logs/gate-t077-final3.log`（t078 小节约 559–615 行）；隔离复跑命令：worktree 内 `.scratch/gate_venv/bin/python -m pytest tests/unit/test_t078_deletion_lifecycle.py::test_concurrent_requests_create_single_open_intent -q -p no:xdist`（1 passed，7.41 秒）。
- 处理：t085；resolution=resolved；reason=t085 修复并发删除收敛竞态：per-profile 锁原子化收敛判定、IntegrityError 重试回退、accepted 守卫 sibling 标 done；压力测试与 3 轮 -n 4 复跑全绿

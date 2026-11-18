---
pid: "p136"
slug: "t078_concurrent_delete_request_race"
status: "todo"
---
# p136 t078 并发删除请求竞态：后到请求在先行删除完成后新建意图并失败

- 现象：`tests/unit/test_t078_deletion_lifecycle.py::test_concurrent_requests_create_single_open_intent` 偶发失败（2026-11-18 t081 合入验证时实测：合并树连跑 8 次 4 过 4 败）。两种失败形态：① 两个并发删除请求各建一条删除意图（断言意图数 ==1 得 2）；② 后到请求的意图最终阶段为 failed（profile_not_found），而非并入先行意图的 done。
- 影响：Profile 删除请求接口（t078 幂等删除生命周期）。并发/重复提交删除时，用户侧可能看到一条莫名失败的删除操作，或同一 Profile 出现两条删除意图记录。删除本身的数据清理无误。
- 根因：`profile_service.request_deletions` 的并入逻辑只覆盖「先行意图尚 open」的窗口：后到请求若在先行意图已 done、Profile 已删除之后才执行 find_open_deletion / get_profile，会查不到 open 意图与 Profile，从而新建一条意图并由执行器以 profile_not_found 失败；两请求交错时亦可各建一条。合入前主仓（3be25c9）与合入后删除相关代码逐字相同，属 t078 既有竞态，非 t081 合入引入。
- 测试缺口：现有并发测试用真实线程时序，竞态窗口靠运气命中，应补确定性验证：在先行意图完成点后注入后到请求的交错时序（可控调度），断言后到请求并入已完成意图（或得到明确的 already-deleted 结果）且不新建意图、不产生 failed 意图。
- 线索：失败签名见 2026-11-18 合入验证记录；复现方式为对上述测试连跑多次（约半数失败）。
- 处理：未开（云端可修：纯后端逻辑＋单元测试覆盖；修复后回归该测试连跑多轮全过为准）


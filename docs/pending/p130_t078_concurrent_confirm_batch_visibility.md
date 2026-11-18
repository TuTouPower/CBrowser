---
pid: "p130"
slug: "t078_concurrent_confirm_batch_visibility"
status: "closed"
resolution: "resolved"
reason: "已在 main 完成根因修复（0012_deletion_batch_members 关联表分离批次成员关系与删除意图、_join_deletion 新增成员而不改写既有 batch_id），补双批次并发确认测试并通过全量 unit/migration/hygiene 门禁"
fix_ref: "main"
---
# p130 t078 并发双确认时先确认者批次轮询留空

- 现象：两个客户端/标签页对同一未终结删除意图近同时确认时，后到者经 `_join_deletion` 把意图改归自己的批次，先到者按其批次号轮询得到空集/404，弹窗回落到确认态，看不到进度与结果。
- 影响：仅删除进度的批次可见性受影响；删除本身不重复、不丢失（部分唯一索引 `uq_profile_deletions_open_profile` 保证单意图，单项查询与再次确认均可恢复，Round 2 code 审阅独立复跑并发用例确认只产生一行意图且收敛 done）。t078 Round 2 code 轴记为 minor finding t078_code_f004，verdict PASS、AC 打勾成立，本条为遗留跟踪。
- 根因：批次成员关系与意图共用同一字段（profile_deletions.batch_id 单值），加入既有意图时只能改归最新批次，无法同时属于两个批次。根治方向：批次成员关系与意图分离（批次-意图关联表），或批次查询按受理返回的 operation id 集合解析；或前端在批次查询为空时回退到 POST 返回的 operations 逐项轮询。
- 测试缺口：现有并发用例只验后端单意图与收敛，未覆盖双客户端各自批次轮询的可见性；补测应模拟两次近同时确认并断言两个批次号都能查到该意图（或前端回退轮询能呈现进度）。
- 线索：`src/backend/cbrowser/services/profile_service.py` `_join_deletion`（意图改归批次处）；`src/frontend/src/features/profiles/EnvironmentListPage.tsx` 弹窗 operations 仅来自批次查询。
- 处理：main；resolution=resolved；reason=已在 main 完成根因修复（0012_deletion_batch_members 关联表分离批次成员关系与删除意图、\_join_deletion 新增成员而不改写既有 batch_id），补双批次并发确认测试并通过全量 unit/migration/hygiene 门禁

# p058 抽取 Supervisor 实例观察的标签定位 helper

- 现象：`SupervisorCore._reconcile_instance_observation` 在加入按 prefix/profile/instance/role 标签定位 Browser 后分支继续增多（review t050_code_f013，圈复杂度约 20+）。
- 影响：可读性与后续修改成本，无功能缺陷。
- 根因：定位逻辑与状态判定写在同一个大方法内，缺少单一职责 helper。
- 测试缺口：无独立单元覆盖该定位 helper；现有观察/恢复集成测试覆盖行为。
- 线索：`src/backend/cbrowser/supervisor/core.py` 的 `_reconcile_instance_observation`。
- 处理：main；resolution=resolved；reason=抽取 BrowserContainerLookup + _lookup_browser_container，定位/围栏/不可用三态显式化，新增四种 outcome 单测

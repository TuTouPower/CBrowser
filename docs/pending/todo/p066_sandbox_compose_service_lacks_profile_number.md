# p066 沙箱 Compose 服务标签未包含 Profile 编号导致 OrbStack/Docker 界面无法区分容器

- 现象：在 OrbStack 或 Docker Desktop 等容器管理 GUI 中，展开 `cbrowser-profiles` 分组后，二级节点仅显示固定的 `browser` 和 `stream` 服务名，没有像容器实际名称（`cbrowser-0001-browser`）那样带有编号；多个 Profile 同时启动时全部折叠在同名服务下，无法按编号区分。
- 影响：用户在 Docker GUI 中无法直观看到各个 Profile 的沙箱编号（如 `0001`、`0002`），也无法按编号区分或独立管理不同 Profile 的容器实例。
- 根因：`src/backend/cbrowser/supervisor/container_spec.py` 中的 `sandbox_compose_labels` 将 `com.docker.compose.service` 硬编码为静态字符串 `"browser"` 和 `"stream"`，未将 `profile_number` 纳入服务名称（例如 `browser-0001` 或 `0001-browser`）。OrbStack 等工具按 Compose 项目分组时，展示的是 Service 名而非容器的实际 Container Name，导致容器本身已有的 `0001` 编号被 UI 折叠隐藏。
    已确认同类位点：
    1. `cbrowser.supervisor.container_spec.browser_labels`
    2. `cbrowser.supervisor.container_spec.stream_labels`
        已全量扫描代码库，无其他沙箱 Compose 标签生成位点。
- 测试缺口：`tests/unit/test_t050_sandbox_grouping.py` 仅在单 Profile 场景下断言了静态值 `assert labels["com.docker.compose.service"] == "browser"`，缺乏多 Profile 容器 Service 命名区分性与编号映射断言。应在单元测试与沙箱启动断言中增加多 Profile 场景的 service 标签带编号验证。
- 线索：`.scratch/reproduce_compose_service_labels.py`
- 处理：未开
- 时间：2026-11-10T19:50:00+08:00

# p063 生产部署环境字体目录路径割裂致平台字体集未配置

- 现象：前端设置页「平台字体集」卡片显示「未配置平台字体集」；`GET /api/v1/font-sets` 返回空数组；新建 Profile 时无法绑定平台字体集，Profile 表 `font_set_id` 为 NULL，运行期回退基础开源字体暴露。
- 影响：生产与部署环境中平台字体集完全不可用；新建 Profile 无法隔离系统 Linux 字体，指纹平台特征缺失；浏览器运行时降级暴露 Linux 基础字体（`PLATFORM_FONTS_UNCONFIGURED`）。
- 根因：配置与路径契约不一致（部署编排与资产路径缺陷）。
    1. `t041` 导入工具与 `.worktreeinclude` 将持久字体集保存在主仓 `$ROOT/data/fonts`（不可变、跨 worktree 与实例共享）。
    2. `compose.yaml` 将 API 与 Supervisor 的 `CBROWSER_FONTS_DIR` 硬编码绑定为 `${CBROWSER_DATA_ROOT}/fonts` 并挂载 `${CBROWSER_DATA_ROOT}/fonts:${CBROWSER_DATA_ROOT}/fonts:ro`。
    3. `scripts/deploy.sh` 默认将 `CBROWSER_DATA_ROOT` 设为 `$ROOT/data/v2`，导致服务实际挂载和扫描 `$ROOT/data/v2/fonts`（空目录），完全看不见 `$ROOT/data/fonts`。
    4. `deploy.sh` 未暴露或处理 `CBROWSER_FONTS_DIR`，也未将主仓持久字体目录链接或挂载进部署环境。
    5. 同类位点扫描：核对其它持久资产目录（`engine-cache`、`network`、`profiles`、`runtime` 等），均由运行期生成在 `$DATA_ROOT`（`data/v2`）内部，唯独 `fonts` 是唯一由宿主预导入、跨实例与 worktree 共享（写入 `.worktreeinclude`）但未与 `deploy.sh` 及 `compose.yaml` 的 `CBROWSER_DATA_ROOT` 对齐的外部资产；已扫无其它类似割裂资产。
- 测试缺口：
    1. 单测与集成测：`test_font_sets_api.py`、`test_font_sets.py`、`test_t041_font_runtime.py` 均用 monkeypatch 注入 `tmp_path` 模拟字体目录，未测试生产配置路径。
    2. 门禁与 E2E：`scripts/run_gates.sh` 全程 `unset CBROWSER_FONTS_DIR`，E2E 专用 `CBROWSER_E2E_FONTS_DIR` 直指 `data/fonts`，绕过了部署环境链路。
    3. 前端测试：`SettingsPage.test.tsx` 直接 mock API 响应数据，未测真实路径。
    4. 部署门禁：`deploy.sh` 仅做 health probe，未校验 `CBROWSER_FONTS_DIR` 的有效性或字体集存在性；`test_t041_font_hygiene.py` 仅断言 `.worktreeinclude` 包含 `/data/fonts`，未断言 `compose.yaml` / `deploy.sh` 挂载路径与 `.worktreeinclude` 一致。
    5. 应补验证：在部署门禁或部署脚本预检增加 `CBROWSER_FONTS_DIR` / 平台字体集检查；在 `test_t041_font_hygiene.py` 补充 `compose.yaml` 与 `deploy.sh` 中字体目录路径一致性断言。
- 线索：
    - `.scratch/repro_font_sets_path_mismatch.py`（最小复现脚本，实测 `data/fonts` 有 2 组完好字体集，而部署路径 `data/v2/fonts` 为 0）
    - 容器内验证：`docker exec cbrowser-api python3 -c "from cbrowser import font_sets; print(font_sets.list_font_sets())"` 结果为 `[]`
    - 挂载比对：`docker inspect cbrowser-api` 显示挂载源为 `<repo>/data/v2/fonts`（空），而非宿主存在的 `<repo>/data/fonts`
- 处理：t051；resolution=transferred；reason=已核实范围并转交该 task

# 门禁与验证体系

需求级 spec，累积 t044。权威入口为 `docs/blueprint/testing.md` 的 `doctor_cmd` / `test_cmd` / `blackbox_verify` 章节命令；本文定义行为契约。

## 1. 并行执行（t044）

- 完整门禁 `scripts/run_gates.sh` 的 unit / integration / E2E suite 以 pytest-xdist 多 worker 并行执行。每个 suite 分两阶段：并行阶段 `-n <workers> -m "not serial"`，串行阶段 `-n 0 -m "serial"`；两阶段 JUnit 由 `scripts/merge_junit.py` 合并为单一 `junit/<suite>.xml`。
- 时序敏感或占用固定宿主端口的用例以模块级 `pytestmark = pytest.mark.serial` 标注。串行阶段单进程执行，执行期间不与任何其它用例并发。
- 用例集合在并行与串行两阶段间完全划分（不重不漏），收集集合与改造前一致。

## 2. 资源隔离（t044）

- xdist worker 通过 `PYTEST_XDIST_WORKER` 派生独立 UDP / HTTP 端口区间与 media 子网（`tests/fixtures/e2e_env.py::worker_resource_offsets`）；端口、Docker 网络、容器名前缀与 basetemp 按 worker 隔离。
- suite 结束不残留本轮创建的容器与网络。

## 3. 证据与并发分组（t044）

- 后端组（contract / unit / integration）与前端组（design_lint / design_check / frontend_test / frontend_build）并发执行，E2E 在两组都完成后开始。逐 suite 写独立 TSV 片段，按固定 `SUITE_ORDER` 合并为 `suites.tsv`；manifest 与 junit 格式不变，任一 suite 失败时证据逐 suite 记录、总退出码非零。
- 门禁不运行 `design:tokens` 生成命令，只做只读 `design:lint` / `design:check`；完整门禁运行前后受跟踪文件内容不变，`design_tokens.css` 过期时由 `design:check` 使门禁失败。
- 环境准备复用持久共享 uv 缓存与 gate venv（requirements 哈希戳），缓存已就绪时环境准备日志无依赖下载。

## 4. E2E 前置条件失败封闭（t044）

- 所有 E2E 前置条件（环境变量、镜像不可变身份、Docker daemon、引擎 / GeoIP 缓存、持久字体集）统一走 `require_e2e_env` / `require_e2e_available`：必跑模式 `CBROWSER_E2E_REQUIRED=1` 下缺失即 `pytest.fail` 并列出缺失项，非必跑模式下为 skip。
- 必跑模式先跑单进程 collection preflight，前置缺失时一次干净失败并列出缺项，不惊动 xdist worker、不产生混乱的失败归因。
- 模块级按开关启用的探针用例是显式可选用例外。

## 5. 指纹平台 E2E 字体集（t044）

- 指纹平台 E2E 从 `CBROWSER_E2E_FONTS_DIR` 持久字体目录读取经 `scripts/import_font_set.py` 导入的内容寻址字体集（`{platform}/{set_id}` + manifest），不依赖任何 worktree 私有 `.scratch` 路径，worktree 删除后仍可运行。
- Windows 字体来自微软官方 Windows 11 企业评估版 ISO（`sources/install.wim` 的 `Windows/Fonts`），macOS 字体来自本机系统目录；字体不入库、不进镜像，仅运行期只读挂载。
- E2E 通过专用 `CBROWSER_E2E_FONTS_DIR` 指向该持久目录，门禁对产品变量 `CBROWSER_FONTS_DIR` 全程 unset：产品 API 在该变量存在时会给每个新建 Profile 绑定默认字体集，而 E2E 的 Supervisor 容器看不到宿主目录，会触发 `font_set_unavailable` 失败封闭，污染所有真实栈用例。专用变量隔离使指纹平台用例仍用导入集，其余用例不受影响。

## 6. 验证工具门禁与弃用策略（t044）

- `scripts/generate_requirements.sh --check` 作为 `requirements_check` suite 接入门禁，依赖锁与导出 requirements 漂移即失败。
- E2E 必跑模式对运行镜像执行 `scripts/verify_image_packages.py`，比对镜像内已安装包集合与依赖锁，不一致即失败。
- 测试运行对未登记来源的 `DeprecationWarning` 视为错误；仅精确登记忽略第三方来源（httpx per-request cookies、aiohttp bare functions、jsonschema RefResolver）。产品源码弃用用法从根因修正：`HTTP_422_UNPROCESSABLE_CONTENT`、SQLAlchemy `lazy="raise"`、`aiohttp.ClientWSTimeout`、Alembic `path_separator`。

## 7. Supervisor 注册状态（p042 / t044）

- 注册状态收敛为每 profile 一个 `RegistrationState`（`known` + `lost_at`），四个生命周期清理点（gateway_missing、gateway_unreachable、启动确认注册、clean stop）一次性清除或重置整个对象。profile 停止后同名重启不继承残留恢复宽限，新 Stream 未注册时按未注册路径替换。

## 8. 测试夹具基线（p044 / t044）

- 测试夹具镜像与运行镜像使用相同的 Python 3.15 / Debian trixie digest 基线；Selkies Web 资产提取的 find 定位、归档取得、出错强制删除探测容器三点均有以 Docker SDK 为边界的单测。

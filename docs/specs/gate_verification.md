# 门禁与验证体系

需求级 spec，累积 t044、t045、t046、t060。权威入口为 `docs/blueprint/testing.md` 的 `doctor_cmd` / `test_cmd` / `blackbox_verify` 章节命令；本文定义行为契约。

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

## 9. 门禁稳定性与 E2E 遗留缺陷收口（t045）

- `run_gate_suite` 并行阶段（c1）与串行阶段（c2）对 pytest exit 5（no tests collected）对称处理：用例全标 `serial` 的 suite 不再假失败；两阶段都为空时判失败并列出缺项，junit 仍由 `scripts/merge_junit.py` 合并串行结果。
- 门禁启动与 `SIGTERM` / `SIGINT` / `EXIT` 中断执行同一套清理：`scripts/gate_container_cleanup.py` 仅按运行标签和本地文件租约清理已结束运行的容器与网络，不再按名称授权；活跃或未知运行资源不删。归属选择由纯函数与真实 Docker 并发验证覆盖。
- 前端 E2E 文件内共享一套容器栈：`test_frontend_session_e2e.py` 改 module-scope `SharedContainerStack`，用例间以 `reset_profile_state`（stop + delete profile）只重置状态；`test_frontend_app_e2e` / `test_frontend_media_e2e` / `test_frontend_display_apply_e2e` / `test_frontend_app_auth_e2e` 核实本就是 module-scope 共享栈，天然满足，不重复改造。隔离语义由 `tests/unit/test_t045_e2e_shared_stack.py` 覆盖。
- Selkies wheel 从 `CBROWSER_SELKIES_WHEEL_CACHE` 指向的本地已锁定 SHA256 缓存读取；`vendor_selkies_web(..., allow_download=False)` 与 E2E 用例不发起任何公网请求；必跑模式 collection 期校验缓存存在与哈希，缺失时失败封闭列出缺项、非必跑模式才 skip，不回落公网。
- 负载下时序判定统一改为就绪条件驱动：`tests/fixtures/wait.py` 的 `poll_until` / `wait_until_sync`（deadline + 最后观测），不靠固定 sleep 兜底、不上调超时。ac007 媒体帧以「stage 文案 + RTP 增长 + worker 已丢弃编码帧」复合就绪谓词判定；supervisor dual_profile 的 API / Supervisor health 以就绪条件收敛后再 POST。
- AC-005 涉及的三个 E2E 用例（`test_vendor_replaces_stale_destination_contents`、`test_ac007_lifecycle_resume_and_isolated_media_diagnostics`、`test_supervisor_dual_profile_port_invariance_on_sigkill`）须在 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 完整必跑门禁中通过，非仅定向单跑。

## 10. E2E 基础设施重构与协议探针模型归一（t046）

- 整个 `tests/e2e/` 目录严禁单个测试文件自建 Docker 编排、私有 API 子进程管理或自写 `finally: remove` 清理循环。
- `tests/e2e/test_runtime_coordinator_e2e.py` 完整重构接入统一的 `FrontendAppTopologyHarness`；所有容器与网络资源纳入统一生命周期管理与 `cleanup_prefixed_resources` / `CBROWSER_E2E_DELETION_LOG` 结构化审计。
- `tests/e2e/test_stream_selkies_tokens_e2e.py` 中协议探针客户端对被驱逐连接使用并发事件监听，确保在握手期间实时接收 Close Frame，保持 4001 与 `Superseded by a new connection.` 精确强断言，消除底层 Transport 异常掐断导致的 1006 假失败。

## 11. 门禁与隐私边界（t060）

- venv 检查、重建和安装持排他 preparation 锁；测试期持共享运行锁。并发热门禁可同时完成，任何重建不能破坏运行读者。
- 同 checkout 互斥使用生成产物，不同 worktree 继续并发共享 venv。测试容器不继承宿主 Docker 配置代理；内部流量直连隔离网络。
- 每轮 run_id 贯穿 CLI / SDK / Supervisor 创建的容器与网络。启动清理只删除已登记且租约结束的运行资源，Docker 归属查询失败不得回退到名称匹配。
- protocol drift 检查作为首个 evidence suite；失败仍生成完整 manifest。pytest / Vitest 收集下限见 testing.md，低于基线、报告缺失或损坏即失败。完整门禁缺少任一运行镜像时 image_packages 为 skipped 且总失败。
- E2E 必跑模式按模块镜像 marker 并集检查，未声明的用例仍按全部前置检查；Browser / Stream 停止观测须分别为不存在，Docker API 异常单列为错误。
- evidence CLI 拒绝非法 image ID、缺失或与预期 os/arch 不符的元数据；shell 预检使用同一验证实现。
- Node engines 的 `>` 严格拒绝相等版本；镜像 requirements marker 不可解析时失败，marker 环境全部取目标镜像。
- 五个镜像构建上下文排除 bytecode；Supervisor services 仅准入实际 COPY 的文件。Artifact 转发保留宿主绝对路径输入中的相对子目录，并拒绝越界。
- 当前 tracked 树及新文件不含开发者家路径与凭据；历史文档原位改写为占位符，删除隐私豁免机制，不改写 Git 历史。交接只保留最新一节，branch 与 head_commit 记录写入时真实值。

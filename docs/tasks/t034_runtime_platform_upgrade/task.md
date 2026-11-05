# Task spec

## 背景

`docs/plan_20261105_ui_redesign.md`（D7、D10，用户 2026-11-05 确认）要求运行时、基础镜像、依赖锁定、Caddy 与 Selkies 统一升到当前最新稳定版本，只保留有事实依据的例外。2026-11-05 于 main@3101540 核实现状：

- 全部 Python 镜像基于 `python:3.12-slim-bookworm`（digest 固定），Browser 镜像的辅助阶段基于 `debian:bookworm-slim`；`pyproject.toml` 为 `requires-python = ">=3.12"`；`scripts/run_gates.sh` 固定 Python 3.12，依赖取自 `scripts/gate-requirements.txt`。
- 没有 `uv.lock`。各镜像依赖分散在 `config/docker/*/requirements.{in,txt}`；`src/backend/requirements.txt` 无任何引用（遗留原生打包）。
- SQLAlchemy 2.0.43、Alembic 1.16.5、aiosqlite 0.21.0。
- Caddy 镜像 2.8-alpine。
- Selkies 固定 2.1.0：`config/docker/stream_runtime/requirements.{in,txt}`、`scripts/vendor_selkies_web.py` 与 `config/selkies/selkies_web_sha256.txt`；`stream_agent/x11_keymap.py` 按 2.1.0 校验 Selkies 键盘私有 ABI，漂移即失败；ADR 002、013 写明 2.1.0。
- cloakbrowser 封装库 0.7.0 删除了无 key 路径（无 key 时自动申领免费 key，只允许 1 个并发会话），会破坏多 Profile 并发；0.6.4 无 key 模式使用免费 Chromium 146 内核，不校验 license、不限制并发（plan 7.2）。

## 契约区

### 范围

- Python 升到最新稳定版本（plan 基线 3.15）：全部镜像、本地门禁与 `requires-python` 一致。
- 全部基础镜像升到 Debian 最新稳定版（trixie），digest 固定；适配 apt 包名变化。
- Python 依赖以 `pyproject.toml` + `uv.lock` 为唯一锁定来源：各镜像 requirements 与门禁依赖由 `uv export` 按依赖组生成，门禁校验生成物与锁文件一致；删除 `src/backend/requirements.txt` 与手写的重复依赖清单。
- SQLAlchemy、Alembic、aiosqlite 升到最新版本，移除已弃用用法。
- Caddy 升到最新 2.x，适配 Caddyfile。
- Selkies 升到最新 2.x（plan 基线 2.2.1）：先做正式 spike 比对 2.1.0 与目标版本的差异，再更新 Stream 镜像、vendor 脚本与 SHA 清单、适配层兼容（HELLO、`client_tab_id`、`resume_key`、Web Locks 身份重映射）、`x11_keymap` 私有 ABI 校验，以及依赖的 pixelflux / pcmflux。
- cloakbrowser 封装库锁定 0.6.4：新增 ADR，写明原因与复查条件（上游恢复无 key 路径，或改用 Pro）。
- 修订 ADR 002、013 中「Selkies 2.1.0 固定」的表述，并记录各组件目标版本。

### 非范围

- 业务行为与 schema 变化（t035）。
- 局域网访问与协议配置（t042）。
- 前端工具链（t033）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：每个运行镜像（API、Gateway、Supervisor、Browser、Stream、Caddy）的基础镜像都以 digest 固定；同一源码两次干净构建得到的 Python 与系统包集合一致。
- [ ] AC-002：Python 依赖只有 `uv.lock` 一处锁定来源。各镜像内安装的 Python 包与 `uv.lock` 导出结果一致；生成的 requirements 被手改或与锁文件不一致时门禁失败；仓库不存在其他手写的 Python 依赖锁定清单。
- [ ] AC-003：`scripts/run_gates.sh` 用与镜像相同的 Python 主次版本运行全部 suite 并通过；本地解释器版本不符时门禁失败并输出所需版本。
- [ ] AC-004：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 全量真实栈 E2E 无头通过，覆盖会话阶段、同 Profile 多页面、复制标签页身份重映射、IME 组合输入、音频、剪贴板、可见性暂停与恢复、x11 键盘映射。
- [ ] AC-005：经 Caddy 的 HTTPS 访问、静态资源、`/api/v1` 与 `/stream/*/signal` 转发行为与升级前一致，由 E2E 覆盖。
- [ ] AC-006：Stream 镜像内 Selkies 服务端版本与 vendor 的官方 Web 客户端版本一致，SHA 清单与 vendor 产物匹配；`x11_keymap` 依赖的 Selkies 私有接口与目标版本不匹配时，启动失败封闭并报告不支持的 ABI。
- [ ] AC-007：部署脚本在隔离实例（独立 project、prefix、端口、数据目录）上完成一次新 release 发布，再回退到上一 release，两次均通过健康检查；其他实例不受影响。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`docs/plan_20261105_ui_redesign.md` WP02、WP04、WP05 与第 7 节（2026-11-05 于 main@3101540 核实，结论见背景）。plan 已核对 19 个原生依赖均有 cp315 aarch64 wheel 或 abi3/纯 Python 兜底，实施时以 `uv lock` 解析结果为准。

### 有意不测

- 无。

### 测试策略

- Selkies spike 先跑现有 Stream 与会话 E2E 作为差异探针，结论写入 `docs/findings/`；适配后跑全量 E2E。
- 依赖一致性：门禁对比镜像内 `pip freeze`（或等价清单）与 `uv export` 结果。
- SQLAlchemy 升级以全量 unit / integration 覆盖异步路径；`-W error::DeprecationWarning` 检查弃用用法残留。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- Selkies 2.1.0 → 目标版本的协议与私有接口差异（HELLO、`client_tab_id`、`resume_key`、键盘 ABI、pixelflux / pcmflux）：UNVERIFIED-SPIKE，用正式 spike 比对源码并跑现有 E2E；存在无法适配的破坏性变化时停止并报告用户，不自行决定保留 2.1.0。
- Debian trixie 下 Browser / Stream 镜像所需 apt 包名与可用性：UNVERIFIED-SPIKE，构建验证。
- Caddy 最新版对现有 Caddyfile 语法与 `tls internal` 的行为：UNVERIFIED-SPIKE，E2E 验证。

### 风险与回退

- 风险：Selkies 新版改变 resume / 多页面语义；trixie 缺包导致 Browser 镜像无法构建；SQLAlchemy 2.1 改变异步会话行为。
- 回退：发布层按 ADR 017 回退到上一 release；源码层回退本 task commit。

### 依赖与约束

- 依赖 t032：t032 正在 main 工作区针对当前镜像做真实环境验收，本 task 会替换这些镜像，须在 t032 合入后开始。
- 只动本 task 的隔离实例，不碰其他会话或 task 的部署实例（如 `cbrowser-t032*`）。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/decisions.md`：cloakbrowser 锁定 0.6.4 ADR；Selkies 目标版本替代 2.1.0 固定（修订 002、013）；Python、Debian、依赖单一来源与各组件目标版本。
- `docs/blueprint/conventions.md`：技术栈版本与依赖管理约定。
- `docs/blueprint/stream_runtime.md`、`docs/blueprint/frontend.md`：Selkies 版本与 vendor 描述。
- `docs/blueprint/testing.md`：Python 版本与依赖一致性门禁。
- `docs/specs/release_deployment.md`、`docs/specs/webrtc_remote_display.md`：版本相关条目。

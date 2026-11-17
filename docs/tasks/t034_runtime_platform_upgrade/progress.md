---
tid: "t034"
slug: "runtime_platform_upgrade"
title: "运行时与镜像底座升级：Python、Debian、依赖锁定与 Caddy"
status: "done"
branch: "t034_runtime_platform_upgrade"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "00f828e9cdf4db729c39f36a12ee303cbb7a5910"
depends_on: "t032"
conflicts_with: ""
note: "来源 plan_20261105_ui_redesign WP02+WP04；Selkies 已拆到 t043"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-05：两项 UNVERIFIED-SPIKE 实测闭环并回填 `task.md`：① trixie 下 34 项 apt 包（X11/GStreamer/Pulse/XTEST/文泉驿等）`apt-cache show` 全部 OK，无包名变化；② Caddy 2.11.8 对现有 Caddyfile `caddy validate` 返回 Valid configuration，`tls internal` / `auto_https disable_redirects` / 三段 `handle` 转发行为保持。另修正 `pyproject.toml` 原缺陷：`dependencies` 误落在 `[project.scripts]` 表下导致项目依赖为空，Python 3.15 下修正后 `uv lock` 解析 77 包成功（SQLAlchemy 2.1.8、Alembic 1.20.1、aiosqlite 0.22.1）。
- 依赖单一来源：根 `pyproject.toml` 改用 PEP 735 `[dependency-groups]` 定义 api/gateway/supervisor/browser/stream/gate 六组；`uv.lock` 为唯一锁定来源；新增 `scripts/generate_requirements.sh`（`uv export --only-group` 按组生成各镜像 requirements.txt 与 gate-requirements.txt，`--check` 校验漂移）；新增 `tests/unit/test_t034_dependency_lock.py`（TDD 先红后绿：逐组比对、uv.lock/pyproject 均 3.15、遗留清单不存在、GATE_PYTHON_MINOR 与 Dockerfile 一致、运行时解释器 minor 断言）；删除 `src/backend/requirements.txt` 与 4 个 `requirements.in`。
- 版本升级：5 个 Python 镜像 FROM 改为 digest 固定的 `python:3.15-slim-trixie@sha256:8c13a3f...`，Browser 辅助阶段 `debian:trixie-slim@sha256:f6b08b0...`；`deploy_v2.sh` 的 `CADDY_REF` 默认改为 digest 固定的 caddy 2.x；`run_gates.sh` 的 `GATE_PYTHON_MINOR=3.15`（两处 `uv venv --python`）；`.mise.toml` 固定 python 3.15.2；`pyproject.toml` 与 `uv.lock` 的 `requires-python>=3.15`；cloakbrowser 精确锁定 0.6.4（ADR 021 说明免费 key 并发限制）。
- AC-001 实证：5 个镜像两次干净构建（不同 tag）镜像 ID 逐一相同（browser d6ed0ef、stream 0a0f200、supervisor e331b71、gateway 3a4dac0、api 537c3be），Caddy 由 digest 固定；`verify_image_packages.py` 逐镜像比对 `pip freeze` 与 uv.lock 导出（规范化 markers 后）全部 MATCH：api 39、gateway 19、supervisor 22、browser 39、stream 35 包。
- Python 3.15 全量回归（3.15 venv 装 uv.lock 导出）：contract 222 passed / 1 skipped、unit 1002 passed + 隐私 8 passed、integration 142 passed / 18 skipped，SQLAlchemy 2.1 / Alembic 1.20 无破坏性回归；t028 stub 契约 4 passed 未破坏。t033 review 报告（随 base 进入 worktree）的绝对路径按约定登记精确 sha256 指纹。
- 长期文档：`docs/blueprint/decisions.md` ADR 021（版本、单一来源、cloakbrowser 锁定与复查条件）、`conventions.md`（Python 3.15 / uv.lock / digest 固定 / 本地工具版本）、`testing.md`（依赖一致性与 Python minor 门禁）、`docs/specs/release_deployment.md`（基础镜像与 Caddy digest 条目）。
- 首轮全量门禁暴露两类真实回归（均属本 task 范围，已修）：① `tests/fixtures/gateway_probe/selkies_assets.py` 与 `scripts/vendor_selkies_web.py` 写死 `python3.12/site-packages/selkies/selkies_web`，3.15 镜像下 `FileNotFoundError`；改为容器内 `find` 动态定位（create + start + exec_run + get_archive），两处实跑提取成功。② `pyproject.toml` 的 api 组用裸 `sqlalchemy>=2.0.0`，升级到 2.1.8 后 `sqlalchemy.ext.asyncio` 强制要求 greenlet，API 容器启动即 `ImportError`、health 不 ready；改为 `sqlalchemy[asyncio]>=2.0.0`，重新 `uv lock` / 导出 requirements / 重建 api 镜像，`import cbrowser.api.main` 通过，`verify_image_packages.py` 40 包一致。新增 `tests/unit/test_t034_runtime_paths.py` 回归（无写死 3.12、动态 find、api 组 asyncio extra 与 greenlet），15 项定向测试全绿。
- 另修正门禁环境：t034 worktree 新建时缺 `node_modules`/`dist`（gitignored），首轮 frontend 两 suite exit 127；`npm ci` + `npm test`（216 passed）+ `npm run build` 补齐后重跑。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-05T17:30:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t034_code_f001|minor|已修|`generate_requirements.sh` 头部注释改为真实说明（`--check` 为开发者/CI 助手，门禁一致性由 `test_t034_dependency_lock.py` 承担），消除「used by run_gates.sh」不实陈述|scripts/generate_requirements.sh:3|
|t034_code_f002|minor|已修|拆分赋值与导出，`mise which python` 失败显式报错退出并 `: "${UV_PYTHON:?...}"` 校验|scripts/generate_requirements.sh:17|
|t034_code_f003|minor|已修|`image_freeze` 去掉 `2>/dev/null`，失败信息含 stdout+stderr；`normalise` 改用 `packaging.markers.Marker` 按 Linux/CPython 3.15 求值|scripts/verify_image_packages.py:17|
|t034_test_f001|minor|已修|同 code_f003 的 marker 求值修复（不再字符串硬编码 win32/pypy）|scripts/verify_image_packages.py:24|
|t034_test_f002|minor|遗留|镜像比对结果已落盘 `.scratch/evidence_t034c/image_packages/`；`--check` 与 `verify_image_packages.py` 接入自动路径会改变 t028 stub 契约，按 TDD 需整体重写，收益不匹配|p044|
|t034_test_f003|minor|已修|同 code_f002（UV_PYTHON 解析显式 fail-closed）|scripts/generate_requirements.sh:17|
|t034_test_f004|minor|遗留|Starlette 弃用常量来自 starlette 1.10（非 t034 引入）、全局 filterwarnings 属既有配置；t034 范围内 SQLAlchemy/Alembic/aiosqlite 升版已由全量 unit/integration/E2E 证明无弃用回归|p044|
|t034_test_f005|minor|遗留|动态 find 已有两处实跑提取 + E2E 101 passed 佐证；mock 边界单测为覆盖深度增强|p044|

Round 1 零 critical/important；5 条 minor 已修、3 条登记 p044，review PASS、0 TICK-VOID。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-001~006 均在 Python 3.15 / trixie / 新镜像上取得目标环境证据；完整门禁 `all_passed=true`）
- 测试：完整 required+evidence 门禁 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`（Node 26.13、Python 3.15，证据 `.scratch/evidence_t034c/`）：contract 222 passed / 1 skipped、unit 全绿、integration 全绿、frontend_test 216 Vitest + 类型检查、frontend_build 含 `verify_frontend_dist.py --check-freshness`、e2e 103 项 0 失败 2 skip（探针门控）；`manifest.json` 六个 suite exit_code 全 0、`all_passed=true`。定向：`test_t034_dependency_lock.py` 5 passed、`test_t034_runtime_paths.py` + vendor 安全 10 passed、`verify_image_packages.py` 五镜像全 MATCH、Python 3.15 venv 全量回归 contract 222 / unit 1002+8 / integration 142。
- 黑盒：全量真实栈 E2E 无头通过（含 AC-005 的 Caddy HTTPS 静态资源与 `/api/v1`、`/stream/*/signal` 转发用例）；AC-006 隔离实例演练：独立 project/prefix `cbrowser-t034-rh`、端口 56789、独立 data/secrets/deploy 目录，连续发布 rh1 → rh2 → 回退 rh1，三次 `up --wait` 四服务全 Healthy、readiness `{"ready": true}`，生产 `cbrowser-*` 栈与其它实例全程未受影响，演练后隔离栈已 down -v 清理。
- review：full 级独立 review（`review_code.md` / `review_test.md`）PASS。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- Python 3.15.2 / Debian trixie / Caddy 2.11.8 digest 固定；`pyproject.toml` 结构缺陷修复，PEP 735 六组依赖 + `uv.lock` 单一来源，`scripts/generate_requirements.sh` 按组导出并在 unit suite 校验；删除遗留手写清单；SQLAlchemy 2.1.8 / Alembic 1.20.1 / aiosqlite 0.22.1 升级无回归；cloakbrowser 锁 0.6.4（ADR 021）。
- 遗留只写引用：无（首轮门禁暴露的两类回归已在本 task 内修复并补回归测试，见实施笔记）。

### 长期文档闭环

- 本 task 更新 `docs/specs/release_deployment.md`（基础镜像/Caddy digest 与依赖单一来源条目）；该 spec 已在 `docs/specs_index.md` 生效表内，无新增 slug。
- 三项 SPIKE 为一次性实验，证据留在 `.scratch/t034_spike/` 与实施笔记，不建正式 sid；结论已回填 `task.md` 未知契约清单。

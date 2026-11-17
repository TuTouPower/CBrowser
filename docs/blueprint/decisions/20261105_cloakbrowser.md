# 021 运行时底座目标版本、依赖单一来源与 cloakbrowser 锁定（2026-11-05，t034）

- 背景：D7/D10 要求运行时、基础镜像、依赖锁定与 Caddy 升到当前最新稳定版本；Selkies 升级拆到 t043 单独回退。2026-11-05 核实现状：全部 Python 镜像 `python:3.12-slim-bookworm`、辅助阶段 `debian:bookworm-slim`、无 `uv.lock`、依赖分散在 `requirements.in`/`requirements.txt` 与 `src/backend/requirements.txt`、SQLAlchemy 2.0.43 / Alembic 1.16.5 / aiosqlite 0.21.0、Caddy 2.8-alpine。
- 选项：全升最新；或遇兼容问题时保留例外。
- 结论：
    - **Python 3.15.2 / Debian trixie**：六个运行时镜像全部改为 digest 固定的 `python:3.15-slim-trixie@sha256:8c13a3f...`、Browser 辅助阶段 `debian:trixie-slim@sha256:f6b08b0...`；trixie apt 包名 SPIKE 实测全部可用（X11/GStreamer/Pulse/XTEST/文泉驿字体等）。`pyproject.toml` 的 `requires-python` 与 `uv.lock` 均为 `>=3.15`，`run_gates.sh` 的 `GATE_PYTHON_MINOR=3.15`，`.mise.toml` 固定 3.15.2。
    - **依赖单一来源**：修正 `pyproject.toml` 原缺陷（`dependencies` 误落在 `[project.scripts]` 表下，项目依赖为空），改用 PEP 735 `[dependency-groups]` 定义 6 组；`uv.lock` 为唯一锁定来源，`scripts/generate_requirements.sh` 按组 `uv export --only-group` 生成各镜像 requirements 与门禁 requirements；`tests/unit/test_t034_dependency_lock.py` 在门禁中校验一致，手改即失败。删除 `src/backend/requirements.txt` 与四处 `requirements.in`。
    - **升级版本**：`uv.lock` 解析 77 包，SQLAlchemy 2.1.8、Alembic 1.20.1、aiosqlite 0.22.1；全量 unit（1002+）、integration（142）、contract（222）在 Python 3.15 下通过，无弃用用法导致的回归。
    - **Caddy 2.11.8**：`deploy.sh` 默认引用改为 digest 固定；现有 Caddyfile（`tls internal`、`auto_https disable_redirects`、`handle` 转发）经 `caddy validate` 实测通过，行为不变。
    - **cloakbrowser 锁定 0.6.4（D7）**：0.6.4 无 key 模式使用免费 Chromium 146 内核、不校验 license、无并发上限；0.7.0 删除无 key 路径，自动申领的免费 key 只允许 1 个并发会话，会破坏多 Profile 并发。故精确锁定 `cloakbrowser[geoip]==0.6.4`，不升 0.7.x。
- 复查条件：上游恢复无 key 路径且免费 key 不再限制并发会话时，重新评估 cloakbrowser 升级（需真引擎并发验证）；Python/Debian/Caddy 后续大版本升级按同一 digest 固定 + SPIKE + 全量门禁流程。
- 替代：无（不采用 `--legacy-peer-deps` 类绕过，不保留手写并行依赖清单）。

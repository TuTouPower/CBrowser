# Task review t034（reviewer_focus: 代码）

- task：`t034_runtime_platform_upgrade`
- spec：`docs/tasks/t034_runtime_platform_upgrade/task.md`
- diff_anchor：`00f828e9cdf4db729c39f36a12ee303cbb7a5910`
- target：`git -C '/Users/karson/kar/code/CBrowser_t034' diff 00f828e9cdf4db729c39f36a12ee303cbb7a5910`
- round：1
- reviewed_at：2026-11-05T17:33:13+08:00

reviewed_scope: 4230c0bb95b7ec52

审查对象为相对 `00f828e9...` 的 35 个已暂存交付文件（`git status --short` 确认无未暂存改动、无未跟踪交付文件；`git -C ... diff 00f828e9...` 全量读取）。按约束未跑 Docker E2E、未跑完整门禁。独立轻量复验：仓库落点 `git rev-parse --show-toplevel` 校验通过；`bash scripts/generate_requirements.sh --check` 六组全 `requirements ok`（exit 0）；`uv export --only-group gate` 在 `UV_PYTHON=3.15` 与 `mise which python`（3.15.2 绝对路径）两种解析下均 rc=0、141 行一致；新增单测直跑 `test_t034_runtime_paths.py` 2 项、`test_t034_dependency_lock.py` 静态 3 项全 passed；mise 3.15.2 下 `test_gate_interpreter_minor_matches_images` 通过；`uv.lock` 77 包 / `requires-python = ">=3.15"` 核对；当前 scope 指纹独立重算 = `2c7edb04628d5c87`（与报告声明一致）。部署态/构建态/E2E 证据（`.scratch/evidence_t034c/`、`.scratch/t034_rehearsal/`）未独立重跑，按披露规则标 `trust_prior`。

## Findings

### t034_code_f001 - `--check` 注释不实且该分支无任何调用者，与 AC-002 门禁实现重复

- 严重度：minor
- 锚点：`行为缺陷` —— 维护者据 `scripts/generate_requirements.sh:5` 注释以为 `run_gates.sh` 会执行 `--check` 漂移校验，实际该脚本从未被门禁调用，AC-002 的漂移校验由另一套 `uv export` 实现承担，两套逻辑参数需各自维护。
- 位置：`scripts/generate_requirements.sh:5`（注释 `#   --check    compare in place, exit 1 on drift (used by run_gates.sh)`）、`:39-46`（`--check` 分支）；对照 `scripts/run_gates.sh:1-119` 全文、`tests/unit/test_t034_dependency_lock.py:33-63`。
- 问题：全仓 `git grep generate_requirements` 仅命中脚本自身注释、文档蓝图与测试里的 `regenerate with ...` 提示文字，`run_gates.sh`（119 行）与任何 CI/入口均未调用 `scripts/generate_requirements.sh`；`--check` 分支是无调用者的死代码，注释 "used by run_gates.sh" 为不实陈述。AC-002 要求的「生成物被手改或与锁文件不一致时门禁失败」实际由 `test_each_requirements_is_the_uv_lock_export`（在 unit suite 中逐组 `uv export --only-group` 并 `assert actual == expected`）独立实现。两处 `uv export` 参数一致（`--no-hashes --no-header --no-emit-project --no-emit-workspace --format requirements.txt`），但 `UV_PYTHON` 解析不同（脚本用 `mise which python` 绝对路径、测试用字符串 `"3.15"`），未来任一侧参数变更不会自动同步，构成同源逻辑重复。本人实跑 `--check` 六组功能正常、exit 0，当前无坏结果，故不阻断。
- 建议：删除或改写 `:5` 注释为真实说明（如「供开发者本地校验，门禁一致性由 test_t034_dependency_lock.py 承担」）；或把 `--check` 真正接入 `run_gates.sh` 并让 Python 测试复用同一脚本，消除两套重复导出逻辑。

### t034_code_f002 - `export UV_PYTHON="$(mise which python)"` 吞掉命令替换失败

- 严重度：minor
- 锚点：`行为缺陷` —— 当 `mise` 不在 PATH 或 `.mise.toml` 固定的 3.15.2 未安装时，`mise which python` 失败被 `export` 包装吞掉，`UV_PYTHON` 静默置空且不报错，脚本继续到 `uv export` 才以「no interpreter found」间接失败，根因被掩盖。
- 位置：`scripts/generate_requirements.sh:17`
- 问题：bash 中 `export VAR="$(cmd)"` 的退出码取 `export`（恒 0），命令替换的失败不会触发脚本首行的 `set -euo pipefail`；`mise which python` 报错或输出空时 `UV_PYTHON=""` 被导出，脚本不显式校验。实测本机 `mise which python` 正常（→ `/Users/karson/.local/share/mise/installs/python/3.15.2/bin/python`），故当前不触发；属健壮性缺口。该脚本不在门禁链（见 f001），影响面限于开发者重新生成 requirements 的诊断体验。
- 建议：拆分赋值与导出并显式校验，如 `UV_PYTHON="$(mise which python)" || { echo "mise python 3.15.2 不可用" >&2; exit 1; }; export UV_PYTHON`，或 `export UV_PYTHON; : "${UV_PYTHON:?mise python 3.15.2 不可用}"`。

### t034_code_f003 - `verify_image_packages.py` 吞掉 pip 错误且 marker 归一化不通用

- 严重度：minor
- 锚点：`行为缺陷` —— 镜像内 `pip` 与 `/opt/venv/bin/pip` 均不可用时，`image_freeze` 抛出的 `RuntimeError` 里 stderr 恒为空、无法诊断；未来 uv.lock 出现其它平台专属 marker 时 `normalise` 会误报 missing/extra。
- 位置：`scripts/verify_image_packages.py:44`（`pip freeze 2>/dev/null || /opt/venv/bin/pip freeze 2>/dev/null`）、`:50`（`proc.stderr[-500:]`）、`:32-36`（`normalise` 仅硬编码跳过 `sys_platform == 'win32'` 与 `implementation-name == 'pypy'`）。
- 问题：`image_freeze` 把两条 pip 命令的 stderr 都 `2>/dev/null` 丢弃，失败时 `:50` 拼入 `RuntimeError` 的 `proc.stderr[-500:]` 恒空，丢失「缺 pip / 权限 / entrypoint 不对」等诊断信息。`normalise` 未按目标平台求值 marker，只按字符串匹配丢弃 win32 与 pypy `==` 变体；当前 uv.lock 全部 marker 行（win32、`implementation_name != 'PyPy'`、`platform_python_implementation != 'PyPy'`、stream 组 uvloop 的 `sys_platform == 'darwin' or sys_platform == 'linux'`）在 linux/cpython 容器内处理结果均正确（五镜像 MATCH 实证亦佐证），故现无坏结果，属潜在健壮性缺口。该脚本为 AC-001/AC-002 的独立验证工具，不在门禁链。
- 建议：去掉 `2>/dev/null`（或把两条命令的错误回显到自定义消息）以保留诊断；`normalise` 用 `packaging` 的 marker 求值或至少覆盖 `sys_platform == 'darwin'` 等其它平台分支，避免把「不满足当前平台」的包计入 expected。

## 结论

- 前轮 finding 复核：本轮为首轮（round 1），无前轮 finding 需复核。
- 本轮新发现：3 条（t034_code_f001 / f002 / f003，均 minor）。无 critical / important。
- 未进表的提示：
    - 文件过大（按降级规则只列路径与行数，不进表）：新增手写脚本 `scripts/generate_requirements.sh` 53 行、`scripts/verify_image_packages.py` 74 行，测试 `tests/unit/test_t034_dependency_lock.py` 105 行、`test_t034_runtime_paths.py` 34 行，均未达 400/600 阈值；`uv.lock` 1570 行与 5 份 `requirements.txt` / `gate-requirements.txt` 为 `uv export` 生成物与 lockfile，按规则排除。无命中。
    - 圈复杂度：新增函数（`normalise` / `image_freeze` / `main`、各 test、`extract_from_stream_image` 与 `prepare_selkies_web_assets` 的动态 find 段）分支浅，无 CC≥10/≥15 命中。
    - 范围外观察（非本轮 diff 引入，不进表）：`tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile:1` 仍为 `python:3.12-slim-bookworm@sha256:e697c8...` 且 `:5` 装 `sqlalchemy[asyncio]==2.1.6`；本 task 未触及该文件。它不属于 AC-001 的六个运行镜像（5 个 `config/docker/*/Dockerfile` + Caddy），`tests/unit/test_baseline_runtime_regressions.py:68-88` 仅对其作 digest 文本完整性断言，`deploy_v2.sh:315` 构建的是生产 `config/docker/api_runtime/Dockerfile`，全仓无对它的 `docker build`。属既有测试夹具，建议另立 follow-up 对齐 3.15/trixie，不影响本 task 任何 AC。
    - ADR 措辞：`docs/blueprint/decisions.md:255`「六个运行时镜像全部改为 digest 固定的 `python:3.15-slim-trixie@sha256:...`」字面上把 Caddy 也计入 python 镜像；该 ADR `:258` 紧接单独列 Caddy 2.11.8 条目，读者不会误解，属措辞，不进表。
    - AC-003 版本门禁形态：`run_gates.sh` 未在入口显式校验本地解释器并打印所需版本（不同于前端 `check_node.mjs`），而是靠 `uv venv --python 3.15` 间接失败 + `test_gate_interpreter_minor_matches_images` 断言兜底；AC 已满足，属「可更细」建议，不进表。
    - 测试层观察（归 test reviewer 轴，仅记录）：新增 2 个测试文件均为真实断言（逐组 `actual == expected`、`sys.version_info[:2]==(3,15)`、`tomllib` 读锁、遗留清单不存在断言），无 mock 掉被测逻辑、无恒真/弱化断言、无就地改旧测试预期；`test_t034_runtime_paths.py` 用源码文本存在性断言（偏弱但非 anti-pattern）。既有测试断言未被改动。
    - 七视角扫描确认：安全（digest 固定、无外部输入直达执行/拼接、动态 find 路径来自容器内 `find` 且经 `get_archive` 取可信镜像内路径、两处 `finally: container.remove(force=True)` 清理正确、无凭证进日志，无命中）；正确性/并发（`--check` 六组实跑 MATCH、两种 UV_PYTHON 解析 rc=0、静态单测 5 passed、3.15 解释器断言通过）；契约·Breaking（依赖组重定义无公开 API/配置键破坏；`uvicorn[standard]`→`uvicorn` 经核对旧 `requirements.txt` 本就未含 standard extra 传递依赖，无行为回退；Caddy 改 digest-only 引用经 `docker image inspect` 固定镜像 ID）；性能·资源（`uv export` 离线、容器 `sleep 60` + `remove(force=True)` 有界清理，无循环查库/同步 IO 阻塞 async）；架构·可维护性（按组导出、单一来源，仅 generate_requirements.sh 与 Python 测试的重复见 f001）；健壮性·可观测（见 f002/f003）；测试·文档·规格（ADR 021 / `testing.md` / `conventions.md` / `release_deployment.md` / `specs_index.md` 与 `uv.lock` 版本一致：SQLAlchemy 2.1.8、Alembic 1.20.1、aiosqlite 0.22.1、77 包；两项 SPIKE 结论已回填 `task.md` 未知契约清单，无 UNVERIFIED 残留）。未命中视角不出凑数 finding。
- 总体判断：35 个交付文件实现层真实支撑 6 条打勾 AC；digest 固定覆盖 6 个运行镜像（含 Caddy 经 `CADDY_REF` digest 与 compose 镜像 ID 固定）、`uv.lock` 单一来源与 `--check`/unit 双重漂移校验经独立复验全绿、动态 find 容器生命周期/清理/路径注入复核无缺陷、删除遗留清单无活跃引用、ADR 与代码一致、无 mock/弱化断言/就改旧预期；仅 3 条 minor（文档与健壮性），无未解决 critical/important，PASS。
- 系统性 follow-up：`tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile` 对齐 Python 3.15 / trixie（建议标题，非阻断）；其余 3 条 minor 为本任务内最小修复，不跨 task。

## AC 复验方式

- AC-001：TICK-VALID，re_verified。逐一核对 5 个 `config/docker/*/Dockerfile` 全部 FROM 行均为 `python:3.15-slim-trixie@sha256:8c13a3f...`（browser 两个辅助阶段为 `debian:trixie-slim@sha256:f6b08b0...`、stream builder+final 两行同 digest）；`scripts/deploy_v2.sh:51` `CADDY_REF` 为 `caddy@sha256:70b3180...`，`:326-347` 用 `docker image inspect` 的镜像 ID 写入 `CBROWSER_CADDY_IMAGE` 供 `compose.yaml:117` 固定；两次干净构建 ID 一致与五镜像包集合 MATCH 由实施侧 `verify_image_packages.py` 证据支撑（构建态未独立重跑）。
- AC-002：TICK-VALID，re_verified。独立实跑 `bash scripts/generate_requirements.sh --check` 六组全 `requirements ok`（exit 0）；两种 `UV_PYTHON`（`"3.15"` 与 `mise which python` 路径）下 `uv export --only-group gate` 均 rc=0/141 行一致；`test_t034_dependency_lock.py` 静态 3 项、`test_t034_runtime_paths.py` 2 项直跑全 passed；`uv.lock:3` 为 `>=3.15`、77 包，`src/backend/requirements.txt` 与 4 个 `requirements.in` 已删且 `test_no_legacy_requirement_lists` 断言；fail-closed 由 `assert actual == expected` 与 `assert result.returncode == 0` 保证。
- AC-003：TICK-VALID，re_verified。通读 `run_gates.sh` 全文：`GATE_PYTHON_MINOR="3.15"`（`:33`）且 `:39`/`:62` 两处 `uv venv --python "$GATE_PYTHON_MINOR"`，本地无 3.15 时 uv 明确报 no interpreter 失败；`test_gate_python_minor_matches_images` 断言所有 `FROM python:X.Y-` 的 X.Y==3.15 并直跑通过；mise 3.15.2 下 `test_gate_interpreter_minor_matches_images` 通过。各 suite 全通过依赖 `evidence_t034c/manifest.json`（六 suite exit 0、`all_passed=true`）。
- AC-004：TICK-VALID，trust_prior。依赖 `.scratch/evidence_t034c/manifest.json` 的 `all_passed=true` 与 e2e 103 项 0 失败 2 skip（探针门控）；按约束未重跑 Docker E2E / 完整门禁。
- AC-005：TICK-VALID，re_verified。实现层核对：本 task diff 未触及 Caddyfile 与 `/api/v1`、`/stream/*/signal` 三段 `handle` 转发路由，仅 `deploy_v2.sh:51` 改 `CADDY_REF` 一行；`task.md:81` 已回填 Caddy 2.11.8 `caddy validate` 返回 Valid configuration（`tls internal` / `auto_https disable_redirects` / 三段转发保持）；转发行为一致的 E2E 证据见 `evidence_t034c`（trust 部分）。
- AC-006：TICK-VALID，trust_prior。依赖 `.scratch/t034_rehearsal/` 日志：隔离实例 `cbrowser-t034-rh`（端口 56789）连续发布 rh1→rh2→回退 rh1，三次健康检查全绿、readiness `{"ready": true}`，生产栈未受影响、演练后清理；部署/回退逻辑在本 task diff 中除 `CADDY_REF` 一行外零改动（实现层已核），但发布/回退演练为部署态，未独立重跑。

## 第 2 轮复核（scope 重绑定）

- 交付内容变化，scope 指纹由 `2c7edb04628d5c87` 重绑定为 `4230c0bb95b7ec52`（`render_review_prompts.py` 已重跑；本轮独立用 `review_scope_fingerprint` 重算一致）。按约束只改本报告，未跑 Docker E2E / 完整门禁。
- 前轮 3 条 minor 逐条复核，全部已修、无残留、无新增问题：
    - `t034_code_f001`（注释真实性）：头部注释已改为 `--check` 为「开发者/CI 助手」、门禁一致性由 `tests/unit/test_t034_dependency_lock.py` 承担，删除「used by run_gates.sh」不实陈述；核对单测 `uv export --only-group` 六项参数与脚本一致，说明属实。实跑 `bash scripts/generate_requirements.sh --check` 六组全 `requirements ok`、exit 0。
    - `t034_code_f002`（mise 失败 fail-closed）：拆分赋值 `UV_PYTHON="$(mise which python)"` 后 `|| { 报错; exit 1; }`，再追加 `: "${UV_PYTHON:?...}"` 防空值；`set -euo pipefail` 下命令替换失败不再被 `export` 吞掉，两条失败路径均显式失败、根因可见。
    - `t034_code_f003`（pip 诊断 + marker 求值）：`image_freeze` 去掉 `2>/dev/null`，`RuntimeError` 含 stdout+stderr；`normalise` 改用 `packaging.markers.Marker` 按 Linux/CPython 3.15 的 `TARGET_ENV` 求值、不可解析 marker fail-closed。独立复验 marker 求值（win32 排除、darwin/linux 保留、PyPy 排除、`python_version < 3.14` 排除）结果正确；五镜像 `verify_image_packages.py` 重新执行全 MATCH（api 40、gateway 19、supervisor 22、browser 39、stream 35）。
- 定向 pytest：`.scratch/venv315/bin/python -m pytest tests/unit/test_t034_dependency_lock.py tests/unit/test_t034_runtime_paths.py -q` 全绿（7 passed）。
- 6 条 AC 的 TICK-VALID 结论继续有效：本轮仅涉及验证工具的注释、健壮性与归一化修复及 scope 重绑定，未触及 AC-001~006 的产品实现与证据；`coverage = 4 / 6` 不变。
- 处置表 8 行齐全（5 已修、3 遗留均指向 `p044`）；`docs/pending/todo/p044_t034_verification_tooling_followups.md` 存在、格式合法、`fix_ref` 为 `p044`。
- 无新 finding（无 critical / important / minor）；结论 verdict 维持 PASS。

coverage = 4 / 6

建议合并前人工抽查 trust_prior 项

verdict: PASS

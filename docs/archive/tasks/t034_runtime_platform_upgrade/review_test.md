# Task review t034（reviewer_focus: 测试）

- task：`t034_runtime_platform_upgrade`
- spec：`docs/tasks/t034_runtime_platform_upgrade/task.md`
- diff_anchor：`00f828e9cdf4db729c39f36a12ee303cbb7a5910`
- target：`git -C '<repo>_t034' diff 00f828e9cdf4db729c39f36a12ee303cbb7a5910`
- round：1
- reviewed_at：2026-11-05T17:35:21+08:00

reviewed_scope: 4230c0bb95b7ec52

## Findings

### t034_test_f001 - 镜像包比对 markers 规范化只认单引号 win32/pypy，其余 marker 未求值

- 严重度：minor
- 锚点：AC-002 验证工具（镜像内已安装包与 uv.lock 导出一致）
- 位置：`scripts/verify_image_packages.py:17-38`（`normalise()`）
- 问题：`normalise()` 只跳过 `sys-platform == 'win32'` / `sys_platform == 'win32'` 与 `implementation-name == 'pypy'`。PEP 508 变量为 `implementation_name`（下划线），`implementation-name == 'pypy'` 分支永不命中；独立实证 `normalise(["pycparser==3.12 ; implementation_name != 'PyPy'", "bar==2.0 ; sys_platform == 'darwin'", 'baz==3.0 ; platform_system == "Windows"', "foo==1.0 ; python_version < '3.15'"])` 四者全被保留。实际导出文件还含 `platform_python_implementation != 'PyPy'`（`config/docker/browser_runtime/requirements.txt:22,68`）、`sys_platform == 'darwin' or sys_platform == 'linux'`（`config/docker/stream_runtime/requirements.txt:78`）等复合 marker，均被丢弃 marker 后直接计入 expected 集合。当前 5 镜像 MATCH 依赖「目标恰好是 linux/CPython 3.15、这些包都被安装」；一旦 uv.lock 出现 darwin-only / `python_version` 条件包，`missing` 非空即误报 FAIL（fail-closed 方向，不会放过不一致，但会阻塞发布）。
- 建议：用 `packaging.markers.Marker(marker).evaluate()` 针对目标镜像环境（`sys_platform=linux`、`platform_system=Linux`、`implementation_name=cpython`、`python_version=3.15`）求值后决定是否计入 expected；或至少规范化引号与变量名，并显式处理 darwin / `platform_system` / `python_version` 条件。

### t034_test_f002 - 依赖一致性校验工具未接入任何自动化路径，镜像侧比对无落盘证据

- 严重度：minor
- 锚点：AC-002（手改/锁过期即门禁失败、镜像内安装包与导出一致）
- 位置：`scripts/generate_requirements.sh:39-46`（`--check`）、`scripts/verify_image_packages.py:54-70`（`main()`）、`scripts/run_gates.sh:62-63`
- 问题：全仓 `.py`/`.sh` 检索 `generate_requirements` / `verify_image_packages` 仅命中 `test_t034_dependency_lock.py:62` 的提示串与脚本自身 usage 注释，无任何调用方；`run_gates.sh` 只 `uv pip install -r scripts/gate-requirements.txt`，不调 `--check`；`verify_image_packages.py` 不在 E2E / deploy / 门禁中。AC-002 的「requirements 漂移即失败」由 `test_t034_dependency_lock.py::test_each_requirements_is_the_uv_lock_export`（独立复跑 5 passed，真调 `uv export --only-group` 全等比对）覆盖；但「镜像内已安装包与导出一致」仅见 `progress.md:30/33/53` 自述（五镜像 MATCH、api 39→40 包），`.scratch/` 下无机器可读结果落盘。约束禁止 reviewer 重跑 Docker，该半条无法独立复验。
- 建议：把 `generate_requirements.sh --check` 接入 `run_gates.sh`（unit suite 之前或 contract suite），把 `verify_image_packages.py` 接入 E2E/发布校验并把逐镜像结果（JSON/日志）落到 evidence 目录，使 AC-002 两侧都有可复验产物。

### t034_test_f003 - `UV_PYTHON` 解析吞掉 mise 失败，`--check` 缺显式 fail-closed 断言

- 严重度：minor
- 锚点：AC-002 生成物一致性（fail-closed）
- 位置：`scripts/generate_requirements.sh:17`
- 问题：`export UV_PYTHON="$(mise which python)"` 中命令替换失败时 `export` 仍返回 0（`set -e` 不触发），`UV_PYTHON` 静默为空，`uv export` 可能回退到非 3.15 解释器。独立复跑 `bash scripts/generate_requirements.sh --check`：6 组 `requirements ok`、EXIT=0，解析用 `CPython 3.15.2`（mise）；代码层 `set -euo pipefail` + `uv export ... > "$out"` 非 0 即退出、`diff -q` 漂移置 `rc=1` 并 `exit "$rc"`，对「导出失败 / requirements 漂移」整体 fail-closed。但 mise 缺失或未装 3.15 时无显式报错，且 `--check` 无调用方（见 f002）使该路径不被门禁触发。
- 建议：改为 `UV_PYTHON="$(mise which python)" || { echo "mise python 3.15 missing" >&2; exit 1; }` 并加 `: "${UV_PYTHON:?}"`；配合 f002 接入门禁。

### t034_test_f004 - `ignore::DeprecationWarning` 与测试策略「视为错误」矛盾，弃用用法残留检查无触发点

- 严重度：minor
- 锚点：行为缺陷（t034 范围「移除已弃用用法」与上下文区测试策略的验证缺口）
- 位置：`pyproject.toml:55-57`、`docs/tasks/t034_runtime_platform_upgrade/task.md:69`、`.scratch/evidence_t034c/logs/e2e.log:11-15`
- 问题：task.md 测试策略要求「以把 DeprecationWarning 视为错误的方式检查弃用用法残留」，但 `pyproject.toml` 全局 `filterwarnings = ["ignore::DeprecationWarning"]`（该段非 t034 改动，diff 未触及 `[tool.pytest.ini_options]`），`run_gates.sh` 各 pytest 命令无 `-W error::DeprecationWarning`，全仓 `.py` 无 `catch_warnings` / `-W error` 定向检查。E2E 实测 `e2e.log` 出现 3 条 `StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated`（`src/backend/cbrowser/api/internal_supervisor.py:7`）被静默忽略，弃用用法残留无自动验证。
- 建议：为 SQLAlchemy/Alembic/aiosqlite 升级新增定向 `-W error::DeprecationWarning` 的 pytest 运行（或 `filterwarnings` 改为 `error::DeprecationWarning` + 精确 ignore 已知第三方噪声），并修复 `internal_supervisor.py:7` 的 Starlette 弃用常量。

### t034_test_f005 - 动态 find 回归测试为源码文本存在性断言，未触达容器内执行逻辑

- 严重度：minor
- 锚点：行为缺陷（运行时升级不留 Python-minor 写死路径的回归防护深度；写死 `python3.15` 在当前镜像下与动态 find 行为等价，当前无测试可区分）
- 位置：`tests/unit/test_t034_runtime_paths.py:11-19`、`scripts/vendor_selkies_web.py:130-170`、`tests/fixtures/gateway_probe/selkies_assets.py:277-316`
- 问题：`test_selkies_asset_extraction_resolves_path_dynamically` 只读两文件文本，断言 `"python3.12" not in text`、`'exec_run(' in text`、`'find' in text`；不验证 `find` 真在容器内执行、返回路径被 `get_archive` 使用、容器被清理。`python3.12` 黑名单无法防写死 `python3.15`，且任意 `find` 字样（含注释）即满足。`extract_from_stream_image` / `prepare_selkies_web_assets` 无直接单测（`test_vendor_selkies_security.py` 只覆盖 `_safe_relative_path` / `verify_manifest` / `extract_from_wheel`）；真实 `exec_run(find)` + `get_archive` 由 E2E 网关探针执行（diff 显示两处真改为 create+start+exec_run+get_archive，e2e 101 passed）。已调查危险模式：非恒真断言、非删/反转断言、非 `.skip`、非 mock 掉被测逻辑，也不作为任何 AC 的全部证据，判为覆盖深度不足而非危险模式命中。
- 建议：以 `docker.from_env()` 为系统边界 mock，单测 `extract_from_stream_image` / `prepare_selkies_web_assets`：断言 `exec_run` 命令含 `find`、`get_archive` 接收返回路径、异常时 `container.remove(force=True)` 被调用；并把源码断言升级为「不含 `python3.<minor>` 形式的 site-packages 字面量」。

## 第 2 轮复核（scope 重绑定）

- scope：交付内容（f001/f003 修复、Review 处置表、p044、evidence 落盘）变化后重跑 `render_review_prompts.py`，`reviewed_scope` 由 `2c7edb04628d5c87` 重绑定为 `4230c0bb95b7ec52`；本轮针对新 scope 复核，不重开 finding、不改前轮 verdict。
- 已修项复核（2 条 minor，关闭）：
    - `t034_test_f001`：`scripts/verify_image_packages.py` 的 `normalise()` 改用 `packaging.markers.Marker(marker).evaluate(environment=TARGET_ENV)`，`TARGET_ENV` 覆盖 `sys_platform` / `platform_system` / `platform_python_implementation` / `implementation_name` / `python_version` / `python_full_version` / `os_name`（Linux/CPython 3.15），不再字符串硬编码 win32/pypy 死分支；`image_freeze()` 去掉 `2>/dev/null` 改 `capture_output=True`，失败信息含 stdout+stderr（pip stderr 保留）。`.scratch/venv315/bin/python` 实证 8 项全通过：darwin-only 与 Windows 排除、`platform_python_implementation != 'PyPy'` 与 `implementation_name != 'PyPy'` 保留、`python_version < '3.15'` 排除 / `>= '3.15'` 保留、`'darwin' or 'linux'` 复合保留（`all_pass: True`）。
    - `t034_test_f003`：`scripts/generate_requirements.sh` 的 `UV_PYTHON="$(mise which python)"` 拆为 `|| { echo ... >&2; exit 1; }` 并加 `: "${UV_PYTHON:?...}"`，mise 失败显式报错退出；`bash scripts/generate_requirements.sh --check` → 6 组 `requirements ok`、`EXIT=0`、`Using CPython 3.15.2`。
- 定向回归：`.scratch/venv315/bin/python -m pytest tests/unit/test_t034_dependency_lock.py tests/unit/test_t034_runtime_paths.py tests/unit/test_t028_run_gates_evidence.py -q` → `11 passed in 5.30s`（t028 stub 契约未破坏）。
- 遗留项复核（3 条 minor，理由充分、不阻断）：`t034_test_f002`（五镜像比对结果已落盘 `.scratch/evidence_t034c/image_packages/`；`--check` 与 `verify_image_packages.py` 接入自动路径会改变 t028 stub 契约、按 TDD 需整体重写、收益不匹配）、`t034_test_f004`（Starlette 弃用常量/全局 filterwarnings 跨 t034 范围）、`t034_test_f005`（动态 find 的 mock 边界单测深度）均登记 `docs/pending/todo/p044_t034_verification_tooling_followups.md`；`progress.md` Review 处置表 8 行齐全，3 条 `遗留` 的 `fix_ref` 均为 `p044`，p044 存在且逐条对应，无 critical/important 未闭环。
- 镜像侧证据：`.scratch/evidence_t034c/image_packages/` 5 个 `.txt` 全 `OK`（api 40、gateway 19、supervisor 22、browser 39、stream 35），与五镜像重跑 `verify_image_packages.py` MATCH 数一致；按约束未独立重跑 Docker。
- 结论：6 条 AC 的 TICK-VALID 结论继续有效（最后一轮 AC 覆盖仍为下文「AC 复验方式」逐条 6 行，覆盖率声明不变）；本轮无新 finding、无 TICK-VOID、无「迁就实现」的改测；verdict 保持 PASS。

## 结论

- 前轮 finding 复核：无（Round 1 首轮，无前轮报告）
- 改测方向复核：无「迁就实现」的改测。`git -C ... diff 00f828e9` 中测试相关改动仅 `tests/fixtures/gateway_probe/selkies_assets.py`（提取工具代码适配 3.15，非断言）与 `tests/unit/review_privacy_allowlist.txt`（新增指纹数据）；`tests/e2e/test_frontend_build_wiring.py`、`tests/unit/test_t028_run_gates_evidence.py` 原样保留（`diff --stat` 为空），无就地改旧测试预期；两个新增测试均为新增文件。
- 本轮新发现：5 条（全部 minor，无 critical / important）
- 未进表的提示：
    - 假绿专项核查：`test_t034_dependency_lock.py::_export` 真调 `uv export --only-group`（独立复跑 19 passed，其中 5 项依赖真实导出，非 mock）；动态 `find` 真在容器内执行由 E2E fixture 完成（unit 深度见 f005）；`scripts/gate_evidence_manifest.py:61` 的 `all_passed` 仅按 suite `exit_code == 0` 聚合，不把 e2e 2 skip 计入 passed（junit 103 = 101 passed + 2 skipped + 0 failed，skip reason 为 `CBROWSER_T029_PROBE_E2E=1` 探针重跑门控，非失败掩盖）；白名单 `docs/tasks/t033_frontend_toolchain_upgrade/review_general.md` 指纹经 `shasum -a 256` 独立核对为 `89f4a7e8...` 一致，`docs/archive/...` 同名条目为预留归档路径（`approved_snapshots()` 只解析 (path, hash) 对、`test_repo_hygiene.py:133` 遍历 `git ls-files`，不要求文件存在），未豁免任何实际文件。
    - 容器清理（任务 3 核查）：`selkies_assets.py:315-316` / `vendor_selkies_web.py:169-170` 均 `try/finally: container.remove(force=True)`，覆盖 `start` / `exec_run` / `get_archive` 全部异常路径，`create()` 紧邻 try 无中间语句，正常与异常路径无容器泄漏，未出 finding。
    - 版本门禁可绕过（任务 3 核查）：`test_gate_python_minor_matches_images`（`test_t034_dependency_lock.py:94-105`）的 `^FROM\s+python:(\d+\.\d+)-` 只匹配字面量 FROM，未来 Dockerfile 参数化 `FROM python:${PY}-...` 会静默跳过该镜像（当前 6 镜像均字面量 `python:3.15-slim-trixie@sha256:`，有效）；`GATE_PYTHON_MINOR="(\d+\.\d+)"` 改单引号/无引号会令 `assert match is not None` 失败（fail-closed 而非绕过）；`test_gate_interpreter_minor_matches_images` 用真实 `sys.version_info`，不可绕过。`test_no_legacy_requirement_lists` 仅查两处已知路径，未全仓扫描其它手写清单（属可再加 case）。
- 总体判断：5 条均 minor；6 条 AC 全部 TICK-VALID、无 TICK-VOID；无假绿（uv export 真调用、旧测试原样、skip 未计 PASS、白名单指纹已验证）；PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立核对 6 个运行镜像 FROM 全为 `python:3.15-slim-trixie@sha256:...`、browser 辅助阶段 `debian:trixie-slim@sha256:...`，`pyproject.toml:6` 与 `uv.lock` 均 `>=3.15`；两次干净构建镜像 ID 一致依赖 `evidence_t034c/manifest.json` 的 `image_identity` 与 `progress.md:30` 演练记录（未独立重跑构建）。
- AC-002：TICK-VALID，re_verified。独立复跑 `test_t034_dependency_lock.py` 5 passed（真调 `uv export --only-group` 逐组全等比对）与 `bash scripts/generate_requirements.sh --check`（6 组 ok、EXIT=0、CPython 3.15.2）；`test_no_legacy_requirement_lists` 核对 `src/backend/requirements.txt` 与 `config/docker/*/requirements.in` 已删除；镜像 pip freeze 比对见 `progress.md:30/33`（未独立重跑 Docker，工具无自动化调用方，见 f002）。
- AC-003：TICK-VALID，re_verified。独立复跑定向 19 passed（含 `test_gate_interpreter_minor_matches_images` 在 `.scratch/venv315` 3.15 下通过），静态核对 `scripts/run_gates.sh:33` `GATE_PYTHON_MINOR="3.15"`、`.mise.toml` `python=3.15.2`、Dockerfile FROM `python:3.15`；`evidence_t034c/manifest.json` 六 suite `exit_code` 全 0、`all_passed=true`。
- AC-004：TICK-VALID，trust_prior。`evidence_t034c/manifest.json` 六 suite exit 0 / `all_passed=true`，e2e junit 101 passed / 2 skipped / 0 failed，`e2e.log` 尾行 `101 passed, 2 skipped, 3 warnings in 1536.86s`；2 skip 为 `CBROWSER_T029_PROBE_E2E=1` 探针重跑门控（t032 项），非失败；约束禁止 reviewer 独立重跑 E2E。
- AC-005：TICK-VALID，trust_prior。e2e junit gateway/stream/frontend 全 PASS，`test_gateway_ac001_auth_e2e.py:46,90,106,129-130,191` 覆盖经 Caddy 的 HTTPS、`/api/v1/auth/login`、`/api/v1/profiles`、`/stream/{pid}/signal`，`test_stream_selkies_tokens_e2e` 4 项信号令牌门控 PASS；约束禁止独立重跑 E2E。
- AC-006：TICK-VALID，trust_prior。`.scratch/t034_rehearsal/` 的 `publish1.log` / `publish2.log` / `rollback.log`：`cbrowser-t034-rh-*` 隔离实例与独立 volume、publish 两 release、rollback 回 `20261105T0340001-rh1` 且 `{"ready": true}`，三次健康检查全绿；约束禁止独立重跑部署。

coverage = 3 / 6

建议合并前人工抽查 trust_prior 项

## reviewer 复跑记录

- 步骤 1 落点校验：`git rev-parse --show-toplevel`（workdir=t034）→ `<repo>_t034`；`git -C ... diff --name-status 00f828e9` 与 `status --short` 确认全部交付为 staged、anchor=HEAD。
- 轻量单测（3.15 venv）：`.scratch/venv315/bin/python -m pytest tests/unit/test_t034_dependency_lock.py tests/unit/test_t034_runtime_paths.py tests/unit/test_vendor_selkies_security.py tests/unit/test_t028_run_gates_evidence.py -q` → `19 passed in 4.97s`。
- 生成物一致性：`bash scripts/generate_requirements.sh --check` → 6 组 `requirements ok`、`EXIT=0`、`Using CPython 3.15.2 interpreter`（mise）。
- markers 边界实证：`.scratch/venv315/bin/python` 调用 `verify_image_packages.normalise()` → 仅单引号 win32 被跳过，`implementation_name`/`platform_python_implementation`/darwin/`python_version`/双引号 Windows 全部保留，`implementation-name == 'pypy'` 分支不命中。
- 白名单指纹：`shasum -a 256 docs/tasks/t033_frontend_toolchain_upgrade/review_general.md` → `89f4a7e8...` 与 allowlist 一致；archive 路径条目指向不存在文件，按 `test_repo_hygiene.py:90-114,124-148` 不豁免任何实际文件。
- 证据静态复核：解析 `evidence_t034c/junit/e2e.xml`（103 = 101 pass + 2 skip + 0 fail）、`manifest.json`（6 suite exit 0）、`suites.tsv`；`grep` 核对 6 镜像 FROM digest、e2e AC-005 路径断言、`t034_rehearsal` 健康检查；读 `gate_evidence_manifest.py:61` 与 `test_repo_hygiene.py` 判定 skip→PASS 与指纹绑定。
- 格式与门禁：`python3 .repo_template/scripts/md_format.py docs/tasks/t034_runtime_platform_upgrade/review_test.md`、`python3 .repo_template/scripts/check_review_status.py --task-dir docs/tasks/t034_runtime_platform_upgrade`（确认 `review_scope=ok`、`^verdict: PASS` 为最后一行、`^reviewed_scope: 2c7edb04628d5c87` 存在）。
- 未跑：完整门禁与 Docker E2E / 镜像构建 / 部署演练（按约束，已有 `evidence_t034c/` 与 `t034_rehearsal/` 证据）。

verdict: PASS

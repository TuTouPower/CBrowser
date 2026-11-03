# Task review t018（reviewer_focus: 测试）

- task：`t018_v2_test_gates_hygiene`
- spec：`docs/tasks/t018_v2_test_gates_hygiene/task.md`
- diff_anchor：`5a3da225fbccf59d410e708a3754e7ab2160e12b`
- target：`git -C '/Users/karson/kar/code/CBrowser_t018' diff 5a3da225fbccf59d410e708a3754e7ab2160e12b`
- round：1
- reviewed_at：2026-11-03T10:38:14+08:00

reviewed_scope: bdba5aa92c5411d1

## Findings

### t018_test_f001 - 前端新鲜度校验接进生产镜像构建路径，镜像构建必失败

- 严重度：critical
- 锚点：行为缺陷（非范围「不改生产代码行为」）；`config/docker/Dockerfile` 构建从成功变为失败
- 位置：`scripts/verify_frontend_dist.py:120`、`scripts/verify_frontend_dist.py:77`、`config/docker/Dockerfile:18`
- 问题：`verify_frontend_dist()` 现在无条件调用 `verify_frontend_build_freshness(dist_dir)`，该函数默认在 `REPO_ROOT/src/frontend` 计算源码哈希；镜像布局中脚本位于 `/app/scripts`，默认源目录是 `/app/src/frontend`，而基础镜像 `/app` 下只有 `backend/frontend/src/backend`，没有该目录。哈希退化为空目录哈希，与 dist 内 stamp 不一致，构建直接抛 `Frontend dist is stale relative to current source`。已复现：`docker build -f config/docker/Dockerfile -t cbrowser-t018-review-probe .` 在 Dockerfile 第 18 行 exit 1。
- 建议：把源码新鲜度校验限定在仓库/E2E 路径（例如由 `tests/e2e/conftest.py` 或 postbuild 显式传入 `--frontend-dir`），不要从生产镜像使用的 `verify_frontend_dist` 默认调用；镜像内只校验 stamp 存在或改由构建时写入可验证的源指纹。

### t018_test_f002 - 构建接线 E2E 仍断言旧 postbuild，t018 改动后门禁测试变红

- 严重度：important
- 锚点：AC-006（本地全量门禁）与 AC-001（构建新鲜度接线）
- 位置：`tests/e2e/test_frontend_build_wiring.py:61`、`tests/e2e/test_frontend_build_wiring.py:73-75`、`src/frontend/package.json:12`
- 问题：`package.json` 的 `postbuild` 已改成 `python3 ../../scripts/write_frontend_build_stamp.py && npm run verify:selkies`，但测试仍精确断言 `npm run verify:selkies`。实跑 `pytest tests/e2e/test_frontend_build_wiring.py tests/unit/test_frontend_build_freshness.py -q` 结果为 `2 failed, 7 passed`，失败项是 `test_package_build_runs_vendor_and_verification` 和 `test_valid_dist_passes`；`_write_dist` 也没有写 build stamp，新的 freshness 校验使合成 dist 用例无法成立（即使修掉既有 CSS 断言失败）。
- 建议：同步更新 postbuild 断言；在 `_write_dist` 中写入匹配的 stamp（或显式传入临时 `frontend_dir`）；按 A37 将 verify 脚本合成用例移到 `tests/unit`。

### t018_test_f003 - `run_gates.sh` 的 E2E 依赖不完整，E2E 模式无法收集

- 严重度：important
- 锚点：AC-006「本地全量门禁由单一入口脚本执行（含 E2E 必需模式）」
- 位置：`scripts/run_gates.sh:32-35`
- 问题：E2E 的 `uv --with` 列表只有 pytest/pytest-asyncio/playwright/docker/httpx/aiohttp/pydantic/websockets，缺 `fastapi`、`uvicorn`、`sqlalchemy`、`aiosqlite`、`alembic`、`jsonschema`、`argon2-cffi`。用该依赖集实跑 `pytest tests/e2e -q --collect-only` 报 2 个 collection error：`test_browser_runtime_e2e.py` 缺 uvicorn，`test_supervisor_resource_monitor_e2e.py` 缺 fastapi。脚本入口本身无法执行 E2E 必需模式。
- 建议：把 E2E 依赖与 `testing.md`/CI 对齐，并增加一次 `tests/e2e --collect-only` 的入口自检。

### t018_test_f004 - `testing.md` 仍重复完整门禁命令，未做到「只引用该脚本」

- 严重度：important
- 锚点：AC-006「testing.md 只引用该脚本」
- 位置：`docs/blueprint/testing.md:44-49`、`docs/blueprint/testing.md:60-63`、`docs/blueprint/testing.md:75`、`docs/blueprint/testing.md:138-140`
- 问题：文件虽然新增了一句「本地全量门禁统一由 scripts/run_gates.sh 执行」，但 `test_cmd`、`blackbox_verify` 及后续章节仍完整复制同一批 pytest/uv 命令，且 E2E 依赖列表与 `run_gates.sh` 已不一致。两份入口漂移正是本 AC 要消除的对象。
- 建议：门禁段落只保留 `scripts/run_gates.sh` 调用与环境变量说明；`doctor_cmd` 等非门禁命令单独保留，不复制到门禁命令块。

### t018_test_f005 - AC-002 未完成：E2E 仍跨测试模块借用 `real_api_server` fixture

- 严重度：important
- 锚点：AC-002「共享 fixture 由 conftest 提供，不存在跨测试模块的 fixture 借用与 sys.path 注入」
- 位置：`tests/e2e/test_supervisor_startup_recovery_e2e.py:51-58`、`tests/e2e/test_supervisor_policy_failure_e2e.py:42-49`、`tests/unit/test_baseline_fixture_regressions.py:1126`
- 问题：两个 E2E 模块仍用 `importlib.util.spec_from_file_location` 加载 `test_supervisor_core_e2e.py` 并复制其 `real_api_server` fixture（`test_supervisor_startup_recovery_e2e.py:58`、`test_supervisor_policy_failure_e2e.py:49`）；单元回归测试还加载整个 E2E 模块。AC-002 已勾选，但这些跨模块借用没有迁移到 conftest。
- 建议：把 `real_api_server` 移到 `tests/e2e/conftest.py` 或独立 fixture 模块，改为普通 import；删除 `importlib`/`sys.modules` 盗用。

### t018_test_f006 - AC-002 未完成：身份 E2E 仍注入测试专用 Web Locks shim

- 严重度：important
- 锚点：AC-002「身份与信令测试驱动生产 adapter」
- 位置：`tests/e2e/test_stream_client_identity_e2e.py:11-15`、`tests/e2e/test_stream_client_identity_e2e.py:58`；生产实现 `src/frontend/src/features/browser-session/adapter.ts:96-101`
- 问题：测试仍通过 `context.add_init_script(WEB_LOCK_SHIM_JS)` 注入 `tests/fixtures/stream_probe/web_lock_shim.js`，该 shim 自己实现 `navigator.locks` 仲裁，生产 adapter 并未进入被测路径；套件只证明了 shim 行为，不能证明生产身份仲裁。
- 建议：测试加载构建产物中的生产 adapter（`selkies_adapter.js` 或对应构建入口）并删除 shim；至少增加生产 adapter 与 shim 行为等价性的断言后再移除。

### t018_test_f007 - AC-001 未完成：新鲜度门禁只在必需模式生效

- 严重度：important
- 锚点：AC-001「前端 E2E 在构建产物与当前源码内容不一致时拒绝运行并提示重新构建」
- 位置：`tests/e2e/conftest.py:33-35`、`tests/e2e/conftest.py:41-48`
- 问题：`pytest_collection_modifyitems` 在 `CBROWSER_E2E_REQUIRED != "1"` 时直接 return，新鲜度检查位于 return 之后。默认 E2E 运行（不带必需变量）不会拒绝 stale dist；两个前端 harness 也仅检查文件是否存在（`tests/fixtures/frontend_probe/host_builder.py:19-30`、`tests/fixtures/frontend_app_probe/harness.py:22-35`），不会比对源码哈希。AC-001 该句没有「仅在必需模式」限定。
- 建议：把 frontend item 的新鲜度校验移到 required 判断之前，或放进两个 harness 的公共前置；必需模式只控制环境变量缺失时是否硬失败。

### t018_test_f008 - AC-001 未完成：必需模式清单漏掉 `CBROWSER_INVALID_POLICY_TEST_IMAGE`

- 严重度：important
- 锚点：AC-001「缺任何必需的镜像或缓存变量时测试会话开始即失败并列出缺项」
- 位置：`tests/e2e/conftest.py:12-21`、`tests/e2e/test_supervisor_policy_failure_e2e.py:57`、`tests/e2e/test_supervisor_policy_failure_e2e.py:77`
- 问题：`REQUIRED_E2E_ENV` 没有 `CBROWSER_INVALID_POLICY_TEST_IMAGE`；该变量是 `test_policy_installation_failure_fail_closed_and_cleanup` 的必需镜像。必需模式会通过会话开始检查，随后该测试用 `pytest.skip` 静默跳过，仍可形成零覆盖绿。
- 建议：将 `CBROWSER_INVALID_POLICY_TEST_IMAGE` 加入必需清单；非必需模式可保留 skip，必需模式应会话级失败。

### t018_test_f009 - AC-003 未完成：IPv6、退避上限、延迟上限断言仍缺失

- 严重度：important
- 锚点：AC-003「IPv6 阻断、退避上下限、首帧与输入延迟上限等断言覆盖其声明的行为」
- 位置：`tests/e2e/test_supervisor_namespace_policy_e2e.py:547`、`tests/e2e/test_supervisor_namespace_policy_e2e.py:552`；`tests/e2e/test_supervisor_retry_e2e.py:310`、`tests/e2e/test_supervisor_retry_e2e.py:404`、`tests/e2e/test_supervisor_retry_e2e.py:485`；`tests/e2e/test_frontend_app_e2e.py:631`、`tests/e2e/test_frontend_app_e2e.py:685`、`tests/e2e/test_frontend_app_e2e.py:752-753`
- 问题：IPv6 阻断仍用 `if v6_c:` / `if v6_b:` 包裹，地址缺失时静默不验证；退避断言只有 `>= 2/10/30s` 下界，没有上界，重试迟到 10 倍也会通过；frontend app 测试只记录 `first_frame_ms` 与 `input_to_remote_ms` 到证据文件，从未断言上限。AC-003 已勾选但上述声明项均无有效断言。
- 建议：先 `assert v6_b and v6_c` 再无条件执行阻断探针；退避增加 `target + max(5, target*0.5)` 上界；为 first-frame/input latency 设置宽松上限并断言。

### t018_test_f010 - 打包关闭断言由两态放宽为三态

- 严重度：important
- 锚点：AC-003「状态、状态码与日志断言精确到契约规定值」；危险模式：弱化断言
- 位置：`tests/unit/test_supervisor_recovery.py:559-564`（原断言为 `WSMsgType.CLOSE`/`CLOSED`）
- 问题：生产 Gateway 契约测试改写后把 viewer close 断言从两态扩大为 `CLOSE, CLOSED, CLOSING` 三态；`CLOSING` 仅表示关闭进行中，不能证明 Gateway 已完成断开隔离。这是把旧断言往更宽的方向改，属于危险模式中的弱化断言。
- 建议：按 Gateway 契约断言单一终态（通常 `WSMsgType.CLOSE`），或额外等待并断言连接最终 `closed`，不要用三态集合代替。

### t018_test_f011 - AC-007 未完成：live spec 仍含凭据形态测试字面量

- 严重度：important
- 锚点：AC-007「spec 中不含凭据形态的测试字面量」
- 位置：`docs/specs/runtime_persistence.md:90`
- 问题：live spec 仍直接写入 `P@ssw0rd_Secret_999`、`SECRET_TOKEN_XYZ_123`、`SECRET_COOKIE_ABC_456`、`SECRET_CLIPBOARD_CONTENT_789`。A40 明确要求 canary 抽象化、真实夹具值只留在测试代码；AC-007 勾选但未执行该子项。
- 建议：改为抽象描述（如「密码、Token、Cookie、剪贴板四类合成值」），具体 canary 只保留在 `tests/integration/test_v2_api_subprocess.py`。

### t018_test_f012 - AC-007 守卫测试对 `docs/reviews` 与无后缀文本存在盲区

- 严重度：minor
- 锚点：AC-007「已跟踪的非归档文本文件不含家目录绝对路径（由测试守护）」
- 位置：`tests/unit/test_repo_hygiene.py:24`、`tests/unit/test_repo_hygiene.py:12-15`、`tests/unit/test_repo_hygiene.py:27`
- 问题：守卫整体排除 `docs/reviews/`，而该目录当前仍有 7 处 `/Users/karson/`（例如 `docs/reviews/review_20261102_201727/review_intensive.md:861`）；同时只扫描固定后缀，`Dockerfile`、`.gitignore` 等无后缀文本不在扫描范围。A44 只批准历史文档不改，不批准未来 review 文档不守护。
- 建议：把历史具体文件放入 allowlist，而不是排除整个 `docs/reviews/`；无后缀文本按 git 文本文件处理或显式加入 `Dockerfile`/`.gitignore`。

### t018_test_f013 - AC-007 新增 vendor 解包安全逻辑无测试

- 严重度：minor
- 锚点：AC-007「Selkies vendor 解包拒绝穿越条目并校验目录文件集合与清单一致」
- 位置：`scripts/vendor_selkies_web.py:29-33`、`scripts/vendor_selkies_web.py:69-84`；现有用例仅覆盖 happy path（`tests/e2e/test_frontend_adapter_build.py:59-128`）
- 问题：新增的 `_safe_relative_path` 与 `unexpected = actual_files - expected_files` 安全逻辑没有正负用例；路径穿越、清单外文件、反斜杠/绝对路径分支均未被测试触达。
- 建议：补 `../`、绝对路径、反斜杠、清单外文件四类负例，并保留一个正常解包正例。

### t018_test_f014 - AC-001 新鲜度函数仅测 stale，缺 missing/corrupt 与 E2E 接线测试

- 严重度：minor
- 锚点：AC-001
- 位置：`tests/unit/test_frontend_build_freshness.py:12-23`、`tests/e2e/conftest.py:41-48`
- 问题：只覆盖「源码变化导致 stale」；stamp 缺失、不可读 JSON、字段缺失三个 fail-closed 分支以及 conftest 对 frontend item 的实际接线均无测试。
- 建议：为三个异常分支各加一个 `pytest.raises` 用例；用子进程或 `pytester` 覆盖 frontend item 触发的 refusal。

## 结论

- 前轮 finding 复核：不适用（Round 1）。
- 改测方向复核：有 1 处迁就实现——`tests/unit/test_supervisor_recovery.py:559-564` 将连接关闭断言从两态扩为三态（f010）。其余重写基本是从固定 sleep 改事件/注入时钟，并把私有状态断言替换为公开可观察结果，未发现其他「把旧预期改成当前实现输出」的改测。
- 本轮新发现：14 条（critical 1、important 10、minor 3）。
- 未进表的提示：`tests/unit/test_stream_capture_policy.py:155,176` 仍有固定 sleep 后断言，`AC-005` 未勾选且 note 已声明该项遗留，故不按 AC-003 重复出表；若 AC-003 本意覆盖单元层，需要调整 AC 措辞。`tests/e2e/test_frontend_build_wiring.py` 中既有 CSS 断言失败在 diff anchor 前已存在，本报告只在 f002 说明 t018 新增的 stamp/postbuild 影响，不把既有失败归给本 task。note 声称 unit 542，实测 `tests/unit` 为 540 passed（不影响结论）。
- 总体判断：生产镜像构建被破坏、AC-001/002/003/006/007 存在未完成的勾选项，且本地 E2E 门禁当前为红，不能 PASS。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 ... pytest tests/e2e/test_frontend_app_e2e.py`，exit 2 并列出 8 个缺项；核对 `tests/e2e/conftest.py` 与 `tests/unit/test_frontend_build_freshness.py`，发现 f007/f008/f014。
- AC-002：`re_verified`。搜索 `tests/` 的 importlib/sys.path 与身份 E2E shim，核对生产 adapter；发现 f005/f006。
- AC-003：`re_verified`。逐条核对 IPv6/退避/延迟/关闭断言；实跑 `tests/unit` 540 passed、`tests/integration` 79 passed；发现 f009/f010。
- AC-004：`trust_prior`。该 AC 未勾选，且并行双跑需真实 Docker 两轮门禁；本报告不把它作为完成项。
- AC-005：`trust_prior`。该 AC 未勾选，note 自述仍有范围外私有断言与固定延迟；本报告未采信其完成度。
- AC-006：`trust_prior`。CI 全绿需要真实 GitHub Actions 运行；本报告已独立核对 workflow 布局、完整 SHA 钉版、release.yml 删除与本地脚本，但本地 E2E 入口本身失败（f002/f003/f004）。
- AC-007：`re_verified`。实跑 `tests/unit/test_repo_hygiene.py` 2 passed；独立扫描 tracked 非归档文件与 `docs/specs`，发现 f011/f012/f013。

coverage = 4 / 7

建议合并前人工抽查 trust_prior 项。

系统性 follow-up：无（阻断项均属 t018 范围，应在合并前修复；若拆分，建议标题 `修复测试门禁与镜像构建新鲜度接线`，slug `gate_freshness_image_wiring`）。

verdict: FAIL

## Round 2 (2026-11-03T11:07:56+08:00)

- round：2
- reviewed_at：2026-11-03T11:07:56+08:00
- reviewed_scope: da1eae9122b416a2

### t018_test_f015 - 路径隐私守卫当前为红，单入口门禁与 CI unit 均无法通过

- 严重度：important
- 锚点：AC-007「已跟踪的非归档文本文件不含家目录绝对路径（由测试守护）」；AC-006「本地全量门禁……全绿」
- 位置：`tests/unit/test_repo_hygiene.py:18-48`、`tests/unit/review_privacy_allowlist.txt:1-5`
- 问题：守卫已从整体排除 `docs/reviews/` 改为 allowlist，但 allowlist 漏掉两个已跟踪历史文件：`docs/reviews/review_20261102_201727/bundle_global_system_properties.md`（1 处 `/Users/karson/`）与 `bundle_local_archive_tasks.md`（2 处）。这两个文件在 diff anchor 已存在，不依赖本轮 review 产物。实跑 `pytest tests/unit` 得 `1 failed, 539 passed`；失败项即 `test_tracked_files_do_not_leak_developer_home_paths`。实跑 `bash scripts/run_gates.sh` 同样在该步失败，AC-006 的单入口门禁当前为红；CI 的 `v2 unit tests` 步骤也会在同一测试失败。此外当前任务 `review_code.md` / `review_test.md` 的模板要求写入 `git -C '/Users/karson/...'`，也被守卫判为违规，说明守卫未区分「项目内容」与「review 过程文档」。
- 建议：把两个遗漏的历史 review 文件补进 allowlist；明确 review 过程文档的处置（排除 `docs/tasks/**/review_*.md` 或在报告模板中去掉本机绝对路径），确保干净 checkout 下 `pytest tests/unit` 与 `scripts/run_gates.sh` 均可绿。

### t018_test_f016 - postbuild 接线断言由精确等值弱化为子串包含

- 严重度：important
- 锚点：AC-001（postbuild 必须执行新鲜度校验）；危险模式：弱化断言
- 位置：`tests/e2e/test_frontend_build_wiring.py:61`
- 问题：anchor 版本为 `assert scripts["postbuild"] == "npm run verify:selkies"`，本轮改成 `assert "write_frontend_build_stamp.py" in scripts["postbuild"]`。当前实现同时包含写 stamp 和执行 `npm run verify:selkies`，精确期望值已知，却只做了子串包含。这样即使 postbuild 删掉 `&& npm run verify:selkies`，测试仍会通过；`verify:selkies` 脚本内容虽另有断言，但不能证明它被 postbuild 真正调用。这是把断言改成迁就实现，属于弱化断言，不是必要的重构。
- 建议：按当前契约断言完整值，例如 `== "python3 ../../scripts/write_frontend_build_stamp.py && npm run verify:selkies"`；若只关心两个命令都存在，至少分别断言 postbuild 同时包含 stamp 写入与 verify 调用。

## 结论

- 前轮 finding 复核：
    - f001 已消除。实跑 `docker build -f config/docker/Dockerfile` 成功，`verify_frontend_dist()` 默认 `check_freshness=False`，Dockerfile 未传 `--check-freshness`。
    - f002 已消除原红（`test_frontend_build_wiring.py` 现通过），但修复方式把精确等值改成子串包含，属换形式弱化，见 f016。
    - f003 已消除。用 `scripts/run_gates.sh` 的 E2E 依赖实跑 `pytest tests/e2e --collect-only` 得 78 tests collected，无 collection error。
    - f004 仍存在。`docs/blueprint/testing.md:44` 虽声明统一入口，但 `test_cmd` 的 47-49 行、`blackbox_verify` 的 57-63 行、`138-140` 行仍完整复制 pytest/uv 命令；`testing.md:75` 还引用了已删除的 `tests/e2e/test_stream_client_identity_e2e.py`，按文档执行会直接报文件不存在。
    - f005 仍存在。`tests/unit/test_baseline_fixture_regressions.py:1123-1160` 仍用 `importlib` 加载 `tests/e2e/test_supervisor_recovery_e2e.py` 并调用其 `real_api_and_sup` fixture；`test_supervisor_startup_recovery_e2e.py:50-57`、`test_supervisor_policy_failure_e2e.py:41-48` 仍用 `importlib` 执行 `test_supervisor_core_e2e.py`（现为未使用的死加载）。AC-002 的「不存在跨测试模块的 fixture 借用」仍未满足。
    - f006 已消除。`tests/e2e/test_stream_client_identity_e2e.py` 已整体删除，生产前端 `test_frontend_app_e2e.py:447` 的身份/重映射测试走真实构建产物；删除理由与替代覆盖在 note 有说明。
    - f007 仍存在。`tests/e2e/conftest.py:42` 在 `CBROWSER_E2E_REQUIRED != "1"` 时直接返回，新鲜度校验仍只在必需模式执行；两个前端 harness 未新增源码哈希比对。
    - f008 已消除。`REQUIRED_E2E_ENV` 已含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`；实跑必需模式 collection 列出全部 9 个缺项并以 exit 2 终止。
    - f009 仍存在（部分修复）。首帧/输入延迟上限已补（`test_frontend_app_e2e.py:632,688`）；IPv6 仍用 `if v6_c:` / `if v6_b:` 条件包裹（`test_supervisor_namespace_policy_e2e.py:547,552`），退避仍只有 `>= 2/10/30s` 下界（`test_supervisor_retry_e2e.py:310,404,485`），均无上界。
    - f010 仍存在。`tests/unit/test_supervisor_recovery.py:559-564` 的 close 断言仍为 `CLOSE/CLOSED/CLOSING` 三态，`CLOSING` 不能证明断开隔离完成。
    - f011 已消除。`docs/specs/runtime_persistence.md:90` 已移除四类凭据字面量，全量扫 `docs/specs` 未再命中凭据形态字面量。
    - f012 部分消除。`docs/reviews/` 已改为逐文件 allowlist，但漏项导致守卫为红（f015）；`tests/unit/test_repo_hygiene.py:12-15,32` 仍只扫描固定后缀，`Dockerfile`/`.gitignore` 等无后缀文本不在范围内。
    - f013 仍存在（minor）。`tests/e2e/test_frontend_adapter_build.py` 仍只有 vendor happy path，`scripts/vendor_selkies_web.py:29-33,80` 的穿越拒绝与清单外文件校验没有正负用例。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py` 只覆盖 stale，stamp 缺失/不可读/字段缺失与 conftest 实际接线仍无测试。
- 改测方向复核：有 1 处本轮新发现的「迁就实现」——f016 将 postbuild 精确等值改成子串包含。其余大量固定 sleep→轮询、私有状态→公开结果的改写方向正确；未发现其他删断言或反转断言。
- 本轮新发现：2 条（important 2）。
- 未进表的提示：`tests/e2e/test_stream_runtime_e2e.py:32,853` 仍注入 `web_lock_shim.js` 且在后文断言 tab 身份，虽然生产身份覆盖已移到 `test_frontend_app_e2e.py`，该处 shim 建议后续清理，避免与生产 adapter 双重包裹；`docs/specs/runtime_persistence.md:90` 有「注入的注入的」重复措辞；note 声称 unit 542，实测为 540（539 passed + 1 failed）；`scripts/run_gates.sh` 的 `mktemp -d` 目录未清理，属资源卫生小项。
- 总体判断：门禁与守卫当前为红，AC-001/002/003/006/007 仍有未完成的勾选项，不能 PASS。

### AC 复验方式

- AC-001：`re_verified`。实跑必需模式 collection 得到 9 个缺项并 exit 2；核对 `tests/e2e/conftest.py:42` 确认非必需模式不检查新鲜度（f007）；Dockerfile 构建成功确认 f001 已修。
- AC-002：`re_verified`。检索 `tests/` 的 importlib/sys.path 与 E2E fixture，核对生产 Gateway 替换与 `tests/e2e/conftest.py` 的共享 fixture；发现 f005 仍未消除。
- AC-003：`re_verified`。实跑 `tests/unit`（1 failed/539 passed，失败为 f015）与 `tests/integration`（79 passed）；逐条核对 IPv6、退避、延迟与 close 断言，发现 f009/f010。
- AC-004：`trust_prior`。AC 未勾选，且并行两次门禁需真实 Docker 双跑，本轮未执行。
- AC-005：`trust_prior`。AC 未勾选；note 自述范围外仍有私有断言与固定延迟，本轮未采信其完成度。
- AC-006：`trust_prior`（CI 实跑外部服务）。本地部分已独立复验：实跑 `scripts/run_gates.sh` 在 unit 阶段失败（f015），`testing.md` 仍复制完整命令并引用已删除测试（f004）；未执行真实 GitHub Actions。
- AC-007：`re_verified`。实跑 `pytest tests/unit/test_repo_hygiene.py` 失败并列出历史 review 文件（f015）；扫描 `docs/specs` 无凭据字面量；vendor 安全分支无测试（f013）。

coverage = 4 / 7

建议合并前人工抽查 trust_prior 项。

- 系统性 follow-up：无（阻断项均属 t018 范围，应在合并前修复；若拆分，建议标题 `修复仓库卫生守卫与门禁文档漂移`，slug `repo_hygiene_gate_docs`）。

verdict: FAIL

## Round 3 (2026-11-03T11:41:00+08:00)

- round：3
- reviewed_at：2026-11-03T11:41:00+08:00

reviewed_scope: 6c7ccfe25dc088c6

### Findings

#### t018_test_f017 - AC-004 未完成：Selkies token E2E 服务仍发布到所有主机接口

- 严重度：important
- 锚点：AC-004「测试服务只绑定回环」；A21 对 `test_stream_selkies_tokens_e2e.py:94-105` 的明确整改项
- 位置：`tests/e2e/test_stream_selkies_tokens_e2e.py:71`、`tests/e2e/test_stream_selkies_tokens_e2e.py:97-98`
- 问题：`settings.addr = "0.0.0.0"` 且 `docker run -p f"{self.port}:{self.port}"` 没有 `127.0.0.1:` 前缀，真实 Selkies Stream 服务会发布到宿主机所有网络接口。A21 对该文件的要求是改成 `-p 127.0.0.1:{port}:{port}`，本轮未改。`find_free_port()`（:34）仍是「先 bind 再释放」的 TOCTOU 取端口方式，与 A38 的「由 Docker 分配后回读」不符。
- 建议：改为 `127.0.0.1:{self.port}:{self.port}` 发布；端口改由 Docker 分配后回读，删除 `find_free_port` 的 TOCTOU 路径。

#### t018_test_f018 - AC-004 未完成：共享 Gateway 夹具的 secret 目录仍为 0777

- 严重度：important
- 锚点：AC-004「夹具秘密文件与目录仅属主可访问」；A38「夹具 secret 目录 0700」
- 位置：`tests/fixtures/gateway_probe/topology.py:131`、`:135`、`:138`；`tests/unit/test_baseline_fixture_regressions.py:534-576`
- 问题：`control_dir` 内写入 `supervisor_key`、`agent_key`、`gateway_key`、`gateway_api_key`、`admin_password`（:144-155），但目录本身是 `chmod(0o777)`，`metadata_dir` 与 data 子目录同样 0777。秘密文件虽是 0600，目录可写仍允许其他本地用户替换/删除秘密文件。现有 `test_gateway_topology_harness_secrets_permission_0600` 只遍历 `harness.key_files` 断言文件 0600，从未断言目录模式，掩盖了该缺口。
- 建议：秘密文件集中到独立 0700 目录，或把 `control_dir` 收紧到 0700 并将容器需要写的目录拆出；在现有测试中断言目录权限。

#### t018_test_f019 - AC-005 勾选但 A39 点名的单元测试仍断言私有状态/墙钟

- 严重度：important
- 锚点：AC-005「单元测试只经公开接口断言……时间相关逻辑使用注入时钟」
- 位置：`tests/unit/test_supervisor_normal_exit_observation.py:368-369`、`:454`、`:716-733`；`tests/unit/test_docker_offload.py:132-134`；`tests/unit/test_stream_capture_policy.py:155-157`、`:176-178`
- 问题：note 称「范围外单元测试仍有私有断言/固定延迟」，但 `test_supervisor_normal_exit_observation.py` 与 `test_docker_offload.py` 都在 A39 的重点文件清单内。现状仍直接断言 `core._sessions[...]`、`core._terminal_observations`；`test_docker_offload` 用 `elapsed >= 0.25`、`ticks >= 5` 墙钟阈值验证卸载；`test_stream_capture_policy` 用真实 `asyncio.sleep(0.15)` 等墙钟 cooldown 后断言 `pipeline.framerate`。这些用例可随内部字段或机器速度变化假绿/假红，AC-005 的打勾缺少依据。
- 建议：把可观察状态改为生产公开接口（runtime status/health/事件计数），卸载测试改事件 rendezvous，cooldown 与时间断言改注入时钟；确无公开观测面的用例需在 spec/note 明确豁免并从 AC-005 打勾依据中排除。

#### t018_test_f020 - AC-003 未完成：负向 activity 注入仍靠固定 sleep，无「已处理」哨兵

- 严重度：important
- 锚点：AC-003「测试中不存在固定 sleep 后断言状态的模式」；A37「负断言改为发送哨兵有效报文、等其生效后再断言无效报文未生效」
- 位置：`tests/e2e/test_gateway_ac007_visibility_e2e.py:398-419`
- 问题：Phase 5 在页面内 `if (ws && ws.readyState === WebSocket.OPEN)` 才发送伪造的 `cbrowser:"activity"` 帧，随后 `await asyncio.sleep(1.0)`（:411）并断言 gateway/stream 日志无 `visibility_update`（:415-416）、`vis_negative["unpaused_video_consumers"] == 1`（:419）。若 `__last_ws` 已关闭或伪造帧未被 Gateway 处理，注入被条件跳过，断言仍绿；没有哨兵证明注入已被处理。这是 A37 要求消除的负断言真空通过模式，也违反 AC-003 对固定 sleep 的禁令。
- 建议：注入后发送一个可观察哨兵（如有效控制帧/心跳）并等待 Gateway 处理计数或日志确认其生效，再断言 activity 帧没有改变可见性；不要用固定 1s 作为唯一等待。

#### t018_test_f021 - AC-004 未完成：集成/E2E 仍把状态写入仓库 `.scratch`

- 严重度：minor
- 锚点：AC-004「测试状态只写临时目录」；A38「集成测试全部改用 tmp_path」
- 位置：`tests/integration/test_automation_cdp_flow.py:88`、`:244`；`tests/integration/test_normal_exit_replay.py:161`、`:313`、`:466`、`:662`；`tests/integration/test_v2_api_subprocess.py:24-27`、`:76-77`、`:145`；`tests/e2e/test_browser_runtime_e2e.py:48-54`
- 问题：这些用例仍在仓库内 `.scratch/...` 建数据库、日志、UDS、basetemp。`.scratch` 已 gitignore 且子目录带随机后缀，冲突风险低，但与 A38 明确的「集成测试全部改用 tmp_path」不符；同机两轮并行时仍共享 `.scratch` 父目录与 `uv_cache`/`tmp`。
- 建议：改用 pytest `tmp_path`；UDS 短路径用 `tempfile.mkdtemp(dir=...)` 并在用例结束清理。

#### t018_test_f022 - AC-004 证据脱敏无测试

- 严重度：minor
- 锚点：AC-004「证据文件不含会话恢复密钥等敏感值」
- 位置：`tests/fixtures/gateway_probe/evidence.py:26-53`
- 问题：新增的 `_redact` 只按 key 子串命中 `token/secret/password/cookie/resume_key`，并对 `data/payload/frame` 截断，但没有单元测试验证 `save_evidence` 的实际落盘内容；现有 E2E 只调用 `save_evidence`，从不读取输出断言敏感值被替换。该安全约束目前只靠代码目测。
- 建议：加一个 unit 用例：构造含 `resume_key`/`token`/长 `data` 的 payload，调用 `save_evidence(tmp_path, ...)`，断言落盘 JSON 不含原值且含脱敏占位。

### 结论

- 前轮 finding 复核：
    - f001 已消除。`config/docker/Dockerfile:18` 不再传 `--check-freshness`，`scripts/verify_frontend_dist.py:82-83` 默认 `check_freshness=False`，镜像构建路径不再执行源码哈希校验。
    - f002 修不彻底。postbuild 断言已恢复精确等值（`tests/e2e/test_frontend_build_wiring.py:60`），但同文件 `test_valid_dist_passes`（:72-74）仍红：合成 dist 不建 `assets/*.css`，`verify_frontend_dist` 在 `scripts/verify_frontend_dist.py:121` 抛 `Generated CSS is missing .bg-primary`。实跑 `pytest tests/e2e/test_frontend_build_wiring.py -q` 为 `1 failed, 14 passed`；Round 2 的「现通过」结论不成立，本地 E2E 门禁仍红。
    - f003 已消除。用 `scripts/run_gates.sh` 的 E2E 依赖实跑 `pytest tests/e2e --collect-only` 得 78 tests collected，无 collection error。
    - f004 仍存在。`docs/blueprint/testing.md:44` 只加了一句统一入口声明，但 `test_cmd` 的 :47-49、`blackbox_verify` 的 :60、Supervisor 的 :138-140 等仍完整复制 pytest/uv 命令；:75 还引用已删除的 `tests/e2e/test_stream_client_identity_e2e.py`，照文档执行会直接报文件不存在。AC-006「testing.md 只引用该脚本」未满足。
    - f005 仍存在。`tests/unit/test_baseline_fixture_regressions.py:1123-1160` 仍用 `importlib` 加载 `tests/e2e/test_supervisor_recovery_e2e.py` 并借用其 `real_api_and_sup` fixture；`tests/e2e/test_supervisor_startup_recovery_e2e.py:50-57`、`tests/e2e/test_supervisor_policy_failure_e2e.py:41-48` 仍执行 `test_supervisor_core_e2e.py` 的模块级加载（现为未使用的死加载）。AC-002 的「不存在跨测试模块的 fixture 借用」仍未满足。
    - f006 已消除。`tests/e2e/test_stream_client_identity_e2e.py` 已整体删除；`tests/e2e/test_frontend_app_e2e.py:447` 起的身份/重映射用例走构建产物中的生产 adapter。`test_stream_runtime_e2e.py:32,853` 仍注入 `web_lock_shim.js`，但生产身份覆盖已由 frontend app 承担，作为遗留提示，不作为本轮 finding。
    - f007 仍存在。`tests/e2e/conftest.py:41-43` 在 `CBROWSER_E2E_REQUIRED != "1"` 时直接 return，新鲜度校验位于 :49-56，默认 E2E 运行仍不拒绝 stale dist；两个前端 harness 仍只检查文件存在。
    - f008 已消除。`REQUIRED_E2E_ENV` 已含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`；实跑必需模式 collection 列出全部 9 个缺项并以 exit 2 终止。
    - f009 已消除。IPv6 改为先 `assert v6_b and v6_c` 再无条件探针（`test_supervisor_namespace_policy_e2e.py:547-555`）；退避加上界 `target + max(5, target*0.5)`（`test_supervisor_retry_e2e.py:310,404,485`）；首帧/输入延迟上限为 8000/3000ms（`test_frontend_app_e2e.py:631,687`）。
    - f010 仍存在。`tests/unit/test_supervisor_recovery.py:559-564` 的 viewer close 断言仍是 `CLOSE/CLOSED/CLOSING` 三态；新增的 `close_env` 断言只证明 Agent 收到 close 通知，不能证明 viewer 已完成关闭，`CLOSING` 仍不能作为终端状态证据。
    - f011 已消除。`docs/specs/runtime_persistence.md:90` 已无四类凭据字面量；全量扫 `docs/specs` 未再命中凭据形态字面量。
    - f012 部分消除。`docs/reviews/` 已改为逐文件 allowlist 且补入两个历史文件；`tests/unit/test_repo_hygiene.py:15-19,32` 仍只扫描固定后缀，`Dockerfile`、`.gitignore` 等无后缀文本不在范围内（minor 保留）。
    - f013 仍存在（minor）。`tests/e2e/test_frontend_adapter_build.py` 仍只有 vendor happy path；`scripts/vendor_selkies_web.py:29-33,80` 的穿越拒绝与清单外文件校验没有正负用例。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py` 只覆盖 stale；stamp 缺失、不可读 JSON、字段缺失三个 fail-closed 分支与 conftest 实际接线仍无测试。
    - f015 已消除。`tests/unit/review_privacy_allowlist.txt` 已补入两个历史 review 文件；实跑 `tests/unit` 得 540 passed，路径隐私守卫与本地单入口门禁的 unit 阶段转绿。
    - f016 已消除。`tests/e2e/test_frontend_build_wiring.py:60` 已恢复 postbuild 完整精确等值，不再用子串包含。
- 改测方向复核：本轮无新增「迁就实现」的改测。f016 已按契约恢复精确等值；f009 的 IPv6/退避修复方向正确；f002 的 postbuild 部分已修，但同一文件的合成 dist 用例仍红（见上）。
- 本轮新发现：6 条（important 4、minor 2）。
- 未进表的提示：
    - `tests/conftest.py:8-12` 仍集中执行 `sys.path.insert`。若按 AC-002 的「不存在 sys.path 注入」字面理解仍不满足；A36 的修复意图可能是把注入集中到 conftest，建议后续用 pytest `pythonpath` 配置或在 spec 明确该豁免。
    - `tests/e2e/test_stream_runtime_e2e.py:32,853` 仍注入 `web_lock_shim.js` 并在后文断言 tab 身份，建议后续清理，避免与生产 adapter 双重包裹。
    - `scripts/run_gates.sh:7` 的 `mktemp -d` 目录未清理，属资源卫生小项。
    - `test_valid_dist_passes` 的合成 dist 用例按 A37 应移到 `tests/unit`；当前留在 E2E 且红，已在 f002 计入门禁结论。
- 总体判断：f004/f005/f007/f010/f002 以及新增 f017/f018/f019/f020 仍为未解决的 important，AC 打勾复核不成立，不能 PASS。

### AC 复验方式

- AC-001：`re_verified`。实跑必需模式 collection，缺项列出 9 个并以 exit 2 终止；核对 `tests/e2e/conftest.py:41-56` 发现非必需模式不校验新鲜度（f007）；Dockerfile 路径确认 f001 已修。
- AC-002：`re_verified`。检索 `tests/` 的 importlib/sys.path 与 E2E fixture，确认生产 Gateway 替换与共享 fixture 已部分完成；发现 f005 的 importlib 借用仍存在。
- AC-003：`re_verified`。实跑 unit/integration 全绿；逐条核对 IPv6、退避上下限、帧增长、逐页静音、延迟上限已修；发现 f010 三态断言与 f020 负断言哨兵缺失。
- AC-004：`re_verified`。静态审计夹具与 E2E 的端口、chmod、证据脱敏、`.scratch` 写入，发现 f017/f018/f021/f022；并行双跑子项未执行，属 `trust_prior`，不影响失败结论。
- AC-005：`re_verified`。逐文件检索私有断言与墙钟阈值，确认 A39 点名文件仍未整改（f019）。
- AC-006：`trust_prior`。CI 全绿需真实 GitHub Actions 运行；本地已独立复验 contract 169 passed、legacy 384 passed、unit 540 passed、integration 79 passed、前端 95 passed，但 `test_frontend_build_wiring.py` 红（f002），且 testing.md 仍复制门禁命令（f004）。
- AC-007：`re_verified`。实跑 `pytest tests/unit/test_repo_hygiene.py` 2 passed；扫描 `docs/specs` 无凭据字面量；vendor 安全分支仍无测试（f013）。

coverage = 6 / 7

建议合并前人工抽查 trust_prior 项。

- 系统性 follow-up：无（剩余阻断项均属 t018 范围；若拆分，建议标题 `修复 E2E 门禁与 AC-004/005 测试基建`，slug `e2e_gate_ac004_ac005`）。

verdict: FAIL

## Round 4 (2026-11-03T12:22:26+08:00)

- round：4
- reviewed_at：2026-11-03T12:22:26+08:00

reviewed_scope: 12d0d1493026e812

### Findings

#### t018_test_f023 - 门禁入口当前为红：testing.md 移除契约命令后模板契约测试失败

- 严重度：important
- 锚点：AC-006「每次 push 由 CI 在 Linux 上运行契约、legacy 与 v2 单元、集成与前端测试及构建并全绿」「本地全量门禁由单一入口脚本执行」
- 位置：`docs/blueprint/testing.md:42-46`、`.repo_template/tests/test_contract_suite.py:82-96`、`scripts/run_gates.sh:19`
- 问题：Round 3 为消除 f004 把 `test_cmd` 改成只写 `scripts/run_gates.sh`，但模板契约 `test_testing_md_default_commands_use_contract_marker` 要求 `test_cmd` 的 pytest 行恰为 `pytest .repo_template/tests -q -m contract`。实跑 `pytest .repo_template/tests -q -m contract` 得 `1 failed, 168 passed`；实跑 `bash scripts/run_gates.sh` 在第一步以 exit 1 终止。`.github/workflows/ci.yml:26` 的 Contract tests 步骤同样必然失败，因此 AC-006 的单入口门禁和 CI 全绿均不成立。`note.md` 声称 contract 169 通过，与当前树不符。
- 建议：在 `test_cmd` 中恢复模板要求的契约命令行（或按模板约定记录消费仓定制状态且保证 CI checkout 中同样可见），重新实跑 `pytest .repo_template/tests -q -m contract` 与 `scripts/run_gates.sh` 到全绿；不要删除契约层对默认命令的断言。

#### t018_test_f024 - 监督循环重启退避断言由精确列表弱化为成员包含

- 严重度：important
- 锚点：AC-003「状态、状态码与日志断言精确到契约规定值」；AC-005「时间相关逻辑使用注入时钟」；危险模式：弱化断言
- 位置：`tests/unit/test_stream_runtime.py:260`
- 问题：diff 把 `assert delays == [1.0]` 改成 `assert 1.0 in clock.delays`。该用例已把 reconciliation loop 与 motion loop 都替换为「失败一次后阻塞」的路径，公共 `agent.start()` 只会产生一次 1.0s 重启退避，精确列表断言仍成立；成员包含无法发现多次重启（如 `[1.0, 2.0]`）或其他循环也睡 1.0s 的回归。这是为适配新公共生命周期而放宽断言，不是规格变化。
- 建议：恢复精确断言（`assert clock.delays == [1.0]`，或断言 `count(1.0) == 1` 且无其他延迟），保留 `agent.start()` 驱动。

#### t018_test_f025 - AC-003 清理校验仍在 finally 内抛错，会覆盖原始失败

- 严重度：important
- 锚点：AC-003「清理校验不掩盖原始失败」
- 位置：`tests/e2e/test_supervisor_policy_failure_e2e.py:241`、`tests/e2e/test_supervisor_container_graph_e2e.py:675`（`test_runtime_coordinator_e2e.py:490`、`test_supervisor_recovery_e2e.py:1069` 已由 code review `t018_code_f005` 记录）
- 问题：`test_supervisor_policy_failure_e2e.py:241` 的 `assert not cleanup_errors` 与 `test_supervisor_container_graph_e2e.py:675` 的 `assert not ownership_violations` 仍在 `finally` 内。主体先失败且清理也失败时，`finally` 的新异常会替换原始异常，原始失败现场被覆盖，正是 AC-003 要求消除的模式。container_graph 位点与 code review f005 重合，policy_failure 位点是本轮新增。
- 建议：`finally` 只做清理并收集错误，清理断言移到 `finally` 之后或 fixture teardown 中；保证主体异常优先保留。

### 结论

- 前轮 finding 复核：
    - f001 已消除。`config/docker/Dockerfile:18-20` 未传 `--check-freshness`，`scripts/verify_frontend_dist.py:82-83` 默认 `check_freshness=False`。
    - f002 仍存在。实跑 `pytest tests/e2e/test_frontend_build_wiring.py tests/unit/test_frontend_build_freshness.py -q` 得 `1 failed, 8 passed`，失败项 `test_valid_dist_passes` 仍因合成 dist 无 `assets/*.css` 抛 `Generated CSS is missing .bg-primary`（`scripts/verify_frontend_dist.py:121`）。该失败在 diff anchor 前已存在，但 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 仍无法全绿，task 的 E2E 门禁声明仍不成立。
    - f003 已消除。用 `scripts/run_gates.sh` 的 E2E 依赖实跑 `pytest tests/e2e -q --collect-only` 得 78 tests collected，无 collection error。
    - f004 核心问题已改，但引入 f023。`test_cmd` 与 `blackbox_verify` 现在只引用 `scripts/run_gates.sh`；代价是模板契约测试转红，单入口门禁无法执行。`docs/blueprint/testing.md:62` 仍引用已删除的 `tests/e2e/test_stream_client_identity_e2e.py`（code review `t018_code_f015` 已记录）。
    - f005 仍存在。`tests/unit/test_baseline_fixture_regressions.py:1123-1160` 仍用 `importlib` 加载 `tests/e2e/test_supervisor_recovery_e2e.py` 并驱动其 `real_api_and_sup` fixture；AC-002 的「不存在跨测试模块的 fixture 借用」仍未满足（另见 code review `t018_code_f016` 的前置条件分散）。
    - f006 已消除。身份 E2E 已整体删除，构建产物中的生产 adapter 由 `tests/e2e/test_frontend_app_e2e.py` 覆盖。
    - f007 仍存在。`tests/e2e/conftest.py:41-43` 在 `CBROWSER_E2E_REQUIRED != "1"` 时直接 return，新鲜度校验位于 :51-56；默认 E2E 运行仍不拒绝 stale dist，两个前端 harness 未做源码哈希比对。
    - f008 已消除。`REQUIRED_E2E_ENV` 含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`；实跑必需模式列出 9 个缺项并终止 collection。
    - f009 已消除。IPv6 先 `assert v6_b and v6_c` 再无条件探针（`test_supervisor_namespace_policy_e2e.py:547-555`）；退避有上下界（`test_supervisor_retry_e2e.py:310,404,485`）；首帧/输入延迟上限为 8000/3000ms（`test_frontend_app_e2e.py:631,687`）。
    - f010 仍存在。`tests/unit/test_supervisor_recovery.py:559-564` 的 viewer close 仍接受 `CLOSE/CLOSED/CLOSING` 三态，`CLOSING` 不能证明断开完成。
    - f011 已消除。`docs/specs` 未再命中四类凭据字面量。
    - f012 仍存在（minor）。`tests/unit/test_repo_hygiene.py:15-19,32` 仍只扫描固定后缀，`Dockerfile`、`.gitignore` 等无后缀文本不在守卫范围。
    - f013 仍存在（minor）。`scripts/vendor_selkies_web.py:29-33,80` 的穿越拒绝与清单外文件校验仍只有 happy path 覆盖。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py` 只覆盖 stale，stamp 缺失/不可读/字段缺失与 conftest 实际接线仍无测试。
    - f015 已消除。实跑 `pytest tests/unit` 得 540 passed，路径隐私守卫转绿。
    - f016 已消除。`tests/e2e/test_frontend_build_wiring.py:60` 已恢复 postbuild 完整精确等值。
    - f017 仍存在。`tests/e2e/test_stream_selkies_tokens_e2e.py:71` 仍 `settings.addr = "0.0.0.0"`，`:97-98` 仍发布到所有接口，`:32` 仍用先 bind 后释放的 `find_free_port`。
    - f018 仍存在。`tests/fixtures/gateway_probe/topology.py:131,135,138` 的 secret 目录仍为 0777；现有测试只断言文件 0600。
    - f019 仍存在。`tests/unit/test_supervisor_normal_exit_observation.py:368-369,454,716-733`、`test_docker_offload.py:57-58,132-133`、`test_stream_capture_policy.py:155,176` 仍断言私有字段或使用墙钟等待；这些文件在 A39 清单内且本轮无改动。
    - f020 仍存在。`tests/e2e/test_gateway_ac007_visibility_e2e.py:398-419` 的负向 activity 注入仍靠 `if (ws && OPEN)` 条件发送，无「已处理」哨兵，随后固定 `sleep(1.0)` 断言日志无 `visibility_update`。
    - f021 仍存在（minor）。集成/E2E 仍在仓库 `.scratch` 写状态（如 `tests/integration/test_v2_api_subprocess.py:25-27`）。
    - f022 仍存在（minor）。`tests/fixtures/gateway_probe/evidence.py:26-53` 的脱敏逻辑仍无落盘内容断言。
- 改测方向复核：有 1 处迁就实现——f024 把精确列表断言改成成员包含；f023 的文档改动不是「迁就实现」，但直接破坏了模板契约门禁。
- 本轮新发现：3 条（important 3）。
- 未进表的提示：
    - `docs/blueprint/testing.md:62` 与 `docs/blueprint/stream_runtime.md:49` 仍引用已删除的 `tests/e2e/test_stream_client_identity_e2e.py`（code review `t018_code_f015` 已登记）。
    - `tests/e2e/test_stream_runtime_e2e.py:44-58` 的动态端口仍是先探测后释放（code review `t018_code_f017` 已登记）。
    - `tests/unit/test_stream_runtime.py:232` 的 `assert clock.delays` 仅证明发生过任一 sleep，证据强度弱，不作为 AC 证据。
    - `git diff --check` 报 `tests/e2e/conftest.py:139` 文件末尾多一空行（风格问题，不阻断）。
    - `docs/specs/runtime_persistence.md:90` 仍有「注入的注入的」重复措辞（code review `t018_code_f021` 已登记）。
- 总体判断：本地单入口门禁在 contract 第一步即红，f002/f005/f007/f010/f017/f018/f019/f020 仍未解决，AC 打勾复核不成立，不能 PASS。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only`，列出 9 个缺项并终止；核对 `tests/e2e/conftest.py:41-56` 确认非必需模式不校验新鲜度（f007）。
- AC-002：`re_verified`。核对 `tests/e2e/conftest.py` 的共享 `real_api_server`、`tests/fixtures/supervisor_recovery_probe/gateway_service.py` 驱动生产 Gateway，以及集成测试的 401/409/503 覆盖；发现 f005 的 importlib 借用仍存在。
- AC-003：`re_verified`。实跑 unit 540 passed、integration 79 passed；逐条核对 IPv6、退避上下限、冻结帧增长、首帧/输入延迟、会话关闭实例断言；发现 f010/f020/f025。
- AC-004：`re_verified`（静态子项）。审计端口、回环绑定、chmod、证据脱敏与 `.scratch` 写入，发现 f017/f018/f021/f022；同机并行双跑子项仍为 `trust_prior`，本轮未执行。
- AC-005：`re_verified`。静态核对 A39 清单文件，确认 f019 仍存在；note 自述的「范围外」不构成豁免。
- AC-006：`trust_prior`（CI 实跑）。本地已独立复验：`scripts/run_gates.sh` 在 contract 步骤 exit 1（f023），`test_frontend_build_wiring.py` 1 failed（f002）；真实 GitHub Actions 未执行，但契约失败已足以判定 CI 不会全绿。
- AC-007：`re_verified`。实跑 `pytest tests/unit/test_repo_hygiene.py -q` 2 passed；扫描 `docs/specs` 无凭据字面量；`tests/unit/review_privacy_allowlist.txt` 覆盖历史 review 文件；vendor 安全分支仍无测试（f013）。

coverage = 6 / 7

建议合并前人工抽查 trust_prior 项。

- 系统性 follow-up：无新增跨 task 缺口；f023 需在 t018 内同时解决 testing.md 与模板契约的冲突（若需模板层配合，按 `repo-template-sync` 流程升格）。

verdict: FAIL

## Round 5 (2026-11-03T12:43:09+08:00)

- round：5
- reviewed_at：2026-11-03T12:43:09+08:00

reviewed_scope: 8a91451b6f27a76d

### Findings

本轮无新 finding。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f001 已消除。`config/docker/Dockerfile:18-20` 只传 `--dist`/`--manifest`，`scripts/verify_frontend_dist.py:83` 默认 `check_freshness=False`，生产镜像构建不再校验源码哈希。
    - f002 仍存在。实跑 `pytest tests/e2e/test_frontend_build_wiring.py tests/unit/test_frontend_build_freshness.py -q` 得 `1 failed, 8 passed`；失败项仍是 `test_valid_dist_passes`（`tests/e2e/test_frontend_build_wiring.py:72`），合成 dist 不建 `assets/*.css`，`scripts/verify_frontend_dist.py:121` 抛 `Generated CSS is missing .bg-primary`。`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 会在 E2E 阶段命中该红。
    - f003 已消除。用 `scripts/run_gates.sh` 的 E2E 依赖实跑 `pytest tests/e2e -q --collect-only` 得 `78 tests collected`，无 collection error。
    - f004 核心已修。`docs/blueprint/testing.md:40-46` 的 `test_cmd` 与 `:49-55` 的 `blackbox_verify` 只保留 `scripts/run_gates.sh` 入口；`testing.md:63` 与 `docs/blueprint/stream_runtime.md:49` 仍引用已删除的 `tests/e2e/test_stream_client_identity_e2e.py`，该文档漂移由 code review `t018_code_f015` 登记，本轮不重复出表。
    - f005 仍存在。`tests/unit/test_baseline_fixture_regressions.py:1119-1160` 仍用 `importlib.util.spec_from_file_location` 加载 `tests/e2e/test_supervisor_recovery_e2e.py`，取 `real_api_and_sup.__wrapped__` 驱动其 fixture；AC-002「不存在跨测试模块的 fixture 借用」仍未满足。`test_supervisor_startup_recovery_e2e.py` 与 `test_supervisor_policy_failure_e2e.py` 的 importlib 死加载已删除。
    - f006 已消除。`tests/e2e/test_stream_client_identity_e2e.py` 整体删除，身份/重映射由 `tests/e2e/test_frontend_app_e2e.py:494-565` 驱动构建产物中的生产 adapter。
    - f007 仍存在。`tests/e2e/conftest.py:41-43` 在 `CBROWSER_E2E_REQUIRED != "1"` 时直接 return，新鲜度校验位于 `:49-55`；默认 E2E 运行仍不拒绝 stale dist，两个前端 harness 未做源码哈希比对。
    - f008 已消除。`REQUIRED_E2E_ENV` 含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`；实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 列出 9 个缺项并以 exit 2 终止。
    - f009 已消除。IPv6 先 `assert v6_b and v6_c` 再无条件探针（`tests/e2e/test_supervisor_namespace_policy_e2e.py:547-555`）；退避有上下界（`tests/e2e/test_supervisor_retry_e2e.py:310,404,485`）；首帧/输入延迟上限为 8000/3000ms（`tests/e2e/test_frontend_app_e2e.py:631,687`）。
    - f010 仍存在。`tests/unit/test_supervisor_recovery.py:560-564` 的 viewer close 断言仍接受 `CLOSE/CLOSED/CLOSING` 三态；`CLOSING` 不是终端状态，`close_env` 只证明 Agent 收到 close 通知。
    - f011 已消除。`docs/specs/runtime_persistence.md:90` 已无四类凭据字面量，全量扫 `docs/specs` 未命中凭据形态字面量。
    - f012 仍存在（minor）。`tests/unit/test_repo_hygiene.py:12-19,32` 仍只扫描固定后缀（外加 `.gitattributes`），`Dockerfile`、`.gitignore` 等无后缀文本不在守卫范围。
    - f013 仍存在（minor）。`scripts/vendor_selkies_web.py:29-33,80` 的穿越拒绝与清单外文件校验仍只有 happy path 覆盖（`tests/e2e/test_frontend_adapter_build.py` 无 `_safe_relative_path`/`outside the manifest` 正负用例）。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py:12-23` 只覆盖 stale；stamp 缺失、不可读 JSON、字段缺失三个 fail-closed 分支与 conftest 实际接线仍无测试。
    - f015 已消除。实跑 `pytest tests/unit` 得 `540 passed`，路径隐私守卫与本地单入口门禁的 unit 阶段转绿。
    - f016 已消除。`tests/e2e/test_frontend_build_wiring.py:60` 已恢复 postbuild 完整精确等值。
    - f017 仍存在。`tests/e2e/test_stream_selkies_tokens_e2e.py:71` 仍 `settings.addr = "0.0.0.0"`，`:98` 仍发布 `f"{self.port}:{self.port}"`（无 `127.0.0.1:` 前缀），`:32-34` 仍用先 bind 后释放的 `find_free_port`。
    - f018 仍存在。`tests/fixtures/gateway_probe/topology.py:131,135,138` 的 control/metadata/data 目录仍 `chmod(0o777)`；`tests/unit/test_baseline_fixture_regressions.py:572-576` 只断言 secret 文件 0600，未断言目录模式。
    - f019 仍存在。`tests/unit/test_supervisor_normal_exit_observation.py:368-369,454,716-719` 仍断言 `core._sessions`/`core._terminal_observations`；`tests/unit/test_docker_offload.py:57-58,132-133` 仍用 `elapsed >= 0.25`/`ticks >= 5` 墙钟阈值；`tests/unit/test_stream_capture_policy.py:155,176` 仍用真实 `asyncio.sleep(0.1/0.15)` 后断言 framerate。
    - f020 仍存在。`tests/e2e/test_gateway_ac007_visibility_e2e.py:398-419` 的负向 activity 注入仍以 `if (ws && ws.readyState === WebSocket.OPEN)` 条件发送，无「已处理」哨兵，随后固定 `sleep(1.0)` 断言日志无 `visibility_update`。
    - f021 仍存在（minor）。集成/E2E 仍在仓库 `.scratch` 写状态，如 `tests/integration/test_v2_api_subprocess.py:25-27`、`tests/integration/test_automation_cdp_flow.py:88,244`、`tests/e2e/test_browser_runtime_e2e.py:48-54`。
    - f022 仍存在（minor）。`tests/fixtures/gateway_probe/evidence.py:26-53` 的脱敏逻辑仍无落盘内容断言。
    - f023 已消除。实跑 `pytest .repo_template/tests -q -m contract` 得 `169 passed, 477 deselected`；实跑 `scripts/run_gates.sh`（非 E2E）依次通过 contract、legacy、unit、integration、前端测试与构建，单入口门禁转绿。
    - f024 已消除。`tests/unit/test_stream_runtime.py:260` 已恢复 `assert clock.delays == [1.0]` 精确列表断言。
    - f025 修不彻底。`tests/e2e/test_supervisor_policy_failure_e2e.py:242` 的 `assert not cleanup_errors` 已移出 `finally`；`tests/e2e/test_supervisor_container_graph_e2e.py:672-676` 的 `assert not ownership_violations`（及 `:681` 的 `raise RuntimeError`）仍在 `finally` 内，主体失败时仍会被清理异常替换（该位点与 code review `t018_code_f005` 重合）。
- 改测方向复核：本轮无「迁就实现」的改测。f023 恢复模板契约行、f024 恢复精确退避列表、f025 把 policy_failure 清理断言移出 `finally`，均为恢复/强化断言方向；未发现删断言、反转断言或新的弱化形式。
- 本轮新发现：0 条。
- 未进表的提示：
    - `docs/blueprint/testing.md:63` 与 `docs/blueprint/stream_runtime.md:49` 仍引用已删除的 `tests/e2e/test_stream_client_identity_e2e.py`（code review `t018_code_f015` 已登记）。
    - `tests/unit/test_stream_runtime.py:232`、`tests/unit/test_stream_agent_lifecycle.py:432` 等处 `assert clock.delays` 仅证明发生过 sleep，证据强度弱，不作为 AC 证据。
    - `tests/e2e/conftest.py:67-69` 的共享 `real_api_server` 端口仍是先 bind 后释放（与 f017 同类 TOCTOU），并行双跑下存在端口竞争风险，未单列。
    - AC-005 的额外私有断言：`tests/unit/test_baseline_fixture_regressions.py:973,1009,1048,1110`（`api._log_file_handle`）、`tests/unit/test_supervisor_recovery.py:394-395`（`core._sessions`）仍未公开接口化；属 f019 同一系统性问题的补充位点。
    - `tests/e2e/test_stream_runtime_e2e.py:33,854` 仍注入 `web_lock_shim.js`，生产身份覆盖已由 frontend app E2E 承担，建议后续清理双重包裹。
    - `tests/unit/test_stream_runtime.py:232` 的 `_wait_until` 使用 `asyncio.sleep(0)` 紧轮询，依赖事件循环让出；当前用例通过，但长时间等待时可能空转。
- 总体判断：f023/f024 已修、f025 部分修，但 f002/f005/f007/f010/f017/f018/f019/f020 与 f025 的 container_graph 位点仍未解决，AC-001/002/003/004/005 的打勾复核仍不成立，不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；剩余阻断项均属 t018 范围。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only`，列出 9 个缺项并以 exit 2 终止；核对 `tests/e2e/conftest.py:41-55` 确认非必需模式不校验新鲜度（f007）；`tests/unit/test_frontend_build_freshness.py` 仅覆盖 stale（f014）。
- AC-002：`re_verified`。核对 `tests/fixtures/supervisor_recovery_probe/gateway_service.py` 驱动生产 `create_gateway_app`、重写替身文件已删除、`tests/conftest.py` 统一导入路径；发现 f005 的 importlib 借用仍存在。
- AC-003：`re_verified`。实跑 unit 540 passed、integration 79 passed；逐条核对 IPv6、退避上下限、冻结帧增长、首帧/输入延迟、会话关闭实例断言；发现 f010/f020/f025。
- AC-004：`re_verified`（静态子项）。审计端口、回环绑定、chmod、证据脱敏与 `.scratch` 写入，发现 f017/f018/f021/f022；同机并行双跑子项仍为 `trust_prior`，本轮未执行。
- AC-005：`re_verified`。静态核对 A39 清单文件，确认 f019 仍存在；补充私有断言位点见结论提示。
- AC-006：`trust_prior`（CI 实跑）。本地已独立复验：`scripts/run_gates.sh` 全绿（contract 169、legacy、unit 540、integration 79、前端测试与构建）；CI workflow 布局与完整 SHA 钉版已核对，真实 GitHub Actions 未执行。
- AC-007：`re_verified`。实跑 `pytest tests/unit/test_repo_hygiene.py -q` 2 passed；扫描 `docs/specs` 无凭据字面量；`tests/unit/review_privacy_allowlist.txt` 覆盖历史 review 文件；vendor 安全分支仍无测试（f013）。

coverage = 6 / 7

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 6 (2026-11-03T13:06:00+08:00)

- round：6
- reviewed_at：2026-11-03T13:06:00+08:00

reviewed_scope: 0bb96e6d2f5a5fcd

### Findings

本轮无新 finding。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f001 已消除。`config/docker/Dockerfile:18-20` 只传 `--dist`/`--manifest`，`scripts/verify_frontend_dist.py:82-83` 默认 `check_freshness=False`，生产镜像构建不再校验源码哈希。
    - f002 已消除。实跑 `pytest tests/e2e/test_frontend_build_wiring.py tests/unit/test_frontend_build_freshness.py -q` 得 `11 passed`；`tests/e2e/test_frontend_build_wiring.py:45-52` 的 `_write_dist` 现生成含 `.bg-primary`/`.text-primary-foreground` 的 `assets/index.css`，`test_valid_dist_passes` 转绿，postbuild 仍为完整精确等值。
    - f003 已消除。用 `scripts/run_gates.sh` 的 E2E 依赖实跑 `pytest tests/e2e -q --collect-only` 得 `78 tests collected`，无 collection error。
    - f004 门禁段落已消除。`docs/blueprint/testing.md:40-54` 的 `test_cmd` 与 `blackbox_verify` 只保留 `scripts/run_gates.sh` 入口。`testing.md:63` 与 `docs/blueprint/stream_runtime.md:49` 仍引用已删除的 `tests/e2e/test_stream_client_identity_e2e.py`，属组件验证段文档漂移，归 code review `t018_code_f015`，不重复出表。
    - f005 仍存在。`tests/unit/test_baseline_fixture_regressions.py:1119-1180` 仍用 `importlib.util.spec_from_file_location` 加载 `tests/e2e/test_supervisor_recovery_e2e.py`，取 `real_api_and_sup.__wrapped__` 驱动其 fixture；AC-002「不存在跨测试模块的 fixture 借用」仍未满足。
    - f006 已消除。`tests/e2e/test_stream_client_identity_e2e.py` 整体删除，身份/重映射由 `tests/e2e/test_frontend_app_e2e.py` 驱动构建产物中的生产 adapter。
    - f007 仍存在。`tests/e2e/conftest.py:41-43` 在 `CBROWSER_E2E_REQUIRED != "1"` 时直接 return，新鲜度校验位于 `:49-55`；默认 E2E 运行仍不拒绝 stale dist，两个前端 harness 未做源码哈希比对。
    - f008 已消除。`REQUIRED_E2E_ENV` 含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`；实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 列出 9 个缺项并以 exit 2 终止（`78 tests collected`，无 collection error）。
    - f009 已消除。IPv6 先 `assert v6_b and v6_c` 再无条件探针（`tests/e2e/test_supervisor_namespace_policy_e2e.py:547-555`）；退避有上下界（`tests/e2e/test_supervisor_retry_e2e.py:310,404,485`）；首帧/输入延迟上限为 8000/3000ms（`tests/e2e/test_frontend_app_e2e.py:631,687`）。
    - f010 仍存在。`tests/unit/test_supervisor_recovery.py:559-564` 的 viewer close 断言仍接受 `WSMsgType.CLOSE/CLOSED/CLOSING` 三态；`CLOSING` 是关闭进行中，不证明断开隔离已完成，`close_env` 只证明 Agent 收到 close 通知。同轮 `tests/e2e/test_supervisor_container_graph_e2e.py:470-481` 对同一契约只接受 `CLOSE`，两处强度不一致。
    - f011 已消除。`docs/specs/runtime_persistence.md:90` 已无四类凭据字面量，全量扫 `docs/specs` 未命中凭据形态字面量。
    - f012 仍存在（minor）。`tests/unit/test_repo_hygiene.py:12-19,32` 仍只扫描固定后缀（外加 `.gitattributes`），`Dockerfile`、`.gitignore` 等无后缀文本不在守卫范围。
    - f013 仍存在（minor）。`scripts/vendor_selkies_web.py:29-33,80` 的穿越拒绝与清单外文件校验仍只有 happy path 覆盖（`tests/e2e/test_frontend_adapter_build.py:42-139` 无 `_safe_relative_path`/`outside the manifest` 正负用例）。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py:12-23` 只覆盖 stale；stamp 缺失、不可读 JSON、字段缺失三个 fail-closed 分支与 conftest 实际接线仍无测试。
    - f015 已消除。实跑 `pytest tests/unit` 得 `540 passed`，路径隐私守卫与门禁 unit 阶段转绿。
    - f016 已消除。`tests/e2e/test_frontend_build_wiring.py:64` 已恢复 postbuild 完整精确等值。
    - f017 仍存在。`tests/e2e/test_stream_selkies_tokens_e2e.py:71` 仍 `settings.addr = "0.0.0.0"`，`:97-98` 仍发布 `f"{self.port}:{self.port}"`（无 `127.0.0.1:` 前缀），`:32-34` 仍用先 bind 后释放的 `find_free_port`。
    - f018 仍存在。`tests/fixtures/gateway_probe/topology.py:131,135,138` 的 control/data/metadata 目录仍 `chmod(0o777)`；`tests/unit/test_baseline_fixture_regressions.py:573-577` 只断言 secret 文件 0600，未断言目录模式。
    - f019 修不彻底。A39 点名的私有状态断言已通过公开观测接口整改（`test_supervisor_normal_exit_observation.py`、`test_stream_capture_policy.py` 的 `_is_paused`/墙钟 cooldown），但 `tests/unit/test_docker_offload.py:57-58,132-133` 仍用 `elapsed >= 0.25`/`ticks >= 5` 墙钟阈值验证卸载，未按 A39「线程内阻塞期间的事件 rendezvous」整改；同一 A39 文件 `tests/unit/test_stream_capture_policy.py:229-231,340-345` 仍断言 `agent._supervisor_fps_cap`、`agent._loop_task` 私有成员。AC-005「时间相关逻辑使用注入时钟」「只经公开接口断言」仍不成立。
    - f020 仍存在。`tests/e2e/test_gateway_ac007_visibility_e2e.py:398-419` 的负向 activity 注入仍以 `if (ws && ws.readyState === WebSocket.OPEN)` 条件发送，无「已处理」哨兵，随后固定 `asyncio.sleep(1.0)` 断言日志无 `visibility_update`。
    - f021 仍存在（minor）。集成/E2E 仍在仓库 `.scratch` 写状态，如 `tests/integration/test_v2_api_subprocess.py:25-27`、`tests/integration/test_automation_cdp_flow.py:88,244`、`tests/e2e/test_browser_runtime_e2e.py:48-54`。
    - f022 仍存在（minor）。`tests/fixtures/gateway_probe/evidence.py:26-53` 的脱敏逻辑仍无落盘内容断言。
    - f023 已消除。实跑 `pytest .repo_template/tests -q -m contract` 得 `169 passed, 477 deselected`；本轮实跑 `bash scripts/run_gates.sh` 全链路通过（contract、legacy、unit 540、integration 79、前端 Vitest 与 build/verify）。
    - f024 已消除。`tests/unit/test_stream_runtime.py` 已恢复精确退避列表断言。
    - f025 已消除。`tests/e2e/test_supervisor_container_graph_e2e.py:672-681` 的 `ownership_violations` 与 `cleanup_errors` 断言已移出 `finally`；`finally` 只收集并清理。主体失败时清理断言不再替换原始异常。
- 改测方向复核：无。本轮新增改动（f002 fixture 补 CSS、f019 公开观测接口、f025 断言移出 `finally`）均为恢复/强化覆盖或消除掩盖，没有「迁就实现」的改测。
- 本轮新发现：0 条。
- 未进表的提示：
    - 契约区 AC-004/AC-006 的收敛（删除 GitHub Actions、取消同机双跑）经用户 2026-11-03 明确确认，本报告不按 drift 处理。
    - `tests/e2e/conftest.py:67-69` 的共享 `real_api_server` 端口仍是先 bind 后释放（与 f017 同类 TOCTOU），并行风险已随用户取消双跑要求降级，未单列。
    - `tests/e2e/test_stream_runtime_e2e.py:33,854` 仍注入 `web_lock_shim.js`，生产身份覆盖已由 frontend app E2E 承担，建议后续清理双重包裹。
    - `tests/unit/test_stream_runtime.py:232`、`tests/unit/test_stream_agent_lifecycle.py:432` 等处 `assert clock.delays` 仅证明发生过 sleep，证据强度弱，不作为 AC 证据。
    - `docs/specs/runtime_persistence.md:90` 仍有「注入的注入的」重复措辞（code review `t018_code_f021` 已登记）。
- 总体判断：f002/f023/f024/f025 已修，f019 部分修，但 f005/f007/f010/f017/f018/f019/f020 仍未解决，AC-001/002/003/004/005 的打勾复核不成立，不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；剩余阻断项均属 t018 范围。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only`，列出 9 个缺项并以 exit 2 终止；非必需模式收集 78 tests 无 error。核对 `tests/e2e/conftest.py:41-55` 确认非必需模式不校验新鲜度（f007）；`tests/unit/test_frontend_build_freshness.py` 仅覆盖 stale（f014）。
- AC-002：`re_verified`。核对 `tests/e2e/conftest.py:60-138` 的共享 `real_api_server`、`tests/fixtures/supervisor_recovery_probe/gateway_service.py` 驱动生产 `create_gateway_app`、`tests/integration/test_supervisor_gateway_control_auth.py` 的 401 覆盖；`test_stream_client_identity_e2e.py` 已删除且生产 adapter 由 frontend E2E 覆盖。发现 f005 的 importlib 借用仍存在。
- AC-003：`re_verified`。实跑 unit 540 passed、integration 79 passed、`scripts/run_gates.sh` 全绿；逐条核对 IPv6、退避上下限、冻结帧增长、逐页静音、首帧/输入延迟、会话关闭实例不变断言；发现 f010/f020。
- AC-004：`trust_prior`（单次真实 Docker E2E）。静态子项已核对端口、回环绑定、chmod、证据脱敏与 `.scratch` 写入，发现 f017/f018/f021/f022；声明要求的真实 Docker 单轮门禁本轮未由 reviewer 执行。
- AC-005：`re_verified`。实跑 `pytest tests/unit` 540 passed；静态核对 A39 清单文件，确认 f019 仍不彻底。
- AC-006：`re_verified`。本轮实跑 `bash scripts/run_gates.sh` 全链路通过；`.github/workflows/ci.yml`、`release.yml` 已按用户决定删除；`docs/blueprint/testing.md:42-54` 只引用该脚本。
- AC-007：`re_verified`。实跑 `pytest tests/unit/test_repo_hygiene.py -q` 2 passed；扫描 `docs/specs` 无凭据字面量；`.gitattributes` 行尾规则生效且 `git ls-files --eol` 无 CRLF；vendor 安全分支仍无测试（f013）。

coverage = 6 / 7

verdict: FAIL

## Round 7 (2026-11-03T13:35:00+08:00)

- round：7
- reviewed_at：2026-11-03T13:35:00+08:00

reviewed_scope: 67b51ace6478e8ad

### Findings

#### t018_test_f026 - AC-002 前置条件仍未收敛到单一模块，缺失/格式错误语义分裂

- 严重度：important
- 锚点：AC-002「测试前置条件由单一模块定义且语义一致」；A36「缺失=skip、格式错=fail、必需模式=硬失败」
- 位置：`tests/fixtures/e2e_env.py:11-26`、`tests/e2e/conftest.py:19-29`、`tests/e2e/test_runtime_profile_defaults_e2e.py:42-56,438-442`、`tests/e2e/test_stream_runtime_e2e.py:37-39,473-475`、`tests/e2e/test_supervisor_event_shutdown_e2e.py:49-60`
- 问题：本轮新增 `require_e2e_env`，但只迁移了部分文件。`tests/e2e/conftest.py:19-29` 仍维护第二份 `REQUIRED_E2E_ENV`；`test_runtime_profile_defaults_e2e.py` 用自己的 `check_prerequisites`（含硬编码默认镜像/缓存）并在镜像不可用时整类 skip；`test_stream_runtime_e2e.py:473-475` 与 `test_supervisor_event_shutdown_e2e.py:56-60` 仍自行读取变量并在缺失时 `assert`/`pytest.fail`。语义与 A36 不一致：非必需模式下缺变量有的 skip、有的 fail；`require_e2e_env(paths=...)` 对「路径不是目录」这类格式错误在非必需模式也 `pytest.skip`（`tests/fixtures/e2e_env.py:20-25`），而 A36 要求格式错=fail。由此同一门禁在不同入口得到不同的跳过/失败集合；required 模式又只校验变量存在，`test_runtime_profile_defaults_e2e.py` 仍可在镜像未构建时整类跳过。
- 建议：把镜像/缓存可用性检查与变量清单全部移入 `tests/fixtures/e2e_env.py`，conftest 复用同一份必需清单；删除各文件本地检查，统一「缺失=skip、格式错=fail、required=硬失败」。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f001 已消除。`config/docker/Dockerfile:18-20` 未传 `--check-freshness`，`scripts/verify_frontend_dist.py` 的 `verify_frontend_dist` 默认 `check_freshness=False`。
    - f002 已消除。实跑 `pytest tests/e2e/test_frontend_build_wiring.py tests/unit/test_frontend_build_freshness.py -q` 得 `9 passed`；`tests/e2e/test_frontend_build_wiring.py:67` 的 postbuild 仍为完整精确等值。
    - f003 已消除。用 `scripts/run_gates.sh` 的 E2E 依赖实跑 `pytest tests/e2e -q --collect-only` 得 `78 tests collected`，无 collection error。
    - f004 门禁段落已消除。`docs/blueprint/testing.md:43-55` 的 `test_cmd` 与 `blackbox_verify` 只保留 `scripts/run_gates.sh` 入口；`docs/blueprint/stream_runtime.md:49` 仍引用已删除的 `tests/e2e/test_stream_client_identity_e2e.py`，该文档漂移归 code review `t018_code_f015`，不重复出表。
    - f005 仍存在。`tests/unit/test_baseline_fixture_regressions.py:1123-1160` 仍用 `importlib.util.spec_from_file_location` 加载 `tests/e2e/test_supervisor_recovery_e2e.py`，取 `real_api_and_sup.__wrapped__` 驱动其 fixture；AC-002「不存在跨测试模块的 fixture 借用」仍未满足（`tests/conftest.py` 的 `sys.path.insert` 已移除，改用 pyproject `pythonpath`）。
    - f006 已消除。`tests/e2e/test_stream_client_identity_e2e.py` 整体删除；`tests/e2e/test_frontend_app_e2e.py:446-565` 的身份/重映射用例驱动构建产物中的生产 adapter。
    - f007 仍存在。`tests/e2e/conftest.py:42-43` 在 `CBROWSER_E2E_REQUIRED != "1"` 时直接 return，新鲜度校验位于 `:49-56`；两个前端 harness 仍只检查文件存在，未比对源码哈希。默认 E2E 运行不会拒绝 stale dist。
    - f008 已消除。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 以 exit 2 列出全部 9 个缺项。
    - f009 已消除。IPv6 先 `assert v6_b and v6_c` 再无条件探针（`tests/e2e/test_supervisor_namespace_policy_e2e.py:547-555`）；退避有上下界（`tests/e2e/test_supervisor_retry_e2e.py:305-306,399-400,480-481`）；首帧/输入延迟上限为 8000/3000ms（`tests/e2e/test_frontend_app_e2e.py:631,687`）。
    - f010 仍存在。`tests/unit/test_supervisor_recovery.py:560-564` 的 viewer close 断言仍接受 `CLOSE/CLOSED/CLOSING` 三态；`CLOSING` 是关闭进行中，不证明断开隔离完成。同契约的 `tests/e2e/test_supervisor_container_graph_e2e.py:470-481` 只接受 `CLOSE`，两处强度不一致。
    - f011 已消除。`docs/specs/runtime_persistence.md:90` 已无四类凭据字面量，扫描 `docs/specs` 未命中。
    - f012 仍存在（minor）。`tests/unit/test_repo_hygiene.py:12-15,32` 仍只扫描固定后缀（外加 `.gitattributes`），`Dockerfile`、`.gitignore` 等无后缀文本不在守卫范围。
    - f013 仍存在（minor）。`scripts/vendor_selkies_web.py:29-33,69-84` 的穿越拒绝与清单外文件校验仍只有 happy path 覆盖（`tests/e2e/test_frontend_adapter_build.py` 无 `_safe_relative_path`/`outside the manifest` 正负用例）。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py:12-23` 只覆盖 stale；stamp 缺失、不可读 JSON、字段缺失三个 fail-closed 分支与 conftest 实际接线仍无测试。
    - f015 已消除。实跑 `pytest tests/unit` 得 `540 passed`，路径隐私守卫转绿。
    - f016 已消除。`tests/e2e/test_frontend_build_wiring.py:67` 已恢复 postbuild 完整精确等值。
    - f017 仍存在。`tests/e2e/test_stream_selkies_tokens_e2e.py:71` 仍 `settings.addr = "0.0.0.0"`，`:97-98` 仍发布 `f"{self.port}:{self.port}"`（无 `127.0.0.1:` 前缀），`:32-34` 仍用先 bind 后释放的 `find_free_port`。
    - f018 仍存在。`tests/fixtures/gateway_probe/topology.py:131,135,138` 的 control/data/metadata 目录仍 `chmod(0o777)`；`tests/unit/test_baseline_fixture_regressions.py:534-577` 只断言 secret 文件 0600，未断言目录模式。
    - f019 仍存在。`tests/unit/test_docker_offload.py:47,51-58,65,126-133` 仍用真实 `time.sleep(0.3)`、`elapsed >= 0.25`、`ticks >= 5` 墙钟阈值验证卸载，未按 A39「线程内阻塞期间的事件 rendezvous」整改。其余 A39 文件已改用公开接口/注入时钟。
    - f020 仍存在。`tests/e2e/test_gateway_ac007_visibility_e2e.py:398-416` 的负向 activity 注入仍以 `if (ws && ws.readyState === WebSocket.OPEN)` 条件发送，无「已处理」哨兵，随后固定 `asyncio.sleep(1.0)` 断言日志无 `visibility_update`。
    - f021 仍存在（minor）。集成/E2E 仍在仓库 `.scratch` 写状态，如 `tests/integration/test_v2_api_subprocess.py:24-27`、`tests/integration/test_automation_cdp_flow.py:88,244`、`tests/e2e/test_browser_runtime_e2e.py:48-54`。
    - f022 仍存在（minor）。`tests/fixtures/gateway_probe/evidence.py:26-53` 的脱敏逻辑仍无落盘内容断言。
    - f023 已消除。实跑 `pytest .repo_template/tests -q -m contract` 得 `169 passed, 477 deselected`。
    - f024 已消除。`tests/unit/test_stream_runtime.py:260` 已恢复 `assert clock.delays == [1.0]` 精确列表断言。
    - f025 已消除。`tests/e2e/test_supervisor_container_graph_e2e.py:670-679` 的 `ownership_violations`/`cleanup_errors` 断言已移出 `finally`；`tests/e2e/test_supervisor_policy_failure_e2e.py:241-243` 与 `tests/e2e/test_runtime_coordinator_e2e.py:489-491` 同样在 `finally` 之后。
- 改测方向复核：无。本轮 68816d8 主要是前置条件集中化与端口运行内派生；未发现把断言改成迁就实现的改动（f026 是迁移不完整，不是断言弱化）。`test_supervisor_policy_failure_e2e.py:63-67` 把「缓存路径必须是目录」从 hard assert 改为非必需模式 skip，已纳入 f026。
- 本轮新发现：1 条（important 1）。
- 未进表的提示：
    - 真实 Docker E2E 未执行（worktree 无 `.scratch/images_env.txt`/镜像变量），AC-004 的单次资源隔离仍依赖实施侧证据。
    - `tests/fixtures/e2e_env.py:29-46` 的 `free_udp_port_span` 仍是探测后释放；用户已取消并行双跑要求，单次运行风险低，未单列。
    - `tests/e2e/conftest.py:66-69` 的共享 `real_api_server` 端口仍是先 bind 后释放，同上。
    - `tests/e2e/test_stream_runtime_e2e.py:853` 仍注入 `web_lock_shim.js`，生产身份覆盖已由 frontend app E2E 承担，建议后续清理双重包裹。
    - `tests/unit/test_stream_resume.py:150,209` 等待 `agent._detached_upstreams`、`tests/unit/test_stream_binding_guards.py:115` 读取 `agent.policy._supervisor_fps_cap` 作为基线，仍是私有状态耦合，但未用于最终断言。
    - `docs/blueprint/stream_runtime.md:49` 仍引用已删除的 `tests/e2e/test_stream_client_identity_e2e.py`（code review `t018_code_f015` 已登记）。
- 总体判断：f005/f007/f010/f017/f018/f019/f020 与新增 f026 仍未解决，AC-001/002/003/004/005 的打勾复核不成立，不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；f026 与 code review `t018_code_f016` 同源，应在 t018 内收敛。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 以 exit 2 列出 9 个缺项；核对 `tests/e2e/conftest.py:41-56` 确认非必需模式不校验新鲜度（f007）；`tests/unit/test_frontend_build_freshness.py` 仅覆盖 stale（f014）。
- AC-002：`re_verified`。核对 `tests/e2e/conftest.py` 的共享 `real_api_server`、`tests/fixtures/supervisor_recovery_probe/gateway_service.py` 驱动生产 `create_gateway_app`、重写替身文件已删除、`tests/integration/test_supervisor_gateway_control_auth.py` 的 401 覆盖；发现 f005/f026。
- AC-003：`re_verified`。实跑 `tests/unit` 540 passed、`tests/integration` 79 passed；逐条核对 IPv6、退避上下限、冻结帧增长、逐页静音、首帧/输入延迟、会话关闭实例不变断言；发现 f010/f020。
- AC-004：`trust_prior`（真实 Docker 单次门禁）。静态子项已核对端口派生、回环绑定、chmod、证据脱敏与 `.scratch` 写入，发现 f017/f018/f021/f022；单次真实 Docker 门禁本轮未由 reviewer 执行，依赖实施侧 note 证据。
- AC-005：`re_verified`。实跑 `tests/unit` 540 passed；静态核对 A39 清单文件，确认 f019 仍存在。
- AC-006：`re_verified`。实跑 `pytest .repo_template/tests -q -m contract`（169 passed）、`tests/unit`（540 passed）、`tests/integration`（79 passed）与 `tests/e2e --collect-only`（78 tests）；`.github/workflows` 已不存在，`docs/blueprint/testing.md:43-55` 只引用 `scripts/run_gates.sh`。前端 Vitest/build 层未在本轮重跑，沿用 Round 6 的全链路证据。
- AC-007：`re_verified`。实跑 `tests/unit` 540 passed（含 `test_repo_hygiene.py`）；扫描 `docs/specs` 无凭据字面量；归档 spike 秘密文件被 `.gitignore` 命中；`git ls-files --eol` 无 CRLF；vendor 安全分支仍无测试（f013）。

coverage = 6 / 7

verdict: FAIL

## Round 8 (2026-11-03T14:03:49+08:00)

- round：8
- reviewed_at：2026-11-03T14:03:49+08:00

reviewed_scope: 59c4147af0c39ad0

### Findings

#### t018_test_f027 - docker offload 单测改为恒真断言，事件循环阻塞回归不再可被发现

- 严重度：critical
- 锚点：AC-005「测试 docstring 与实际覆盖一致」；危险模式：恒真断言 / 删除行为断言
- 位置：`tests/unit/test_docker_offload.py:42-54`、`tests/unit/test_docker_offload.py:62-65`、`tests/unit/test_docker_offload.py:124-133`
- 问题：两个用例的唯一断言分别是 `assert ticks[1] == 1`（:54）与 `assert ticks == 1`（:133），而 `ticks` 是测试自身 `unblock()` 的常量返回值（`return 1`），与生产是否把阻塞调用卸载到线程无关。`blocking_teardown`（:44）与 `inspect_container`（:65）虽调用 `release.wait(2)`，但丢弃了返回值。若实现退化为在事件循环内直接执行，事件循环被阻塞 2 秒后 `release.wait` 超时返回，`unblock` 随后照样返回 1，断言仍通过。已用同一 rendezvous 骨架、把 `teardown_profile` 改为同步直接调用（不卸载）复现：输出 `ticks [None, 1] -> assert ticks[1]==1 -> True`，耗时 2.01s，测试通过；第一个用例甚至在 `_teardown_profile_sync` 完全不被调用时也会通过（`unblock` 等 2s 后返回 1）。因此文件标题「Blocking Docker SDK work must not stall the Supervisor event loop」与用例名声称的行为已无任何测试证据，且这是从原 `elapsed >= 0.25` / `ticks >= 5` 行为断言退化为恒真断言，AC-005 的 docstring/覆盖一致性不成立。
- 建议：让阻塞桩断言自己等到了事件循环的放行，例如把 `release.wait(2)` 改为 `assert release.wait(2), "event loop did not run while blocking call pending"`，并对 `started.wait(2)` 的返回值断言；卸载缺失时 `wait` 超时返回 False，用例必红。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f001 已消除。`config/docker/Dockerfile:18-21` 只传 `--dist`/`--manifest`，`scripts/verify_frontend_dist.py:82-83` 默认 `check_freshness=False`。
    - f002 已消除。实跑 `pytest tests/e2e/test_frontend_build_wiring.py tests/unit/test_frontend_build_freshness.py -q` 得 `11 passed`；`tests/e2e/test_frontend_build_wiring.py:67` 的 postbuild 仍为完整精确等值。
    - f003 已消除。非必需模式实跑 `pytest tests/e2e -q --collect-only` 得 `78 tests collected`，无 collection error。
    - f004 门禁段落已消除。`docs/blueprint/testing.md:40-54` 的 `test_cmd`/`blackbox_verify` 只保留 `scripts/run_gates.sh` 入口；`docs/blueprint/stream_runtime.md:49` 仍引用已删除的 `tests/e2e/test_stream_client_identity_e2e.py`，该文档漂移归 code review `t018_code_f015`，不重复出表。
    - f005 仍存在。`tests/unit/test_baseline_fixture_regressions.py:1123-1180` 仍用 `importlib.util.spec_from_file_location` 加载 `tests/e2e/test_supervisor_recovery_e2e.py` 并驱动 `real_api_and_sup.__wrapped__`；AC-002「不存在跨测试模块的 fixture 借用」仍未满足。
    - f006 已消除。`tests/e2e/test_stream_client_identity_e2e.py` 整体删除；`tests/e2e/test_frontend_app_e2e.py` 的身份/重映射用例驱动构建产物中的生产 adapter。
    - f007 已消除。`tests/e2e/conftest.py:31-39` 的新鲜度校验已移到必需模式判断（:41-42）之前；默认 E2E 运行遇到 stale dist 会在 collection 阶段拒绝。缺 fail-closed 分支测试（见 f014）。
    - f008 已消除。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 列出全部 9 个缺项并以 exit 2 终止。
    - f009 已消除。IPv6 先 `assert v6_b and v6_c` 再无条件探针；退避有上下界；首帧/输入延迟上限为 8000/3000ms。
    - f010 已消除。`tests/unit/test_supervisor_recovery.py:560-561` 已恢复为精确 `WSMsgType.CLOSE`。
    - f011 已消除。`docs/specs` 未再命中四类凭据字面量。
    - f012 仍存在（minor）。`tests/unit/test_repo_hygiene.py:12-15,32` 仍只扫描固定后缀（外加 `.gitattributes`），`Dockerfile`、`.gitignore` 等无后缀文本不在守卫范围。
    - f013 仍存在（minor）。`scripts/vendor_selkies_web.py:29-33,69-84` 的穿越拒绝与清单外文件校验仍只有 happy path 覆盖。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py:12-23` 只覆盖 stale；stamp 缺失、不可读 JSON、字段缺失三个 fail-closed 分支与 conftest 实际接线仍无测试。
    - f015 已消除。实跑 `tests/unit` 得 `540 passed`，路径隐私守卫转绿。
    - f016 已消除。postbuild 断言仍为完整精确等值。
    - f017 已消除。`tests/e2e/test_stream_selkies_tokens_e2e.py:71` 已改为 `settings.addr = "127.0.0.1"`，`:98` 已改为 `127.0.0.1:{port}:{port}`；端口仍用 bind 后释放的 `find_free_port`（:32-35），用户已取消并行双跑，单次运行风险低，见提示。
    - f018 已消除。`tests/fixtures/gateway_probe/topology.py:131` 的 secret 目录已收为 0700，`tests/unit/test_baseline_fixture_regressions.py:577-580` 新增目录模式断言；`data`/`metadata` 子目录仍 0777，但不再存放密钥文件。
    - f019 修不彻底（转 f027）。墙钟阈值与私有断言已移除，但替代的 event rendezvous 不构成可失败的卸载断言，卸载行为仍无有效测试。
    - f020 仍存在。`tests/e2e/test_gateway_ac007_visibility_e2e.py:399-419` 的负向 activity 注入仍以 `if (ws && ws.readyState === WebSocket.OPEN)` 条件发送，无「已处理」哨兵，随后固定 `asyncio.sleep(1.0)` 断言日志无 `visibility_update`。
    - f021 仍存在（minor）。集成/E2E 仍在仓库 `.scratch` 写状态，如 `tests/integration/test_v2_api_subprocess.py:25-27`、`tests/integration/test_automation_cdp_flow.py:88,244`、`tests/e2e/test_browser_runtime_e2e.py:48-54`。
    - f022 仍存在（minor）。`tests/fixtures/gateway_probe/evidence.py:26-53` 的脱敏逻辑仍无落盘内容断言。
    - f023 已消除。实跑 `pytest .repo_template/tests -q -m contract` 得 `169 passed, 477 deselected`。
    - f024 已消除。`tests/unit/test_stream_runtime.py:260` 已恢复 `assert clock.delays == [1.0]` 精确列表断言。
    - f025 已消除。`tests/e2e/test_supervisor_container_graph_e2e.py:670-679` 与 `tests/e2e/test_supervisor_policy_failure_e2e.py:241-243` 的清理断言均在 `finally` 之后。
    - f026 仍存在。`REQUIRED_E2E_ENV` 已收敛到 `tests/fixtures/e2e_env.py:11-20` 且 conftest 复用，但各文件仍维护第二套检查：`tests/e2e/test_runtime_profile_defaults_e2e.py:28-58,437-442` 用硬编码默认镜像并在镜像缺失时整类 skip（required 模式也会零覆盖绿）；`tests/e2e/test_stream_runtime_e2e.py:473-475` 与 `tests/e2e/test_supervisor_event_shutdown_e2e.py:48-63` 在测试内自行读取并 fail；`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:43-70` 另行维护 skip 语义。AC-002「前置条件由单一模块定义且语义一致」仍未满足。
- 改测方向复核：有 1 处改测造成覆盖虚化——f027（把墙钟行为断言换成测试自身返回值的恒真断言），非「迁就实现」的预期值调整但属危险模式。其余本轮改动（f010 收紧 close 断言、f018 增加目录权限断言、f007 前置新鲜度校验）均为强化方向；未发现其他迁就实现、反转或注释掉断言。
- 本轮新发现：1 条（critical 1）。
- 未进表的提示：
    - `tests/e2e/conftest.py:31-39` 的 freshness 校验对所有文件名含 `frontend` 的 E2E 用例生效，`test_frontend_build_wiring.py` 这类验证 verifier 自身的合成用例在没有新鲜 dist 的干净 checkout 中无法收集；A37 建议的「合成用例移到 unit」仍未做（当前不红，仅提示）。
    - `tests/e2e/test_supervisor_retry_e2e.py:43-46` 重复 import `e2e_env`（风格）。
    - `tests/fixtures/e2e_env.py:24` docstring 仍写「fail in required mode, skip otherwise」，但路径格式错误现在总是 fail（A36 语义正确，docstring 过时）。
    - `tests/fixtures/e2e_env.py:40-55` 的 `free_udp_port_span` 仍是 bind 后释放的 TOCTOU；用户已取消并行双跑，单跑风险低。
    - `tests/e2e/test_stream_runtime_e2e.py:853` 仍注入 `web_lock_shim.js`，生产身份覆盖已由 frontend app E2E 承担，建议后续清理双重包裹。
- 总体判断：f005/f020/f026 仍未解决，f019 以 f027 形式保留（卸载行为无有效测试），AC-002/003/005 的打勾复核不成立，不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；f005/f020/f026/f027 均属 t018 范围。

### AC 复验方式

- AC-001：`re_verified`。实跑默认模式 `pytest tests/e2e -q --collect-only`（78 tests collected）与 `CBROWSER_E2E_REQUIRED=1` 同命令（列出 9 个缺项、exit 2）；核对 `tests/e2e/conftest.py:31-46` 确认新鲜度检查已前置于必需模式判断。fail-closed 分支缺测试（f014 minor）。
- AC-002：`re_verified`。核对 `tests/fixtures/e2e_env.py:11-20` 的单一必需清单与 conftest 导入；检索 importlib 与各文件本地前置检查，发现 f005、f026 仍未满足。
- AC-003：`re_verified`。实跑 `tests/unit` 540 passed、`tests/integration` 79 passed；逐条核对 IPv6、退避上下限、冻结帧增长、首帧/输入延迟、会话关闭实例不变断言，f010/f025 已修，f020 仍在。
- AC-004：`trust_prior`（真实 Docker 单次门禁）。静态核对 control 目录 0700、Selkies 回环绑定、证据脱敏与 `.scratch` 写入，f017/f018 已修，f021/f022 minor 仍在；声明要求的单次真实 Docker 门禁本轮未由 reviewer 执行。
- AC-005：`re_verified`。实跑 `tests/unit` 540 passed；静态核对 A39 清单文件，发现 f027（恒真断言）致 AC-005 仍不成立。
- AC-006：`re_verified`（本地部分）。实跑 contract 169 passed、unit 540、integration 79、前端 Vitest 95 passed、`tests/e2e --collect-only` 78；`.github/` 已不存在，`docs/blueprint/testing.md:40-54` 只引用 `scripts/run_gates.sh`。`CBROWSER_RUN_E2E=1` 的真实 Docker 全链路未执行（归 AC-004 trust_prior）。
- AC-007：`re_verified`。实跑 `tests/unit` 540 passed（含 `test_repo_hygiene.py`）；扫描 `docs/specs` 无凭据字面量；归档 spike README 与 `.gitignore` 秘密路径规则存在；`git ls-files --eol` 无 CRLF；vendor 安全分支仍无测试（f013）。

coverage = 6 / 7

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 9 (2026-11-03T14:45:00+08:00)

- round：9
- reviewed_at：2026-11-03T14:45:00+08:00

reviewed_scope: 06dd68eaa92d59b2

### Findings

本轮无新 finding；f020、f026 两个前轮 blocker 未修完，按原 ID 复核，证据见下。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f001 已消除。`config/docker/Dockerfile:18-20` 未传 `--check-freshness`，`scripts/verify_frontend_dist.py:82-83` 默认 `check_freshness=False`。
    - f002 已消除。`pytest tests/e2e/test_frontend_build_wiring.py tests/e2e/test_frontend_adapter_build.py -q` 得 12 passed；postbuild 精确等值断言仍在 `tests/e2e/test_frontend_build_wiring.py:67`。
    - f003 已消除。默认模式 `pytest tests/e2e -q --collect-only` 得 79 tests collected，无 collection error。
    - f004 门禁段落已消除。`docs/blueprint/testing.md:40-54` 的 `test_cmd`/`blackbox_verify` 只保留 `scripts/run_gates.sh` 入口；`docs/blueprint/stream_runtime.md:49` 仍引用已删除的 `tests/e2e/test_stream_client_identity_e2e.py`，该文档漂移归 code review `t018_code_f015`，不重复出表。
    - f005 已消除。`tests/unit/test_baseline_fixture_regressions.py` 中 importlib 加载 E2E 模块并借用 `real_api_and_sup` 的用例已删除，测试整体迁入同模块 `tests/e2e/test_supervisor_recovery_e2e.py:1079`；全仓已无 `spec_from_file_location` 跨模块 fixture 借用，实跑该用例 1 passed。
    - f006 已消除。`tests/e2e/test_stream_client_identity_e2e.py` 整体删除；身份/重映射由 `tests/e2e/test_frontend_app_e2e.py` 驱动构建产物中的生产 adapter。
    - f007 已消除。`tests/e2e/conftest.py:31-39` 的新鲜度校验位于必需模式判断（:41-42）之前，默认 E2E 运行收集阶段即校验 `src/frontend/dist`。
    - f008 已消除。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 以 exit 2 列出全部 9 个缺项。
    - f009 已消除。IPv6 先 `assert v6_b and v6_c` 再无条件探针；退避有上下界；首帧/输入延迟上限为 8000/3000ms。
    - f010 已消除。`tests/unit/test_supervisor_recovery.py:560` 已恢复精确 `WSMsgType.CLOSE`。
    - f011 已消除。扫描 `docs/specs` 未命中四类凭据字面量。
    - f012 仍存在（minor）。`tests/unit/test_repo_hygiene.py:12-19,32` 仍只扫描固定后缀（外加 `.gitattributes`），`Dockerfile`、`.gitignore` 等无后缀文本不在守卫范围。
    - f013 仍存在（minor）。`scripts/vendor_selkies_web.py` 的穿越拒绝与清单外文件校验仍只有 happy path 覆盖。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py:12-23` 只覆盖 stale；stamp 缺失、不可读 JSON、字段缺失三个 fail-closed 分支与 conftest 实际接线仍无测试。
    - f015 已消除。实跑 `tests/unit` 得 539 passed，路径隐私守卫转绿。
    - f016 已消除。postbuild 断言仍为完整精确等值。
    - f017 已消除。`tests/e2e/test_stream_selkies_tokens_e2e.py:98` 宿主发布仍为 `127.0.0.1:{port}:{port}`；f139540 把容器内 `settings.addr` 恢复为 `0.0.0.0`，容器内监听与宿主回环发布分工正确，宿主暴露面未变。
    - f018 已消除。`tests/fixtures/gateway_probe/topology.py:131` 的 secret 目录 0700，`tests/unit/test_baseline_fixture_regressions.py:577-580` 断言目录模式。
    - f019 已消除。A39 点名文件已改用公开接口/注入时钟，墙钟阈值断言已移除（f027 的 offload 断言修复见下）。
    - f020 修不彻底。f139540 把 `if (ws && OPEN)` 改成不满足即抛出，注入不再可能被静默跳过；但 Phase 5 仍无「已处理」哨兵，且注入帧被测试夹具自身的 `WebSocket.send` 包装吞掉：`tests/fixtures/gateway_probe/selkies_assets.py:108` 的 `window.__last_ws` 指向 shim 包装后的 socket，`:131-133` 对 `"cbrowser"+"activity"` 直接 `return`，不调用 `nativeSend`。因此 `tests/e2e/test_gateway_ac007_visibility_e2e.py:399-419` 断言的是夹具 shim 的丢弃行为，生产 Gateway 的过滤（`src/backend/cbrowser/gateway/server.py:580-586`）从未被该 E2E 触达；`asyncio.sleep(1.0)` 后断言日志无 `visibility_update` 的负断言仍然恒绿。该契约另有 `tests/integration/test_gateway_control.py:302-345` 用 `REAL_SIGNALING_MSG` 哨兵覆盖真实 Gateway，故不计 critical，但 AC-003/A37 对这条 E2E 的要求未满足。
    - f021 仍存在（minor）。集成/E2E 仍在仓库 `.scratch` 写状态，如 `tests/integration/test_v2_api_subprocess.py:24-27`。
    - f022 仍存在（minor）。`tests/fixtures/gateway_probe/evidence.py` 的脱敏逻辑仍无落盘内容断言。
    - f023 已消除。实跑 `pytest .repo_template/tests -q -m contract` 得 169 passed。
    - f024 已消除。`tests/unit/test_stream_runtime.py` 的精确退避列表断言仍在。
    - f025 已消除。清理断言均在 `finally` 之后。
    - f026 修不彻底。`REQUIRED_E2E_ENV`/`require_e2e_env` 已集中到 `tests/fixtures/e2e_env.py:10-40`，但 `tests/e2e/test_runtime_profile_defaults_e2e.py:46-60,444-446` 仍维护第二套前置检查并整类 `pytest.skip`：实跑 `CBROWSER_E2E_REQUIRED=1`、9 个变量齐备但 engine cache 指向不存在目录时，该用例 `SKIPPED` 而非硬失败（零覆盖绿）。`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:43-77` 也另维护一份 skip 语义。AC-002「测试前置条件由单一模块定义且语义一致」仍不成立。
    - f027 已消除。把 `docker_adapter.asyncio` / `supervisor.core.asyncio` 分别替换为同步 `to_thread` 后重跑，`test_teardown_offloads_blocking_docker_cleanup` 与 `test_scan_inspect_offloads_blocking_docker_call` 均 AssertionError 失败；真实实现下通过，卸载行为已有可失败的证据。
- 改测方向复核：无。f139540 的改动均为强化/纠正方向：不满足发送条件改为抛错、env 缺省值改为 `require_e2e_env`、offload 断言增加 `unblocked_while_running`、移除未使用 import；未发现把旧预期改成当前实现的输出。
- 本轮新发现：0 条。
- 未进表的提示：
    - `tests/e2e/test_stream_runtime_e2e.py:480` 的 `globals().update(env)` 不会更新模块导入期读取的 `BROWSER_IMAGE`/`STREAM_IMAGE`/`ENGINE_CACHE`，实际仍依赖导入时环境；行同虚设，建议直接赋值。
    - `tests/e2e/test_runtime_profile_defaults_e2e.py:25-28` 的 `DEFAULT_IMAGE`/`DEFAULT_CACHE` 已无引用（死常量）。
    - `tests/e2e/test_supervisor_event_shutdown_e2e.py:37-48` 在非必需模式下 Docker daemon 不可达仍 `pytest.fail`，与 A36「缺失=skip」语义不完全一致，归入 f026 的系统性问题。
    - `tests/integration/test_supervisor_rpc.py:3`、`tests/integration/test_runtime_coordinator_integration.py:8`、`tests/integration/test_v2_api_subprocess.py:6` 的 `importlib.util` 在迁移后已无使用（未使用 import，风格）。
    - `tests/e2e/conftest.py:19-21` 有多余空行；`tests/e2e/test_supervisor_retry_e2e.py:43-46` 重复 import `e2e_env`。
- 总体判断：f005/f027 已真正修复，但 f020 的 E2E 负向注入仍被夹具 shim 吞掉、f026 的 required 模式仍可整类 skip，AC-002/AC-003 打勾复核不成立，不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；f020/f026 均属 t018 范围。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only`（exit 2，列出 9 个缺项）与默认模式（79 tests collected）；实跑 `python3 scripts/verify_frontend_dist.py --check-freshness` exit 0；`tests/unit/test_frontend_build_freshness.py` 通过。fail-closed 分支缺测试（f014 minor）。
- AC-002：`re_verified`。检索确认无 `spec_from_file_location`/跨模块 fixture 借用、无 `sys.path.insert`；`tests/fixtures/supervisor_recovery_probe/gateway_service.py:147` 驱动生产 `create_gateway_app`；发现 f026 仍未满足。
- AC-003：`re_verified`。实跑 unit 539 passed、integration 79 passed、legacy 384 passed；逐条核对 IPv6、退避上下限、冻结帧增长、逐页静音、首帧/输入延迟、会话关闭实例不变断言；发现 f020 未满足。
- AC-004：`trust_prior`（真实 Docker 单次门禁）。静态核对 Selkies 宿主发布仅 127.0.0.1、control 目录 0700、证据脱敏与 `.scratch` 写入；f021/f022 minor 仍在；`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 本轮未由 reviewer 执行。
- AC-005：`re_verified`。实跑 unit 539 passed；A39 文件已用公开接口/注入时钟；用同步 `to_thread` 回归探针确认两个 offload 用例会红（f027 已修）。
- AC-006：`re_verified`（本地非 E2E）。实跑 contract 169、legacy 384、unit 539、integration 79、前端 Vitest 95、`npm run build`（含 stamp 写入与 freshness verify）均通过；`.github/` 已不存在；`docs/blueprint/testing.md:40-54` 只引用 `scripts/run_gates.sh`。
- AC-007：`re_verified`。实跑 `tests/unit` 539 passed（含 `test_repo_hygiene.py`）；扫描 `docs/specs` 无凭据字面量；`.gitattributes` 行尾规则生效且 `git ls-files --eol` 无 CRLF；vendor 解包安全分支仍无测试（f013 minor）。

coverage = 6 / 7

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 10 (2026-11-03T14:54:34+08:00)

- round：10
- reviewed_at：2026-11-03T14:54:34+08:00

reviewed_scope: ee0bcb5a5cd459c4

### Findings

#### t018_test_f028 - stream_runtime E2E 前置变量大小写写错：必需模式确定性红灯、默认模式静默跳过

- 严重度：important
- 锚点：AC-002「测试前置条件由单一模块定义且语义一致」；AC-006「本地全量门禁由单一入口脚本执行（含 E2E 必需模式）」
- 位置：`tests/e2e/test_stream_runtime_e2e.py:474-475,479`
- 问题：88528f9 迁移前置条件时把 `CBROWSER_RUNTIME_ENGINE_CACHE` 写成 `CBROWSER_RUNTIME_engine_cache`（`engine` 小写）；`tests/fixtures/e2e_env.py:17` 的 `REQUIRED_E2E_ENV` 与 conftest 必需模式校验都用大写。已复现：9 个正确变量（含大写缓存目录）齐备且 `CBROWSER_E2E_REQUIRED=1` 时，`pytest tests/e2e/test_stream_runtime_e2e.py::test_stream_runtime_direct_media_matrix` 直接 `FAILED ... Missing required E2E environment variables: CBROWSER_RUNTIME_engine_cache`；同命令默认模式为 `1 skipped`。因此 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 无法全绿，Direct Media 矩阵即使提供正确前置也不执行（漏测）。同缺陷 code review 已登记 `t018_code_f033`。
- 建议：三处改回 `CBROWSER_RUNTIME_ENGINE_CACHE`；补一条守卫断言（测试代码引用的 `CBROWSER_*` 名称必须属于 `REQUIRED_E2E_ENV`），防止同类拼写漂移。

#### t018_test_f029 - AC-002 残余：部分 E2E 仍直接读环境变量，缺失时 KeyError/可变标签回退而非 skip

- 严重度：important
- 锚点：AC-002「测试前置条件由单一模块定义且语义一致」；A36「缺失=skip、格式错=fail」
- 位置：`tests/e2e/test_runtime_coordinator_e2e.py:76-78,93`、`tests/e2e/test_supervisor_container_graph_e2e.py:73-75,93,555`、`tests/e2e/test_browser_runtime_e2e.py:44-53`、`tests/e2e/test_stream_selkies_tokens_e2e.py:26-29`、`tests/e2e/test_supervisor_event_shutdown_e2e.py:40-48`
- 问题：这些用例未走 `require_e2e_env`。已复现：无任何 E2E 变量运行 `pytest tests/e2e/test_runtime_coordinator_e2e.py -q` 得 `FAILED ... KeyError: 'CBROWSER_RUNTIME_ENGINE_CACHE'`，而非 A36 要求的 skip；`test_supervisor_container_graph_e2e.py:73-75` 同样直接下标。镜像前置也未集中：`test_browser_runtime_e2e.py:44-45` 回退到可变标签 `cbrowser-t003-impl-runtime:latest`、`:49-52` 回退到 `.scratch` 缓存；`test_stream_selkies_tokens_e2e.py:26-28` 回退到硬编码 sha256；`test_supervisor_event_shutdown_e2e.py:40-48` 在非必需模式 Docker daemon 不可达时仍 `pytest.fail`。默认模式下这些用例会拿本地任意标记镜像/旧缓存运行或直接报 KeyError，A36「镜像摘要集中一处并注明来源」与「缺失=skip」仍未完成，AC-002 的单一来源与语义一致仍有缺口。
- 建议：迁移到 `require_e2e_env(..., paths=...)` 并删除回退默认值；镜像摘要只保留 `REQUIRED_E2E_ENV` 一处来源；默认模式缺变量/缺 Docker 走 skip，格式错与必需模式才硬失败。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f001 已消除。`config/docker/Dockerfile:18-20` 未传 `--check-freshness`，`scripts/verify_frontend_dist.py:82-83` 默认 `check_freshness=False`。
    - f002 已消除。实跑 `tests/e2e/test_frontend_build_wiring.py tests/e2e/test_frontend_adapter_build.py tests/unit/test_frontend_build_freshness.py -q` 得 13 passed；`tests/e2e/test_frontend_build_wiring.py:67` 的 postbuild 仍为完整精确等值。
    - f003 已消除。默认模式 `pytest tests/e2e -q --collect-only` 得 79 tests collected，无 collection error。
    - f004 门禁段落已消除。`docs/blueprint/testing.md:40-55` 的 `test_cmd`/`blackbox_verify` 只引用 `scripts/run_gates.sh`；`docs/blueprint/stream_runtime.md:49` 仍引用已删除测试，归 code review `t018_code_f015`，不重复出表。
    - f005 已消除。`tests/` 无 `spec_from_file_location`；原 importlib 借用用例已迁入 `tests/e2e/test_supervisor_recovery_e2e.py`（Round 9 实跑 1 passed，本轮未重跑，仅静态复核）。
    - f006 已消除。`tests/e2e/test_stream_client_identity_e2e.py` 整体删除；身份/重映射由 `tests/e2e/test_frontend_app_e2e.py` 驱动构建产物中的生产 adapter。
    - f007 已消除。`tests/e2e/conftest.py:31-39` 的新鲜度校验位于必需模式判断（:41-42）之前；实跑 `python3 scripts/verify_frontend_dist.py --check-freshness` 成功。
    - f008 已消除。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 以 exit 2 列出全部 9 个缺项。
    - f009 已消除。IPv6 先 `assert v6_b and v6_c` 再无条件探针（`tests/e2e/test_supervisor_namespace_policy_e2e.py:546-554`）；退避有上下界（`tests/e2e/test_supervisor_retry_e2e.py:305-306,399-400,480-481`）；首帧/输入延迟上限为 8000/3000ms。
    - f010 已消除。`tests/unit/test_supervisor_recovery.py:559-560` 已恢复精确 `WSMsgType.CLOSE`。
    - f011 已消除。扫描 `docs/specs` 未命中四类凭据字面量。
    - f012 仍存在（minor）。`tests/unit/test_repo_hygiene.py:12-19,32` 仍只扫描固定后缀（外加 `.gitattributes`），`Dockerfile`、`.gitignore` 等无后缀文本不在守卫范围。
    - f013 仍存在（minor）。`scripts/vendor_selkies_web.py:29-33,69-84` 的穿越拒绝与清单外文件校验仍只有 happy path 覆盖（`tests/e2e/test_frontend_adapter_build.py` 四个用例均无负例）。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py:12-23` 只覆盖 stale；stamp 缺失、不可读 JSON、字段缺失三个 fail-closed 分支与 conftest 实际接线仍无测试。
    - f015 已消除。实跑 `tests/unit` 得 539 passed，路径隐私守卫转绿。
    - f016 已消除。`tests/e2e/test_frontend_build_wiring.py:67` 的 postbuild 仍为完整精确等值。
    - f017 已消除。`tests/e2e/test_stream_selkies_tokens_e2e.py:98` 宿主发布为 `127.0.0.1:{port}:{port}`；容器内监听 `0.0.0.0` 属容器内服务，宿主暴露面未变。
    - f018 已消除。`tests/fixtures/gateway_probe/topology.py:131` 的 secret 目录 0700；`tests/unit/test_baseline_fixture_regressions.py:577-580` 断言目录模式。
    - f019 已消除。A39 点名文件已改用公开接口/注入时钟；`tests/unit/test_docker_offload.py` 以 `unblocked_while_running` 证明卸载。
    - f020 已消除。88528f9 删除的 Phase 5 负向注入只测到夹具 shim 丢弃帧、从未触达生产 Gateway；替代覆盖在 `tests/integration/test_gateway_control.py:302-342`（真实 `create_gateway_app` + `REAL_SIGNALING_MSG` 哨兵，本轮该文件 3 passed），属合法删除。
    - f021 仍存在（minor）。集成/E2E 仍在仓库 `.scratch` 写状态：`tests/integration/test_v2_api_subprocess.py:25`、`tests/integration/test_automation_cdp_flow.py:88,244`、`tests/e2e/test_browser_runtime_e2e.py:48-54`。
    - f022 仍存在（minor）。`tests/fixtures/gateway_probe/evidence.py` 的脱敏逻辑仍无落盘内容断言。
    - f023 已消除。实跑 `pytest .repo_template/tests -q -m contract` 得 169 passed。
    - f024 已消除。`tests/unit/test_stream_runtime.py:260` 仍为精确 `assert clock.delays == [1.0]`。
    - f025 已消除。清理断言均在 `finally` 之后（`tests/e2e/test_supervisor_container_graph_e2e.py:671-681`、`test_supervisor_policy_failure_e2e.py:241-243`、`test_runtime_coordinator_e2e.py:488-490`）。
    - f026 已消除（原列位点）。`tests/fixtures/e2e_env.py:10-20` 是单一必需清单；defaults/stream/event/offline 已迁移，required 模式下 defaults 缺失改硬失败；同类残余位点见 f029。
    - f027 已消除。offload 用例新增 `unblocked_while_running` 断言（`tests/unit/test_docker_offload.py:61,145`），Round 9 的同步 `to_thread` 回归探针可使其变红，本轮静态复核仍在。
- 改测方向复核：无。88528f9 的改动均为迁移前置条件、删除未使用常量/import、删除未触达生产 Gateway 的假负向探针（替代覆盖见 f020 复核）；未发现删断言、反转断言、注释掉断言或把旧预期改成当前实现输出的改动。
- 本轮新发现：2 条（important 2）。
- 未进表的提示：
    - `tests/e2e/test_supervisor_event_shutdown_e2e.py:51-65` 连续两次 `require_e2e_env` 且 `browser_image = browser_image or ...` 为死代码；`policy_image` 回退从 `CBROWSER_SUPERVISOR_TEST_IMAGE` 改为 `CBROWSER_RUNTIME_TEST_IMAGE`（code review `t018_code_f034` 已登记）。
    - `tests/e2e/test_supervisor_namespace_policy_e2e.py:173,192,209,226,245` 固定 `time.sleep` 后断言进程状态，且无采样窗口说明（code review `t018_code_f028` 已登记）；`tests/e2e/test_frontend_media_e2e.py:627`、`test_gateway_ac007_visibility_e2e.py:390` 的固定窗口已注明采样用途。
    - `tests/e2e/test_runtime_profile_defaults_e2e.py:26-29` 的 `DEFAULT_IMAGE`/`DEFAULT_CACHE` 已无引用（死常量）。
    - `docs/blueprint/stream_runtime.md:49` 仍把已删除的 `tests/e2e/test_stream_client_identity_e2e.py` 列为身份/重连覆盖来源（code review `t018_code_f015`）。
    - note 对 f020 的删除只写了删除理由，未写替代覆盖（`tests/integration/test_gateway_control.py` 的哨兵用例），建议补一句。
    - `tests/e2e/conftest.py:19-21` 有多余空行；`tests/e2e/test_supervisor_retry_e2e.py:43-46` 重复 import `e2e_env`（风格）。
    - 真实 Docker E2E 未执行（worktree 缺镜像/缓存变量），AC-004 的单次运行与 AC-006 的 E2E 层依赖实施侧证据。
- 总体判断：f028 使 E2E 必需模式确定性红灯、默认模式漏测，f029 证明 AC-002 前置条件仍未完全单一来源与语义一致；AC-002/AC-006 打勾复核不成立，不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；f028/f029 均属 t018 收尾范围。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only`（exit 2，列出 9 个缺项）与默认模式（79 tests collected）；实跑 `python3 scripts/verify_frontend_dist.py --check-freshness` exit 0；fail-closed 分支缺测试（f014 minor）。
- AC-002：`re_verified`。检索确认无 `spec_from_file_location`/`sys.path.insert`，共享 fixture 位于各层 conftest，Supervisor 测试驱动生产 `create_gateway_app`；发现 f028/f029 仍未满足单一来源与语义一致。
- AC-003：`re_verified`。实跑 `tests/unit` 539 passed、`tests/integration` 79 passed；逐条核对 IPv6 无条件下阻断、退避上下限、冻结帧增长、逐页静音、首帧/输入延迟、会话关闭后容器 running 且实例不变；f020 已以集成层哨兵覆盖。
- AC-004：`trust_prior`（真实 Docker 单次门禁）。静态核对回环发布、control 目录 0700、证据脱敏与 `.scratch` 写入；f021/f022 minor 仍在；`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 本轮未由 reviewer 执行。
- AC-005：`re_verified`。实跑 `tests/unit` 539 passed；A39 文件已用公开接口/注入时钟；offload 用例含可失败的 `unblocked_while_running` 断言。
- AC-006：`re_verified`（本地非 E2E）。实跑 `bash scripts/run_gates.sh` 全链路通过（contract 169、legacy、unit 539、integration 79、前端 Vitest 与 build/verify）；`.github/` 已不存在；`docs/blueprint/testing.md:40-55` 只引用 `scripts/run_gates.sh`；E2E 必需模式被 f028 确定性打断。
- AC-007：`re_verified`。实跑 `pytest tests/unit/test_repo_hygiene.py -q` 2 passed；扫描 `docs/specs` 无凭据字面量；`git ls-files --eol` 无 CRLF；`python3 scripts/verify_frontend_dist.py --check-freshness` 通过；vendor 解包安全分支仍无测试（f013 minor）。

coverage = 6 / 7

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 11 (2026-11-03T15:10:30+08:00)

- round：11
- reviewed_at：2026-11-03T15:10:30+08:00

reviewed_scope: 455e4795e8c343cb

### Findings

#### t018_test_f029 - AC-002 修不彻底：两个 E2E 仍自带镜像/缓存回退，event shutdown 在非必需模式缺 Docker 仍 fail

- 严重度：important
- 锚点：AC-002「测试前置条件由单一模块定义且语义一致」；A36「缺失=skip、格式错=fail」
- 位置：`tests/e2e/test_browser_runtime_e2e.py:44-53`、`tests/e2e/test_stream_selkies_tokens_e2e.py:26-29`、`tests/e2e/test_supervisor_event_shutdown_e2e.py:39-48`、`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:359-362`
- 问题：489ce00 只把 runtime_coordinator、container_graph、topology 与 event_shutdown 的镜像读取迁到 `require_e2e_env`，但 `test_browser_runtime_e2e.py` 仍在模块导入时以可变标签 `cbrowser-t003-impl-runtime:latest` 和 `.scratch/t003_implementation/tmp/engine-cache` 兜底，`test_stream_selkies_tokens_e2e.py` 仍内置硬编码 sha256；两者完全不调用 `require_e2e_env`，默认模式（无 `CBROWSER_E2E_REQUIRED`）会直接拿回退值执行而非 skip。`test_supervisor_event_shutdown_e2e.py:39-48` 在 `require_e2e_env` 之前对 Docker 不可达直接 `pytest.fail`，非必需模式语义仍是 fail 而非 skip。实跑 `pytest tests/e2e/test_browser_runtime_e2e.py tests/e2e/test_stream_selkies_tokens_e2e.py --collect-only -q` 得 15 tests collected，确认两文件在门禁收集范围内。required 模式下 conftest 的 9 项检查会兜底，但 AC-002 要求的单一来源与语义一致在默认模式仍不成立，AC-002 打勾复核不成立。
- 建议：两文件把镜像/缓存前置改为 `require_e2e_env(...)` 并删除模块级回退；event shutdown 的 Docker 探测在非必需模式改为 `pytest.skip`（必需模式仍 fail）；`offline_fixture.py:359-362` 的 supervisor 镜像直读一并收敛。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f028 已消除。`tests/e2e/test_stream_runtime_e2e.py:471-479` 三处变量均为 `CBROWSER_RUNTIME_ENGINE_CACHE`，与 `tests/fixtures/e2e_env.py:17` 和 conftest 必需清单一致；实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 仍以 exit 2 列出 9 项缺项，变量名不再出现大小写漂移。
    - f029 修不彻底（仍为 important）。489ce00 已修 runtime_coordinator、container_graph、event_shutdown 的重复调用/镜像回退，但 `test_browser_runtime_e2e.py:44-53` 与 `test_stream_selkies_tokens_e2e.py:26-29` 仍保留模块级回退且不调用 `require_e2e_env`，`test_supervisor_event_shutdown_e2e.py:39-48` 非必需模式的 Docker 缺失仍 fail；证据见上。
    - f012 仍存在（minor）。`tests/unit/test_repo_hygiene.py:12-15,32` 仍只扫描固定后缀（外加 `.gitattributes`），`Dockerfile`、`.gitignore` 等无后缀文本不在守卫范围。
    - f013 仍存在（minor）。`scripts/vendor_selkies_web.py:29-33,69-84` 的穿越拒绝与清单外文件校验仍只有 happy path 覆盖。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py:12-23` 只覆盖 stale；stamp 缺失、不可读 JSON、字段缺失三个 fail-closed 分支与 conftest 实际接线仍无测试。
    - f021 仍存在（minor）。集成/E2E 仍在仓库 `.scratch` 写状态：`tests/integration/test_v2_api_subprocess.py:25`、`tests/integration/test_automation_cdp_flow.py:88,244`、`tests/e2e/test_browser_runtime_e2e.py:48-54`。
    - f022 仍存在（minor）。`tests/fixtures/gateway_probe/evidence.py:26-53` 的脱敏逻辑仍无落盘内容断言。
- 改测方向复核：无。489ce00 的改动为修正变量名、补充 `require_e2e_env`、删除重复前置调用与错误镜像回退，均为强化或纠正方向；未发现删断言、反转断言、注释掉断言、`.skip`/`.only`、`# type: ignore` 或把旧预期改成当前实现输出的改动。
- 本轮新发现：0 条（f029 沿用原 ID 复核）。
- 未进表的提示：
    - `tests/fixtures/gateway_probe/topology.py:84` 现在硬性要求 `CBROWSER_CADDY_TEST_IMAGE`，但 `docs/guides/supervisor_validation.md` 的环境清单未列该项；属文档补充，不计 finding。
    - `tests/e2e/test_supervisor_namespace_policy_e2e.py:173,192,209,226,245` 仍是固定 `time.sleep` 后断言进程状态；后续轮次可补采样窗口说明（此前 code review 已登记）。
    - `tests/e2e/test_supervisor_retry_e2e.py:307-310,401-404,482-485` 的退避上下限已从单边下限收紧为双边窗口，属本轮看到的强化改动。
    - 真实 Docker E2E 未执行（worktree 缺镜像/缓存变量与 Chrome 前置），AC-004 的单次运行依赖实施侧证据。
- 总体判断：f028 已真正修复，但 f029 残留使 AC-002 的单一来源与语义一致仍不成立，AC-002 打勾复核不成立，不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；f029 属 t018 收尾范围。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only`（exit 2，列出 9 个缺项）与默认模式（79 tests collected）；实跑 `python3 scripts/verify_frontend_dist.py --check-freshness` 通过；`tests/unit/test_frontend_build_freshness.py` 通过。fail-closed 分支缺测试（f014 minor）。
- AC-002：`re_verified`。检索确认 `tests/` 无 `spec_from_file_location` 与 `sys.path` 注入；共享 fixture 位于各层 conftest；Supervisor 测试驱动 `ProductionGatewayService`/`create_gateway_app`；发现 f029 仍未满足单一来源与语义一致。
- AC-003：`re_verified`。实跑 `tests/unit` 539 passed、`tests/integration` 79 passed；逐条核对 IPv6 无条件下阻断、退避上下限、冻结恢复帧增长、逐页静音、首帧/输入延迟上限（8000/3000ms）、会话关闭后容器 running 且 instance-id 不变；f020 的替代哨兵在 `tests/integration/test_gateway_control.py` 实测通过。
- AC-004：`trust_prior`（真实 Docker 单次门禁）。静态核对 control 目录 0700、密钥文件 0600、Selkies 宿主发布 127.0.0.1、证据默认写系统临时目录；f021/f022 minor 仍在；`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 本轮未由 reviewer 执行。
- AC-005：`re_verified`。实跑 `tests/unit` 539 passed；A39 文件已改用公开访问器/注入时钟；offload 用例保留可失败的 `unblocked_while_running` 断言。
- AC-006：`re_verified`（本地非 E2E）。实跑 contract 169、unit 539、integration 79、前端 Vitest 95 均通过；`scripts/run_gates.sh` 是唯一入口；`.github/` 已不存在；`docs/blueprint/testing.md:40-55` 只引用该脚本（含模板契约标记行）；f029 影响默认模式前置语义，不影响脚本入口存在性。
- AC-007：`re_verified`。实跑 `tests/unit/test_repo_hygiene.py` 2 passed；`git ls-files --eol` 无 CRLF；`docs/specs` 无凭据形态字面量；归档 spike README 与 `.gitignore` 秘密路径规则存在；vendor 解包安全分支仍无测试（f013 minor）。

coverage = 6 / 7

verdict: FAIL

## Round 12 (2026-11-03T15:37:49+08:00)

- round：12
- reviewed_at：2026-11-03T15:37:49+08:00

reviewed_scope: c333b4c83e8133c2

### Findings

#### t018_test_f029 - AC-002 修不彻底：offline fixture 仍直读 supervisor 镜像，部分前置缺失时 fail 而非 skip

- 严重度：important
- 锚点：AC-002「测试前置条件由单一模块定义且语义一致」；A36「缺失=skip、格式错=fail、必需模式=硬失败」
- 位置：`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:360-361`、`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:474`、`tests/e2e/test_supervisor_recovery_e2e.py:56-62`、`tests/e2e/test_supervisor_retry_e2e.py:73-79`、`tests/e2e/test_supervisor_offline_recovery_e2e.py:77`
- 问题：7526763 已删除 browser runtime / stream selkies 的模块级镜像回退，但 f029 明确点名的 offline fixture 未收敛：`RealSupervisorContainer.__init__` 仍以 `os.environ.get("CBROWSER_SUPERVISOR_TEST_IMAGE")` 作为第二来源（`offline_fixture.py:360-361`），`start()` 用 `assert self.supervisor_image`（`:474`）校验。三个调用方的前置检查（`require_e2e_env` 只要求 browser/stream/engine/geoip 四项）不含 supervisor 镜像，且调用 `RealSupervisorContainer` 时也未显式传 `supervisor_image`；因此默认模式下提供这四项而缺 `CBROWSER_SUPERVISOR_TEST_IMAGE` 时，用例会进入 Docker 编排并以 `AssertionError` 失败，而不是按 A36 跳过。前置条件仍是「单一模块」与「fixture 内直读」两套语义。
- 建议：调用方用 `require_e2e_env("CBROWSER_SUPERVISOR_TEST_IMAGE")` 取值并显式传入 `supervisor_image`，删除 fixture 内直读与 assert；或在 fixture 内统一调用 `require_e2e_env`（缺失走 skip、required 走 fail）。

#### t018_test_f030 - browser runtime 前置检查晚于 session 夹具，默认模式由 skip 退化为 11 个 setup error

- 严重度：important
- 锚点：AC-002「测试前置条件由单一模块定义且语义一致」；A36「缺失=skip」
- 位置：`tests/e2e/test_browser_runtime_e2e.py:46-62`、`tests/e2e/test_browser_runtime_e2e.py:190-229`
- 问题：7526763 把模块级回退改为函数级 `@pytest.fixture(autouse=True) _require_runtime_prerequisites`，但同模块的 `http_server` 是 `scope="session"`（:190）且被全部 11 个用例直接请求；pytest 先实例化 session 夹具，此时 `IMAGE_TAG` 仍是导入期的 `""`，`docker run ... --entrypoint python3 '' -c ...` 以 exit 125 失败。已复现：无任何 `CBROWSER_*` 环境时 `pytest tests/e2e/test_browser_runtime_e2e.py -q` 得 `11 errors`（`subprocess.CalledProcessError` exit 125），而不是 skip；同轮对照 `test_stream_selkies_tokens_e2e.py` + `test_supervisor_event_shutdown_e2e.py` 为 `5 skipped`。默认模式 `pytest tests/e2e` 因此无法干净跳过，A36 的「缺失=skip」与 AC-002 的语义一致仍不成立（required 模式因 conftest 先校验 9 项，掩盖了该缺陷）。
- 建议：把该前置检查提升为 `scope="session"` 的 autouse fixture，或让 `http_server` 显式依赖前置 fixture；镜像/缓存缺失时应在创建 Docker 网络与容器前 skip。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f001 已消除。`config/docker/Dockerfile` 未传 `--check-freshness`，`scripts/verify_frontend_dist.py` 默认 `check_freshness=False`；生产镜像构建路径不执行源码哈希校验。
    - f002 已消除。实跑 `tests/e2e/test_frontend_build_wiring.py tests/e2e/test_frontend_adapter_build.py tests/unit/test_frontend_build_freshness.py -q` 得 13 passed；`tests/e2e/test_frontend_build_wiring.py:67` 的 postbuild 仍为完整精确等值。
    - f003 已消除。默认模式 `pytest tests/e2e -q --collect-only` 得 79 tests collected，无 collection error。
    - f004 已消除。`docs/blueprint/testing.md:40-55` 的 `test_cmd`/`blackbox_verify` 只保留 `scripts/run_gates.sh` 与模板契约标记行。
    - f005 已消除。`tests/` 已无 `spec_from_file_location` 与 `sys.path.insert`；原 importlib 借用用例已迁入 `tests/e2e/test_supervisor_recovery_e2e.py` 同模块。
    - f006 已消除。`tests/e2e/test_stream_client_identity_e2e.py` 已整体删除；身份/重映射由 `tests/e2e/test_frontend_app_e2e.py` 驱动构建产物中的生产 adapter。
    - f007 已消除。`tests/e2e/conftest.py:31-39` 的新鲜度校验位于必需模式判断（:41-42）之前；本轮门禁 `npm run build` 的 `verify:selkies --check-freshness` 通过。
    - f008 已消除。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 以 exit 2 列出全部 9 个缺项。
    - f009 已消除。IPv6 先 `assert v6_b and v6_c` 再无条件探针（`tests/e2e/test_supervisor_namespace_policy_e2e.py:547-555`）；退避为双边窗口（`tests/e2e/test_supervisor_retry_e2e.py:310,404,485`）；首帧/输入延迟上限为 8000/3000ms。
    - f010 已消除。`tests/unit/test_supervisor_recovery.py:560` 只接受 `WSMsgType.CLOSE`。
    - f011 已消除。扫描 `docs/specs` 未命中四类凭据字面量。
    - f012 仍存在（minor）。`tests/unit/test_repo_hygiene.py:12-19,32` 仍只扫描固定后缀（外加 `.gitattributes`），`Dockerfile`、`.gitignore` 等无后缀文本不在守卫范围。
    - f013 仍存在（minor）。`scripts/vendor_selkies_web.py:29-33,69-84` 的穿越拒绝与清单外文件校验仍只有 happy path 覆盖。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py:12-23` 只覆盖 stale；stamp 缺失、不可读 JSON、字段缺失三个 fail-closed 分支与 conftest 实际接线仍无测试。
    - f015 已消除。实跑 `tests/unit` 得 539 passed，路径隐私守卫转绿。
    - f016 已消除。`tests/e2e/test_frontend_build_wiring.py:67` 已恢复 postbuild 完整精确等值。
    - f017 已消除。`tests/e2e/test_stream_selkies_tokens_e2e.py:105` 宿主发布为 `127.0.0.1:{port}:{port}`；容器内监听 `0.0.0.0` 属容器内服务，宿主暴露面未变。
    - f018 已消除。`tests/fixtures/gateway_probe/topology.py:131` 的 secret 目录 0700；`tests/unit/test_baseline_fixture_regressions.py` 断言文件 0600 与目录 0700。
    - f019 已消除。`tests/unit/test_docker_offload.py` 以 `unblocked_while_running` 证明卸载；A39 其余文件已改用公开访问器/注入时钟。
    - f020 已消除。未触达生产 Gateway 的负向注入已删除；替代覆盖 `tests/integration/test_gateway_control.py:302-345` 用真实 `create_gateway_app` + `REAL_SIGNALING_MSG` 哨兵，本轮 integration 79 passed。
    - f021 仍存在（minor）。集成/E2E 仍在仓库 `.scratch` 写状态：`tests/integration/test_v2_api_subprocess.py:25`、`tests/integration/test_automation_cdp_flow.py:88,244`、`tests/e2e/test_browser_runtime_e2e.py:48-50,1419,2631`。
    - f022 仍存在（minor）。`tests/fixtures/gateway_probe/evidence.py` 的 `_redact` 仍无落盘内容断言。
    - f023 已消除。实跑 `pytest .repo_template/tests -q -m contract` 得 169 passed。
    - f024 已消除。`tests/unit/test_stream_runtime.py:260` 仍为精确 `assert clock.delays == [1.0]`。
    - f025 已消除。清理/所有权断言均在 `finally` 之后（`test_supervisor_container_graph_e2e.py:679-692`、`test_supervisor_policy_failure_e2e.py:241-243`、`test_runtime_coordinator_e2e.py:499-502`）。
    - f026 已消除（原列位点）。`tests/fixtures/e2e_env.py:11-20` 是单一必需清单；defaults/stream/event/offline 已迁移，required 模式下 defaults 缺失改硬失败；同类残余见 f029/f030。
    - f027 已消除。`tests/unit/test_docker_offload.py:61,145` 的 `unblocked_while_running` 断言仍在，卸载退化时用例会红。
    - f028 已消除。`tests/e2e/test_stream_runtime_e2e.py:474-479` 三处变量均为 `CBROWSER_RUNTIME_ENGINE_CACHE`。
    - f029 修不彻底（仍为 important）。两个 E2E 的模块级回退与 event shutdown 非必需模式 fail 已修，但 offline fixture 的 supervisor 镜像直读与 `assert` 仍在；证据见上。
    - f030 新增（important）。browser runtime 的前置检查晚于 session 夹具，默认模式 11 个 setup error；证据见上。
- 改测方向复核：无。7526763 删除模块级回退属强化方向；event shutdown 由无条件 `pytest.fail` 改为「required fail / 默认 skip」是语义修正；`topology.py` 删除未使用 `os` import。未发现删断言、反转断言、注释掉断言、`.skip`/`.only`、`# type: ignore` 或把旧预期改成当前实现输出。
- 本轮新发现：2 条（important 2；f029 沿用原 ID 复核，f030 新增）。
- 未进表的提示：
    - `tests/e2e/test_supervisor_namespace_policy_e2e.py:173,192,209,226,245` 仍是固定 `time.sleep` 后断言进程状态（code review `t018_code_f028` 已登记）。
    - `tests/fixtures/e2e_env.py:40-55` 的 `free_udp_port_span` 与各文件 `find_free_port` 仍是先 bind 后释放的 TOCTOU；用户已取消并行双跑，单次运行风险低。
    - `tests/e2e/test_stream_runtime_e2e.py:853` 仍注入 `web_lock_shim.js`，生产身份覆盖已由 frontend app E2E 承担，建议后续清理双重包裹。
    - `tests/unit/test_stream_resume.py` 仍以 `agent._detached_upstreams` 作为轮询条件（非最终断言），`tests/unit/test_stream_binding_guards.py:115` 仍读取私有 cap 作为基线；证据强度弱，未用于 AC 证据。
    - `docs/specs/runtime_persistence.md:90` 仍有「注入的注入的」重复措辞（code review `t018_code_f021` 已登记）。
    - `docs/blueprint/testing.md` 的「Supervisor 控制契约导出使用」段已无导出命令（code review `t018_code_f026` 已登记）。
    - 真实 Docker E2E 未执行（worktree 无镜像/缓存变量与 Chrome 前置），AC-004 的单次运行依赖实施侧证据。
- 总体判断：7526763 修掉了两个 E2E 的回退与 event shutdown 语义，但 AC-002 仍有两处未收敛（f029 offline fixture 直读、f030 session 夹具早于前置检查），AC-002 打勾复核不成立，不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；f029/f030 属 t018 收尾范围。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only`（exit 2，列出 9 个缺项）与默认模式（79 tests collected）；门禁 `npm run build` 的 `verify:selkies --check-freshness` 通过；`tests/unit/test_frontend_build_freshness.py` 通过。fail-closed 分支缺测试（f014 minor）。
- AC-002：`re_verified`。检索确认 `tests/` 无 `spec_from_file_location` 与 `sys.path` 注入；共享 fixture 位于各层 conftest；Supervisor 测试驱动 `ProductionGatewayService`/`create_gateway_app`；实跑默认模式发现 f029/f030，单一来源与语义一致仍不成立。
- AC-003：`re_verified`。实跑 `tests/unit` 539 passed、`tests/integration` 79 passed；逐条核对 IPv6 无条件下阻断、退避上下限、冻结恢复帧增长、逐页静音、首帧/输入延迟上限（8000/3000ms）、viewer close 只接受 CLOSE、清理断言在 `finally` 之后、会话关闭后容器 running 且 instance-id 不变。
- AC-004：`trust_prior`（真实 Docker 单次门禁）。静态核对 Selkies 宿主发布 127.0.0.1、secret 目录 0700/文件 0600、证据默认写系统临时目录、显示号/端口按 run_id 派生；f021/f022 minor 仍在；`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 本轮未由 reviewer 执行。
- AC-005：`re_verified`。实跑 `tests/unit` 539 passed；A39 文件已改用公开访问器/注入时钟；offload 用例保留可失败的 `unblocked_while_running` 断言。
- AC-006：`re_verified`（本地非 E2E）。实跑 `bash scripts/run_gates.sh` EXIT=0（contract 169、legacy、unit 539、integration 79、前端 Vitest 与 build/verify）；`.github/` 已不存在；`docs/blueprint/testing.md:40-55` 只引用 `scripts/run_gates.sh`（含模板契约标记行）；required 模式 collection exit 2。
- AC-007：`re_verified`。实跑 `tests/unit` 539 passed（含 `test_repo_hygiene.py`）；扫描 `docs/specs` 无凭据形态字面量；`git ls-files --eol` 无 CRLF；归档 spike README 与 `.gitignore` 秘密路径规则存在；vendor 解包安全分支仍无测试（f013 minor）。

coverage = 6 / 7

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 13 (2026-11-03T16:05:53+08:00)

- round：13
- reviewed_at：2026-11-03T16:05:53+08:00

reviewed_scope: 027ac3d407446845

### Findings

本轮新发现 0 条。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f029 已消除。`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:360-362` 改为 `require_e2e_env("CBROWSER_SUPERVISOR_TEST_IMAGE")`，原 `start()` 中的空值 `assert` 已删除；默认模式实跑 `pytest tests/e2e/test_stream_selkies_tokens_e2e.py tests/e2e/test_supervisor_recovery_e2e.py tests/e2e/test_supervisor_retry_e2e.py tests/e2e/test_supervisor_offline_recovery_e2e.py -v` 得 1 passed / 9 skipped，三个 supervisor 用例均 SKIPPED 而非 AssertionError。
    - f030 已消除。`tests/e2e/test_browser_runtime_e2e.py:53-63` 的 `_require_runtime_prerequisites` 提升为 `scope="session"` autouse，`:191` 的 `http_server` 显式依赖它；实跑 `pytest tests/e2e/test_browser_runtime_e2e.py -q` 得 11 skipped，无 setup error 与 Docker 调用。
    - f012/f013/f014/f021/f022 仍存在（minor），本轮改动未触及：`tests/unit/test_repo_hygiene.py:12-19` 仍只扫描固定后缀；`scripts/vendor_selkies_web.py` 穿越/清单外分支无测试；`tests/unit/test_frontend_build_freshness.py:12-23` 只覆盖 stale；`.scratch` 写入与 evidence `_redact` 无落盘断言仍在。
    - 其余前轮 important/critical finding 均维持前轮已消除结论，本轮抽查 e465691 的改动未发现回退。
- 改测方向复核：无。e465691 只把前置检查提升到 session 夹具并让 offline fixture 走单一 `require_e2e_env`，属强化/统一方向；未发现删断言、反转断言、注释掉断言、`.skip`/`.only`、`# type: ignore`、弱化断言或把旧预期改成当前实现输出。
- 本轮新发现：0 条。
- 未进表的提示：
    - AC-003 字面要求「测试中不存在固定 sleep 后断言状态」；`tests/e2e/test_supervisor_namespace_policy_e2e.py:173,192,209,226,245` 仍是 `time.sleep` 后断言进程状态，属前轮 code review `t018_code_f028` 已登记的 minor，本轮未新增影响。
    - `tests/e2e/test_supervisor_recovery_e2e.py:262` 先启动 Gateway 再在 `:294` 构造 `RealSupervisorContainer`；默认模式仅缺 supervisor 镜像时 skip 会早于 `:445` 的 finally，Gateway/Docker client 依赖事件循环收尾。属既有提前失败清理边界，未观察到测试失败或端口冲突，不进 finding。
    - 契约区 drift 与用户决策一致：AC-004 删除并行双跑、AC-006 删除 GitHub Actions CI，均为已确认需求变更，不计 finding。
- 总体判断：f029/f030 均已真正修复，AC-002 的默认模式前置语义与单一来源恢复成立；其余仅剩已知 minor，本轮无新增 blocking finding。
- 系统性 follow-up：无新增；既有 minors 属 t018 收尾范围。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only`（exit 2，列出 9 个缺项）与默认模式（79 tests collected）；`bash scripts/run_gates.sh` 的 build/verify 通过；`tests/unit/test_frontend_build_freshness.py` 通过。fail-closed 分支仍缺测试（f014 minor）。
- AC-002：`re_verified`。检索 `tests/` 无 `spec_from_file_location`/`sys.path.insert`；Supervisor 测试均驱动 `ProductionGatewayService`；实跑默认模式 browser runtime 11 skipped、stream/supervisor 9 skipped，f029/f030 已修。
- AC-003：`re_verified`。实跑 unit 539、integration 79；核对 IPv6 无条件阻断、退避双边窗口、冻结恢复帧增长、逐页静音、首帧/输入延迟上限（8000/3000ms）、viewer close 只接受 CLOSE、清理断言在 finally 之后、会话关闭后容器 running 且 instance-id 不变；namespace policy 固定 sleep 为已知 minor。
- AC-004：`trust_prior`（真实 Docker 单次门禁）。静态核对 0700/0600、Selkies 宿主发布 127.0.0.1、证据默认系统临时目录、端口/显示号按 run 派生；`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 本轮未执行；f021/f022 minor 仍在。
- AC-005：`re_verified`。实跑 unit 539 passed；公开访问器/注入时钟落地，offload `unblocked_while_running` 可失败断言保留。
- AC-006：`re_verified`（本地非 E2E）。实跑 contract 169、unit 539、integration 79、前端 Vitest 95、build/verify 均通过；`.github/` 不存在；`docs/blueprint/testing.md:40-55` 只引用 `scripts/run_gates.sh`。
- AC-007：`re_verified`。unit 539 含 `test_repo_hygiene.py`；`git ls-files --eol` 无 CRLF；归档 spike README 与 `.gitignore` 规则存在；`docs/specs` 无凭据字面量；vendor 安全分支仍无测试（f013 minor）。

coverage = 6 / 7

建议合并前人工抽查 trust_prior 项。

verdict: PASS

## Round 14 (2026-11-03T16:37:17+08:00)

- round：14
- reviewed_at：2026-11-03T16:37:17+08:00

reviewed_scope: 628bfcea67c7530a

### Findings

#### t018_test_f031 - AC-004 未完成：两个 E2E 的专用秘密目录仍为 0777

- 严重度：important
- 锚点：AC-004「夹具秘密文件与目录仅属主可访问」
- 位置：`tests/e2e/test_runtime_coordinator_e2e.py:69-71`、`tests/e2e/test_supervisor_container_graph_e2e.py:79-80`
- 问题：两处 `control` 目录被显式 `chmod(0o777)`，目录内写入全部秘密：`supervisor_key`/`agent_key`/`gateway_key`/`gateway_api_key`；`tests/e2e/test_runtime_coordinator_e2e.py:174` 还经 `create_auth_context(control, ...)` 写入 admin 密码与 supervisor token。秘密文件本身 0600，但目录可写允许同机其他用户替换或删除秘密文件，与 f018 已判 important 的 `tests/fixtures/gateway_probe/topology.py` 同类；Round 12/13 的「control 目录 0700」复验只覆盖拓扑夹具，未覆盖这两个 E2E 位点，AC-004 打勾复核不成立。父目录 `tmp_path` 当前为 0700，可利用性受限，但目录模式仍不满足 AC，工作目录一旦移出 `tmp_path` 即成实际暴露。
- 建议：两处 `control` 目录改 0700（supervisor 容器以 root 运行且带 `DAC_OVERRIDE`，0700 可读）；若容器需非 root 写目录，把 secret 拆到 0700 子目录并只挂载文件；在权限测试中补断言。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f029 已消除。`tests/fixtures/supervisor_recovery_probe/offline_fixture.py:360-362` 仍走 `require_e2e_env("CBROWSER_SUPERVISOR_TEST_IMAGE")`；默认模式实跑 `tests/e2e/test_supervisor_recovery_e2e.py tests/e2e/test_supervisor_retry_e2e.py tests/e2e/test_supervisor_offline_recovery_e2e.py tests/e2e/test_stream_selkies_tokens_e2e.py` 得 1 passed / 9 skipped。
    - f030 已消除。`tests/e2e/test_browser_runtime_e2e.py:53-63` 的 `_require_runtime_prerequisites` 为 session 级 autouse 且被 `http_server` 依赖；实跑该文件 11 skipped，无 setup error。
    - f018 清单内位点已修（`tests/fixtures/gateway_probe/topology.py:133` 0700），同类位点残留见 f031。
    - f012 仍存在（minor）。`tests/unit/test_repo_hygiene.py:12-19,32` 仍只扫描固定后缀，`Dockerfile`、`.gitignore` 等无后缀文本不在守卫范围。
    - f013 仍存在（minor）。`scripts/vendor_selkies_web.py:29-33,66-84` 的穿越拒绝与清单外文件校验仍只有 happy path 覆盖。
    - f014 仍存在（minor）。`tests/unit/test_frontend_build_freshness.py:12-23` 只覆盖 stale；stamp 缺失、不可读 JSON、字段缺失分支无测试。
    - f021 仍存在（minor）。集成/E2E 仍在仓库 `.scratch` 写状态：`tests/integration/test_v2_api_subprocess.py:24`、`tests/integration/test_automation_cdp_flow.py:88,244`、`tests/e2e/test_browser_runtime_e2e.py:48-50`。
    - f022 仍存在（minor）。`tests/fixtures/gateway_probe/evidence.py:26-53` 的脱敏逻辑落盘内容仍无断言。
    - 其余前轮 important/critical 维持已消除：本轮重跑 contract 169、unit 539、integration 79、前端 Vitest 95、默认 E2E 17 passed / 62 skipped、required 模式 collection exit 2、`--check-freshness` exit 0，并在全量 diff 中复核了生产 Gateway 替换、实例不变断言、IPv6 无条件阻断、退避双边窗口、首帧/输入延迟上限与清理断言位置，未发现回退。
- 改测方向复核：无。c18c418 只删除未使用 import/常量、把 postcss 纳入源哈希、contract 步骤显式带 pytest，属清理；e465691 等提交将前置检查提升为 session 夹具、统一 `require_e2e_env`，属强化方向。未发现删断言、反转断言、注释掉断言、`.skip`/`.only`、`# type: ignore` 或把旧预期改成当前实现输出。
- 本轮新发现：1 条（important 1）。
- 未进表的提示：
    - 契约区 drift 与用户决策一致：AC-004 删除并行双跑、AC-006 删除 GitHub Actions CI，均为已确认需求变更。
    - `tests/e2e/test_supervisor_namespace_policy_e2e.py:173,192,209,226,245` 仍是固定 `time.sleep` 后断言进程状态（code review `t018_code_f028` 已登记，minor）。
    - `tests/unit/test_stream_binding_guards.py:115` 仍以私有 `_supervisor_fps_cap` 作基线读取（其后断言已用公开访问器），证据强度弱，未作为 AC 证据。
    - `tests/e2e/test_supervisor_retry_e2e.py:44-46` 重复两行 `from e2e_env import ...`，风格问题。
    - 真实 Docker E2E 未执行（worktree 无镜像/缓存/Chrome 前置），AC-004 的单次运行依赖实施侧证据；f031 为静态核对结论。
- 总体判断：全量 diff 与门禁复跑未见新红，但 AC-004 的专用秘密目录要求仍有 2 处未满足，f031 为 important，不能 PASS。
- 系统性 follow-up：无新增；f031 属 t018 收尾范围。

### AC 复验方式

- AC-001：`re_verified`。实跑 required 模式 collection（exit 2，列出 9 个缺项）与默认模式 79 collected；`python3 scripts/verify_frontend_dist.py --check-freshness` exit 0；`tests/unit/test_frontend_build_freshness.py` 通过。missing/corrupt stamp 分支无测试（f014 minor）。
- AC-002：`re_verified`。检索 `tests/` 无 `spec_from_file_location`/`sys.path.insert`；共享 fixture 位于 `tests/{unit,integration,e2e}/conftest.py`；Supervisor 测试驱动 `ProductionGatewayService`/`create_gateway_app`，重写 Gateway 夹具已删除；实跑默认模式 browser runtime 11 skipped、相关 supervisor/stream 组 1 passed / 9 skipped。
- AC-003：`re_verified`。实跑 unit 539、integration 79、默认 E2E 17 passed / 62 skipped；核对 IPv6 无条件阻断、退避双边窗口、冻结恢复帧增长、逐页静音、首帧/输入延迟上限（8000/3000ms）、viewer close 仅接受 CLOSE、清理断言在 finally 之后、会话关闭后容器 running 且 instance-id 不变。
- AC-004：`trust_prior`（真实 Docker 单次门禁）。静态核对端口派生、回环绑定、证据默认写系统临时目录、明文 `.scratch` 写入（f021 minor）与脱敏实现（f022 minor），发现 f031；`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 本轮未执行。
- AC-005：`re_verified`。实跑 unit 539 passed；本轮改动的单元测试使用公开访问器与注入时钟（ManualClock/fake_clock），`tests/unit/test_docker_offload.py` 的 `unblocked_while_running` 可失败断言保留。
- AC-006：`re_verified`（本地非 E2E）。实跑 contract 169、unit 539、integration 79、前端 Vitest 95、`--check-freshness` 通过；`.github/` 不存在；`docs/blueprint/testing.md` 的 `test_cmd`/`blackbox_verify` 只引用 `scripts/run_gates.sh`（含模板契约标记行）。
- AC-007：`re_verified`。实跑 `tests/unit/test_repo_hygiene.py` 2 passed；`git ls-files --eol` 无 CRLF；`docs/specs` 无凭据形态字面量；归档 spike README 与 `.gitignore` 规则存在；vendor 穿越/清单外分支仍无测试（f013 minor）。

coverage = 6 / 7

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 16 (2026-11-03T17:26:50+08:00)

- round：16
- reviewed_at：2026-11-03T17:26:50+08:00

reviewed_scope: 1d1e069822000fd7

### Findings

#### t018_test_f032 - `_wait_for_server_ready` 移除 sleep 后首次轮询即抛错，IPv6 网络策略 E2E 无法通过

- 严重度：important
- 锚点：AC-003「IPv6 阻断……断言覆盖其声明的行为」「测试中不存在固定 sleep 后断言状态」；AC-005「测试 docstring 与实际覆盖一致」；AC-006「本地全量门禁由单一入口脚本执行（含 E2E 必需模式）」
- 位置：`tests/e2e/test_supervisor_namespace_policy_e2e.py:257-264`（`_wait_for_server_ready`），调用点 `:449-451`
- 问题：0821e47 为满足 AC-003 删除 `time.sleep(0.1)`，把 `raise TimeoutError` 移进 `while` 循环体。循环第一次迭代若 `container.logs()` 尚无 `READY` 就立即抛错，`deadline = time.monotonic() + 10.0` 形同虚设。`target_b`/`target_c`/`target_d` 在调用前刚 `start()`，Docker 日志通常尚未包含 READY。已用同函数 + 假容器复现：`logs()` 返回 `b"booting without ready marker\n"` 时 0.0s 抛 `TimeoutError: Server fake-peer-b did not become READY in 10s`。该 helper 是 `test_kernel_network_policy_real_netns` 等待三台 raw server 的唯一同步点；E2E 必需模式（`CBROWSER_RUN_E2E=1 scripts/run_gates.sh`）下该用例会以 TimeoutError 失败，IPv6 ULA fail-closed 断言无法执行。函数 docstring 仍写「Bounded wait」，与实际覆盖不符。
- 建议：保留无固定 sleep 的轮询语义，改用 `tests/fixtures/wait.py::wait_until_sync(lambda: "READY" in container.logs().decode("utf-8", errors="replace"), timeout=10.0, interval=0.1, description=...)`，或至少把 `raise` 移出循环；补一个「首轮无 READY、次轮出现 READY」的回归用例。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f001–f011、f015–f020、f023–f031 维持已消除：Dockerfile 不再做镜像内新鲜度校验；E2E 依赖可收集（79 tests）；testing.md 只引用 `scripts/run_gates.sh`；无 `spec_from_file_location`/`sys.path.insert`；身份 E2E 已删除，生产 adapter 由 frontend app E2E 覆盖；新鲜度检查位于必需模式判断之前；必需模式列出 9 项缺项；IPv6 无条件下阻断、退避双边窗口、首帧/输入延迟上限、viewer close 仅 `CLOSE`、清理断言在 `finally` 之后、会话关闭后容器 running 且实例不变；Selkies 宿主发布 127.0.0.1；秘密目录 0700；offload 用例在同步 `to_thread` 回归下两用例均失败（本重复验），f024/f025/f028/f029/f030 均已按代码核对；生产 Gateway 驱动与拓扑夹具断言成立。
    - f012 已消除。`tests/unit/test_repo_hygiene.py:12-29` 改为扫描全部已跟踪非二进制文本（`.gitignore`、`.gitattributes` 均在范围内），不再依赖固定后缀；`pytest tests/unit/test_repo_hygiene.py` 2 passed。
    - f013 修不彻底（minor）。`tests/unit/test_vendor_selkies_security.py` 新增 `../escape`、`a/../../b`、`..`、空串与清单外文件用例，但未覆盖绝对路径/反斜杠，也未驱动真实的 `extract_from_wheel` zip 解包路径。
    - f014 修不彻底（minor）。`tests/unit/test_frontend_build_freshness.py:26-46` 已覆盖 stamp 缺失、不可读 JSON、字段缺失；其对 `tests/e2e/conftest.py` frontend item 实际拒绝接线的端到端覆盖仍缺。
    - f021 仍存在（minor）。`.scratch` 仍被 `tests/unit/test_supervisor_normal_exit_observation.py:600,916,998`、`tests/integration/test_normal_exit_replay.py:161,313,466,662`、`tests/e2e/test_browser_runtime_e2e.py:1420,2632`、`tests/e2e/test_runtime_profile_defaults_e2e.py:368`、`tests/e2e/test_supervisor_retry_e2e.py:603` 等写入；note 的「E2E 不再写仓库 .scratch」声明不准确。
    - f022 已消除。`tests/unit/test_evidence_redaction.py` 对 `save_evidence` 落盘内容断言 token/password/payload 被替换为占位符，且保留非敏感字段。
    - f031 已消除。`tests/e2e/test_runtime_coordinator_e2e.py:71` 与 `tests/e2e/test_supervisor_container_graph_e2e.py:80` 的 control 目录均为 0700，密钥文件 0600；拓扑夹具的目录模式断言仍在。
- 改测方向复核：无「迁就实现」的改测。a136a3f 仅收紧目录权限；c18c418/0821e47 为清理与补测；0821e47 的 sleep 删除求解 AC-003 方向正确，但实现引入 f032 回归，不属于把旧预期改成当前实现输出。
- 本轮新发现：1 条（important 1）。
- 未进表的提示：
    - `tests/e2e/test_supervisor_namespace_policy_e2e.py:173` 的 `assert proc.poll() is None` 在删除 0.3s 等待后紧贴 Popen 执行，单条断言近乎恒真；案例 2/6 仍能发现 gate 提前退出或串行错误，故不单列，但建议改用 `proc.wait(timeout=...)`/就绪哨兵。
    - `tests/unit/test_vendor_selkies_security.py:7` 直接 import 私有 `_safe_relative_path`，与 AC-005「单元测试只经公开接口断言」字面不一致（minor）。
    - `tests/e2e/test_browser_runtime_e2e.py:48-50` 与 `tests/integration/test_v2_api_subprocess.py:24` 改为模块级 `tempfile.mkdtemp`，目录未在用例结束清理（资源卫生 minor；已满足「只写临时目录」）。
    - 真实 Docker E2E 未执行（worktree 无 9 项镜像/缓存/Chrome 前置），AC-004 的单次资源隔离仍依赖实施侧证据；f032 为静态核对 + 假容器复现。
    - 契约区 drift（AC-004 删除并行双跑、AC-006 删除 GitHub Actions）与用户 2026-11-03 决策一致，不计 finding。
- 总体判断：本轮仅 f032 为 blocking；它使 E2E 必需模式无法通过，AC-003/AC-006 的打勾复核不成立，不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；f032 属 t018 收尾范围。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 以 exit 2 列出 9 个缺项；默认模式 79 tests collected；`pytest tests/unit/test_frontend_build_freshness.py` 3 passed；`scripts/run_gates.sh` 的 `npm run build` 执行 `--check-freshness` 通过。
- AC-002：`re_verified`。检索 `tests/` 无 `spec_from_file_location`/`sys.path.insert`；`tests/fixtures/e2e_env.py` 为单一前置清单；Supervisor 测试驱动 `ProductionGatewayService`/`create_gateway_app`；默认模式 `tests/e2e/test_browser_runtime_e2e.py` 11 skipped、supervisor/stream 组 1 passed / 19 skipped。
- AC-003：`re_verified`（代码+单元层）。实跑 `tests/unit` 547 passed、`tests/integration` 79 passed；核对 IPv6 无条件下阻断、退避上下限、冻结恢复帧增长、逐页静音、首帧 8000ms/输入 3000ms 上限、viewer close 仅 CLOSE、清理断言在 `finally` 之后、会话关闭后容器 running 且 instance-id 不变；f032 使 IPv6 E2E 的启动同步失效，完整真实 Docker E2E 未执行。
- AC-004：`trust_prior`（真实 Docker 单次门禁）。静态核对：Selkies 宿主发布仅 127.0.0.1、control 目录 0700 与密钥 0600、证据默认写系统临时目录、显示号/端口按 run 派生；f021 的 `.scratch` 写入仍为 minor；`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 本轮未由 reviewer 执行。
- AC-005：`re_verified`。实跑 `tests/unit` 547 passed；A39 点名文件已改用公开访问器/注入时钟；用同步 `to_thread` 替换 offload 实现后 `test_teardown_offloads_blocking_docker_cleanup` 与 `test_scan_inspect_offloads_blocking_docker_call` 均 AssertionError（卸载行为可失败）；f032 的 helper docstring 与实际不符仍归 AC-005。
- AC-006：`re_verified`（本地非 E2E）。实跑 `bash scripts/run_gates.sh` EXIT=0（contract 169、legacy 384、unit 547、integration 79、前端 Vitest 95、build/verify）；`.github/` 不存在；`docs/blueprint/testing.md` 的 `test_cmd`/`blackbox_verify` 只引用脚本（含模板契约标记行）；E2E 必需模式未由 reviewer 执行且 f032 使其静态失效。
- AC-007：`re_verified`。实跑 `pytest tests/unit/test_evidence_redaction.py tests/unit/test_vendor_selkies_security.py tests/unit/test_frontend_build_freshness.py tests/unit/test_repo_hygiene.py` 11 passed；`git ls-files --eol` 无 CRLF；`docs/specs` 无凭据形态字面量；归档 spike README 与 `.gitignore` 规则存在；vendor 穿越/清单外测试已补（绝对路径/反斜杠仍缺，见 f013）。

coverage = 6 / 7

建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 17 (2026-11-03T17:54:00+08:00)

- round：17
- reviewed_at：2026-11-03T17:54:00+08:00

reviewed_scope: d849d5179612e92c

### Findings

#### t018_test_f033 - AC-004 未完成：RuntimeCoordinator E2E 宿主测试 API 仍绑定 0.0.0.0

- 严重度：important
- 锚点：AC-004「测试服务只绑定回环」
- 位置：`tests/e2e/test_runtime_coordinator_e2e.py:189-193`
- 问题：`uvicorn.Config(api_app, host="0.0.0.0", port=api_host_port)` 由 pytest 在宿主进程启动，把带 admin 认证的测试 API 暴露到宿主全部网络接口；同套 E2E 的其它宿主服务（`tests/e2e/conftest.py:91-99` 的 `real_api_server`）都绑 `127.0.0.1`。此前以「Gateway 容器需经 host 访问」解释，但本机 OrbStack 实测该理由不成立：宿主仅绑 `127.0.0.1` 的 HTTP 服务可从自定义 bridge 网络的容器经 `host.docker.internal` 访问（`docker network create <net>` 后 `docker run --rm --network <net> alpine wget -qO- http://host.docker.internal:<port>/` 返回 200）。AC-004 已勾选但此子项未满足。
- 建议：改为 `host="127.0.0.1"`，保留 `CBROWSER_GATEWAY_API_URL=http://host.docker.internal:{api_host_port}` 供 Gateway 容器访问；若某环境不支持 loopback 转发，应在 spec/note 明确记录该环境豁免，而不是默认绑全接口。

#### t018_test_f034 - READY 轮询修复无回归测试

- 严重度：minor
- 锚点：AC-003 / AC-005（f032 修复的可测性）
- 位置：`tests/e2e/test_supervisor_namespace_policy_e2e.py:257-265`
- 问题：0821e47 曾把 `raise TimeoutError` 误移进循环体，4b1739b 已把 `raise` 移回循环外并恢复 50ms 轮询，修复本身正确；但没有用例覆盖「首次 logs 无 READY、下一次出现 READY 返回成功」与「始终无 READY 抛 TimeoutError」。该 helper 只在真实 Docker IPv6 E2E 中被调用，同类回归没有单测守护。
- 建议：用假 container 让 `logs()` 依次返回不含/含 READY，断言返回；再用始终不含 READY 的假容器断言 `TimeoutError`。

### 结论

- 前轮 finding 复核（以当前 worktree 与实跑为准）：
    - f001–f004 已消除。`config/docker/Dockerfile` 未传 `--check-freshness`，`bash scripts/run_gates.sh` 的 build/postbuild 实测通过；实跑 `tests/e2e/test_frontend_build_wiring.py tests/e2e/test_frontend_adapter_build.py tests/e2e/test_frontend_session_vendor.py` 13 passed；默认模式 `pytest tests/e2e --collect-only` 79 collected；`docs/blueprint/testing.md:40-55` 只引用 `scripts/run_gates.sh` 与模板契约标记行。
    - f005–f011 已消除。`grep -rn 'spec_from_file_location\|sys.path.insert' tests/` 无命中；`test_stream_client_identity_e2e.py` 已删除且身份/重映射由 `test_frontend_app_e2e.py` 驱动生产 adapter；新鲜度校验位于必需模式判断之前（`tests/e2e/conftest.py:28-46`）；`CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` exit 2 列出 9 个缺项；IPv6 无条件下阻断、退避双边窗口、首帧 8000ms/输入 3000ms 上限均在位；viewer close 只接受 `WSMsgType.CLOSE`；`docs/specs` 无凭据形态字面量。
    - f012–f014 已消除。`tests/unit/test_repo_hygiene.py:22-39` 扫描全部已跟踪非二进制文本；`tests/unit/test_vendor_selkies_security.py` 覆盖 `../`、绝对路径、反斜杠、清单外文件与真实 zip 解包；`tests/unit/test_frontend_build_freshness.py` 覆盖 stale/missing/corrupt stamp 与 conftest hook 拒绝。实跑 unit 551 passed。
    - f015–f020 已消除。unit 551 passed、integration 79 passed；Selkies 宿主发布 `127.0.0.1:{port}`（`test_stream_selkies_tokens_e2e.py:105`）；control 目录 0700/密钥 0600；offload 用例保留 `unblocked_while_running` 可失败断言；activity 负向注入由 `tests/integration/test_gateway_control.py:302-345` 的真实 Gateway + `REAL_SIGNALING_MSG` 哨兵覆盖。
    - f021 仍存在（minor）。`tests/integration/test_normal_exit_replay.py:161,313,466,662` 仍把状态写到仓库 `.scratch/normal_exit_fix`；note 已记录改用 /tmp 会导致 API 事件收敛用例失败，沿用前轮 minor。
    - f022–f032 已消除。证据脱敏落盘断言（`test_evidence_redaction.py` 1 passed）；contract 169 passed；`clock.delays == [1.0]` 精确断言仍在；清理断言在 `finally` 之后；`require_e2e_env` 单一前置清单与格式错 fail；offload 断言；变量名拼写；offline fixture 走 `require_e2e_env`（`offline_fixture.py:360-362`）；browser runtime 前置为 session autouse；control 目录 0700；f032 的 READY 轮询已恢复有界循环。
- 改测方向复核：无。4b1739b 的 READY 轮询、vendor 路径收紧、freshness/证据/vendor 安全测试均为新增或强化断言；`.scratch`→`/tmp` 与 0700 权限为资源隔离修正。未发现删断言、反转断言、`.skip`/`.only`、`# type: ignore` 或把旧预期改成当前实现输出的改动。
- 本轮新发现：2 条（important 1、minor 1）。
- 未进表的提示：
    - `tests/e2e/test_supervisor_namespace_policy_e2e.py:170-176,238` 的 `assert proc.poll() is None` / `assert not out_file.exists()` 紧贴 `Popen` 执行（原 0.3s/0.2s 等待已按 AC-003 删除），单条断言近乎恒真；契约仍由 case 2–5（非法 marker 必非零退出且不执行 app）与 case 6 覆盖，故不单列，建议改用 `proc.wait(timeout=0.3)` + `TimeoutExpired` 的有界等待写法。
    - `tests/unit/test_frontend_build_freshness.py:57` 用相对路径 `runpy.run_path("tests/e2e/conftest.py")`，只在仓库根运行时成立；门禁固定从根执行，属健壮性 minor。
    - `tests/e2e/test_frontend_adapter_build.py:66,96,124` 每次用全新 `mkdtemp` 作为 wheel 缓存，失去跨轮复用，每轮门禁都从 PyPI 重新下载（本机实测通过，但增加网络依赖与耗时）；`test_automation_cdp.py:57`、`test_runtime_profile_defaults_e2e.py:369`、`test_browser_runtime_e2e.py:49,51` 的 `mkdtemp` 未清理，属临时资源残留。
    - `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 未执行（缺 9 项镜像/缓存与 Chrome 前置）；AC-004 的「单次运行」仍依赖实施侧证据，本轮 f033 为静态核对 + 本机 Docker 可达性复现。
    - `tests/fixtures/frontend_probe/harness.py:24` 仍读取 `.scratch/images_env.txt`（只读，非写入），与 f021 的 `.scratch` 同属遗留面。
- 总体判断：f001–f020、f022–f032 均已真正修复且本地门禁全绿，但 AC-004「测试服务只绑定回环」仍有宿主 API 绑 `0.0.0.0` 的实例（f033 important），打勾复核不成立，不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；f033 属 t018 收尾范围（一行 host 修改 + 一次 E2E 复核）。

### AC 复验方式

- AC-001：`re_verified`。实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 以 exit 2 列出 9 个缺项；默认模式 79 collected；`bash scripts/run_gates.sh` 的 `npm run build` 执行 `--check-freshness` 通过；`pytest tests/unit/test_frontend_build_freshness.py -q` 4 passed（含 conftest hook 拒绝用例）。
- AC-002：`re_verified`。`grep` 确认 `tests/` 无 `spec_from_file_location`/`sys.path.insert`；共享 fixture 在 `tests/{unit,integration,e2e}/conftest.py`；`ProductionGatewayService` 驱动生产 `create_gateway_app`，旧 `gateway_fixture.py` 已删除；默认模式 `test_browser_runtime_e2e.py` 11 skipped、runtime_coordinator/container_graph/event_shutdown/stream_selkies 7 skipped，无 error。
- AC-003：`re_verified`（代码+单元层）。实跑 unit 551 passed、integration 79 passed；核对 IPv6 无条件下阻断、退避双边窗口、冻结恢复帧增长、逐页静音、首帧/输入延迟上限、viewer close 仅 CLOSE、清理断言在 `finally` 之后、会话关闭后容器 running 且 instance-id 不变；完整真实 Docker E2E 未执行。
- AC-004：`trust_prior`（真实 Docker 单次门禁）。静态核对 Selkies 宿主发布仅 127.0.0.1、control 目录 0700/密钥 0600、证据默认写系统临时目录并脱敏、端口/显示号按 run 派生；发现 f033；`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 本轮未由 reviewer 执行。
- AC-005：`re_verified`。实跑 unit 551 passed；A39 文件已改用公开访问器/注入时钟；offload 用例保留可失败的 `unblocked_while_running` 断言。
- AC-006：`re_verified`（本地非 E2E）。实跑 `bash scripts/run_gates.sh` EXIT=0（contract 169、legacy 384、unit 551、integration 79、前端 Vitest 与 build/verify）；`.github/` 不存在；`docs/blueprint/testing.md` 的 `test_cmd`/`blackbox_verify` 只引用脚本与模板契约标记行。
- AC-007：`re_verified`。实跑 `tests/unit` 551 passed（含 repo hygiene、vendor 安全、freshness fail-closed、证据脱敏）；`git ls-files --eol` 无 CRLF；`docs/specs` 无凭据形态字面量；归档 spike README 与 `.gitignore` 规则存在。

coverage = 6 / 7

verdict: FAIL

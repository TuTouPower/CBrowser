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

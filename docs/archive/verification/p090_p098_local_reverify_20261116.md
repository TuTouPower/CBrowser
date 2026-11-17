# p090–p098 本地补验证据（主线 ae02d42，2026-11-16）

## 口径与基线

- 用户选定「按现状做本地复核」：gate5 终局证据里已验证过的真实部署栈 / E2E / 真实引擎切片不重复执行；只做当前主线上仍缺的本地实测（源码存在性 + 定向单测 / 契约检查）。未重建生产栈、未跑 `CBROWSER_RUN_E2E=1`、未改任何产品/测试源码、未 commit。
- 基线：`main` @ `ae02d42 merge(t073): t073_frontend_design_system_env_and_session_ui`，`git status --short` 为空；Node 26.13.0 / Python 3.15.2 / Docker 29.4.0；门禁 venv `.scratch/gate_venv`（Python 3.15.2）；时间 2026-11-16T13:26:29+08:00。
- 逐项日志：`.scratch/p090_p098_reverify_20261116/logs/`（`environment.log`、`static_checks.log`、9 份 `p0NN_*.log`）。
- 9 项均已在 `docs/archive/pending/` 且 `resolution` 已定（8 resolved / 1 obsolete）；本次仅在各归档文件末尾追加「主线 ae02d42 本地复核」段落，保留历史正文，未重复 `pending.py archive`。

## 逐项结果

|项|resolution|静态核对|定向实测|结论|
|---|---|---|---|---|
|p090|resolved|`SESS_DETAILS_TOGGLE` 唯一、面板内无第二开关、`useBrowserSession.wsRecovery` 状态机仍在|`p090_frontend` Vitest 5 文件 → 61 passed / EXIT=0|AC-001 真实 Chrome 布局实测属 gate5 已验，不重复；行为层单测仍成立，重判裁定不变|
|p091|resolved|中文 transport 三态、详情面板兜底、AC-007 不含凭据断言仍在|`p091_frontend` 4 文件 → 59 passed / EXIT=0|代码/测试修复仍成立；本项非 Docker 验证范畴|
|p092|resolved|`generate_requirements.sh --check` 6 组 ok；6 份 Dockerfile 存在|`p092_t062` → 19 passed / EXIT=0|镜像边界云端可验部分仍成立；真实部署/非默认端口属 gate5 已验|
|p093|resolved|`env-backup`/`env-restore` 入口、`db_backup.py`/`db_restore.py`、findings d044/d045 齐备|`p093_t066` → 26 passed / EXIT=0|恢复点/状态守卫仍成立；f2/f3 真实引擎实测属终局已验|
|p094|resolved|`cdp_guard.py` 403 fail-closed + Host/Origin、`network_config.py:97` `forward_auth`|`p094_cdp` → 36 passed / EXIT=0（含 chain 1 例）|CDP 守护与集成链仍成立；真实拓扑 E2E 属 gate5 已验|
|p095|resolved|`deploy.sh:616` `check_prefix_conflict`、`:624-658` 严格 instance-id 归属|`p095_t069` → 86 passed / EXIT=0|归属严格化仍成立；无标签容器专项属终局已验|
|p096|resolved|受控构建清单 `config/selkies/selkies_controlled_build.json` 与对应单测仍在|`p096_t063_control` → 10 passed / EXIT=0|AC-001 镜像链属 gate5 已验；措辞细化见下|
|p097|resolved|`_selkies_root_names`/`_is_selkies_attribute_write`/`_selkies_guard_violations` 与四种拼写试探仍在|`p097_t063_guard` → 19 passed / EXIT=0|导入溯源守护仍成立、零误报|
|p098|obsolete|转发器标识全仓零命中；`credential_revision` 失败封闭保留|`p098_t035` → 33 passed / EXIT=0|验收对象未复现，obsolete 裁定仍成立|

合计：后端定向 7 组（19+26+36+86+10+19+33 = 229 passed）/ 前端定向 2 组（61+59 = 120 tests），全部 `EXIT=0`、`0 failed`。

## 复核发现（如实记录，未修）

- p096 措辞：归档「全仓检索确认后端无 `active_peers` / `fps` 仲裁逻辑」在当前源码不够精确 —— `src/backend/cbrowser/stream_agent/policy.py:578` 存在 `active_peers`，语义是「无活跃 viewer → 暂停采集」的可见性仲裁（`reconcile_capture_state`），不是「静止 8 / 运动 30 FPS」帧率仲裁；全仓仍无 8/30 数值仲裁逻辑。gate5 `test_frontend_media_e2e.py::test_ac004_visibility_stop_start_through_full_app` 覆盖的正是前者。AC-002 核心判定（8/30 属 Selkies 上游策略、非 cbrowser 实现）不变，仅措辞按此细化；未改归档历史正文、未改代码。
- p091 细节：t073 把顶栏状态标签换成 `sessHeader*` 带主语 key，p091 补的中文 recovering/failed/unknown 三态覆盖仍保留（`SessionHeader.test.tsx:299-301`）。
- 9 项归档状态与最终裁定在 `ae02d42` 上均仍成立，无新增阻塞项。

## 易失证据清单（本次固化入库）

- gate5 原始证据目录 `.scratch/local_verify_terminal_gate5/`：**不存在**（归档文件仍引用；gitignored、未归档）。
- gate4 原始证据目录 `.scratch/local_verify_terminal_gate4/`：**不存在**（同上）。
- `.scratch/terminal_deploy_slices/` 现存：`p090_layout.log`、`p090_p100_real_profile.log`、`p092_nondefault_port.log`、`p093_ac003.json` / `.log`、`p093_ac005.json` / `.log` / `.py` / `_probe.py` / `_recheck.py`、`p093_e2`、`p093_env_roundtrip.log` / `p093_env_roundtrip2.log` / `p093_phase1.log` / `p093_state.log`、`p095_prefix_conflict.log`、`point-a`、`nondefault.env`。均为 gitignored 易失路径。
- `.scratch/local_verify_20261113.md`（2026-11-13 全链本地验证报告）仍在，gitignored。
- `artifacts/t060/` 仍在，但 `/artifacts/` 被 `.gitignore` 忽略，`git ls-files artifacts/` 为 0，未入库。
- 本轮新证据 `.scratch/p090_p098_reverify_20261116/`（logs/ + tmp/）同为 gitignored；逐项结论已随本文件与 9 个归档文件入库。
- 范围外提示：同批 gate5 原始证据目录缺失也影响 p099 / p100 / p101 的引用，未在本次 p090–p098 范围内处理。

## 未做的事

- 未重跑 `CBROWSER_RUN_E2E=1` / `CBROWSER_REQUIRE_REAL_ENGINE=1`、未重建任何镜像、未启动 `scripts/deploy.sh deploy` 生产栈、未构造故障注入/长时观测脚本。
- 未跑全量门禁（上一轮 `ae02d42` 终局门禁 9 项已全绿，见 `.scratch/gate_final_ae02d42/manifest.json`）。
- 未改产品/测试源码、未改归档文件历史正文、未 `commit` / `push`。

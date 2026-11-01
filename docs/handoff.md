# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-01T12:48:22+08:00 已获直接基线修复授权，实现lane运行中

### 状态与范围

- branch：main；head_commit：`a673edfac30f7394d70f79ffe7945101f8bfcfd1`（本文另行提交）；生产源码、测试与冻结队列均未改动。
- t001–t007 done/integrated；goal-check 为 GOAL_QUEUE_INCOMPLETE（2/9 closed）。剩余 t008 → t013 → t014 → t009 → t010 → t011 → t012，均无 attempt。本地逐项合并已获附件授权；禁止 push。
- 用户最新明确授权：“不需要创建task 直接改”。基线修复不创建task，不变更冻结队列；独立worktree实施、review与主控门禁后合入main，再继续t008。此授权覆盖前置门禁发现缺陷，无需重复询问。

### 本轮证据与结果

- 目录 `.scratch/v2_baseline_20261101/`；实际生产源 `4be9ee2`，后续仅交接文档提交。镜像由该源构建；不可变 ID 为 `images.env`、六个 `.iid`，构建日志及 `build_results.json` 均保留。
- 后端 unit：383 passed（`unit_r2.log`）；旧后端 + integration：446 passed（`backend_r2.log`）。最初运行器目录/PYTHONPATH失误原日志保留，修正 scratch 环境后复跑，未改代码或断言。
- 模板 contract：168 passed、1 skipped；Vitest exit 0；生产前端构建含 vendor/postbuild verify exit 0；md_format 格式一致；五项 schema/codegen 重生成字节一致。tsconfig.tsbuildinfo 已恢复，工作区干净。
- Runtime Docker E2E：13 passed（167.80 秒）。Stream：17 passed、2 failed（142.13 秒）。Supervisor：17 passed、9 failed（161.28 秒）。Gateway：5 failed（27.80 秒）。前端：14 passed、4 failed、13 errors（21.68 秒）。旧生产健康检查 exit 0，不代表 v2 已交付。
- Ruff E/F/W/I：90 errors（`ruff_efwi.log`），全默认规则报告另见 `ruff.log`；未修复或豁免。
- 完整首轮 runner session 82335/PID73111 已结束，退出 0 仅代表脚本跑完，逐项失败见 `check_results.json`，不能计全门禁 PASS。

### 已确认缺陷

- 镜像实际 import 冒烟 `image_import_smoke.py` 在同一外层锁下执行，session21030 已结束：API 与测试 Gateway 缺 `cbrowser.gateway`；正式 Supervisor/Gateway 缺 `cbrowser.secret_files`。四镜像均 exit1，原始 `import_*.log` 与 `import_smoke_results.json` 已保存，实际 Docker 整镜像执行，无源码覆盖。
- Supervisor recovery 夹具仍用旧 Gateway 端口，真实子进程 ValueError `Gateway URL port does not match the configured Gateway port`；resource monitor fixture token 权限不符合0600；旧基础设施测试期待18097，实际18080；旧启动恢复测试期待missing_runtime而实际observed_error。
- Stream旧精确挂载断言漏新增凭证文件；修复须保留旧测试或整体删除注明替代覆盖，禁止就地改预期迁就实现。
- 拓扑初始化失败泄漏容器，coturn占用50000导致后续前端级联失败；不能计作网络安全负例或产品媒体失败。
- 初步归因与证据索引 `root_failure_triage.json`，独立审核已结束，报告及主控复核见下文。

### 资源、审核与下一步

- 主控已核对并清理本轮16个残留容器、6个空网络；精确清单 `cleanup_plan.json`，关键异常行 `cleanup_error_*.txt`。旧生产cbrowser、kkmail/haiwa及来源不明历史对象保留。
- 独立审核已结束：session59258、CLI PID76238已终止，实际cli_exit=0，durable_finished=False（wrapper只读全局DB，XDG隔离后的会话不在该DB中），不据外层退出码判断完成。最终report存在且已主控读取。
- 证据备份 `.scratch/v2_baseline_20261101/audit_evidence/`（report.md、guard.json、permission.json）；JSON与wrapper日志留主仓。审核worktree tracked文件无变化，已git worktree remove + prune；最终仅main和主worktree，无新增分支。
- 主控确认审核新增发现：supervisor/runner.py:187/192引用当前函数作用域不存在的d_client/docker_adapter，Ruff F821与源码对应；需补触达真实事件监听任务的RED测试后修复。policy.py中should_block_client_verb被动态重导出，禁止盲目ruff --fix删除。
- 审核报告部分计数与主控原始日志矛盾（Runtime应13通过、Vitest应112通过、Supervisor应17通过9失败、前端应14通过4失败13错误），均以本交接及原始日志为准。共享pytest缓存导致污染的因果未经证实，不采信；单独执行build/contract/schema等证据有效，不以未集成同一个runner否定。
- 当前实现lane：worktree `/Users/karson/kar/code/CBrowser_baseline_fix`，branch `fix/v2_baseline_gates`，base/diff_anchor `a673edf`；OpenCode cpa/gemini-3.8-flash high；dispatch PID79658、wrapper79668、CLI79669（启动时值，恢复须核对实时进程）。无task identity，不动ledger。
- lane证据主仓 `.scratch/v2_baseline_20261101/fix_dispatch/`：prompt.md、allowed_paths.json、implementation.jsonl、wrapper.log、launch.json。只给已确认缺陷具体文件写权；lane报告 `.scratch/baseline_fix/report.md`。XDG data/cache/state在主仓scratch。
- 主控已准备 `fix_dispatch/verify_candidate.py`（尚未运行）：先重建六镜像/实际import，再unit/integration/legacy、前端安装测试构建、schema/codegen、Ruff、文档及逐文件Docker/Chrome E2E。先修正运行器目录和PYTHONPATH准备；前端buildinfo还原原字节。
- 下一步：观察同一CLI实际状态，待实现报告后审diff并主控复跑、独立review；完整门禁通过才启动t008。不得复用已结束的82335/59258等旧句柄。
- 本轮未改 `.repo_template`，未重启OrbStack或扩大配额。公网/原生Linux x86_64为NOT_RUN / USER_WAIVED；8小时与1000次IME/剪贴板未执行，不预计通过。

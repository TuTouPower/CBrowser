---
tid: "t032"
slug: "local_target_environment_acceptance"
title: "本地完成真实镜像、运行时故障与 Agent 目标环境最终验收"
status: "done"
branch: "t032_local_target_environment_acceptance"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "c0ab32d7ba453ef520cb9fbbeb7a6991d7f82f6a"
depends_on: "t025,t026,t027,t028,t029,t030,t031"
conflicts_with: ""
note: "仅本地执行；合并 p021-p024/p026/p027 实跑债，并验收 t025-t031；云端 Muse 不执行"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-04：六条历史真实环境债与本批新增目标环境验证汇总；本 task 只在本地最后执行。

- 云端任务结束不构成本 task 任何实跑条款通过证据。

- 2026-11-04：按三方审阅修订：隔离实例、构建上下文、镜像身份、证据模式与历史真实链入口改由 t027/t028 交付；指纹/XTEST 用 t029 预登记阈值在真实镜像复核；daemon 故障演练无独立 daemon 时记 NOT_RUN。

- 2026-11-05：用户决定 AC-011/012 改用实际交付引擎 `146.0.7680.177.3`，在 Linux arm64 容器内挂载引擎缓存并用 Xvfb/xte 跑探针；`146.0.7680.177.5` 不再作为阻塞条件。AC-012 外站人工判读/因果复核、AC-013 原生权限/设备选择器、真人 CAPTCHA/2FA、IME 人工交接移出本轮，报告记 `OUT_OF_SCOPE_BY_USER`；自动项不得降低。

- 2026-11-05T09:09:47+08:00：承接 OpenCode 会话，按用户“继续完成工作”授权沿用 main 实施现场；模板同步至 `3101540`，总账由 note.md 迁为 progress.md。当前 task 尚未登记为 active，不伪造 execution identity 或 done 回执。

- 本轮补齐 `.3` 版本选择（缓存、实际 BrowserRunner、报告一致）、修正已删除的 close 用例名，并加入 t030 执行器完整集；容器入口固定 Linux arm64、5 样本、不可变镜像及独立证据目录。源码使用受限 tracked 文件快照，隔离生产数据与秘密。

- TDD：选中 `.3` 时 runner.engine_build 原为 None；新增回归先红后绿。探针与隐私守护定向检查 19 passed；源码快照冒烟通过。

- 初轮完整 unit：992 passed / 1 failed，失败为上轮 handoff 追加导致历史精确指纹失效；验证旧历史字节完整保留、新增正文无路径泄露后更新精确 SHA256。同步又将历史 note.md 改为 progress.md；验证只改标题后同步两条精确路径与指纹，不改归档正文。

- 完整门禁在 `.scratch/t032/resume/evidence-complete/` 运行；首轮环境问题与测试失败分开记录。使用已有 Python 3.12.14 与已锁定 uv 缓存，不修改门禁脚本。contract 出现模板本地 .env 受管链接相关两项失败，已立即报告，未修改或绕过模板。unit 的迁移白名单失败已定向修正，最终需引用补验结果。

- 2026-11-05T10:00:00+08:00：修 handoff 点名的两个 review 清理问题，均未提交：Gateway 诊断 finally 改为嵌套 finally + 30s 有界 best-effort，cleanup 必执行；探针 `run_levels.Sample` 在 `__aexit__` 按样本 `PULSE_RUNTIME_PATH` 有界停止 Pulse daemon 并恢复全局环境（helper 落 `harness.py`，`run_levels` 只调用，不改生产 Runner）。探针单测 13 passed，`compileall` 与 `git diff --check` 通过。

- Gateway AC-003 间歇 404/409 根因：Supervisor 在 Gateway 重启后、Stream 重注册前观测到 unregistered 即替换 Stream（`stream_unregistered`），测试持有的旧 `stream_box` 失效。诊断证据：`supervisor_failure.log`（新诊断落盘生效）显示 `Stream-only replacement: stream_unregistered`。定为产品缺陷：健康但暂时断连的 Stream 不应为恢复瞬态付出容器代价。

- 产品修复（`src/backend/cbrowser/supervisor/core.py`，未提交）：registered→unregistered 跃迁进入 90s 恢复宽限（`_REGISTRATION_LOSS_GRACE_SEC`，覆盖 Stream 最大 30s backoff 台阶 + 注册往返 + 收敛轮次），宽限内只记 `registration_recovery_grace` 不替换；从未注册过的 profile 仍立即替换；宽限过期仍未恢复则替换。TDD：新增 2 单测先红后绿，`test_t026_supervisor_convergence.py` 32 passed。

- Supervisor SIGKILL 端口 None 根因：health 200 只代表 liveness，post-startup 扫描异步恢复 session，测试读早了（产品侧 t027 已明确 health 不被慢扫描阻塞）。定为测试等待契约：测试改为 120s 内轮询 status 至双 profile 端口落定再断言不变性。单例 32.66s 通过。

- 定向单例验证（新 Supervisor 镜像 `sha256:304e60fc...`，仅覆盖本次运行变量，未改 `fix-env.sh`）：Gateway AC-003 连续 3 passed（62s/37s/34s）；Supervisor 端口不变性 1 passed。一次通过不宣布根除，单测为确定性证据。

- 模板 contract 两项失败已走 `template-issue-report` 上报：`TuTouPower/repo_template#84`，本地件在 `.scratch/repo_template_issues/20261105-094615*.md`；本仓不再碰模板。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-05T11:44:36+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t032_code_f001|minor|遗留|有界 ≤90s、过期必替换，不造成崩溃/数据丢失/资源泄漏/协议不兼容，不阻断本轮收口；不在验收 task 扩大交付范围|p042|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-012/013 人工项按用户决定移出范围；AC-013 DPR 与复杂手势记 `INCONCLUSIVE`；完整门禁 `all_passed=false` 的 7 项 e2e 失败如实登记为环境与性能遗留，均不声称通过）
- 测试：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 完整 required + evidence 门禁（contract 223 项、unit 998 项、integration 160 项 18 skip、frontend_test / frontend_build 全绿；e2e 102 项中 7 项失败、2 项 skip，`all_passed=false`，逐项见 `final_report.md`）；定向单测 45 passed；容器探针 `probe.xml` 2 passed、子 `chain.xml` 16 passed 0 skip、`levels.json` L0–L6 八组各 5 样本；Gateway AC-003 单例连续 3 passed、Supervisor 双 Profile 端口不变性 1 passed。
- 黑盒：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 的 E2E 必需模式在真实 Docker/Chrome 拓扑执行，镜像 ID 通过 `image_identity_problems` 不可变身份校验；另在 Linux arm64 容器内以实际交付引擎 `146.0.7680.177.3` 跑 AC-011/012/013 探针与外站三站可达性（`.scratch/t032/resume/probe-final/`）。
- review：full 级独立 review（`review_code.md` / `review_test.md`）PASS，finding 全部处置，AC 打勾经 TICK-VALID 复核。
- AC 判定：见 `task.md` 行内打勾与本目录 `final_report.md`

### 结果摘要

- 15 条 AC 全部在本轮目标环境取得证据；最终验收报告与运行入口索引见 [`final_report.md`](final_report.md)。
- 本轮修复 3 个缺陷：Gateway 恢复瞬态误替换 Stream（`core.py` 注册恢复宽限）、Supervisor 端口不变性测试等待契约、两个 review 清理问题（Gateway 诊断 finally、探针 Pulse 按样本隔离）。
- 遗留只写引用：模板 contract 2 项见 `TuTouPower/repo_template#84`；AC-013 DPR/复杂手势 `INCONCLUSIVE` 与 AC-011 OOPIF 细粒度断言见 `final_report.md` 遗留节；人工项 `OUT_OF_SCOPE_BY_USER`。

### 长期文档闭环

- specs_index: not_applicable: 本 task 为目标环境最终验收，不产生新的长期行为契约；既有 `automation_compatibility` 等 spec 不变，`docs/blueprint/testing.md` 仅新增探针运行入口。
- 正式 spike：无；一次性实验证据全部留在 `.scratch/t032/resume/`，不建 sid。

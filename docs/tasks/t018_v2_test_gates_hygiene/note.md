---
tid: "t018"
slug: "v2_test_gates_hygiene"
title: "测试体系、交付门禁与仓库卫生整改"
status: "active"
branch: "t018_v2_test_gates_hygiene"
worktree: "../CBrowser_t018"
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "5a3da225fbccf59d410e708a3754e7ab2160e12b"
depends_on: "t015,t016,t017"
conflicts_with: ""
note: "来源 docs/reviews/review_20261102_201727/adoption_decision.md"
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 2026-11-03 实施

- 已实现：`tests/e2e/conftest.py` 必需模式与前端构建新鲜度门禁；`scripts/verify_frontend_dist.py` 增加源码哈希 stamp/新鲜度校验；`scripts/write_frontend_build_stamp.py` 与 postbuild 接入；`scripts/run_gates.sh` 统一本地门禁入口；删除 GitHub Actions 工作流与 `release.yml`；`.gitattributes` 行尾规则；`docs/archive/spikes/README.md` 与 `.gitignore` 探针秘密/工作目录；路径隐私守卫测试与 conventions 约定；vendor wheel/tar 解包穿越拒绝与目录集合精确校验；会话 E2E 关闭页面后实例不变的断言。
- 已通过：unit 540、integration 79、contract 169、frontend Vitest 95、tsc/build/verify、E2E collect 78。

2026-11-03 用户决定：不需要任何 GitHub Actions CI；不做同机双跑验收。AC-004 收敛为单次门禁资源隔离，AC-006 收敛为本地单入口并删除全部 GitHub 工作流。

- 继续完成：Supervisor E2E/单元改用生产 Gateway，删除重写替身与容器入口；12 个 E2E 文件固定 sleep 改为有界轮询，保留采样/负断言/冻结窗口并注明理由；共享 `tests/fixtures/wait.py`；单元测试公开接口化、注入时钟与全局状态还原；`tests/conftest.py` 统一导入路径，移除跨测试模块 sys.path/importlib 注入；会话 E2E 关闭页面后断言 running 且实例不变。
- 复审修复：生产镜像不再执行源码新鲜度校验（仅 E2E/conftest 与本地 postbuild 校验）；必需清单补 invalid-policy 镜像；run_gates 补全 E2E 依赖；测试门禁改为只引用脚本；`real_api_server` 移入 e2e conftest；删除 Web Locks shim 身份测试，改由生产 adapter/前端 E2E 覆盖；IPv6/清理断言移出 finally；补首帧/输入延迟上限与冻结帧增长；stream E2E 端口改为动态分配；路径隐私守卫纳入 reviews（历史文件 allowlist）；live spec 凭据字面量抽象化。
- 复审修复：E2E NameError/socket/REPO_ROOT、testing.md 单入口、run_gates 临时目录清理、证据脱敏、ProductionGatewayService 关闭 httpx、IPv6 无条件下阻断、退避上下限、会话冻结帧增长。
- AC-005 收尾：`test_stream_capture_policy.py` 去掉 `_is_paused` 断言与固定 sleep，改用公开 pipeline 状态与注入时钟；`SupervisorCore` 新增只读 `get_session` / `terminal_observation_acknowledged` / `query_agent_health` 观测接口，相关单测不再直接断言 `_sessions` / `_terminal_observations`。剩余存量私有断言不在本 task 触碰范围。

第二轮：E2E 前置条件统一走 `tests/fixtures/e2e_env.py`（required 模式 fail、否则 skip）；单测私有状态断言清零并改用公开访问器；Supervisor E2E 端口改为运行内空闲范围，容器通过 `CBROWSER_UDP_MUX_MIN_PORT/MAX_PORT` 注入；`tests/conftest.py` sys.path 注入移除，改用 pyproject `pythonpath`，跨模块 fixture 移入 conftest。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round N (YYYY-MM-DDThh:mm:ss+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t000_code_f001|critical/important/minor|已修/遗留/撤回|一句话|文件:行 / pNNN / tid|

无 finding 时写“Round N 零 finding”。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足 / 未满足
- 测试：待执行时填写
- 黑盒：待执行时填写
- review：待执行时填写
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 待执行时填写；遗留只写引用，不复制正文

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

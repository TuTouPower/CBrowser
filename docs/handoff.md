# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T21:55:00+08:00 全仓审阅 adoption 定稿，剩余 v2 队列重排；下一步 t015

### 主仓

- branch `main`，交出时 head_commit `fc38a1d`（本交接单独提交）。仅 main 分支，无 task worktree。origin/main 在 `38c40c8`；`4e6a4fa`、`4970596`、`fc38a1d` 与本交接 commit 未 push。
- 本节 commit：`4e6a4fa` 审阅决策归档；`4970596` legacy compose 端口绑定 127.0.0.1、AUTH_TOKEN 标为必填；`fc38a1d` 新建 t015–t018 并重排 t009/t010/t012。

### 审阅与决策

- intensive review `docs/reviews/review_20261102_201727`：362 条 finding（Critical 1 / High 32）全部处置，决策文档 `adoption_decision.md`：采纳 A1–A48、不采纳 R1–R6，附逐条映射。
- 用户决策标准：最好的架构与设计、最少技术债，不考虑开发时间与改动大小；单机单人是需求范围，不降低质量标准。t014 drop 与 t009 AC-003 手动清单两项降级不恢复。
- 关键用户决策：D2=A（CI 改现行布局跑可移植层、`scripts/run_gates.sh` 统一本地门禁、删除 release.yml）；D3=B（先 spike 验证同机直连，通过则删除 coturn/TURN 轮换/ICE 代次接管/Selkies 私有 ABI 补丁）；D4=A（模板缺陷向模板仓提 issue）；D5=A（路径隐私约定 + 守卫测试）；D6=A（启动参数白名单）；D7=A（提前删除 v1 前端）；D8=A（生产 adapter 删除测试钩子）；D1=A（见下）。

### 现场

- 旧版 legacy 容器 `cbrowser`：审阅实测 SPA 路由存在无认证路径穿越且发布在 0.0.0.0；已改为 127.0.0.1 绑定后，用户决定直接停用（`docker compose stop`，未删除）。数据根 `~/.cbrowser` 保留，供 t010 迁移。注意：仓库 `.env` 的 `AUTH_TOKEN` 与旧容器原用值不同，legacy 已停用且将由 t010 删除，无需处理。
- 模板工具链缺陷（59 条，按组件归并）由 sub agent 按 template-issue-report 向 `TuTouPower/repo_template` 提交；本地报告在 `.scratch/repo_template_issues/`（gitignored）。交出时该 sub agent 仍在运行，issue 编号以其报告为准。
- 已知 skill 缺陷（用户自有 my-adoption skill，非模板）：第 1 步 `ls -d docs/reviews/review_* | sort -V | tail -1` 在目录命名混用时会选中旧目录 `review_v2_scope_20261027`，已报告用户，未修改。

### 队列

- goal 快照已重新冻结：t015 → t016 → t017 → t018 → t012 → t009 → t010（`docs/runtime/goal_queue.json`，gitignored）。全部 full review，创建期 preflight PASS。
- t015 媒体链路收敛：AC-001 依赖 UNVERIFIED-SPIKE（同机 Chrome local 直连全场景）；spike 不通过须停下请用户批准改写 AC（改为保留并冻结 TURN 机制，落实 A10/A11/A12/A30 的 TURN 部分）。t016 与 t015 只有冲突标记无硬依赖，t015 阻塞时可先做 t016。
- t012 已改为“v2 正式部署产物与部署文档”，排在 t009 之前；原 AC-004 移入 t010。
- t009 依赖改为 t012；AC-005 的 coturn/凭证切换项待 t015 结论后改写。
- t010 已合并原 t011（AC-006~009）与原 t012 AC-004（AC-010）：迁移真实数据、停用 legacy 并删除其代码、正式部署到本机。真实数据操作与本机部署需用户单独授权。
- `docs/pending/todo/` 为空。

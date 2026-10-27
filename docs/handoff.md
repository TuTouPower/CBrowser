# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落由 `repo-hygiene` 迁入 `docs/archive/handoff.md`。

## 2026-10-27T19:12:42+08:00 v2 架构计划执行交接

- branch：main
- head_commit：df439afa48cfd1705fdbd18e21164de3fc56f4b2（更新本交接前主干 HEAD）
- 交接更新约定：每完成一个阶段立即更新本文件（用户最新明确要求），包含该阶段提交、实际验证、遗留项及下一步。
- 执行目标：完成 `docs/v2_architecture_plan.md`，最终部署到当前 Mac 的 OrbStack Docker，由同机 Chrome 访问。当前仍处于 t001 技术验证收尾，正式 v2 业务实现尚未合入。

### 最新用户决定

- 公网穿透、原生 Linux x86_64 执行记 `NOT_RUN / USER_WAIVED`，不再阻塞实施，不得记为实测通过；保留相关功能及构建支持。
- 基准：M1 Max、10 核、64GiB；OrbStack 实际 10 CPU、约 15.66GiB，Linux aarch64，CPU 编码。1/3/10 活跃流逐级测容量，保留单流 1080p30、反馈 P95≤100ms、首帧 P95≤1秒、8小时压力及1000次 IME/剪贴板验收。这些是目标，尚未完成正式性能验收。
- 本地部署为最终交付；外部推送、公网发布须另获明确授权。旧环境阻塞记录已被上述决定取代，不再索要被豁免环境。

### 已完成与验证

- 主干已登记14个 task 及依赖：t001→t002→t003→t004→t005→t006→t007→t008→t013/t014→t009→t010→t011→t012；t013/t014 存在并发冲突，依工具生成计划执行。
- 最近提交：`ece7eaa` 记录环境豁免；`df439af` 调整本地性能基准及 t009/t012 契约，文档已独立审查。
- t001 工作副本有9项已归档 spike、d001–d014 findings、验证矩阵与蓝图/spec 更新，均未作为 t001 执行 commit 合入。
- 基线回归：模板169通过、后端384通过、前端49通过。前端 Node26 需 `NODE_OPTIONS=--no-experimental-webstorage`；模板测试 TMPDIR 使用 Git 工作副本之外目录，避免已有 fixture 受真实 worktree 影响。
- doctor/test/blackbox 命令块通过；repo_sync status 报未初始化，不能据退出码0宣称同步已配置。

### 当前现场与恢复入口

- t001 权威工作副本：`/Users/karson/kar/code/CBrowser_t001`；branch：`t001_v2_runtime_validation`；head_commit/diff_anchor：`3c8bdbc55570e85aaeb6365a3d512da9c0ce180c`。存在大量未提交交付文件，必须保留，不得依据主干旧 backlog 重复 start。
- exact identity：attempt=1，execution_id=`f5cd74fec7234b418c76206a08cff06b`，owner_id=`root_v2_20261027`。状态读取、恢复和收尾只经 task.py；严格 preflight 已按修订契约通过。
- 正式 Round1 code/test 审查已派发 OpenCode `cpa/gemini-3.8-flash`，两路原进程均已终止并生成 PASS。主控复核发现 code 报告有与实际源码不符的 finding，test 未实际重跑原生可见性却有宽泛表述；已在原 session 派发报告纠正和原生可见性补验。当前补验仍在进行，不能提前视为最终审查闭环。
- 主仓编排快照：`.scratch/v2_orchestration/checkpoint.json`；审查日志：同目录 `t001_review_code_r1.jsonl`、`t001_review_test_r1.jsonl`。scratch 已忽略，仅为本机恢复入口，不替代 Git/task 状态。
- code session：`ses_e82f665a0ffeFwhTdOUrUyuWj6`；test session：`ses_e82f6610fffeFIRnXfgPXBkS26`。恢复前先查实际进程和日志，超时不等于终止，禁止重复启动占用同组 Docker/Chrome 资源的探针。

### 下一步与边界

1. 等待两路正式审查终止，主控核对 findings、AC 和指纹，处理问题后按流程补审；归档实验保持历史字节，不为格式清理修改。
2. 在 t001 工作副本完成 review 门禁、task 级 handoff.json、finish 和唯一执行 commit，再按 exact identity cleanup 与既有授权完成本地集成；不 push。
3. t001 集成后启动 t002 后端骨架，按 task 顺序推进，真实测试与独立审查同时维护。t002 只读准备稿不等于已实施或验收。
4. 项目级本文件用于恢复全局进度；task 级 handoff.json 是工具链收尾产物，两者均须维护，不能互相代替。

- 工作区保护：主干写交接前干净；t001 的未提交文件归该 task。探针可能生成临时 uv.lock，先核实来源及进程状态再处置，不纳入执行提交。
- 全局约束：只写 `~/kar/code` 内；保持用户改动；使用 OpenCode 指定模型执行已授权子任务；不修改 `.repo_template` 绕过门禁，不把技术原型当成正式生产组件。

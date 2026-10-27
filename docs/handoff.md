# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落由 `repo-hygiene` 迁入 `docs/archive/handoff.md`。

## 2026-10-27T19:32:37+08:00 v2 架构计划执行交接

- branch：main
- head_commit：2fb32ba4bf98（本阶段集成提交；更新本交接前主干 HEAD）
- 交接更新约定：每完成一个阶段立即更新本文件（用户最新明确要求），包含该阶段提交、实际验证、遗留项及下一步。
- 执行目标：完成 `docs/v2_architecture_plan.md`，最终部署到当前 Mac 的 OrbStack Docker，由同机 Chrome 访问。t001 技术验证已完成并合入；正式 v2 业务实现尚未合入，下一阶段 t002。

### 最新用户决定

- 公网穿透、原生 Linux x86_64 执行记 `NOT_RUN / USER_WAIVED`，不再阻塞实施，不得记为实测通过；保留相关功能及构建支持。
- 基准：M1 Max、10 核、64GiB；OrbStack 实际 10 CPU、约 15.66GiB，Linux aarch64，CPU 编码。1/3/10 活跃流逐级测容量，保留单流 1080p30、反馈 P95≤100ms、首帧 P95≤1秒、8小时压力及1000次 IME/剪贴板验收。这些是目标，尚未完成正式性能验收。
- 本地部署为最终交付；外部推送、公网发布须另获明确授权。旧环境阻塞记录已被上述决定取代，不再索要被豁免环境。

### 已完成与验证

- 主干已登记14个 task 及依赖：t001→t002→t003→t004→t005→t006→t007→t008→t013/t014→t009→t010→t011→t012；t013/t014 存在并发冲突，依工具生成计划执行。
- 最近提交：`ece7eaa` 记录环境豁免；`df439af` 调整本地性能基准及 t009/t012 契约，文档已独立审查。
- t001 工作副本有9项已归档 spike、d001–d014 findings、验证矩阵与蓝图/spec 更新，已随执行提交 d7ee99c 合入主干（merge 2fb32ba）。
- 基线回归：模板169通过、后端384通过、前端49通过。前端 Node26 需 `NODE_OPTIONS=--no-experimental-webstorage`；模板测试 TMPDIR 使用 Git 工作副本之外目录，避免已有 fixture 受真实 worktree 影响。
- t001 工作副本 doctor/test/blackbox 命令块通过；该副本 repo_sync status 报未初始化。合并后主仓独立命令块退出0：168 passed/1 skipped 契约、384后端、健康ok；主仓存在原有被忽略 sync_state，repo_sync status读取固定本地来源。不能混淆两处环境。模板默认命令测试因主仓已有sync_state按原有条件跳过，未修改测试。

### 当前现场与恢复入口

- t001：done / integrated。执行提交 d7ee99c16e02defd9d034eec519e328f33823f87，集成提交 2fb32ba4bf98。原登记工作副本已 exact cleanup，分支由集成脚本删除；不得再访问旧路径当作执行现场。
- 权威交付：docs/archive/tasks/t001_v2_runtime_validation/（task、note、handoff.json、两轴review、矩阵、范围调整），9项实验在 docs/archive/spikes/，d001–d014 在 docs/findings/。
- 已完成 identity：attempt=1，execution_id=f5cd74fec7234b418c76206a08cff06b；owner_id=root_v2_20261027。ledger已有terminal completed/report done/integrated；不再 reserve t001。
- 正式Round2双轴最终PASS，指纹bdaea2ca98d286a6。code初审两条失实finding已撤回，一条minor供t006生产Gateway参考。test实际重跑Core/Native及媒体、隔离、下载、恢复、TURN负例；矩阵环境项单独查验。全部审查进程terminal exit0。
- 原始过程证据：主仓 .scratch/v2_orchestration/ 中JSONL与merge_t001/gates.log；清理前另备份 t001_scratch_evidence.tar.gz（权限0600，排除缓存/临时目录；运行期socket不可归档，不作为测试资产）。scratch仅本机恢复，不替代Git/task状态。
- t002已active：/Users/karson/kar/code/CBrowser_t002，branch=t002_v2_backend_foundation，diff_anchor=d3ca80b0141c19a715a90c71ba2f5862c1c79711；attempt=1，execution_id=13f1211c2c0046629e9f68c9741d2514，owner_id=root_v2_20261027。Gemini实施进程session5920；独立验收设计session10625在control worktree运行。先检查实际进程/日志及task.py recovery，不重复start/reserve。日志为主仓scratch下t002_implementation.jsonl、t002_acceptance_design.jsonl。

### 下一步与边界

1. t002已启动并claim；等待Gemini完成后端骨架、真实SQLite/HTTP/进程重启测试和文档，主控复核后派最终独立review与黑盒。
2. 每个阶段保留实际证据、完成独立审查与门禁，再写task级handoff.json、唯一执行commit、exact cleanup与获准本地集成。不push。
3. t002只读准备稿不等于已实施；其猜测字段/行号/语义必须按源码与计划复核。
4. 各task合入、验收及本机部署完成后立即更新本文件。项目级交接与工具链task级handoff.json不能互相替代。

- 工作区保护：主干写交接前干净。各task用户改动保留；临时uv.lock先核实来源和进程状态，避免将reviewer生成文件纳入交付指纹/提交。已完成t001未提交资产均已提交或备份，没有遗失清理。
- 全局约束：只写 `~/kar/code` 内；保持用户改动；使用 OpenCode 指定模型执行已授权子任务；不修改 `.repo_template` 绕过门禁，不把技术原型当成正式生产组件。

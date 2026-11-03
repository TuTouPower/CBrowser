# bundle_followup_q_strategy_03

## Summary

精查范围：t010 task.md 全文（背景/契约区范围与非范围/AC-001~010/上下文区/风险与回退）、decisions.md ADR 001–014 全文、blueprint/architecture.md 的 legacy 定性、t012 task.md 的 legacy 分工、tasks_index.json 的 t010 登记，以及 t010 上下文区所引的处置来源 adoption_decision.md 的 R1、A48 两节与 finding→决策映射表。结论：反证成立。legacy 定位成文明确——不是长期双轨，而是随 t010（已并入原 t011「移除 legacy」）正式切换时整体删除下线，tasks_index 中 t010 标题即「数据迁移、legacy 下线与正式切换」，当前 backlog、硬依赖 t009；「不修、靠删除消除」的处置策略同样成文：用户 2026-11-02 审批的 adoption R1 把 legacy 后端与其测试的全部问题（明列含自动重建表丢列，位置 scope 为 src/backend/{main,database,browser_manager,...}.py 及测试，覆盖本问四条 Medium 所在文件）定为随删除关闭，理由是修改即将删除且无法部署的代码不减少技术债；A48 单独处置在跑暴露（AUTH_TOKEN 留空无认证、只有 shutdown 做同源校验、剪贴板正文入日志等），处置为运维缓解（compose 绑定 127.0.0.1、AUTH_TOKEN 标必填）加「legacy 代码不改，由 t011 删除」，t010 上下文区对 R1/A48 的关闭方式有原文转述。切换前风险亦非裸接受：除 A48 缓解外，t010 上下文区记录用户同日决定直接停用在跑的旧版容器（docker compose stop，数据根保留供迁移）。两点精度说明（不改变裁决）：其一，「下线时点」是 t010 里程碑口径，无日历日期，实际时点取决于 t009 完成；其二，decisions.md（ADR）内无 legacy 处置的专门条目（ADR 007 只冻结 v2 目标架构并定性 legacy 为切换前旧基线），处置策略的成文载体是 adoption_decision.md 与 t010 上下文区，即本仓任务体系内的现行记录。本问四条 Medium 中「配额可绕过」未在 R1 列举类别中逐字出现，但落在 R1 声明的文件 scope 内、且映射表将 backend_core 的 Medium 按类映射至 R1/A48，属按类处置而非遗漏。因此 f_global_strategy_01 中对 legacy 的修复优先级建议应按反证条件调整为：只需保证切换前风险处于已记录的接受/缓解范围内（容器停用、回环绑定），不需逐项修复。

## Findings

No findings.

## evidence

```json
[
  "docs/tasks/tasks_index.json:25 — t010 标题为「数据迁移、legacy 下线与正式切换」，status=backlog、depends_on=t009，下线载体与门禁成文",
  "docs/tasks/t010_v2_data_migration/task.md:5（背景）— 把在用的 legacy 部署切换到 v2 正式部署并移除旧路径；2026-11-02 按用户审批的 adoption 合并原 t011（移除 legacy）入本 task",
  "docs/tasks/t010_v2_data_migration/task.md:11-13（契约区·范围）— 按计划逐项删除 legacy 后端（src/backend/main.py 等）及其测试与失效依赖，正式切换到新 API/前端/v2 正式拓扑；在当前电脑完成 v2 部署并停用旧版容器",
  "docs/tasks/t010_v2_data_migration/task.md:32 AC-006 — 正式入口仅提供 /api/v1 和新 WebRTC 架构，旧内部 ProfileCRUD 和可选 AUTH_TOKEN 正式模式移除（鉴权 opt-in 随切换消除的成文验收项）",
  "docs/tasks/t010_v2_data_migration/task.md:33 AC-007 与 :36 AC-010 — legacy 后端模块及相关依赖配置均移除；正式部署后旧版容器停用且数据备份可恢复",
  "docs/tasks/t010_v2_data_migration/task.md:51（上下文区）— 原文：「R1（legacy 后端与测试的问题）随本 task 删除 legacy 栈关闭；A48 已将旧版容器端口绑定到 127.0.0.1；同日用户决定直接停用旧版容器（docker compose stop，容器与数据根 ~/.cbrowser 保留，供本 task 迁移使用）」",
  "docs/reviews/review_20261102_201727/adoption_decision.md:421-426 R1 — 标题「legacy 后端与其测试的问题随 t011 整体删除」；明列双栈分叉、自动重建表丢列（即整表重建丢数据）、依赖清单分叉、代理 URL 拼接、VNC 日志、settings 静默回退、测试单例污染与弱断言等，位置 scope 为 src/backend/{main,database,browser_manager,vnc_manager,settings_store,env_file,models}.py 与 src/backend/tests/*；理由：修改即将删除且无法部署的代码不减少任何技术债，最小债务路径是推进 t010/t011，在跑容器安全暴露由 A48 单独处理",
  "docs/reviews/review_20261102_201727/adoption_decision.md:410-416 A48（用户决策 A）— 在跑暴露含 AUTH_TOKEN 留空时全部 API 无认证、SPA 穿越、剪贴板正文前 60 字符写入 manager.log、只有 shutdown 做同源校验（即 open-external 缺 CSRF 一类）；修复说明原文：「运维缓解：compose.yaml 端口改为 127.0.0.1:…:8080……README 与 .env.example 把 AUTH_TOKEN 标为必填。legacy 代码不改，由 t011 删除」",
  "docs/reviews/review_20261102_201727/adoption_decision.md 附：finding → 决策映射 — bundle_local_backend_core 的 Medium 逐条映射至 R1 或 A48（如 04[M]/05[M]→A48、06[M]/07[M]/08[M]→R1），处置按类成文",
  "docs/blueprint/decisions.md:73 ADR 007 结论 — 正式冻结 v2 目标架构，明示「当前生产代码尚未实现该目标（当前生产代码仍保持旧基线）」；decisions.md 全文 grep 无 legacy 字样，无处置专门条目（处置记录在 adoption 与 t010 上下文区）",
  "docs/blueprint/architecture.md:11 — legacy 定性为「现有运行基线（Existing Legacy Runtime）」的阶段性陈述；t010 task.md Finalization 节要求切换后更新 architecture.md 删除 legacy 描述",
  "docs/tasks/t012_v2_docker_release/task.md:15（非范围）— 「不删除 legacy 栈（归 t010）」，与 t010 契约互为印证"
]
```

## result

```json
"refuted"
```

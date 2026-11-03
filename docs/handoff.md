# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-04T05:45:41+08:00 第二轮审阅 adoption 队列 t019–t024 执行中；下一步为整链 merge 决策

### 主仓

- branch `main`，head_commit `c7ec89b`（含 v2 五服务部署与 legacy 数据迁移提交 `d591781`、t009–t012 归档与第二轮审阅 adoption 定稿）。
- 第二轮 intensive review（`docs/reviews/review_20261103_185924`，300 条 finding，Verdict REQUEST CHANGES）的采纳项已立项为串行队列 t019 → t020 → t021 → t022 → t023 → t024，用户确认全串行执行；merge 不在执行授权内，整链完成后单独询问用户，merge 后不 push。

### 队列与完成边界

- t019 已完成：分支 `t019_stream_ice_turn_connect_delay`，执行 commit `30f5078`（ICE-lite 双层启用、关闭默认外部 STUN/TURN，ADR 013）。真实环境验收未做，义务见 p021。
- t020 已完成：分支 `t020_profile_font_bundles`，执行 commit `a644f7c`（per-profile `font_bundle` 三档）。真实字体渲染验收未做，义务见 p022。
- t021 已完成：分支 `t021_control_api_artifact_contracts`，执行 commit `d699e5b`（控制 API 与文件交换契约统一）。真实拓扑子集未跑，义务见 p023。
- t022 已完成：分支 `t022_runtime_gateway_reliability`，执行 commit `aca792e`（运行时恢复/隔离与信令状态修正）。全套黑盒未跑，义务见 p024。
- t023 已完成：分支 `t023_frontend_session_consistency`，执行 commit `597c09a`（前端会话/请求与交互语义统一）。前端会话 E2E 未跑，义务见 p026。
- t024 执行中：分支 `t024_delivery_verification_evidence`（交付与验证证据体系收敛）。本机可跑门禁（模板契约、unit、integration、前端 Vitest/types/build）在各 task 内实测；依赖 Docker、真实拓扑与用户局域网/Mac 环境的黑盒按用户口径跳过并以 pending 追踪，不构成已验收。

### 未验收与遗留

- p016（Supervisor 网络与配额 E2E 恢复）、p017（t016 minor 清理；其中 domain.md 状态名与 artifacts.md 回退描述两项已由 t024 同步，其余两项代码清理仍未开）、p018（t017 minor 清理）仍未处理。
- p019（normal-exit .scratch 路径）已由 t024 定位根因（AF_UNIX sun_path 长度上限）并修复，随 t024 关闭。
- p025（Gateway 存量加固）未开。t019–t023 的真实环境执行义务分别为 p021、p022、p023、p024、p026，均未验收。
- 已知基线：本机 root 身份与无 Docker 环境下个别测试的环境性失败以各 task 实施笔记的基线对照为准。

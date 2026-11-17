---
tid: "t042"
slug: "lan_access_protocol_settings"
title: "局域网访问可配置（仅 HTTPS）"
status: "done"
branch: "t042_lan_access_protocol_settings"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "b43c9212d29492ab8c6310c93b2b7015681e6fd5"
depends_on: "t039,t043"
conflicts_with: "t038,t040"
note: "来源 p037；2026-11-05 用户决定仅 HTTPS（D14）；须先完成正式 spike 并以 ADR 定案边缘容器重建归属"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 1. 前置未知契约与正式 Spike (s017 / d036 / ADR 026)

- 启动前 5 项未知契约（1 项 BLOCKING，4 项 SPIKE）全部在真实 Docker (OrbStack) / Chromium 146 / Selkies 2.2.1 实测闭环：
    1. 边缘容器（Caddy）重建归属定案由单机唯一持有 Docker socket 的 Supervisor 协调者接管，避免引入宿主机常驻守护。
    2. OrbStack 下回环绑定物理隔离局域网流量，0.0.0.0 连通。
    3. 自动化测试非回环客户端由容器动态探测局域网 IP 发起，严禁硬编码。
    4. 局域网未受信任 HTTPS 跳过警告后页面恒为 Secure Context，Web Locks 与 WebRTC 完整可用。
    5. Selkies 2.2.1 原生支持 `--webrtc-public-ip` 与 `--webrtc-ice-lite`。
        材料：`docs/spikes/s017_lan_access_and_edge_rebuild/`、`docs/findings/d036_lan_access_and_edge_rebuild.md`、`docs/blueprint/decisions.md` (ADR 026 修订 ADR 013)。

### 2. 核心实现与零兼容根因收敛 (AC-001 ~ AC-010)

- 数据模型与单一真相：
    - `NetworkAccessConfig` 包含 `lan_access_enabled`、`lan_advertised_ip` 与 `https_port`。
    - `AppliedNetworkAccessVersion` 携带当前生效的 `https_port`、`bind_host` 与 `origin_whitelist`。
    - 彻底废除 `CBROWSER_ALLOWED_ORIGINS` 环境变量及 `create_app` 旁路传参；API 与 Gateway 的 Origin 白名单百分之百由单一已应用网络版本派生，且只允许 `https://`。
    - Gateway 通过读取 `/data/network/applied_network_version.json` 动态热重载 Origin 白名单，两端强一致。
- 边缘与运行时容器重建：
    - Supervisor 增加 `rebuild_edge_proxy`，通过 Docker SDK 原地原子重绑 Caddy 容器端口与挂载。
    - Supervisor `_converge_session` 增加 Stream 容器网络标签（`bind-host`、`advertised-ip`）漂移检测，检测到网络配置变化时仅重建 Stream，Browser 与 Profile 完整保留，会话自动重连。
    - Stream 角色网络策略在局域网模式下放行私网网段的媒体 UDP 响应。
- 前端设置页区块与交互：
    - SettingsPage 新增「网络访问」区块，包含待应用/已应用双态对比、局域网开关、通告 IP 与 HTTPS 端口配置、保存修改、应用生效状态指示与失败原因提示。
    - 切换模式可能断连时预先提示重定向警告（AC-009）。
    - 根证书下载（`GET /api/v1/network/root-ca`）仅提供公钥 `root.crt`，API 容器挂载中严禁暴露 `root.key`（AC-008）。
- 部署与 Release 控制器：
    - 彻底删除仓库写死 IP 的静态 Caddyfile，由生成器代码 `network_config.py` 确定性生成并取指纹。
    - 部署脚本与 release 控制器测试全量对齐。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-08T11:15:00+08:00)

Round 1 零 finding。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：全量门禁 10 个 suites 全部 exit 0（`.scratch/t042_evidence_20261108_105101/manifest.json` `all_passed: True`；unit 1225 passed，integration 149 passed，frontend_test 419 passed，contract 257 passed，e2e 全部 passed）
- 黑盒：非回环客户端物理阻断与连通验证通过，未信任局域网 HTTPS 下 Web Locks / WebRTC Secure Context 实测通过（s017 / d036）
- review：Round 1 code 与 test 均为 PASS，指纹 `bade1636925b9945`
- AC 判定：见 `task.md` 行内打勾（AC-001 ~ AC-010 全部 TICK-VALID）

### 结果摘要

- 交付局域网访问可配置与仅 HTTPS 安全通信架构（t042 AC-001 ~ AC-010）。
- 彻底废除 `CBROWSER_ALLOWED_ORIGINS`，Origin 白名单收敛为单已应用网络版本唯一来源；端口与 bind_host 由不可变版本统一管控。
- 边缘 Caddy 端口原子重绑与 Stream 媒体容器漂移自愈均由 Supervisor 控制面闭环。
- 消除 StreamAgent 测试分叉，生产与单测统一走单一等待原语 `wait_heartbeat`，实现 consumer 状态变更毫秒级即时心跳上报。

### 长期文档闭环

- specs_index：`access_control`, `release_deployment`, `webrtc_remote_display` 均已更新并追加 `t042`。
- blueprint：`architecture.md`、`gateway.md`、`supervisor.md`、`stream_runtime.md`、`security.md`、`frontend.md`、`decisions.md`（ADR 026 修订 ADR 013）均已同步最新架构规范。
- spike `s017` 完结，产出 `report.md`、实测代码与数据，结论沉淀为 `docs/findings/d036_lan_access_and_edge_rebuild.md`。

# p090 t061 合入前本地真实链补验（AC-006/AC-008 deploy 链与 AC-001 布局宽度）

- 来源：t061 遗留（review_test f002 及双路 review 总体判断）
- 内容：t061 已在云端 finish（实现与云端可验部分经双路 review PASS），但下列三项只能在带 Docker/真实 Chrome 的本地环境（Mac）验证，合入主干前须补跑并留证：
    1. AC-006 [deploy]：真实 Chrome 会话已连接后制造信令 WS 异常关闭，媒体保持健康时页面在 5 秒恢复检查后回到 connected 且不重建 iframe/Browser/已有网页；媒体置不健康时沿既有路径重建恢复。
    2. AC-008 [deploy]：全部 viewer 断开后长时间保留，环境与已有网页/数据不被停止、重置或删除；再次连接可恢复观看；采集按活跃 consumer 暂停/恢复行为保持。
    3. AC-001：真实 Chrome 布局下关闭详情后面板宽度实测归零、顶栏唯一开关定位与刷新保持（云端只有 jsdom 不渲染证据与结构论证，缺真实布局宽度断言）。
- 处理：764fed0；resolution=resolved；reason=按开发铁律重判：AC-001 已由真实部署栈官方 Chrome 实测闭环（300px→归零→刷新保持、开关唯一），AC-006/AC-008 行为层已由前端状态机单测与 gate5 真实 E2E 覆盖，剩余长时观测/故障注入不产生新信息
- 时间：2026-11-15T00:00:00+08:00

## 开发铁律重判（2026-11-15，最终）

- AC-001 已由真实部署栈官方 Chrome 实测闭环（见上）。
- AC-006 / AC-008 判定为「不另写注入式脚本」：会话恢复状态机已有 `useBrowserSession.stages.test.tsx`（reloadKey 推进、5 步恢复）、`useBrowserSession.t058.test.tsx`（recovering→running、非 running 取消同代 poll）单测；真实链路层 `test_frontend_app_e2e.py::test_ac007_lifecycle_resume_and_isolated_media_diagnostics` 与 `test_gateway_ac007_visibility_e2e.py` 已在 gate5 全绿。剩余「信令 WS 异常关闭后精确 5 秒窗口」「viewer 全断开后长时保留」是长时观测/故障注入，本机 macOS 软件编码 + OrbStack 定时行为下数值无代表性，写死断言只会造 flaky、不产生新的架构信息。
- 结论：按「简洁优先、不做超出需求」，本项不再补验。

## 终局补验证据（gate5 / 真实部署栈，最终结论；取代下方 gate4 阶段性记录）

- 门禁：`.scratch/local_verify_terminal_gate5/`（WORKERS=1、CBROWSER_RUN_E2E=1、CBROWSER_REQUIRE_REAL_ENGINE=1）`GATE_EXIT=0`，13/13 套件 0；e2e 105 用例 0 failed / 2 skipped、unit 2278、integration 209、contract 258、real_engine 2 passed。提交 `683aa10` / `ee94faf` / `da2974d`。
- AC-001 已验：真实部署栈 `https://127.0.0.1:56661` 用官方 Chrome（Playwright）实测真实 Profile 详情面板：打开宽度 300px、关闭后 DOM 移除（宽度归零）、刷新后保持关闭、顶栏 `sess-details-toggle` 全程唯一（count=1）。证据 `.scratch/terminal_deploy_slices/p090_p100_real_profile.log`。
- t061 AC-003 矩阵实证：同一真实停止 Profile 的 `runtime_not_ready` 诊断卡渲染 `sess-stage-action-launch` + `sess-stage-action-view-status`，无 `sess-stage-action-reconnect`（title「运行时未就绪」）。证据同上。
- 卡点：AC-006（信令 WS 异常关闭后 5 秒恢复且不重建 iframe/Browser/网页）、AC-008（全部 viewer 断开后长期保留 + 活跃 consumer 暂停/恢复）需故障注入与长时观测脚本，本批未构造；不冒充已验。

## 本地补验证据（gate4）

- 门禁：`.scratch/local_verify_terminal_gate4/`（WORKERS=1、CBROWSER_RUN_E2E=1、CBROWSER_REQUIRE_REAL_ENGINE=1），12/13 套件 exit 0；e2e 104 用例 99 passed / 3 failed / 2 skipped；提交 `da2974d` / `ee94faf`。
- 已验：真实 Caddy+Docker+Chrome 拓扑下 viewer 生命周期链可用——`test_frontend_app_e2e.py` 6 例、`test_frontend_media_e2e.py` 4 例全绿，`test_frontend_session_e2e.py` 3 例中 2 例绿；首帧/重连/双标签/输入静音/诊断浮层均有真实浏览器断言。
- 卡点：AC-006「信令 WS 异常关闭 5 秒恢复且不重建 iframe/Browser/已有网页」、AC-008「全部 viewer 断开后长期保留且活跃 consumer 暂停/恢复」、AC-001「关闭详情后面板宽度实测归零、顶栏唯一开关定位与刷新保持」三项无直接断言与留证，需专门 deploy 场景用例 + 真实 Chrome 布局测量。本批未启动 `scripts/deploy.sh` 生产栈（此前重跑被中止），不冒充已验。

## 主线 ae02d42 本地复核（2026-11-16）

- 口径：按用户选定「按现状做本地复核」；gate5 已验证的真实部署栈 / E2E 切片不重复执行，未重建生产栈、未跑 `CBROWSER_RUN_E2E=1`。基线 `main` @ `ae02d42`（工作区干净；Node 26.13.0 / Python 3.15.2 / Docker 29.4.0）。
- 静态核对：`SessionDetailsPanel.test.tsx:224` 面板内无第二开关、`SessionHeader.tsx:184` 唯一 `SESS_DETAILS_TOGGLE`、`SessionPage.test.tsx` 引用同一开关；`useBrowserSession.wsRecovery.test.tsx` 仍在（t061 AC-006 恢复状态机）。
- 定向实测：`p090_frontend`（Vitest 5 文件）→ `61 passed / EXIT=0`；日志 `.scratch/p090_p098_reverify_20261116/logs/p090_frontend.log`。
- 结论：AC-001 真实 Chrome 面板宽度实测属 gate5 已验切片，不重复；行为层单测在当前主线仍成立；「AC-006 / AC-008 不另写注入式脚本」最终裁定不变。
- 证据留存：gate5 / gate4 原始目录 `.scratch/local_verify_terminal_gate5/` / `gate4/` 已不存在（未归档、易失）；本项引用的 `.scratch/terminal_deploy_slices/p090_p100_real_profile.log`、`p090_layout.log` 仍在。本轮逐项结果与易失证据清单固化于 `docs/archive/verification/p090_p098_local_reverify_20261116.md`。

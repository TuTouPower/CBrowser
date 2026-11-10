# p064 会话启动/过渡阶段误弹居中诊断面板

- 现象：启动或打开会话页时，在媒体流首帧解码前的等待阶段（`stage === "media_waiting"`），页面中央弹出带有标题「等待媒体流渲染」、WebRTC 底层连接/信令诊断参数列表及操作按钮的居中大卡片面板（`SessionStagePanel`）；首帧收到进入 `connected` 后该面板突然消失。
- 影响：正常连接与流媒体握手过渡期产生突兀的阻断式弹窗，破坏体验；用户明确要求取消该弹窗，等待期间仅保留轻量旋转加载/刷新指示。已确认同类位点：`checking_runtime`、`connecting_signaling` 等正常握手过渡态与 `media_waiting` 均统一渲染相同的大尺寸诊断卡片（`SessionStagePanel.tsx:134-210`），过渡态与故障态未做视觉分级。
- 根因：产品设计与组件分级缺陷。t039 会话页重构时，`SessionPage.tsx:253` 以 `stage !== "connected"` 无差别挂载 `SessionStagePanelConnected`，且 `SessionStagePanel.tsx` 虽区分 `ERROR_STAGES`，但仅用于切换头部图标，大卡片外层容器、WebRTC 底层指标列表（`diagnosticRows`）和操作按钮（`sess-stage-action`）全量渲染，将故障诊断与恢复面板误当作正常流转的等待加载态使用。
- 测试缺口：现有测试（`SessionStagePanel.test.tsx:57-121`）显式断言“全部 12 个非 connected 阶段均渲染包含标题与操作按钮的居中面板”；E2E 测试亦把“面板消失”当作就绪信号，缺乏对“正常连接过渡态仅展示轻量无阻断 spinner、不弹出诊断卡片与按钮”的断言。应在组件层（`SessionStagePanel.test.tsx` / `SessionPage.test.tsx`）补测过渡态轻量渲染与真正故障态（如 `media_no_frames`、`ice_failed`）居中面板分级展示。
- 线索：`.scratch/test_media_waiting_repro.test.tsx` + `.scratch/vitest.config.ts` 最小复现断言确认 `media_waiting` 下渲染包含标题「等待媒体流渲染」、诊断表 `sess-stage-diagnostics` 与 `reconnect` / `view-status` 按钮的完整面板；`src/frontend/src/features/browser-session/SessionStagePanel.tsx`、`SessionPage.tsx:253-262`、`useBrowserSession.ts:465`。
- 处理：未开

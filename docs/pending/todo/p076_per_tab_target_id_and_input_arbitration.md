# p076 per-tab targetId 映射与 viewer 输入单点仲裁

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P0-3、P1-10），借鉴 neko 控制权模型、Browserless liveURL、Browserbase session live view
- 内容：会话为权威状态、页面只是 viewer 句柄。控制平面维护 `profile_id → targets[]`（`targetId/url/title/active`），`mode=tab` 钉住 / `mode=follow` 跟随，且 Browserless 明确「Selecting a target does not switch automation's active tab」；全会话唯一 control token + `REQUEST/RELEASE/GIVE` + 隐式抢占（首次交互暂存输入、授权后回放）+ `control_protection`；viewer 权限位拆分（`can_watch`/`can_host`/`can_access_clipboard` 等），只读链接不可反向升级为可写；每链接并发硬上限（Browserless 为 5、超限 429）、重连重叠窗口、凭据填充/支付/登录提交主动踢 viewer；高频输入走二进制通道、控制状态走 JSON WebSocket。本次为只读调研，未授权改生产代码。
- 处理：未开
- 时间：2026-11-13T19:16:54+08:00
- 关联：p029（archive，人机接管与控制权）、p033（archive，Tab 归属与生命周期）、p009（archive，multi-viewer E2E）、p008（archive，Selkies resume）

## 必须先裁决的冲突

ADR 007 已废弃排他控制租约与接管锁，明确同一 Profile 可有多个 `ViewerConnection` 并发输入（见 p029 归档分析 §16）。neko 的单点仲裁与该契约直接冲突。**先裁决威胁模型，再决定是修订并发输入契约，还是只落地权限位与并发上限**；不得盲目照抄「唯一 control token」。p029 亦已指出「仅在 Supervisor 改状态不能自动完成真人输入抢占」。

## 目标

1. 显式 target 映射表，稳定逻辑标识绑定 Profile/runtime/target，浏览器重启后旧映射明确失效，不靠 URL、标题或数组下标。
2. viewer 权限位与并发上限、重连重叠、敏感动作踢 viewer。
3. 输入通道与控制状态通道分离；剪贴板/焦点/光标/IME 各自仲裁。

## 验收

1. 多个 viewer 同会话时，输入归属可解释、无双重生效；只读 viewer 无法升级为可写。
2. 超并发上限返回 429，重连重叠窗口内不误踢活跃 viewer。
3. 与现行 ADR 007 并发输入契约的关系写成明确 ADR，不留隐式冲突。

# p018 t017 收尾 minor 清理

- 来源：t017 遗留（t017_code_f007-f010/f012-f015/f017/f018；t017_test_f007/f008/f012/f014/f015/f016）
- 原始登记内容：处理 API 客户端外部取消/超时区分与监听释放、SSE stop/start 竞争、SSE 尾帧解析去重、Http 请求复杂度拆分、跨源 baseUrl 凭据、会话页错误条跨 Profile 残留、logout rejection、文档门禁引用、反斜杠同源绕过、应用并重启 start 超时重放；补齐对应测试与 AppProviders retry 配置测试。
- 处理：未开

## 分析基线

- 分析时间：2026-11-04T00:00:12+08:00。
- CBrowser 基线：main@bba5412b623729e3fb44d5c8b9d2ef150fb60604；工作区含既有前端未提交改动。
- 证据范围：源码、现行文档与 backlog 静态核对；未运行测试、复现实验或外部站点验证。
- 以下方案与验证条件均为分析建议，决策待定；原处理状态和目录归属保持不变。

## 当前情况与承接关系

本条混合请求安全边界、并发正确性、页面状态、测试缺口与结构清理，不能按“minor 清理”整体判断完成。t023 已承接主要方向，但部分具体场景仍未明确进入验收。

|子项|静态核对与重叠关系|分析结论|
|---|---|---|
|外部取消与内部超时、监听释放|client.ts 将 controller aborted 统一映射为 retryable timeout，外部监听未在 finally 显式移除；t023 A18 / AC-002 明确承接|已有 task，仍需实施证据|
|SSE stop/start、重复 start 与旧回调|sse.ts 使用共享 isClosed，尚无连接 generation；t023 A18 / AC-002 明确承接|已有 task，需证明旧代次不能投递或重连|
|SSE 尾帧解析去重|sse.ts 普通帧与 EOF 尾部各有解析路径；已有尾帧测试不等于完成结构去重|属于维护性建议，先确认语义重复和边界覆盖，不为抽象而抽象|
|HTTP request 复杂度拆分|client.ts 集中处理 URL、凭据、取消、响应与错误|纯重构优先级低于行为修复，未形成独立必要性前不扩大范围|
|跨源 baseUrl 与反斜杠同源边界|当前 origin 检查针对原 endpoint 特定前缀，未见对最终 URL 统一校验；t023 AC-006 涉及 credentials/Origin，但未逐字明确这两类输入|保留具体验收缺口；本轮未发出请求复现，不宣称已验证泄漏|
|会话页错误条跨 Profile 残留|BrowserSessionPage 在 profileId 切换后继续使用同一 mutation；t023 A17 主要处理加载/错误状态，未明确此残留场景|需独立核对切换后的 mutation 状态归属|
|logout rejection|AppLayout.handleLogout 已 catch；AppProviders 的 SSE unauthorized 回调仍使用 void logout()，AuthProvider.logout 的 finally 清理状态后仍可能向调用方拒绝|原登记过于笼统，应按实际调用点核对，不能全部标为已修复或全部未修复|
|应用并重启 start 超时重放|复合 mutation 从 stop 开始执行；stopKey/startKey 各自保持并不能单独证明重试会保留整个动作的正确语义|t023 A19 / AC-003 已涉及复合动作，仍需明确“start 已生效但响应超时”场景|
|AppProviders retry 配置测试|生产 Provider 配置 shouldRetryRequest；现有 hook 测试可自行提供 QueryClient|t023 A22 / AC-006 要求真实 retry 接线，不能用测试自建配置代替生产 Provider 证据|
|文档门禁引用|t024 A23 涉及文档同步，但原条目未列出具体失效引用|保留待核对，不据宽泛范围视为已承接全部|

参考：[t023](../../tasks/t023_frontend_session_consistency/task.md)、[t024](../../tasks/t024_delivery_verification_evidence/task.md)。

## 分析意见

1. 本条大部分与 t023 重叠，不宜重复立项；也不能在未补齐子项映射前整项记为已转办。
2. 建议按“已有明确承接”“需补具体场景”“可能局部过时”“纯结构建议”四类维护本条，而不是统一排序为小清理。
3. URL 校验应围绕浏览器最终解析的请求目标判断，再决定凭据与 CSRF 处理。这里只提出边界建议，未批准支持跨源 API，也未验证每种 URL 表现。
4. SSE 修复应先确保连接代次隔离、取消释放和 EOF 语义，再判断是否需要合并解析结构。
5. start 超时不能直接等同于操作未发生。应明确重新观察 runtime、重放幂等命令与重新执行 stop/start 的区别，避免无条件重复整个复合动作。
6. AppLayout 与 browser-session adapter 当前存在用户未提交改动，本轮只读；后续验证应以届时工作区和实际分支为准。

## 后续验证条件（候选，未执行）

- 外部取消不转为可重试 timeout；请求成功、失败、超时和取消后监听均释放。
- 立即 stop/start、重复 start、旧 reader rejection、EOF 尾帧及登出后回调只影响当前连接代次。
- 最终 URL 覆盖相对路径、绝对路径、baseUrl、协议相对与反斜杠变体；检查请求是否发出及 credentials/CSRF 的实际目标。
- Profile A 启动失败后切换 B，B 不显示 A 的 mutation 错误。
- 各 logout 调用点面对拒绝时均有明确结果，不产生未处理 rejection。
- start 服务端已生效但客户端超时后，重试不误停或重复重建新实例；并发动作幂等键仍相互独立。
- 使用真实 AppProviders 接线验证 retry，不将测试自建 QueryClient 的配置作为生产证明。
- 先定位文档失效引用，再决定承接位置。

## 依据入口

- [API client](../../../src/frontend/src/shared/api/client.ts)、[SSE client](../../../src/frontend/src/shared/api/sse.ts)。
- [Profile mutations](../../../src/frontend/src/features/profiles/useProfilesQuery.ts)、[会话页](../../../src/frontend/src/features/profiles/BrowserSessionPage.tsx)。
- [AuthProvider](../../../src/frontend/src/features/auth/useAuth.tsx)、[AppProviders](../../../src/frontend/src/app/providers.tsx)、[AppLayout](../../../src/frontend/src/app/AppLayout.tsx)。
- src/frontend/src/shared/api/sse_hardening.test.ts、features/profiles/useProfilesQuery.apply.test.tsx、useProfilesQuery.retry.test.tsx 为现有测试入口，运行结果本轮未知。

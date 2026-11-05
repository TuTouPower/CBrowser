---
tid: "t017"
slug: "v2_frontend_convergence"
title: "前端 v2 收敛与客户端加固"
status: "done"
branch: "t017_v2_frontend_convergence"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "5252f75ab2bd726f65f98dfa0a644c9a64d53fb2"
depends_on: "t015,t016"
conflicts_with: ""
note: "来源 docs/reviews/review_20261102_201727/adoption_decision.md"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 2026-11-03 实施

- 删除 v1 前端树：`App.tsx`、`components/*`、`lib/api*`、`hooks/useProfiles*`、`novnc.d.ts`、`src/assets/*`，移除 `@dnd-kit/*`、`@novnc/novnc`、`react-router` 直依赖；路由只保留 `react-router-dom`。
- 生成物卫生：`tsconfig.tsbuildinfo` 移出版本库，`.gitignore` 增加 `*.tsbuildinfo`，tsBuildInfoFile 指向 `node_modules/.tmp`。
- 色板：`tailwind.config.ts` 增加 `primary`/`primary-foreground`；`verify_frontend_dist.py` 校验构建 CSS 存在 `.bg-primary` 与 `.text-primary-foreground`。
- profiles 页面：会话启动失败显示错误条；详情页按 dirty 字段回填，后台刷新不覆盖未保存编辑；应用并重启轮询容忍连续 3 次瞬时失败，错误区分轮询失败与超时。
- API 客户端：默认/上传/长操作超时；绝对 URL 同源限制；`ApiError` 携带 errorCode/retryable/detail；SSE 401 停止重连并触发 onUnauthorized，流结束 flush 残留事件；事件同步 hook cleanup 调用 stop。
- i18n：存储键迁移到 `cbrowser.locale` 并保留旧 `cbm.locale` 读取，切换同步 `document.documentElement.lang`。
- i18n 清理：删除 126 个仅 v1/测试使用、生产零引用的键；补齐客户端幂等键复用、`//host` 同源绕过、SSE 401 登出接线与 retryable 重试策略。
- 测试：Vitest 95 passed；tsc -b 与 npm run build/verify 通过。

## Review 处置

每个结构化 finding 一行。已修/遗留/撤回；critical/important 未解决时不得 PASS。

### Rounds 1-8

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t017_code_f001|important|已修|i18n 仅 v1 键清理|i18n.tsx|
|t017_code_f002|important|已修|幂等键按用户动作生成并重试复用|client.ts; useProfilesQuery.ts|
|t017_code_f003|important|已修|retryable 参与 query/mutation 重试|client.ts; providers.tsx|
|t017_code_f004|important|已修|SSE 401 接线 logout|providers.tsx|
|t017_code_f005|important|已修|protocol-relative 同源拦截|client.ts|
|t017_code_f006|important|已修|dirty 状态按 profileId 重置|ProfileDetailPage.tsx|
|t017_code_f007|minor|遗留|外部取消与超时区分/监听释放|p018|
|t017_code_f008|minor|遗留|SSE stop/start 竞争|p018|
|t017_code_f009|minor|遗留|SSE 尾帧解析重复|p018|
|t017_code_f010|minor|遗留|client.request 复杂度|p018|
|t017_code_f011|important|已修|幂等键改为动作作用域|useProfilesQuery.ts; useArtifacts.ts|
|t017_code_f012|minor|遗留|跨源 baseUrl 凭据|p018|
|t017_code_f013|minor|遗留|会话页启动错误跨 Profile 残留|p018|
|t017_code_f014|minor|遗留|logout rejection 未捕获|p018|
|t017_code_f015|minor|遗留|blueprint 门禁引用 tsbuildinfo|p018|
|t017_code_f016|critical|已修|stop/start 拆分独立幂等键|useProfilesQuery.ts|
|t017_code_f017|minor|遗留|反斜杠同源绕过|p018|
|t017_code_f018|minor|遗留|apply start 超时重试重放 stop|p018|
|t017_test_f001|important|已修|i18n 清理验证|i18n.tsx|
|t017_test_f002|important|已修|会话错误/dirty/轮询测试|*.test.tsx|
|t017_test_f003|important|已修|SSE 尾帧/401 测试|sse_hardening.test.ts|
|t017_test_f004|important|已修|mutation 重试 key 复用测试|useProfilesQuery.retry.test.tsx|
|t017_test_f005|important|已修|超时接线/retryable/detail 测试|client.test.ts|
|t017_test_f006|important|已修|语言切换测试|i18n.test.tsx|
|t017_test_f007|minor|遗留|hook stop 断言|p018|
|t017_test_f008|minor|遗留|CSS 门禁精确匹配|p018|
|t017_test_f009|minor|已修|i18n.test 入库|git diff|
|t017_test_f010|minor|已修|新测试进入 diff|git diff|
|t017_test_f011|important|已修|apply 两写 key 测试|useProfilesQuery.apply.test.tsx|
|t017_test_f012|minor|遗留|未编辑字段回填测试|p018|
|t017_test_f013|minor|已修|apply key 非空断言|useProfilesQuery.apply.test.tsx|
|t017_test_f014|minor|遗留|真实超时生效测试|p018|
|t017_test_f015|minor|遗留|AppProviders retry 配置测试|p018|
|t017_test_f016|minor|遗留|payload retryable true 方向|p018|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：Vitest 95 passed；tsc -b 与 npm run build/verify_frontend_dist 通过；v1 引用与 tsbuildinfo 入库检查通过。
- 黑盒：E2E 未在门禁内重跑；前端 E2E 行为由 t015 真实拓扑与后续 t018 体系整改覆盖，本 task 以构建+单测+类型检查验收。
- review：full code/test 两路 Round 8 PASS；剩余 minor 转 p018。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 删除 v1 前端树与依赖，收敛路由；补齐色板、客户端超时/同源/幂等/retryable、SSE 401 与尾帧、i18n 语言同步与存储键迁移。遗留见 p018。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

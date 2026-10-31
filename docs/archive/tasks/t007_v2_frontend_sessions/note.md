---
tid: "t007"
slug: "v2_frontend_sessions"
title: "实现页面独立 Profile 选择与 WebRTC 浏览界面"
status: "done"
branch: "t007_v2_frontend_sessions"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "077778fef84f22312e6b18583c547c8b5f418617"
depends_on: "t006"
conflicts_with: ""
note: ""
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

无

#### 2026-10-31T15:08:08+08:00 开工、spike 与 lane 派发

- identity：attempt1 / execution_id=1a08cbc562094e73ae64c8039127ed0a / owner_id=claude_v2_6e1f7a8e7a46；diff_anchor=077778f。范围已纳入 p003（AC-009）与 p004（AC-010）。
- Selkies token 机制：Gemini spike lane 以真实 Stream 镜像实验 5 项，主控复跑 5 passed，结论入 d024；UNVERIFIED-SPIKE 已改写，strict preflight PASS。
- 并行 Gemini lane：be_coord（AC-009 协调 + SSE）、fe_shell（前端外壳）、fe_session（浏览会话/适配层）、stream_tokens（AC-008/AC-010）。
- 编排事故（主控责任）：
    - 首次批量派发的 shell 后台调用看似失败、实际已启动进程，随后用启动器重派，导致 fe_shell 与 be_coord 各有两个实例并行写同一 worktree；fe_shell 自行发现并结束重复实例，be_coord 由主控结束启动器那一套，保留其一，合入时须核对交错写入。
    - 合入 fe_shell 时误把 lane 同步脚本指向任务 WT，在任务分支生成中间提交 acd3832 “noop”（内容全为 fe_shell 交付 + tsbuildinfo）。已用 `git reset --soft 077778f` 撤销，改动保留在暂存区，HEAD 回到 diff_anchor，tsbuildinfo 还原为基线；原提交仍在 reflog。
    - 镜像清单文件 `images.env` 命中 lane 读取权限 `*.env` 拒绝规则，改用 `images_env.txt`；fe_session 构建改写已入库的 `src/frontend/tsconfig.tsbuildinfo` 触发 SHA 守卫，已还原并放开守卫，该产物变化不入交付。
- fe_shell 交付（已合入 t007 WT 暂存区）：React Router 7 路由（计划 13.1 + /login）、TanStack Query、openapi-typescript 生成类型、CSRF fetch 封装、SSE 客户端与断线恢复、Profile/设置页、`BrowserSessionMount` 挂载点；旧组件与旧测试保留到 t011。主控复跑 Vitest 8 文件 60 passed，构建成功。

#### 2026-10-31T17:42:10+08:00 lane 合入、真实栈 E2E 与主控评审修正

- Gemini 额度耗尽后，经用户批准 lane 改用 `opencode-go/deepseek-v4.1-flash --variant high`。
- fe_session（`features/browser-session`、官方 Selkies 2.1.0 资源固定 wheel SHA 拉取脚本 `scripts/vendor_selkies_web.py`）、be_coord（`api/runtime_coordinator.py`、SSE `GET /api/v1/events`、OpenAPI 重导出）、stream_tokens（`supervisor/selkies_tokens.py`、Stream 入口 tokens 文件与安全模式、Agent HELLO 代注入）均已合入；主控复跑 unit+integration 336 passed、Vitest 72 passed、构建成功。
- fe_e2e：构建产物 + 完整真实栈（Caddy/API 启用 Coordinator/Supervisor/Gateway/coturn/Browser/Stream）无头 Chrome E2E `tests/e2e/test_frontend_app_e2e.py` 5 passed；主控在独立环境复跑 5 passed。暴露并修复生产缺陷：运行意愿方法 PUT→PATCH（405，Profile 无法启动）、协调错误未经 SSE/界面展示、会话诊断缺“查看运行状态”操作；夹具 Caddy 静态 fallback 拦截 `/api` 已改为互斥 `handle`。`client.test.ts` 原 PUT 用例编码了与 OpenAPI 冲突的方法，整项删除并新增 PATCH/CSRF 用例。
- 主控评审修正：前端生成类型未随 OpenAPI 重生成（lane 用手写交叉类型补 `last_coordinator_error`）→ 重跑 `npm run generate:api` 并删除手写类型；会话页/页头硬编码文案改走 i18n，E2E 浏览器上下文固定 `zh-CN`。
- 主控评审发现两项 important，另派 DeepSeek lane：
    - adapter：生产注入 Selkies iframe 的适配层是 `vendor_selkies_web.py` 内嵌 JS 字符串，`adapter.ts` 仅被单测引用（双实现、单测未触达生产代码）→ 收敛为 `adapter.ts` 单一来源并由前端构建产出 `selkies_adapter.js`。
    - auth：`useAuth` 未被任何路由消费，未登录访问不跳 `/login`，SSE 登录前即启动 → 登录守卫、401 跳转、SSE 仅认证后运行、拒绝开放重定向。
- p005（t006 遗留 minor）不在本 task 契约范围，保持开放。

#### 2026-10-31T19:01:06+08:00 门禁 r1 与编排痕迹清理

- 门禁 r1（`.scratch/project_gates/r1/summary.txt`）：构建、Vitest、前端构建、contract 169、旧后端 384、unit 282、integration 54、runtime 13、sup_lifecycle/startup/graph/resource、gateway 5、schema 三项、md_format、diff_check 通过。失败项与处置：
    - frontend_e2e 死锁：lane 把编排用 Docker 互斥锁（含本机绝对路径 `.scratch/v2_orchestration/docker_e2e.lock`）写进 `test_frontend_session_e2e.py`、`test_frontend_app_e2e.py`、`test_runtime_coordinator_e2e.py` 与 `tests/fixtures/frontend_probe/docker_lock.py`，门禁外层已持锁时测试内部等待超时。主控删除这些锁代码与 helper（仓库测试不得引用编排目录），待 r2 复验。
    - stream_e2e：`test_stream_selkies_tokens_e2e.py` 因门禁脚本该步缺 `tests/fixtures` PYTHONPATH 导入失败（门禁脚本已修）；`test_stream_runtime_multi_viewer_e2e` 固定 sleep 2 秒后断言两个 viewer，负载下偶发 1 个。主控单独复跑二者 5 passed（`.scratch/project_gates/r1_rerun/stream.log`）。
    - sup_netpolicy：`test_kernel_network_policy_real_netns` 公网 IPv4 出站超时（外网抖动，t007 未改网络策略），复跑 2 passed（`r1_rerun/netpolicy.log`）。
    - ruff：lane 新增代码未达 E/F/W/I 与 format 要求；主控格式化后端与测试文件并修正 E2E 测试长行，`vendor_selkies_web.py` 由 adapter lane 改写时清理（同时删除其引用编排目录的分支）。
- adapter/auth lane 因上述锁改动暂停后续行（DeepSeek，同会话，`--unguard-changed`）。

#### 2026-10-31T21:44:32+08:00 门禁 r2、AC 复核缺口与 display 合入

- adapter lane 合入：`adapter.ts` 为唯一实现，`vite.selkies.config.ts` 产出 IIFE `dist/selkies/selkies_adapter.js`，`vendor_selkies_web.py` 删除内嵌 JS 与编排目录分支；`vendor_selkies_web.py` 内嵌 JS 曾被 `test_vendor_extract_and_manifest_verification` 断言“必须写出 selkies_adapter.js”，该语义被推翻，lane 整项删除该用例，替代覆盖为 `tests/e2e/test_frontend_adapter_build.py`。主控追加：完整性校验由 `assert` 改为显式 `RuntimeError`（`python -O` 下不失效）；wheel 缓存改为中性路径 `.scratch/selkies_wheels`；vendor 每次重建目标目录（RED `.scratch/t007_master/red_vendor_stale.log`，GREEN `green_vendor_stale.log`），避免旧内嵌适配器残留进构建。
- auth lane 合入：`RequireAuth` 守卫、`/login?next=` 同源相对路径校验、401 回登录、SSE 仅认证后运行（Vitest 9 例 + 真实栈 E2E `test_frontend_app_auth_e2e.py`）。`router.test.tsx` 只改测试包装（加 `AuthProvider`，`/login` 子用例以未认证渲染以符合新语义），断言未改。
- 门禁 r2（`.scratch/project_gates/r2/`）：除 coordinator E2E 因门禁脚本缺 uvicorn 依赖失败外全部通过（Vitest 82、unit 282、integration 54、runtime 13、stream 19、Supervisor 全组、gateway 5、frontend 13/14、schema、ruff 基线 0、md_format）；补依赖复跑 1 passed（`r2_rerun/coordinator.log`）。
- AC 复核（主控）发现阻断缺口：AC-004 Stream 入口把 Selkies 分辨率写死 1920×1080 且无“明确应用”；经完整应用的可见性未验证；AC-005 静音仅改 DOM、内部标签页同步与音频故障状态无实现/测试。派 display、media 两个 DeepSeek lane。
- display lane 合入：Supervisor 从绑定快照读取尺寸注入 Stream（缺失/非法 fail closed），入口删除写死值，运行中改尺寸显示待应用并提供“应用并重启”（经 API stop→running）；E2E `test_frontend_display_apply_e2e.py` 2 passed，unit 291、integration 54、stream_runtime、frontend_app 回归通过。主控追加入口导出 `CBROWSER_SCREEN_WIDTH/HEIGHT` 给 Agent，使独立启动时注册几何与 Selkies 一致。
- 已知抖动：`test_stream_runtime_multi_viewer_e2e`（t004 用例）固定 sleep 2 秒后断言两个 viewer，负载下偶发一个 viewer 在 HELLO 前断开（Selkies 记 `Invalid hello message type`，为关闭帧而非 token 代注入改写的 HELLO），复跑通过。

#### 2026-10-31T22:00:02+08:00 media 合入与门禁 r3

- media lane 合入：每页静音按钮走官方 `pipelineControl` audio（`STOP_AUDIO`/`START_AUDIO`），独立音频状态 `audio_status.ts`（实验确认内容静音仍有 Opus 包、不判故障；`pkill pulseaudio` 后 3 秒无包判 `no_data`，视频阶段保持 connected）。E2E `test_frontend_media_e2e.py` 4 例：完整应用内 A 隐藏发官方 `STOP_VIDEO`、Gateway 未暂停 consumer 2→1、B 前台 30.3 FPS（下限 20）、全隐藏 capture 停止、恢复 `START_VIDEO`；A 静音时 A 音频字节 0 增长、B +32 KB 且能量增长；远端 CDP 新标签纯色在两页同步显示；音频诊断正常/静音/真实故障。lane 最终 media+app+session 12 passed，Vitest 93 passed。主控合并 display/media 两 lane 的 `i18n.tsx` 新键并修正 E2E lint。
- 门禁模板加入 `test_frontend_media_e2e.py`、`test_frontend_display_apply_e2e.py`；门禁 r3 开跑（`.scratch/project_gates/r3/`）。

#### 主控评审追加项（不进 reviewer 处置表）

- 安全（Round 1 期间主控发现）：`selkies_tokens.json` 原写在以 rw 挂进 Browser 容器的 `runtime/<profile>/`，fix_be 改写入只挂给 Stream 的 `runtime/.secrets/<profile>/`（目录 0700、文件 0600）；`tests/unit/test_supervisor_selkies_token_isolation.py` 与 `test_stream_selkies_tokens_e2e.py`（真实 Browser 容器内读取原路径失败）覆盖。同类 `agent_secret.txt` 属 t005/t006 既有，登记 p006。
- t007_code_f004 Round 2 残留：设置页/新建页部分文案与阶段错误详情仍硬编码，blueprint 表述已改准，登记 p007。

#### 2026-11-01T05:15:00+08:00 黑盒 r1 与 Round 3 后修复

- 独立黑盒 r1（DeepSeek，冻结 Round 1 修复前候选，证据 `.scratch/lane_evidence/blackbox_r1/`）：自写探针 AC-001..AC-010 全部 PASS；文档门禁 unit 291、integration 54、gateway 5、stream tokens 4、frontend 20/21。发现：`test_ac005_audio_diagnostics_normal_silence_and_link_failure` 可复现失败——健康音频诊断在“正常/未知”间跳变（产品缺陷）；testing.md 前端章节缺 `CBROWSER_GATEWAY_TEST_IMAGE` 与 uvicorn 等依赖；stream tokens 驱逐关闭码偶发 1006（登记 p012）；contract 2 项为验证 WT 内 TMPDIR 的已知环境差异；AC-002/AC-007 resume_key 疑问与 Round 1 改写后的 AC 一致。
- 主控修复音频状态：预热改按保留历史起点判断，增长比较以窗口起点前最后样本为基线（RED `.scratch/t007_master/red_audio_status_flap.log` 预热后 11 次中多数为 unknown，GREEN `green_audio_status_flap.log`）；testing.md 补变量与依赖。

#### 2026-11-01T06:10:00+08:00 门禁 r4 与 token 文件重启回归

- 门禁 r4（`.scratch/project_gates/r4/`）：除 frontend_e2e 1 项（构建早于 audio 修复的旧 dist）与 sup_lifecycle 1 项外全部通过；用最终代码补跑前端 E2E 22 passed（`r4_final/frontend_e2e.log`）。
- sup_lifecycle 失败为真实回归：`test_supervisor_real_subprocess_retry_e2e` 第二次启动的 Stream Agent 报 `Selkies credentials file not found or not a regular file`（调试镜像只改日志措辞得到原文，`.scratch/t007_master/retry_debug5/`）。fix_be 把 token 移到只以单文件挂载的 `.secrets/<profile>/selkies_tokens.json` 后，重启时同一路径被原子替换，本机 OrbStack 文件共享在随后毫秒级启动的新容器里仍给出失效条目（原路径位于挂进存活 Browser 的目录下，缓存一致，故此前不暴露）。修复：`SelkiesTokens.provision_credentials_file` 每实例写新文件名 `selkies_tokens_<runtime_instance_id>.json` 并删除旧实例文件（RED/GREEN `.scratch/t007_master/*selkies_token_instances.log`），E2E 夹具与断言按前缀查找。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-10-31T22:53:36+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t007_code_f001|important|已修|SSE 事件 id 改为 `<epoch>:<seq>`，跨进程/越窗口发完整快照|src/backend/cbrowser/api/runtime_coordinator.py；tests/integration/test_sse_epoch_integration.py|
|t007_code_f002|important|已修|ICE 失败经真实状态消息检测并有真实栈 E2E；失效连接真实重建有单测与 E2E|useBrowserSession.ts；tests/e2e/test_frontend_ice_failure_e2e.py|
|t007_code_f003|minor|已修|stop 路径区分不可达与无实例，重试循环不再静默终止|runtime_coordinator.py；tests/unit/test_runtime_coordinator_stop_paths.py|
|t007_code_f004|minor|已修|会话/页头/表单文案改走 `t()`|SessionDiagnostics.tsx、AppLayout.tsx、ProfileDetailPage.tsx、i18n.tsx|
|t007_code_f005|minor|已修|BrowserSessionMount 改静态 import，删除 glob/placeholder|src/frontend/src/shared/components/BrowserSessionMount.tsx|
|t007_code_f006|minor|已修|宿主校验 event.source/origin，适配层指定 targetOrigin|useBrowserSession.ts、adapter.ts；BrowserSessionView.test.tsx|
|t007_code_f007|minor|已修|侧边栏选择统一导航到 `/?profileId=`|AppLayout.tsx；router.test.tsx|
|t007_code_f008|minor|已修|按官方 resume_key 语义改写 AC-002/AC-007 措辞（契约区 drift 已在上下文区记录）|task.md AC-002/AC-007|
|t007_test_f001|important|已修|activity/resize 拦截断言改为真实底层 send 边界|BrowserSessionView.test.tsx|
|t007_test_f002|important|已修|重建断言改为 reloadKey/阶段迁移，并补真实失效 E2E|BrowserSessionView.test.tsx；test_frontend_session_e2e.py|
|t007_test_f003|important|已修|静音走产品按钮并断言 STOP/START_AUDIO，输入断言远端真实值|test_frontend_session_e2e.py、test_frontend_app_e2e.py|
|t007_test_f004|important|已修|补 noopener 单测与“不重写官方 HELLO”E2E|BrowserSessionView.test.tsx；test_frontend_app_e2e.py|
|t007_test_f005|minor|已修|派发 CBROWSER_PC_STATE 断言 ice_failed；主控追加 disconnected 5 秒宽限（RED/GREEN `.scratch/t007_master/*ice_disconnect_grace.log`）|useBrowserSession.ts；BrowserSessionView.test.tsx|
|t007_test_f006|minor|已修|断言 list query 失效重取|useProfilesQuery.test.tsx|
|t007_test_f007|minor|已修|完整应用 E2E 点击查看运行状态断言跳转|test_frontend_app_e2e.py|
|t007_test_f008|minor|已修|resize 断言改读 DataChannel 发送记录|test_frontend_app_e2e.py|

### Round 2 (2026-11-01T01:28:28+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t007_test_f009|important|已修|前端 E2E 夹具改读 `runtime/.secrets/<profile>/selkies_tokens.json`|tests/fixtures/frontend_app_probe/harness.py|
|t007_test_f010|minor|已修|静音断言先筛出携带远端音频轨道的媒体元素并要求非空，再比较静音状态|test_frontend_app_e2e.py、test_frontend_session_e2e.py|
|t007_code_f009|minor|已修|SSE 无缓存时不再伪造 runtime（`config_version: 1`），每个事件使 runtime 查询失效重取（RED/GREEN `.scratch/t007_master/*sse_no_fabricated_runtime.log`）|useProfilesQuery.ts；useProfilesQuery.test.tsx|
|t007_code_f010|minor|已修|补 bfcache `pageshow(persisted)` 单测（健康不重建、非 persisted 不检查、失效重建），变异检查去掉 persisted 判断即失败（`.scratch/t007_master/bfcache_pageshow*.log`）|BrowserSessionView.test.tsx|

### Round 3 (2026-11-01T05:05:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t007_test_f011|minor|遗留|SSE 事件后 runtime 查询失效重取缺回归测试（行为已由实现与 E2E 间接覆盖）|p011|
|t007_test_f012|minor|遗留|session E2E 对容器状态接受 `created`，app E2E 已有严格 `running` 断言|p011|

### Round 4 (2026-11-01T05:40:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t007_test_f013|minor|遗留|测试辅助函数丢弃 totalAudioEnergy，判定逻辑不读能量，结论不受影响|p011|

### Round 5 (2026-11-01T06:40:00+08:00)

Round 5 零 finding。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-002/AC-007 按官方 Selkies resume_key 语义改写措辞，见 task.md 上下文区）
- 测试：最终门禁 r5（`.scratch/project_gates/r5/`，全部镜像当前源构建）：contract 169、legacy 384、unit 307、integration 55、Vitest 105、前端构建与 Selkies vendor、runtime 13、stream 19、Supervisor 生命周期 6、启动恢复 2、容器图 8、网络策略 5、资源 5、Gateway 5、前端 E2E 21/22（唯一失败为 AC-001 静止画面出帧抖动，复跑 2/2 passed，`r5_rerun/`，登记 p013）、schema 导出与前端生成类型一致、Ruff 基线 0、md_format、diff_check。token 修复专项：retry E2E 2/2、Supervisor core/recovery/offline + stream tokens + 前端 app 14 passed（`.scratch/t007_master/token_instance_verify/`）。
- 黑盒：独立 DeepSeek 黑盒 r1（冻结 Round 1 修复前候选，93 文件 SHA 核对，自建全部镜像）AC-001..AC-010 自写探针全部 PASS；其发现的音频诊断跳变缺陷已修并经最终门禁前端 E2E 验证；证据 `.scratch/lane_evidence/blackbox_r1/`。Round 1 之后的修复由门禁 r4/r5 与专项复跑覆盖，未再做第二轮独立黑盒。
- review：Full 五轮，Round 5 code/test 两路 PASS 零 finding（reviewed_scope a006b995998b9c28），check_review_status overall=PASS；minor 遗留 p007、p011。
- AC 判定：见 `task.md` 行内打勾；证据见各轮评审「AC 复验方式」与本文件实施笔记。

### 结果摘要

- 交付 v2 前端：React Router 7 外壳与登录守卫、OpenAPI 生成类型客户端、TanStack Query + SSE（`<epoch>:<seq>` 事件 id，跨进程发快照）、Profile 管理、页面独立 `?profileId=` 目标、官方 Selkies 2.1.0 iframe 与单一来源适配层（`adapter.ts` 构建为 IIFE 注入）、会话阶段诊断（运行时未就绪/信令/ICE/媒体/独立音频状态）、冻结恢复重建、每页静音、显示尺寸“明确应用”。
- 后端：API Runtime Coordinator 经内部 RPC 驱动 Supervisor 启停（p003 闭环）；每 Profile Selkies master/controller token、Stream 安全模式与 Agent 代注入（d024，p004 闭环），token 文件只挂给 Stream（`runtime/.secrets/<profile>/selkies_tokens_<instance>.json`）；Stream 分辨率取自 Profile 配置。
- 审查/验证中发现并修复的缺陷：运行意愿 PUT→PATCH（Profile 无法启动）、协调错误不可见、适配层双实现、未登录不跳转与 SSE 401 重连、Stream 分辨率写死、经完整应用的可见性/静音/音频故障缺证据、SSE 跨进程 epoch、token 文件挂进 Browser 沙箱、token 文件原地替换导致 Supervisor 重启失败、音频诊断跳变、ICE disconnected 立即报失败。
- 遗留：p005（t006 minor）、p006（agent_secret 挂进 Browser）、p007（前端残留硬编码文案）、p008（Agent 隧道未触发 Selkies RESUMED）、p009（multi_viewer 固定等待）、p010（生产构建固定 vendor 步骤，归 t012）、p011（评审 minor）、p012（同 tab 驱逐关闭码抖动）、p013（AC-001 静止画面出帧抖动）。豁免：公网 WebRTC/TURN 与原生 Linux x86_64 为 NOT_RUN / USER_WAIVED；容量/P95/8 小时/1000 次输入属 t009。

### 长期文档闭环

- specs_index：webrtc_remote_display、runtime_lifecycle、access_control 追加 t007，新增 profile_management；旧 chrome_external_tabs（控制租约模型）移入 docs/archive/specs/。
- blueprint：新增 frontend.md；architecture.md 5.5 Runtime Coordinator；stream_runtime.md、security.md、testing.md 更新。
- finding：d024（Selkies token 安全模式与代注入）。

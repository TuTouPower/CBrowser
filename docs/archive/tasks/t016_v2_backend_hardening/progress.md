---
tid: "t016"
slug: "v2_backend_hardening"
title: "后端控制面、数据模型与运行时加固"
status: "done"
branch: "t016_v2_backend_hardening"
worktree: ""
review_level: "full"
review_limit: "6"
verify_limit: "5"
diff_anchor: "fb6185c46f41500a9089e526a1773774a7cd6c67"
depends_on: ""
conflicts_with: "t015"
note: "来源 docs/reviews/review_20261102_201727/adoption_decision.md; budget: review_limit: 5->6; Round 5 PASS 后修复 6 项 minor（限流来源、URL 转义、损坏事件隔离、属性初始化、重复校验器、文档）需要最终复核"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 2026-11-03 实施

- 控制面：Supervisor 上报 bind/observed/events 从用户路由移除，只保留内部 Bearer 面；补 OpenAPI 安全方案（sessionCookie/csrfHeader/serviceBearer）、可达错误码与内部 OpenAPI 导出 `schemas/openapi/cbrowser_internal.json`；前端类型重新生成。
- 认证与事件流：伪造/未知自动化令牌只记日志不落库；Retry-After 先修剪全局队列；AuthService 缺失返回 503；自动化令牌支持可选过期并按期拒绝；创建会话时清理过期会话；API docs 默认关闭（`CBROWSER_API_DOCS=1` 开启）；SSE 在同一锁内先构建快照/补发再注册订阅队列，消除乱序窗口。
- 数据模型：删除 `runtime_mode`/`viewer_mode` 字段与 API/契约输出，新增 Alembic `0004_remove_modes` 与 `0005_token_expiry`。
- Runtime Agent：健康探活改为并发 `to_thread`；CDP 事件逐帧隔离异常并按 1/2/4…30 秒退避重连、重连后重新 arm 下载捕获；启动参数改为白名单（API 422 + runner 第二道校验）。
- Supervisor：下载路径越界拒绝、无法解析事件进 dead-letter、事件信封带版本、ingest 返回原因；对账按 Profile 隔离；启动对账失败不阻断控制面；资源/状态/标签/token/日志/指标/WS 鉴权等 A31/A6 加固；URL 标识转义与 snapshot 0600。
- 存储与所有权：下载事件有界索引与分页；runner 的 Pulse/X11/Openbox 路径收进 run_dir、X lock PID 校验、显式子进程 env；Artifact 配额在 per-profile 锁内重新断言；artifact_id 单组件校验；删除 0777/0666 回退，目录 0700/0750、文件 0600/0640，chown 失败报错；ADR 014。
- 验证：unit 530 passed；integration 79 passed；frontend Vitest 126 passed；tsc/build 通过；当前源码重建 Browser/Supervisor/API 镜像后，真实 Gateway/Supervisor 拓扑的 frontend session E2E 通过（uid 1000、X11 0750、媒体/输入/复制/刷新），Browser Runtime E2E 与 profile defaults 通过；OpenAPI public/internal schema 漂移测试通过。

## Review 处置

每个结构化 finding 一行。已修/遗留/撤回；critical/important 未解决时不得 PASS。

### Rounds 1-6

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t016_code_f001|critical|已修|launch_args 校验迁到请求 DTO，旧库读取过滤|domain/models.py; repository|
|t016_code_f002|critical|已修|CDP 重连 rearm 不再等待自身消费 ACK|runtime_agent/cdp_proxy.py|
|t016_code_f003|important|已修|ProfileCreateRequest 白名单校验返回 422|domain/models.py|
|t016_code_f004|important|已修|自动化授权按来源限流|auth/service.py|
|t016_code_f005|important|已修|内部 OpenAPI 补 404/409/429/413/507，守卫遍历全部 operation|api/app.py; tests|
|t016_code_f006|important|已修|Profile/Artifact 默认 uid/gid 1000|profile_service.py; artifact_store.py|
|t016_code_f007|important|已修|recovery_coordinator URL 标识符转义|recovery_coordinator.py|
|t016_code_f008|important|已修|下载事件信封带 version，读取侧兼容|runtime_agent/protocol.py|
|t016_code_f009|important|已修|仓储测试改用真实迁移并加 metadata/migration 漂移守卫|tests/unit/test_domain_and_repository.py|
|t016_code_f010|minor|遗留|文档残留 failed/0755 回退描述|p017|
|t016_code_f011|minor|已修|runtime snapshot 改 0600 并 chown|docker_adapter.py|
|t016_code_f012|critical|已修|0006 迁移清理旧快照中的 runtime_mode/viewer_mode|migrations/versions/0006|
|t016_code_f013|minor|已修|自动化 WS 复用 resolve_client_ip|automation_router.py|
|t016_code_f014|minor|已修|剩余内部 URL 统一 quote|automation_router.py; runtime_coordinator.py|
|t016_code_f015|minor|已修|损坏下载事件移入 quarantine 后继续|event_storage.py|
|t016_code_f016|minor|已修|__init__ 初始化 _last_rearm_ok|cdp_proxy.py|
|t016_code_f017|important|已修|重新生成前端 API 类型|cbrowser_v1.d.ts|
|t016_code_f018|minor|遗留|ProfileUpdateRequest 重复 launch_args 校验器|p017|
|t016_code_f019|minor|遗留|重连 rearm 未校验 CDP error 响应|p017|
|t016_test_f001|critical|已修|仓储测试改用真实迁移|tests/unit/test_domain_and_repository.py|
|t016_test_f002|important|已修|非法 launch_args HTTP 422 用例|tests/integration/test_v2_api_subprocess.py|
|t016_test_f003|important|已修|token 过期、会话清理、docs 关闭、503 测试|tests/unit/test_auth_service.py 等|
|t016_test_f004|important|已修|伪造 token 不写 audit 的断言|tests/unit/test_auth_service.py|
|t016_test_f005|important|已修|SSE 快照/实时事件时序测试|tests/unit/test_runtime_event_broadcaster_epoch.py|
|t016_test_f006|important|已修|坏帧后有效事件与断线 rearm 测试|tests/unit/test_runtime_agent_faults.py|
|t016_test_f007|important|已修|Pulse cookie/Xauthority 0600 E2E 断言|tests/e2e/test_browser_runtime_e2e.py|
|t016_test_f008|important|已修|全 operation 契约码遍历守卫|tests/unit/test_runtime_agent_protocol_export.py|
|t016_test_f009|minor|遗留|路由/实现可达码动态枚举仍为结构映射|p017|
|t016_test_f010|minor|遗留|特殊字符 URL 请求路径断言未加|p017|
|t016_test_f011|minor|已修|文档字段与 ObservedState 对齐|docs/blueprint|
|t016_test_f012|minor|遗留|后台重试与 labels 字符串化的直接测试未加|p017|
|t016_test_f013|minor|已修|默认 uid 1000 断言|tests/unit/test_launch_args.py|
|t016_test_f014|important|已修|前端生成类型同步|cbrowser_v1.d.ts|
|t016_test_f015|important|已修|E2E stat 导入|tests/e2e/test_browser_runtime_e2e.py|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：unit 539 passed；integration 79 passed；legacy 384 passed；contract 169 passed；frontend Vitest 126 passed；tsc -b 与 npm run build/verify 通过；真实迁移/漂移守卫与 public/internal OpenAPI 漂移测试通过。
- 黑盒：当前源码重建 Browser/Supervisor/API/Stream 镜像后，真实 Gateway/Supervisor 拓扑 frontend session E2E 通过（uid 1000、X11 0750、媒体/输入/复制/刷新）；Browser Runtime E2E 与 profile defaults 通过。
- review：full code/test 两路 Round 6 PASS；所有 blocking 已修，剩余 minor 转 p017。
- AC 判定：见 `task.md` 行内打勾。

### 结果摘要

- 控制面上报只留内部服务面；认证/SSE/OpenAPI 契约与前端类型同步；数据模型删除死字段；Runtime Agent 健康/D/CDP/启动参数加固；Supervisor 下载、对账、状态、日志、指标、URL 与权限加固；存储所有权统一 uid 1000。遗留见 p017。

### 长期文档闭环

- specs_index: storage_and_artifacts、runtime_persistence 已加入 t016；access_control 未宣称更新。

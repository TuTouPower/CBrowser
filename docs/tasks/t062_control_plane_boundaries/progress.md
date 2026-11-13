---
tid: "t062"
slug: "control_plane_boundaries"
title: "跨服务中立模块与运行镜像边界收敛"
status: "done"
branch: "t062_control_plane_boundaries"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "c5f83296ece80a9a0ed9f1e48d957ce332f858c4"
depends_on: ""
conflicts_with: "t061,t063,t064,t065,t066,t068,t069"
note: "p073；原严格契约 AC-001..004 转 t069；本 task 只交付包边界、公共规则与相关职责拆分"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-13 审阅修订：原 AC-001..004 转入 t069 AC-001..004，编号不复用；p071 归档原引用仍可经 t062 找到 t069。修正 ORM/I/O 归因，新增端口/路径验收。

- 本次仅维护 backlog；不 start、不实现；旧归档来源只追加转办链，不改写历史。

- 调度字段经 task.py edit 写入；plan 的 runnable 只指依赖/冲突候选，不代表产品 BLOCKING 已解决。

- 2026-11-13 云端执行（worktree `CBrowser_t062`，基线 main `c5f8329`，preflight PASS、1 条 SPIKE 警告待回填）。用户已授权与本地 t068 强行并发，合入成本由主会话承担；本 task 避开 t068 核心文件面（指纹/引擎探针与测量报告），只可能触及 runtime_agent 的 import 行与原子写调用（egress_probe/event_storage/fontconfig），不改其行为。
- 设计（中立归属 = 既有 `cbrowser/shared/` 包，零业务包依赖）：
  - `shared/endpoints.py`：自 `gateway/endpoint.py` 平移 GatewayEndpoint、normalize_origin(s)、DEFAULT_GATEWAY_PORT/HOST、gateway_port_from_env；新增控制面权威常量 DEFAULT_SUPERVISOR_PORT=8005 与 DEFAULT_SUPERVISOR_URL（由端口派生），消除 control_client 的 8091 分裂。`gateway/endpoint.py` 删除，全部 import 者（含 tests）改指 shared。
  - `shared/agent_credentials.py`：自 `supervisor/agent_credentials.py` 平移 AgentCredentials；原文件删除，gateway/server 与 supervisor/core 改 import。
  - `shared/atomic_write.py`：唯一原子写实现（O_EXCL 临时文件 + flush + fchmod + fsync + replace + 目录 fsync，机制以原 supervisor/file_storage 为准），签名 atomic_write_bytes/text(path, ..., mode=0o600, uid/gid 可选)。`supervisor/file_storage.py` 删除；手写点迁移：preview._atomic_write（保留签名薄封装）、runtime_agent/event_storage.atomic_write_json（保留 StorageError/目录确保语义，内部改用 shared）、runtime_agent/fontconfig、agent_executor/state.py。adapters/artifact_store 的流式落盘是流式变体（无法用一次性接口），保留实现但补目录 fsync 对齐同一耐久契约；font_sets/manifest 的目录 swap、core/artifact_store 的文件 rename 是移动语义非写实现，不动。
  - `shared/profile_locks.py`：唯一 per-profile 锁注册表（自 services/profile_service.ProfileLockRegistry 平移，接口 lock()/lock_for()/is_locked()/is_idle，自清理语义不变）。三方迁移：profile_service（删自有类）、control_service（删自有 dict/_lock_for）、supervisor/core（删自有 dict/_get_profile_lock；探查点改 is_locked）。非范围声明不变：不同进程的注册表实例不构成跨进程互斥。
  - `shared/delivery.py`：投递分类唯一规则（DELIVERED/REJECTED/UNAVAILABLE、RETRYABLE_4XX、classify_delivery_status 自 supervisor/event_forwarder 平移）；artifact_forwarder 删内联状态判定改用 classify（语义等价：200 由调用方处理，非 200 经分类得 REJECTED 才标记 processed 继续、UNAVAILABLE 即停）。
  - `shared/fencing.py`：实例 fence 唯一规则 fence_by_instance（Protocol 结构化约束，shared 不 import 业务包）；api/v1/runtime_views 的 fence_* 与 api/runtime_coordinator 的 fenced_* 内部改调它，规则实现只剩一份。
  - origin 第二份消除：network_config._format_origin 删除，derive_origin_whitelist 改用 shared.normalize_origin 构造条目（默认端口剥离等行为一致）。
  - 认证领域会话：domain/models.py 新增 AuthenticatedSession（pydantic frozen：id/csrf_token/expires_at/created_at，不含 token_hash 存储细节）；auth/service 的 create_session/get_valid_session 改返回领域对象（内部仍用 ORM）；auth/dependencies 与 api/v1 六个 router 的类型标注改领域对象、删 SessionModel import。ProfileService 新增公开方法 profile_lock()，api/v1/router.py 不再访问 service._locks 私有属性。
  - egress 移出 domain：新建 `cbrowser/shared/egress.py` 承载 fetch_egress_ip/GeoIpLookup/resolve_geoip_db_path/probe_egress/GEOIP_DB_FILENAME（httpx/GeoIP/文件 I/O），以及探针自身的词汇 ECHO_URLS 与 EgressProbeError/GeoIpUnavailableError（自 domain 迁入，它们是探针契约的一部分、由 services 层捕获）；domain/egress_observation.py 只留 EgressObservation、observation_is_current 与观测常量。probe_egress 签名由收 ProxyEndpoint 改为收其 proxy_url() 字符串，shared.egress 由此零 cbrowser import。落点两度修正（实测驱动）：原拟放 adapters，但 tests/unit/test_a26_browser_image_modules.py 的闭包分析证明 Browser 镜像不得带 adapters 包（其闭包含 DB 模型等无关面），而探针必须随 runtime_agent 进 Browser 镜像——故中立归属只能是 shared；其后镜像闭包测试（test_t062_image_closure.py）又证明 shared 若 import domain 叶子，Gateway 镜像（不带 domain）里 shared.egress 将不可导入——故词汇一并迁入、签名去 Endpoint 化，shared 的依赖纪律收敛为「除 secret_files 叶子外零 cbrowser import」（已写入 shared/__init__ 文档与边界测试）。Browser 镜像为此补 secret_files.py 一行 COPY（shared 的唯一叶子依赖随包同行），a26 的 UNRELATED 与闭包展开规则同步更新（terminal 包只展开其顶层叶子模块引用）。services/egress_probe.py、runtime_agent/egress_probe.py、supervisor/docker_adapter.py（ECHO_URLS）、services/profile_service.py（EgressProbeError）改 import 源；t052 测试按拆分更新 import 路径与 probe_egress 调用（传 endpoint.proxy_url()，断言语义不变）。
  - 原子写所有权修正（实测驱动）：tests/unit/test_preview.py 的碰撞用例证明原 supervisor/file_storage 规范实现在 O_EXCL 碰撞时 finally 会误删他人暂存文件；shared 实现按 preview 旧实现的所有权语义修正（仅删除本调用创建的暂存文件），并在 tests/unit/test_shared_atomic_write.py 补碰撞/失败保旧两条机制级用例；preview 两条旧用例的注入点随机制搬家更新（fchmod 注入、暂存命名与 patch 点），断言语义不变。
  - 镜像闭包统一策略：以「包」为 COPY 粒度；顶层单文件模块逐个列名；只消费兄弟包个别模块且整包会引入错误依赖面时才逐文件（gateway 的 stream_agent 两文件、supervisor 的 services 两文件属此类，维持现状）。gateway 删 supervisor 三行跨包 COPY 与未被 import 的 domain 整包行、shared 改整包一行；supervisor 删 gateway 整包行、加 shared 整包一行；api 把全量 `COPY src/backend` 改为 cbrowser 整包 + migrations 两行（同布局）；browser 加 shared 整包一行（egress 最终落 shared，原拟的 adapters 两行 COPY 不再需要、未加；本句原稿误记为已加，Round 1 test 轴指出后于收尾订正）；stream/automation_probe 不动。新增 shared 模块永不需改 Dockerfile。
  - SPIKE（跨镜像依赖闭包）：新增 tests/unit/test_t062_image_closure.py，按各 Dockerfile 的 COPY 清单把文件组装到临时树、子进程以镜像 PYTHONPATH 实际 import 该镜像全部 cbrowser 模块（第三方依赖以本机 venv 近似镜像 requirements），云端验证文件闭包；真实 Docker 构建 + readiness 属 AC-005 [deploy] 部分，顺延本地并登记 pending，不假验证。依赖方向由 tests/unit/test_t062_boundaries.py 以 AST import 图守护（gateway↔supervisor 零互 import、路由/认证依赖无 SessionModel、domain egress 无 I/O 实现、shared 零业务包依赖）。

- 调度依据：中立包、认证依赖、服务锁与 Dockerfile 为 t064/t065/t066/t069 提供公共边界；与会话、Selkies、引擎构建存在文件/集成验证冲突。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-13T22:59:00+08:00)

code 轴 verdict FAIL（1 important + 3 minor），test 轴 verdict FAIL（2 important + 3 minor）；实现层复验均成立，FAIL 主因是 AC 打勾闭环未完成与守护测试盲区。逐条处置如下，全部修复后派 Round 2 复核。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t062_code_f001|important|已修|四条 AC 在审阅时尚未行内打勾、与收尾报告口径矛盾（TICK-VOID）；审阅后已逐条按实测打勾，AC-005 的 [deploy] 顺延已登记|docs/tasks/t062_control_plane_boundaries/task.md:30-33；docs/pending/todo/p092_t062_local_image_verification.md|
|t062_code_f002|minor|已修|profile_lock 返回标注误写未导入的 AsyncContextManager，且遗留无用 import；已改标注并清 import|src/backend/cbrowser/services/profile_service.py:282|
|t062_code_f003|minor|已修|迁移残留无用 import（control_service 的 asyncio、fontconfig 的 os）已删，fontconfig docstring 同步改指 shared 原子写|src/backend/cbrowser/services/control_service.py；src/backend/cbrowser/runtime_agent/fontconfig.py|
|t062_code_f004|minor|已修|supervisor.md「禁止独立字面量」与 compose/探针实际保留字面量不符；已改实为非 Python 表面保留字面量、由边界测试对齐锁定|docs/blueprint/supervisor.md（共享规则与控制端口权威节）|
|t062_test_f001|important|已修|同 code 轴 f001：AC 未打勾与收尾报告矛盾；已打勾闭环|docs/tasks/t062_control_plane_boundaries/task.md:30-33|
|t062_test_f002|important|已修|端口权威守护盲区已补：runner 运行期默认值以 inspect.signature 断言、CLI 默认值以 AST 断言须引用常量名、compose 监督块三类端口面（command/healthcheck/跨服务 URL）全量提取对齐|tests/unit/test_t062_boundaries.py（test_supervisor_port_single_authority）|
|t062_test_f003|minor|已修|artifact 消费方投递分类补行为用例：422 永久拒绝只投递一次并标记已处理、503 不可用保留并在下一轮重试|tests/unit/test_download_reconciler.py（test_forwarder_delivery_classification_outcomes）|
|t062_test_f004|minor|已修|两处 AST import 图助手已解析相对 import（按文件所在包归一），跨包相对引用不再绕过守护|tests/unit/test_t062_boundaries.py（_cbrowser_refs）；tests/unit/test_a26_browser_image_modules.py（_top_level_cbrowser_refs）|
|t062_test_f005|minor|已修|交付文件（shared 新模块、新测试、p092）在 finish 前已全部 git add 暂存，git diff c5f8329 可见完整交付|git index（本轮 finish 前暂存）|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-005 的真实 Docker 构建/readiness 部分按 [deploy] 口径顺延本地，p092 登记）
- 测试：证据模式全量门禁（manifest 在 worktree `.scratch/gate_evidence_20261113/`）：protocol_drift_check PASS、requirements_check PASS、contract 257 passed/1 skipped PASS、design_lint PASS、design_check PASS、frontend_build PASS；unit 2012 passed/1 failed/1 skipped——唯一 failed 为 `test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip`，主仓 pristine c5f8329 同法同错误复现的既存基线失败（本链既定留终局处置、非本 task 引入）；integration 186 passed/7 skipped/2 errors——2 errors 均为隔离 API 子进程就绪超时（并行负载），串行复跑 2/2 passed，定性负载 flaky；frontend_test 618 passed/5 failed——5 条均为 5.5s+ 超时（profiles/settings 文件），受影响 5 文件单跑 45/45 passed，且本 task 零前端改动，定性负载 flaky。门禁首轮另有三组真实失败已逐项修复并复验：deploy.sh 内嵌 Python 仍 import 已删的 supervisor.file_storage（t027 文件 41 条连带失败，改指 shared.atomic_write 后整文件 74 passed）；preview 策略 chown 两条用例的注入点随原子写机制搬家更新（os.chown→os.fchown，契约断言保留）；a31 与 baseline 两条打包完整性测试断言的正是本 task 废除的旧打包形态（API 全量 COPY、Supervisor 借 Gateway 包），已按新契约改写并通过。
- 黑盒：云端无 Docker，e2e 与 real_engine 未运行（run_gates 未启 CBROWSER_RUN_E2E、real_engine NOT_RUN），按本链口径跳过按 pass 计；真实镜像构建/readiness 与非默认端口真实贯穿顺延本地（p092）。
- review：见上 Review 处置（full：code/test 双轴）。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 结果：中立包 `cbrowser/shared` 成为跨服务共享逻辑的唯一归属（endpoints、agent_credentials、atomic_write、profile_locks、delivery、fencing、egress），Gateway/Supervisor 互 import 清零，API 镜像改按包 COPY、新增 shared 模块不再改 Dockerfile，控制端口以 8005 单一权威消除 8091 分裂，API 路由与认证依赖改用领域会话对象、domain 不再承载 I/O 实现。AC-005..008 全部满足（AC-005 真实镜像部分与 AC-008 非默认端口真实贯穿按 [deploy] 顺延 p092）；审阅 Round 1 双轴 FAIL 的 9 条 finding 全部修复，Round 2 code/test 双轴均 PASS、四条 AC 均 TICK-VALID。收尾由主会话接手执行者未完成的 finish（执行者 23:04 无声结束，test 轴 Round 2 由主会话另行派独立复核补齐）。
- 遗留：p092（本地真实镜像构建/readiness 与非默认端口贯穿补验）；unit 基线失败 `test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip` 一条，按本链既定口径留终局门禁阶段处置。

### 长期文档闭环

在 specs_index 行的 task 清单中登记当前 tid（格式见 `.repo_template/docs/usage.md`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

- specs_index: not_applicable: 本 task 为包边界与镜像 COPY 形态收敛，无长期 spec 条目变更；长期真相侧已同步 `docs/blueprint/supervisor.md`（共享规则与控制端口权威节）。
- spike 闭环：跨镜像依赖闭包 spike 的结论已写入 `task.md`（中立归属为既有 shared 整包、shared 除 secret_files 叶子外零 cbrowser import 的硬约束、五镜像组装导入验证方式），采纳结论即本 task 的实现形态，后续由 p092 在本地补真实 Docker 验证，无需另立 finding。

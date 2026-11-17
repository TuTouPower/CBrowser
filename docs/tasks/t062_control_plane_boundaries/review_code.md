# Task review t062（reviewer_focus: 代码）

- task：`t062_control_plane_boundaries`
- spec：`docs/tasks/t062_control_plane_boundaries/task.md`
- diff_anchor：`c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- target：`git -C '<home>/workspace/CBrowser_t062' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- round：1
- reviewed_at：2026-11-13T22:58:18+08:00

reviewed_scope: ec0027fced40d5c9

## Findings

### t062_code_f001 - 四条 AC 全部未打勾，progress 却宣称「全部满足 / AC 判定见 task.md 行内打勾」

- 严重度：important
- 锚点：AC-005、AC-006、AC-007、AC-008 全部；实施打勾是 AC 完成声明，`task.md` 未打勾（`- [ ]`）的 AC 一律按未完成处理
- 位置：`docs/tasks/t062_control_plane_boundaries/task.md:30`（AC-005 至 `:33` AC-008 均为 `- [ ]`）；`docs/tasks/t062_control_plane_boundaries/progress.md:67`（「结果：全部满足」）、`progress.md:71`（「AC 判定：见 task.md 行内打勾」）
- 问题：本 reviewer 直接读 `task.md` 契约区，四条 AC 无一条打勾，与收尾报告的宣称矛盾。实现层经本轮独立复验（见「AC 复验方式」）大体成立，但打勾缺失使四条 AC 的完成声明无据可依，按 review 规则全部记 `TICK-VOID`，本轮 verdict 必须为 FAIL。这不是实现缺陷，而是交付状态未闭环：实施方须在复验实现后就地补打勾（AC-005 的 [deploy] 部分按 p092 顺延口径处理），或撤回 progress 的「全部满足」表述。
- 建议：实施方逐条复核实现证据后在 `task.md` 就地打勾并重派 review；若某条 AC 实际未完成，改 progress 收尾报告口径而不是补勾。

### t062_code_f002 - ProfileService.profile_lock 返回标注引用未导入的 AsyncContextManager，且遗留无用 import

- 严重度：minor
- 锚点：行为缺陷（类型契约错误）+ AC-007「路由通过 service 公开接口协调操作」的新增公开方法即此处
- 位置：`src/backend/cbrowser/services/profile_service.py:282`（`def profile_lock(...) -> AsyncContextManager[None]`）；同文件 `:14` 导入的是 `AbstractAsyncContextManager`，`:13` 的 `AsyncIterator` 与 `:15` 的 `asynccontextmanager` 在删除自有 ProfileLockRegistry 后已无任何使用点
- 问题：标注里的 `AsyncContextManager` 在本模块命名空间不存在（导入名是 `AbstractAsyncContextManager`）。因文件有 `from __future__ import annotations`，导入期不报错、本轮测试全过，但任何对该方法求值标注的工具（`get_type_hints`、类型检查、文档生成）都会 NameError，公开接口的类型契约是假的；同批删除还留下两个无用 import。
- 建议：标注改用已导入的 `AbstractAsyncContextManager[None]`（或从 `contextlib` 导入一致名称），并删除 `AsyncIterator`、`asynccontextmanager` 两个无用导入。

### t062_code_f003 - 锁/原子写迁移后遗留无用 import（control_service 的 asyncio、fontconfig 的 os）

- 严重度：minor
- 锚点：行为缺陷（死代码，迁移残留）
- 位置：`src/backend/cbrowser/services/control_service.py:16`（`import asyncio`，基线中仅被已删除的 `_lock_for`/`dict[str, asyncio.Lock]` 使用，现文件内无 `asyncio.` 使用点）；`src/backend/cbrowser/runtime_agent/fontconfig.py:28`（`import os`，原子写改走 shared 后文件内仅剩 docstring 一处文字提及 `os.replace`）
- 问题：本 task 的职责迁移删掉了这两个 import 的唯一使用点却未同步删除导入，属迁移残留死代码；运行时无害，但与本 task「删除重复/旧归属」的交付整洁性口径不符，也会给后续读者错误信号。
- 建议：删除两处无用 import。

### t062_code_f004 - blueprint 宣称 compose/就绪探针「禁止再出现独立字面量」，实现仍保留独立 8005 字面量

- 严重度：minor
- 锚点：AC-008（文档与实现不一致；端口值本身一致、无行为缺陷，故 minor）
- 位置：`docs/blueprint/supervisor.md:100`（「compose 与就绪探针全部与之对齐，禁止再出现独立字面量」）；实现侧 `compose.yaml:132`（`--port 8005`）、`compose.yaml:153`（healthcheck URL 中 `127.0.0.1:8005`）、`scripts/supervisor_readiness_probe.py:32`（`DEFAULT_BASE_URL = "http://127.0.0.1:8005"`）
- 问题：AC-008 要求的是同一权威值（8005 处处一致，runner/控制客户端已由 `shared.endpoints.DEFAULT_SUPERVISOR_PORT`/`DEFAULT_SUPERVISOR_URL` 派生，本 reviewer 已核实无 8091 残留、值无分裂），这一点成立；但 blueprint 把口径写成「禁止再出现独立字面量」，与 compose 三处、就绪探针一处仍存在的独立字面量不符（它们靠 `test_t062_boundaries.py` 的值一致断言锁定，是「对齐校验」不是「派生」）。`docs/blueprint/architecture.md` §5.6 的表述（「全部派生或与之对齐校验」）是准确的，supervisor.md 与之不一致。
- 建议：把 supervisor.md 该句改为与 architecture.md 一致的「派生或对齐校验」口径，或给 compose/探针补值一致守护后注明守护方式；不需改端口实现。

## 结论

- 本轮新发现：4 条（1 important、3 minor）
- 未进表的提示：文件过大——`src/backend/cbrowser/supervisor/core.py` 3232 行、`src/backend/cbrowser/services/profile_service.py` 1177 行均超实现源码 800 行阈值，core.py 本 task 净增 4 行、profile_service.py 净减 15 行；spec 明确「只拆本次边界相关职责，不以行数拆全仓大类」，按降级规则只在此提示、不进 finding 表。圈复杂度：本 task 新增/迁移函数均为平移或薄委托，无 CC≥15 函数。范围外观察：新增交付文件（`src/backend/cbrowser/shared/` 七个新模块、四个新测试文件、`docs/pending/todo/p092_t062_local_image_verification.md`）在 git 中仍是未跟踪状态（未执行 `git add -N`），不出现在 `git diff` 输出里；本 reviewer 已按 `git status` 逐个直读审阅，未构成 INCOMPLETE，但实施方收尾前应按派审规程补 `git add -N`。`src/frontend/node_modules` 为未跟踪杂物、非交付内容，未审。已知基线失败 `test_t060_gate_boundaries` 的 geoip 用例与本 task 无关，未报 finding（与派审说明一致）。
- 复验摘要（实现层，本 reviewer 独立执行）：以 gate venv + `PYTHONPATH=src/backend` 复跑两组最小集合全过——t062 boundaries/shared_rules/shared_atomic_write/auth/gateway_endpoint/agent_credentials 组 40 passed；image_closure（五镜像组装树实际导入）/t052 egress/event_delivery/preview/t052 runner/recovery 组 79 passed。逐项核对：gateway↔supervisor 互 import 已清零（AST 守护 + grep 复核，`supervisor/address_pool.py` 的命中是 Docker label 字符串非 import）；三份旧文件（gateway/endpoint.py、supervisor/agent_credentials.py、supervisor/file_storage.py）已删且全仓无旧 import 残留；shared 七模块除 `secret_files` 叶子外零 cbrowser import，Gateway/Browser/Supervisor 三镜像 requirements 均含 shared.egress/agent_credentials 所需的 httpx 与 pydantic，无真实镜像缺包；原子写所有权语义（O_EXCL 碰撞不误删他人暂存）有机制级用例且复跑通过；artifact_forwarder 改走 `classify_delivery_status` 后与原 RETRYABLE_4XX 分支语义等价（REJECTED 才标记 processed，其余落 else 提前返回）；认证六路由 + dependencies 已全换 `AuthenticatedSession`，domain/egress_observation 无 httpx/GeoIP/文件 I/O 定义；控制端口 8091 全仓清零（仅剩 shared/endpoints.py 注释与 decisions.md 历史叙述），runner 与 control_client 由同一常量派生。
- 总体判断：实现层质量过关、无 critical/行为缺陷类 important，但四条 AC 全部未打勾与 progress「全部满足」宣称矛盾，按门禁规则 TICK-VOID 必须 FAIL；补打勾（并处置三条 minor）后可重派复审。
- 系统性 follow-up：无（AC-005 真实 Docker 构建/readiness 与 AC-008 非默认端口真实贯穿已由实施方登记 `docs/pending/todo/p092_t062_local_image_verification.md`，本 reviewer 已核对该 pending 存在且内容覆盖这两项，不重复建议）

### AC 复验方式

- AC-005：TICK-VOID，re_verified。实现云端部分经复验成立（五镜像闭包组装导入复跑全过、Dockerfile 按包 COPY、跨服务逐文件 COPY 清零），真实 Docker 构建/readiness 按 [deploy] 顺延 p092；但 task.md 该 AC 未打勾（`- [ ]`），按规则打勾作废。
- AC-006：TICK-VOID，re_verified。原子写失败保旧/碰撞不误删、锁注册表同 Profile 串行异 Profile 并行、origin/fence/投递分类单一权威实现均经代码核对与相关测试复跑通过；但 task.md 该 AC 未打勾，按规则打勾作废。
- AC-007：TICK-VOID，re_verified。六个 router 与 auth/dependencies 已全换领域会话对象且无 SessionModel import、router 经 `ProfileService.profile_lock()` 公开方法协调、domain/egress_observation 已无 I/O 实现且业务测试复跑通过；但 task.md 该 AC 未打勾，按规则打勾作废。
- AC-008：TICK-VOID，re_verified。runner 与控制客户端已由 `DEFAULT_SUPERVISOR_PORT`/`DEFAULT_SUPERVISOR_URL` 派生、8091 清零、compose 与探针字面量值与权威值一致（边界测试复跑通过）；但 task.md 该 AC 未打勾，按规则打勾作废。

coverage = 4 / 4

verdict: FAIL

## Round 2 (2026-11-13T23:03:51+08:00)

- task：`t062_control_plane_boundaries`
- spec：`docs/tasks/t062_control_plane_boundaries/task.md`
- diff_anchor：`c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- target：`git -C '<home>/workspace/CBrowser_t062' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`（交付已全部暂存，`git diff --cached` 可见完整交付，105 文件）
- round：2
- reviewed_at：2026-11-13T23:03:51+08:00

## Findings

本轮无新发现（无 t062_code_f005 及后续编号）。

### 前轮 finding 复核

- t062_code_f001（important）：处置成立。`task.md:30-33` 四条 AC 现均为 `- [x]`；`progress.md` 收尾报告口径已与之对齐——「结果：全部满足（AC-005 的真实 Docker 构建/readiness 部分按 [deploy] 口径顺延本地，p092 登记）」「AC 判定：见 task.md 行内打勾」，不再有 Round 1 的自相矛盾。`docs/pending/todo/p092_t062_local_image_verification.md` 实存且内容覆盖两项顺延：AC-005 五镜像真实构建/独立启动/readiness、AC-008 默认与非默认端口真实贯穿。AC 声明与实现相符性本轮独立抽核成立：路由与 `auth/dependencies.py` 全仓 grep 无 `SessionModel`、`domain/models.py:59` 有 `AuthenticatedSession` 且 `auth/service.py` 返回它；后端源码与 compose/探针无 `8091`（仅 `shared/endpoints.py` 历史注释提及）；本轮自跑最小集合 47 passed（见结论），含五镜像闭包实际导入与端口权威守护。故四条打勾改判 TICK-VALID（AC-005 的 [deploy] 部分、AC-008 的真实贯穿部分以 p092 为顺延凭据，非云端已验，此口径与 Round 1 建议一致）。
- t062_code_f002（minor）：处置成立。`src/backend/cbrowser/services/profile_service.py:14` 现为 `from contextlib import AbstractAsyncContextManager`，`:281` `profile_lock(...) -> AbstractAsyncContextManager[None]`，标注名与导入名一致；`AsyncIterator`、`asynccontextmanager` 在该文件已无任何出现。实测（gate venv、`PYTHONPATH=src/backend`）：模块可导入，`typing.get_type_hints(ProfileService.profile_lock)` 成功求值、返回 `contextlib.AbstractAsyncContextManager[None]`——Round 1 所述 NameError 隐患已消除（progress 处置表把方法记为 `:282`，实际在 `:281`，一行之差、不影响处置成立，不另立 finding）。
- t062_code_f003（minor）：处置成立。`services/control_service.py` 已无 `import asyncio` 与任何裸 `asyncio.` 使用点（仅剩 `sqlalchemy.ext.asyncio` 的 `AsyncSession` 导入，属另一模块），锁改用 `shared.profile_locks.ProfileLockRegistry`；`runtime_agent/fontconfig.py` 已无 `import os` 与 `os.` 使用点，docstring（`:141-142`）改为「The file lands via the shared atomic write (cbrowser.shared.atomic_write)」，实现 `:148` 调 `atomic_write_text(target, xml, mode=0o600)`、`:31` 自 `cbrowser.shared.atomic_write` 导入。实测两模块均可导入，`hasattr(module, "asyncio")` / `hasattr(module, "os")` 均为 False，无残留引用。
- t062_code_f004（minor）：处置成立。`docs/blueprint/supervisor.md:100`（新增「共享规则与控制端口权威（t062）」节）现措辞为：runner 的 `--port` 默认值与控制客户端默认 URL「直接派生自该常量；compose 与就绪探针等非 Python 表面保留字面量，但由边界测试逐一与权威值对齐锁定，禁止出现不一致的字面量（历史 8091 分裂已消除）」——与 `architecture.md:163` 的「全部派生或与之对齐校验」口径一致，且与现状相符：`compose.yaml:34`（`supervisor:8005`）、`:132`（`--port 8005`）、`:153`（healthcheck `127.0.0.1:8005`）、`scripts/supervisor_readiness_probe.py:32`（`DEFAULT_BASE_URL = "http://127.0.0.1:8005"`）四处字面量均为 8005、与权威值一致，无不一致字面量。

### test 轴补强抽核（非本轴处置，仅查与实现矛盾）

未发现与实现矛盾，不立新 finding。三处补强均实存且在本轮自跑集合内通过：① 端口守护 `test_t062_boundaries.py::test_supervisor_port_single_authority` 已断言 runner 运行期签名默认值（`inspect.signature`）、CLI 默认值须为 AST `Name` 且名为 `DEFAULT_SUPERVISOR_PORT`、compose 三类端口面（`--port`、healthcheck `127.0.0.1:`、跨服务 `supervisor:`）全量提取比对、探针含权威值；② 相对 import 解析已进 `_cbrowser_refs`（`test_t062_boundaries.py:54-55` 按文件所在包归一）与 `test_a26_browser_image_modules.py` 的 `_top_level_cbrowser_refs`，逻辑抽核无误（level≥2 跨包引用可命中、包内引用只记本包名不误报跨服务）；③ artifact 分类用例 `test_download_reconciler.py::test_forwarder_delivery_classification_outcomes` 以参数化覆盖 422（只投递一次、标记已处理）与 503（保留并下一轮重试），与 `artifact_forwarder` 走 `classify_delivery_status` 的实现一致。

## 结论

- 前轮 finding 复核：4 条全部处置成立（1 important + 3 minor），逐条依据见上，均由直读文件 + grep + 导入/`get_type_hints` 实测 + 测试自跑支撑，未采信处置表自述。
- 本轮新发现：0 条。
- 复验摘要（本 reviewer 独立执行）：落点校验 `git rev-parse --show-toplevel`（在 worktree 内、不带 `-C`）= `<home>/workspace/CBrowser_t062`、分支 `t062_control_plane_boundaries`、基线 `c5f8329`；以 gate venv + `PYTHONPATH=src/backend` + `TMPDIR=.scratch/tmp` 自跑 `test_t062_boundaries.py`、`test_t062_shared_rules.py`、`test_shared_atomic_write.py`、`test_t062_image_closure.py`、`test_download_reconciler.py` 共 47 passed；另以同一 venv 做 `profile_service`/`control_service`/`fontconfig` 三模块导入与标注求值验证，全过。
- 总体判断：Round 1 的 FAIL 主因（AC 打勾闭环）与三条 minor 均已真实修复，四条 AC 打勾与实现、progress 口径三者一致，无 critical/important/minor 遗留，code 轴 verdict PASS。AC-005 [deploy] 真实镜像验证与 AC-008 非默认端口真实贯穿仍待本地 p092 补验，属已登记顺延、不阻断本轴判定。
- 系统性 follow-up：无（顺延事项已登记 p092，不重复建议）。

### AC 复验方式

- AC-005：TICK-VALID，re_verified。task.md 已打勾；云端部分（中立包导入、Gateway/Supervisor 零互 import、按包 COPY、五镜像闭包组装实际导入）经本轮自跑复验成立，真实 Docker 构建/readiness 按 [deploy] 顺延 p092（pending 实存且内容覆盖）。
- AC-006：TICK-VALID，re_verified。task.md 已打勾；原子写、锁注册表、origin/fence/投递分类单一权威经代码抽核与 shared_rules/atomic_write/download_reconciler 测试自跑通过。
- AC-007：TICK-VALID，re_verified。task.md 已打勾；路由/认证依赖无 SessionModel（grep 实测）、`AuthenticatedSession` 在位、`profile_lock()` 公开方法标注自洽（f002 复核）、domain egress 无 I/O 的边界守护在自跑集合内通过。
- AC-008：TICK-VALID，re_verified。task.md 已打勾；runner/控制客户端派生、8091 清零、compose 与探针字面量与权威值一致，且守护已覆盖 runner 与 healthcheck 表面（test 轴补强抽核通过）；非默认端口真实贯穿顺延 p092 第 2 项。

coverage = 4 / 4

reviewed_scope: 6feea54970e59850

verdict: PASS

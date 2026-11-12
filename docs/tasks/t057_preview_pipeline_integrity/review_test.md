# Task review t057（reviewer_focus: 测试）

- task：`t057_preview_pipeline_integrity`
- spec：`docs/tasks/t057_preview_pipeline_integrity/task.md`
- diff_anchor：`ff253095dec4ba070c22d69e221730db383ec30b`
- target：CBrowser_t057 内 `git diff ff253095dec4ba070c22d69e221730db383ec30b`
- round：1（预审历史）
- reviewed_at：2026-11-12T09:39:59+08:00 起

reviewed_scope: d6987d5b40340c02

## Findings

### t057_test_f001 - 存储格式迁移留下恒真清除断言

- 严重度：important
- 锚点：行为缺陷：关闭预览的测试不能证明实际帧文件被删除；旧测试迁移规则。
- 位置：Round 1 快照 `tests/unit/test_supervisor_preview_policy.py:148`、`:158`，`test_disabled_policy_clears_existing_preview`；另涉及两份 preview integration 文件的旧格式用例。
- 问题：前置已改用 `frame_path` 创建新格式帧，关闭后却仍断言从未创建的 `latest.jpg` 不存在，删除真实帧的行为可能退化而该断言继续通过。部分生命周期/复制用例仅就地更换旧格式预期，未按失效语义整体替换。
- 建议：整体替换旧格式用例，播种当前帧和保留帧，验证全部实际帧及 meta 清除；复制场景同时验证目标无帧且源帧保留。

### t057_test_f002 - E2E把切换前的新帧误当成切换后帧

- 严重度：important
- 锚点：AC-006 测试可信；正确截图管线仍可能被测试误判失败。
- 位置：Round 1 快照 `tests/e2e/test_profile_preview_e2e.py:157`、`:215`、`:222`，原 `next_frame`。
- 问题：读取 A1 后进行多个 HTTP/CDP 操作，正常采集周期可能先提交另一张切换前 A2。仅以 ETag 不同为屏障会立即接受 A2，随后把正确实现误判为 B 布局错误；切回 A 同样存在。直接编译原测试 helper 的 AST、在 HTTP 边界返回合法 A2 JPEG，已确定性复现该假失败。
- 证据：`.scratch/t057/test_review/reproduce_waiter_race.py`、`waiter_race.json` 与 `e2e_waiter_snapshot.py`。
- 建议：保留原40秒预算和严格图像结构断言，同时等待新 ETag 与预期空间结构，不用 ETag 单独推断采集时序。

## 结论

- 本轮发现2项 important；当时全部 AC 尚未勾选、真实验证未闭环，不能给 PASS。
- 改测方向复核：新存储格式测试迁移不完整；旧 CDP 测试随用户批准的整张浏览器截图范围失效，可以整体替换，但不能留下恒真断言。
- 本轮历史与独立复现保存在 `.scratch/t057/test_review/`；不以后续修复覆盖原发现。

### AC 复验方式

- AC-001：TICK-VOID，trust_prior。当时尚未勾选且完整验证未闭环。
- AC-002：TICK-VOID，trust_prior。当时尚未勾选且完整验证未闭环。
- AC-003：TICK-VOID，trust_prior。当时尚未勾选且完整验证未闭环。
- AC-004：TICK-VOID，trust_prior。当时尚未勾选且完整验证未闭环。
- AC-005：TICK-VOID，trust_prior。当时尚未勾选且完整验证未闭环。
- AC-006：TICK-VOID，trust_prior。当时尚未勾选且 E2E 时序证据不足。
- AC-007：TICK-VOID，trust_prior。当时尚未勾选且完整验证未闭环。
- AC-008：TICK-VOID，trust_prior。当时尚未勾选且完整验证未闭环。

coverage = 0/8

建议合并前人工抽查 trust_prior 项；本历史轮结论已在下轮重新逐项复核。

verdict: FAIL

## Round 2 (2026-11-13T07:40:02+08:00)

reviewed_scope: b75df5c9c154d64d

### Findings

本轮零新增 finding。

### 结论

- t057_test_f001 复核已消除：旧用例整体替换为 `test_supervisor_revocation_removes_all_immutable_frames_and_metadata`、`test_lifecycle_removes_every_immutable_preview_frame` 与 `test_browser_state_clone_excludes_current_and_retained_preview_frames`；均播种两帧并检查真实帧集合、meta及源/目标隔离，不再依赖旧文件名空断言。
- t057_test_f002 复核已消除：`wait_for_layout_frame` 在原40秒预算内同时检查新 ETag 与严格空间结构，外层结构断言保留。独立执行新 helper 原始 AST，A2→B 序列确实请求两次、拒绝 A2、接受 B，见 `.scratch/t057/test_review/verify_waiter_fix.py`、`waiter_fix.json`。
- 改测方向复核：无迁就实现的改测。删除 A13 截图 CDP 会话测试及 CDP viewport 参数测试，因为生产已不再创建截图 CDP 会话；新显示采集、坏帧、撤销及真实双标签 E2E 覆盖替代行为。生命周期、复制与前端旧裁剪语义用例已整体替换。三份集成 `_Chain` 仅补真实 display 与 Xauthority 元数据，原行为断言/超时不变；裸 Xvfb 场景未启用预览策略，不冒充截图认证验证。
- d041 为用户追加授权范围：两处策略 helper 改为先 create 持有句柄再 start，unit doubles 仅适配 SDK 边界，原断言保持。真实 Docker 红灯残留1、绿灯残留0，原失败真实 E2E 原样定向复验通过；没有换故障镜像、取消零残留断言或增加等待预算。
- 独立验证披露：预审独立执行预览后端72 passed/8 deselected、前端2 passed及上述 AST 复现；末轮对最终源码、测试断言、JUnit、manifest和镜像源码哈希重新核对，未违反用户要求再次启动全量门禁或争抢真实拓扑。当前 Browser/API/Supervisor 的关键源码哈希与 `image_sources.json` 全部一致。
- 证据统计已直接解析：完整B unit1676 passed、integration180 passed/18 host skips、contract257 passed/1 policy skip，均0 failed；前端日志502 passed。B真实E2E102 passed/1 failed/2 optional skips，唯一失败为 d041 对应用例，原始 manifest 的 all_passed=false 保留。用户明确要求修复后只重跑该用例，`policy_fix_e2e.xml` 为1 passed/0 failed/0 skipped、6.41秒；不将分轮结果相加冒充新整轮全绿。协议、依赖锁、设计lint/check、类型、构建及五镜像包检查在B均0退出。
- 跳过边界：宿主18项集成已由 `container_integration/integration.xml` 补验18 passed/0 skipped；默认2项容器探针由独立 `gate_B_real_engine/probe.xml` 补验2 passed/0 skipped；contract1项为显式项目策略不适用。未把宿主缺 Xvfb/独立 Chromium 写成已安装或已执行。
- 危险模式扫描：未见新增 skip/only、忽略类型检查、恒真主验收断言或阈值放宽。HTTP/CDP/SSE、截图输入和故障写入的替身用于边界/故障注入，生产权限、重试、帧校验、存储与缓存逻辑保持可达；参数化正反例都有无条件主断言，不因条件分支空过验收。
- 七视角已核对：安全（关闭围栏、认证、无宿主回退）；正确性（重试、pending与字节快照）；契约/Breaking（已授权截图范围、存储语义及夹具升级）；性能/资源（原采集参数、过期帧回收及零残留）；架构/可维护性（复用真实生产模块）；健壮性/可观测（坏帧、失败封闭与warning）；测试/文档/规格（AC、来源、发现及补验边界）。本轴无新增未解决问题。
- 本轮新发现：0条。未进表提示：无。系统性 follow-up：无。
- 总体判断：8项打勾均有可信证据；用户批准的定向验证口径已准确披露，当前无未解决 critical/important，PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`test_disabled_same_epoch_rejects_capture` 与 `test_disabled_policy_same_epoch_never_notifies_or_updates` 直接验证同epoch关闭后DB时间戳和SSE均不更新；已核对生产分支及B证据。
- AC-002：TICK-VALID，re_verified。`test_observation_failure_retries_same_frame` 的HTTP/transport两类失败均同帧重试后成功且有脱敏warning，另有无效观测不污染缓存与限频断言。
- AC-003：TICK-VALID，re_verified。`test_preview_retry_reuses_request_id`、`test_preview_old_success_cannot_remove_new_pending` 验证原请求ID复用和6/7并发顺序；Supervisor重复请求分支另有真实生产方法测试。
- AC-004：TICK-VALID，re_verified。`test_reader_keeps_open_frame_across_replacement_and_clear` 与 `test_response_remains_consistent_if_files_are_cleared_before_send` 检查同帧字节及ETag；metadata失败与旧帧保留测试已核对。
- AC-005：TICK-VALID，re_verified。并发policy写入三方屏障、O_EXCL名称碰撞及失败清理测试验证暂存所有权；目录锁仅按d039声明覆盖同Linux内核，不伪称跨Mac/VM互斥。
- AC-006：TICK-VALID，trust_prior。已独立审查严格空间结构、整张480×270画面与A→B→A断言，实际Docker/Profile截图证据依赖B内两项预览E2E均PASS及认证探针；本review未另起真实拓扑重跑。
- AC-007：TICK-VALID，re_verified。格式、尺寸、截断、补EOI损坏帧、合法纯色以及jpeginfo缺失/超时测试均触达真实capture loop或严格校验器；已核对B与真实容器帧校验断言及d040。
- AC-008：TICK-VALID，re_verified。缓存未知/关闭、列表详情冲突、时区偏移旧事件、非法时间及迟到事件测试覆盖真实hook；卡片开关关闭后立即隐藏原图另有组件测试。

coverage = 7/8

verdict: PASS

---
tid: "t057"
slug: "preview_pipeline_integrity"
title: "预览管线完整性与隐私收口"
status: "done"
branch: "t057_preview_pipeline_integrity"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "ff253095dec4ba070c22d69e221730db383ec30b"
depends_on: ""
conflicts_with: "t055"
note: "来源 review_20261110_200842 adoption_decision A32-A38"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- run-begin 已完成：owner_id=local_t057_20261112，attempt=1，execution_id=39f43bd3762046ddbbfba46eead1a53c，branch=t057_preview_pipeline_integrity，base=main@12380b25a51fc0dc51a7b00306e93684715f6b3f，worktree=<repo>\_t057。主仓开始时干净，未改 main / 其它 task / t060。

- preflight=PASS（1条UNVERIFIED-SPIKE警告），当前仅允许先验证真实引擎多标签可见性。现行d035声称各页恒visible，与A36待核对；先实测再确定方案，不假定活动页可见性可靠。

- 已完整读task、A32–A38来源与相关spec/blueprint；引用存在性记录在.scratch/t057/reference_audit.json。spec中的docs/tasks/t040旧路径不存在，实际docs/archive/tasks/t040路径存在；s016仍位于docs/spikes/，归档目录不存在。已按逐项存在性结果记录，不套用统一归档假设。

- 修改产品代码前先验：`tests/unit/test_repo_hygiene.py` 实跑1 failed / 7 passed，失败为既有tracked家路径检查；日志保存在.scratch/t057/baseline_hygiene.log。未改范围外文档，未引入t060，已请求用户裁定基线失败的最终验证口径。该失败不记环境跳过、不冒充全绿。

- 来源第100项涉及5209eec / 73b9c41，Git对象均存在且类型commit；12380b2亦核对为commit。审阅第92–100项及未证实_preview\_\*状态清理疑点已对应A32–A38核对。

- 2026-11-12T05:52:29+08:00：真实Docker/Xvfb引擎实验完成，普通Playwright与生产SDK两路径各3次切前台，三个测试标签的主世界/隔离世界始终全部visible，且每路径window_id相同。d038已通过findings.py分配并写入实测结论；task未知契约由UNVERIFIED-SPIKE改为已验证事实与待裁定的UNVERIFIED-BLOCKING，未改任何AC。探针容器已退出且无残留。

- 当时两项裁定等待中（后续base裁定见恢复记录）：①指定base原有隐私门禁失败是否获明确基线豁免；②A36可见性判定与AC-006多标签行为目标冲突如何处理。未修改产品代码或测试，AC仍0/8，不将准备和实验冒充实施完成。

- 2026-11-12T06:10:27+08:00：用户明确授权改为从t060完成分支继续。备份3份交付文档、runtime和全部.scratch后，用task.py rewind/start --base t060_gate_infra_and_privacy重建t057；base及diff_anchor=ff253095dec4ba070c22d69e221730db383ec30b。通过reserve/claim恢复attempt=2、execution_id=83fe024238794ec3a49b7a02ff86bf69、owner_id=local_t057_20261112。main保持原HEAD且干净，t060分支未改；旧base失败记录仅为历史证据，不再请求旧基线豁免。截图范围待确认：现行网页viewport与用户提出整张浏览器画面存在差异，暂不修改AC-006及产品逻辑。

- 新base抽验：真实运行tests/unit/test_repo_hygiene.py，6 passed，exit=0。旧main基线家路径失败已随继承t060实现消除；该抽验不代替全量门禁。git diff --check通过；main工作区干净、HEAD仍12380b2，t060分支仍ff253095。产品代码及测试仍未修改。

- 2026-11-12T06:13:32+08:00：用户明确确认整张浏览器画面，包含标签栏/地址栏。已将A36与AC-006同步为此范围；旧CDP可见性方案撤销，7项其它AC保持。恢复attempt=3，execution_id=430b3b3e7d1d43ab833b60f26eec1ce7，owner不变。先验证Pillow/XCB独立显示采集，再严格preflight、TDD与全量门禁。

- Pillow13/XCB真实容器探针通过：1280×800独立显示、480×300 JPEG、两个标签0→1→0均反映前台内容且保留浏览器界面。task/spec/browser_runtime已同步用户范围，未知契约已替换实测结论。旧CDP viewport/首target/attach/detach测试整体失去生产语义，将删除并由独立显示截图及失败封闭测试替代；不改旧预期来追随实现。

- TDD第一轮：权限/重试/并发暂存7 failed，快照读取1 failed，完整显示/帧校验10 failed，前端围栏2 failed，均触达生产逻辑。修复后预览后端专项77 passed；前端围栏2 passed。继续扩充中断/清除/缓存冲突验证，未将专项结果当作全量通过。

- 存储契约改为metadata选择不可变帧；旧latest.jpg专用预期失效，生命周期清除/复制测试改验全部帧集合与meta，保留原业务行为。删除旧CDP参数测试和A13 attach/detach整组，原因：生产截图不再创建CDP会话；由整张显示、格式/尺寸/撤销/失败封闭测试接替。JPEG坏帧/纯色检查以完整解码及尺寸为准；E2E旧中心均色判据整体替换为两页空间结构与界面区域校验。

- 真实预览E2E首轮2 failed：两项均在50秒首帧等待超时，未到内容断言；真实Xvfb认证探针证实无XAUTHORITY时ImageGrab报OSError，传Runner cookie文件后成功1280×1024。首次探针直接以xvfb-run作容器PID1卡在信号握手，已仅清理自身容器，改带--init后探针正常完成，不记环境跳过。

- 认证接线TDD先红1 failed（生产run_uds_agent缺少XAUTHORITY），修复为Agent启动时校验并加载Runner独立cookie；认证及Agent故障回归41 passed。Browser/API/Supervisor均COPY runtime_agent，因此仅这3个受影响镜像重建；Gateway/Stream镜像复用最终已验证ID。

- 普通门禁A的unit为1665 passed/1 failed，失败是既有Coordinator十五轮DB重试测试5秒未收敛；当轮与镜像构建并发，尚不推断原因、不改超时/断言，待原样复验。前端501 passed及构建已通过；完整A结果待manifest。

- 认证修复后真实预览E2E 2 passed（129.17秒）：整张浏览器界面、双布局标签切换及切回、HTTP/ETag/鉴权、关闭/重启用预览、停止保留及容器内损坏帧/纯色帧校验均已执行。

- 既有Coordinator重试测试原样复验1 passed（0.99秒），未改断言或5秒预算；最终仍需整轮门禁复验，A不记通过。

- Round1独立review发现：t057_test_f001（important，旧latest断言恒真）已整体替换为两帧清除/复制测试；t057_test_f002（important，ETag变化不能证明采于切换后）按原40秒预算同时等待新ETag与严格布局，独立AST复现先红、修复后拒绝A2并接受B。t057_code_f001（important，metadata异常孤帧）、f002（minor，过期旧格式帧未回收及文档失真）新增回归先红2 failed/1 passed，修复后存储相关44 passed。全部AC仍0/8，未提前勾选。

- d039记录双侧实测：目录flock仅同一Linux内核内互斥，Mac宿主/VM不互通；初始“三方均互通”探索断言失败如实保留。生产全Docker拓扑采用目录inode锁，fd字节快照不依赖跨VM互斥；非全局策略事务。

- 容器补验首轮1 passed/17 failed，原因是3份集成链手写Runner metadata缺display/xauth_path。已在16处调用中传入实际display，Runner路径传真实cookie，裸Xvfb仅建私有空认证文件；未改行为断言/超时/skip。重跑18 passed（116.91秒），含独立Chromium156与目标引擎146；这些用例不作为截图认证证据。

- t057_code_f003（important）：Pillow容错接受补回EOI的截断熵数据。新增坏帧回归先红1 failed/4 passed，缺工具及超时回归先红2 failed。Docker实测jpeginfo1.7.1的--check -：合法纯色0、损坏帧1；无位置参数的--check --stdin两者均1，未采纳错误接口。

- Mac严格检查工具从上游v1.7.1实际构建到本task scratch，未写系统安装。d040记录依据；Pillow格式/尺寸检查与jpeginfo严格码流检查均在工作线程执行。修复后预览专项85 passed，独立review亦证明坏帧拒绝、合法白帧接受。

- 最新Browser构建因APT代理502退出100，当前tag仍是旧镜像，不将其冒充新版本。API/Supervisor已成功；继续时仅补完Browser构建，本次清空build代理参数，不改机器配置、不重建其它镜像。

- 附加全仓Markdown检查发现既有归档格式差异，不改范围外文件；本次修改文档单独按compact模式校验。Ruff变更范围零新问题，51项未变基线诊断如实登记；项目设计lint/check、类型和构建仍由全量门禁执行。

- 卡片补充：完整预览等比显示，不同比例不裁掉浏览器界面；关闭缓存开关即隐藏旧帧。关闭场景先红1 failed/5 passed，修复后卡片与SSE专项8 passed。原object-cover样式断言因新截图范围失效，旧用例整体替换为URL/懒加载契约，不靠CSS类名断言制造通过。

- Browser最新构建已完成；原依赖与Python包层复用，仅独立安装jpeginfo。未修改机器代理配置。镜像内全部关键修改模块与工作区哈希一致，jpeginfo实际版本1.7.1，证据image_sources.json/prepare_gate.log。

- 完整门禁B普通部分通过：unit1676/0 failed，integration180/0 failed/18 host skips，frontend502/0 failed，contract257/0 failed/1 policy skip；协议、依赖锁、设计lint/check、类型、构建、五镜像包检查均0退出。2 worker执行全量，原断言与超时未改。

- 完整E2E并行部分43 passed/1 failed/2 optional skips；失败为策略helper OCI启动异常残留一个created容器，非超时。测试finally已清理。原DockerAdapter未被本task修改，暂不自行扩范围。

- 最小实Docker复现直接调用生产_run_policy_helper，得到APIError且残留created helper计数1，复现finally精确清理自身资源；证据oci_helper_repro/result.json。最小create/start拆分补丁仅存proposed_helper.patch，尚未写入生产文件；已请求用户裁定是否纳入t057。

- 补核spec引用：旧docs/plan_20261105_ui_redesign.md不存在，实际docs/archive/plans/plan_20261105_ui_redesign.md存在；已核对6.7/WP13并修正当前spec引用，不改归档原文。

- 完整门禁B已结束：manifest all_passed=false、cleanup_exit_code=0，唯一失败suite为e2e。最终E2E102 passed/1 failed/2 optional skips；独立real_engine2 passed/0 failed/0 skipped，evidence all_passed=true。未放宽断言、未换故障镜像、未跳过失败用例；d041登记既有helper残留事实，等待用户范围裁定。

- 2026-11-12T16:23:39+08:00：严格preflight因d041范围裁定未决而FAIL；已按task-run将attempt 3登记blocked并保留worktree，控制面仅写terminal/report。main工作区仍干净、HEAD仍12380b25；DockerAdapter未修改，任务HEAD仍ff253095，AC 0/8。恢复须在主仓先运行task.py recovery t057，不重复run-begin。

- 2026-11-12T16:32:57+08:00：用户明确授权纳入d041最小修复，并要求修复后只重跑此前失败的真实E2E、不重复全量。已按recovery恢复attempt 4，execution_id=eb4aef1a07394f27b06a6c000a4a44c0；既有全量B结果保留，定向重验单列，不改写B为全绿。继续使用task-run/task-work流程。

- d041修复前真实Docker探针再次红灯：created残留1；修复后同探针绿灯：残留0。进一步核对表明B直接失败于_install_network_policy，原独立探针覆盖_run_policy_helper；两条策略路径均已最小拆分create/start。旧unit夹具只适配SDK调用，原断言未变。仅API/Supervisor镜像包含该新增修改，增量构建2个，其余3个复用。

- 2026-11-12T16:37:25+08:00：API/Supervisor增量镜像构建成功，镜像内新增Adapter与全部变更模块哈希核对一致；原失败真实E2E原样重跑1 passed/0 failed/0 skipped（6.41秒）。故障镜像、零残留断言及原超时均保持；用户明确免重复全量，B原manifest仍为false，定向复验单列。当前Ruff变更范围零新问题，54项未变基线诊断保留（新增检查Adapter及夹具后计数变化）。

- 2026-11-13T07:40:07+08:00：credits恢复后续行，自核现场无变化：HEAD ff253095、分支t057_preview_pipeline_integrity、交付改动47项，AC8/8；attempt4仍running且owner一致。正式报告未写，双路review已从既有审查结论恢复，最终scope仍b75df5c9c154d64d；不重复全量或已通过定向E2E。main仍干净、HEAD12380b25。

- 2026-11-13T07:42:23+08:00：正式末轮双路review完成，code/test均PASS，Round2、scope=b75df5c9c154d64d、ac_review=ok、next_action=finalize；新增finding0。代码轴8/8独立复核，测试轴7/8独立复核，AC-006实际Docker执行如实依赖已产出的真实E2E证据。五项历史finding均已修，无未处置项；进入task.py finish单一实现提交与push收尾，不创建中间实现commit。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-12T16:01:03+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t057_code_f001|important|已修|metadata异常不累计孤帧且保留已选中同名帧|src/backend/cbrowser/preview.py|
|t057_code_f002|minor|已修|回收过期旧格式帧并同步真实读写契约|src/backend/cbrowser/preview.py; docs/specs/profile_preview.md|
|t057_code_f003|important|已修|严格拒绝libjpeg容错警告，合法纯色仍通过|src/backend/cbrowser/runtime_agent/preview_capture.py|
|t057_test_f001|important|已修|整体替换旧格式测试，验证真实帧集合清除/复制|tests/unit/test_supervisor_preview_policy.py; tests/integration/test_preview_clear_on_lifecycle.py|
|t057_test_f002|important|已修|原40秒预算内同时等待新帧及严格预期布局|tests/e2e/test_profile_preview_e2e.py|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：t057实施、用户要求的验证与正式full双路review均已完成，AC 8/8。仅在t057_preview_pipeline_integrity分支由task.py finish生成单一实现提交与执行回执；远端交付目标为origin同名分支，不合入main。finish提交号以任务分支tip及最终回复为准。
- 测试：完整B的unit1676 passed/0 failed、integration180 passed/0 failed/18 host skips、frontend502 passed/0 failed、contract257 passed/0 failed/1 policy skip；协议、依赖锁、设计lint/check、类型、构建及五镜像包检查通过。d041修复后按用户明确要求不重复全量，仅定向复验；旧unit夹具仅适配create/start，原断言保持。当前变更范围Ruff零新问题，54项未变基线诊断保留；变更Markdown已校验。
- 黑盒：完整B真实E2E102 passed/1 failed/2 optional skips，唯一失败为既有策略helper在OCI启动异常后残留created容器。用户授权纳入最小修复后，原失败E2E原样定向复验1 passed/0 failed/0 skipped（6.41秒），证明失败封闭、API状态收敛、端口释放及容器/网络零残留。B原始all_passed=false如实保留，不将分轮结果冒充最终全量重跑。独立真实引擎2 passed/0 failed/0 skipped，evidence all_passed=true；宿主跳过18项已在容器专项补验18 passed。
- review：full双路Round2均PASS，最终scope=b75df5c9c154d64d；checker的review_scope=ok、ac_review=ok、next_action=finalize。五项历史finding均已修复独立复验，新增finding0；两份报告保留首轮FAIL历史。代码轴复核8/8，测试轴7/8独立复核，AC-006实际Docker执行据实依赖既有证据。
- AC判定：以下逐项证据来自生产逻辑测试及真实Docker验证；8项均已打勾，双路reviewer已逐项确认TICK-VALID。

|AC|实施与验证证据|
|---|---|
|AC-001|repository capture_preview开关检查；test_disabled_same_epoch_rejects_capture覆盖同epoch关闭后拒绝时间戳与事件|
|AC-002|Supervisor仅上报成功后去重；test_observation_failure_retries_same_frame覆盖失败重试，invalid_observation与warning限频回归|
|AC-003|Coordinator pending保存完整首次请求并比较后删除；request_id重用、旧成功不删除新pending、Supervisor重复请求测试|
|AC-004|meta选择不可变帧，同一打开fd读取并由同份字节生成ETag；清除/替换过程中快照与HTTP响应一致性回归|
|AC-005|uuid与O_EXCL独占暂存，只有所有者清理；并发policy写入及暂存名碰撞测试；d039限定同Linux内核容器锁语义|
|AC-006|真实Profile Xvfb认证显示采集；两个结构不同标签前台A→B→A及浏览器界面区域E2E通过；卡片等比整图显示|
|AC-007|Pillow完整解码和jpeginfo严格码流校验；截断及补回EOI损坏帧拒绝、合法纯色接受，真实容器capture loop校验|
|AC-008|SSE以明确开启缓存与Date.parse单调时刻为围栏；列表/详情冲突、迟到关闭事件及卡片关闭隐藏测试|

### 结果摘要

- 用户已确认整张Profile浏览器画面含标签栏/地址栏；task、spec和blueprint已同步，不采集宿主桌面。
- 用户追加授权d041两条策略helper路径修复；create后即持有句柄，start失败仍执行原finally。真实Docker复现先红残留1、后绿残留0；原失败E2E已通过。
- 分支t057_preview_pipeline_integrity，base与diff_anchor为t060完成提交ff253095；不合入main、不改t056/t060分支。
- 引用审计、TDD红绿、真实引擎、Docker构建与review复现证据当前位于本worktree的.scratch/t057，finish后流程清理前将完整移至同级CBrowser_t057_evidence/.scratch/t057保留；旧缺失引用已按实际归档位置修正，未虚构提交或文件。
- 环境跳过：integration宿主18项因无Xvfb或独立Playwright Chromium跳过，已在容器用独立Chromium156与目标引擎146补验18 passed；E2E默认2项t032 probe通过独立real_engine补验2 passed；contract1项因项目显式验证策略而不适用，不冒充执行通过。
- 用户明确不重复全量，故不将定向复验视作一轮新的全量通过；本轮未放宽超时、未替换故障镜像、未跳过失败用例。

### 长期文档闭环

- profile_preview spec与specs_index已登记t057；browser_runtime、supervisor、security、testing已同步采集范围、认证、严格校验及一致性契约。
- d038记录多标签可见性与采集认证；d039记录OrbStack目录锁边界；d040记录JPEG容错与严格检查依据；d041记录策略helper启动泄漏修复与真实验证。
- docs/handoff.md仅保留最新t057一节，记录实际写入时branch与HEAD；继承的旧交接段落原样追加到archive/handoff.md，历史内容未改写。

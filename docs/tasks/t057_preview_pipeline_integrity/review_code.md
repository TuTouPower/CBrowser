# Task review t057（reviewer_focus: 代码）

- task：`t057_preview_pipeline_integrity`
- spec：`docs/tasks/t057_preview_pipeline_integrity/task.md`
- diff_anchor：`ff253095dec4ba070c22d69e221730db383ec30b`
- target：任务工作区完整`git diff ff253095dec4ba070c22d69e221730db383ec30b`，包含新交付文件。
- round：2
- reviewed_at：2026-11-13T07:41:23+08:00

## Round 1 (历史预审补录)

首次派审时AC均未勾选，门禁尚在执行。本节保留实际独立预审发现与当时未完成结论；不将修复后结果倒填为首轮PASS。历史快照指纹来自初次渲染prompt，最终交付由Round 2重新核对。

reviewed_scope: d6987d5b40340c02

### Findings

### t057_code_f001 - metadata发布失败累计私密孤帧

- 严重度：important
- 锚点：行为缺陷；metadata持续写失败时，每轮截图留下新私密帧，存储持续增长且绕过正常回收。
- 位置：`src/backend/cbrowser/preview.py:commit_preview`初审版本的帧写入、metadata写入与其后的回收循环。
- 问题：以实际文件系统将`meta.json`设为目录，三次提交均抛`IsADirectoryError`，却留下三张JPEG；即使将其mtime设为过期，下一次metadata失败仍不会运行回收。问题已独立复现，非仅依赖实施方描述。
- 建议：发布失败时清理自身未发布帧，保留当前metadata选中的同名快照；发布、清除、回收须避免互相误删，失败路径也处理过期孤帧。

### t057_code_f002 - 旧格式帧永久绕过回收且文档失真

- 严重度：minor
- 锚点：A35旧帧延后回收及相关长期文档。
- 位置：`src/backend/cbrowser/preview.py:commit_preview`初审版本的`frame_*.jpg`回收循环；`docs/specs/profile_preview.md`、`docs/blueprint/browser_runtime.md`。
- 问题：预置mtime早于保留期的旧`latest.jpg`，成功提交新格式帧后旧私密文件仍留存；当时文档还称初检拒绝会清理全部预览、读端使用已不再调用的旧helper。
- 建议：回收覆盖旧格式未选中JPEG，并同步实际拒绝/读取语义；不通过恢复旧读取路径增加兼容层。

### t057_code_f003 - 容错解码接受提前结束的JPEG熵数据

- 严重度：important
- 锚点：AC-007，已知损坏帧不得落盘或更新时间戳。
- 位置：`src/backend/cbrowser/runtime_agent/preview_capture.py:valid_frame`初审版本。
- 问题：合法480×300白色JPEG共2907字节，删除末尾1000字节后补回EOI，Pillow仍load成功，旧`valid_frame`返回True；解码底部被容错填充为灰色。该像素观察仅用于证明已知码流损坏，不作为生产像素判据。
- 建议：采用成熟JPEG码流检查工具拒绝解码警告，保留格式、尺寸、完整解码及纯色合法帧检查；外部调用须限时、失败封闭并避免泄露内容。

### 结论

预审存在两项important及一项minor，且当时8项AC均未声明完成。此处保留历史FAIL，后续复验单列。

### AC 复验方式

- AC-001：TICK-VOID，re_verified。预审时未勾选，虽已查权限分支，尚无完整验收结论。
- AC-002：TICK-VOID，re_verified。预审时未勾选，重试实现仍待完整验证闭环。
- AC-003：TICK-VOID，re_verified。预审时未勾选，稳定request_id及比较删除未形成最终验收声明。
- AC-004：TICK-VOID，re_verified。预审时未勾选，存储异常路径另有f001待修。
- AC-005：TICK-VOID，re_verified。预审时未勾选，并发发布/清除/回收尚未闭环。
- AC-006：TICK-VOID，re_verified。预审时未勾选，真实整张画面E2E仍在进行。
- AC-007：TICK-VOID，re_verified。f003独立复现损坏JPEG被接受，不能认可完成。
- AC-008：TICK-VOID，re_verified。预审时未勾选，前端围栏尚待最终交付复核。

coverage = 8 / 8

verdict: FAIL

## Round 2 (2026-11-13T07:41:23+08:00)

reviewed_scope: b75df5c9c154d64d

### 审查范围与验证边界

- 完整读取最终渲染prompt并重算指纹一致；核对用户已批准整张浏览器画面及d041最小修复。最终八项AC均已勾选，未知契约均有实测结论。
- 核对完整差异与新增文件、关键生产路径、相关断言及原始证据。`image_sources.json`记录的Browser/API/Supervisor修改模块摘要逐项与最终源文件匹配。
- 直接解析完整B的E2E JUnit：105项中102 passed、1 failed、2 skipped；另解析`policy_fix_e2e.xml`：原失败`test_policy_installation_failure_fail_closed_and_cleanup`为1 passed、0 failed、0 skipped。B的原始失败结论保留，未声称修复后又跑完全量。
- d041后仅定向重验为用户明确授权范围，不作为验收缺陷。两个策略helper均在create后持有句柄再start，原netns、权限、标签、30秒等待、故障镜像及清理/零残留断言保持；运行期实Docker复现修复后残留计数0。

### 前轮finding复核

- `t057_code_f001`已消除：`preview.py:177`至`:208`在目录inode锁内发布，finally只移除未被当前metadata选中的本次帧，成功与失败均回收过期未选中帧。独立重跑原三次metadata失败复现，孤帧计数变为0；已选中同名帧受保护。
- `t057_code_f002`已消除：`preview.py:153`至`:161`回收全部过期未选中JPEG，独立重跑旧格式复现后`latest.jpg`不再留存；spec、runtime及security文档已改为真实帧格式及`read_preview`快照语义。
- `t057_code_f003`已消除：`preview_capture.py:51`至`:72`保留Pillow检查并以`jpeginfo --check -`检查码流，stdin传字节、双输出丢弃、2秒预算，缺工具/超时返回False；`:127`将检查放入工作线程。独立复验原补EOI坏帧被拒绝且无metadata/时间戳，合法白帧正常提交。

### 七视角核对

|视角|最终核对结果|
|---|---|
|安全与隐私|读取保持登录鉴权、no-store及nosniff；文件0600，暂存独占创建；截图只允许显式Linux本地display，启动加载独立Xauthority，日志不输出图片/路径或工具原始输出。无新增可复现缺陷。|
|实现正确性|DB开关围栏、成功后去重、稳定request_id、比较删除、metadata指针与同fd字节快照均已查证；三个预审问题已独立复验消除。|
|契约与Breaking|整张画面为用户批准变更；480px宽/15秒/质量70保持，高度随完整画面比例生成；旧格式只回收，不恢复兼容读取；d041范围及定向验证授权明确。|
|性能与资源|截图与严格检查均在工作线程；jpeginfo限时且不落中间图片；未发布孤帧及过期帧回收，目录fd与文件fd均关闭。|
|架构与可维护性|共享预览模块统一文件规则，未新增锁文件或自写JPEG解析器；独立实测确认目录锁仅同一Linux内核互斥，未夸大为跨VM策略事务。|
|健壮性与可观测|API上报失败可重试且warning限频；坏帧失败封闭；策略helper启动异常能进入原清理逻辑，原错误/等待边界未扩大。|
|文档与规格|task、spec/index、相关blueprint及d038–d041事实记录与最终行为一致；handoff明确B失败与定向补验、证据保留位置。无新未处置finding。|

### 结论

- 本轮新发现：0条；前轮三项均已从代码及独立复现确认消除，无未解决critical/important。
- 非阻断规模提示：`supervisor/core.py`3485行、`supervisor/docker_adapter.py`2168行、`runtime_agent/agent.py`850行、`useProfilesQuery.ts`629行。本次未扩成无关重构；生成的requirements与lock不计入规模评价。
- 复杂度按AST分支及短路表达式近似计量：`read_preview`12、`capture_once`11、`_observe_preview_capture`13；仅作简化条件的非阻断提示，未见因此造成的行为缺陷。
- 系统性follow-up：无未解决项；跨VM锁边界为已披露的部署约束，非全Docker写入端不在本次互斥承诺内。fd快照一致性不依赖该锁。
- 总体判断：最终实现支持八项AC，d041定向补验范围与用户授权一致，代码轴PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。核对`repository.py:record_preview_capture`在写事务内检查capture_preview、epoch及instance；内部通知仅accepted时发布，拒绝分支不更新时间戳、不发SSE，并核对同epoch关闭用例。
- AC-002：TICK-VALID，re_verified。核对`core.py:_observe_preview_capture`仅在完整校验及API200后写去重，HTTP/传输失败保留同帧机会并经限频warning报告；核对两类失败重试断言。
- AC-003：TICK-VALID，re_verified。核对Coordinator pending保存完整首次request及request_id，重发复用、成功按对象比较删除；Supervisor成功缓存去重，epoch6在途成功不会移除epoch7 pending的用例触达生产逻辑。
- AC-004：TICK-VALID，re_verified。核对`read_preview`一次metadata选择、打开fd读取、摘要验证，以及router从该快照生成ETag/响应；核对已打开帧遇替换/清除及发送前清除的字节一致性断言。
- AC-005：TICK-VALID，re_verified。核对共享原子写以uuid和O_EXCL创建0600暂存、异常只删自身文件；并发写及名称碰撞用例覆盖原缺陷。另独立Docker双容器目录锁实测互斥，Mac跨VM不互斥已披露。
- AC-006：TICK-VALID，re_verified。核对显式Linux/XCB整张显示采集、Runner认证接线及卡片object-contain；真实E2E严格断言480×270、浏览器界面区、双布局切换和切回，等待同时要求新ETag与正确布局，禁止宿主fallback。
- AC-007：TICK-VALID，re_verified。独立构造原合法白帧及删除1000字节后补EOI坏帧，最终生产验证分别接受/拒绝；实际capture_once拒绝坏帧且不写meta/时间戳，合法白帧提交成功，缺工具与超时分支均失败封闭。
- AC-008：TICK-VALID，re_verified。核对详情/列表任一缓存关闭即丢事件、缺授权不写、时间点严格单调且拒绝无效时间；卡片关闭flag立即隐藏旧图，相关迟到/旧值/时区偏移断言与生产路径一致。

coverage = 8 / 8

verdict: PASS

# Agent 执行器（t030）

版本：执行器规约 v1；CLI 动作程序 `version` 必须为 1；实现见
`src/backend/cbrowser/agent_executor/`，隧道过滤见
`src/backend/cbrowser/runtime_agent/tunnel_filter.py`。

## CLI

- 入口：`cbrowser-agent`（`pyproject.toml` `[project.scripts]`），stdin 读 JSON
  动作程序，stdout 输出机器可读 JSON 结果。生产路径不用 Playwright：
  Playwright 不暴露 targetId，而 targetId 是 adopt、账本与 ref 校验的
  身份原语；生产路径走原始 CDP。Playwright 只在门禁/测试环境出现，
  按 `scripts/gate-requirements.txt` 固定 `playwright==1.64.1`，不是
  打包依赖。
- 连接：经既有 cbat_ 认证隧道（`WS /api/v1/automation/profiles/{id}/cdp`），
  不用裸 CDP TCP。凭证只经 `--token-file`（0600）或
  `CBROWSER_AGENT_TOKEN` 传入；故意不设 `--token` 旗标（会进进程列表）。
  CLI 自身输出、错误、日志与账本不含凭证、Cookie 或认证头；默认不导出
  Cookie/存储。调用方脚本经 `extract`/`evaluate` 主动返回的数据由调用方
  负责，不伪装成只读。
- 步骤：`targets`、`new_page`、`adopt`、`snapshot`、`click`、`input`、
  `navigate`、`wait_for`、`extract`、`dialog_answer`、`dialog_wait`、
  `set_input_files`、`permission`、`wait_for_target_count`、`cleanup`。
  步骤失败后仍报告清理结果；程序超时、取消与步骤错误可区分。
- 稳定错误码：`ref_stale`、`target_not_found`、`step_timeout`、
  `tunnel_rejected`、`cdp_error`、`invalid_program`、`connection_failed`、
  `dialog_not_open`、`dialog_timeout`、`cancelled`、`internal_error`。

## 会话与跨调用状态

- 一次 CLI 调用是一个进程，但一个 Agent 会话横跨多次调用：快照 ref 与
  页面账本持久化到状态文件（`--state-file`，默认
  `~/.cache/cbrowser/agent-executor/<profile>_<runtime>.json`，0600、
  原子写入），按（profile，runtime-instance）区分。状态文件只含 ref 映射
  与账本元数据，不含凭证、Cookie 或认证头；缺失、损坏或版本不符时
  静默重置为空，活校验仍拒绝一切 stale ref。状态文件内写明它所属的
  （profile，runtime-instance）绑定，加载时绑定不符（包括无绑定的旧
  文件）即整体丢弃：`--state-file` 被复用或拷贝到另一 runtime 时，
  旧 ref 与旧账本清理权不得混入新调用。每条 ref 本身也记录创建它的
  runtime，校验时以条目自带 runtime 对照调用方传入的活 runtime，
  不是拿两个调用方参数互比。
- 会话启动时先 `Target.getTargets` 做 baseline（已存页面记 user/unknown），
  再 `Target.setDiscoverTargets`（discovery 会为已存目标重放事件，顺序颠倒
  会把已存页误记为 unknown）；随后把持久化账本按存活目标覆盖到 baseline
  之上（上一调用创建的 agent 页不被误认作用户页），把持久化快照按存活
  目标恢复。恢复页的排序按保存顺序（单调时钟偏移），保证最后 Tab 保护
  的 newest 判定稳定。
- 成功退出不做隐式清理：会话靠状态文件续存，Agent 页留待后续调用；失败
  或取消时自动清理（fail-safe）；显式 `cleanup` 步骤是正常结束的清理入口。
  早期“每次退出都清理”的语义已废弃：它使跨调用 Agent 工作不可能
  （上一调用创建的页在下一调用前就被关闭）。

## 页面账本

- 来源、管理权、清理权三分离。会话启动时已存 target 记 user/unknown；
  本会话 `createTarget` 创建的记 agent-owned 且可清理；`adopt` 保留原始
  来源、只授管理权不授清理权；`managed=true` 永不推导清理权。
- popup 归属需三方证据：openerId 是 agent 页 + 动作时序窗口（5 秒）+
  账本来源；证据不足记 unknown，永不可清理；不按 URL、标题、索引或重用
  ID 误绑定。
- 清理永不关闭浏览器最后一个剩余页面 target；全部 live 目标皆可清理时
  保留 created_at 最新的一个并报告 `last_tab_protected`；不能安全保留时
  拒绝清理并报告原因。清理不关闭浏览器、不关闭 context、不关闭用户页。

## Snapshot 与 ref

- 快照取 `Page.getFrameTree`（frameId/loaderId）+ `DOM.getDocument`
  （depth -1、pierce）+ `Accessibility.getFullAXTree`。ref 按 frame 命名
  `f<frame_index>e<seq>`，iframe/OOPIF 以 frameId 隔离。
- frame 归属以 DOM 映射为准，不信任 AX 节点的 frameId：实测 Chrome 的 AX
  树只在 frame 根节点带 frameId，其余节点 frameId 为空；信任它会丢掉除
  根外的全部节点。DOM 走查按文档槽位记录节点，iframe 文档按 URL 匹配
  优先、等数时按序 zip 映射到子 frame；无法可靠映射的文档节点不进快照，
  绝不猜进主 frame。
- 主 frame 由 AX 树覆盖；子 frame 中无 AX 对应元素的 DOM 元素也进快照
  （role/name 诚实为空，tag + id/class 供识别）；主 frame 的 DOM-only
  节点与结构节点（HTML/HEAD/SCRIPT 等）不进快照。
- 使用 ref 时逐项校验：runtime_instance_id、target 存活、frame 存在且
  loaderId 一致、DOM.resolveNode + describeNode 签名一致；任一失配返回
  `ref_stale` 并要求新快照，不静默重新解析。
- 节点存活以 `isConnected` 为准：被替换节点仍可 resolve，且克隆节点
  签名与原节点相同，仅凭 resolve + 签名无法识别；分离节点必须判 stale。
  校验与动作之间节点分离时，动作侧的 detached 错误同样映射为
  `ref_stale`，不以裸 CDP 错误呈现。
- 输入只走 CDP Input 域（t029 采用结论），不用 synthetic-event 回退，
  不注入全局探测变量。

## Dialog

- 动作前建立监听（attach 时启用 Page 域并绑定会话），`dialog_answer`
  支持 accept/dismiss/promptText；无 handler 时保守语义：alert 只关闭，
  confirm/prompt/beforeunload 不默认 accept。
- 触发命令 pending 时仍可应答：传输层每命令独立 future，Dialog 应答
  走独立命令 id，不被触发命令锁死。click 的 mouse press/release 分发
  是 dialog 感知的：modal dialog 会阻塞渲染线程致使分发响应不到达；
  等满整个步骤超时等于死锁（应答步骤在 click 之后才跑）。因此分发
  等待时轮询 Dialog 跟踪器，dialog 一打开即提前返回并附带 dialog 信息，
  调用方以 `dialog_answer` 应答；应答后挂起的分发完成，其迟到响应被
  丢弃。click 自身永不自动应答。`dialog_wait` 与 `dialog_answer` 一样
  先 attach 再观测（不 attach 时 Page 未启用、opening 事件到不了跟踪器，
  等待恒超时）。若 dialog 在 mousePressed 阶段打开，mouseReleased 从未
  发出，click 结果以 `release_skipped: true` 明示该次点击未完成，调用方
  应答后需重新动作；不得把该结果当作一次完整点击。
- 非法 answer（非 accept/dismiss 的非空值）是程序错误（`invalid_program`），
  不静默折算为保守默认值；只有 answer 缺省时才走保守默认。
- 遗留 Dialog（AC-006）：机制与 t029 AC-006 证据一致，但机制细节经实测
  精确化——当没有会话认领 dialog 处理时，Chrome 在打开时即自动 dismiss
  （Opening 后紧跟 Closed，结果 false），因此执行器页上不存在“存活到
  退出”的遗留 dialog；下一调用命令畅通且观测到消解结果 false。由
  lingering 处理会话（如 Playwright 的 dialog 监听）滞留的 dialog 是
  Chrome 层限制：新会话无法启用 Page（modal 阻塞）也无法应答（报无
  dialog），本文档记录该限制，不谎称可恢复。超时不自动重放点击/提交，
  不关闭 Profile；同一 Profile 由当前执行器会话应答，其他外部客户端的
  排他由 t031 保证。
- 跨调用遗留 Dialog 的机制选择（task 设计要求记录的选择与依据）：
  新连接能得知并应答的 dialog 由 CLI 处理（本节上述机制）；CLI 退出后
  无认领的 dialog 由 Chrome 在打开时自动消解，下一调用畅通。常驻
  Agent 维护 dialog 状态的分支不在 t030 实现：它会改变全部自动化客户
  端的 dialog 语义（认领即不再自动消解），必须与 t031 的真人优先与排他
  设计一并定夺；仍由 live 外部处理会话持有的 dialog 不属于“CLI 退出后
  遗留”，其仲裁归 t031，不在 AC-006 的“下一调用畅通”承诺内。

## 权限与设备提示

- CDP 无原生权限/设备提示事件，属不可检测情形，文档列为限制，不冒充
  检测能力。CLI 提供显式 `permission` 步骤，一律返回需真人结果并附
  t031 handOff 可消费的载荷（profile/target/kind/时间），永不静默授权。
  文件选择走 `DOM.setFileInputFiles` 独立步骤，与权限提示分开。

## 隧道过滤（v2）

- 隧道是外部客户端的唯一 choke 点；Agent 自身 `/control` 关闭路径不受
  影响，Supervisor 生命周期关闭仍可用。
- 一律拒绝：`Browser.close`；`Browser.setDownloadBehavior`、
  `Page.setDownloadBehavior` 与 Emulation 覆盖族
  （`setUserAgentOverride`、`setDeviceMetricsOverride`、
  `setGeolocationOverride`、`setTouchEmulationEnabled`、
  `setFocusEmulationEnabled`、`setEmulatedMedia`）、
  `Network.emulateNetworkConditions`。拒绝返回带原 id 与原 sessionId 的
  稳定 CDP 错误（code -32000，message 含 `CBrowser tunnel:`），不转发。
- `Page.addScriptToEvaluateOnNewDocument` 按会话登记，断开时经同一
  chrome_ws 以 sessionId 尽力清除（平拒会破坏 Playwright utility 注入，
  t029 L5 已证实其存在；登记 + 清理达到“不断开不残留”）。
- 关 Tab 不在隧道做归属过滤：实测 Playwright `popup.close()`（点击从用户页
  打开的 popup）会被归属过滤永久挂起——隧道无法区分“刚点击打开的
  popup”与“用户页”。执行器自身发起的清理由账本约束（仅 cleanable
  目标）；外部客户端经隧道的关 Tab 在 t031 排他落地前不受账本约束，
  仅受最后一页 backstop 约束：当其观测到的页面集恰为 1 项时
  拒绝关闭，观测不到页面集时放行。失败的 `Target.getTargets` 响应不
  清空已观测页面集（否则一次错误响应即可悄悄关掉 backstop）。
- 自动化会话期间下载仍进入 Artifact 捕获：下载行为变更被拒绝后，Agent
  的 browser 级捕获不受客户端覆盖；断开后 Agent rearm 恢复。

## 薄入口 Skill

- Skill 在 `assets/skills/cbrowser-agent/SKILL.md`（产品资产目录，不放
  模板软链目录 `.claude/skills`、`.agents/skills`，不安装到用户全局
  skill 目录）。Skill 只做薄入口：指引调用方用 `cbrowser-agent --help`
  核对当前 CLI 表面、用动作程序 `version: 1` 调用本规约，凭证走
  `--token-file` 或环境变量；凭证不写入 Skill 或账本。

## t032 交接（本 task 不判定）

- 真实镜像（arm64、容器化 X11/Stream、Mac Chrome Viewer）下的页面、
  ref、Dialog、隧道保护与 CLI 行为；目标引擎 Dialog 与最后 Tab 的真实
  演练；t029 AC-005 缩放子项（XTEST 未校准，INCONCLUSIVE）的复核；
  p028 真实镜像部分是否随 t032 闭环。
- t029 探针结论中“外部 Browser.close 停 Profile”与“no_defaults=False
  期间客户端下载优先”两条断言已被本 task 的隧道策略变更取代（测试按
  政策变更规则整体替换并注明 t030 为裁决来源），t032 不必复测旧语义。

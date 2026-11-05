---
tid: "t001"
slug: "v2_runtime_validation"
title: "验证 v2 双容器媒体与控制通道架构"
status: "done"
branch: "t001_v2_runtime_validation"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "3c8bdbc55570e85aaeb6365a3d512da9c0ce180c"
depends_on: ""
conflicts_with: ""
note: ""
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-10-27T01:19:12+08:00：attempt=1，execution_id=f5cd74fec7234b418c76206a08cff06b，owner_id=root_v2_20261027；未知契约尚未通过，不开展正式代码重构。

- 并行实验分支：spike/selkies-runtime、spike/selkies-protocol、spike/selkies-control；OpenCode 模型均为 cpa/gemini-3.8-flash。独立审查分支 spike/selkies-review。

- 正式 spike：s001_selkies_runtime、s002_selkies_protocol、s003_selkies_control；临时实验均在主仓 .scratch/v2_orchestration 下各自 worktree 内运行。报告待整合，不宣称完成。

- 主分支基线：168 passed / 1 skipped 模板契约；384 passed 后端；健康接口返回 ok。证据见 d001。

- 当前 worktree 默认 python3 为系统 Python 3.9.6，工具链需要现代 Python；使用主仓 .venv/bin/python（3.14.7）执行 preflight 通过，未改模板。

- OpenCode 协议 agent 初次跨 worktree 写目录被自动拒绝，原进程确认退出后在原 session 恢复，仅使用自身相对 .scratch 路径。未修改权限配置。

- 2026-10-27T01:22:00+08:00：控制通道 agent 违规将一次 Chrome 临时 Profile 写入 /tmp/test_chrome_cdp；主控 SIGINT 停止 OpenCode，确认相关测试/Chrome 进程已退出。保留该目录不擅自删除。原 session 已收到纠正写域、真实下载、自动恢复与超时要求后恢复。此事件最终结果中必须披露。

- 2026-10-27T01:26:38+08:00：主控独立重跑 UDS/CDP 补强脚本，首次下载与外部覆盖断开后第二次下载均完成；两文件内容匹配，覆盖目录为空，退出码 0。d002 与 s003/code 已收录可重跑代码；不据此勾选包含正式恢复链路的 AC-005。

- 独立 Gemini reviewer 补强版结论：原型技术可行性 PASS，完整第18.15生产验收 INCOMPLETE；对无泄漏与长期稳定性等宽泛评价未作为通过依据。另派独立黑盒 agent 重跑，结果待回填。

- 2026-10-27T01:38:05+08:00：CDP 脚本改为自动分配端口、只读取自身 Profile 的 DevToolsActivePort 并检查 Chrome 存活，避免端口碰撞误连；主控重跑退出码 0，两次下载与断开恢复通过。最终代码尚待完整独立 review。

- d003 新增固定 Selkies 2.1.0 ICE restart 缺口：真实 UDP 两端连接成功后，再次 start 不应用新远端凭证、旧路径继续传输。原第10.6要求保留；已向用户异步询问实现路线，未回复前不改为仅更新新连接。

- Runtime agent 初报“第18.1–5、12全部通过”被拒绝：重跑 IPC 负例失败、音频吞错、UDP sendto 无接收观察。已要求改正并派独立 reviewer；所有对应 AC 保持未勾选。

- OpenCode glob 默认忽略 .scratch，导致 agent 在文件存在时误报缺失并尝试跨目录搜索，触发自动拒绝退出。确认进程终止后在原 session 恢复，改为同 worktree 精确路径 read/bash；未修改配置。任务结束必须报告该工具行为限制。

- 新增独立媒体 agent 分支 spike/selkies-media，独占 cbrowser-spike-media Docker 前缀，使用真实 Google Chrome + Playwright 观察双页面帧解码和 candidate stats；待验证。

- 2026-10-27T10:10:00+08:00：s003 收录真实恢复三进程代码和独立 reviewer 报告；源码 SHA-256 与 reviewer 重跑快照完全相同，主控 exit0、独立重跑29.3秒 exit0。只采纳队列落盘后/HTTP发送前 SIGKILL 恢复；observed running、异常退出退避和并发队列缺口明确保留。

- 新增 s004_media_connections 冻结媒体候选，主控修复路径可移植性并补关闭首页后另一页音频 bytes/energy 增长；另派独立 Gemini 复核，不能用作者报告勾 AC。

- Gateway 新报告被主控拒绝：UDP不符分支仍PASS，入口未根据结果非零退出，“重启”仅进程内HTTP runner。原session确认terminal后恢复，要求真实独立Gateway/Agent进程、SIGKILL/自动重注册/重连解码及严格双candidate核验。

- 独立捕获策略 reviewer 在独立worktree审查/重跑真实双peer策略；静止target8与damage模式实际0 decoded严格区分，不以字段状态单独代替全链路。

- 2026-10-27T10:20:42+08:00：媒体最终五文件与独立review快照逐字节一致，真实重跑55.58秒exit0；1080p双页、真实DOM输入121212、close首tab后次页视频/音频增长见s004/d007。09/10保持NOT_RUN。

- 捕获策略首次独立复现因主控冻结快照漏拷原目录已有test_page.html而404失败；原始失败保留，但不采纳reviewer据此推断作者历史造假。补齐原文件后同session重新复核，禁止改实现/预期。原report已区分静止target8与decoded0，不采纳“静止输出8”的误读。

- Gateway最新候选已改独立Gateway/Agent进程；主控冻结独立review副本，进一步修复非503异常误判PASS、fatal_error仍整体PASS及总timeout未生效。实际Chrome PID探针、重连恢复与认证隔离待独立审查，未勾AC。

- 新增spike/turn-refresh实验worktree与Gemini session，验证真实coturn、REST凭证、双端relay-to-relay与同PeerConnection ICE重启，不允许新建PC冒充原要求。

- 2026-10-27T10:25:14+08:00：依据s004最终五文件独立review及55.58秒真实重跑，AC-002勾选；仅证明本技术原型中双页面媒体/交错输入/刷新复制关闭行为。其余5项AC仍未通过，完整公网/TURN/平台与正式隔离不因AC-002局部闭环而省略。

- 2026-10-27T10:32:53+08:00：s006四个probe源文件与最终独立重跑快照逐字节一致；最终12项exit0，实际Chrome main PID49/start_ticks78629999在Gateway SIGKILL前后不变。主控/proc探针初次误识别空格改写argv失败exit1已保留，修正后重新独立review通过；不是原PC ICE restart，音频未覆盖。d008登记。

- 新派Gemini在runtime实验worktree进行双Profile非root/只读/Xauthority/Pulse cookie隔离与真实捕获，独占cbrowser-spike-isolation前缀；未改生产代码。

- 2026-10-27T10:48:23+08:00：新增真实CloakBrowser跨容器UDS下载实验与独立覆盖生效对照，主控与独立Gemini两case均exit0；Browser/客户端networknone、无发布端口，五文件与独立快照逐字节一致，s003/container_download_review.md。仍保留纯内存事件、并发重臂与listener生命周期生产缺口。

- 主控复现Page Visibility对照：Playwright启动的真实Chrome同window两页切换/最小化仍报告visible；无Playwright启动、原生CDP直接控制独立Chrome时，页面真实hidden/visible交替且最小化均hidden（root scratch visibility_probe/result_native.jsonl，exit0）。已把参考代码/结果交作者补实际Selkies原生visibility E2E，不把此项降为平台不可测。

- Linux x86_64及公网UDP/TURN实际资源入口已异步询问，未获回复前不代用模拟数据或假入口；本地独立工作继续。

- 2026-10-27T10:51:10+08:00：逐句复核AC-005范围为第18章技术实验观察，不是要求先实现正式生产框架。s003跨真实Cloak容器UDS/下载恢复及覆盖生效对照均获独立重跑exit0，结合d006真实API/Supervisor重启/浏览器正常退出后5轮不误自启，已勾选AC-005。生产统一RPC、持久Artifact、并发重臂、observed running与异常退出退避缺口继续留给正式实现，未缩减全目标范围。

- 2026-10-27T11:38:22+08:00：主控显式ICE代适配器经标准Offer/Answer三轮真实重协商通过：PC/SCTP/DTLS/ICE外层/DataChannel对象不变，旧连接关闭并拒绝send，30条独特新payload精确收到；d010与s002/code/datachannel_restart_probe.py。仅本机UDP/DataChannel层，不宣称Chrome/媒体/TURN通过。补关闭失败pending代旧Connection清理后再次三轮exit0（task scratch datachannel_final.log）。

- 隔离v1作者和独立黑盒均exit0，但review发现Pulse同UID可绕过Cookie、合法Xauth的普通XGetImage不依赖SHM、未转义dataURL#导致body白屏；主控实际查看两截图确认真实Chrome工具栏和白屏。已退回修正URL、Stream只读、实际UID和认证边界，不把v1报告“完整安全/固化生产”当结论。AC-001尚未勾选。

- 原可见性agent越界写入宿主/tmp/run_probe_inspect.py、/tmp/run_probe_inspect_2.py、/tmp/run_probe_inspect_3.py、/tmp/run_probe_inspect_4.py、/tmp/run_probe_inspect_5.py。已告知用户，SIGINT确认原71313 terminal exit130，保留这5文件未越权删除；后续新执行明确唯一宿主写目录并设置TMPDIR。停止旧TURN42253 exit130用于交付主控已验证的标准SDP适配器和明确媒体接入任务，不是因观察超时误判停止。

- 新可见性执行已完成真实原生Chrome7场景exit0，新增薄CBrowser visibility adapter监听实际document.visibilitychange并发送官方STOP/START；不改hidden/HELLO/pageTabId/resume_key。最终6源冻结后独立Gemini正在串行复核旧完整策略与新原生Visibility，未提前勾AC-003。TURN媒体和隔离修正版并行继续。

- 2026-10-27T14:50:34+08:00：前轮已取得独立TURN对抗证据：正常套件exit0，但第二轮无效凭证、新代0 relay candidate时旧媒体仍满足原成功条件，独立review明确FAIL。原成功结论拒绝；作者正在修正为等待新代commit、关闭旧连接后再取媒体增量基线，并要求无效凭证负例非零退出。不是原SDK原生支持结论，AC-004不变。

- 捕获策略R3独立复核Core失败/Native7通过；R4作者报告Core9与Native7均exit0，当前六文件冻结由新独立Gemini复核。移除仅为测试采样添加600ms锁8，统一捕获仲裁，恢复顺序使用本轮内部时间戳和实际API trace；未提前勾AC-003。

- 隔离R2独立真实重跑exit0、19.3秒，主控查看A/B截图确认真实Chrome UI与正确fixture颜色；但音源仍paplay。当前作者补实际CloakBrowser WebAudio440/880，保留原PCM隔离判据与同UID Pulse cookie限制，待最终独立复核后再定AC-001。

- 主控新增原生IME实验于当前task scratch/ime_probe，独立容器前缀cbrowser-spike-ime、HTTP18095/UDP30018。外部Chrome真实CDP composition提交、官方输入链路与只读远端DOM判定，尚无通过结论；不以直接写远端DOM或JS合成事件替代输入链路。

- 主控IME原生提交最终探针exit0（scratch/ime_probe/native_probe.log）：外部Chrome先通过ASCII7正例，再由原生CDP composition/textInput发送官方input channel co,end,中文，远端CloakBrowser只读DOM精确中文，容器clipboard哨兵不变且不访问宿主clipboard。末尾compositionend的isTrusted=false来源未定位；撤回“官方客户端合成”未经源码证实推断。先前过严末尾事件oracle及未等待连接的失败均保留，最终冻结五源待独立review，不称1000次/OS候选窗/完整剪贴板通过。

- R4捕获策略独立Core9退出0，Native实际退出1（Expected 2 total peers, got 1），reviewer正以独立诊断harness定位，禁止采纳作者全绿报告。TURN修正版作者报告正常两轮exit0、无效凭证被HTTP400拒绝并exit1，冻结新六源由原独立reviewer重跑；隔离BrowserWebAudio作者21.8秒exit0，主控将BrowserRunner调试print换logging后最终快照重新独立验证。AC-001/003/004保持未勾选。

- 主仓创建提交b5f732c补齐t005–t012，全部creation preflight PASS（SPIKE警告保留），真实依赖锁住Supervisor→Gateway/鉴权/RTC→前端→文件自动化→完整验收→迁移→删除旧路径→正式发布。此为创建commit，不是实施完成；t001未通过前不启动正式重写。

- 捕获R4最终六源与独立/主控副本逐字节一致，独立Core9/Native7最终exit0，主控Native7再次exit0，s005/d013已更新并勾AC-003。首次Native两Peer握手失败保留；独立报告以34.7ms提帧推断第19章P95达标未采纳。旧Core S10完整保留revision_03，不就地改旧预期。

- s007/d011落盘非root/只读/Xauthority/IPC/Pulse边界及WebAudio证据；主控DFT确认按声明44100采样的音频峰值404/808而目标440/880。独立review虽PASS并称重采样导致，正常重采样应保持音高，此根因推论不采纳；作者正在诊断实际时钟/caps，AC-001不勾选。

- s008/d012最终九源与独立R3快照一致，正常exit0/16.0秒、真实无效凭证负例exit1/15.6秒；客户端PC/track引用===、新代接管后真实媒体增长。主控移除被review漏检的pendingIceConfig临时凭证console输出并重新review通过。仅本地技术可行性，公网/独立内外URL/24h调度未测，AC-004保持未勾选。

- IME独立五源真实重跑19.517秒exit0，主控额外标点/预编辑取消/Emoji严格结果包装再跑exit0，s009/d014已登记。末尾isTrusted=false在空白页CDP也出现，未见JS dispatchEvent，排除Selkies站点合成；Blink具体内部机制未有源码佐证，不采纳更细根因。少量fixture不代表第19章1000次或OS候选窗通过。

- 按机器目录地图只读检查现有机器清单/约束文档：记录中唯一可用x86_64机器仅1.7GB+swap且明确禁止再堆重服务，另一较大机器为ARM64；均不满足第19章16vCPU/32GiB原生x86_64基准。未连接或改动远端服务，不将现有生产主机视为已授权实验目标；原生Linux/公网入口待用户提供。

- s007最终R5九源与作者/独立快照一致，纯净目录无历史PCM仍完整重跑19.0秒exit0：48000实际链路、440.15/880.32Hz、1%门禁、当前PCM错误44100声明必跑拒绝、非root/只读/跨Profile认证与挂载负例通过。AC-001按技术观察勾选；不采纳未定位反指纹因果/错误dB换算/绝对安全表述。

- s008更新当前复现入口为分离RTC九源，独立正常exit0/17.5秒，单侧失效双会话exit1/33.3秒；宿主/内网不同URL及两端不同凭证实际分配，PC/track引用===，旧媒体不冒充新代成功。原同URL探针整项替换，历史报告与旧scratch源保留，门禁未弱化。公网/24h调度仍未证明。

- 主仓提交0cb6e63修补独立覆盖审查11项缺口并拆t013/t014，修订文档覆盖PASS。主控再明确t003消费t002配置快照、去掉t005冗余依赖，符合计划20顺序；preflight/图检查通过。仅契约维护，不是正式代码实施。

- 当前AC-001/002/003/005技术观察通过，AC-004/006仍缺公网和原生Linux。未知项改UNVERIFIED-BLOCKING；已再次询问具体SSH别名/测试目录/公网IP与端口/凭据文件路径。未把现有受限生产主机当测试目标，也未开始正式重写或冻结架构。

- 2026-10-27T15:56:21+08:00：严格preflight --require-verified退出1，明确UNVERIFIED-BLOCKING：公网候选与原生Linux x86_64资源缺失。该环境缺口连续多轮未变，本地可独立实验/复核已完成；所有当前OpenCode进程terminal，专属spike/diag容器、网络、卷均无残留。保留active task与未提交实验交付，不finish、不合并部分t001、不启动正式重写。

- 恢复定位：branch=t001_v2_runtime_validation，head_commit=3c8bdbc55570e85aaeb6365a3d512da9c0ce180c，attempt=1，execution_id=f5cd74fec7234b418c76206a08cff06b，owner_id=root_v2_20261027。主仓当前head=0cb6e63；完整编排状态在主仓.scratch/v2_orchestration/checkpoint.json。等待具体测试SSH别名/目录/公网IP及端口/凭据文件路径；真实Linux平台和公网验证后才能重跑严格门禁，不能用现有低配受限生产主机、QEMU或本地结果代替。

- 2026-10-27T18:35:56+08:00：用户明确指示“把这两个跳过”，豁免公网环境和原生Linux x86_64执行。已修订plan/t001契约及矩阵，原AC全文保留scope_adjustment.md；未运行项为NOT_RUN/USER_WAIVED，不报PASS。保留本地真实TURN/Gateway/IPC/输入/恢复验收，解除资源阻塞并继续task收尾与后续正式实施；不因此删除公网/Linux功能或豁免其他压力/输入/安全检查。

- 2026-10-27T18:58:20+08:00：用户进一步明确最终在当前电脑Docker部署、同机Chrome访问。按sysctl/docker info实测将计划19.1改为M1Max10核/64GiB宿主、OrbStack10CPU/约15.66GiB、Linuxaarch64/CPU编码；保留1/3/10场景及延迟/8h/1000次目标，容量按实测。主仓已提交df439af（基准专项独立文档review PASS，仅设计一致性，不代表性能通过）。

- 九个已闭环spike已由repo_hygiene官方命令dry-run后归档。首轮因新增源未入索引、git mv未动作，确认源完整后git add -N补登记再迁移成功；无模板修改。归档保持原始测试源码/报告字节，完整git diff --check仅命中这些历史快照行尾空格；活跃变更排除docs/archive后检查通过。该差异明示并交最终review，不改已归档证据以消除提示。

- 当前回归：模板169 passed（原样在Git工作树外、允许写域内TMPDIR重跑），后端384 passed，前端NODE_OPTIONS=--no-experimental-webstorage下49 passed。初次模板临时目录位于真实worktree内引发两个.env fixture误报，原失败日志保留，未改断言/模板；独立TMPDIR恢复真实隔离后全过。

- 文档agent原70326按新部署目标明确SIGINT结束exit130，再同session恢复52091，已terminal exit0；五文档草案完成。主控修正旧/manage目标残留、共享内存非端到端零拷贝、可见静态8/活动30、探针缺素材/依赖/预期非零说明等，待最终全scope review。Agent生成的自身uv.lock清理，不提交生成锁文件。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

正式Round1：code reviewer原进程已terminal，主控发现原报告两条finding与源码不符后同session纠正，修订进程82153已terminal exit0。原始报告及纠正过程保留在编排JSONL；不能据最初PASS跳过复核。test补验91415已terminal exit0；独立Native7实际Chrome前后台/最小化/恢复全部通过，日志保留于主仓scratch备份。Round1双轴同指纹PASS；最终Round2移除生成锁文件后重新确认。组件历史review保留在归档spike，不计为正式review轮次。

|finding_id|status|fix_ref|说明|
|---|---|---|---|
|t001_code_f001|撤回||源码stage2_containers.sh第2行已有set -euo pipefail，原报告缺失判断失实，reviewer复核撤回|
|t001_code_f002|撤回||stage2_media_restart_probe.py无ws.close及所述finally，第590行为摘要；原锚点与风险描述失实，reviewer复核撤回|
|t001_code_f003|遗留|t006|修正锚点为Gateway恢复探针396–407行有界等待；归档探针保持原字节，生产Gateway应使用明确就绪通知/状态与超时，不把探针轮询当作正式服务设计|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：修订后六项AC已有本地技术/报告证据；公网及原生x86单列用户豁免，最终full review已完成，双轴同scope PASS。
- 测试：模板169 passed；后端384 passed；前端49 passed（Node26显式关闭实验WebStorage）；当前测试命令块已实际整组执行退出0。
- 黑盒：健康接口返回ok；task状态读取成功；repo_sync status输出未初始化但退出0，只记录状态，不据此声称上游同步已配置。专项真实媒体/输入/恢复证据见归档和矩阵。
- review：full双轴Round2最终PASS，review_scope=bdaea2ca98d286a6；code静态核验、test五项实际复验加一项环境/矩阵查验，coverage=5/6。主控核对全部调用/关键成功和负例输出。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 新增可重跑验证资产与d001–d014、更新v2目标/现状区分、明确用户豁免和本机基准；生产代码未改。

### 长期文档闭环

本task已由specs_index的v2_runtime_validation行关联t001，记录技术验证而非生产实现完成。无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

- 最终复核限定：code报告的“AST分支覆盖”不作为动态分支覆盖证明，“15.66GiB硬限制”仅指当前Docker总预算，不代表已配置各生产容器限制。test初轮scratch部分已自行删除，历史输出以主仓JSONL原始工具结果为准；本轮Native7源码/日志独立保留。两路进程均终止，未将补验等待误判完成。

- 2026-10-27T19:30:00+08:00：t001阶段收尾；按用户最新要求每阶段更新项目handoff。t001仅关闭技术验证，后续t002至t012（含t013/t014）正式实现、性能/8h/1000次输入及部署未完成，绝不据原型PASS宣称全计划完成。

- 最终Round2：原Round1指纹包含reviewer运行uv生成的未跟踪uv.lock；实际交付不含此锁文件，移至scratch后指纹变更。主控内存对照确认唯一范围差异为该生成文件，两路按重新渲染prompt复核最终scope bdaea2ca98d286a6，10317/67499均terminal exit0，原实施与实际测试资产未变，未重复无关测试。

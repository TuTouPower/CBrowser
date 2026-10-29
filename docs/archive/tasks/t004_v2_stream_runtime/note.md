---
tid: "t004"
slug: "v2_stream_runtime"
title: "实现 Selkies Stream Runtime 与 Profile 级媒体控制"
status: "done"
branch: "t004_v2_stream_runtime"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "8ff9fd237dcd8e6d1093f3de7503f5b7f599b3e6"
depends_on: "t003"
conflicts_with: ""
note: ""
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 开工现场

- attempt=1；execution_id=c738656d4a2144cc9643f66c1b4831e9；owner_id=root_v2_t004_20261028。branch=t004_v2_stream_runtime，base/diff_anchor=8ff9fd237dcd8e6d1093f3de7503f5b7f599b3e6。登记worktree=/Users/karson/kar/code/CBrowser_t004，已claim，不重复start/reserve。
- t003已done/执行commit/terminal/report/cleanup。主干集成失败为已删除scratch音频分析器未入库，9HTTP PASS、13Runtime中1FAIL12PASS，合并已撤销。保留原提交与失败证据，本task先补共同媒体fixture，不恢复临时文件伪造通过。
- 沿已授权固定队列以t003完成分支为base，t003/t004链尾一起做最终主干验证；不增加成员、不改写t003历史。原六项独立Runtime能力证明有效，测试可移植性由本task闭环。
- 生产写域为Stream模块/独立镜像/协议/新媒体测试；共享音频fixture及原Runtime E2E路径由Root独占修正。Browser Agent生产代码/API/SQLite/正式compose/前端应用不动。.env与真实用户数据不读不动。
- 干净上游Selkies commit6ee68a7a815956e6745e916741f13335e0b3ff53的195源码与72项归档材料在.scratch/t004_preparation，带SHAmanifest；仅机制参考，不把临时裸控制口当正式认证设计。

### 计划与验证

1. 正式音频fixture/路径/解释器修正 → 无历史audio_tools目录的新worktree运行原13项真实Docker，维持1%/串扰/错采样率负例。
2. Selkies共享编码、固定几何、身份/输入/认证需求边界 → 同Mac Google Chrome双页+真实Docker媒体、UDP/TURN/同PC换代。
3. 独立黑盒与full code/test七视角 → 全AC与项目门禁通过后一个执行commit、exact cleanup及t003/t004链尾集成；每阶段更新handoff。

### 2026-10-28T18:41:58+08:00 共享 fixture 与 ICE 失败恢复阶段

- Root正式audio fixture及原Runtime E2E对接：干净worktree13真实Docker PASS161.53秒；独立Gemini在全新自身cwd复验双Profile音频/重建Cookie，1PASS23.29秒；校准负例拒绝。独立日志在主仓验证worktree `.scratch/t004_blackbox/retained_logs/candidate_ac001_85395414.log`，不把它当Stream六AC通过。
- ICE错误信息隐私：先2FAIL，修复URI输入回显后9单元PASS。真实relay候选准备失败泄漏socket且取消旧monitor：原socket4→7；修复后direct/sharedUDPmux均连续三次失败socket4→4、旧monitor及DataChannel存活、随后同PC健康换代至2。原红/绿证据在本worktree `.scratch/t004_root_checks/`。该诊断为固定SDK镜像+helper挂载，正式新fixture/E2E必须最终完整Stream镜像再跑，不能替代三代TURN媒体验收。
- ICE原作者terminal，Root已接管其文件；主体当前99316/PID872/session ses_e7dfee378ffeyRFj6tt50WDSqi。前草稿缺真实Selkies服务与桥接被拒；续行provider HTTP400后确认terminal，再建指定模型新会话，未改配置。当前仍实施，6AC未勾，正式Verify/review均0，不提交执行commit。

### 2026-10-28T18:52:53+08:00 ICE 独立资源审计闭环

- 独立固定快照审计复现两个缺陷：pending restart关闭遗留active连接；真实TURN分配超时/取消遗留原生socket。原红证据及快照留在独立lane `.scratch/t004_ice_audit/`，原报告nonroot宣称有误，已要求基于新显式UID1000复验勘误。
- Root修复stop finally释放active、新TURN transport取消清理、gather shield/drain；新增正式独立fixture与E2E。真实direct/mux pending关闭socket2→2；TURN timeout/cancel四模式socket5→5，旧DataChannel/monitor保留。9单元+8真实Docker正式测试入口17PASS47.53秒，日志 `.scratch/t004_root_checks/ice_integrated_17_tests.log`。
- 不可变集成package诊断镜像sha256:8df3f4e20625d244556747ac33b22fb77be760eb4ffe26b9bfd819526b0aa8bd；含当前helper，无生产源码host overlay，仍基于旧Stream诊断base，不作为最终可复现镜像或媒体六AC。最终镜像必须重跑。独立修正版复验61854/PID9847进行中；正式Verify/review仍0。

### 2026-10-29T03:14:17+08:00 原生 relay 与客户端身份阶段

- 首轮主体terminal0，真实双Chrome固定1080p解码PASS73.04秒；audio=None，宽松帧断言不算完整AC。当前transport84130/PID35472与policy84524/PID35471分文件实施；Root负责shim/媒体E2E/ICE，无重叠写域。旧错误/失败日志保留，6AC仍未勾，正式轮次0。
- Root将真实coturn三代原生PC/DC relay换代机制转为正式fixture+E2E：gens2/3/4 server/client各自不同HMAC及relay端口，同PC/DTLS/DC/mux，旧transport发送拒绝。使用coturn本地4.18.0测试镜像；exec EPERM初错通过最小NET_BIND_SERVICE修复，仅coturn需要此cap、测试peer仍cap-dropALL。非真实Chrome音视频证明，不算AC004完成。
- Root真实Chrome复现同文档并发HELLO错误重映射（Timeout FAIL），共享pending lock acquisition修复；保持官方HELLO原文、复制标签仅重映射自身、重载ID稳定，删生产shim中测试音频/PC钩子及无界日志。正式身份+relay E2E合跑2PASS3.98秒，日志 `.scratch/t004_root_checks/client_identity_and_relay_formal.log`。完整媒体仍待补音频/输入/策略/隔离。
- 独立ICE固定镜像绿复验terminal0，实际UID1000、helperSHA一致，direct/mux关闭无遗留、TURN失败/取消FD增量0且通道/monitor存活；原报告nonroot错误已勘误，原始红快照保留。

### 2026-10-29T03:24:34+08:00 首次严格双 Chrome 音视频

- Root新实际Canvas/WebAudio远端页面：两页固定1920×1080实际解码，2秒窗口8→66/1→58帧，音频字节/能量均严格增长；首页面静音并关闭后另一页仍149帧、264691音频字节且能量继续。1PASS76.63秒，原始源/指标/manifest/log在 `.scratch/t004_root_checks/media_audio_first_*`，已复制出轮转pytest tmp。
- 使用实际Browser03与不可变初版Stream镜像477c51b32d35154b163e8d7d1634bdc01c9534cc5a9e355dbf21556c8eb94f7a，不冒充后续新transport/policy最终镜像。输入/刷新/策略/Chrome TURN三代仍待做，未勾AC。
- policy首轮19单元通过，Native探针只构造SDK类，rtc_app=None，不能证明callback或capture。已派75821/PID40377在相同明确写域补实际原生管线；Root扩展媒体7028进行中，含真实中文IME、剪贴板哨兵和刷新，等待实际结果。

### 2026-10-29T03:48:56+08:00 捕获机制通过与原生 IME 边界失败

- policy续行terminal0：源e356e43f9c09b1daaaa8026e7560ec508b81d5f0a4b52d1483033d97897361a5，20unit+Ruff通过。真实Nativeprobe旧spike双容器+诊断UDS验证damage静止/运动与原生配置8→30、cap15及恢复、allhidden实际capture=False/计数冻结、set8先于resume。不是Browser03默认入口/正式Gateway授权/Chrome实际30FPS/P95，最终镜像仍需复验。
- transport首轮镜像556ef91d...公共base构建/29unit通过，但wire模型未消费、identity可缺、实际SDK Peer映射错误及旧reader关闭替代worker等尚在；已派98387/PID45726同写域修复，未通过最终验收。
- Root真实双页ASCII正反例通过；两轮原生中文仍FAIL，可信composition与官方co,end已发但DOM空。定向远端真实事件显示pinyin/Backspace后NUL F24/IntlRo，未定根因、未降低断言或改用剪贴板。独立23802/PID43440自身worktree诊断；Root备份 `.scratch/t004_root_checks/ime_round2/` 与失败日志。回归保持FAIL，6AC未勾，正式Verify/review仍0。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-10-29T13:11:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t004_code_f001|minor|遗留|全链路保持同一Browser/Peer状态有验收价值；后续正式拓扑验收新增场景时按需拆阶段helper，当前不为行数重构已验证量具|t009|
|t004_code_f002|minor|遗留|Agent协调器仍内聚且无行为缺陷；正式交付入口整理时复核CLI拆分，避免当前纯结构改动失效整镜像实证|t012|
|t004_test_f001|minor|遗留|同code_f001，后续正式拓扑压力验收按场景扩展独立量具和失败定位，保留本次整体连续性证明|t009|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：六AC满足，最终报告及处置核验通过，待finish与一个执行commit。
- 测试：169contract、384legacy、120unit、9HTTP全部PASS；12实际Stream E2E通过；共享fixture修正后13Runtime E2E通过。
- 黑盒：正式独立Verify Round1 PASS；全媒体正例96.58秒，双侧错误短凭证真实401被拒绝，不发生新代假commit。
- review：Full Round1 code/test PASS，scope740fe6627e7735db；3minor已遗留至t009/t012，两reviewer各自49unit PASS，Docker实证诚实trust_prior；报告事实勘误已核，未做Docker重跑的范围诚实披露。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- Stream Runtime六AC已真实验证；minor后续t009/t012，性能/压力验收仍由原计划后续任务执行。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

### 2026-10-29T04:32:39+08:00 Root身份绑定与回收阶段

四项回归先4FAIL后修复：拒绝空session、tab/resume同时匹配、映射双射替代清除旧项、失联/stop/替代viewer等待worker和reader清理。新增未注册control拒绝测试；去除PC别名回退，Native任务注册确保shutdown回收。六组单元45PASS1.28秒；旧草稿两项补新版必填instance输入而保留原断言。镜像待重建，不能以旧c27b声称修复实测；六AC未勾、正式Verify/review仍0。私有bridge已证双页音视频/ASCII及最小挂载，但整体中文仍FAIL，Trixie/XKB诊断未定根因。日志.scratch/t004_root_checks/stream_unit_binding_round{1,2}.log及private_bridge_media_proof.json。

### 2026-10-29T04:41:27+08:00 原生中文整链诊断通过

新v2 wire镜像42bd真实Chrome仍FAIL34.77秒；Linux新鲜Profile同FAIL，Trixie源保持对照同FAIL，均未采纳。Root证服务端XKB已变但Chrome缓存旧map，重新加载map后恢复可信XTest中文。诊断Stream8fd431...整链1PASS42.46秒（两页中文、剪贴板不变、刷新/静音/关闭、生存页输入、同Browser PID/start_ticks），证据.scratch/t004_root_checks/ime_reload_complete_proof/。生产改仅Stream Native prebind适配与x11-xkb-utils，最终公共基镜像重建待验。六AC仍未勾，正式Verify/review仍0，1000IME/性能未测。

### 2026-10-29T08:15:13+08:00 溢出回收完成；CJK长提交未通过

队列溢出缺Gateway关闭通知先FAIL后修复，6新回归PASS，全组六文件46PASS0.79秒、Ruff通过。候选41a7f0...；前镜像38c86e实际ICE/Chrome身份10PASS50.39秒（非Chrome3代relay）。扩大6×20不同CJK后揭Native有限spare容量未分批（evdev room0），补容量后出现确定性错序；增加settle仍错，不当通过。Root正用仅诊断计数镜像dcb9...定位真实pool/alloc。fixture改复用SDK默认页、显式前台激活避免startup CDP race/失焦，断言保留。定向review报告已Root限定并非正式full review，六AC仍未勾/正式Verify与review0。关键日志keymap_source_media_round2.log、keymap_batch_media_round1.log、keymap_rebind_focus_round1.log、keymap_batch_trace_media.log。

### 2026-10-29T08:37:27+08:00 多字Native输入闭环与独立复验

真实Xvfb证明无XKB名称spare在xkbcomp序列化被合并，导致Native invalidate/rebind错序；改按运行时非空名称过滤17个spare，保留preferred、有限容量分批与原SDK25ms settle，移除无效额外延迟。根因/红绿证据.scratch/t004_root_checks/native_prebind_probe/。Root正式源镜像f1...媒体1PASS45.60秒（8提交124字、剪贴板、双音视频、UDP候选、刷新/关闭/输入/PID），Xvfb5轮重用1PASS1.18秒。当前a9fc镜像9个Stream源SHA全一致；独立validation冻结候选仅端口/资源前缀适配，实际连续2PASS47.69秒+2PASS46.25秒，无断言变化或重试，证据该WT/.scratch/t004_keymap_frozen_blackbox/retained_evidence/。Root勘误续流页标签及未测试release泛化；不计正式六AC Verify/review。31新增交付已add-N。新定向源review68638与AC003认证Gateway真媒体诊断70222活跃；Root源码独占，后者只写自有scratch。

### 2026-10-29T09:39:10+08:00 仲裁与真实Peer路径闭环，剩余TURN403

审查两边界先RED后修：DISPLAY缺失安全报错、全部spare真实按住时禁止重绑。47相关单元PASS；镜像06十二项真实E2E100.83秒通过。Agent断线重新注册与Stream容器暂停时Browser仍前进，媒体48.53秒通过。Root正式媒体用例加入真实v2 quota15/解除、静止8/运动30、单隐藏不影响Page2、双隐藏停增、未知viewer拒绝、新关键帧与先8恢复；真实input DataChannel越权fps/resize不破坏配额/1920×1080；不同viewport、connected PC+计数、8IME/剪贴板/刷新关闭/输入/重连与pause均通过，镜像07完整1PASS73.83秒。

实际SDK键peer_conn，旧单元test_native_peer_correlation_without_guessing伪造pc键掩盖契约错误，已整体删除（不改其预期造绿），改由真实两Chrome Gateway ICE控制与非原生形状拒绝覆盖；旧镜像06实际FAIL25.90秒，镜像07两个真实Peer生成OfferPASS26.41秒，未证明协商完成。当前镜像072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531。d017/d018已由findings.py分配创建，d014补限定。32核心证据固化main/.scratch/v2_orchestration/t004_evidence_live/，避免cleanup丢失。

TURN续行同一真实Agent路径到client答复/两端分配，ChannelBind403，generation2无commit，不能用旧媒体冒充新代；allow-loopback-peers已配置，no-ip-check不是当前coturn帮助选项，待查配置/真实路由。原独立诊断含MagicMock的字段复现不算真实媒体；后续Root实跑证据才算。剩余复制标签真实媒体、3代relay、schema生成同步、全门禁/正式Verify/full review，六AC暂未勾。所有producer/诊断CLI现terminal。

执行失误：Root首次ICE焦点TMPDIR未创建，pytest回退/private/tmp生成自有临时资料后Chrome启动失败；已告知用户，外部目录保留不动，不计验证，后续预建目录+显式basetemp/cache_dir。日志native_peer_lookup_chrome_red.log。

### 2026-10-29T09:54:00+08:00 复制标签闭环与TURN实际三代诊断

独立指定模型会话ses_e7aae040fffe4e87xAIEhzHtjm真实全流程PASS86.25秒，原生window.open复制sessionStorage且新页自动重映射ID，原两Peer引用/数量和音视频增长不受影响。Root移入正式E2E，去掉无用手工storage适配，镜像07完整1PASS84.58秒，日志full_duplicate_policy_media.log。后续策略/8IME/剪贴板/刷新/静音/失联与暂停断言保留。

TURN403在补全coturn日志后，通过真实relay-ip=172.30.0.10、external-ip=127.0.0.1/172.30.0.10解决诊断配置；生产源/镜像未改。Root连续gen2/3/4精确commit并退役旧代后，才校验新ufrag的双relay候选与音视频增长、同PC/DTLS/Track，诊断均通过。证据.scratch/t004_ice_media_gateway_diagnostic/run/28843ea0/relay_generations.json；正式入库/独立复验与单侧失效待完成，不宣称六AC完成。新增wire schema导出与两个契约测试通过；尚待完整门禁。

### 2026-10-29T10:04:00+08:00 正式三代Chrome TURN与项目门禁完成

正式fixture chrome_relay.py已入库路径，真实内外网TURN地址/独立HMAC，每代精确commit+旧closed/sendreject后才采样新ufrag双relay及帧、音频、pair字节增长，同PC/DTLS/Track。镜像07+Browser03+coturn4.18完整1PASS96.49秒；计划固定coturn4.6首次CLI配置失败46.76秒（不是ICE能力失败），补隔离no-cli后完整1PASS96.13秒。另11项XKB/身份/Native失败回收及三代DC E2E PASS52.10秒。最终9个Stream源SHA与07整镜像一致，证据current_final_image_source_provenance.json。最后仅两项测试/夹具AST等价format和删未用MagicMock import；生产源未变化。

独立冻结候选matrix正例exit0/96.58秒，server错误HMAC真实401→无freshOffer（exit1/47.41秒），client错误HMAC真实401→无新代commit（exit1/65.26秒）。各自新Profile与精确cleanup，冻结manifest_revision2保留；报告待该会话收尾，不将前轮仅读Source或被Root中断当独立PASS。来源validation/.scratch/t004_relay_independent/。新增d019记录版本/映射边界。

项目门禁：169 contract、384旧后端、120单元、9真实HTTP全部通过，日志.scratch/t004_project_gates/{contract,legacy,unit,http}.log；Ruff E/F/W/I通过。共享Runtime音频fixture原13项真实Docker PASS161.53秒，源未再改变，后续集成仍需按声明门禁复验。六AC现按正式真实证据勾选；剩独立报告审计、最终full review和收尾，不把打勾当已完成task。

长期文档已更新Stream蓝图、验证指南、webrtc_remote_display需求及specs_index关联t004；旧租约/60FPS失效约定删除。wire schema从实际四种Pydantic envelope生成，两个契约测试通过；JSON Schema不替代实际动作payload/跨字段授权。P95/首帧/容量/8h/1000次不在本阶段冒充通过。

## Verify Round1

独立指定模型session ses_e7a9f67c6ffeEXhpqZCBKERrEW已实际完成冻结候选全媒体正例与双侧错误凭证矩阵，CLI0且JSONL最终step_finish=stop；Root逐项核六AC对应生产路径、media/duplicate/policy/relay证明和负例401日志。正例PASS96.58秒，两个负例各预期exit1且分别无offer/无commit，未用旧连接传流冒充。候选51文件与manifest_revision2.json全一致，仅预先适配独立端口/前缀。正式Verify Round1 PASS，limit5不变；原先只读/被中断未运行会话不计Verify轮次。最终report.md的Darwin24.x属未经核实metadata，不采纳该环境细节；实际镜像、数字、执行状态已核。证据main/.scratch/v2_orchestration/t004_evidence_live/及validation/.scratch/t004_relay_independent/，不会随当前task cleanup消失。

最终Full Round1两路审查已派：code86136/test86155，scope740fe6627e7735db；只写review_code.md/review_test.md和各自scratch，Root冻结交付。结果待核，不提前写PASS。

### 2026-10-29T13:15:00+08:00 Full Round1最终处置

两路独立作者各49单元PASS0.95秒，最终code/test PASS、scope740fe6627e7735db、checker overallPASS。code三类minor与test同类维护提示已在处置表关联t009/t012，不扩当前代码。作者已补七视角、8提交124字、XKB真实E2E分类、时间戳与不存在的独立isolation文件勘误；Root不采纳未经实测的CPU/GPU收益量化表述。第一次审查派错validation cwd已停止，重新在登记t004 WT执行才算正式报告。代码报告勘误时作者一次双引号Python命令使Markdown反引号被shell替换、引用丢失；已核Source无变化，Root从作者原quoted-heredoc原样恢复稿提供作者，由同作者安全Python写回，完整锚点与Scope复核通过。原始错误保留，不以checker机械PASS替代报告完整性核对。

主仓repo_sync status显示模板存在待同步差异与active worktree迁移门禁；本task未请求模板同步，未修改或绕过模板。当前WT无sync_state属登记WT局部状态，主仓状态正常只读可查。

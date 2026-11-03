# bundle_local_docs_current

## responsibilities

- 本单元是仓库的现行文档体系：根文档（README/AGENTS/CHANGELOG/LICENSE/BINARY-LICENSE）、docs/blueprint/（14 篇，项目约定的当前长期真相）、docs/specs/（8 篇生效契约）+ specs_index.md（在表即生效）、docs/findings/（d001–d026 实验事实登记）、docs/guides/（4 篇验证指南）、docs/tasks/（t009/t010/t012 任务书）+ tasks_index.json、docs/pending/todo/（p016–p019 未开清理项）、docs/handoff.md（只保留当前有效一节）、docs/v2_architecture_plan.md（v2.3 方案+修订节）、docs/reviews/ 下冻结的历史审阅与 adoption 决策记录。

## interfaces

- 文档间契约接口：specs_index.md 的 slug/task/更新时间表与 specs 正文；decisions.md 的 ADR 编号与替代链（如 013 替代 010、012 替代 t014 策略）；findings 的 d 编号被 blueprint/spec/task 交叉引用；tasks_index.json 的 depends_on 与各 task note.md front matter 的依赖声明；handoff 的队列顺序与 goal 快照叙述。

## dependencies

- 任务依赖链三方一致（tasks_index.json、t009/t010/t012 的 note.md front matter、handoff 叙述）：t009 depends t012，t010 depends t009，t012 depends t018；t015–t018 为 2026-11-02 adoption 后新建的整改队列。本单元文档依赖代码事实（如权限模式、协议字段）作为真值来源，但代码本身不在本单元审阅范围内。

## flows

- 文档维护流：task 收尾时更新 specs_index 对应行与相关 spec/blueprint；架构级变更以 ADR 追加进 blueprint/decisions.md 并在新条目标注替代关系；实验事实以 dNNN 登记进 findings/；评审遗留以 pNNN 登记进 pending/todo/ 并标注处理状态；handoff.md 只保留最新一节、旧节追加 archive；历史 review 报告按 review_disposition 约定原文冻结保留。

## constraints

- 静态审阅：未运行代码/测试/构建，未用浏览器，未查上一轮 review_20261102_201727 报告。部署包络为单机单人（ADR 013）；公网穿透与原生 Linux x86_64 验证为 NOT_RUN/USER_WAIVED，文档多处如实单列。冻结的历史审阅报告（review_20261101_075819 三路 + adoption_decision、review_v2_scope_20261027、review_local_benchmark_20261027）按项目约定原文保留，其中的时点结论不视为现行文档缺陷（除 f_docs_current_10 的 Info 提示外）。凭据类材料：通读中仅见已脱敏的占位/说明性内容（如 gemini 报告中的 Bearer <redacted> 记法），无明文凭据值，未记录任何值。

## decisions

- ADR 001–014（decisions.md）。与本轮最相关的三条：ADR 012（2026-11-02，剪贴板 seamless 用户决定）、ADR 013（2026-11-02，删除 coturn/TURN 凭证轮换/ICE 代次接管/Selkies 私有 ABI 补丁，媒体改同机直连，替代 ADR 010）、ADR 014（2026-11-03，运行时数据统一 uid 1000、目录 0750/文件 0640、chown 失败即报错、删除全局可写回退）。

## evidence

- 正面核对（非缺陷）：README.md:55 引用的 DOCKER_DEPLOYMENT.md 确实存在于仓根，非死链；README 的 AUTH_TOKEN 必填随机值+仅回环监听与 4970596 整改后状态一致。tasks 依赖链在 tasks_index.json、各 note.md front matter、handoff 三处一致。blueprint/security.md:33,35 的权限模型（0750/0640、chown 失败即报错、不存在 0777/0666 回退）与 ADR 014 一致（与 artifacts.md:14 形成对照，见 f_docs_current_03）。guides/browser_isolation_analysis.md:3 已正确标注 Superseded 并指向现行 architecture/ADR 007/ADR 013。ADR 010 被 013 替代已按 decisions.md:3 约定由新条目替代字段标注。specs/v2_runtime_validation.md:184-186 的 §2.4 已正确标注被 ADR 013 取代，说明同类修订在本仓有先例。全单元 80 文件以 UTF-8 解码干净，U+FFFD 计数为 0（python 实测；通读输出中偶见的 � 为工具传输显示伪影，已用原文复核排除）。specs_index 显示 t015–t018 均已产生 spec 更新（webrtc_remote_display 经 t015 更新于 2026-11-02T23:30、storage_and_artifacts/runtime_persistence 经 t016 更新于 2026-11-03T03:00、profile_management 经 t017 更新于 2026-11-03T05:15）。

## uncertainties

- 1) 代码实现是否与文档一致不在本单元范围，由代码类单元审阅；本文档级矛盾（文档 vs ADR/spec/blueprint 之间）均为静态可判。2) review_20261101_075819 三路历史报告中的代码级结论（基线 3c8bdbc..78c9563）未复核其当前有效性，只按冻结记录对待。3) handoff.md 过期（f_docs_current_01）是否因新一节尚在撰写无法从静态证据判定，但按仓内现状其内容已与事实不符。4) v2_architecture_plan.md 的定位（历史方案+修订节 vs 现行文档）存在解释空间，f_docs_current_06 按其自身『修订节+实现细节以 blueprint/specs 为准』的约定降为 Low。

## Findings

- [Medium][95] docs/handoff.md:5,9,26,29,31 — handoff.md 已整体过期一轮：仍称下一步 t015、head fc38a1d、pending 为空
  - ID: f_docs_current_01; verification: static
  - Evidence: docs/handoff.md:5 最新一节日期 2026-11-02T21:55，标题称『下一步 t015』；:9 交出 head_commit 为 fc38a1d；:26 队列为 t015 → t016 → t017 → t018 → t012 → t009 → t010；:31 称 docs/pending/todo/ 为空。; docs/specs_index.md 显示 t015 已更新 webrtc_remote_display（2026-11-02T23:30）、t016 已更新 storage_and_artifacts 与 runtime_persistence（2026-11-03T03:00）、t017 已更新 profile_management（2026-11-03T05:15），即 t015–t018 均已实际执行。; docs/pending/todo/ 现有 p016、p017、p018、p019 四个文件，与 handoff:31『为空』直接矛盾；当前仓库 HEAD 为 b473408，远在 fc38a1d 之后。; docs/handoff.md:3 自述『本文件只保留当前有效一节』，CBrowser AGENTS.md 亦规定 handoff 只保留当前有效一节。
  - Impact: 接手者按 handoff 会误判项目状态：以为 t015 未开始、队列未动、pending 为空，从而重复规划或漏掉 p016–p019 的未开清理项；交接文档作为当前状态单一入口失效。
  - Fix: 按约定将本节追加到 docs/archive/handoff.md 并写入当前有效一节：更新 head_commit、已完成 t015–t018 的收尾状态、当前队列（t012 → t009 → t010）与 pending 现有 p016–p019。

- [Medium][90] docs/findings/d003_selkies_ice_restart_gap.md:11; docs/findings/d019_turn_loopback_mapping.md:9; docs/findings/d021_selkies_ice_restart_commit_is_async.md:7; docs/findings/d022_selkies_rtc_config_url_contract.md:7（另 d009、d010、d012、d018 同类） — findings 登记表未随 ADR 013 修订：8 篇 TURN/ICE 类 finding 仍标『有效』且含已失效指令
  - ID: f_docs_current_02; verification: static
  - Evidence: docs/blueprint/decisions.md ADR 013（2026-11-02）结论：删除 coturn、TURN 凭证与轮换、ICE 代次接管与 Selkies 私有 ABI 补丁，媒体只走同机直连，并明确『替代：010』。; d003、d019、d021、d022 的『现状』仍标『有效』（d021/d022 标『有效，限固定 Selkies 2.1.0』），d009/d010/d012/d018 同样未加被替代标注。; 其中含已失效的操作指令：d003 影响段要求保持原 ICE restart 验收、未通过前不冻结架构；d019 称后续 t006/t012 沿代栅栏复验；d021 称 Gateway 须等待 ice_restart_committed；d022 称 Stream TURN 只经 Gateway→Agent 下发、前端适配层须保持 Gateway 下发的 iceServers。; 反证对照：docs/blueprint/stream_runtime.md:33 明确现行协议已无 rtc_config/ice_restart/visibility_update；docs/blueprint/frontend.md:25 明确适配层不再处理 RTC/TURN 配置或 ICE restart；docs/specs/v2_runtime_validation.md:184-186 的 §2.4 已正确标注被 ADR 013 取代，说明登记表本可同步修订。
  - Impact: findings/ 是实验事实与后续设计依据的登记表；按现文执行会把已删除的 TURN 轮换/ICE 代次机制当作仍需满足的约束，误导 t012 部署与后续验收，甚至可能复活 ADR 013 已删除的机制。
  - Fix: 为 d003、d009、d010、d012、d018、d019、d021、d022 追加状态标注（如『机制已由 ADR 013 删除，本条仅作历史事实保留』），并删除或改写其中指向未来 task 的失效指令；与 v2_runtime_validation §2.4 的既有标注方式保持一致。

- [Medium][92] docs/blueprint/artifacts.md:14 — blueprint/artifacts.md 仍写 chown 失败回退 0755/0644，与 ADR 014 及 security.md 直接冲突
  - ID: f_docs_current_03; verification: static
  - Evidence: docs/blueprint/artifacts.md:14：『发布后的目录与文件应用 Browser runtime UID/GID（默认 1000），目录 0750、文件 0640；无法 chown 的宿主开发环境回退到 0755/0644，保证容器 UID 1000 可读。』; docs/blueprint/decisions.md ADR 014（2026-11-03）：背景明确指出 0777/0666 类回退导致『Cookie、登录态与运行时文件对宿主其他用户可读写』，结论为目录 0700/0750、文件 0600/0640、chown 失败即报错，删除全局可写回退。; docs/blueprint/security.md:33 规定 Artifact Service 发布目录同样收敛 0750/0640、『不回退到全局可写，chown 失败即报错』；:35 明言『不存在 0777/0666 回退』。; docs/pending/todo/p017_t016_minor_cleanup.md:4 已把『删除 artifacts.md 中 0755/0644 回退描述』列为清理项，但处理状态为『未开』，现行 blueprint 未改。
  - Impact: blueprint 是项目约定的当前长期真相；在其中保留一条已被 ADR 以安全理由明令删除的回退路径，后续实现者或审阅者按 artifacts.md 落地即可重新引入宿主其他用户可读 Artifact（含下载文件）的权限面，且两篇现行文档互相矛盾使验收无所适从。
  - Fix: 删除 artifacts.md:14 的回退句，改写为与 ADR 014/security.md:33 一致的表述（0750/0640、chown 失败即报错、非 root 开发路径保留开发者属主但使用精确 mode）；同步关闭 p017 的对应条目。

- [Low][90] docs/tasks/t009_v2_full_acceptance/task.md:29,71 — t009 AC-005 仍要求验证已删除的 coturn/凭证切换，AC 正文未按其自注改写
  - ID: f_docs_current_04; verification: static
  - Evidence: docs/tasks/t009_v2_full_acceptance/task.md:29 AC-005：『通过真实本机/容器网络验证UDP映射、候选、coturn UDP/TCP/TLS和relay-to-relay凭证切换……』; 同文件:71 上下文自注：『AC-005中coturn与凭证切换相关验证按t015结论改写』，且 handoff.md:29 亦记『AC-005 的 coturn/凭证切换项待 t015 结论后改写』。; t015 已收尾：ADR 013 删除 coturn 与 TURN 轮换，specs_index 显示 webrtc_remote_display 已由 t015 于 2026-11-02T23:30 更新；但 AC-005 正文至今未改写。
  - Impact: t009 是全量验收 task，其 AC 是硬门禁；按现文，验收要求验证一个已不存在的组件（coturn 已删、无凭证可切换），AC-005 字面不可执行，执行期必然临时改口径，削弱验收契约的权威性。
  - Fix: 按 ADR 013/t015 结论改写 AC-005：删除 coturn UDP/TCP/TLS 与 relay-to-relay 凭证切换项，替换为同机直连拓扑下的 UDP mux 映射、host 候选与直连媒体验证项。

- [Low][82] docs/v2_architecture_plan.md:§3 固定常驻服务清单; §7.5 内部协议边界表; §10.4–10.6; §16 安全与网络矩阵; §19.4 — v2_architecture_plan.md 未记录 ADR 013 修订：正文仍以 coturn/TURN 轮换为现行设计且无替代标注
  - ID: f_docs_current_05; verification: static
  - Evidence: 文首修订节止于 2026-11-02 剪贴板决定（ADR 012），无 ADR 013（同日稍晚、同属架构级删除）的修订条目；2026-11-01 修订节反而还写『TURN 轮换：future 校验 generation；current 过期 fail-closed』等保留 TURN 的修订。; §3 固定常驻服务仍列 coturn；§7.5 协议表『Agent 注册与信令隧道』职责仍含『TURN 配置、配额、ICE 轮换』；§10.4–10.6 仍为 coturn 部署、RtcConfigService 与 TURN 凭证 24h/12h 刷新的现行设计；§16 矩阵仍有『Stream Runtime → coturn』行；§19.4 验收仍含『coturn、ICE 和 UDP 端口映射通过真实网络测试』。; 同文对其他被替代内容有明确标注先例：§8.4 与 §19.3 均有『已被 2026-11-02 用户决定替代』的显式注记；2026-11-01 修订节亦声明『当前实现细节以 docs/blueprint/ 与 docs/specs/ 为准』。上述 TURN 章节无任何同类标注。
  - Impact: 该文标题为『最终技术架构修订与实施方案』，新读者或后续 task 按 §3/§10/§16 落地会重新引入 coturn 与 TURN 轮换，与 ADR 013 的删除决定相悖；标注不一致使『哪些章节已作废』只能靠读者自行比对 blueprint 才能判断。
  - Fix: 在文首补 ADR 013 修订条目，并给 §3 清单、§7.5 表、§10.4–10.6、§16 矩阵行、§19.4 相关项加与 §8.4/§19.3 同格式的『已被替代』标注（或整段移入历史原文区）。

- [Low][88] docs/blueprint/architecture.md:19,31 — blueprint/architecture.md 两处表述与现状自相矛盾（t011 移除旧 UI、Selkies 凭证轮换依赖行）
  - ID: f_docs_current_06; verification: static
  - Evidence: architecture.md 已交付节称『旧 UI 组件在 t011 移除』；但 t011 已被合并入 t010（docs/tasks_index.json 中 t010 条目 note 与 docs/handoff.md:30『t010 已合并原 t011』），任务清单中已无独立 t011。; v1 前端树实际由 t017 删除：docs/blueprint/frontend.md 记载 t017 前端收敛删 v1 死树，docs/specs_index.md 显示 profile_management 经 t017 更新于 2026-11-03T05:15。; 同文件 §2 依赖矩阵 Selkies 行仍述『同 PC 凭证轮换依赖显式私有接口适配器（d010, d012），该机制属于固定 SDK 版本下的内部维护约束』；而同文件已交付节自述 t015（ADR 013）已删除 TURN 凭证轮换与 ICE 代次接管——凭证轮换已不存在，所谓依赖无从谈起。
  - Impact: architecture.md 是全仓架构总览，两处残留会让读者误判旧 UI 的移除归属与当前媒体链路的维护约束，尤其 Selkies 行会把已删除的私有 ABI 适配机制继续当作现行内部约束。
  - Fix: 改写两处：旧 UI 移除归属改为 t017（并注明 t011 已并入 t010）；Selkies 依赖行删除凭证轮换/私有接口适配器表述，改为同机直连口径并指向 ADR 013/d026。

- [Low][88] docs/specs/webrtc_remote_display.md:26 — specs/webrtc_remote_display.md 仍称适配层处理 RTC 配置，与 frontend.md 的现行职责矛盾
  - ID: f_docs_current_07; verification: static
  - Evidence: docs/specs/webrtc_remote_display.md:26（前端会话节）：『薄适配层只改写信令地址、处理 Gateway 控制帧与 RTC 配置、锁定远端尺寸/DPR……』; docs/blueprint/frontend.md:25（现行职责）：『媒体为同机直连，适配层不再处理 RTC/TURN 配置或 ICE restart。』; specs_index.md 显示 webrtc_remote_display 已由 t015 于 2026-11-02T23:30 更新，但该句未随 ADR 013 一并修订。
  - Impact: spec 是生效契约（specs_index 约定在表即生效）；按 spec 字面，验收会要求适配层处理已被删除的 RTC 配置下发，与实现与 blueprint 均不符，产生假验收项。
  - Fix: 删除该句中『与 RTC 配置』或改写为与 frontend.md:25 一致的职责描述（信令改写、Gateway 控制帧、尺寸/DPR 锁定）。

- [Low][95] docs/blueprint/domain.md:12,27 — blueprint/domain.md 状态图用 failed，与同文件 ObservedState 枚举的 error 不一致
  - ID: f_docs_current_08; verification: static
  - Evidence: docs/blueprint/domain.md:12 ObservedState 枚举为 stopped / starting / running / stopping / error。; 同文件:27 的 Profile 生命周期状态图中，starting 的失败分支标为 failed，与枚举不一致。; docs/pending/todo/p017_t016_minor_cleanup.md:4 已登记『把 domain.md 状态图中的 failed 改为 error』，处理状态『未开』。
  - Impact: 状态枚举是 API/持久化/前端共同消费的契约词汇；图与枚举两名并存会让实现者误以为存在第六个状态或单独的 failed 语义。
  - Fix: 将状态图中的 failed 改为 error，与枚举统一；同步关闭 p017 对应条目。

- [Info][90] CHANGELOG.md:7 — CHANGELOG 未跟进 v2：最新条目止于 [0.1.9] 2026-10-16
  - ID: f_docs_current_09; verification: static
  - Evidence: CHANGELOG.md:7 最新条目为 [0.1.9] - 2026-10-16（上游 fork 的语言切换），其后 v2 重构（t001–t007）、上轮审阅整改与 t015–t018 均无条目。; docs/tasks/t012_v2_docker_release/task.md 的 AC-003 要求 CHANGELOG 记录 v2 阶段变更，属该 task 待落实项，故仅记 Info。
  - Impact: 外部读者从 CHANGELOG 无法得知 v2 架构与安全整改已发生；影响有限且已有 task 承接。
  - Fix: 随 t012 落实：将 v2 阶段变更（架构重构、ADR 013 媒体链路收敛、ADR 014 权限收敛、鉴权整改）补入 CHANGELOG 的 Unreleased/新版本节。

- [Info][85] docs/reviews/review_local_benchmark_20261027/review_benchmark.md:78 — benchmark 冻结报告的『1000 次验收未减免』结论已被 2026-11-02 用户决定覆盖（冻结原文，仅提示）
  - ID: f_docs_current_10; verification: static
  - Evidence: review_benchmark.md:78（2026-10-27）：『1000 次中文组合输入与 1000 次纯文本剪贴板验收……均未因调整硬件基准而删除或减免。』; 2026-11-02 用户决定已覆盖：docs/v2_architecture_plan.md 文首修订节与 ADR 012 将 1000 次输入/剪贴板改为 t009 手动清单验收、取消自动压测；t009 task.md/note.md 已按此更新，用户确认不恢复。; 该报告为冻结快照，docs/reviews/review_v2_scope_20261027/review_disposition.md:3 约定历史报告原文保留，故不要求改写原文，仅作 Info 提示。
  - Impact: 后来读者若只读该报告会误以为 1000 次自动压测仍是现行验收门禁；实际决策链完整存在于 plan 修订节/ADR/t009 中，风险低。
  - Fix: 无需改动冻结原文；如需进一步防误读，可在该目录旁注或索引处加一行指向 ADR 012 与 t009 现行口径的指针（可选）。

## views

```json
{
  "contracts": {
    "reviewer": "cb76a00d-a4e0-4e07-bf72-30d6fea6a557",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "cb76a00d-a4e0-4e07-bf72-30d6fea6a557",
    "status": "completed"
  },
  "design": {
    "reviewer": "cb76a00d-a4e0-4e07-bf72-30d6fea6a557",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "cb76a00d-a4e0-4e07-bf72-30d6fea6a557",
    "status": "completed"
  },
  "performance": {
    "reviewer": "cb76a00d-a4e0-4e07-bf72-30d6fea6a557",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "cb76a00d-a4e0-4e07-bf72-30d6fea6a557",
    "status": "completed"
  },
  "security": {
    "reviewer": "cb76a00d-a4e0-4e07-bf72-30d6fea6a557",
    "status": "completed"
  },
  "tests": {
    "reviewer": "cb76a00d-a4e0-4e07-bf72-30d6fea6a557",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "AGENTS.md",
  "BINARY-LICENSE.md",
  "CHANGELOG.md",
  "LICENSE",
  "README.md",
  "docs/blueprint/architecture.md",
  "docs/blueprint/artifacts.md",
  "docs/blueprint/automation.md",
  "docs/blueprint/browser_runtime.md",
  "docs/blueprint/conventions.md",
  "docs/blueprint/decisions.md",
  "docs/blueprint/domain.md",
  "docs/blueprint/frontend.md",
  "docs/blueprint/gateway.md",
  "docs/blueprint/persistence.md",
  "docs/blueprint/security.md",
  "docs/blueprint/stream_runtime.md",
  "docs/blueprint/supervisor.md",
  "docs/blueprint/testing.md",
  "docs/findings/d001_v2_validation_baseline.md",
  "docs/findings/d002_cdp_uds_download_recovery.md",
  "docs/findings/d003_selkies_ice_restart_gap.md",
  "docs/findings/d004_docker_shareable_ipc_contract.md",
  "docs/findings/d005_encoded_fps_is_not_motion.md",
  "docs/findings/d006_runtime_event_recovery_checkpoint.md",
  "docs/findings/d007_multi_viewer_media_identity.md",
  "docs/findings/d008_gateway_process_media_recovery.md",
  "docs/findings/d009_turn_hmac_relay_transport.md",
  "docs/findings/d010_ice_generation_continuity.md",
  "docs/findings/d011_profile_ipc_audio_boundary.md",
  "docs/findings/d012_turn_generation_media_commit.md",
  "docs/findings/d013_capture_visibility_arbiter.md",
  "docs/findings/d014_native_ime_commit_path.md",
  "docs/findings/d015_sql_error_log_boundary.md",
  "docs/findings/d016_sdk_owner_lifecycle_boundary.md",
  "docs/findings/d017_native_xkb_named_spares.md",
  "docs/findings/d018_selkies_native_peer_entry.md",
  "docs/findings/d019_turn_loopback_mapping.md",
  "docs/findings/d020_orbstack_bridge_reachability.md",
  "docs/findings/d021_selkies_ice_restart_commit_is_async.md",
  "docs/findings/d022_selkies_rtc_config_url_contract.md",
  "docs/findings/d023_headless_chrome_visibility_static.md",
  "docs/findings/d024_selkies_token_secure_mode.md",
  "docs/findings/d025_selkies_resume_grace.md",
  "docs/findings/d026_direct_media_local_only.md",
  "docs/guides/browser_isolation_analysis.md",
  "docs/guides/browser_runtime_validation.md",
  "docs/guides/stream_runtime_validation.md",
  "docs/guides/supervisor_validation.md",
  "docs/handoff.md",
  "docs/pending/todo/p016_restore_supervisor_network_and_quota_e2e.md",
  "docs/pending/todo/p017_t016_minor_cleanup.md",
  "docs/pending/todo/p018_t017_minor_cleanup.md",
  "docs/pending/todo/p019_t018_normal_exit_scratch_path.md",
  "docs/reviews/review_20261101_075819/adoption_decision.md",
  "docs/reviews/review_20261101_075819/review_opencode_cpa_gemini_3_8_flash.md",
  "docs/reviews/review_20261101_075819/review_opencode_opencode_go_deepseek_v4_1_flash.md",
  "docs/reviews/review_20261101_075819/review_opencode_opencode_go_muse_spark_1_3_contributor.md",
  "docs/reviews/review_local_benchmark_20261027/review_benchmark.md",
  "docs/reviews/review_v2_scope_20261027/review_disposition.md",
  "docs/reviews/review_v2_scope_20261027/review_scope_initial.md",
  "docs/reviews/review_v2_scope_20261027/review_scope_revised.md",
  "docs/reviews/review_v2_scope_20261027/review_traceability.md",
  "docs/specs/access_control.md",
  "docs/specs/browser_isolation.md",
  "docs/specs/profile_management.md",
  "docs/specs/runtime_lifecycle.md",
  "docs/specs/runtime_persistence.md",
  "docs/specs/storage_and_artifacts.md",
  "docs/specs/v2_runtime_validation.md",
  "docs/specs/webrtc_remote_display.md",
  "docs/specs_index.md",
  "docs/tasks/t009_v2_full_acceptance/note.md",
  "docs/tasks/t009_v2_full_acceptance/task.md",
  "docs/tasks/t010_v2_data_migration/note.md",
  "docs/tasks/t010_v2_data_migration/task.md",
  "docs/tasks/t012_v2_docker_release/note.md",
  "docs/tasks/t012_v2_docker_release/task.md",
  "docs/tasks_index.json",
  "docs/v2_architecture_plan.md"
]
```

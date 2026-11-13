# bundle_followup_q_architecture_03

## Summary

精查证实：磁盘 spool 信封无版本号、schema 文档版本从不写入也不校验，版本错位时一律拒绝；事件侧隔离留痕、下载侧静默永久跳过（新 Medium），两条新 finding 已记录。

## Findings

- [Medium][95] src/backend/cbrowser/supervisor/artifact_forwarder.py:115-135 — DownloadArtifactForwarder 对无法解析/版本错位的下载事件文件静默永久丢弃：无日志、无隔离、游标持久标记已处理

    - ID: f_followup_q_architecture_03_01; verification: static
    - Evidence: artifact_forwarder.py:118-126：except (OSError, ValueError, ValidationError, UnicodeError) 后 event=None、key=f"unparsed:{event_file.name}"，except 分支内无任何 logger 调用; artifact_forwarder.py:128-135：event is None 时 \_mark_processed 后 continue，\_save_processed 将该标记以 0o600 原子写入 download_cursors.json 持久化；后续 forward_pending 经 \_is_processed 永远跳过该文件名，即使文件内容已被修复; DownloadEventRecord 为 extra="forbid"（runtime_agent/protocol.py:73），Runtime Agent 与 Supervisor 版本错位时新版新增字段即触发此路径，已完成下载的 artifact 注册（/artifacts/downloads 投递）无声丢失
    - Impact: 滚动替换或双版本并存期间，格式错位的 completed 下载事件不会被登记为 artifact，且不留任何可观测痕迹，运维无法发现、无法重放；与 EventForwarder 的 quarantine 做法和 EventStorage 的 fail-loud 做法相比，这是全仓磁盘信封中最差的失败姿态。
    - Fix: 解析失败时至少：记录 warning（含文件名与错误类型）、把文件移入隔离目录或以独立 dead-letter 标记而非计入 processed 集合、且不要把 unparsed 标记持久化为终局状态（允许修复后重试）。

- [Low][90] src/backend/cbrowser/supervisor/event_forwarder.py:117-133,168-178 — EventForwarder spool 信封无版本治理：extra=forbid 校验使版本错位时排队事件被整体隔离，且 schema 隔离分支无测试

    - ID: f_followup_q_architecture_03_02; verification: static
    - Evidence: emit_event 写入的 spool dict 无 version 键（event_forwarder.py:121-130），\_validate_spooled_event 用 extra="forbid" 的 RuntimeEventReportRequest 校验（domain/models.py:488），任一未知字段即失败并 quarantine(reason="schema"); tests/unit/test_supervisor_event_delivery.py 与 tests/integration/test_normal_exit_replay.py 中无任何用例覆盖 quarantine 分支（grep quarantine 无命中），错位行为未被钉住; schemas/runtime/agent_protocol.json 的文档级 "version": "2.0.0" 从未写入 spool 文件或被读取侧校验，不能充当信封版本
    - Impact: spool 的存在意义就是 API 不可达/进程替换期间保住事件；但容器滚动替换后若先升级写入方再回滚（或模型新增必填字段），排队中的 exit 事件会在重放时被整批隔离，恢复路径恰在版本切换这一最可能需要它的时刻失效。文件保留在 quarantine 可人工恢复，故定 Low。
    - Fix: 为 spool 信封加显式 version 字段并在读取侧按版本做兼容/拒绝分支（或将模型改为 extra="ignore" + 必填字段显式校验的容忍策略，二选一并写明）；补一条向 spool 写入未知字段/缺字段文件的重放测试钉住选定行为。

## evidence

```json
[
  "无信封版本字段（写入侧实查）：EventForwarder.emit_event (event_forwarder.py:117-133) 写入 spool 的 dict 恰为 8 个键 event_id/profile_id/runtime_instance_id/event_type/exit_code/exit_reason/config_version/payload，无 version/schema 键；其中 config_version 是 Profile 配置代次而非信封版本。DownloadEventRecord (runtime_agent/protocol.py:72-87) 与 RuntimeEventRecord (protocol.py:58-69) 均无 version 字段，EventStorage.save_download_event/save_runtime_event 写盘的是 model_dump() 原样，故磁盘文件同样不带任何版本标识。",
  "schema 文档的 version 不落盘、不校验：schemas/runtime/agent_protocol.json 顶层有 \"version\": \"2.0.0\"，但它只是由 pydantic 模型生成的 JSON Schema 文档版本，不是任何记录的字段，没有任何写入方把它写进 spool 文件，也没有任何读取方校验它；schemas/runtime/supervisor_protocol.json 干脆无 version，且只覆盖 Supervisor 控制 RPC，不覆盖磁盘信封。两个 forwarder 的读取侧都不参照 JSON Schema 文件，只用当前运行代码的 pydantic 模型校验。",
  "EventForwarder 读取侧行为=拒绝并隔离（非兼容）：replay_spooled_events 经 _validate_spooled_event (event_forwarder.py:168-178) 用 RuntimeEventReportRequest.model_validate 校验，该模型 model_config=extra=\"forbid\" (domain/models.py:488)。新版写入方新增任一字段、或模型新增必填字段，旧/异版 spool 文件即校验失败，被 os.replace 移入 spool/quarantine（reason=\"schema\"，仅 warning 日志），永不投递；不可读 JSON 同样 quarantine（reason=\"unreadable\"）。没有版本协商、没有未知字段剥离/容忍路径；对旧文件的兼容仅来自 pydantic 字段默认值这一 incidental 性质，不是显式治理。",
  "DownloadArtifactForwarder 读取侧行为=静默永久丢弃：forward_pending (artifact_forwarder.py:115-135) 对每个事件文件 DownloadEventRecord.model_validate（extra=\"forbid\"），任一解析/校验失败即 event=None、instance_id=\"_invalid\"、key=\"unparsed:<文件名>\"，随即 _mark_processed 并经 _save_processed 持久化到 download_cursors.json，之后即使文件被修复/替换（同名）也永远跳过；该分支无任何日志、无隔离副本，原文件留置但被永久忽略。对照同仓 EventStorage.get_download_events/_read_runtime_events 读取同一批文件时是遇损坏即抛 StorageError（fail-loud），同一文件的两种读取方容忍姿态不一致。",
  "错位版本测试为零：test_supervisor_event_delivery.py 与 test_normal_exit_replay.py 只覆盖正常重放、路径逃逸、旧 exit 围栏，没有任何用例向 spool 写入含未知字段/缺字段的 JSON 来钉住 quarantine(\"schema\") 分支（两文件中 grep quarantine 无命中）；test_download_reconciler.py 只喂格式良好的事件（happy path/去重/顺序/retryable 4xx），tests/ 全仓 grep \"unparsed\" 无命中，该静默丢弃分支无测试。"
]
```

## result

```json
"confirmed"
```

## limitations

```json
[
  "静态审阅：未运行两个 forwarder 或任何测试，quarantine/unparsed 的实际触发均由代码路径推得，未做隔离复现。",
  "滚动替换造成版本错位的场景按 AGENTS.md 的单机单容器部署形态推断（spool 目录位于持久 data 卷、进程可独立替换）；未核查部署脚本是否保证 Supervisor 与 Runtime Agent 永远同版本原子切换，若有此保证则错位窗口收窄，但信封无版本与静默丢弃的代码事实不变。",
  "未回溯 git 历史核查这两个模型过去是否发生过字段增删，故无法判断该风险是否已经实际触发过。"
]
```

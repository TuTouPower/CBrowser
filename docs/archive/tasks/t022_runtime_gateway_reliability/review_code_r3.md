Verdict: PASS

# t022 code review 第 3 轮（定向复审：第 1 轮 code 15 条处置 + N1 专项裁决）

- 基线：`d699e5b`（t021），分支 `t022_runtime_gateway_reliability`；复核对象为第 1 轮 `review_code.md` 的 t022_code_f001–f015 在当前最终文件状态上的处置（以 `note.md`「## Review 处置」code 路为准），以及第 2 轮 `review_test_r2.md` 唯一阻塞项 N1 的最终状态。
- 方法：逐项到当前源码 + 对应测试原文核实（不采信执行侧自述），并实跑全部必查测试文件。第 2 轮两位复审者结论（code 路 PASS、test 路因中间快照的 N1 REQUEST CHANGES）仅作背景；本轮结论绑定本报告实跑时点的磁盘最终状态。

## 实跑记录（本轮实测）

命令：`export TMPDIR="$(mktemp -d)" && .scratch/run_unit.sh <文件> -q`（逐文件单跑；另将前四文件、后四文件各合跑一次，结果一致）。

| 测试文件 | 结果 |
|---|---|
| `tests/unit/test_gateway_registry.py`（N1 专项，全文件） | **7 passed** |
| `tests/unit/test_supervisor_cache_generations.py` | 7 passed |
| `tests/unit/test_network_policy_failure.py` | 3 passed |
| `tests/unit/test_supervisor_docker_boundaries.py`（全文件） | 7 passed |
| `tests/unit/test_runtime_agent_faults.py` | 29 passed |
| `tests/unit/test_stream_keymap_abi.py` | 7 passed |
| `tests/unit/test_api_search_defaults.py` | 6 passed |
| `tests/unit/test_supervisor_event_delivery.py` | 17 passed |
| 合计 | **83 passed / 0 failed** |

## N1 专项裁决：已消解

- 第 2 轮 N1 事实回顾：`review_test_r2.md` 抽跑 `test_throttle_eviction_never_drops_live_reservations_or_history` 时在 victim 失败史保留断言处失败；该复审者已注明当时执行侧第二批修复正在落盘、属中间快照。本轮在最终状态上复裁。
- 最终实现（`gateway/registry.py` `RegistrationThrottle._evict_sources(clock, *, protect)`）：reserve/release 均传入当前 key 作 `protect` 永不自逐；stale 循环与超额 `while` 循环都只淘汰 `_inflight == 0` 的来源（在途计数永不被逐出销毁）；两处淘汰均同步 pop `_failures` 与 `_inflight`（无残留计数不一致）；`while` 淘汰顺序为无失败史者优先、其余按最近失败时间 LRU（`min` 键 `(bool(history), last_failure)`），洪泛新来源不会冲掉仍活跃失败来源的历史；全部来源皆在途时 `break` 允许暂时超 cap（docstring 明示以实际并发为界），不以破坏状态换有界。
- 最终测试：现用例构造与第 2 轮所见版本已不同——holder 持 2 个在途预留贯穿全程，victim 在洪泛中段累积满 3 次在窗失败后再经两个新洪泛来源（t=19/20），末断言 `_inflight["holder"] == 2`、`reserve("holder", 30)` 与 `reserve("victim", 31)` 均被拒。该断言直接命中 N1 的失败点（失败史保留）与 f002 的在途点。
- 本轮实跑：`test_gateway_registry.py` 全文件单跑 **7 passed**（含上述 N1 用例），另在合跑中复现全绿。执行侧最终门禁自述（unit 710 passed / 2 基线 failed）本轮未全量重跑，但 N1 曾声称与该数字矛盾的那一条非基线失败已不存在。
- **裁决：N1 在最终状态下消解，不再构成 REQUEST CHANGES 理由。** 第 2 轮 test 路的 REQUEST CHANGES 系中间快照产物，其 F001–F010「已修」结论与本轮不冲突。

## 逐项复核表（第 1 轮 code f001–f015）

| 条目 | 核实证据（源码 + 测试） | 结论 |
|---|---|---|
| f001 (important) | `docker_adapter._validate_cache_root` 快速路径在根身份 + sidecar 一致后**重算 `_cache_tree_fingerprint` 并与封存记录比对**（指纹/entry_count 均符才 return），漂移即落全量逐条校验并重封。`test_tree_change_without_sidecar_change_falls_back_to_full`：封存后把文件换成逃逸 symlink、不动 sidecar，断言后代校验被实际调用（计数 >0）且校验抛错拒绝——用例非空转。cache 文件 7 passed | **属实已修** |
| f002 (important) / N1 | 见上节专项裁决：protect + 在途不淘汰 + 两映射同步清理 + 无史优先/LRU；洪泛用例全绿 | **属实已修；N1 消解** |
| f003 | `_cache_tree_fingerprint` 普通文件项为 `f"{st_size}:{st_mtime_ns}"`（含 mtime_ns，内容哈希不做已在 docstring/blueprint 成文信任边界）；`_next_cache_generation` 取内存记录与**磁盘 sidecar 代次的 max + 1**，跨进程单调。`test_fresh_process_continues_generation_from_disk_sidecar` 断言新 adapter 封存代次恰为旧 sidecar +1，实跑通过 | **属实已修** |
| f004 | `gateway/server.py` register 后：旧会话 `close_viewers_for_session` 与旧 ws close 各包 try/except 只记日志；节流先 `release(success=True)` 并置 `handshake_complete`，ACK `ws.send_str` 再包 try/except 只记日志——ACK 失败后代码继续进入 pump，死连接由 pump 收尾 `registry.remove(pid, ws=ws)`，不留无 pump 孤儿。注：ACK 注入失败的集成用例执行侧已在 note 明示未做（harness 所限），本条以代码路径逐行核实为准，与第 2 轮 code 路对该残余的 minor 定级一致，不阻塞 | **属实已修**（测试缺口已如实披露） |
| f005 | `network_policy._install_fail_closed` 故意省略 `--noflush` 做整表替换（docstring 明示理由），正常路径保留 `--noflush`。`test_fail_closed_fallback_replaces_rather_than_appends` 按 argv 区分两路：断言 normal 含 `--noflush`、fallback 恰 2 条（双 family）且均不含。3 passed | **属实已修** |
| f006 | `setup_x11_permissions` 传确定性名 `f"{prefix}-x11-{uuid4().hex[:12]}"`；`_cleanup_orphan_helpers` 角色集含 `x11-permissions` 并映射名称段 `x11` 做同一 fullmatch 校验。`test_x11_orphan_helper_is_reaped_at_startup` 与 remove-failure 用例中的名称前缀断言均通过；docker_boundaries 全文件 7 passed | **属实已修** |
| f007 | 同函数 finally 中 `helper.remove` 包 try/except Exception 只记日志不掩盖结果；异常映射为 `DockerSandboxError` 透传 → `DockerException` 脱敏映射 → 泛 `Exception` 统一映射（wait 的非 DockerException 走第三支）。`test_x11_helper_remove_failure_never_masks_the_outcome`（成功不被 remove 失败翻转）与 wait 失败仍清理用例通过。注：wait 泛异常分支无专属用例，靠代码直读确认，量级 minor 不阻塞 | **属实已修** |
| f008 | `cdp_proxy` 新增 `_rearm_deadline`/`_rearm_ack_timeout_s=5.0`：reader 处理每条消息前先判截止，过期即清 pending，晚到 ACK 不再命中匹配分支；`_allocate_cmd_id` 为单一点同步分配，`send_command`（锁内）与重连 rearm 均经它。`test_reconnect_rearm_late_ack_does_not_restore_health`（窗口 0.3s、ACK 0.6s 迟到，断言 `capture_alive is False` 且 `rearm_count` 不变）与共享分配用例通过；faults 文件 29 passed | **属实已修** |
| f009 | `x11_keymap._init_assigned_attributes` 改 AST 解析 `__init__` 源码，只认 `ast.Assign/AnnAssign` 中 `self.<attr>` 目标；`_verify_selkies_keyboard_abi` 对 `inspect.signature` 包 `(TypeError, ValueError)` 归一为 signature_ok=False → unsupported RuntimeError。`test_attributes_in_comments_do_not_satisfy_the_abi`（六属性仅出现在注释中、真实只赋 `_other`，断言 raises）通过；keymap 文件 7 passed。注：signature 异常用例以 `print`（签名可 introspect 但不匹配）触发同一 RuntimeError 出口，未直接构造 introspect 抛错的 callable，属用例锐度注记，代码归一路径已直读确认 | **属实已修** |
| f010 | `runtime_coordinator.publish_profile_change` 改用 `self.fenced_search_defaults(profile_id, rt.runtime_instance_id)`；`runtime_views.fence_search_defaults` 为单一实现，REST 的 `make_runtime_response` 与 SSE 快照组装（router `get_initial_snapshots`）共用之，coordinator 的 fenced 访问器与之同规则（状态 instance 不符即丢弃）。`test_publish_fences_status_from_another_instance` 断言 publish 事件 `search_defaults is None`，通过 | **属实已修** |
| f011 | `runtime_coordinator.retry_search_defaults` 在 POST 成功后有界轮询：`refresh_search_defaults` 后以 5s deadline、0.25s 间隔刷新，直到 status 的 `request_id` 等于本次请求才 publish/返回。`test_retry_waits_for_the_runners_terminal_status`：handler 前两次轮询回旧 request_id 状态、第三次回本次终态，断言返回 applied 且 `polls >= 3`，通过 | **属实已修** |
| f012 | `runner._clear_stale_x11_state` 无锁分支改 socket 探活：connect 成功→报错保留、ConnectionRefused/FileNotFound→才删 socket、其他 OSError→报错保留；有锁分支保持仅死 PID 删。死 socket 用例（bind 后 close 留拒连文件→被清）与活 socket 用例（listen 中→ raises 且文件保留）均在 faults 文件通过 | **属实已修** |
| f013 | `supervisor/core._quarantine_event_file` 返回 bool（成功 True、OSError/PathSecurityError 记日志 False），三处调用点（unreadable / invalid / REJECTED）均按返回值才 `_advance_event_cursor`；consume 路径传 `dead_letter_spool=False`，forwarder REJECTED 分支改走 `_acknowledge` 删 spool 副本（unlink），单一死信归 core 对 journal 原件的隔离。`test_rejected_disk_event_dead_letters_exactly_once`（quarantine 下 `exit.json` 恰 1 份、spool quarantine 无件、二次扫描不重投）与 `test_failed_quarantine_keeps_event_pending`（隔离 False 时 journal 保留、二次扫描重投 `received == 2`）均通过；event_delivery 文件 17 passed | **属实已修** |
| f014 | `stream_agent/messaging.py` 已无 `__all__`，仅留注释说明 iso_now 转发与不声明 `__all__` 的理由（引 f014） | **属实已修** |
| f015 | `runner._search_defaults_processed_requests` 改 `OrderedDict[str, None]`：命中 move_to_end、插入后 `while len > 64: popitem(last=False)`，上界 64 落地 | **属实已修** |

## 新问题

无。逐项复核未发现处置不实、测试空转或修复引入的新缺陷；上表 f004/f007/f009 三处测试锐度/覆盖注记均为执行侧已披露或量级 minor 的既有定级，不构成新 finding、不阻塞本 Verdict。

## 最终 Verdict

**PASS**

理由：第 1 轮 code 15 条（f001–f015，含 2 条 important）在最终文件状态上逐项属实已修，源码与对应测试双向核对一致；必查 8 个测试文件实跑 83 passed / 0 failed。第 2 轮 test 路唯一阻塞项 N1 经专项复裁在最终状态下消解（实现已按 protect/在途不淘汰/LRU 重写，`test_gateway_registry.py` 全文件 7 passed）。至此第 1 轮双路 + 第 2 轮遗留的全部阻塞项均已关闭。

# Task review t040（reviewer_focus: 测试）

- task：`t040_environment_preview_thumbnails`
- spec：`docs/tasks/t040_environment_preview_thumbnails/task.md`
- diff_anchor：`d9e0843545275d26f64d7b2932fa933c4e3263fb`
- target：`git -C '<repo_root>' diff d9e0843545275d26f64d7b2932fa933c4e3263fb`
- round：1
- reviewed_at：2026-11-08T02:18:36+08:00

reviewed_scope: dd68f28d604368f2

落点校验：`git rev-parse --show-toplevel`（不带 `-C`，workdir 置于目标仓）输出精确等于 `<repo_root>`。`git status --short` 中 `?? src/frontend/node_modules` 为测试运行产物，非交付文件；全部交付文件已 `git add -N` 以 `A` 状态进入完整 diff。`git diff --check` 通过。

## Findings

### t040_test_f001 - AC-001 点名的「以已知页面内容比对」在真实栈 E2E 未落地，截图内容正确性缺有效证据

- 严重度：important
- 锚点：AC-001
- 位置：`tests/e2e/test_profile_preview_e2e.py:88-89`（截图内容断言）、`:15-19`（`MARKER_HTML`/`PREVIEW_MARKER_40`）、`:74`、`:131`（marker 仅用于 DOM 状态）
- 问题：AC-001 明文要求「内容为当前活动标签页的网页区域，不含浏览器标签栏与地址栏（真实栈 E2E 以已知页面内容比对）」，测试策略亦写「真实栈 E2E 验证截图内容区域」。`test_profile_preview_capture_and_http_contract` 注入了专门设计的大字号高对比 `PREVIEW_MARKER_40`（`:15-19`），但 `PREVIEW_MARKER_40` 只在 `browser_eval` 的 `PAGE_STATE` DOM 文本检查里被读取（`:74` `first["value"]["marker"]`、`:131` `after["value"]["marker"]`，属页面状态 / AC-007 范畴），从未用于下载 JPEG 的内容比对。全仓新增测试无 JPEG 解码 / 像素 / OCR 比对代码（对照 `test_frontend_media_e2e.py:285-359` 的 iframe 像素比对，preview E2E 未复用）。截图内容相关断言仅 `jpeg_width(response.content) == 480`（`:88`，`jpeg_width` 只解析 SOF 头取宽度）与 `len(response.content) > 1000`（`:89`）。可复现：把 `MARKER_HTML` 换成任意页面，或让 `capture_once` 错误地截到含标签栏/地址栏的全屏图、非活动标签页、纯色大图，只要产出一张 480 宽且 >1000 字节的 JPEG，`:84-95` 与 `:120-131` 全部断言仍 PASS；`_wait_for_preview`（`:47-58`）就绪 predicate 也只看 status 200。即断言对「内容 = 活动标签页网页区域 / 不含浏览器 UI」这一 AC 核心行为无鉴别力，是 spec 点名的验证方式被尺寸 / 字节数检查替代。unit `test_capture_once_scales_clip_and_commits_without_activation`（`test_runtime_agent_preview.py:77-117`，`_FakeCdp` 模拟的 clip 参数）与 s016/d035 spike 是机制层间接证据，不能替代 spec 要求的真实栈 E2E 内容比对。实施侧自述（`progress.md`「验证（定向）」）也只列「页面 marker 存活」，未声称内容比对，印证该验证方式未落地。AC-001 打勾缺少对该子行为的有效测试支撑，判 TICK-VOID。
- 建议：E2E 下载 JPEG 后做内容比对——解码像素或 OCR 确认 `PREVIEW_MARKER_40` 出现在截图内，用已知白底 `#ffffff` 边界确认截图仅含 viewport 网页区域（无标签栏 / 地址栏色带），并确认截的是注入 marker 的那个活动 target；保留 480 宽断言作为补充，不以尺寸 / 字节数代替内容比对。

### t040_test_f002 - AC-005「重置 / 删除 Profile 后预览被清除」无测试能捕获清除逻辑回归

- 严重度：minor
- 锚点：AC-005
- 位置：`tests/integration/test_preview_late_writes.py:167-185`（唯一 `reset_profile` 用例）、`:189-209`（复制用例）、`:83-85`（`_late_frame`）、`src/backend/cbrowser/services/profile_service.py:473`（delete 路径）、`:792`（reset 路径）
- 问题：AC-005 含「重置或删除 Profile 后预览被清除」。新增测试里唯一调用 `reset_profile` 的是 `test_old_instance_after_reset_is_dropped`（`:172`），其断言路径 `_assert_discarded`（`:88-119`）先经 `_late_frame`（`:83-85`）主动 `clear_preview(directory)` 再写 `latest.jpg`，随后断言 `not (directory / IMAGE_FILE).exists()`（`:117`）——该断言证明的是「迟到写入被丢弃」（AC-004），不是「reset 清除了已有预览」。`test_duplicate_with_browser_state_does_not_copy_preview`（`:189-209`）测复制不复制，不测删除清除；全仓新增测试无 `delete_profile` 调用。可复现：移除生产 `profile_service.py` delete 路径 `:473` 与 reset 路径 `:792` 两处 `await self._clear_preview_state(profile_id)`，现有全部新增测试及门禁仍 PASS（seed 预览被 `_late_frame` 的 `clear_preview` 清掉，两段生产清除逻辑无任何断言触达）→ 该生产逻辑缺测试覆盖。AC-005 的「停止后保留最后一帧」（E2E `:187-190`）与「含浏览器状态复制不复制预览」（integration `:189-209`）已有真证据，故此项为覆盖扩展，minor，不推翻 AC-005 打勾。
- 建议：integration 增两例，seed 预览后分别调用 `delete_profile` / `reset_profile`，直接断言 `get_preview_dir(pid)/latest.jpg`、`policy.json` 均不存在且 `preview_captured_at is None`。

## 结论

- 改测方向复核：本轮 diff 中所有测试文件均为新增（`A`），无就地修改既有测试断言、无「让断言迁就当前实现」。`tests/fixtures/gateway_probe/topology.py` 是共享 E2E 夹具的目录 / 挂载拓扑对齐（`CBROWSER_DB_PATH` `/metadata/control.db` → `/data/cbrowser.db`、`data_dir → /data` 单一数据根、删 `metadata_dir` 死代码），有归因（`progress.md`「用户监督纠正」撤销 `CBROWSER_PREVIEW_ROOT` 专用旋钮、对齐生产 compose），目的是让 API 能读到 `data_root/profiles/{id}/preview`，非断言改动、非弱化；门禁 `junit/e2e.xml` 中两个 preview 用例均 PASS（25.568s / 51.431s）、e2e 53 passed 佐证既有 E2E 未被破坏。无「迁就实现」的改测。
- 危险模式调查与放行说明：逐条扫描无 `.skip` / `.only` / `@ts-ignore` / `@ts-expect-error` / `eslint-disable` / `pytest.mark.skip` / `assert True` / `expect(true)` / 条件跳过弱化断言 / 注释掉断言 / 反转 expect / 删测试块 / `.value =` 冒充交互。`status_code in (401, 403)`（`test_preview_router.py:86`、E2E `:118`）、`in (200, 202)`（E2E `:188`）为合法多值。`poll_until`（`tests/fixtures/wait.py:42-64`）超时抛 `TimeoutError` 且返回真实值供后续断言，`_wait_for_preview` 就绪 predicate 仅判 status 200，content-type / ETag / 304 / 宽 480 断言在 poll 之后，不掩盖缺陷、不弱化断言；前端 `waitUntil`（`sse_preview.test.ts:91-101`）超时 resolve 后由 `toHaveLength` / `toEqual` 兜底，不会假绿。`test_supervisor_preview_policy.py` 8 处 `# type: ignore[method-assign]`（`:104,133,168,210,233,254,274,290`）命中「静默错误」字面，调查后放行：`SupervisorCore._agent_uds_client`（`core.py:1660`）是 async 方法，测试将其替换为 `_control_uds` / `_health_uds` 的 asynccontextmanager fake（系统边界 UDS 客户端注入），注释仅抑制 mypy「给方法赋值」静态告警，不删 expect、不弱化断言、不掩盖失败、不降低行为覆盖，按「调查后判定，非盲目语法命中」放行，特此说明。mock 边界核查：`_FakeCdp`（CDP）、`_control_uds`/`_health_uds`（UDS）、`_FakeAPI`（HTTP）、monkeypatch `publish_profile_preview` 为 spy（记录调用并断言 `published == []` / `== [(pid,"t1")]`，真实发布逻辑由 `test_transient_frame_reaches_live_subscriber_without_history` 用真实 coordinator 覆盖）、`stubFetch` 重定向到真实本地 http server、`vi.fn()` 仅替回调，均未 mock 被测逻辑本身。
- 本轮新发现：2 条（1 important / 1 minor）
- 未进表的提示：
    - AC-006「内容 / 路径不进日志与事件」：`test_error_body_never_leaks_path_or_image_content`（`test_preview_router.py:134-147`）与 `test_meta_json_never_contains_image_bytes`（`test_preview.py:174-186`）覆盖错误响应与 meta.json；生产日志仅记 `error_type` / `failures`（`preview_capture.py:146-150`）、SSE 帧断言只查字段包含未做「不含路径 / 内容」负向断言（`test_preview_late_writes.py:288-292`），属覆盖扩展，minor 级不单列。
    - AC-007「活动标签页不变」：E2E `browser_eval` 用固定 `target_id`（`:163,166`）求值，d035 已证多标签下 visibility / focus 恒真，`after == before`（`:169-170`）对焦点 / 可见性及标签切换鉴别力弱；由 `test_runtime_agent_preview.py:108-110` 断言未调用 `Target.activateTarget` / `Page.bringToFront` 补足，结合 d035 的 CDP 限制说明，组合覆盖可接受，不单列 finding。
    - 15s 调度循环 `PreviewCaptureLoop.run()`（`preview_capture.py:138-157`）无直接单测，仅 `CAPTURE_INTERVAL_SEC == 15.0` 常量断言（`test_preview.py:171`）与 E2E 17s 跨周期（`:165`）间接覆盖，属覆盖扩展。
    - 门禁证据与 p052 处置核对：`013227` 门禁 `manifest.json` / `suites.tsv` 显示 9 个非 E2E suite 全 exit 0、e2e 仅 `test_t019_switch_and_refresh_first_frame_within_2s_host_only` FAILED（`logs/e2e.log:184`，3.3427s > 2.0，t032 登记基线）；两个 preview E2E 用例在 `junit/e2e.xml` 均 PASS，「定向 E2E 2 passed」与全量门禁一致。p052 第 3 次复现（`015845` 第 2 轮作废门禁）已追记进 `docs/pending/todo/p052_selkies_evict_close_code_1006.md` 证据链（附第 1 轮 PASS、t039 第 10 轮 PASS 对照），明确「保持 `close_code == 4001` 精确断言，不放宽为 1006 白名单」，未删 / 弱化断言、未把该用例加入允许失败集合、未以波动放过；第 2 轮门禁按用户监督决定作废（kill PID 1406 及子进程、按 label 清理容器），最终门禁仍取 `013227`（允许失败集合仅 t019）。处置合规，不出 finding。
    - contract / 生成物测试：`config/docker/supervisor_runtime/Dockerfile` 与 `Dockerfile.dockerignore` 补 `preview.py` 白名单，使既有 `test_docker_build_contexts.py` 两例（`test_copy_sources_admitted_by_dockerignore`、`test_supervisor_context_admits_every_copied_package_file`）通过——是补齐构建配置而非弱化测试；`test_t035_openapi_contract` / `test_domain_and_repository` / `test_runtime_agent_protocol_export` 未在 diff 中改动（原样保留），contract suite exit 0。前端 generated `preview_captured_at?: string | null`（`cbrowser_v1.d.ts:1266`）与 `runtime()` 夹具（`EnvironmentCard.preview.test.tsx:82`）同步；`test_preview_router.py` 的 data_root 经 `create_app(db_path=tmp_path/"preview.db")` → `data_root=resolved_db.parent=tmp_path`（`app.py:126`）注入，读写同一真实路径，401/403 / 404 / 304 端点校验真实覆盖。
    - 7 视角正交体检已逐视角扫描：安全（鉴权 / 隐私）、正确性（策略代次与实例 fencing）、契约·Breaking（OpenAPI / 协议 / generated 一致性）、性能·资源（15s 周期）、架构·可维护性（mock 边界）、健壮性·可观测（失败 / 迟到路径）六轴未命中阻断项，细节见上；「测试·文档·规格」轴命中 f001 / f002。
- 总体判断：AC-001 明文要求的「真实栈 E2E 以已知页面内容比对」未落地，截图内容正确性缺有效测试证据、打勾作废；其余 6 条 AC 测试可信、覆盖充分、门禁证据一致。存在 1 条未解决 important，FAIL。
- 系统性 follow-up：p052 已有 tid（Selkies evict close 1006，收尾阶段以独立 follow-up 根治）；f001 / f002 均属本 task 交付面内修复，无需新建跨 task follow-up。写「无」。

### AC 复验方式

- AC-001：TICK-VOID，trust_prior。真实栈 E2E 内容比对属 Docker 部署态、本轮无法重跑；独立查证 `test_profile_preview_e2e.py:88-89` 仅断言宽 480 + 字节 > 1000、`PREVIEW_MARKER_40` 只用于 DOM 状态检查，spec 点名的「以已知页面内容比对」未落地，依赖门禁 junit 2 passed 不足以支撑内容正确性打勾。
- AC-002：TICK-VALID，re_verified。`test_preview_router.py:84-147` 四例 + E2E `:84-95,115-118` 真实走 `create_app`/TestClient 与 HTTPS 端点，断言未登录 401/403、image/jpeg、no-store、ETag 含 captured_at、304、无预览 / 撤销 404。
- AC-003：TICK-VALID，re_verified。`test_preview_late_writes.py:243-292` 断言 50 次 `publish_profile_preview` 不进 `_history`、SSE 重连重放 3 帧全为 runtime_state 且不含 profile_preview；`test_preview_repository.py:34-51`、`sse_preview.test.ts`、`EnvironmentCard.preview.test.tsx:137-152` 覆盖 `preview_captured_at` / null 占位 / `?v=` 版本 URL 刷新。
- AC-004：TICK-VALID，re_verified。`test_preview_late_writes.py:123-185` 真实注入关闭时截图进行中 / 旧代次通知 / 重置后旧实例回传三类时序并断言不复活（`:102-119`）；`test_runtime_agent_preview.py:195-226` 即时 in-memory 策略、`test_supervisor_preview_policy.py:98-159` 即时 control 下发；E2E `:172-178` 撤销后 404。
- AC-005：TICK-VALID，re_verified。E2E `:187-190` 停止后保留最后一帧、`test_preview_late_writes.py:189-209`「含浏览器状态」复制不复制预览为真证据；reset/delete 清除缺直接断言另列 minor f002，不推翻打勾。
- AC-006：TICK-VALID，re_verified。`test_preview.py:41,59-60` 与 E2E `:124-126` 断言 0600；`test_preview_router.py:134-147` 错误响应不含路径 / 图片、`test_preview.py:174-186` meta.json 不含图片字节，生产日志仅记 `error_type`/`failures`（`preview_capture.py:146-150`）。
- AC-007：TICK-VALID，re_verified。E2E `:162-170` 截图前后 visibility/hidden/focus/marker/title 不变（17s 跨 15s 周期）+ `test_runtime_agent_preview.py:108-110` 断言未调用 `activateTarget`/`bringToFront`；d035 已证 CDP 多标签恒真限制，组合覆盖成立。

coverage = 6 / 7

verdict: FAIL

## Round 2 (2026-11-08T03:00:00+08:00)

reviewed_scope: 6b3cc2bf67d285f0

落点校验：`git rev-parse --show-toplevel`（不带 `-C`，workdir 置于目标仓）输出精确等于 `<repo_root>`。`git status` 中全部交付文件以 `new file:` / `modified:` 进入「Changes not staged」段（已 `git add -N`），唯一未跟踪项 `src/frontend/node_modules` 为测试运行产物。全量核对 `git diff d9e0843545275d26f64d7b2932fa933c4e3263fb`；`generate_requirements.sh --check` 6/6 通过，依赖契约文件（pyproject.toml / uv.lock / gate-requirements.txt / 各 requirements.txt）均未进 diff。门禁 `.scratch/t040_evidence_20261108_024359/junit/e2e.xml`：两例 preview E2E 均 PASS（52.978s / 53.206s），非 skip；全量 106 例仅 t019 基线 1 failure、2 skipped（t032 probe，非 preview）。不采信 `progress.md` 处置表自称「已修」，以下全部以 diff / 测试代码为准。

### 前轮 finding 复核

**t040_test_f001（important，AC-001 TICK-VOID）— 已消除。** 逐项核实：

- 已知页面内容比对落地：`test_profile_preview_e2e.py:18-20` 定义 `COLOR_A=(0,51,0)`(#003300)、`COLOR_B=(204,0,0)`(#cc0000)、`COLOR_TOLERANCE=20.0`（±20/通道）；`:36-43` `DECODE_SCRIPT` 用 PIL `Image` / `ImageStat` 对中心 50% 区域 `box=(w//4,h//4,3w//4,3h//4)` 求平均 RGB；`:93-101` `assert_center_color` 同时断言 Pillow 解码宽 ==480、SOF 头 `jpeg_width`==480、每通道 `abs(value-target)<=20`。非恒真、非弱化、非纯存在性断言。
- 双色 + 变色跟随：`:22-26` MARKER_HTML body 为纯色 A；`:135-136` 先取基线帧 ETag；`:144-156` `frame_after_navigate` 仅接受 `etag != baseline_etag` 的新帧（captured_at 作 ETag，避开 navigate 前白页），`:161` 断言中心色 A；`:184-189` 复用 `target_id` recolor `#cc0000`；`:191-203` `recolored` 仅接受 `etag != etag`（navigate 帧）的新帧，`:204-205` 断言中心色 B 且 `color_a != color_b`。页面变色后预览 ETag 变化且中心色跟着变，证明实时重截当前活动标签页。基线帧 / navigate 后等新 ETag 的时序把 baseline 白页排除在 predicate 之外，且 `assert_center_color` 对白页必然红灯，不构成假绿。
- 字节相似度 / `0.97` 启发式彻底移除：全仓 `rg '0\.97|SequenceMatcher|difflib|bytes_similar'`（\*.py）零命中；Round 1 的 `len(response.content) > 1000`（旧 `:89`）已不在文件；内容正确性不再由尺寸 / 字节数代替。`PREVIEW_MARKER_40` 仍作 DOM 状态（AC-007），内容比对已改由像素语义承担。
- 镜像 Pillow 零契约改动：`:63-90` `decode_center_color` 用既有 E2E 环境变量 `CBROWSER_STREAM_TEST_IMAGE`（`tests/fixtures/e2e_env.py:14` `REQUIRED_E2E_ENV`）以 `docker run --entrypoint python3` 复用 stream_runtime 镜像；`config/docker/stream_runtime/requirements.txt:42` `pillow==13.0.0 # via selkies` 为镜像既有依赖，未新增；依赖契约文件未进 diff，`generate_requirements.sh --check` 全绿。
- 容差语义：`±20` 容纳 JPEG q70 有损压缩对纯色中心区域的色偏；两目标色 R / G 通道差 >150，±20 不会让错误色蒙混通过；非「迁就实现输出」。
- 双色鉴别力：任意 480 宽静态图 / 缓存旧帧 / 错页面 / 白页无法同时通过 A±20、recolor 后 B±20 与 `color_a != color_b`，能捕获「截了非活动标签页内容 / 固定图」。诚实边界：`browser_oracle.py:51-53` 断言仅 1 个 page target，且取中心 50% 区域，该测试不独立证明「多标签中选对活动 target」与「不含浏览器 UI 顶部色带」；两子行为由 s016 / d035 spike（真实 Chromium 双标签实测）、`preview.py:151-161` 的 viewport clip 与 `test_runtime_agent_preview.py:78-120` 的 clip / 未激活断言补足，属披露不构成假绿。
- 2 例仍触达生产链路：例 1 no-store(`:158`)、ETag(`:159-160`)、304(`:163-167`)、未登录 401/403(`:207-211`)、0600(`:213-219`)、runtime `preview_captured_at`(`:169-182`)；例 2 撤销后 404(`:265-271`)、重新启用(`:273-278`)、停止保留(`:280-283`)、17s 跨周期页面状态不变(`:255-263`)。AC-001 打勾恢复成立。

**t040_test_f002（minor）— 已消除（附透明观察）。** 新增 `tests/integration/test_preview_clear_on_lifecycle.py:35-63`：`_seed`(`:21-31`) 经生产 `write_policy` + `commit_preview` 写入 `latest.jpg` / `meta.json` 并 `assert is_file()` 确认，再真实调用 `service.delete_profile`(`:50`) / `service.reset_profile`(`:61`)，断言 `latest.jpg` 与 `meta.json` 均 `not exists()`(`:51-52`、`:62-63`)。「移除 `_clear_preview_state`（`profile_service.py:278-290`）调用会红」逐路径核实：reset 路径 `source_dir`（测试 `user_data_dir=tmp_path/profiles/rst/profile`，`:56`）与 `preview_dir`（`tmp_path/profiles/{reset.id}/preview`，`preview.py:37-38`）不同路径，`:743-791` 只 rename / 重建 / rmtree `source_dir`，移除 `:795` 后 `latest.jpg` 残留 → `:62` 红；delete 路径 `:470-475` `_remove_profile_directory(profiles/{id})` 连坐删含 preview 子目录，单独移除 `:476` 时 `:51` 仍 PASS（该用例对 delete 专有清除调用不敏感，如实披露）。两处同时移除 → reset 用例红，Round 1「移除两处调用全部新增测试仍 PASS」缺口关闭。另：未断言 `policy.json` 清除与 DB `preview_captured_at` 复位（`:283-290` 另两项职责），属覆盖扩展。`test_preview_late_writes.py` 仍为 Round 1 态（8 例、`:167-185` 迟到写入、`:83-85` `_late_frame` 先 `clear_preview` 再写），未改未弱化。两处观察均 minor 级扩展，不单列、不凑数。

### 本轮新发现

0 条。危险模式扫描（新增 / 改动测试）：恒真断言、弱化断言、删 / 反转 / 注释 expect、`.skip` / `.only` / `@Ignore` / `eslint-disable` / `@ts-ignore` 均无；`assert color_a != color_b`(`test_profile_preview_e2e.py:205`) 在两处实质像素断言之后，冗余但非假绿制造者；`assert meta is not None`(`test_runtime_agent_preview.py:115`)、`assert read_meta(...) is not None`(`test_supervisor_preview_policy.py:146`)、`assert health is not None`(`:212`) 为 Round 1 既有中间检查，后接实质字段断言，非 AC 唯一证据。`# type: ignore[method-assign]` 新增 2 处(`test_supervisor_preview_policy.py:290,322`) 与 Round 1 已调查放行的 8 处同构（UDS 边界 fake 替换 async 方法，仅抑制 mypy 告警，不删 / 弱化断言），一致放行。无 `if cond: expect` 条件跳过弱化；`poll_until` 超时抛 `TimeoutError`，ETag 变化 predicate + 颜色断言双重兜底，不弱化。阈值：`COLOR_TOLERANCE=20.0` 有明确 JPEG 压缩语义，非放宽掩盖。mock 边界：`_FakeAPI` / `_control_uds` / `_health_uds` / `_FakeCdp` 为系统边界 fake，未 mock 被测逻辑本身。

新增用例真实触达生产逻辑核实：

- `test_apply_preview_policy_fences_stale_epoch_instance_and_duplicate`(`test_supervisor_preview_policy.py:317-362`)：真实 `SupervisorCore.apply_preview_policy` + `read_policy` 读真实文件，断言旧 epoch(4\<5) / 旧实例(epoch6 inst_2) / 重复 request_id 不更新或不重复 dispatch，新 epoch(6 inst_1) 落 epoch=6 且 dispatch 1 次，epoch 单调与 fence 真实。
- `test_set_policy_persists_the_live_policy`(`test_runtime_agent_preview.py:234-241`)：真实 `PreviewCaptureLoop.set_policy` + `read_policy` 断言 policy 落文件。
- `test_preview_policy_local_failure_fails_the_patch`(`test_preview_router.py:150-157`)：`monkeypatch` `get_preview_dir`→`lambda:None` 注入「本地预览存储不可用」边界，触发生产 `router.py:79-84` 的 500 分支（PATCH handler `:413-416` 真实调 `_apply_preview_policy`），断言真实 HTTP 500；非 mock 被测逻辑、非测 mock 存在。

改测方向复核：本轮测试文件相对 anchor 均为新增（A），无就地改既有断言、无「让断言迁就实现」。

未进表提示：`test_profile_preview_e2e.py:64` 直读 `os.environ[...]` 而非既有 `require_e2e_env`（`e2e_env.py:84-103`），缺失时 `KeyError` 红灯而非假绿，属基础设施一致性偏好；E2E 单标签中心色对多标签 / 无 UI 色带不独立鉴别（见 f001 披露）；delete 用例对 `:476` 不敏感、`policy.json` / DB 字段未断言（见 f002）。均 minor 级，不阻断。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`test_profile_preview_e2e.py:18-20,36-43,63-101,135-161,184-205` Pillow 中心色 ±20 双色比对、宽 480 双校验、ETag 变化后 A→B 变色跟随，独立复验像素语义测试真实覆盖「内容 = 当前活动标签页网页区域」；多标签 / 无 UI 边界由 s016 / d035 + `preview.py:151-161` clip + clip unit 补足。
- AC-002：TICK-VALID，re_verified。`test_preview_router.py:84-147` + E2E `:157-167,207-211` 真实走 create_app / TestClient 与 HTTPS 端点，断言未登录 401/403、image/jpeg、no-store、ETag 含 captured_at、304、无预览 / 撤销 404。
- AC-003：TICK-VALID，re_verified。`test_preview_late_writes.py:243-292` 断言 50 次 `publish_profile_preview` 不进 `_history`、SSE 重连重放 3 帧全 runtime_state 不含 profile_preview；`test_preview_repository.py:34-51`、`sse_preview.test.ts`、`EnvironmentCard.preview.test.tsx` 覆盖 `preview_captured_at` / null 占位 / `?v=` 刷新。
- AC-004：TICK-VALID，re_verified。`test_preview_late_writes.py:123-185` 真实注入关闭时截图进行中 / 旧代次通知 / 重置后旧实例回传三类时序并断言不复活，`test_supervisor_preview_policy.py:317-362` epoch fence，E2E `:265-271` 撤销后 404。
- AC-005：TICK-VALID，re_verified。E2E `:280-283` 停止后保留最后一帧、`test_preview_clear_on_lifecycle.py:35-63` delete / reset 清除（移除 reset 清除调用会红）、`test_preview_late_writes.py:189-209` 复制不复制预览。
- AC-006：TICK-VALID，re_verified。`test_preview.py:41,59-60` 与 E2E `:216-219` 断言 0600；`test_preview_router.py:134-147`、`test_preview.py:174-186` 错误体 / meta 不泄路径与图片字节。
- AC-007：TICK-VALID，re_verified。E2E `:255-263` 17s 跨 15s 周期 visibility / hidden / focus / marker / title 不变 + `test_runtime_agent_preview.py:108-110` 断言未调用 activateTarget / bringToFront，结合 d035 CDP 限制组合覆盖成立。

coverage = 7 / 7

verdict: PASS

## Round 3 (2026-11-08T04:00:00+08:00)

reviewed_scope: f002728c2b1ebfc0

- round：3
- 落点校验：不带 `-C` 的 `git rev-parse --show-toplevel`（workdir 置于目标仓）= `<repo_root>`，通过。`git -C '<repo_root>' diff d9e0843545275d26f64d7b2932fa933c4e3263fb` 全量复核；`git status --short` 中交付文件均以 `A`/`M` 进入 diff，`src/frontend/node_modules` 为运行产物非交付物。不采信 `progress.md` 处置表，全部以 diff / 生产代码 / 测试代码为准。全仓 `tests/` 与 `*.py` 零残留 `0.97` / `SequenceMatcher` / `difflib` / `bytes_similar`（唯一 `difflib` 命中在 `.repo_template/scripts/render_review_prompts.py`，模板工具非交付逻辑）；依赖契约文件（pyproject.toml / uv.lock / 各 requirements.txt）相对 anchor diff 0 行，`config/docker/stream_runtime/requirements.txt:42 pillow==13.0.0` 与 `tests/fixtures/e2e_env.py:14 CBROWSER_STREAM_TEST_IMAGE` 均为镜像 / 夹具既有、未改动。

### 前轮 finding 复核

**t040_test_f001（important，AC-001「真实栈 E2E 以已知页面内容比对」）— 持续已消除。** 像素语义完整：`test_profile_preview_e2e.py:18-20` `COLOR_A=(0,51,0)` / `COLOR_B=(204,0,0)` / `COLOR_TOLERANCE=20.0`；`:36-43` `DECODE_SCRIPT` 用 PIL `Image`/`ImageStat` 对中心 50% 区域求平均 RGB；`:63-90` `decode_center_color` 经 `CBROWSER_STREAM_TEST_IMAGE` 以 `docker run --entrypoint python3` 复用 stream_runtime 镜像既有 Pillow；`:93-101` `assert_center_color` 同时断言 Pillow 解码宽 480 与 SOF 头 `jpeg_width` 480、每通道 `abs(value-target)<=20`；`:135-136` 先取基线帧 ETag，`:144-161` navigate 后仅接受 `etag != baseline_etag` 的新帧并断言中心色 A（白页 baseline 被 predicate 排除，且 `assert_center_color` 对白页必红）；`:184-205` recolor 后仅接受 `etag != etag` 的新帧并断言中心色 B + `color_a != color_b`。全仓零 `0.97` / 字节相似度启发式；依赖契约零改动。非恒真、非弱化、非纯存在性断言，打勾持续成立。

**t040_test_f002（minor，AC-005 delete/reset 清除）— 持续已消除。** `tests/integration/test_preview_clear_on_lifecycle.py:21-31` `_seed` 经生产 `write_policy` + `commit_preview` 写帧并 `assert is_file()`；`:35-63` 真实调用 `service.delete_profile` / `service.reset_profile`，断言 `latest.jpg` 与 `meta.json` 均 `not exists()`。两处生产清除调用被真断言触达（移除 reset 清除即红），Round 1 缺口持续关闭。`test_preview_late_writes.py` 仍为 Round 1 态、未弱化。

**Round 2 结论（f001/f002 均判已消除、7 条 TICK-VALID、PASS）— 持续成立。** 逐条复核 AC 证据文件均在且未弱化（见下方各测试复核与 AC 复验方式），无「修成另一种弱化形式」。

**f004 修复后新增 / 改动测试复核（本轮重点，逐条）：** 生产侧 `preview_capture.py:73-87` `set_policy` 现为纯内存、epoch 单调（`epoch < self._policy.epoch` 时 return）、`_wake.set()`，**不写文件**；`capture_once:90` `policy = self._policy or read_policy(self.directory)`；`commit_preview`（`preview.py:101-118`）落盘前重读共享 `policy.json`，`_policy_matches` 不命中即 `clear_preview` 且不写帧。

- `test_control_preview_policy_updates_in_memory_policy`（`test_runtime_agent_preview.py:196-228`）：真实 `create_agent_app` + `httpx.ASGITransport` POST `/control` → `agent.py:507-516` → `preview_loop.set_policy`；断言 `loop.policy == PreviewPolicy(enabled=True, epoch=7, inst-1)`（下发真改内存策略）与 `read_policy(directory) is None`（Agent 不写 policy）。真触达生产链路；非恒真——目录初始无 policy 文件，若 `set_policy` 写文件则 `read_policy` 非 None 即红。
- `test_set_policy_is_epoch_monotonic_and_never_writes`（`:232-242`）：真实 `set_policy(9)` 后 `set_policy(8)`，断言 `loop.policy.epoch == 9`（单调）与 `read_policy(directory) is None`（不写文件）。非恒真——无单调检查则 epoch 变 8 即红，写文件则 `read_policy` 非 None 即红。
- `test_stale_uds_cannot_reenable_capture_after_revocation`（`:246-261`）：`write_policy(enabled=False, epoch=10)` 预置撤销态共享文件 → `set_policy(True,10)` → `set_policy(True,9)`（旧代次乱序 / 迟到）→ 断言 `loop.policy.epoch == 10` → 真实 `capture_once()` → 断言 `not latest.jpg.exists()` 与 `read_meta is None`。被测 `set_policy` / `capture_once` / `commit_preview` 均为真实生产代码，`_FakeCdp` 仅 CDP 系统边界 fake；断言非恒真、不弱化、不 mock 被测逻辑。诚实披露：共享文件「不回退」经 `commit_preview` 重读文件的不变量由「撤销态下不落 latest.jpg」等价捕获（未逐字段断言 `read_policy` 值），配合上两条 `read_policy is None` 直接断言「Agent 不写文件」，新语义覆盖完整。
- 「Agent 不写文件」新语义（而非沿用旧断言）：Round 2 `test_set_policy_persists_the_live_policy`（report `:234-241`，断言 policy 落文件）已不在当前文件，替换为 `test_set_policy_is_epoch_monotonic_and_never_writes` + `test_control...` 的 `read_policy is None`，并由 `test_stale_uds...` 撤销态文件兜底补强；未沿用旧断言。
- 其余集成 / 单测真触达生产逻辑核实：`test_preview_late_writes.py:123-185` 三类迟到写入经 `_assert_discarded:88-119` 真实 `record_preview_capture` / `report_preview_observation` / `get_runtime`，`:243-292` 真实 coordinator / broadcaster 重放环 50 帧隔离，`:189-209` 复制不复制预览；`test_preview_router.py:150-157` `monkeypatch get_preview_dir→None` 注入「本地预览存储不可用」边界触发 PATCH handler 真实 500 分支（`router.py` 无 `except Exception` 包裹），断言 `500`，非 mock 被测逻辑；`test_supervisor_preview_policy.py:317-362` 真实 `apply_preview_policy`，对照 `core.py:1810-1840` 的 stale epoch / duplicate / stale instance fence 前置 `write_policy:1837`，断言旧代次 / 旧实例 / 重复 ID 不更新文件且 `control_calls == []`、新 epoch 落 6 且 dispatch 1 次，epoch 单调与 fence 真实。10 处 `# type: ignore[method-assign]`（`:104,133,168,210,233,254,274,290,322`）与 Round 1/2 已调查放行同构（UDS 边界 fake 替换 async 方法，仅抑制 mypy 告警），一致放行。

### 本轮新发现

0 条（critical 0 / important 0 / minor 0）。逐项扫描与判定：

- 危险模式：diff 中 10 个测试文件为 `A`（新增）、`tests/fixtures/gateway_probe/topology.py` 为 `M`（夹具目录 / 挂载对齐，Round 1/2 已复核非断言改动）；新增行无恒真断言（`assert True` / `expect(true)` / 纯存在性当 AC 证据）、弱化断言（`toBe`→`toContain` / 正则 / `>=` / `toBeTruthy`）、删 / 反转 / 注释 expect、`.skip` / `.only` / `pytest.mark.skip` / `@Ignore`、`@ts-ignore` / `eslint-disable` / 条件跳过弱化断言（`if cond: expect`）、阈值放宽、程序赋值替代真实交互、mock 被测逻辑本身。`status_code in (401,403)` / `in (200,202)` 为合法多值；`poll_until` 超时抛 `TimeoutError`，ETag 变化 predicate 后接中心色断言双重兜底；`COLOR_TOLERANCE=20.0` 有 JPEG q70 有损压缩语义、非放宽掩盖。全仓 `git grep` 命中的 `pytest.skip` / `toBeTruthy` / `# type: ignore` 均落在既有非本 task 测试文件（如 `test_agent_executor_chain.py`、`SettingsPage.test.tsx`），非本次 diff 改动，不因语法命中出 finding。mock 边界：`_FakeCdp`（CDP）、`_control_uds` / `_health_uds`（UDS）、`_FakeAPI`（HTTP）、`spy`（发布记录，`published == []` / `== [(...)]` 实质断言）、`stubFetch`（本地 http server 重定向）均为系统边界，未 mock 被测逻辑。
- E2E 双色鉴别力：单标签真栈下，截到非活动标签页（非 marker 色页）→ `assert_center_color(response.content, COLOR_A)` 中心色 ±20 红；任意 480 宽静态图若恰为 A 色但 recolor 后不变 → `:204` COLOR_B 断言红 + `:205 color_a != color_b` 红；白页 baseline 被 ETag predicate 排除且对白页必红。故能捕获「截了非活动标签页 / 任意 480 宽图」。诚实边界（Round 2 已披露）：`browser_oracle` 仅 1 个 page target、取中心 50%，不独立证明「多标签中选对活动 target」与「不含浏览器 UI 顶部色带」，由 s016 / d035 spike + `preview.py:143-161` viewport clip + `test_runtime_agent_preview.py:78-111` clip / 未激活断言补足，属覆盖边界非假绿，不构成 finding。
- `test_stale_uds...` 真能捕获 f004 回归（把 `set_policy` 改回无条件写文件会红）：形式 A（保留 epoch 单调 + 加回 `write_policy`）——首条 `set_policy(True,10)` 把共享文件覆盖为 `enabled=True/epoch=10`，`capture_once` 用内存 enabled 策略截图、`commit_preview` 重读文件命中 `_policy_matches` → 写 `latest.jpg` → `:260` `assert not exists` 红；形式 B（无单调 + 无条件写，即 f004 原始竞态）——次条 `set_policy(True,9)` 把文件回退 `enabled=True/epoch=9` 且 `loop.policy.epoch` 变 9 → `:258` `assert == 10` 红。两种回归形式均红，验证「乱序 UDS 不能回退共享 policy / 不能复活 latest.jpg」真实有效。
- 改测方向复核：相对 anchor 的测试文件均为 `A`（新增），无就地改既有测试断言。跨轮唯一语义反转是 Round 2 `test_set_policy_persists_the_live_policy`（断言写文件）→ 本轮 `read_policy is None`（断言不写文件），有独立归因：code 轴 `t040_code_f004` 以直跑生产代码探针复现「乱序 UDS → 共享文件回退 → latest.jpg 重现」的实现 bug，修复令 Agent 收敛为单写者、不再写文件。新断言反转验证修复后的正确不变量、非恒真、能捕获回归，非「让断言迁就当前实现输出」制造假绿；按「调查后判定，非盲目语法命中」放行。
- 验证现状披露：最终门禁 `.scratch/t040_evidence_20261108_032501` contract 257 passed / 1 skipped、unit 1203 passed、repo_hygiene 8 passed（review 报告 home 路径 #89 失败已清理）；E2E 2 failed 为 `Sandbox launch failed ... Timed out waiting for current Browser instance readiness` 跨会话 daemon 资源级联（对照 013227 / 024359 同 2 用例 PASS、t019 本轮 PASS），按用户决定不重跑完整 E2E；定向 E2E 2 passed（98s）。E2E 全量失败属环境非测试缺陷，不改变上述测试可信 / 覆盖判定；本报告以 diff + 生产 / 测试代码静态复核为准。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`test_profile_preview_e2e.py:18-20,36-43,93-101,135-161,184-205` Pillow 中心色 ±20 双色 A→B 跟随 + 双 480 校验，全仓零 `0.97` 残留；多标签 / 无 UI 色带边界由 s016 / d035 + `preview.py` clip + clip unit 补足。
- AC-002：TICK-VALID，re_verified。`test_preview_router.py:84-147` + E2E `:157-167,207-211` 真实 create_app / TestClient 与 HTTPS 端点，断言未登录 401/403、image/jpeg、no-store、ETag 含 captured_at、304、无预览 / 撤销 404、body 不泄路径与内容。
- AC-003：TICK-VALID，re_verified。`test_preview_late_writes.py:243-292` 50 帧不进 `_history`、SSE 重连重放 3 帧全 runtime_state 不含 profile_preview；`test_preview_repository.py:34-51`、`sse_preview.test.ts`、`EnvironmentCard.preview.test.tsx` 覆盖 `preview_captured_at` / null 占位 / `?v=` 刷新。
- AC-004：TICK-VALID，re_verified。`test_preview_late_writes.py:123-185` 注入关闭时截图进行中 / 旧代次通知 / 重置后旧实例回传三类时序并断言不复活；`test_runtime_agent_preview.py:232-261` epoch 单调 + 撤销态文件兜底不复活 latest.jpg（能捕获 f004 回归）；`test_supervisor_preview_policy.py:317-362` fence 前置；E2E `:265-271` 撤销即时 404。
- AC-005：TICK-VALID，re_verified。E2E `:280-283` 停止后保留最后一帧、`test_preview_clear_on_lifecycle.py:35-63` delete / reset 清除（移除 reset 清除调用会红）、`test_preview_late_writes.py:189-209` 含浏览器状态复制不复制预览。
- AC-006：TICK-VALID，re_verified。`test_preview.py:41,59-60` 与 E2E `:216-219` 断言 0600；`test_preview_router.py:134-147` 错误体、`test_preview.py:174-186` meta.json 不泄路径与图片字节。
- AC-007：TICK-VALID，re_verified。E2E `:255-263` 17s 跨 15s 周期 visibility / hidden / focus / marker / title 不变 + `test_runtime_agent_preview.py:109-111` 断言未调用 activateTarget / bringToFront，结合 d035 CDP 限制组合覆盖成立。

coverage = 7 / 7

verdict: PASS

## Round 4 (2026-11-08T04:45:00+08:00)

- 落点仓库校验：`<repo_root>` 校验通过。
- 审查范围：`git -C '<repo_root>' diff d9e0843545275d26f64d7b2932fa933c4e3263fb -- tests/ src/`。
- 本轮背景：测试源码及相关生产代码相对 Round 3 **零改动**。指纹变更为 `3cfef0709d1ad59b` 仅因删除临时未跟踪的前端运行软链 `src/frontend/node_modules`、补充 `progress.md` 模板固定说明行及规范化 spike 报告结论措辞。

reviewed_scope: 3cfef0709d1ad59b

### 前轮 finding 复核

- `t040_test_f001`（important）：已消除。E2E 基于 Pillow 双纯色页中心色采样与 480 宽断言持续生效，无脆弱字节比对残留。
- `t040_test_f002`（minor）：已消除。生命周期重置与删除的预览文件清理覆盖保持完整。
- f004 关联单调性与策略文件隔离测试持续有效。

### 本轮新发现

0 条（clean）。测试源码与断言相对 Round 3 无任何变动，无危险模式引入，无假绿断言。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。双纯色 E2E 与宽 480 真实有效。
- AC-002：TICK-VALID，re_verified。状态码、ETag、缓存头与错误体不泄密断言真实有效。
- AC-003：TICK-VALID，re_verified。瞬态 SSE 隔离重放环断言真实有效。
- AC-004：TICK-VALID，re_verified。迟到写入丢弃与撤销阻断断言真实有效。
- AC-005：TICK-VALID，re_verified。停止保留与生命周期清除断言真实有效。
- AC-006：TICK-VALID，re_verified。0600 权限与无泄露断言真实有效。
- AC-007：TICK-VALID，re_verified。跨采集周期标签无状态变更断言真实有效。

coverage = 7 / 7

verdict: PASS

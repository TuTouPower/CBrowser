# Task review t013（reviewer_focus: 代码）

- task：`t013_v2_profile_copy_reset`
- spec：`docs/tasks/t013_v2_profile_copy_reset/task.md`
- diff_anchor：`986d3e2c1ff7783b6b66606e6591998e449f8b68`
- target：`git -C '/Users/karson/kar/code/CBrowser_t013' diff 986d3e2c1ff7783b6b66606e6591998e449f8b68`
- round：1
- reviewed_at：2026-11-02T11:58:55+08:00

reviewed_scope: 5f0e36be4dbb4e9d

## Findings

### t013_code_f001 - 复制名称绕过 ProfileConfig 校验，可持久化非法行并毒化整个 Profile 列表

- 严重度：critical
- 锚点：AC-001「只复制配置会创建新Profile和配置版本，全部有效配置字段保留」；行为缺陷：一次 duplicate 请求可让 `GET /api/v1/profiles` 永久 500。
- 位置：`src/backend/cbrowser/services/profile_service.py:360-362`、`src/backend/cbrowser/domain/models.py:280-284`、`src/backend/cbrowser/adapters/database/repository.py:775-777`
- 问题：`clone_name = name or f"{source.config.name} (copy)"` 之后用 `source.config.model_copy(update={"name": clone_name})` 覆盖名称。`model_copy` 不做 Pydantic 校验，而 `ProfileDuplicateRequest.name` 只有 `min_length=1/max_length=255`，既没有 `strip()` 也没有 blank 校验（`ProfileCreateRequest`/`ProfileUpdateRequest` 都有）。两条可复现路径：
    1. `POST /api/v1/profiles/p1/duplicate` body `{"include_browser_state":false,"name":" "}`：`create_profile` 事务已提交名称为 `" "` 的行，随后 `_to_domain_profile` 构造 `ProfileConfig` 时触发校验错误，duplicate 返回 500；此后 `GET /api/v1/profiles` 对所有 Profile 返回 500（列表被毒化），只有直接按 ID 查询仍可用。
    2. 源 Profile 名称长度 ≥249（API 允许到 255）时默认追加 `" (copy)"`，克隆名称 257–262 字符，同样触发上述持久化+500。
        证据：`.scratch/t013_review_code/evidence_name_validation.py`（service 层）与 `.scratch/t013_review_code/evidence_api_name.py`（HTTP 层）实测 duplicate 500、随后 `GET /profiles` 500、`GET /profiles/p1` 200；非法行已留在 DB。
- 建议：最终名称必须经过 `ProfileConfig` 校验（先 `strip`、blank/长度校验，再构造 `ProfileConfig(**{**source.config.model_dump(), "name": clone_name})`）；或直接删除 spec 未要求的 `name` 入参。补齐 whitespace-only 与 255 字符源名称的回归测试。

### t013_code_f002 - 状态复制的文件属主/权限未收敛到 Browser UID 1000，克隆目录在受管部署中不可读/不可写

- 严重度：important
- 锚点：AC-004「容器重建后Cookie与配置结果符合所选操作」；AC-002「复制用户数据且校验文件和配置」。
- 位置：`src/backend/cbrowser/services/profile_service.py:87-97`；`src/backend/cbrowser/supervisor/docker_adapter.py:345-353`、`374-395`；`src/backend/cbrowser/adapters/filesystem/artifact_store.py:133-147`；`docs/blueprint/security.md:32-33`
- 问题：`shutil.copytree(..., symlinks=True)` 只保留源文件 mode/时间，不复制属主。受管部署中 API 容器没有 `user:` 覆盖、镜像 `Config.User` 为空（root），Browser 容器固定 `user="1000:1000"`；Supervisor 启动时 `prepare_profile_directories` 只对顶层 `<profiles>/<id>/profile` 执行 `chown 1000:1000`，不会递归。因此副本中的 `Default/`、`Cookies` 等仍是 root 所有并保留 Chrome 的受限 mode（POSIX 上通常目录 0700/文件 0600）；Browser UID 1000 无法遍历/更新这些内容。API 返回 201 后，克隆容器即使读到部分 Cookie，也无法写回会话状态，AC-004 的“Cookie与配置结果符合所选操作”在正式部署不成立。`ArtifactStore._apply_runtime_permissions` 已经是同类问题的既有处理范式，本 diff 未复用。
- 证据：静态代码路径与 `docs/blueprint/security.md:32-33` 的属主契约；`docker image inspect cbrowser:latest --format '{{.Config.User}}'` 为空（root），`tests/e2e` 以宿主用户执行复制、且只 `chmod 0777` 顶层，无法覆盖 root→1000 的正式属主场景。建议用 Linux 环境以 root 执行复制、再以 1000 启动 Browser 验证。
- 建议：复制完成后递归把每个目录/文件收敛到 runtime UID/GID（目录 0750、文件 0640），或让复制在 UID 1000 下执行；补一条受管属主下的真实容器写回验证。

### t013_code_f003 - 「源已停止」门禁只拒绝 running，starting/stopping/error 均可继续复制或重置

- 严重度：important
- 锚点：AC-002「同时复制浏览器状态仅在源浏览器停止并确认无写者后执行」；AC-003「且源已停止」；`docs/blueprint/persistence.md` 声称「desired_state 与 observed_state 均为 stopped 时执行」。
- 位置：`src/backend/cbrowser/services/profile_service.py:319-335`、`389-403`；前端 `src/frontend/src/features/profiles/ProfileDetailPage.tsx:52-53`
- 问题：两处检查都是 `desired_state == "running" or observed_state == "running"`。`observed_state` 的合法域是 `stopped|starting|running|stopping|error`。用户刚点停止时 `desired=stopped, observed=stopping`，此时 Reset 面板仍可用（前端 `runtimeRunning` 同样只看 running），reset 会把仍在写入的 Chrome 用户目录改名、新建空目录、改种子并删除备份；状态复制也会在 Chrome 正在落盘时读取。实测：`evidence_copy_reset.py` CASE1/CASE2 在 `observed=stopping` 下 duplicate/reset 均成功，未被拒绝。
- 建议：只有 `desired_state == "stopped" and observed_state == "stopped"`（或明确评估后的安全状态）才允许；前端同步禁用并提示；补 starting/stopping 回归测试。

### t013_code_f004 - Idempotency-Key 跨操作/跨 Profile 复用返回错误实体，并发同键 reset 返回 409

- 严重度：important
- 锚点：AC-004「重复请求…不会产生…跨Profile覆盖」；`docs/specs/profile_management.md`「重复请求使用 Idempotency-Key 返回同一结果」。
- 位置：`src/backend/cbrowser/adapters/database/repository.py:203-209`；`src/backend/cbrowser/services/profile_service.py:313-317`、`383-387`
- 问题：`get_profile_by_operation` 只要 audit 的 `entity_type == "profile"` 就返回其 `entity_id` 对应 Profile，不校验 audit 的 `action`、目标 `profile_id`，也不比较 payload 的 `sig_hash`；service 在拿锁前直接短路返回。可复现后果：
    1. 先 `PATCH /profiles/p2` 带 key K，再 `POST /profiles/p1/duplicate` 带 K：返回 p2（201），p1 并未被复制（实测 CASE3）。
    2. 先 duplicate p1 带 key K，再 `POST /profiles/p1/reset` 带 K：返回克隆 Profile（200），p1 完全未被重置，调用方会误判成功（实测 CASE3）。
    3. 同一 key 携带不同 `include_browser_state`/`name` 重复请求被静默当成旧结果，而不是既有 create/update 路径的 409 `idempotency_conflict`。
    4. 并发同 key reset：first 成功，second 因每次重新生成随机种子导致 `sig_hash` 不同而抛 `IdempotencyConflictError`（409），不是“返回同一结果”（实测 `evidence_reset_race.py`）。
        证据：`.scratch/t013_review_code/evidence_copy_reset.py` CASE3、`evidence_reset_race.py`。
- 建议：把幂等作用域限定为 `(action, target_profile_id, payload_sig)`；短路前校验 audit action/target/sig；reset 的幂等 payload 用稳定值（例如操作类型+目标+确认语义），不要用每次新生成的 seed 直接参与 sig；对不匹配 payload 返回 409。补跨 action/跨 Profile/并发同键测试。

### t013_code_f005 - 复制失败/取消/同键并发会遗留完整或半复制目录（含 Cookie）

- 严重度：important
- 锚点：AC-004「并发源启动或重复请求不会产生半复制目录、重复Profile或跨Profile覆盖」；隐私残留。
- 位置：`src/backend/cbrowser/services/profile_service.py:337-373`、`87-89`
- 问题：`clone_dir` 在任何 DB 行写入前已创建；copy 抛错、`create_profile` 抛 DB/其他异常、`CancelledError`（`asyncio.to_thread` 取消时线程仍继续写）、以及并发同 key 时 loser 已复制完但 repo 返回 winner，都没有清理该目录。实测：
    - `evidence_copy_reset.py` CASE4：`create_profile` 模拟失败后，`<profiles>/<uuid>/profile/Cookies` 仍存在。
    - `evidence_partial_copy.py`：copy 中途 `OSError` 后留下半复制目录。
    - CASE6：并发同 key 两个请求只产生 1 个 DB Profile，但 `<profiles>` 下多出 1 个孤儿副本目录。
        这些目录不在 DB 中，不会被 list/launch/delete 管理，也没有启动扫描清理；包含 Cookie/登录态，属于持久化隐私残留。旧 v1 实现 `src/backend/main.py` 对 duplicate 的 `except`/取消路径有显式 `rmtree` 与取消吸收，本实现退化了。
- 建议：复制与建行包在 `try/except BaseException` 中，任何失败（含取消）删除 staging 目录；检测到同 key 返回已有 Profile 时删除本次本地副本；清理失败要记录日志；补失败注入/取消/并发测试。

### t013_code_f006 - 对从未启动的 Profile 做状态复制返回 500 并留下空目录

- 严重度：important
- 锚点：行为缺陷（AC-002 状态复制语义）；UI 对新建 Profile 也提供“含状态复制”。
- 位置：`src/backend/cbrowser/services/profile_service.py:339-342`、`87-89`
- 问题：新建 Profile 在首次启动前 `user_data_dir` 不存在（`create_profile` 不会创建）。`duplicate(include_browser_state=true)` 调用 `_copy_user_data`，先 `target.mkdir`，随后 `copytree(source, ...)` 对不存在的 source 抛 `FileNotFoundError`；router 未捕获，返回 500，且留下空的 `<profiles>/<uuid>/profile`。实测 `evidence_copy_reset.py` CASE5。
- 建议：source 不存在时按空状态处理（创建空克隆目录）或返回明确的 4xx；补“新建后立即含状态复制”的用例。

### t013_code_f007 - Reset 与并发启动无互斥/复制后复检，存在移动中的目录被容器启动使用

- 严重度：important
- 锚点：AC-004「并发源启动…不会产生半复制目录、重复Profile或跨Profile覆盖」；AC-003「失败保留源状态或按已验证回滚方案恢复」。
- 位置：`src/backend/cbrowser/services/profile_service.py:396-428`；`src/backend/cbrowser/api/v1/router.py:604-616`（`set_desired_state` 不共享该锁）
- 问题：reset 只在进入锁后、`os.replace` 前检查一次 stopped；之后 `os.replace`、新建空目录、`update_profile`、删除备份全程没有再次校验/预留。启动请求由 API 直接写 `desired_state=running` 并触发 Coordinator，Coordinator/Supervisor 是独立执行体，不获取 `ProfileService._locks`。因此 reset 检查通过后并发 start 可成功：容器会挂载被改名的旧目录（rename 保留 inode）或 reset 后新建的空目录，随后 reset 删除备份/换种子，造成运行中实例与 DB 状态/目录不一致。AC-004 明确要求并发源启动安全。
- 建议：引入 start/stop 也遵守的权威 per-Profile 维护租约（DB 状态或 Coordinator 锁），或在移动/更新后再次校验并在发现 running 时回滚；用真实 Coordinator 补 concurrent start+reset 测试。

### t013_code_f008 - Reset 成功后静默忽略备份删除失败，Cookie/登录态可能残留但返回成功

- 严重度：important
- 锚点：AC-003「重置…将清数据」；错误处理规范（不允许静默吞错）。
- 位置：`src/backend/cbrowser/services/profile_service.py:427-428`
- 问题：`shutil.rmtree(backup, True)` 的第二个位置参数是 `ignore_errors=True`；删除失败不重试、不记日志、不影响响应。接口仍返回 200，用户以为 Cookie/登录态已清除，但旧的 `.reset-backup-<uuid>` 目录仍保留完整浏览器数据。这是重置隐私承诺的静默破坏。
- 建议：清理失败要记录并向上反馈（至少 500/带 warning 的响应），或采用可重试的清理任务；故障注入验证。

### t013_code_f009 - 重置确认面板未列全将被清除的数据（书签/历史/密码/扩展）

- 严重度：minor
- 锚点：AC-003「确认界面明确列出将清数据」。
- 位置：`src/frontend/src/i18n.tsx:144-147`、`479-482`；`src/frontend/src/features/profiles/ProfileDetailPage.tsx:247-274`
- 问题：reset 用整体替换 `user_data_dir` 的方式清除数据，实际会连带删除书签、历史、保存的密码、扩展和 Preferences；面板只列 Cookie、站点数据、缓存、登录状态和指纹身份。用户可能基于该文案误以为书签保留（v1 reset 曾保留书签/Preferences）。
- 建议：列出全部清除范围，或明确写“清除该 Profile 的全部浏览器数据（含书签/历史/密码/扩展），仅保留设置、标签、备注与 Artifact”。

## 结论

- 前轮 finding 复核：Round 1，无前轮 finding。
- 本轮新发现：9 条（critical 1、important 7、minor 1）。
- 未进表的提示：
    - 文件过大（未超重要阈值，按规则只在结论提示）：`src/backend/cbrowser/api/v1/router.py` 817 行（本 task +114，已进入 ≥800 提示区间）；`src/backend/cbrowser/services/profile_service.py` 431 行（+187）；`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 421 行（+134）。
    - 圈复杂度：`duplicate_profile` 约 13、`reset_profile` 约 10（均 ≥10、\<15，仅提示拆分）。
    - `ProfileService._locks` 按 Profile 无限增长，无清理；只保护同进程 duplicate/reset，不覆盖 start/stop（见 f007）。
    - `_clone_dir` 假设 `user_data_dir` 形如 `<profiles_root>/<id>/profile`（`parent.parent`）；若未来出现自定义/迁移路径，克隆目标会落到错误目录。
    - 状态复制对全部文件做一次复制 + 两次全量 SHA-256（3x IO），大 Profile 慢且无磁盘空间预检；失败会放大 f005 的残留。
- AC 复验方式：
    - AC-001：`re_verified`。独立重跑 `tests/unit/test_profile_copy_reset.py` 与 `tests/integration/test_profile_copy_reset_api.py`（11 passed），并核对 `create_profile`/`model_copy` 路径；同时用证据脚本复现名称毒化（f001）。
    - AC-002：`re_verified`。重跑运行中拒绝与状态复制用例；用 `evidence_copy_reset.py` CASE1/CASE5 复验 stopping/never-launched 分支，确认 stopped 门禁不完整（f003/f006）。
    - AC-003：`re_verified`。重跑 reset/回滚用例；用 `evidence_ac003.py` 确认种子重掷、配置版本 1→2、tags/proxy/notes 保留、备份清理；用 CASE2 复验 stopping 可重置（f003）。
    - AC-004：`trust_prior`。未运行真实 Docker/Chrome E2E（需要 `CBROWSER_RUNTIME_TEST_IMAGE` 与已初始化引擎缓存，本轮未提供）；依赖实施侧新增的 `tests/e2e/test_browser_runtime_e2e.py` 用例作为容器/Cookie 证据（`note.md` 未记录其执行结果）。前端部分独立运行 `npx vitest run src/app/router.test.tsx`（4 passed）与 `npx tsc -b`；并发/幂等部分由 `evidence_copy_reset.py`、`evidence_reset_race.py` 复验并发现 f002/f004/f005/f007。
    - coverage = 3/4
- 总体判断：配置/状态复制与重置的基本路径和回滚已落地，但存在 1 个 critical（名称校验导致持久化非法行并毒化列表）和 7 个 important（停止门禁、属主权限、幂等语义、残留目录、并发 reset、静默清理失败等）；AC-004 的并发/幂等与 AC-002/AC-003 的 stopped 语义当前未真实满足。
- 系统性 follow-up：无（均在本 task 范围修复；属主收敛可复用/抽取 `ArtifactStore._apply_runtime_permissions` 的既有模式）。

verdict: FAIL

## Round 2 (2026-11-02T12:47:11+08:00)

reviewed_scope: d74d710df6e683fe

### 前轮 finding 复核（Round 1）

|finding_id|严重度|本轮复核|依据|
|---|---|---|---|
|t013_code_f001|critical|已消除|HTTP 空白名 `" "` / `"   "` / `"\t\n"` 均返回 400，随后 `GET /profiles` 仍 200 且只有 1 个 Profile；255 字符源名的默认克隆名与 255 字符显式名均 201 且列表 200（`.scratch/t013_review_code_r2/evidence/evidence_r2_core.py` f001 段）。`ProfileConfig` 重新构造 + `_validated_clone_name` 的 strip/非空/截断已覆盖原两条毒化路径。|
|t013_code_f002|important|已消除（主路径）|`_apply_copy_ownership` 递归 chown/chmod；宿主非 root 回退 777/666，`tests/unit/test_profile_copy_reset.py::test_copy_permissions_are_readable_and_writable_for_runtime` 通过。但该修复引入新 f010（符号链接跟随），见下。|
|t013_code_f003|important|已消除|desired/observed 的六种组合实测：stopping/starting/error/running 全部 `ProfileRunningError`，仅 `(stopped, stopped)` 接受（同证据脚本 f003 段）；前端 `runtimeRunning` 同步使用双 stopped 条件。|
|t013_code_f004|important|已消除|跨 action（update→duplicate/reset）409；duplicate 跨 payload（include/name）409；reset 跨 Profile 409；并发同 key reset 返回同一 seed、version 仍为 2（同证据脚本 f004 段）。稳定派生种子与锁内预检均生效。|
|t013_code_f005|important|已消除（主路径）|复制中途 OSError、create_profile 失败、取消复制三种路径均无残留目录（同证据脚本 f005 段）；并发同 key 由锁串行并未复制。清理动作自身失败仍静默，见 f011。|
|t013_code_f006|important|已消除|从未启动的 Profile 经真实 HTTP `include_browser_state=true` 返回 201，克隆目录存在且为空，不再 500（同证据脚本 f006 段）。|
|t013_code_f007|important|仍存在（修不彻底）|`set_desired_state` 已入锁，但 Supervisor 启动路径的 `bind_runtime_instance` 不入锁，且 reset 移动目录前只读一次 runtime、移动后无复检。见下方复核段与 `.scratch/t013_review_code_r2/evidence/evidence_r2_core.py` f007 段：把 bind 注入 `get_runtime` 返回之后，reset 在 `observed_state=starting` 下仍完成并换 seed，证明原 TOCTOU 窗口仍在。|
|t013_code_f008|important|已消除|注入备份 rmtree 失败：`logger.warning("Reset backup cleanup failed...")` 实际输出，异常为 `ProfileServiceError`，备份保留且 seed 已更新（同证据脚本 f008 段）。不再静默成功。|
|t013_code_f009|minor|已消除|`i18n.tsx` 的 `resetProfileDataList` 已列出 cookies/site data/cache/history/bookmarks/passwords/extensions/sessions；`npx vitest run src/app/router.test.tsx` 4 passed，`npx tsc -b` 通过。|

f007 复核细节：Round 1 要求的是 start/stop 全路径的权威维护租约，或移动后的复检/回滚。当前实现只给 `ProfileService.set_desired_state`（`src/backend/cbrowser/services/profile_service.py:338`）加锁；`bind_runtime_instance`（`profile_service.py:294-313`）不共享该锁，Supervisor 在执行 desired 检查（`src/backend/cbrowser/supervisor/core.py:814-823`）后、bind（`core.py:844-853`）前仍可继续。序列：start 意图 → Supervisor 通过 desired 检查 → stop 意图 → reset 通过 `(stopped, stopped)` 检查（`profile_service.py:502-507`）→ Supervisor bind 提交 `observed_state=starting` → reset 执行 `os.replace`（`profile_service.py:512-514`）并删除备份。容器会挂载被移走目录的 inode 或 reset 新建的空目录，AC-004 的“并发源启动”不成立。

### t013_code_f010 - 复制后的递归属主收敛会跟随目录符号链接，受管 root API 可被诱导修改克隆外路径

- 严重度：critical
- 锚点：AC-004「并发源启动或重复请求不会产生…跨Profile覆盖」+ `docs/blueprint/security.md`「其他宿主 UID 无读写权」/ 跨 Profile 隔离；行为缺陷：一个 profile 内的目录符号链接可让 API 以 root 对 `/data`、其他 Profile 或容器内任意目录执行 chown/chmod。
- 位置：`src/backend/cbrowser/services/profile_service.py:99-131`（`_apply_copy_ownership`），由 `:148` 调用；危险点在 `:102-112` 的 dirnames 循环。
- 问题：`shutil.copytree(..., symlinks=True)` 会原样复制符号链接；随后 `os.walk` 把符号链接目录放进 `dirnames`，`Path.is_dir()` 跟随链接返回 True，`os.chown`/`os.chmod` 默认也跟随符号链接，于是对链接目标（克隆外）执行 1000:1000 与 0750。受管部署 API 以 root 运行，chown 成功，能实际改动目标；宿主开发回退路径虽因 chown 失败而 `continue`，但受管路径不受影响。攻击者只需在本 Profile 可写目录放入 `escape -> /data`（或 `/`、`/app`、其他 Profile 目录）后触发一次含状态复制；API 会把 `/data` 等目录改属 1000 并 chmod 750，破坏跨 Profile 权限边界（宿主 UID 1000 可遍历/读取全部 Profile），或改变 API 容器目录权限。
- 证据：`.scratch/t013_review_code_r2/evidence/evidence_r2_symlink_duplicate.py` 走完整 `duplicate_profile(include_browser_state=True)`：克隆内保留 `escape` 符号链接，克隆外 victim 目录 mode 由 0755 变为 0750，chown/chmod 调用记录指向克隆外路径；`evidence_r2_symlink.py` 直接调用 `_apply_copy_ownership` 得到相同结果。
- 建议：在递归权限收敛中跳过所有符号链接（dirnames 循环先 `path.is_symlink()` 判断并 continue，文件循环已有该判断），或使用不跟随链接的 `lchown` 与 `follow_symlinks=False`；补一条“源含目录符号链接时目标目录权限不变”的回归测试。

### t013_code_f011 - 复制失败清理自身失败时仍静默，可能留下含 Cookie 的完整/半复制目录

- 严重度：minor
- 锚点：AC-004「不会产生半复制目录」的故障清理边界；`t013_code_f005` 的清理建议要求清理失败记录日志。
- 位置：`src/backend/cbrowser/services/profile_service.py:460-465`（`shutil.rmtree(..., True)` 无日志；reset 回滚 `:533` 同样 ignore）。
- 问题：正常复制/建行失败与取消路径已清理（f005 关闭）；但清理动作自身失败时 `ignore_errors=True` 或异常被替换，目录（含 `Cookies`）会留在 `<profiles>/<clone-id>`，没有日志也没有启动扫描。证据：`.scratch/t013_review_code_r2/evidence/evidence_r2_core.py` f005 段注入 rmtree 失败后残留一个完整克隆目录。
- 建议：清理失败至少 `logger.warning`（profile_id、clone_id、error_type），并考虑非静默 rmtree + 后续 orphan 扫描；保持主失败异常不被清理异常覆盖。

### t013_code_f012 - 新增的 `get_profile_by_operation` 无任何调用方（死代码）

- 严重度：minor
- 锚点：代码质量/死代码。
- 位置：`src/backend/cbrowser/adapters/database/repository.py:222-229`
- 问题：本 diff 新增该方法，但 `src/`、`tests/` 均无引用（`grep -rn get_profile_by_operation` 仅定义；Round 1 的旧实现路径已改为 `get_audit_event`）。保留会增加幂等查询入口的维护面。
- 建议：删除；若计划复用，在 service 内显式使用并测试。

### t013_code_f013 - duplicate 端点实际返回 400 但 OpenAPI `responses` 未声明

- 严重度：minor
- 锚点：契约/文档一致性；f001 的非法名称路径。
- 位置：`src/backend/cbrowser/api/v1/router.py:367-380`（responses）与 `:407-410`（400）
- 问题：`InvalidProfileNameError` 明确返回 HTTP 400，但 duplicate 的 `responses` 只声明 404/409/503；导出的 OpenAPI 和生成的消费者类型看不到该错误契约。reset 的 400 已声明，duplicate 缺。
- 建议：在 duplicate 的 `responses` 增加 400/`ErrorResponse`，并重生成 OpenAPI 与前端类型。

## 结论

- 前轮 finding 复核：f001/f003/f004/f006/f008/f009 已消除；f002/f005 主路径已消除但分别引出 f010 与 f011；f007 修不彻底仍存在（Supervisor bind 不入锁、移动后无复检，残余 TOCTOU）。
- 本轮新发现：4 条（critical 1：f010；minor 3：f011/f012/f013）；另有前轮 f007 仍为重要。
- 未进表的提示：
    - 文件过大（按规则只在结论提示）：`src/backend/cbrowser/api/v1/router.py` 831 行（anchor 703，+128，已越过 800 重要区间）；`src/backend/cbrowser/adapters/database/repository.py` 834 行（anchor 806，+28）；`src/backend/cbrowser/services/profile_service.py` 556 行（anchor 244，+312）；`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 422 行（anchor 289，+133）。均未见不可拆的硬约束，建议后续拆分。
    - 圈复杂度（手算近似，仅提示）：`duplicate_profile` 约 13、`reset_profile` 约 11，均 ≥10 且 \<15。
    - `ProfileService._locks` 按 Profile 无限增长（Round 1 已提示）；仍只覆盖进程内，多 worker 部署不成立。
    - 幂等重放在源 Profile 已删除时返回 404（`get_profile` 在 audit 短路前执行），与“返回同一结果”的 spec 文案有边角差距；本轮未单列 finding。
- AC 复验方式：
    - AC-001：`re_verified`。`tests/unit/test_profile_copy_reset.py` 与 `tests/integration/test_profile_copy_reset_api.py` 共 25 passed；`evidence_r2_core.py` f001 段重跑 HTTP 空白名/长名，列表保持 200；配置全字段、标签、种子、Artifact 不复制均有断言。
    - AC-002：`re_verified`。f003 六种状态组合、f006 未启动 Profile、状态复制文件/清单/取消清理均实测；f010 是复制后权限收敛的独立安全缺陷，不影响“复制内容与校验”本身的断言。
    - AC-003：`re_verified`。reset 的 seed 重掷、配置版本 2、其他 Profile 不变、DB 失败回滚、备份删除失败日志与异常均实测（f008 段）；真实容器 Cookie 未在本轮重跑。
    - AC-004：`trust_prior`。API/HTTP/并发/幂等部分已独立复验（25 passed + evidence），前端 `npx vitest run src/app/router.test.tsx` 4 passed、`npx tsc -b` 通过；但真实 Docker/Chrome 的 Cookie 容器重建未运行（缺 `CBROWSER_RUNTIME_TEST_IMAGE`/引擎缓存，note 未记录该 E2E 执行结果），依赖实施侧新增的 `tests/e2e/test_browser_runtime_e2e.py` 作为容器证据。`coverage = 3/4`（trust_prior 25%，未超过 30%）。
- 总体判断：Round 1 的 f001/f003/f004/f005 主路径/f006/f008/f009 已真实关闭，f002 主路径也成立；但 f007 仍有可复现的启动/重置 TOCTOU，且 f002 的权限修复引入 f010 的 root 级符号链接跟随安全缺陷。两个 blocking 未解决，本轮 FAIL。
- 系统性 follow-up：无（f007/f010 均在本 task 范围；未见等价 pending/tid）。

verdict: FAIL

## Round 3 (2026-11-02T13:06:03+08:00)

reviewed_scope: 88d58a5a76da143a

### 前轮 finding 复核（Round 2）

|finding_id|严重度|本轮复核|依据|
|---|---|---|---|
|t013_code_f007|important|已消除|`bind_runtime_instance` 与 `set_desired_state`、`duplicate_profile`、`reset_profile` 共用同一 per-Profile 锁；实测 reset 持锁期间并发 bind 不完成（事件序 `replace-start → bind-start → replace-done → bind-done`），bind 只能看到 reset 完成后的新目录；先 bind 或先写 start 意图后 reset 均返回 `ProfileRunningError`。Round 2 的旧利用脚本（绕过 service、在 `get_runtime` 内直接 repo bind）现在也被移动后的复检拦截并回滚。证据：`.scratch/t013_review_code_r3/evidence_r3.log` f007 段。|
|t013_code_f010|critical|已消除|`_apply_copy_ownership` 的 `_own` 在 chown/chmod 前对 `is_symlink()` 直接返回，chown 使用 `follow_symlinks=False`；实测含目录/文件符号链接的克隆完成后，克隆外 victim 目录 0755、文件 0644 不变，记录的 chown/chmod 全部落在克隆路径内。回归测试 `test_copy_ownership_does_not_follow_directory_symlinks` 通过。证据：`.scratch/t013_review_code_r3/evidence_r3.log` f010 段。|
|t013_code_f011|minor|未消除（修不彻底）|`_cleanup_copy` 只接到 reset 回滚路径；duplicate 的失败清理仍是 `shutil.rmtree(clone_dir.parent, True)`（`profile_service.py:475,478`），不记日志且清理异常会覆盖主异常。实测注入复制失败 + rmtree 失败后：响应变为 `cleanup denied`（原 `disk full` 丢失）、残留一个含 `Cookies` 的完整克隆目录、无任何 cleanup warning。证据：`.scratch/t013_review_code_r3/evidence_r3.log` f011 段。|
|t013_code_f012|minor|已消除|`grep -rn get_profile_by_operation src tests` 零命中，方法已删除。|
|t013_code_f013|minor|已消除|导出 OpenAPI 的 duplicate responses 为 `201/400/404/409/422/503`，reset 为 `200/400/404/409/422/503`；`test_exported_openapi_schema_matches_live_app` 通过；生成 d.ts 的 duplicate 操作含 400。|

Round 2 已关闭项回归：f001（空白名 400、列表不中毒、255 字符名 201）、f003（六种 desired/observed 组合仅 `(stopped, stopped)` 接受）、f004（跨 action/跨 Profile 409、同键并发 reset 同一 seed）、f005（copy/create/取消失败无残留）、f006（未启动 Profile 状态复制 201 且空目录）经重跑 `.scratch/t013_review_code_r2/evidence/evidence_r2_core.py` 对应段确认未回归；f002 的权限收敛与测试仍在且通过；f008 的备份删除失败告警/异常、f009 的清数据文案未受本轮改动影响，复核代码与前端测试通过。

### t013_code_f014 - f007 的锁修复使长复制/重置可能阻塞 Supervisor bind 超过 10s 客户端超时，服务端仍提交绑定

- 严重度：minor（低概率时序；会触发一次伪启动失败与失败计数，recovery coordinator 后续可经 `missing_runtime` 补偿清理，非永久损坏）
- 锚点：AC-004「并发源启动…不会产生…」的健壮性边界；f007 修复引入的锁等待与既有 Supervisor 请求超时的交互。
- 位置：`src/backend/cbrowser/services/profile_service.py:313-319`（bind 进入 per-Profile 锁）；`src/backend/cbrowser/supervisor/runner.py:89`（内部 API 客户端 `timeout=10.0`）；`src/backend/cbrowser/supervisor/core.py:846-859`（bind 请求无额外超时）；`src/backend/cbrowser/supervisor/recovery_coordinator.py:371-416`（missing_runtime 补偿）。
- 问题：状态复制包含全量复制 + 两次全量 SHA-256，大 Profile 很容易超过 10s。若一次 Supervisor start 已通过 `desired=running` 检查、尚未 bind 时，用户/自动化先 stop 再触发带状态复制或 reset，维护操作先获得锁并持续 >10s；Supervisor 的 bind 请求在 10s 客户端超时后抛错，而 FastAPI 不会因客户端断开取消处理器（`uvicorn_timeout_probe.py` 实测客户端 ReadTimeout 后处理器仍继续）。锁释放后服务端 bind 仍提交 `observed_state=starting`，但 Supervisor 已按启动失败处理；随后重试 bind 会因现有 `starting` 实例冲突。证据：`.scratch/t013_review_code_r3/evidence_bind_timeout.log`（客户端超时 → bind 在锁释放后提交 `starting` → retry `InstanceConflictError`）。
- 建议：给维护锁等待设小于 10s 的显式 deadline，超时返回 409/503 让 Supervisor 干净重试；或让 bind 在客户端断开/请求取消时放弃提交；或把内部 bind 超时提高到覆盖最大维护时长并在复位/复制前后用期望实例做栅栏。补一条“长复制期间并发 start”的回归用例。

## 结论（Round 3）

- 前轮 finding 复核：f007、f010 两个 blocker 均已按代码与独立证据消除；f012、f013 已消除；f011 未修彻底，仍为 minor（duplicate 清理路径静默且覆盖主异常）。
- 本轮新发现：1 条（minor：f014）。
- 未进表的提示：
    - 文件过大（按规则只在结论提示，生成物 `schemas/openapi/cbrowser_v1.json`、`cbrowser_v1.d.ts`、`tsconfig.tsbuildinfo` 排除）：`src/backend/cbrowser/api/v1/router.py` 835 行、`src/backend/cbrowser/adapters/database/repository.py` 826 行（均越过 800 重要阈值）；`src/backend/cbrowser/services/profile_service.py` 576 行；`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 422 行（越过 400 建议阈值）。均未见不可拆硬约束。
    - 圈复杂度（手算近似）：`duplicate_profile` 约 14、`reset_profile` 约 14，均 ≥10 且 \<15，仅提示后续拆分。
    - `ProfileService._locks` 按 Profile 无限增长；且为进程内 asyncio 锁，当前单 worker uvicorn 部署成立，多 worker 部署不覆盖。
    - `tsconfig.tsbuildinfo` 是已跟踪的生成物，本轮 `tsc -b` 把它从旧 v1 文件清单刷新为当前 v2 清单（无业务逻辑）。
- AC 复验方式：
    - AC-001：`re_verified`。重跑 `tests/unit/test_profile_copy_reset.py`（20 passed）与 `tests/integration/test_profile_copy_reset_api.py`（6 passed），并重跑 Round 2 核心证据 f001 段；全字段、标签、种子、Artifact 不复制与源不变均有断言。
    - AC-002：`re_verified`。重跑状态复制、stopped 门禁、未启动 Profile、Singleton 跳过与 manifest 校验用例；Round 2 核心证据 f003/f006 段无回归。
    - AC-003：`re_verified`。重跑 reset 的 seed 重掷、配置版本 2、DB 失败回滚与备份清理用例；独立运行 t013 E2E 的 reset 段（空目录、seed 变化）通过。
    - AC-004：`re_verified`。独立运行全量后端 unit（489 passed）、integration（85 passed）、前端 Vitest（117 passed）与 t013 E2E（1 passed，`CBROWSER_RUNTIME_TEST_IMAGE=cbrowser-t008-browser:e2e`）；E2E 真实容器写入 Cookie → duplicate → 克隆容器读回 Cookie → reset 后源目录为空。
    - coverage = 4/4（无 trust_prior）。
- 总体判断：f007 的锁覆盖与 f010 的符号链接收敛均已真实验证；未发现新的 critical/important，f011 与 f014 为 minor，可进入合并前收尾。
- 系统性 follow-up：无（f011/f014 均在本 task 范围；未见等价 pending/tid）。

verdict: PASS

## Round 4 (2026-11-02T13:16:59+08:00)

reviewed_scope: 68994e2bb7fa7d48

### 前轮 finding 复核（Round 3）

|finding_id|严重度|本轮复核|依据|
|---|---|---|---|
|t013_code_f011|minor|已消除|duplicate 失败清理（`src/backend/cbrowser/services/profile_service.py:474-482`）与 reset 回滚清理（`:556-559`）均改用 `_cleanup_copy`（`:133-144`）：`OSError` 只记 warning 并返回，主异常原样抛出。`.scratch/t013_review_code_r4/evidence_f011.py` 四条注入路径实测 surfaced 分别为 `OSError: disk full`（拷贝失败）、`RuntimeError: db write failed`（create_profile 失败）、`CancelledError`（取消）、`RuntimeError: db update failed`（reset DB 失败），每条均输出 `Copy cleanup failed: profile=... error_type=OSError`；reset 路径源 Cookie 成功回滚（`b'cookie-data'`）。清理失败时残留目录属预期，但已告警且不覆盖主异常，满足 f011 最低要求。|
|t013_code_f014|minor|仍遗留（非阻断）|Round 3 已判为窄时序、交由 t009 覆盖；本轮改动未触及 bind 锁等待，判定不变。|

Round 3 已关闭项回归：本轮仅 `profile_service.py` 与 `tests/unit/test_profile_copy_reset.py` 在 Round 3 报告后发生变更（其余交付文件 mtime 早于 Round 3 报告）；全量后端 unit（489 passed）、integration（85 passed）、t013 真实容器 E2E（1 passed）复跑通过，f001/f003/f004/f005/f006/f007/f008/f009/f010/f012/f013 无回归。新增 manifest 断言（`tests/unit/test_profile_copy_reset.py:108-110`）与 `test_copy_manifest_mismatch_removes_clone` 均通过。

### 结论（Round 4）

- 前轮 finding 复核：f011 已消除；f014 仍为 minor 遗留（t009）；Round 3 其余 finding 无回归。
- 本轮新发现：0 条。
- 未进表的提示：
    - 文件过大与圈复杂度同 Round 3，本轮无新增：`src/backend/cbrowser/api/v1/router.py` 835 行、`src/backend/cbrowser/adapters/database/repository.py` 826 行（越过 800 重要阈值）；`src/backend/cbrowser/services/profile_service.py` 576 行；`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 422 行。
    - `_cleanup_copy` 的 `to_thread` 在极端二次取消下仍可能被 `CancelledError` 打断，告警已尽力；非新 blocker。
    - 流程提示（非代码 finding）：`python3 .repo_template/scripts/check_review_status.py --task-dir docs/tasks/t013_v2_profile_copy_reset` 当前报 `finding_id 重复：t013_code_f011`，原因是 note.md 的 Round 2/3 处置表重复登记 `t013_code_f011`、`t013_test_f012/f015/f017`。工具无法产出 overall；需实施侧按工具要求去重（reviewer 只读，未改 note.md）。
- AC 复验方式：
    - AC-001：`re_verified`。重跑 `tests/unit/test_profile_copy_reset.py`（20 passed）与 `tests/integration/test_profile_copy_reset_api.py`（6 passed），全字段/标签/种子/Artifact 不复制与源不变断言通过。
    - AC-002：`re_verified`。状态复制、manifest 一致性、stopped 门禁、未启动 Profile、Singleton 跳过用例通过；新增源/副本 `_manifest` 全量比较通过。
    - AC-003：`re_verified`。reset 的 seed 重掷、配置版本、DB 失败回滚与备份清理用例通过；f011 注入证明回滚后源数据恢复且主异常保留。
    - AC-004：`re_verified`。真实容器 E2E `test_t013_state_copy_restores_cookies_in_clone` 通过（`CBROWSER_RUNTIME_TEST_IMAGE=cbrowser-t008-browser:e2e`），integration 并发/幂等用例通过；前端本轮未改动，Round 3 Vitest 117 passed 结论沿用。
    - coverage = 4/4（无 trust_prior）。
- 总体判断：f011 已真实关闭，本轮仅清理路径日志化与 manifest 断言，无新 critical/important；Round 3 PASS 维持。
- 系统性 follow-up：无。

verdict: PASS

## Round 5 (2026-11-02T13:26:47+08:00)

reviewed_scope: 3b90f37ed20afe31

### 范围确认（相对 986d3e2）

- 当前已提交 diff 共 24 个文件（+2862/−86），与 Round 4 的交付清单一致；工作区 `git status --short` 为空，无 reviewer 不可见的未跟踪交付文件。
- Round 4 之后非流程文件的唯一改动为 `tests/unit/test_profile_copy_reset.py:108-110` 的 manifest 断言：`assert _manifest(clone_dir) == _manifest(profile_dir)`。该断言由生产 `_manifest` 对克隆与源做全量内容/大小比较（按 `_SKIP_COPY_FILES` 排除 Singleton 文件），比逐文件抽查更强，未弱化或恒真；`test_state_duplicate_copies_files_and_skips_singleton` 仍保留 Cookie、Preferences、Singleton 缺席/源符号链接与 Artifact 空集断言。
- `note.md` 仅做处置表去重与收尾信息更新；`python3 .repo_template/scripts/check_review_status.py --task-dir docs/archive/tasks/t013_v2_profile_copy_reset` 不再报 finding_id 重复，输出 `code_verdict=PASS`、`test_verdict=PASS`；`overall=INCOMPLETE` 仅因 `review_test.md` 仍保留 Round 4 指纹（测试轴须另行追加 Round 5），本报告 code 轴 `reviewed_scope` 已与当前 diff 匹配。
- 生产代码锚点与 Round 4 一致（`_cleanup_copy` 于 `src/backend/cbrowser/services/profile_service.py:133`、duplicate 清理 `:474-482`、reset 回滚/备份清理 `:556-570`；router 835 行、repository 826 行、ProfileDetailPage 422 行），未发现本轮新增生产逻辑改动。

### 前轮 finding 复核（Round 4）

|finding_id|severity|本轮复核|依据|
|---|---|---|---|
|t013_code_f011|minor|已消除（无回归）|`_cleanup_copy` 仍为 `OSError` warning 后返回、主异常原样抛出；duplicate 与 reset 回滚均调用，Round 4 结论未受本轮 note/test 改动影响。|
|t013_code_f014|minor|仍遗留（非阻断）|长复制/重置阻塞 Supervisor bind 的窄时序未改动，按 Round 3/4 处置遗留 t009；note.md 已登记。|

Round 1–3 已关闭的 f001–f010、f012、f013 无回归：本轮重跑全量 unit（489 passed）、integration（85 passed）与 t013 真实容器 E2E（1 passed），生产代码未改。

### 验证证据

- `.scratch/t013_review_code_r5/evidence/unit_t013.log`：`tests/unit/test_profile_copy_reset.py` 20 passed（含更新后的 manifest 断言）。
- `.scratch/t013_review_code_r5/evidence/unit_full.log`：`tests/unit` 489 passed。
- `.scratch/t013_review_code_r5/evidence/integration.log`：`tests/integration` 85 passed。
- `.scratch/t013_review_code_r5/evidence/e2e_t013.log`：`test_t013_state_copy_restores_cookies_in_clone` 1 passed（`CBROWSER_RUNTIME_TEST_IMAGE=sha256:fce542f64d1c96d805ae93937320806629dfe30b650635245becc71cf2731b86`，引擎缓存只读挂载）。
- `.scratch/t013_review_code_r5/evidence/vitest_router.log`：前端 `src/app/router.test.tsx` 4 passed。

### 结论（Round 5）

- 前轮 finding 复核：f011 无回归；f014 仍为 minor 遗留（t009），非阻断。
- 本轮新发现：0 条。
- 未进表的提示：
    - 文件过大与圈复杂度同 Round 3/4，本轮无新增：`src/backend/cbrowser/api/v1/router.py` 835 行、`src/backend/cbrowser/adapters/database/repository.py` 826 行（越过 800 重要阈值）；`src/backend/cbrowser/services/profile_service.py` 580 行；`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 422 行（越过 400 建议阈值）。
    - `ProfileService._locks` 进程内锁与多 worker 限制同前轮，未因本轮改动变化。
- AC 复验方式：
    - AC-001：`re_verified`。重跑 `tests/unit/test_profile_copy_reset.py`（20 passed）与 `tests/integration`（85 passed）；配置全字段、标签、种子、Artifact 不复制与源不变断言通过。
    - AC-002：`re_verified`。状态复制用例含源/副本全量 `_manifest` 比较、Singleton 跳过、stopped 门禁与未启动 Profile 分支，全部通过。
    - AC-003：`re_verified`。reset 的种子重掷、配置版本 2、其他 Profile 不变、DB 失败回滚与备份清理用例通过。
    - AC-004：`re_verified`。本轮重跑真实容器 E2E（Cookie 写入源 → API 状态复制 → 克隆容器读回 → reset 清空源目录并换种子）1 passed；integration 并发/幂等用例通过；前端 `router.test.tsx` 4 passed。
    - coverage = 4/4（无 trust_prior）。
- 总体判断：本轮仅有 note.md 处置去重与测试 manifest 断言增强，生产代码与 Round 4 一致；重跑 unit/integration/E2E/前端全部通过，无未解决 critical/important，维持 PASS。
- 系统性 follow-up：无（f014 已登记遗留 t009）。

verdict: PASS

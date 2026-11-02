# Task review t013（reviewer_focus: 测试）

- task：`t013_v2_profile_copy_reset`
- spec：`docs/tasks/t013_v2_profile_copy_reset/task.md`
- diff_anchor：`986d3e2c1ff7783b6b66606e6591998e449f8b68`
- target：`git -C '/Users/karson/kar/code/CBrowser_t013' diff 986d3e2c1ff7783b6b66606e6591998e449f8b68`
- round：1
- reviewed_at：2026-11-02T12:12:53+08:00

reviewed_scope: 5f0e36be4dbb4e9d

## Findings

### t013_test_f001 - 复制请求的非法 name 无负向测试，实际会持久化坏行并打挂 Profile 列表

- 严重度：critical
- 锚点：行为缺陷（无对应 AC）；`POST /api/v1/profiles/p1/duplicate` 传入 `{"name":" "}` 返回 500，随后 `GET /api/v1/profiles` 也返回 500，坏行重启后仍在。
- 位置：`tests/integration/test_profile_copy_reset_api.py:67`（仅覆盖 happy path）；生产锚点 `src/backend/cbrowser/domain/models.py:293`、`src/backend/cbrowser/services/profile_service.py:363`；证据 `.scratch/t013_review_test/evidence_duplicate_name_api.py`。
- 问题：`ProfileDuplicateRequest.name` 只做 `min_length/max_length`，没有 `strip`/blank 校验；service 用 `source.config.model_copy(update={"name": clone_name})` 绕过 `ProfileConfig` 的 validator，非法 name 被写入 SQLite。随后 `_to_domain_profile` 反序列化该行时抛 `ValidationError`，API 返回 500，并且所有 Profile 列表请求持续 500。另一个同类输入是源 name 恰好 255 字符：默认 clone name 追加 `" (copy)"` 后 262 字符，也会持久化坏行（`evidence_name_validation.py` 已复现）。测试套件没有任何非法 name 的负向用例。
- 建议：新增 HTTP 集成负向测试：`name=" "`、显式 `name` 超 255、255 字符源 Profile 的默认 clone name，断言 4xx/422、数据库无新 Profile、后续 `GET /api/v1/profiles` 仍为 200；并在生产侧于 `ProfileDuplicateRequest`/service 统一做 strip 与非空/长度校验，禁止非法行落库。

### t013_test_f002 - 并发状态复制同 Idempotency-Key 无测试，实际遗留完整浏览器状态目录

- 严重度：critical
- 锚点：AC-004「并发源启动或重复请求不会产生半复制目录、重复Profile或跨Profile覆盖」。
- 位置：`tests/unit/test_profile_copy_reset.py:162`、`tests/integration/test_profile_copy_reset_api.py:140`（两个重复请求用例都是串行）；证据 `.scratch/t013_review_test/evidence_concurrent_duplicate.py`。
- 问题：两个并发 `duplicate_profile(include_browser_state=True, operation_id="same")` 都返回同一个 Profile，但第二个请求在拿锁后再次执行了完整复制，`create_profile` 识别幂等键后返回已存在 Profile，已复制的目录没有被删除。实际结果是在 `profiles/` 下留下一个未关联的完整目录，其中包含源 `Cookies`。这违反 AC-004 的「不产生半复制目录」，且对隐私浏览器属于浏览器状态残留。现有测试只验证串行重复请求，无法发现该行为。
- 建议：新增并发用例：`asyncio.gather` 两个同 key、`include_browser_state=True` 的复制请求，断言只有一个新 Profile、`profiles/` 下只有源目录和已发布 clone 目录、无孤立目录；生产侧在锁内再次检查 operation_id，或在 `create_profile` 返回已存在 Profile 时清理本次 staged 目录。

### t013_test_f003 - 同 Idempotency-Key 不同复制参数无负向测试，状态复制被静默降级为仅配置

- 严重度：important
- 锚点：行为缺陷 + 重复请求语义（AC-004；`docs/specs/profile_management.md` 的「重复请求使用 Idempotency-Key 返回同一结果」）。
- 位置：`tests/integration/test_profile_copy_reset_api.py:140` 只重复完全相同的 payload；证据 `.scratch/t013_review_test/evidence_idempotency_payload.py`。
- 问题：先用同一 key 做 `include_browser_state=False` 复制，再用同一 key 请求 `include_browser_state=True`，service 在幂等预检查中直接返回已有 config-only clone，不校验请求差异，也不进入 repository 的 `sig_hash` 冲突检查。用户明明选择「含浏览器状态」，却静默得到没有用户数据的 clone；现有测试只覆盖相同 payload，无法发现。
- 建议：新增负向测试：同 key 不同 `include_browser_state`/`name` 必须返回 409（或明确冲突错误），且不得返回先前 clone；service 在返回已有 operation 前校验请求签名，或把幂等检查下沉到 repository。

### t013_test_f004 - 并发 reset 同 Idempotency-Key 无测试，重试返回 409 而非同一结果

- 严重度：important
- 锚点：行为缺陷 + 测试策略的并发要求；`docs/specs/profile_management.md` 声明重复请求返回同一结果。
- 位置：`tests/unit/test_profile_copy_reset.py:174` 只做串行 reset 幂等；证据 `.scratch/t013_review_code/evidence_reset_race.py`（只读执行）。
- 问题：两个并发 `reset_profile("p1", operation_id="same")` 中一个成功、另一个抛 `IdempotencyConflictError`，API 会映射为 409 `idempotency_conflict`。原因是每次 reset 都生成新的随机指纹种子，两个并发请求算出不同 `sig_hash`；同 key 重试没有返回第一次结果。数据最终回滚到安全状态，但幂等语义和重试可用性不成立。
- 建议：新增并发 reset 测试：同 key 两个请求都应返回同一结果/同一新种子，且只新增一个配置版本；生产侧应在锁内复用第一次生成的种子，或在冲突时返回已存在结果而不是 409。

### t013_test_f005 - AC-004 的「真实前端经 API」流程无测试

- 严重度：important
- 锚点：AC-004「真实前端经API完成配置复制/状态复制/重置，容器重建后Cookie与配置结果符合所选操作」。
- 位置：`src/frontend/src/app/router.test.tsx:219`（`defaultApiClient.profiles.reset` 被 mock）、`tests/e2e/test_browser_runtime_e2e.py:2684`（直接调用 `service.duplicate_profile`）。
- 问题：前端 Vitest 测试只验证面板文字和 mock 的 `reset` 方法，不经过真实 API；E2E 绕过 HTTP 路由和前端，直接调用 `ProfileService`，且只覆盖状态复制的 Cookie 恢复，没有覆盖配置复制、重置，也没有验证 clone 配置字段。现有 `tests/e2e/test_frontend_*.py` 的 Playwright 基础设施可用，但 t013 没有新增真实 UI 流程。AC-004 的打勾缺少直接证据。
- 建议：新增真实前端 E2E（Playwright）或至少 HTTP API + 真实容器的 E2E：从 Profile 详情页触发仅配置复制、含状态复制、重置三种操作，经 `/api/v1/profiles/{id}/duplicate|reset`，重建容器后断言 Cookie 与 `fingerprint_seed`/配置字段符合所选操作。

### t013_test_f006 - AC-002 的文件/配置校验失败与复制后源启动分支无测试

- 严重度：important
- 锚点：AC-002「复制用户数据且校验文件和配置」；AC-004「并发源启动」。
- 位置：`tests/unit/test_profile_copy_reset.py:78`、`tests/integration/test_profile_copy_reset_api.py:83`（均只覆盖成功复制）；生产分支 `src/backend/cbrowser/services/profile_service.py:347`、`:354`。
- 问题：`source_manifest != clone_manifest` 的失败清理分支、复制后再次检查 runtime 运行状态并删除 clone 的分支从未被触发。删除或破坏 `_manifest` 比较、复制后复检逻辑，现有测试仍全绿；测试策略要求的「并发/故障注入」没有落到这两条关键的 AC-002/AC-004 路径上。复制中途抛异常时残留目录的行为也没有覆盖。
- 建议：增加故障注入用例：复制期间在源目录制造差异（或使用可注入的文件系统 copy/manifest seam）使 manifest 不一致，断言请求失败且 clone 目录被删除；在复制后把源 runtime 置为 running/observed running，断言拒绝且不发布 clone；复制过程中抛 OSError，断言半成品目录清理。

### t013_test_f007 - Artifact 不复制断言为空证据

- 严重度：important
- 锚点：AC-001、AC-002「Artifact 不复制」。
- 位置：`tests/unit/test_profile_copy_reset.py:70`、`:92`。
- 问题：源 Profile 从未创建 Artifact，`ArtifactRepository(...).list_artifacts(clone.id) == []` 无论实现是否复制 Artifact 都会通过。这是典型的空集合假证据；AC-001/AC-002 的 Artifact 边界没有被验证。集成测试同样没有 seed 源 Artifact。
- 建议：在源 Profile 上创建至少一个 Artifact（元数据 + storage 文件），分别执行仅配置复制和含状态复制，断言 clone 的 Artifact 列表为空、源 Artifact 仍存在且内容未变。

### t013_test_f008 - 前端重置确认仅断言 cookies，未验证确认前不执行

- 严重度：minor
- 锚点：AC-003「确认界面明确列出将清数据」。
- 位置：`src/frontend/src/app/router.test.tsx:231`。
- 问题：测试只断言重置面板文本匹配 `/cookies/i`，没有断言面板打开后、确认前 `resetCalled === false`；如果头部 Reset 按钮直接执行重置，测试仍会通过。也没有验证「站点数据、缓存、登录状态、指纹身份」这些 AC 要求的列表项。
- 建议：在打开面板后断言 `resetCalled` 仍为 false，确认点击后才变为 true；断言完整数据清单（或 i18n 的 resetProfileDataList 全文）；补充运行中时状态复制按钮禁用的断言。

### t013_test_f009 - 配置复制只抽样字段，配置版本快照未校验

- 严重度：minor
- 锚点：AC-001「全部有效配置字段保留」。
- 位置：`tests/unit/test_profile_copy_reset.py:58`。
- 问题：只检查 name/fingerprint_seed/proxy/timezone/locale/notes 和 tags；`list_config_versions` 只用 truthiness 断言，未校验版本 1 的快照内容。screen/gpu/humanize/geoip/clipboard/launch_args/extension_paths 等字段或版本快照被破坏时测试不会失败。
- 建议：比较 `clone.config == source.config.model_copy(update={"name": ...})`；读取 `list_config_versions(clone.id)[0].config` 并逐字段/整体比较，确认标签也在快照中。

### t013_test_f010 - 源数据完整性只用少量文件验证，Singleton 仅测一个，运行态仅测 desired

- 严重度：minor
- 锚点：AC-002「不损坏源数据」「确认无写者」。
- 位置：`tests/unit/test_profile_copy_reset.py:43`、`:87`、`:100`；`tests/integration/test_profile_copy_reset_api.py:27`、`:94`。
- 问题：测试只创建 `SingletonLock`，没有覆盖 `SingletonCookie`/`SingletonSocket`；只设置 `desired_state=running`，没有覆盖 `observed_state=running`；源目录只在复制后检查 `Cookies` 和 `SingletonLock`，未按测试策略做用户数据目录 hash。其他源文件被修改时测试不会发现。
- 建议：创建三种 Singleton 文件并断言全部跳过；分别用 observed_state=running 和 desired_state=running 验证拒绝；复制前后对源目录（排除 Singleton）计算相对路径 + SHA-256 清单并比较，同时断言源配置/标签未变。

### t013_test_f011 - 重置未断言新配置版本

- 严重度：minor
- 锚点：AC-003「按既有指纹种子重新生成语义执行」；spec 上下文要求生成新配置版本。
- 位置：`tests/unit/test_profile_copy_reset.py:126`、`tests/integration/test_profile_copy_reset_api.py:134`。
- 问题：只断言 `fingerprint_seed` 改变和 Profile 行内 name/proxy/notes 保留，没有断言 `current_config_version` 从 1 增到 2，也没有读取新版本快照确认新种子和设置。若实现只改 Profile 行而不新增配置版本，测试仍会通过。
- 建议：断言 `updated.current_config_version == 2`，读取版本 2 快照并确认种子为新值、其余设置与重置前一致。

## 结论

- 前轮 finding 复核（Round N≥2 才写）：首轮，无。
- 改测方向复核：无；本轮只新增测试文件和在 `router.test.tsx` 追加新测试，没有修改既有断言的预期来迁就实现。
- 本轮新发现：11 条（critical 2、important 5、minor 4）。
- 未进表的提示：真实 Chrome E2E 未独立重跑（未设置 `CBROWSER_RUNTIME_TEST_IMAGE`，默认 engine cache 路径不存在），AC-004 的容器重建结论只能列为 trust_prior；新增 API 还缺 404/503/CSRF 负向用例；测试使用 `repo._session_maker` 私有属性，属测试基础设施 smell，不阻断。
- 流程提示：prompt 指定指纹 5f0e36be4dbb4e9d 与当前 `check_review_status.py` 重算值 215bbce14df73464 不一致；本轮按 prompt 要求保留指定行，实际审查以当前 `git diff 986d3e2c...` 为准。差异来源需实施方核查（疑似 prompt 渲染后工作区有变化）。
- 总体判断：AC-001/002/003 有可执行测试和实际通过结果，但 AC-004 的真实前端经 API、并发幂等与故障清理没有有效覆盖；另有非法 name 导致 Profile 列表持续 500、并发状态复制遗留完整浏览器数据目录等已复现缺陷，当前打勾不可信，必须 FAIL。
- 系统性 follow-up：无；缺失的前端 E2E 基础设施已在 `tests/e2e/test_frontend_*.py` 存在，属本 task 覆盖缺口，不建议另立 follow-up 替代。

### AC 复验方式

- AC-001：re_verified。独立重跑 `tests/unit/test_profile_copy_reset.py`（6 passed）与 `tests/integration/test_profile_copy_reset_api.py`（5 passed）；克隆创建、部分配置字段、配置版本存在、源 Cookies 不变均有断言，但 Artifact 断言为空证据（f007），字段抽样见 f009。
- AC-002：re_verified。独立重跑 unit/integration；停止源拒绝、用户数据复制、`SingletonLock` 跳过、源 Cookies 不变均通过；manifest 校验失败、复制后源启动、全量源目录 hash 未覆盖（f006/f010）。
- AC-003：re_verified。独立重跑 unit/integration 与 `src/app/router.test.tsx`（4 passed）；确认参数、种子重掷、其他 Profile 不变、DB 更新失败回滚均通过；UI 确认断言偏弱（f008），新配置版本未断言（f011）。
- AC-004：trust_prior。真实 Chrome E2E 未独立重跑（缺环境变量/engine cache）；现有前端测试 mock API，E2E 直接调 service 且只覆盖状态复制（f005）；并发幂等无覆盖（f002/f003/f004）。

coverage = 3 / 4

verdict: FAIL

## Round 2 (2026-11-02T12:44:45+08:00)

reviewed_scope: d74d710df6e683fe

### 前轮 finding 复核

|finding_id|Round 1 严重度|本轮结论|证据|
|---|---|---|---|
|t013_test_f001|critical|已消除|`tests/unit/test_profile_copy_reset.py:208` 覆盖空白名与 255 字符源名；`tests/integration/test_profile_copy_reset_api.py:159` 断言 400 且列表 200；独立重跑 `.scratch/t013_review_test/evidence_duplicate_name_api.py` 得 400/200。残留仅集成用例未断言列表长度为 1（f016）。|
|t013_test_f002|critical|已消除|`tests/unit/test_profile_copy_reset.py:430` 并发同键状态复制断言同一 id 且 `profiles/` 只有源与 clone；独立重跑 `evidence_concurrent_duplicate.py` 输出 `profile dirs: ['<clone>', 'p1']`，无孤儿目录。|
|t013_test_f003|important|已消除|`tests/unit/test_profile_copy_reset.py:455` 同键不同 `include_browser_state`/`name` 均抛 `ProfileOperationConflictError`；独立重跑 `evidence_idempotency_payload.py` 得到该异常。HTTP 409 映射未加集成用例，列为提示。|
|t013_test_f004|important|已消除|`tests/unit/test_profile_copy_reset.py:299` 并发同键 reset 得到同一新种子；独立重跑 `evidence_reset_race.py` 得 `results: [('Profile', 58549), ('Profile', 58549)]`、`versions: [1, 2]`。|
|t013_test_f005|important|已消除（按前轮允许的替代路径）|`tests/e2e/test_browser_runtime_e2e.py:2611` 已改为真实 HTTP API + 真实 Docker/Chrome：状态复制后重建 clone 容器并验证 Cookie，reset 经 API 并断言源数据目录清空；本轮用 t008 镜像与新建 engine cache 独立重跑，`1 passed in 17.43s`。`src/frontend/src/app/router.test.tsx:208` 覆盖前端重置确认。真实前端 duplicate 动作仍未直接测试（f012），config-only copy 未进入该 E2E（f013）。|
|t013_test_f006|important|已消除|`tests/unit/test_profile_copy_reset.py:359` manifest 不一致清理、`:382` 复制中途 OSError 清理、`:404` 复制后源运行清理；全部通过。故障注入 monkeypatch 限定在 copy/runtime seam，未替代 manifest 比较与清理逻辑本身。|
|t013_test_f007|important|已消除|`tests/unit/test_profile_copy_reset.py:333` 预置真实 Artifact DB 行后断言两个 clone 的 Artifact 列表为空、源仍为 1 条。残留仅未创建 storage 文件（f018）。|
|t013_test_f008|minor|已消除核心问题|`src/frontend/src/app/router.test.tsx:233-239` 断言确认前 `resetCalled === false`、确认后才为 true，并检查 cookies/history 文案。完整清除清单与运行中禁用仍未断言（f017）。|
|t013_test_f009|minor|已消除核心问题|`tests/unit/test_profile_copy_reset.py:71` 对 clone 与源 config 做整体比较；配置版本快照仍只抽样 seed/proxy/tags（f014）。|
|t013_test_f010|minor|已消除核心问题|`tests/unit/test_profile_copy_reset.py:102-107` 三个 Singleton 文件均断言跳过且源符号链接保留；`:323` 覆盖 observed stopping 拒绝。源目录全量 hash 仍未计算（f015）。|
|t013_test_f011|minor|已消除|`tests/unit/test_profile_copy_reset.py:148-152` 断言 `current_config_version == 2` 且版本 2 快照种子等于重置后种子。|

### Findings

#### t013_test_f012 - 前端 duplicate 动作与真实 client 请求仍未测试，AC-004 的“真实前端”子句证据不足

- 严重度：minor
- 锚点：AC-004“真实前端经API完成配置复制/状态复制/重置”。
- 位置：`src/frontend/src/app/router.test.tsx:226-228`；`src/frontend/src/features/profiles/ProfileDetailPage.tsx:52`；`src/frontend/src/shared/api/client.ts:180`；对照 `tests/e2e/test_browser_runtime_e2e.py:2611`。
- 问题：前端测试只点击 `profile-duplicate-button` 并断言面板文字，没有点击“仅配置复制”或“含状态复制”动作，也没有断言 `defaultApiClient.profiles.duplicate` 的 id / `include_browser_state`。真实 E2E 用 httpx 直接调 API，绕过前端。若 `handleDuplicate` 或 client 的 duplicate 路径写错，现有测试仍全绿。因 API+容器路径已有独立 E2E，按覆盖扩展定为 minor，而非 blocking。
- 建议：至少在前端測試中分别点击两个 duplicate 动作，断言 `profiles.duplicate` 被调用且 `include_browser_state` 正确；有条件时补真实 Playwright 前端流程。

#### t013_test_f013 - 真实容器 E2E 未验证 clone 配置版本，配置复制结果仍在容器启动路径之外

- 严重度：minor
- 锚点：AC-004“容器重建后 Cookie 与配置结果符合所选操作”。
- 位置：`tests/e2e/test_browser_runtime_e2e.py:2727-2734`。
- 问题：E2E 为 clone 手工调用 `create_snapshot_file(..., screen_width=1280, screen_height=720)`，没有读取 clone 的 `current_config_version` / 配置版本快照来生成容器配置；也完全没有覆盖 config-only duplicate 的容器重建。配置字段目前由 unit/integration 覆盖，故定为 minor。
- 建议：从 clone 的配置版本快照生成 clone 容器配置，或在 E2E 中至少断言 clone 的 `current_config_version == 1` 且快照配置与源一致。

#### t013_test_f014 - 配置版本快照仍只抽样字段，未做整体比较

- 严重度：minor
- 锚点：AC-001“全部有效配置字段保留”。
- 位置：`tests/unit/test_profile_copy_reset.py:75-78`。
- 问题：`versions[0].config` 只断言 `fingerprint_seed`、`proxy`，标签单独断言；`screen_width`、`gpu_family`、`humanize`、`geoip`、`clipboard_sync`、`launch_args`、`extension_paths` 等从快照丢失时测试仍通过。Profile 域对象有整体比较，但配置版本快照没有。
- 建议：断言 `versions[0].config == clone.config.model_dump()`，或逐字段比较快照。

#### t013_test_f015 - 源用户数据目录未做整体 hash，源数据完整性只验证少量文件

- 严重度：minor
- 锚点：AC-002“不损坏源数据”。
- 位置：`tests/unit/test_profile_copy_reset.py:81`、`:105-108`。
- 问题：复制后只断言源 `Cookies` 字节和三个 Singleton 符号链接；源 `Default/Preferences` 或其他文件被修改时测试不会失败。spec 测试策略要求用户数据目录 hash。
- 建议：复制前后对源目录（排除 Singleton 文件）计算相对路径 + SHA-256 清单并比较。

#### t013_test_f016 - 空白名 HTTP 负向测试未断言未创建 Profile

- 严重度：minor
- 锚点：AC-001 复制创建新 Profile 的边界；f001 原始修复。
- 位置：`tests/integration/test_profile_copy_reset_api.py:159-167`。
- 问题：只断言 400 和 `GET /api/v1/profiles` 为 200，没有断言列表长度仍为 1。若实现先创建一条合法但不该存在的 Profile 再返回 400，测试仍通过；原始坏行导致列表 500 的问题已被 200 断言覆盖。
- 建议：补 `listed = client.get(...).json(); assert len(listed) == 1`，并断言数据库无新 Profile。

#### t013_test_f017 - 前端重置确认未断言完整清除清单与运行中禁用

- 严重度：minor
- 锚点：AC-003“确认界面明确列出将清数据”。
- 位置：`src/frontend/src/app/router.test.tsx:231-232`。
- 问题：只匹配 `/cookies/i` 与 `/history|bookmarks/i`，未验证站点数据、缓存、保存密码、扩展、登录状态、指纹身份等完整 `resetProfileDataList`，也未验证运行中时含状态复制按钮/重置按钮禁用。
- 建议：断言完整 i18n 文案或关键项全量，并补 `observed_state=running` 下按钮 disabled 断言。

#### t013_test_f018 - Artifact 边界测试只建元数据行，未建 storage 文件

- 严重度：minor
- 锚点：AC-001/AC-002“不复制 Artifact”。
- 位置：`tests/unit/test_profile_copy_reset.py:336-353`。
- 问题：`create_artifact` 的 `storage_path` 指向的文件从未创建；断言只覆盖 Artifact DB 记录，未覆盖 storage 文件不被复制/源文件不变。
- 建议：创建源 Artifact storage 文件，复制后断言 clone 无对应文件且源文件内容不变。

### 结论

- 前轮 finding 复核：f001、f002、f003、f004、f005、f006、f007 六条 important/critical 均已消除；f005 采用前轮允许的“HTTP API + 真实容器”替代路径，本轮已独立跑通真实 Docker/Chrome E2E。f008、f009、f010 的核心问题已消除，残留覆盖扩展列为 f014/f015/f017。f011 已消除。
- 改测方向复核：无。diff 中只有新增测试与新增断言，没有删除测试、删除/反转 expect、`.skip`/`.only`，也没有把旧断言改成当前实现输出。
- 本轮新发现：7 条，全部 minor（f012–f018）。
- 未进表提示：同键不同 payload 的 HTTP 409 映射仍只有 unit 覆盖，建议补 integration；并发 reset 测试未断言配置版本数量（证据脚本显示 `[1, 2]`）；测试使用 `repo._session_maker` 私有属性，属测试基础设施 smell；E2E 依赖镜像与 engine cache，本轮用 t008 镜像并新建 `.scratch/t013_review_test_r2/engine-cache` 跑通，CI 仍需显式设置环境变量；`.repo_template` contract 失败与 legacy `src/backend/tests` 收集错误按已知前提不计入本轮。
- 流程提示：本测试报告 Round 2 的 `reviewed_scope: d74d710df6e683fe` 与当前重算值一致；`check_review_status.py` 仍报 `review_scope=stale`，是因为 `review_code.md` 仍保留 Round 1 旧指纹，不是本报告失效。
- 总体判断：前轮所有 critical/important 已消除，本轮无新 blocker；真实 Docker/Chrome E2E 已独立通过，仅剩 minor 覆盖扩展，PASS。
- 系统性 follow-up：无；f012/f013 属本 task AC-004 的前端/配置 E2E 覆盖残留，建议在 finalization 前补最小前端 duplicate 调用断言或 Playwright 流程，不另立替代 task。

### AC 复验方式

- AC-001：re_verified。独立重跑 `tests/unit`（488 passed）与 `tests/integration`（85 passed）；`tests/unit/test_profile_copy_reset.py:71` 做完整 config 比较，`:74-78` 检查版本 1 与部分快照字段；Artifact 边界由 `:333` 的非空源 Artifact 用例覆盖。快照整体比较与 storage 文件仍为 minor（f014/f018）。
- AC-002：re_verified。独立重跑真实 E2E `test_t013_state_copy_restores_cookies_in_clone`（1 passed in 17.43s）；unit 覆盖三 Singleton、manifest 不一致、复制后源运行、复制中途 OSError；源目录全量 hash 未做（f015）。
- AC-003：re_verified。unit/integration 覆盖确认参数、种子重掷、版本 2、DB 失败回滚、其他 Profile 不受影响；前端测试覆盖确认前不执行、确认后执行；完整清除清单仍为 minor（f017）。
- AC-004：re_verified（API+真实容器路径）。独立重跑真实 HTTP API + Docker/Chrome E2E 通过；并发同键 duplicate/reset、同键不同 payload、非法名、列表不中毒均有 unit/integration 证据。真实前端 duplicate 动作仍只 mock 覆盖（f012），前端 UI 子项为 trust_prior；config-only copy 的容器重建未覆盖（f013）。

coverage = 4 / 4（AC-004 的 API/容器路径已 re_verified；真实前端 duplicate UI 子项 trust_prior，见 f012）

verdict: PASS

## Round 3 (2026-11-02T12:58:20+08:00)

reviewed_scope: 88d58a5a76da143a

### 前轮 finding 复核

|finding_id|Round 2 严重度|本轮结论|证据|
|---|---|---|---|
|t013_test_f012|minor|修不彻底：仅覆盖 config-only 分支|`src/frontend/src/app/router.test.tsx:235-238` 点击 “Duplicate settings and fingerprint only” 并断言 `include_browser_state=false`；仍未点击 “With browser state”（`src/frontend/src/features/profiles/ProfileDetailPage.tsx:223-231`），也未断言调用的 profile id。`defaultApiClient.profiles.duplicate` 在 `router.test.tsx:227` 被整体替换，真实 `shared/api/client.ts:180` 的 duplicate 路径仍未执行。|
|t013_test_f013|minor|已消除（按前轮允许的“至少断言”路径）|`tests/e2e/test_browser_runtime_e2e.py:2720-2721` 断言 clone `current_config_version == 1` 且 `fingerprint_seed == 999`；本轮真实 Docker/Chrome E2E 重跑通过。clone 容器配置仍由手工 `create_snapshot_file` 生成（`:2728-2741`），但原 finding 已给出该替代条件。|
|t013_test_f014|minor|已消除|`tests/unit/test_profile_copy_reset.py:76` 断言 `versions[0].config == clone.config.model_dump()`，`:77` 断言版本标签与源一致；全量字段进入比较。|
|t013_test_f015|minor|仍存在：声称的全量源目录 hash 未实现|状态复制用例 `tests/unit/test_profile_copy_reset.py:90-112` 仍只比较源 `Cookies` 字节和遗留 Singleton 符号链接；整个文件仅 `:363` 的 `test_copy_manifest_mismatch_removes_clone` 出现 manifest，且该用例是注入克隆差异，不是“复制前后源目录相对路径 + SHA-256 清单”比较。`note.md` Round 2 的“状态复制前后源/副本 manifest 全量比较”与当前文件不符。|
|t013_test_f016|minor|已消除|`tests/integration/test_profile_copy_reset_api.py:159-169` 空白名请求返回 400 后断言 `GET /api/v1/profiles` 为 200 且 `len(listed.json()) == 1`。|
|t013_test_f017|minor|修不彻底：文案仍只抽查三项，运行中禁用未测|`src/frontend/src/app/router.test.tsx:241-243` 仅匹配 cookies、history/bookmarks、passwords/extensions；`src/frontend/src/i18n.tsx:144-145` 的完整清单还含 site data、cache、logged-in sessions、fingerprint identity。确认前 `resetCalled === false` 已断言（`:242`），但没有 running 状态下 duplicate-with-state / reset 按钮 disabled 的用例。|
|t013_test_f018|minor|已消除|`tests/unit/test_profile_copy_reset.py:332-357` 预置真实 Artifact 元数据与 storage 文件，断言两个 clone 的 Artifact 列表为空、源记录仍为 1、源 storage 内容不变、clone artifact 目录不存在。|

### Findings

本轮无新增 finding。

### 结论

- 前轮 finding 复核：f013、f014、f016、f018 已消除；f012、f017 仍为 minor 级覆盖残留；f015 的声称修复不存在，仍为 minor。无未解决的 critical / important。
- 改测方向复核：无。本轮 router 测试只在新增 `it` 内追加断言，E2E 新增用例也只追加断言；没有删除既有测试、删除/反转 expect、`.skip` / `.only`，也没有把旧断言改成当前实现输出。
- 本轮新发现：0 条。
- 未进表的提示：`note.md` 的 review 处置表重复使用 `t013_code_f007`（Round 1 与 Round 2 各一行），`check_review_status.py --task-dir` 因此报 `finding_id 重复：t013_code_f007` 退出，影响收尾门禁，建议实施侧修正处置表 ID；E2E 仍需显式设置 `CBROWSER_RUNTIME_TEST_IMAGE` 与 `CBROWSER_RUNTIME_ENGINE_CACHE`；测试使用 `repo._session_maker` 私有属性；config-only duplicate 的容器重建仍无 E2E 覆盖。
- 总体判断：本轮无新 blocker，AC 行为由可执行测试与真实 Docker/Chrome E2E 支撑；f012、f015、f017 仅为 minor 覆盖残留，PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：re_verified。独立重跑 `tests/unit/test_profile_copy_reset.py`（20 passed）与 `tests/integration/test_profile_copy_reset_api.py`（6 passed）；克隆创建、全量 config/版本快照比较、Artifact 非复制与源文件不变均有断言。
- AC-002：re_verified。独立重跑 unit/integration 与真实 E2E `test_t013_state_copy_restores_cookies_in_clone`（1 passed in 19.32s）；停止源拒绝、用户数据复制、三 Singleton 跳过、manifest 不一致清理、复制中异常清理、复制后源运行清理均通过。源目录全量 hash 仍缺（f015）。
- AC-003：re_verified。独立重跑 unit/integration 与前端 router 测试（4 passed，full Vitest 117 passed）；确认前不执行、确认后执行、种子重掷、`current_config_version == 2`、DB 失败回滚、其他 Profile 不受影响均通过。
- AC-004：re_verified（HTTP API + 真实容器路径）。E2E 经真实 HTTP duplicate/reset 并在重建 clone 容器后验证 Cookie；并发同键 duplicate/reset、同键不同 payload、非法名均有 unit/integration 证据。真实前端 duplicate 的 with-state 分支与真实 client 仍未执行，属 f012 的 minor 残留（UI 子项 trust_prior）。

coverage = 4 / 4（AC-004 的真实前端 with-state UI 子项为 trust_prior，见 f012）

verdict: PASS

## Round 4 (2026-11-02T13:12:17+08:00)

reviewed_scope: 68994e2bb7fa7d48

### 前轮 finding 复核

|finding_id|Round 3 严重度|本轮结论|证据|
|---|---|---|---|
|t013_test_f012|minor|同意撤回（覆盖扩展）|`src/frontend/src/app/router.test.tsx:235-238` 仍只点击 config-only 并 mock `defaultApiClient.profiles.duplicate`；with-state 前端分支由真实 HTTP API + Docker/Chrome E2E 覆盖。属 minor 覆盖扩展，按处置表撤回，不阻断。|
|t013_test_f013|minor|已消除（前轮已确认）|`tests/e2e/test_browser_runtime_e2e.py:2720-2721` 断言 clone `current_config_version` 与 `fingerprint_seed`；本轮 E2E 重跑通过。|
|t013_test_f014|minor|已消除（Round 3 已确认）|`tests/unit/test_profile_copy_reset.py:76-77` 全量比较配置版本快照与标签；本轮回归通过。处置表遗留项为代码轴 `t013_code_f014`（长复制阻塞 bind），已指向 t009；非本报告 finding。|
|t013_test_f015|minor|已消除|`tests/unit/test_profile_copy_reset.py:110` 新增 `assert _manifest(clone_dir) == _manifest(profile_dir)`；`_manifest` 对相对路径 + SHA-256 + size 全量建表并排除三个 Singleton 文件。独立探针输出源/克隆各 2 条内容哈希、Singleton 未入表；删除克隆 `Cookies` 后比较立即为 False，断言非恒真（`.scratch/t013_review_test_r4/evidence/manifest_probe.log`）。|
|t013_test_f016|minor|已消除（Round 3 已确认）|`tests/integration/test_profile_copy_reset_api.py:159-169` 断言空白名 400、列表 200 且长度为 1。|
|t013_test_f017|minor|同意撤回（覆盖扩展）|`src/frontend/src/app/router.test.tsx:241-243` 已断言确认前 `resetCalled === false` 及 cookies/history/passwords 等关键文案；完整清单与运行中禁用属 minor 扩展，按处置表撤回，不阻断。|
|t013_test_f018|minor|已消除（Round 3 已确认）|`tests/unit/test_profile_copy_reset.py:332-357` 建真实 Artifact storage 文件并断言不复制、源内容不变。|

Round 4 回归：`tests/unit` 489 passed、`tests/integration` 85 passed、`tests/unit/test_profile_copy_reset.py tests/integration/test_profile_copy_reset_api.py` 26 passed、前端 `router.test.tsx` 4 passed、真实 Docker/Chrome E2E `test_t013_state_copy_restores_cookies_in_clone` 1 passed（镜像 `cbrowser-t008-browser:e2e`，engine cache `.scratch/t013_review_test_r3/engine-cache`）。证据日志均在 `.scratch/t013_review_test_r4/evidence/`。

### Findings

本轮无新增 finding。

### 结论

- 前轮 finding 复核：f015 已真实修复；f012、f017 的 minor 扩展开支按处置表撤回，同意；f013、f014、f016、f018 维持已消除。无未解决的 critical / important。
- 改测方向复核：无。本轮测试改动只为状态复制用例追加源/克隆全量 manifest 断言（`tests/unit/test_profile_copy_reset.py:110`），没有删除/反转既有断言，也没有把断言改成迁就当前实现。
- 本轮新发现：0 条。
- 未进表的提示：
    - `src/backend/cbrowser/services/profile_service.py` 在 Round 3 code review（`reviewed_scope: 88d58a5a76da143a`）之后有改动，当前工作区指纹为 `68994e2bb7fa7d48`，code review 的 Round 3 PASS 已失效，需按流程补 code Round 4。本轮已针对当前生产代码重跑 unit/integration/前端/E2E，测试轴证据仍成立。
    - `note.md` 处置表 Round 2 与 Round 3 重复使用 `t013_code_f011`，`check_review_status.py --task-dir` 仍会以「finding_id 重复」退出，影响收尾门禁；请实施侧修正 ID（本 reviewer 不修改 note.md）。
    - manifest fixture 仍只有 `Cookies` 与 `Default/Preferences` 两个文件；f015 的结构性全量比较已具备，若要验证更深目录/二进制/权限差异可再扩 fixture，属可选覆盖扩展，不阻断。
- 总体判断：f015 修复真实有效，Round 4 无新 blocker；AC-001～AC-004 的测试证据与当前生产代码一致，PASS。
- 系统性 follow-up：`t013_code_f014` 已指向 t009（完成正式拓扑安全与性能输入压力验收）；无新增 follow-up。

### AC 复验方式

- AC-001：re_verified。本轮重跑 `tests/unit/test_profile_copy_reset.py`（20 passed）与 `tests/integration/test_profile_copy_reset_api.py`（6 passed）；全量 config、配置版本快照、标签、Artifact 非复制与源不变断言通过。
- AC-002：re_verified。状态复制用例新增源/克隆全量 manifest 比较并携带 Singleton 排除断言；manifest 探针证明比较非恒真；真实 E2E 重跑通过（18.75s）。
- AC-003：re_verified。unit/integration/reset 断言（确认参数、种子重掷、`current_config_version == 2`、回滚）与前端确认流程测试均通过。
- AC-004：re_verified（HTTP API + 真实容器主路径）。本轮真实 HTTP duplicate/reset + Docker/Chrome 重建 clone 并读回 Cookie、reset 后源目录清空；真实前端 with-state UI 子项仍为 trust_prior（f012 撤回记录）。

coverage = 4 / 4（AC-004 的真实前端 with-state UI 子项为 trust_prior，见 f012 撤回记录）

verdict: PASS

## Round 5 (2026-11-02T13:27:33+08:00)

reviewed_scope: 3b90f37ed20afe31

### 范围确认（相对 986d3e2）

- 交付 diff 与 HEAD 一致；`review_scope_fingerprint` 重算为 `3b90f37ed20afe31`，与本 prompt 指定值一致。`git status` 仅有并发的 `review_code.md` 过程文件改动，不在审查指纹内。
- 当前源/克隆 manifest 断言为 `tests/unit/test_profile_copy_reset.py:110` 的 `assert _manifest(clone_dir) == _manifest(profile_dir)`。生产 `_manifest` 按相对路径、类型、SHA-256 与 size 建立全量 dict，并排除三个 Singleton 文件；独立探针复跑得源/克隆各 2 条且相等，删除克隆 `Cookies` 后比较立即为 `False`，断言非恒真、未弱化。该用例原有 Cookie、Preferences、三 Singleton 缺席、源符号链接与 Artifact 空集断言均保留。
- `note.md` 处置表去重完成：32 个 finding ID 无重复（29 已修 / 2 撤回 / 1 遗留 `t009`），`check_review_status.py` 不再报 `finding_id 重复`。收尾报告仍写 `reviewed_scope=68994e2bb7fa7d48`，属流程文档陈旧值，不影响本轮审查指纹；建议实施侧同步（reviewer 未改 `note.md`）。

### 前轮 finding 复核

|finding_id|Round 4 严重度|本轮结论|证据|
|---|---|---|---|
|t013_test_f012|minor|同意撤回（覆盖扩展）|`src/frontend/src/app/router.test.tsx:235-238` 仍只覆盖 config-only 前端动作；with-state 路径由真实 HTTP API + Docker/Chrome E2E 覆盖。|
|t013_test_f013|minor|已消除（维持）|`tests/e2e/test_browser_runtime_e2e.py:2720-2721` 断言 clone `current_config_version == 1` 与 `fingerprint_seed == 999`；本轮 E2E 重跑通过。|
|t013_test_f014|minor|已消除（维持）|`tests/unit/test_profile_copy_reset.py:76-77` 全量比较配置版本快照与标签；本轮回归通过。|
|t013_test_f015|minor|已消除（维持）|`:110` 源/克隆 `_manifest` 全量比较；探针证明条目非空且比较非恒真。|
|t013_test_f016|minor|已消除（维持）|`tests/integration/test_profile_copy_reset_api.py:159-169` 断言空白名 400、列表 200 且长度为 1；本轮 integration 重跑通过。|
|t013_test_f017|minor|同意撤回（覆盖扩展）|`src/frontend/src/app/router.test.tsx:241-243` 已断言确认前 `resetCalled === false` 及 cookies/history/passwords 关键文案；完整清单与运行中禁用属 minor 扩展。|
|t013_test_f018|minor|已消除（维持）|`tests/unit/test_profile_copy_reset.py:332-357` 建真实 Artifact storage 文件并断言不复制、源内容不变；本轮回归通过。|

Round 1–3 已关闭的 f001–f011 无回归：本轮全量 unit 489 passed、integration 85 passed。

### 结论

- 前轮 finding 复核：f012、f017 撤回维持；f013、f014、f015、f016、f018 维持已消除；无未解决 critical / important。
- 改测方向复核：无。当前 diff 只有新增测试与新增断言；manifest 断言从抽查升级为全量 dict 比较，没有删除/反转 expect、`.skip` / `.only`、条件弱化或迁就实现的改测。
- 本轮新发现：0 条。
- 未进表的提示：
    - `note.md` 收尾报告仍写旧指纹 `68994e2bb7fa7d48`；当前审查指纹为 `3b90f37ed20afe31`，建议收尾同步。`review_code.md` 的 Round 4 历史小节保留旧指纹属正常，其 Round 5 已为同一当前指纹。
    - E2E 依赖 `CBROWSER_RUNTIME_TEST_IMAGE` 与已初始化 engine cache；本轮使用 `cbrowser-t008-browser:e2e` 与 `.scratch/t013_review_test_r3/engine-cache` 重跑通过，CI 仍需显式设置。
- 总体判断：当前测试交付与 Round 4 PASS 结论一致，manifest 断言全量且非恒真，无未解决 blocker，PASS。
- 系统性 follow-up：无（`t013_code_f014` 已登记遗留 `t009`）。

### 回归证据

- `tests/unit`：489 passed（`.scratch/t013_review_test_r5/evidence/pytest_unit_full_r5.log`）。
- `tests/integration`：85 passed（`.scratch/t013_review_test_r5/evidence/pytest_integration_full_r5.log`）。
- 本 task 定向用例：26 passed（`.scratch/t013_review_test_r5/evidence/pytest_t013_r5.log`）。
- 前端 `src/app/router.test.tsx`：4 passed（`.scratch/t013_review_test_r5/evidence/frontend_router_r5.log`）。
- 真实 Docker/Chrome E2E `test_t013_state_copy_restores_cookies_in_clone`：1 passed in 18.21s（`.scratch/t013_review_test_r5/evidence/e2e_t013_r5.log`）。
- manifest 探针：源/克隆各 2 条、相等；删除克隆 `Cookies` 后为 `False`（`.scratch/t013_review_test_r5/evidence/manifest_probe_r5.log`）。

### AC 复验方式

- AC-001：re_verified。定向 unit/integration 与全量 unit 重跑通过；全量 config、配置版本快照、标签、Artifact 不复制与源不变断言均执行。
- AC-002：re_verified。源/克隆 `_manifest` 全量比较、三 Singleton 跳过、stopped 门禁、manifest 不一致/复制中异常/复制后源运行清理用例通过；真实容器 E2E 重跑通过。
- AC-003：re_verified。reset 的确认参数、种子重掷、`current_config_version == 2`、其他 Profile 不变、DB 失败回滚与备份清理用例通过；前端确认流程 4 passed。
- AC-004：re_verified（HTTP API + 真实容器主路径）。真实 HTTP duplicate/reset 与重建 clone 容器读回 Cookie 的 E2E 通过；并发同键 duplicate/reset、同键不同 payload、非法名、列表不中毒均有 unit/integration 证据。真实前端 with-state UI 子项为 trust_prior（f012 撤回记录）。

coverage = 4 / 4（AC-004 的真实前端 with-state UI 子项为 trust_prior，见 f012 撤回记录）

verdict: PASS

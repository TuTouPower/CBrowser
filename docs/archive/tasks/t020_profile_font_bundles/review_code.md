# Task review t020（reviewer_focus: 代码）

- task：`t020_profile_font_bundles`
- spec：`docs/tasks/t020_profile_font_bundles/task.md`
- diff_anchor：`30f5078d597d6f8c0b1e73986339e22ab7a1aafc`
- target：`git -C ~/workspace/CBrowser_t020 diff 30f5078d597d6f8c0b1e73986339e22ab7a1aafc`
- round：1
- reviewed_at：2026-11-04T01:11:55+08:00

reviewed_scope: 5f0d2fda8efbde6b

## Findings

本轮共 4 条 finding，全部为 minor；无 critical / important。

### t020_code_f001（minor）未知 bundle 时生成失败不走回退、与契约措辞不符

- 位置：`src/backend/cbrowser/runtime_agent/fontconfig.py:60`（`prepare_profile_fontconfig`）。
- 证据：`build_fontconfig_xml(...)` 在 `try` 块之外调用，未知 bundle 时其 `ValueError` 直接向外传播（本 reviewer 实测：`prepare_profile_fontconfig(p, "simsun")` 抛 `ValueError: Unknown font bundle`，不返回 `None`）；而该函数 docstring 只声明「`none` 与写入失败时返回 `None`」，task.md 风险回退条款与 note.md 实施笔记均无条件地写「生成失败回退系统默认配置」。实测对照：写入失败路径（run_dir 位于普通文件之下）确实捕获 `OSError`、记 error 日志并返回 `None`，回退成立——只有「非法值」这一类生成失败不在回退内。
- 影响评估：经正常通路不可达——快照必经 `load_config_snapshot` 的 `ProfileConfig.model_validate`（`Literal` 三档）校验后才进 `runner.start()`，非法值在更早层已被拒。故定 minor 而非 important。
- 建议：把 `build_fontconfig_xml` 调用移入 `try` 并把 `ValueError` 一并按回退处理（或收窄 docstring / 笔记措辞为「写入失败回退、非法值 fail-closed」），使实现与契约表述一致，并补一条 `prepare_profile_fontconfig` 未知 bundle 的 unit 断言钉住选定语义。

### t020_code_f002（minor）note.md 称「原子写 + fsync」，实现为就地直写

- 位置：`src/backend/cbrowser/runtime_agent/fontconfig.py:64-68`；披露在 `docs/tasks/t020_profile_font_bundles/note.md` 实施笔记 Runner 条。
- 证据：实现为 `target.open("w")` 直接截断并写入目标文件，再 `flush` + `os.fsync` + `chmod`；没有本仓标准原子写（`runtime_agent/event_storage.py:atomic_write_json` 的 tmp 文件 + `os.replace` + 目录 fsync）中的任何一步。写入中途崩溃会留下一份截断的 `profile-fonts.conf`。
- 影响评估：受限——文件在每次 `start()`、Chrome 启动之前重新生成，`prepare` 仅在写成功后才返回路径，失败返回 `None` 时本次运行不会引用残文件；不构成可用性缺陷，但实施笔记的证据表述不准确，后来者会据此误判该文件的崩溃一致性等级。
- 建议：二选一——改用 tmp + `os.replace` 落实原子写，或把 note.md 措辞改成与实现一致的「直写 + fsync」。

### t020_code_f003（minor）切回 `none` 后 run_dir 内残留旧的 profile-fonts.conf

- 位置：`src/backend/cbrowser/runtime_agent/fontconfig.py:58-59`（`none` 分支直接返回，不清理既有文件）。
- 证据：本 reviewer 实测——同一目录先以 `wqy-microhei` 生成、再以 `none` 调用 `prepare_profile_fontconfig`，返回 `None` 后 `profile-fonts.conf` 仍留在目录中。
- 影响评估：当前无功能影响——`runner._browser_environment` 恒先 `pop("FONTCONFIG_FILE")`、仅在拿到路径时才设置，残文件不会被 Chrome 读到；且生产上每个 runtime 实例有独立 run_dir。属卫生/健壮性问题：残文件会让排障时对「该 profile 实际字体状态」的判断产生误导。
- 建议：`none` 分支顺手 `target.unlink(missing_ok=True)`（生成失败回退时同理），使 run_dir 内容与生效配置一致。

### t020_code_f004（minor）note.md 实施笔记字面引用了 repo_hygiene 所禁的开发者 home 路径串

- 位置：`docs/tasks/t020_profile_font_bundles/note.md:35`（基线对照条）。
- 证据：本 reviewer 复跑 `tests/unit/test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths`，其违规清单除 anchor 已含的 `docs/reviews/review_20261103_185924/` 两文件（提交 4f78524 引入、属存量）外，新增一行指向 t020 自己的 note.md——实施笔记为说明基线失败原因，把该测试所禁止的开发者 home 绝对路径字面量原样写进了被跟踪文件（该行在 diff_anchor 版本中不存在）。note.md 称「本 task 零新增失败」按测试 ID 计数属实（仍是同 2 条失败），但违规条目数因本 task 增加了一条。
- 建议：把该处措辞改为不含字面量的转述（如「review 归档文件含开发者 home 路径」），避免继续扩散该测试要拦的内容。

## 审查覆盖记录

- 规格合规 / 一致性映射：`font_bundle` 五处贯通且取值/默认值一致——领域 `ProfileConfig.font_bundle: FontBundle = "none"`（`domain/models.py:72`，含显式 null 拒绝 validator）；DTO `ProfileCreateRequest`（默认 `none`、null 由 `Literal` 拒绝，本 reviewer 探针实测）、`ProfileUpdateRequest`（`FontBundle | None = None` + before-validator 拒显式 null，与 `exclude_unset` 的 PATCH 三态语义不冲突）、`ProfileResponse`（`from_domain` 携带）；SQLite 列 `String(32), NOT NULL, default="none"`（`adapters/database/models.py:47`）；Alembic `0007_font_bundle`（`down_revision="0006_snapshot_modes"` 与 0006 文件 `revision` 对齐、batch `add_column` + `server_default="none"`、downgrade 对称）；repository 四处映射齐全（create 写入 `repository.py:119`、update 合并基底字典 `:305`、update 写回 `:348`、`_to_domain` 读取 `:802`），create/update 两处快照 JSON 均经 `ProfileConfig.model_dump()` 自动携带；复制 Profile 走 `model_dump` 克隆、字段自动继承。旧快照（无该键）经 `model_validate` 默认 `none`，存量兼容成立。
- OpenAPI / 生成类型：`schemas/openapi/cbrowser_v1.json` 与 `cbrowser_internal.json` 的 font_bundle 结构逐项一致（Create 为 enum+default、Response 为 string、Update 为 enum+null 的 anyOf）；前端生成类型 `cbrowser_v1.d.ts` 已同步重生成，手写层仅经 `types.ts` 别名 + `DEFAULT_PROFILE_CREATE_VALUES.font_bundle="none"` 消费，生成/手写边界干净。
- Runner / fontconfig：生成内容与契约一致——include `/etc/fonts/fonts.conf` + 仅追加所选 bundle 的一个 `<dir>`，两档互不串（unit 断言覆盖）；`_browser_environment` 恒清除继承的 `FONTCONFIG_FILE`、仅生成成功时设置、且不 mutate `os.environ`（探针实测宿主 env 不受影响）；`start()` 在 Chrome 启动前接线 `prepare_profile_fontconfig(self.run_dir, cfg.font_bundle)`；XML 插值前先做白名单成员校验，`bundle_root` 生产上恒为常量，无注入面。除 f001/f002/f003 外未见其他问题。
- Dockerfile：`font_bundle_builder` 阶段（digest 钉版 `debian:bookworm-slim`）装两包装出两个 `.ttc` 到 `/opt/cbrowser-fonts/{wqy-microhei,wqy-zenhei}`，最终镜像仅 `COPY --from=font_bundle_builder /opt/cbrowser-fonts`，最终阶段 apt 清单无任何字体包新增（仅存量的 `fonts-liberation`，非 CJK），字体不进默认扫描路径；包内路径错误会在构建期 `cp` 失败（fail-closed），且实施侧已用官方 .deb 的 `dpkg-deb -c` 核实路径与体积（5.2MB/16.8MB 与契约一致）。unit 静态断言对最终阶段的切分检查有效（按 `AS font_bundle_builder` 后第二个 `FROM` 切分，能拦最终阶段装包）。
- 前端：创建页三档 `<select>`（testid `profile-font-bundle-select`）、state 初值 `none`、提交时以显式 `font_bundle` 覆盖 `DEFAULT_PROFILE_CREATE_VALUES` 展开值；编辑页按既有 dirty-field 模式回显（`fontBundle` 键）、提交携带该字段；en/zh i18n 四键齐全。本 reviewer 复跑前端全量 21 文件 / 97 测试全过，其中新增 `ProfileNewPage` 字体用例与改写的 `ProfileDetailPage` 回显/提交用例均在内。
- 文档同步：task.md Finalization 列明的四份 blueprint 均已更新且与实现逐项一致（`browser_runtime.md` 字体包与开关边界、`domain.md` 字段语义、`persistence.md` 列与迁移约束、`decisions.md` 新增 015 决策）；`docs/specs/profile_management.md` 新增小节属实、`docs/specs_index.md` 的 profile_management 关联 task 已加 t020；p022 已立项追踪真实环境黑盒债务。diff 共 29 文件，全部落在契约范围内，无范围外改动、无顺手功能。
- 未进表的提示（与存量惯例一致、不作 finding）：① `ProfileResponse.font_bundle` 用宽松 `str` 而非 `FontBundle`、Update 的 OpenAPI schema 形式上允许 null——两者与同文件既有字段（`color_scheme` / `gpu_family` 的响应宽松类型与 reject-null validator + anyOf-null schema）完全同构，是本仓既有约定而非 t020 引入的回归；运行时拒绝路径经集成测试与探针证实有效。② e2e 隔离场景在单个容器内同跑两个 Runner（生产为每 Profile 独立容器），对 env 级隔离是更强口径，不作问题记录；该文件 5 条用例收集通过、容器脚本的 Runner 构造参数与现行签名核对无误，但从未真正执行（见 AC 复验）。

## 结论

- 本轮新发现：4 条，全部 minor（critical 0 / important 0 / minor 4）。
- 测试复跑（本 reviewer 在临时 venv 中按 `scripts/run_gates.sh` 的依赖口径独立执行，本机无 uv/Docker）：`tests/unit/test_font_bundles.py` + `tests/integration/test_profile_font_bundle_api.py` 共 24 条全过；全量 unit 573 passed / 2 failed，2 条失败与 note.md 声明的存量基线逐 ID 一致（repo_hygiene 与 terminal storage，后者与本 task 无关；前者另见 f004）；前端 97 测试全过；e2e 文件 5 条收集通过。另以探针补测了实施测试未覆盖的 create 端 null/非法值拒绝、写入失败回退、env 不污染宿主三条路径，均符合契约（未知 bundle 的 prepare 行为除外，见 f001）。

### AC 复验方式

- AC-001：`trust_prior`（静态半已 re_verified）。Dockerfile 布局、默认扫描路径之外的位置、最终镜像不装包已由本 reviewer 逐行核查并经 unit 静态断言复跑通过；实施侧从 Debian bookworm 官方源下载两 .deb 核实包内路径/体积、并以宿主 fontconfig 实测「默认不可见、单包可见、双包不串扰」，记录与契约吻合。但 AC 正文的镜像内 `fc-list`/`fc-match` 断言只能在构建后的真实镜像中执行，本机无 Docker、从未实跑，依赖 p022 在真实环境补验。
- AC-002：`re_verified`。本 reviewer 复跑 unit + integration 共 24 条：三档创建/更新/读取、未提供默认 `none`、迁移后存量行与 repository 读取均为 `none`、非法值在领域/创建/更新/API 四层被拒、更新显式 null 返回 422；另以探针补验创建端 null 被拒（实施测试未覆盖此格）。
- AC-003：`trust_prior`（机制半 re_verified）。`none` 不生成文件、`_browser_environment` 清除 `FONTCONFIG_FILE` 的 unit 断言已复跑通过，2026-11-03 真实引擎预验证（中文与私用区等宽）记录在 task.md；但「Chrome 渲染度量一致」的正文断言在 `tests/e2e/test_browser_font_bundles_e2e.py` 中从未于真实容器执行，归 p022。
- AC-004：`trust_prior`（机制半 re_verified）。生成配置只含对应 bundle 目录、env 指向生成文件的 unit 断言已复跑通过，实施侧宿主 fontconfig 实验显示两档分别只列出 Micro Hei / Zen Hei；CDP 实际字体族断言同样未在真实镜像执行，归 p022。
- AC-005：`trust_prior`（版本半 re_verified）。「修改产生新配置版本且不影响旁观 Profile」已由本 reviewer 复跑的 repository unit 用例证实（目标 1→2、双版本快照值正确、旁观者版本与值不变）；但「两个 Profile 同时运行互不影响」与「重建容器后新值生效」依赖双 Runner 真实渲染 e2e，从未执行，归 p022。
- AC-006：`re_verified`。前端组件层（创建默认 `none` 并提交所选档、编辑回显 API 值并提交变更）与 API 层回显（integration 的 create/update/read-back）分别经本 reviewer 复跑证实，两层取值一致；未做真实浏览器内的 UI 端到端，但这与本仓前端门禁的既定验证层级一致。
- coverage = 2 / 6
- 总体判断：实现与契约逐项对齐，领域/持久化/迁移/runner/前端五层的非黑盒部分经独立复跑成立；4 条 minor 均为健壮性与披露精度问题，不改变任何 AC 的行为结论。AC-001/003/004/005 的真实环境（镜像 + Chrome）证据等级为 trust_prior，note.md 对此披露属实（明确标注 trust_prior 并立 p022），按用户 2026-11-03 指令黑盒跳过按 pass 计，不据此判 FAIL。
- 系统性 follow-up：真实环境执行债务已由 p022 承接；f001–f004 建议在本 task 内以小修处置或在 note.md 逐条登记去向。

verdict: PASS

## Round 2 — scope re-attestation（证据修复轮次，非全新业务审阅）

- round：2（scope re-attestation）
- reviewed_at：2026-11-04T01:15:02+08:00
- 性质：Round 1 本路结论为 PASS、零 critical / important、4 条 minor（t020_code_f001–f004），但其 `reviewed_scope: 5f0d2fda8efbde6b` 因实施方逐项修复（含 test 路两条 minor 的修复）导致交付内容变更而过期。本轮只独立核实「四项修复属实、delta 清单完整、当前指纹正确」并重签 scope，不重做业务审阅；若核实发现新问题，按实情记录。

### 核实结果

1. **f001 未知 bundle 回退（属实）**。`src/backend/cbrowser/runtime_agent/fontconfig.py` 的 `prepare_profile_fontconfig` 已把 `build_fontconfig_xml(...)` 调用移入 `try` 块（第 70–71 行），`except (OSError, ValueError)`（第 84 行）统一记 error 日志并返回 `None`，与 docstring 的「生成失败回退系统默认配置」口径一致。新增 unit 测试 `test_prepare_fontconfig_unknown_bundle_falls_back_to_none`（`tests/unit/test_font_bundles.py:270`）断言未知 bundle（`simsun`）返回 `None` 且目录内无残留文件，本轮复跑通过。
2. **f002 真原子写（属实）**。生成文件改为先写同目录 tmp 文件（`profile-fonts.conf.tmp`）、`flush` + 文件 `fsync`、`chmod 0o600`，再 `os.replace(tmp, target)` 落位，最后打开 run_dir 目录 fd 做目录 `fsync`（`fontconfig.py:73–83`），与本仓原子写纪律一致，不再是 Round 1 的就地直写。`note.md` 措辞已同步为「tmp + os.replace + fsync 原子写」（实施笔记 Runner 条与 f002 处置行），实现与披露一致。
3. **f003 `none` 清理残留（属实）**。`prepare_profile_fontconfig` 在 `font_bundle == "none"` 分支先执行 `target.unlink(missing_ok=True)` 再返回 `None`（`fontconfig.py:66–68`）。新增 unit 测试 `test_prepare_fontconfig_none_removes_stale_generated_file`（`test_font_bundles.py:261`）先以 `wqy-microhei` 生成、再以 `none` 调用并断言已生成文件被删除，本轮复跑通过。
4. **f004 note.md 字面路径串已删除（属实）**。`note.md` 基线对照条已改写为「review 归档文件含开发者 home 路径串」，全文件无字面开发者 home 路径串。本轮按任务口径复跑 `tests/unit/test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths`：该测试仍失败，但违规清单恰为基线 2 条——均为 `docs/reviews/review_20261103_185924/` 下的两个存量文件，不再包含 t020 的 `note.md`，本 task 新增违规条目已消除。
5. **test 路 f001 / f002 修复（属实，同在本轮 delta 内）**。test_f001：`tests/unit/test_font_bundles.py` 新增 `_xml_dirs` / `_xml_includes` 解析助手（ElementTree 解析后取元素文本集合），`test_fontconfig_xml_includes_system_config_and_only_the_bundle_dir` 改为 `<dir>` 与 `<include>` 集合精确相等断言（祖先目录突变可被抓），`test_prepare_fontconfig_writes_bundle_file` 同步采用解析式集合断言。test_f002：`src/frontend/src/features/profiles/ProfileDetailPage.test.tsx` 的字体用例在提交断言后，把 mock query 数据改为 API 返回的新 `font_bundle`（`wqy-microhei`）并 `rerender`，断言保存后 select 回显仍为新值，补上了保存后回显一环。
6. **delta 清单完整、无清单外变更（属实）**。对 diff_anchor 的全量变更仍为 Round 1 报告所述 29 个文件；按文件修改时间与内容核对，Round 1 双路审阅（test 路 01:09:39、code 路 01:11:55，+08:00）之后发生内容变更的只有 4 个文件：`src/backend/cbrowser/runtime_agent/fontconfig.py`（code f001–f003）、`tests/unit/test_font_bundles.py`（code f001/f003 新测试 + test_f001 解析式断言）、`src/frontend/src/features/profiles/ProfileDetailPage.test.tsx`（test_f002 回显断言）、`docs/tasks/t020_profile_font_bundles/note.md`（code f002/f004 措辞与 Review 处置记录，属指纹排除的过程文件）。其余 25 个交付文件的修改时间均不晚于 01:05（+08:00），已包含在 Round 1 原指纹内；未跟踪文件只有本文件与 `review_test.md` 两份 review 报告（均为过程文件）。
7. **当前指纹独立重算一致**。以 `.repo_template/scripts` 的 `repo_task.monitoring.review_scope_fingerprint("30f5078d597d6f8c0b1e73986339e22ab7a1aafc", "docs/tasks/t020_profile_font_bundles")` 在当前工作区独立重算，结果为 `85728d7c53eb63a7`，与预期一致。本文件属指纹排除的过程文件，本次追加不改变该指纹（追加后已复算确认）。

### 结论

- 本轮新发现：0 条。code 路 4 条 minor（f001–f004）修复逐项回查源码 / 测试 / 记录均属实，test 路 2 条 minor 的修复亦已核实同在 delta 内，无清单外变更；Round 1 的 PASS 结论在修复后的交付内容上重签成立。
- 测试复跑（本 reviewer 按任务给定口径独立执行）：`tests/unit/test_font_bundles.py` 共 **22 passed**（Round 1 的 20 条 + f001 / f003 新增 2 条）；hygiene 专项如上，违规清单恰为基线 2 条存量项。
- AC 复验方式沿用 Round 1 记录不变（AC-002 / AC-006 为 `re_verified`，AC-001 / 003 / 004 / 005 为 `trust_prior`，真实环境执行债务仍由 p022 追踪）。

reviewed_scope: 85728d7c53eb63a7

verdict: PASS

## Round 3 — scope re-attestation（指纹重签核实，非业务重审）

- round：3（scope re-attestation）
- reviewed_at：2026-11-04T01:19:14+08:00
- 性质：Round 2 本路已 PASS 并签指纹 `85728d7c53eb63a7`（本文件 Round 2 节，reviewed_at `2026-11-04T01:15:02+08:00`）。其后 test 路 Round 2（`review_test.md` Round 2，`2026-11-04T01:16:51+08:00`，verdict FAIL）判定其 f002 修复空转，实施方仅改一个前端测试文件并做突变验证、生产代码零变化，指纹随之变更。本轮只核实「Round 2 之后 delta 仅该测试文件、生产文件零变更」与「当前指纹实算值」，不重做业务审阅。

### 核实结果

1. **delta 仅该测试文件、生产文件零变更（属实）**。以 `git diff 30f5078d597d6f8c0b1e73986339e22ab7a1aafc` 对照：全量变更仍为 29 个交付文件。按文件 mtime（Asia/Shanghai）核对 Round 2 本路时点（reviewed_at 01:15:02、本文件 mtime 01:15:17）之后：29 个交付文件中只有 `src/frontend/src/features/profiles/ProfileDetailPage.test.tsx` 的 mtime 为 `2026-11-04T01:17:44+08:00`，晚于该时点（亦晚于 test 路 Round 2 的 01:16:51）；其余 28 个交付文件 mtime 均不晚于 01:14:08——次晚者为 `docs/tasks/t020_profile_font_bundles/note.md` 01:14:08（指纹排除的过程文件，下同）、`tests/unit/test_font_bundles.py` 01:13:16、`src/backend/cbrowser/runtime_agent/fontconfig.py` 01:12:56，其余均 ≤01:05:26。故 Round 2 之后生产文件（`src/backend/**`、`src/frontend/**` 非测试文件、`config/**`、`schemas/**`、迁移等）零变更。未跟踪文件仍只有本文件与 `review_test.md` 两份 review 报告（过程文件）。
2. **该测试文件的变更内容与任务描述一致**。与 Round 2 时点副本（`.scratch/mutation_r2/frontend/src/features/profiles/ProfileDetailPage.test.tsx`）逐行 diff：字体用例的 `const tree = (<MemoryRouter>…)` 改为工厂函数 `const pageTree = () => (<MemoryRouter>…)` 并加注「Fresh JSX per render」说明，初次渲染改为 `render(pageTree())`、保存后回显改为 `view.rerender(pageTree())`，即每次现构造新 JSX，不再复用同一 element 对象；除此之外该文件无其他改动。内容对照旁证：`tests/unit/test_font_bundles.py`、`src/frontend/src/features/profiles/ProfileDetailPage.tsx`、`note.md` 与 Round 2 时点副本（`.scratch/mutation_r2/repo/` 内对应文件）逐字相同（该副本内 `fontconfig.py` 的差异为 test 路祖先目录突变所加行、非交付内容，不计）。
3. **当前指纹独立实算一致**。以 `PYTHONPATH=.repo_template/scripts` 调用 `repo_task.monitoring.review_scope_fingerprint("30f5078d597d6f8c0b1e73986339e22ab7a1aafc", "docs/tasks/t020_profile_font_bundles")` 在当前工作区独立实算，结果为 `d2f32fdbdfbdcb06`，与预期逐字一致；Round 2 指纹 `85728d7c53eb63a7` 已因上述单一测试文件变更而过期。本文件属指纹排除的过程文件，本次追加不改变该指纹（追加后已复算确认，见回报）。

### 结论

- 本轮新发现：0 条。Round 2 之后 delta 仅 `ProfileDetailPage.test.tsx` 一个测试文件、生产代码零变化，当前指纹实算为 `d2f32fdbdfbdcb06`；Round 1 / Round 2 的 PASS 结论在当前交付内容上重签成立。AC 复验方式沿用 Round 1 / Round 2 记录不变。

reviewed_scope: d2f32fdbdfbdcb06

verdict: PASS

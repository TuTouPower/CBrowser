# Task review t020（reviewer_focus: 测试）

- task：`t020_profile_font_bundles`
- spec：`docs/tasks/t020_profile_font_bundles/task.md`
- diff_anchor：`30f5078d597d6f8c0b1e73986339e22ab7a1aafc`
- target：`git -C '<home>/workspace/CBrowser_t020' diff 30f5078d597d6f8c0b1e73986339e22ab7a1aafc`
- round：1
- reviewed_at：2026-11-04T01:09:39+08:00

reviewed_scope: 5f0d2fda8efbde6b

## Findings

### t020_test_f001 - fontconfig XML 测试为子串断言，追加祖先目录（递归含两包）的回归不会变红

- 严重度：minor
- 锚点：AC-003/AC-004 的机制条款（「其余档位只让对应字体目录参与扫描」）在 unit 层的唯一防线
- 位置：`tests/unit/test_font_bundles.py` `test_fontconfig_xml_includes_system_config_and_only_the_bundle_dir`、`test_prepare_fontconfig_writes_bundle_file`
- 问题：两条测试只断言本包 `<dir>` 存在、且另一包名字符串不出现在 XML 文本中。审查侧在 `.scratch` 副本上做突变实测：给 `build_fontconfig_xml` 生成的 XML 追加一行 `<dir>/opt/cbrowser-fonts</dir>`（fontconfig 的 `<dir>` 为递归扫描，该目录含两个 bundle 子目录，等于两包同时可见、隔离失效），`-k fontconfig` 的 6 条测试**全部通过**——祖先目录字符串不含任一包名，子串断言抓不到。对照之下其余突变均被抓：换包目录（3 条变红）、`FONT_BUNDLE_DIRS` 对调（1 条变红）、runner 删除 `env.pop("FONTCONFIG_FILE", None)`（1 条变红）、`ProfileConfig` 默认值改 `wqy-microhei`（3 条变红），说明测试整体可证伪、仅此一处盲区。当前生产代码生成的 XML 正确（审查侧逐行核对 `fontconfig.py` 且突变 3 反证断言对包名敏感），故本条不影响当前交付正确性；但该回归方向恰是 AC-003/004 隔离语义的核心，且能兜底的 e2e 渲染断言从未执行（见结论 trust_prior），unit 层不应留此盲区。
- 建议：把 XML 断言改为解析后断言 `<dir>` 元素集合恰等于 `[FONT_BUNDLE_ROOT/<bundle>]`（精确集合相等），`test_prepare_fontconfig_writes_bundle_file` 同步采用。

### t020_test_f002 - AC-006「保存后回显与 API 返回一致」的前端一环未被断言：mutation 被 mock 且不校验保存后重渲染

- 严重度：minor
- 锚点：AC-006 后半句
- 位置：`src/frontend/src/features/profiles/ProfileDetailPage.test.tsx` 新增用例、`src/frontend/src/features/profiles/ProfileNewPage.test.tsx`
- 问题：两个前端测试把 `useProfilesQuery` 的 mutation hook 整体 mock（Detail 的 `updateMutateAsync` 返回 `{}`、New 的 `createMutateAsync` 返回 `{id}`），断言止于「初始回显 = query 数据中的 `font_bundle`」「提交 payload 含所选 bundle」。保存成功后页面以 API 返回/刷新后的数据重新回显这一环（mutation 结果处理与 query 失效刷新，在本 diff 未触及的 hook 胶水层）没有任何断言；若该胶水对 `font_bundle` 失效，前端测试全绿而 AC-006 后半句实际不成立。API 侧的回显已由 integration 测试独立证实（PATCH 后 GET 一致），故证据链只缺前端保存后一环，定 minor。
- 建议：Detail 测试让 mock mutation 返回带新 `font_bundle` 的对象（或让 mock query 在 mutation 后返回新值），补一条保存后 select 值等于新 bundle 的断言；或在既有前端 e2e 中补字体档位保存-回显场景。

## 结论

- 改测方向复核：无迁就实现的改测。本 diff 仅改动一个既有测试文件 `ProfileDetailPage.test.tsx`：把 `useUpdateProfileMutation` 的 mock 由匿名 `vi.fn()` 改为 hoisted 的 `updateMutateAsync` 以便断言调用，原有用例原样保留且复跑通过；其余测试（unit 20 条、integration 4 条、e2e 5 条、ProfileNewPage 1 条）均为新增。无删/反转/注释断言，无预期改写为实现输出。
- 危险模式扫描：逐条扫过，未命中。无恒真断言（unit 断言具体默认值、版本号、XML 内容、env 键存在性；integration 断言真实 HTTP 状态码与响应体；前端断言 select 值、options 全集与 mutation payload）；无 `.skip`/`.only`/`xfail`（e2e 文件中唯一的 `pytest.skip` 是仓库既有前置条件模式：环境缺失时 skip、`CBROWSER_E2E_REQUIRED=1` 时 fail，与 t019 同机制，非掩盖）；mock 边界合理——后端 unit/integration 零 mock（直调生产 `ProfileConfig`/`ProfileRepository`/真实 Alembic 迁移/真实 `BrowserRunner._browser_environment`，integration 走真实 `TestClient` 全栈），前端仅 mock query hook 层、渲染真实页面组件（与既有前端测试同模式，其保存后胶水缺口见 f002）；迁移测试用真实旧版 schema（upgrade 到 `0006_snapshot_modes` 后插入存量行再 upgrade head），非伪造数据结构。
- 突变抽查（`.scratch/mutation/repo` 副本上进行，未触交付文件）：共 5 项——`FONT_BUNDLE_DIRS` 对调、生成 XML 换包、runner 不清除继承的 `FONTCONFIG_FILE`、`ProfileConfig` 默认值改非 `none` 四项均被对应测试抓红（分别 1/3/1/3 条失败）；仅「XML 追加祖先目录」一项漏检，见 f001。
- 黑盒跳过披露核查：属实。本机实测 `docker: command not found`、无 `/Applications`（Linux 云 VM），与 note 记录一致；e2e 文件按门禁口径以 `PYTHONPATH=src/backend:tests/fixtures` collect 正常（5 条：image_layout、render 三档、isolation），未执行。note 明示 AC-001 镜像 fc 条款与 AC-003/004/005 渲染条款为 trust_prior、按用户 2026-11-03 指令跳过按 pass 计，口径与 t019 Round 3 的所有者裁量一致。
- 替代验证独立复现：实施侧的宿主 fontconfig 替代验证经审查侧用 `.scratch/fontpkgs` 实物复跑成立——`FONTCONFIG_FILE=micro.conf` 时 `fc-list` 只列 WenQuanYi Micro Hei、`zen.conf` 时只列 WenQuanYi Zen Hei、未设置时 WenQuanYi 计数 0；两个 `.ttc` 体积 5,177,387 / 16,791,251 字节与契约声明的 5.2MB / 16.8MB 一致，提取布局为 `opt/cbrowser-fonts/{wqy-microhei,wqy-zenhei}`。这为机制层提供了真实（非 mock）旁证，但不等于镜像内 `fc-match` 与 Chrome 渲染证据。
- p022 追踪充分性：`docs/pending/todo/p022_t020_e2e_real_env_execution_debt.md` 内容完整——明确要求在 OrbStack Docker + 当前源构建 Browser 镜像 + 引擎缓存环境运行 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`、至少单独执行 `tests/e2e/test_browser_font_bundles_e2e.py` 全部用例、保存 evidence（镜像内 fc 输出、三档 canvas 度量/CDP 平台字体族、双 Profile 隔离结果）、执行后回填并归档，处理状态「未开」。e2e 用例本身经审查可信：真实 canvas `measureText` 中文/私用区度量、CDP `DOM.getPlatformFontsForNode` 实际字体族、Chrome 进程 `/proc/<pid>/environ` 的 `FONTCONFIG_FILE` 三重断言，非虚构信号。p022 足以承载 AC-001 镜像条款与 AC-003/004/005 渲染条款的 trust_prior 债务。
- AC 复验方式：
  - AC-001：`trust_prior`。静态半已独立复验：Dockerfile unit 测试复跑通过（builder 阶段装包、最终阶段只 COPY `/opt/cbrowser-fonts` 且不含 `fonts-wqy`/`/usr/share/fonts`）、布局常量在默认扫描路径之外、替代验证复现默认不可见。但「构建后镜像内 `fc-list`/`fc-match` 不命中」从未在真实镜像执行，待 p022。
  - AC-002：`re_verified`。独立复跑 unit（默认值/三档接受/非法与 null 拒绝、repository 往返、存量迁移默认 `none`、迁移后 repository 读取）与 integration（创建默认、两档创建+读回、非法 422、更新升版+null/非法 422+读回一致）全过；突变实测默认值与校验可证伪。
  - AC-003：`trust_prior`。机制半已复验：`none` 不生成文件、runner 清除继承的 `FONTCONFIG_FILE`（突变可抓）、宿主 fontconfig 下默认无 WenQuanYi 已复现；但「Chrome 渲染中文与私用区等宽」依赖未执行的 e2e render:none，待 p022。
  - AC-004：`trust_prior`。机制半已复验：XML 只含本包目录（换包突变可抓）、两份生成配置在宿主 fontconfig 下各只暴露本包字体族已复现；但「Chrome 实际使用对应文泉驿字体渲染」依赖未执行的 e2e render 两档，待 p022。
  - AC-005：`trust_prior`。配置版本半已复验：unit 断言改 `font_bundle` 产生新版本（v1→v2、快照 JSON 两版值正确）且旁观 Profile 不受影响，integration 复证 API 层升版；同时运行的字体可见集合互不影响依赖未执行的 e2e isolation，待 p022。
  - AC-006：`re_verified`。独立复跑前端测试 3 条全过（Detail 回显 `wqy-zenhei`、三档 options 全集、改选后提交 payload；New 默认 `none`、选档后提交 payload），integration 复证 API 返回与保存值一致；保存后前端重渲染一环的胶水缺口见 f002（minor，不推翻本条主体证据）。
  - coverage = 2 / 6
  - 建议合并前人工抽查 trust_prior 项（AC-001 镜像条款、AC-003、AC-004、AC-005 隔离条款），并在真实环境优先执行 p022 留存 evidence 后再对外宣称该四项已实测。
- reviewer 独立复跑结果：后端新增测试按任务给定命令复跑，`tests/unit/test_font_bundles.py`（20 条）+ `tests/integration/test_profile_font_bundle_api.py`（4 条）共 **24 passed**；全量 `tests/unit` 为 **573 passed / 2 failed**，两条失败即 note 点名的存量基线（`test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths`、`test_runtime_persistence_guards.py::test_terminal_storage_failure_propagates_instead_of_reporting_saved`），审查侧另在干净主干 `~/workspace/CBrowser`（c7ec89b）单独复跑该两条、同为 2 failed，证实零新增失败、note 基线声明属实。前端按给定命令复跑 **3 passed**（2 文件）。e2e collect-only 5 条正常、未执行（环境不具备，与 note 一致）。note 中其余门禁声明（模板契约、前端全量、build 等）不在本 reviewer 复跑范围内，未独立核对。
- 本轮新发现：2 条（minor 2；critical/important 0）
- 未进表的提示：e2e isolation 场景在单个容器内以双 runner（双 display、独立 run_dir 与 per-process `FONTCONFIG_FILE`）验证隔离，与 AC-005 字面「各自 Browser 容器」拓扑不同；生产拓扑（每 Profile 独立容器）隔离强度只增不减，且单容器双进程恰是对 env 级隔离机制的更严苛测法，不构成证据缺口，仅记录拓扑差异。runner 的 `start()` 内调用 `prepare_profile_fontconfig(run_dir, cfg.font_bundle)` 的胶水行无 unit 直接断言，由 e2e render 场景覆盖（trust_prior 同批），机制两端均已 unit 复验，不单独成条。
- 总体判断：可自动复验的证据链（AC-002、AC-006 及各 trust_prior 条款的机制半）扎实、与 note 声明逐项一致，突变抽查整体可证伪；黑盒条款的跳过披露属实、按所有者既定口径计 pass 且债务已由 p022 完整追踪，无未解决的 critical/important，给予 PASS。本 PASS 不是黑盒已执行的证据声明；AC-001 镜像条款与 AC-003/AC-004/AC-005 渲染条款的 trust_prior 状态与 p022 未开状态须原样保留至真实环境执行回填。
- 系统性 follow-up：p022（已立项，本轮不重复立项）。

verdict: PASS

## Round 2 (2026-11-04T01:16:51+08:00)

reviewed_scope: 85728d7c53eb63a7

### 指纹核对

- 以 `PYTHONPATH=.repo_template/scripts` 调用 `repo_task.monitoring.review_scope_fingerprint("30f5078d597d6f8c0b1e73986339e22ab7a1aafc", "docs/tasks/t020_profile_font_bundles")` 在本 worktree 独立实算，结果 `85728d7c53eb63a7`，与本轮给定预期指纹逐字一致；Round 1 指纹 `5f0d2fda8efbde6b` 已过期。本轮全部突变/探针均在 `.scratch/mutation_r2/` 副本上进行，交付文件复核哈希未变（`fontconfig.py`、`test_font_bundles.py`、`ProfileDetailPage.tsx`、`ProfileDetailPage.test.tsx`），副本操作后指纹重算仍为 `85728d7c53eb63a7`（`.scratch` 本就在指纹排除内）。

### 前轮 finding 复核

- t020_test_f001（minor）：**已消除**。以当前交付核实：`tests/unit/test_font_bundles.py` 新增 `_xml_dirs`/`_xml_includes` 两个 XML 解析 helper，`test_fontconfig_xml_includes_system_config_and_only_the_bundle_dir` 改为解析后断言 `<dir>` 集合精确等于 `{FONT_BUNDLE_ROOT/<bundle>}`、`<include>` 集合精确等于 `{/etc/fonts/fonts.conf}`，`test_prepare_fontconfig_writes_bundle_file` 同步采用 `<dir>` 精确集合断言，无子串断言残留。审查侧重做 Round 1 的祖先目录突变抽查：在 `.scratch/mutation_r2/repo` 副本上改 `build_fontconfig_xml` 实现副本、追加一行 `<dir>/opt/cbrowser-fonts</dir>`（即 `bundle_root` 本身、递归含两包），复跑 `-k fontconfig` 共选中 8 条、**2 条变红**——正是上述两条精确集合断言，失败信息均为集合多出 `'/opt/cbrowser-fonts'`；Round 1 时同一突变下 6 条全过。盲区已闭合。
- t020_test_f002（minor）：**未消除（形式已补、断言实际空转）**。新增段落表面齐备：submit 后 `await` 一个 tick、把 `profileState.data.font_bundle` 改为 API 返回值 `wqy-microhei`、`view.rerender(tree)`、断言 select 仍为 `wqy-microhei`，前端复跑亦全绿。但审查侧在 `.scratch/mutation_r2/frontend` 副本上做三组探针，证明该 rerender 没有真正发生、断言对回显值不敏感：
  1. 只改探针数据、其余与交付测试逐字相同：把保存后回显数据改为 `font_bundle: "none"`（与期望值不同），交付测试**仍然全绿**——最终断言照样通过。
  2. 在副本组件的 fontBundle 同步 effect 上插桩：保存后 `rerender` 前后 effect **零执行**（全程仅初始挂载的同步日志）。根因是测试把同一 `tree` element 对象先 `render(tree)` 再 `rerender(tree)`，React 对引用相同的 element 直接 bailout，组件不重渲染、mock query 不被重读、effect 不运行；对照同文件第一条用例的 rerender 是现构造一份新 JSX、effect 正常执行。
  3. 对照组（副本上改用现构造的新 JSX tree rerender，其余不变）：回显 `none` 时 effect 实际执行（`fontBundle <- none`，且此时 dirty 已被 submit 清除）、最终断言变红（`expected 'none' to be 'wqy-microhei'`）；回显 `wqy-microhei` 时 effect 同步为该值、测试全绿。**即生产机制本身（submit 清 dirty + effect 按刷新后 profile 同步 select）经探针证实工作正常，缺的只是交付测试的 rerender 构造方式**——把 `view.rerender(tree)` 换成现构造的新 JSX（同文件第一条用例已有此写法）即可让该断言真实生效。按现状，f002 揭示的「保存后回显一环无有效断言」缺口与 Round 1 实质相同，不予消除。

### code 路 4 条 minor 顺带复核（未削弱测试）

- t020_code_f001（未知 bundle 回退）：已落实且有新增测试钉住——`fontconfig.py` 已把 `build_fontconfig_xml` 调用移入 `try`、捕获 `(OSError, ValueError)` 记 error 日志返回 `None`；新增 `test_prepare_fontconfig_unknown_bundle_falls_back_to_none`（断言返回 `None` 且目录为空）复跑通过。
- t020_code_f002（原子写）：已落实——实现改为 tmp 文件写入 + `flush`/`fsync` + `chmod 0o600` + `os.replace` + 目录 `fsync`，与 note.md 措辞一致。
- t020_code_f003（`none` 清理残留）：已落实且有新增测试钉住——`none` 分支先 `target.unlink(missing_ok=True)`；新增 `test_prepare_fontconfig_none_removes_stale_generated_file`（先生成 micro、再切 `none`、断言返回 `None` 且旧文件消失）复跑通过。
- t020_code_f004（note 字面 home 路径）：已落实——`note.md` 全文已无 `/home/` 字面量（审查侧 grep 复核），基线对照条已改写为不含字面路径的表述。
- 测试强度总评：本轮测试改动只有收紧与新增（XML 精确集合相等、新增 2 条 unit、前端新增保存后段落），无删/反转/放宽断言；code 路修复未以改测迁就实现。

### 本轮复跑

- 后端：按任务给定命令复跑 `tests/unit/test_font_bundles.py` + `tests/integration/test_profile_font_bundle_api.py` 共 **26 passed**（unit 22 条，较 Round 1 的 20 条新增即上述 code f001/f003 两条；integration 4 条不变），较 Round 1 的 24 条为 +2、无减少。
- 前端：按任务给定命令复跑 `ProfileDetailPage.test.tsx` + `ProfileNewPage.test.tsx` 共 **3 passed**（2 文件），与 Round 1 条数一致；新增保存后段落随 Detail 文件执行并通过（其有效性问题见 f002 复核，与通过/失败无关）。
- 突变抽查：f001 祖先目录突变 1 项，已由漏检转为抓红（详见上）；f002 回显探针 3 组（同上）。
- 本轮新发现：0 条（f002 为前轮 finding 未消除，非新条目）。改测方向复核：无迁就实现的改测。

### AC 复验（Round 2 更新）

- AC-002：`re_verified`（维持）。26 条后端复跑全过，含新增未知 bundle 回退与 `none` 残留清理两条。
- AC-006：主体维持 `re_verified`（integration 的 PATCH 后 GET 回显一致 + 前端初始回显/提交 payload 断言 + 本轮探针证实生产组件的保存后同步机制实际工作）；但其前端保存后一环的**测试证据**仍缺位（f002 未消除），该缺口的定级与 Round 1 相同（minor：API 侧回显已独立证实、生产机制已由本轮探针证实）。
- 其余 AC（001/003/004/005）的 trust_prior 状态与 p022 未开状态较 Round 1 无变化，本轮不重开。
- coverage = 2 / 6（维持 Round 1 口径）

### 结论

- 总体判断：f001 已真实消除、code 路 4 条 minor 修复属实且测试只收紧不削弱、指纹与最终交付绑定成立；唯 f002 的修复经突变/插桩探针证实未真正生效——保存后回显断言因 `rerender` 复用同一 element 对象而空转，回显值改错仍全绿。note.md 处置表将 t020_test_f002 记为「已修」，与实测不符，本轮不予在最终指纹上重签 PASS。转 PASS 只缺一步：把该用例的 `view.rerender(tree)` 改为现构造的新 JSX tree 后复跑（审查侧已在副本上证明此改法下断言对错误回显变红、对正确回显全绿），届时 f002 即可消除、无需再改任何生产代码。
- 系统性 follow-up：p022（已立项，本轮不重复立项）。

verdict: FAIL

## Round 3 (2026-11-04T01:20:02+08:00)

reviewed_scope: d2f32fdbdfbdcb06

### 本轮范围

- scope re-attestation：只核实 Round 2 唯一阻断项 t020_test_f002 的修复是否真实生效、Round 2 之后 delta 是否仅限该测试文件（+ note.md 过程文件）、指纹是否与预期一致。不重开其余 finding 与 AC（001/003/004/005 的 trust_prior 与 p022 未开状态较 Round 2 无变化）。

### 指纹核对

- 以 `PYTHONPATH=.repo_template/scripts` 调用 `repo_task.monitoring.review_scope_fingerprint("30f5078d597d6f8c0b1e73986339e22ab7a1aafc", "docs/tasks/t020_profile_font_bundles")` 独立实算，结果 `d2f32fdbdfbdcb06`，与本轮给定预期指纹逐字一致；本轮探针与指纹重构操作完成后重算仍为 `d2f32fdbdfbdcb06`，交付测试文件 sha256 恢复为 `e9577433cd17d02c5412d372ae6f978b53600b9da659fe0c7f6df0b9407d1c3c`（与实施侧 `.scratch/f002_backup.tsx` 逐字一致）。

### f002 修复核实（真实生效）

- 交付文件现状核实：`ProfileDetailPage.test.tsx` 的字体档位用例已改为 `const pageTree = () => (...)` 每次现构造新 JSX，首渲染 `render(pageTree())`、保存后 `view.rerender(pageTree())`，并附注释说明复用同一 element 会使 React bailout、令回显断言空转——正是 Round 2 给出的转 PASS 条件写法。
- 前端复跑：按给定命令 `NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend -- src/features/profiles/ProfileDetailPage.test.tsx src/features/profiles/ProfileNewPage.test.tsx` 复跑，**3 passed**（2 文件；Detail 2 条 + New 1 条），探针还原后再次复跑仍 3 passed。
- 独立探针（重做 Round 2 探针 1）：在交付文件上把保存后回显数据由 `font_bundle: "wqy-microhei"` 改为 `"none"`（其余逐字不动），单独复跑 Detail 文件——该用例**变红**，失败为最终回显断言 `AssertionError: expected 'none' to be 'wqy-microhei'`（文件第 106 行），同文件另一用例仍通过。与 Round 2 时同一探针下全绿形成对照：rerender 现真实发生、保存后回显断言对回显值敏感，空转已消除。探针后已还原交付文件并核对 sha256 与指纹（见上），交付文件无残留改动。实施侧自述的突变验证（回显改 none 变红、恢复全绿）与本轮独立重做结果一致。

### Round 2 之后 delta 核对（仅限该测试文件 + 过程文件）

- 与 Round 2 审查侧留存副本 `.scratch/mutation_r2/repo`（Round 2 时点交付快照）逐文件比对 anchor diff 清单内全部文件：仅 `ProfileDetailPage.test.tsx` 内容不同，差异恰为 3 处、全部落在 f002 修复本身——新增两行 bailout 注释、`const tree` 改为 `const pageTree = () =>`、`render(tree)`/`rerender(tree)` 改为 `render(pageTree())`/`rerender(pageTree())`，无其他行变动。（副本中 `fontconfig.py` 与交付的差异是 Round 2 审查侧在副本上做的祖先目录突变行本身，非交付 delta。）
- 指纹重构反证：将交付测试文件临时换回 Round 2 副本版本后实算指纹，恰得 Round 2 指纹 `85728d7c53eb63a7`；换回现版本后回到 `d2f32fdbdfbdcb06`。即指纹 delta 完全由该测试文件一处变更解释，清单外无任何非过程文件变更。`note.md` 为指纹排除的过程文件，其变动不影响上述结论，且本轮比对中其内容与 Round 2 副本一致。

### 结论

- t020_test_f002：**已消除**。修复写法与 Round 2 转 PASS 条件一致，且经独立探针证实断言真实生效（错误回显变红、正确回显全绿）；生产代码未动、未改。
- Round 1/2 其余结论维持：f001 已消除、code 路 4 条 minor 修复属实、AC-002/AC-006 为 re_verified、其余 AC 的 trust_prior 状态与 p022 未开状态不变，coverage 口径不变（2 / 6）。
- 本轮新发现：0 条。

verdict: PASS

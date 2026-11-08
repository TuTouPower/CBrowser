---
tid: "t038"
slug: "proxy_library_ui"
title: "代理库界面"
status: "done"
branch: "t038_proxy_library_ui"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "1ca4cb4fd4212ddfb7ad4b6c9bcfcbcc9b1df65d"
depends_on: "t037,t045"
conflicts_with: ""
note: "来源 plan_20261105_ui_redesign WP10"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 实施与验证（2026-11-07）

- 基础层：`features/proxies/parseProxyUrl.ts` 纯函数（判别联合，scheme 白名单 / IPv6 方括号 / 百分号编码账密 / port 1..65535，失败不含部分字段）+ 33 条表驱动测试；`shared/api/types.ts` 补 `ProxyCreateRequest` / `ProxyUpdateRequest` 生成类型别名；`shared/api/client.ts` 的 `proxies` 补 `create`/`update`/`remove`（照 `groups` 同构、写操作带 `Idempotency-Key`）；`useProfilesQuery.ts` 就地补 3 个 mutation（`useActionKeyMutation` 独立幂等键、失效 `proxyKeys.lists()` 与 `profileKeys.lists()`）；`i18n.tsx` en/zh 同步补 48 个 `proxy*` 键。
- 页面层：`features/proxies/ProxyListPage.tsx` / `ProxyListToolbar.tsx` / `ProxyTable.tsx` / `ProxyFormDialog.tsx` 替换 t036 的 `/proxies` 占位页（`app/router.tsx` 与 `router.test.tsx` 同步）。8 个 AC：列 + 搜索/协议组合（AC-001）、字段校验字段旁错误（AC-002）、密码三态（留空省略键 / `null` 清除 / 字符串）且不进入 DOM/query cache/URL（AC-003）、URL 粘贴含 IPv6 与百分号编码且非法保持已填（AC-004）、`used_by_count>0` 禁用删除 + 409 从 `ApiError.detail` 读引用数（AC-005）、使用环境数 `<Link to={"/?proxy="+id}>`（AC-006，环境列表 `useEnvironmentFilters` 已支持）、带认证 SOCKS5（AC-007）、真实栈 E2E（AC-008）。
- **AC-007 裁决依据**：task.md 措辞「引擎不支持时阻止提交」沿用 plan 旧假设；以 `docs/findings/d031_authenticated_socks5_supported.md`、spike s013 报告、ADR 023（`docs/blueprint/decisions.md:280`）为准——CloakBrowser 0.6.4 / Chromium 146 实测**支持**带认证 SOCKS5，且 `src/backend` 无任何 socks5 拒绝分支、API 永不返回该 422。实现为**直接支持**：表单默认允许 `socks5` + 用户名/密码提交，无阻止、无降级、无「引擎不支持」提示；所有后端错误统一走 `describeError()` 结构化展示。按监督纠正删除推测性降级路径（`isSocks5Unsupported` / `proxySocks5Unsupported` 键 / 2 条专属测试），详见测试处置清单与 `docs/specs/proxy_management.md` 第 5 节。
- 定向验证：`npm test --prefix src/frontend` 54 文件 356 测试全过（含 `test:types` 严格类型）、`design:lint` 0 error / 0 warning、`design:check` up to date；parseProxyUrl 33、ProxyFormDialog 10、ProxyListPage + router 17；AC-008 E2E collect-only 1 test、py_compile OK。
- finalization：`docs/blueprint/frontend.md` 第 8 节（并去掉第 1 / 7 节的占位表述）、新建 `docs/specs/proxy_management.md`、`docs/specs_index.md` 登记 `proxy_management|t038|2026-11-07`。
- 第 1 轮完整门禁（`.scratch/t038_evidence_20261107_111126`）：unit `exit 1`（`test_repo_hygiene` 命中 base 分支 t045 Round 2 review 报告的 7 处 home 绝对路径，属已上报的模板缺陷 #89 复现，非 t038 实现引入）；E2E 102 用例 FAIL=2 —— `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（t032 已登记基线首帧 3.346s）、`test_runtime_coordinator_docker_e2e`（`docker.errors.NotFound` 容器消失，**p051 已知缺陷复现，见 p051**：本轮首次带删除诊断日志 100 条覆盖整个 E2E 期、按容器 ID 与 `t007-be-coord` prefix 检索均无删除记录，排除 `cleanup_prefixed_resources`，排查范围已缩小到用例自建 finally / Supervisor reconcile / daemon `--rm`；t038 改动不创建该容器，排除本 task 引入）。**AC-008 `test_ac008_proxy_library_outbound_via_ui` 真实栈 PASS**（UI 新建代理 → 环境引用该代理 → 启动 → 浏览器出站经本地记录代理 `PROXY_GET`）。`gate cleanup: removed 1 containers, 1 networks`（t045 启动清理在真实残留上生效，生产容器未碰）。
- 处置：t045 两份 review 报告 7 处 home 路径做最小去路径修复（去掉 `git -C '<abs>'` 绝对路径参数、路径改 `t045 worktree` 占位，**不动任何审查结论**），与 t045 处理 t037 报告方式一致；`test_repo_hygiene` 定向 `8 passed`。该 2 个文件改动属跨 task 格式修复，随 t038 实现 commit 交付并在收尾报告披露。
- 待办（已完成）：处置后重跑完整门禁（冻结代码）→ 打勾 AC → 重新渲染 review prompts → full 两路复审 → `check_review_status.py` PASS → finish。
- 第 2 轮完整门禁（`.scratch/t038_evidence_20261107_113648`，冻结代码、finish 依据）：9 个非 E2E suite 全 exit 0、unit `exit 0`（home 路径修复生效）；E2E 102 用例 FAIL=2 / ERROR=0 / SKIP=2 —— 仅 `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（t032 已登记基线首帧 3.352s）与 `test_runtime_coordinator_docker_e2e`（`docker.errors.NotFound` 容器 ID `a1da37ebd71c...`，**p051 已知缺陷复现**）；AC-008 真实栈 PASS。失败集合符合监督要求（t019 + 有 p051 证据记录的 1 项）。第 1 轮删除诊断日志 100 条无该容器删除记录 → 排除 `cleanup_prefixed_resources`；p051 已补第 5 次复现与缩小后的排查范围（用例自建 finally / Supervisor reconcile / daemon `--rm`），并确认 t038 改动不创建该容器、排除本 task 引入。
- Round 1 复审（code / test 两轴均 PASS、8/8 TICK-VALID）出 4 条 minor：`t038_code_f001`（任意 422 误标 SOCKS5 不支持）、`t038_code_f002`（缺 username/region_label 255 上限校验）按「拒绝妥协」从根因修复并补 2 条回归测试；`t038_code_f003` / `t038_test_f001`（task.md AC-007 字面过时）按 d031 / ADR 023 裁决撤回并写明实质理由。修复未改 `run_gates.sh` 与 E2E 拓扑代码，按定向验证（`npm test` 358 全过、`tsc`、`design:lint`/`design:check`），第 2 轮 E2E 证据仍有效；处置表 4 条已登记，重新渲染后做 Round 2 复审。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-07T12:20:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t038_code_f001|minor|已修|**删除推测性降级路径**：`isSocks5Unsupported` 函数、catch 中的降级分支、`proxySocks5Unsupported` 的 en/zh 文案键与 2 条专属测试全部删除；后端 `src/backend` 无 socks5 拒绝分支、API 永不返回该 422（d031 实测 / ADR 023），任何 422 与其它错误统一走 `describeError()` 结构化展示。按「架构至上、不留补丁」处理，不在死代码上打文本匹配补丁|src/frontend/src/features/proxies/ProxyFormDialog.tsx / ProxyFormDialog.test.tsx / src/frontend/src/i18n.tsx|
|t038_code_f002|minor|已修|前端缺 `username`/`region_label` ≤255 校验（后端 `models.py` 有）；补校验 + `FieldKey` + 字段旁错误 + 回归测试|src/frontend/src/features/proxies/ProxyFormDialog.tsx / ProxyFormDialog.test.tsx|
|t038_code_f003|minor|撤回|task.md AC-007 字面沿用 plan 旧假设「引擎不支持时阻止提交」；`d031` 实测 Chromium 146 支持带认证 SOCKS5、ADR 023 裁决、且 `src/backend` 无任何 socks5 拒绝分支（API 永不返回该 422），条件句前提不成立，实现「直接支持、无降级」才与 t035 结论一致。改 task.md 契约区措辞会影响 AC 编号永久归属与 review 基准，裁决依据与「无拒绝分支」事实已写入 `proxy_management.md` 第 5 节与实施笔记|docs/specs/proxy_management.md|
|t038_test_f001|minor|撤回|同上（`d031` 实测 + 后端无拒绝分支）：测试覆盖 AC-007 正向行为「默认允许提交」即完整，无需为不存在的 422 补测；spec 字面过时非测试缺陷，推测性降级测试按测试处置清单删除|docs/specs/proxy_management.md|

code / test 两轴 Round 1 verdict 均 PASS、8/8 TICK-VALID。按监督纠正：f001 由「文本匹配打补丁」改为**删除推测性降级路径**，f002 保留真实校验修复，f003 / test_f001 撤回理由补充 `d031` 结论与「后端无拒绝分支」事实。按监督要求以最终代码重跑完整门禁（E2E 必跑），再重新渲染并做 Round 2 复审。

### 测试处置清单

- `ProxyFormDialog.test.tsx::shows the socks5-unsupported banner on a 422 and keeps the dialog open`：**整体删除**。专测「后端 422 + socks5 不支持」降级提示；契约前提已被 `d031`（Chromium 146 实测支持带认证 SOCKS5）与 ADR 023 推翻，且 `src/backend` 无任何 socks5 拒绝分支、API 永不返回此 422，属推测性代码专属测试，随降级路径一并删除。
- `ProxyFormDialog.test.tsx::does not mislabel an unrelated 422 as socks5-unsupported`：**整体删除**。仅为上一轮给推测性 `isSocks5Unsupported` 打补丁时新增的误标回归；降级路径整体删除后无被测对象，按「不为死代码补测试」删除。
- 保留 `submits authenticated socks5 without any frontend blocking`（AC-007 正向行为）、`rejects username and region_label longer than 255 characters`（f002 真实校验缺陷）、409 object detail 用例（结构化错误展示仍走 `describeError`）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：`npm test --prefix src/frontend` 54 文件 356 测试全过（含 `test:types` 严格类型）；`design:lint` 0 error / 0 warning、`design:check` up to date；parseProxyUrl 33、ProxyFormDialog 10、ProxyListPage + router 17；AC-008 E2E collect-only + py_compile OK。完整门禁 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 共三轮（第 1 / 2 轮诊断，第 3 轮最终代码为 finish 依据）；第 3 轮 unit 曾 `exit 1`（仅 `test_repo_hygiene` 命中 review 报告 / progress 的 home 绝对路径，属 #89 复现），修复后定向重跑 contract（`257 passed, 1 skipped`）与 unit（`1165 passed`，`test_repo_hygiene` `8 passed`）确认通过。
- 黑盒：**第 3 轮最终代码完整门禁** E2E 102 用例 FAIL=1 / ERROR=0 / SKIP=2 —— 仅 `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（t032 已登记基线首帧 3.363s），`test_runtime_coordinator_docker_e2e` 本轮未复现；符合监督要求的失败集合（只允许 t019 + 有 p051 证据的 runtime_coordinator）。**AC-008 `test_ac008_proxy_library_outbound_via_ui` 真实栈 PASS**（UI 新建代理 → 环境引用 → 启动 → 浏览器出站经本地记录代理 `PROXY_GET`）。integration / 前端 / design / requirements_check / image_packages 共 8 个非 E2E suite 全 exit 0。
- .md-only 收尾修复（同 t041 先例）：第 3 轮 unit 失败的唯一根因是 `docs/tasks/t038_proxy_library_ui/review_code.md` / `review_test.md`（Round 1 reviewer 写入）与 `progress.md` 共 5 处 home 绝对路径；修复**只改这 3 个 .md**（去掉 `git -C '<abs>'` 参数、路径改 `t038 worktree` 占位、描述改「home 绝对路径」），产品代码与测试代码**零变化**，且 review 报告 / progress 均属 review 指纹排除的流程文件。按监督要求不重跑完整 E2E 门禁，只定向重跑 contract + unit 确认 `test_repo_hygiene` 通过；finish 依据 = 第 3 轮完整门禁（E2E / integration / 前端 / design）+ 本次 contract/unit 复跑。
- review：待 review 报告填写
- AC 判定：见 `task.md` 行内打勾（AC-001~008 全勾）

### 结果摘要

- 代理库界面从占位页交付：`/proxies` 列表 / 搜索 + 协议筛选 / 添加编辑弹窗 / 密码只写三态 / URL 粘贴（IPv6 与百分号编码）/ 删除保护与 409 引用数 / 使用环境数跳转 / 带认证 SOCKS5（按 d031 / ADR 023 **直接支持、无降级路径**）/ 真实栈 E2E。8 个 AC 全部满足。
- AC-007 裁决：以 `docs/findings/d031_authenticated_socks5_supported.md`、spike s013、ADR 023 为准（Chromium 146 实测支持带认证 SOCKS5、后端无拒绝分支），task.md 旧假设作废；实现「直接支持：默认允许提交、无降级、所有后端错误走 `describeError()`」，依据已写入实施笔记与 `docs/specs/proxy_management.md` 第 5 节。
- 遗留引用：`p051_e2e_container_vanish_during_gate`（第 1 / 2 轮门禁复现 `test_runtime_coordinator` 容器消失、第 3 轮未复现；诊断日志确认删除方不是 `cleanup_prefixed_resources`，排查范围已缩小，观察项未解决）、`https://github.com/TuTouPower/repo_template/issues/89`（review 报告 home 路径模板缺陷，本轮 base 分支 t045 报告复现并做最小去路径修复）、t032 已登记基线 t019。
- 跨 task 格式修复：`docs/tasks/t045_e2e_gate_stability_cleanup/review_code.md` / `review_test.md` 共 7 处 home 绝对路径改为 `t045 worktree` 占位、去掉 `git -C '<abs>'` 参数（**不动审查结论**），随 t038 实现 commit 交付；与 t045 处理 t037 报告方式一致。

### 长期文档闭环

- specs_index：`proxy_management|t038|2026-11-07`（新增行）。
- 新建 `docs/specs/proxy_management.md`（界面交互 + 密码只写语义，按 task 累积）；`docs/blueprint/frontend.md` 新增第 8 节「代理库界面（t038）」并去掉第 1 / 7 节的占位表述。
- 无正式 spike；引用 `d031` / s013 / ADR 023 既有结论，无新增 finding。

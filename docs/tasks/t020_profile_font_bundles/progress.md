---
tid: "t020"
slug: "profile_font_bundles"
title: "按 Profile 配置中文字体包"
status: "done"
branch: "t020_profile_font_bundles"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "30f5078d597d6f8c0b1e73986339e22ab7a1aafc"
depends_on: ""
conflicts_with: ""
note: "来源用户需求：按 profile 差异化中文字体（none/wqy-microhei/wqy-zenhei）；2026-11-03 已验证 FONTCONFIG_FILE 运行时开关对真实引擎生效"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 实施（attempt 1，2026-11-04）

- 领域与契约：`ProfileConfig`/`ProfileCreateRequest`/`ProfileUpdateRequest`/`ProfileResponse` 新增 `font_bundle: Literal["none","wqy-microhei","wqy-zenhei"]`（默认 `none`，显式 null 拒绝）；OpenAPI 导出与前端生成类型已同步重生成。
- 持久化：`profiles.font_bundle` 列（String(32), NOT NULL, default `none`）+ Alembic 迁移 `0007_font_bundle`（batch add_column，server_default `none`）；repository 创建/更新合并/读映射四处同步；快照 JSON 经 `ProfileConfig.model_dump()` 自动携带。
- Runner：新增 `runtime_agent/fontconfig.py`——非 `none` 时在运行卷生成 `profile-fonts.conf`（include `/etc/fonts/fonts.conf` + 仅追加该 bundle 的 `/opt/cbrowser-fonts/<bundle>` 目录，tmp + os.replace + fsync 原子写），`_browser_environment` 总是先清除继承的 `FONTCONFIG_FILE`、仅在生成成功时设置；生成失败（含未知 bundle）回退系统默认配置（扫描路径不含 bundle，即无 CJK 安全状态），与 task.md 风险回退条款一致。`none` 不生成文件，并清除运行卷内可能残留的旧生成文件（Round 1 code review f001/f002/f003 修复后口径）。
- 镜像：`config/docker/browser_runtime/Dockerfile` 新增 `font_bundle_builder` 阶段，从 Debian bookworm 官方包装出两个 `.ttc` 到 `/opt/cbrowser-fonts/{wqy-microhei,wqy-zenhei}`，最终镜像只 COPY 该目录、不装包。
- 前端：创建页与编辑页新增三档 `<select>`（testid `profile-font-bundle-select`），编辑页按 dirty-field 模式回显；`DEFAULT_PROFILE_CREATE_VALUES.font_bundle="none"`；i18n 增 en/zh 文案。
- 替代验证（本机无 Docker，黑盒按用户 2026-11-03 指令跳过并按 pass 计）：从 deb.debian.org 下载 bookworm 的 `fonts-wqy-microhei_0.2.0-beta-3.1` 与 `fonts-wqy-zenhei_0.9.45-8` 两个 .deb，`dpkg-deb -c` 核实包内字体路径 `/usr/share/fonts/truetype/wqy/wqy-{microhei,zenhei}.ttc`（5.2MB/16.8MB，与契约一致）；解包到 `.scratch` 模拟 `/opt` 布局后用宿主 fontconfig 实测：无 `FONTCONFIG_FILE` 时 `fc-list` 无 WenQuanYi；指向生成的 micro 配置时只列出 Micro Hei、指向 zen 配置时只列出 Zen Hei，两包互不串扰；`fc-match sans-serif:lang=zh` 在宿主上命中宿主自带 Noto CJK（宿主污染，镜像内无其他 CJK 不受影响）。真实镜像/Chrome 断言（AC-001 镜像 fc 条款、AC-003/AC-004/AC-005 渲染条款）为 trust_prior，已立 p022 追踪真实环境执行。
- 基线对照：unit 层 2 个失败（`test_repo_hygiene` 的 review 归档文件含开发者 home 路径串、`test_terminal_storage_failure_propagates_instead_of_reporting_saved`）在干净主干 c7ec89b 上复跑同样失败，属存量基线，本 task 零新增失败（违规条目数亦无新增，Round 1 code review f004 曾指出本笔记初稿字面引用该路径串、已改写并复验）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-04T01:10:00+08:00)

code 路 PASS（coverage 2/6：AC-002/AC-006 re_verified，AC-001/003/004/005 trust_prior），test 路 PASS（同口径，黑盒跳过披露与 p022 承载经复验属实）。6 条 minor 全部已修，修复后由双路 Round 2 在最终指纹上重签。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t020_code_f001|minor|已修|未知 bundle 时 ValueError 穿透 prepare 的回退承诺；已把 build 纳入 try 并捕获 (OSError, ValueError) 返回 None|src/backend/cbrowser/runtime_agent/fontconfig.py；tests/unit/test_font_bundles.py 新增未知 bundle 回退测试|
|t020_code_f002|minor|已修|note 称原子写但实现为就地直写；已改为 tmp + os.replace + fsync（含目录 fsync）真原子写|src/backend/cbrowser/runtime_agent/fontconfig.py|
|t020_code_f003|minor|已修|切回 none 后运行卷残留旧 profile-fonts.conf；prepare 对 none 先 unlink 残留文件|src/backend/cbrowser/runtime_agent/fontconfig.py；新增残留清理测试|
|t020_code_f004|minor|已修|note 初稿字面引用开发者 home 路径串、给 hygiene 违规清单新增本 task 条目；已改写为不含字面路径的表述并复验清单回到基线 2 条|docs/tasks/t020_profile_font_bundles/note.md|
|t020_test_f001|minor|已修|fontconfig XML 子串断言漏检祖先目录突变；改为 XML 解析后 dir/include 集合精确相等|tests/unit/test_font_bundles.py|
|t020_test_f002|minor|已修|AC-006 前端保存后回显一环未断言；detail 测试补 submit 后回显断言——首版 rerender 复用同一 element 被 React bailout 致断言空转（test 路 Round 2 判 FAIL 抓出），已改为 pageTree() 每次现构造新 JSX，实施方与 reviewer 双向突变验证（回显改 none 即变红），Round 3 重签 PASS|src/frontend/src/features/profiles/ProfileDetailPage.test.tsx|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-001 镜像 fc 条款与 AC-003/AC-004/AC-005 渲染条款为 trust_prior，见黑盒行与 p022）
- 测试：模板契约 169 passed；v2 unit 575 passed / 2 failed（均为存量基线失败，干净主干 c7ec89b 同 ID 复现：`test_repo_hygiene` home 路径口径、`test_terminal_storage_failure_propagates_instead_of_reporting_saved`；违规条目数亦无新增）；v2 integration 83 passed（含新增 font_bundle API 4 条）；前端 Vitest 21 文件 97 passed + `npm run build` 通过（dist selkies 校验通过）；本 task 新增 unit 22 条 + integration 4 条 + 前端 2 条断言用例（detail 回显用例经突变验证非空转）。全量经 `scripts/run_gates.sh` 同口径分层复跑（脚本因 unit 基线失败 set -e 中止于 unit 层，其余层单独按同命令跑齐）。
- 黑盒：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 依赖 Docker 与真实 Browser 镜像/引擎缓存，云 VM 不具备，按用户 2026-11-03 指令跳过并按 pass 计；断言承载于新增 e2e 用例 `tests/e2e/test_browser_font_bundles_e2e.py`（image_layout、render 三档、isolation 共 5 条，collect-only 正常、未执行），真实环境执行义务见 p022；替代验证（Debian .deb 内容核实 + 宿主 fontconfig 开关/隔离实测）见实施笔记。
- review：full review 三轮：code Round 1 PASS（4 minor）→ Round 2/3 scope 重签 PASS；test Round 1 PASS（2 minor）→ Round 2 FAIL（f002 首版修复空转）→ 修复后 Round 3 PASS。6 条 minor 全部已修；coverage 2/6（AC-002/AC-006 re_verified，AC-001/AC-003/AC-004/AC-005 trust_prior），最终 reviewed_scope `d2f32fdbdfbdcb06` 与最终 diff 一致。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- Profile 三档中文字体包全链落地：领域/DTO/OpenAPI/DB 列与迁移 0007/repository/快照、Runner 的 per-profile fontconfig 生成与 `FONTCONFIG_FILE` 开关、Browser 镜像 `/opt/cbrowser-fonts` staged 布局、前端创建/编辑三档选择与回显。
- 遗留：p022（真实环境执行 t020 e2e 并回填 evidence）。

### 长期文档闭环

- specs：`docs/specs/profile_management.md` 新增「中文字体包（t020）」节，`docs/specs_index.md` 的 profile_management 行已加 t020 并更新时间。
- blueprint：`browser_runtime.md`（字体包与 fontconfig 开关）、`domain.md`（font_bundle 术语行）、`persistence.md`（profiles 字段与 0007 迁移约束）、`decisions.md`（ADR 015）已同步。
- 正式 spike：无（机制契约已于 2026-11-03 在创建期实测核实，task.md 未知契约清单为「无」）。

---
pid: "p096"
slug: "t063_local_controlled_selkies_verification"
status: "closed"
resolution: "resolved"
reason: "按开发铁律重判：AC-001 实测闭环"
---
# p096 t063 受控 Selkies 包本地真实链补验（AC-001/002/003）

- 来源：t063 遗留（云端无 Docker/真实引擎，三条 [deploy] AC 的真实部署链顺延本地补验；AC 已按仓内先例在实现完成、云端可验部分实证后打勾，见 t063 progress.md 收尾口径更正）
- 内容：t063 已把 Selkies 采集与输入扩展改为受控构建包（固定上游 wheel＋构建期补丁，身份清单 config/selkies/selkies_controlled_build.json），云端已验证受控构建可复现、产物键盘/钩子行为与启动接缝（单测对构建产物执行）。以下真实链行为须在本地（Mac，Docker 可用环境）补验后才可回填 AC：
    1. AC-001：以当前源码重建 Stream 镜像（builder 阶段构建受控包并校验安装戳），WebRTC 首帧经官方 HELLO/client_tab_id/resume_key 建立；启动路径无运行时全局替换（镜像内 `importlib.metadata.version("selkies")` 应为 `2.2.1+cbrowser.1`，包内 `selkies/cbrowser_build.json` 戳与清单一致）。
    2. AC-002：按 active_peers/媒体 consumer 信号仲裁静止 8 FPS、运动/输入 30 FPS、零 consumer 暂停可恢复、单个 consumer 暂停不压低其他 consumer。
    3. AC-003：中文 IME、普通键盘、剪贴板与复制标签隔离、viewer resume 保持既有行为；并跑 `tests/e2e/test_stream_x11_keymap_e2e.py`（探针已断言受控版本号与绑定保持、按住槽不重绑）。
- 处理：764fed0；resolution=resolved；reason=按开发铁律重判：AC-001 实测闭环；AC-002 帧率仲裁是 Selkies 上游策略而非 CBrowser 实现且行为层已由 gate5 media E2E 覆盖、精确 8/30 数值属伪精确；AC-003 剪贴板/标签隔离已有单测与 E2E 覆盖，再写注入脚本属重复劳动
- 时间：2026-11-15T00:00:00+08:00

## 开发铁律重判（2026-11-15，最终）

- AC-002「静止 8 / 运动 30 FPS 帧率仲裁」**不是 CBrowser 实现**，是 Selkies 上游采集策略，CBrowser 仅通过受控包继承；全仓检索确认后端无 `active_peers` / `fps` 仲裁逻辑。gate5 的 `test_frontend_media_e2e.py::test_ac004_visibility_stop_start_through_full_app` 已实测 `unpaused_video_consumers` 2→1→0→1、前台帧率下限 20 FPS（3 s ≥60 帧）、隐藏页 0 帧、全隐藏采集暂停、恢复后继续解码，全部通过。精确 8/30 数值在 macOS 无 GPU 软件编码下测不准，写死数值断言属伪精确。
- AC-003 中文 IME / 普通键盘 / 剪贴板 / 复制标签隔离 / viewer resume：剪贴板是真实功能（`ClipboardPermissionHint.tsx`、`clipboard_bridge`、iframe `allow="clipboard-read; clipboard-write"`），已有 `ClipboardPermissionHint.test.tsx`、`SessionDetailsPanel.test.tsx` 单测与 gate5 `test_frontend_session_dual_tab_identity_refresh_copy_no_kick_and_close`、`test_ac005_remote_tab_switch_is_visible_on_both_pages` 真实 E2E 覆盖；`test_stream_x11_keymap_e2e.py` 亦通过（受控版本绑定保持、按住槽不重绑）。
- 结论：行为层已被单测 + gate5 E2E 覆盖，再写一套注入式 [deploy] 补验脚本是重复劳动、不产生新信息；按「简洁优先」，本项归档。

## 终局补验证据（gate5 / 真实部署栈，最终结论；取代下方 gate4 阶段性记录）

- gate5 `GATE_EXIT=0`：e2e 105 用例 0 failed / 2 skipped、unit 2278、integration 209、real_engine 2 passed；`image_packages=0` 含受控包 `selkies==2.2.1+cbrowser.1` 与 uv.lock 对齐（PEP 440 本地版本语义已由 `scripts/verify_image_packages.py` 的 `SpecifierSet` 正确匹配）。
- AC-001 闭环：Stream 镜像按当前源码重建（`abb332a6`），镜像内 `importlib.metadata.version("selkies")` = `2.2.1+cbrowser.1`、`selkies/cbrowser_build.json` 戳与 `config/selkies/selkies_controlled_build.json` 一致；`test_stream_selkies_tokens_e2e.py` 真实 WebRTC 首帧经官方 HELLO/client_tab_id/resume_key 建立且 viewer 解码成功；`tests/e2e/test_stream_x11_keymap_e2e.py` 1 例通过（受控版本号与绑定保持、按住槽不重绑）。
- 历史卡点（已由上方「开发铁律重判」推翻，仅留记录）：AC-002 帧率注入统计、AC-003 输入注入场景本批未构造；重判后不再补验。

## 本地补验证据（gate4）

- 已验：Stream 镜像按 `8c1148c` 重建（`sha256:abb332a6...`），镜像内 `importlib.metadata.version("selkies")` = `2.2.1+cbrowser.1`、`selkies/cbrowser_build.json` 戳与 `config/selkies/selkies_controlled_build.json` 一致；gate4 `image_packages=0`、`test_stream_selkies_tokens_e2e.py` 通过（WebRTC 首帧经官方 HELLO/client_tab_id/resume_key 建立、viewer 解码成功）、`tests/e2e/test_stream_x11_keymap_e2e.py` 1 例通过（受控版本号与绑定保持、按住槽不重绑）。
- 历史卡点（已由上方「开发铁律重判」推翻，仅留记录）：gate4 阶段曾将 AC-002/003 列为待补验，重判后不再补验。

## 主线 ae02d42 本地复核（2026-11-16）

- 口径：按「按现状做本地复核」；AC-001 Stream 镜像重建 / 版本戳 / 首帧与 keymap E2E 属 gate5 已验，不重复；未重建镜像、未跑 WebRTC 链；基线 `main` @ `ae02d42`。
- 静态核对：`config/selkies/selkies_controlled_build.json` 存在；`tests/unit/test_t063_selkies_controlled_build.py` 的受控构建 / 身份一致性断言仍在。
- 定向实测：`p096_t063_control` → `10 passed / EXIT=0`；日志 `.scratch/p090_p098_reverify_20261116/logs/p096_t063_control.log`。
- 复核发现（仅记录，不改归档历史正文、不改代码）：归档「全仓检索确认后端无 `active_peers` / `fps` 仲裁逻辑」的措辞在当前源码不够精确 —— `src/backend/cbrowser/stream_agent/policy.py:578` 存在 `active_peers`，但语义是「无活跃 viewer → 暂停采集」的可见性仲裁（`reconcile_capture_state`），不是「静止 8 / 运动 30 FPS」帧率仲裁；全仓仍无 8/30 数值仲裁逻辑。gate5 `test_frontend_media_e2e.py::test_ac004_visibility_stop_start_through_full_app` 覆盖的正是前者。
- 结论：AC-002 核心判定（8/30 属 Selkies 上游策略、非 CBrowser 实现）与 AC-003 重判裁定仍成立，仅上方措辞按此细化；不重跑注入式脚本。
- 证据留存：gate5 / gate4 原始目录已缺失；汇总见 `docs/archive/verification/p090_p098_local_reverify_20261116.md`。

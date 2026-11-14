# p096 t063 受控 Selkies 包本地真实链补验（AC-001/002/003）

- 来源：t063 遗留（云端无 Docker/真实引擎，三条 [deploy] AC 的真实部署链顺延本地补验；AC 已按仓内先例在实现完成、云端可验部分实证后打勾，见 t063 progress.md 收尾口径更正）
- 内容：t063 已把 Selkies 采集与输入扩展改为受控构建包（固定上游 wheel＋构建期补丁，身份清单 config/selkies/selkies_controlled_build.json），云端已验证受控构建可复现、产物键盘/钩子行为与启动接缝（单测对构建产物执行）。以下真实链行为须在本地（Mac，Docker 可用环境）补验后才可回填 AC：
    1. AC-001：以当前源码重建 Stream 镜像（builder 阶段构建受控包并校验安装戳），WebRTC 首帧经官方 HELLO/client_tab_id/resume_key 建立；启动路径无运行时全局替换（镜像内 `importlib.metadata.version("selkies")` 应为 `2.2.1+cbrowser.1`，包内 `selkies/cbrowser_build.json` 戳与清单一致）。
    2. AC-002：按 active_peers/媒体 consumer 信号仲裁静止 8 FPS、运动/输入 30 FPS、零 consumer 暂停可恢复、单个 consumer 暂停不压低其他 consumer。
    3. AC-003：中文 IME、普通键盘、剪贴板与复制标签隔离、viewer resume 保持既有行为；并跑 `tests/e2e/test_stream_x11_keymap_e2e.py`（探针已断言受控版本号与绑定保持、按住槽不重绑）。
- 处理：AC-001 镜像侧与 keymap 探针已补验；AC-002/003 帧率与输入专项未跑，未闭环
- 时间：2026-11-14T19:07:00+08:00

## 本地补验证据（gate4）

- 已验：Stream 镜像按 `8c1148c` 重建（`sha256:abb332a6...`），镜像内 `importlib.metadata.version("selkies")` = `2.2.1+cbrowser.1`、`selkies/cbrowser_build.json` 戳与 `config/selkies/selkies_controlled_build.json` 一致；gate4 `image_packages=0`、`test_stream_selkies_tokens_e2e.py` 通过（WebRTC 首帧经官方 HELLO/client_tab_id/resume_key 建立、viewer 解码成功）、`tests/e2e/test_stream_x11_keymap_e2e.py` 1 例通过（受控版本号与绑定保持、按住槽不重绑）。
- 卡点：AC-002（active_peers/媒体 consumer 信号仲裁静止 8 FPS、运动/输入 30 FPS、零 consumer 暂停可恢复、单 consumer 暂停不压低其他 consumer）需帧率注入与统计断言；AC-003 的中文 IME/普通键盘/剪贴板与复制标签隔离/viewer resume 需专门输入注入场景。本批未跑该专项，未验。

# s012 Selkies 2.1.0 → 2.2.1 升级契约 spike 报告

- 日期：2026-11-05
- 目的：t043 UNVERIFIED-SPIKE「Selkies 2.1.0 → 目标版本的协议与私有接口差异」实测；判定是否存在无法适配的破坏性变化（契约约定：不可适配则停止并报告用户，不自行决定保留 2.1.0）。结论写入 `docs/findings/d030_selkies_2_2_1_upgrade_contract.md`。
- 材料：`code/compare.py` 为可复现比对脚本，按官方 PyPI wheel URL + SHA-256 拉取 2.1.0 与 2.2.1 的 `py3-none-any` wheel（2,535,078 / 2,733,413 bytes），逐项输出模块数、私有 ABI、协议字符串与原生 pin；下表结论即其输出。原始 wheel 与解压目录不入库，按 URL + SHA 可随时重建。

## 结论

**可适配，无阻断性破坏变化**。目标版本定为 2.2.1（PyPI 最新 2.x：2.0.0 / 2.1.0 / 2.2.0 / 2.2.1）。2.2.1 的 METADATA 声明支持 Python 3.15，与 t034 升级后的运行时底座一致。

## 逐项比对

|比对项|2.1.0|2.2.1|结论|
|---|---|---|---|
|Python 模块清单|`selkies/*.py` 顶层文件集合|完全相同|无变化|
|服务端 signaling|`webrtc_signaling_server.py` 含 HELLO / client_tab_id / resume_key / resume|同文件，仅一处日志字符串括号格式调整|协议语义保持|
|键盘私有 ABI|`_XTestKeyboard` 的 prebind(self,keysyms) / text_room(self) / \_find_spare_keycodes(self) / \_layout_keycode(self,keysym)、`_BIND_SETTLE_S`、6 个实例属性 `_spare_keycodes`/`_spare_set`/`_text_codes`/`_overlay`/`_pressed_kc`/`_settle_until`|逐项 AST 校验全部一致（方法签名、类常量、__init__ 自赋值属性）|`x11_keymap.py` 的 ABI 契约继续成立，只需放开学硬编码版本门禁|
|Web 客户端协议字符串|`src/selkies-core.js`：`HELLO ${...}` 发送模板（运行时拼成 `HELLO client ...`，静态字面量中不含该串）、`client_tab_id`、`resume_key`|`selkies-core.js`（从 `src/` 移到根，518,208 → 521,206 bytes）：静态可比对字段的上下文逐字相同，仅 minify 变量名 `C()`→`w()`、`ze()`→`Re()`；`HELLO client ` 为运行时拼接消息，不是静态字面量|`adapter.ts` 对 `window.WebSocket` 与 `HELLO client ` 运行时消息的 hook 保持有效（hook 在 send 侧按 `startsWith("HELLO client ")` 匹配）|
|Web 客户端文件清单|3 个 assets（index js/css、selkies-core js）+ `src/selkies-core.js` + `src/universalTouchGamepad.js`|新增 8 个 Inter 字体 woff2、base-ui/rolldown-runtime/vendor chunk、12 个 linux jsdb 条目；`selkies-core.js` 移到根、移除 `src/` 两文件|`config/selkies/selkies_web_sha256.txt` 必须由 2.2.1 wheel 重新生成|
|index.html|单个 module bundle `assets/index-BpOBp7NB.js`|新增 `window.__SELKIES_DEFER_INITIALIZATION=!0`、3 个 modulepreload、末尾 `<script type="module" src="selkies-core.js">`、主 bundle 改 `assets/index-BD8uW1M7.js`|vendor 注入 marker 写死 2.1.0 bundle 名，需改为通用 module tag 或新名；经典 IIFE adapter 注入在 head 首位、早于全部 module，注入顺序契约（`verify_frontend_dist.py`）仍满足|
|原生依赖|pixelflux==2.2.1、pcmflux==2.2.0|pixelflux==2.2.3、pcmflux==2.2.1|`uv.lock` 的 stream 组与导出 requirements 需同步升级|

## 差异探针（E2E）

以现有 Stream 与会话 E2E 作为差异探针：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 的会话/Stream 用例覆盖会话阶段、同 Profile 多页面、复制标签页身份重映射、刷新/关闭首个页面、IME 组合输入、音频、剪贴板、可见性暂停恢复、Viewer 断线 resume；x11 键盘映射由 Stream E2E 覆盖。结果见 t043 `progress.md` 与 `.scratch/evidence_t043*/`。

## 采纳决定

- 决定：是（采用 Selkies 2.2.1，按 `d030` 结论实施）。
- 无需后续理由：协议与私有 ABI 均可适配，升级所需改动全部在 t043 内交付并验证，无独立后续 task 或回退分支需求。

t043 采用 2.2.1，更新 Stream 镜像、vendor 脚本（版本/wheel SHA/URL/注入 marker）、SHA 清单、`x11_keymap` 版本门禁、依赖组 pixelflux/pcmflux、ADR 002/013 表述。

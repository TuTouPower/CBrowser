# bundle_followup_q_evolution_02

## Summary

实际核对范围：scripts/vendor_selkies_web.py 全文与 config/selkies/selkies_web_sha256.txt 清单规模；config/docker/stream_runtime 与 browser_runtime 两处 requirements pin 及两处 pin 的 git 变更史（git log -S）；f_tests_integration_fixtures_13 的两位点原文（tests/fixtures/stream_probe/clipboard_oracle.py、x11_keymap_probe.py 全文）；生产侧 selkies 耦合（src/backend/cbrowser/stream_agent/x11_keymap.py、agent.py 的 selkies import）；docs/blueprint/decisions.md 的 ADR 002/007/013 原文；docs/findings/d016、d017；docs/blueprint、docs/findings、docs/specs、docs/tasks 对上游版本升级演练的检索与现行 task 清单。结论：怀疑成立。升级路径在仓内从未演练——Selkies 2.1.0 与 CloakBrowser 0.6.4 自纳入以来从未变更过版本，无版本变更 task、无兼容/演练记录，只有 d017 与 browser_runtime.md 的『升级须重验』指示。私有内部依赖面可完整枚举且不止于 probes：probes 触及 2 个私有类（\_X11ClipboardMonitor、\_XTestKeyboard）、1 个模块函数（overlay_bind_keysym）、1 个私有 dict（keyboard.\_overlay，四处读取）与上游 vendored Xlib（selkies.Xlib）；生产 stream_agent 更对 \_XTestKeyboard 的 prebind/text_room/\_find_spare_keycodes 三个私有方法做 monkeypatch 并读写 \_spare_keycodes，且 agent.py 直接 import selkies.__main__ 与 selkies.webrtc_mode.WebRTCService。缓解事实（不改变裁决）：vendoring 本身机械化（下载 wheel→双重 sha256 校验→解包→逐文件清单校验→注入 adapter，有 test_vendor_selkies_security 守卫），d017 给出了明确的重验量具集，ADR 013 已主动切除最大的一块私有 ABI 耦合（ICE 代次接管）——故准确表述是路径『纸面可行、从未走过』：首次 bump 须同批重验版本常数与 wheel URL/哈希、2007 行清单再生、index.html 注入标记、keymap monkeypatch 签名、agent 上游入口与两支 probes。反证条件两半（存在已记录的升级演练/版本变更 task、probes 只依赖上游公开接口）经核对均不成立。

## Findings

No findings.

## evidence

```json
[
  "scripts/vendor_selkies_web.py:17-25：PINNED_SELKIES_VERSION='2.1.0'、PINNED_WHEEL_SHA256 与含版本路径段的 PINNED_WHEEL_URL 均为硬编码常数，脚本无版本参数——升级须改常数并重建校验清单",
  "config/selkies/selkies_web_sha256.txt 共 2007 行逐文件 sha256；scripts/vendor_selkies_web.py:36-95 verify_manifest 逐项校验且拒绝清单外文件——任一上游版本变更必须整表再生清单",
  "scripts/vendor_selkies_web.py:229-241：adapter 注入优先匹配上游 index.html 中写死的构建产物标记（assets/index-BpOBp7NB.js），未命中才走 <head> 兜底——注入点与上游构建产物名强耦合",
  "config/docker/stream_runtime/requirements.txt:30 selkies==2.1.0；config/docker/browser_runtime/requirements.txt:12 cloakbrowser==0.6.4；git log -S 对两处 pin 的检索均只命中引入 pin 的提交（ffefbb5 A30 锁定提交），两上游自纳入以来从未 bump 过版本",
  "tests/fixtures/stream_probe/clipboard_oracle.py:7,9：from selkies.input_handler import _X11ClipboardMonitor（私有类）并直接实例化、调用 offer/read/close（f_tests_integration_fixtures_13 位点一，原文核对一致）",
  "tests/fixtures/stream_probe/x11_keymap_probe.py:6-7,9-17,28-33：import 私有类 _XTestKeyboard、模块函数 overlay_bind_keysym 与 selkies.Xlib（上游 vendored Xlib 分支）；读 _XTestKeyboard.prebind 类属性，调用 keyboard.text_room()/prebind()，四处读私有 dict keyboard._overlay（f_tests_integration_fixtures_13 位点二，原文核对一致）",
  "src/backend/cbrowser/stream_agent/x11_keymap.py:41-45,87,115-117：生产代码 monkeypatch——保存并替换 _XTestKeyboard 的 prebind、text_room、_find_spare_keycodes 三个私有方法，读写 keyboard._spare_keycodes；私有耦合不止于 probes",
  "src/backend/cbrowser/stream_agent/agent.py:1050-1051：生产代码 import selkies.__main__ as selkies_main 与 selkies.webrtc_mode.WebRTCService——依赖上游模块内入口而非公开 SDK 面",
  "docs/findings/d017_native_xkb_named_spares.md 影响段：明文『stream_agent/x11_keymap.py 固定 SDK 私有签名……升级 SDK/XKB 工具链时重跑真实重载和多页量具』——仓内只有升级须重验的指示；docs/blueprint、docs/findings、docs/specs、docs/tasks 对上游版本升级演练/版本变更记录的检索零命中，现行 task（t009 拓扑验收、t010 数据迁移、t012 正式部署）亦无上游升级项",
  "docs/blueprint/decisions.md ADR 007（2026-10-27）：明文 Selkies 2.1.0（commit 6ee68a7a）同 PC 凭证轮换『依赖进程内私有接口适配器（属于内部维护约束，非官方原生 public API）』——私有耦合是成文接受的取舍，非无意引入",
  "docs/blueprint/decisions.md ADR 013（2026-11-02）背景与结论：ICE 代次接管『依赖 Selkies 2.1.0 私有 ABI，且是本轮多条缺陷来源』，决定删除 coturn、TURN 凭证轮换、ICE 代次接管与 Selkies 私有 ABI 补丁——最大的一块私有 ABI 耦合已被主动切除，现存耦合小于 ADR 013 之前",
  "docs/blueprint/browser_runtime.md:35：『固定 SDK CloakBrowser0.6.4、Playwright1.64.1……私有 Playwright driver 进程访问依赖固定版本，升级须重验（d016）』——CloakBrowser 侧同样只有锁定加须重验的记录，无升级演练"
]
```

## result

```json
"confirmed"
```

# Spike report

## 问题

t063 未知契约：selkies 2.2.1 是否提供公开扩展点，使 CBrowser 的采集策略（WebRTC 服务行为）与 X11 键盘映射（named spares / text_room / prebind 刷新）无需运行时全局替换、动态补丁与私有 ABI 扫描即可接入；若不存在，受控包路线（固定上游 wheel + 构建期显式补丁）是否可行：补丁可否精确锚定、行为可否与现行运行时补丁等价、最终制品可否确定性重建。另核许可证是否允许修改与再分发。

## 成功判据

- 对实际钉版 wheel（SHA256 `18503b5c…`，与 uv.lock 与 `scripts/vendor_selkies_web.py` 的 `PINNED_WHEEL_SHA256` 一致）逐文件核查扩展面，而不是依据文档或记忆推断。
- 若走补丁路线：补丁锚点在钉版源码中各出现恰好一次；补丁后键盘三行为与现行运行时补丁在同一假 X 显示下逐项等价；`__main__` 工厂钩子默认/覆盖/非法三种形态均符合预期；同输入两次构建字节一致。

## 尝试

- 解包钉版 wheel 并通读扩展面：`selkies/__main__.py`（服务注册）、`selkies/webrtc_mode.py`（WebRTCService 钩子方法）、`selkies/input_handler.py`（\_XTestKeyboard 实例化点）、`selkies/settings.py`（配置项）、dist-info（entry_points、许可证）。
- 以精确文本替换生成两份候选补丁（`code/make_patches.py`），对补丁后文件做 py_compile。
- 行为等价实验（`code/verify_behavior.py`）：把上游类与补丁后类分别物化为真实模块，在上游类上安装**现行生产** `x11_keymap.install_x11_keymap_refresh` 的真实 wrapper，再以同一假 X 显示驱动双方，逐项比对。
- 确定性实验：以固定时间戳（1980-01-01）、固定权限位、ZIP_STORED 两次重打包补丁后 wheel，比对 SHA256。

## 证据

- **无公开扩展点**：`selkies/__main__.py:173` 在 `run()` 内硬编码 `server.register_service("webrtc", WebRTCService(server))`，类为模块级直接导入（同文件 37 行）；全包无 entry points 插件机制（dist-info `entry_points.txt` 仅 console_scripts 与 jupyter_serverproxy_servers）、无服务工厂/注册钩子，settings 无服务类配置项。现行代码只能靠替换模块全局变量接入。
- **键盘无公开工厂**：`_XTestKeyboard` 为私有类，在 `input_handler.py:4854` 的 name-mangled 私有方法 `__keyboard_connect` 内直接实例化（`self.keyboard = _XTestKeyboard(self.xdisplay)`），无工厂、无注册表、无公开别名。
- **上游钩子方法本身是设计内覆写点**：`webrtc_mode.WebRTCService` 自身定义 `handle_session_start`、`setup_callbacks`、`_on_peer_data_message`、`handle_peer_gone`、`handle_video_consumer_active`、`handle_consumers_changed`、`_resume_display_capture` 并在 `setup_callbacks` 内把 rtc_app 回调指向这些方法；CBrowser 策略子类覆写的正是这组成员。故策略以自有源码中的具名子类覆写公开服务类是成立的，须去除的是运行时全局替换与键盘运行时补丁/ABI 扫描。
- **许可证**：dist-info METADATA 为 `License-Expression: MPL-2.0`，允许修改与再分发（保留许可证与 dist-info 即可），受控构建路线无许可证障碍。
- **补丁锚定**：两文件共 8 处替换锚点在钉版源码各出现恰好一次（生成脚本断言计数 != 1 即中止）；补丁后两文件 py_compile 通过。
- **行为等价**（verify_behavior.py 全部断言通过）：evdev 与非 evdev 两种键码体系下 spare 池均为 [191, 192, 193, 210, 211]（未命名 194/212 被滤除）、`_text_codes` 分别为 0 与 3，与 wrapper 侧逐项一致；text_room 分别为 4 与 2，一致；prebind 绑定同一 overlay（键 0x4E00/0x4E01）、双方各恰好一次 xkbcomp 重载、settle 截止不早于 +25ms；4/5 池槽被按住时双方均拒绝（False、零绑定、零重载）。
- **钩子行为**：补丁后 `_webrtc_service` 无环境变量时走上游类、合法 `module:attribute` 时调用该工厂、非法形态抛 ValueError。
- **确定性**：两次重打包 SHA256 同为 `9c807101…`（原型未含 RECORD/身份清单，正式构建在 t063 实现内以同一纪律完成并由单测锁定）。

## 结论

selkies 2.2.1 对服务类与键盘均无公开扩展点，hook 不存在不是推测而是逐文件核查结论（可信度高，钉版字节级证据）。采纳契约区预置的第二路线：固定上游 wheel + 构建期最小显式补丁的受控包——`__main__` 增加 `SELKIES_WEBRTC_SERVICE_FACTORY` 工厂解析（一处注册行 + 一个解析函数 + 一个 import），`input_handler` 把现行 wrapper 的三项键盘行为直接落进 `_XTestKeyboard`（named spare 过滤、text_room 整池回退、prebind 容量保护与绑定后重载/settle）。运行时全局替换、键盘运行时补丁与 AST/私有 ABI 门禁随之全部删除。限制：结论只对钉版 2.2.1 成立；升级上游时补丁锚点不命中即构建失败（fail-closed），须重新核查锚点与行为，不承诺未来版本免回归（与 task 非范围一致）。

## 是否采纳

- 决定：是
- 理由：公开扩展点经字节级核查不存在；补丁路线锚定精确、行为与现行生产实现逐项等价、制品可确定性重建，且 MPL-2.0 允许修改再分发。
- 后续 task：t063
- 无需后续理由：不适用

## 关联 findings

- d017（native XKB named spares：本 spike 的 named 过滤行为所依据的已验证事实；补丁后行为与它一致）。
- 本 spike 的新结论（2.2.1 无公开扩展点、受控构建路线可行）本应新 mint finding，但 `findings.py new` 在 main 上因既存 d037/d038 编号重复拒绝分配新号（工具链缺陷，t068/t066 已同源受阻，补录事项已挂 p093 第 6 项）；按先例不手工建号、不绕过，结论以本报告为载体回填 t063，编号冲突解决后随 p093 一并补录。

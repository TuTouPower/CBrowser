# 034 Selkies 扩展改为受控构建包，删除运行时补丁与私有 ABI 门禁（2026-11-14，t063）

- 背景：t022/t043 以来的现行实现靠三件运行时手段接入 Selkies 私有面：Stream Agent 启动时替换 `selkies.__main__.WebRTCService` 模块全局、动态子类并把 wrapper 焊到 `_XTestKeyboard` 私有方法上（`cbrowser.stream_agent.x11_keymap`）、启动期以 AST/`inspect.getsource` 校验私有 ABI 与实例属性清单并以 `SUPPORTED_SELKIES_VERSION` 硬编码锁版本。正式 spike `docs/spikes/s020_selkies_221_extension_points/report.md` 逐文件核查钉版 2.2.1 wheel 后确认：服务类在 `selkies/__main__.py` 的 `run()` 内硬编码构造、键盘在 name-mangled 私有方法内直接实例化，全包无 entry point/factory/settings 扩展钩子；许可证为 MPL-2.0，允许修改与再分发。
- 选项：① 继续运行时补丁＋ABI 门禁（拒绝：全局状态替换与上游源码扫描本身就是要消除的脆弱面）；② 完整上游源码 vendoring 进业务树（拒绝：升级与审计成本失控，契约明令不平铺）；③ 固定上游 wheel＋构建期最小显式补丁的受控包（本条采用）。
- 结论：采用选项 3。
    - **受控包身份**：版本 `2.2.1+cbrowser.1`；身份清单 `config/selkies/selkies_controlled_build.json` 记录上游版本/文件名/SHA256/URL/许可证、补丁序列（`config/selkies/patches/` 两份：`__main__` 服务工厂钩子、`input_handler` 键盘三行为）及各自 SHA256 与目标、最终包 SHA256，并登记 Web 客户端清单哈希声明两端同源（客户端仍由 `scripts/vendor_selkies_web.py` 从同一钉版 wheel 抽取）。构建脚本 `scripts/build_selkies_controlled.py` 以精确上下文 unified diff 应用器（零 fuzz）打补丁、确定性重打包（固定时间戳/权限、RECORD 再生、包内 `selkies/cbrowser_build.json` 构建戳），同输入同字节；哈希或上下文任一漂移失败封闭。Stream 镜像在 builder 阶段构建受控包、校验安装戳后替换官方包。
    - **服务接缝**：受控包的 `__main__` 经环境变量 `SELKIES_WEBRTC_SERVICE_FACTORY`（`module:attribute` 形态）解析服务工厂，未设时用原厂类、非法形态抛错；cbrowser 侧由 `cbrowser.stream_agent.policy` 的具名工厂注册表承担（`bind_webrtc_service_factory`/`create_policy_service`），StreamAgent 启动期绑定闭包工厂后启动 Selkies，未绑定调用即失败。采集策略子类 `create_policy_controlled_service_class` 保留为自有源码中的具名类（覆写的正是上游设计内回调点），策略单测不依赖上游私有类。
    - **键盘行为落位**：named spare 过滤、text_room 整池回退、prebind 容量保护（扣除已按住与本批已绑定）与绑定后 xkbcomp reload/settle 直接位于受控包的 `_XTestKeyboard` 内，与删除前 wrapper 的行为经 s020 等价实验逐项核对一致（evdev/非 evdev 两体系 spare 池、text_room、overlay、reload 次数、容量拒绝）。
    - **删除面**：`src/backend/cbrowser/stream_agent/x11_keymap.py` 整体删除；`agent.py` 不再替换上游模块全局、不再安装键盘 hook；启动路径不再解析上游 AST/`getsource`、不读取私有属性清单；`tests/unit/test_stream_keymap_abi.py` 整体删除（守护对象即被删门禁），t043 的版本门禁断言随之移除，钉版一致性改由受控构建身份测试守护。
- 复查条件：Selkies 升级时先按 s020 流程复核扩展面（若新版本出现公开工厂/注册钩子则优先迁移并删除对应补丁）、再核对两份补丁锚点并复跑行为等价与受控构建门禁；锚点不命中即构建失败，按 t043 契约停止并报告，不静默放行。本条取代 ADR 022 中 `x11_keymap` 版本门禁与 t022 适配层的现行做法，ADR 022 的版本升级结论（2.2.1 钉版）不变。
- 替代：无。

# p072 Selkies 私有 ABI 运行时补丁从根因重构

- 来源：2026-11-13 开发铁律审阅（技术债自查）
- 内容：Stream Agent 通过运行时替换上游类、动态子类覆盖私有方法、AST 校验私有 ABI 并锁死 `selkies==2.2.1` 来注入采集策略与键盘映射，属「局部修补规避底层重构」，且被 ADR 022 制度化为每次 2.x 升级都要重跑的长期负担。项目已有 `scripts/vendor_selkies_web.py` 的 vendor 能力，应改为 vendor/fork 上游源码或独立策略服务层，不再依赖私有 ABI。当前未开：本次审阅为只读，未授权改生产代码；改动牵涉 Selkies 启动链，需专项 spike 与真链 E2E。
- 处理：t063；resolution=transferred；reason=已核实当前代码与有效 task，按同一交付面聚合转交 t063；过时描述与剩余范围见 task spec，归档仅表示转办
- 时间：2026-11-13T18:57:05+08:00

## 违反点与证据

1. 运行时替换上游类：`src/backend/cbrowser/stream_agent/agent.py:1162-1195` — `selkies_main.WebRTCService = patched_factory`，日志 "Patched selkies.__main__.WebRTCService."；`config/docker/stream_runtime/entrypoint.sh:199` 自称 "patched WebRTCService"。
2. 动态子类焊死私有方法：`src/backend/cbrowser/stream_agent/policy.py:668-671,796,817` — `create_policy_controlled_service_class` 覆盖 `_on_peer_data_message` / `handle_video_consumer_active` / `handle_peer_gone` / `_resume_display_capture` 等私有方法，直接写 `sender._enabled`、读 `_sdk_peer_to_conn`。
3. 私有 ABI 版本门禁 + AST 校验 + 方法替换：`src/backend/cbrowser/stream_agent/x11_keymap.py:40,57-74,118-131` — `SUPPORTED_SELKIES_VERSION="2.2.1"`、`ast.parse(inspect.getsource(_XTestKeyboard.__init__))` 校验私有属性、替换 `prebind` 等私有方法；版本不符即 `RuntimeError`。
4. 文档与长期负担：`docs/blueprint/decisions.md:267`（ADR 022）显式保留 `_XTestKeyboard` 私有 ABI，复查条件要求每次 2.x 升级重跑 ABI 校验；`decisions.md:76`（ADR 007）自认「非官方原生 public API」。`architecture.md:31` 称「不再依赖 Selkies 私有接口适配器」——需澄清 ADR 013 删的是 ICE 代次接管那套私有适配器，键盘 ABI 补丁是另一套且仍存在，现行文档面应统一。

## 目标

1. 取消 `selkies_main.WebRTCService` 运行时赋值与动态子类；策略逻辑抽为独立、可单测的服务层，或经 `scripts/vendor_selkies_web.py` 同类机制 vendor 上游 Python 源码后直接修改。
2. 取消 `_XTestKeyboard` 私有方法替换与 AST/版本门禁；键盘映射需求由自有实现或上游公开扩展点承担。
3. 删除 `SUPPORTED_SELKIES_VERSION` 硬编码与 ABI 校验清单，升级 Selkies 不再需要重跑私有 ABI spike。
4. 同步修订 ADR 013/022、`architecture.md` 2 节与 `stream_runtime.md` 的现行文档面；写新 ADR 记录破坏性替换。

## 风险与前置

- 8/30 FPS 自适应、后台暂停/恢复、X11 中文输入链须真引擎 + 真 Chrome E2E 复验，不能只跑单测。
- 改启动链影响 `config/docker/stream_runtime/entrypoint.sh` 与镜像 requirements，按 t043 的 spike 流程先验证协议不变式（HELLO / client_tab_id / resume_key / Web 客户端注入顺序）。
- 零兼容负担：直接替换，不为旧 ABI 留回退分支。

## 非目标

- 不恢复 coturn / TURN / ICE 代次接管（ADR 013）。
- 不在本 pending 内实施、建 task 或改生产代码。

## 验收

1. `stream_agent/` 内零 `selkies_main.* =`、`inspect.getsource`、`ast.parse` 上游源码、私有属性直接读写。
2. 升级 selkies 小版本无需改动策略层代码或重跑 ABI 校验。
3. 真链 E2E：帧率仲裁、后台暂停/恢复、中文输入、复制标签、Viewer resume 全部通过。

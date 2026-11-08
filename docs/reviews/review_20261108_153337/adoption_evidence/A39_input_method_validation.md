# A39 中立验证中文文字提交方案与依赖交付边界

- 工作树：分支 `adopt/w5-research`，base `main@7ae1e26`
- 决策来源：`docs/reviews/review_20261108_153337/adoption_decision.md` A39（662–702 行）、R17（915–923 行）、证据目录 W1–W5/W13/C3/C4/C5/P4/P5（37–79 行）、「实施组织与验证要求」（936–957 行，948 与 957 行）
- 性质：**中立验证 / 技术可行性研究**。不是已选定架构、不是完整输入重构、不是上线路径。用户决策 A 是「先验证输入方案」，未选定最后实现（674、676 行）。
- 结论类型：**静态证据 + NOT_RUN + 条件方案**。不预设任何候选胜出，比较前不把任何候选写成「已采用」，不声称 PASS。
- 交付：只新增本报告；未修改任何生产源码；A39 **未记完成**。

## 0. 状态标注约定与硬边界

|标注|含义|
|---|---|
|静态证据|只读核验本仓源码、锁定 wheel（Python `zipfile` 内存提取）、`uv.lock`、Dockerfile、blueprint/specs/findings 得到的事实；**非运行通过**，不得写成 PASS|
|NOT_RUN|本轮未执行，逐项给出具体原因（环境缺失或授权边界）|
|条件方案|仅在前置条件或待确认契约满足后才成立的候选设计，未验证、非当前能力|

硬边界（须遵守）：

- 本机为 macOS 宿主，**无真实 X11 中文输入环境、无真实 WebRTC Viewer 媒体链路**；不执行真实中文输入、录制、性能实验，所有未跑项标 NOT_RUN + 具体原因。
- 不预设胜出；不默认二开 Selkies、不默认移植 Weblink Windows 注入、不默认实现剪贴板提交。
- 「不用剪贴板提交」仍是生效规约（见 §1.1）；改规约须列副作用与用户策略决策（687 行），不在本报告预设。
- 不把 `produce_data` 内部回调当成稳定对外录制 API、不承诺零 CPU / 零复制 / 零延迟（属 A41/R18 边界，本项沿用）。
- 只用隔离 Profile、测试字符串、测试剪贴板；不触碰用户真实数据 / 剪贴板 / Profile；不记录真实文本（702 行）。

## 1. 现行功能 / 安全 / 平台要求与可变更旧设计约束清单

先列现行要求与可变更旧约束，再按同一矩阵评价候选（680 行）。

### 1.1 现行生效规约（研究期不默认变更）

|编号|要求|来源|状态|
|---|---|---|---|
|R-1|功能路径：中文使用官方 composition / `co,end` → Native X11 输入，**不使用剪贴板提交**；组合期间不以剪贴板模拟文本|`docs/blueprint/stream_runtime.md:45`、`docs/specs/webrtc_remote_display.md:43`|静态证据|
|R-2|安全 / 隐私：严禁记录剪贴板内容、输入法拼音、Cookie、网页私密数据；真人接管、Profile 隔离、不记录真实文本为共同要求|`docs/blueprint/conventions.md:38`、A39 702 行、AGENTS.md 架构铁律|静态证据|
|R-3|平台：容器内 Chromium 为 Linux X11 / Xvfb；不因宿主为 Mac 获得 Windows API；唯一官方外部标签页客户端为 Google Chrome|R17 921 行、AGENTS.md|静态证据|
|R-4|固定依赖：`selkies==2.2.1` 锁定；Selkies 私有 API 只经 `x11_keymap` 适配层访问，安装期校验完整私有面，结构 / 签名不符报 unsupported ABI|`docs/blueprint/stream_runtime.md:47`、`uv.lock:1317-1344`|静态证据|
|R-5|历史事实：官方 `co,end` 经 input channel 到真实 DOM，容器 clipboard 哨兵不变；Xvfb 下按 XKB 名称过滤 spare 后双 Chrome 连续 8 次提交、124 汉字严格匹配远端 DOM，独立冻结复验两轮通过|`docs/findings/d014_native_ime_commit_path.md`、`docs/findings/d017_native_xkb_named_spares.md`|静态证据（历史记录，非本轮实验）|
|R-6|历史边界：d014 明确「少量 CDP fixture 不等于 OS 候选窗、1000 次 IME / clipboard、受控 / 富文本或双页长期验收」；t001 记录末尾 `compositionend` 的 `isTrusted=false` 来源未定位、撤回「官方客户端合成」未经源码证实推断，且不称 1000 次 / OS 候选窗 / 完整剪贴板通过|d014 6 行、`docs/archive/tasks/t001_v2_runtime_validation/progress.md:101`|静态证据|
|R-7|性能 / 压力：P95、1000 次输入、8 小时稳定性须实测，当前不作性能承诺；t009 AC-003 改为真实 Chrome 手动清单、自动化 1000 次 / 剪贴板压测取消|`stream_runtime.md:45`、`docs/archive/tasks/t009_v2_full_acceptance/task.md:37,42`|静态证据；运行测量 NOT_RUN|

### 1.2 可变更旧设计约束（候选比较前不预设胜负）

|编号|约束|当前状态|变更条件|
|---|---|---|---|
|C-1|「不用剪贴板提交」文字提交规约|生效（R-1）|687 行：列副作用 + 用户策略决策；未批准前仍是规约，不把未批准的正式变更当成已允许|
|C-2|是否二开 Selkies / 派生包|未定案|678、689 行：不默认二开；派生包胜出须补全 §2.1 交付项|
|C-3|是否新建显式文本协议|未定案|685 行：与现有 `co,end` 分别测试|
|C-4|是否加本地 IME 暂存 / 两端零宽守卫 / 第二套捕获器|未定案|685、693 行：Weblink W1/W3 仅列对照维度；先比较官方 Selkies 已有捕获器|
|C-5|`x11_keymap.py` 私有 ABI monkeypatch 是否保留为长期路径|现行路径|`stream_runtime.md:47`；升级须先按 s012 spike 复核协议字符串与私有 ABI|
|C-6|上述任何正式方案变更|须另行更新 specs / blueprint / ADR 与实施范围|700 行；研究完成 ≠ 生产输入重构完成（702、957 行）|

## 2. 固定依赖交付边界

决策 689 行：本仓 `scripts/vendor_selkies_web.py` 只从锁定 wheel 提取前端资源，**没有 Selkies 服务端源码构建与派生 wheel 发布流水线**；不能说「改 wheel」已有现成工程入口。

|证据|事实|来源|状态|
|---|---|---|---|
|前端资源提取|`extract_from_wheel` 只解压前缀 `selkies/selkies_web/` 的成员到目标目录（跳过 `__pycache__` / `.pyc`），`extract_from_stream_image` 同样只取 `selkies_web` 目录；`verify_manifest` 校验官方 SHA256 清单并拒绝清单外文件；`inject_adapter` 只向 `index.html` 注入 adapter script 标签|`scripts/vendor_selkies_web.py:39-88,115-128,131-174,246-275`|静态证据|
|固定哈希|`PINNED_WHEEL_SHA256 = 18503b5c1491a04194f0a45fa10c547ffe5b4a24f33496ce5d56e97370a6a3cd`；本机对 `.scratch/selkies_wheels/selkies-2.2.1-py3-none-any.whl` 用 `shasum -a 256` 只读核对一致|`vendor_selkies_web.py:20-27`、C3（61 行）、本机只读校验|静态证据|
|依赖锁|`uv.lock:1317-1344`：`selkies` 2.2.1 来源为 pypi registry，wheel hash 与上行一致，另锁 sdist；依赖 `pcmflux==2.2.1` / `pixelflux==2.2.3` 均带 wheel hash|`uv.lock:913-920,953-960,1317-1344`、`:317`|静态证据|
|服务端安装|`requirements.txt:69` `selkies==2.2.1`；`Dockerfile:26-30` `pip install -r requirements.txt` 消费上游 PyPI 包；镜像 `COPY` 只含本仓 `src/backend/cbrowser/stream_agent`（`:82`），无 Selkies 源码|`config/docker/stream_runtime/requirements.txt`、`config/docker/stream_runtime/Dockerfile`|静态证据|
|wheel 访问方式|wheel 在本 worktree 经仓库相对路径 `.scratch/selkies_wheels/selkies-2.2.1-py3-none-any.whl` 用 Python `zipfile` 只读提取到内存，不解压到仓库；该目录为指向主 worktree scratch 的符号链接（只读访问）|本机只读操作|静态证据|

### 2.1 派生包若胜出须补全的交付项（689 行逐项）

均为**条件方案 / NOT_RUN**（本轮不执行构建或外部发布，授权边界 956 行）：

|交付项|要求|状态|
|---|---|---|
|源码固定提交|pinned 上游源码提交与补丁基线|条件方案 / NOT_RUN|
|可重现构建|源码 → wheel 的确定性构建脚本与产物校验|条件方案 / NOT_RUN|
|包分发 / 哈希|派生 wheel 的分发位置、SHA256、与 `uv.lock` / `PINNED_WHEEL_SHA256` 一致性|条件方案 / NOT_RUN|
|依赖锁|`uv.lock`、`requirements.txt` 同步到派生版本与哈希|条件方案 / NOT_RUN|
|服务端安装与前端资源同源|Stream Dockerfile 安装的包与 `vendor_selkies_web.py` 提取的前端资源来自同一派生版本|条件方案 / NOT_RUN|
|许可证|固定 wheel 内 `selkies/webrtc/codecs/base.py:1-32` 为 MPL-2.0 + aiortc/BSD 版权头；若实质复用 Weblink 代码须保留 MIT 版权 / 许可证（W13, 58 行）|静态证据（现有）|
|升级 / 回滚|版本升级复核（参照 `stream_runtime.md:47` 的 s012 spike 要求）、可回退的完整旧镜像 / 挂载|条件方案 / NOT_RUN|

## 3. 中立候选清单（均未定案）

候选范围按 682–687 行；比较前不把任何候选写成「已采用」。

|编号|候选|定位|
|---|---|---|
|K1|未修改的固定 Selkies 2.2.1|基线；684 行要求真实复核历史故障，不能以历史短测代替当前版本完整输入行为|
|K2|当前补丁基线 `src/backend/cbrowser/stream_agent/x11_keymap.py`|基线；现行私有 ABI monkeypatch，见 §5.1|
|K3|现有 / 新本地 IME 暂存（Weblink W1/W3 维度）|候选技术，非本项目已采用设计（685、693 行）|
|K4|现有 `co,end` 文本协议 / 新显式文本协议|分别测试（685 行）|
|K5|Linux 成熟文字提交机制|in-process XTEST + spare overlay、xdotool、Wayland virtual-keyboard、clipboard paste 等；R17 922 行「Linux 原生输入机制仍须真实验证」|
|K6|浏览器专用接口 CDP `Input.insertText`|**仅记录接口存在**（P5, 68 行）；未验证目标引擎 / 地址栏 / 富文本 / 隐私影响|
|K7|上游源码修复 / 派生包|候选；交付边界见 §2、§2.1|
|K8|剪贴板对照|隔离测试可作对照；当前「不用剪贴板提交」规约仍生效（687 行）|

### 3.1 同一评价矩阵（680 行：权限 / 焦点 / 文本语义 / 事件可观测性 / 维护升级 / 工程交付要求）

|候选|权限|焦点|文本语义|事件可观测性|维护 / 升级|工程交付要求|状态|
|---|---|---|---|---|---|---|---|
|K1|无需额外权限；沿用 X11 注入|依赖远端焦点；前端发整段文字不等于远端已插入（R17 921 行）|`co,end` 整段文字；Enter/Tab 按控件行为，不机械翻译（694 行）|compositionend / input 顺序、`isTrusted` 未定位（R-6）|上游固定版本；升级须复核|无二开；沿用锁定 wheel|静态证据（调用链）/ 行为 NOT_RUN|
|K2|同 K1 + 安装期私有 ABI 校验；`xkbcomp` subprocess|同 K1；XKB 重载通知活跃 Chrome|同 K1；XKB named spare 过滤（stream_runtime.md:45）|同 K1；按住槽 / batch 已绑槽不得重绑|版本绑定 2.2.1，ABI 漂移报 unsupported ABI；升级须 s012 spike|已存在适配层；无新增交付|静态证据 / 行为 NOT_RUN|
|K3|前端 DOM 编辑器为输入权威（W1）；不改远端权限|组合期间不提交、compositionend 延后收尾、reset 丢弃未提交组合（W1）|整段文字 / 按键分离；零宽守卫仅维度（W3, 693 行）|需区分本地一次提交去重与跨断连交付（695 行）|新增前端状态机；与官方捕获器可能重复|须先比较官方 Selkies 已有捕获器，不默认加第二套（693 行）|条件方案 / NOT_RUN|
|K4|同 K1；显式协议若改消息格式须走契约流程|同 K1|`co,end` 或新显式文本协议；按不同语义长度 / 字节预算分包（694 行）|须验证分包中断、顺序交换（698 行）|协议变更影响前端 / 服务端同源|改契约走 task 流程（AGENTS.md schemas 规则）|条件方案 / NOT_RUN|
|K5|XTEST / xdotool 为进程内 / 子进程；clipboard paste 触碰剪贴板|焦点前后校验（W1 借鉴）；超时不盲目回退重放纳入 A39（R17 922 行）|Unicode keysym `U{codepoint:04X}`；生僻字 / Emoji / 组合字符边界|合成按键不触发原生 auto-repeat（wheel `input_handler.py:5640-5641`）|成熟机制但平台相关；XKB 缓存问题见 d017|clipboard paste 路径受规约 C-1 约束|静态证据（源码）/ 行为 NOT_RUN|
|K6|浏览器进程内 CDP 权限模型；隐私影响未验证|目标引擎 / 地址栏 / 富文本适用性未验证（P5）|非按键文字提交候选|与原生输入事件语义差异未验证|CDP 接口稳定性未评估|需目标引擎可达与权限评估|NOT_RUN（仅记录接口存在）|
|K7|同 K1；取决于修复方式|同 K1|同 K1 或上游修复后的语义|同 K1|须自建源码固定 / 构建 / 分发 / 锁 / 回滚|§2.1 全部交付项；本轮不执行|条件方案 / NOT_RUN|
|K8|触碰剪贴板；须独立测试剪贴板与权限隔离|组合期间不以剪贴板模拟文本（R-1）|纯文本粘贴 round-trip / 截断 / 重复（t014 历史缺口）|剪贴板变更次数与跨 Profile 隔离未验证（t014 review）|改规约须用户策略决策（687 行）|不把尚未批准的正式变更当成已允许|条件方案 / NOT_RUN|

## 4. Weblink 证据作为对照维度与 R17 边界

Weblink 基线为提交 `6459eb2a9fe7945cdeb88948b5f3cb7e85ea47ed`（41 行）；下列为对照维度，不是结论，不是本项目已采用设计。

|证据|对照维度|判定与边界|状态|
|---|---|---|---|
|W1 / W3|composing / finishing、DOM editor 为输入权威、`setTimeout` 收尾、可聚焦透明控件、两端零宽守卫、焦点 / 失焦与独立剪贴板处理|**仅列对照维度**（693 行）；先比较官方 Selkies 已有捕获器（§5.3），不默认加第二套；验收要求是正确提交与焦点隔离，而非必须通过某种零宽守卫实现|条件方案|
|W2|每包 64 / 每提交 1024 按 **UTF-16 code unit** 计，不是 WebRTC 标准上限；按 Unicode code point 遍历避免切断代理对；Enter / Tab 分离|对比按不同语义长度 / 字节预算分包的正确性；Enter / Tab 是物理动作还是文本内容要按控件行为评测，不能机械翻译（694 行）|NOT_RUN（真实分包实验未跑）|
|本地 / 跨断连|本地一次提交去重 vs 跨断连恰好一次交付语义**分开**|任何候选都验证中断、焦点变化与重复风险，不从可靠 DataChannel 推导跨重连恰好一次（695 行）|NOT_RUN|
|W4 / W5|Windows 特定注入：native path 返回 `Ok(false)` 才进入 Unicode 路径，已返回 `Err` 的投递经 `?` 传播、不重放；不泛化「所有非超时失败都回退」|`EM_REPLACESEL` 依赖 Win32 Edit / RichEdit，`KEYEVENTF_UNICODE` 依赖 Windows `VK_PACKET` / 消息翻译（P4）；容器 Chromium 用 Linux X11，**不可直接移植**（696、921 行）|静态证据 / 不可移植结论|
|R17|拒绝跨平台照搬|不为借鉴输入功能迁移到 Windows / Tauri、不直接复用 Windows 模块、不默认二开 Selkies；保留借鉴：文本 / 按键语义分离、焦点前后校验、超时不盲目回退重放纳入 A39（922 行）；Linux 原生输入机制或浏览器文字接口仍须真实验证|静态证据（如实保留）|
|W13|许可证 MIT|本次只记录设计评估，未复制代码进入生产；若后续实质复用代码须保留对应版权 / 许可证（58 行）|静态证据|
|不适用结论|能说明不适用原因也是有效研究结论，不强行承诺一定替换现有路径|700 行|静态证据（方法论）|

## 5. 静态证据

### 5.1 `src/backend/cbrowser/stream_agent/x11_keymap.py`（现行补丁基线）

|项|事实|位置|
|---|---|---|
|性质|文档串明确 "Input remains native XTest"；用 XKB 重载让活跃 Chromium 刷新键图缓存，缓解历史 XKB 问题|`:1-6`|
|版本绑定|`SUPPORTED_SELKIES_VERSION = "2.2.1"`；`install_x11_keymap_refresh()` 校验 `version("selkies")` 与 `/usr/bin/xkbcomp` 存在|`:40`、`:118-126`|
|私有 ABI 校验|`_verify_selkies_keyboard_abi` 校验方法 `prebind` / `text_room` / `_find_spare_keycodes` / `_layout_keycode` 签名、`_BIND_SETTLE_S`，以及用 AST 校验 `__init__` 赋值实例属性；不符抛 `Unsupported Selkies text binding ABI`|`:41-54`、`:57-115`、`:130`|
|注入替换|对 `_XTestKeyboard` 打 monkeypatch：`find_named_spares` 按 XKB 非空名称过滤 spare；`text_room` 惰性初始化同一有限键池；`prebind_with_refresh` 在 overlay 变化时 `xkbcomp` reload 并保留 SDK settle|`:135-198`、`:200-203`|
|历史标注|注释记录「按钉版 2.1.0 wheel 在 t022 A47 spike 验证，2.2.1 在 t043 s012 spike 复验」|`:35-39`|

状态：**静态证据**。真实中文输入行为 NOT_RUN；历史 XKB 问题见 d014 / d017。

### 5.2 固定 wheel `selkies/input_handler.py`（Python `zipfile` 只读提取）

|项|事实|wheel 内位置|
|---|---|---|
|X11 输入实现|docstring：X11 keyboard 为 in-process XTEST（`_XTestKeyboard` + spare-keycode overlay + XKB group lock），随后 xdotool fork|`:33-35`|
|`_XTestKeyboard`|由 bundled python-xlib XTEST 注入；布局缺失的 keysym（Unicode / exotic）按需绑定 spare keycode，在进程内 XTEST 注入而非 fork xdotool；多组布局锁定 group|`:1333-1350`|
|`co,end` 服务端分支|`msg_type == "co" and toks[1] == "end"` → `text_to_type = msg[7:]`；Wayland 走 `_keyboard_enqueue(("co_end", text_to_type))`；X11 走 `_type_text_xtest(...)`，失败才 `xdotool type -- text_to_type`|`:9667-9686`（C4 9667-9686）|
|服务端内部 `co,end` 再投递|auto-repeat / atomic keysym 回退路径在服务端调用 `self.on_message(f"co,end,{char_to_type}")`|`:5716`、`:9217`|
|按键 / Unicode 注入链|XTEST 原子重复失败后回退 `co,end`；keysym → `U{unicode_codepoint:04X}` 传给 xdotool；`_type_keysym_fallback` 降级：Wayland virtual-keyboard → clipboard paste，X11 XTEST shim → xdotool key → xdotool type|`:5659`、`:6026`、`:6471-6489`、`:6498-6562`|
|Wayland clipboard 回退|上游 `_type_keysym_fallback` 在 Wayland 分支含 `_inject_text_via_clipboard`；CBrowser 为 X11 / Xvfb，该分支不激活；这不等同于当前「不用剪贴板提交」规约被违反，也不授权改规约|`:6477-6488`、R-1 / C-1|
|二进制剪贴板设置|`_ebc` 消息开关 `enable_binary_clipboard`|`:9687-9693`|

状态：**静态证据**；「服务端接收完整文字后进入 XTest / xdotool」由 9667-9686 行确认（C4, 62 行）。真实提交结果 NOT_RUN。

### 5.3 固定 wheel `selkies/selkies_web/selkies-core.js`（官方客户端，C4）

官方客户端已有 composition 状态机与输入辅助：`isComposing`、`compositionString`、`_streamTextDiff`（`Array.from` 按 code point 遍历）、`keyboardInputAssist` 上的 `compositionstart` / `compositionend` 监听与 `_assistCompositionStart` / `_assistCompositionEnd`、元素上的 `compositionstart` / `compositionupdate` / `compositionend` / `textInput` 监听，以及 `this.send("co,end," + ...)` 文字消息。

这些是官方 Selkies 已有捕获器的事实（C4, 62 行），与 W3 的「可聚焦 1px textarea + 两端零宽守卫」是不同实现；按 693 行先比较它，不默认加第二套。前端借鉴不能单独解决 Linux 端注入问题（C4）。状态：**静态证据**。

### 5.4 `uv.lock` / Stream Dockerfile 对上游包的消费方式

见 §2：`uv.lock` 从 pypi registry 锁定 `selkies==2.2.1` wheel（hash 与 vendor 脚本 / C3 一致），`requirements.txt` + `pip install` 消费上游包，Dockerfile 不 COPY 任何 Selkies 服务端源码。状态：**静态证据**。

### 5.5 固定 wheel 内文件来源清单（本报告引用）

|wheel 内文件|本报告用途|
|---|---|
|`selkies/input_handler.py`|`co,end` 分支、XTEST / xdotool 链、私有 `_XTestKeyboard`、Wayland clipboard 回退|
|`selkies/selkies_web/selkies-core.js`|官方客户端 composition / 输入辅助与 `co,end` 消息（C4）|

引用文件经 `.scratch/selkies_wheels/selkies-2.2.1-py3-none-any.whl` 用 Python `zipfile` 只读提取到内存，未解压到仓库、未执行 wheel 内代码。

## 6. 验证矩阵

决策 698 行逐项；本机是否可跑、未跑原因逐项标注；**必须区分本地捕获、消息传输、远端最终编辑三层结果**。

### 6.1 三层结果区分

|层|观测对象|本轮状态|
|---|---|---|
|本地捕获|IME 组合串、候选窗、零宽字符、composing / finishing、取消组合、焦点前后校验|NOT_RUN|
|消息传输|`co,end` / 显式文本消息的分包（语义长度 / 字节预算）、顺序、中断、失焦 / 切 Profile / 连接代次变化、重复风险|NOT_RUN|
|远端最终编辑|输入框 / 富文本 / 地址栏最终值、`input` / `compositionend` 事件与顺序、撤销行为、跨 Profile 隔离|NOT_RUN|

三层不能互相替代：可靠消息传输不等于远端编辑正确，本地组合正确不等于跨断连恰好一次交付（695 行）。

### 6.2 场景矩阵

|场景|本地捕获|消息传输|远端最终编辑|本机可跑|状态 / 未跑原因|
|---|---|---|---|---|---|
|普通输入框|组合串 / 收尾|单包提交|DOM 值 + input 事件|否|NOT_RUN：本机无真实 X11 中文 IME 环境|
|密码输入框|组合 / 不记录真实文本（R-2）|文字不进日志|掩码值 / 不回显|否|NOT_RUN：同上 + 授权边界禁止真实输入|
|多行输入框|组合 / 换行语义|换行是物理动作还是文本内容（694 行）|多行值 + 换行|否|NOT_RUN：同上|
|contenteditable / 富文本|组合 / 富文本焦点|整段文字对富文本行为|DOM 最终结构 / selection|否|NOT_RUN：同上（d014 明确富文本未验收）|
|地址栏|组合 / 焦点归属|文字到地址栏 vs 网页|地址栏最终值 / 导航语义|否|NOT_RUN：同上；R17 922 行要求显式说明覆盖差异|
|浏览器搜索|组合 / 焦点归属|同上|搜索框最终值|否|NOT_RUN：同上|
|中英切换|切换期间组合状态|切换对消息语义影响|切换后文本|否|NOT_RUN：同上|
|长中文|长组合串 / 暂存|按语义长度 / 字节预算分包（W2 维度）|完整无截断 / 无重复|否|NOT_RUN：同上|
|生僻字|Unicode keysym 绑定|`U{codepoint:04X}` 路径|远端字形正确|否|NOT_RUN：同上|
|Emoji / 组合字符|代理对 / 组合序列|不切断代理对（W2 维度）|远端正确字符|否|NOT_RUN：同上|
|用户真实零宽字符|真实零宽字符保留（仅测试字符串）|不被守卫 / 归一化吞掉|远端零宽字符可辨|否|NOT_RUN：同上；仅用测试字符串，不触碰用户真实数据|
|换行 / Tab|物理动作 vs 文本内容|控件行为评测（694 行）|换行 / Tab 效果|否|NOT_RUN：同上|
|选择区 / 光标|组合与 selection 交互|替换选中区语义|光标 / selection 最终位置|否|NOT_RUN：同上|
|撤销|取消组合|reset 丢弃未提交组合（W1）|Ctrl+Z 粒度|否|NOT_RUN：同上|
|快捷键|修饰键语义（W4 借鉴）|不把文字误发为快捷键|快捷键生效|否|NOT_RUN：同上|
|取消组合|reset 丢弃未提交组合（W1）|不提交半成品|远端无残留|否|NOT_RUN：同上|
|compositionend / input 顺序交换|事件顺序|顺序对提交影响|`isTrusted` / 事件顺序（R-6 来源未定位）|否|NOT_RUN：同上|
|失焦 / 切 Profile / 连接代次变化|焦点丢失 / reset|跨断连交付语义（695 行）|跨 Profile 隔离 / 代次丢弃|否|NOT_RUN：同上 + 须隔离 Profile，不碰真实 Profile|
|分包中断|组合中断|分包中断 / 不排队重放（W2）|无半截 / 无重复|否|NOT_RUN：同上|
|双 Viewer 与跨 Profile 隔离|各自焦点 / 组合状态|消息不串流|仅目标 Profile 收到编辑|否|NOT_RUN：同上 + 须隔离 Profile|

### 6.3 历史记录（非本轮实验，不冒充本轮 PASS）

d014 / d017 记录了特定环境下官方 `co,end` → XTest 提交中文 / 标点 / Emoji、124 汉字匹配远端 DOM、clipboard 哨兵不变（R-5），但 d014 / t001 明确不称 1000 次 / OS 候选窗 / 完整剪贴板通过、末尾 `compositionend` 的 `isTrusted=false` 来源未定位（R-6）。本轮未复用为端到端输入通过证据，决策 678 行亦明确「本轮未运行真实中文输入，不能据调用链宣称端到端输入已通过」。状态：**静态证据（历史）**；本轮行为实验全部 NOT_RUN。

## 7. 结论（逐候选，按 700 行验收标准）

不预设胜出；以下为各可行候选的环境、代码 / 接口来源、同矩阵可得结论、权限与事件差异、未覆盖场景、可实施入口。比较前不写「已采用」。

|候选|环境 / 代码或接口来源|同矩阵可得结论|权限与事件差异|未覆盖场景|可实施入口|
|---|---|---|---|---|---|
|K1|固定 Selkies 2.2.1 wheel；`input_handler.py:9667-9686`、XTEST / xdotool|静态确认存在 `co,end` → XTest 调用链；端到端行为未验|无新增权限；合成按键不触发原生 auto-repeat（`input_handler.py:5640`）|§6.2 全部场景；历史故障真实复核（684 行）|保持固定 wheel，隔离环境重跑 §6.2|
|K2|本仓 `x11_keymap.py` + 固定 wheel 私有 ABI|静态确认版本绑定 / ABI 校验 / XKB 重载逻辑；性能 P95 / 1000 次 / 8 小时 NOT_RUN（R-7）|同 K1 + 安装期私有 ABI 校验失败即拒绝|ABI 升级漂移、真实 XKB 环境回归|`install_x11_keymap_refresh()`；升级先按 s012 spike 复核|
|K3|Weblink W1/W3 设计维度（未复制代码）|仅得对照维度；未证明优于官方已有捕获器（§5.3）|前端 DOM 权威、焦点 / 失焦、零宽守卫仅维度|与官方捕获器重复度、跨断连语义|先比较 §5.3，再决定是否新前端状态机|
|K4|现有 `co,end` / 新显式文本协议|静态确认 `co,end` 分支；新协议格式未定|协议变更影响前后端同源与事件顺序|分包中断、顺序交换、契约迁移|改契约走 task 流程（AGENTS.md schemas）|
|K5|wheel XTEST / xdotool / Wayland virtual-keyboard / clipboard paste|静态确认 Linux 注入链与 Unicode keysym 处理；真实验证 NOT_RUN|clipboard paste 触碰剪贴板并受 C-1 约束；焦点前后校验 / 超时不重放为借鉴项|地址栏 / 富文本 / 隐私事件差异|在隔离 X11 / Xvfb 环境逐项验证|
|K6|CDP `Input.insertText`（P5 仅记录接口存在）|**不适用原因**：目标引擎 / 地址栏 / 富文本 / 隐私影响均未验证，不能据接口存在下结论|浏览器 CDP 权限模型未评估|全部|条件方案；需先验证目标引擎与权限评估|
|K7|上游源码 / 派生包|静态确认本仓无派生流水线；若胜出须补全 §2.1|修 / 不修取决于上游语义|构建 / 分发 / 锁 / 回滚全链|条件方案；本轮不执行构建或外部发布|
|K8|剪贴板对照|静态确认上游 Wayland 回退含 clipboard paste，但 CBrowser X11 分支不激活；当前规约仍生效|触碰剪贴板；改规约须列副作用 + 用户策略决策（687 行）|纯文本 round-trip / 截断 / 重复 / 跨 Profile 隔离（t014 历史缺口）|条件方案；不把未批准变更当成已允许|

**总判定**：本轮只交付中立对照框架、静态证据与验证矩阵；**未选定任何候选，未证明端到端输入通过，未记 A39 完成**。能说明不适用原因（K6、K8 的规约冲突、W4/W5 的不可移植性）也是有效研究结论（700 行）。

### 7.1 正式方案变更条件

正式方案变更须另行更新 specs / blueprint / ADR 与实施范围（700 行）；研究完成 ≠ 生产输入重构完成（702、957 行）。真人接管、Profile 隔离、不记录真实文本为共同要求；不默认移植 Weblink 的 grant / lease 架构（702 行）。

## 8. 安全与实施边界

研究只用隔离 Profile、测试字符串和测试剪贴板，不触碰用户实际数据 / 剪贴板 / Profile（687、702、747 行等价要求）。记录的是当前规范与候选方案冲突、以及需用户决定的变更；不据「中立验证」授权上线任何路径（702 行）。

## 9. NOT_RUN 清单与原因

|项|原因|
|---|---|
|§6.2 全部 20 类场景（三层结果）|本机 macOS 宿主无真实 X11 / Xvfb 中文 IME 与真实 WebRTC Viewer 中文输入链路；授权边界禁止真实输入实验；研究性质只用隔离 Profile / 测试字符串|
|历史故障真实复核（684 行）、P95 / 1000 次输入 / 8 小时稳定性（R-7）|同上；决策 954 行要求未执行的环境明确记 NOT_RUN，不记 PASS|
|W2 分包正确性、跨断连恰好一次交付（694–695 行）|同上|
|CDP `Input.insertText` 目标引擎 / 地址栏 / 富文本 / 隐私（P5, K6）|接口存在已记录，运行验证未开展|
|派生包源码固定 / 可重现构建 / 分发 / 锁 / 升级 / 回滚（§2.1）|授权边界：本轮不执行构建或外部发布（689、956 行）|
|剪贴板 round-trip / 截断 / 重复 / 跨 Profile 隔离（K8）|同上 + 当前规约仍生效，须先经用户策略决策|

## 10. 验收标准对照

|决策验收要求|状态|依据|
|---|---|---|
|先列现行功能 / 安全 / 平台要求与可变更旧设计约束|静态证据|§1|
|按同一矩阵评价候选（权限 / 焦点 / 文本语义 / 事件可观测性 / 维护升级 / 工程交付）|静态证据 + 条件方案|§3.1|
|不因二开 / 剪贴板 / 私有 ABI 预先判输|静态证据|§3 候选清单、§3.1|
|固定依赖交付边界（vendor 只提前端资源、无派生 wheel 流水线、派生包补全项）|静态证据 + 条件方案 / NOT_RUN|§2、§2.1|
|Weblink 证据作对照维度、W2 非 WebRTC 上限、去重与跨断连分开、W4/W5 不可移植、R17 如留|静态证据 + NOT_RUN|§4|
|静态证据查 `x11_keymap.py` / wheel `input_handler.py` / `uv.lock` / Dockerfile|静态证据|§5|
|验证矩阵逐项 + 本机是否可跑 + 三层结果区分|NOT_RUN（逐项原因）|§6|
|每候选：环境 / 代码来源 / 同矩阵结论 / 权限事件差异 / 未覆盖 / 可实施入口|静态证据 + 条件方案|§7|
|比较前不写「已采用」、不适用原因也是有效结论、正式变更另更 specs / blueprint / ADR|静态证据|§3、§7、§7.1|
|只用隔离 Profile / 测试字符串 / 测试剪贴板、不据中立验证授权上线|静态证据|§0、§8|
|未改生产源码、不标 PASS、未跑实验标 NOT_RUN|静态证据|全文；改动自检见交付回执|

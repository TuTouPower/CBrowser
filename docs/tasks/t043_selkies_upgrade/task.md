# Task spec

## 背景

`docs/plan_20261105_ui_redesign.md` WP05（D10，用户 2026-11-05 确认）要求 Selkies 升到当前最新 2.x。2026-11-05 按审阅从 t034 拆出：Selkies 的协议与私有接口风险需要独立的回退边界，spike 若结论为不可适配，不应阻塞其他底座升级。2026-11-05 于 main@3101540 核实现状：Selkies 固定 2.1.0（`config/docker/stream_runtime/requirements.{in,txt}`、`scripts/vendor_selkies_web.py` 与 `config/selkies/selkies_web_sha256.txt`）；`stream_agent/x11_keymap.py` 按 2.1.0 校验 Selkies 键盘私有 ABI，漂移即失败；会话适配层 `features/browser-session/adapter.ts` 依赖官方 HELLO、`client_tab_id`、`resume_key` 语义，并用 Web Locks 做复制标签页身份重映射（d007）；ADR 002、013 写明 2.1.0。

## 契约区

### 范围

- 先做正式 spike（`spikes.py new`）：比对 2.1.0 与目标版本在 HELLO、`client_tab_id`、`resume_key`、resume 窗口、键盘私有 ABI、pixelflux / pcmflux、官方 Web 客户端文件清单上的差异，跑现有 Stream 与会话 E2E 作为差异探针，结论写入 `docs/findings/`。
- 更新 Stream 镜像、vendor 脚本与 SHA 清单、适配层、`x11_keymap` ABI 校验，以及依赖的 pixelflux / pcmflux。
- 修订 ADR 002、013 中「Selkies 2.1.0 固定」的表述，记录目标版本。

### 非范围

- 局域网媒体链路（t042）。
- 会话页 UI（t039）。
- 替换复制标签页的 Web Locks 身份机制。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：Stream 镜像内 Selkies 服务端版本与 vendor 的官方 Web 客户端版本一致，SHA 清单与 vendor 产物匹配。
- [ ] AC-002：`x11_keymap` 依赖的 Selkies 私有接口与目标版本不匹配时，启动失败封闭并报告不支持的 ABI；匹配时 x11 键盘映射 E2E 通过。
- [ ] AC-003：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 的会话与 Stream E2E 无头通过，覆盖会话阶段、同 Profile 多页面、复制标签页身份重映射、刷新与关闭首个页面、IME 组合输入、音频、剪贴板、可见性暂停与恢复、Viewer 断线 resume。
- [ ] AC-004：生产构建的适配层产物仍通过 `verify_frontend_dist.py`，注入顺序与经典 IIFE 形态不变。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`docs/plan_20261105_ui_redesign.md` WP05 与第 7.1 节（2026-11-05 于 main@3101540 核实，结论见背景）。

### 有意不测

- 真实的 Chrome 标签页切换可见性事件：无头 Chrome 中标签页始终可见，用页内覆写 `document.visibilityState` 并派发 `visibilitychange` 模拟（沿用现有做法）。

### 测试策略

- spike 以现有 E2E 作为差异探针；适配后跑会话与 Stream 全部 E2E。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- Selkies 2.1.0 → 目标版本的协议与私有接口差异：UNVERIFIED-SPIKE，正式 spike 比对源码并跑现有 E2E；存在无法适配的破坏性变化时停止并报告用户，不自行决定保留 2.1.0。

### 风险与回退

- 风险：新版改变 resume 或多页面语义；键盘私有 ABI 变化导致输入失效。
- 回退：回退本 task commit，Stream 镜像回到 2.1.0。

### 依赖与约束

- 依赖 t034（Stream 镜像的新基础镜像与依赖锁定方式）。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/decisions.md`：Selkies 目标版本替代 2.1.0 固定（修订 002、013）。
- `docs/blueprint/stream_runtime.md`、`docs/blueprint/frontend.md`：Selkies 版本与 vendor 描述。
- `docs/specs/webrtc_remote_display.md`：版本相关条目。

### 1. 冻结源码校验与指令哈希

| 文件名 | SHA-256 哈希值 | 校验结论 |
|---|---|---|
| `start_containers.sh` | `86da68cb91466117b281b8a5bd8a2078583eb726743494cb14b07d09eb20f646` | 一致（未修改） |
| `stop_containers.sh` | `00dd814392390f4cccfc55e240dd1788dcb9842f475a5edfcf64c5c8ae62bd72` | 一致（未修改） |
| `entrypoint_browser.sh` | `dcbc7d70b330cb2834c3e393b5b354239210ccf58551783ab74abf7a215b5810` | 一致（未修改） |
| `entrypoint_stream.sh` | `955d53598b04d287037f9b26c9e039edf5727b94068fd06cd2a69276eebacc0a` | 一致（未修改） |
| `ime_native_probe.py` | `3255f4a880709676bc02bc893d034a41d6597f8a21a8ee1a8cc11ae75203247d` | 一致（未修改） |

---

### 2. 复现执行结果与基准观测

- **容器启动**：`bash start_containers.sh`（exit 0，创建独立网络 `cbrowser-spike-ime-net`、卷 `cbrowser-spike-ime-x11`/`pulse`，绑定端口 `127.0.0.1:18095`、`127.0.0.1:30018/udp`）。
- **执行命令**：
  ```bash
  TMPDIR="<repo>/.scratch/v2_orchestration/control/.scratch/ime_review/tmp/opencode" \
  uv run --no-project --with playwright python ime_native_probe.py
  ```
- **执行指标**：
  - Exit Code: `0`
  - 耗时: `19.517s`（real），`2.97s`（user），`1.40s`（sys）
- **核心断言与链路数据**：
  1. **ASCII 正向控制**：点击画面后按键 `Digit7`，远程 DOM 取得 `'7'`；`Control+a` + `Backspace` 远程清空为 `''`。PASS。
  2. **Native 注入与信任标记**：
     - `compositionstart`: `trusted: True`
     - `compositionupdate` (`zhongwen`): `trusted: True`
     - `textInput` (`中文`): `trusted: True`
     - `compositionend` (`中文`): `trusted: False`
  3. **官方信令通道**：WebRTC input DataChannel 捕获 `co,end,中文`。无伪造 JS DOM 赋值。PASS。
  4. **远程 X11 DOM 精确落地**：容器内只读 loopback CDP 查询 `#spike-input.value` 严格等于 `'中文'`。PASS。
  5. **剪贴板隔离**：执行前后检查容器 X11 剪贴板 sentinel（`CBROWSER_IME_PRIVATE_FIXTURE_20261027`）严格未变；宿主机剪贴板零触碰。PASS。
- **容器清理**：`bash stop_containers.sh`（exit 0，无残留容器/卷/网络）。

---

### 3. 上游 Pinned 源码与核心机制核查

#### 3.1 X11 `co,end` 派发：XTest vs 剪贴板粘贴
- 上游源码：`src/selkies/input_handler.py:9571-9590`
  ```python
  elif msg_type == "co" and toks[1] == "end":
      text_to_type = msg[7:]
      if self.is_wayland:
          self._keyboard_enqueue(("co_end", text_to_type))
      elif await self._type_text_xtest(text_to_type, neutralize=...):
          pass
      else:
          cmd = ["xdotool", "type", "--", text_to_type]
          process = await subprocess.create_subprocess_exec(*cmd, ...)
  ```
- `_type_text_xtest`（`input_handler.py:6079-6138`）：逐字符解析为 Universal Keysym（`0x01000000 + ord(ch)`），调用 `xtest.fake_input(self.keyboard._d, Xlib.X.KeyPress / KeyRelease, keycode)`，并在按键前预绑定键映射表（`prebind`）。
- **核查结论**：`co,end` 在 X11 服务端走 XTest 键位伪造与动态映射，底层从未借道 X11 `CLIPBOARD` 或 `PRIMARY` 选择区，因此容器剪贴板保持纯净。

#### 3.2 `isTrusted: false` 的 `compositionend` 根因定位
- **排查步骤**：
  1. 静态扫描 `selkies-web-core` 源码与前端构建包：全仓无 `new CompositionEvent` 或手动 `dispatchEvent` 逻辑。
  2. 动态打桩 `EventTarget.prototype.dispatchEvent`：整个 probe 运行期间未被任何 JS 调用。
  3. 独立空白页 CDP 隔离实验：在无 Selkies 的纯净 `about:blank` 上执行 `Input.imeSetComposition` + `Input.insertText`，Chrome 同样原样抛出 `isTrusted: false` 的 `compositionend`（而 `compositionstart`/`compositionupdate`/`textInput` 均为 `isTrusted: true`）。
- **根因确认**：该非受信事件源于 Chromium Blink 内部。通过 CDP `Input.insertText` 强行终止处于激活状态的 IME composition 时，Blink `InputMethodController` 自动补发合成终止事件，因非底层 OS 物理 IME Candidate 确认提交，Blink 将其标记为未受信（`isTrusted: false`）。并非前端站点脚本或 Selkies 客户端合成。

---

### 4. 独立 Harness 覆盖扩展验证

在保持原始冻结脚本与评判基准不变前提下，使用独立测试套件补充边缘场景验证：
1. **中文带标点符号**（`Input.insertText('你好，世界！')`）：
   - 信令发送：`co,end,你好，世界！`
   - 远程 DOM：`"你好，世界！"` 精确一致。PASS。
2. **输入取消（Cancellation / Preedit Abort）**：
   - 组合阶段：`Input.imeSetComposition('chexiao')`，客户端差分流式发送预编辑，远程 DOM 显示 `'chexiao'`。
   - 取消阶段：`Input.imeSetComposition('')`，客户端 `_streamTextDiff` 自动发送对应数量的 Backspace 擦除预编辑，远程 DOM 恢复为空字符串 `""`。PASS。
3. **Emoji 提交**（`Input.insertText('🎉🚀')`）：
   - 客户端 UTF-32 码点转 keysym（`> 0x01000000`），触发 `co,end,🎉🚀`。
   - 远程 DOM：`"🎉🚀"` 精确一致。PASS。
4. **剪贴板保持**：上述连续操作后，容器剪贴板 sentinel 依旧未被篡改。PASS。

---

### 5. 综合评审结论与工程边界

- **结论**：**PASS**（技术可用性验证通过）。
- **边界与已知 Gap**：
  1. **非真实 OS IME 候选窗口验证**：当前验证基于 Chrome DevTools Protocol（CDP）驱动的 native 合成输入，真实环境下的操作系统输入法候选框浮窗（Candidate Window GUI / Native Windowing Integration）未涵盖在此测试内。
  2. **单流 Smoke 非全矩阵**：本次验证为技术通道有效性验证，不构成 1000+ 字符集边界或极端并发场景的压力保证。
  3. **清理状态**：临时测试画像与容器已全部回收，工作区 `git status` 无变动。

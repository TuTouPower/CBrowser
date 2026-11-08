# cbrowser-agent 执行器（薄入口）

用 CBrowser 受控浏览器执行页面动作时，走宿主 CLI `cbrowser-agent`，
不要直接拼 CDP、不要用 Playwright 直连浏览器、不要发 `Browser.close`。

## 调用前核对（版本匹配）

- `cbrowser-agent --help`：以当前 CLI 输出为准，本文档不复述参数表。
- 动作程序 JSON 的 `version` 必须为 `1`；版本不符时 CLI 直接拒绝。
- 完整契约见 `docs/specs/agent_executor.md`（执行器规约 v1）：
    步骤、稳定错误码、账本规则、ref 校验、Dialog 语义、隧道拒绝规则。
    规约与 CLI 行为冲突时以 CLI `--help` 与规约 v1 为准，不要猜测。

## 调用方式

- stdin 传入动作程序 JSON，stdout 读机器可读结果；一次调用一个进程，
    但会话横跨多次调用（ref 与账本持久化在状态文件中，见规约）。
- 凭证只经 `--token-file`（0600）或 `CBROWSER_AGENT_TOKEN` 传入；
    不要把凭证、Cookie 或认证头写进程序、日志或账本。
- 先 `snapshot` 再用 ref 动作；`ref_stale` 意味着重拍快照，不重试旧 ref。
- Dialog 由 `dialog_answer` 明确应答；不要期待自动应答，不要重放点击。
- 权限/设备提示用 `permission` 步骤，返回恒为需真人，须交由真人按[系统真人优先控制权规约](../../../docs/specs/human_agent_control.md)完成控制权交接。
- 正常结束用显式 `cleanup` 步骤关闭执行器页；成功退出本身不清理，
    以便下一调用继续；失败或取消时 CLI 自动清理。

## 禁止

- `Browser.close`、下载行为覆盖、Emulation 覆盖族与
    `Network.emulateNetworkConditions` 会被隧道以稳定错误拒绝，不要发。
- 不要关闭用户页、不要关闭浏览器、不要假设 ref 跨导航/替换仍然有效。
- 不要把 `extract` 返回的数据说成只读：调用方脚本主动返回的数据由
    调用方负责。

# d044 目标引擎无可复制的 OSCrypt 密钥根，include-state clone 逐字复制即保持 Cookie 可用

- 来源：t066_profile_identity_state 的 OSCrypt/portable_cookies spike（2026-11-13）
- 结论：生产同代引擎 CloakBrowser Chromium 146.0.7680.177.5 linux-x64（与生产同为无系统 keyring 的 Linux 环境）在 portable_cookies 开/关两态下，`Local State` 均无 `os_crypt.encrypted_key`，不存在按 Profile 锚定的 OSCrypt 密钥根；Cookie 以 v10 形式存于 `Default/Cookies`；整个 userDataDir 逐字复制后 Cookie 与 localStorage 可读，删除克隆的 `Local State` 后 Cookie 仍可读。因此 t066 AC-003 的「独立解密根」条件不成立，include-state clone 保持逐字复制即可；盲删 `Local State` 无收益且会丢其他状态。
- 证据：`docs/archive/tasks/t066_profile_identity_state/task.md:81` 的未知契约清单；实验脚本与样本在该 task worktree `.scratch/engine_spike/`（gitignore，未入库）。
- 影响：t066 两态 clone 的实现与 AC-003 验收口径；不涉及运行时代码改动。
- 现状：有效

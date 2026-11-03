# p017 t016 收尾 minor 清理

- 来源：t016 遗留（t016_code_f010/f018/f019）
- 内容：删除 `ProfileUpdateRequest` 中重复的 `launch_args` 归一化校验器，明确 explicit null 语义；把 `docs/blueprint/domain.md` 状态图中的 `failed` 改为 `error`，删除 `docs/blueprint/artifacts.md` 中 0755/0644 回退描述；校验 CDP 重连 rearm 的实际 `error` 响应后再置 `_last_rearm_ok=True`。
- 处理：未开
- t024 进展（2026-11-04）：四项中两项文档项已完成 —— domain.md 状态图 `failed` 已改 `error`；artifacts.md 的 0755/0644 回退描述已删除并改 ADR 014 口径。其余两项代码清理（ProfileUpdateRequest 重复校验器、CDP rearm 的 `_last_rearm_ok` 置位时机）仍未开，本条保持 todo。

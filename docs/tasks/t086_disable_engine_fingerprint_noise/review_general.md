# Task review t086（reviewer_focus: 通用）

- task：`t086_disable_engine_fingerprint_noise`
- spec：`docs/tasks/t086_disable_engine_fingerprint_noise/task.md`
- diff_anchor：`ca50c816a1c8b35831040f2f533343486831f2ee`
- target：`git diff ca50c816a1c8b35831040f2f533343486831f2ee`
- round：1
- reviewed_at：2026-11-19T09:35:35+08:00

reviewed_scope: 6f33d9d893d0b7d7

## Findings

无。

## 结论

- 本轮新发现：0 条。
- 未进表的提示：无。
- 总体判断：固定引擎启动路径统一关闭噪声。启动参数规则、环境配置和出站路径继续按原有契约执行。独立重跑目标单测和候选镜像探针，两个 AC 均有复验证据。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`src/backend/cbrowser/runtime_agent/runner.py:610` 在首次启动和重启的共同路径固定传入参数，`runner.py:654` 继续传代理、时区和语言。`tests/unit/test_egress_plan_and_runner_sdk.py:281` 及 launch args 单测共 16 项通过，另直接复验用户传入 true、false 或无值均由 `src/backend/cbrowser/launch_args.py:61` 拒绝。
- AC-002：TICK-VALID，re_verified。候选镜像与当前 `runner.py` 的 SHA-256 一致，独立重跑 `../cbrowser/.scratch/runtime_identity_acceptance/runner_probe.py:28`，首次启动及用同一测试 Profile 数据目录重启后，16×16 棋盘逐像素及 4096 个常量音频样本均准确。

coverage = 2 / 2

verdict: PASS

## Round 2 (2026-11-19T09:46:09+08:00)

reviewed_scope: 6d2552d13fab8b3f

## Findings

无。

## 结论

- 前轮 finding 复核：前轮零 finding。
- 本轮新发现：0 条。
- 未进表的提示：无。
- 总体判断：`tests/e2e/test_t068_fingerprint_gate_e2e.py:315` 将失效的 seed 噪声输入替换为真实时区变更。用例仍要求未批准漂移阻断升级，并在四个上下文逐个对照出现的时区及原值。TLS 证据与同制品比较分支完整保留。独立复跑实际候选镜像上的该 E2E，用例通过。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。生产 Runner、参数白名单和代理断言与首轮已复验内容一致。本轮独立运行 `tests/e2e/test_t068_fingerprint_gate_e2e.py:204`，确认运行时从 `America/New_York` 切换到 `Asia/Tokyo` 后四个上下文均读取到配置值。
- AC-002：TICK-VALID，re_verified。核对本轮 diff，候选镜像与 `src/backend/cbrowser/runtime_agent/runner.py:610` 的噪声策略和首轮逐像素及逐样本实测对应的版本一致。替换用例保留四个上下文中适用的 Canvas 指标采集断言。

coverage = 2 / 2

verdict: PASS

# p065 会话顶栏传输状态多语言本地化与环境状态展示去重

- 来源：用户提出
- 内容：会话页面顶栏传输状态根据用户界面语言进行国际化（如中文显示为正常/恢复中/失败/未知）；环境切换器触发按钮仅保留环境名称、移除状态徽标，状态仅在下拉弹窗列表中显示；顶栏整体呈现为「环境名 运行中 传输 正常」，消除冗余重复。
- 处理：未开
- 时间：2026-11-10T21:05:00+08:00

## 用户原始诉求

1. 传输的四种状态在页面显示时根据用户的语言来。用户设置界面中文时，改成中文。
2. 目前显示为 `nm [运行中] 状态 [运行中] 传输 [ready]`，期望显示为 `环境名 运行中 传输 正常`（或传输正常）。
3. 筛选环境时（顶部环境切换下拉按钮），后面的状态不要直接在顶栏触发按钮上显示，而是在下拉多选/单选列表中显示。

## 当前现状与根因分析

1. **传输状态未国际化**：
    - `SessionHeader.tsx` 中直接将后端的 `transportState` 原样作为 `StatusBadge` 的 `label`（`label={transportState}`），导致无论界面语言是中文还是英文，始终显示为 `ready` / `recovering` / `failed` / `unknown`。
2. **环境切换器与顶栏状态冗余重复**：
    - `EnvironmentSwitcher.tsx` 的触发按钮（`SESS_SWITCHER_TRIGGER`）同时渲染了环境名称 `{current.name}` 和状态徽标 `<StatusBadge tone={status.tone} label={status.label} />`。
    - `SessionHeader.tsx` 紧接着又独立渲染了一套 `<div data-testid="sess-observed-state">`（包含前缀文本「状态」与状态徽标）。
    - 两者并列导致出现 `nm [运行中]` + `状态 [运行中]` 两次重复显示。
3. **环境切换器下拉项状态保留**：
    - 下拉弹窗列表中的条目原本已包含状态徽标，切换器触发按钮移除状态后，下拉列表内依然保留状态以供选择参考。

## 目标改造方案

1. **传输状态（TransportState）国际化支持**：
    - 在 `i18n.tsx` 中补充传输状态的翻译词条：
        - 中文：`ready` -> `正常`（或传输状态文案），`recovering` -> `恢复中`，`failed` -> `失败`，`unknown` -> `未知`。
        - 英文：`ready` -> `Ready`，`recovering` -> `Recovering`，`failed` -> `Failed`，`unknown` -> `Unknown`。
    - `SessionHeader.tsx` 及 `SessionDetailsPanel.tsx` 统一调用本地化翻译转换函数，渲染本地化标签。
2. **环境切换触发按钮简化**：
    - `EnvironmentSwitcher.tsx` 触发按钮中移除 `<StatusBadge>`，仅展示环境名称与下拉指示箭头。
    - 下拉弹窗（Popover）内的环境列表条目保持展示对应的运行状态徽标。
3. **会话顶栏状态组织优化**：
    - 梳理 `SessionHeader.tsx` 顶部排版，呈现为 `[环境切换器(仅名称)]` + `[运行状态徽标]` + `[传输状态徽标]`。
    - 消除视觉上的重复「运行中」，界面清晰呈现为：`环境名` + `运行中` + `传输 正常`。
4. **适配相关测试**：
    - 更新 `SessionHeader.test.tsx` 与 `EnvironmentSwitcher.test.tsx` 中的断言与定位逻辑。

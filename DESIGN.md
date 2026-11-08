---
name: CBrowser Design System
colors:
  primary: "#006EDC"
  light-background: "#F0F5F1"
  dark-background: "#080E0A"
  light-surface: "#F7FBF8"
  dark-surface: "#0E1411"
  light-surface-raised: "#FDFFFD"
  dark-surface-raised: "#141B17"
  light-surface-subtle: "#E9EEEA"
  dark-surface-subtle: "#1B231E"
  light-surface-hover: "#E2E9E4"
  dark-surface-hover: "#232B26"
  light-sidebar: "#E7EDE9"
  dark-sidebar: "#050A07"
  light-stage: "#E4EBE6"
  dark-stage: "#050A07"
  light-on-surface: "#0D1611"
  dark-on-surface: "#E6EDE8"
  light-on-surface-muted: "#48534C"
  dark-on-surface-muted: "#A1ABA4"
  light-on-surface-subtle: "#656F69"
  dark-on-surface-subtle: "#858F88"
  light-outline: "#D3DCD6"
  dark-outline: "#242C28"
  light-outline-strong: "#BAC4BD"
  dark-outline-strong: "#38433C"
  light-accent: "#006EDC"
  dark-accent: "#49A9FF"
  light-accent-soft: "#DAEEFF"
  dark-accent-soft: "#112A43"
  light-on-accent: "#F8FAFD"
  dark-on-accent: "#021020"
  light-danger: "#D02C2E"
  dark-danger: "#F66D64"
  light-danger-soft: "#FFE6E2"
  dark-danger-soft: "#391A17"
  light-warning: "#A76100"
  dark-warning: "#EBAE42"
  light-warning-soft: "#FBEDD1"
  dark-warning-soft: "#33230A"
  light-overlay: "#050B0785"
  dark-overlay: "#010201BD"
  light-focus: "#006EDC"
  dark-focus: "#49A9FF"
  light-group-slate: "#64748B"
  dark-group-slate: "#94A3B8"
  light-group-blue: "#2563EB"
  dark-group-blue: "#60A5FA"
  light-group-teal: "#0D9488"
  dark-group-teal: "#2DD4BF"
  light-group-green: "#16A34A"
  dark-group-green: "#4ADE80"
  light-group-amber: "#D97706"
  dark-group-amber: "#FBBF24"
  light-group-orange: "#EA580C"
  dark-group-orange: "#FB923C"
  light-group-red: "#DC2626"
  dark-group-red: "#F87171"
  light-group-violet: "#7C3AED"
  dark-group-violet: "#A78BFA"
typography:
  headline-lg:
    fontFamily: Space Grotesk Variable
    fontSize: 24px
    fontWeight: 600
    lineHeight: 30px
    letterSpacing: -0.48px
  headline-md:
    fontFamily: Space Grotesk Variable
    fontSize: 18px
    fontWeight: 600
    lineHeight: 23px
  title-sm:
    fontFamily: Space Grotesk Variable
    fontSize: 14px
    fontWeight: 600
    lineHeight: 20px
  body-md:
    fontFamily: Space Grotesk Variable
    fontSize: 13px
    fontWeight: 400
    lineHeight: 20px
  body-sm:
    fontFamily: Space Grotesk Variable
    fontSize: 12px
    fontWeight: 400
    lineHeight: 18px
  label-md:
    fontFamily: Space Grotesk Variable
    fontSize: 12px
    fontWeight: 600
    lineHeight: 12px
  label-sm:
    fontFamily: Space Grotesk Variable
    fontSize: 11px
    fontWeight: 500
    lineHeight: 13px
  mono-md:
    fontFamily: IBM Plex Mono
    fontSize: 12px
    fontWeight: 400
    lineHeight: 17px
  mono-caps:
    fontFamily: IBM Plex Mono
    fontSize: 10px
    fontWeight: 500
    lineHeight: 10px
    letterSpacing: 0.4px
rounded:
  sm: 4px
  md: 7px
  lg: 10px
  xl: 13px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px
components:
  app-light:
    backgroundColor: "{colors.light-background}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  app-dark:
    backgroundColor: "{colors.dark-background}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  sidebar-light:
    backgroundColor: "{colors.light-sidebar}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  sidebar-dark:
    backgroundColor: "{colors.dark-sidebar}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  nav-item-light:
    backgroundColor: "{colors.light-sidebar}"
    textColor: "{colors.light-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  nav-item-dark:
    backgroundColor: "{colors.dark-sidebar}"
    textColor: "{colors.dark-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  nav-item-active-light:
    backgroundColor: "{colors.light-accent-soft}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  nav-item-active-dark:
    backgroundColor: "{colors.dark-accent-soft}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  card-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  card-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  environment-card-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  environment-card-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  modal-light:
    backgroundColor: "{colors.light-surface-raised}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  modal-dark:
    backgroundColor: "{colors.dark-surface-raised}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  popover-light:
    backgroundColor: "{colors.light-surface-raised}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  popover-dark:
    backgroundColor: "{colors.dark-surface-raised}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  toast-light:
    backgroundColor: "{colors.light-surface-raised}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  toast-dark:
    backgroundColor: "{colors.dark-surface-raised}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  tooltip-light:
    backgroundColor: "{colors.light-surface-raised}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  tooltip-dark:
    backgroundColor: "{colors.dark-surface-raised}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  table-header-light:
    backgroundColor: "{colors.light-surface-subtle}"
    textColor: "{colors.light-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  table-header-dark:
    backgroundColor: "{colors.dark-surface-subtle}"
    textColor: "{colors.dark-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  table-row-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  table-row-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  table-row-selected-light:
    backgroundColor: "{colors.light-accent-soft}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  table-row-selected-dark:
    backgroundColor: "{colors.dark-accent-soft}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  table-row-hover-light:
    backgroundColor: "{colors.light-surface-hover}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  table-row-hover-dark:
    backgroundColor: "{colors.dark-surface-hover}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  input-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  input-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  select-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  select-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  search-field-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  search-field-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  checkbox-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  checkbox-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  switch-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  switch-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  icon-button-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  icon-button-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-ghost-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-ghost-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-secondary-light:
    backgroundColor: "{colors.light-surface-subtle}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-secondary-dark:
    backgroundColor: "{colors.dark-surface-subtle}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  menu-item-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  menu-item-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  empty-state-light:
    backgroundColor: "{colors.light-background}"
    textColor: "{colors.light-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  empty-state-dark:
    backgroundColor: "{colors.dark-background}"
    textColor: "{colors.dark-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-primary-light:
    backgroundColor: "{colors.light-accent}"
    textColor: "{colors.light-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-primary-dark:
    backgroundColor: "{colors.dark-accent}"
    textColor: "{colors.dark-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-connect-light:
    backgroundColor: "{colors.light-accent}"
    textColor: "{colors.light-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-connect-dark:
    backgroundColor: "{colors.dark-accent}"
    textColor: "{colors.dark-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-danger-light:
    backgroundColor: "{colors.light-danger}"
    textColor: "{colors.light-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-danger-dark:
    backgroundColor: "{colors.dark-danger}"
    textColor: "{colors.dark-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-stop-light:
    backgroundColor: "{colors.light-danger}"
    textColor: "{colors.light-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-stop-dark:
    backgroundColor: "{colors.dark-danger}"
    textColor: "{colors.dark-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-primary-hover-light:
    backgroundColor: "{colors.light-accent}"
    textColor: "{colors.light-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-primary-hover-dark:
    backgroundColor: "{colors.dark-accent}"
    textColor: "{colors.dark-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-primary-disabled-light:
    backgroundColor: "{colors.light-surface-subtle}"
    textColor: "{colors.light-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-primary-disabled-dark:
    backgroundColor: "{colors.dark-surface-subtle}"
    textColor: "{colors.dark-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-primary-small-light:
    backgroundColor: "{colors.light-accent}"
    textColor: "{colors.light-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-primary-small-dark:
    backgroundColor: "{colors.dark-accent}"
    textColor: "{colors.dark-on-accent}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  status-badge-running-light:
    backgroundColor: "{colors.light-accent-soft}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  status-badge-running-dark:
    backgroundColor: "{colors.dark-accent-soft}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  status-badge-transition-light:
    backgroundColor: "{colors.light-warning-soft}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  status-badge-transition-dark:
    backgroundColor: "{colors.dark-warning-soft}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  status-badge-error-light:
    backgroundColor: "{colors.light-danger-soft}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  status-badge-error-dark:
    backgroundColor: "{colors.dark-danger-soft}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  status-badge-stopped-light:
    backgroundColor: "{colors.light-surface-subtle}"
    textColor: "{colors.light-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  status-badge-stopped-dark:
    backgroundColor: "{colors.dark-surface-subtle}"
    textColor: "{colors.dark-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-chip-light:
    backgroundColor: "{colors.light-surface-subtle}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-chip-dark:
    backgroundColor: "{colors.dark-surface-subtle}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  protocol-chip-light:
    backgroundColor: "{colors.light-surface-subtle}"
    textColor: "{colors.light-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  protocol-chip-dark:
    backgroundColor: "{colors.dark-surface-subtle}"
    textColor: "{colors.dark-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  region-code-light:
    backgroundColor: "{colors.light-surface-subtle}"
    textColor: "{colors.light-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  region-code-dark:
    backgroundColor: "{colors.dark-surface-subtle}"
    textColor: "{colors.dark-on-surface-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  banner-warning-light:
    backgroundColor: "{colors.light-warning-soft}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  banner-warning-dark:
    backgroundColor: "{colors.dark-warning-soft}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  banner-danger-light:
    backgroundColor: "{colors.light-danger-soft}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  banner-danger-dark:
    backgroundColor: "{colors.dark-danger-soft}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  session-header-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  session-header-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  session-stage-light:
    backgroundColor: "{colors.light-stage}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  session-stage-dark:
    backgroundColor: "{colors.dark-stage}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  session-details-panel-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  session-details-panel-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  brand-mark-light:
    backgroundColor: "{colors.primary}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  brand-mark-dark:
    backgroundColor: "{colors.primary}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  divider-light:
    backgroundColor: "{colors.light-outline}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  divider-dark:
    backgroundColor: "{colors.dark-outline}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  scrollbar-thumb-light:
    backgroundColor: "{colors.light-outline-strong}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  scrollbar-thumb-dark:
    backgroundColor: "{colors.dark-outline-strong}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  modal-backdrop-light:
    backgroundColor: "{colors.light-overlay}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  modal-backdrop-dark:
    backgroundColor: "{colors.dark-overlay}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  focus-ring-light:
    backgroundColor: "{colors.light-focus}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  focus-ring-dark:
    backgroundColor: "{colors.dark-focus}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  danger-dot-light:
    backgroundColor: "{colors.light-danger}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  danger-dot-dark:
    backgroundColor: "{colors.dark-danger}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  warning-dot-light:
    backgroundColor: "{colors.light-warning}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  warning-dot-dark:
    backgroundColor: "{colors.dark-warning}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  helper-text-light:
    textColor: "{colors.light-on-surface-subtle}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  helper-text-dark:
    textColor: "{colors.dark-on-surface-subtle}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-slate-light:
    backgroundColor: "{colors.light-group-slate}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-slate-dark:
    backgroundColor: "{colors.dark-group-slate}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-blue-light:
    backgroundColor: "{colors.light-group-blue}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-blue-dark:
    backgroundColor: "{colors.dark-group-blue}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-teal-light:
    backgroundColor: "{colors.light-group-teal}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-teal-dark:
    backgroundColor: "{colors.dark-group-teal}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-green-light:
    backgroundColor: "{colors.light-group-green}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-green-dark:
    backgroundColor: "{colors.dark-group-green}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-amber-light:
    backgroundColor: "{colors.light-group-amber}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-amber-dark:
    backgroundColor: "{colors.dark-group-amber}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-orange-light:
    backgroundColor: "{colors.light-group-orange}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-orange-dark:
    backgroundColor: "{colors.dark-group-orange}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-red-light:
    backgroundColor: "{colors.light-group-red}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-red-dark:
    backgroundColor: "{colors.dark-group-red}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-violet-light:
    backgroundColor: "{colors.light-group-violet}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  group-swatch-violet-dark:
    backgroundColor: "{colors.dark-group-violet}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
---

## Overview

CBrowser 的 UI 设计权威。`DESIGN.md` 是唯一颜色、字体、间距、圆角与组件来源；`npm run design:tokens` 从本文件生成 `src/frontend/src/styles/design_tokens.css`（Tailwind 4 `@theme`）。业务代码只用语义 token，不写颜色字面量。

## Colors

颜色全部以 hex 定义。`primary` 是与模式无关的品牌色，只由 `brand-mark` 引用。其余颜色角色以 `light-` / `dark-` 成对出现，两套角色名集合必须完全相同；组件以 `<component>-light` / `<component>-dark` 成对定义并只引用同模式 token。

### Modes

亮暗双模式约定（plan 4.2）：`primary` 为模式无关色；`light-<role>` 与 `dark-<role>` 成对且角色名集合相同；涉及颜色的组件成对定义 `<component>-light` / `<component>-dark`，状态变体写作 `<component>-<state>-light` / `<component>-<state>-dark`；字体、间距、圆角与模式无关，只定义一次。生成器在生成前校验角色集合相等、无未解析引用、且颜色 token 只能是 `primary` 或带模式前缀。上游规范支持多模式时只改 token 写法与生成器，业务代码不变。

语义：`background` 页面底色、`surface` 卡片/表格/面板、`surface-raised` 浮层、`surface-subtle` 表头/次级区块、`surface-hover` 悬停、`sidebar` 侧栏、`stage` 会话画面区、`outline` 边框、`accent` 唯一强调色、`danger` 危险、`warning` 过渡态、`overlay` 遮罩、`focus` 焦点环、`group-<hue>` 8 个分组色相。状态必须有文字或图标，不能只靠颜色；两种模式下所有文字与背景组合达 WCAG AA（正文 4.5:1）。

## Typography

UI 字体 Space Grotesk Variable，技术数据字体 IBM Plex Mono，均经 `@fontsource` 随前端产物自托管。中文回退栈 `"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif`。最小字号 11px，唯一例外是 mono 大写表头 `mono-caps` 10px。ID、端口、版本号、种子、host 一律用 mono 字体。行高与字距写在 `lineHeight` / `letterSpacing`，生成器只把 `fontSize` 落到 `--text-*` 变量。

## Layout

间距基准 4px（`xs` 到 `2xl`）。侧栏默认 232px，可拖宽 200–360px，折叠为 72px 图标栏，状态存 `cbrowser.sidebar.width` 与 `cbrowser.sidebar.collapsed`。页面内容最大宽度 1600px，内边距 24px（窄屏 16px）。控件高度常规 36px、小号 30px，表格行高 56px。桌面优先（≥1024px），窄屏侧栏改抽屉。动效 160–200ms ease-out，遵守 `prefers-reduced-motion`。

## Elevation & Depth

用深浅不同的底色与边框区分层级，阴影只用于浮层（popover、弹窗、toast）。规范 alpha 没有阴影 token，浮层阴影精确值：`0 12px 32px rgba(0,0,0,0.18)`（亮色）/ `0 12px 32px rgba(0,0,0,0.55)`（暗色），由 WP03 落到 Tailwind 主题。

## Shapes

圆角 `sm 4`（状态标签、分组标签）、`md 7`（按钮、输入框）、`lg 10`（表格、卡片）、`xl 13`（弹窗）、`full`（圆形）。

## Components

组件按 4.2 成对定义：按钮族（`button-primary`、`button-secondary`、`button-ghost`、`button-danger`、`button-connect`、`button-stop` 及 hover/disabled/小号变体）、`icon-button`、`input`、`select`、`search-field`、`checkbox`、`switch`、`nav-item`、`nav-item-active`、`sidebar`、`table-header`、`table-row`、`table-row-selected`、`card`、`environment-card`、四态 `status-badge`、`group-chip`、`protocol-chip`、`region-code`、`modal`、`popover`、`menu-item`、`toast`、`tooltip`、`empty-state`、`banner-warning`、`banner-danger`、`session-header`、`session-stage`、`session-details-panel`、`brand-mark`，以及分组色板 `group-swatch-*` 与纯色标记 `divider` / `scrollbar-thumb` / `modal-backdrop` / `focus-ring` / `danger-dot` / `warning-dot`。Dialog、DropdownMenu、Popover、Tooltip 基于 Radix 原语，Toast 全局单实例。

## Do's and Don'ts

不绘制任何模拟浏览器框；会话画面区只承载 Selkies iframe。每个视图最多一个 `button-primary`。状态必须有文字或图标，不能只靠颜色。ID、端口、版本号、种子、host 一律 mono 字体。两种模式下所有文字与背景组合达 WCAG AA（正文 4.5:1）。不引用外部字体或图标 CDN。不使用 `DESIGN.md` 之外的颜色值；业务代码只用语义 token。会话页快捷键不得占用 Esc，以及会转发给远端浏览器的常用组合键。

## Container sizes

Named spacing tokens (`--spacing-xs` … `--spacing-2xl`) share Tailwind 4's
`--spacing-*` namespace, so a named size utility such as `max-w-lg` resolves
to `var(--spacing-lg)` (16px) instead of a container width. Components must
never use named or arbitrary size utilities; use these semantic container
tokens instead. The generator emits them into the independent
`--container-*` namespace, which cannot be hijacked by spacing tokens.

|token|value|
|---|---|
|dialog|32rem|
|dialog-width|calc(100% - 2rem)|
|dialog-height|90vh|
|panel|28rem|
|hint|20rem|
|page|100rem|
|menu|10rem|
|select|8rem|
|control-sm|1.875rem|

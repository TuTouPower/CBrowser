---
name: CBrowser Spike
colors:
  primary: "#006EDC"
  light-background: "#F0F5F1"
  dark-background: "#080E0A"
  light-surface: "#F7FBF8"
  dark-surface: "#0E1411"
  light-on-surface: "#0D1611"
  dark-on-surface: "#E6EDE8"
  light-accent: "#006EDC"
  dark-accent: "#49A9FF"
  light-on-accent: "#F8FAFD"
  dark-on-accent: "#021020"
typography:
  body-md:
    fontFamily: Space Grotesk Variable
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
  headline-lg:
    fontFamily: Space Grotesk Variable
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.25
  mono-md:
    fontFamily: IBM Plex Mono
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
rounded:
  sm: 4px
  md: 7px
  lg: 10px
spacing:
  sm: 8px
  md: 12px
  lg: 16px
components:
  app-light:
    backgroundColor: "{colors.light-background}"
    textColor: "{colors.light-on-surface}"
  app-dark:
    backgroundColor: "{colors.dark-background}"
    textColor: "{colors.dark-on-surface}"
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
  card-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.lg}"
  card-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.lg}"
  brand-mark:
    backgroundColor: "{colors.primary}"
---

## Overview

CBrowser design system spike.

## Colors

Mode-prefixed color roles; `primary` is the single brand color.

### Modes

`light-*` and `dark-*` roles are paired with identical role-name sets. Components are defined as `<component>-light` / `<component>-dark`.

## Typography

Space Grotesk Variable for UI, IBM Plex Mono for technical data.

## Components

Buttons, cards and app shell defined per mode.

## Do's and Don'ts

Use semantic tokens only.

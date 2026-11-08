import { describe, it, expect } from "vitest";
import { validateAndGenerate, DesignValidationError, assertNoSizeTokenHijack } from "./design_tokens.mjs";

const VALID_SOURCE = `---
name: CBrowser Test Design
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
  mono-md:
    fontFamily: IBM Plex Mono
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
rounded:
  md: 7px
spacing:
  md: 12px
components:
  app-light:
    backgroundColor: "{colors.light-background}"
    textColor: "{colors.light-on-surface}"
  app-dark:
    backgroundColor: "{colors.dark-background}"
    textColor: "{colors.dark-on-surface}"
  card-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-on-surface}"
    rounded: "{rounded.md}"
  card-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-on-surface}"
    rounded: "{rounded.md}"
  button-primary-light:
    backgroundColor: "{colors.light-accent}"
    textColor: "{colors.light-on-accent}"
  button-primary-dark:
    backgroundColor: "{colors.dark-accent}"
    textColor: "{colors.dark-on-accent}"
  brand-mark:
    backgroundColor: "{colors.primary}"
---

## Overview

Test fixture.

## Colors

### Modes

Mode-prefixed roles.

## Typography

Two scales.

## Layout

Spacing.

## Components

Paired components.

## Container sizes

|token|value|
|---|---|
|dialog|32rem|
`;

const withReplacements = (pairs) =>
  pairs.reduce((src, [from, to]) => src.replace(from, to), VALID_SOURCE);

describe("validateAndGenerate", () => {
  it("fails when light-* and dark-* role sets differ", () => {
    const source = withReplacements([
      ['dark-surface: "#0E1411"', 'dark-surface-extra: "#0E1411"'],
      ['"{colors.dark-surface}"', '"{colors.dark-surface-extra}"'],
    ]);
    expect(() => validateAndGenerate(source)).toThrow(DesignValidationError);
    expect(() => validateAndGenerate(source)).toThrow(/role/i);
  });

  it("fails on unresolved token references", () => {
    const source = withReplacements([
      ['"{colors.light-surface}"', '"{colors.light-missing-role}"'],
    ]);
    expect(() => validateAndGenerate(source)).toThrow(DesignValidationError);
  });

  it("fails on a color token without primary or mode prefix", () => {
    const source = withReplacements([
      ['  primary: "#006EDC"', '  primary: "#006EDC"\n  stray: "#123456"'],
      ["  brand-mark:\n    backgroundColor: \"{colors.primary}\"", "  brand-mark:\n    backgroundColor: \"{colors.stray}\""],
    ]);
    expect(() => validateAndGenerate(source)).toThrow(DesignValidationError);
  });

  it("fails when official lint reports errors or warnings", () => {
    const source = withReplacements([
      ['    backgroundColor: "{colors.light-accent}"', '    backgroundColor: "{colors.light-accent}"\n    borderColor: "{colors.light-on-surface}"'],
    ]);
    expect(() => validateAndGenerate(source)).toThrow(DesignValidationError);
  });

  it("deterministically generates Tailwind 4 @theme with light defaults and .dark overrides", () => {
    const css = validateAndGenerate(VALID_SOURCE);
    expect(css).toBe(validateAndGenerate(VALID_SOURCE));
    expect(css).toContain("@theme");
    expect(css).toContain("--color-*: initial");
    expect(css).toContain("--color-background: #f0f5f1;");
    expect(css).toContain(".dark");
    expect(css).toContain("--color-background: #080e0a;");
    expect(css).toContain("--font-ui:");
    expect(css).toContain("--font-mono:");
    expect(css).toContain("--text-body-md: 13px;");
    expect(css).toContain("--radius-md: 7px;");
    expect(css).toContain("--spacing-md: 12px;");
    expect(css).toContain("--container-dialog: 32rem;");
    expect(css).not.toContain("--container-lg");
  });
});


describe("size-token hijack gate", () => {
  it("rejects a named size class resolved from --spacing-*", () => {
    expect(() =>
      assertNoSizeTokenHijack([
        { path: "src/x.tsx", text: '<div className="max-w-lg" />' },
      ]),
    ).toThrow(/Named\/arbitrary size utilities/);
  });

  it("rejects an arbitrary size value", () => {
    expect(() =>
      assertNoSizeTokenHijack([
        { path: "src/x.tsx", text: '<div className="max-w-[32rem]" />' },
      ]),
    ).toThrow(/Named\/arbitrary size utilities/);
  });

  it("accepts semantic container token classes", () => {
    expect(
      assertNoSizeTokenHijack([
        { path: "src/x.tsx", text: '<div className="max-w-dialog p-md" />' },
      ]),
    ).toEqual([]);
  });
});

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  validateAndGenerate,
  DesignValidationError,
  assertNoSizeTokenHijack,
  assertNoColorViolations,
  runLintSources,
  collectSources,
} from "./design_tokens.mjs";

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

  it("fails when body-md or mono-md font family is missing", () => {
    const source = withReplacements([
      ["  body-md:\n    fontFamily: Space Grotesk Variable\n    fontSize: 13px\n    fontWeight: 400\n    lineHeight: 1.5", ""],
    ]);
    expect(() => validateAndGenerate(source)).toThrow(DesignValidationError);
    expect(() => validateAndGenerate(source)).toThrow(/body-md and mono-md font families/);
  });

  it("fails when typography font families mismatch within group", () => {
    const source = withReplacements([
      [
        "  mono-md:\n    fontFamily: IBM Plex Mono\n    fontSize: 12px\n    fontWeight: 400\n    lineHeight: 1.4",
        "  mono-md:\n    fontFamily: IBM Plex Mono\n    fontSize: 12px\n  mono-caps:\n    fontFamily: Other Mono\n    fontSize: 10px",
      ],
    ]);
    expect(() => validateAndGenerate(source)).toThrow(DesignValidationError);
    expect(() => validateAndGenerate(source)).toThrow(/must match mono-md/);
  });

  it("emits typography font-weight, line-height and letter-spacing variables", () => {
    const source = withReplacements([
      [
        '    lineHeight: 1.5',
        '    lineHeight: "1.5"\n    letterSpacing: -0.01em',
      ],
    ]);
    const css = validateAndGenerate(source);
    expect(css).toContain("--text-body-md: 13px;");
    expect(css).toContain("--text-body-md--line-height: 1.5;");
    expect(css).toContain("--text-body-md--font-weight: 400;");
    expect(css).toContain("--text-body-md--letter-spacing: -0.01em;");
  });

  it("parses and emits shadow tokens for light and dark themes", () => {
    const source = withReplacements([
      [
        "## Components",
        `## Elevation & Depth\n\n| token | light | dark |\n|---|---|---|\n| lg | 0 12px 38px rgba(20, 30, 60, 0.2) | 0 12px 38px rgba(0, 0, 0, 0.55) |\n| xl | 0 20px 60px -12px rgba(23, 33, 68, 0.28) | 0 20px 60px -12px rgba(0, 0, 0, 0.65) |\n\n## Components`,
      ],
    ]);
    const css = validateAndGenerate(source);
    expect(css).toContain("--shadow-lg: 0 12px 38px rgba(20, 30, 60, 0.2);");
    expect(css).toContain("--shadow-xl: 0 20px 60px -12px rgba(23, 33, 68, 0.28);");
    const darkSection = css.slice(css.indexOf(".dark {"));
    expect(darkSection).toContain("--shadow-lg: 0 12px 38px rgba(0, 0, 0, 0.55);");
    expect(darkSection).toContain("--shadow-xl: 0 20px 60px -12px rgba(0, 0, 0, 0.65);");
  });

  it("deterministically generates Tailwind 4 @theme with light defaults and .dark overrides", () => {
    const css = validateAndGenerate(VALID_SOURCE);
    expect(css).toBe(validateAndGenerate(VALID_SOURCE));
    expect(css).toContain("@theme");
    expect(css).toContain("--color-*: initial");
    expect(css).toContain("--color-background: #f0f5f1;");
    expect(css).toContain(".dark");
    expect(css).toContain("--color-background: #080e0a;");
    expect(css).toContain('--font-ui: "Space Grotesk Variable", system-ui, "PingFang SC"');
    expect(css).toContain('--font-mono: "IBM Plex Mono", ui-monospace, "SF Mono"');
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

describe("color gate", () => {
  it("rejects a Tailwind default palette color class", () => {
    let error;
    try {
      assertNoColorViolations([
        { path: "src/x.tsx", text: '<div className="bg-red-500" />' },
      ]);
    } catch (caught) {
      error = caught;
    }
    expect(error).toBeInstanceOf(DesignValidationError);
    expect(error.message).toContain("src/x.tsx");
    expect(error.message).toContain("bg-red-500");
  });

  it("rejects neutral/white/hex literals", () => {
    const texts = [
      '<div className="text-gray-500" />',
      '<div className="bg-white" />',
      '<div style={{ color: "#ff00aa" }} />',
    ];
    for (const text of texts) {
      expect(() =>
        assertNoColorViolations([{ path: "src/x.tsx", text }]),
      ).toThrow(/hardcoded color/i);
    }
  });

  it("accepts semantic token classes", () => {
    expect(
      assertNoColorViolations([
        {
          path: "src/x.tsx",
          text: '<div className="bg-surface text-on-surface-muted"><span className="bg-accent" /></div>',
        },
      ]),
    ).toEqual([]);
  });
});

describe("global color gate integration (lint path)", () => {
  let tmp;
  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), "cbrowser-design-lint-"));
  });
  afterEach(() => {
    rmSync(tmp, { recursive: true, force: true });
  });

  const buildSources = (text) => {
    writeFileSync(join(tmp, "a.tsx"), text);
    return collectSources(tmp, "src");
  };

  it("fails the lint gate when a source adds a default palette color class", () => {
    const sources = buildSources('<div className="bg-red-500" />');
    let error;
    try {
      runLintSources(sources);
    } catch (caught) {
      error = caught;
    }
    expect(error).toBeInstanceOf(DesignValidationError);
    expect(error.message).toContain("src/a.tsx");
    expect(error.message).toContain("bg-red-500");
  });

  it("passes the lint gate for semantic token sources", () => {
    const sources = buildSources(
      '<div className="bg-surface text-on-surface-muted" />',
    );
    expect(() => runLintSources(sources)).not.toThrow();
  });
});

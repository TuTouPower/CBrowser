import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  validateAndGenerate,
  DesignValidationError,
  assertNoSizeTokenHijack,
  assertNoColorViolations,
  assertNoNumericSizeOrSpacing,
  assertNoForeignColors,
  generateBrandAssets,
  runLintSources,
  collectSources,
  collectPublicSources,
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

## Shapes

|component|rounded|
|---|---|
|card|md|

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
        "## Shapes",
        `## Elevation & Depth\n\n| token | light | dark |\n|---|---|---|\n| lg | 0 12px 38px rgba(20, 30, 60, 0.2) | 0 12px 38px rgba(0, 0, 0, 0.55) |\n| xl | 0 20px 60px -12px rgba(23, 33, 68, 0.28) | 0 20px 60px -12px rgba(0, 0, 0, 0.65) |\n\n## Shapes`,
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

const withDialogPair = (extra = "") =>
  withReplacements([
    [
      '  brand-mark:\n    backgroundColor: "{colors.primary}"',
      `  brand-mark:\n    backgroundColor: "{colors.primary}"\n  dialog-light:\n    backgroundColor: "{colors.light-surface}"\n    textColor: "{colors.light-on-surface}"\n    rounded: "{rounded.md}"\n    height: "36px"\n    width: "288px"\n  dialog-dark:\n    backgroundColor: "{colors.dark-surface}"\n    textColor: "{colors.dark-on-surface}"\n    rounded: "{rounded.md}"\n    height: "36px"\n    width: "288px"${extra}`,
    ],
    ["|card|md|", "|card|md|\n|dialog|md|"],
  ]);

describe("component-level variables (t059)", () => {
  it("exports radius and size variables for paired components, collapsed across modes", () => {
    const css = validateAndGenerate(withDialogPair());
    expect(css).toContain("--component-card-radius: var(--radius-md);");
    expect(css).toContain("--component-dialog-radius: var(--radius-md);");
    expect(css).toContain("--component-dialog-height: 36px;");
    expect(css).toContain("--component-dialog-width: 288px;");
    expect(css).not.toContain("--component-dialog-light-radius");
    expect(css).not.toContain("--component-dialog-dark-radius");
  });

  it("fails when a -dark entry is not the mode counterpart of its -light entry", () => {
    const source = withDialogPair().replace(
      '  dialog-dark:\n    backgroundColor: "{colors.dark-surface}"',
      '  dialog-dark:\n    backgroundColor: "{colors.dark-background}"',
    );
    expect(() => validateAndGenerate(source)).toThrow(DesignValidationError);
    expect(() => validateAndGenerate(source)).toThrow(/counterpart/);
  });

  it("fails when paired entries disagree on a size field", () => {
    const source = withDialogPair().replace(
      '    rounded: "{rounded.md}"\n    height: "36px"\n    width: "288px"\n---',
      '    rounded: "{rounded.md}"\n    height: "30px"\n    width: "288px"\n---',
    );
    expect(() => validateAndGenerate(source)).toThrow(/counterpart/);
  });
});

describe("Shapes consistency gate (t059)", () => {
  it("fails when components rounded disagrees with the Shapes table", () => {
    const source = withDialogPair().replace("|dialog|md|", "|dialog|lg|");
    expect(() => validateAndGenerate(source)).toThrow(DesignValidationError);
    expect(() => validateAndGenerate(source)).toThrow(/Shapes/);
  });

  it("fails when a rounded-bearing component is missing from the Shapes table", () => {
    const source = withDialogPair().replace("\n|dialog|md|", "");
    expect(() => validateAndGenerate(source)).toThrow(/Shapes/);
  });
});

describe("contrast gate (t059)", () => {
  it("fails when a component text/background pair is below 4.5", () => {
    const source = withDialogPair()
      .replace(
        '  dialog-light:\n    backgroundColor: "{colors.light-surface}"\n    textColor: "{colors.light-on-surface}"',
        '  dialog-light:\n    backgroundColor: "{colors.light-surface}"\n    textColor: "{colors.light-surface}"',
      )
      .replace(
        '  dialog-dark:\n    backgroundColor: "{colors.dark-surface}"\n    textColor: "{colors.dark-on-surface}"',
        '  dialog-dark:\n    backgroundColor: "{colors.dark-surface}"\n    textColor: "{colors.dark-surface}"',
      );
    expect(() => validateAndGenerate(source)).toThrow(DesignValidationError);
    expect(() => validateAndGenerate(source)).toThrow(/contrast/);
  });

  it("applies 4.5 to declared text pairs and 3.0 to declared graphic pairs", () => {
    const pair = "|{colors.light-accent}|{colors.light-background}|KIND|";
    const asText = withDialogPair().replace(
      "## Container sizes",
      `## Contrast\n\n|foreground|background|kind|\n|---|---|---|\n${pair.replace("KIND", "text")}\n\n## Container sizes`,
    );
    expect(() => validateAndGenerate(asText)).toThrow(/contrast/);
    const asGraphic = withDialogPair().replace(
      "## Container sizes",
      `## Contrast\n\n|foreground|background|kind|\n|---|---|---|\n${pair.replace("KIND", "graphic")}\n\n## Container sizes`,
    );
    expect(() => validateAndGenerate(asGraphic)).not.toThrow();
  });
});

const BRAND_SOURCE = () =>
  withReplacements([
    [
      '  primary: "#006EDC"',
      '  primary: "#006EDC"\n  brand-gradient-start: "#00F0FF"\n  brand-gradient-mid: "#0088FF"\n  brand-gradient-end: "#0052FF"\n  light-brand-ink: "#000000"\n  dark-brand-ink: "#FFFFFF"',
    ],
    [
      '  brand-mark:\n    backgroundColor: "{colors.primary}"',
      `  brand-mark:\n    backgroundColor: "{colors.primary}"\n  brand-swatch-gradient-start:\n    backgroundColor: "{colors.brand-gradient-start}"\n  brand-swatch-gradient-mid:\n    backgroundColor: "{colors.brand-gradient-mid}"\n  brand-swatch-gradient-end:\n    backgroundColor: "{colors.brand-gradient-end}"\n  favicon-light:\n    backgroundColor: "{colors.light-brand-ink}"\n  favicon-dark:\n    backgroundColor: "{colors.dark-brand-ink}"`,
    ],
  ]);

describe("brand tokens and generated assets (t059)", () => {
  it("accepts brand-* colors and emits them as mode-independent theme colors", () => {
    const css = validateAndGenerate(BRAND_SOURCE());
    expect(css).toContain("--color-brand-gradient-start: #00f0ff;");
    expect(css).toContain("--color-brand-ink: #000000;");
    const darkSection = css.slice(css.indexOf(".dark {"));
    expect(darkSection).toContain("--color-brand-ink: #ffffff;");
  });

  it("generates logo and favicon assets from brand tokens", () => {
    const assets = generateBrandAssets(BRAND_SOURCE());
    const logo = assets.get("logo.svg");
    expect(logo).toContain('stop-color="#00f0ff"');
    expect(logo).toContain('stop-color="#0088ff"');
    expect(logo).toContain('stop-color="#0052ff"');
    expect(assets.get("favicon-light.svg")).toContain('stroke="#000000"');
    expect(assets.get("favicon-dark.svg")).toContain('stroke="#ffffff"');
    expect(assets.get("favicon.svg")).toContain("stroke: #000000");
    expect(assets.get("favicon.svg")).toContain("stroke: #ffffff");
    expect(assets.get("menubar-icon.svg")).toContain("stroke: #ffffff");
  });

  it("asset colors follow brand token changes", () => {
    const changed = generateBrandAssets(
      BRAND_SOURCE().replace('brand-gradient-start: "#00F0FF"', 'brand-gradient-start: "#112233"'),
    );
    expect(changed.get("logo.svg")).toContain('stop-color="#112233"');
    expect(changed.get("logo.svg")).not.toContain("#00f0ff");
  });
});

describe("public asset color gate (t059)", () => {
  const allowed = new Set(["#00f0ff", "#000000", "#ffffff"]);

  it("accepts literals that are design token values", () => {
    expect(
      assertNoForeignColors(
        [{ path: "public/logo.svg", text: '<stop stop-color="#00F0FF"/>' }],
        allowed,
      ),
    ).toEqual([]);
  });

  it("rejects literals that are not design token values", () => {
    expect(() =>
      assertNoForeignColors(
        [{ path: "public/logo.svg", text: '<stop stop-color="#123456"/>' }],
        allowed,
      ),
    ).toThrow(/non-token color/);
    expect(() =>
      assertNoForeignColors(
        [{ path: "public/theme_boot.js", text: "el.style.background = 'rgb(1, 2, 3)';" }],
        allowed,
      ),
    ).toThrow(/non-token color/);
  });
});

describe("numeric size/spacing gate (t059)", () => {
  const rejects = [
    '<div className="w-72" />',
    '<div className="h-9 px-md" />',
    '<span className="py-0.5" />',
    '<div className="gap-2" />',
    '<div className="max-h-64" />',
    '<div className="inset-0" />',
    '<div className="min-w-0" />',
    '<div className="-mt-2" />',
    // assembled at runtime so Tailwind's source scan does not emit these
    // forbidden utilities as dead CSS from the fixture strings
    '<div className="translate-x-[' + '18px]" />',
    '<div className="w-[' + '100px]" />',
    '<div className="size-4" />',
  ];
  for (const text of rejects) {
    it(`rejects ${text}`, () => {
      expect(() =>
        assertNoNumericSizeOrSpacing([{ path: "src/x.tsx", text }]),
      ).toThrow(/Numeric size\/spacing/);
    });
  }

  const accepts = [
    '<div className="p-md gap-sm" />',
    '<span className="py-2xs" />',
    '<div className="inset-none min-w-none" />',
    '<div className="left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2" />',
    '<div className="h-(--component-button-height) size-(--component-icon-md-size)" />',
    '<div className="translate-x-[calc(var(--component-switch-width)-var(--component-switch-size)-var(--spacing-2xs))]" />',
    '<div className="max-w-dialog w-table-select z-[70]" />',
  ];
  for (const text of accepts) {
    it(`accepts ${text}`, () => {
      expect(
        assertNoNumericSizeOrSpacing([{ path: "src/x.tsx", text }]),
      ).toEqual([]);
    });
  }

  it("fails the lint gate when a source adds a numeric size class", () => {
    let error;
    try {
      runLintSources([{ path: "src/x.tsx", text: '<div className="w-72" />' }]);
    } catch (caught) {
      error = caught;
    }
    expect(error).toBeInstanceOf(DesignValidationError);
    expect(error.message).toContain("w-72");
  });
});

describe("public source collection scope", () => {
  let tmp;
  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), "cbrowser-design-public-"));
  });
  afterEach(() => {
    rmSync(tmp, { recursive: true, force: true });
  });

  it("skips the gitignored selkies vendor drop but keeps app-owned assets", async () => {
    const { mkdirSync } = await import("node:fs");
    mkdirSync(join(tmp, "selkies"), { recursive: true });
    writeFileSync(join(tmp, "selkies", "selkies.svg"), '<svg stop-color="#C34AA2"/>');
    writeFileSync(join(tmp, "logo.svg"), "<svg/>");
    writeFileSync(join(tmp, "theme_boot.js"), "void 0;");
    const paths = collectPublicSources(tmp, "public").map((source) => source.path);
    expect(paths).toEqual(["public/logo.svg", "public/theme_boot.js"]);
  });
});

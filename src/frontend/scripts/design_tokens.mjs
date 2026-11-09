import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { lint } from "@google/design.md/linter";

export class DesignValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = "DesignValidationError";
  }
}

const DESIGN_MD_URL = new URL("../../../DESIGN.md", import.meta.url);
const OUTPUT_CSS_URL = new URL("../src/styles/design_tokens.css", import.meta.url);
const SOURCE_DIR_URL = new URL("../src/", import.meta.url);

const HIJACKED_SIZE_CLASS =
  /\b(?:max-w|min-w|w|max-h|min-h|h|size)-(?:xs|sm|md|lg|xl|2xl)\b/;
const ARBITRARY_SIZE_CLASS =
  /\b(?:max-w|min-w|w|max-h|min-h|h|size)-\[[^\]]+\]/;

const PALETTE_COLOR_CLASS =
  /\b(?:bg|text|border|outline|ring|from|to|via|fill|stroke)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}(?:\/\d{1,3})?\b/;
const PLAIN_COLOR_CLASS =
  /\b(?:bg|text|border|outline|ring|from|to|via|fill|stroke)-(?:white|black)\b/;
const LEGACY_COLOR_CLASS =
  /\b(?:bg|text|border|outline|ring|from|to|via|fill|stroke)-(?:surface-[0-4]|primary-foreground)\b/;
const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch)\s*\([^)]*\)/;

const COLOR_VIOLATION_PATTERNS = [
  PALETTE_COLOR_CLASS,
  PLAIN_COLOR_CLASS,
  LEGACY_COLOR_CLASS,
  COLOR_LITERAL,
];

const CJK_UI_FALLBACK =
  '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif';
const CJK_MONO_FALLBACK =
  '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", monospace';

function dimension(value) {
  if (!value || value.type !== "dimension") return null;
  return `${value.value}${value.unit}`;
}

function parseContainerSizes(source) {
  const start = source.indexOf("## Container sizes");
  if (start < 0) {
    throw new DesignValidationError("DESIGN.md Container sizes section is missing");
  }
  const rest = source.slice(start);
  const next = rest.indexOf("\n## ", 1);
  const body = next >= 0 ? rest.slice(0, next) : rest;
  const rows = [];
  for (const line of body.split("\n")) {
    const match = line.match(/^\|\s*([a-z][a-z0-9-]*)\s*\|\s*([^|]+?)\s*\|/);
    if (match && match[1] !== "token") {
      rows.push([match[1], match[2].trim()]);
    }
  }
  if (rows.length === 0) {
    throw new DesignValidationError("DESIGN.md Container sizes table is empty");
  }
  return rows;
}

function parseShadows(source) {
  const start = source.indexOf("## Elevation & Depth");
  if (start < 0) return [];
  const rest = source.slice(start);
  const next = rest.indexOf("\n## ", 1);
  const body = next >= 0 ? rest.slice(0, next) : rest;
  const rows = [];
  for (const line of body.split("\n")) {
    const match = line.match(/^\|\s*([a-z][a-z0-9-]*)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|/);
    if (match && match[1] !== "token") {
      rows.push([match[1], match[2].trim(), match[3].trim()]);
    }
  }
  return rows;
}

export function assertNoSizeTokenHijack(sources) {
  const offenders = [];
  for (const { path, text } of sources) {
    text.split("\n").forEach((line, index) => {
      if (HIJACKED_SIZE_CLASS.test(line) || ARBITRARY_SIZE_CLASS.test(line)) {
        offenders.push(`${path}:${index + 1}: ${line.trim().slice(0, 140)}`);
      }
    });
  }
  if (offenders.length > 0) {
    throw new DesignValidationError(
      `Named/arbitrary size utilities are forbidden (spacing-token hijack or non-semantic value):\n${offenders
        .map((offender) => `  - ${offender}`)
        .join("\n")}`,
    );
  }
  return offenders;
}

export function assertNoColorViolations(sources) {
  const offenders = [];
  for (const { path, text } of sources) {
    text.split("\n").forEach((line, index) => {
      if (COLOR_VIOLATION_PATTERNS.some((pattern) => pattern.test(line))) {
        offenders.push(`${path}:${index + 1}: ${line.trim().slice(0, 140)}`);
      }
    });
  }
  if (offenders.length > 0) {
    throw new DesignValidationError(
      `Hardcoded colors are forbidden (use semantic tokens):\n${offenders
        .map((offender) => `  - ${offender}`)
        .join("\n")}`,
    );
  }
  return offenders;
}

export function runLintSources(sources) {
  assertNoSizeTokenHijack(sources);
  assertNoColorViolations(sources);
}

export function collectSources(dirPath, baseRel) {
  const out = [];
  for (const entry of readdirSync(dirPath, { withFileTypes: true })) {
    const full = resolve(dirPath, entry.name);
    const rel = `${baseRel}/${entry.name}`;
    if (entry.isDirectory()) {
      if (entry.name === "generated" || entry.name === "styles") continue;
      out.push(...collectSources(full, rel));
    } else if (
      /\.(ts|tsx)$/.test(entry.name) &&
      !/\.(test|spec)\./.test(entry.name) &&
      entry.name !== "test_setup.ts"
    ) {
      out.push({ path: rel, text: readFileSync(full, "utf8") });
    }
  }
  return out;
}

function assertValid(report) {
  const blocking = report.findings.filter(
    (finding) => finding.severity === "error" || finding.severity === "warning",
  );
  if (blocking.length > 0) {
    throw new DesignValidationError(
      `DESIGN.md lint failed:\n${blocking
        .map((finding) => `  - ${finding.path ?? "-"}: ${finding.message}`)
        .join("\n")}`,
    );
  }

  const names = [...report.designSystem.colors.keys()];
  const invalidNames = names.filter(
    (name) => !/^(primary|light-.+|dark-.+)$/.test(name),
  );
  if (invalidNames.length > 0) {
    throw new DesignValidationError(
      `Color tokens must be 'primary' or mode-prefixed (light-* / dark-*): ${invalidNames.join(", ")}`,
    );
  }

  const light = names
    .filter((name) => name.startsWith("light-"))
    .map((name) => name.slice("light-".length))
    .sort();
  const dark = names
    .filter((name) => name.startsWith("dark-"))
    .map((name) => name.slice("dark-".length))
    .sort();
  if (JSON.stringify(light) !== JSON.stringify(dark)) {
    throw new DesignValidationError(
      `light-* / dark-* role sets differ: light=[${light.join(",")}] dark=[${dark.join(",")}]`,
    );
  }

  for (const [name, component] of report.designSystem.components) {
    if (component.unresolvedRefs.length > 0) {
      throw new DesignValidationError(
        `Unresolved references in components.${name}: ${component.unresolvedRefs.join(", ")}`,
      );
    }
  }

  const uiFont = report.designSystem.typography.get("body-md")?.fontFamily;
  const monoFont = report.designSystem.typography.get("mono-md")?.fontFamily;
  if (!uiFont || !monoFont) {
    throw new DesignValidationError(
      "DESIGN.md typography must define body-md and mono-md font families",
    );
  }

  for (const [name, typo] of report.designSystem.typography) {
    if (name.startsWith("mono-")) {
      if (typo.fontFamily !== monoFont) {
        throw new DesignValidationError(
          `typography.${name} fontFamily '${typo.fontFamily}' must match mono-md '${monoFont}'`,
        );
      }
    } else {
      if (typo.fontFamily !== uiFont) {
        throw new DesignValidationError(
          `typography.${name} fontFamily '${typo.fontFamily}' must match body-md '${uiFont}'`,
        );
      }
    }
  }

  return { light, uiFont, monoFont };
}

function generateCss(report, { light, containers, shadows, uiFont, monoFont }) {
  const state = report.designSystem;
  const primary = state.colors.get("primary").hex;
  const lines = ["@theme {", "  --color-*: initial;", `  --color-primary: ${primary};`];

  for (const role of light) {
    lines.push(`  --color-${role}: ${state.colors.get(`light-${role}`).hex};`);
  }

  lines.push(`  --font-ui: "${uiFont}", system-ui, ${CJK_UI_FALLBACK};`);
  lines.push(`  --font-mono: "${monoFont}", ui-monospace, "SF Mono", Menlo, Consolas, ${CJK_MONO_FALLBACK};`);

  for (const [name, value] of state.typography) {
    const size = dimension(value.fontSize);
    if (size) lines.push(`  --text-${name}: ${size};`);
    const lh = dimension(value.lineHeight);
    if (lh) lines.push(`  --text-${name}--line-height: ${lh};`);
    if (value.fontWeight !== undefined) lines.push(`  --text-${name}--font-weight: ${value.fontWeight};`);
    const ls = dimension(value.letterSpacing);
    if (ls) lines.push(`  --text-${name}--letter-spacing: ${ls};`);
  }
  for (const [name, value] of state.rounded) {
    const size = dimension(value);
    if (size) lines.push(`  --radius-${name}: ${size};`);
  }
  for (const [name, value] of state.spacing) {
    const size = dimension(value);
    if (size) lines.push(`  --spacing-${name}: ${size};`);
  }
  for (const [name, lightVal] of shadows) {
    lines.push(`  --shadow-${name}: ${lightVal};`);
  }
  for (const [name, value] of containers) {
    lines.push(`  --container-${name}: ${value};`);
  }

  lines.push("}");
  lines.push("", "@layer utilities {");
  for (const [name] of containers) {
    lines.push(`  .h-${name} { height: var(--container-${name}); }`);
    lines.push(`  .max-h-${name} { max-height: var(--container-${name}); }`);
    lines.push(`  .min-h-${name} { min-height: var(--container-${name}); }`);
  }
  lines.push("}", "", ".dark {");
  lines.push(`  --color-primary: ${primary};`);
  for (const role of light) {
    lines.push(`  --color-${role}: ${state.colors.get(`dark-${role}`).hex};`);
  }
  for (const [name, , darkVal] of shadows) {
    lines.push(`  --shadow-${name}: ${darkVal};`);
  }
  lines.push("}", "");

  return lines.join("\n");
}

export function validateAndGenerate(source) {
  const report = lint(source);
  const { light, uiFont, monoFont } = assertValid(report);
  const containers = parseContainerSizes(source);
  const shadows = parseShadows(source);
  return generateCss(report, { light, containers, shadows, uiFont, monoFont });
}

function main() {
  const mode = process.argv[2] ?? "--write";
  if (!["--write", "--check", "--lint"].includes(mode)) {
    console.error(`Unknown mode: ${mode}`);
    process.exit(2);
  }

  let css;
  try {
    css = validateAndGenerate(readFileSync(DESIGN_MD_URL, "utf8"));
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }

  if (mode === "--lint") {
    const sources = collectSources(fileURLToPath(SOURCE_DIR_URL), "src");
    runLintSources(sources);
    console.log(
      `DESIGN.md lint: 0 error / 0 warning; size+color scan: ${sources.length} files clean`,
    );
    return;
  }
  if (mode === "--check") {
    const current = readFileSync(OUTPUT_CSS_URL, "utf8");
    if (current !== css) {
      console.error("design:check failed: design_tokens.css is stale or edited");
      process.exit(1);
    }
    console.log("design:check: design_tokens.css is up to date");
    return;
  }
  writeFileSync(OUTPUT_CSS_URL, css);
  console.log(`wrote ${fileURLToPath(OUTPUT_CSS_URL)}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}

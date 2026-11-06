import { readFileSync, writeFileSync } from "node:fs";
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

const CJK_FALLBACK =
  '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif';

function dimension(value) {
  if (!value || value.type !== "dimension") return null;
  return `${value.value}${value.unit}`;
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

  return { light };
}

function generateCss(report, { light }) {
  const state = report.designSystem;
  const primary = state.colors.get("primary").hex;
  const lines = ["@theme {", "  --color-*: initial;", `  --color-primary: ${primary};`];

  for (const role of light) {
    lines.push(`  --color-${role}: ${state.colors.get(`light-${role}`).hex};`);
  }

  lines.push(`  --font-ui: "Space Grotesk Variable", ${CJK_FALLBACK};`);
  lines.push(`  --font-mono: "IBM Plex Mono", ${CJK_FALLBACK};`);

  for (const [name, value] of state.typography) {
    const size = dimension(value.fontSize);
    if (size) lines.push(`  --text-${name}: ${size};`);
  }
  for (const [name, value] of state.rounded) {
    const size = dimension(value);
    if (size) lines.push(`  --radius-${name}: ${size};`);
  }
  for (const [name, value] of state.spacing) {
    const size = dimension(value);
    if (size) lines.push(`  --spacing-${name}: ${size};`);
  }

  lines.push("}", "", ".dark {");
  lines.push(`  --color-primary: ${primary};`);
  for (const role of light) {
    lines.push(`  --color-${role}: ${state.colors.get(`dark-${role}`).hex};`);
  }
  lines.push("}", "");

  return lines.join("\n");
}

export function validateAndGenerate(source) {
  const report = lint(source);
  const { light } = assertValid(report);
  return generateCss(report, { light });
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
    console.log("DESIGN.md lint: 0 error / 0 warning");
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

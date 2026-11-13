import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
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
const PUBLIC_DIR_URL = new URL("../public/", import.meta.url);
const INDEX_HTML_URL = new URL("../index.html", import.meta.url);

const HIJACKED_SIZE_CLASS =
  /\b(?:max-w|min-w|w|max-h|min-h|h|size)-(?:xs|sm|md|lg|xl|2xl)\b/;
const ARBITRARY_SIZE_CLASS =
  /\b(?:max-w|min-w|w|max-h|min-h|h|size)-\[[^\]]+\]/;

const SIZE_SPACING_FAMILY =
  "p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|gap-x|gap-y|gap|space-x|space-y|inset-x|inset-y|inset|top|right|bottom|left|translate-x|translate-y|min-w|max-w|min-h|max-h|w|h|size";
const NUMERIC_SIZE_SPACING_CLASS = new RegExp(
  `(?<![\\w-])-?(?:${SIZE_SPACING_FAMILY})-\\d+(?:\\.\\d+)?(?![\\w/-])`,
);
const ARBITRARY_SIZE_SPACING_CLASS = new RegExp(
  `(?<![\\w-])-?(?:${SIZE_SPACING_FAMILY})-\\[([^\\]]+)\\]`,
  "g",
);

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

function sectionBody(source, heading) {
  const start = source.indexOf(heading);
  if (start < 0) return null;
  const rest = source.slice(start);
  const next = rest.indexOf("\n## ", 1);
  return next >= 0 ? rest.slice(0, next) : rest;
}

function parseContainerSizes(source) {
  const body = sectionBody(source, "## Container sizes");
  if (body === null) {
    throw new DesignValidationError("DESIGN.md Container sizes section is missing");
  }
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
  const body = sectionBody(source, "## Elevation & Depth");
  if (body === null) return [];
  const rows = [];
  for (const line of body.split("\n")) {
    const match = line.match(/^\|\s*([a-z][a-z0-9-]*)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|/);
    if (match && match[1] !== "token") {
      rows.push([match[1], match[2].trim(), match[3].trim()]);
    }
  }
  return rows;
}

function parseShapesTable(source) {
  const body = sectionBody(source, "## Shapes");
  if (body === null) return null;
  const rows = new Map();
  for (const line of body.split("\n")) {
    const match = line.match(/^\|\s*([a-z][a-z0-9-]*)\s*\|\s*([a-z0-9]+)\s*\|/);
    if (match && match[1] !== "component") {
      rows.set(match[1], match[2]);
    }
  }
  return rows;
}

function parseContrastPairs(source) {
  const body = sectionBody(source, "## Contrast");
  if (body === null) return [];
  const pairs = [];
  for (const line of body.split("\n")) {
    const match = line.match(
      /^\|\s*\{colors\.([a-z0-9-]+)\}\s*\|\s*\{colors\.([a-z0-9-]+)\}\s*\|\s*(text|graphic)\s*\|/,
    );
    if (match) {
      pairs.push({ foreground: match[1], background: match[2], kind: match[3] });
    }
  }
  return pairs;
}

// The official linter resolves component references to values; the declared
// reference strings themselves (which token each property points at) are only
// visible in the front matter text. Parse them directly so pairing, Shapes
// consistency and component-variable export work on declarations, not on
// resolved values that different tokens can share.
function parseComponentRefs(source) {
  const frontMatter = source.match(/^---\n([\s\S]*?)\n---/);
  if (!frontMatter) {
    throw new DesignValidationError("DESIGN.md front matter is missing");
  }
  const components = new Map();
  let inComponents = false;
  let current = null;
  for (const line of frontMatter[1].split("\n")) {
    if (/^[a-z-]+:/.test(line)) {
      inComponents = line.startsWith("components:");
      current = null;
      continue;
    }
    if (!inComponents) continue;
    const nameMatch = line.match(/^ {2}([a-z][a-z0-9-]*):\s*$/);
    if (nameMatch) {
      current = new Map();
      components.set(nameMatch[1], current);
      continue;
    }
    const propMatch = line.match(/^ {4}([a-zA-Z]+):\s*(.+?)\s*$/);
    if (propMatch && current) {
      let value = propMatch[2];
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      current.set(propMatch[1], value);
    }
  }
  return components;
}

function refTarget(value) {
  const match = /^\{([a-z-]+)\.([a-z0-9-]+)\}$/.exec(value ?? "");
  return match ? { namespace: match[1], key: match[2] } : null;
}

function componentBase(name) {
  if (name.endsWith("-light")) return name.slice(0, -"-light".length);
  if (name.endsWith("-dark")) return name.slice(0, -"-dark".length);
  return name;
}

function assertRefsMatchReport(refs, report) {
  const declared = [...refs.keys()].sort();
  const parsed = [...report.designSystem.components.keys()].sort();
  if (JSON.stringify(declared) !== JSON.stringify(parsed)) {
    throw new DesignValidationError(
      `Component declarations parsed from front matter differ from the linter report: front matter=[${declared.join(",")}] linter=[${parsed.join(",")}]`,
    );
  }
}

function assertComponentPairs(refs) {
  for (const [name, props] of refs) {
    let lightName;
    let darkName;
    if (name.endsWith("-light")) {
      lightName = name;
      darkName = `${componentBase(name)}-dark`;
    } else if (name.endsWith("-dark")) {
      darkName = name;
      lightName = `${componentBase(name)}-light`;
    } else {
      continue;
    }
    if (!refs.has(lightName) || !refs.has(darkName)) {
      throw new DesignValidationError(
        `components.${name} has no mode counterpart (expected ${lightName} / ${darkName} pair)`,
      );
    }
    if (name === darkName) continue;
    const lightProps = refs.get(lightName);
    const darkProps = refs.get(darkName);
    const keys = new Set([...lightProps.keys(), ...darkProps.keys()]);
    for (const prop of keys) {
      const lightValue = lightProps.get(prop);
      const darkValue = darkProps.get(prop);
      const lightRef = refTarget(lightValue);
      let expected = lightValue;
      if (lightRef && lightRef.namespace === "colors" && lightRef.key.startsWith("light-")) {
        expected = `{colors.dark-${lightRef.key.slice("light-".length)}}`;
      }
      if (darkValue !== expected) {
        throw new DesignValidationError(
          `components.${darkName}.${prop} '${darkValue}' is not the mode counterpart of components.${lightName}.${prop} '${lightValue}' (expected '${expected}')`,
        );
      }
    }
  }
}

function assertShapesConsistency(source, refs) {
  const table = parseShapesTable(source);
  const roundedBases = new Map();
  for (const [name, props] of refs) {
    const rounded = props.get("rounded");
    if (rounded === undefined) continue;
    const target = refTarget(rounded);
    if (!target || target.namespace !== "rounded") {
      throw new DesignValidationError(
        `Shapes consistency: components.${name}.rounded must reference a rounded token, got '${rounded}'`,
      );
    }
    roundedBases.set(componentBase(name), target.key);
  }
  if (roundedBases.size === 0) return;
  if (table === null || table.size === 0) {
    throw new DesignValidationError(
      "Shapes consistency: DESIGN.md Shapes section must declare a component rounded table",
    );
  }
  for (const [base, key] of roundedBases) {
    if (!table.has(base)) {
      throw new DesignValidationError(
        `Shapes consistency: component '${base}' is missing from the Shapes table`,
      );
    }
    if (table.get(base) !== key) {
      throw new DesignValidationError(
        `Shapes consistency: components '${base}' rounded is '{rounded.${key}}' but the Shapes table declares '${table.get(base)}'`,
      );
    }
  }
  for (const base of table.keys()) {
    if (!roundedBases.has(base)) {
      throw new DesignValidationError(
        `Shapes consistency: Shapes table row '${base}' has no component with a rounded reference`,
      );
    }
  }
}

function contrastRatio(a, b) {
  const [hi, lo] = a.luminance >= b.luminance ? [a, b] : [b, a];
  return (hi.luminance + 0.05) / (lo.luminance + 0.05);
}

function assertContrast(report, source) {
  const colors = report.designSystem.colors;
  const failures = [];
  const check = (label, foreground, background, threshold) => {
    const ratio = contrastRatio(foreground, background);
    if (ratio < threshold) {
      failures.push(
        `${label}: ${foreground.hex} on ${background.hex} = ${ratio.toFixed(2)}:1 < ${threshold}:1`,
      );
    }
  };
  for (const [name, component] of report.designSystem.components) {
    const props = new Map(component.properties);
    const background = props.get("backgroundColor");
    const foreground = props.get("textColor");
    if (background && foreground) {
      check(`components.${name} text`, foreground, background, 4.5);
    } else if (foreground) {
      const mode = name.endsWith("-dark") ? "dark" : "light";
      for (const role of ["background", "surface", "surface-raised", "surface-subtle"]) {
        const under = colors.get(`${mode}-${role}`);
        if (under) {
          check(`components.${name} text on ${mode}-${role}`, foreground, under, 4.5);
        }
      }
    }
  }
  for (const pair of parseContrastPairs(source)) {
    const foreground = colors.get(pair.foreground);
    const background = colors.get(pair.background);
    if (!foreground || !background) {
      throw new DesignValidationError(
        `Contrast pair references an unknown color: {colors.${pair.foreground}} on {colors.${pair.background}}`,
      );
    }
    check(
      `declared ${pair.kind} pair ${pair.foreground} on ${pair.background}`,
      foreground,
      background,
      pair.kind === "graphic" ? 3.0 : 4.5,
    );
  }
  if (failures.length > 0) {
    throw new DesignValidationError(
      `WCAG contrast gate failed:\n${failures.map((failure) => `  - contrast: ${failure}`).join("\n")}`,
    );
  }
}

const COMPONENT_VAR_PROPS = [
  ["rounded", "radius"],
  ["height", "height"],
  ["width", "width"],
  ["size", "size"],
];

function cssVarForRef(target) {
  if (target.namespace === "colors") return `var(--color-${target.key})`;
  if (target.namespace === "rounded") return `var(--radius-${target.key})`;
  if (target.namespace === "spacing") return `var(--spacing-${target.key})`;
  return `var(--${target.namespace}-${target.key})`;
}

function componentVariables(refs) {
  const lines = [];
  for (const [name, props] of refs) {
    if (name.endsWith("-dark")) continue;
    const base = componentBase(name);
    for (const [prop, suffix] of COMPONENT_VAR_PROPS) {
      const value = props.get(prop);
      if (value === undefined) continue;
      const target = refTarget(value);
      lines.push(
        `  --component-${base}-${suffix}: ${target ? cssVarForRef(target) : value};`,
      );
    }
  }
  return lines;
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

function isTokenOnlyArbitrary(content) {
  const withoutVars = content.replace(/var\(--[\w-]+\)/g, "");
  const withoutFunctions = withoutVars.replace(/\b(?:calc|min|max|clamp)\b/g, "");
  return /^[\s()*+/,._-]*$/.test(withoutFunctions);
}

export function assertNoNumericSizeOrSpacing(sources) {
  const offenders = [];
  for (const { path, text } of sources) {
    text.split("\n").forEach((line, index) => {
      if (NUMERIC_SIZE_SPACING_CLASS.test(line)) {
        offenders.push(`${path}:${index + 1}: ${line.trim().slice(0, 140)}`);
        return;
      }
      for (const match of line.matchAll(ARBITRARY_SIZE_SPACING_CLASS)) {
        if (!isTokenOnlyArbitrary(match[1])) {
          offenders.push(`${path}:${index + 1}: ${line.trim().slice(0, 140)}`);
          return;
        }
      }
    });
  }
  if (offenders.length > 0) {
    throw new DesignValidationError(
      `Numeric size/spacing utilities are forbidden (use spacing, container or component tokens):\n${offenders
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

function normalizeHex(literal) {
  const hex = literal.slice(1).toLowerCase();
  if (hex.length === 3) return `#${hex.split("").map((c) => c + c).join("")}`;
  if (hex.length === 4) return `#${hex.split("").map((c) => c + c).join("")}`;
  return `#${hex}`;
}

export function assertNoForeignColors(sources, allowedHexes) {
  const offenders = [];
  for (const { path, text } of sources) {
    text.split("\n").forEach((line, index) => {
      for (const match of line.matchAll(new RegExp(COLOR_LITERAL.source, "g"))) {
        const literal = match[0];
        const isTokenValue =
          literal.startsWith("#") && allowedHexes.has(normalizeHex(literal));
        if (!isTokenValue) {
          offenders.push(`${path}:${index + 1}: ${line.trim().slice(0, 140)}`);
          return;
        }
      }
    });
  }
  if (offenders.length > 0) {
    throw new DesignValidationError(
      `Public assets contain a non-token color (only DESIGN.md token values may appear; regenerate assets with design:tokens):\n${offenders
        .map((offender) => `  - ${offender}`)
        .join("\n")}`,
    );
  }
  return offenders;
}

export function runLintSources(sources) {
  assertNoSizeTokenHijack(sources);
  assertNoNumericSizeOrSpacing(sources);
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

export function collectPublicSources(dirPath, baseRel) {
  const out = [];
  for (const entry of readdirSync(dirPath, { withFileTypes: true })) {
    const full = resolve(dirPath, entry.name);
    const rel = `${baseRel}/${entry.name}`;
    if (entry.isDirectory()) {
      // public/selkies is a gitignored vendor drop populated by the build
      // (official Selkies web assets); its colors are Selkies' own branding,
      // not CBrowser design tokens, so it stays out of the color scan.
      if (entry.name === "selkies") continue;
      out.push(...collectPublicSources(full, rel));
    } else if (/\.(svg|html|js)$/.test(entry.name)) {
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
    (name) => !/^(primary|brand-.+|light-.+|dark-.+)$/.test(name),
  );
  if (invalidNames.length > 0) {
    throw new DesignValidationError(
      `Color tokens must be 'primary', a 'brand-*' token or mode-prefixed (light-* / dark-*): ${invalidNames.join(", ")}`,
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

function generateCss(report, { light, containers, shadows, uiFont, monoFont, componentVars }) {
  const state = report.designSystem;
  const singles = [...state.colors.keys()].filter(
    (name) => !name.startsWith("light-") && !name.startsWith("dark-"),
  );
  const lines = ["@theme {", "  --color-*: initial;"];
  for (const name of singles) {
    lines.push(`  --color-${name}: ${state.colors.get(name).hex};`);
  }

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
  if (componentVars.length > 0) {
    lines.push("", ":root {");
    lines.push(...componentVars);
    lines.push("}");
  }
  lines.push("", "@layer utilities {");
  for (const [name] of containers) {
    lines.push(`  .h-${name} { height: var(--container-${name}); }`);
    lines.push(`  .max-h-${name} { max-height: var(--container-${name}); }`);
    lines.push(`  .min-h-${name} { min-height: var(--container-${name}); }`);
  }
  lines.push("}", "", ".dark {");
  for (const name of singles) {
    lines.push(`  --color-${name}: ${state.colors.get(name).hex};`);
  }
  for (const role of light) {
    lines.push(`  --color-${role}: ${state.colors.get(`dark-${role}`).hex};`);
  }
  for (const [name, , darkVal] of shadows) {
    lines.push(`  --shadow-${name}: ${darkVal};`);
  }
  lines.push("}", "");

  return lines.join("\n");
}

// Fingerprint geometry shared by the logo and the favicons. Only colors come
// from brand tokens; the geometry is the assets' own spec and changes only by
// editing this table together with DESIGN.md.
const BRAND_PATHS = [
  "M 318 463 A 202 202 0 0 1 688 489",
  "M 329 610 A 737 737 0 0 0 342.6 548.1 A 163 163 0 1 1 661.4 615.9 A 1063 1063 0 0 1 655 638",
  "M 351 724 A 800 800 0 0 0 404.2 561.2 A 100 100 0 1 1 599.8 602.8 A 1000 1000 0 0 1 564 724",
  "M 407 758 A 863 863 0 0 0 465.8 574.3 A 37 37 0 1 1 538.2 589.7 A 937 937 0 0 1 485 756",
];

function brandAssetFiles(report) {
  const colors = report.designSystem.colors;
  const start = colors.get("brand-gradient-start");
  const mid = colors.get("brand-gradient-mid");
  const end = colors.get("brand-gradient-end");
  const lightInk = colors.get("light-brand-ink");
  const darkInk = colors.get("dark-brand-ink");
  if (!start || !mid || !end || !lightInk || !darkInk) return new Map();
  const paths = BRAND_PATHS.map((d) => `    <path d="${d}"/>`).join("\n");
  const files = new Map();
  files.set(
    "logo.svg",
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="260 316 480 480" width="100%" height="100%" fill="none">
  <defs>
    <!-- 亮蓝色指纹渐变（纯蓝色系，零紫色） -->
    <linearGradient id="brand-gradient" x1="280" y1="340" x2="720" y2="780" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="${start.hex}"/>
      <stop offset="50%" stop-color="${mid.hex}"/>
      <stop offset="100%" stop-color="${end.hex}"/>
    </linearGradient>
  </defs>

  <!-- 中心指纹线条（无边框，饱满清晰） -->
  <g stroke="url(#brand-gradient)" stroke-width="40" stroke-linecap="round" stroke-linejoin="round">
${paths}
  </g>
</svg>
`,
  );
  files.set(
    "favicon.svg",
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="260 316 480 480" width="100%" height="100%" fill="none">
  <style>
    path { stroke: ${lightInk.hex}; }
    @media (prefers-color-scheme: dark) {
      path { stroke: ${darkInk.hex}; }
    }
  </style>

  <!-- 网页 Favicon（深色模式纯白、亮色模式纯黑，无边框） -->
  <g stroke-width="40" stroke-linecap="round" stroke-linejoin="round">
${paths}
  </g>
</svg>
`,
  );
  files.set(
    "favicon-light.svg",
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="260 316 480 480" width="100%" height="100%" fill="none">
  <!-- 网页亮色模式 Favicon（纯黑指纹，无边框） -->
  <g stroke="${lightInk.hex}" stroke-width="40" stroke-linecap="round" stroke-linejoin="round">
${paths}
  </g>
</svg>
`,
  );
  files.set(
    "favicon-dark.svg",
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="260 316 480 480" width="100%" height="100%" fill="none">
  <!-- 网页深色模式 Favicon（纯白指纹，无边框） -->
  <g stroke="${darkInk.hex}" stroke-width="40" stroke-linecap="round" stroke-linejoin="round">
${paths}
  </g>
</svg>
`,
  );
  files.set(
    "menubar-icon.svg",
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="260 316 480 480" width="100%" height="100%" fill="none">
  <style>
    path { stroke: ${darkInk.hex}; }
    @media (prefers-color-scheme: light) {
      path { stroke: ${lightInk.hex}; }
    }
  </style>

  <!-- 菜单栏纯指纹线条（无边框，自适应深浅色） -->
  <g stroke-width="40" stroke-linecap="round" stroke-linejoin="round">
${paths}
  </g>
</svg>
`,
  );
  return files;
}

function processDesign(source) {
  const report = lint(source);
  const meta = assertValid(report);
  const refs = parseComponentRefs(source);
  assertRefsMatchReport(refs, report);
  assertComponentPairs(refs);
  assertShapesConsistency(source, refs);
  assertContrast(report, source);
  const containers = parseContainerSizes(source);
  const shadows = parseShadows(source);
  const css = generateCss(report, {
    ...meta,
    containers,
    shadows,
    componentVars: componentVariables(refs),
  });
  return { css, report };
}

export function validateAndGenerate(source) {
  return processDesign(source).css;
}

export function generateBrandAssets(source) {
  return brandAssetFiles(processDesign(source).report);
}

function collectGateSources() {
  const sources = collectSources(fileURLToPath(SOURCE_DIR_URL), "src");
  const publicSources = collectPublicSources(fileURLToPath(PUBLIC_DIR_URL), "public");
  publicSources.push({
    path: "index.html",
    text: readFileSync(INDEX_HTML_URL, "utf8"),
  });
  return { sources, publicSources };
}

function runSourceGates(report) {
  const { sources, publicSources } = collectGateSources();
  runLintSources(sources);
  const allowedHexes = new Set(
    [...report.designSystem.colors.values()].map((color) => color.hex),
  );
  assertNoForeignColors(publicSources, allowedHexes);
  return { sources, publicSources };
}

function main() {
  const mode = process.argv[2] ?? "--write";
  if (!["--write", "--check", "--lint"].includes(mode)) {
    console.error(`Unknown mode: ${mode}`);
    process.exit(2);
  }

  let processed;
  try {
    processed = processDesign(readFileSync(DESIGN_MD_URL, "utf8"));
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
  const { css, report } = processed;
  const assets = brandAssetFiles(report);

  if (mode === "--lint") {
    const { sources, publicSources } = runSourceGates(report);
    console.log(
      `DESIGN.md lint: 0 error / 0 warning; size+color scan: ${sources.length} source files + ${publicSources.length} public files clean`,
    );
    return;
  }
  if (mode === "--check") {
    runSourceGates(report);
    const current = readFileSync(OUTPUT_CSS_URL, "utf8");
    if (current !== css) {
      console.error("design:check failed: design_tokens.css is stale or edited");
      process.exit(1);
    }
    for (const [name, content] of assets) {
      const assetUrl = new URL(`../public/${name}`, import.meta.url);
      if (!existsSync(assetUrl) || readFileSync(assetUrl, "utf8") !== content) {
        console.error(`design:check failed: public/${name} is stale or edited (regenerate with design:tokens)`);
        process.exit(1);
      }
    }
    console.log("design:check: design_tokens.css and brand assets are up to date");
    return;
  }
  writeFileSync(OUTPUT_CSS_URL, css);
  for (const [name, content] of assets) {
    writeFileSync(new URL(`../public/${name}`, import.meta.url), content);
  }
  console.log(`wrote ${fileURLToPath(OUTPUT_CSS_URL)}`);
  if (assets.size > 0) {
    console.log(`wrote ${assets.size} brand assets in public/`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import vm from "node:vm";
import { describe, it, expect } from "vitest";

const BOOT_PATH = resolve(process.cwd(), "public/theme_boot.js");
const INDEX_PATH = resolve(process.cwd(), "index.html");

function runBoot(stored, prefersDark) {
  const classes = new Set();
  const root = {
    classList: {
      toggle: (name, on) => {
        if (on) classes.add(name);
        else classes.delete(name);
      },
    },
    style: {},
  };
  const context = {
    document: { documentElement: root },
    localStorage: { getItem: () => stored },
    window: { matchMedia: () => ({ matches: prefersDark }) },
  };
  vm.runInNewContext(readFileSync(BOOT_PATH, "utf8"), context);
  return { classes, colorScheme: root.style.colorScheme };
}

describe("theme_boot.js", () => {
  it("defaults to dark with no stored preference", () => {
    const { classes, colorScheme } = runBoot(null, false);
    expect([...classes]).toEqual(["dark"]);
    expect(colorScheme).toBe("dark");
  });

  it("honours an explicit light preference", () => {
    const { classes, colorScheme } = runBoot("light", true);
    expect([...classes]).toEqual(["light"]);
    expect(colorScheme).toBe("light");
  });

  it("follows prefers-color-scheme in system mode", () => {
    expect(runBoot("system", true).classes.has("dark")).toBe(true);
    expect(runBoot("system", false).classes.has("light")).toBe(true);
  });

  it("is an external classic script in head with no inline scripts in index.html", () => {
    const html = readFileSync(INDEX_PATH, "utf8");
    const head = html.slice(html.indexOf("<head>"), html.indexOf("</head>"));
    expect(head).toContain('<script src="/theme_boot.js"></script>');
    expect(head.indexOf("<script")).toBeLessThan(html.indexOf("</head>"));
    expect(html).not.toContain("<html lang=\"en\" class=");
    expect(/<script(?![^>]*\bsrc=)[^>]*>[\s\S]*?<\/script>/i.test(html)).toBe(false);
  });
});

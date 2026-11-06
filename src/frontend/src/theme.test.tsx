import { describe, it, expect, beforeEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { ThemeProvider, useTheme } from "./theme";

let systemDark = false;
const listeners = new Set<() => void>();

function installMatchMedia() {
  listeners.clear();
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      get matches() {
        return query === "(prefers-color-scheme: dark)" ? systemDark : false;
      },
      media: query,
      addEventListener: (_event: string, cb: () => void) => listeners.add(cb),
      removeEventListener: (_event: string, cb: () => void) => listeners.delete(cb),
      addListener: (cb: () => void) => listeners.add(cb),
      removeListener: (cb: () => void) => listeners.delete(cb),
    })),
  });
}

function emitSystemChange(dark: boolean) {
  systemDark = dark;
  act(() => {
    for (const cb of listeners) cb();
  });
}

function Probe() {
  const { preference, resolved, setPreference } = useTheme();
  return (
    <div>
      <span data-testid="preference">{preference}</span>
      <span data-testid="resolved">{resolved}</span>
      <button type="button" onClick={() => setPreference("light")}>
        to-light
      </button>
      <button type="button" onClick={() => setPreference("dark")}>
        to-dark
      </button>
      <button type="button" onClick={() => setPreference("system")}>
        to-system
      </button>
    </div>
  );
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    localStorage.clear();
    systemDark = false;
    installMatchMedia();
    document.documentElement.className = "";
    document.documentElement.style.colorScheme = "";
  });

  it("defaults to dark and applies the class plus color-scheme before any interaction", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("preference")).toHaveTextContent("dark");
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("persists three-state preference and applies resolved theme immediately", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByText("to-light"));
    expect(localStorage.getItem("cbrowser.theme")).toBe("light");
    expect(screen.getByTestId("resolved")).toHaveTextContent("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("light");

    fireEvent.click(screen.getByText("to-system"));
    expect(localStorage.getItem("cbrowser.theme")).toBe("system");
    expect(screen.getByTestId("resolved")).toHaveTextContent("light");

    emitSystemChange(true);
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    fireEvent.click(screen.getByText("to-dark"));
    expect(localStorage.getItem("cbrowser.theme")).toBe("dark");
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");
  });

  it("reads an existing stored preference on mount", () => {
    localStorage.setItem("cbrowser.theme", "light");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("preference")).toHaveTextContent("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
  });
});

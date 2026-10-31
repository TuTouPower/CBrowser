import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

// Builds the Selkies client adapter as a classic (IIFE) script so it can be
// injected before the official Selkies module bundle.
export default defineConfig({
  publicDir: false,
  build: {
    outDir: "dist/selkies",
    emptyOutDir: false,
    target: "es2020",
    minify: false,
    sourcemap: false,
    lib: {
      entry: fileURLToPath(
        new URL(
          "./src/features/browser-session/selkies_adapter_entry.ts",
          import.meta.url
        )
      ),
      name: "CBrowserSelkiesAdapter",
      formats: ["iife"],
      fileName: () => "selkies_adapter.js",
    },
  },
});

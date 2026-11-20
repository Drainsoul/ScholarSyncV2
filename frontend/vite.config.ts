import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  base: "/static/dist/",
  build: {
    outDir: resolve(root, "../static/dist"),
    emptyOutDir: true,
    manifest: true,
    assetsInlineLimit: 0,
    rollupOptions: {
      input: {
        main: resolve(root, "src/main.ts"),
        kit: resolve(root, "src/kit.ts"),
      },
      output: {
        // pdf.js's worker ships as .mjs; .js is served as JavaScript by every static server
        // (Windows and some proxies serve .mjs as text/plain, which a module worker refuses).
        assetFileNames: (asset) =>
          asset.names.some((name) => name.endsWith(".mjs"))
            ? "assets/[name]-[hash].js"
            : "assets/[name]-[hash][extname]",
      },
    },
  },
  server: { origin: "http://localhost:5173" },
});

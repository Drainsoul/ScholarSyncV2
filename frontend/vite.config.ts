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
    },
  },
  server: { origin: "http://localhost:5173" },
});

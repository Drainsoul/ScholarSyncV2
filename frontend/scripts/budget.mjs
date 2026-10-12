// Fails the build when the gzipped JS + CSS referenced by the Vite manifest exceed the budget (spec §12).
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const LIMIT_BYTES = 100 * 1024;
const dist = resolve(dirname(fileURLToPath(import.meta.url)), "../../static/dist");
const manifest = JSON.parse(readFileSync(resolve(dist, ".vite/manifest.json"), "utf8"));

const files = new Set();
for (const entry of Object.values(manifest)) {
  if (entry.file) files.add(entry.file);
  for (const css of entry.css ?? []) files.add(css);
}

let total = 0;
for (const file of files) {
  if (!/\.(js|css)$/.test(file)) continue;
  total += gzipSync(readFileSync(resolve(dist, file))).length;
}

const kb = (total / 1024).toFixed(1);
if (total > LIMIT_BYTES) {
  console.error(`budget: ${kb} KB gzipped exceeds ${LIMIT_BYTES / 1024} KB`);
  process.exit(1);
}
console.log(`budget: ${kb} KB gzipped (limit ${LIMIT_BYTES / 1024} KB)`);

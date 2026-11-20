// Fails the build when the gzipped JS + CSS the pages load up front exceed the budget (spec §12).
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const LIMIT_BYTES = 100 * 1024;
const dist = resolve(dirname(fileURLToPath(import.meta.url)), "../../static/dist");
const manifest = JSON.parse(readFileSync(resolve(dist, ".vite/manifest.json"), "utf8"));

// Entries and what they import statically. Lazy chunks (dynamic imports, such as the pdf.js
// preview) and their assets (its worker) load only when used, so they are not counted.
const files = new Set();
const visit = (key) => {
  const entry = manifest[key];
  if (!entry || files.has(entry.file)) return;
  files.add(entry.file);
  for (const css of entry.css ?? []) files.add(css);
  for (const imported of entry.imports ?? []) visit(imported);
};
for (const [key, entry] of Object.entries(manifest)) if (entry.isEntry) visit(key);

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

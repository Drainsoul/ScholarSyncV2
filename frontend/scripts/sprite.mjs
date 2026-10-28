// Builds static/dist/icons.svg (spec §12): one <symbol> per Lucide icon named in src/icons/icons.json,
// plus our own icons in src/icons/*.svg. Runs after `vite build`, which empties static/dist.
// A misspelt name fails the build (readFileSync throws ENOENT).
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const iconsDir = resolve(here, "../src/icons");
const lucideDir = resolve(here, "../node_modules/lucide-static/icons");
const out = resolve(here, "../../static/dist/icons.svg");
const ATTRS =
  'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
  'stroke-linecap="round" stroke-linejoin="round"';

function inner(file) {
  const match = readFileSync(file, "utf8").match(/<svg[^>]*>([\s\S]*?)<\/svg>/);
  if (!match) throw new Error(`sprite: no <svg> element in ${file}`);
  return match[1].replace(/\s+/g, " ").trim();
}

const symbols = new Map();
for (const name of JSON.parse(readFileSync(resolve(iconsDir, "icons.json"), "utf8"))) {
  symbols.set(name, inner(resolve(lucideDir, `${name}.svg`)));
}
for (const file of readdirSync(iconsDir).filter((f) => f.endsWith(".svg"))) {
  const name = basename(file, ".svg");
  if (symbols.has(name)) throw new Error(`sprite: ${name}.svg clashes with a Lucide icon`);
  symbols.set(name, inner(resolve(iconsDir, file)));
}

const body = [...symbols].map(([id, svg]) => `<symbol id="${id}" ${ATTRS}>${svg}</symbol>`);
writeFileSync(out, `<svg xmlns="http://www.w3.org/2000/svg">${body.join("")}</svg>\n`);
console.log(`sprite: ${symbols.size} icons`);

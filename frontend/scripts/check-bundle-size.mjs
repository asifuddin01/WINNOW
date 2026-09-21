// Fails when the JavaScript needed for the first page exceeds the budget in guide 2.2
// (initial bundle < 200 KB gzipped). Run after `vite build`.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const BUDGET_KB = 200;
const dist = join(import.meta.dirname, "..", "dist");
const manifest = JSON.parse(readFileSync(join(dist, ".vite", "manifest.json"), "utf8"));

const gzipKb = (file) => gzipSync(readFileSync(join(dist, file))).length / 1024;

// The entry chunk plus everything it imports statically: what loads before any route.
const initial = new Set();
const visit = (key) => {
  const chunk = manifest[key];
  if (!chunk || initial.has(chunk.file)) return;
  initial.add(chunk.file);
  for (const dependency of chunk.imports ?? []) visit(dependency);
};
for (const [key, chunk] of Object.entries(manifest)) if (chunk.isEntry) visit(key);

const allJs = Object.values(manifest)
  .map((chunk) => chunk.file)
  .filter((file, index, files) => file.endsWith(".js") && files.indexOf(file) === index);

const sum = (files) => [...files].reduce((total, file) => total + gzipKb(file), 0);
const initialKb = sum(initial);
console.log(`Initial JS: ${initialKb.toFixed(1)} KB gzipped (budget ${BUDGET_KB} KB)`);
console.log(`All JS:     ${sum(allJs).toFixed(1)} KB gzipped across ${allJs.length} chunks`);

if (initialKb > BUDGET_KB) {
  console.error(`Initial bundle is over budget by ${(initialKb - BUDGET_KB).toFixed(1)} KB.`);
  process.exit(1);
}

#!/usr/bin/env node
import { cpSync, existsSync, readFileSync, writeFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");

const name = process.argv[2];

if (!name) {
  console.error("Usage: npm run new <sketch-name>");
  process.exit(1);
}

if (!/^[a-z0-9-]+$/.test(name)) {
  console.error("Sketch name must be lowercase letters, numbers, and hyphens only.");
  process.exit(1);
}

const dest = resolve(root, "sketches", name);

if (existsSync(dest)) {
  console.error(`sketches/${name} already exists.`);
  process.exit(1);
}

cpSync(resolve(root, "sketches/_template"), dest, { recursive: true });

const htmlPath = resolve(dest, "index.html");
const today = new Date().toISOString().slice(0, 10);
const html = readFileSync(htmlPath, "utf8")
  .replace(/^title: .+$/m, `title: ${name}`)
  .replace(/^date: .+$/m, `date: ${today}`);
writeFileSync(htmlPath, html);

console.log(`Created sketches/${name}/`);

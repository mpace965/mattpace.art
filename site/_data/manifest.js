import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const manifestPath = resolve(__dirname, "../bundle/manifest.json");

export default function () {
  if (!existsSync(manifestPath)) {
    return [];
  }
  return JSON.parse(readFileSync(manifestPath, "utf-8"));
}

import { existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const bundleDir = resolve(__dirname, "bundle");

export default function (eleventyConfig) {
  // Copy built images and manifest from the bundle symlink into dist/
  if (existsSync(bundleDir)) {
    eleventyConfig.addPassthroughCopy({ "bundle": "." });
  }

  eleventyConfig.addPassthroughCopy("favicon.png");
  eleventyConfig.addPassthroughCopy("assets");
  eleventyConfig.addPassthroughCopy("CNAME");

  return {
    dir: {
      input: ".",
      output: "dist",
      includes: "_includes",
      data: "_data",
    },
  };
}

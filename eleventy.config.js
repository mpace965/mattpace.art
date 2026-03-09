export default function (eleventyConfig) {
  eleventyConfig.ignores.add("sketches/_template");
  eleventyConfig.ignores.add("CLAUDE.md");

  eleventyConfig.addCollection("sketch", (api) => {
    return api.getFilteredByGlob("sketches/*/index.html");
  });


  eleventyConfig.addPassthroughCopy("vendor", {
    filter: ["**", "!**/types", "!**/types/**"],
  });

  eleventyConfig.addPassthroughCopy("sketches", {
    filter: [
      "**",
      "!**/*.d.ts",
      "!**/jsconfig.json",
      "!_template",
      "!_template/*",
      "!**/*.html",
    ],
  });
}

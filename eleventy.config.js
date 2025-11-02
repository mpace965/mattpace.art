export default function (eleventyConfig) {
	eleventyConfig.addPassthroughCopy("vendor", {
		filter: ["**", "!**/types", "!**/types/**"],
	});

	eleventyConfig.addPassthroughCopy("sketches", {
		filter: ["**", "!**/*.d.ts", "!**/jsconfig.json"],
	});
};

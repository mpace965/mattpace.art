import { ref } from "../../vendor/@vue/reactivity@3.5.23/reactivity.js";

import { Pane } from "../../vendor/tweakpane@4.0.5/tweakpane.min.js";

// #region sketch

/**
 * @typedef Params
 * @property {number} count
 * @property {number} radius
 */

/** @type {Record<string, Params>} */
const PRESETS = {
  default: { count: 8, radius: 1 },
};

const DEFAULT_PRESET_NAME = "default";

/**
 * @param {Pane} pane
 * @param {Params} params
 */
function bindParamsToPane(pane, params) {
  pane.addBinding(params, "count", { min: 1, max: 20, step: 1 });
  pane.addBinding(params, "radius", { min: 0, max: 1, step: 0.01 });
}

/**
 * @param {import("../../vendor/@vue/reactivity@3.5.23/reactivity.js").Ref<Params>} params
 */
function mountSketch(params) {
  const size = squareCanvasSize();

  /** @type {import("../../vendor/p5@1.11.11/types/index.js").Image} */
  let img;
  /** @type {import("../../vendor/p5@1.11.11/types/index.js").Graphics} */
  let mask;

  globalThis.preload = function () {
    img = loadImage("assets/cardboard.jpg");
  };

  globalThis.setup = function () {
    createCanvas(size.value, size.value);
    mask = createGraphics(size.value, size.value);
  }

  globalThis.windowResized = function () {
    resizeCanvas(size.value, size.value);
    mask.resizeCanvas(size.value, size.value);
    redraw();
  };

  globalThis.draw = function () {
    image(img, 0, 0, size.value, size.value);

    drawMask(mask, size.value, params.value.count, params.value.radius);

    blendMode(DIFFERENCE);
    image(mask, 0, 0);
    blendMode(BLEND);
  };
}

// #endregion

// #region lib: sketch

/**
 * Draw the mask used to invert the image.
 *
 * @param {import("../../vendor/p5@1.11.11/types/index.js").Graphics} mask
 * @param {number} size
 * @param {number} count
 * @param {number} radius
 */
function drawMask(mask, size, count, radius) {
  mask.clear();
  mask.noStroke();
  mask.fill(255);

  const cell = size / count;

  for (let row = 0; row < count; row++) {
    for (let col = 0; col < count; col++) {
      const cx = (col + 0.5) * cell;
      const cy = (row + 0.5) * cell;
      mask.circle(cx, cy, cell * radius);
    }
  }
}

/**
 * Returns a ref holding the side length of the largest square that fits the
 * viewport. The value updates automatically on window resize.
 *
 * Usage in mountSketch:
 *   const size = squareCanvasSize();
 *   // createCanvas(size.value, size.value)
 *   // windowResized: resizeCanvas(size.value, size.value)
 *
 * @returns {import("../../vendor/@vue/reactivity@3.5.23/reactivity.js").Ref<number>}
 */
function squareCanvasSize() {
  const size = ref(Math.min(window.innerWidth, window.innerHeight));
  window.addEventListener("resize", () => {
    size.value = Math.min(window.innerWidth, window.innerHeight);
  });
  return size;
}

// #endregion

// #region lib: parameters and presets

const PRESET_SEARCH_PARAM = "preset";

function getPresetNameOrDefault() {
  const url = new URL(window.location.href);
  const preset = url.searchParams.get(PRESET_SEARCH_PARAM);

  if (preset && isPreset(preset)) {
    return preset;
  }

  return DEFAULT_PRESET_NAME;
}

/**
 * @param {string} preset
 */
function linkToPreset(preset) {
  if (isPreset(preset)) {
    const url = new URL(window.location.href);

    url.searchParams.set(PRESET_SEARCH_PARAM, preset);

    window.location.href = url.toString();
  } else {
    throw new Error(
      `Invalid preset "${preset}", must be one of ${getPresetNames().toString()}.`
    );
  }
}

/**
 * @param {string} preset
 */
function isPreset(preset) {
  return preset in PRESETS;
}

/**
 * @param {string} presetName
 */
function getParamsForPresetName(presetName) {
  return PRESETS[presetName];
}

function getPresetNames() {
  return Object.keys(PRESETS).sort();
}

// #endregion

// #region lib: tweakpane

/**
 * @param {string} title
 */
function mountTweakpane(title) {
  const PANE = new Pane({ title });
  listenForHidePaneEvent(PANE.element);

  bindParamsToPane(PANE, PARAMS.value);

  addSelectPresetDropdown(PANE);
  addExportPresetButton(PANE, PARAMS.value);
}

/**
 * @param {HTMLElement} paneElement
 */
function listenForHidePaneEvent(paneElement) {
  document.addEventListener("keydown", (e) => {
    if (e.key === "h") {
      toggleVisibility(paneElement);
    }
  });
}

/**
 * @param {HTMLElement} element
 */
function toggleVisibility(element) {
  const currentVisibility = element.style.getPropertyValue("visibility");

  if (currentVisibility !== "hidden") {
    element.style.setProperty("visibility", "hidden");
  } else {
    element.style.setProperty("visibility", "visible");
  }
}

/**
 * @param {Pane} pane
 */
function addSelectPresetDropdown(pane) {
  const PRESET_PARAMS = {
    presetName: "",
  };

  pane
    .addBinding(PRESET_PARAMS, "presetName", {
      label: "preset",
      options: buildPresetOptions(),
    })
    .on("change", (ev) => linkToPreset(ev.value));
}

function buildPresetOptions() {
  const options = {
    "Select...": "",
  };

  for (const presetName of getPresetNames()) {
    options[presetName] = presetName;
  }

  return options;
}

/**
 * @param {Pane} pane
 * @param {Params} params
 */
function addExportPresetButton(pane, params) {
  const exportBtn = pane.addButton({ title: "Export" });
  exportBtn.on("click", () =>
    navigator.clipboard.writeText(JSON.stringify(params))
  );
}

function getTitleOrDefault() {
  return document.querySelector("title").textContent || "sketch";
}

// #endregion

// #region bootstrap

const PRESET_NAME = getPresetNameOrDefault();
const PARAMS = ref(getParamsForPresetName(PRESET_NAME));

mountTweakpane(`${getTitleOrDefault()} (${PRESET_NAME})`);
mountSketch(PARAMS);

// #endregion

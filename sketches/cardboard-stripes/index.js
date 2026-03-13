import { ref } from "../../vendor/@vue/reactivity@3.5.23/reactivity.js";

import { Pane } from "../../vendor/tweakpane@4.0.5/tweakpane.min.js";

// #region sketch

/** @type {Record<string, (i: number, count: number) => number>} */
const WIDTH_FNS = {
  uniform: (_i, _count) => 1.0,
  linear: (i, count) => count < 2 ? 1.0 : i / (count - 1),
  exponential: (i, count) => count < 2 ? 1.0 : (Math.exp(i / (count - 1)) - 1) / (Math.E - 1),
  sinusoidal: (i, count) => count < 2 ? 1.0 : Math.sin(Math.PI * i / (count - 1)),
};

/**
 * @typedef Params
 * @property {number} count
 * @property {number} vertMargin
 * @property {number} horzMargin
 * @property {string} widthFn
 * @property {boolean} invertFn
 * @property {string} align
 */

/** @type {Record<string, Params>} */
const PRESETS = {
  default: { "count": 3, "vertMargin": 0.45, "horzMargin": 0.2, "widthFn": "uniform", "invertFn": false, "align": "center" },
  steps: { "count": 5, "vertMargin": 0.39, "horzMargin": 0.11000000000000001, "widthFn": "linear", "invertFn": true, "align": "left" }
};

const DEFAULT_PRESET_NAME = "default";

/**
 * @param {Pane} pane
 * @param {Params} params
 */
function bindParamsToPane(pane, params) {
  pane.addBinding(params, "count", { min: 1, max: 50, step: 1 });
  pane.addBinding(params, "vertMargin", { min: 0, max: 1, step: 0.01 });
  pane.addBinding(params, "horzMargin", { min: 0, max: 1, step: 0.01 });
  pane.addBinding(params, "widthFn", {
    label: "widthFn",
    options: Object.fromEntries(Object.keys(WIDTH_FNS).map((k) => [k, k])),
  });
  pane.addBinding(params, "invertFn");
  pane.addBinding(params, "align", {
    options: { center: "center", left: "left", right: "right" },
  });
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

  function drawMask() {
    const { count, vertMargin, horzMargin, widthFn, invertFn, align } = params.value;

    mask.clear();
    mask.noStroke();
    mask.fill(255);

    const inset = horzMargin * 0.5 * size.value;
    const availableWidth = size.value - 2 * inset;

    const totalGap = vertMargin * size.value;
    const gap = totalGap / (count + 1);
    const rectH = (size.value - totalGap) / count;

    for (let i = 0; i < count; i++) {
      const raw = WIDTH_FNS[widthFn]?.(i, count) ?? 1.0;
      const v = invertFn ? 1 - raw : raw;
      const rectW = availableWidth * map(v, 0, 1, 1 / count, 1);
      const offset = align === "left" ? 0 : align === "right" ? availableWidth - rectW : (availableWidth - rectW) / 2;
      const x = inset + offset;
      const y = gap + i * (rectH + gap);
      mask.rect(x, y, rectW, rectH);
    }
  }

  globalThis.draw = function () {
    image(img, 0, 0, size.value, size.value);

    drawMask();

    blendMode(DIFFERENCE);
    image(mask, 0, 0);
    blendMode(BLEND);
  };
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
  const isProd = window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1";
  if (isProd) toggleVisibility(PANE.element);
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

  let lastTap = 0;
  document.addEventListener("touchend", () => {
    const now = Date.now();
    if (now - lastTap < 300) toggleVisibility(paneElement);
    lastTap = now;
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

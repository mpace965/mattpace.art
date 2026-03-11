import { ref } from "../../vendor/@vue/reactivity@3.5.23/reactivity.js";

import { Pane } from "../../vendor/tweakpane@4.0.5/tweakpane.min.js";

// #region sketch

/**
 * @typedef Params
 * @property {number} foo
 */

/** @type {Record<string, Params>} */
const PRESETS = {
  default: { foo: 0 },
};

const DEFAULT_PRESET_NAME = "default";

/**
 * @param {Pane} pane
 * @param {Params} params
 */
function bindParamsToPane(pane, params) {}

const IMG_SIZE = 2048;
const IMG_SEGMENTS = 256;
const IMG_SEGMENT_SIZE = Math.round(IMG_SIZE / IMG_SEGMENTS);

/**
 * @param {import("../../vendor/@vue/reactivity@3.5.23/reactivity.js").Ref<Params>} params
 */
function mountSketch(params) {
  const size = squareCanvasSize();

  /** @type {import("../../vendor/p5@1.11.11/types/index.js").Image} */
  let img;

  globalThis.preload = function () {
    img = loadImage("assets/tile2.jpg");
  };

  globalThis.setup = function () {
    const canvasSegmentSize = (IMG_SEGMENT_SIZE / IMG_SIZE) * size.value;
    createCanvas(size.value, size.value);

    // tree texture

    img.loadPixels();

    background("lightgray");

    noStroke();
    fill(0);

    for (let y = 0; y < IMG_SEGMENTS; y++) {
      for (let x = 0; x < IMG_SEGMENTS; x++) {
        const indexX = x * IMG_SEGMENT_SIZE * 4;
        const indexY = y * IMG_SEGMENT_SIZE * 4 * IMG_SIZE;

        const value = map(img.pixels[indexY + indexX], 0, 255, 0, 9);

        const drawX = map(x, 0, IMG_SEGMENTS, 0, size.value);
        const drawY = map(y, 0, IMG_SEGMENTS, 0, size.value);

        diceTexture(drawX, drawY, canvasSegmentSize, value, 0.9, circle);
      }
    }

    // frame

    stroke(0);
    noFill();
    strokeWeight(50);

    rect(0, 0, size.value, size.value);
  };

  globalThis.draw = function () {};
}

// #endregion

// #region lib: sketch

/**
 * Returns a ref holding the side length of the largest square that fits the
 * viewport. The value updates automatically on window resize.
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

/**
 * Draw the face of a dice at the given size and coordinates.
 *
 * @param {number} x
 * @param {number} y
 * @param {number} size
 * @param {number} value [0, 9] the dice value
 * @param {number} pipScale [0, 1] the ratio of a pip's 'full size'. 0 - no pip, 1 - pips are touching
 * @param {function(number, number, number): void} callback callback for drawing the pip at (x, y, size)
 */
function diceTexture(x, y, size, value, pipScale, callback) {
  value = Math.round(constrain(value, 0, 9));

  const marginSize = (size / 3) * (1 - pipScale);
  const pipSize = size / 3 - marginSize;
  const gridLength = marginSize + pipSize;

  let points = [];

  if (value === 1) {
    points = [[x, y]];
  }

  if (value === 2) {
    points = [
      [x - gridLength, y - gridLength],
      [x + gridLength, y + gridLength],
    ];
  }

  if (value === 3) {
    points = [
      [x - gridLength, y - gridLength],
      [x, y],
      [x + gridLength, y + gridLength],
    ];
  }

  if (value === 4) {
    points = [
      [x - gridLength, y - gridLength],
      [x + gridLength, y - gridLength],
      [x - gridLength, y + gridLength],
      [x + gridLength, y + gridLength],
    ];
  }

  if (value === 5) {
    points = [
      [x - gridLength, y - gridLength],
      [x + gridLength, y - gridLength],
      [x, y],
      [x - gridLength, y + gridLength],
      [x + gridLength, y + gridLength],
    ];
  }

  if (value === 6) {
    points = [
      [x - gridLength, y - gridLength],
      [x + gridLength, y - gridLength],
      [x - gridLength, y],
      [x + gridLength, y],
      [x - gridLength, y + gridLength],
      [x + gridLength, y + gridLength],
    ];
  }

  if (value === 7) {
    points = [
      [x - gridLength, y - gridLength],
      [x + gridLength, y - gridLength],
      [x - gridLength, y],
      [x + gridLength, y],
      [x - gridLength, y + gridLength],
      [x + gridLength, y + gridLength],
      [x, y],
    ];
  }

  if (value === 8) {
    points = [
      [x - gridLength, y - gridLength],
      [x, y - gridLength],
      [x + gridLength, y - gridLength],
      [x - gridLength, y],
      [x + gridLength, y],
      [x - gridLength, y + gridLength],
      [x, y + gridLength],
      [x + gridLength, y + gridLength],
    ];
  }

  if (value === 9) {
    points = [
      [x - gridLength, y - gridLength],
      [x, y - gridLength],
      [x + gridLength, y - gridLength],
      [x - gridLength, y],
      [x, y],
      [x + gridLength, y],
      [x - gridLength, y + gridLength],
      [x, y + gridLength],
      [x + gridLength, y + gridLength],
    ];
  }

  for (const [x, y] of points) {
    callback(x, y, pipSize);
  }
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

// #region lib: controls

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

function listenForFullscreenEvent() {
  document.addEventListener("keydown", function (event) {
    if (event.key === "f" || event.key === "F") {
      toggleFullscreen();
    }
  });
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen();
  } else {
    document.exitFullscreen();
  }
}

// #endregion

// #region bootstrap

const PRESET_NAME = getPresetNameOrDefault();
const PARAMS = ref(getParamsForPresetName(PRESET_NAME));

mountTweakpane(`${getTitleOrDefault()} (${PRESET_NAME})`);
listenForFullscreenEvent();
mountSketch(PARAMS);

// #endregion

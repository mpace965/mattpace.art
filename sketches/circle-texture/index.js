// #region parameters and presets

/**
 * @typedef Params
 * @prop {number} circleScale
 * @prop {number} segments
 * @prop {number} seed
 * @prop {number} noiseScale
 * @prop {number} noiseLod
 * @prop {number} noiseFalloff
 */

/**
 * @typedef DerivedParams
 * @prop {number} segmentSize
 * @prop {number} segmentOffset
 * @prop {Array<Array<number>>} values
 */

/** @type {Record<string, Params>} */
const PRESETS = {
  default: {
    circleScale: 3 / 4,
    segments: 13,
    seed: 0,
    noiseScale: 1,
    noiseLod: 4,
    noiseFalloff: 0.5,
  },
  terrain: {
    circleScale: 0.75,
    segments: 64,
    seed: 0,
    noiseScale: -0.06521739130434767,
    noiseLod: 4,
    noiseFalloff: 0.29347826086956524,
  },
};

const DEFAULT_PRESET_NAME = "default";

const PRESET_SEARCH_PARAM = "preset";

function getPresetName() {
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

const presetName = getPresetName();
const params = getParamsForPresetName(presetName);

// #endregion

// #region tweakpane

import { Pane } from "../../vendor/tweakpane@4.0.5/tweakpane.min.js";

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

const pane = new Pane({ title: `Circle texture ${presetName}` });
listenForHidePaneEvent(pane.element);

pane.addBinding(params, "circleScale", { min: 0, max: 1 });
pane
  .addBinding(params, "segments", { step: 1, min: 1, max: 200 })
  .on("change", () => (derivedParams = computeDerivedParams()));
pane
  .addBinding(params, "seed", { step: 1 })
  .on("change", () => (derivedParams = computeDerivedParams()));
pane
  .addBinding(params, "noiseScale", { min: -3, max: 3 })
  .on("change", () => (derivedParams = computeDerivedParams()));
pane
  .addBinding(params, "noiseLod", { step: 1, min: 0 })
  .on("change", () => (derivedParams = computeDerivedParams()));
pane
  .addBinding(params, "noiseFalloff", { min: 0, max: 1 })
  .on("change", () => (derivedParams = computeDerivedParams()));

addSelectPresetDropdown(pane);
addExportPresetButton(pane, params);

// #endregion

// #region sketch

const CANVAS_SIZE = 800;

/** @type {DerivedParams} */
let derivedParams;

/**
 * @returns {DerivedParams}
 */
function computeDerivedParams() {
  noiseSeed(params.seed);
  noiseDetail(params.noiseLod, params.noiseFalloff);
  const values = [];

  for (let x = 0; x < params.segments; x++) {
    const row = [];
    for (let y = 0; y < params.segments; y++) {
      row.push(9 * noise(params.noiseScale * x, params.noiseScale * y));
    }
    values.push(row);
  }

  const segmentSize = CANVAS_SIZE / params.segments;
  const segmentOffset = segmentSize / 2;

  return { values, segmentSize, segmentOffset };
}

globalThis.setup = function () {
  createCanvas(CANVAS_SIZE, CANVAS_SIZE);

  derivedParams = computeDerivedParams();
};

globalThis.draw = function () {
  background(220);
  fill(0);

  for (let x = 0; x < params.segments; x++) {
    for (let y = 0; y < params.segments; y++) {
      diceTexture(
        x * derivedParams.segmentSize + derivedParams.segmentOffset,
        y * derivedParams.segmentSize + derivedParams.segmentOffset,
        derivedParams.segmentSize,
        derivedParams.values[x][y],
        params.circleScale,
        circle
      );
    }
  }
};

function diceTexture(x, y, areaSize, value, scale, callback) {
  value = Math.round(constrain(value, 0, 9));

  const marginSize = (areaSize / 3) * (1 - scale);
  const pipSize = areaSize / 3 - marginSize;
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

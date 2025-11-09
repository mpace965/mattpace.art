import {
  ref,
  computed,
} from "../../vendor/@vue/reactivity@3.5.23/reactivity.js";

import { Pane } from "../../vendor/tweakpane@4.0.5/tweakpane.min.js";

// #region sketch

/**
 * @typedef Params
 * @prop {number} canvasSize
 * @prop {number} pipScale
 * @prop {number} gridLength
 * @prop {NoiseParams} noise
 */

/**
 * @typedef NoiseParams
 * @prop {number} seed
 * @prop {number} scale
 * @prop {number} lod
 * @prop {number} falloff
 */

/** @type {Record<string, Params>} */
const PRESETS = {
  terrain: {
    canvasSize: 800,
    pipScale: 0.75,
    gridLength: 64,
    noise: {
      seed: 0,
      scale: -0.06521739130434767,
      lod: 4,
      falloff: 0.29347826086956524,
    },
  },
  face: {
    canvasSize: 800,
    pipScale: 0.75,
    gridLength: 100,
    noise: {
      seed: 0,
      scale: 0.01630434782608703,
      lod: 3,
      falloff: 0.2717391304347826,
    },
  },
};

const DEFAULT_PRESET_NAME = "face";

/**
 * @param {Pane} pane
 * @param {Params} params
 */
function bindParamsToPane(pane, params) {
  pane.addBinding(params, "pipScale", { min: 0, max: 1 });
  pane.addBinding(params, "gridLength", { step: 1, min: 1, max: 200 });

  const noiseFolder = pane.addFolder({ title: "noise" });
  noiseFolder.addBinding(params.noise, "seed", { step: 1 });
  noiseFolder.addBinding(params.noise, "scale", { min: -0.75, max: 0.75 });
  noiseFolder.addBinding(params.noise, "lod", { step: 1, min: 0 });
  noiseFolder.addBinding(params.noise, "falloff", { min: 0, max: 1 });
}

/**
 * @param {import("../../vendor/@vue/reactivity@3.5.23/reactivity.js").Ref<Params>} params
 */
function mountSketch(params) {
  const diceSize = computed(
    () => params.value.canvasSize / params.value.gridLength
  );
  const diceOffset = computed(() => diceSize.value / 2);
  const diceValueGrid = computed(() =>
    sampleDiceValueGridFromNoise(params.value.noise, params.value.gridLength)
  );

  globalThis.setup = function () {
    createCanvas(params.value.canvasSize, params.value.canvasSize);
  };

  globalThis.draw = function () {
    background(220);
    fill(0);

    for (let x = 0; x < params.value.gridLength; x++) {
      for (let y = 0; y < params.value.gridLength; y++) {
        diceTexture(
          x * diceSize.value + diceOffset.value,
          y * diceSize.value + diceOffset.value,
          diceSize.value,
          diceValueGrid.value[x][y],
          params.value.pipScale,
          circle
        );
      }
    }
  };
}

// #endregion

// #region lib: sketch

/**
 * Sample an n x n grid of dice values using noise configured with the given parameters.
 *
 * @param {NoiseParams} noiseParams
 * @param {number} n
 * @returns {Array<Array<number>>}
 */
function sampleDiceValueGridFromNoise({ seed, lod, falloff, scale }, n) {
  noiseSeed(seed);
  noiseDetail(lod, falloff);
  const values = [];

  for (let x = 0; x < n; x++) {
    const row = [];
    for (let y = 0; y < n; y++) {
      row.push(9 * noise(scale * x, scale * y));
    }
    values.push(row);
  }

  return values;
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

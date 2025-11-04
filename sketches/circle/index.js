// #region parameters and presets

/**
 * @typedef Params
 * @prop {number} size
 */

/** @type {Record<string, Params>} */
const PRESETS = {
  small: { size: 10 },
  large: { size: 100 },
};

const DEFAULT_PRESET_NAME = "small";

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

function mountTweakpane() {
  const pane = new Pane({ title: `Circle ${presetName}` });
  listenForHidePaneEvent(pane.element);

  pane.addBinding(params, "size", { min: 2, max: 250 });

  addSelectPresetDropdown(pane);
  addExportPresetButton(pane, params);
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

mountTweakpane();

// #endregion

// #region sketch

globalThis.setup = function () {
  createCanvas(400, 400);
};

globalThis.draw = function () {
  background(220);
  circle(mouseX, mouseY, params.size);
};

// #endregion

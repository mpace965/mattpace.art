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

/**
 * @param {import("../../vendor/@vue/reactivity@3.5.23/reactivity.js").Ref<Params>} params
 */
function mountSketch(params) {
  let img;

  globalThis.preload = function () {
    img = loadImage("assets/tile.jpg");
  };

  globalThis.setup = function () {
    createCanvas(800, 800);

    // Draw the image.
    image(img, 0, 0, 800, 800);
  };

  globalThis.draw = function () {};
}

// #endregion

// #region lib: sketch

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

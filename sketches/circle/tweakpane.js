import { makePane, addPresetBlades } from '../lib/tweakpane.js';

/**
 * @param {import("../lib/preset-manager").PresetManager<any>} presetManager
 * @param {string} presetName
 * @param {object} params
 */
export function mountTweakpane(presetManager, presetName, params) {
  const pane = makePane(`Circle ${presetName}`);

  pane.addBinding(params, 'size', { min: 2, max: 250 });

  addPresetBlades(pane, presetManager, params);
}

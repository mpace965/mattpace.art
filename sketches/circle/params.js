import { PresetManager } from '../lib/preset-manager.js';

/**
 * @typedef Params
 * @property {number} size
 */

export function getPresetManager() {
  /** @type {PresetManager<Params>} */
  const presetManager = new PresetManager();

  presetManager.addPreset('small', { size: 10 });
  presetManager.addPreset('large', { size: 100 });
  presetManager.setDefaultPreset('small');

  return presetManager;
}

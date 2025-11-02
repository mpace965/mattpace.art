import { mountSketch } from './sketch.js'
import { getPresetManager } from './params.js';

document.addEventListener('DOMContentLoaded', () => {
  const presetManager = getPresetManager();
  const presetName = presetManager.getPresetName();
  const params = presetManager.getParamsForPresetName(presetName);

  mountSketch(params);
})

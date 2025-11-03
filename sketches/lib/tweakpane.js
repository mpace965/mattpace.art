import { Pane } from '../../vendor/tweakpane@4.0.5/tweakpane.min.js'

// TODO: tweakpane types

/**
 * 
 * @param {string} title 
 * @returns {Pane}
 */
export function makePane(title) {
  const pane = new Pane({ title });
  listenForHidePaneEvent(pane.element);

  return pane;
}

/**
 * 
 * @param {Pane} pane 
 * @param {import('./preset-manager.js').PresetManager} presetManager 
 * @param {object} params
 */
export function addPresetBlades(pane, presetManager, params) {
  addSelectPresetDropdown(pane, presetManager);
  addExportPresetButton(pane, params);
}

/**
 * 
 * @param {Pane} pane 
 * @param {import('./preset-manager.js').PresetManager} presetManager 
 */
function addSelectPresetDropdown(pane, presetManager) {
  const PRESET_PARAMS = {
    presetName: '',
  };

  pane
    .addBinding(PRESET_PARAMS, 'presetName', {
      label: 'preset',
      options: buildPresetOptions(presetManager),
    })
    .on('change', (ev) => presetManager.linkToPreset(ev.value));
}

/**
 * 
 * @param {import('./preset-manager.js').PresetManager} presetManager 
 */
function buildPresetOptions(presetManager) {
  const options = {
    'Select...': '',
  };

  for (const presetName of presetManager.getPresetNames()) {
    options[presetName] = presetName;
  }

  return options;
}

function addExportPresetButton(pane, params) {
  const exportBtn = pane.addButton({ title: 'Export' });
  exportBtn.on('click', () =>
    navigator.clipboard.writeText(JSON.stringify(params))
  );
}

function listenForHidePaneEvent(paneElement) {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'h') {
      toggleVisibility(paneElement);
    }
  });
}

function toggleVisibility(element) {
  const currentVisibility = element.style.getPropertyValue('visibility');

  if (currentVisibility !== 'hidden') {
    element.style.setProperty('visibility', 'hidden');
  } else {
    element.style.setProperty('visibility', 'visible');
  }
}

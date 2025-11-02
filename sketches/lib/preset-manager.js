const PRESET_SEARCH_PARAM = 'preset';

/**
 * @template {Record<string, any>} TParams
 * @class
 * A generic preset manager for handling named parameter presets,
 * reading/writing them from the URL, and managing defaults.
 */
export class PresetManager {
  /**
   * @type {Record<string, TParams>}
   * @private
   */
  presets = {};

  /**
   * @type {string|null}
   * @private
   */
  defaultPresetName = null;

  /**
   * Adds or replaces a preset.
   * @param {string} name - The name of the preset.
   * @param {TParams} params - The preset parameters.
   * @returns {void}
   */
  addPreset(name, params) {
    this.presets[name] = params;
  }

  /**
   * Sets the default preset name.
   * @param {string} name - The name of the preset to set as default.
   * @throws {Error} If the preset does not exist.
   * @returns {void}
   */
  setDefaultPreset(name) {
    this.checkPreset(name);
    this.defaultPresetName = name;
  }

  /**
   * Gets the current preset name from the URL, or the default one if not found.
   * @throws {Error} If no preset is in the URL and no default is set.
   * @returns {string}
   */
  getPresetName() {
    const url = new URL(window.location.href);
    const preset = url.searchParams.get(PRESET_SEARCH_PARAM);

    if (preset && this.isPreset(preset)) {
      return preset;
    }

    if (this.defaultPresetName) {
      return this.defaultPresetName;
    }

    throw new Error('No preset found in URL and no default preset set.');
  }

  /**
   * Navigates to a new URL with the given preset name.
   * @param {string} name - The name of the preset.
   * @throws {Error} If the preset name is invalid.
   * @returns {void}
   */
  linkToPreset(name) {
    this.checkPreset(name);

    const url = new URL(window.location.href);
    url.searchParams.set(PRESET_SEARCH_PARAM, name);
    window.location.href = url.toString();
  }

  /**
   * Returns the parameters for a given preset name.
   * @param {string} name - The preset name.
   * @throws {Error} If the preset does not exist.
   * @returns {TParams}
   */
  getParamsForPresetName(name) {
    this.checkPreset(name);
    return this.presets[name];
  }

  /**
   * Returns all preset names, sorted alphabetically.
   * @returns {string[]}
   */
  getPresetNames() {
    return Object.keys(this.presets).sort();
  }

  /**
   * Checks if a preset name exists.
   * @param {string} name - The name to check.
   * @private
   * @returns {boolean}
   */
  isPreset(name) {
    return name in this.presets;
  }

  /**
   * Checks if a preset name exists, and throws an error otherwise
   * @param {string} name - The preset name.
   * @throws {Error} If the preset name is invalid.
   * @returns {void}
   */
  checkPreset(name) {
    if (!this.isPreset(name)) {
      throw new Error(
        `Invalid preset "${name}", must be one of ${this.getPresetNames().toString()}.`
      );
    }
  }
}

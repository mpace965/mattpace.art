- `site_presets` should live with `OutputBundle`, not on a sketch
- Decouple `Image` from framework
  - framework still needs some notion of types I think. Right now only image nodes are supported, but I could see raw data being supported. SVGs. The framework really just
    needs to know what to do with these in the UI. It's probably relevant to execution as well, but let's cross that bridge when we come to it.

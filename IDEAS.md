- Decouple `Image` from framework
  - framework still needs some notion of types I think. Right now only image nodes are supported, but I could see raw data being supported. SVGs. The framework really just
    needs to know what to do with these in the UI. It's probably relevant to execution as well, but let's cross that bridge when we come to it.
- sketch 404s if it hits an error
- node horizontal offset should be a quarter of the width overall of the node - it looks like it's stacking (so there's fewer offset every iteration)
- Rename "Site Builder" to "Bundle Builder" in framework code — the module at `framework/src/sketchbook/site/builder.py` only produces output bundles now, not a full site
- Authoring utility CLI tasks via Mise — userland tasks for common workflows like scaffolding a new sketch or generating a mask image with the same dimensions as a target image

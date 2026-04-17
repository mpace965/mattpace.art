# mattpace.art

A creative coding sketchbook powered by [Sketchbook](framework/), a reactive DAG-based pipeline framework.

Sketches are decorated Python functions. The framework builds the DAG implicitly as the sketch runs, then handles execution order, file watching, partial re-execution, preset persistence, and live browser updates via WebSocket. Finished work is published as a static site.

The editing experience is just editing code — by hand or with an AI agent. The browser is for viewing outputs and tweaking parameters, not authoring.

## Projects

This is a `uv` workspace monorepo with three projects:

| Directory | What it is |
|---|---|
| [`framework/`](framework/) | The Sketchbook engine — DAG executor, dev server, build CLI |
| `sketches/` | Userland sketch modules (depend on the framework, never the reverse) |
| [`site/`](site/) | 11ty static site that renders built sketch bundles |

## Quick start

### Prerequisites

- [mise](https://mise.jdx.dev/) — manages Python, uv, and Node versions (pinned in `.mise.toml`)

```sh
mise install          # install pinned runtimes
uv sync               # install Python dependencies
npm --prefix site ci  # install site dependencies
```

### Development

```sh
mise run sketches:dev   # start dev server on :8000
mise run site:dev       # start 11ty dev server
```

### Build and deploy

```sh
mise run build          # build sketch bundles + static site
mise run deploy         # build then push to gh-pages
```

### Testing and linting

```sh
mise run test           # run framework tests
mise run lint           # lint framework + sketches
```

## How it works

A sketch is a `@sketch`-decorated function that calls `source()`, decorated `@step` functions, and `output()`. The framework intercepts these calls, builds a DAG, and executes it:

```python
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step
from typing import Annotated
from sketches.types import Image

@sketch(date="2026-03-20")
def portrait() -> None:
    """blurred portrait blend."""
    photo = source("assets/photo.jpg", Image.load)
    blurred = gaussian_blur(photo)
    output(blurred, "bundle")

@step
def gaussian_blur(
    image: Image,
    *,
    kernel: Annotated[int, Param(min=1, max=31, step=2)] = 5,
) -> Image:
    """Return the Gaussian-blurred image."""
    ...
```

`@step` functions return proxy objects when called from a sketch context. The proxies record DAG edges. On execution the framework unwraps them and passes real values to each step. Parameters annotated with `Param(...)` become live sliders and controls in the browser UI.

The framework does not ship image-processing steps — those belong to the sketches that need them. Value types (`Image`, `Color`) also live in userland; the framework duck-types them via a protocol (`to_bytes()`, `extension`).

## Project structure

```
mattpace.art/
├── framework/              # sketchbook engine (Python package)
│   ├── src/sketchbook/
│   │   ├── core/           # DAG, executor, decorators, presets, watcher
│   │   └── server/         # FastAPI dev server, WebSocket, Tweakpane wiring
│   └── tests/              # acceptance/ and unit/
├── sketches/               # userland sketch modules
│   ├── types.py            # Image, Color — satisfy SketchValueProtocol
│   ├── cardboard/          # circle grid on cardboard texture
│   ├── cardboard_stripes/  # horizontal stripes variant
│   ├── fence-torn-paper/   # Canny edge detection on a weathered fence
│   └── kick-polygons/      # radially arranged polygon shapes
├── site/                   # 11ty static site
│   ├── _data/              # reads bundle manifest
│   └── dist/               # built output (gitignored)
└── docs/                   # design docs and implementation plans
```

## License

Code is MIT. Artwork and generated assets are CC BY-NC 4.0. See [LICENSE](LICENSE).

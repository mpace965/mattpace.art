# mattpace.art

A creative coding sketchbook powered by [Sketchbook](framework/), a reactive DAG-based pipeline framework.

Sketches are Python classes that wire together image-processing steps into pipelines. In dev mode, a FastAPI server watches source files and propagates changes through the pipeline in real time, with every intermediate step inspectable in the browser. Finished work is published as a static site.

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

Each sketch defines a pipeline of `PipelineStep` subclasses connected as a DAG:

```python
from sketchbook import Sketch
from .steps import MyBlur, MyBlend

class Portrait(Sketch):
    name = "portrait"
    description = "blurred portrait blend"
    date = "2026-03-20"

    def build(self):
        photo = self.source("photo", "assets/photo.jpg")
        blurred = photo.pipe(MyBlur)
        blurred.pipe(MyBlend)
```

Steps declare their inputs and parameters in `setup()`, and the framework handles execution order, file watching, partial re-execution, preset persistence, and live browser updates via WebSocket.

The framework does not ship image-processing steps — those belong to the sketches that need them. This keeps the framework generic and the sketches self-contained.

## Project structure

```
mattpace.art/
├── framework/          # sketchbook engine (Python package)
│   ├── src/sketchbook/ # core/, server/, steps/, site/
│   └── tests/          # acceptance/ and unit/
├── sketches/           # userland sketch modules
│   ├── cardboard/      # circle grid on cardboard texture
│   └── cardboard_stripes/  # horizontal stripes variant
├── site/               # 11ty static site
│   ├── _data/          # reads bundle manifest
│   └── dist/           # built output (gitignored)
└── docs/               # archived plans and design docs
```

## License

Code is MIT. Artwork and generated assets are CC BY-NC 4.0. See [LICENSE](LICENSE).

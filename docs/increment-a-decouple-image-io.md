# Increment A — Decouple image I/O from the framework

Remove `opencv-python-headless` as a runtime dependency. Introduce `PipelineValue` as
the framework's serialisation interface for workdir intermediates. `Image` implements it
using Pillow. The executor writes workdir files via `to_bytes()` instead of `Image.save()`.
`SourceFile` delegates loading to a caller-supplied function. Sketches own their
image-library choices.

## Definition of done

- [ ] `PipelineValue` base class exists in `core/types.py` with `extension`, `mime_type`,
      and abstract `to_bytes()`
- [ ] `Image` is a `PipelineValue` subclass; `to_bytes()` encodes as PNG via Pillow
- [ ] `Image` has no `load` or `save` methods and does not import `cv2`
- [ ] Executor writes workdir files with `Path(path).write_bytes(node.output.to_bytes())`
      instead of `node.output.save(path)`
- [ ] `SourceFile` accepts an optional `loader` callable; raises a descriptive error if
      executed without one
- [ ] `Sketch.source()` accepts an optional `loader` parameter and forwards it to `SourceFile`
- [ ] `pillow` added to `[dependencies]`; `opencv-python-headless` moved to
      `[dependency-groups] dev`
- [ ] All existing tests pass

---

## Outer loop — acceptance test

### Step 1: write `tests/acceptance/test_08_loader_decoupling.py`

```python
"""Acceptance test 08: loader decoupling.

Acceptance criteria:
    Image is a PipelineValue with extension and mime_type.
    Image.to_bytes() produces valid PNG bytes without cv2.
    Image has no load or save methods.
    A sketch that passes loader= to source() runs end-to-end and the result is
    visible in the browser — identical to the walking skeleton, but image
    loading is entirely the sketch's responsibility and the workdir write
    goes through to_bytes(), not cv2.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from sketchbook import Sketch
from sketchbook.core.executor import execute
from sketchbook.core.types import Image
from sketchbook.server.app import create_app
from tests.conftest import make_test_image
from tests.steps import Passthrough


def test_image_is_pipeline_value() -> None:
    """Image must subclass PipelineValue."""
    from sketchbook.core.types import PipelineValue
    assert issubclass(Image, PipelineValue)


def test_image_extension_is_png() -> None:
    assert Image.extension == "png"


def test_image_mime_type_is_image_png() -> None:
    assert Image.mime_type == "image/png"


def test_image_to_bytes_produces_valid_png() -> None:
    """to_bytes() returns bytes that start with the PNG magic number."""
    img = Image(np.zeros((8, 8, 3), dtype=np.uint8))
    data = img.to_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_image_has_no_load_method() -> None:
    """Image must not expose a load classmethod — I/O belongs in userland."""
    assert not hasattr(Image, "load"), "Image.load must not exist on the framework type"


def test_image_has_no_save_method() -> None:
    """Image must not expose a save method — I/O belongs in userland."""
    assert not hasattr(Image, "save"), "Image.save must not exist on the framework type"


class _LoaderSketch(Sketch):
    """Sketch that supplies its own cv2-based loader via _source_loader."""

    name = "Loader Sketch"
    description = "Tests that a sketch-supplied loader runs end-to-end."
    date = "2026-03-22"

    _source_loader = staticmethod(lambda p: Image(cv2.imread(str(p))))

    def build(self) -> None:
        photo = self.source("photo", "assets/photo.png")
        photo.pipe(Passthrough)


def test_sketch_with_loader_runs_end_to_end(tmp_path: Path) -> None:
    """A sketch with _source_loader completes pipeline execution without error."""
    sketch_dir = tmp_path / "loader_sketch"
    make_test_image(sketch_dir / "assets" / "photo.png")

    sketch = _LoaderSketch(sketch_dir)
    execute(sketch.dag)  # must not raise


def test_workdir_file_written_via_to_bytes(tmp_path: Path) -> None:
    """After execution the workdir PNG exists and contains valid PNG bytes."""
    sketch_dir = tmp_path / "loader_sketch"
    make_test_image(sketch_dir / "assets" / "photo.png")

    sketch = _LoaderSketch(sketch_dir)
    execute(sketch.dag)

    workdir_files = list((sketch_dir / ".workdir").glob("*.png"))
    assert workdir_files, "No PNG written to workdir"
    assert workdir_files[0].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_sketch_with_loader_result_visible_in_browser(tmp_path: Path) -> None:
    """The server returns an <img> tag for a sketch that uses _source_loader."""
    sketch_dir = tmp_path / "loader_sketch"
    make_test_image(sketch_dir / "assets" / "photo.png")

    sketch = _LoaderSketch(sketch_dir)
    execute(sketch.dag)

    app = create_app({"loader_sketch": sketch}, sketches_dir=tmp_path)
    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.get("/sketch/loader_sketch/step/passthrough_0")
        assert response.status_code == 200
        assert "<img" in response.text
```

### Step 2: run the acceptance test — confirm RED for the right reasons

```
uv run pytest tests/acceptance/test_08_loader_decoupling.py -v
```

Expected failures:
- `test_image_is_pipeline_value` — `PipelineValue` does not exist yet
- `test_image_extension_is_png` — `Image` has no `extension` attribute
- `test_image_mime_type_is_image_png` — `Image` has no `mime_type` attribute
- `test_image_to_bytes_produces_valid_png` — `Image` has no `to_bytes()` method
- `test_image_has_no_load_method` — `Image.load` currently exists
- `test_image_has_no_save_method` — `Image.save` currently exists
- `test_sketch_with_loader_runs_end_to_end` — `source()` does not yet accept `loader=`
- `test_workdir_file_written_via_to_bytes` — same root cause
- `test_sketch_with_loader_result_visible_in_browser` — same root cause

If any of these pass right now, stop and investigate before continuing.

---

## Inner loop 1 — `PipelineValue` base class and `Image.to_bytes()`

### Step 3: write new unit tests for `tests/unit/test_types.py`

Replace the existing file contents. The old load/save/round-trip tests are deleted because
those methods will no longer exist. The new tests cover `PipelineValue` interface
compliance and the `Image` wrapper.

```python
"""Unit tests for PipelineValue, Image: interface, construction, serialisation."""

from __future__ import annotations

import numpy as np
import pytest

from sketchbook.core.types import Image, PipelineValue


# ---------------------------------------------------------------------------
# PipelineValue interface on Image
# ---------------------------------------------------------------------------

def test_image_is_pipeline_value() -> None:
    assert issubclass(Image, PipelineValue)


def test_image_extension() -> None:
    assert Image.extension == "png"


def test_image_mime_type() -> None:
    assert Image.mime_type == "image/png"


def test_image_to_bytes_returns_png_magic() -> None:
    img = Image(np.zeros((8, 8, 3), dtype=np.uint8))
    assert img.to_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_image_to_bytes_non_empty() -> None:
    img = Image(np.full((4, 4, 3), 128, dtype=np.uint8))
    assert len(img.to_bytes()) > 0


# ---------------------------------------------------------------------------
# Image wrapper
# ---------------------------------------------------------------------------

def test_image_stores_ndarray() -> None:
    data = np.zeros((8, 8, 3), dtype=np.uint8)
    img = Image(data)
    assert img.data is data


def test_image_has_no_load_method() -> None:
    assert not hasattr(Image, "load")


def test_image_has_no_save_method() -> None:
    assert not hasattr(Image, "save")


def test_image_data_shape_preserved() -> None:
    data = np.zeros((16, 32, 3), dtype=np.uint8)
    img = Image(data)
    assert img.data.shape == (16, 32, 3)
```

### Step 4: run unit tests — confirm RED

```
uv run pytest tests/unit/test_types.py -v
```

Expected failures: all `PipelineValue`-related tests (`test_image_is_pipeline_value`,
`test_image_extension`, `test_image_mime_type`, `test_image_to_bytes_*`) because neither
`PipelineValue` nor `Image.to_bytes()` exist yet. `test_image_has_no_load_method` and
`test_image_has_no_save_method` also fail. The wrapper tests should already pass.

### Step 5: implement — add `PipelineValue` and update `Image`

Rewrite `framework/src/sketchbook/core/types.py`:

- Add `PipelineValue` abstract base class with `extension: str`, `mime_type: str`, and
  abstract `to_bytes() -> bytes`
- Make `Image` a `PipelineValue` subclass with `extension = "png"`, `mime_type = "image/png"`
- Implement `Image.to_bytes()` using Pillow
- Remove `Image.load`, `Image.save`, and `import cv2`

### Step 6: run unit tests — confirm GREEN

```
uv run pytest tests/unit/test_types.py -v
```

All tests must pass. Then run the full suite to see what else broke:

```
uv run pytest -v
```

Expected new failures: the executor (`node.output.save(path)` now calls a nonexistent
method), and tests that call `Image.load` or `Image.save` directly. Note each failure —
they are inputs to the remaining inner loops.

---

## Inner loop 2 — update the executor

### Step 7: add executor unit test

Add to `tests/unit/test_executor.py`:

```python
def test_executor_writes_workdir_via_to_bytes(tmp_path: Path) -> None:
    """Executor writes workdir files using to_bytes(), not a save() method."""
    import numpy as np
    from sketchbook.core.types import Image

    sketch_dir = tmp_path / "sketch"
    # build a minimal one-node DAG with a SourceFile that returns a known Image
    sentinel = Image(np.zeros((4, 4, 3), dtype=np.uint8))

    from sketchbook.core.dag import DAG, DAGNode
    from sketchbook.steps.source import SourceFile

    dag = DAG()
    step = SourceFile(tmp_path / "photo.png", loader=lambda _: sentinel)
    workdir_path = tmp_path / "out.png"
    node = DAGNode(step, "source_photo", workdir_path=str(workdir_path))
    dag.add_node(node)

    execute(dag)

    assert workdir_path.exists()
    assert workdir_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
```

### Step 8: run unit test — confirm RED

```
uv run pytest tests/unit/test_executor.py -v -k "to_bytes"
```

Expected: fails because the executor still calls `node.output.save(path)` which no longer
exists on `Image`.

### Step 9: implement — update the executor

In `framework/src/sketchbook/core/executor.py`, replace:

```python
node.output.save(node.workdir_path)
```

with:

```python
Path(node.workdir_path).write_bytes(node.output.to_bytes())
```

The `Path` import is already present.

### Step 10: run unit tests — confirm GREEN

```
uv run pytest tests/unit/test_executor.py -v
```

All executor tests must pass.

---

## Inner loop 3 — `SourceFile` accepts a loader callable

### Step 11: add `tests/unit/test_source.py`

```python
"""Unit tests for SourceFile: path storage, loader delegation, error on missing loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sketchbook.core.types import Image
from sketchbook.steps.source import SourceFile


def _dummy_loader(path: Path) -> Image:
    """Return a blank image regardless of path."""
    return Image(np.zeros((4, 4, 3), dtype=np.uint8))


def test_source_file_stores_path(tmp_path: Path) -> None:
    """SourceFile remembers the path it was given."""
    p = tmp_path / "photo.png"
    step = SourceFile(p)
    assert step._path == p


def test_source_file_without_loader_raises_on_process(tmp_path: Path) -> None:
    """Calling process() without a loader raises ValueError with a helpful message."""
    step = SourceFile(tmp_path / "photo.png")
    step.setup()
    with pytest.raises(ValueError, match="loader"):
        step.process({}, {})


def test_source_file_process_calls_loader_with_path(tmp_path: Path) -> None:
    """process() passes the stored path to the loader."""
    called_with: list[Path] = []

    def recording_loader(p: Path) -> Image:
        called_with.append(p)
        return Image(np.zeros((4, 4, 3), dtype=np.uint8))

    p = tmp_path / "photo.png"
    step = SourceFile(p, loader=recording_loader)
    step.setup()
    step.process({}, {})

    assert called_with == [p]


def test_source_file_process_returns_loader_result(tmp_path: Path) -> None:
    """process() returns whatever the loader returns."""
    expected = Image(np.full((2, 2, 3), 42, dtype=np.uint8))
    step = SourceFile(tmp_path / "photo.png", loader=lambda _: expected)
    step.setup()
    result = step.process({}, {})
    assert result is expected
```

### Step 12: run unit tests — confirm RED

```
uv run pytest tests/unit/test_source.py -v
```

Expected failures:
- `test_source_file_without_loader_raises_on_process` — currently `process()` calls
  `Image.load` (now missing), so it will raise `AttributeError`, not `ValueError`
- `test_source_file_process_calls_loader_with_path` — `SourceFile.__init__` does not
  accept a `loader` kwarg yet
- `test_source_file_process_returns_loader_result` — same

`test_source_file_stores_path` should pass already.

### Step 13: implement — update `SourceFile`

Update `framework/src/sketchbook/steps/source.py`:

```python
"""SourceFile step — holds a watched path and delegates loading to a caller-supplied loader."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sketchbook.core.step import PipelineStep


class SourceFile(PipelineStep):
    """Reads a file from disk by delegating to a caller-supplied loader function.

    The loader is the sketch's responsibility. This step exists to mark nodes
    that the file watcher should observe — the framework does not care what
    format the file is in.
    """

    def __init__(self, path: str | Path, loader: Callable[[Path], Any] | None = None) -> None:
        self._path = Path(path)
        self._loader = loader
        super().__init__()

    def setup(self) -> None:
        """No inputs — this is a source node."""

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Any:
        """Load and return the file using the provided loader."""
        if self._loader is None:
            raise ValueError(
                f"SourceFile at '{self._path}' has no loader. "
                "Set _source_loader on your Sketch subclass or pass loader= to source()."
            )
        return self._loader(self._path)
```

### Step 14: run unit tests — confirm GREEN

```
uv run pytest tests/unit/test_source.py -v
```

All four tests must pass.

---

## Inner loop 4 — `source()` accepts a `loader=` parameter

### Step 15: add tests to `tests/unit/test_sketch.py`

Add the following tests (do not remove existing ones):

```python
def test_sketch_source_without_loader_fails_on_execute(tmp_path: Path) -> None:
    """A source() call with no loader produces a ValueError in the execution result."""
    _make_asset(tmp_path)

    class _NoLoaderSketch(Sketch):
        name = "no loader"
        description = ""
        date = ""

        def build(self) -> None:
            self.source("photo", "assets/photo.png")

    sketch = _NoLoaderSketch(tmp_path)
    result = execute(sketch.dag)
    assert not result.ok
    err = result.errors["source_photo"]
    assert isinstance(err, ValueError)
    assert "loader" in str(err)


def test_sketch_source_loader_is_called(tmp_path: Path) -> None:
    """loader= passed to source() is invoked during execution."""
    import numpy as np

    _make_asset(tmp_path)
    sentinel = Image(np.zeros((2, 2, 3), dtype=np.uint8))

    class _WithLoaderSketch(Sketch):
        name = "with loader"
        description = ""
        date = ""

        def build(self) -> None:
            self.source("photo", "assets/photo.png", loader=lambda _p: sentinel)

    sketch = _WithLoaderSketch(tmp_path)
    execute(sketch.dag)
    assert sketch.dag.node("source_photo").output is sentinel
```

### Step 16: run unit tests — confirm RED

```
uv run pytest tests/unit/test_sketch.py -v -k "loader"
```

Both new tests should fail: `source()` does not yet accept a `loader=` parameter.

### Step 17: implement — add `loader=` to `Sketch.source()`

Update `framework/src/sketchbook/core/sketch.py`:

- Update `source()` to accept an optional `loader` parameter and forward it to `SourceFile`
- No class attribute needed — the loader is per-call

```python
def source(self, name: str, path: str, loader: Callable[[Path], Any] | None = None) -> _ManagedNode:
    """Add a SourceFile node to the DAG.

    Args:
        name: Node name suffix (becomes source_{name}).
        path: Path relative to the sketch directory.
        loader: Callable that accepts a Path and returns a pipeline value.
                The framework provides no default — image-library choices belong in userland.
    """
    from sketchbook.steps.source import SourceFile

    node_id = f"source_{name}"
    node = self._register_node(
        SourceFile(self._sketch_dir / path, loader=loader), node_id
    )
    log.debug(f"Added source node '{node_id}' watching {self._sketch_dir / path}")
    return node
```

### Step 18: run unit tests — confirm GREEN

```
uv run pytest tests/unit/test_sketch.py -v
```

All tests must pass.

---

## Inner loop 5 — update fixtures and wiring tests

The test infrastructure in `conftest.py` and several unit tests still constructs sketches
via `self.source()` without a `_source_loader`. These will now raise at execution time.

### Step 19: run full suite — catalogue remaining failures

```
uv run pytest -v 2>&1 | grep FAILED
```

Each failing test falls into one of these categories:

**a) Sketch fixtures in `conftest.py`**
`_HelloSketch`, `_EdgeHelloSketch`, `_MultiStepSketch`, `_MaskedEdgeSketch`,
`_NoMaskEdgeSketch` all call `self.source()` without a loader.

Fix: pass `loader=` directly to each `source()` call:
```python
photo = self.source("photo", "assets/photo.jpg", loader=lambda p: Image(cv2.imread(str(p))))
```

**b) Sketch subclasses in watcher tests (`test_watcher.py`)**
`_SingleSourceSketch` and `_TwoSourceSketch` have the same problem.
Apply the same fix.

**c) `test_presets.py` — `SourceFile` constructed directly without a loader**
These tests only build a DAG and never execute it — `process()` is never called — so no
fix is needed. They should pass as-is.

**d) `test_sketch.py` — `_SingleSourceSketch`, `_PipeSketch`, etc.**
Most inline sketch classes in this file only build the DAG and never execute it, so no
loader is needed. Only the two `loader` tests (added in Step 15) call `execute()`, and
those already supply a loader via `source(loader=...)`.

There is no unit test to write for this step — it is purely adapting test fixtures to the
new API. Do not write new implementation. Just update the fixtures.

### Step 20: run full suite — confirm GREEN

```
uv run pytest -v
```

Zero failures.

---

## Inner loop 6 — update `pyproject.toml`

### Step 21: no test to write

This is a packaging change, not a behaviour change. There is no meaningful pytest for
"opencv is not in the wheel's metadata". Verify by inspection.

### Step 22: implement — update `pyproject.toml`

Add `"pillow"` to `[project] dependencies`.
Remove `"opencv-python-headless"` from `[project] dependencies`.
Add it to `[dependency-groups] dev`:

```toml
[project]
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "jinja2",
    "numpy",
    "pillow",
    "watchdog",
    "websockets",
]

[dependency-groups]
dev = [
    "httpx>=0.28.1",
    "opencv-python-headless",
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "ruff>=0.9",
]
```

### Step 23: run full suite — confirm still GREEN

```
uv run pytest -v
```

---

## Outer loop — acceptance test green

### Step 24: run the acceptance test — confirm GREEN

```
uv run pytest tests/acceptance/test_08_loader_decoupling.py -v
```

All nine tests must pass.

Then run the complete suite one final time:

```
uv run pytest -v
```

Zero failures. Run the linter:

```
uv run mise run lint
```

Zero violations.

---

## Step 25: refactor

With both loops green, review for cleanup:

- `framework/tests/unit/test_types.py` — confirm the old load/save tests are fully removed
  and no dead imports remain
- `framework/src/sketchbook/core/types.py` — confirm `PipelineValue` docstring is clear
  about what `from_bytes()` is for (not yet called by anything; deferred to Increment B)
- `framework/src/sketchbook/core/executor.py` — confirm the workdir write is clean and
  the log message still makes sense
- `framework/src/sketchbook/steps/source.py` — confirm the docstring accurately describes
  the new contract
- `framework/src/sketchbook/core/sketch.py` — confirm `_source_loader` is documented on
  the class and the `Callable` import is clean
- `framework/README.md` — update the dependency table (pillow added to runtime, opencv
  moved to dev)
- `docs/decouple-image-type.md` — mark Increment A complete

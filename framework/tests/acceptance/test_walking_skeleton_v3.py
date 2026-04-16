"""Acceptance test: v3 walking skeleton.

Acceptance criteria:
    A @sketch function with one source() and one @step:
    1. GETs /sketch/hello and follows the <img src> URL — returns image/* bytes.
    2. Opens /ws/hello, overwrites the source PNG on disk, and receives a
       step_updated message within 5 seconds.
"""

from __future__ import annotations

import queue
import re
import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import sketch, step
from sketchbook.server.app import create_app
from sketchbook.server.fn_registry import SketchFnRegistry
from tests.conftest import TestImage, write_test_image

# ---------------------------------------------------------------------------
# Inline hello sketch — defined here to exercise the full decorator path
# ---------------------------------------------------------------------------


@step
def passthrough_v3(image: TestImage) -> TestImage:
    """Return the image unchanged."""
    return image


@sketch(date="2026-04-14")
def hello_v3() -> None:
    """Hello world v3 sketch."""
    img = source("assets/hello.png", TestImage.load)
    result = passthrough_v3(img)
    output(result, "main")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fn_registry_client(tmp_fn_sketch: Path) -> Generator[TestClient]:
    """Build a TestClient backed by SketchFnRegistry with the hello_v3 sketch."""
    fn_registry = SketchFnRegistry(
        sketch_fns={"hello": hello_v3},
        sketches_dir=tmp_fn_sketch.parent,
    )
    app = create_app(fn_registry=fn_registry)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_sketch_page_has_img_tag(fn_registry_client: TestClient) -> None:
    """GET /sketch/hello returns HTML containing an <img> tag."""
    resp = fn_registry_client.get("/sketch/hello")
    assert resp.status_code == 200
    assert "<img" in resp.text


def test_img_url_resolves_to_image_bytes(fn_registry_client: TestClient) -> None:
    """The <img src> URL in the sketch page returns image/* content."""
    resp = fn_registry_client.get("/sketch/hello")
    assert resp.status_code == 200

    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', resp.text)
    assert match, f"No <img src=...> found in:\n{resp.text}"
    img_url = match.group(1)

    img_resp = fn_registry_client.get(img_url)
    assert img_resp.status_code == 200
    assert img_resp.headers["content-type"].startswith("image/")


def test_file_change_triggers_step_updated(
    tmp_fn_sketch: Path,
    fn_registry_client: TestClient,
) -> None:
    """Overwriting the source PNG sends a step_updated message over /ws/hello."""
    # Trigger lazy load so the watcher is registered.
    fn_registry_client.get("/sketch/hello")

    received: queue.Queue = queue.Queue()

    def _receive_all(ws) -> None:
        try:
            while True:
                received.put(ws.receive_json())
        except Exception:
            pass

    with fn_registry_client.websocket_connect("/ws/hello") as ws:
        t = threading.Thread(target=_receive_all, args=(ws,), daemon=True)
        t.start()

        # Drain any initial-state messages.
        time.sleep(0.3)
        while not received.empty():
            received.get_nowait()

        # Trigger a file change.
        write_test_image(tmp_fn_sketch / "assets" / "hello.png", color="red")

        try:
            msg = received.get(timeout=5.0)
        except queue.Empty:
            pytest.fail("No WebSocket message received after file change within 5 seconds")

    assert msg["type"] == "step_updated"
    assert "image_url" in msg

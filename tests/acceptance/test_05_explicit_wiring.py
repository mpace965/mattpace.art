"""Acceptance test 05: Explicit Wiring and Optional Inputs.

Acceptance criteria:
    A sketch with source_photo → blur → edge_detect AND source_mask wired as an
    optional input to edge_detect. Changing mask.png re-executes only edge_detect
    (not blur). A sketch with the optional mask input unwired runs successfully.
"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import write_test_image


def test_mask_change_only_reruns_downstream(
    tmp_masked_sketch: Path,
    masked_client: TestClient,
    masked_ws_client,
) -> None:
    """Changing the mask file re-executes edge_detect but not gaussian_blur."""
    received: queue.Queue = queue.Queue()

    def _receive_all(ws) -> None:
        try:
            while True:
                received.put(ws.receive_json())
        except Exception:
            pass

    with masked_ws_client("/ws/edge_portrait") as ws:
        t = threading.Thread(target=_receive_all, args=(ws,), daemon=True)
        t.start()

        # Drain initial-state messages sent on connect.
        time.sleep(0.3)
        while not received.empty():
            received.get_nowait()

        # Overwrite the mask file
        write_test_image(tmp_masked_sketch / "assets" / "mask.png", color="white")

        # Collect all step_updated messages within a short window
        updated_steps: set[str] = set()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                msg = received.get(timeout=0.2)
                if msg["type"] == "step_updated":
                    updated_steps.add(msg["step_id"])
                if "edge_detect_0" in updated_steps:
                    break
            except queue.Empty:
                pass

    assert "edge_detect_0" in updated_steps, "edge_detect_0 was not re-executed"
    assert "gaussian_blur_0" not in updated_steps, "gaussian_blur_0 should not re-execute"


def test_optional_input_not_required(
    tmp_no_mask_sketch: Path,
    no_mask_client: TestClient,
) -> None:
    """A sketch with an optional mask input unwired renders the step page successfully."""
    response = no_mask_client.get("/sketch/edge_portrait_no_mask/step/edge_detect_0")
    assert response.status_code == 200
    assert "<img" in response.text

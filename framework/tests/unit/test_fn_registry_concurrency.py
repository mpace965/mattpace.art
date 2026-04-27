"""Regression test: concurrent set_param and file-change callbacks are serialized."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import pytest

import sketchbook.server.dag_cache as dag_cache_mod
import sketchbook.server.watcher_coordinator as watcher_coordinator_mod
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step
from sketchbook.server.fn_registry import SketchFnRegistry
from tests.conftest import TestImage, make_test_image


@step
def concurrent_threshold(
    image: TestImage,
    *,
    level: Annotated[int, Param(min=0, max=255, step=1, debounce=150)] = 128,
) -> TestImage:
    """Threshold step used for concurrency regression tests."""
    return image


@sketch(date="2026-01-01")
def concurrent_sketch() -> None:
    """Sketch for concurrency regression tests."""
    img = source("assets/hello.png", TestImage.load)
    result = concurrent_threshold(img)
    output(result, "bundle")


@pytest.fixture()
def tmp_concurrent_sketch(tmp_path: Path):
    """Temporary sketch directory for concurrency tests."""
    sketch_dir = tmp_path / "concurrent_sketch"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "hello.png")
    yield sketch_dir


def test_exec_lock_blocks_on_change_during_set_param(
    tmp_concurrent_sketch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """on_change cannot acquire _exec_locks[sketch_id] while set_param holds it."""
    execution_started = threading.Event()
    execution_may_proceed = threading.Event()
    call_log: list[str] = []
    call_log_mu = threading.Lock()

    original_execute_partial = dag_cache_mod.execute_partial_built

    def slow_execute_partial(dag, start_ids, workdir, mode="dev"):
        with call_log_mu:
            call_log.append("execute_start")
        execution_started.set()
        execution_may_proceed.wait(timeout=5)
        result = original_execute_partial(dag, start_ids, workdir, mode)
        with call_log_mu:
            call_log.append("execute_end")
        return result

    monkeypatch.setattr(dag_cache_mod, "execute_partial_built", slow_execute_partial)

    registry = SketchFnRegistry(
        sketch_fns={"concurrent_sketch": concurrent_sketch},
        sketches_dir=tmp_concurrent_sketch.parent,
    )
    # Initial load uses execute_built (not patched), so the patch doesn't interfere.
    dag = registry.get_dag("concurrent_sketch")
    assert dag is not None

    errors: list[Exception] = []

    def do_set_param() -> None:
        try:
            registry.set_param("concurrent_sketch", "concurrent_threshold", "level", 50)
        except Exception as exc:
            errors.append(exc)

    t_param = threading.Thread(target=do_set_param, daemon=True)
    t_param.start()

    # Wait for set_param to enter execute_partial_built (holding the exec lock).
    assert execution_started.wait(timeout=5), "set_param never started executing"
    execution_started.clear()

    # Now simulate an on_change trying to acquire the same lock.
    on_change_acquired = threading.Event()

    def simulate_on_change() -> None:
        # Attempt to acquire the exec lock — should block until set_param releases it.
        with registry._exec_locks["concurrent_sketch"]:
            with call_log_mu:
                call_log.append("on_change_acquired_lock")
            on_change_acquired.set()

    t_change = threading.Thread(target=simulate_on_change, daemon=True)
    t_change.start()

    # Give t_change a moment to reach the lock acquisition attempt.
    time.sleep(0.05)

    # The lock is still held by set_param — on_change must not have acquired it.
    with call_log_mu:
        assert "on_change_acquired_lock" not in call_log, (
            "on_change_acquired_lock appeared before set_param released the exec lock"
        )

    # Unblock set_param.
    execution_may_proceed.set()
    t_param.join(timeout=5)
    t_change.join(timeout=5)

    assert not errors, f"set_param raised: {errors}"

    # on_change must have acquired the lock only after set_param finished executing.
    with call_log_mu:
        assert "execute_end" in call_log
        assert "on_change_acquired_lock" in call_log
        assert call_log.index("execute_end") < call_log.index("on_change_acquired_lock"), (
            f"on_change acquired lock before execute_end: {call_log}"
        )

    # Final output must not be None — execution completed cleanly.
    assert dag.nodes["concurrent_threshold"].output is not None


def test_broadcast_future_exception_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """_log_broadcast_future logs exceptions with sketch and step context."""
    future: concurrent.futures.Future[None] = concurrent.futures.Future()
    future.set_exception(RuntimeError("broadcast boom"))

    with caplog.at_level(logging.ERROR, logger="sketchbook.server.watcher_coordinator"):
        watcher_coordinator_mod._log_broadcast_future(future, sid="my_sketch", nid="my_step")

    assert any(
        "broadcast_results failed for 'my_sketch' after 'my_step' changed" in r.message
        for r in caplog.records
    )


def test_on_change_shutdown_race_does_not_raise(
    tmp_concurrent_sketch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """on_change fired after stop_watcher() (self._loop is None) does not raise."""
    from sketchbook.core import watcher as watcher_mod

    captured: list[Callable] = []
    monkeypatch.setattr(watcher_mod.Watcher, "watch", lambda self, path, cb: captured.append(cb))

    loop = asyncio.new_event_loop()
    registry = SketchFnRegistry(
        sketch_fns={"concurrent_sketch": concurrent_sketch},
        sketches_dir=tmp_concurrent_sketch.parent,
    )
    registry._watcher_coordinator._loop = loop
    registry._watcher_coordinator._watcher = watcher_mod.Watcher()

    dag = registry.get_dag("concurrent_sketch")
    assert dag is not None
    assert captured, "Expected at least one on_change callback to be captured"

    # Simulate stop_watcher() clearing the loop reference mid-flight
    registry._watcher_coordinator._loop = None

    # Must not raise even though self._loop is None
    captured[0]()

    loop.close()

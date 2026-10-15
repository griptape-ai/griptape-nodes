"""Handlers that do CPU-bound image work must leave the engine's event loop free.

A 9000x9000 image takes seconds to re-encode for a write or to shrink for a preview. Done on the
event loop, it stops the engine from answering the editor for that long. Each test parks the slow
step on a worker thread and asks the engine something else while it is parked: if the loop were
held, the question could not be answered until the step gave up waiting.
"""

from __future__ import annotations

import asyncio
import threading
import time
from io import BytesIO
from typing import TYPE_CHECKING, Any

import pytest
from PIL import Image

from griptape_nodes.retained_mode.events.config_events import GetConfigValueRequest, GetConfigValueResultSuccess
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    WriteFileRequest,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.managers.artifact_providers.image.preview_generators.pil_rounded_preview_generator import (
    PILRoundedPreviewGenerator,
)
from griptape_nodes.retained_mode.managers.artifact_providers.image.preview_generators.pil_thumbnail_generator import (
    PILThumbnailGenerator,
)

if TYPE_CHECKING:
    from pathlib import Path

    from griptape_nodes.retained_mode.engine import Engine

# What the editor would tolerate: far shorter than the slow step, far longer than a healthy request.
_RESPONSIVE_WITHIN_SECONDS = 1.0
# Only reached if the loop is held, so the test cannot release the step in time.
_SLOW_STEP_GIVES_UP_SECONDS = 5.0
_START_TIMEOUT_SECONDS = 10.0


class _SlowStep:
    """A stand-in for a slow, synchronous step that stays busy until the test releases it."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.gave_up = False
        self.thread_id: int | None = None

    def run(self, result: Any) -> Any:
        self.thread_id = threading.get_ident()
        self.started.set()
        if not self.release.wait(timeout=_SLOW_STEP_GIVES_UP_SECONDS):
            self.gave_up = True
        return result

    async def wait_until_started(self) -> None:
        deadline = time.monotonic() + _START_TIMEOUT_SECONDS
        while not self.started.is_set():
            if time.monotonic() > deadline:
                msg = "The slow step never started."
                raise AssertionError(msg)
            await asyncio.sleep(0.01)


async def _assert_engine_answers_while_parked(engine: Engine, step: _SlowStep) -> None:
    await step.wait_until_started()
    asked_at = time.monotonic()
    result = await asyncio.wait_for(
        engine.ahandle_request(GetConfigValueRequest(category_and_key="log_level")), timeout=_START_TIMEOUT_SECONDS
    )
    answered_in = time.monotonic() - asked_at
    assert isinstance(result, GetConfigValueResultSuccess), result
    assert answered_in < _RESPONSIVE_WITHIN_SECONDS


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 64), "red").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def slow_metadata_injection(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> _SlowStep:
    """Make the metadata injection a write does (a full image re-encode) wait for the test."""
    step = _SlowStep()
    engine.config_manager.set_config_value("auto_inject_workflow_metadata", True)
    monkeypatch.setattr(engine.artifact_manager, "prepare_content_for_write", lambda data, _name: step.run(data))
    return step


class TestWriteFileRequest:
    @pytest.mark.asyncio
    async def test_engine_answers_while_a_write_prepares_its_content(
        self, engine: Engine, tmp_path: Path, slow_metadata_injection: _SlowStep
    ) -> None:
        target = tmp_path / "out.png"
        write = asyncio.create_task(
            engine.ahandle_request(
                WriteFileRequest(
                    file_path=str(target), content=_png_bytes(), existing_file_policy=ExistingFilePolicy.OVERWRITE
                )
            )
        )
        try:
            await _assert_engine_answers_while_parked(engine, slow_metadata_injection)
        finally:
            slow_metadata_injection.release.set()
            result = await asyncio.wait_for(write, timeout=_START_TIMEOUT_SECONDS)

        assert not slow_metadata_injection.gave_up, "The write held the event loop until its step gave up."
        assert isinstance(result, WriteFileResultSuccess), result
        assert target.read_bytes() == _png_bytes()
        assert slow_metadata_injection.thread_id != threading.get_ident()

    def test_sync_request_without_a_running_loop_writes_the_file(self, engine: Engine, tmp_path: Path) -> None:
        target = tmp_path / "bootstrap.png"

        result = engine.handle_request(
            WriteFileRequest(
                file_path=str(target), content=_png_bytes(), existing_file_policy=ExistingFilePolicy.OVERWRITE
            )
        )

        assert isinstance(result, WriteFileResultSuccess), result
        assert target.exists()

    @pytest.mark.asyncio
    async def test_sync_request_from_inside_a_running_loop_writes_the_file(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        target = tmp_path / "inside_loop.png"

        result = engine.handle_request(
            WriteFileRequest(
                file_path=str(target), content=_png_bytes(), existing_file_policy=ExistingFilePolicy.OVERWRITE
            )
        )

        assert isinstance(result, WriteFileResultSuccess), result
        assert target.exists()

    def test_direct_sync_call_still_writes_the_file(self, engine: Engine, tmp_path: Path) -> None:
        """Storage drivers and the config manager call the synchronous method directly."""
        target = tmp_path / "direct.bin"

        result = engine.os_manager.on_write_file_request(
            WriteFileRequest(file_path=str(target), content=b"abc", existing_file_policy=ExistingFilePolicy.OVERWRITE)
        )

        assert isinstance(result, WriteFileResultSuccess), result
        assert target.read_bytes() == b"abc"


def _make_generator(generator_type: type, engine: Engine, source: Path, destination_dir: Path) -> Any:
    return generator_type(
        str(source),
        "webp",
        str(destination_dir),
        "preview.webp",
        {"max_width": 32, "max_height": 32},
        engine=engine,
    )


class TestPreviewGenerators:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("generator_type", "render_method"),
        [
            (PILThumbnailGenerator, "_render_thumbnail"),
            (PILRoundedPreviewGenerator, "_render_rounded_preview"),
        ],
        ids=["thumbnail", "rounded"],
    )
    async def test_engine_answers_while_a_preview_is_rendered(
        self,
        engine: Engine,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        generator_type: type,
        render_method: str,
    ) -> None:
        source = tmp_path / "source.png"
        source.write_bytes(_png_bytes())
        generator = _make_generator(generator_type, engine, source, tmp_path / "previews")
        step = _SlowStep()
        monkeypatch.setattr(generator, render_method, lambda _image_data: step.run(_png_bytes()))

        generation = asyncio.create_task(generator.attempt_generate_preview())
        try:
            await _assert_engine_answers_while_parked(engine, step)
        finally:
            step.release.set()
            file_name = await asyncio.wait_for(generation, timeout=_START_TIMEOUT_SECONDS)

        assert not step.gave_up, "Rendering the preview held the event loop until it gave up."
        assert (tmp_path / "previews" / file_name).exists()
        assert step.thread_id != threading.get_ident()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "generator_type", [PILThumbnailGenerator, PILRoundedPreviewGenerator], ids=["thumbnail", "rounded"]
    )
    async def test_preview_is_still_rendered_from_the_source_image(
        self, engine: Engine, tmp_path: Path, generator_type: type
    ) -> None:
        source = tmp_path / "source.png"
        Image.new("RGB", (200, 100), "blue").save(source)
        generator = _make_generator(generator_type, engine, source, tmp_path / "previews")

        file_name = await generator.attempt_generate_preview()

        with Image.open(tmp_path / "previews" / file_name) as preview:
            assert preview.width == 32  # noqa: PLR2004
            assert preview.height <= 32  # noqa: PLR2004

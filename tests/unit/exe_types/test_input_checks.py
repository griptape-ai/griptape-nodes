# ruff: noqa: PLR2004

"""Tests for the checks nodes run on their media inputs before a run."""

from __future__ import annotations

import base64
import json
import subprocess
from io import BytesIO
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from PIL import Image

from griptape_nodes.exe_types import input_checks
from griptape_nodes.exe_types.input_checks import (
    ImageInfo,
    VideoProbe,
    check_aspect_ratio_range,
    check_count,
    check_dimensions,
    check_duration,
    check_frame_rate,
    check_mime_type,
    check_size,
    image_errors,
    input_check_budget,
    input_subject,
    local_image_info,
    local_size_bytes,
    local_video_probe,
    video_errors,
)
from griptape_nodes.exe_types.node_error import NodeError

if TYPE_CHECKING:
    from pathlib import Path


def _probed_seconds(value: Any) -> float | None:
    """The stream duration `local_video_probe` reads, or None when it reads nothing."""
    probe = local_video_probe(value)
    if probe is None:
        return None
    return probe.seconds


def _probed_frame(value: Any) -> ImageInfo | None:
    """The frame size `local_video_probe` reads, or None when it reads nothing."""
    probe = local_video_probe(value)
    if probe is None:
        return None
    return probe.info


SUBJECT = "Image 2 in 'reference images'"
DOCS = "https://example.com/limits"


def _png_bytes(width: int, height: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height)).save(buffer, format="PNG")
    return buffer.getvalue()


def _rotated_jpeg_bytes(width: int, height: int, orientation: int) -> bytes:
    """A JPEG stored `width`x`height` with an EXIF Orientation tag, as phones save a rotated shot."""
    exif = Image.Exif()
    exif[0x0112] = orientation
    buffer = BytesIO()
    Image.new("RGB", (width, height)).save(buffer, format="JPEG", exif=exif.tobytes())
    return buffer.getvalue()


def _data_uri(data: bytes, mime_type: str = "image/png") -> str:
    return f"data:{mime_type};base64,{base64.b64encode(data).decode()}"


class TestInputSubject:
    def test_names_a_position_in_a_list(self) -> None:
        assert input_subject("reference images", noun="image", position=2) == SUBJECT

    def test_names_a_single_input(self) -> None:
        assert input_subject("start frame", noun="image") == "The image in 'start frame'"


class TestLocalSizeBytes:
    @pytest.mark.parametrize("length", [1, 2, 3, 100, 1001])
    def test_measures_a_data_uri_exactly(self, length: int) -> None:
        assert local_size_bytes(_data_uri(b"x" * length), kind="image") == length

    def test_ignores_line_breaks_in_a_data_uri(self) -> None:
        wrapped = f"data:image/png;base64,{base64.encodebytes(b'x' * 1000).decode()}"
        assert local_size_bytes(wrapped, kind="image") == 1000

    def test_measures_a_local_file(self, tmp_path: Path) -> None:
        path = tmp_path / "image.png"
        path.write_bytes(b"x" * 1234)
        assert local_size_bytes(ImageUrlArtifact(value=str(path)), kind="image") == 1234

    def test_skips_a_remote_url(self) -> None:
        assert local_size_bytes("https://example.com/image.png", kind="image") is None

    def test_skips_a_path_the_os_refuses(self) -> None:
        assert local_size_bytes("A" * 3000, kind="image") is None

    def test_skips_a_missing_file(self, tmp_path: Path) -> None:
        assert local_size_bytes(str(tmp_path / "missing.png"), kind="image") is None

    def test_skips_an_empty_value(self) -> None:
        assert local_size_bytes(None, kind="image") is None


class TestLocalImageInfo:
    def test_reads_a_data_uri(self) -> None:
        assert local_image_info(_data_uri(_png_bytes(40, 30))) == ImageInfo(40, 30, "image/png")

    @pytest.mark.parametrize("orientation", [5, 6, 7, 8])
    def test_reports_an_exif_rotated_photo_as_displayed(self, orientation: int) -> None:
        image = _data_uri(_rotated_jpeg_bytes(400, 300, orientation), "image/jpeg")
        assert local_image_info(image) == ImageInfo(300, 400, "image/jpeg")

    @pytest.mark.parametrize("orientation", [1, 2, 3, 4])
    def test_keeps_the_stored_size_when_exif_does_not_rotate_a_quarter_turn(self, orientation: int) -> None:
        image = _data_uri(_rotated_jpeg_bytes(400, 300, orientation), "image/jpeg")
        assert local_image_info(image) == ImageInfo(400, 300, "image/jpeg")

    def test_reads_a_local_file(self, tmp_path: Path) -> None:
        path = tmp_path / "image.jpg"
        Image.new("RGB", (64, 48)).save(path, format="JPEG")
        assert local_image_info(str(path)) == ImageInfo(64, 48, "image/jpeg")

    def test_reads_an_image_artifact(self) -> None:
        artifact = ImageArtifact(value=_png_bytes(8, 4), format="png", width=8, height=4)
        assert local_image_info(artifact) == ImageInfo(8, 4, "image/png")

    def test_reports_a_multi_picture_jpeg_as_jpeg(self) -> None:
        buffer = BytesIO()
        Image.new("RGB", (8, 8)).save(buffer, format="MPO", save_all=True, append_images=[Image.new("RGB", (8, 8))])
        assert local_image_info(_data_uri(buffer.getvalue(), "image/jpeg")) == ImageInfo(8, 8, "image/jpeg")

    def test_skips_an_image_too_large_to_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
        assert local_image_info(_data_uri(_png_bytes(40, 30))) is None

    def test_skips_a_remote_url(self) -> None:
        assert local_image_info("https://example.com/image.png") is None

    def test_skips_an_image_pillow_recognises_but_cannot_decode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def unimplemented(*_args: Any, **_kwargs: Any) -> None:
            msg = "Unimplemented DXGI format 10"
            raise NotImplementedError(msg)

        monkeypatch.setattr(input_checks.Image, "open", unimplemented)
        assert local_image_info(_data_uri(_png_bytes(8, 8))) is None

    def test_skips_bytes_that_are_not_an_image(self) -> None:
        assert local_image_info(_data_uri(b"not an image")) is None


class TestLocalVideoDuration:
    @pytest.fixture(autouse=True)
    def no_ffmpeg_download(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fetch(*_args: Any, **_kwargs: Any) -> None:
            pytest.fail("a pre-run input check must never fetch ffmpeg")

        monkeypatch.setattr(input_checks.static_ffmpeg_run, "get_or_fetch_platform_executables_else_raise", fetch)

    @pytest.fixture
    def clip(self, tmp_path: Path) -> Path:
        path = tmp_path / "clip.mp4"
        path.write_bytes(b"video")
        return path

    @pytest.fixture
    def ffprobe_runs(self, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
        """Pretend ffprobe is installed and answer every run with a 9.5 second duration."""
        runs: list[dict[str, Any]] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> SimpleNamespace:
            runs.append({"cmd": cmd, **kwargs})
            return SimpleNamespace(stdout=json.dumps({"format": {"duration": "9.5"}}))

        monkeypatch.setattr(input_checks, "_installed_ffprobe", lambda: "/usr/bin/ffprobe")
        monkeypatch.setattr(input_checks.subprocess, "run", fake_run)
        return runs

    def test_probes_a_local_file_with_a_short_timeout(self, clip: Path, ffprobe_runs: list[dict[str, Any]]) -> None:
        assert _probed_seconds(VideoUrlArtifact(value=str(clip))) == 9.5
        assert ffprobe_runs[0]["cmd"][0] == "/usr/bin/ffprobe"
        assert ffprobe_runs[0]["cmd"][-1] == str(clip)
        assert ffprobe_runs[0]["timeout"] == input_checks.FFPROBE_TIMEOUT_SECONDS

    def test_decodes_ffprobe_output_as_utf8(self, clip: Path, ffprobe_runs: list[dict[str, Any]]) -> None:
        # ffprobe echoes the file name in UTF-8; decoding with Windows' code page fails on a non-Latin one.
        _probed_seconds(str(clip))
        assert ffprobe_runs[0]["encoding"] == "utf-8"

    def test_gives_each_probe_the_probe_timeout_outside_a_budget(
        self, clip: Path, ffprobe_runs: list[dict[str, Any]]
    ) -> None:
        _probed_seconds(str(clip))
        assert ffprobe_runs[0]["timeout"] == input_checks.FFPROBE_TIMEOUT_SECONDS

    def test_gives_a_probe_only_what_is_left_of_the_budget(
        self, clip: Path, ffprobe_runs: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = [100.0]
        monkeypatch.setattr(input_checks.time, "monotonic", lambda: now[0])
        with input_check_budget(seconds=3):
            _probed_seconds(str(clip))
            now[0] += 2.5
            _probed_seconds(str(clip))
        assert [run["timeout"] for run in ffprobe_runs] == [input_checks.FFPROBE_TIMEOUT_SECONDS, 0.5]

    def test_skips_a_probe_once_the_budget_is_spent(
        self, clip: Path, ffprobe_runs: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = [100.0]
        monkeypatch.setattr(input_checks.time, "monotonic", lambda: now[0])
        with input_check_budget(seconds=3):
            now[0] += 3
            assert _probed_seconds(str(clip)) is None
        assert ffprobe_runs == []

    def test_lets_a_nested_budget_shorten_but_not_extend_the_outer_one(
        self, clip: Path, ffprobe_runs: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = [100.0]
        monkeypatch.setattr(input_checks.time, "monotonic", lambda: now[0])
        with input_check_budget(seconds=3):
            with input_check_budget(seconds=60):
                now[0] += 2.5
                _probed_seconds(str(clip))
            with input_check_budget(seconds=0.2):
                _probed_seconds(str(clip))
        assert [run["timeout"] for run in ffprobe_runs] == [0.5, pytest.approx(0.2)]

    def test_ends_the_budget_with_its_block(
        self, clip: Path, ffprobe_runs: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = [100.0]
        monkeypatch.setattr(input_checks.time, "monotonic", lambda: now[0])
        with input_check_budget(seconds=1):
            now[0] += 5
        assert _probed_seconds(str(clip)) == 9.5
        assert ffprobe_runs[0]["timeout"] == input_checks.FFPROBE_TIMEOUT_SECONDS

    def test_skips_when_ffprobe_times_out(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def slow_run(cmd: list[str], **kwargs: Any) -> SimpleNamespace:
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

        monkeypatch.setattr(input_checks, "_installed_ffprobe", lambda: "/usr/bin/ffprobe")
        monkeypatch.setattr(input_checks.subprocess, "run", slow_run)

        assert _probed_seconds(str(clip)) is None

    def test_skips_when_the_probe_fails(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def failing_run(cmd: list[str], **_kwargs: Any) -> SimpleNamespace:
            raise subprocess.CalledProcessError(1, cmd, stderr="Invalid data found")

        monkeypatch.setattr(input_checks, "_installed_ffprobe", lambda: "/usr/bin/ffprobe")
        monkeypatch.setattr(input_checks.subprocess, "run", failing_run)

        assert _probed_seconds(str(clip)) is None

    def test_skips_when_ffprobe_is_not_installed(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(input_checks, "_installed_ffprobe", lambda: None)
        monkeypatch.setattr(input_checks.subprocess, "run", lambda *_a, **_k: pytest.fail("ffprobe must not run"))

        assert _probed_seconds(str(clip)) is None

    @pytest.mark.parametrize("value", ["https://example.com/clip.mp4", "data:video/mp4;base64,AAAA"])
    def test_does_not_probe_a_remote_or_inline_video(self, value: str, ffprobe_runs: list[dict[str, Any]]) -> None:
        assert _probed_seconds(value) is None
        assert ffprobe_runs == []


class TestLocalVideoProbe:
    @pytest.fixture
    def clip(self, tmp_path: Path) -> Path:
        path = tmp_path / "clip.mp4"
        path.write_bytes(b"video")
        return path

    def _answer(self, monkeypatch: pytest.MonkeyPatch, output: dict[str, Any]) -> list[list[str]]:
        runs: list[list[str]] = []

        def fake_run(cmd: list[str], **_kwargs: Any) -> SimpleNamespace:
            runs.append(cmd)
            return SimpleNamespace(stdout=json.dumps(output))

        monkeypatch.setattr(input_checks, "_installed_ffprobe", lambda: "/usr/bin/ffprobe")
        monkeypatch.setattr(input_checks.subprocess, "run", fake_run)
        return runs

    def test_reads_size_and_duration_in_one_ffprobe_run(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        runs = self._answer(
            monkeypatch,
            {
                "format": {"duration": "9.5"},
                "streams": [{"width": 1920, "height": 1080, "avg_frame_rate": "30000/1001"}],
            },
        )
        probe = local_video_probe(str(clip))
        assert probe is not None
        assert probe.info == ImageInfo(1920, 1080, None)
        assert probe.seconds == 9.5
        assert probe.fps == pytest.approx(29.97, abs=0.01)
        assert len(runs) == 1
        assert "-show_format" in runs[0]
        assert "-show_streams" in runs[0]

    def test_takes_the_duration_from_the_video_stream_not_the_container(
        self, clip: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A 10 s video with a 31 s audio track: the container reports the longer audio.
        self._answer(
            monkeypatch,
            {"format": {"duration": "31.0"}, "streams": [{"width": 1280, "height": 720, "duration": "10.0"}]},
        )
        probe = local_video_probe(str(clip))
        assert probe is not None
        assert probe.seconds == 10.0

    def test_falls_back_to_the_container_duration(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._answer(monkeypatch, {"format": {"duration": "7.5"}, "streams": [{"width": 1280, "height": 720}]})
        probe = local_video_probe(str(clip))
        assert probe is not None
        assert probe.seconds == 7.5

    def test_reports_the_part_ffprobe_gave_when_the_other_is_missing(
        self, clip: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._answer(monkeypatch, {"format": {"duration": "4.0"}, "streams": []})
        assert local_video_probe(str(clip)) == VideoProbe(info=None, seconds=4.0, fps=None, container_seconds=4.0)

    def test_skips_when_ffprobe_is_not_installed(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(input_checks, "_installed_ffprobe", lambda: None)
        assert local_video_probe(str(clip)) is None

    def test_skips_a_remote_video(self) -> None:
        assert local_video_probe("https://example.com/clip.mp4") is None

    @pytest.mark.parametrize(
        ("stream", "container", "shortest", "longest"),
        [(10.0, 31.0, 10.0, 31.0), (None, 7.5, 7.5, 7.5), (None, None, None, None)],
        ids=["both", "container-only", "neither"],
    )
    def test_reports_the_shorter_and_longer_duration(
        self, stream: float | None, container: float | None, shortest: float | None, longest: float | None
    ) -> None:
        probe = VideoProbe(info=None, seconds=stream, container_seconds=container)
        assert probe.shortest_seconds == shortest
        assert probe.longest_seconds == longest


class TestLocalVideoInfo:
    @pytest.fixture
    def clip(self, tmp_path: Path) -> Path:
        path = tmp_path / "clip.mp4"
        path.write_bytes(b"video")
        return path

    def _answer(self, monkeypatch: pytest.MonkeyPatch, stream: dict[str, Any]) -> None:
        monkeypatch.setattr(input_checks, "_installed_ffprobe", lambda: "/usr/bin/ffprobe")
        monkeypatch.setattr(
            input_checks.subprocess,
            "run",
            lambda *_a, **_k: SimpleNamespace(stdout=json.dumps({"streams": [stream]})),
        )

    def test_reads_the_frame_size(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._answer(monkeypatch, {"width": 1920, "height": 1080})
        assert _probed_frame(str(clip)) == ImageInfo(1920, 1080, None)

    def test_treats_a_0x0_frame_size_as_unread(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._answer(monkeypatch, {"width": 0, "height": 0})
        assert _probed_frame(str(clip)) is None

    @pytest.mark.parametrize(
        "stream",
        [
            {"width": 1920, "height": 1080, "tags": {"rotate": "90"}},
            {"width": 1920, "height": 1080, "side_data_list": [{"rotation": -90}]},
        ],
        ids=["rotate-tag", "display-matrix"],
    )
    def test_reports_a_rotated_clip_as_displayed(
        self, clip: Path, monkeypatch: pytest.MonkeyPatch, stream: dict[str, Any]
    ) -> None:
        self._answer(monkeypatch, stream)
        assert _probed_frame(str(clip)) == ImageInfo(1080, 1920, None)

    def test_skips_when_ffprobe_is_not_installed(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(input_checks, "_installed_ffprobe", lambda: None)
        assert _probed_frame(str(clip)) is None

    def test_skips_a_remote_video(self) -> None:
        assert _probed_frame("https://example.com/clip.mp4") is None


class TestInstalledFfprobe:
    @pytest.fixture(autouse=True)
    def no_ffmpeg_download(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fetch(*_args: Any, **_kwargs: Any) -> None:
            pytest.fail("a pre-run input check must never fetch ffmpeg")

        monkeypatch.setattr(input_checks.static_ffmpeg_run, "get_or_fetch_platform_executables_else_raise", fetch)

    def _platform_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exe_name: str = "ffprobe") -> Path:
        monkeypatch.setattr(input_checks.static_ffmpeg_run, "get_platform_dir", lambda: str(tmp_path))
        (tmp_path / exe_name).write_bytes(b"")
        return tmp_path

    @pytest.mark.parametrize(("platform", "exe_name"), [("linux", "ffprobe"), ("win32", "ffprobe.exe")])
    def test_uses_a_finished_static_ffmpeg_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str, exe_name: str
    ) -> None:
        monkeypatch.setattr(input_checks.sys, "platform", platform)
        platform_dir = self._platform_dir(tmp_path, monkeypatch, exe_name)
        (platform_dir / "installed.crumb").write_text("installed")
        assert input_checks._installed_ffprobe() == str(platform_dir / exe_name)

    def test_ignores_an_unfinished_static_ffmpeg_install(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._platform_dir(tmp_path, monkeypatch)
        monkeypatch.setattr(input_checks.shutil, "which", lambda _name: None)
        assert input_checks._installed_ffprobe() is None

    def test_falls_back_to_ffprobe_on_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._platform_dir(tmp_path, monkeypatch)
        monkeypatch.setattr(input_checks.shutil, "which", lambda _name: "/opt/bin/ffprobe")
        assert input_checks._installed_ffprobe() == "/opt/bin/ffprobe"


class TestCheckCount:
    def test_allows_the_maximum(self) -> None:
        assert check_count(3, maximum=3, parameter="reference images") is None

    def test_rejects_more_than_the_maximum(self) -> None:
        error = check_count(5, maximum=3, parameter="reference images", noun="images", docs_url=DOCS)
        assert isinstance(error, NodeError)
        assert str(error) == "5 images are connected to 'reference images' and the limit is 3. Remove 2."
        assert error.links is not None
        assert error.links[0].url == DOCS


class TestCheckSize:
    def test_allows_the_maximum(self) -> None:
        assert check_size(7 * 1024 * 1024, maximum_bytes=7 * 1024 * 1024, subject=SUBJECT) is None

    def test_skips_an_unknown_size(self) -> None:
        assert check_size(None, maximum_bytes=1, subject=SUBJECT) is None

    def test_rejects_a_larger_file(self) -> None:
        error = check_size(int(8.5 * 1024 * 1024), maximum_bytes=7 * 1024 * 1024, subject=SUBJECT)
        assert error is not None
        assert str(error) == f"{SUBJECT} is 8.5 MB and the limit is 7 MB. Use a smaller file."
        assert not error.links

    def test_reports_a_size_just_over_the_limit_as_over_it(self) -> None:
        error = check_size(7 * 1024 * 1024 + 1024, maximum_bytes=7 * 1024 * 1024, subject=SUBJECT)
        assert str(error).startswith(f"{SUBJECT} is 7.001 MB and the limit is 7 MB.")

    def test_reports_a_size_over_a_non_round_limit_as_over_it(self) -> None:
        error = check_size(10_000_001, maximum_bytes=10_000_000, subject=SUBJECT)
        assert str(error).startswith(f"{SUBJECT} is 9.54 MB and the limit is 9.53674 MB.")

    def test_never_shows_the_size_and_limit_as_the_same_number(self) -> None:
        error = check_size(200_000_001, maximum_bytes=200_000_000, subject=SUBJECT)
        assert str(error).startswith(f"{SUBJECT} is 190.735 MB and the limit is 190.734 MB.")

    def test_uses_the_given_fix(self) -> None:
        error = check_size(2, maximum_bytes=1, subject=SUBJECT, fix="Turn on 'Auto Image Resize'.")
        assert error is not None
        assert str(error).endswith("Turn on 'Auto Image Resize'.")


class TestCheckDimensions:
    def test_allows_an_image_within_every_limit(self) -> None:
        info = ImageInfo(1280, 720, "image/png")
        assert check_dimensions(info, subject=SUBJECT, min_side=200, max_side=4096, max_megapixels=16) is None

    def test_skips_an_unknown_image(self) -> None:
        assert check_dimensions(None, subject=SUBJECT, min_side=10_000) is None

    def test_rejects_a_short_side(self) -> None:
        error = check_dimensions(ImageInfo(1000, 150, None), subject=SUBJECT, min_side=200)
        assert str(error) == f"{SUBJECT} is 1000x150 and each side must be at least 200 pixels. Use a larger one."

    def test_rejects_a_long_side(self) -> None:
        error = check_dimensions(ImageInfo(300, 5000, None), subject=SUBJECT, max_side=4096)
        assert str(error) == f"{SUBJECT} is 300x5000 and each side must be at most 4096 pixels. Resize it smaller."

    def test_rejects_too_many_pixels(self) -> None:
        error = check_dimensions(ImageInfo(4000, 4000, None), subject=SUBJECT, max_megapixels=8)
        assert str(error) == (
            f"{SUBJECT} is 4000x4000 (16.0 megapixels) and the limit is 8 megapixels. Resize it smaller."
        )

    def test_reports_megapixels_just_over_the_limit_as_over_them(self) -> None:
        error = check_dimensions(ImageInfo(2829, 2829, None), subject=SUBJECT, max_megapixels=8)
        assert "(8.003 megapixels)" in str(error)

    def test_allows_exactly_the_minimum_area(self) -> None:
        assert check_dimensions(ImageInfo(614, 664, None), subject=SUBJECT, min_megapixels=0.407696) is None

    def test_rejects_too_few_pixels(self) -> None:
        error = check_dimensions(ImageInfo(640, 480, None), subject=SUBJECT, min_megapixels=0.407696)
        assert str(error) == (
            f"{SUBJECT} is 640x480 (0.3 megapixels) and the minimum is 0.407696 megapixels. Use a larger one."
        )

    def test_reports_megapixels_just_under_the_minimum_as_under_it(self) -> None:
        error = check_dimensions(ImageInfo(1999, 1000, None), subject=SUBJECT, min_megapixels=2)
        assert "(1.999 megapixels) and the minimum is 2 megapixels" in str(error)


class TestCheckAspectRatioRange:
    @pytest.mark.parametrize(("width", "height"), [(300, 900), (900, 300), (1000, 1000), (1920, 1080)])
    def test_allows_a_shape_in_range_including_the_ends(self, width: int, height: int) -> None:
        info = ImageInfo(width, height, None)
        assert check_aspect_ratio_range(info, subject=SUBJECT, widest="3:1", tallest="1:3") is None

    def test_rejects_a_shape_that_is_too_wide(self) -> None:
        error = check_aspect_ratio_range(ImageInfo(1000, 300, None), subject=SUBJECT, widest="3:1", tallest="1:3")
        assert str(error) == (
            f"{SUBJECT} is 1000x300, which is too wide. The aspect ratio must be between 1:3 and 3:1. Crop it."
        )

    def test_rejects_a_shape_that_is_too_tall(self) -> None:
        error = check_aspect_ratio_range(ImageInfo(250, 1000, None), subject=SUBJECT, widest="3:1", tallest="1:3")
        assert str(error) == (
            f"{SUBJECT} is 250x1000, which is too tall. The aspect ratio must be between 1:3 and 3:1. Crop it."
        )

    def test_names_the_bound_that_failed_for_a_portrait_only_range(self) -> None:
        error = check_aspect_ratio_range(ImageInfo(1000, 1000, None), subject=SUBJECT, widest="3:4", tallest="9:16")
        assert "which is too wide" in str(error)

    def test_skips_an_unknown_image(self) -> None:
        assert check_aspect_ratio_range(None, subject=SUBJECT, widest="3:1", tallest="1:3") is None


class TestImageErrors:
    LIMITS: ClassVar[dict[str, Any]] = {
        "allowed_mime_types": ("image/jpeg", "image/png"),
        "maximum_bytes": 10 * 1024 * 1024,
        "min_side": 300,
        "widest": "2.5:1",
        "tallest": "1:2.5",
    }

    def test_judges_an_exif_rotated_photo_by_its_displayed_shape(self) -> None:
        # Stored 4032x3024 but shown portrait, as a phone saves a portrait shot.
        photo = _data_uri(_rotated_jpeg_bytes(4032, 3024, 6), "image/jpeg")
        assert image_errors(photo, subject=SUBJECT, widest="1:1", tallest="9:16") == []

    @pytest.mark.parametrize(("widest", "tallest"), [("3:1", None), (None, "1:3")], ids=["widest-only", "tallest-only"])
    def test_refuses_half_an_aspect_ratio_range(self, widest: str | None, tallest: str | None) -> None:
        with pytest.raises(ValueError, match="only one of widest and tallest"):
            image_errors(_data_uri(_png_bytes(4000, 1000)), subject=SUBJECT, widest=widest, tallest=tallest)

    def test_accepts_an_image_within_every_limit(self) -> None:
        assert image_errors(_data_uri(_png_bytes(800, 600)), subject=SUBJECT, **self.LIMITS) == []

    def test_reports_every_limit_the_image_breaks(self) -> None:
        buffer = BytesIO()
        Image.new("RGB", (200, 1000)).save(buffer, format="GIF")
        messages = [
            str(e) for e in image_errors(_data_uri(buffer.getvalue(), "image/gif"), subject=SUBJECT, **self.LIMITS)
        ]
        assert messages == [
            f"{SUBJECT} is in GIF format. Convert it to JPEG or PNG.",
            f"{SUBJECT} is 200x1000 and each side must be at least 300 pixels. Use a larger one.",
            f"{SUBJECT} is 200x1000, which is too tall. The aspect ratio must be between 1:2.5 and 2.5:1. Crop it.",
        ]

    def test_runs_only_the_checks_whose_limits_are_given(self) -> None:
        image = _data_uri(_png_bytes(100, 1000))
        assert image_errors(image, subject=SUBJECT, allowed_mime_types=("image/png",)) == []
        assert [str(e) for e in image_errors(image, subject=SUBJECT, min_side=300)] == [
            f"{SUBJECT} is 100x1000 and each side must be at least 300 pixels. Use a larger one."
        ]

    def test_checks_the_area(self) -> None:
        errors = image_errors(_data_uri(_png_bytes(400, 300)), subject=SUBJECT, max_megapixels=0.1)
        assert [str(e) for e in errors] == [
            f"{SUBJECT} is 400x300 (0.12 megapixels) and the limit is 0.1 megapixels. Resize it smaller."
        ]

    def test_checks_the_minimum_area(self) -> None:
        errors = image_errors(_data_uri(_png_bytes(400, 300)), subject=SUBJECT, min_megapixels=0.2)
        assert [str(e) for e in errors] == [
            f"{SUBJECT} is 400x300 (0.1 megapixels) and the minimum is 0.2 megapixels. Use a larger one."
        ]

    def test_checks_the_size(self) -> None:
        errors = image_errors(_data_uri(_png_bytes(800, 600)), subject=SUBJECT, maximum_bytes=10)
        assert len(errors) == 1
        assert "and the limit is" in str(errors[0])

    def test_links_the_docs_page(self) -> None:
        errors = image_errors(_data_uri(_png_bytes(100, 100)), subject=SUBJECT, min_side=300, docs_url=DOCS)
        assert errors[0].links
        assert errors[0].links[0].url == DOCS

    def test_skips_a_remote_image(self) -> None:
        assert image_errors("https://example.com/image.gif", subject=SUBJECT, **self.LIMITS) == []


class TestVideoErrors:
    @pytest.fixture
    def clip(self, tmp_path: Path) -> Path:
        path = tmp_path / "clip.mp4"
        path.write_bytes(b"video")
        return path

    def _probe(self, monkeypatch: pytest.MonkeyPatch, info: ImageInfo | None, seconds: float | None) -> list[Any]:
        calls: list[Any] = []

        def fake_probe(value: Any) -> VideoProbe:
            calls.append(value)
            return VideoProbe(info=info, seconds=seconds)

        monkeypatch.setattr(input_checks, "local_video_probe", fake_probe)
        return calls

    def test_accepts_a_video_within_every_limit(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._probe(monkeypatch, ImageInfo(1280, 720, None), 5.0)
        assert (
            video_errors(
                str(clip),
                subject=SUBJECT,
                maximum_bytes=1024,
                min_seconds=2,
                max_seconds=30,
                min_side=200,
                max_side=2048,
                widest="3:1",
                tallest="1:3",
            )
            == []
        )

    def test_reports_every_limit_the_video_breaks_from_one_probe(
        self, clip: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._probe(monkeypatch, ImageInfo(4000, 1000, None), 40.0)
        messages = [
            str(e)
            for e in video_errors(
                str(clip),
                subject=SUBJECT,
                max_seconds=30,
                max_side=2048,
                widest="3:1",
                tallest="1:3",
            )
        ]
        assert messages == [
            f"{SUBJECT} is 40.00 seconds long and the limit is 30. Use a Trim Video node to shorten it.",
            f"{SUBJECT} is 4000x1000 and each side must be at most 2048 pixels. Resize it smaller.",
            f"{SUBJECT} is 4000x1000, which is too wide. The aspect ratio must be between 1:3 and 3:1. Crop it.",
        ]
        assert len(calls) == 1

    def test_checks_the_size_without_probing(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._probe(monkeypatch, ImageInfo(1280, 720, None), 5.0)
        errors = video_errors(str(clip), subject=SUBJECT, maximum_bytes=1)
        assert len(errors) == 1
        assert "and the limit is" in str(errors[0])
        assert calls == []

    def test_checks_the_area(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._probe(monkeypatch, ImageInfo(4000, 2100, None), 5.0)
        errors = video_errors(str(clip), subject=SUBJECT, max_megapixels=8.2944)
        assert len(errors) == 1
        assert "megapixels" in str(errors[0])

    def test_checks_the_minimum_area(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._probe(monkeypatch, ImageInfo(640, 480, None), 5.0)
        errors = video_errors(str(clip), subject=SUBJECT, min_megapixels=0.407696)
        assert [str(e) for e in errors] == [
            f"{SUBJECT} is 640x480 (0.3 megapixels) and the minimum is 0.407696 megapixels. Use a larger one."
        ]
        assert len(calls) == 1

    @pytest.mark.parametrize(
        ("average", "nominal", "min_fps", "max_fps", "expected"),
        [
            # A 60 fps screen recording averaging 19 fps: the minimum uses the higher, declared rate.
            (19.1, 60.0, 24, 60, None),
            # A clip declaring 120 fps but averaging 50: the maximum uses the lower, average rate.
            (50.0, 120.0, 24, 60, None),
            # Both rates under the minimum still fail, quoting the higher.
            (15.0, 20.0, 24, None, "is 20 fps and the minimum is 24 fps."),
        ],
        ids=["vfr-under-min-average", "vfr-over-max-nominal", "both-under-min"],
    )
    def test_checks_each_frame_rate_bound_against_the_easier_rate(  # noqa: PLR0913, PLR0917
        self,
        clip: Path,
        monkeypatch: pytest.MonkeyPatch,
        average: float,
        nominal: float,
        min_fps: float | None,
        max_fps: float | None,
        expected: str | None,
    ) -> None:
        monkeypatch.setattr(
            input_checks,
            "local_video_probe",
            lambda _value: VideoProbe(info=None, seconds=5.0, fps=average, nominal_fps=nominal),
        )
        messages = [str(e) for e in video_errors(str(clip), subject=SUBJECT, min_fps=min_fps, max_fps=max_fps)]
        if expected is None:
            assert messages == []
        else:
            assert len(messages) == 1
            assert expected in messages[0]

    def test_checks_the_frame_rate(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            input_checks, "local_video_probe", lambda _value: VideoProbe(info=None, seconds=5.0, fps=15.0)
        )
        errors = video_errors(str(clip), subject=SUBJECT, min_fps=24, max_fps=60)
        assert [str(e) for e in errors] == [
            f"{SUBJECT} is 15 fps and the minimum is 24 fps. Re-export it at a higher frame rate."
        ]

    @pytest.mark.parametrize(
        ("stream", "container", "min_seconds", "max_seconds", "expected"),
        [
            # A 10 s video with a 31 s audio track: the maximum is checked against the video.
            (10.0, 31.0, None, 30, None),
            # A 2.9 s video with 3.5 s of audio: the minimum is checked against the longer reading.
            (2.9, 3.5, 3, None, None),
            # Both readings over the maximum still fail, quoting the shorter.
            (31.0, 32.0, None, 30, "is 31.00 seconds long and the limit is 30."),
            # Both readings under the minimum still fail, quoting the longer.
            (2.0, 2.5, 3, None, "is 2.50 seconds long and the minimum is 3."),
        ],
        ids=["long-audio-under-max", "long-audio-over-min", "both-over-max", "both-under-min"],
    )
    def test_checks_each_bound_against_the_easier_duration(  # noqa: PLR0913, PLR0917
        self,
        clip: Path,
        monkeypatch: pytest.MonkeyPatch,
        stream: float,
        container: float,
        min_seconds: float | None,
        max_seconds: float | None,
        expected: str | None,
    ) -> None:
        monkeypatch.setattr(
            input_checks,
            "local_video_probe",
            lambda _value: VideoProbe(info=None, seconds=stream, container_seconds=container),
        )
        errors = video_errors(str(clip), subject=SUBJECT, min_seconds=min_seconds, max_seconds=max_seconds)
        messages = [str(e) for e in errors]
        if expected is None:
            assert messages == []
        else:
            assert len(messages) == 1
            assert expected in messages[0]

    def test_uses_a_probe_the_caller_already_read(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._probe(monkeypatch, ImageInfo(1280, 720, None), 5.0)
        probe = VideoProbe(info=ImageInfo(4000, 1000, None), seconds=40.0)
        errors = video_errors(str(clip), subject=SUBJECT, max_seconds=30, max_side=2048, probe=probe)
        assert [str(e) for e in errors] == [
            f"{SUBJECT} is 40.00 seconds long and the limit is 30. Use a Trim Video node to shorten it.",
            f"{SUBJECT} is 4000x1000 and each side must be at most 2048 pixels. Resize it smaller.",
        ]
        assert calls == []

    def test_does_not_probe_again_a_video_the_caller_could_not_read(
        self, clip: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._probe(monkeypatch, ImageInfo(4000, 1000, None), 40.0)
        assert video_errors(str(clip), subject=SUBJECT, max_seconds=30, max_side=2048, probe=None) == []
        assert calls == []

    @pytest.mark.parametrize(("widest", "tallest"), [("3:1", None), (None, "1:3")], ids=["widest-only", "tallest-only"])
    def test_refuses_half_an_aspect_ratio_range(
        self, clip: Path, monkeypatch: pytest.MonkeyPatch, widest: str | None, tallest: str | None
    ) -> None:
        calls = self._probe(monkeypatch, ImageInfo(4000, 1000, None), 5.0)
        with pytest.raises(ValueError, match="only one of widest and tallest"):
            video_errors(str(clip), subject=SUBJECT, widest=widest, tallest=tallest)
        assert calls == []

    def test_uses_the_given_duration_fix(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._probe(monkeypatch, None, 1.0)
        errors = video_errors(str(clip), subject=SUBJECT, min_seconds=3, duration_fix="Pick a longer clip.")
        assert [str(e) for e in errors] == [f"{SUBJECT} is 1.00 seconds long and the minimum is 3. Pick a longer clip."]

    def test_links_the_docs_page(self, clip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._probe(monkeypatch, ImageInfo(100, 100, None), 5.0)
        errors = video_errors(str(clip), subject=SUBJECT, min_side=200, docs_url=DOCS)
        assert errors[0].links
        assert errors[0].links[0].url == DOCS

    def test_skips_a_remote_video(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            input_checks.subprocess, "run", lambda *_a, **_k: pytest.fail("a remote video must not be probed")
        )
        assert (
            video_errors("https://example.com/clip.mp4", subject=SUBJECT, maximum_bytes=1, max_seconds=1, min_side=1)
            == []
        )


class TestCheckFrameRate:
    @pytest.mark.parametrize("fps", [24.0, 23.976, 30.0, 59.94, 60.0])
    def test_allows_a_frame_rate_in_range_including_ntsc(self, fps: float) -> None:
        assert check_frame_rate(fps, subject=SUBJECT, minimum=24, maximum=60) is None

    def test_skips_an_unknown_frame_rate(self) -> None:
        assert check_frame_rate(None, subject=SUBJECT, minimum=24) is None

    def test_rejects_a_low_frame_rate(self) -> None:
        error = check_frame_rate(15.0, subject=SUBJECT, minimum=24, maximum=60, docs_url=DOCS)
        assert str(error) == f"{SUBJECT} is 15 fps and the minimum is 24 fps. Re-export it at a higher frame rate."
        assert error is not None
        assert error.links

    def test_prints_a_very_high_frame_rate_in_full(self) -> None:
        error = check_frame_rate(1000.0, subject=SUBJECT, maximum=60)
        assert str(error).startswith(f"{SUBJECT} is 1000 fps and the maximum is 60 fps.")

    def test_never_prints_a_frame_rate_as_equal_to_the_limit(self) -> None:
        error = check_frame_rate(23.97, subject=SUBJECT, minimum=24, tolerance=0.001)
        assert str(error).startswith(f"{SUBJECT} is 23.97 fps and the minimum is 24 fps.")

    def test_rejects_a_high_frame_rate(self) -> None:
        error = check_frame_rate(120.0, subject=SUBJECT, minimum=24, maximum=60)
        assert str(error) == f"{SUBJECT} is 120 fps and the maximum is 60 fps. Re-export it at a lower frame rate."


class TestCheckMimeType:
    def test_allows_a_listed_type(self) -> None:
        assert check_mime_type("image/png", subject=SUBJECT, allowed=("image/jpeg", "image/png")) is None

    def test_skips_an_unknown_type(self) -> None:
        assert check_mime_type(None, subject=SUBJECT, allowed=("image/png",)) is None

    def test_rejects_an_unlisted_type(self) -> None:
        error = check_mime_type("image/webp", subject=SUBJECT, allowed=("image/jpeg", "image/png"))
        assert str(error) == f"{SUBJECT} is in WEBP format. Convert it to JPEG or PNG."

    @pytest.mark.parametrize(
        ("mime_type", "name"),
        [
            ("image/avif", "AVIF"),
            ("image/x-icon", "ICON"),
            ("image/vnd.adobe.photoshop", "PSD"),
            ("video/mp4", "MP4"),
            ("video/quicktime", "MOV"),
            ("video/x-matroska", "MKV"),
            ("video/x-msvideo", "AVI"),
        ],
        ids=["subtype", "strips-x-prefix", "known-name", "mp4", "mov", "mkv", "avi"],
    )
    def test_names_the_format_the_way_artists_know_it(self, mime_type: str, name: str) -> None:
        error = check_mime_type(mime_type, subject=SUBJECT, allowed=("image/jpeg", "image/png"))
        assert str(error) == f"{SUBJECT} is in {name} format. Convert it to JPEG or PNG."


class TestCheckDuration:
    def test_allows_a_duration_in_range(self) -> None:
        assert check_duration(5.0, subject="The video in 'Video'", minimum=1, maximum=8.7) is None

    def test_skips_an_unknown_duration(self) -> None:
        assert check_duration(None, subject="The video in 'Video'", maximum=1) is None

    def test_rejects_a_long_video(self) -> None:
        error = check_duration(12.345, subject="The video in 'Video'", maximum=8.7)
        assert str(error) == (
            "The video in 'Video' is 12.35 seconds long and the limit is 8.7. Use a Trim Video node to shorten it."
        )

    def test_rejects_a_short_video(self) -> None:
        error = check_duration(0.5, subject="The video in 'Video'", minimum=2)
        assert str(error) == "The video in 'Video' is 0.50 seconds long and the minimum is 2. Use a longer clip."

    def test_reports_a_duration_just_over_the_limit_as_over_it(self) -> None:
        error = check_duration(8.701, subject="The video in 'Video'", maximum=8.7)
        assert str(error).startswith("The video in 'Video' is 8.701 seconds long and the limit is 8.7.")

    def test_reports_a_duration_under_a_non_round_minimum_as_under_it(self) -> None:
        error = check_duration(1.9455, subject="The video in 'Video'", minimum=1.946)
        assert str(error).startswith("The video in 'Video' is 1.9455 seconds long and the minimum is 1.946.")

    def test_reports_a_duration_under_a_long_minimum_as_under_it(self) -> None:
        error = check_duration(2.046665, subject="The video in 'Video'", minimum=2.0466666666)
        assert str(error).startswith("The video in 'Video' is 2.04666 seconds long and the minimum is 2.04667.")

    def test_uses_the_given_fix(self) -> None:
        error = check_duration(20, subject="The video in 'Video'", maximum=10, fix="Pick a shorter clip.")
        assert str(error).endswith("Pick a shorter clip.")

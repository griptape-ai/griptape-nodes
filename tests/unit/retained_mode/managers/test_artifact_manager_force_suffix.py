"""Tests for the ``_force_suffix`` helper used by ``ArtifactManager``'s write API."""

from pathlib import Path

from griptape_nodes.retained_mode.managers.artifact_manager import _force_suffix


class TestForceSuffix:
    def test_no_change_when_already_matching(self) -> None:
        assert _force_suffix("foo.png", "png") == ("foo.png", False)

    def test_change_when_extension_differs(self) -> None:
        assert _force_suffix("foo.png", "jpg") == ("foo.jpg", True)

    def test_jpg_jpeg_treated_as_equivalent(self) -> None:
        assert _force_suffix("foo.jpg", "jpeg") == ("foo.jpg", False)
        assert _force_suffix("foo.jpeg", "jpg") == ("foo.jpeg", False)

    def test_preserves_directory(self) -> None:
        new_filename, changed = _force_suffix("renders/foo.png", "jpg")
        assert changed is True
        assert Path(new_filename) == Path("renders/foo.jpg")

    def test_case_insensitive_match(self) -> None:
        assert _force_suffix("foo.PNG", "png") == ("foo.PNG", False)

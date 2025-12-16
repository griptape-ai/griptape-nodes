from __future__ import annotations

from io import BytesIO
import sys
from pathlib import Path

import pytest
from griptape.artifacts import ImageUrlArtifact
from PIL import Image


_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIB_ROOT = _REPO_ROOT / "libraries" / "griptape_nodes_library"
sys.path.insert(0, str(_LIB_ROOT))


from griptape_nodes_library.image.add_text_to_existing_image import (  # noqa: E402
    AddTextToExistingImage,
)


def _write_test_png(tmp_path: Path, *, size: tuple[int, int] = (200, 200)) -> Path:
    image_path = tmp_path / "input.png"
    Image.new("RGBA", size, (255, 255, 255, 255)).save(image_path, format="PNG")
    return image_path


def _bbox_for_pixels(image: Image.Image, predicate) -> tuple[int, int, int, int] | None:
    pixels = image.convert("RGBA").load()
    if pixels is None:
        return None

    width, height = image.size
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if predicate(r, g, b, a):
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x < 0 or max_y < 0:
        return None

    return (min_x, min_y, max_x, max_y)


@pytest.mark.parametrize("text_vertical_alignment", ["top", "center", "bottom"])
@pytest.mark.parametrize("text_horizontal_alignment", ["left", "center", "right"])
def test_process_produces_output_for_all_alignments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    text_vertical_alignment: str,
    text_horizontal_alignment: str,
) -> None:
    # Stub out static-file upload to keep this a true unit test.
    from griptape_nodes_library.image import add_text_to_existing_image as module  # noqa: E402

    def _fake_save(_image: Image.Image, _filename: str, _format: str = "PNG") -> ImageUrlArtifact:
        return ImageUrlArtifact(value="mock://static/output.png")

    monkeypatch.setattr(module, "save_pil_image_with_named_filename", _fake_save)

    input_path = _write_test_png(tmp_path)

    node = AddTextToExistingImage(name="test-node")
    node.set_parameter_value("input_image", ImageUrlArtifact(value=str(input_path)))
    node.set_parameter_value("text", "Hello\nworld")
    node.set_parameter_value("text_color", "#ff0000ff")
    node.set_parameter_value("text_background", "#00ff00ff")
    node.set_parameter_value("text_vertical_alignment", text_vertical_alignment)
    node.set_parameter_value("text_horizontal_alignment", text_horizontal_alignment)
    node.set_parameter_value("border", 10)
    node.set_parameter_value("font_size", 24)

    node.process()

    output = node.parameter_output_values["output"]
    assert isinstance(output, ImageUrlArtifact)


def test_text_is_centered_within_background_when_center_aligned(tmp_path: Path) -> None:
    input_path = _write_test_png(tmp_path, size=(240, 240))

    node = AddTextToExistingImage(name="test-node")

    png_bytes = node._render_png_bytes(
        image_value=ImageUrlArtifact(value=str(input_path)),
        text="Hello",
        text_color="#ff0000ff",
        text_background="#00ff00ff",
        text_vertical_alignment="center",
        text_horizontal_alignment="center",
        border=10,
        font_size=36,
    )

    rendered = Image.open(BytesIO(png_bytes)).convert("RGBA")

    red_bbox = _bbox_for_pixels(rendered, lambda r, g, b, a: a > 200 and r > 200 and g < 80 and b < 80)
    green_bbox = _bbox_for_pixels(rendered, lambda r, g, b, a: a > 200 and g > 200 and r < 80 and b < 80)

    assert red_bbox is not None, "Expected some rendered red text pixels"
    assert green_bbox is not None, "Expected some rendered green background pixels"

    _, red_top, _, red_bottom = red_bbox
    _, green_top, _, green_bottom = green_bbox

    red_center_y = (red_top + red_bottom) / 2
    green_center_y = (green_top + green_bottom) / 2

    assert abs(red_center_y - green_center_y) <= 2


def test_text_dict_template_expands_keys(tmp_path: Path) -> None:
    input_path = _write_test_png(tmp_path, size=(240, 240))

    node = AddTextToExistingImage(name="test-node")

    png_bytes = node._render_png_bytes(
        image_value=ImageUrlArtifact(value=str(input_path)),
        text="Hello Ian #7",
        text_color="#ff0000ff",
        text_background="#00ff00ff",
        text_vertical_alignment="top",
        text_horizontal_alignment="left",
        border=10,
        font_size=36,
    )

    # If expansion failed completely, we'd likely have no red pixels (empty label) or placeholders would remain.
    rendered = Image.open(BytesIO(png_bytes)).convert("RGBA")
    red_bbox = _bbox_for_pixels(rendered, lambda r, g, b, a: a > 200 and r > 200 and g < 80 and b < 80)
    assert red_bbox is not None


def test_separate_template_values_expands_and_reports_missing_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from griptape_nodes_library.image import add_text_to_existing_image as module  # noqa: E402

    def _fake_save(_image: Image.Image, _filename: str, _format: str = "PNG") -> ImageUrlArtifact:
        return ImageUrlArtifact(value="mock://static/output.png")

    monkeypatch.setattr(module, "save_pil_image_with_named_filename", _fake_save)

    input_path = _write_test_png(tmp_path)

    node = AddTextToExistingImage(name="test-node")
    node.set_parameter_value("input_image", ImageUrlArtifact(value=str(input_path)))
    node.set_parameter_value("text", "Hello {name} #{num}")
    node.set_parameter_value("template_values", {"name": "Ian"})
    node.set_parameter_value("text_color", "#ff0000ff")
    node.set_parameter_value("text_background", "#00ff00ff")
    node.set_parameter_value("text_vertical_alignment", "top")
    node.set_parameter_value("text_horizontal_alignment", "left")
    node.set_parameter_value("border", 10)
    node.set_parameter_value("font_size", 24)

    node.process()

    assert node.parameter_output_values["text"] == "Hello {name} #{num}"
    result_details = node.get_parameter_value("result_details")
    assert isinstance(result_details, str)
    assert "key: num not found in dictionary input" in result_details

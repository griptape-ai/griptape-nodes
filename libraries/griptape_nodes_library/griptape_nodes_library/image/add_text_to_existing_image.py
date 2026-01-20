from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image, ImageDraw, ImageFont

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.color_picker import ColorPicker
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.color_utils import parse_color_to_rgba
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)

TEXT_PREVIEW_LENGTH = 50
TEXT_BACKGROUND_PADDING_PX = 4
TEXT_LINE_SPACING_PX = 4

VERTICAL_ALIGN_TOP = "top"
VERTICAL_ALIGN_CENTER = "center"
VERTICAL_ALIGN_BOTTOM = "bottom"
VERTICAL_ALIGN_OPTIONS = [VERTICAL_ALIGN_TOP, VERTICAL_ALIGN_CENTER, VERTICAL_ALIGN_BOTTOM]

HORIZONTAL_ALIGN_LEFT = "left"
HORIZONTAL_ALIGN_CENTER = "center"
HORIZONTAL_ALIGN_RIGHT = "right"
HORIZONTAL_ALIGN_OPTIONS = [HORIZONTAL_ALIGN_LEFT, HORIZONTAL_ALIGN_CENTER, HORIZONTAL_ALIGN_RIGHT]


@dataclass(frozen=True)
class _RenderSignature:
    source_fingerprint: str
    text: str
    template_values_fingerprint: str
    text_color: str
    text_background: str
    text_vertical_alignment: str
    text_horizontal_alignment: str
    margin: int
    font_size: int


@dataclass(frozen=True)
class _AlignedTextBoxOrigin:
    x: int
    y: int


@dataclass(frozen=True)
class _TextLayoutSettings:
    border: int
    text_vertical_alignment: str
    text_horizontal_alignment: str


@dataclass(frozen=True)
class _TextExpansionResult:
    rendered_text: str
    missing_keys: list[str]


class AddTextToExistingImage(SuccessFailureNode):
    """Node to add text rendered on top of an existing image."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self._cached_render_signature: _RenderSignature | None = None
        self._cached_render_png_bytes: bytes | None = None

        self.add_parameter(
            ParameterImage(
                name="input_image",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=None,
                tooltip="The image to add text to",
                ui_options={"clickable_file_browser": True, "expander": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="text",
                type="str",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Text to render on the image. Use {key} placeholders to insert values from template_values.",
                ui_options={"multiline": True, "placeholder_text": "Enter text to render on image"},
            )
        )

        self.add_parameter(
            Parameter(
                name="template_values",
                input_types=["dict"],
                type="dict",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=None,
                tooltip="Dictionary of values used to replace {key} placeholders in the text parameter",
            )
        )

        self.add_parameter(
            Parameter(
                name="text_color",
                type="str",
                default_value="#ffffffff",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Color of the text (hex format, supports alpha)",
                traits={ColorPicker(format="hexa")},
            )
        )

        self.add_parameter(
            Parameter(
                name="text_background",
                type="str",
                default_value="#000000ff",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Background color behind the text (hex format, supports alpha)",
                traits={ColorPicker(format="hexa")},
            )
        )

        vertical_alignment_param = Parameter(
            name="text_vertical_alignment",
            type="str",
            default_value=VERTICAL_ALIGN_TOP,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            tooltip="Vertical alignment of the text block within the image",
        )
        vertical_alignment_param.add_trait(Options(choices=VERTICAL_ALIGN_OPTIONS))
        self.add_parameter(vertical_alignment_param)

        horizontal_alignment_param = Parameter(
            name="text_horizontal_alignment",
            type="str",
            default_value=HORIZONTAL_ALIGN_LEFT,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            tooltip="Horizontal alignment of the text block within the image",
        )
        horizontal_alignment_param.add_trait(Options(choices=HORIZONTAL_ALIGN_OPTIONS))
        self.add_parameter(horizontal_alignment_param)

        self.add_parameter(
            Parameter(
                name="margin",
                type="int",
                default_value=10,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Margin (in pixels) between the text block and the image edges",
            )
        )

        self.add_parameter(
            Parameter(
                name="font_size",
                type="int",
                default_value=36,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Font size in points",
            )
        )

        self.add_parameter(
            ParameterImage(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The image with rendered text",
                ui_options={"pulse_on_run": True, "expander": True},
            )
        )

        self._create_status_parameters(
            result_details_tooltip="Details about the add-text-to-existing-image operation result",
            result_details_placeholder="Details on the text rendering will be presented here.",
            parameter_group_initially_collapsed=True,
        )

    def _expand_text_template(self, template: str, template_values: Any) -> _TextExpansionResult:
        template_value = template or ""

        values: dict = {}
        if isinstance(template_values, dict):
            values = template_values

        pattern = r"\{(\w+)\}"
        matches = re.findall(pattern, template_value)
        if not matches:
            return _TextExpansionResult(rendered_text=template_value, missing_keys=[])

        missing_keys: list[str] = []
        seen_missing: set[str] = set()

        for key in matches:
            if key in values:
                template_value = template_value.replace(f"{{{key}}}", str(values[key]))
            elif key not in seen_missing:
                missing_keys.append(key)
                seen_missing.add(key)

        return _TextExpansionResult(rendered_text=template_value, missing_keys=missing_keys)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # Re-render and cache image locally when any relevant parameter changes.
        if parameter.name in {
            "input_image",
            "text",
            "template_values",
            "text_color",
            "text_background",
            "text_vertical_alignment",
            "text_horizontal_alignment",
            "margin",
            "font_size",
        }:
            try:
                self._refresh_cached_render_if_possible()
            except Exception as e:
                logger.warning(f"{self.name}: Cached render refresh failed: {e}")
        return super().after_value_set(parameter, value)

    def process(self) -> AsyncResult[None]:
        """Run using AsyncResult pattern for UI running status."""
        self._clear_execution_status()
        self._set_failure_output_values()
        yield lambda: self._process()

    def _process(self) -> None:
        """Synchronous implementation for AsyncResult wrapper."""
        # The async wrapper handles execution status reset and failure defaults.

        input_image = self.get_parameter_value("input_image")
        text_template = self.get_parameter_value("text") or ""
        template_values = self.get_parameter_value("template_values")
        expansion = self._expand_text_template(text_template, template_values)
        rendered_text = expansion.rendered_text
        text_color = self.get_parameter_value("text_color") or "#ffffffff"
        text_background = self.get_parameter_value("text_background") or "#000000ff"
        text_vertical_alignment = self.get_parameter_value("text_vertical_alignment") or VERTICAL_ALIGN_TOP
        text_horizontal_alignment = self.get_parameter_value("text_horizontal_alignment") or HORIZONTAL_ALIGN_LEFT
        margin = self.get_parameter_value("margin")
        font_size = self.get_parameter_value("font_size")

        try:
            self._validate_parameters(
                input_image=input_image,
                text_vertical_alignment=text_vertical_alignment,
                text_horizontal_alignment=text_horizontal_alignment,
                margin=margin,
                font_size=font_size,
            )
        except ValueError as validation_error:
            error_details = f"Parameter validation failed: {validation_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"AddTextToExistingImage '{self.name}': {error_details}")
            self._handle_failure_exception(validation_error)
            return

        try:
            signature = self._build_render_signature(
                image_value=input_image,
                text=rendered_text,
                template_values=template_values,
                text_color=text_color,
                text_background=text_background,
                text_vertical_alignment=text_vertical_alignment,
                text_horizontal_alignment=text_horizontal_alignment,
                margin=margin,
                font_size=font_size,
            )
        except Exception as signature_error:
            error_details = f"Failed to build render signature: {signature_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"AddTextToExistingImage '{self.name}': {error_details}")
            self._handle_failure_exception(signature_error)
            return

        try:
            png_bytes = self._get_cached_or_rendered_png_bytes(signature, input_image)
        except Exception as render_error:
            error_details = f"Failed to render image: {render_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"AddTextToExistingImage '{self.name}': {error_details}")
            self._handle_failure_exception(render_error)
            return

        try:
            output_artifact = self._upload_png_bytes(png_bytes)
        except Exception as upload_error:
            error_details = f"Failed to upload image: {upload_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"AddTextToExistingImage '{self.name}': {error_details}")
            self._handle_failure_exception(upload_error)
            return

        self._set_success_output_values(
            text=text_template,
            text_color=text_color,
            text_background=text_background,
            text_vertical_alignment=text_vertical_alignment,
            text_horizontal_alignment=text_horizontal_alignment,
            margin=margin,
            font_size=font_size,
            output_artifact=output_artifact,
        )

        success_details = self._get_success_message(rendered_text)
        result_lines = [f"SUCCESS: {success_details}"]
        result_lines.extend(
            [f"key: {missing_key} not found in dictionary input" for missing_key in expansion.missing_keys]
        )
        self._set_status_results(was_successful=True, result_details="\n".join(result_lines))
        logger.info(f"AddTextToExistingImage '{self.name}': {success_details}")

    def _validate_parameters(
        self,
        *,
        input_image: Any,
        text_vertical_alignment: str,
        text_horizontal_alignment: str,
        margin: int,
        font_size: int,
    ) -> None:
        if input_image is None:
            msg = "input_image is required"
            raise ValueError(msg)

        if text_vertical_alignment not in VERTICAL_ALIGN_OPTIONS:
            msg = f"text_vertical_alignment must be one of {VERTICAL_ALIGN_OPTIONS}, got: {text_vertical_alignment}"
            raise ValueError(msg)

        if text_horizontal_alignment not in HORIZONTAL_ALIGN_OPTIONS:
            msg = (
                f"text_horizontal_alignment must be one of {HORIZONTAL_ALIGN_OPTIONS}, got: {text_horizontal_alignment}"
            )
            raise ValueError(msg)

        if margin < 0:
            msg = f"margin must be >= 0, got: {margin}"
            raise ValueError(msg)

        if font_size <= 0:
            msg = f"font_size must be a positive integer, got: {font_size}"
            raise ValueError(msg)

    def _refresh_cached_render_if_possible(self) -> None:
        input_image = self.get_parameter_value("input_image")
        if input_image is None:
            self._cached_render_signature = None
            self._cached_render_png_bytes = None
            return

        text_template = self.get_parameter_value("text") or ""
        template_values = self.get_parameter_value("template_values")
        expansion = self._expand_text_template(text_template, template_values)
        text = expansion.rendered_text
        text_color = self.get_parameter_value("text_color") or "#ffffffff"
        text_background = self.get_parameter_value("text_background") or "#000000ff"
        text_vertical_alignment = self.get_parameter_value("text_vertical_alignment") or VERTICAL_ALIGN_TOP
        text_horizontal_alignment = self.get_parameter_value("text_horizontal_alignment") or HORIZONTAL_ALIGN_LEFT
        margin = self.get_parameter_value("margin")
        font_size = self.get_parameter_value("font_size")

        signature = self._build_render_signature(
            image_value=input_image,
            text=text,
            template_values=template_values,
            text_color=text_color,
            text_background=text_background,
            text_vertical_alignment=text_vertical_alignment,
            text_horizontal_alignment=text_horizontal_alignment,
            margin=margin,
            font_size=font_size,
        )

        # Render fresh and cache locally, but do not upload or update output artifact.
        png_bytes = self._render_png_bytes(
            image_value=input_image,
            text=text,
            text_color=text_color,
            text_background=text_background,
            text_vertical_alignment=text_vertical_alignment,
            text_horizontal_alignment=text_horizontal_alignment,
            margin=margin,
            font_size=font_size,
        )
        self._cached_render_signature = signature
        self._cached_render_png_bytes = png_bytes

    def _build_render_signature(  # noqa: PLR0913
        self,
        *,
        image_value: Any,
        text: str,
        template_values: Any,
        text_color: str,
        text_background: str,
        text_vertical_alignment: str,
        text_horizontal_alignment: str,
        margin: int,
        font_size: int,
    ) -> _RenderSignature:
        source_fingerprint = self._fingerprint_image_value(image_value)
        template_values_fingerprint = self._fingerprint_template_values(template_values)
        return _RenderSignature(
            source_fingerprint=source_fingerprint,
            text=text,
            template_values_fingerprint=template_values_fingerprint,
            text_color=text_color,
            text_background=text_background,
            text_vertical_alignment=text_vertical_alignment,
            text_horizontal_alignment=text_horizontal_alignment,
            margin=margin,
            font_size=font_size,
        )

    def _fingerprint_template_values(self, template_values: Any) -> str:
        if template_values is None:
            return "none"
        if not isinstance(template_values, dict):
            return f"type:{type(template_values).__name__}"
        try:
            serialized = json.dumps(template_values, sort_keys=True, default=str)
        except Exception:
            serialized = repr(template_values)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _fingerprint_image_value(self, image_value: Any) -> str:
        if isinstance(image_value, dict):
            image_value = dict_to_image_url_artifact(image_value)

        if isinstance(image_value, ImageUrlArtifact):
            return f"url:{image_value.value}"

        if isinstance(image_value, ImageArtifact):
            image_bytes = self._get_artifact_bytes(image_value)
            return f"bytes:{hashlib.sha256(image_bytes).hexdigest()}"

        msg = f"Unsupported input_image type: {type(image_value).__name__}"
        raise ValueError(msg)

    def _get_artifact_bytes(self, image_artifact: Any) -> bytes:
        if hasattr(image_artifact, "to_bytes"):
            return image_artifact.to_bytes()

        if hasattr(image_artifact, "value") and isinstance(image_artifact.value, bytes):
            return image_artifact.value

        msg = f"Unsupported image artifact value type: {type(getattr(image_artifact, 'value', None)).__name__}"
        raise ValueError(msg)

    def _get_cached_or_rendered_png_bytes(self, signature: _RenderSignature, image_value: Any) -> bytes:
        if self._cached_render_signature == signature and self._cached_render_png_bytes is not None:
            return self._cached_render_png_bytes

        # Cache is missing or stale, render fresh.
        text = signature.text
        text_color = signature.text_color
        text_background = signature.text_background
        text_vertical_alignment = signature.text_vertical_alignment
        text_horizontal_alignment = signature.text_horizontal_alignment
        margin = signature.margin
        font_size = signature.font_size

        png_bytes = self._render_png_bytes(
            image_value=image_value,
            text=text,
            text_color=text_color,
            text_background=text_background,
            text_vertical_alignment=text_vertical_alignment,
            text_horizontal_alignment=text_horizontal_alignment,
            margin=margin,
            font_size=font_size,
        )
        self._cached_render_signature = signature
        self._cached_render_png_bytes = png_bytes
        return png_bytes

    def _render_png_bytes(  # noqa: PLR0913
        self,
        *,
        image_value: Any,
        text: str,
        text_color: str,
        text_background: str,
        text_vertical_alignment: str,
        text_horizontal_alignment: str,
        margin: int,
        font_size: int,
    ) -> bytes:
        try:
            text_rgba = parse_color_to_rgba(text_color)
            bg_rgba = parse_color_to_rgba(text_background)
        except Exception as color_error:
            msg = f"Color parsing failed: {color_error}"
            raise RuntimeError(msg) from color_error

        pil_image = self._load_pil_image(image_value)
        pil_image = pil_image.convert("RGBA")

        # If there's no text, still return a valid PNG of the original image.
        if not text.strip():
            return self._pil_to_png_bytes(pil_image)

        # Draw text/background onto a transparent overlay and alpha-composite it onto
        # the original image. This ensures semi-transparent colors blend correctly.
        overlay = Image.new("RGBA", pil_image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")

        try:
            font = ImageFont.load_default(size=font_size)
        except Exception as font_error:
            msg = f"Failed to load font: {font_error}"
            raise RuntimeError(msg) from font_error

        text_align_for_multiline = text_horizontal_alignment

        bbox_left_f, bbox_top_f, bbox_right_f, bbox_bottom_f = self._get_text_bbox(
            draw=draw, text=text, font=font, align=text_align_for_multiline
        )
        bbox_left = int(bbox_left_f)
        bbox_top = int(bbox_top_f)
        text_width = int(bbox_right_f - bbox_left_f)
        text_height = int(bbox_bottom_f - bbox_top_f)

        # x/y here represent the desired top-left of the rendered text bounds (bbox),
        # not the draw origin. PIL fonts can have negative bbox_top; we compensate below.
        layout_settings = _TextLayoutSettings(
            border=margin,
            text_vertical_alignment=text_vertical_alignment,
            text_horizontal_alignment=text_horizontal_alignment,
        )
        origin = self._compute_aligned_text_bbox_origin(
            image_width=pil_image.width,
            image_height=pil_image.height,
            text_width=text_width,
            text_height=text_height,
            layout_settings=layout_settings,
        )
        x = origin.x
        y = origin.y

        draw_x = x - bbox_left
        draw_y = y - bbox_top

        bg_left = max(0, x - TEXT_BACKGROUND_PADDING_PX)
        bg_top = max(0, y - TEXT_BACKGROUND_PADDING_PX)
        bg_right = min(pil_image.width, x + text_width + TEXT_BACKGROUND_PADDING_PX)
        bg_bottom = min(pil_image.height, y + text_height + TEXT_BACKGROUND_PADDING_PX)

        try:
            draw.rectangle([bg_left, bg_top, bg_right, bg_bottom], fill=bg_rgba)
            draw.multiline_text(
                (draw_x, draw_y),
                text,
                fill=text_rgba,
                font=font,
                spacing=TEXT_LINE_SPACING_PX,
                align=text_align_for_multiline,
            )
        except Exception as draw_error:
            msg = f"Failed to draw text: {draw_error}"
            raise RuntimeError(msg) from draw_error

        pil_image = Image.alpha_composite(pil_image, overlay)

        return self._pil_to_png_bytes(pil_image)

    def _pil_to_png_bytes(self, pil_image: Image.Image) -> bytes:
        img_bytes = BytesIO()
        pil_image.save(img_bytes, format="PNG")
        return img_bytes.getvalue()

    def _load_pil_image(self, image_value: Any) -> Image.Image:
        if isinstance(image_value, dict):
            image_value = dict_to_image_url_artifact(image_value)

        if isinstance(image_value, ImageUrlArtifact):
            return load_pil_from_url(image_value.value)

        if isinstance(image_value, ImageArtifact):
            image_bytes = self._get_artifact_bytes(image_value)
            return Image.open(BytesIO(image_bytes))

        msg = f"Unsupported input_image type: {type(image_value).__name__}"
        raise ValueError(msg)

    def _upload_png_bytes(self, png_bytes: bytes) -> ImageUrlArtifact:
        pil_image = Image.open(BytesIO(png_bytes))

        filename = generate_filename(
            node_name=self.name,
            suffix="_text_overlay",
            extension="png",
        )
        return save_pil_image_with_named_filename(pil_image, filename, "PNG")

    def _get_success_message(self, text: str) -> str:
        text_preview = text[:TEXT_PREVIEW_LENGTH]
        if len(text) > TEXT_PREVIEW_LENGTH:
            text_preview += "..."
        return f"Successfully rendered text onto existing image: '{text_preview}'"

    def _set_success_output_values(  # noqa: PLR0913
        self,
        *,
        text: str,
        text_color: str,
        text_background: str,
        text_vertical_alignment: str,
        text_horizontal_alignment: str,
        margin: int,
        font_size: int,
        output_artifact: ImageUrlArtifact,
    ) -> None:
        self.parameter_output_values["text"] = text
        self.parameter_output_values["text_color"] = text_color
        self.parameter_output_values["text_background"] = text_background
        self.parameter_output_values["text_vertical_alignment"] = text_vertical_alignment
        self.parameter_output_values["text_horizontal_alignment"] = text_horizontal_alignment
        self.parameter_output_values["margin"] = margin
        self.parameter_output_values["font_size"] = font_size
        self.parameter_output_values["output"] = output_artifact

    def _set_failure_output_values(self) -> None:
        self.parameter_output_values["text"] = ""
        self.parameter_output_values["text_color"] = ""
        self.parameter_output_values["text_background"] = ""
        self.parameter_output_values["text_vertical_alignment"] = VERTICAL_ALIGN_TOP
        self.parameter_output_values["text_horizontal_alignment"] = HORIZONTAL_ALIGN_LEFT
        self.parameter_output_values["margin"] = 0
        self.parameter_output_values["font_size"] = 0
        self.parameter_output_values["output"] = None

    def _get_text_bbox(
        self,
        *,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: Any,
        align: str,
    ) -> tuple[float, float, float, float]:
        return draw.multiline_textbbox(
            (0, 0),
            text,
            font=font,
            spacing=TEXT_LINE_SPACING_PX,
            align=align,
        )

    def _compute_aligned_text_bbox_origin(
        self,
        *,
        image_width: int,
        image_height: int,
        text_width: int,
        text_height: int,
        layout_settings: _TextLayoutSettings,
    ) -> _AlignedTextBoxOrigin:
        border = layout_settings.border
        text_vertical_alignment = layout_settings.text_vertical_alignment
        text_horizontal_alignment = layout_settings.text_horizontal_alignment
        inset_left = border
        inset_top = border
        inset_right = max(inset_left, image_width - border)
        inset_bottom = max(inset_top, image_height - border)

        inset_width = max(0, inset_right - inset_left)
        inset_height = max(0, inset_bottom - inset_top)

        x = inset_left
        if inset_width > text_width:
            if text_horizontal_alignment == HORIZONTAL_ALIGN_CENTER:
                x = inset_left + (inset_width - text_width) // 2
            elif text_horizontal_alignment == HORIZONTAL_ALIGN_RIGHT:
                x = inset_right - text_width

        y = inset_top
        if inset_height > text_height:
            if text_vertical_alignment == VERTICAL_ALIGN_CENTER:
                y = inset_top + (inset_height - text_height) // 2
            elif text_vertical_alignment == VERTICAL_ALIGN_BOTTOM:
                y = inset_bottom - text_height

        # Clamp within image bounds.
        x = max(0, min(x, max(0, image_width - text_width)))
        y = max(0, min(y, max(0, image_height - text_height)))

        return _AlignedTextBoxOrigin(x=x, y=y)

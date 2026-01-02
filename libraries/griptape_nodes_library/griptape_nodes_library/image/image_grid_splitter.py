from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import numpy as np
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image, ImageDraw, ImageFilter

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AddParameterToNodeResultSuccess,
    RemoveParameterFromNodeRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes.utils import async_utils
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_to_static_file,
)


@dataclass
class _EdgeBounds:
    top: int
    bottom: int
    left: int
    right: int


@dataclass(frozen=True)
class _EdgeTrimSettings:
    threshold: float
    max_trim: int


@dataclass(frozen=True)
class _GapAxisInfo:
    std: np.ndarray
    mean: np.ndarray
    bounds: list[int]
    length: int
    is_vertical: bool


class ImageGridSplitter(DataNode):
    """Split a regular image grid into individual images.

    - Manual mode: user supplies rows/cols.
    - Auto mode: attempts to infer rows/cols for a regular grid even without visible separators.
    - Preview: dotted yellow grid lines overlaid on the input image.
    - Outputs:
      * images: list of ImageUrlArtifact (row-major order)
      * r{row}c{col}: one ImageUrlArtifact output per cell (created on run)
    """

    MIN_GRID = 1
    MAX_GRID = 12

    _DEFAULT_DASH_LEN = 10
    _DEFAULT_GAP_LEN = 6

    _DETECTION_BAND_PX = 2
    _DETECTION_MIN_ABS_SCORE = 1.0
    _DETECTION_STD_PENALTY = 0.15
    _DETECTION_SCORE_RATIO_THRESHOLD = 1.12

    _CELL_PARAM_RE = re.compile(r"^r(\d+)c(\d+)$")

    _GAP_STD_THRESHOLD = 8.0
    _GAP_SEARCH_WINDOW_PX = 12
    _GAP_PADDING_PX = 3
    _GAP_EXPAND_STD_MAX = 25.0
    _GAP_COLOR_DISTANCE_THRESHOLD = 55.0
    _RGB_CHANNELS = 3
    _EDGE_STRIP_STD_THRESHOLD = 10.0
    _EDGE_STRIP_MAX_PX = 12
    _EDGE_STRIP_COLOR_DISTANCE_THRESHOLD = 60.0
    _EDGE_STRIP_COLOR_COVERAGE_MIN = 0.15
    _GAP_COLOR_DEDUP_L2_THRESHOLD = 5.0
    _CELL_INSET_PX_ON_GAPS = 2

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.category = "image"
        self.description = "Split a grid image into individual images (auto or manual grid detection)."

        self._grid_detection_mode = Options(choices=["auto", "manual"])

        # Auto detections group (hidden in manual mode)
        self._detections_group = ParameterGroup(
            name="detections_auto",
            ui_options={"display_name": "Detections (auto)", "collapsed": True},
            collapsed=True,
        )
        self.add_node_element(self._detections_group)

        # Captured per-split so we can strip dotted/aliased divider pixels at cell edges.
        self._last_gap_strip_colors: list[np.ndarray] = []

        self.add_parameter(
            Parameter(
                name="input_image",
                tooltip="Grid input image to split.",
                type="ImageUrlArtifact",
                input_types=["ImageArtifact", "ImageUrlArtifact", "dict", "str"],
                default_value=None,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Image", "hide_property": True, "expander": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="grid_detection_mode",
                tooltip="Auto attempts to infer rows/cols. Manual uses the configured row/col sliders.",
                type=ParameterTypeBuiltin.STR.value,
                default_value="auto",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={self._grid_detection_mode},
                ui_options={"display_name": "Grid Detection"},
            )
        )

        rows_param = Parameter(
            name="rows",
            tooltip=f"Manual grid rows ({self.MIN_GRID}-{self.MAX_GRID}).",
            type=ParameterTypeBuiltin.INT.value,
            default_value=2,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": "Rows", "hide": True, "step": 1},
        )
        rows_param.add_child(Slider(min_val=self.MIN_GRID, max_val=self.MAX_GRID))
        self.add_parameter(rows_param)

        cols_param = Parameter(
            name="cols",
            tooltip=f"Manual grid columns ({self.MIN_GRID}-{self.MAX_GRID}).",
            type=ParameterTypeBuiltin.INT.value,
            default_value=2,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": "Columns", "hide": True, "step": 1},
        )
        cols_param.add_child(Slider(min_val=self.MIN_GRID, max_val=self.MAX_GRID))
        self.add_parameter(cols_param)

        self.add_parameter(
            Parameter(
                name="preview",
                tooltip="Preview of detected/manual grid (dotted yellow lines).",
                type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Preview", "expander": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="images",
                tooltip="List of split images in row-major order.",
                type="list",
                output_type="list",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Images"},
            )
        )

        self.add_parameter(
            Parameter(
                name="detected_rows",
                tooltip="Rows used for preview and splitting.",
                type=ParameterTypeBuiltin.INT.value,
                allowed_modes={ParameterMode.OUTPUT},
                parent_element_name=self._detections_group.name,
                ui_options={"display_name": "Detected Rows"},
            )
        )
        self.add_parameter(
            Parameter(
                name="detected_cols",
                tooltip="Columns used for preview and splitting.",
                type=ParameterTypeBuiltin.INT.value,
                allowed_modes={ParameterMode.OUTPUT},
                parent_element_name=self._detections_group.name,
                ui_options={"display_name": "Detected Columns"},
            )
        )
        self.add_parameter(
            Parameter(
                name="detected_count",
                tooltip="Detected cell count (rows * cols).",
                type=ParameterTypeBuiltin.INT.value,
                allowed_modes={ParameterMode.OUTPUT},
                parent_element_name=self._detections_group.name,
                ui_options={"display_name": "Detected Count"},
            )
        )

        # Grid cell outputs group (created on run). We move this group to the bottom for readability.
        self._grid_cells_group = ParameterGroup(
            name="grid_cells",
            ui_options={"display_name": "Grid Cells", "collapsed": True},
            collapsed=True,
        )
        self.add_node_element(self._grid_cells_group)
        # Order groups: place detections directly below preview, and keep grid cells at the bottom.
        preview_index = self.get_element_index("preview")
        self.move_element_to_position(self._detections_group.name, preview_index + 1)
        self.move_element_to_position(self._grid_cells_group.name, "last")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "grid_detection_mode":
            if value == "manual":
                self.show_parameter_by_name("rows")
                self.show_parameter_by_name("cols")
                self._set_group_visible(self._detections_group.name, visible=False)
            else:
                self.hide_parameter_by_name("rows")
                self.hide_parameter_by_name("cols")
                self._set_group_visible(self._detections_group.name, visible=True)

        if parameter.name in ["input_image", "grid_detection_mode", "rows", "cols"]:
            self._refresh_preview()

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Synchronous fallback: run the same logic without offloading work.
        self._process_sync()

    async def aprocess(self) -> None:
        """Async implementation.

        Best practice: the engine executes nodes via `await node.aprocess()`.
        We keep retained-mode / parameter lifecycle operations on the main thread,
        and offload heavy image work to a worker thread.
        """
        self.parameter_output_values["images"] = []
        self.parameter_output_values["preview"] = None

        pil_image = await async_utils.to_thread(self._load_input_as_pil)
        if pil_image is None:
            return

        rows, cols = self._get_effective_grid(pil_image)
        self._publish_detected(rows, cols)

        preview, cell_images = await async_utils.to_thread(self._compute_preview_and_cells, pil_image, rows, cols)

        # Save and publish preview on the main thread (StaticFilesManager interaction).
        preview_artifact = save_pil_image_to_static_file(preview, image_format="JPEG")
        self.parameter_output_values["preview"] = preview_artifact

        # Ensure the per-cell output parameters exist for this run.
        self._ensure_cell_output_parameters(rows, cols)

        outputs: list[ImageUrlArtifact] = []
        for r_idx in range(rows):
            for c_idx in range(cols):
                cell = cell_images[r_idx][c_idx]
                cell_artifact = save_pil_image_to_static_file(cell, image_format="JPEG")
                outputs.append(cell_artifact)

                cell_name = f"r{r_idx + 1}c{c_idx + 1}"
                self.parameter_output_values[cell_name] = cell_artifact

        self.parameter_output_values["images"] = outputs

    def _process_sync(self) -> None:
        self.parameter_output_values["images"] = []
        self.parameter_output_values["preview"] = None

        pil_image = self._load_input_as_pil()
        if pil_image is None:
            return

        rows, cols = self._get_effective_grid(pil_image)
        self._publish_detected(rows, cols)

        preview, cell_images = self._compute_preview_and_cells(pil_image, rows, cols)
        preview_artifact = save_pil_image_to_static_file(preview, image_format="JPEG")
        self.parameter_output_values["preview"] = preview_artifact

        self._ensure_cell_output_parameters(rows, cols)

        outputs: list[ImageUrlArtifact] = []
        for r_idx in range(rows):
            for c_idx in range(cols):
                cell = cell_images[r_idx][c_idx]
                cell_artifact = save_pil_image_to_static_file(cell, image_format="JPEG")
                outputs.append(cell_artifact)

                cell_name = f"r{r_idx + 1}c{c_idx + 1}"
                self.parameter_output_values[cell_name] = cell_artifact

        self.parameter_output_values["images"] = outputs

    def _compute_preview_and_cells(
        self, pil_image: Image.Image, rows: int, cols: int
    ) -> tuple[Image.Image, list[list[Image.Image]]]:
        # Always update preview on run (even if it was already up to date).
        preview = self._draw_preview(pil_image, rows, cols)
        cell_images = self._split_grid(pil_image, rows, cols)
        return preview, cell_images

    # -------------------------
    # Input + preview helpers
    # -------------------------

    def _load_input_as_pil(self) -> Image.Image | None:
        value = self.get_parameter_value("input_image")
        if value is None:
            return None

        if isinstance(value, dict):
            value = dict_to_image_url_artifact(value)

        if isinstance(value, ImageUrlArtifact):
            img = load_pil_from_url(value.value)
            return self._ensure_rgb(img)

        if isinstance(value, ImageArtifact):
            img = Image.open(BytesIO(value.to_bytes()))
            return self._ensure_rgb(img)

        if isinstance(value, str):
            img = load_pil_from_url(value)
            return self._ensure_rgb(img)

        msg = f"Unsupported input_image type: {type(value).__name__}"
        raise ValueError(msg)

    def _refresh_preview(self) -> None:
        pil_image = self._load_input_as_pil()
        if pil_image is None:
            self.parameter_output_values["preview"] = None
            self.parameter_output_values["detected_rows"] = None
            self.parameter_output_values["detected_cols"] = None
            self.parameter_output_values["detected_count"] = None
            return

        rows, cols = self._get_effective_grid(pil_image)
        self._publish_detected(rows, cols)

        preview = self._draw_preview(pil_image, rows, cols)
        preview_artifact = save_pil_image_to_static_file(preview, image_format="JPEG")

        self.parameter_output_values["preview"] = preview_artifact
        self.publish_update_to_parameter("preview", preview_artifact)

    def _publish_detected(self, rows: int, cols: int) -> None:
        count = rows * cols
        self.parameter_output_values["detected_rows"] = rows
        self.parameter_output_values["detected_cols"] = cols
        self.parameter_output_values["detected_count"] = count

        self.publish_update_to_parameter("detected_rows", rows)
        self.publish_update_to_parameter("detected_cols", cols)
        self.publish_update_to_parameter("detected_count", count)

    def _get_effective_grid(self, pil_image: Image.Image) -> tuple[int, int]:
        mode = self.get_parameter_value("grid_detection_mode") or "auto"
        if mode == "manual":
            rows = self._clamp_grid_int(self.get_parameter_value("rows"), default=2)
            cols = self._clamp_grid_int(self.get_parameter_value("cols"), default=2)
            return rows, cols

        rows, cols = self._detect_grid_auto(pil_image)
        return rows, cols

    def _clamp_grid_int(self, value: Any, *, default: int) -> int:
        try:
            ivalue = int(value)
        except Exception:
            ivalue = default

        if ivalue < self.MIN_GRID:
            return self.MIN_GRID
        if ivalue > self.MAX_GRID:
            return self.MAX_GRID
        return ivalue

    # -------------------------
    # Auto detection (regular grid)
    # -------------------------

    def _detect_grid_auto(self, pil_image: Image.Image) -> tuple[int, int]:
        gray = pil_image.convert("L")
        gray = self._downscale_for_detection(gray, max_dim=768)

        # Edges are usually more informative than raw luminance for boundary scoring.
        edges = gray.filter(ImageFilter.FIND_EDGES)
        arr = np.asarray(edges, dtype=np.float32)

        grad_x = np.abs(arr[:, 1:] - arr[:, :-1])
        grad_y = np.abs(arr[1:, :] - arr[:-1, :])

        cols = self._pick_axis_count(grad_x, axis_length=arr.shape[1], axis="x")
        rows = self._pick_axis_count(grad_y, axis_length=arr.shape[0], axis="y")

        return rows, cols

    def _downscale_for_detection(self, pil_image: Image.Image, *, max_dim: int) -> Image.Image:
        w, h = pil_image.size
        if w <= 0 or h <= 0:
            return pil_image
        if max(w, h) <= max_dim:
            return pil_image

        scale = max_dim / max(w, h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        return pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    def _pick_axis_count(self, grad: np.ndarray, *, axis_length: int, axis: str) -> int:
        """Pick the most likely grid count along one axis.

        This assumes a regular grid. We score candidates (1..12) based on the mean edge strength
        near evenly spaced boundaries, with a small penalty for inconsistent boundary strengths.
        """
        length = axis_length
        band = self._DETECTION_BAND_PX

        if axis == "x":
            limit = int(grad.shape[1])

            def sample(lo: int, hi: int) -> np.ndarray:
                return grad[:, lo:hi]

        else:
            limit = int(grad.shape[0])

            def sample(lo: int, hi: int) -> np.ndarray:
                return grad[lo:hi, :]

        best_n = 1
        best_score = 0.0
        second_score = 0.0

        for n in range(self.MIN_GRID, self.MAX_GRID + 1):
            score = self._score_axis_candidate(n, length=length, limit=limit, band=band, sample=sample)
            if score > best_score:
                second_score = best_score
                best_score = score
                best_n = n
                continue
            second_score = max(second_score, score)

        if best_n == 1:
            return 1

        if best_score < self._DETECTION_MIN_ABS_SCORE:
            return 1

        if second_score > 0 and (best_score / second_score) < self._DETECTION_SCORE_RATIO_THRESHOLD:
            return 1

        return best_n

    def _score_axis_candidate(
        self,
        n: int,
        *,
        length: int,
        limit: int,
        band: int,
        sample: Callable[[int, int], np.ndarray],
    ) -> float:
        if n <= 1:
            return 0.0

        boundary_scores: list[float] = []
        for k in range(1, n):
            pos = round(k * length / n)
            if pos <= 0 or pos >= length:
                continue

            idx = pos - 1
            lo = max(0, idx - band)
            hi = min(limit, idx + band + 1)
            if hi <= lo:
                continue

            boundary_scores.append(float(np.mean(sample(lo, hi))))

        if not boundary_scores:
            return 0.0

        mean_score = float(np.mean(boundary_scores))
        std_score = float(np.std(boundary_scores))
        return mean_score - (self._DETECTION_STD_PENALTY * std_score)

    # -------------------------
    # Preview drawing + splitting
    # -------------------------

    def _draw_preview(self, pil_image: Image.Image, rows: int, cols: int) -> Image.Image:
        img = self._ensure_rgb(pil_image).copy()
        draw = ImageDraw.Draw(img)

        w, h = img.size
        color = (255, 255, 0)
        width = 2

        # Vertical boundaries
        for c in range(1, cols):
            x = round(c * w / cols)
            self._draw_dotted_line(draw, (x, 0), (x, h - 1), color=color, width=width)

        # Horizontal boundaries
        for r in range(1, rows):
            y = round(r * h / rows)
            self._draw_dotted_line(draw, (0, y), (w - 1, y), color=color, width=width)

        return img

    def _draw_dotted_line(  # noqa: PLR0913
        self,
        draw: ImageDraw.ImageDraw,
        start: tuple[int, int],
        end: tuple[int, int],
        *,
        color: tuple[int, int, int],
        width: int,
        dash_len: int = _DEFAULT_DASH_LEN,
        gap_len: int = _DEFAULT_GAP_LEN,
    ) -> None:
        x0, y0 = start
        x1, y1 = end

        if x0 == x1:
            # vertical
            y = min(y0, y1)
            y_end = max(y0, y1)
            while y < y_end:
                seg_end = min(y + dash_len, y_end)
                draw.line([(x0, y), (x1, seg_end)], fill=color, width=width)
                y = seg_end + gap_len
            return

        if y0 == y1:
            # horizontal
            x = min(x0, x1)
            x_end = max(x0, x1)
            while x < x_end:
                seg_end = min(x + dash_len, x_end)
                draw.line([(x, y0), (seg_end, y1)], fill=color, width=width)
                x = seg_end + gap_len
            return

        # Fallback: solid line for non-axis-aligned (shouldn't happen here).
        draw.line([start, end], fill=color, width=width)

    def _split_grid(self, pil_image: Image.Image, rows: int, cols: int) -> list[list[Image.Image]]:
        img = self._ensure_rgb(pil_image)
        w, h = img.size

        x_bounds = [round(i * w / cols) for i in range(cols + 1)]
        y_bounds = [round(i * h / rows) for i in range(rows + 1)]
        x_bounds[-1] = w
        y_bounds[-1] = h

        x_starts, x_ends, y_starts, y_ends, gap_colors = self._compute_gap_trimmed_bounds(img, x_bounds, y_bounds)
        self._last_gap_strip_colors = gap_colors

        grid: list[list[Image.Image]] = []
        for r in range(rows):
            row_imgs: list[Image.Image] = []
            y0 = y_starts[r]
            y1 = y_ends[r]
            if y1 <= y0:
                y1 = min(h, y0 + 1)
            for c in range(cols):
                x0 = x_starts[c]
                x1 = x_ends[c]
                if x1 <= x0:
                    x1 = min(w, x0 + 1)
                cell = img.crop((x0, y0, x1, y1))
                cell = self._trim_uniform_edge_strips(cell)
                row_imgs.append(cell)
            grid.append(row_imgs)
        return grid

    def _compute_gap_trimmed_bounds(
        self,
        img: Image.Image,
        x_bounds: list[int],
        y_bounds: list[int],
    ) -> tuple[list[int], list[int], list[int], list[int], list[np.ndarray]]:
        """Compute per-cell crop bounds with separator gaps removed.

        This looks for low-variance vertical/horizontal stripes near each internal boundary. When found,
        the stripe is removed from both adjacent cells so output images do not include visible borders.
        """
        arr = np.asarray(img, dtype=np.float32)
        if arr.ndim != self._RGB_CHANNELS or arr.shape[2] < self._RGB_CHANNELS:
            cols = len(x_bounds) - 1
            rows = len(y_bounds) - 1
            return (
                [x_bounds[i] for i in range(cols)],
                [x_bounds[i + 1] for i in range(cols)],
                [y_bounds[i] for i in range(rows)],
                [y_bounds[i + 1] for i in range(rows)],
                [],
            )

        col_std = arr.std(axis=0).mean(axis=1)  # shape: (w,)
        row_std = arr.std(axis=1).mean(axis=1)  # shape: (h,)
        col_mean = arr.mean(axis=0)[:, :3]  # shape: (w, 3)
        row_mean = arr.mean(axis=1)[:, :3]  # shape: (h, 3)

        x_starts, x_ends = self._apply_gap_strips_to_axis(col_std, means=col_mean, bounds=x_bounds)
        y_starts, y_ends = self._apply_gap_strips_to_axis(row_std, means=row_mean, bounds=y_bounds)
        x_axis = _GapAxisInfo(std=col_std, mean=col_mean, bounds=x_bounds, length=int(arr.shape[1]), is_vertical=True)
        y_axis = _GapAxisInfo(std=row_std, mean=row_mean, bounds=y_bounds, length=int(arr.shape[0]), is_vertical=False)
        gap_colors = self._collect_gap_strip_colors(arr, x_axis=x_axis, y_axis=y_axis)
        return x_starts, x_ends, y_starts, y_ends, gap_colors

    def _collect_gap_strip_colors(
        self,
        arr: np.ndarray,
        *,
        x_axis: _GapAxisInfo,
        y_axis: _GapAxisInfo,
    ) -> list[np.ndarray]:
        """Collect representative divider colors used for edge stripping.

        Some dividers are dotted/aliased and won't be removed by uniform edge stripping alone.
        We sample divider bands (when detected) and use their mean colors as a reference.
        """
        colors: list[np.ndarray] = []
        self._collect_internal_gap_colors(colors, arr=arr, axis=x_axis)
        self._collect_internal_gap_colors(colors, arr=arr, axis=y_axis)
        self._collect_outer_edge_gap_colors(colors, arr=arr, axis=x_axis)
        self._collect_outer_edge_gap_colors(colors, arr=arr, axis=y_axis)
        return colors

    def _add_gap_color(self, colors: list[np.ndarray], color: np.ndarray) -> None:
        # De-duplicate by rounding to reduce noise.
        rounded = np.round(color, 0)
        for existing in colors:
            if np.linalg.norm(np.round(existing, 0) - rounded) <= self._GAP_COLOR_DEDUP_L2_THRESHOLD:
                return
        colors.append(color)

    def _collect_internal_gap_colors(self, colors: list[np.ndarray], *, arr: np.ndarray, axis: _GapAxisInfo) -> None:
        for boundary in axis.bounds[1:-1]:
            gap = self._find_gap_segment(axis.std, means=axis.mean, boundary=boundary)
            if gap is None:
                continue
            gap_start, gap_end = gap
            band = self._extract_gap_band(arr, axis=axis, start=gap_start, end=gap_end)
            self._add_gap_color(colors, band.mean(axis=0))

    def _collect_outer_edge_gap_colors(self, colors: list[np.ndarray], *, arr: np.ndarray, axis: _GapAxisInfo) -> None:
        for boundary in (0, axis.length - 1):
            gap = self._find_gap_segment(axis.std, means=axis.mean, boundary=boundary)
            if gap is None:
                continue
            gap_start, gap_end = gap
            if gap_start > self._GAP_SEARCH_WINDOW_PX and gap_end < (axis.length - 1 - self._GAP_SEARCH_WINDOW_PX):
                continue
            band = self._extract_gap_band(arr, axis=axis, start=gap_start, end=gap_end)
            self._add_gap_color(colors, band.mean(axis=0))

    def _extract_gap_band(self, arr: np.ndarray, *, axis: _GapAxisInfo, start: int, end: int) -> np.ndarray:
        if axis.is_vertical:
            return arr[:, start : end + 1, :3].reshape(-1, 3)
        return arr[start : end + 1, :, :3].reshape(-1, 3)

    def _apply_gap_strips_to_axis(
        self, stds: np.ndarray, *, means: np.ndarray, bounds: list[int]
    ) -> tuple[list[int], list[int]]:
        n = len(bounds) - 1
        starts = [bounds[i] for i in range(n)]
        ends = [bounds[i + 1] for i in range(n)]
        pad = self._GAP_PADDING_PX

        for i in range(1, n):
            boundary = bounds[i]
            gap = self._find_gap_segment(stds, means=means, boundary=boundary)
            if gap is None:
                continue

            gap_start, gap_end = gap
            ends[i - 1] = min(ends[i - 1], gap_start - pad)
            starts[i] = max(starts[i], gap_end + 1 + pad)

        limit = int(stds.shape[0])
        for i in range(n):
            starts[i] = max(0, min(limit, starts[i]))
            ends[i] = max(0, min(limit, ends[i]))
            if ends[i] <= starts[i]:
                ends[i] = min(limit, starts[i] + 1)

        return starts, ends

    def _find_gap_segment(self, stds: np.ndarray, *, means: np.ndarray, boundary: int) -> tuple[int, int] | None:
        window = self._GAP_SEARCH_WINDOW_PX
        threshold = self._GAP_STD_THRESHOLD

        limit = int(stds.shape[0])
        lo = max(0, boundary - window)
        hi = min(limit, boundary + window + 1)
        if hi - lo <= 1:
            return None

        mask = stds[lo:hi] <= threshold
        if not bool(np.any(mask)):
            return None

        segments = self._collect_true_segments(mask, offset=lo)
        core = self._choose_closest_segment(segments, stds=stds, boundary=boundary)
        if core is None:
            return None
        return self._expand_gap_segment(core, stds=stds, means=means, lo=lo, hi=hi)

    def _expand_gap_segment(
        self,
        core: tuple[int, int],
        *,
        stds: np.ndarray,
        means: np.ndarray,
        lo: int,
        hi: int,
    ) -> tuple[int, int]:
        core_start, core_end = core
        core_color = means[core_start : core_end + 1].mean(axis=0)

        max_std = self._GAP_EXPAND_STD_MAX
        max_dist = self._GAP_COLOR_DISTANCE_THRESHOLD

        start = core_start
        x = core_start - 1
        while x >= lo:
            if float(stds[x]) > max_std:
                break
            dist = float(np.linalg.norm(means[x] - core_color))
            if dist > max_dist:
                break
            start = x
            x -= 1

        end = core_end
        x = core_end + 1
        while x < hi:
            if float(stds[x]) > max_std:
                break
            dist = float(np.linalg.norm(means[x] - core_color))
            if dist > max_dist:
                break
            end = x
            x += 1

        return start, end

    def _collect_true_segments(self, mask: np.ndarray, *, offset: int) -> list[tuple[int, int]]:
        segments: list[tuple[int, int]] = []
        start: int | None = None
        values = mask.tolist()
        for idx, is_true in enumerate(values):
            x = offset + idx
            if is_true and start is None:
                start = x
                continue
            if (not is_true) and start is not None:
                segments.append((start, x - 1))
                start = None
        if start is not None:
            segments.append((start, offset + len(values) - 1))
        return segments

    def _segment_distance_to_boundary(self, seg: tuple[int, int], boundary: int) -> int:
        seg_start, seg_end = seg
        if seg_start <= boundary <= seg_end:
            return 0
        if boundary < seg_start:
            return seg_start - boundary
        return boundary - seg_end

    def _choose_closest_segment(
        self,
        segments: list[tuple[int, int]],
        *,
        stds: np.ndarray,
        boundary: int,
    ) -> tuple[int, int] | None:
        if not segments:
            return None

        best_seg: tuple[int, int] | None = None
        best_dist: int | None = None
        best_mean: float | None = None

        for seg in segments:
            dist = self._segment_distance_to_boundary(seg, boundary)
            seg_start, seg_end = seg
            seg_mean = float(np.mean(stds[seg_start : seg_end + 1]))
            if best_seg is None or best_dist is None or best_mean is None:
                best_seg = seg
                best_dist = dist
                best_mean = seg_mean
                continue

            if dist < best_dist or (dist == best_dist and seg_mean < best_mean):
                best_seg = seg
                best_dist = dist
                best_mean = seg_mean

        return best_seg

    def _trim_uniform_edge_strips(self, cell: Image.Image) -> Image.Image:
        """Trim uniform edge strips from a cell.

        Some grids have divider pixels that are not perfectly detected as a contiguous gap band.
        As a safety net, remove uniform rows/columns at the edges of each cell and (when available)
        strip rows/columns that match detected divider colors.
        """
        if cell.width <= 1 or cell.height <= 1:
            return cell

        arr = np.asarray(cell, dtype=np.float32)
        if arr.ndim != self._RGB_CHANNELS or arr.shape[2] < self._RGB_CHANNELS:
            return cell

        bounds = _EdgeBounds(top=0, bottom=int(arr.shape[0]), left=0, right=int(arr.shape[1]))
        settings = _EdgeTrimSettings(threshold=self._EDGE_STRIP_STD_THRESHOLD, max_trim=self._EDGE_STRIP_MAX_PX)

        bounds.top = self._trim_top_edge(arr, bounds=bounds, settings=settings)
        bounds.bottom = self._trim_bottom_edge(arr, bounds=bounds, settings=settings)
        bounds.left = self._trim_left_edge(arr, bounds=bounds, settings=settings)
        bounds.right = self._trim_right_edge(arr, bounds=bounds, settings=settings)

        if bounds.top == 0 and bounds.left == 0 and bounds.bottom == arr.shape[0] and bounds.right == arr.shape[1]:
            return cell

        if bounds.right <= bounds.left or bounds.bottom <= bounds.top:
            return cell

        cropped = cell.crop((bounds.left, bounds.top, bounds.right, bounds.bottom))

        # Final safety net: if we detected divider colors for this split, trim a tiny inset on all
        # sides to remove residual divider pixels that are not a clean stripe (e.g., dotted/aliased).
        if getattr(self, "_last_gap_strip_colors", []):
            inset = self._CELL_INSET_PX_ON_GAPS
            if cropped.width > (inset * 2 + 1) and cropped.height > (inset * 2 + 1):
                return cropped.crop((inset, inset, cropped.width - inset, cropped.height - inset))

        return cropped

    def _edge_matches_gap_color(self, edge_rgb: np.ndarray) -> bool:
        colors = getattr(self, "_last_gap_strip_colors", [])
        if not colors:
            return False

        # edge_rgb expected shape: (n, 3)
        threshold = self._EDGE_STRIP_COLOR_DISTANCE_THRESHOLD
        min_coverage = self._EDGE_STRIP_COLOR_COVERAGE_MIN
        for color in colors:
            dists = np.linalg.norm(edge_rgb - color, axis=1)
            coverage = float((dists <= threshold).mean())
            if coverage >= min_coverage:
                return True
        return False

    def _should_strip_edge(self, edge_rgb: np.ndarray, *, uniform_threshold: float) -> bool:
        edge_std = float(edge_rgb.std(axis=0).mean())
        if edge_std <= uniform_threshold:
            return True
        return self._edge_matches_gap_color(edge_rgb)

    def _trim_top_edge(
        self,
        arr: np.ndarray,
        *,
        bounds: _EdgeBounds,
        settings: _EdgeTrimSettings,
    ) -> int:
        trimmed = 0
        while trimmed < settings.max_trim and bounds.top < bounds.bottom - 1:
            edge = arr[bounds.top, bounds.left : bounds.right, :3]
            if not self._should_strip_edge(edge, uniform_threshold=settings.threshold):
                break
            bounds.top += 1
            trimmed += 1
        return bounds.top

    def _trim_bottom_edge(
        self,
        arr: np.ndarray,
        *,
        bounds: _EdgeBounds,
        settings: _EdgeTrimSettings,
    ) -> int:
        trimmed = 0
        while trimmed < settings.max_trim and bounds.bottom - 1 > bounds.top:
            edge = arr[bounds.bottom - 1, bounds.left : bounds.right, :3]
            if not self._should_strip_edge(edge, uniform_threshold=settings.threshold):
                break
            bounds.bottom -= 1
            trimmed += 1
        return bounds.bottom

    def _trim_left_edge(
        self,
        arr: np.ndarray,
        *,
        bounds: _EdgeBounds,
        settings: _EdgeTrimSettings,
    ) -> int:
        trimmed = 0
        while trimmed < settings.max_trim and bounds.left < bounds.right - 1:
            edge = arr[bounds.top : bounds.bottom, bounds.left, :3]
            if not self._should_strip_edge(edge, uniform_threshold=settings.threshold):
                break
            bounds.left += 1
            trimmed += 1
        return bounds.left

    def _trim_right_edge(
        self,
        arr: np.ndarray,
        *,
        bounds: _EdgeBounds,
        settings: _EdgeTrimSettings,
    ) -> int:
        trimmed = 0
        while trimmed < settings.max_trim and bounds.right - 1 > bounds.left:
            edge = arr[bounds.top : bounds.bottom, bounds.right - 1, :3]
            if not self._should_strip_edge(edge, uniform_threshold=settings.threshold):
                break
            bounds.right -= 1
            trimmed += 1
        return bounds.right

    def _ensure_rgb(self, pil_image: Image.Image) -> Image.Image:
        if pil_image.mode == "RGB":
            return pil_image
        return pil_image.convert("RGB")

    def _set_group_visible(self, group_name: str, *, visible: bool) -> None:
        group = self.get_group_by_name_or_element_id(group_name)
        if group is None:
            return

        ui_options = group.ui_options.copy()
        if visible:
            ui_options.pop("hide", None)
        else:
            ui_options["hide"] = True
        group.ui_options = ui_options

    # -------------------------
    # Dynamic output parameters
    # -------------------------

    def _ensure_cell_output_parameters(self, rows: int, cols: int) -> None:
        self._remove_existing_cell_outputs()

        for r in range(1, rows + 1):
            for c in range(1, cols + 1):
                name = f"r{r}c{c}"
                existing = self.get_parameter_by_name(name)
                if existing is not None and not getattr(existing, "user_defined", False):
                    msg = (
                        f"Cannot create output parameter '{name}' because a non-removable parameter "
                        f"with that name already exists on node '{self.name}'."
                    )
                    raise ValueError(msg)

                request = AddParameterToNodeRequest.create(
                    node_name=self.name,
                    parameter_name=name,
                    type="ImageUrlArtifact",
                    input_types=None,
                    output_type="ImageUrlArtifact",
                    tooltip=f"Grid cell output {name} (row-major).",
                    ui_options={
                        "display_name": name,
                        "expander": True,
                        "pulse_on_run": True,
                    },
                    mode_allowed_input=False,
                    mode_allowed_property=False,
                    mode_allowed_output=True,
                    is_user_defined=True,
                    settable=False,
                    parent_element_name=self._grid_cells_group.name,
                )
                result = GriptapeNodes.handle_request(request)
                if not isinstance(result, AddParameterToNodeResultSuccess):
                    raise RuntimeError(  # noqa: TRY004
                        str(getattr(result, "result_details", "Failed to add parameter"))
                    )

    def _remove_existing_cell_outputs(self) -> None:
        to_remove: list[str] = []
        for param in self.parameters:
            if not getattr(param, "user_defined", False):
                continue
            if param.parent_element_name != self._grid_cells_group.name:
                continue
            if self._CELL_PARAM_RE.match(param.name):
                to_remove.append(param.name)

        for name in to_remove:
            GriptapeNodes.handle_request(RemoveParameterFromNodeRequest(parameter_name=name, node_name=self.name))

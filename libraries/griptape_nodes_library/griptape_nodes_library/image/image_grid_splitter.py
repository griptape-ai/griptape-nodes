from __future__ import annotations

import re
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

        grid: list[list[Image.Image]] = []
        for r in range(rows):
            row_imgs: list[Image.Image] = []
            y0 = y_bounds[r]
            y1 = y_bounds[r + 1]
            if y1 <= y0:
                y1 = min(h, y0 + 1)
            for c in range(cols):
                x0 = x_bounds[c]
                x1 = x_bounds[c + 1]
                if x1 <= x0:
                    x1 = min(w, x0 + 1)
                cell = img.crop((x0, y0, x1, y1))
                row_imgs.append(cell)
            grid.append(row_imgs)
        return grid

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

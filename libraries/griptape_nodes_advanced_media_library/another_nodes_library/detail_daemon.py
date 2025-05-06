import io
import logging
import uuid
from typing import Any

import matplotlib as mpl  # type: ignore[reportMissingImports]
import numpy as np
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa:  N813

mpl.use(
    "Agg"
)  # 'Agg', which stands for Anti-Grain Geometry. The Agg backend is a non-interactive, raster-based backend that is suitable for generating images without requiring a display. This is particularly useful in environments where a graphical user interface (GUI) is not available, such as when running scripts on a server or in automated processes.
import matplotlib.pyplot as plt  # type: ignore[reportMissingImports]
from matplotlib.figure import Figure  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


# Alternate naming: SigmaEnvelope (or even something semantically generic)
# but I also want to give credit to the original source.
class DetailDaemon(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="steps",
                default_value=30,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="steps",
            )
        )
        self.add_float_input_parameter(name="start", default=0.2, min_val=0.0, max_val=1.0)
        self.add_float_input_parameter(name="end", default=0.8, min_val=0.0, max_val=1.0)
        self.add_float_input_parameter(name="bias", default=0.71, min_val=0.0, max_val=1.0)
        self.add_float_input_parameter(name="amount", default=0.25, min_val=0.0, max_val=1.0)
        self.add_float_input_parameter(name="exponent", default=1.0, min_val=0.0, max_val=10.0)
        self.add_float_input_parameter(name="start_offset", default=0.0, min_val=-1.0, max_val=1.0)
        self.add_float_input_parameter(name="end_offset", default=-0.15, min_val=-1.0, max_val=1.0)
        self.add_float_input_parameter(name="fade", default=0.0, min_val=0.0, max_val=1.0)
        self.add_parameter(
            Parameter(
                name="smooth",
                input_types=["bool"],
                type="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                default_value=True,
                tooltip="smooth",
            )
        )

        self.add_parameter(
            Parameter(
                name="sigmas",
                output_type="str",
                tooltip="sigmas",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="visualization",
                output_type="ImageArtifact",
                tooltip="visualization -- for display only",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def add_float_input_parameter(
        self,
        name: str,
        default: float,
        min_val: float,
        max_val: float,
    ) -> None:
        self.add_parameter(
            Parameter(
                name=name,
                input_types=["float"],
                type="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                default_value=default,
                tooltip=name,
                ui_options={
                    "slider": {"min_val": min_val, "max_val": max_val},
                    "step": 0.01,
                },
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:  # noqa: ARG002
        if parameter.name in {"visualization"}:
            return
        cmd.run_node(node_name=self.name)

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        values, visualization_image_artifact = self.visualize(
            steps=int(self.get_parameter_value("steps")),
            start=float(self.get_parameter_value("start")),
            end=float(self.get_parameter_value("end")),
            bias=float(self.get_parameter_value("bias")),
            amount=float(self.get_parameter_value("amount")),
            exponent=float(self.get_parameter_value("exponent")),
            start_offset=float(self.get_parameter_value("start_offset")),
            end_offset=float(self.get_parameter_value("end_offset")),
            fade=float(self.get_parameter_value("fade")),
            smooth=bool(self.get_parameter_value("smooth")),
            enabled=True,
        )
        self.parameter_output_values["sigmas"] = ",".join([f"{sigma:.2f}" for sigma in values])
        self.parameter_output_values["visualization"] = visualization_image_artifact

    def make_schedule(  # noqa: PLR0913
        self,
        steps: int,
        start: float,
        end: float,
        bias: float,
        amount: float,
        exponent: float,
        start_offset: float,
        end_offset: float,
        fade: float,
        *,
        smooth: bool,
    ) -> np.ndarray:
        start = min(start, end)
        mid = start + bias * (end - start)
        multipliers = np.zeros(steps)

        start_idx, mid_idx, end_idx = [round(x * (steps - 1)) for x in [start, mid, end]]

        start_values = np.linspace(0, 1, mid_idx - start_idx + 1)
        if smooth:
            start_values = 0.5 * (1 - np.cos(start_values * np.pi))
        start_values = start_values**exponent
        if start_values.any():
            start_values *= amount - start_offset
            start_values += start_offset

        end_values = np.linspace(1, 0, end_idx - mid_idx + 1)
        if smooth:
            end_values = 0.5 * (1 - np.cos(end_values * np.pi))
        end_values = end_values**exponent
        if end_values.any():
            end_values *= amount - end_offset
            end_values += end_offset

        multipliers[start_idx : mid_idx + 1] = start_values
        multipliers[mid_idx : end_idx + 1] = end_values
        multipliers[:start_idx] = start_offset
        multipliers[end_idx + 1 :] = end_offset
        multipliers *= 1 - fade

        return multipliers

    def visualize(  # noqa: PLR0913
        self,
        steps: int,
        start: float,
        end: float,
        bias: float,
        amount: float,
        exponent: float,
        start_offset: float,
        end_offset: float,
        fade: float,
        *,
        smooth: bool,
        enabled: bool,
    ) -> tuple[np.ndarray, ImageUrlArtifact]:
        values = self.make_schedule(
            steps, start, end, bias, amount, exponent, start_offset, end_offset, fade, smooth=smooth
        )
        mean = sum(values) / steps
        peak = np.clip(max(abs(values)), -1, 1)
        start = min(start, end)
        mid = start + bias * (end - start)
        opacity = 0.1 + (1 - fade) * 0.7
        plot_color = (
            (0.5, 0.5, 0.5, opacity)
            if not enabled
            else ((1 - peak) ** 2, 1, 0, opacity)
            if mean >= 0
            else (1, (1 - peak) ** 2, 0, opacity)
        )
        plt.rcParams.update(
            {
                "text.color": plot_color,
                "axes.labelcolor": plot_color,
                "axes.edgecolor": plot_color,
                "figure.facecolor": (0.0, 0.0, 0.0, 0.0),
                "axes.facecolor": (0.0, 0.0, 0.0, 0.0),
                "ytick.labelsize": 6,
                "ytick.labelcolor": plot_color,
                "ytick.color": plot_color,
            }
        )
        fig, ax = plt.subplots(figsize=(2.15, 2.00), layout="constrained")
        ax.plot(range(steps), values, color=plot_color)
        ax.axhline(y=0, color=plot_color, linestyle="dotted")
        ax.axvline(x=mid * (steps - 1), color=plot_color, linestyle="dotted")
        ax.tick_params(right=False, color=plot_color)
        ax.set_xticks([i * (steps - 1) / 10 for i in range(10)][1:])
        ax.set_xticklabels([])
        ax.set_ylim(-1, 1)
        ax.set_xlim(0, steps - 1)
        plt.close()

        return (values, self.fig_to_svg_image_url_artifact(fig))

    def fig_to_png_image_artifact(self, fig: Figure) -> ImageUrlArtifact:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        image_io = io.BytesIO()
        fig.savefig(image_io, format="png")
        image_bytes = image_io.getvalue()
        url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, f"{uuid.uuid4()}.svg")
        return ImageUrlArtifact(value=url)

    def fig_to_svg_image_url_artifact(self, fig: Figure) -> ImageUrlArtifact:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        image_io = io.BytesIO()
        fig.savefig(image_io, format="svg")
        image_bytes = image_io.getvalue()
        url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, f"{uuid.uuid4()}.svg")
        return ImageUrlArtifact(value=url)

import io
import uuid

import numpy as np
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image, ImageFilter

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact


class LensBlur(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "Image"
        self.description = "Simulates lens blur (bokeh) using a depth map. White=in focus, black=blurry."

        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
                tooltip="Input image to blur (also available as passthrough output)",
            )
        )
        self.add_parameter(
            Parameter(
                name="depth_map",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
                tooltip="Depth map (white=in focus, black=blurry) (also available as passthrough output)",
            )
        )
        self.add_parameter(
            Parameter(
                name="aperture",
                type="float",
                default_value=2.8,
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="Aperture (f-stop): lower = more blur, higher = less blur",
                traits={Slider(min_val=1.0, max_val=16.0)},
                ui_options={"min": 1.0, "max": 16.0, "step": 0.1},
            )
        )
        self.add_parameter(
            Parameter(
                name="focus_distance",
                type="float",
                default_value=0.5,
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="Which depth is in focus (0=background/black, 1=foreground/white)",
                traits={Slider(min_val=0.0, max_val=1.0)},
                ui_options={"min": 0.0, "max": 1.0, "step": 0.01},
            )
        )
        self.add_parameter(
            Parameter(
                name="focus_falloff",
                type="float",
                default_value=1.0,
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="How soft the blur transitions are (higher = softer)",
                traits={Slider(min_val=0.0, max_val=5.0)},
                ui_options={"min": 0.0, "max": 5.0, "step": 0.1},
            )
        )
        self.add_parameter(
            Parameter(
                name="bokeh_shape",
                type="str",
                default_value="gaussian",
                allowed_modes={ParameterMode.PROPERTY},
                tooltip="Blur kernel shape: Gaussian (soft) or Disk (bokeh)",
                traits={Options(choices=["gaussian", "disk"])},
                ui_options={"choices": ["gaussian", "disk"]},
            )
        )
        self.add_parameter(
            Parameter(
                name="invert_depth",
                type="bool",
                default_value=False,
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="Invert the depth map (swap near/far) before blurring",
            )
        )
        self.add_parameter(
            Parameter(
                name="blur_quality",
                type="int",
                default_value=32,
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="Blur quality: number of blur layers (higher = smoother, slower)",
                traits={Slider(min_val=2, max_val=64)},
                ui_options={"min": 2, "max": 64, "step": 1},
            )
        )
        self.add_parameter(
            Parameter(
                name="min_blur_radius",
                type="int",
                default_value=0,
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="Minimum blur radius (pixels)",
                traits={Slider(min_val=0, max_val=50)},
                ui_options={"min": 0, "max": 50, "step": 1},
            )
        )
        self.add_parameter(
            Parameter(
                name="max_blur_radius",
                type="int",
                default_value=35,
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="Maximum blur radius (pixels)",
                traits={Slider(min_val=1, max_val=200)},
                ui_options={"min": 1, "max": 200, "step": 1},
            )
        )
        self.add_parameter(
            Parameter(
                name="depth_gamma",
                type="float",
                default_value=1.0,
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="Gamma correction for depth map (advanced)",
                traits={Slider(min_val=0.1, max_val=5.0)},
                ui_options={"min": 0.1, "max": 5.0, "step": 0.01},
            )
        )
        self.add_parameter(
            Parameter(
                name="depth_contrast",
                type="float",
                default_value=1.0,
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="Depth map contrast: increase to make whites whiter and blacks blacker (centered at 0.5)",
                traits={Slider(min_val=0.1, max_val=3.0)},
                ui_options={"min": 0.1, "max": 3.0, "step": 0.01},
            )
        )
        self.add_parameter(
            Parameter(
                name="show_depth_preview",
                type="bool",
                default_value=False,
                allowed_modes={ParameterMode.PROPERTY},
                tooltip="Show the processed depth map as an output image",
            )
        )
        self.add_parameter(
            Parameter(
                name="focus_picker",
                type="list",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="Click on depth preview to set focus distance. Format: [x, y] coordinates (0-1 normalized)",
            )
        )
        self.add_parameter(
            Parameter(
                name="output",
                type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Output image with lens blur",
            )
        )
        self.add_parameter(
            Parameter(
                name="depth_preview",
                type="ImageUrlArtifact",
                output_type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Preview of the processed depth map (click to set focus)",
            )
        )

    def process(self) -> None:
        image_artifact = self.parameter_values.get("image")
        depth_artifact = self.parameter_values.get("depth_map")
        if image_artifact is None or depth_artifact is None:
            self.parameter_output_values["output"] = None
            self.parameter_output_values["depth_preview"] = None
            self.parameter_output_values["image"] = image_artifact
            self.parameter_output_values["depth_map"] = depth_artifact
            return
        aperture = float(self.parameter_values.get("aperture", 2.8))
        focus_distance = float(self.parameter_values.get("focus_distance", 0.5))
        focus_falloff = float(self.parameter_values.get("focus_falloff", 1.0))
        bokeh_shape = self.parameter_values.get("bokeh_shape", "gaussian")
        invert_depth = bool(self.parameter_values.get("invert_depth", False))
        blur_quality = int(self.parameter_values.get("blur_quality", 32))
        min_blur_radius = int(self.parameter_values.get("min_blur_radius", 0))
        max_blur_radius = int(self.parameter_values.get("max_blur_radius", 35))
        depth_gamma = float(self.parameter_values.get("depth_gamma", 1.0))
        depth_contrast = float(self.parameter_values.get("depth_contrast", 1.0))
        show_depth_preview = bool(self.parameter_values.get("show_depth_preview", False))
        focus_picker = self.parameter_values.get("focus_picker")

        # Map aperture to blur strength: lower f-stop = more blur
        # We'll use max_blur_radius as the main blur control, but scale it by aperture for realism
        # (e.g., max_blur_radius = user max_blur_radius * (2.8 / aperture))
        blur_scale = 2.8 / max(aperture, 0.01)
        max_blur = int(max_blur_radius * blur_scale)
        min_blur = min_blur_radius
        num_layers = blur_quality

        # Passthrough outputs
        self.parameter_output_values["image"] = image_artifact
        self.parameter_output_values["depth_map"] = depth_artifact

        # Load images
        def load_img(artifact):
            if isinstance(artifact, dict):
                artifact = dict_to_image_url_artifact(artifact)
            if isinstance(artifact, ImageUrlArtifact):
                return Image.open(io.BytesIO(artifact.to_bytes())).convert("RGB")
            if isinstance(artifact, ImageArtifact):
                return Image.open(io.BytesIO(artifact.value)).convert("RGB")
            msg = "Invalid image artifact"
            raise ValueError(msg)

        img = load_img(image_artifact)
        depth = load_img(depth_artifact).convert("L")
        img_np = np.array(img)
        depth_np = np.array(depth).astype(np.float32) / 255.0

        # Optionally apply gamma correction to depth map
        if depth_gamma != 1.0:
            depth_np = np.power(depth_np, depth_gamma)
        # --- Contrast adjustment (centered at 0.5) ---
        if depth_contrast != 1.0:
            depth_np = np.clip(0.5 + depth_contrast * (depth_np - 0.5), 0, 1)

        # Optionally invert the depth map
        if invert_depth:
            depth_np = 1.0 - depth_np

        # Optionally blur the depth map for smooth transitions
        if focus_falloff > 0:
            from scipy.ndimage import gaussian_filter

            depth_np = gaussian_filter(depth_np, sigma=focus_falloff)

        # Handle focus picker - if user clicked on depth preview, use that depth value
        if focus_picker is not None and isinstance(focus_picker, (list, tuple)) and len(focus_picker) == 2:
            x_norm, y_norm = focus_picker
            # Convert normalized coordinates (0-1) to pixel coordinates
            h, w = depth_np.shape
            x = int(np.clip(x_norm * w, 0, w - 1))
            y = int(np.clip(y_norm * h, 0, h - 1))
            # Get the depth value at that pixel
            picked_depth = float(depth_np[y, x])
            focus_distance = picked_depth
            # Update the parameter value for UI sync
            self.parameter_values["focus_distance"] = picked_depth

        # Show depth preview if requested
        if show_depth_preview:
            depth_img = Image.fromarray(np.clip(depth_np * 255, 0, 255).astype(np.uint8), mode="L")
            img_byte_arr = io.BytesIO()
            depth_img.save(img_byte_arr, format="PNG")
            img_byte_arr = img_byte_arr.getvalue()
            static_url = GriptapeNodes.StaticFilesManager().save_static_file(
                img_byte_arr, f"depth_preview_{uuid.uuid4()}.png"
            )
            self.parameter_output_values["depth_preview"] = ImageUrlArtifact(value=static_url)
        else:
            self.parameter_output_values["depth_preview"] = None

        # Prepare blurred versions
        blurred_np = []
        if bokeh_shape == "disk":
            try:
                from skimage.filters import rank
                from skimage.morphology import disk
                from skimage.util import img_as_ubyte

                img_ubyte = img_as_ubyte(img)
                for i in range(num_layers):
                    radius = int(min_blur + (max_blur - min_blur) * (i / max(num_layers - 1, 1)))
                    if radius < 1:
                        blurred = img_ubyte
                    else:
                        blurred_channels = [rank.mean(img_ubyte[..., c], disk(radius)) for c in range(3)]
                        blurred = np.stack(blurred_channels, axis=-1)
                    blurred_np.append(blurred)
            except ImportError:
                blurred_np = [
                    np.array(
                        img.filter(
                            ImageFilter.GaussianBlur(
                                radius=min_blur + (max_blur - min_blur) * (i / max(num_layers - 1, 1))
                            )
                        )
                    )
                    for i in range(num_layers)
                ]
        else:
            blurred_np = [
                np.array(
                    img.filter(
                        ImageFilter.GaussianBlur(radius=min_blur + (max_blur - min_blur) * (i / max(num_layers - 1, 1)))
                    )
                )
                for i in range(num_layers)
            ]

        # Linear interpolation between blur layers for realism
        h, w = depth_np.shape
        out_np = np.zeros_like(img_np)
        for y in range(h):
            for x in range(w):
                # Blur is proportional to distance from focus_distance
                blur_dist = abs(depth_np[y, x] - focus_distance)
                blur_f = blur_dist * (num_layers - 1)
                blur_idx_low = int(np.floor(blur_f))
                blur_idx_high = min(blur_idx_low + 1, num_layers - 1)
                t = blur_f - blur_idx_low
                out_np[y, x] = ((1 - t) * blurred_np[blur_idx_low][y, x] + t * blurred_np[blur_idx_high][y, x]).astype(
                    np.uint8
                )

        out_img = Image.fromarray(out_np)
        img_byte_arr = io.BytesIO()
        out_img.save(img_byte_arr, format="PNG")
        img_byte_arr = img_byte_arr.getvalue()
        static_url = GriptapeNodes.StaticFilesManager().save_static_file(img_byte_arr, f"{uuid.uuid4()}.png")
        url_artifact = ImageUrlArtifact(value=static_url)
        self.parameter_output_values["output"] = url_artifact

    def after_value_set(self, parameter, value, modified_parameters_set=None) -> None:
        if parameter.name in {
            "aperture",
            "focus_distance",
            "focus_falloff",
            "image",
            "depth_map",
            "bokeh_shape",
            "invert_depth",
            "blur_quality",
            "min_blur_radius",
            "max_blur_radius",
            "depth_gamma",
            "show_depth_preview",
            "focus_picker",
            "depth_contrast",
        }:
            from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd

            cmd.run_node(node_name=self.name)

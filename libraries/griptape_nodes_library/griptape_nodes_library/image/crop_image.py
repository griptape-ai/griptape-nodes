import io
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from libraries.griptape_nodes_library.griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact


class CropMetadataTethering:
    """Helper object for managing bidirectional sync between crop parameters and metadata.

    This class provides reusable tethering logic that synchronizes crop parameters
    (left, top, width, height, zoom, rotate) with input_image.meta["crop_settings"].
    When one is updated, the other automatically updates to reflect the change.
    """

    def __init__(self, node, input_image_parameter: Parameter, crop_parameters: list[str]):
        """Initialize the tethering helper.

        Args:
            node: The node that owns the parameters
            input_image_parameter: The input image parameter that contains metadata
            crop_parameters: List of crop parameter names to sync
        """
        self.node = node
        self.input_image_parameter = input_image_parameter
        self.crop_parameters = crop_parameters

        # Tracks which parameter is currently driving updates to prevent infinite loops
        # This lock is critical: crop param change -> metadata update -> crop param change -> ...
        self._updating_from_parameter = None

    def on_after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes - call from node's after_value_set().

        Args:
            parameter: The parameter that changed
            value: The new value
        """
        logger.info(f"Tethering on_after_value_set called for parameter: {parameter.name}")

        # Check if we're in processing mode - skip tethering during execution
        if hasattr(self.node, "_processing") and self.node._processing:
            logger.debug(f"Skipping tethering during node execution for {parameter.name}")
            return

        # Check the lock first: Skip if we're already in an update cycle to prevent infinite loops
        if self._updating_from_parameter is not None:
            logger.debug(
                f"Skipping tethering for {parameter.name} - already updating from {self._updating_from_parameter}"
            )
            return

        # Only handle our parameters
        if parameter.name not in [self.input_image_parameter.name] + self.crop_parameters:
            logger.debug(f"Parameter {parameter.name} not in our scope, ignoring")
            return

        logger.info(f"Processing tethering for parameter: {parameter.name}")

        # Acquire the lock: Set which parameter is driving the current update cycle
        self._updating_from_parameter = parameter.name
        try:
            if parameter.name == self.input_image_parameter.name:
                logger.info("Calling _handle_metadata_change")
                self._handle_metadata_change(value)
            elif parameter.name in self.crop_parameters:
                logger.info("Calling _handle_crop_parameter_change")
                self._handle_crop_parameter_change(parameter.name, value)
        except Exception as e:
            logger.error(f"Failed to sync crop metadata for parameter '{parameter.name}': {e}")
        finally:
            # Always clear the update lock - critical for allowing future updates
            self._updating_from_parameter = None

    def check_and_sync_metadata(self) -> None:
        """Check if metadata has changed and sync parameters if needed.
        This can be called periodically or when we suspect metadata might have changed.
        """
        # Check if we're in processing mode - skip during execution
        if hasattr(self.node, "_processing") and self.node._processing:
            logger.debug("Skipping metadata check during node execution")
            return

        if self._updating_from_parameter is not None:
            logger.debug("Skipping metadata check - already in update cycle")
            return  # Skip if we're already in an update cycle

        input_artifact = self.node.get_parameter_value(self.input_image_parameter.name)
        if input_artifact is None:
            logger.debug("No input artifact found for metadata check")
            return

        # Check if metadata exists and has crop settings
        if hasattr(input_artifact, "meta"):
            meta = input_artifact.meta or {}
            crop_settings = meta.get("crop_settings", {})
            if crop_settings:
                logger.info("Found crop metadata, syncing parameters")
                self._updating_from_parameter = "metadata_check"
                try:
                    self._handle_metadata_change(input_artifact)
                finally:
                    self._updating_from_parameter = None
        else:
            logger.debug("No meta attribute found on input artifact")

    def _handle_crop_parameter_change(self, param_name: str, value: Any) -> None:
        """Handle changes to crop parameters by updating metadata."""
        logger.info(f"Updating metadata from crop parameter change: {param_name} = {value}")

        # Get current metadata
        input_artifact = self.node.get_parameter_value(self.input_image_parameter.name)
        if input_artifact is None:
            return

        # Log the current metadata before we change it
        if hasattr(input_artifact, "meta") and input_artifact.meta:
            logger.info(f"Current metadata before update: {input_artifact.meta}")
        else:
            logger.info("No existing metadata found")

        # Ensure metadata exists
        if hasattr(input_artifact, "meta"):
            if input_artifact.meta is None:
                input_artifact.meta = {}
        else:
            logger.warning("Input artifact has no 'meta' attribute")
            return

        # Get or create crop settings
        if "crop_settings" not in input_artifact.meta:
            input_artifact.meta["crop_settings"] = {}

        crop_settings = input_artifact.meta["crop_settings"]

        # Get or create crop data
        if "crop" not in crop_settings:
            crop_settings["crop"] = {}

        crop_data = crop_settings["crop"]

        # Update ALL crop parameters in metadata (not just the one that changed)
        # Get current values for all crop parameters
        left = self.node.get_parameter_value("left") or 0
        top = self.node.get_parameter_value("top") or 0
        width = self.node.get_parameter_value("width") or 0
        height = self.node.get_parameter_value("height") or 0
        zoom = self.node.get_parameter_value("zoom") or 1.0
        rotate = self.node.get_parameter_value("rotate") or 0.0

        logger.info(
            f"About to update metadata with values: left={left}, top={top}, width={width}, height={height}, zoom={zoom}, rotation={rotate}"
        )

        # Update all crop coordinates
        crop_data["left"] = int(left)
        crop_data["top"] = int(top)
        crop_data["width"] = int(width)
        crop_data["height"] = int(height)

        # Update zoom and rotation at top level
        crop_settings["zoom"] = float(zoom)  # Store as percentage (100 = no zoom)
        crop_settings["rotate"] = float(rotate)

        logger.info(f"Updated metadata with all crop parameters: {crop_settings}")

        # After updating metadata, manually trigger a metadata check to sync parameters
        # This ensures that if the GUI updates metadata, our parameters get updated too
        logger.info("Manually triggering metadata check after update")
        self.check_and_sync_metadata()

    def _handle_metadata_change(self, input_artifact: Any) -> None:
        """Handle changes to input image metadata by updating crop parameters."""
        logger.info("Updating crop parameters from metadata change")
        logger.info(f"Input artifact: {input_artifact}")

        if input_artifact is None:
            logger.info("Input artifact is None, skipping")
            return

        # Get metadata - handle both dict and object formats
        if isinstance(input_artifact, dict):
            # Input artifact is a dictionary
            meta = input_artifact.get("meta", {})
            logger.info(f"Found metadata (dict): {meta}")
        elif hasattr(input_artifact, "meta"):
            # Input artifact is an object with meta attribute
            meta = input_artifact.meta or {}
            logger.info(f"Found metadata (object): {meta}")
        else:
            logger.warning("Input artifact has no 'meta' attribute and is not a dict")
            return

        # Get crop settings
        crop_settings = meta.get("crop_settings", {})
        logger.info(f"Found crop settings: {crop_settings}")
        if not crop_settings:
            logger.info("No crop settings found in metadata")
            return

        # Update crop parameters from metadata
        crop_data = crop_settings.get("crop", {})
        logger.info(f"Found crop data: {crop_data}")

        # Check if this is the first time loading this image (no user-set values yet)
        # We'll assume if any crop parameter is at its default value, we can load from metadata
        current_left = self.node.get_parameter_value("left") or 0
        current_top = self.node.get_parameter_value("top") or 0
        current_width = self.node.get_parameter_value("width") or 0
        current_height = self.node.get_parameter_value("height") or 0
        current_zoom = self.node.get_parameter_value("zoom") or 100.0
        current_rotation = self.node.get_parameter_value("rotate") or 0.0

        # Only sync from metadata if parameters are at their defaults
        # This prevents overwriting user-set values with metadata defaults
        should_sync_left = current_left == 0 and "left" in crop_data
        should_sync_top = current_top == 0 and "top" in crop_data
        should_sync_width = current_width == 0 and "width" in crop_data
        should_sync_height = current_height == 0 and "height" in crop_data
        should_sync_zoom = current_zoom == 100.0 and "zoom" in crop_settings
        should_sync_rotation = current_rotation == 0.0 and "rotate" in crop_settings

        logger.info(
            f"Current values: left={current_left}, top={current_top}, width={current_width}, height={current_height}, zoom={current_zoom}, rotation={current_rotation}"
        )
        logger.info(
            f"Should sync: left={should_sync_left}, top={should_sync_top}, width={should_sync_width}, height={should_sync_height}, zoom={should_sync_zoom}, rotation={should_sync_rotation}"
        )

        # Sync crop coordinates from metadata (only if at defaults)
        if should_sync_left:
            value = crop_data["left"]
            logger.info(f"Syncing left = {value}")
            self._sync_parameter_value("left", value)
            logger.info(f"Synced left = {value}")
        else:
            logger.info(f"Skipping left sync - current value {current_left} is not default")

        if should_sync_top:
            value = crop_data["top"]
            logger.info(f"Syncing top = {value}")
            self._sync_parameter_value("top", value)
            logger.info(f"Synced top = {value}")
        else:
            logger.info(f"Skipping top sync - current value {current_top} is not default")

        if should_sync_width:
            value = crop_data["width"]
            logger.info(f"Syncing width = {value}")
            self._sync_parameter_value("width", value)
            logger.info(f"Synced width = {value}")
        else:
            logger.info(f"Skipping width sync - current value {current_width} is not default")

        if should_sync_height:
            value = crop_data["height"]
            logger.info(f"Syncing height = {value}")
            self._sync_parameter_value("height", value)
            logger.info(f"Synced height = {value}")
        else:
            logger.info(f"Skipping height sync - current value {current_height} is not default")

        # Sync zoom and rotation from metadata (only if at defaults)
        if should_sync_zoom:
            value = crop_settings["zoom"]
            # Convert from old zoom factor format (1.0 = no zoom) to new percentage format (100 = no zoom)
            if isinstance(value, (int, float)) and value <= 10.0:
                # This is likely the old format, convert to percentage
                value = value * 100.0
                logger.info(f"Converting zoom from factor {value / 100.0} to percentage {value}")
            logger.info(f"Syncing zoom = {value}")
            self._sync_parameter_value("zoom", value)
            logger.info(f"Synced zoom = {value}")
        else:
            logger.info(f"Skipping zoom sync - current value {current_zoom} is not default")

        if should_sync_rotation:
            value = crop_settings["rotate"]
            logger.info(f"Syncing rotate = {value}")
            self._sync_parameter_value("rotate", value)
            logger.info(f"Synced rotate = {value}")
        else:
            logger.info(f"Skipping rotation sync - current value {current_rotation} is not default")

    def _sync_parameter_value(self, param_name: str, value: Any) -> None:
        """Helper to sync parameter values without triggering infinite loops."""
        # Use initial_setup=True to avoid triggering after_value_set() again
        self.node.set_parameter_value(param_name, value, initial_setup=True)
        self.node.publish_update_to_parameter(param_name, value)


class CropImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "Image"
        self.description = "Crop an image to a specific size."

        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                type="ImageUrlArtifact",
                default_value=None,
                tooltip="Input image to crop",
                ui_options={"crop_image": True},
            )
        )

        with ParameterGroup(name="crop_coordinates", ui_options={"collapsed": False}) as crop_coordinates:
            Parameter(
                name="left",
                type="int",
                default_value=0,
                tooltip="Left edge of crop area in pixels",
                traits={Slider(min_val=0, max_val=4000)},
            )

            Parameter(
                name="top",
                type="int",
                default_value=0,
                tooltip="Top edge of crop area in pixels",
                traits={Slider(min_val=0, max_val=4000)},
            )

            Parameter(
                name="width",
                type="int",
                default_value=0,
                tooltip="Width of crop area in pixels (0 = use full width)",
                traits={Slider(min_val=0, max_val=4000)},
            )

            Parameter(
                name="height",
                type="int",
                default_value=0,
                tooltip="Height of crop area in pixels (0 = use full height)",
                traits={Slider(min_val=0, max_val=4000)},
            )
        self.add_node_element(crop_coordinates)

        with ParameterGroup(name="transform_options", ui_options={"collapsed": False}) as transform_options:
            Parameter(
                name="zoom",
                type="float",
                default_value=100.0,
                tooltip="Zoom percentage (100 = no zoom, 200 = 2x zoom in, 50 = 0.5x zoom out)",
                traits={Slider(min_val=0.0, max_val=300.0)},
            )
            Parameter(
                name="rotate",
                type="float",
                default_value=0.0,
                tooltip="Rotation in degrees (-180 to 180)",
                traits={Slider(min_val=-180.0, max_val=180.0)},
            )

        self.add_node_element(transform_options)
        with ParameterGroup(name="output_options", ui_options={"collapsed": True}) as output_options:
            Parameter(
                name="background_color",
                type="str",
                default_value="#00000000",
                tooltip="Background color (RGBA or hex) for transparent areas",
            )
            Parameter(
                name="output_format",
                type="str",
                default_value="PNG",
                tooltip="Output format: PNG, JPEG, WEBP",
                traits={Options(choices=["PNG", "JPEG", "WEBP"])},
            )

            Parameter(
                name="output_quality",
                type="float",
                default_value=0.9,
                tooltip="Output quality (0.0 to 1.0) for lossy formats",
            )

        self.add_node_element(output_options)

        # Output parameter
        self.add_parameter(
            Parameter(
                name="output",
                type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Cropped output image",
            )
        )

        # Initialize processing flag
        self._processing = False

        # Initialize crop metadata tethering
        input_image_param = self.get_parameter_by_name("input_image")
        if input_image_param is None:
            raise ValueError("input_image parameter not found")
        crop_params = ["left", "top", "width", "height", "zoom", "rotate"]
        self._crop_tethering = CropMetadataTethering(
            node=self,
            input_image_parameter=input_image_param,
            crop_parameters=crop_params,
        )

    def _crop(self) -> None:
        input_artifact = self.get_parameter_value("input_image")
        left = self.get_parameter_value("left")
        top = self.get_parameter_value("top")
        width = self.get_parameter_value("width")
        height = self.get_parameter_value("height")
        zoom = self.get_parameter_value("zoom")
        rotate = self.get_parameter_value("rotate")
        background_color = self.get_parameter_value("background_color")
        output_format = self.get_parameter_value("output_format")
        output_quality = self.get_parameter_value("output_quality")

        # Load image
        def load_img(artifact):
            if isinstance(artifact, dict):
                artifact = dict_to_image_url_artifact(artifact)
            if isinstance(artifact, ImageUrlArtifact):
                return Image.open(io.BytesIO(artifact.to_bytes()))
            if isinstance(artifact, ImageArtifact):
                return Image.open(io.BytesIO(artifact.value))
            raise ValueError("Invalid image artifact")

        img = load_img(input_artifact)
        original_width, original_height = img.size

        # Apply crop coordinates FIRST (before rotation and zoom)
        img_width, img_height = img.size

        # Apply crop if coordinates are specified
        if left > 0 or top > 0 or width > 0 or height > 0:
            # Set defaults for unspecified coordinates
            if width == 0:
                width = img_width  # Use full width
            if height == 0:
                height = img_height  # Use full height

            # Calculate crop coordinates
            crop_left = left
            crop_top = top
            crop_right = left + width
            crop_bottom = top + height

            # Ensure crop coordinates are within image bounds
            crop_left = max(0, min(crop_left, img_width))
            crop_right = max(crop_left, min(crop_right, img_width))
            crop_top = max(0, min(crop_top, img_height))
            crop_bottom = max(crop_top, min(crop_bottom, img_height))

            # Additional safety check - ensure we have a valid crop area
            if crop_right > crop_left and crop_bottom > crop_top:
                try:
                    img = img.crop((crop_left, crop_top, crop_right, crop_bottom))
                    # Update dimensions after crop
                    img_width, img_height = img.size
                except Exception as e:
                    msg = f"{self.name}: Crop failed: {e}. Using original image."
                    logger.warning(msg)
                    # If crop fails, continue with original image
            else:
                msg = f"{self.name}: Invalid crop coordinates, skipping crop"
                logger.warning(msg)

        # Apply rotation SECOND (around the center of the cropped area)
        if rotate != 0.0:
            # Convert background color to RGBA
            bg_color = self._parse_color(background_color)
            # Rotate without expanding to keep the same image dimensions
            img = img.rotate(rotate, expand=False, fillcolor=bg_color)
            # Dimensions remain the same since we're not expanding

        # Apply zoom (percentage-based: 100 = no zoom, 200 = 2x zoom in, 50 = 0.5x zoom out)
        if zoom != 100.0:
            # Convert percentage to factor (100% = 1.0, 200% = 2.0, 50% = 0.5)
            zoom_factor = zoom / 100.0

            if zoom_factor > 1.0:
                # Zoom in (crop a smaller area from the center)
                # Use the center of the current (potentially cropped) image
                zoom_center_x = img_width / 2
                zoom_center_y = img_height / 2

                # Calculate new dimensions after zoom (smaller than current)
                new_width = int(img_width / zoom_factor)
                new_height = int(img_height / zoom_factor)

                # Calculate crop coordinates to zoom into center
                crop_x = int(zoom_center_x - new_width / 2)
                crop_y = int(zoom_center_y - new_height / 2)

                # Ensure crop coordinates are within bounds
                crop_x = max(0, min(crop_x, img_width - new_width))
                crop_y = max(0, min(crop_y, img_height - new_height))

                img = img.crop((crop_x, crop_y, crop_x + new_width, crop_y + new_height))
            elif zoom_factor < 1.0:
                # Zoom out (enlarge the image)
                # Calculate new dimensions after zoom (larger than current)
                new_width = int(img_width / zoom_factor)
                new_height = int(img_height / zoom_factor)

                # Create a new image with the zoomed out size and background color
                bg_color = self._parse_color(background_color)
                zoomed_img = Image.new(img.mode, (new_width, new_height), bg_color)

                # Calculate position to center the original image in the zoomed out image
                paste_x = (new_width - img_width) // 2
                paste_y = (new_height - img_height) // 2

                # Paste the original image centered in the zoomed out image
                zoomed_img.paste(img, (paste_x, paste_y))
                img = zoomed_img

        # Save result
        img_byte_arr = io.BytesIO()

        # Determine save format and options
        save_format = output_format.upper()
        save_options = {}

        if save_format == "JPEG":
            save_options["quality"] = int(output_quality * 100)
            save_options["optimize"] = True
        elif save_format == "WEBP":
            save_options["quality"] = int(output_quality * 100)
            save_options["lossless"] = False

        img.save(img_byte_arr, format=save_format, **save_options)
        img_byte_arr = img_byte_arr.getvalue()

        # Generate meaningful filename based on workflow and node
        filename = self._generate_filename(save_format.lower())
        static_url = GriptapeNodes.StaticFilesManager().save_static_file(img_byte_arr, filename)
        self.parameter_output_values["output"] = ImageUrlArtifact(value=static_url)

    def _generate_filename(self, extension: str) -> str:
        """Generate a meaningful filename based on workflow and node information."""
        # Get workflow and node context
        workflow_name = "unknown_workflow"
        node_name = self.name

        # Try to get workflow name from context
        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            context_manager = GriptapeNodes.ContextManager()
            workflow_name = context_manager.get_current_workflow_name()
        except Exception as e:
            msg = f"{self.name}: Error getting workflow name: {e}"
            logger.warning(msg)

        # Clean up names for filename use
        workflow_name = "".join(c for c in workflow_name if c.isalnum() or c in ("-", "_")).rstrip()
        node_name = "".join(c for c in node_name if c.isalnum() or c in ("-", "_")).rstrip()

        # Get current timestamp for cache busting
        from datetime import datetime

        timestamp = int(datetime.now().timestamp())

        # Create filename with meaningful structure and timestamp as query parameter
        filename = f"crop_{workflow_name}_{node_name}.{extension}?t={timestamp}"

        return filename

    def process(self) -> None:
        logger.info(f"Starting process() for {self.name}")

        # Log current parameter values before processing
        left = self.get_parameter_value("left") or 0
        top = self.get_parameter_value("top") or 0
        width = self.get_parameter_value("width") or 0
        height = self.get_parameter_value("height") or 0
        zoom = self.get_parameter_value("zoom") or 100.0
        rotation = self.get_parameter_value("rotate") or 0.0

        logger.info(
            f"Parameter values at start of process: left={left}, top={top}, width={width}, height={height}, zoom={zoom}, rotation={rotation}"
        )

        # Set processing flag to prevent after_value_set interference
        self._processing = True
        try:
            # Just do the cropping - metadata updates happen in after_value_set
            self._crop()
        finally:
            # Always clear the processing flag
            self._processing = False
            logger.info(f"Finished process() for {self.name}")

    def _parse_color(self, color_str: str) -> tuple[int, int, int, int]:
        """Parse color string to RGBA tuple"""
        if color_str.startswith("#"):
            # Hex color
            color_str = color_str[1:]
            if len(color_str) == 6:
                r = int(color_str[0:2], 16)
                g = int(color_str[2:4], 16)
                b = int(color_str[4:6], 16)
                return (r, g, b, 255)
            if len(color_str) == 8:
                r = int(color_str[0:2], 16)
                g = int(color_str[2:4], 16)
                b = int(color_str[4:6], 16)
                a = int(color_str[6:8], 16)
                return (r, g, b, a)
        return (0, 0, 0, 0)  # Default transparent

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        logger.info(f"after_value_set called for parameter: {parameter.name} = {value}")

        # Delegate tethering logic to helper
        self._crop_tethering.on_after_value_set(parameter, value)

        # Also check for metadata changes proactively (in case GUI updated metadata)
        # But only if we're not in execution mode
        if parameter.name == "input_image" and not (hasattr(self, "_processing") and self._processing):
            logger.debug("Checking for metadata changes proactively")
            self._crop_tethering.check_and_sync_metadata()

        # Only do live cropping for crop parameters if we're not in execution mode
        if parameter.name in ["left", "top", "width", "height", "zoom", "rotate"] and not (
            hasattr(self, "_processing") and self._processing
        ):
            logger.info("Doing live crop preview")
            self._crop()

        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = []

        if not self.get_parameter_value("input_image"):
            msg = f"{self.name} - Input image is required"
            exceptions.append(Exception(msg))

        return exceptions

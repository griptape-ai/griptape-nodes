import re
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.traits.color_picker import ColorPicker
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor
from griptape_nodes_library.utils.color_utils import parse_color_to_rgba


class AddBoundingBoxes(BaseImageProcessor):
    """Node to draw bounding boxes on images from coordinate dictionaries."""

    # Label font size as percentage of image height
    LABEL_HEIGHT_PERCENT = 0.04  # % of image height

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters for bounding box drawing."""
        # Bounding boxes input parameter (dict or list of dicts)
        self.add_parameter(
            Parameter(
                name="bounding_boxes",
                input_types=["dict", "list"],
                type="dict",
                tooltip="Single bounding box dict or list of bounding box dicts. Each must have x, y, width, height as integers.",
                ui_options={"hide_property": True},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Box color parameter with color picker
        self.add_parameter(
            Parameter(
                name="box_color",
                type="str",
                default_value="#FF0000",
                tooltip="Color of the bounding box (hex format)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={ColorPicker(format="hex")},
            )
        )

        # Line thickness parameter
        self.add_parameter(
            ParameterInt(
                name="line_thickness",
                default_value=2,
                min_val=1,
                max_val=10,
                slider=True,
                tooltip="Thickness of the bounding box lines in pixels",
                allow_output=False
            )
        )

        # Show labels parameter
        self.add_parameter(
            Parameter(
                name="show_labels",
                type="bool",
                default_value=True,
                tooltip="Show labels on the bounding boxes",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Label key parameter with dropdown options
        label_param = Parameter(
            name="label_key",
            type="str",
            default_value="{x}, {y}, width: {width}, height: {height}",
            tooltip="Template for bounding box labels. Use {key} to insert values from the bounding box dict (e.g., {x}, {confidence}).",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(label_param)

    def _get_processing_description(self) -> str:
        """Get a description of what this processor does."""
        return "Adding bounding boxes to image"

    def _validate_image_input(self) -> list[Exception] | None:
        """Override to make image input optional - don't validate if not connected."""
        return None

    def validate_before_node_run(self) -> list[Exception] | None:
        """Override to skip image validation entirely."""
        exceptions = []

        # Only validate custom parameters (bounding boxes), not image
        custom_exceptions = self._validate_custom_parameters()
        if custom_exceptions:
            exceptions.extend(custom_exceptions)

        # If there are validation errors, set the status to failure
        if exceptions:
            error_messages = [str(e) for e in exceptions]
            error_details = f"Validation failed: {'; '.join(error_messages)}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")

        return exceptions if exceptions else None

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate bounding box parameters."""
        exceptions = []

        bounding_boxes = self.get_parameter_value("bounding_boxes")

        if bounding_boxes is None:
            msg = f"{self.name}: Bounding boxes parameter is required"
            exceptions.append(ValueError(msg))
            return exceptions

        # Normalize to list for validation
        boxes_list = []
        if isinstance(bounding_boxes, dict):
            boxes_list = [bounding_boxes]
        elif isinstance(bounding_boxes, list):
            boxes_list = bounding_boxes
        else:
            msg = f"{self.name}: Bounding boxes must be a dict or list of dicts. Example: {{'x': 10, 'y': 20, 'width': 100, 'height': 150}}"
            exceptions.append(ValueError(msg))
            return exceptions

        # Validate each bounding box
        required_keys = {"x", "y", "width", "height"}
        for idx, box in enumerate(boxes_list):
            if not isinstance(box, dict):
                msg = f"{self.name}: Bounding box at index {idx} must be a dict, got {type(box).__name__}"
                exceptions.append(ValueError(msg))
                continue

            # Check for required keys
            missing_keys = required_keys - box.keys()
            if missing_keys:
                msg = f"{self.name}: Bounding box at index {idx} missing required keys: {missing_keys}. Required keys: x, y, width, height (all must be integers or convertible strings)"
                exceptions.append(ValueError(msg))
                continue

            # Validate key values are integers or convertible strings
            for key in required_keys:
                value = box.get(key)

                # If it's already an int, it's valid
                if isinstance(value, int):
                    continue

                # If it's a string, try to convert it
                if isinstance(value, str):
                    try:
                        converted_value = int(value)
                        # Store the converted value back in the dict
                        box[key] = converted_value
                    except (ValueError, TypeError):
                        msg = f"{self.name}: Bounding box at index {idx} has invalid '{key}' value: '{value}'. Cannot convert string to integer. All coordinate values must be integers or convertible strings."
                        exceptions.append(ValueError(msg))
                else:
                    msg = f"{self.name}: Bounding box at index {idx} has invalid '{key}' value. Expected int or string, got {type(value).__name__}. All coordinate values must be integers or convertible strings."
                    exceptions.append(ValueError(msg))

            # Validate values are non-negative and width/height are positive
            # At this point, values should be integers (either originally or converted)
            x = box.get("x")
            y = box.get("y")
            width = box.get("width")
            height = box.get("height")

            if isinstance(x, int) and x < 0:
                msg = f"{self.name}: Bounding box at index {idx} has negative x value: {x}. x must be >= 0"
                exceptions.append(ValueError(msg))

            if isinstance(y, int) and y < 0:
                msg = f"{self.name}: Bounding box at index {idx} has negative y value: {y}. y must be >= 0"
                exceptions.append(ValueError(msg))

            if isinstance(width, int) and width <= 0:
                msg = f"{self.name}: Bounding box at index {idx} has non-positive width value: {width}. width must be > 0"
                exceptions.append(ValueError(msg))

            if isinstance(height, int) and height <= 0:
                msg = f"{self.name}: Bounding box at index {idx} has non-positive height value: {height}. height must be > 0"
                exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_image_input_data_safe(self) -> tuple[Image.Image, str] | None:
        """Safely get PIL image and detected format, returning None if not available."""
        from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact, load_pil_from_url

        image = self.parameter_values.get("input_image")

        if not image:
            return None

        # Convert to ImageUrlArtifact if needed
        if hasattr(image, "to_dict"):
            image = dict_to_image_url_artifact(image.to_dict())
        elif isinstance(image, dict):
            image = dict_to_image_url_artifact(image)

        # Ensure we have a valid image artifact with a value
        if not hasattr(image, "value") or not image.value:
            return None

        try:
            # Load PIL image using existing utility
            pil_image = load_pil_from_url(image.value)

            # Detect format
            detected_format = self._detect_image_format(pil_image)

            return pil_image, detected_format
        except Exception:
            return None

    def process(self) -> AsyncResult[None]:
        """Override process to make image input optional."""
        from griptape_nodes.retained_mode.griptape_nodes import logger

        # Reset execution state and result details at the start of each run
        self._clear_execution_status()

        # Clear output values to prevent downstream nodes from getting stale data on errors
        self.parameter_output_values["output"] = None

        # Try to get image input data safely
        image_data = self._get_image_input_data_safe()

        # If no image provided, this is acceptable for this node
        if image_data is None:
            error_details = "No input image provided - image input is required"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.warning(f"{self.__class__.__name__} '{self.name}': {error_details}")
            return

        try:
            pil_image, detected_format = image_data
            self._log_format_detection(detected_format)
            self._log_image_properties(pil_image)

            # Get custom parameters from subclasses
            custom_params = self._get_custom_parameters()

            # Initialize logs
            self.append_value_to_parameter("logs", f"[Processing {self._get_processing_description()}..]\n")

            # Run the image processing
            self.append_value_to_parameter("logs", "[Started image processing..]\n")
            yield lambda: self._process(pil_image, detected_format, **custom_params)
            self.append_value_to_parameter("logs", "[Finished image processing.]\n")

            # Success case
            success_details = f"Successfully processed image: {self._get_processing_description()} ({pil_image.width}x{pil_image.height})"
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
            logger.info(f"{self.__class__.__name__} '{self.name}': {success_details}")

        except Exception as e:
            error_details = f"Failed to process image: {e}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"{self.__class__.__name__} '{self.name}': {error_details}")
            self._handle_failure_exception(e)

    def _process_image(self, pil_image: Image.Image, **kwargs) -> Image.Image:
        """Process the image by drawing bounding boxes."""
        bounding_boxes = kwargs.get("bounding_boxes")
        box_color = kwargs.get("box_color", "#FF0000")
        line_thickness = kwargs.get("line_thickness", 2)
        show_labels = kwargs.get("show_labels", True)
        label_key = kwargs.get("label_key", "none")

        # Validate bounding_boxes is not None
        if bounding_boxes is None:
            msg = f"{self.name}: Bounding boxes parameter is required"
            raise ValueError(msg)

        # Parse color to RGBA tuple
        try:
            color_rgba = parse_color_to_rgba(box_color)
            # Use RGB only for drawing
            color_rgb = color_rgba[:3]
        except Exception as e:
            msg = f"{self.name}: Failed to parse box color '{box_color}': {e}"
            raise ValueError(msg) from e

        # Normalize bounding_boxes to list
        boxes_list = [bounding_boxes] if isinstance(bounding_boxes, dict) else bounding_boxes

        # Create a copy of the image to draw on
        image_copy = pil_image.copy()
        draw = ImageDraw.Draw(image_copy)

        # Calculate font size based on image height and load font
        font_size = int(pil_image.height * self.LABEL_HEIGHT_PERCENT)
        try:
            font = ImageFont.load_default(size=font_size)
        except Exception:
            # Fallback to default font if size parameter fails
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None

        # Draw each bounding box
        for box in boxes_list:
            x = box["x"]
            y = box["y"]
            width = box["width"]
            height = box["height"]

            # Calculate rectangle coordinates
            x1, y1 = x, y
            x2, y2 = x + width, y + height

            # Draw rectangle
            draw.rectangle(
                [(x1, y1), (x2, y2)],
                outline=color_rgb,
                width=line_thickness,
            )

            # Draw label if specified and show_labels is enabled
            if show_labels and label_key and label_key != "none" and label_key.strip():
                # Process template string by replacing {key} patterns with values
                label_value = label_key

                # Find all {key} patterns and replace with values from box
                pattern = r"\{(\w+)\}"
                matches = re.findall(pattern, label_key)

                for key in matches:
                    if key in box:
                        # Replace {key} with the actual value
                        label_value = label_value.replace(f"{{{key}}}", str(box[key]))
                    else:
                        # If key doesn't exist, leave the {key} as is
                        pass

                # Only draw if we have a label value after substitution
                if (label_value and label_value != label_key) or not matches:
                    # Calculate text dimensions to position it properly
                    if font:
                        try:
                            # Get text bbox at origin to measure dimensions
                            temp_bbox = draw.textbbox((0, 0), label_value, font=font)
                            text_height = temp_bbox[3] - temp_bbox[1]  # y1 - y0

                            # Position label so its bottom edge is clear of the bounding box top
                            # Add padding equal to half the text height between label bottom and box top
                            label_x = x1
                            gap = text_height // 2
                            label_y = y1 - text_height - gap

                            # If label would go off top of image, position it inside the box at the top
                            if label_y < 0:
                                label_y = y1 + gap  # Position inside box, with half-height gap below top edge

                            # Draw text background for better visibility
                            label_bbox = draw.textbbox((label_x, label_y), label_value, font=font)
                            draw.rectangle(label_bbox, fill=(0, 0, 0, 180))

                            # Draw text label
                            draw.text(
                                (label_x, label_y),
                                label_value,
                                fill=(255, 255, 255),
                                font=font,
                            )
                        except Exception as e:
                            # Log warning but continue - text rendering is optional
                            self.append_value_to_parameter("logs", f"Warning: Could not draw text label: {e}\n")
                    else:
                        # No font available, skip label
                        self.append_value_to_parameter("logs", "Warning: Font not available for label rendering\n")

        return image_copy

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for processing."""
        return {
            "bounding_boxes": self.get_parameter_value("bounding_boxes"),
            "box_color": self.get_parameter_value("box_color") or "#FF0000",
            "line_thickness": self.get_parameter_value("line_thickness") or 2,
            "show_labels": self.get_parameter_value("show_labels") if self.get_parameter_value("show_labels") is not None else True,
            "label_key": self.get_parameter_value("label_key") or "none",
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get the output filename suffix."""
        num_boxes = 1
        bounding_boxes = kwargs.get("bounding_boxes")
        if isinstance(bounding_boxes, list):
            num_boxes = len(bounding_boxes)
        return f"_bboxes_{num_boxes}"


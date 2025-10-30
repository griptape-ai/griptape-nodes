from io import BytesIO
from typing import Any

from griptape.artifacts import ImageUrlArtifact, UrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.utils.image_utils import load_pil_from_url


class ImagesToPdf(ControlNode):
    """Convert multiple images to a single multi-page PDF file.

    Takes a list of ImageUrlArtifact objects and combines them into a single PDF,
    with each image as a separate page. Images are automatically converted to RGB
    mode as required by PDF format.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Input parameter for list of images
        self.images = ParameterList(
            name="images",
            input_types=[
                "ImageArtifact",
                "ImageUrlArtifact",
                "str",
                "list",
                "list[ImageArtifact]",
                "list[ImageUrlArtifact]",
            ],
            default_value=[],
            tooltip="List of images to convert to PDF",
            allowed_modes={ParameterMode.INPUT},
            ui_options={"expander": True, "display_name": "Images"},
        )
        self.add_parameter(self.images)

        # Filename parameter
        self.filename_param = Parameter(
            name="filename",
            type="str",
            default_value="output.pdf",
            tooltip="Output filename for the PDF file",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.filename_param)

        # Output parameter showing final path
        self.output = Parameter(
            name="output",
            type="UrlArtifact",
            default_value=None,
            tooltip="Final path where PDF was saved",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate that images list is not empty."""
        exceptions: list[Exception] = []

        images = self.get_parameter_list_value("images") or []
        if not images:
            msg = f"{self.name}: Images parameter is required and cannot be empty"
            exceptions.append(ValueError(msg))

        filename = self.get_parameter_value("filename")
        if not filename:
            msg = f"{self.name}: Filename parameter is required"
            exceptions.append(ValueError(msg))

        if not str(filename).lower().endswith(".pdf"):
            msg = f"{self.name}: Filename must end with .pdf extension"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def process(self) -> None:
        """Convert list of images to a multi-page PDF file."""
        images = self.get_parameter_list_value("images") or []
        filename = self.get_parameter_value("filename")

        logger.info(f"{self.name}: Converting {len(images)} images to PDF")

        # Load all images and convert to RGB
        pil_images = []
        for idx, image_artifact in enumerate(images):
            if not isinstance(image_artifact, ImageUrlArtifact):
                msg = f"{self.name}: Item {idx} is not an ImageUrlArtifact"
                raise TypeError(msg)

            pil_image = load_pil_from_url(image_artifact.value)

            # Convert to RGB (PDF doesn't support RGBA)
            if pil_image.mode == "RGBA":
                # Create white background for transparent images
                rgb_image = Image.new("RGB", pil_image.size, (255, 255, 255))
                rgb_image.paste(pil_image, mask=pil_image.split()[3])
                pil_images.append(rgb_image)
            elif pil_image.mode != "RGB":
                pil_images.append(pil_image.convert("RGB"))
            else:
                pil_images.append(pil_image)

        if not pil_images:
            msg = f"{self.name}: No valid images to convert"
            raise ValueError(msg)

        # Create PDF in memory
        pdf_buffer = BytesIO()
        if len(pil_images) == 1:
            # Single image PDF
            pil_images[0].save(pdf_buffer, format="PDF")
        else:
            # Multi-page PDF
            first_image = pil_images[0]
            rest_images = pil_images[1:]
            first_image.save(
                pdf_buffer,
                format="PDF",
                save_all=True,
                append_images=rest_images,
            )

        pdf_bytes = pdf_buffer.getvalue()
        pdf_buffer.close()

        # Save to static files
        static_url = GriptapeNodes.StaticFilesManager().save_static_file(
            pdf_bytes,
            filename,
        )
        logger.debug(f"{self.name}: PDF saved to static files as {static_url}")

        # Set output
        self.parameter_output_values["output"] = UrlArtifact(static_url)

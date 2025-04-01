import pytest
from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver
from griptape_nodes_library.drivers.griptape_cloud_image_driver import GriptapeCloudImageDriverNode


class TestGriptapeCloudImageGenerationNode:
    def test___init__(self) -> None:
        griptape_cloud_image_generation_node = GriptapeCloudImageDriverNode(name="Griptape Cloud Image Generation")

        parameters = [
            {
                "name": parameter.name,
                "allowed_types": parameter.allowed_types,
                "default_value": parameter.default_value,
                "tooltip": parameter.tooltip,
            }
            for parameter in griptape_cloud_image_generation_node.parameters
        ]

        assert parameters == [
            {
                "allowed_types": [
                    "BaseImageGenerationDriver",
                ],
                "default_value": None,
                "name": "driver",
                "tooltip": "",
            },
            {
                "allowed_types": [
                    "str",
                ],
                "default_value": "",
                "name": "quality",
                "tooltip": "",
            },
            {
                "allowed_types": [
                    "str",
                ],
                "default_value": "",
                "name": "style",
                "tooltip": "",
            },
            {
                "name": "image_generation_model",
                "allowed_types": ["str"],
                "default_value": "dall-e-3",
                "tooltip": "Select the model for image generation.",
            },
            {
                "name": "image_deployment_name",
                "allowed_types": ["str"],
                "default_value": "dall-e-3",
                "tooltip": "Enter the deployment name for the image generation model.",
            },
            {
                "name": "size",
                "allowed_types": ["str"],
                "default_value": "1024x1024",
                "tooltip": "Select the size of the generated image.",
            },
        ]

    @pytest.mark.parametrize(
        ("model", "size", "expected_size"),
        [
            ("dall-e-3", "256x256", "1024x1024"),
            ("dall-e-3", "1024x1024", "1024x1024"),
        ],
    )
    def test_adjust_size_based_on_model(self, model, size, expected_size) -> None:
        griptape_cloud_image_generation_node = GriptapeCloudImageDriverNode(name="Griptape Cloud Image Generation")

        adjusted_size = griptape_cloud_image_generation_node.adjust_size_based_on_model(model, size)

        assert adjusted_size == expected_size

    def test_process(self) -> None:
        griptape_cloud_image_generation_node = GriptapeCloudImageDriverNode(name="Griptape Cloud Image Generation")

        griptape_cloud_image_generation_node.process()

        driver = griptape_cloud_image_generation_node.parameter_output_values["driver"]

        assert isinstance(driver, GriptapeCloudImageGenerationDriver)
        assert driver.model == "dall-e-3"
        assert driver.api_key == griptape_cloud_image_generation_node.get_config_value(
            service="Griptape", value="GT_CLOUD_API_KEY"
        )
        assert driver.image_size == "1024x1024"

import pytest
from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver
from griptape_nodes_library.drivers.image.griptape_cloud_image_driver import GriptapeCloudImage


class TestGriptapeCloudImageGenerationNode:
    def test___init__(self) -> None:
        griptape_cloud_image_generation_node = GriptapeCloudImage(name="Griptape Cloud Image Generation")

        parameters = [
            {
                "name": parameter.name,
                "input_types": parameter.input_types,
                "output_type": parameter.output_type,
                "type": parameter.type,
                "default_value": parameter.default_value,
                "tooltip": parameter.tooltip,
            }
            for parameter in griptape_cloud_image_generation_node.parameters
        ]

        assert parameters == [
            {
                "name": "model",
                "input_types": ["str"],
                "output_type": "str",
                "type": "str",
                "default_value": "dall-e-3",
                "tooltip": "Choose a model",
            },
            {
                "name": "quality",
                "input_types": ["str"],
                "output_type": "str",
                "type": "str",
                "default_value": "standard",
                "tooltip": "Image Quality",
            },
            {
                "name": "style",
                "input_types": ["str"],
                "output_type": "str",
                "type": "str",
                "default_value": "natural",
                "tooltip": "Image Style",
            },
            {
                "name": "size",
                "input_types": ["str"],
                "output_type": "str",
                "type": "str",
                "default_value": "1024x1024",
                "tooltip": "Image Size",
            },
            {
                "input_types": [
                    "Image Generation Driver",
                ],
                "output_type": "Image Generation Driver",
                "type": "Image Generation Driver",
                "default_value": None,
                "name": "image_generation_driver",
                "tooltip": "",
            },
        ]

    @pytest.mark.parametrize(
        ("model", "size"),
        [
            ("dall-e-3", "1024x1024"),
            ("dall-e-3", "1792x1024"),
            ("dall-e-2", "512x512"),
        ],
    )
    def test_model_size_configuration(self, model, size) -> None:
        """Test that the size parameter respects model constraints."""
        griptape_cloud_image_generation_node = GriptapeCloudImage(name="Griptape Cloud Image Generation")

        # Set model and size parameters
        griptape_cloud_image_generation_node.set_parameter_value("model", model)
        griptape_cloud_image_generation_node.set_parameter_value("size", size)

        # Process to create the driver
        griptape_cloud_image_generation_node.process()

        # Get the created driver
        driver = griptape_cloud_image_generation_node.parameter_output_values["image_generation_driver"]

        # Verify the driver has the correct size parameter
        assert driver.image_size == size

        # Verify model is set correctly
        assert driver.model == model

    def test_process(self) -> None:
        griptape_cloud_image_generation_node = GriptapeCloudImage(name="Griptape Cloud Image Generation")

        griptape_cloud_image_generation_node.process()

        driver = griptape_cloud_image_generation_node.parameter_output_values["image_generation_driver"]

        assert isinstance(driver, GriptapeCloudImageGenerationDriver)
        assert driver.model == "dall-e-3"
        assert driver.api_key == griptape_cloud_image_generation_node.get_config_value(
            service="Griptape", value="GT_CLOUD_API_KEY"
        )
        assert driver.image_size == "1024x1024"

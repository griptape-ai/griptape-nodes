from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver
from griptape_nodes_library.config.image.griptape_cloud_image_driver import GriptapeCloudImage


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
                "input_types": ["Image Generation Driver"],
                "output_type": "Image Generation Driver",
                "type": "Image Generation Driver",
                "default_value": None,
                "name": "image_model_config",
                "tooltip": "",
            },
            {
                "input_types": ["str"],
                "output_type": "str",
                "type": "str",
                "default_value": "⚠️ This node requires an API key to function.",
                "name": "message",
                "tooltip": "",
            },
            {
                "input_types": ["str"],
                "output_type": "str",
                "type": "str",
                "default_value": "dall-e-3",
                "name": "model",
                "tooltip": "Select the model you want to use from the available options.",
            },
            {
                "input_types": ["str"],
                "output_type": "str",
                "type": "str",
                "default_value": "1024x1024",
                "name": "image_size",
                "tooltip": "Select the size of the generated image.",
            },
            {
                "input_types": ["str"],
                "output_type": "str",
                "type": "str",
                "default_value": "vivid",
                "name": "style",
                "tooltip": "Select the style for image generation.",
            },
            {
                "input_types": ["str"],
                "output_type": "str",
                "type": "str",
                "default_value": "hd",
                "name": "quality",
                "tooltip": "Select the quality for image generation.",
            },
        ]

    def test_process(self) -> None:
        griptape_cloud_image_generation_node = GriptapeCloudImage(name="Griptape Cloud Image Generation")

        griptape_cloud_image_generation_node.process()

        driver = griptape_cloud_image_generation_node.parameter_output_values["image_model_config"]

        assert isinstance(driver, GriptapeCloudImageGenerationDriver)
        assert driver.model == "dall-e-3"
        assert driver.api_key == griptape_cloud_image_generation_node.get_config_value(
            service="Griptape", value="GT_CLOUD_API_KEY"
        )
        assert driver.image_size == "1024x1024"

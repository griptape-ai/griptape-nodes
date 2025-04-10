from griptape.drivers.embedding.dummy import DummyEmbeddingDriver

from griptape_nodes_library.drivers.base_driver import BaseDriver


class BaseEmbeddingDriver(BaseDriver):
    """Node for Base Embedding Driver.

    This node creates a basic embedding driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Override the allowed types for the driver parameter
        driver_parameter = self.get_parameter_by_name("driver")
        if driver_parameter is not None:
            driver_parameter.name = "embedding_driver"
            driver_parameter.output_type = "EmbeddingDriver"

    def process(self) -> None:
        # Get the parameters from the node

        # In the base implementation, we just create a dummy driver
        # Derived classes would implement specific embedding drivers
        driver = DummyEmbeddingDriver()

        # Set the output
        self.parameter_output_values["embedding_driver"] = driver

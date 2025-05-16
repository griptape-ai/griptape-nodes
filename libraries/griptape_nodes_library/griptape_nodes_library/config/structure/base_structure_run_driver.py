from griptape_nodes_library.config.base_driver import BaseDriver


class BaseStructureRunDriver(BaseDriver):
    """Base driver node for creating Structure Run Drivers.

    Attributes:
        driver (dict): A dictionary representation of the created tool.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self._replace_param_by_name(
            param_name="driver",
            new_param_name="structure_run_config",
            new_output_type="Structure Run Driver",
            tooltip="Connect to a Structure Run Tool",
        )

from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.engines import CsvExtractionEngine, JsonExtractionEngine
from griptape.rules import Rule
from griptape.tools import ExtractionTool as GtExtractionTool

from griptape_nodes_library.tools.base_tool import BaseTool

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class StructuredDataExtractor(BaseTool):
    def process(self) -> None:
        prompt_driver = self.parameter_values.get("prompt_driver", None)
        extraction_type = self.parameter_values.get("extraction_type", "json")
        column_names_string = self.parameter_values.get("column_names", "")
        column_names = (
            [column_name.strip() for column_name in column_names_string.split(",")] if column_names_string else []
        )
        template_schema = self.parameter_values.get("template_schema", "")

        # Set default prompt driver if none provided
        if not prompt_driver:
            prompt_driver = GriptapeCloudPromptDriver(model="gpt-4o")

        # Create the appropriate extraction engine based on type
        engine = None
        if extraction_type == "csv":
            engine = CsvExtractionEngine(prompt_driver=prompt_driver, column_names=column_names)
        elif extraction_type == "json":
            engine = JsonExtractionEngine(prompt_driver=prompt_driver, template_schema=template_schema)

        # Create the tool with parameters
        params: dict = {"extraction_engine": engine}
        tool = GtExtractionTool(**params, rules=[Rule("Raw output please")])

        # Set the output
        self.parameter_output_values["tool"] = tool

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = []
        if self.parameter_values.get("prompt_driver", None):
            return exceptions
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        return exceptions if exceptions else None

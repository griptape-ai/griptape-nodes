from griptape.drivers.prompt.openai import OpenAiChatPromptDriver
from griptape.engines import CsvExtractionEngine, JsonExtractionEngine
from griptape.rules import Rule
from griptape.tools import ExtractionTool
import openai

from griptape_nodes_library.tools.base_tool import gnBaseTool

API_KEY_ENV_VAR = "OPENAI_API_KEY"
SERVICE = "OpenAI"

class gnExtractionTool(gnBaseTool):
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
            prompt_driver = OpenAiChatPromptDriver(model="gpt-4o-mini")

        # Create the appropriate extraction engine based on type
        engine = None
        if extraction_type == "csv":
            engine = CsvExtractionEngine(prompt_driver=prompt_driver, column_names=column_names)
        elif extraction_type == "json":
            engine = JsonExtractionEngine(prompt_driver=prompt_driver, template_schema=template_schema)

        # Create the tool with parameters
        params: dict = {"extraction_engine": engine}
        tool = ExtractionTool(**params, rules=[Rule("Raw output please")])

        # Set the output
        self.parameter_output_values["tool"] = tool

    def validate_node(self) -> list[Exception] | None:
        exceptions = []
        if self.parameter_values.get("prompt_driver",None):
            return exceptions
        api_key = self.getenv(SERVICE,API_KEY_ENV_VAR)
        if not api_key:
            msg=f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        try:
            client = openai.OpenAI(api_key=api_key)
            client.models.list()
        except openai.AuthenticationError as e:
            exceptions.append(e)
        return exceptions if exceptions else None

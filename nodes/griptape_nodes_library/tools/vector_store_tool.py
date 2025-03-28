import ast
import json
import logging

from griptape.drivers.vector.dummy import DummyVectorStoreDriver
from griptape.tools import VectorStoreTool

from griptape_nodes_library.tools.tools import BaseToolNode

logger = logging.getLogger(__name__)


class VectorStoreToolNode(BaseToolNode):
    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)
        query_params = self.parameter_values.get("optional_query_params", "{}")
        description = self.parameter_values.get("description", "This DB has information about...")
        vector_store_driver = self.parameter_values.get("vector_store_driver", DummyVectorStoreDriver())

        # Create parameters dictionary
        params = {"off_prompt": off_prompt}

        if query_params and query_params.strip() != "{}":
            params["query_params"] = self.string_to_dict(query_params)

        if description:
            params["description"] = description

        if vector_store_driver:
            params["vector_store_driver"] = vector_store_driver

        # Create the tool
        tool = VectorStoreTool(**params)

        # Set the output
        self.parameter_output_values["tool"] = tool

    def string_to_dict(self, s) -> dict:
        s = s.strip()

        # Try JSON format first
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass

        # Try literal eval (for dict-like strings)
        try:
            return ast.literal_eval(s)
        except (ValueError, SyntaxError):
            pass

        # Try key-value pair format
        try:
            return {
                str.strip(item.split(":", 1)[0]): str.strip(item.split(":", 1)[1])
                for item in s.split("\n")
                if ":" in item
            }
        except Exception:
            logger.exception("Failed to convert string to dict: %s", s)

        # If all else fails, return an empty dict
        return {}

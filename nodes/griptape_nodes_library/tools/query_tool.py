from __future__ import annotations

from attrs import define
from griptape.artifacts import ErrorArtifact, ListArtifact, TextArtifact
from griptape.drivers.prompt.google import GooglePromptDriver
from griptape.engines.rag.rag_context import RagContext
from griptape.tools import QueryTool
from griptape.utils.decorators import activity
from schema import Literal, Schema

from griptape_nodes_library.tools.tools import gnBaseTool


@define(kw_only=True)
class GeminiQueryTool(QueryTool):
    @activity(
        config={
            "description": "Can be used to search through textual content.",
            "schema": Schema(
                {
                    Literal("query", description="A natural language search query"): str,
                    Literal("content"): Schema(
                        {
                            "memory_name": str,
                            "artifact_namespace": str,
                        }
                    ),
                }
            ),
        },
    )
    def query(self, params: dict) -> ListArtifact | ErrorArtifact:
        query = params["values"]["query"]
        content = params["values"]["content"]

        if isinstance(content, str):
            text_artifacts = [TextArtifact(content)]
        else:
            memory = self.find_input_memory(content["memory_name"])
            artifact_namespace = content["artifact_namespace"]

            if memory is not None:
                artifacts = memory.load_artifacts(artifact_namespace)
            else:
                return ErrorArtifact("memory not found")

            text_artifacts = [artifact for artifact in artifacts if isinstance(artifact, TextArtifact)]

        outputs = self._rag_engine.process(RagContext(query=query, text_chunks=text_artifacts)).outputs

        if len(outputs) > 0:
            return ListArtifact(outputs)
        return ErrorArtifact("query output is empty")


class gnQueryTool(gnBaseTool):
    """A tool generator class that creates an query tool based on the provided prompt driver.

    Create either a specialized GeminiQueryTool when using a Google prompt driver, or a
    standard QueryTool for other driver types.
    """

    def process(self) -> None:
        """A GeminiQueryTool is created when using GooglePromptDriver, otherwise a standard QueryTool is created with the provided prompt driver."""
        # Get the prompt driver from parameters, will be None if not provided
        prompt_driver = self.parameter_values.get("prompt_driver", None)

        # Initialize empty parameters dictionary
        params = {}

        # Add prompt_driver to params if it exists
        if prompt_driver:
            params["prompt_driver"] = prompt_driver

        # Create the appropriate tool based on driver type
        if isinstance(prompt_driver, GooglePromptDriver):
            # For Google's Gemini models, use the specialized GeminiQueryTool
            tool = GeminiQueryTool()
        else:
            # For all other driver types, use the standard QueryTool with the given parameters
            tool = QueryTool(**params)

        # Store the tool as a dictionary in the output parameters for later use
        self.parameter_output_values["tool"] = tool

import logging

import diffusers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter

logger = logging.getLogger("diffusers_nodes_library")


class StableDiffusionAttendAndExcitePipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node)
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "stabilityai/stable-diffusion-2-1",
                "stabilityai/stable-diffusion-2",
                "CompVis/stable-diffusion-v1-4",
                "CompVis/stable-diffusion-v1-3",
                "CompVis/stable-diffusion-v1-2",
                "CompVis/stable-diffusion-v1-1",
            ],
            list_all_models=list_all_models,
        )

    def _add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                type="str",
                tooltip="The prompt to guide image generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="words_to_emphasize",
                default_value="",
                type="str",
                tooltip="Words to emphasize (whitespace separated). Token indices will be automatically detected.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                type="str",
                tooltip="The prompt to not guide the image generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=7.5,
                type="float",
                tooltip="Guidance scale for generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="max_iter_to_alter",
                default_value=25,
                type="int",
                tooltip="Number of denoising steps to apply attend-and-excite",
            )
        )

    def _remove_input_parameters(self) -> None:
        self._huggingface_repo_parameter.remove_input_parameters()
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("words_to_emphasize")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("guidance_scale")
        self._node.remove_parameter_element_by_name("max_iter_to_alter")

    def _get_pipe_kwargs(self) -> dict:
        # Get token indices by computing them from the pipeline
        token_indices = self._get_token_indices()

        return {
            "prompt": self._node.get_parameter_value("prompt"),
            "token_indices": token_indices,
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "guidance_scale": float(self._node.get_parameter_value("guidance_scale")),
            "max_iter_to_alter": int(self._node.get_parameter_value("max_iter_to_alter")),
        }

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        repo_errors = self._huggingface_repo_parameter.validate_before_node_run()
        if repo_errors:
            errors.extend(repo_errors)

        words_to_emphasize = self._node.get_parameter_value("words_to_emphasize")
        if not words_to_emphasize.strip():
            errors.append(
                ValueError("Parameter 'words_to_emphasize' cannot be empty. Please provide words to emphasize.")
            )
        return errors if errors else None

    def preprocess(self) -> None:
        super().preprocess()

    def get_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def _get_token_indices(self) -> list[int]:
        """Get token indices by computing them from words_to_emphasize.

        Note: This method assumes the pipeline is available when called.
        In the runtime context, token indices computation will need to be
        handled by the calling pipeline code.
        """
        words_to_emphasize = self._node.get_parameter_value("words_to_emphasize")

        if not words_to_emphasize.strip():
            return []

        # Return empty list for now - the actual computation will be done
        # in the pipeline code where the diffusers pipeline is available
        return []

    def compute_token_indices(self, pipe: diffusers.StableDiffusionAttendAndExcitePipeline) -> list[int]:
        """Compute token indices using the provided pipeline.

        This method should be called by the pipeline code to get the actual token indices.
        """
        words_to_emphasize = self._node.get_parameter_value("words_to_emphasize")

        if not words_to_emphasize.strip():
            return []

        prompt = self._node.get_parameter_value("prompt")
        words = words_to_emphasize.strip().split()

        if not words or not prompt:
            return []

        # Get token indices from the pipeline
        token_map = pipe.get_indices(prompt)

        token_indices = []
        for word in words:
            # Find tokens that start with the word (case-insensitive)
            for idx, token in token_map.items():
                # Remove tokenizer artifacts like </w> and <|...
                clean_token = token.replace("</w>", "").replace("<|", "").replace("|>", "").lower()
                if clean_token.startswith(word.lower()) and idx not in token_indices:
                    token_indices.append(idx)

        return token_indices

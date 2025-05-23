import logging
from functools import cache
from typing import Any, ClassVar

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.torch_utils import (  # type: ignore[reportMissingImports]
    get_best_device,
    print_pipeline_memory_footprint,
)
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


def print_sd3_pipeline_memory_footprint(pipe: diffusers.StableDiffusion3Pipeline) -> None:
    """Print SD3 pipeline memory footprint."""
    print_pipeline_memory_footprint(
        pipe,
        [
            "vae",
            "text_encoder",
            "text_encoder_2",
            "text_encoder_3",
            "transformer",
        ],
    )


@cache
def optimize_sd3_pipeline_memory_footprint(pipe: diffusers.StableDiffusion3Pipeline) -> None:
    """Optimize SD3 pipeline memory footprint following official patterns."""
    device = get_best_device()

    if device == torch.device("cuda"):
        # For GPUs: Use model CPU offloading to save VRAM
        # Don't call pipe.to(device) as it would load everything to GPU
        logger.info("Enabling model CPU offload for SD3.5")
        pipe.enable_model_cpu_offload()
    elif device == torch.device("mps"):
        # For MPS: Move pipeline to device
        logger.info("Transferring SD3.5 pipeline to MPS - may take minutes")
        pipe.to(device)
    else:
        # For CPU: Move pipeline to device
        logger.info("Using CPU for SD3.5 pipeline")
        pipe.to(device)

    # Enable attention slicing for memory optimization
    logger.info("Enabling attention slicing for SD3.5")
    pipe.enable_attention_slicing()

    # Enable VAE slicing for memory optimization
    if hasattr(pipe, "enable_vae_slicing"):
        logger.info("Enabling VAE slicing for SD3.5")
        pipe.enable_vae_slicing()
    elif hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_slicing"):
        logger.info("Enabling VAE slicing for SD3.5")
        pipe.vae.enable_slicing()

    logger.info("Final SD3 memory footprint:")
    print_sd3_pipeline_memory_footprint(pipe)


class SD3ModelManager:
    """Manages Stable Diffusion 3 model loading, caching, and validation."""

    # Model repository mappings
    MODEL_REPOS: ClassVar[dict[str, str]] = {
        "large": "stabilityai/stable-diffusion-3.5-large",
        "medium": "stabilityai/stable-diffusion-3.5-medium",
    }

    # Pipeline cache
    _pipeline_cache: ClassVar[dict[str, Any]] = {}

    def __init__(self, node: BaseNode):
        self._node = node

    def add_model_parameter(self) -> None:
        """Add model selection parameter using HuggingFaceRepoParameter."""
        self._repo_param = HuggingFaceRepoParameter(
            node=self._node, repo_ids=list(self.MODEL_REPOS.values()), parameter_name="model"
        )
        self._repo_param.add_input_parameters()

    def get_pipeline(self) -> diffusers.StableDiffusion3Pipeline:
        """Get or load the SD3.5 pipeline with caching and optimization."""
        repo_id, revision = self._repo_param.get_repo_revision()
        cache_key = f"sd35_{repo_id}_{revision}"

        # Check cache first
        if cache_key in self._pipeline_cache:
            logger.info("Using cached SD3.5 pipeline: %s", cache_key)
            return self._pipeline_cache[cache_key]

        # Load new pipeline
        logger.info("Loading new SD3.5 pipeline: %s", repo_id)

        # Configure pipeline kwargs following official SD3.5 patterns
        pipeline_kwargs = {
            "pretrained_model_name_or_path": repo_id,
            "torch_dtype": torch.bfloat16,  # Official SD3.5 recommendation
        }

        # Load pipeline using model_cache
        pipe = model_cache.from_pretrained(diffusers.StableDiffusion3Pipeline, **pipeline_kwargs)

        # Apply memory optimizations
        optimize_sd3_pipeline_memory_footprint(pipe)

        # Cache the optimized pipeline
        self._pipeline_cache[cache_key] = pipe
        logger.info("Cached SD3.5 pipeline: %s", cache_key)

        return pipe

    def validate_model_availability(self) -> list[Exception] | None:
        """Validate model using the same pattern as Flux."""
        return self._repo_param.validate_before_node_run()

    def get_repo_revision(self) -> tuple[str, str]:
        """Get the selected model repo and revision."""
        return self._repo_param.get_repo_revision()

    def get_quantization_config(self) -> str:
        """Get the quantization configuration."""
        return str(self._node.get_parameter_value("quantization"))

    def get_scheduler_name(self) -> str:
        """Get the selected scheduler name."""
        return str(self._node.get_parameter_value("scheduler"))

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the pipeline cache to free memory."""
        cls._pipeline_cache.clear()
        logger.info("Pipeline cache cleared")

"""Thin subclasses for DiffusionPipelineRuntimeNode to provide distinct node names."""

from diffusers_nodes_library.common.nodes.diffusion_pipeline_runtime_node import (
    DiffusionPipelineRuntimeNode,
)


class GenerateVideoNode(DiffusionPipelineRuntimeNode):
    """Generate videos via Diffusers Pipelines."""


class GenerateAudioNode(DiffusionPipelineRuntimeNode):
    """Generate audio via Diffusers Pipelines."""


class GenerateImageNode(DiffusionPipelineRuntimeNode):
    """Generate images via Diffusers Pipelines."""

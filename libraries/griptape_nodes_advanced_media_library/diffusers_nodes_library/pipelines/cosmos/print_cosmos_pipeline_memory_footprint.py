from diffusers_nodes_library.common.utils.torch_utils import print_pipeline_memory_footprint  # type: ignore[reportMissingImports]


def print_cosmos_pipeline_memory_footprint(pipe) -> None:
    """Convenience wrapper around print_pipeline_memory_footprint for Cosmos.
    
    Args:
        pipe: The Cosmos pipeline (type annotation omitted for compatibility)
    """
    # Standard components for video generation models
    component_names = [
        "vae",
        "text_encoder",
        "transformer",
        "scheduler",
    ]
    print_pipeline_memory_footprint(pipe, component_names)
import logging
from typing import override

from diffusers_nodes_library.pipelines.flux.lora.huggingface_flux_lora import (
    HuggingFaceFluxLora,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


class RiverZNormalDiptychFluxFillLora(HuggingFaceFluxLora):
    @override
    def get_repo_id(self) -> str:
        return "RiverZ/normal-lora"

    @override
    def get_filename(self) -> str:
        return "pytorch_lora_weights.safetensors"

    @override
    def get_trigger_phrase(self) -> str | None:
        return None

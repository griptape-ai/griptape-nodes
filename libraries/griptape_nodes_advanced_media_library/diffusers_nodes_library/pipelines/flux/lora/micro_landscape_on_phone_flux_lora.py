import logging
from typing import override

from diffusers_nodes_library.pipelines.flux.lora.huggingface_flux_lora import (
    HuggingFaceFluxLora,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


class MicroLandscapeOnPhoneFluxLora(HuggingFaceFluxLora):
    @override
    def get_repo_id(self) -> str:
        return "Shakker-Labs/FLUX.1-dev-LoRA-Micro-landscape-on-Mobile-Phone"

    @override
    def get_filename(self) -> str:
        return "FLUX-dev-lora-micro-landscape.safetensors"

    @override
    def get_trigger_phrase(self) -> str | None:
        return None

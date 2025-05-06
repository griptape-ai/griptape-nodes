import logging
from typing import override

from diffusers_nodes_library.pipelines.flux.lora.hugging_face_lora_node import HuggingFaceLoraNode  # type: ignore[reportMissingImports] 

logger = logging.getLogger("diffusers_nodes_library")


class ShakkerLabs_FLUX_1_dev_LoRA_Micro_landscape_on_Mobile_Phone(HuggingFaceLoraNode):
   
    @override
    def get_repo_id(self) -> str:
        return "Shakker-Labs/FLUX.1-dev-LoRA-Micro-landscape-on-Mobile-Phone"

    @override
    def get_filename(self) -> str:
        return "FLUX-dev-lora-micro-landscape.safetensors"

    @override
    def get_trigger_phrase(self) -> str|None:
        return None

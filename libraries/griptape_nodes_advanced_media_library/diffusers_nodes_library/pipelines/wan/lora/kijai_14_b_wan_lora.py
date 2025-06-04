import logging
from typing import override

from diffusers_nodes_library.pipelines.wan.lora.huggingface_wan_lora import (
    HuggingFaceWanLora,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


class Kijai14BWanLora(HuggingFaceWanLora):
    @override
    def get_repo_id(self) -> str:
        return "Kijai/WanVideo_comfy"

    @override
    def get_filename(self) -> str:
        return "Wan21_CausVid_14B_T2V_lora_rank32.safetensors"

    @override
    def get_trigger_phrase(self) -> str | None:
        return None

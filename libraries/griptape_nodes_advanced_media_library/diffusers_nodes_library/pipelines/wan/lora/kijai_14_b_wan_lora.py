import logging
from typing import override

from diffusers_nodes_library.pipelines.wan.lora.huggingface_wan_lora import (
    HuggingFaceWanLora,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import ParameterMessage

logger = logging.getLogger("diffusers_nodes_library")


class Kijai14BWanLora(HuggingFaceWanLora):
    @override
    def add_parameters(self) -> None:
        self.add_node_element(
            ParameterMessage(
                name="instructions_message",
                title="Instructions",
                variant="info",
                value=(
                    "This LoRA allows the Wan models to generate videos in as little as 2 (yes 2!) inference steps.\n"
                    "\n"
                    "Compatible nodes:\n"
                    "- Wan T2V\n"
                    "- Wan I2V\n"
                    "- Wan Vace\n"
                    "\n"
                    "Compatible models:\n"
                    "- Wan-AI/Wan2.1-T2V-14B-Diffusers\n"
                    "- Wan-AI/Wan2.1-I2V-14B-480P-Diffusers\n"
                    "- Wan-AI/Wan2.1-I2V-14B-720P-Diffusers\n"
                    "- Wan-AI/Wan2.1-VACE-1.3B-diffusers\n"
                    "\n"
                    "Notes:\n"
                    '- Set "num_inference_steps" to 2 for fastest results, increase for slower but better results.\n'
                    '- ⚠️ You MUST set "guidance_scale" to 0 or face weird artifacts in results.\n'
                ),
            )
        )
        super().add_parameters()

    @override
    def get_repo_id(self) -> str:
        return "Kijai/WanVideo_comfy"

    @override
    def get_filename(self) -> str:
        return "Wan21_CausVid_14B_T2V_lora_rank32.safetensors"

    @override
    def get_trigger_phrase(self) -> str | None:
        return None

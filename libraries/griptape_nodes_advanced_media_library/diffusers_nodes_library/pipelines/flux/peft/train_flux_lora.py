import logging
import os

from accelerate.cli.launch import launch_command_parser, launch_command  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class TrainFluxLora(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.log_params = LogParameter(self)
        self.log_params.add_output_parameters()


    # def validate_before_node_run(self) -> list[Exception] | None:
    #     # errors = self.pipe_params.validate_before_node_run()
    #     return errors or None

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        # export MODEL_NAME="black-forest-labs/FLUX.1-schnell"
        # export INSTANCE_DIR="dog"
        # export OUTPUT_DIR="trained-flux-lora"

        # accelerate launch train_dreambooth_lora_flux.py \
        # --pretrained_model_name_or_path=$MODEL_NAME  \
        # --instance_data_dir=$INSTANCE_DIR \
        # --output_dir=$OUTPUT_DIR \
        # --mixed_precision="no" \
        # --instance_prompt="a photo of sks dog" \
        # --resolution=512 \
        # --train_batch_size=1 \
        # --guidance_scale=1 \
        # --gradient_accumulation_steps=4 \
        # --gradient_checkpointing \
        # --optimizer="adamw" \
        # --learning_rate=1.0e-04 \
        # --lr_scheduler="constant" \
        # --lr_warmup_steps=0 \
        # --num_train_epochs=200 \
        # --max_train_steps=200 \
        # --train_batch_size=1 \
        # --cache_latents \
        # --validation_prompt="A photo of sks dog in a bucket" \
        # --num_validation_images=1 \
        # --validation_epochs=10 \
        # --seed=42

        

        with self.log_params.append_stdout_to_logs():
            print("CURRENT WORKING DIR", os.getcwd())
            parser = launch_command_parser()
            args   = parser.parse_args(["train_dreambooth_lora_flux.py"])
            launch_command(args)

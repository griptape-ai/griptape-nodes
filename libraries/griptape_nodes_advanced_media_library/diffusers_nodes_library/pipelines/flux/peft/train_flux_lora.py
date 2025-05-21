import io
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

from diffusers_nodes_library.pipelines.flux.peft.train_flux_lora_parameters import TrainFluxLoraParameters

logger = logging.getLogger("diffusers_nodes_library")




class TrainFluxLora(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.train_params = TrainFluxLoraParameters(self)
        self.log_params = LogParameter(self)
        self.train_params.add_input_parameters()
        self.train_params.add_output_parameters()
        self.log_params.add_output_parameters()


    # def validate_before_node_run(self) -> list[Exception] | None:
    #     # errors = self.pipe_params.validate_before_node_run()
    #     return errors or None

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.log_params.clear_logs()
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(__file__).parent / "training"
            model_name="black-forest-labs/FLUX.1-schnell"
            instance_data_dir = Path(tmpdir) / "sylphluxnix"
            output_dir = Path(tmpdir) / "trained-flux-lora"

            output_dir.mkdir(parents=True, exist_ok=True)

            # Copy a hardcoded data set for testing
            shutil.copytree("/Users/dylan/Documents/lora/datasets/sylphluxnix", instance_data_dir)

            env = os.environ.copy()

            # Convert current sys.path entries to resolved Path objects and join them
            current_python_paths = [str(Path(p).resolve()) for p in sys.path if p]
            new_python_path = os.pathsep.join([str(cwd)] + current_python_paths)

            # Create a copy of the current environment and update PYTHONPATH
            env = os.environ.copy()
            env["PYTHONPATH"] = new_python_path

            process = subprocess.Popen(
                [
                    "accelerate",
                    "launch",
                    "accelerate_main.py",
                    f"--pretrained_model_name_or_path={model_name}",
                    f"--instance_data_dir={instance_data_dir}",
                    f"--output_dir={output_dir}",
                    '--mixed_precision=no',
                    '--instance_prompt="glorp"', # We are going to rely on txt caption files next to the image files
                    f"--resolution={self.train_params.get_resolution()}",
                    "--train_batch_size=1",
                    "--guidance_scale=1",
                    "--gradient_accumulation_steps=4",
                    "--gradient_checkpointing",
                    '--optimizer=adamw',
                    f"--learning_rate={self.train_params.get_learning_rate()}",
                    '--lr_scheduler=constant',
                    "--lr_warmup_steps=0",
                    f"--num_train_epochs={self.train_params.get_num_train_epochs()}",
                    f"--max_train_steps={self.train_params.get_max_train_steps()}",
                    "--train_batch_size=1",
                    "--cache_latents",
                    f'--validation_prompt="{self.train_params.get_validation_prompt()}"',
                    "--num_validation_images=1",
                    "--validation_epochs=10",
                    "--seed=42",
                ],
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
            
            assert process.stdout is not None, "Failed to open stdout for subprocess"

            # Stream output to logger
            with process.stdout:
                for line in iter(process.stdout.readline, ''):
                    self.log_params.append_to_logs(f"{line.rstrip()}\n")

            # Wait for the process to finish
            exit_code = process.wait()
            if exit_code != 0:
                logger.error(f"Training process exited with code {exit_code}")


            lora_path = output_dir / "pytorch_lora_weights.safetensors"
            self.train_params.publish_lora_output(lora_path)
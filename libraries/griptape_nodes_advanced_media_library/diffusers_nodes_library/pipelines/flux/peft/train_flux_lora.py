import io
import json
import logging
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

from xdg_base_dirs import xdg_data_home
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
            repo, revision = self.train_params.get_repo_revision()
            model_name=repo  # TODO: get from the thing
            instance_data_dir = Path(tmpdir) / "training-data"
            output_dir = Path(tmpdir) / "trained-flux-lora"

            output_dir.mkdir(parents=True, exist_ok=True)

            # Copy the dataset to the temporary directory
            shutil.copytree(self.train_params.get_training_data_directory(), instance_data_dir)

            # Convert current sys.path entries to resolved Path objects and join them
            current_python_paths = [str(Path(p).resolve()) for p in sys.path if p]
            new_python_path = os.pathsep.join([str(cwd)] + current_python_paths)

            # Create a copy of the current environment and update PYTHONPATH
            library_name = "griptape_nodes_advanced_media_library"
            python_version = platform.python_version()
            library_venv_path = (
                xdg_data_home()
                / "griptape_nodes"
                / "venvs"
                / python_version
                / library_name.replace(" ", "_").strip()
            )
            library_venv_scripts_path = library_venv_path / "Scripts"

            
            accelerate_path = library_venv_scripts_path / "accelerate.exe"

            if platform.system() == "Windows":
                accelerate_path = accelerate_path.with_suffix(".exe")

            print(f"{str(library_venv_scripts_path)=}")
        
            env = os.environ.copy()
            env["PYTHONPATH"] = new_python_path
            # env["PATH"] = str(library_venv_scripts_path) + os.pathsep + env["PATH"]

            process = subprocess.Popen(
                [
                    str(accelerate_path),
                    "launch",
                    "accelerate_main.py",
                    f"--pretrained_model_name_or_path={model_name}",
                    f"--revision={revision}",
                    f"--instance_data_dir={instance_data_dir}",
                    f"--repeats={self.train_params.get_repeats()}",
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
                    f"--validation_epochs={self.train_params.get_validation_epoch()}",
                    "--seed=42",
                    # "--status_log_prefix=badger",
                ],
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1,
                env=env,
            )
            
            assert process.stdout is not None, "Failed to open stdout for subprocess"

            # Stream output to logger
            with process.stdout:
                for line in iter(process.stdout.readline, ''):
                    splits = line.split("|")
                    badger = splits[0] == "badger" if len(splits) > 0 else None
                    if not badger:
                        self.log_params.append_to_logs(f"{line.rstrip()}\n")
                        continue

                    badge = splits[1] if len(splits) > 1 else None
                    if not badge:
                        continue

                    if badge == "StdoutTracker.log":
                        data_json_str = "|".join(splits[2:]).rstrip()
                        data = json.loads(data_json_str)
                        step = data.get("step")
                        values = data.get("values")
                        # TODO: use the data from here:
                        #       - loss graph
                        #       - grid of validation images + partial _tiles_ oh man
                        print(f"{step=}")
                        print(f"{values=}")

            # Wait for the process to finish
            exit_code = process.wait()
            if exit_code != 0:
                logger.error(f"Training process exited with code {exit_code}")


            lora_path = output_dir / "pytorch_lora_weights.safetensors"
            self.train_params.publish_lora_output(lora_path)
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import torch  # type: ignore[reportMissingImports]
from xdg_base_dirs import xdg_data_home  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.flux.peft.train_flux_lora_parameters import TrainFluxLoraParameters
from griptape_nodes.exe_types.core_types import Parameter  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


class TrainFluxLora(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.train_params = TrainFluxLoraParameters(self)
        self.log_params = LogParameter(self)
        self.train_params.add_input_parameters()
        self.train_params.add_output_parameters()
        self.log_params.add_output_parameters()

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self.train_params.after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.log_params.clear_logs()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use the user-selected model for training.
            repo_name, revision = self.train_params.get_repo_revision()

            # The accelerate script expects to be run from the ./training/ directory.
            working_dir = Path(__file__).parent / "training"

            # Create the output directory in the temporary directory.
            # This is where the training output (lora & blah) will be saved.
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Copy the dataset to the temporary directory to ensure that we
            # don't modify the original dataset.
            training_data_dir = Path(tmpdir) / "training_data"
            shutil.copytree(self.train_params.get_training_data_directory(), training_data_dir)

            # Technically, I think this should be consistent with "frozen_dtype" (no => f32, bf16 => bf16),
            # but from experience mixed_precision needs to be "no" for MPS even if we actually use bf16
            # on the frozen weights to save on VRAM.
            mixed_precision = "bf16" if torch.cuda.is_available() else "no"

            # Snapshots are only supported on CUDA for the cuda backend.
            snapshot_html_path = output_dir / "snapshot.html" if torch.cuda.is_available() else None

            process = subprocess.Popen(  # noqa: S603
                [
                    self._get_accelerate_command_path(),
                    "launch",
                    "--num_processes=1",
                    "--num_machines=1",
                    f"--mixed_precision={mixed_precision}",
                    "--dynamo_backend=no",
                    "accelerate_main.py",
                    f"--pretrained_model_name_or_path={repo_name}",
                    # The dtype bfloat16 seems to work for a single machine on the devices I tested (M2 Max with MPS, Windows with CUDA), so
                    # I'm using it across the board (even if accelerate's mixed precision disagrees).
                    "--frozen_dtype=bf16",
                    *([f"--snapshot_html_path={snapshot_html_path}"] if snapshot_html_path else []),
                    f"--revision={revision}",
                    f"--instance_data_dir={training_data_dir}",
                    f"--repeats={self.train_params.get_repeats()}",
                    f"--output_dir={output_dir}",
                    '--instance_prompt="glorp"',  # We are going to rely on txt caption files next to the image files
                    f"--resolution={self.train_params.get_resolution()}",
                    f"--train_batch_size={self.train_params.get_train_batch_size()}",
                    f"--gradient_accumulation_steps={self.train_params.get_gradient_accumulation_steps()}",
                    "--guidance_scale=1",
                    "--gradient_checkpointing",
                    f"--optimizer={self.train_params.get_optimizer()}",
                    f"--learning_rate={self.train_params.get_learning_rate()}",
                    "--lr_scheduler=constant",
                    "--lr_warmup_steps=0",
                    f"--num_train_epochs={self.train_params.get_num_train_epochs()}",
                    f"--max_train_steps={self.train_params.get_max_train_steps()}",
                    "--cache_latents",
                    "--seed=42",
                ],
                cwd=str(working_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env={
                    **os.environ.copy(),
                    "PYTHONPATH": self._get_current_python_path_with_dir(working_dir),
                },
            )

            if process.stdout is None:
                msg = "Failed to open stdout for subprocess"
                raise RuntimeError(msg)

            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1354
            #       Implement training progress indicators via stdout:
            # loss_plot_image_prefix = "LossPlotImagePath="  # noqa: ERA001
            # progress_fraction_prefix = "ProgressFraction="  # noqa: ERA001
            with process.stdout:
                for line in iter(process.stdout.readline, ""):
                    #         if line.startswith(loss_plot_image_prefix):
                    #              do it
                    self.log_params.append_to_logs(line)

            # Wait for the process to finish
            exit_code = process.wait()
            if exit_code != 0:
                logger.error("Training process exited with code %d", exit_code)

            lora_path = output_dir / "pytorch_lora_weights.safetensors"
            self.train_params.publish_lora_output(lora_path)

            if snapshot_html_path and snapshot_html_path.exists():
                self.train_params.publish_snapshot_html_path(snapshot_html_path)

    def _get_accelerate_command_path(self) -> str:
        library_name = "griptape_nodes_advanced_media_library"
        python_version = platform.python_version()
        library_venv_path = (
            xdg_data_home() / "griptape_nodes" / "venvs" / python_version / library_name.replace(" ", "_").strip()
        )

        if platform.system() == "Windows":
            accelerate_path = library_venv_path / "Scripts" / "accelerate.exe"
        else:
            accelerate_path = library_venv_path / "bin" / "accelerate"

        return str(accelerate_path.resolve())

    def _get_current_python_path_with_dir(self, dir_to_add: Path) -> str:
        current_python_paths = [str(Path(p).resolve()) for p in sys.path if p]
        new_python_path = str(dir_to_add)
        formatted_python_path_str = os.pathsep.join([new_python_path, *current_python_paths])
        return formatted_python_path_str

import logging
import uuid
from pathlib import Path
from typing import Any

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.parameters.log_parameter import LogParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.flux.peft.training.utils.dreambooth_dataset import (
    DreamBoothDataset,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import (  # type: ignore[reportMissingImports]
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


def upload_and_get_local_file_path(path: Path) -> str:
    """Uploads a file to the static files manager and returns the local file path."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore[reportMissingImports]

    filename = f"{uuid.uuid4()}{path.suffix}"
    GriptapeNodes.StaticFilesManager().save_static_file(path.read_bytes(), filename)
    config_manager = GriptapeNodes.ConfigManager()
    static_dir = config_manager.workspace_path / config_manager.merged_config["static_files_directory"]
    return str(static_dir / filename)


class TrainFluxLoraParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "black-forest-labs/FLUX.1-dev",
                "black-forest-labs/FLUX.1-schnell",
            ],
        )

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="training_data_directory",
                input_types=["str"],
                type="str",
                tooltip="A path to a directory on the engine's filesystem containing training samples. Each sample should consist of two files with the same name. The first file should be an image (png, jpg, jpeg) and the second file should be a plain text file containing captions (txt).",
                default_value=None,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="repeats",
                input_types=["int"],
                type="int",
                tooltip="repeats",
                default_value=10,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="resolution",
                input_types=["int"],
                type="int",
                tooltip="resolution",
                default_value=512,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="optimizer",
                input_types=["str"],
                type="str",
                tooltip="optimizer",
                default_value="adamw",
                allowed_modes=set(),
            )
        )
        self._node.add_parameter(
            Parameter(
                name="learning_rate",
                input_types=["float"],
                type="float",
                tooltip="learning_rate",
                default_value=5e-4,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="train_batch_size",
                input_types=["int"],
                type="int",
                tooltip="effective batch size is train_batch_size * gradient_accumulation_steps -- lean towards 1 for train_batch_size for low-vram, compensate with gradient_accumulation_steps",
                default_value=4,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="gradient_accumulation_steps",
                input_types=["int"],
                type="int",
                tooltip="effective batch size is train_batch_size * gradient_accumulation_steps -- lean towards 1 for train_batch_size for low-vram, compensate with gradient_accumulation_steps",
                default_value=1,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="effective_batch_size",
                type="str",
                tooltip="effective batch size is train_batch_size * gradient_accumulation_steps -- lean towards 1 for train_batch_size for low-vram, compensate with gradient_accumulation_steps",
                default_value="4",
                allowed_modes=set(),
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_train_epochs",
                input_types=["int"],
                type="int",
                tooltip="num_train_epochs",
                default_value=10,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="max_train_steps",
                input_types=["int"],
                type="int",
                tooltip="max_train_steps",
                default_value=200,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="effective_train_steps",
                type="str",
                default_value="Need valid training data directory to calculate effective train steps",
                tooltip="effective train steps is min(num_train_epochs * (repeats * training_data_size / effective_batch_size), max_train_steps)",
                allowed_modes=set(),
            )
        )

    def add_output_parameters(self) -> None:
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1354
        # Cache the output model -- only train if input parameters change
        self._node.add_parameter(
            Parameter(
                name="lora_path",
                output_type="str",
                tooltip="the trained LoRA model",
                default_value="",
                type="str",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        # Snapshots are only supported on CUDA for the cuda backend.
        if torch.cuda.is_available():
            self._node.add_parameter(
                Parameter(
                    name="snapshot_html_path",
                    output_type="str",
                    tooltip="the html file with vram snapshot",
                    default_value="",
                    type="str",
                    allowed_modes={ParameterMode.OUTPUT},
                )
            )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        gradient_accumulation_steps = (
            value if parameter.name == "gradient_accumulation_steps" else self.get_gradient_accumulation_steps()
        )
        train_batch_size = value if parameter.name == "train_batch_size" else self.get_train_batch_size()
        effective_batch_size = train_batch_size * gradient_accumulation_steps

        if parameter.name in {"gradient_accumulation_steps", "train_batch_size"}:
            # Update effective batch size when train_batch_size or gradient_accumulation_steps changes
            self._node.set_parameter_value("effective_batch_size", effective_batch_size)
            self._node.publish_update_to_parameter("effective_batch_size", effective_batch_size)
            modified_parameters_set.add("effective_batch_size")

        training_data_directory = (
            value if parameter.name == "training_data_directory" else self.get_training_data_directory()
        )
        repeats = value if parameter.name == "repeats" else self.get_repeats()
        num_train_epochs = value if parameter.name == "num_train_epochs" else self.get_num_train_epochs()
        max_train_steps = value if parameter.name == "max_train_steps" else self.get_max_train_steps()

        if parameter.name in {
            "gradient_accumulation_steps",
            "train_batch_size",
            "training_data_directory",
            "repeats",
            "num_train_epochs",
            "max_train_steps",
        }:
            if not training_data_directory or not Path(training_data_directory).exists():
                effective_train_steps = "Need valid training data directory to calculate effective train steps"
            else:
                # Update effective train steps when num_train_epochs, repeats, effective_batch_size or max_train_steps changes
                dataset_length = DreamBoothDataset.length_from_local_directory(
                    instance_data_root=training_data_directory,
                    repeats=repeats,
                )
                effective_train_steps = min(
                    num_train_epochs * (dataset_length / effective_batch_size),
                    max_train_steps,
                )
            self._node.set_parameter_value("effective_train_steps", effective_train_steps)
            self._node.publish_update_to_parameter("effective_train_steps", effective_train_steps)
            modified_parameters_set.add("effective_train_steps")

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_training_data_directory(self) -> str:
        return str(self._node.get_parameter_value("training_data_directory"))

    def get_repeats(self) -> int:
        return int(self._node.get_parameter_value("repeats"))

    def get_resolution(self) -> int:
        return int(self._node.get_parameter_value("resolution"))

    def get_optimizer(self) -> str:
        return str(self._node.get_parameter_value("optimizer"))

    def get_learning_rate(self) -> float:
        return float(self._node.get_parameter_value("learning_rate"))

    def get_train_batch_size(self) -> int:
        return int(self._node.get_parameter_value("train_batch_size"))

    def get_gradient_accumulation_steps(self) -> int:
        return int(self._node.get_parameter_value("gradient_accumulation_steps"))

    def get_num_train_epochs(self) -> int:
        return int(self._node.get_parameter_value("num_train_epochs"))

    def get_max_train_steps(self) -> int:
        return int(self._node.get_parameter_value("max_train_steps"))

    def get_validation_prompt(self) -> str:
        return str(self._node.get_parameter_value("validation_prompt"))

    def get_validation_epoch(self) -> int:
        return int(self._node.get_parameter_value("validation_epoch"))

    def publish_lora_output(self, lora_safetensors_path: Path) -> None:
        lora_path = upload_and_get_local_file_path(lora_safetensors_path)
        if hasattr(self._node, "log_params") and isinstance(self._node.log_params, LogParameter):  # type: ignore[reportAttributeAccessIssue]
            self._node.log_params.append_to_logs(f"LoRA model moved to {lora_path}.\n")  # type: ignore[reportAttributeAccessIssue]
        self._node.parameter_output_values["lora_path"] = lora_path

    def publish_snapshot_html_path(self, snapshot_html_path: Path) -> None:
        if not torch.cuda.is_available():
            logger.warning("Snapshot HTML path is only available when CUDA is enabled.")
            return
        self._node.parameter_output_values["snapshot_html_path"] = upload_and_get_local_file_path(snapshot_html_path)

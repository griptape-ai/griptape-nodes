import os
import time
from typing import Any, Iterator, OrderedDict, Protocol, runtime_checkable

import contextlib
import logging

from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from PIL.Image import Image
from diffusers_nodes_library.utils.lora_utils import configure_flux_loras # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)
from griptape.artifacts import ImageUrlArtifact, UrlArtifact

from diffusers_nodes_library.utils.logging_utils import StdoutCapture, LoggerCapture  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options


from diffusers_nodes_library.utils.huggingface_utils import (  # type: ignore[reportMissingImports]
    list_repo_revisions_in_cache,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")

class VideoUrlArtifact(UrlArtifact):
    """
    Artifact that contains a URL to a video.
    """
    def __init__(self, url: str, name: str = "VideoUrlArtifact"):
        super().__init__(value=url, name=name)

class AudioUrlArtifact(UrlArtifact):
    """
    Artifact that contains a URL to an audio file.
    """
    def __init__(self, url: str, name: str = "AudioUrlArtifact"):
        super().__init__(value=url, name=name)
class HuggingFaceRepoParameter:
    @classmethod
    def _repo_revision_to_key(cls, repo_revision: tuple[str, str]) -> str:
        return f"{repo_revision[0]} ({repo_revision[1]})"

    @classmethod
    def _key_to_repo_revision(cls, key: str) -> tuple[str, str]:
        parts = key.rsplit(" (", maxsplit=1)
        if len(parts) != 2 or parts[1][-1] != ")":  # noqa: PLR2004
            logger.exception("Invalid key")
        return parts[0], parts[1][:-1]

    def __init__(self, node: ControlNode, repo_ids: list[str], parameter_name: str = "model"):
        self._node = node
        self._parameter_name = parameter_name
        self._repo_revisions = [
            repo_revision
            for repo_id in repo_ids
            for repo_revision in list_repo_revisions_in_cache(repo_id)
        ]

    def add_parameter(self):
        self._node.add_parameter(
            Parameter(
                name=self._parameter_name,
                default_value=(
                    self._repo_revision_to_key(self._repo_revisions[0])
                    if self._repo_revisions
                    else None
                ),
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=list(map(self._repo_revision_to_key, self._repo_revisions)),
                    )
                },
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip=self._parameter_name,
            )
        )


    def get_repo_revision(self):
        value = self._node.get_parameter_value(self._parameter_name)
        if value is None:
            logger.exception(f"No {self._parameter_name} specified")
        base_repo_id, base_revision = self._key_to_repo_revision(value)
        return base_repo_id, base_revision

class FluxControlRepoRevisionParameters:
    @classmethod
    def _repo_revision_to_key(cls, repo_revision: tuple[str, str]) -> str:
        return f"{repo_revision[0]} ({repo_revision[1]})"

    @classmethod
    def _key_to_repo_revision(cls, key: str) -> tuple[str, str]:
        parts = key.rsplit(" (", maxsplit=1)
        if len(parts) != 2 or parts[1][-1] != ")":  # noqa: PLR2004
            logger.exception("Invalid key")
        return parts[0], parts[1][:-1]
    
    def __init__(self, node: ControlNode, repo_id: str):
        self._node = node
        self._repo_id = repo_id
        self._controlnet_model_repo_revisions = list_repo_revisions_in_cache(self._repo_id)

    def add_input_parameters(self):
        self._node.add_parameter(
            Parameter(
                name="controlnet_model",
                default_value=(
                    self._repo_revision_to_key(self._controlnet_model_repo_revisions[0])
                    if self._controlnet_model_repo_revisions
                    else None
                ),
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=list(
                            map(self._repo_revision_to_key, self._controlnet_model_repo_revisions)
                        ),
                    )
                },
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
            )
        )

    def get_repo_revision(self):
        controlnet_model = self._node.get_parameter_value("controlnet_model")
        if controlnet_model is None:
            logger.exception("No controlnet model specified")
        repo_id, revision = self._key_to_repo_revision(controlnet_model)
        return repo_id, revision
    
class FilePathParameter:
    def __init__(self, node: ControlNode, parameter_name: str = "file_path"):
        self._node = node
        self._parameter_name = parameter_name

    def add_input_parameters(self):
        self._node.add_parameter(
            Parameter(
                name=self._parameter_name,
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
            )
        )

    def get_file_path(self):
        return self._node.get_parameter_value(self._parameter_name)

    def validate_parameter_values(self):
        file_path = self.get_file_path()
        if not os.path.exists(file_path):
            raise RuntimeError(f"No file at {file_path} exists")
    
class FluxLoraRepoRevisionParameters:
    @classmethod
    def _repo_revision_to_key(cls, repo_revision: tuple[str, str]) -> str:
        return f"{repo_revision[0]} ({repo_revision[1]})"

    @classmethod
    def _key_to_repo_revision(cls, key: str) -> tuple[str, str]:
        parts = key.rsplit(" (", maxsplit=1)
        if len(parts) != 2 or parts[1][-1] != ")":  # noqa: PLR2004
            logger.exception("Invalid key")
        return parts[0], parts[1][:-1]
    
    def __init__(self, node: ControlNode, repo_id: str):
        self._node = node
        self._repo_id = repo_id
        self._repo_revisions = list_repo_revisions_in_cache(self._repo_id)

    def add_input_parameters(self):
        self._node.add_parameter(
            Parameter(
                name="lora_repo_revision",
                default_value=(
                    self._repo_revision_to_key(self._repo_revisions[0])
                    if self._repo_revisions
                    else None
                ),
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=list(
                            map(self._repo_revision_to_key, self._repo_revisions)
                        ),
                    )
                },
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
            )
        )

    def get_repo_revision(self):
        lora_repo_revision = self._node.get_parameter_value("lora_repo_revision")
        if lora_repo_revision is None:
            logger.exception("No lora_repo_revision specified")
        repo_id, revision = self._key_to_repo_revision(lora_repo_revision)
        return repo_id, revision
    
class FluxLoraWeightAndOutputParameters:
    def __init__(self, node: ControlNode):
        self._node = node

    def add_input_parameters(self):
        self._node.add_parameter(
            Parameter(
                name="weight",
                default_value=1.0,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},

            )
        )
    
    def add_output_parameters(self):
        self._node.add_parameter(
            Parameter(
                name="loras",
                default_value=1.0,
                input_types=["dict"],
                type="dict",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="loras",

            )
        )

    def get_weight(self) -> float:
        return float(self._node.get_parameter_value("weight"))
    
    def set_output_lora(self, lora: dict) -> None:
        self._node.set_parameter_value("loras", lora)
        self._node.parameter_output_values["loras"] = lora

class FluxLoraParameters:
    def __init__(self, node: ControlNode):
        self._node = node

    def add_input_parameters(self):
        self._node.add_parameter(
            Parameter(
                name="loras",
                input_types=["dict"],
                type="dict",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="loras",
            )
        )

    def configure_loras(self, pipe: Any):
        loras = self._node.get_parameter_value("loras")

        # Well, I guess it's ok to mutate the pipeline as long as we mutate it back
        # before another node instance uses it, since there is no parallelism.
        # Not sure if pytorch handles any model cachinging process -- that would be
        # nice since we don't want to duplicate such large objects (GBs) in RAM.
        configure_flux_loras(self._node, pipe, loras)


class FluxControlNetParameters:
    def __init__(self, node: ControlNode):
        self._node = node

    def add_input_parameters(self):
        self._node.add_parameter(
            Parameter(
                name="controlnet_conditioning_scale",
                default_value=0.7,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="controlnet_conditioning_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_guidance_end",
                default_value=0.8,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="control_guidance_end",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_mode",
                default_value=0,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="control_mode",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="control_image",
            )
        )

    def get_control_image_pil(self):
        control_image_artifact = self._node.get_parameter_value("control_image")
        if isinstance(control_image_artifact, ImageUrlArtifact):
            control_image_artifact = ImageLoader().parse(control_image_artifact.to_bytes())
        control_image_pil = image_artifact_to_pil(control_image_artifact)
        return control_image_pil.convert("RGB")
    

    def get_pipe_kwargs(self) -> dict:

        # controlnet_model = self._node.get_parameter_value("controlnet_model")
        # if controlnet_model is None:
        #     logger.exception("No controlnet model specified")
        # controlnet_repo_id, controlnet_revision = FluxControlNetPipeline._key_to_repo_revision(controlnet_model)

        control_image_pil = self.get_control_image_pil()
        controlnet_conditioning_scale = float(self._node.get_parameter_value("controlnet_conditioning_scale"))
        control_guidance_end = float(self._node.get_parameter_value("control_guidance_end"))
        control_mode = int(self._node.get_parameter_value("control_mode"))

        return {
            "control_image": [control_image_pil],
            "controlnet_conditioning_scale": [controlnet_conditioning_scale],
            "control_guidance_end": [control_guidance_end],
            "control_mode": control_mode, #[control_mode],
        }
    
class FluxControlNetParameters__UnionOne:
    def __init__(self, node: ControlNode):
        self._node = node
        self._control_mode_by_name = OrderedDict()
        self._control_mode_by_name["canny"] = 0
        self._control_mode_by_name["tile"] = 1
        self._control_mode_by_name["depth"] = 2
        self._control_mode_by_name["blur"] = 3
        self._control_mode_by_name["pose"] = 4
        self._control_mode_by_name["gray"] = 5
        self._control_mode_by_name["lq"] = 6

    def add_input_parameters(self):
        self._node.add_parameter(
            Parameter(
                name="controlnet_conditioning_scale",
                default_value=0.7,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="controlnet_conditioning_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_guidance_end",
                default_value=0.8,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="control_guidance_end",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_mode",
                default_value=list(self._control_mode_by_name.keys())[0],
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=list(self._control_mode_by_name.keys()),
                    )
                },
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="control_image",
            )
        )

    def get_control_image_pil(self):
        control_image_artifact = self._node.get_parameter_value("control_image")
        if isinstance(control_image_artifact, ImageUrlArtifact):
            control_image_artifact = ImageLoader().parse(control_image_artifact.to_bytes())
        control_image_pil = image_artifact_to_pil(control_image_artifact)
        return control_image_pil.convert("RGB")
    

    def get_pipe_kwargs(self) -> dict:

        # controlnet_model = self._node.get_parameter_value("controlnet_model")
        # if controlnet_model is None:
        #     logger.exception("No controlnet model specified")
        # controlnet_repo_id, controlnet_revision = FluxControlNetPipeline._key_to_repo_revision(controlnet_model)

        control_image_pil = self.get_control_image_pil()
        controlnet_conditioning_scale = float(self._node.get_parameter_value("controlnet_conditioning_scale"))
        control_guidance_end = float(self._node.get_parameter_value("control_guidance_end"))
        control_mode_int = self._control_mode_by_name[self._node.get_parameter_value("control_mode")]

        return {
            "control_image": control_image_pil,
            "controlnet_conditioning_scale": controlnet_conditioning_scale,
            "control_guidance_end": control_guidance_end,
            "control_mode": control_mode_int, #[control_mode],
        }
    
class FluxControlNetParameters__UnionTwo:
    def __init__(self, node: ControlNode):
        self._node = node

    def add_input_parameters(self):
        self._node.add_parameter(
            Parameter(
                name="controlnet_conditioning_scale",
                default_value=0.7,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="controlnet_conditioning_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_guidance_end",
                default_value=0.8,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="control_guidance_end",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="control_image",
            )
        )

    def get_control_image_pil(self):
        control_image_artifact = self._node.get_parameter_value("control_image")
        if isinstance(control_image_artifact, ImageUrlArtifact):
            control_image_artifact = ImageLoader().parse(control_image_artifact.to_bytes())
        control_image_pil = image_artifact_to_pil(control_image_artifact)
        return control_image_pil.convert("RGB")
    

    def get_pipe_kwargs(self) -> dict:

        control_image_pil = self.get_control_image_pil()
        controlnet_conditioning_scale = float(self._node.get_parameter_value("controlnet_conditioning_scale"))
        control_guidance_end = float(self._node.get_parameter_value("control_guidance_end"))

        return {
            "control_image": control_image_pil,
            "controlnet_conditioning_scale": controlnet_conditioning_scale,
            "control_guidance_end": control_guidance_end,
        }

class LogParameter:
    def __init__(self, node: ControlNode):
        self._node = node
    
    def add_output_parameters(self):
        self._node.add_parameter(
            Parameter(
                name="logs",
                output_type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="logs",
                ui_options={"multiline": True},
            )
        )


    @contextlib.contextmanager
    def append_stdout_to_logs(self) -> Iterator[None]:
        def callback(data: str) -> None:
            self.append_to_logs(data)

        with StdoutCapture(callback):
            yield

    @contextlib.contextmanager
    def append_logs_to_logs(self, logger: logging.Logger) -> Iterator[None]:
        def callback(data: str) -> None:
            self.append_to_logs(data)

        with LoggerCapture(logger, callback):
            yield

    @contextlib.contextmanager
    def append_profile_to_logs(self, label: str) -> Iterator[None]:
        start = time.perf_counter()
        yield
        seconds = (time.perf_counter() - start)
        human_readable_duration = seconds_to_human_readable(seconds)
        self.append_to_logs(f"{label} took {human_readable_duration}\n")

    def append_to_logs(self, text: str):
        self._node.append_value_to_parameter("logs", text)


def seconds_to_human_readable(seconds: float):
    intervals = (
        ('year', 31536000),
        ('month', 2592000),
        ('day', 86400),
        ('hour', 3600),
        ('minute', 60),
        ('second', 1),
        ('millisecond', 0.001),
    )

    for name, count in intervals:
        if seconds >= count:
            value = seconds / count
            return f"{value:.2f} {name}{'s' if value != 1 else ''}"
    return "0.00 milliseconds"
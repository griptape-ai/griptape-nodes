import io
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from griptape_nodes.exe_types.core_types import ParameterList, ParameterMode
from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

from diffusers_nodes_library.pipelines.flux.peft.train_flux_lora_parameters import TrainFluxLoraParameters

logger = logging.getLogger("diffusers_nodes_library")




class FluxLoraTrainingData(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            ParameterList(
                name="foo",
                input_types=["foo"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )
        

    def process(self) -> AsyncResult | None:
        pass
import logging
from abc import ABC, abstractmethod

import diffusers  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineTypePipelineParameters(ABC):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        self._node = node
        self._list_all_models = list_all_models

    @abstractmethod
    def add_input_parameters(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def remove_input_parameters(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_config_kwargs(self) -> dict:
        raise NotImplementedError

    @property
    @abstractmethod
    def pipeline_class(self) -> type[diffusers.DiffusionPipeline]:
        raise NotImplementedError

    @property
    def pipeline_name(self) -> str:
        return self.pipeline_class.__name__

    @abstractmethod
    def validate_before_node_run(self) -> list[Exception] | None:
        raise NotImplementedError

    @abstractmethod
    def build_pipeline(self) -> diffusers.DiffusionPipeline:
        raise NotImplementedError

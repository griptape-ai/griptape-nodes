import logging

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter

logger = logging.getLogger("sam2_nodes_library")


class DinoSam2DetectorParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_dino_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "IDEA-Research/grounding-dino-base",
            ],
            parameter_name="dino_model",
        )
        self._huggingface_sam2_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "facebook/sam2-hiera-tiny",
                "facebook/sam2-hiera-small",
                "facebook/sam2-hiera-base-plus",
                "facebook/sam2-hiera-large",
            ],
            parameter_name="sam2_model",
        )

    def add_input_parameters(self) -> None:
        self._huggingface_dino_repo_parameter.add_input_parameters()
        self._huggingface_sam2_repo_parameter.add_input_parameters()

    def get_dino_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_dino_repo_parameter.get_repo_revision()

    def get_sam2_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_sam2_repo_parameter.get_repo_revision()

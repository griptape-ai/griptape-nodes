import logging

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_model_parameter import HuggingFaceModelParameter
from griptape_nodes.exe_types.param_components.huggingface.huggingface_utils import (
    list_all_repo_revisions_in_cache,
    list_repo_revisions_in_cache,
)

logger = logging.getLogger("griptape_nodes")


class HuggingFaceRepoParameter(HuggingFaceModelParameter):
    def __init__(
        self, node: BaseNode, repo_ids: list[str], parameter_name: str = "model", *, list_all_models: bool = False
    ):
        super().__init__(node, parameter_name)
        self._repo_ids = repo_ids
        self._list_all_models = list_all_models
        self.refresh_parameters()

    def fetch_repo_revisions(self) -> list[tuple[str, str]]:
        if self._list_all_models:
            all_revisions = list_all_repo_revisions_in_cache()
            return sorted(all_revisions, key=lambda x: x[0] not in self._repo_ids)
        return [repo_revision for repo in self._repo_ids for repo_revision in list_repo_revisions_in_cache(repo)]

    def get_download_commands(self) -> list[str]:
        return [f'huggingface-cli download "{repo}"' for repo in self._repo_ids]

    def get_download_models(self) -> list[str]:
        """Returns a list of model names that should be downloaded."""
        return self._repo_ids

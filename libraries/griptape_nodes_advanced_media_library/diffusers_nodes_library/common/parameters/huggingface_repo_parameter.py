import logging

from diffusers_nodes_library.common.parameters.huggingface_model_parameter import HuggingFaceModelParameter
from diffusers_nodes_library.common.utils.huggingface_utils import list_all_repo_revisions_in_cache, list_repo_revisions_in_cache
from griptape_nodes.exe_types.node_types import BaseNode  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


class HuggingFaceRepoParameter(HuggingFaceModelParameter):
    def __init__(self, node: BaseNode, repo_ids: list[str], parameter_name: str = "model", list_all_models: bool = False):
        super().__init__(node, parameter_name)
        self._repo_ids = repo_ids
        self._list_all_models = list_all_models
        self.refresh_parameters()

    def fetch_repo_revisions(self) -> list[tuple[str, str]]:
        if self._list_all_models:
            return list_all_repo_revisions_in_cache()
        else:
            return [repo_revision for repo in self._repo_ids for repo_revision in list_repo_revisions_in_cache(repo)]

    def get_download_commands(self) -> list[str]:
        return [f'huggingface-cli download "{repo}"' for repo in self._repo_ids]

    def get_download_models(self) -> list[str]:
        """Returns a list of model names that should be downloaded."""
        return self._repo_ids

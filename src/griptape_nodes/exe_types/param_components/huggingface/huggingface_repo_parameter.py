import logging

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_model_parameter import HuggingFaceModelParameter
from griptape_nodes.exe_types.param_components.huggingface.huggingface_utils import (
    list_all_repo_revisions_in_cache,
    list_repo_revisions_in_cache,
)
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")


class HuggingFaceRepoParameter(HuggingFaceModelParameter):
    def __init__(
        self,
        node: BaseNode,
        repo_ids: list[str],
        parameter_name: str = "model",
        *,
        list_all_models: bool = False,
        deprecated_repo_ids: list[str] | None = None,
    ):
        super().__init__(node, parameter_name)

        deprecated_repo_ids = deprecated_repo_ids or []
        self._deprecated_repos = deprecated_repo_ids

        self._repo_ids = repo_ids + deprecated_repo_ids
        self._list_all_models = list_all_models
        self.refresh_parameters()

    def fetch_repo_revisions(self) -> list[tuple[str, str]]:
        if self._list_all_models:
            all_revisions = list_all_repo_revisions_in_cache()
            return sorted(all_revisions, key=lambda x: x[0] not in self._repo_ids)
        results = []
        for repo in self._repo_ids:
            revisions = list_repo_revisions_in_cache(repo)
            results.extend(revisions if revisions else [(repo, "")])
        return results

    def _is_deprecated(self, repo: str) -> bool:
        return repo in self._deprecated_repos

    def refresh_parameters(self, value_being_set: str | None = None) -> None:
        """Override to filter deprecated models except the currently selected one.

        Args:
            value_being_set: Optional value that's being set (used during after_value_set)
        """
        parameter = self._node.get_parameter_by_name(self._parameter_name)
        if parameter is None:
            logger.debug(
                "Parameter '%s' not found on node '%s'; cannot refresh choices.",
                self._parameter_name,
                self._node.name,
            )
            return

        # Get all cached models
        all_choices = self.get_choices()
        if not all_choices:
            return

        # Get current value - use value_being_set if provided (during after_value_set)
        current_value = (
            value_being_set if value_being_set is not None else self._node.get_parameter_value(self._parameter_name)
        )

        # Filter: include non-deprecated models, and deprecated model if it's currently selected
        filtered_choices = []
        for choice in all_choices:
            repo_id, _ = self._key_to_repo_revision(choice)
            is_deprecated = self._is_deprecated(repo_id)

            # Include if: not deprecated OR matches current/being-set value
            if not is_deprecated or choice == current_value:
                filtered_choices.append(choice)

        # If no choices after filtering, include all (initial state)
        if not filtered_choices:
            return

        # Determine default value
        if current_value and current_value in filtered_choices:
            default_value = current_value
        else:
            default_value = filtered_choices[0]

        if parameter.find_elements_by_type(Options):
            self._node._update_option_choices(self._parameter_name, filtered_choices, default_value)
        else:
            parameter.add_trait(Options(choices=filtered_choices))

    def add_input_parameters(self) -> None:
        """Override to apply deprecated model filtering after parameter creation."""
        super().add_input_parameters()
        self.refresh_parameters()

    def get_download_commands(self) -> list[str]:
        return [f'huggingface-cli download "{repo}"' for repo in self._repo_ids if not self._is_deprecated(repo)]

    def get_download_models(self) -> list[str]:
        """Returns a list of model names that should be downloaded (excluding deprecated models)."""
        return [repo for repo in self._repo_ids if not self._is_deprecated(repo)]

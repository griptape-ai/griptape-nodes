import logging
import re
from abc import ABC, abstractmethod

from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")


class HuggingFaceModelParameter(ABC):
    @classmethod
    def _repo_revision_to_key(cls, repo_revision: tuple[str, str]) -> str:
        return f"{repo_revision[0]} ({repo_revision[1]})"

    @classmethod
    def _key_to_repo_revision(cls, key: str) -> tuple[str, str]:
        # Check if key has hash format using regex
        hash_pattern = r"^(.+) \(([a-f0-9]{40})\)$"
        match = re.match(hash_pattern, key)
        if match:
            return match.group(1), match.group(2)

        # Key is just the model name (no hash)
        return key, ""

    def __init__(self, node: BaseNode, parameter_name: str):
        self._node = node
        self._parameter_name = parameter_name
        self._repo_revisions = []

    def refresh_parameters(self) -> None:
        parameter = self._node.get_parameter_by_name(self._parameter_name)
        if parameter is None:
            logger.debug(
                "Parameter '%s' not found on node '%s'; cannot refresh choices.",
                self._parameter_name,
                self._node.name,
            )
            return

        choices = self.get_choices()

        current_value = self._node.get_parameter_value(self._parameter_name)
        if current_value in choices:
            default_value = current_value
        else:
            default_value = choices[0]

        if parameter.find_elements_by_type(Options):
            self._node._update_option_choices(self._parameter_name, choices, default_value)
        else:
            parameter.add_trait(Options(choices=choices))

    def add_input_parameters(self) -> None:
        choices = self.get_choices()

        if not choices:
            self._node.add_node_element(
                ParameterMessage(
                    name=f"huggingface_repo_parameter_message_{self._parameter_name}",
                    title="Huggingface Model Download Required",
                    variant="warning",
                    value=self.get_help_message(),
                    button_link=f"#model-management?search={self.get_download_models()[0]}",
                    button_text="Model Management",
                    button_icon="hard-drive",
                )
            )
            return

        self._node.add_parameter(
            Parameter(
                name=self._parameter_name,
                default_value=choices[0] if choices else None,
                input_types=["str"],
                type="str",
                ui_options={"display_name": self._parameter_name, "show_search": True},
                traits={
                    Options(
                        choices=choices,
                    )
                },
                tooltip=self._parameter_name,
                allowed_modes={ParameterMode.PROPERTY},
            )
        )

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name(self._parameter_name)
        self._node.remove_parameter_element_by_name(f"huggingface_repo_parameter_message_{self._parameter_name}")

    def get_choices(self) -> list[str]:
        # Ensure the latest repo revisions are fetched
        self._repo_revisions = self.fetch_repo_revisions()
        # Count occurrences of each model name
        model_counts = {}
        for repo_id, _ in self.list_repo_revisions():
            model_counts[repo_id] = model_counts.get(repo_id, 0) + 1

        # Generate choices with hash only when there are duplicates
        choices = []
        for repo_revision in self.list_repo_revisions():
            repo_id, _ = repo_revision
            if model_counts[repo_id] > 1:
                # Multiple versions exist, show hash for disambiguation
                choices.append(self._repo_revision_to_key(repo_revision))
            else:
                # Only one version, show just the model name
                choices.append(repo_id)
        logger.debug("Available choices for parameter '%s': %s", self._parameter_name, choices)
        return choices

    def validate_before_node_run(self) -> list[Exception] | None:
        self.refresh_parameters()
        try:
            self.get_repo_revision()
        except Exception as e:
            return [e]

        return None

    def list_repo_revisions(self) -> list[tuple[str, str]]:
        return self._repo_revisions

    def get_repo_revision(self) -> tuple[str, str]:
        value = self._node.get_parameter_value(self._parameter_name)
        if value is None:
            msg = "Model download required!"
            raise RuntimeError(msg)

        # Parse the value using _key_to_repo_revision
        repo_id, revision = self._key_to_repo_revision(value)

        # If revision is empty (just model name), find it in our stored list
        if not revision:
            for stored_repo_id, stored_revision in self._repo_revisions:
                if stored_repo_id == repo_id:
                    logger.debug("Using revision '%s' for model '%s'", stored_revision, repo_id)
                    return stored_repo_id, stored_revision
            # If not found, raise an error
            msg = f"Model '{repo_id}' not found in available models!"
            raise RuntimeError(msg)

        # If revision was provided, return it directly
        return repo_id, revision

    def get_help_message(self) -> str:
        download_models = "\n".join([f"  {model}" for model in self.get_download_models()])

        return (
            "Model download required to continue.\n\n"
            "To download models:\n\n"
            "1. Navigate to Settings -> Model Management\n\n"
            "2. Search for the model(s) you need and click the download button:\n"
            f"{download_models}\n\n"
            "After completing these steps, a dropdown menu with available models will appear."
        )

    @abstractmethod
    def fetch_repo_revisions(self) -> list[tuple[str, str]]: ...

    @abstractmethod
    def get_download_commands(self) -> list[str]: ...

    @abstractmethod
    def get_download_models(self) -> list[str]: ...

import logging
from abc import ABC, abstractmethod

from diffusers_nodes_library.common.utils.option_utils import update_option_choices
from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


class HuggingFaceModelParameter(ABC):
    @classmethod
    def _repo_revision_to_key(cls, repo_revision: tuple[str, str]) -> str:
        return f"{repo_revision[0]} ({repo_revision[1]})"

    @classmethod
    def _key_to_repo_revision(cls, key: str) -> tuple[str, str]:
        parts = key.rsplit(" (", maxsplit=1)
        if len(parts) != 2 or parts[1][-1] != ")":  # noqa: PLR2004
            logger.exception("Invalid key")
        return parts[0], parts[1][:-1]

    def __init__(self, node: BaseNode, parameter_name: str):
        self._node = node
        self._parameter_name = parameter_name
        self._repo_revisions = []

    def refresh_parameters(self) -> None:
        num_repo_revisions_before = len(self.list_repo_revisions())
        self._repo_revisions = self.fetch_repo_revisions()
        num_repo_revisions_after = len(self.list_repo_revisions())

        if num_repo_revisions_before != num_repo_revisions_after and self._node.get_parameter_by_name(
            self._parameter_name
        ):
            choices = self.get_choices()
            update_option_choices(self._node, self._parameter_name, choices, choices[0])

    def add_input_parameters(self) -> None:
        self._repo_revisions = self.fetch_repo_revisions()
        choices = self.get_choices()

        if not choices:
            self._node.add_node_element(
                ParameterMessage(
                    name="huggingface_repo_parameter_message",
                    title="Huggingface Model Download Required",
                    variant="warning",
                    value=self.get_help_message(),
                )
            )
            return

        self._node.add_parameter(
            Parameter(
                name=self._parameter_name,
                default_value=choices[0] if choices else None,
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=choices,
                    )
                },
                tooltip=self._parameter_name,
            )
        )

    def get_choices(self) -> list[str]:
        return list(map(self._repo_revision_to_key, self._repo_revisions))

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
        base_repo_id, base_revision = self._key_to_repo_revision(value)
        return base_repo_id, base_revision

    def get_help_message(self) -> str:
        download_commands = "\n".join([f"  - `{cmd}`" for cmd in self.get_download_commands()])
        return (
            "📥 How to download the models:\n"
            "1. Setup huggingface-cli as per our docs: https://docs.griptapenodes.com/en/stable/how_to/installs/hugging_face/ \n"
            "2. Download at least one model:\n"
            f"{download_commands}\n"
            "3. Save, close, then open the again workflow. (❌ Do not just reload the page)\n"
            "\n"
            "✅ If successful, you should see a dropdown with the available models.\n"
            "❌ If not successful because download fails then check huggingface-cli docs.\n"
            "❌ If not successful for some other reason then reach out to us on Discord or GitHub.\n"
            "\n"
            "Note: Currently this is the only supported method for downloading models. \n"
            "Hopefully this gets more intuitive (and customizable) soon!\n"
            "- from ✊📼🍜 with ❤️\n"
        )

    @abstractmethod
    def fetch_repo_revisions(self) -> list[tuple[str, str]]: ...

    @abstractmethod
    def get_download_commands(self) -> list[str]: ...

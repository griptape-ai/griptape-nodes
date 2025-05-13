import logging

from diffusers_nodes_library.common.utils.huggingface_utils import list_repo_revisions_in_cache
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


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

    def __init__(self, node: BaseNode, repo_ids: list[str], parameter_name: str = "model"):
        self._node = node
        self._parameter_name = parameter_name
        self._repo_ids = repo_ids
        self._repo_revisions = [
            repo_revision for repo_id in repo_ids for repo_revision in list_repo_revisions_in_cache(repo_id)
        ]

    def add_input_parameters(self) -> None:
        if not self.list_repo_revisions():
            download_commands = "\n".join([f'     huggingface-cli download "{repo}"' for repo in self._repo_ids])
            self._node.add_parameter(
                Parameter(
                    name="message",
                    type="str",
                    default_value=(
                        "⚠️ Model Download Required!\n"
                        "\n"
                        "Why?\n"
                        "  This node requires a huggingface model downloaded on the\n"
                        "  same machine as the engine in order to function. It looks\n"
                        "  for downloaded models in the huggingface cache.\n"
                        "\n"
                        "\n"
                        "How?\n"
                        "  1. Set up huggingface cli following https://docs.griptapenodes.com/en/stable/how_to/installs/hugging_face/\n"
                        "  2. Download at least one of the following models:\n"
                        "\n"
                        f"{download_commands}\n"
                        "\n"
                        "  3. Delete this node and re-add it to the workflow.\n"
                        "  4. Verify you see the model in the dropdown (and you don't see this message anymore!).\n"
                        "\n"
                    ),
                    tooltip="",
                    allowed_modes={},  # type: ignore  # noqa: PGH003
                    ui_options={
                        "is_full_width": True,
                        "multiline": True,
                        "is_read_only": True,
                    },
                )
            )

        self._node.add_parameter(
            Parameter(
                name=self._parameter_name,
                default_value=(self._repo_revision_to_key(self._repo_revisions[0]) if self._repo_revisions else None),
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

    def validate_before_node_run(self) -> list[Exception] | None:
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
            logger.exception("No %s specified", self._parameter_name)
        base_repo_id, base_revision = self._key_to_repo_revision(value)
        return base_repo_id, base_revision

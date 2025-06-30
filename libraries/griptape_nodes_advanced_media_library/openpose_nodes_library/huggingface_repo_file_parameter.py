import logging

from huggingface_hub import scan_cache_dir

from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("openpose")


def list_repo_file_revisions_with_file_in_cache(repo_id: str, file: str) -> list[tuple[str, str]]:
    """Returns a list of (repo_id, revision) tuples matching repo_id in the huggingface cache if it contains file."""
    cache_info = scan_cache_dir()
    results = []
    for repo in cache_info.repos:
        if repo.repo_id == repo_id:
            for revision in repo.revisions:
                if any(f.file_name == file for f in revision.files):
                    results.append((repo.repo_id, revision.commit_hash))  # noqa: PERF401
    return results


class HuggingFaceRepoFileParameter:
    def __init__(
        self,
        node: BaseNode,
        repo_files_by_name: dict[str, tuple[str, str]],
        parameter_name: str = "model",
    ):
        self._node = node
        self._parameter_name = parameter_name
        self._repo_file_revisions = []
        self._repo_files_by_name = repo_files_by_name
        self.refresh_parameters()

    def refresh_parameters(self) -> None:
        num_repo_revisions_before = len(self.list_repo_file_revisions())
        self._repo_file_revisions = self.fetch_repo_file_revisions()
        num_repo_revisions_after = len(self.list_repo_file_revisions())

        if num_repo_revisions_before != num_repo_revisions_after and self._node.get_parameter_by_name(
            self._parameter_name
        ):
            choices = self.get_choices()
            # Simple approach - just update choices without complex option utils
            parameter = self._node.get_parameter_by_name(self._parameter_name)
            if parameter and choices:
                parameter.traits[Options].choices = choices  # type: ignore[reportAttributeAccessIssue]
                parameter.default_value = choices[0]

    def add_input_parameters(self) -> None:
        self._repo_file_revisions = self.fetch_repo_file_revisions()
        choices = self.get_choices()

        if not choices:
            self._node.add_node_element(
                ParameterMessage(
                    name="huggingface_model_parameter_message",
                    title="OpenPose Model Download Required",
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
        return list(self._repo_files_by_name.keys())

    def validate_before_node_run(self) -> list[Exception] | None:
        self.refresh_parameters()
        try:
            self.get_repo_file_revision()
        except Exception as e:
            return [e]

        return None

    def list_repo_file_revisions(self) -> list[tuple[str, str, str]]:
        return self._repo_file_revisions

    def get_repo_file_revision(self) -> tuple[str, str, str]:
        value = self._node.get_parameter_value(self._parameter_name)
        if value is None:
            msg = "Model download required!"
            raise RuntimeError(msg)
        repo, file, revision = self._key_to_repo_file_revision(value)
        return repo, file, revision

    def get_help_message(self) -> str:
        download_commands = "\n".join([f"  - `{cmd}`" for cmd in self.get_download_commands()])
        return (
            "📥 How to download the OpenPose models:\n"
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

    def _repo_file_revision_to_key(self, repo_file_revision: tuple[str, str, str]) -> str:
        repo = repo_file_revision[0]
        file = repo_file_revision[1]
        names = [name for name, (r, f) in self._repo_files_by_name.items() if r == repo and f == file]
        if not names:
            logger.exception("File not found in repo_files_by_name")
            msg = f"File {file} not found in repo_files_by_name for repo {repo}"
            raise RuntimeError(msg)
        if len(names) > 1:
            logger.warning("A repo file has multiple revisions, using the first one")
        return names[0]

    def _key_to_repo_file_revision(self, key: str) -> tuple[str, str, str]:
        repo = self._repo_files_by_name[key][0]
        file = self._repo_files_by_name[key][1]
        repo_file_revisions = self.list_repo_file_revisions()
        # Find the first revision for this repo and file
        revision = None
        for r, f, rev in repo_file_revisions:
            if r == repo and f == file:
                revision = rev
                break
        if revision is None:
            logger.exception("Revision not found for repo and file")
            msg = f"Revision not found for repo {repo} and file {file}"
            raise RuntimeError(msg)
        # Return the repo, file, and revision

        return repo, file, revision

    def fetch_repo_file_revisions(self) -> list[tuple[str, str, str]]:
        return [
            (repo, file, revision)
            for (repo, file) in self._repo_files_by_name.values()
            for (repo, revision) in list_repo_file_revisions_with_file_in_cache(repo, file)
        ]

    def get_download_commands(self) -> list[str]:
        return [f'huggingface-cli download "{repo}" "{file}"' for (repo, file) in self._repo_files_by_name.values()]

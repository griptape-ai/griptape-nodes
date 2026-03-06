import logging
import shlex

from huggingface_hub import hf_hub_download, snapshot_download

logging.basicConfig(
    level=logging.INFO,
)
logger = logging.getLogger("griptape_nodes")

DOWNLOAD_COMMANDS = ["REPLACE_DOWNLOAD_COMMANDS"]


def download_models(commands: list[str]) -> None:
    """Download HuggingFace models from the provided CLI-style commands.

    Args:
        commands (list[str]): A list of huggingface-cli download commands to execute.
            Expected formats:
                huggingface-cli download "repo_id"
                huggingface-cli download "repo_id" "filename"
    """
    for cmd in commands:
        logger.info("Executing: %s", cmd)
        match shlex.split(cmd):
            case ["huggingface-cli", "download", repo_id]:
                snapshot_download(repo_id=repo_id)
            case ["huggingface-cli", "download", repo_id, filename]:
                hf_hub_download(repo_id=repo_id, filename=filename)
            case _:
                msg = f"Unexpected command format: {cmd}"
                raise ValueError(msg)


if __name__ == "__main__":
    download_models(DOWNLOAD_COMMANDS)

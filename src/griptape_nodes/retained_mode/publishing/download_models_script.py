import logging
import shlex

from huggingface_hub import get_token, hf_hub_download, login, snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError

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
    logger.info("Starting model download check (%d command(s))", len(commands))

    token = get_token()
    if token:
        logger.info("HuggingFace token found, logging in...")
        try:
            login(token=token, add_to_git_credential=False)
            logger.info("HuggingFace login succeeded")
        except Exception as e:
            logger.warning("HuggingFace login failed: %s", e)
    else:
        logger.warning("No HF token found — authenticated downloads will fail")

    for i, cmd in enumerate(commands, start=1):
        logger.info("[%d/%d] %s", i, len(commands), cmd)
        match shlex.split(cmd):
            case ["huggingface-cli", "download", repo_id]:
                logger.info("Checking cache for model: %s", repo_id)
                try:
                    snapshot_download(repo_id=repo_id, local_files_only=True)
                    logger.info("Model %s found in cache, skipping download", repo_id)
                except LocalEntryNotFoundError:
                    logger.info("Model %s not in cache, downloading now (this may take a while)...", repo_id)
                    snapshot_download(repo_id=repo_id)
                    logger.info("Model %s download complete", repo_id)
            case ["huggingface-cli", "download", repo_id, filename]:
                logger.info("Checking cache for file %s from %s", filename, repo_id)
                try:
                    hf_hub_download(repo_id=repo_id, filename=filename, local_files_only=True)
                    logger.info("File %s from %s found in cache, skipping download", filename, repo_id)
                except LocalEntryNotFoundError:
                    logger.info("File %s from %s not in cache, downloading now...", filename, repo_id)
                    hf_hub_download(repo_id=repo_id, filename=filename)
                    logger.info("File %s from %s download complete", filename, repo_id)
            case _:
                msg = f"Unexpected command format: {cmd}"
                raise ValueError(msg)

    logger.info("All model downloads complete")


if __name__ == "__main__":
    download_models(DOWNLOAD_COMMANDS)

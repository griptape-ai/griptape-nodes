import logging
from pathlib import Path
from typing import Any

from huggingface_hub import scan_cache_dir  # pyright: ignore[reportMissingImports]
from huggingface_hub.constants import HF_HUB_CACHE

from diffusers_nodes_library.common.utils.pipeline_utils import clear_diffusion_pipeline

logger = logging.getLogger("griptape_nodes")


def list_all_repo_revisions_in_cache() -> list[tuple[str, str]]:
    """Returns a list of (repo_id, revision) tuples for all repos in the huggingface cache."""
    # Use quick scan for diffuser repos, fallback to scan_cache_dir only on errors
    try:
        repos = quick_scan_diffuser_repos(HF_HUB_CACHE)
        results = [(repo["name"], repo["hash"]) for repo in repos]
    except Exception:
        logger.exception("Failed to quick scan diffuser repos, falling back to scan_cache_dir.")
    else:
        return results

    # Fallback to original implementation
    cache_info = scan_cache_dir()
    results = []
    for repo in cache_info.repos:
        for revision in repo.revisions:
            results.append((repo.repo_id, revision.commit_hash))
    return results


def list_repo_revisions_in_cache(repo_id: str) -> list[tuple[str, str]]:
    """Returns a list of (repo_id, revision) tuples matching repo_id in the huggingface cache."""
    # Use quick scan for diffuser repos, fallback to scan_cache_dir only on errors
    try:
        repos = quick_scan_diffuser_repos(HF_HUB_CACHE)
        results = [(repo["name"], repo["hash"]) for repo in repos if repo["name"] == repo_id]
    except Exception:
        logger.exception("Failed to quick scan diffuser repos, falling back to scan_cache_dir.")
    else:
        return results

    # Fallback to original implementation
    cache_info = scan_cache_dir()
    results = []
    for repo in cache_info.repos:
        if repo.repo_id == repo_id:
            for revision in repo.revisions:
                results.append((repo.repo_id, revision.commit_hash))
    return results


def list_repo_revisions_with_file_in_cache(repo_id: str, file: str) -> list[tuple[str, str]]:
    """Returns a list of (repo_id, revision) tuples matching repo_id in the huggingface cache if it contains file."""
    # Use quick scan for diffuser repos, check if file exists
    try:
        repos = quick_scan_diffuser_repos(HF_HUB_CACHE)
        results = [
            (repo["name"], repo["hash"])
            for repo in repos
            if repo["name"] == repo_id and (Path(repo["path"]) / file).exists()
        ]
    except Exception:
        logger.exception("Failed to quick scan diffuser repos, falling back to scan_cache_dir.")
    else:
        return results

    # Fallback to original implementation
    cache_info = scan_cache_dir()
    results = []
    for repo in cache_info.repos:
        if repo.repo_id == repo_id:
            for revision in repo.revisions:
                if any(f.file_name == file for f in revision.files):
                    results.append((repo.repo_id, revision.commit_hash))
    return results


class ModelCache:
    def __init__(self) -> None:
        self._pipeline_cache: dict[str, Any] = {}

    def from_pretrained(self, cls: Any, *args, **kwargs) -> Any:
        return cls.from_pretrained(*args, **kwargs)

    def has_pipeline(self, config_hash: str) -> bool:
        """Check if a pipeline with the given config hash exists in the cache."""
        return config_hash in self._pipeline_cache

    def get_pipeline(self, config_hash: str) -> Any | None:
        """Get cached pipeline by config hash."""
        return self._pipeline_cache.get(config_hash)

    def get_or_build_pipeline(self, config_hash: str, builder_func: Any) -> Any:
        """Get cached pipeline or build new one if not exists."""
        if config_hash not in self._pipeline_cache:
            logger.info("No cached pipeline found with config hash: %s", config_hash)
            # TODO: Support multiple pipelines via Resource Manager: https://github.com/griptape-ai/griptape-nodes/issues/2237
            self.clear_pipeline_cache()
            logger.info("Building new pipeline with config hash: %s", config_hash)
            self._pipeline_cache[config_hash] = builder_func()
        else:
            logger.info("Using cached pipeline with config hash: %s", config_hash)
        return self._pipeline_cache[config_hash]

    def clear_pipeline_cache(self) -> None:
        """Clear all cached pipelines."""
        logger.info("Clearing pipeline cache")
        for config_hash, pipe in self._pipeline_cache.items():
            logger.info("Clearing pipeline with config hash: %s", config_hash)
            clear_diffusion_pipeline(pipe)
        self._pipeline_cache.clear()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get statistics about the pipeline cache."""
        return {
            "cached_pipelines": len(self._pipeline_cache),
            "cache_keys": list(self._pipeline_cache.keys()),
        }


model_cache = ModelCache()


def quick_scan_diffuser_repos(cache_dir: str) -> list[dict[str, Any]]:
    """Quick scan of diffuser repositories in huggingface cache directory.

    Adapted from https://github.com/huggingface/huggingface_hub/issues/1564#issuecomment-1710764361

    Args:
        cache_dir: Path to huggingface cache directory

    Returns:
        List of dictionaries containing repo info with keys:
        - name: Repository name
        - filename: Repository name (alias for name)
        - path: Path to the snapshot folder
        - hash: Commit hash
        - mtime: Modification time
        - model_info: Path to model_info.json file
    """
    diffuser_repos = []
    cache_path = Path(cache_dir)

    if not cache_path.exists():
        return diffuser_repos

    for folder_path in cache_path.iterdir():
        folder = folder_path.name
        if not folder_path.is_dir() or "--" not in folder:
            continue
        _, name = folder.split("--", maxsplit=1)
        name = name.replace("--", "/")

        snapshots_dir = folder_path / "snapshots"
        if not snapshots_dir.exists():
            continue

        snapshots = [p.name for p in snapshots_dir.iterdir() if p.is_dir()]
        if len(snapshots) == 0:
            continue

        commit = snapshots[-1]
        snapshot_path = snapshots_dir / commit

        if (snapshot_path / "hidden").exists():
            continue

        mtime = snapshot_path.stat().st_mtime
        info = snapshot_path / "model_info.json"

        diffuser_repos.append(
            {
                "name": name,
                "filename": name,
                "path": str(snapshot_path),
                "hash": commit,
                "mtime": mtime,
                "model_info": str(info),
            }
        )

    return diffuser_repos

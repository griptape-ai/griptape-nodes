from functools import cache
from typing import Any

from huggingface_hub import scan_cache_dir


def list_repo_revisions_in_cache(repo_id: str) -> list[tuple[str, str]]:
    """Returns a list of (repo_id, revision) tuples matching repo_id in the huggingface cache."""
    cache_info = scan_cache_dir()
    results = []
    for repo in cache_info.repos:
        if repo.repo_id == repo_id:
            for revision in repo.revisions:
                results.append((repo.repo_id, revision.commit_hash))  # noqa: PERF401
    return results


def list_repo_revisions_with_file_in_cache(repo_id: str, file: str) -> list[tuple[str, str]]:
    """Returns a list of (repo_id, revision) tuples matching repo_id in the huggingface cache if it contains file."""
    cache_info = scan_cache_dir()
    results = []
    for repo in cache_info.repos:
        if repo.repo_id == repo_id:
            for revision in repo.revisions:
                if any(f.file_name == file for f in revision.files):
                    results.append((repo.repo_id, revision.commit_hash))  # noqa: PERF401
    return results


class ModelCache:
    @cache  # noqa: B019
    def from_pretrained(self, cls: Any, *args, **kwargs) -> Any:
        return cls.from_pretrained(*args, **kwargs)


model_cache = ModelCache()

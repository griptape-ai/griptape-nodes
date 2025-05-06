from functools import lru_cache
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



class ModelCache:
    @lru_cache(maxsize=None)
    def from_pretrained(self, cls, *args, **kwargs) -> Any:
        return cls.from_pretrained(*args, **kwargs)

model_cache = ModelCache()

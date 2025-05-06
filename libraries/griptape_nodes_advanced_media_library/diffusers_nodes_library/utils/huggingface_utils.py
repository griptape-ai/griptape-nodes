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
    def __init__(self) -> None:
        self._pipes = {}


    @lru_cache(maxsize=None)
    def from_pretrained(self, cls, *args, **kwargs) -> Any:
        return cls.from_pretrained(
            *args,
            **kwargs,
            # local_files_only=True,
        )



     # @classmethod
    # def _get_pipe(cls, base_repo_id: str, base_revision: str, controlnet_repo_id: str, controlnet_revision: str) -> diffusers.FluxControlNetPipeline:
    #     key = (base_repo_id, base_revision, controlnet_repo_id, controlnet_revision)
    #     if key not in cls._pipes:
    #         if base_repo_id not in ("black-forest-labs/FLUX.1-dev", "black-forest-labs/FLUX.1-schnell"):
    #             logger.exception("Repo id %s not supported by %s", base_repo_id, cls.__name__)

    #         controlnet = diffusers.FluxControlNetModel.from_pretrained(
    #             pretrained_model_name_or_path=controlnet_repo_id,
    #             revision=controlnet_revision,
    #             torch_dtype=torch.bfloat16,
    #             local_files_only=True,
    #         )
    #         pipe = diffusers.FluxControlNetPipeline.from_pretrained(
    #             pretrained_model_name_or_path=base_repo_id,
    #             revision=base_revision,
    #             controlnet=[controlnet],
    #             torch_dtype=torch.bfloat16,
    #             local_files_only=True,
    #         )
    #         optimize_flux_pipeline_memory_footprint(pipe)
    #         cls._pipes[key] = pipe

    #     return cls._pipes[key]

model_cache = ModelCache()

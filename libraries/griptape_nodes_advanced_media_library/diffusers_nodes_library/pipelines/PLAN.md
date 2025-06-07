# PLAN: Mirror Hugging Face Diffusers Pipelines into `griptape_nodes_advanced_media_library`

## 1. Objective

Wrap **every** Hugging Face `diffusers` pipeline with a Griptape node so future additions are plug-and-play and no "shoehorning" is required.

## 2. Target Location

```
libraries/
└─ griptape_nodes_advanced_media_library/
   └─ diffusers_nodes_library/
      └─ pipelines/      ← all work goes here
```

## 3. Directories to Replicate

Mirror the tree at\
`https://github.com/huggingface/diffusers/tree/main/src/diffusers/pipelines`\
(full list in Appendix A).

## 4. Deliverables

For **each** upstream `pipeline_*.py`:

1. Directory & filename identical to upstream.
1. Wrapper class named exactly like the upstream pipeline (no "Node" suffix).
1. Companion `parameters.py` plus any helpers.
1. Memory-footprint helper file:\
    • `<pipeline>_pipeline_memory_footprint.py` (contains both optimisation & printing utilities)
1. `__init__.py` containing only a module docstring.
1. JSON registry block appended to `griptape_nodes_library.json`.

## 5. Out of Scope

Anything not required to wrap and register upstream pipelines.

## 6. Implementation Guidelines

### 6.1 Reference Implementations

- `diffusers_nodes_library/pipelines/flux/flux_pipeline.py`
- `diffusers_nodes_library/pipelines/flux/flux_pipeline_parameters.py`
- `diffusers_nodes_library/pipelines/flux/flux_pipeline_memory_footprint.py`
- `diffusers_nodes_library/pipelines/wan/wan_pipeline.py` — good example for pipelines that output or operate on video
- `diffusers_nodes_library/pipelines/flux/flux_fill_pipeline.py` — good example for pipelines that accept images as input

### 6.2 Import Style

- External:
    ```python
    import diffusers
    ```
- Internal (within `diffusers_nodes_library`): absolute paths, e.g.
    ```python
    from diffusers_nodes_library.pipelines.kandinsky3.kandinsky3_pipeline_parameters import (
        Kandinsky3PipelineParameters,
    )  # type: ignore[reportMissingImports]
    ```
    Do **not** use relative imports; add `# type: ignore[reportMissingImports]` where needed.

### 6.3 Wrapper Skeleton (abbreviated)

```python
import logging
import diffusers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.util.model_cache import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.kandinsky3.kandinsky3_pipeline_parameters import (  # type: ignore[reportMissingImports]
    Kandinsky3PipelineParameters,
)
from diffusers_nodes_library.pipelines.kandinsky3.kandinsky3_pipeline_memory_footprint import (  # type: ignore[reportMissingImports]
    optimize_kandinsky3_pipeline_memory_footprint,
    print_kandinsky3_pipeline_memory_footprint,
)
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class Kandinsky3Pipeline(ControlNode):  # same name as upstream
    """Griptape wrapper around diffusers.pipelines.kandinsky3.Kandinsky3Pipeline."""
    ...
```

(See earlier revisions or Flux example for the complete template.)

### 6.4 Parameters Module

Mirror `flux_pipeline_parameters.py`: add parameters, validation, preprocess hooks, preview publishing, etc.

### 6.5 Pipeline-Specific Model Loading

Consult the official diffusers **example scripts** for each pipeline and replicate any special-case steps (e.g., separate VAE loading, custom schedulers, text encoders).

### 6.6 Memory-Footprint Helper

- File: `<pipeline>_pipeline_memory_footprint.py`
- Exposes two functions:\
    • `optimize_<pipeline>_pipeline_memory_footprint` (CUDA-only, `@functools.cache`, moves the pipeline to GPU).
    - Raise `RuntimeError` if CUDA is unavailable.
        • `print_<pipeline>_pipeline_memory_footprint` (invokes `print_pipeline_memory_footprint` with a tailored list of sub-modules).

### 6.7 Registry Entry

Add block:

```jsonc
{
  "class_name": "<PipelineClass>",
  "file_path": "diffusers_nodes_library/pipelines/<dir>/<file>.py",
  "metadata": {
    "category": "image/<dir>",      // or audio/…, video/…
    "description": "Generate … via 🤗 Diffusers.",
    "display_name": "<Human-readable>"
  }
}
```

### 6.8 Logging & Previews

Use `LogParameter` utilities and placeholder previews exactly like the Flux implementation.

### 6.9 CUDA-Only Assumption

All optimization helpers error if `torch.cuda.is_available()` is `False`.
All optimization should just perform `pipe.to(device)` and nothing else initially.

## 7. Milestone Checklist

- [ ] Create directory tree (Appendix A) with docstring-only `__init__.py`.
- [ ] Implement wrapper, parameters & memory-footprint helper.
- [ ] Mirror diffusers example loading quirks (§6.5).
- [ ] Append registry JSON.
- [ ] Run linters & unit tests (existing ones must still pass).
- [ ] Commit & open PR.

______________________________________________________________________

## Appendix A — Directory List

```
allegro/
amused/
animatediff/
audioldm/
audioldm2/
aura_flow/
blip_diffusion/
cogvideo/
cogview3/
cogview4/
consisid/
consistency_models/
controlnet/
controlnet_hunyuandit/
controlnet_sd3/
controlnet_xs/
cosmos/
dance_diffusion/
ddim/
ddpm/
deepfloyd_if/
dit/
easyanimate/
flux/
hidream_image/
hunyuan_video/
hunyuandit/
i2vgen_xl/
kandinsky/
kandinsky2_2/
kandinsky3/
kolors/
latent_consistency_models/
latent_diffusion/
latte/
ledits_pp/
ltx/
lumina/
lumina2/
marigold/
mochi/
musicldm/
omnigen/
pag/
paint_by_example/
pia/
pixart_alpha/
sana/
semantic_stable_diffusion/
shap_e/
stable_audio/
stable_cascade/
stable_diffusion/
stable_diffusion_3/
stable_diffusion_attend_and_excite/
stable_diffusion_diffedit/
stable_diffusion_gligen/
stable_diffusion_k_diffusion/
stable_diffusion_ldm3d/
stable_diffusion_panorama/
stable_diffusion_safe/
stable_diffusion_sag/
stable_diffusion_xl/
stable_video_diffusion/
t2i_adapter/
text_to_video_synthesis/
unclip/
unidiffuser/
visualcloze/
wan/
wuerstchen/
```

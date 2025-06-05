# PLAN: Mirror Hugging Face Diffusers Pipelines into `griptape_nodes_advanced_media_library`

## 1. Objective  
Wrap **every** Hugging Face `diffusers` pipeline with a Griptape node so future additions are plug-and-play and no “shoehorning” is required.

## 2. Target Location
```
libraries/
└─ griptape_nodes_advanced_media_library/
   └─ diffusers_nodes_library/
      └─ pipelines/      ← all work goes here
```

## 3. Directories to Replicate  
Mirror the tree at  
`https://github.com/huggingface/diffusers/tree/main/src/diffusers/pipelines`  
(full list in Appendix A).

## 4. Deliverables
For **each** upstream `pipeline_*.py`:

1. Directory & filename identical to upstream.  
2. Wrapper class named exactly like the upstream pipeline (no “Node” suffix).  
3. Companion `parameters.py` plus any helpers.  
4. Two helpers per family:  
   • `optimize_<pipeline>_pipeline_memory_footprint.py`  
   • `print_<pipeline>_pipeline_memory_footprint.py`  
5. `__init__.py` containing only a module docstring.  
6. JSON registry block appended to `griptape_nodes_library.json`.

## 5. Out of Scope  
Anything not required to wrap and register upstream pipelines.

## 6. Implementation Guidelines  

### 6.1 Reference Implementations  
* `diffusers_nodes_library/pipelines/flux/flux_pipeline.py`  
* `diffusers_nodes_library/pipelines/flux/flux_pipeline_parameters.py`  
* `diffusers_nodes_library/pipelines/flux/flux_pipeline_memory_footprint.py`

### 6.2 Import Style  
* External:  
  ```python
  import diffusers
  ```  
* Internal (within `diffusers_nodes_library`): absolute paths, e.g.  
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
from diffusers_nodes_library.pipelines.kandinsky3.optimize_kandinsky3_pipeline_memory_footprint import (  # type: ignore[reportMissingImports]
    optimize_kandinsky3_pipeline_memory_footprint,
)
from diffusers_nodes_library.pipelines.kandinsky3.print_kandinsky3_pipeline_memory_footprint import (  # type: ignore[reportMissingImports]
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

### 6.6 Optimisation Helper  
* File: `optimize_<pipeline>_pipeline_memory_footprint.py`  
* Use `@functools.cache`, assume CUDA, call `pipe.to(torch.device("cuda"))`, raise `RuntimeError` if CUDA is unavailable.

### 6.7 Memory-Footprint Printer  
* File: `print_<pipeline>_pipeline_memory_footprint.py`  
* Calls `print_pipeline_memory_footprint` with a tailored list of sub-modules.

### 6.8 Registry Entry  
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

### 6.9 Logging & Previews  
Use `LogParameter` utilities and placeholder previews exactly like the Flux implementation.

### 6.10 CUDA-Only Assumption  
All optimisation helpers error if `torch.cuda.is_available()` is `False`.
All optimisation should just perform `pipe.to(device)` and nothing else initially.

## 7. Milestone Checklist
- [ ] Create directory tree (Appendix A) with docstring-only `__init__.py`.  
- [ ] Implement wrapper, parameters, optimisation & print helpers.  
- [ ] Mirror diffusers example loading quirks (§6.5).  
- [ ] Append registry JSON.  
- [ ] Run linters & unit tests (existing ones must still pass).  
- [ ] Commit & open PR.

---

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
deprecated/
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

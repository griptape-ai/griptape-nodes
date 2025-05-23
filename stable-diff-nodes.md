# Stable Diffusion 3.5 Node Implementation Plan

## Overview
Implementation of Griptape nodes for Stable Diffusion 3.5 Large/Medium models from Stability AI. The node will support text-to-image generation with proper model validation, caching, and parameter management following Griptape Node development best practices.

## Architecture Design

### Core Node Structure
- **Base Class**: `ControlNode` (for control flow in generative workflows)
- **Helper Classes**: 
  - `SD35PipelineParameters` - Manages SD3.5-specific parameters
  - `SD35ModelManager` - Handles model loading, caching, and validation
  - `LogParameter` - Progress logging and status updates
- **Model Variants**: Support for both `stable-diffusion-3.5-large` and `stable-diffusion-3.5-medium`

### Node Features
- Text-to-image and image-to-image generation using Diffusers StableDiffusion3Pipeline
- Optional image input (automatically switches between txt2img and img2img modes)
- Model variant selection via dropdown (large/medium)
- Scheduler/sampler selection with multiple options
- Batch generation support with smart output handling
- HuggingFace model validation during node validation
- Progress streaming with step-by-step updates
- Memory optimization options (quantization)
- Proper error handling and user feedback

## File Structure
```
libraries/griptape_nodes_advanced_media_library/diffusers_nodes_library/
├── pipelines/
│   ├── flux/                                # Existing flux nodes
│   └── stabilityai/                         # New Stability AI directory
│       ├── __init__.py
│       ├── stable_diffusion_35/
│       │   ├── __init__.py
│       │   ├── stable_diffusion_35_node.py  # Main node class
│       │   └── helpers/
│       │       ├── __init__.py
│       │       ├── sd35_pipeline_parameters.py    # Parameter helper
│       │       ├── sd35_model_manager.py          # Model management
│       │       └── log_parameter.py               # Logging helper
│       └── [future_stability_models]/       # Space for SDXL, etc.
```

## Detailed TODO List

### Phase 1: Core Infrastructure
- [x] **1.1** Set up directory structure
  - [x] Create `libraries/griptape_nodes_advanced_media_library/diffusers_nodes_library/pipelines/stabilityai/` directory
  - [x] Create `stable_diffusion_35/` subdirectory with `__init__.py`
  - [x] Create `helpers/` subdirectory with `__init__.py`
  - [x] Set up proper imports in parent `stabilityai/__init__.py`

- [x] **1.2** Create base node class structure inheriting from `ControlNode`
  - [x] Set up `__init__` method with helper instantiation
  - [x] Define node metadata (`category = "image"`, `description`)
  - [x] Implement abstract methods from ControlNode

- [x] **1.3** Create `SD35ModelManager` helper class
  - [x] Define model repository mappings (large/medium variants)
  - [x] Implement model caching with `ClassVar[dict[str, Any]]` pattern
  - [x] Add model loading with proper error handling
  - [x] Include memory optimization setup (quantization options)
  - [x] Implement `validate_model_availability()` method

- [x] **1.4** Create `SD35PipelineParameters` helper class
  - [x] Define standard diffusion parameters (prompt, negative_prompt, steps, guidance_scale, etc.)
  - [x] Add SD3.5-specific parameters (max_sequence_length, etc.)
  - [x] Implement parameter validation methods
  - [x] Add `get_pipe_kwargs()` method for pipeline arguments

- [x] **1.5** Register node in library configuration
  - [x] Add node entry to `griptape_nodes_library.json` in the "nodes" array
  - [x] Set `class_name`: "StableDiffusion35Pipeline"
  - [x] Set `file_path`: "diffusers_nodes_library/pipelines/stabilityai/stable_diffusion_35/stable_diffusion_35_node.py"
  - [x] Configure metadata with category, description, and display_name

### Phase 2: Parameter Definition
- [x] **2.1** Core generation parameters
  - [x] `prompt` - Text input with multiline support
  - [x] `negative_prompt` - Optional negative prompting
  - [x] `input_image` - Optional image input (enables img2img mode when provided)
  - [x] `width` / `height` - Image dimensions with validation
  - [x] `num_inference_steps` - Generation steps (default: 28)
  - [x] `guidance_scale` - CFG scale (default: 3.5)
  - [x] `strength` - Denoising strength for img2img (only shown when image input provided)
  - [x] `seed` - Random seed for reproducibility

- [x] **2.2** Model and sampling parameters
  - [x] `model_variant` - Dropdown with Options trait ["large", "medium"]
  - [x] `scheduler` - Scheduler/sampler selection (DPM++, Euler, etc.)
  - [x] `quantization` - Memory optimization options (none/4bit/8bit)
  - [ ] `device` - GPU/CPU selection if needed

- [x] **2.3** Batch generation parameters
  - [x] `num_images_per_prompt` - Batch generation (default: 1)
  - [ ] Dynamic UI logic to hide batch param when set to 1

- [x] **2.4** Advanced parameters (in expandable group)
  - [x] `max_sequence_length` - Text encoder sequence length
  - [x] `generator` - Custom random number generator

- [x] **2.5** Output parameters
  - [x] `output_image` - Single ImageArtifact (when batch=1) or dict of ImageUrlArtifacts (when batch>1)
  - [x] `used_seed` - The actual seed used for generation
  - [x] `logs` - Progress and status information

### Phase 3: Core Logic Implementation
- [x] **3.1** Model validation in `validate_before_node_run()`
  - [x] Check HuggingFace model availability using `huggingface_hub`
  - [x] Validate local cache presence
  - [x] Return descriptive error messages for missing models
  - [x] Suggest download commands if models not found

- [x] **3.2** Main `process()` method implementation
  - [x] Implement as generator for progress updates: `yield lambda: self._process()`
  - [x] Call helper validation methods
  - [x] Load/retrieve cached model via `SD35ModelManager`
  - [x] Detect txt2img vs img2img mode based on input_image presence
  - [x] Set up progress callback for step updates
  - [x] Execute pipeline with proper error handling
  - [x] Handle batch output logic (single ImageArtifact vs dict of ImageUrlArtifacts)
  - [x] Convert PIL outputs appropriately based on batch size

- [x] **3.3** Progress and logging implementation
  - [x] Implement `callback_on_step_end` for progress updates
  - [x] Use `append_value_to_parameter("logs", ...)` for status messages
  - [x] Publish preview updates using `publish_update_to_parameter()`
  - [x] Handle generation completion and final output

### Phase 4: Model Management
- [x] **4.1** HuggingFace integration
  - [x] Use `huggingface_hub.hf_hub_download()` for model files
  - [x] Implement proper repo_id mapping for variants
  - [x] Handle authentication if required (license acceptance)
  - [x] Support `local_files_only=True` for offline operation

- [x] **4.2** Model caching strategy
  - [x] Implement class-level model cache with proper cache keys
  - [x] Include model variant and quantization in cache key
  - [x] Add memory management for large models
  - [x] Implement cache cleanup if needed

- [x] **4.3** Pipeline optimization
  - [x] Apply `optimize_pipeline_memory_footprint()` pattern
  - [x] Support quantization with BitsAndBytesConfig
  - [x] Enable model CPU offloading for memory management
  - [x] Handle CUDA out of memory gracefully

### Phase 5: UI and User Experience
- [ ] **5.1** Parameter UI optimization
  - [ ] Use `ParameterGroup` for advanced settings with `{"expander": True}`
  - [ ] Set appropriate `ui_options` for each parameter type
  - [ ] Add helpful tooltips and parameter descriptions
  - [ ] Implement parameter validation with clear error messages
  - [ ] Dynamic UI for img2img parameters (show `strength` only when image input provided)
  - [ ] Dynamic UI for batch parameters (hide when batch=1)

- [ ] **5.2** Progress feedback
  - [ ] Show generation progress in logs
  - [ ] Display current step information
  - [ ] Provide ETA estimates if possible
  - [ ] Show model loading status

- [ ] **5.3** Error handling and user guidance
  - [ ] Provide clear error messages for common issues
  - [ ] Suggest solutions for model download problems
  - [ ] Guide users through license acceptance process
  - [ ] Handle GPU memory issues gracefully

### Phase 6: Documentation and Examples
- [ ] **6.1** Analyze existing documentation structure
  - [ ] Examine `/docs` folder structure and mkdocs configuration
  - [ ] Identify existing node documentation patterns
  - [ ] Suggest appropriate placement for SD3.5 node documentation
  - [ ] Review existing examples and workflow documentation

- [ ] **6.2** Code documentation
  - [ ] Add comprehensive docstrings
  - [ ] Document helper class interfaces
  - [ ] Include parameter descriptions
  - [ ] Add troubleshooting notes

- [ ] **6.3** User documentation and examples
  - [ ] Create SD3.5 node documentation page for mkdocs
  - [ ] Document HuggingFace CLI download process: `huggingface-cli download stabilityai/stable-diffusion-3.5-large`
  - [ ] Create basic text-to-image workflow examples
  - [ ] Create image-to-image workflow examples
  - [ ] Document batch generation workflows
  - [ ] Provide configuration examples and best practices
  - [ ] Include performance optimization tips and memory management
  - [ ] Add troubleshooting guide for common issues

## Technical Specifications

### Dependencies
```python
# Core dependencies
torch >= 2.0.0
diffusers >= 0.30.0
transformers >= 4.44.0
huggingface_hub >= 0.20.0

# Optional for quantization
bitsandbytes >= 0.43.0
```

### Model Repository Mapping
```python
MODEL_REPOS = {
    "large": "stabilityai/stable-diffusion-3.5-large",
    "medium": "stabilityai/stable-diffusion-3.5-medium"
}
```

### Default Parameter Values
```python
DEFAULT_PARAMS = {
    "num_inference_steps": 28,
    "guidance_scale": 3.5,
    "width": 1024,
    "height": 1024,
    "max_sequence_length": 512,
    "model_variant": "large",
    "num_images_per_prompt": 1,
    "strength": 0.7,  # For img2img mode
    "scheduler": "DPMSolverMultistepScheduler"  # Default scheduler
}
```

### Scheduler Options
```python
AVAILABLE_SCHEDULERS = [
    "DPMSolverMultistepScheduler",
    "EulerDiscreteScheduler", 
    "EulerAncestralDiscreteScheduler",
    "DDIMScheduler",
    "LMSDiscreteScheduler",
    "PNDMScheduler",
    "UniPCMultistepScheduler"
]
```

### Library Registration Entry
```json
{
  "class_name": "StableDiffusion35Pipeline",
  "file_path": "diffusers_nodes_library/pipelines/stabilityai/stable_diffusion_35/stable_diffusion_35_node.py",
  "metadata": {
    "category": "image/stabilityai",
    "description": "Generate Images with Stable Diffusion 3.5 (Large/Medium) via 🤗 Diffusers. Supports both text-to-image and image-to-image generation.",
    "display_name": "Stable Diffusion 3.5"
  }
}
```

## Implementation Notes

### Following Griptape Node Patterns
- Use `ControlNode` base class for generative workflow integration
- Implement helper classes for parameter management (Fat Helper, Thin Node pattern)
- Follow caching patterns with `ClassVar` for model storage
- Use validation patterns for model availability checking
- Implement progress streaming with generators and callbacks
- Apply memory optimization patterns for large models

### Error Handling Strategy
- Validate models before node execution
- Provide clear error messages for missing dependencies
- Handle GPU memory issues gracefully
- Guide users through model download and setup process

### Future Extensibility
- Design for easy addition of new model variants
- Prepare for ControlNet integration as separate node
- Support for additional specialized pipelines (inpainting, etc.)
- Integration with other Stability AI models

## Implementation Priorities
Based on user requirements:
1. ✅ **img2img functionality**: Integrated in main node with optional image input
2. ✅ **ControlNet support**: Separate node (not in this implementation)
3. ✅ **Scheduler selection**: Multiple scheduler options exposed
4. ✅ **Model variants**: Official HuggingFace cache variants only (large/medium)
5. ✅ **Batch generation**: Support with smart output handling (single vs dict)
6. ✅ **Memory optimization**: Quantization options included
7. ✅ **Documentation**: Full mkdocs integration with HuggingFace CLI instructions

## Key Implementation Details
- **Dual Mode Operation**: Automatically detect txt2img vs img2img based on input_image presence
- **Smart Output Handling**: Single ImageArtifact for batch=1, dict of ImageUrlArtifacts for batch>1
- **Dynamic UI**: Hide/show parameters based on context (strength for img2img, batch controls)
- **HuggingFace Integration**: Use cached models like flux node pattern, validate availability
- **Documentation**: Comprehensive mkdocs integration with CLI download instructions 
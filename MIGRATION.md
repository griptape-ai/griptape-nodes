# v0.64.0

This guide documents the removal of deprecated nodes from the Griptape Nodes Advanced Media Library in version 0.64.0.

## Overview

Version 0.64.0 removes deprecated nodes that were previously marked for removal. These nodes have been replaced with more flexible and powerful alternatives, primarily the new Diffusion Pipeline Builder system.

### Affected Libraries

| Library                               | Version |
| ------------------------------------- | ------- |
| Griptape Nodes Advanced Media Library | 0.64.0  |

## Removed Nodes and Replacements

### Image Processing Nodes

| Display Name  | Replacement                                                                                                                                          |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Desaturate    | `Grayscale Image` from Griptape Nodes Library<br/>Location: `Image/Edit/Grayscale Image`<br/>[See details ↓](#for-image-processing-nodes)            |
| Gaussian Blur | `Gaussian Blur Image` from Griptape Nodes Library<br/>Location: `Image/Effects/Gaussian Blur Image`<br/>[See details ↓](#for-image-processing-nodes) |
| Rescale Image | `Rescale Image` from Griptape Nodes Library<br/>Location: `Image/Edit/Rescale Image`<br/>[See details ↓](#for-image-processing-nodes)                |

### Diffusion Pipeline Nodes

All diffusion pipeline nodes have been replaced with the **Diffusion Pipeline Builder** system, which provides a more flexible and composable approach to working with diffusion models.

**Replacement:** Use `Diffusion Pipeline Builder` + `Generate Image (Diffusion Pipeline)` nodes

**Documentation:** https://docs.griptapenodes.com/en/stable/nodes/advanced_media_library/diffusion_pipelines/

**[See migration details ↓](#for-diffusion-pipeline-nodes)**

#### Flux Family

| Display Name      | Category        |
| ----------------- | --------------- |
| Flux              | `image/flux`    |
| Flux Fill         | `image/flux`    |
| Flux Kontext      | `image/flux`    |
| Flux ICEdit       | `image/flux`    |
| Flux Post Upscale | `image/upscale` |

#### Flux ControlNet

| Display Name        | Category                |
| ------------------- | ----------------------- |
| Flux CN Union       | `image/flux/controlnet` |
| Flux CN Union Pro   | `image/flux/controlnet` |
| Flux CN Union Pro 2 | `image/flux/controlnet` |

#### Stable Diffusion Family

| Display Name                       | Category                                   |
| ---------------------------------- | ------------------------------------------ |
| Stable Diffusion                   | `image/stable_diffusion`                   |
| Stable Diffusion 3                 | `image/stable_diffusion_3`                 |
| Stable Diffusion Attend and Excite | `image/stable_diffusion_attend_and_excite` |
| Stable Diffusion DiffEdit          | `image/stable_diffusion_diffedit`          |

#### aMUSEd Family

| Display Name   | Category       |
| -------------- | -------------- |
| aMUSEd         | `image/amused` |
| aMUSEd Img2Img | `image/amused` |
| aMUSEd Inpaint | `image/amused` |

#### Video Generation

| Display Name | Category        |
| ------------ | --------------- |
| Allegro      | `video/allegro` |
| Wan T2V      | `video/wan`     |
| Wan I2V      | `video/wan`     |
| Wan V2V      | `video/wan`     |
| Wan VACE     | `video/wan`     |

#### Audio Generation

| Display Name | Category          |
| ------------ | ----------------- |
| AudioLDM     | `audio/audioldm`  |
| AudioLDM 2   | `audio/audioldm2` |

#### Other Pipelines

| Display Name | Category          |
| ------------ | ----------------- |
| Würstchen    | `image/würstchen` |

### Upscaling Nodes

| Display Name | Replacement                                                                                                                       |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| SPAN Upscale | Use `Diffusion Pipeline Builder` + `Generate Image (Diffusion Pipeline)` nodes<br/>[See details ↓](#for-diffusion-pipeline-nodes) |

### LoRA Nodes

| Display Name   | Replacement                                                                                                                 |
| -------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Flux LoRA File | `Load LoRA` from Griptape Nodes Advanced Media Library<br/>Location: `LoRAs/Load LoRA`<br/>[See details ↓](#for-lora-nodes) |

## Removed Dependencies

The following Python package dependencies were removed from the Advanced Media Library:

- `beautifulsoup4`
- `protobuf` (duplicate entries consolidated)
- `sentencepiece`
- `spandrel`
- `torchaudio`
- `ftfy`

## Migration Steps

### For Image Processing Nodes

Replace deprecated nodes with these specific nodes from the main Griptape Nodes Library:

1. **Desaturate** → Replace with **`Grayscale Image`**

    - Location: `Image/Edit/Grayscale Image`
    - Same functionality: converts color images to grayscale

1. **Gaussian Blur** → Replace with **`Gaussian Blur Image`**

    - Location: `Image/Effects/Gaussian Blur Image`
    - Same functionality: applies gaussian blur with configurable radius

1. **Rescale Image** → Replace with **`Rescale Image`**

    - Location: `Image/Edit/Rescale Image`
    - Same functionality: resizes images with various interpolation methods

The replacement nodes have equivalent functionality and similar parameters.

### For Diffusion Pipeline Nodes

1. Identify all deprecated diffusion pipeline nodes in your flows
1. Replace each with a combination of:
    - **Diffusion Pipeline Builder** node (configure your model and settings)
    - **Generate Image (Diffusion Pipeline)** node (run the generation)
1. Refer to the [Diffusion Pipeline documentation](https://docs.griptapenodes.com/en/stable/nodes/advanced_media_library/diffusion_pipelines/) for detailed examples
1. The new system offers more flexibility with:
    - Composable pipeline components
    - Reusable pipeline configurations
    - Better control over model loading and optimization

### For LoRA Nodes

1. Replace **Flux LoRA File** with the new `Load LoRA` node
1. The new node is available under `LoRAs/Load LoRA` in the Advanced Media Library
1. Connect the output to your Diffusion Pipeline Builder

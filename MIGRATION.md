# v0.64.0

This guide documents the removal of deprecated nodes from the Griptape Nodes Advanced Media Library in version 0.64.0.

## Overview

Version 0.64.0 removes deprecated nodes that were previously marked for removal. These nodes have been replaced with more flexible and powerful alternatives, primarily the new Diffusion Pipeline Builder system.

## Removed Nodes and Replacements

### Image Processing Nodes

| Removed Node            | Display Name  | Replacement                                                                                         |
| ----------------------- | ------------- | --------------------------------------------------------------------------------------------------- |
| `GrayscaleConvertImage` | Desaturate    | `Grayscale Image` from Griptape Nodes Library<br/>Location: `Image/Edit/Grayscale Image`            |
| `GaussianBlurImage`     | Gaussian Blur | `Gaussian Blur Image` from Griptape Nodes Library<br/>Location: `Image/Effects/Gaussian Blur Image` |
| `RescaleImage`          | Rescale Image | `Rescale Image` from Griptape Nodes Library<br/>Location: `Image/Edit/Rescale Image`                |

### Diffusion Pipeline Nodes

All diffusion pipeline nodes have been replaced with the **Diffusion Pipeline Builder** system, which provides a more flexible and composable approach to working with diffusion models.

**Replacement:** Use `Diffusion Pipeline Builder` + `Generate Image (Diffusion Pipeline)` nodes

**Documentation:** https://docs.griptapenodes.com/en/stable/nodes/advanced_media_library/diffusion_pipelines/

#### Flux Family

| Removed Node                | Display Name      | Category        |
| --------------------------- | ----------------- | --------------- |
| `FluxPipeline`              | Flux              | `image/flux`    |
| `FluxFillPipeline`          | Flux Fill         | `image/flux`    |
| `FluxKontextPipeline`       | Flux Kontext      | `image/flux`    |
| `DiptychFluxFillPipeline`   | Flux ICEdit       | `image/flux`    |
| `TilingFluxImg2ImgPipeline` | Flux Post Upscale | `image/upscale` |

#### Flux ControlNet

| Removed Node                        | Display Name        | Category                |
| ----------------------------------- | ------------------- | ----------------------- |
| `UnionFluxControlNetPipeline`       | Flux CN Union       | `image/flux/controlnet` |
| `UnionProFluxControlNetPipeline`    | Flux CN Union Pro   | `image/flux/controlnet` |
| `UnionProTwoFluxControlNetPipeline` | Flux CN Union Pro 2 | `image/flux/controlnet` |

#### Stable Diffusion Family

| Removed Node                             | Display Name                       | Category                                   |
| ---------------------------------------- | ---------------------------------- | ------------------------------------------ |
| `StableDiffusionPipeline`                | Stable Diffusion                   | `image/stable_diffusion`                   |
| `StableDiffusion3Pipeline`               | Stable Diffusion 3                 | `image/stable_diffusion_3`                 |
| `StableDiffusionAttendAndExcitePipeline` | Stable Diffusion Attend and Excite | `image/stable_diffusion_attend_and_excite` |
| `StableDiffusionDiffeditPipeline`        | Stable Diffusion DiffEdit          | `image/stable_diffusion_diffedit`          |

#### aMUSEd Family

| Removed Node            | Display Name   | Category       |
| ----------------------- | -------------- | -------------- |
| `AmusedPipeline`        | aMUSEd         | `image/amused` |
| `AmusedImg2ImgPipeline` | aMUSEd Img2Img | `image/amused` |
| `AmusedInpaintPipeline` | aMUSEd Inpaint | `image/amused` |

#### Video Generation

| Removed Node              | Display Name | Category        |
| ------------------------- | ------------ | --------------- |
| `AllegroPipeline`         | Allegro      | `video/allegro` |
| `WanPipeline`             | Wan T2V      | `video/wan`     |
| `WanImageToVideoPipeline` | Wan I2V      | `video/wan`     |
| `WanVideoToVideoPipeline` | Wan V2V      | `video/wan`     |
| `WanVacePipeline`         | Wan VACE     | `video/wan`     |

#### Audio Generation

| Removed Node        | Display Name | Category          |
| ------------------- | ------------ | ----------------- |
| `AudioldmPipeline`  | AudioLDM     | `audio/audioldm`  |
| `Audioldm2Pipeline` | AudioLDM 2   | `audio/audioldm2` |

#### Other Pipelines

| Removed Node                 | Display Name | Category          |
| ---------------------------- | ------------ | ----------------- |
| `WuerstchenCombinedPipeline` | Würstchen    | `image/würstchen` |

### Upscaling Nodes

| Removed Node | Display Name | Replacement                                                                    |
| ------------ | ------------ | ------------------------------------------------------------------------------ |
| `TilingSPAN` | SPAN Upscale | Use `Diffusion Pipeline Builder` + `Generate Image (Diffusion Pipeline)` nodes |

### LoRA Nodes

| Removed Node       | Display Name   | Replacement                                                                            |
| ------------------ | -------------- | -------------------------------------------------------------------------------------- |
| `FluxLoraFromFile` | Flux LoRA File | `Load LoRA` from Griptape Nodes Advanced Media Library<br/>Location: `LoRAs/Load LoRA` |

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

1. **`GrayscaleConvertImage` (Desaturate)** → Replace with **`Grayscale Image`**

    - Location: `Image/Edit/Grayscale Image`
    - Same functionality: converts color images to grayscale

1. **`GaussianBlurImage` (Gaussian Blur)** → Replace with **`Gaussian Blur Image`**

    - Location: `Image/Effects/Gaussian Blur Image`
    - Same functionality: applies gaussian blur with configurable radius

1. **`RescaleImage` (Rescale Image)** → Replace with **`Rescale Image`**

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

1. Replace `FluxLoraFromFile` with the new `Load LoRA` node
1. The new node is available under `LoRAs/Load LoRA` in the Advanced Media Library
1. Connect the output to your Diffusion Pipeline Builder

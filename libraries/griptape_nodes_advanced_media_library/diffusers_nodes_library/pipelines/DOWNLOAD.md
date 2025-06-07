# Hugging Face Models Download Guide

This document contains commands to download all Hugging Face models referenced in the diffusers pipeline parameter classes.

## Check Space Requirements (Without Downloading)

To check how much space all models will require without actually downloading them:

```bash
# Install huggingface-hub if not already installed
pip install huggingface-hub

# Check space for all models
python -c "
from huggingface_hub import HfApi
api = HfApi()
models = [
    'ali-vilab/EasyAnimateV5-12b-zh-InP',
    'ali-vilab/EasyAnimateV5-7b-zh',
    'ali-vilab/i2vgen-xl',
    'Alpha-VLLM/Lumina-Next-SFT',
    'Alpha-VLLM/Lumina-Next-T2I',
    'amused/amused-256',
    'amused/amused-512',
    'anhnct/Gligen_Text_Image',
    'BestWishYsh/ConsisID-preview',
    'black-forest-labs/FLUX.1-dev',
    'black-forest-labs/FLUX.1-Fill-dev',
    'black-forest-labs/FLUX.1-schnell',
    'CompVis/ldm-text2im-large-256',
    'CompVis/stable-diffusion-v1-4',
    'cosmos-video/cosmos-1.0',
    'cvssp/audioldm-l-full',
    'cvssp/audioldm-s-full',
    'cvssp/audioldm-s-full-v2',
    'cvssp/audioldm2',
    'cvssp/audioldm2-large',
    'cvssp/audioldm2-music',
    'damo-vilab/text-to-video-ms-1.7b',
    'DeepFloyd/IF-I-L-v1.0',
    'DeepFloyd/IF-I-M-v1.0',
    'DeepFloyd/IF-I-XL-v1.0',
    'Efficient-Large-Model/Sana_1600M_1024px_BF16_diffusers',
    'Efficient-Large-Model/Sana_1600M_1024px_diffusers',
    'Efficient-Large-Model/Sana_600M_512px_diffusers',
    'emilianJR/epiCRealism',
    'facebook/DiT-B-2-256',
    'facebook/DiT-L-2-256',
    'facebook/DiT-XL-2-256',
    'facebook/DiT-XL-2-512',
    'fal/AuraFlow',
    'fal/AuraFlow-v0.1',
    'Fantasy-Studio/Paint-by-Example',
    'genmo/mochi-1-preview',
    'google/ddpm-bedroom-256',
    'google/ddpm-celebahq-256',
    'google/ddpm-church-256',
    'google/ddpm-cifar10-32',
    'google/if-xl',
    'harmonai/dance-diffusion-ddim-1024',
    'harmonai/maestro-150k',
    'HiDream/HiDiffusion',
    'hunyuanvideo-community/HunyuanVideo',
    'InstantX/SD3-Controlnet-Canny',
    'InstantX/SD3-Controlnet-Pose',
    'InstantX/SD3-Controlnet-Tile',
    'Intel/ldm3d',
    'Intel/ldm3d-4c',
    'kakaobrain/karlo-v1-alpha',
    'kakaobrain/karlo-v1-alpha-image-variations',
    'kandinsky-community/kandinsky-2-1',
    'kandinsky-community/kandinsky-2-1-inpaint',
    'kandinsky-community/kandinsky-2-2-decoder',
    'kandinsky-community/kandinsky-2-2-decoder-inpaint',
    'kandinsky-community/kandinsky-3',
    'Kwai-Kolors/Kolors',
    'latent-consistency/lcm-lora-sdv1-5',
    'Lightricks/LTX-Video',
    'lllyasviel/sd-controlnet-canny',
    'lllyasviel/sd-controlnet-depth',
    'lllyasviel/sd-controlnet-hed',
    'lllyasviel/sd-controlnet-normal',
    'lllyasviel/sd-controlnet-openpose',
    'lllyasviel/sd-controlnet-scribble',
    'lllyasviel/sd-controlnet-seg',
    'masterful/gligen-1-4-generation-text-box',
    'masterful/gligen-1-4-inpainting-text-box',
    'maxin-cn/Latte-1',
    'openai/clip-vit-large-patch14',
    'openai/diffusers-cd_bedroom256_lpips',
    'openai/diffusers-cd_imagenet64_l2',
    'openai/shap-e',
    'PixArt-alpha/PixArt-Alpha-DMD-XL-2-512x512',
    'PixArt-alpha/PixArt-XL-2-1024-MS',
    'PixArt-alpha/PixArt-XL-2-512x512',
    'prs-eth/marigold-depth-lcm-v1-0',
    'prs-eth/marigold-depth-v1-0',
    'rhymes-ai/Allegro',
    'runwayml/stable-diffusion-v1-5',
    'Salesforce/blipdiffusion',
    'SG161222/Realistic_Vision_V5.1_noVAE',
    'SG161222/Realistic_Vision_V6.0_B1_noVAE',
    'Shitao/OmniGen-v1',
    'SimianLuo/LCM_Dreamshaper_v7',
    'stabilityai/sdxl-turbo',
    'stabilityai/stable-audio-open-1.0',
    'stabilityai/stable-cascade',
    'stabilityai/stable-diffusion-2',
    'stabilityai/stable-diffusion-2-1',
    'stabilityai/stable-diffusion-2-1-base',
    'stabilityai/stable-diffusion-3-medium-diffusers',
    'stabilityai/stable-diffusion-3.5-large',
    'stabilityai/stable-diffusion-3.5-medium',
    'stabilityai/stable-diffusion-xl-base-1.0',
    'stabilityai/stable-video-diffusion-img2vid',
    'stabilityai/stable-video-diffusion-img2vid-xt',
    'Tencent-Hunyuan/HunyuanDiT-Diffusers',
    'Tencent-Hunyuan/HunyuanDiT-v1.1-Diffusers',
    'Tencent-Hunyuan/HunyuanDiT-v1.2-ControlNet-Diffusers-Canny',
    'Tencent-Hunyuan/HunyuanDiT-v1.2-ControlNet-Diffusers-Depth',
    'Tencent-Hunyuan/HunyuanDiT-v1.2-ControlNet-Diffusers-Pose',
    'Tencent-Hunyuan/HunyuanDiT-v1.2-Diffusers',
    'tencent/HunyuanVideo',
    'TencentARC/t2iadapter_canny_sd15v2',
    'TencentARC/t2iadapter_color_sd14v1',
    'TencentARC/t2iadapter_depth_sd15v2',
    'TencentARC/t2iadapter_openpose_sd15v2',
    'TencentARC/t2iadapter_seg_sd15v2',
    'TencentARC/t2iadapter_sketch_sd15v2',
    'thu-ml/unidiffuser-v1',
    'THUDM/CogVideoX-2b',
    'THUDM/CogVideoX-5b',
    'THUDM/CogView3-Plus-3B',
    'THUDM/CogView4-6B',
    'ucsd-reach/musicldm',
    'UmerHA/Testing-ConrolNet-Canny-Diff',
    'UmerHA/Testing-SD-V1.5-ControlNet-XS-Canny',
    'vishnunkumar/controlnet-xs-depth-mid',
    'Wan-AI/Wan2.1-I2V-14B-480P-Diffusers',
    'Wan-AI/Wan2.1-I2V-14B-720P-Diffusers',
    'Wan-AI/Wan2.1-T2V-1.3B-Diffusers',
    'Wan-AI/Wan2.1-T2V-14B-Diffusers',
    'warp-ai/wuerstchen-v2-aesthetic',
    'warp-ai/wuerstchen-v2-base',
    'warp-ai/wuerstchen-v2-interpolated'
]

total_size = 0
print('Checking model sizes...')
for model in models:
    try:
        # Request model info with file metadata to get individual file sizes
        info = api.model_info(model, files_metadata=True)
        # Sum up sizes from all files in the repository
        model_size = sum(f.size or 0 for f in info.siblings)
        size_gb = model_size / (1024**3)
        total_size += size_gb
        print(f'{model}: {size_gb:.2f} GB')
    except Exception as e:
        print(f'{model}: Error - {str(e)[:100]}...')

print(f'\nTotal estimated space required: {total_size:.2f} GB')
"
```

## Download All Models

To download all models to your local Hugging Face cache:

```bash
# Install huggingface-hub if not already installed
pip install huggingface-hub

# Download all models
huggingface-cli download ali-vilab/EasyAnimateV5-12b-zh-InP
huggingface-cli download ali-vilab/EasyAnimateV5-7b-zh
huggingface-cli download ali-vilab/i2vgen-xl
huggingface-cli download Alpha-VLLM/Lumina-Next-SFT
huggingface-cli download Alpha-VLLM/Lumina-Next-T2I
huggingface-cli download amused/amused-256
huggingface-cli download amused/amused-512
huggingface-cli download anhnct/Gligen_Text_Image
huggingface-cli download BestWishYsh/ConsisID-preview
huggingface-cli download black-forest-labs/FLUX.1-dev
huggingface-cli download black-forest-labs/FLUX.1-Fill-dev
huggingface-cli download black-forest-labs/FLUX.1-schnell
huggingface-cli download CompVis/ldm-text2im-large-256
huggingface-cli download CompVis/stable-diffusion-v1-4
huggingface-cli download cosmos-video/cosmos-1.0
huggingface-cli download cvssp/audioldm-l-full
huggingface-cli download cvssp/audioldm-s-full
huggingface-cli download cvssp/audioldm-s-full-v2
huggingface-cli download cvssp/audioldm2
huggingface-cli download cvssp/audioldm2-large
huggingface-cli download cvssp/audioldm2-music
huggingface-cli download damo-vilab/text-to-video-ms-1.7b
huggingface-cli download DeepFloyd/IF-I-L-v1.0
huggingface-cli download DeepFloyd/IF-I-M-v1.0
huggingface-cli download DeepFloyd/IF-I-XL-v1.0
huggingface-cli download Efficient-Large-Model/Sana_1600M_1024px_BF16_diffusers
huggingface-cli download Efficient-Large-Model/Sana_1600M_1024px_diffusers
huggingface-cli download Efficient-Large-Model/Sana_600M_512px_diffusers
huggingface-cli download emilianJR/epiCRealism
huggingface-cli download facebook/DiT-B-2-256
huggingface-cli download facebook/DiT-L-2-256
huggingface-cli download facebook/DiT-XL-2-256
huggingface-cli download facebook/DiT-XL-2-512
huggingface-cli download fal/AuraFlow
huggingface-cli download fal/AuraFlow-v0.1
huggingface-cli download Fantasy-Studio/Paint-by-Example
huggingface-cli download genmo/mochi-1-preview
huggingface-cli download google/ddpm-bedroom-256
huggingface-cli download google/ddpm-celebahq-256
huggingface-cli download google/ddpm-church-256
huggingface-cli download google/ddpm-cifar10-32
huggingface-cli download google/if-xl
huggingface-cli download harmonai/dance-diffusion-ddim-1024
huggingface-cli download harmonai/maestro-150k
huggingface-cli download HiDream/HiDiffusion
huggingface-cli download hunyuanvideo-community/HunyuanVideo
huggingface-cli download InstantX/SD3-Controlnet-Canny
huggingface-cli download InstantX/SD3-Controlnet-Pose
huggingface-cli download InstantX/SD3-Controlnet-Tile
huggingface-cli download Intel/ldm3d
huggingface-cli download Intel/ldm3d-4c
huggingface-cli download kakaobrain/karlo-v1-alpha
huggingface-cli download kakaobrain/karlo-v1-alpha-image-variations
huggingface-cli download kandinsky-community/kandinsky-2-1
huggingface-cli download kandinsky-community/kandinsky-2-1-inpaint
huggingface-cli download kandinsky-community/kandinsky-2-2-decoder
huggingface-cli download kandinsky-community/kandinsky-2-2-decoder-inpaint
huggingface-cli download kandinsky-community/kandinsky-3
huggingface-cli download Kwai-Kolors/Kolors
huggingface-cli download latent-consistency/lcm-lora-sdv1-5
huggingface-cli download Lightricks/LTX-Video
huggingface-cli download lllyasviel/sd-controlnet-canny
huggingface-cli download lllyasviel/sd-controlnet-depth
huggingface-cli download lllyasviel/sd-controlnet-hed
huggingface-cli download lllyasviel/sd-controlnet-normal
huggingface-cli download lllyasviel/sd-controlnet-openpose
huggingface-cli download lllyasviel/sd-controlnet-scribble
huggingface-cli download lllyasviel/sd-controlnet-seg
huggingface-cli download masterful/gligen-1-4-generation-text-box
huggingface-cli download masterful/gligen-1-4-inpainting-text-box
huggingface-cli download maxin-cn/Latte-1
huggingface-cli download openai/clip-vit-large-patch14
huggingface-cli download openai/diffusers-cd_bedroom256_lpips
huggingface-cli download openai/diffusers-cd_imagenet64_l2
huggingface-cli download openai/shap-e
huggingface-cli download PixArt-alpha/PixArt-Alpha-DMD-XL-2-512x512
huggingface-cli download PixArt-alpha/PixArt-XL-2-1024-MS
huggingface-cli download PixArt-alpha/PixArt-XL-2-512x512
huggingface-cli download prs-eth/marigold-depth-lcm-v1-0
huggingface-cli download prs-eth/marigold-depth-v1-0
huggingface-cli download rhymes-ai/Allegro
huggingface-cli download runwayml/stable-diffusion-v1-5
huggingface-cli download Salesforce/blipdiffusion
huggingface-cli download SG161222/Realistic_Vision_V5.1_noVAE
huggingface-cli download SG161222/Realistic_Vision_V6.0_B1_noVAE
huggingface-cli download Shitao/OmniGen-v1
huggingface-cli download SimianLuo/LCM_Dreamshaper_v7
huggingface-cli download stabilityai/sdxl-turbo
huggingface-cli download stabilityai/stable-audio-open-1.0
huggingface-cli download stabilityai/stable-cascade
huggingface-cli download stabilityai/stable-diffusion-2
huggingface-cli download stabilityai/stable-diffusion-2-1
huggingface-cli download stabilityai/stable-diffusion-2-1-base
huggingface-cli download stabilityai/stable-diffusion-3-medium-diffusers
huggingface-cli download stabilityai/stable-diffusion-3.5-large
huggingface-cli download stabilityai/stable-diffusion-3.5-medium
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0
huggingface-cli download stabilityai/stable-video-diffusion-img2vid
huggingface-cli download stabilityai/stable-video-diffusion-img2vid-xt
huggingface-cli download Tencent-Hunyuan/HunyuanDiT-Diffusers
huggingface-cli download Tencent-Hunyuan/HunyuanDiT-v1.1-Diffusers
huggingface-cli download Tencent-Hunyuan/HunyuanDiT-v1.2-ControlNet-Diffusers-Canny
huggingface-cli download Tencent-Hunyuan/HunyuanDiT-v1.2-ControlNet-Diffusers-Depth
huggingface-cli download Tencent-Hunyuan/HunyuanDiT-v1.2-ControlNet-Diffusers-Pose
huggingface-cli download Tencent-Hunyuan/HunyuanDiT-v1.2-Diffusers
huggingface-cli download tencent/HunyuanVideo
huggingface-cli download TencentARC/t2iadapter_canny_sd15v2
huggingface-cli download TencentARC/t2iadapter_color_sd14v1
huggingface-cli download TencentARC/t2iadapter_depth_sd15v2
huggingface-cli download TencentARC/t2iadapter_openpose_sd15v2
huggingface-cli download TencentARC/t2iadapter_seg_sd15v2
huggingface-cli download TencentARC/t2iadapter_sketch_sd15v2
huggingface-cli download thu-ml/unidiffuser-v1
huggingface-cli download THUDM/CogVideoX-2b
huggingface-cli download THUDM/CogVideoX-5b
huggingface-cli download THUDM/CogView3-Plus-3B
huggingface-cli download THUDM/CogView4-6B
huggingface-cli download ucsd-reach/musicldm
huggingface-cli download UmerHA/Testing-ConrolNet-Canny-Diff
huggingface-cli download UmerHA/Testing-SD-V1.5-ControlNet-XS-Canny
huggingface-cli download vishnunkumar/controlnet-xs-depth-mid
huggingface-cli download Wan-AI/Wan2.1-I2V-14B-480P-Diffusers
huggingface-cli download Wan-AI/Wan2.1-I2V-14B-720P-Diffusers
huggingface-cli download Wan-AI/Wan2.1-T2V-1.3B-Diffusers
huggingface-cli download Wan-AI/Wan2.1-T2V-14B-Diffusers
huggingface-cli download warp-ai/wuerstchen-v2-aesthetic
huggingface-cli download warp-ai/wuerstchen-v2-base
huggingface-cli download warp-ai/wuerstchen-v2-interpolated
```

## Download Specific Model Categories

### Text-to-Image Models

```bash
# FLUX models
huggingface-cli download black-forest-labs/FLUX.1-dev
huggingface-cli download black-forest-labs/FLUX.1-schnell

# Stable Diffusion models
huggingface-cli download runwayml/stable-diffusion-v1-5
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0
huggingface-cli download stabilityai/stable-diffusion-3.5-medium
```

### Video Generation Models

```bash
huggingface-cli download tencent/HunyuanVideo
huggingface-cli download hunyuanvideo-community/HunyuanVideo
huggingface-cli download THUDM/CogVideoX-5b
huggingface-cli download genmo/mochi-1-preview
huggingface-cli download rhymes-ai/Allegro
```

### Audio Generation Models

```bash
huggingface-cli download cvssp/audioldm2
huggingface-cli download stabilityai/stable-audio-open-1.0
huggingface-cli download ucsd-reach/musicldm
```

## Notes

- **Space Requirements**: These models collectively require several hundred GB of storage space. Run the space check command first to estimate total requirements.
- **Authentication**: Some models may require authentication. You may need to log in with `huggingface-cli login` and accept model licenses on the Hugging Face website.
- **Gated Models**: Some models are gated and require approval from the model creators.
- **Cache Location**: Models are downloaded to your Hugging Face cache directory (usually `~/.cache/huggingface/hub/`).
- **Selective Download**: Consider downloading only the models you need for your specific use cases instead of all models at once.

## Alternative Download Method

You can also use Python to download models programmatically:

```python
from huggingface_hub import snapshot_download

# Download a specific model
model_name = "black-forest-labs/FLUX.1-schnell"
snapshot_download(repo_id=model_name)
```

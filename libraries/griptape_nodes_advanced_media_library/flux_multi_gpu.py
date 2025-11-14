import torch
import gc
from diffusers import FluxPipeline, AutoencoderKL
from diffusers.models import AutoModel
from diffusers.image_processor import VaeImageProcessor

def flush():
    """Clear GPU memory"""
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_max_memory_allocated()
    torch.cuda.reset_peak_memory_stats()

def main():
    prompt = "a photo of a dog with cat-like look"
    model_id = "black-forest-labs/FLUX.1-dev"
    
    # Step 1: Load text encoders and encode prompt
    print("Loading text encoders...")
    pipeline = FluxPipeline.from_pretrained(
        model_id,
        transformer=None,
        vae=None,
        device_map="balanced",  # Distribute text encoders across GPUs
        max_memory={0: "16GB", 1: "16GB", 2: "16GB", 3: "16GB"},
        torch_dtype=torch.bfloat16
    )
    
    print("Encoding prompts...")
    with torch.no_grad():
        prompt_embeds, pooled_prompt_embeds, text_ids = pipeline.encode_prompt(
            prompt=prompt, 
            prompt_2=None, 
            max_sequence_length=512
        )
    
    # Step 2: Clear text encoders from memory
    print("Clearing text encoders from memory...")
    del pipeline.text_encoder
    del pipeline.text_encoder_2
    del pipeline.tokenizer
    del pipeline.tokenizer_2
    del pipeline
    flush()
    
    # Step 3: Load transformer and run denoising
    print("Loading transformer...")
    transformer = AutoModel.from_pretrained(
        model_id,
        subfolder="transformer",
        device_map="auto",  # Auto-distribute across all 4 GPUs
        torch_dtype=torch.bfloat16
    )
    
    # Check how transformer is distributed
    print(f"Transformer device map: {transformer.hf_device_map}")
    
    pipeline = FluxPipeline.from_pretrained(
        model_id,
        text_encoder=None,
        text_encoder_2=None,
        tokenizer=None,
        tokenizer_2=None,
        vae=None,
        transformer=transformer,
        torch_dtype=torch.bfloat16
    )
    
    print("Running denoising...")
    height, width = 768, 1360
    latents = pipeline(
        prompt_embeds=prompt_embeds,
        pooled_prompt_embeds=pooled_prompt_embeds,
        num_inference_steps=50,
        guidance_scale=3.5,
        height=height,
        width=width,
        output_type="latent",
    ).images
    
    # Step 4: Clear transformer from memory
    print("Clearing transformer from memory...")
    del pipeline.transformer
    del pipeline
    flush()
    
    # Step 5: Load VAE and decode
    print("Loading VAE and decoding...")
    vae = AutoencoderKL.from_pretrained(
        model_id, 
        subfolder="vae", 
        torch_dtype=torch.bfloat16
    ).to("cuda:0")  # VAE fits on single GPU
    
    vae_scale_factor = 2 ** (len(vae.config.block_out_channels))
    image_processor = VaeImageProcessor(vae_scale_factor=vae_scale_factor)
    
    with torch.no_grad():
        latents = FluxPipeline._unpack_latents(latents, height, width, vae_scale_factor)
        latents = (latents / vae.config.scaling_factor) + vae.config.shift_factor
        image = vae.decode(latents, return_dict=False)[0]
        image = image_processor.postprocess(image, output_type="pil")
    
    # Save result
    image[0].save("flux_output.png")
    print("Image saved as flux_output.png")

if __name__ == "__main__":
    main()
import torch
import gc
from diffusers import FluxPipeline, AutoencoderKL
from diffusers.models import AutoModel
from diffusers.image_processor import VaeImageProcessor
from transformers import BitsAndBytesConfig

def flush():
    """Clear GPU memory"""
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_max_memory_allocated()
    torch.cuda.reset_peak_memory_stats()

def main():
    # 4 different prompts for batch generation
    prompts = [
        "a photo of a dog with cat-like look",
        "a majestic lion in the savanna at sunset",
        "a colorful parrot perched on a tropical branch",
        "a sleek black panther in the jungle"
    ]
    
    model_id = "black-forest-labs/FLUX.1-schnell"
    batch_size = len(prompts)
    
    # Step 1: Load text encoders and encode all prompts
    print(f"Loading text encoders for {batch_size} prompts...")
    pipeline = FluxPipeline.from_pretrained(
        model_id,
        transformer=None,
        vae=None,
        device_map="balanced",
        max_memory={0: "16GB", 1: "16GB", 2: "16GB", 3: "16GB"},
        torch_dtype=torch.bfloat16
    )
    
    print(f"Encoding {batch_size} prompts in batch...")
    with torch.no_grad():
        # Encode all prompts at once
        prompt_embeds_list = []
        pooled_prompt_embeds_list = []
        
        for prompt in prompts:
            p_embeds, pooled_p_embeds, text_ids = pipeline.encode_prompt(
                prompt=prompt, 
                prompt_2=None, 
                max_sequence_length=256
            )
            prompt_embeds_list.append(p_embeds)
            pooled_prompt_embeds_list.append(pooled_p_embeds)
        
        # Stack into batches
        prompt_embeds = torch.cat(prompt_embeds_list, dim=0)
        pooled_prompt_embeds = torch.cat(pooled_prompt_embeds_list, dim=0)
    
    print(f"Batch shape: {prompt_embeds.shape}")
    
    # Step 2: Clear text encoders from memory
    print("Clearing text encoders from memory...")
    del pipeline.text_encoder
    del pipeline.text_encoder_2
    del pipeline.tokenizer
    del pipeline.tokenizer_2
    del pipeline
    flush()
    
    # Step 3: Load transformer with 8-bit quantization
    print("Loading transformer with 8-bit quantization...")
    quantization_config = BitsAndBytesConfig(
        load_in_8bit=True,
        llm_int8_threshold=6.0,
        llm_int8_has_fp16_weight=False,
    )
    
    transformer = AutoModel.from_pretrained(
        model_id,
        subfolder="transformer",
        device_map="auto",
        quantization_config=quantization_config,
        torch_dtype=torch.bfloat16
    )
    
    # Compile model for speed
    print("Compiling model for optimized inference...")
    transformer = torch.compile(transformer, mode="reduce-overhead", fullgraph=False)
    
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
    
    print(f"Running denoising for {batch_size} images (first run includes compilation)...")
    height, width = 512, 512
    
    # Generate all 4 images in one batch
    latents = pipeline(
        prompt_embeds=prompt_embeds,
        pooled_prompt_embeds=pooled_prompt_embeds,
        num_inference_steps=2,
        guidance_scale=0.0,
        height=height,
        width=width,
        output_type="latent",
    ).images
    
    print(f"Generated {latents.shape[0]} latent images")
    
    # Step 4: Clear transformer from memory
    print("Clearing transformer from memory...")
    del pipeline.transformer
    del pipeline
    flush()
    
    # Step 5: Load VAE and decode all images
    print("Loading VAE and decoding all images...")
    vae = AutoencoderKL.from_pretrained(
        model_id, 
        subfolder="vae", 
        torch_dtype=torch.bfloat16
    ).to("cuda:0")
    
    vae_scale_factor = 2 ** (len(vae.config.block_out_channels))
    image_processor = VaeImageProcessor(vae_scale_factor=vae_scale_factor)
    
    with torch.no_grad():
        latents = FluxPipeline._unpack_latents(latents, height, width, vae_scale_factor)
        latents = (latents / vae.config.scaling_factor) + vae.config.shift_factor
        
        # Decode in batch
        images = vae.decode(latents, return_dict=False)[0]
        images = image_processor.postprocess(images, output_type="pil")
    
    # Save all results
    print(f"\n✅ Saving {len(images)} images...")
    for i, (image, prompt) in enumerate(zip(images, prompts)):
        filename = f"flux_output_{i+1}.png"
        image.save(filename)
        print(f"  • {filename}: {prompt[:50]}...")
    
    print(f"\n🚀 Generated {batch_size} images!")
    print("Note: First generation includes compilation time. Run again for true speed.")

if __name__ == "__main__":
    main()
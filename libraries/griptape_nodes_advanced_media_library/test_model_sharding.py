"""
Test script for diffusers model sharding across multiple GPUs.
Based on: https://huggingface.co/docs/diffusers/en/training/distributed_inference
"""

import torch
from diffusers import DiffusionPipeline

print("=" * 80)
print("Testing Diffusers Model Sharding with device_map")
print("=" * 80)

# Check available GPUs
num_gpus = torch.cuda.device_count()
print(f"\nAvailable GPUs: {num_gpus}")

if num_gpus == 0:
    print("No GPUs available, cannot test model sharding")
    exit(1)

for i in range(num_gpus):
    print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")

# Example 1: Load pipeline with device_map="balanced"
print("\n" + "=" * 80)
print("Example 1: Loading pipeline with device_map='balanced'")
print("=" * 80)

try:
    pipe = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
        device_map="balanced",  # Automatically distribute across GPUs
    )
    print("✓ Pipeline loaded successfully with device_map='balanced'")

    # Show where components are placed
    if hasattr(pipe, 'hf_device_map'):
        print("\nDevice map:")
        for component, device in pipe.hf_device_map.items():
            print(f"  {component}: {device}")

    # Generate an image to test
    print("\nGenerating test image...")
    image = pipe(
        "A photo of a cat",
        num_inference_steps=20,
    ).images[0]
    print("✓ Image generated successfully")

except Exception as e:
    print(f"✗ Error with device_map='balanced': {e}")

# Example 2: Load pipeline with custom max_memory
print("\n" + "=" * 80)
print("Example 2: Loading pipeline with custom max_memory")
print("=" * 80)

try:
    # Define max memory per device
    max_memory = {i: "10GB" for i in range(num_gpus)}
    max_memory["cpu"] = "30GB"

    print(f"\nMax memory config: {max_memory}")

    pipe = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
        device_map="auto",  # Use 'auto' with custom max_memory
        max_memory=max_memory,
    )
    print("✓ Pipeline loaded successfully with custom max_memory")

    # Show where components are placed
    if hasattr(pipe, 'hf_device_map'):
        print("\nDevice map:")
        for component, device in pipe.hf_device_map.items():
            print(f"  {component}: {device}")

except Exception as e:
    print(f"✗ Error with custom max_memory: {e}")

# Example 3: Load pipeline with sequential offloading
print("\n" + "=" * 80)
print("Example 3: Loading pipeline with sequential CPU offload")
print("=" * 80)

try:
    pipe = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
        device_map="sequential",  # Sequential offloading
    )
    print("✓ Pipeline loaded successfully with device_map='sequential'")

    # Show where components are placed
    if hasattr(pipe, 'hf_device_map'):
        print("\nDevice map:")
        for component, device in pipe.hf_device_map.items():
            print(f"  {component}: {device}")

except Exception as e:
    print(f"✗ Error with device_map='sequential': {e}")

print("\n" + "=" * 80)
print("Test complete")
print("=" * 80)

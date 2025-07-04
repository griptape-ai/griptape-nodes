import time
import torch
import onnxruntime as ort
from diffusers import AutoencoderKL
from claude_vae_to_onnx_export import ONNXVAEDecoder

# Load both models
vae_pytorch = AutoencoderKL.from_pretrained(
    "black-forest-labs/FLUX.1-Kontext-dev",
    subfolder="vae"
).to("cuda").eval()
vae_onnx = ONNXVAEDecoder("flux_kontext_vae_decoder.onnx").to("cuda")

# Benchmark
latents = torch.randn(1, 16, 128, 128).to("cuda")  # Example latent tensor

# PyTorch
start = time.time()
for _ in range(10):
    print("Decoding with PyTorch VAE...")
    _ = vae_pytorch.decode(latents, return_dict=False)[0]
pytorch_time = time.time() - start

# ONNX
start = time.time()
for _ in range(10):
    print("Decoding with ONNX VAE...")
    _ = vae_onnx.decode(latents, return_dict=False)[0]
onnx_time = time.time() - start

print(f"PyTorch: {pytorch_time:.3f}s")
print(f"ONNX: {onnx_time:.3f}s")
print(f"Speedup: {pytorch_time/onnx_time:.2f}x")
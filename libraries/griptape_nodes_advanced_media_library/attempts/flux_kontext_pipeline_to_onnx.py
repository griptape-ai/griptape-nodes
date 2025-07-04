import diffusers
import torch
from optimum.exporters.onnx import main_export

# Download the model (bfloat16 or float16 is fine)
pipe = diffusers.FluxKontextPipeline.from_pretrained(
    "black-forest-labs/FLUX.1-Kontext-dev",
    local_files_only=True
    torch_dtype=torch.bfloat16,
)

# Export pipeline (UNet, VAE, text encoder)
pipe.save_pretrained("flux_kontext_onnx")

# Optional: can use CLI too
# optimum-cli export onnx --model runwayml/stable-diffusion-v1-5 onnx_sd15
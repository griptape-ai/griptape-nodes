import diffusers
import torch
from pathlib import Path
from optimum.exporters.onnx import main_export
from optimum.exporters.onnx import OnnxConfig
from optimum.utils import NormalizedConfig  # <—— add this import


class FluxTransformerOnnxConfig(OnnxConfig):
    NORMALIZED_CONFIG_CLASS = NormalizedConfig

    @property
    def inputs(self):
        return {
            "sample": {0: "batch", 2: "height", 3: "width"},
            "timestep": {0: "batch"},
            "encoder_hidden_states": {0: "batch", 1: "seq"},
        }

    @property
    def outputs(self):
        return {"latent": {0: "batch", 2: "height", 3: "width"}}


# Download the model (bfloat16 or float16 is fine)
config = diffusers.AutoConfig.from_pretrained("black-forest-labs/FLUX.1-Kontext-dev", local_files_only=True)
# pipe = diffusers.FluxKontextPipeline.from_pretrained(
#     pretrained_model_name_or_path="black-forest-labs/FLUX.1-Kontext-dev",
#     local_files_only=True,
#     torch_dtype=torch.bfloat16,
# )


out_dir = Path("flux_kontext_onnx")
submodels = {
    "transformer": pipe.transformer,
    "vae_encoder": pipe.vae.encoder,
    "vae_decoder": pipe.vae.decoder,
    "text_encoder": pipe.text_encoder,
    "text_encoder_2": pipe.text_encoder_2,
    "image_encoder": pipe.image_encoder,
}

custom_cfgs = {"transformer": FluxTransformerOnnxConfig(pipe.transformer.config)}

main_export(
    model_name_or_path="black-forest-labs/FLUX.1-Kontext-dev",
    preprocessor=None,  # we only want the weights
    model=submodels,
    output=out_dir,
    custom_onnx_configs=custom_cfgs,
    device="cuda",
    opset=18,  # first opset with complete SD support :contentReference[oaicite:4]{index=4}
    monolith=False,  # keep sub‑graphs separate
)


# Optional: can use CLI too
# optimum-cli export onnx --model runwayml/stable-diffusion-v1-5 onnx_sd15


###### https://huggingface.co/docs/optimum/en/exporters/onnx/usage_guides/export_a_model#custom-export-of-transformers-models

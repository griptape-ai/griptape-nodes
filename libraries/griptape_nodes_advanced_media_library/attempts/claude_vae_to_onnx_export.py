import torch
import torch.nn as nn
from diffusers import AutoencoderKL
from pathlib import Path
import numpy as np

# Configuration
MODEL_ID = "black-forest-labs/FLUX.1-Kontext-dev"
ONNX_PATH = "./flux_kontext_vae.onnx"
OPSET_VERSION = 17  # Use a recent opset for better operator support


def load_vae_model(model_id):
    """Load the VAE model from the Flux pipeline"""
    print(f"Loading VAE from {model_id}...")
    vae = AutoencoderKL.from_pretrained(
        model_id,
        subfolder="vae",
        torch_dtype=torch.float32,  # Use fp32 for ONNX export
    )
    vae.eval()
    return vae


def create_vae_wrapper(vae):
    """Create a wrapper that handles both encoding and decoding"""

    class VAEWrapper(nn.Module):
        def __init__(self, vae):
            super().__init__()
            self.vae = vae

        def forward(self, sample, mode="decode"):
            if mode == "decode":
                # Decode latents to image
                decoded = self.vae.decode(sample, return_dict=False)[0]
                return decoded
            else:
                # Encode image to latents
                encoded = self.vae.encode(sample, return_dict=False)[0]
                return encoded

    return VAEWrapper(vae)


def export_vae_decoder(vae, output_path):
    """Export only the decoder part of the VAE"""
    print("Exporting VAE decoder to ONNX...")

    # Create dummy input for decoder
    # Flux uses 16-channel latents
    batch_size = 1
    latent_channels = 16
    latent_height = 128  # Adjust based on your needs
    latent_width = 128

    dummy_latent = torch.randn(batch_size, latent_channels, latent_height, latent_width, dtype=torch.float32)

    # Export decoder
    with torch.no_grad():
        torch.onnx.export(
            vae.decoder,
            dummy_latent,
            output_path,
            input_names=["latent_sample"],
            output_names=["sample"],
            dynamic_axes={
                "latent_sample": {0: "batch", 2: "height", 3: "width"},
                "sample": {0: "batch", 2: "height", 3: "width"},
            },
            opset_version=OPSET_VERSION,
            do_constant_folding=True,
        )

    print(f"Decoder exported to {output_path}")


def export_vae_encoder(vae, output_path):
    """Export only the encoder part of the VAE"""
    print("Exporting VAE encoder to ONNX...")

    # Create a wrapper that properly handles the VAE encoding
    class EncoderWrapper(nn.Module):
        def __init__(self, vae):
            super().__init__()
            self.vae = vae

        def forward(self, x):
            # Use the VAE's encode method to get the distribution
            dist = self.vae.encode(x, return_dict=False)[0]
            # Return only the mean for ONNX
            return dist.mean

    # Create wrapper model
    encoder_wrapper = EncoderWrapper(vae)
    encoder_wrapper.eval()

    # Create dummy input for encoder
    batch_size = 1
    channels = 3
    height = 1024  # Adjust based on your needs
    width = 1024

    dummy_image = torch.randn(batch_size, channels, height, width, dtype=torch.float32)

    # Export encoder
    with torch.no_grad():
        torch.onnx.export(
            encoder_wrapper,
            dummy_image,
            output_path,
            input_names=["sample"],
            output_names=["latent_mean"],
            dynamic_axes={
                "sample": {0: "batch", 2: "height", 3: "width"},
                "latent_mean": {0: "batch", 2: "height", 3: "width"},
            },
            opset_version=OPSET_VERSION,
            do_constant_folding=True,
        )

    print(f"Encoder exported to {output_path}")


def verify_onnx_model(onnx_path, vae, mode="decoder"):
    """Verify the ONNX model produces similar outputs to PyTorch"""
    import onnxruntime as ort

    print(f"Verifying ONNX {mode}...")

    # Create ONNX session
    ort_session = ort.InferenceSession(onnx_path)

    # Create test input
    if mode == "decoder":
        test_input = torch.randn(1, 16, 64, 64, dtype=torch.float32)
        pytorch_output = vae.decode(test_input, return_dict=False)[0]
        onnx_input = {"latent_sample": test_input.numpy()}
    else:
        test_input = torch.randn(1, 3, 512, 512, dtype=torch.float32)
        # Encoder returns DiagonalGaussianDistribution, we need the mean
        distribution = vae.encode(test_input, return_dict=False)[0]
        pytorch_output = distribution.mean  # or distribution.sample() for stochastic
        onnx_input = {"sample": test_input.numpy()}

    # Run ONNX inference
    onnx_output = ort_session.run(None, onnx_input)[0]

    # Compare outputs
    pytorch_output_np = pytorch_output.detach().numpy()
    max_diff = np.max(np.abs(pytorch_output_np - onnx_output))
    mean_diff = np.mean(np.abs(pytorch_output_np - onnx_output))

    print(f"Max difference: {max_diff}")
    print(f"Mean difference: {mean_diff}")
    print(f"Output shapes match: {pytorch_output_np.shape == onnx_output.shape}")

    return max_diff < 1e-3  # Tolerance for fp32


def main():
    """Main conversion function"""
    # Load VAE
    vae = load_vae_model(MODEL_ID)

    # Export decoder (most commonly used)
    decoder_path = Path(ONNX_PATH).parent / "flux_kontext_vae_decoder.onnx"
    export_vae_decoder(vae, str(decoder_path))

    # Export encoder (if needed)
    encoder_path = Path(ONNX_PATH).parent / "flux_kontext_vae_encoder.onnx"
    export_vae_encoder(vae, str(encoder_path))

    # Verify exports
    decoder_ok = verify_onnx_model(str(decoder_path), vae, "decoder")
    encoder_ok = verify_onnx_model(str(encoder_path), vae, "encoder")

    if decoder_ok and encoder_ok:
        print("\n✅ Both encoder and decoder exported successfully!")
    else:
        print("\n⚠️ Export completed but verification found differences")

    return decoder_path, encoder_path


# Usage with custom ONNX session in diffusers pipeline
class ONNXVAEDecoder:
    """Wrapper to use ONNX VAE decoder in diffusers pipeline"""

    def __init__(self, onnx_path):
        import onnxruntime as ort

        self.session = ort.InferenceSession(onnx_path)
        self.config = None  # Add config if needed

    def decode(self, latents, return_dict=False):
        """Decode latents using ONNX model"""
        output = self.session.run(None, {"latent_sample": latents.cpu().numpy()})[0]

        output_tensor = torch.from_numpy(output)

        if return_dict:
            from diffusers.models.autoencoders.vae import DecoderOutput

            return DecoderOutput(sample=output_tensor)
        return (output_tensor,)

    def to(self, device):
        """Compatibility method"""
        return self


class ONNXVAEEncoder:
    """Wrapper to use ONNX VAE encoder in diffusers pipeline"""

    def __init__(self, onnx_path):
        import onnxruntime as ort

        self.session = ort.InferenceSession(onnx_path)

    def encode(self, sample, return_dict=False):
        """Encode images using ONNX model"""
        # ONNX encoder outputs only the mean of the latent distribution
        output = self.session.run(None, {"sample": sample.cpu().numpy()})[0]

        output_tensor = torch.from_numpy(output)

        # Create a mock distribution object for compatibility
        class SimpleDist:
            def __init__(self, mean):
                self.mean = mean
                self.mode = mean  # For compatibility
                self.std = torch.ones_like(mean)  # Mock std
                self.var = torch.ones_like(mean)  # Mock variance

            def sample(self):
                # For deterministic behavior, just return mean
                # For stochastic, you'd add noise: mean + torch.randn_like(mean) * std
                return self.mean

        dist = SimpleDist(output_tensor)

        if return_dict:
            from diffusers.models.autoencoders.vae import AutoencoderKLOutput

            return AutoencoderKLOutput(latent_dist=dist)
        return (dist,)

    def to(self, device):
        """Compatibility method"""
        return self


if __name__ == "__main__":
    # Run the conversion
    decoder_path, encoder_path = main()

    # Example of using ONNX VAE in pipeline
    print("\nExample usage in pipeline:")
    print(f"""
    from diffusers import FluxKontextPipeline
    
    # Load pipeline without VAE
    pipe = FluxKontextPipeline.from_pretrained(
        "{MODEL_ID}",
        vae=None,  # Don't load PyTorch VAE
        torch_dtype=torch.bfloat16
    )
    
    # Replace with ONNX VAE
    pipe.vae = ONNXVAEDecoder("{decoder_path}")
    
    # Use pipeline as normal with kontext conditioning
    image = pipe(
        prompt="A beautiful landscape",
        kontext_conditioning=kontext_embeds,  # Your kontext embeddings
        height=1024,
        width=1024,
        num_inference_steps=50,  # Kontext-dev typically uses more steps
    ).images[0]
    """)

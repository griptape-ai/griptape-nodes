# pyright: reportMissingImports=false
# pyright: reportOptionalMemberAccess=false
import base64
import re
import uuid
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import folder_paths
import numpy as np
import requests
import torch
from jinja2 import Template
from PIL import Image, ImageOps, ImageSequence

from griptape_nodes.retained_mode.griptape_nodes import logger


def to_pascal_case(string) -> str:
    # First, replace any non-word character with a space
    string = re.sub(r"[^\w\s]", " ", string)

    # Replace underscores with spaces
    string = string.replace("_", " ")

    # Split the string into words
    words = string.split()

    # Capitalize the first letter of each word after the first word
    return "".join(word.capitalize() for word in words)


def construct_base_url(base_url: str, port: int) -> str:
    # Parse the base_url
    parsed_url = urlparse(base_url)

    # If there's no scheme (http:// or https://), add http://
    if not parsed_url.scheme:
        parsed_url = parsed_url._replace(scheme="http")

    # Replace the port
    parsed_url = parsed_url._replace(netloc=f"{parsed_url.hostname}:{port}")

    # Reconstruct the URL without any path
    return urlunparse(parsed_url._replace(path=""))


def get_models(engine, base_url, port) -> list[str]:
    reconstructed_base_url = construct_base_url(base_url, port)

    if engine == "ollama":
        api_url = f"{reconstructed_base_url}/api/tags"
    elif engine == "lmstudio":
        api_url = f"{reconstructed_base_url}/v1/models"
    else:
        msg = f"Unsupported engine: {engine}"
        raise ValueError(msg)

    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()

        if engine == "ollama":
            models = [model["name"] for model in response.json().get("models", [])]
        else:  # lmstudio
            models = [model["id"] for model in response.json().get("data", [])]
    except Exception as e:
        error_msg = f"Failed to fetch models from {engine.capitalize()}: {e}"
        logger.error(error_msg)
        return []
    else:
        return models


def replace_with_context(template_string, context) -> str:
    template = Template(template_string)
    result = template.render(**context)
    return result


def get_prompt_text(string_prompt, input_string) -> str:
    template = Template(string_prompt)
    return template.render(input_string=input_string)


def image_path_to_output(image_path) -> tuple[torch.Tensor, torch.Tensor]:
    img: Image.Image | None = Image.open(image_path)
    if img is None:
        msg = f"Failed to open image at path: {image_path}"
        raise ValueError(msg)

    output_images = []
    output_masks = []
    for i in ImageSequence.Iterator(img):
        ti = ImageOps.exif_transpose(i)
        if ti.mode == "I":
            ti = ti.point(lambda i: i * (1 / 255))
        image = ti.convert("RGB")
        image = np.array(image).astype(np.float32) / 255.0
        image = torch.from_numpy(image)[None,]
        if "A" in i.getbands():
            mask = np.array(i.getchannel("A")).astype(np.float32) / 255.0
            mask = 1.0 - torch.from_numpy(mask)
        else:
            mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")
        output_images.append(image)
        output_masks.append(mask.unsqueeze(0))

    if len(output_images) > 1:
        output_image = torch.cat(output_images, dim=0)
        output_mask = torch.cat(output_masks, dim=0)
    else:
        output_image = output_images[0]
        output_mask = output_masks[0]
    return (output_image, output_mask)


def convert_tensor_batch_to_base_64(image_batch) -> list[str] | None:
    if isinstance(image_batch, torch.Tensor):
        # Ensure it's on CPU
        image_batch = image_batch.cpu()

        # If it's a 3D tensor, add a batch dimension
        if image_batch.dim() == 3:  # noqa: PLR2004
            image_batch = image_batch.unsqueeze(0)

        # Permute dimensions if necessary (from B, C, H, W to B, H, W, C)
        if image_batch.shape[1] < image_batch.shape[3]:
            image_batch = image_batch.permute(0, 2, 3, 1)

        # Scale to 0-255 and convert to uint8
        image_batch = (255.0 * image_batch).clamp(0, 255).numpy().astype(np.uint8)

        base64_images = []
        for img_array in image_batch:
            img = Image.fromarray(img_array)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
            base64_images.append(base64_image)

        success_msg = f"Converted {len(base64_images)} images to base64"
        logger.info(success_msg)
        return base64_images
    return None


def load_audio_from_artifact(audio_artifact) -> dict:
    import torchaudio

    # Get the audio data from the value property
    audio_data = audio_artifact.value

    # If the value is base64 encoded, decode it
    if isinstance(audio_data, str):
        audio_data = base64.b64decode(audio_data)

    # Create a BytesIO object from the audio data
    audio_buffer = BytesIO(audio_data)

    # Use torchaudio to load the audio
    waveform, sample_rate = torchaudio.load(audio_buffer)

    # Create the AUDIO dictionary expected by ComfyUI
    audio_output = {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}

    return audio_output


def save_images_to_disk(images) -> list[Path]:
    image_paths = []
    output_dir = Path(folder_paths.get_temp_directory())

    for _batch_number, image in enumerate(images):
        i = 255.0 * image.cpu().numpy()
        img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
        filepath = output_dir / (uuid.uuid4().hex + ".png")
        img.save(filepath)
        image_paths.append(filepath)
    return image_paths


def convert_tensor_to_base_64(image) -> list[str]:
    if not isinstance(image, torch.Tensor):
        msg = "Input must be a PyTorch tensor"
        raise TypeError(msg)

    # Ensure it's on CPU
    image = image.cpu()

    # Handle different tensor shapes
    if image.dim() == 2:  #  noqa: PLR2004 Single channel image
        image = image.unsqueeze(0).unsqueeze(0)
    elif image.dim() == 3:  # noqa: PLR2004 Single image with channels
        image = image.unsqueeze(0)  # Add batch dim
    elif image.dim() == 4:  # noqa: PLR2004 Batch of images or complex structure
        pass  # Already in the right format
    else:
        msg = f"Unexpected tensor shape: {image.shape}"
        raise ValueError(msg)

    # Permute dimensions if necessary (from B, C, H, W to B, H, W, C)
    if image.shape[1] < image.shape[3]:
        image = image.permute(0, 2, 3, 1)

    # Scale to 0-255 and convert to uint8
    image = (255.0 * image).clamp(0, 255).to(torch.uint8).numpy()

    base64_images = []
    for img_array in image.reshape(-1, *image.shape[-3:]):
        # Handle single-channel masks
        if img_array.shape[-1] == 1:
            # Squeeze out the channel dimension and convert to 'L' (8-bit pixels, black and white)
            squeezed_img = img_array.squeeze()
            img = Image.fromarray(squeezed_img, mode="L")
        else:
            # Regular RGB/RGBA images
            img = Image.fromarray(img_array)

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
        base64_images.append(base64_image)

    return base64_images

import logging

import numpy as np
import PIL.Image
import spandrel  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
import torch.nn.functional  # type: ignore[reportMissingImports]
from huggingface_hub import hf_hub_download
from PIL.Image import Image

logger = logging.getLogger("spandrel_nodes_library")


class SpandrelPipeline:
    def __init__(self, model: spandrel.ModelDescriptor) -> None:
        self.model = model

    @classmethod
    def from_hf_file(cls, repo_id: str, revision: str, filename: str) -> "SpandrelPipeline":
        if repo_id != "skbhadra/ClearRealityV1" or filename != "4x-ClearRealityV1.pth":
            logger.exception("Unsupported (repo_id: %s filename: %s) pair", repo_id, filename)

        model_path = hf_hub_download(
            repo_id=repo_id,
            revision=revision,
            filename=filename,
            local_files_only=True,
        )

        sd = torch.load(model_path, map_location="cpu")
        model = spandrel.ModelLoader().load_from_state_dict(sd).eval()

        return SpandrelPipeline(model)

    def __call__(self, input_image_pil: Image, *, scale: float) -> Image:
        model = self.model

        # Will fail if not RGB (like RGBA), I think it actually just
        # needs to be 3 channels, not sure what will happen if you
        # do for example BurGeR.
        input_image_pil = input_image_pil.convert("RGB")

        device = torch.device("cpu")

        input_tensor = pil_to_tensor(input_image_pil)
        input_tensor = input_tensor.movedim(-1, -3)
        input_tensor.to(device)

        with torch.no_grad():
            output_tensor = model(input_tensor)

        # TODO(dylan): DO NOT SMOOTH the output (or make configurable!)
        output_tensor = torch.nn.functional.interpolate(
            output_tensor,
            # This 1/4 scale factor specifically to account for 4x-ClearRealityV1.pth,
            # which changes the image size by 4x. Totally forgot about this. need to mention to amaru...
            scale_factor=(scale / 4.0),
            mode="bilinear",
            align_corners=False,
        )
        output_tensor = torch.clamp(output_tensor.movedim(-3, -1), min=0, max=1.0)
        output_image_pil = tensor_to_pil(output_tensor)
        return output_image_pil


def tensor_to_pil(img_tensor: torch.Tensor, batch_index: int = 0) -> Image:
    """Converts a image tensor to a Pillow Image.

    Args:
        img_tensor: tensor of shape [batch_size, channels, height, width]
        batch_index: index of the desired batch (image within a batch)

    Returns:
        Pillow Image with the corresponding mode deduced by the number of channels
    """
    img_tensor = img_tensor[batch_index].unsqueeze(0)
    i = 255.0 * img_tensor.cpu().numpy()
    img = PIL.Image.fromarray(np.clip(i, 0, 255).astype(np.uint8).squeeze())
    return img


def pil_to_tensor(image: Image) -> torch.Tensor:
    """Converts a Pillow Image to a Torch Tensor.

    Args:
        image: Pillow Image

    Returns:
        Torch Tensor of shape [batch_size, height, width, channels] where batch_size is always 1 (single image)
    """
    image_np = np.array(image).astype(np.float32) / 255.0
    image_pt = torch.from_numpy(image_np).unsqueeze(0)
    # If the image is grayscale, add a channel dimension
    if len(image_pt.shape) == 3:  # noqa:  PLR2004
        image_pt = image_pt.unsqueeze(-1)
    return image_pt

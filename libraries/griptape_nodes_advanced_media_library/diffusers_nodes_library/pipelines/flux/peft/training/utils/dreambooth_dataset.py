import itertools
import logging
import random
from pathlib import Path
from typing import Any

import torch  # type: ignore[reportMissingImports]
from PIL import Image  # type: ignore[reportMissingImports]
from PIL.ImageOps import exif_transpose  # type: ignore[reportMissingImports]
from torch.utils.data import Dataset  # type: ignore[reportMissingImports]
from torchvision import transforms  # type: ignore[reportMissingImports]
from torchvision.transforms.functional import crop  # type: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


def collate_fn(examples: list[dict[str, Any]], *, with_prior_preservation: bool = False) -> dict[str, Any]:
    """Collate function for DataLoader that optionally handles prior preservation.

    Args:
        examples (List[Dict[str, Any]]): A list of example dictionaries.
        with_prior_preservation (bool): Whether to include prior preservation.

    Returns:
        Dict[str, Any]: A batch dictionary suitable for model input.
    """
    pixel_values = [example["instance_images"] for example in examples]
    prompts = [example["instance_prompt"] for example in examples]

    logger.debug("Collating %d examples", len(examples))

    # Concat class and instance examples for prior preservation.
    # We do this to avoid doing two forward passes.
    if with_prior_preservation:
        pixel_values += [example["class_images"] for example in examples]
        prompts += [example["class_prompt"] for example in examples]

    pixel_values = torch.stack(pixel_values)
    pixel_values = pixel_values.to(memory_format=torch.contiguous_format).float()

    batch = {"pixel_values": pixel_values, "prompts": prompts}
    return batch


class DreamBoothDataset(Dataset):
    """A dataset to prepare the instance and class images with the prompts for fine-tuning the model."""

    @classmethod
    def from_hf_dataset(  # noqa: PLR0913
        cls,
        *,
        dataset_name: str,
        dataset_config_name: str | None,
        cache_dir: str | None,
        image_column: str | None,
        caption_column: str | None,
        random_flip: bool,
        resolution: int,
        instance_prompt: str,
        class_prompt: str,
        class_data_root: str | None = None,
        class_num: int | None = None,
        size: int = 1024,
        repeats: int = 1,
        center_crop: bool = False,
    ) -> "DreamBoothDataset":
        # if --dataset_name is provided or a metadata jsonl file is provided in the local --instance_data directory,
        # we load the training data using load_dataset
        try:
            from datasets import load_dataset  # type: ignore[reportMissingImports]
        except ImportError as e:
            msg = (
                "You are trying to load your data using the datasets library. If you wish to train using custom "
                "captions please install the datasets library: `pip install datasets`. If you wish to load a "
                "local folder containing images only, specify --instance_data_dir instead."
            )
            raise ImportError(msg) from e
        # Downloading and loading a dataset from the hub.
        # See more about loading custom images at
        # https://huggingface.co/docs/datasets/v2.0.0/en/dataset_script
        dataset = load_dataset(
            dataset_name,
            dataset_config_name,
            cache_dir=cache_dir,
        )
        # Preprocessing the datasets.
        column_names = dataset["train"].column_names

        # 6. Get the column names for input/target.
        if image_column is None:
            image_column = column_names[0]
            logger.info("image column defaulting to %s", image_column)
        elif image_column not in column_names:
            msg = f"`--image_column` value '{image_column}' not found in dataset columns. Dataset columns are: {', '.join(column_names)}"
            raise ValueError(msg)
        dataset["train"][image_column]

        if caption_column is None:
            logger.info(
                "No caption column provided, defaulting to instance_prompt for all images. If your dataset "
                "contains captions/prompts for the images, make sure to specify the "
                "column as --caption_column"
            )
            custom_instance_prompts = None
        else:
            if caption_column not in column_names:
                msg = f"`--caption_column` value '{caption_column}' not found in dataset columns. Dataset columns are: {', '.join(column_names)}"
                raise ValueError(msg)
            custom_instance_prompts = dataset["train"][caption_column]
            # create final list of captions according to --repeats
            custom_instance_prompts = []
            for caption in custom_instance_prompts:
                custom_instance_prompts.extend(itertools.repeat(caption, repeats))

        return cls(
            instance_images=dataset["train"][image_column],
            custom_instance_prompts=custom_instance_prompts,
            random_flip=random_flip,
            resolution=resolution,
            instance_prompt=instance_prompt,
            class_prompt=class_prompt,
            class_data_root=class_data_root,
            class_num=class_num,
            size=size,
            center_crop=center_crop,
        )

    @classmethod
    def from_local_directory(  # noqa: PLR0913
        cls,
        *,
        instance_data_root: str,
        instance_prompt: str,
        class_prompt: str,
        class_data_root: str | None = None,
        class_num: int | None = None,
        random_flip: bool = True,
        resolution: int = 512,
        size: int = 1024,
        repeats: int = 1,
        center_crop: bool = False,
    ) -> "DreamBoothDataset":
        """Create a DreamBoothDataset from a local directory of images."""
        instance_data_root_path = Path(instance_data_root)
        if not instance_data_root_path.exists():
            msg = "Instance images root doesn't exists."
            raise ValueError(msg)

        images = []
        captions = []
        for path in list(Path(instance_data_root).iterdir()):
            if path.is_file() and path.suffix.lower() in [".jpg", ".jpeg", ".png"]:
                caption_path = path.with_suffix(".txt")
                if not caption_path.exists():
                    logger.warning("Caption file %s does not exist. Skipping image %s.", caption_path, path)
                    continue
                image = Image.open(path)
                caption = caption_path.read_text().strip()
                logger.info("Caption for image at %s: %s", path, caption)
                images.append(image)
                captions.append(caption)

            custom_instance_prompts = None

        instance_images = []
        for image in images:
            instance_images.extend(itertools.repeat(image, repeats))

        custom_instance_prompts = []
        for caption in captions:
            custom_instance_prompts.extend(itertools.repeat(caption, repeats))

        return cls(
            instance_images=instance_images,
            custom_instance_prompts=custom_instance_prompts,
            random_flip=random_flip,
            resolution=resolution,
            instance_prompt=instance_prompt,
            class_prompt=class_prompt,
            class_data_root=class_data_root,
            class_num=class_num,
            size=size,
            center_crop=center_crop,
        )

    @classmethod
    def length_from_local_directory(
        cls,
        *,
        instance_data_root: str,
        repeats: int = 1,
    ) -> int:
        """Create a DreamBoothDataset from a local directory of images."""
        instance_data_root_path = Path(instance_data_root)
        if not instance_data_root_path.exists():
            msg = "Instance images root doesn't exists."
            raise ValueError(msg)

        image_count = 0
        for path in list(Path(instance_data_root).iterdir()):
            if path.is_file() and path.suffix.lower() in [".jpg", ".jpeg", ".png"]:
                caption_path = path.with_suffix(".txt")
                if not caption_path.exists():
                    logger.warning("Caption file %s does not exist. Skipping image %s.", caption_path, path)
                    continue
                image_count += 1

        return image_count * repeats

    def __init__(  # noqa: PLR0913
        self,
        *,
        instance_images: list[Image.Image],
        custom_instance_prompts: list[str] | None,
        random_flip: bool,
        resolution: int,
        instance_prompt: str,
        class_prompt: str,
        class_data_root: str | None = None,
        class_num: int | None = None,
        size: int = 1024,
        center_crop: bool = False,
    ):
        self.random_flip = random_flip
        self.resolution = resolution
        self.size = size
        self.center_crop = center_crop
        self.instance_prompt = instance_prompt
        self.instance_images = instance_images
        self.custom_instance_prompts = custom_instance_prompts
        self.class_prompt = class_prompt

        self.pixel_values = []
        train_resize = transforms.Resize(size, interpolation=transforms.InterpolationMode.BILINEAR)
        train_flip = transforms.RandomHorizontalFlip(p=1.0)
        train_transforms = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize([0.5], [0.5]),
            ]
        )
        for instance_image in self.instance_images:
            image = exif_transpose(instance_image)
            if image.mode != "RGB":
                image = image.convert("RGB")
            image = train_resize(image)
            if self.random_flip and random.random() < 0.5:  # noqa: S311,PLR2004
                # flip
                image = train_flip(image)
            if self.center_crop:
                train_crop = transforms.CenterCrop(size)
                y1 = max(0, round((image.height - self.resolution) / 2.0))
                x1 = max(0, round((image.width - self.resolution) / 2.0))
                image = train_crop(image)
            else:
                train_crop = transforms.RandomCrop(size)
                y1, x1, h, w = train_crop.get_params(image, (self.resolution, self.resolution))
                image = crop(image, y1, x1, h, w)
            image = train_transforms(image)
            self.pixel_values.append(image)

        self.num_instance_images = len(self.instance_images)
        self._length = self.num_instance_images

        if class_data_root is not None:
            self.class_data_root = Path(class_data_root)
            self.class_data_root.mkdir(parents=True, exist_ok=True)
            self.class_images_path = list(self.class_data_root.iterdir())
            if class_num is not None:
                self.num_class_images = min(len(self.class_images_path), class_num)
            else:
                self.num_class_images = len(self.class_images_path)
            self._length = max(self.num_class_images, self.num_instance_images)
        else:
            self.class_data_root = None

        self.image_transforms = transforms.Compose(
            [
                transforms.Resize(size, interpolation=transforms.InterpolationMode.BILINEAR),
                transforms.CenterCrop(size) if center_crop else transforms.RandomCrop(size),
                transforms.ToTensor(),
                transforms.Normalize([0.5], [0.5]),
            ]
        )

    def __len__(self) -> int:
        return self._length

    def __getitem__(self, index: int) -> dict[str, Image.Image | str]:
        example = {}
        instance_image = self.pixel_values[index % self.num_instance_images]
        example["instance_images"] = instance_image

        if self.custom_instance_prompts:
            caption = self.custom_instance_prompts[index % self.num_instance_images]
            if caption:
                example["instance_prompt"] = caption
            else:
                example["instance_prompt"] = self.instance_prompt

        else:  # custom prompts were provided, but length does not match size of image dataset
            example["instance_prompt"] = self.instance_prompt

        if self.class_data_root:
            class_image = Image.open(self.class_images_path[index % self.num_class_images])
            class_image = exif_transpose(class_image)

            if class_image.mode != "RGB":
                class_image = class_image.convert("RGB")
            example["class_images"] = self.image_transforms(class_image)
            example["class_prompt"] = self.class_prompt

        return example

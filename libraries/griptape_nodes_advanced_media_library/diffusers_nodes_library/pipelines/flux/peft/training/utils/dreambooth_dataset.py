import itertools
import random
from pathlib import Path
from typing import Optional
from PIL import Image
from PIL.ImageOps import exif_transpose
import torch
from torch.utils.data import Dataset
from torchvision import transforms
from torchvision.transforms.functional import crop
import logging

logger = logging.getLogger(__name__)

def collate_fn(examples, with_prior_preservation=False):
    pixel_values = [example["instance_images"] for example in examples]
    prompts = [example["instance_prompt"] for example in examples]

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
    """
    A dataset to prepare the instance and class images with the prompts for fine-tuning the model.
    It pre-processes the images.
    """

    def __init__(
        self,
        dataset_name: Optional[str],
        dataset_config_name: Optional[str],

        cache_dir,
        image_column,
        caption_column,
        random_flip,
        resolution,


        instance_data_root,
        instance_prompt,
        class_prompt,
        class_data_root=None,
        class_num=None,
        size:int=1024,
        repeats:int=1,
        center_crop: bool =False,
    ):
        self.dataset_name = dataset_name
        self.dataset_config_name = dataset_config_name
        self.cache_dir = cache_dir
        self.image_column = image_column
        self.caption_column = caption_column
        self.random_flip = random_flip
        self.resolution = resolution

        self.size = size
        self.center_crop = center_crop

        self.instance_prompt = instance_prompt
        self.custom_instance_prompts = None
        self.class_prompt = class_prompt

        # if --dataset_name is provided or a metadata jsonl file is provided in the local --instance_data directory,
        # we load the training data using load_dataset
        if self.dataset_name is not None:
            try:
                from datasets import load_dataset  # type: ignore
            except ImportError:
                raise ImportError(
                    "You are trying to load your data using the datasets library. If you wish to train using custom "
                    "captions please install the datasets library: `pip install datasets`. If you wish to load a "
                    "local folder containing images only, specify --instance_data_dir instead."
                )
            # Downloading and loading a dataset from the hub.
            # See more about loading custom images at
            # https://huggingface.co/docs/datasets/v2.0.0/en/dataset_script
            dataset = load_dataset(
                self.dataset_name,
                self.dataset_config_name,
                cache_dir=self.cache_dir,
            )
            # Preprocessing the datasets.
            column_names = dataset["train"].column_names

            # 6. Get the column names for input/target.
            if self.image_column is None:
                image_column = column_names[0]
                logger.info(f"image column defaulting to {image_column}")
            else:
                image_column = self.image_column
                if image_column not in column_names:
                    raise ValueError(
                        f"`--image_column` value '{self.image_column}' not found in dataset columns. Dataset columns are: {', '.join(column_names)}"
                    )
            instance_images = dataset["train"][image_column]

            if self.caption_column is None:
                logger.info(
                    "No caption column provided, defaulting to instance_prompt for all images. If your dataset "
                    "contains captions/prompts for the images, make sure to specify the "
                    "column as --caption_column"
                )
                self.custom_instance_prompts = None
            else:
                if self.caption_column not in column_names:
                    raise ValueError(
                        f"`--caption_column` value '{self.caption_column}' not found in dataset columns. Dataset columns are: {', '.join(column_names)}"
                    )
                custom_instance_prompts = dataset["train"][self.caption_column]
                # create final list of captions according to --repeats
                self.custom_instance_prompts = []
                for caption in custom_instance_prompts:
                    self.custom_instance_prompts.extend(itertools.repeat(caption, repeats))
        else:
            self.instance_data_root = Path(instance_data_root)
            if not self.instance_data_root.exists():
                raise ValueError("Instance images root doesn't exists.")
            

            images = []
            captions = []
            for path in list(Path(instance_data_root).iterdir()):
                if path.is_file() and path.suffix.lower() in [".jpg", ".jpeg", ".png"]:
                    caption_path = path.with_suffix(".txt")
                    if not caption_path.exists():
                        logger.warning(
                            f"Caption file {caption_path} does not exist. Skipping image {path}."
                        )
                        continue
                    image = Image.open(path)
                    caption = caption_path.read_text().strip()
                    logger.info(f"Caption for image at {path}: {caption}")
                    images.append(image)
                    captions.append(caption)

                self.custom_instance_prompts = None

            self.instance_images = []
            for image in images:
                self.instance_images.extend(itertools.repeat(image, repeats))

            self.custom_instance_prompts = []
            for caption in captions:
                self.custom_instance_prompts.extend(itertools.repeat(caption, repeats))

        self.pixel_values = []
        train_resize = transforms.Resize(size, interpolation=transforms.InterpolationMode.BILINEAR)
        train_crop = transforms.CenterCrop(size) if center_crop else transforms.RandomCrop(size)
        train_flip = transforms.RandomHorizontalFlip(p=1.0)
        train_transforms = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize([0.5], [0.5]),
            ]
        )
        for image in self.instance_images:
            image = exif_transpose(image)
            if not image.mode == "RGB":
                image = image.convert("RGB")
            image = train_resize(image)
            if self.random_flip and random.random() < 0.5:
                # flip
                image = train_flip(image)
            if self.center_crop:
                y1 = max(0, int(round((image.height - self.resolution) / 2.0)))
                x1 = max(0, int(round((image.width - self.resolution) / 2.0)))
                image = train_crop(image)
            else:
                y1, x1, h, w = train_crop.get_params(image, (self.resolution, self.resolution))  # type: ignore
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

    def __len__(self):
        return self._length

    def __getitem__(self, index):
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

            if not class_image.mode == "RGB":
                class_image = class_image.convert("RGB")
            example["class_images"] = self.image_transforms(class_image)
            example["class_prompt"] = self.class_prompt

        return example

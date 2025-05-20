

import argparse
from diffusers import PreTrainedModel  # type: ignore[reportMissingImports]
import torch


def load_text_encoders(
    args: argparse.Namespace,
    class_one: type[PreTrainedModel],
    class_two: type[PreTrainedModel]
) -> tuple[PreTrainedModel, PreTrainedModel]:
    text_encoder_one = class_one.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="text_encoder",
        revision=args.revision,
        variant=args.variant,
        torch_dtype=torch.bfloat16,
    )
    text_encoder_two = class_two.from_pretrained(
        args.pretrained_model_name_or_path,
        subfolder="text_encoder_2",
        revision=args.revision,
        variant=args.variant,
        torch_dtype=torch.bfloat16,
    )
    return text_encoder_one, text_encoder_two
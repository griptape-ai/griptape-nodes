import argparse
import logging

import torch  # type: ignore[reportMissingImports]
from accelerate import Accelerator  # type: ignore[reportMissingImports]
from accelerate.utils.deepspeed import DummyOptim  # type: ignore[reportMissingImports]
from torch.optim import Optimizer  # type: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


def create_optimizer(accelerator: Accelerator, args: argparse.Namespace, params_to_optimize: list[dict]) -> Optimizer:
    """Create an optimizer based on the provided arguments."""
    if (
        accelerator.state.deepspeed_plugin is not None
        and "optimizer" in accelerator.state.deepspeed_plugin.deepspeed_config
    ):
        return create_dummy_optimizer(args, params_to_optimize)

    optimizer_name = args.optimizer
    match optimizer_name.lower():
        case "adamw":
            return create_adamw_optimizer(args, params_to_optimize)
        case "adamw-8bit":
            return create_adamw_8bit_optimizer(args, params_to_optimize)
        case "prodigy":
            return create_prodigy_optimizer(args, params_to_optimize)
        case _:
            msg = f"Unsupported choice of optimizer: {optimizer_name}."
            raise RuntimeError(msg)


def create_dummy_optimizer(args: argparse.Namespace, params_to_optimize: list[dict]) -> Optimizer:
    """Create a dummy optimizer for use with DeepSpeed."""
    optimizer = DummyOptim(
        params_to_optimize,
        lr=args.learning_rate,
        weight_decay=args.adam_weight_decay,
    )
    return optimizer


def create_adamw_optimizer(args: argparse.Namespace, params_to_optimize: list[dict]) -> Optimizer:
    """Create a standard AdamW optimizer."""
    optimizer = torch.optim.AdamW(
        params_to_optimize,
        betas=(args.adam_beta1, args.adam_beta2),
        weight_decay=args.adam_weight_decay,
        eps=args.adam_epsilon,
    )
    return optimizer


def create_adamw_8bit_optimizer(args: argparse.Namespace, params_to_optimize: list[dict]) -> Optimizer:
    """Create an 8-bit AdamW optimizer using the bitsandbytes library."""
    try:
        import bitsandbytes as bnb  # type: ignore[reportMissingImports]
    except ImportError as e:
        msg = "To use 8-bit Adam, please install the bitsandbytes library: `pip install bitsandbytes`."
        raise ImportError(msg) from e
    optimizer = bnb.optim.AdamW8bit(
        params_to_optimize,
        betas=(args.adam_beta1, args.adam_beta2),
        weight_decay=args.adam_weight_decay,
        eps=args.adam_epsilon,
    )
    return optimizer


def create_prodigy_optimizer(args: argparse.Namespace, params_to_optimize: list[dict]) -> Optimizer:
    """Create a Prodigy optimizer."""
    try:
        import prodigyopt  # type: ignore[reportMissingImports]
    except ImportError as e:
        msg = "To use Prodigy, please install the prodigyopt library: `pip install prodigyopt`"
        raise ImportError(msg) from e

    if args.learning_rate <= 0.1:  # noqa: PLR2004
        logger.warning(
            "Learning rate is too low. When using prodigy, it's generally better to set learning rate around 1.0"
        )
    if args.train_text_encoder and args.text_encoder_lr:
        logger.warning(
            "Learning rates were provided both for the transformer and the text encoder- e.g. text_encoder_lr:"
            " %s and learning_rate: %s. "
            "When using prodigy only learning_rate is used as the initial learning rate.",
            args.text_encoder_lr,
            args.learning_rate,
        )
        # changes the learning rate of text_encoder_parameters_one to be
        # --learning_rate
        params_to_optimize[1]["lr"] = args.learning_rate

    optimizer = prodigyopt.Prodigy(
        params_to_optimize,
        betas=(args.adam_beta1, args.adam_beta2),
        beta3=args.prodigy_beta3,
        weight_decay=args.adam_weight_decay,
        eps=args.adam_epsilon,
        decouple=args.prodigy_decouple,
        use_bias_correction=args.prodigy_use_bias_correction,
        safeguard_warmup=args.prodigy_safeguard_warmup,
    )
    return optimizer

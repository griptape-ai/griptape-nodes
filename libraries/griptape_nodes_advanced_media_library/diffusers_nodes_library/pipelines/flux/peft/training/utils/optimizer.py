import argparse
import torch
import logging

logger = logging.getLogger(__name__)

def create_optimizer(args: argparse.Namespace, params_to_optimize):
    optimizer_name = args.optimizer
    match optimizer_name.lower():
        case "adamw":
            return create_adamw_optimizer(args, params_to_optimize)
        case "adamw-8bit":
            return create_adamw_8bit_optimizer(args, params_to_optimize)
        case "prodigy":
            return create_prodigy_optimizer(args, params_to_optimize)
        case _:
            raise RuntimeError(f"Unsupported choice of optimizer: {optimizer_name}.")

def create_adamw_optimizer(args: argparse.Namespace, params_to_optimize):
    optimizer = torch.optim.AdamW(
        params_to_optimize,
        betas=(args.adam_beta1, args.adam_beta2),
        weight_decay=args.adam_weight_decay,
        eps=args.adam_epsilon,
    )
    return optimizer

def create_adamw_8bit_optimizer(args: argparse.Namespace, params_to_optimize):
    try:
        import bitsandbytes as bnb  # type: ignore[reportMissingImports]
    except ImportError:
        raise ImportError(
            "To use 8-bit Adam, please install the bitsandbytes library: `pip install bitsandbytes`."
        )
    optimizer = bnb.optim.AdamW8bit(
        params_to_optimize,
        betas=(args.adam_beta1, args.adam_beta2),
        weight_decay=args.adam_weight_decay,
        eps=args.adam_epsilon,
    )
    return optimizer

def create_prodigy_optimizer(args: argparse.Namespace, params_to_optimize):
    try:
        import prodigyopt  # type: ignore
    except ImportError:
        raise ImportError("To use Prodigy, please install the prodigyopt library: `pip install prodigyopt`")

    if args.learning_rate <= 0.1:
        logger.warning(
            "Learning rate is too low. When using prodigy, it's generally better to set learning rate around 1.0"
        )
    if args.train_text_encoder and args.text_encoder_lr:
        logger.warning(
            f"Learning rates were provided both for the transformer and the text encoder- e.g. text_encoder_lr:"
            f" {args.text_encoder_lr} and learning_rate: {args.learning_rate}. "
            f"When using prodigy only learning_rate is used as the initial learning rate."
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
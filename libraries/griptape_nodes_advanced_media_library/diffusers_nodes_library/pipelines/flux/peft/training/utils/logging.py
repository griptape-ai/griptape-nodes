import logging

import diffusers  # type: ignore[reportMissingImports]
import transformers  # type: ignore[reportMissingImports]
import transformers.utils.logging  # type: ignore[reportMissingImports]
from accelerate import Accelerator  # type: ignore[reportMissingImports]
from accelerate.logging import MultiProcessAdapter  # type: ignore[reportMissingImports]


def configure_logging(accelerator: Accelerator, logger: MultiProcessAdapter) -> None:
    """Configure logging for the training process."""
    logger.info("Configuring logging.")
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO,
    )

    # Log the accelerator state on every process to help with debugging.
    logger.info(accelerator.state, main_process_only=False)

    if accelerator.is_local_main_process:
        transformers.utils.logging.set_verbosity_warning()
        diffusers.utils.logging.set_verbosity_info()
    else:
        transformers.utils.logging.set_verbosity_error()
        diffusers.utils.logging.set_verbosity_error()

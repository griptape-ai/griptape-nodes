import transformers
import diffusers
from accelerate import Accelerator
from accelerate.logging import MultiProcessAdapter


import logging

def configure_logging(accelerator: Accelerator, logger: MultiProcessAdapter) -> None:
# Make one log on every process with the configuration for debugging.
    logger.info("Configuring logging.")
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO,
    )
    logger.info(accelerator.state, main_process_only=False)
    if accelerator.is_local_main_process:
        transformers.utils.logging.set_verbosity_warning()
        diffusers.utils.logging.set_verbosity_info()
    else:
        transformers.utils.logging.set_verbosity_error()
        diffusers.utils.logging.set_verbosity_error()
from typing import Optional
from accelerate.logging import get_logger
from accelerate.utils import set_seed

logger = get_logger(__name__)

def configure_seed(seed: Optional[int]) -> None:
    if seed is not None:
        logger.info(f"Seed provided, setting seed to {seed}.")
        set_seed(seed)
    else:
        logger.info(f"No seed not provided, not setting seed.")
import logging

from rich.logging import RichHandler


class LogManager:
    def __init__(self) -> None:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        if not root_logger.hasHandlers():
            root_logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True))

    def get_logger(self) -> logging.Logger:
        logger = logging.getLogger()
        return logger

import logging


class LogManager:
    def __init__(self) -> None:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        if not root_logger.hasHandlers():
            console = logging.StreamHandler()
            console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            root_logger.addHandler(console)

    def get_logger(self) -> logging.Logger:
        logger = logging.getLogger()
        return logger

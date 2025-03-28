import logging

from rich.logging import RichHandler

from griptape.events import EventBus
from griptape_nodes.retained_mode.events.base_events import AppEvent
from griptape_nodes.retained_mode.events.logger_events import LogHandlerEvent


class EventLogHandler(logging.Handler):
    def emit(self, record):
        EventBus.publish_event(AppEvent(payload=LogHandlerEvent(message=record.getMessage(), levelname=record.levelname, created=record.created)))

class LogManager:
    def __init__(self) -> None:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        if not root_logger.hasHandlers():
            root_logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True))
            root_logger.addHandler(EventLogHandler())

    def get_logger(self) -> logging.Logger:
        logger = logging.getLogger()
        return logger

import logging

from rich.logging import RichHandler

from griptape_nodes.api.queue_manager import event_queue
from griptape_nodes.retained_mode.events.base_events import AppEvent
from griptape_nodes.retained_mode.events.logger_events import LogHandlerEvent


class EventLogHandler(logging.Handler):
    def emit(self, record) -> None:
        event_queue.put(
            AppEvent(  # pyright: ignore[reportArgumentType]
                payload=LogHandlerEvent(message=record.getMessage(), levelname=record.levelname, created=record.created)
            )
        )


class LogManager:
    LOGGER_NAME = "griptape_nodes"

    def __init__(self) -> None:
        logger = logging.getLogger(LogManager.LOGGER_NAME)
        logger.setLevel(logging.INFO)

        if not logger.hasHandlers():
            logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True))
            logger.addHandler(EventLogHandler())

        self.logger = logger

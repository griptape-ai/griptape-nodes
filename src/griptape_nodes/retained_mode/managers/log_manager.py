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
    def __init__(self) -> None:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        if not root_logger.hasHandlers():
            root_logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True))
            root_logger.addHandler(EventLogHandler())

        local_logger = logging.getLogger("griptape_nodes_engine")
        local_logger.setLevel(logging.INFO)

        if not local_logger.hasHandlers():
            local_logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True))

    def get_logger(self, *, event_handler: bool = True) -> logging.Logger:
        logger = logging.getLogger() if event_handler else logging.getLogger("griptape_nodes_engine")
        return logger

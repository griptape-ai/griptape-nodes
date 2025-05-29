import contextlib
import logging
import time
from collections.abc import Iterator

from diffusers_nodes_library.common.utils.logging_utils import LoggerCapture, StdoutCapture, seconds_to_human_readable
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode


class LogParameter:
    def __init__(self, node: BaseNode):
        self._node = node

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="logs",
                output_type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="logs",
                ui_options={"multiline": True},
            )
        )

    @contextlib.contextmanager
    def append_stdout_to_logs(self) -> Iterator[None]:
        def callback(data: str) -> None:
            self.append_to_logs(data)

        with StdoutCapture(callback):
            yield

    @contextlib.contextmanager
    def append_logs_to_logs(self, logger: logging.Logger) -> Iterator[None]:
        def callback(data: str) -> None:
            self.append_to_logs(data)

        with LoggerCapture(logger, callback):
            yield

    @contextlib.contextmanager
    def append_profile_to_logs(self, label: str) -> Iterator[None]:
        start = time.perf_counter()
        yield
        seconds = time.perf_counter() - start
        human_readable_duration = seconds_to_human_readable(seconds)
        self.append_to_logs(f"{label} took {human_readable_duration}\n")

    def append_to_logs(self, text: str) -> None:
        self._node.append_value_to_parameter("logs", text)

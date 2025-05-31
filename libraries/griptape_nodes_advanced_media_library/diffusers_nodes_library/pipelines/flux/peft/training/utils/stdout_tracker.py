import json

from accelerate.tracking import GeneralTracker, on_main_process  # type: ignore[reportMissingImports]


class StdoutTracker(GeneralTracker):
    name = "stdout"
    requires_logging_directory = False

    @on_main_process
    def __init__(self, run_name: str):
        self.run_name = run_name

    @property
    def tracker(self) -> GeneralTracker:
        return self

    @on_main_process
    def store_init_configuration(self, values: dict) -> None:
        pass

    @on_main_process
    def log(self, values: dict, step: int | None = None, **_) -> None:
        data = {
            "step": step,
            "values": values,
        }
        json.dumps(data)

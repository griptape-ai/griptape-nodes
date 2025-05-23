import json
from accelerate.tracking import GeneralTracker, on_main_process
from typing import Optional


class StdoutTracker(GeneralTracker):
    name = "stdout"
    requires_logging_directory = False

    @on_main_process
    def __init__(self, run_name: str):
        self.run_name = run_name

    @property
    def tracker(self):
        return self

    @on_main_process
    def store_init_configuration(self, values: dict):
        pass

    @on_main_process
    def log(self, values: dict, step: Optional[int] = None, **_):
        data  = {
            "step": step,
            "values": values,
        }
        data_json_str = json.dumps(data)
        print(f"badger|StdoutTracker.log|{data_json_str}")
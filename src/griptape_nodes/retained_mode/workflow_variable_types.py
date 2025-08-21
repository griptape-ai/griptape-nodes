from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class VariableScope(StrEnum):
    GLOBAL = "global"
    CURRENT_FLOW = "current_flow"
    PARENT_FLOWS = "parent_flows"


@dataclass
class FlowVariable:
    uuid: str
    name: str
    scope: VariableScope
    type: str
    value: Any

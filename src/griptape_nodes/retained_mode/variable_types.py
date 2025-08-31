from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class VariableScope(StrEnum):
    CURRENT_FLOW_ONLY = "current_flow_only"
    HIERARCHICAL = "hierarchical"
    GLOBAL_ONLY = "global_only"
    ALL = "all"  # For ListVariables to get all variables from all flows


@dataclass
class FlowVariable:
    name: str
    owning_flow_name: str | None  # None for global variables
    type: str
    value: Any

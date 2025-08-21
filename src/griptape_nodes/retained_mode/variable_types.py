from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class VariableScope(StrEnum):
    CURRENT_FLOW_ONLY = "current_flow_only"
    PARENT_FLOWS = "parent_flows"
    GLOBAL_ONLY = "global_only"
    ALL = "all"  # For ListVariables to get all variables from all flows


@dataclass
class FlowVariable:
    name: str
    scope: VariableScope
    type: str
    value: Any

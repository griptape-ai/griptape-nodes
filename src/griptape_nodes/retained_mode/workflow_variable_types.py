from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class VariableScope(StrEnum):
    GLOBAL = "global"
    CURRENT_WORKFLOW = "current_workflow"


@dataclass
class WorkflowVariable:
    uuid: str
    name: str
    scope: VariableScope
    type: str
    value: Any

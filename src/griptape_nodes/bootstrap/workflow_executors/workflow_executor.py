import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class WorkflowExecutor(ABC):
    @abstractmethod
    def run(self, workflow_name: str, flow_input: Any, storage_backend: str = "local") -> None:
        pass

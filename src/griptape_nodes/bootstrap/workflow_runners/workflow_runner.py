import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class WorkflowRunner(ABC):
    @abstractmethod
    def run(self, workflow_path: str, workflow_name: str, flow_input: Any, storage_backend: str = "local") -> None:
        pass

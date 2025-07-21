import logging
from abc import ABC, abstractmethod
from typing import Any

from griptape_nodes.drivers.storage import StorageBackend

logger = logging.getLogger(__name__)


class WorkflowExecutor(ABC):
    @abstractmethod
    def run(
        self,
        workflow_name: str,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
        **kwargs: Any,
    ) -> None:
        pass

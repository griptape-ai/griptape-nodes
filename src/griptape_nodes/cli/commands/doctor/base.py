"""Base types for doctor health checks."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CheckResult:
    """Result of a single health check."""

    name: str
    passed: bool
    message: str


class HealthCheck(ABC):
    """Base class for health checks run by the doctor command."""

    @abstractmethod
    def run(self) -> CheckResult: ...

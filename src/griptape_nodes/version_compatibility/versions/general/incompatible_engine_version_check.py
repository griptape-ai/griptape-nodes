from __future__ import annotations

from typing import TYPE_CHECKING

import semver

from griptape_nodes.retained_mode.events.app_events import (
    GetEngineVersionRequest,
    GetEngineVersionResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_engine_version_too_new_problem import (
    LibraryEngineVersionTooNewProblem,
)
from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
    LibraryVersionCompatibilityCheck,
    LibraryVersionCompatibilityIssue,
)

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibrarySchema


class IncompatibleEngineVersionCheck(LibraryVersionCompatibilityCheck):
    """Check that a library's required engine version is not newer than the current engine.

    This check applies to libraries whose engine_version metadata is greater than
    the current running engine version. Such libraries were built for a newer engine
    and may use features that don't exist in the current engine.

    Libraries failing this check are marked UNUSABLE and cannot be loaded.
    """

    def applies_to_library(self, library_data: LibrarySchema) -> bool:
        """Check applies to libraries with engine_version > current engine version."""
        try:
            library_engine_version = semver.VersionInfo.parse(library_data.metadata.engine_version)

            engine_version_result = GriptapeNodes.handle_request(GetEngineVersionRequest())
            if not isinstance(engine_version_result, GetEngineVersionResultSuccess):
                return False

            current_engine_version = semver.VersionInfo(
                engine_version_result.major,
                engine_version_result.minor,
                engine_version_result.patch,
            )

            return library_engine_version > current_engine_version
        except Exception:
            return False

    def check_library(self, library_data: LibrarySchema) -> list[LibraryVersionCompatibilityIssue]:
        """Return UNUSABLE issue for libraries requiring a newer engine version."""
        engine_version_result = GriptapeNodes.handle_request(GetEngineVersionRequest())
        if not isinstance(engine_version_result, GetEngineVersionResultSuccess):
            return []

        current_version_str = (
            f"{engine_version_result.major}.{engine_version_result.minor}.{engine_version_result.patch}"
        )

        return [
            LibraryVersionCompatibilityIssue(
                problem=LibraryEngineVersionTooNewProblem(
                    library_engine_version=library_data.metadata.engine_version,
                    current_engine_version=current_version_str,
                ),
                severity=LibraryManager.LibraryFitness.UNUSABLE,
            )
        ]

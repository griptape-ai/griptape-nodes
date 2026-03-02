from __future__ import annotations

from typing import TYPE_CHECKING

import semver

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_engine_version_too_new_problem import (
    LibraryEngineVersionTooNewProblem,
)
from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
    LibraryVersionCompatibilityCheck,
    LibraryVersionCompatibilityIssue,
)
from griptape_nodes.utils.version_utils import engine_version, get_install_source

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibrarySchema


class IncompatibleEngineVersionCheck(LibraryVersionCompatibilityCheck):
    """Check that a library's required engine version is not newer than the current engine.

    This check applies to libraries whose engine_version metadata is greater than
    the current running engine version. Such libraries were built for a newer engine
    and may use features that don't exist in the current engine.

    Libraries failing this check are marked UNUSABLE on stable PyPI releases, or FLAWED
    on non-release installs (git, file) so nightly and git-commit users can still load them.
    """

    def applies_to_library(self, library_data: LibrarySchema) -> bool:
        """Check applies to libraries with engine_version > current engine version."""
        try:
            library_engine_version = semver.VersionInfo.parse(library_data.metadata.engine_version)
            engine_ver = semver.VersionInfo.parse(engine_version)
        except Exception:
            return False
        else:
            return library_engine_version > engine_ver

    def check_library(self, library_data: LibrarySchema) -> list[LibraryVersionCompatibilityIssue]:
        """Return a compatibility issue for libraries requiring a newer engine version.

        The severity depends on the engine install source: FLAWED for non-PyPI installs
        (git, file) so users on nightly or git-commit builds can still load the library,
        and UNUSABLE for stable PyPI releases where the incompatibility is definitive.
        """
        install_source, _ = get_install_source()
        severity = (
            LibraryManager.LibraryFitness.FLAWED if install_source != "pypi" else LibraryManager.LibraryFitness.UNUSABLE
        )

        return [
            LibraryVersionCompatibilityIssue(
                problem=LibraryEngineVersionTooNewProblem(
                    library_engine_version=library_data.metadata.engine_version,
                    current_engine_version=engine_version,
                ),
                severity=severity,
            )
        ]

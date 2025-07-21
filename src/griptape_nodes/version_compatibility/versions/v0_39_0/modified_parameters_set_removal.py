from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.events.app_events import (
    GetEngineVersionRequest,
    GetEngineVersionResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, Version
from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus
from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
    LibraryVersionCompatibilityCheck,
    LibraryVersionCompatibilityIssue,
)

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibrarySchema


class ModifiedParametersSetRemovalCheck(LibraryVersionCompatibilityCheck):
    """Check for libraries impacted by the modified_parameters_set deprecation timeline."""

    def applies_to_library(self, library_data: LibrarySchema) -> bool:
        """Check applies to libraries with engine_version < 0.39.0."""
        library_version = Version.from_string(library_data.metadata.engine_version)
        return library_version is not None and library_version < Version(0, 39, 0)

    def check_library(self, library_data: LibrarySchema) -> list[LibraryVersionCompatibilityIssue]:
        """Perform the modified_parameters_set deprecation check."""
        # Get current engine version
        engine_version_result = GriptapeNodes.handle_request(GetEngineVersionRequest())
        if not isinstance(engine_version_result, GetEngineVersionResultSuccess):
            # If we can't get current engine version, skip version-specific warnings
            return []

        current_engine_version = Version(
            engine_version_result.major, engine_version_result.minor, engine_version_result.patch
        )

        # Determine which phase we're in based on current engine version
        library_version_str = library_data.metadata.engine_version

        if current_engine_version >= Version(0, 39, 0):
            # 0.39+ Release: Parameter removed, reject incompatible libraries
            return [
                LibraryVersionCompatibilityIssue(
                    message=f"This library (built for engine version {library_version_str}) is incompatible with Griptape Nodes 0.39+. "
                    "The 'modified_parameters_set' parameter has been removed from BaseNode methods: 'after_incoming_connection', 'after_outgoing_connection', 'after_incoming_connection_removed', 'after_outgoing_connection_removed', 'before_value_set', and 'after_value_set'. "
                    "If this library overrides any of these methods, it will not load or function properly. Please update to a newer version of this library or contact the library author immediately.",
                    severity=LibraryStatus.UNUSABLE,
                ),
                LibraryVersionCompatibilityIssue(
                    message=f"This library (built for engine version {library_version_str}) is incompatible with Griptape Nodes 0.39+."
                    "The 'ui_options' field has been modified on all Elements. In order to function properly, all nodes must update ui_options by setting its value to a new dictionary. Updating ui_options by accessing the private field _ui_options will no longer create UI updates in the editor."
                    "If this library accesses the private _ui_options field, it will not update the editor properly. Please update to a newer version of this library or contact the library author immediately.",
                    severity=LibraryStatus.UNUSABLE,
                ),
            ]
        if current_engine_version >= Version(0, 38, 0):
            # 0.38 Release: Warning about upcoming removal in 0.39
            return [
                LibraryVersionCompatibilityIssue(
                    message=f"WARNING: The 'modified_parameters_set' parameter will be removed in Griptape Nodes 0.39 from BaseNode methods: 'after_incoming_connection', 'after_outgoing_connection', 'after_incoming_connection_removed', 'after_outgoing_connection_removed', 'before_value_set', and 'after_value_set'. "
                    f"This library (built for engine version {library_version_str}) must be updated before the 0.39 release. "
                    "If this library overrides any of these methods, it will fail to load in 0.39. If not, no action is necessary. Please contact the library author to confirm whether this library is impacted.",
                    severity=LibraryStatus.FLAWED,
                ),
                LibraryVersionCompatibilityIssue(
                    message="WARNING: The 'ui_options' field has been modified in Griptape Nodes 0.38 on all BaseNodeElements."
                    "In order to function properly, all nodes must update ui_options by setting its value to a new dictionary. Updating ui_options by accessing the private field _ui_options will no longer create UI updates in the editor."
                    "If this library accesses the private _ui_options field, it will not update the editor properly. Please update to a newer version of this library or contact the library author immediately.",
                    severity=LibraryStatus.FLAWED,
                ),
            ]

        # No compatibility issues for current version
        return []

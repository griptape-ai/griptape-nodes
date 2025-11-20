from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibraryMetadata, LibrarySchema, NodeMetadata
    from griptape_nodes.retained_mode.managers.fitness_problems.libraries import LibraryProblem
    from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesRequest(RequestPayload):
    """List all currently registered libraries.

    Use when: Displaying available libraries, checking library availability,
    building library selection UIs, debugging library registration.

    Results: ListRegisteredLibrariesResultSuccess (with library names) | ListRegisteredLibrariesResultFailure (system error)
    """


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Registered libraries listed successfully.

    Args:
        libraries: List of registered library names
    """

    libraries: list[str]


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Library listing failed. Common causes: registry not initialized, system error."""


@dataclass
@PayloadRegistry.register
class ListCapableLibraryEventHandlersRequest(RequestPayload):
    """List libraries capable of handling a specific event type.

    Use when: Finding libraries that can process specific events, implementing event routing,
    library capability discovery, debugging event handling.

    Results: ListCapableLibraryEventHandlersResultSuccess (with handler names) | ListCapableLibraryEventHandlersResultFailure (query error)
    """

    request_type: str


@dataclass
@PayloadRegistry.register
class ListCapableLibraryEventHandlersResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Event handlers listed successfully.

    Args:
        handlers: List of library names capable of handling the event type
    """

    handlers: list[str]


@dataclass
@PayloadRegistry.register
class ListCapableLibraryEventHandlersResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Event handlers listing failed. Common causes: invalid event type, registry error."""


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryRequest(RequestPayload):
    """List all node types available in a specific library.

    Use when: Discovering available nodes, building node creation UIs,
    validating node types, exploring library contents.

    Args:
        library: Name of the library to list node types for

    Results: ListNodeTypesInLibraryResultSuccess (with node types) | ListNodeTypesInLibraryResultFailure (library not found)
    """

    library: str


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Node types in library listed successfully.

    Args:
        node_types: List of node type names available in the library
    """

    node_types: list[str]


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Node types listing failed. Common causes: library not found, library not loaded."""


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryRequest(RequestPayload):
    """Get metadata for a specific node type from a library.

    Use when: Inspecting node capabilities, validating node types, building node creation UIs,
    getting parameter definitions, checking node requirements.

    Args:
        library: Name of the library containing the node type
        node_type: Name of the node type to get metadata for

    Results: GetNodeMetadataFromLibraryResultSuccess (with metadata) | GetNodeMetadataFromLibraryResultFailure (node not found)
    """

    library: str
    node_type: str


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Node metadata retrieved successfully from library.

    Args:
        metadata: Complete node metadata including parameters, description, requirements
    """

    metadata: NodeMetadata


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Node metadata retrieval failed. Common causes: library not found, node type not found, library not loaded."""


@dataclass
@PayloadRegistry.register
class LoadLibraryMetadataFromFileRequest(RequestPayload):
    """Request to load library metadata from a JSON file without loading node modules.

    This provides a lightweight way to get library schema information without the overhead
    of dynamically importing Python modules. Useful for metadata queries, validation,
    and library discovery operations.

    Args:
        file_path: Absolute path to the library JSON schema file to load.
    """

    file_path: str


@dataclass
@PayloadRegistry.register
class LoadLibraryMetadataFromFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successful result from loading library metadata.

    Contains the validated library schema that can be used for metadata queries,
    node type discovery, and other operations that don't require the actual
    node classes to be loaded.

    Args:
        library_schema: The validated LibrarySchema object containing all metadata
                       about the library including nodes, categories, and settings.
        file_path: The file path from which the library metadata was loaded.
        git_remote: The git remote URL if the library is in a git repository, None otherwise.
        git_branch: The current git branch name if the library is in a git repository, None otherwise.
    """

    library_schema: LibrarySchema
    file_path: str
    git_remote: str | None
    git_branch: str | None


@dataclass
@PayloadRegistry.register
class LoadLibraryMetadataFromFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed result from loading library metadata with detailed error information.

    Provides comprehensive error details including the specific failure type and
    a list of problems encountered during loading. This allows callers to understand
    exactly what went wrong and take appropriate action.

    Args:
        library_path: Path to the library file that failed to load.
        library_name: Name of the library if it could be extracted from the JSON,
                     None if the name couldn't be determined.
        status: The LibraryStatus enum indicating the type of failure
               (MISSING, UNUSABLE, etc.).
        problems: List of specific problems encountered during loading
                 (file not found, JSON parse errors, validation failures, etc.).
    """

    library_path: str
    library_name: str | None
    status: LibraryStatus
    problems: list[LibraryProblem]


@dataclass
@PayloadRegistry.register
class LoadMetadataForAllLibrariesRequest(RequestPayload):
    """Request to load metadata for all libraries from configuration without loading node modules.

    This loads metadata from both:
    1. Library JSON files specified in configuration
    2. Sandbox library (dynamically generated from Python files)

    Provides a lightweight way to discover all available libraries and their schemas
    without the overhead of importing Python modules or registering them in the system.
    """


@dataclass
@PayloadRegistry.register
class LoadMetadataForAllLibrariesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successful result from loading metadata for all libraries.

    Contains metadata for all discoverable libraries from both configuration files
    and sandbox directory, with clear separation between successful loads and failures.

    Args:
        successful_libraries: List of successful library metadata loading results,
                             including both config-based libraries and sandbox library if applicable.
        failed_libraries: List of detailed failure results for libraries that couldn't be loaded,
                         including both config-based libraries and sandbox library if applicable.
    """

    successful_libraries: list[LoadLibraryMetadataFromFileResultSuccess]
    failed_libraries: list[LoadLibraryMetadataFromFileResultFailure]


@dataclass
@PayloadRegistry.register
class LoadMetadataForAllLibrariesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed result from loading metadata for all libraries.

    This indicates a systemic failure (e.g., configuration access issues)
    rather than individual library loading failures, which are captured
    in the success result's failed_libraries list.
    """


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromFileRequest(RequestPayload):
    """Register a library from a JSON file.

    Use when: Loading custom libraries, adding new node types,
    registering development libraries, extending node capabilities.

    Args:
        file_path: Path to the library JSON file to register
        load_as_default_library: Whether to load as the default library (default: False)

    Results: RegisterLibraryFromFileResultSuccess (with library name) | RegisterLibraryFromFileResultFailure (load error)
    """

    file_path: str
    load_as_default_library: bool = False


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromFileResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Library registered successfully from file.

    Args:
        library_name: Name of the registered library
    """

    library_name: str


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromFileResultFailure(ResultPayloadFailure):
    """Library registration from file failed. Common causes: file not found, invalid format, load error."""


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromRequirementSpecifierRequest(RequestPayload):
    """Register a library from a requirement specifier (e.g., package name).

    Use when: Installing libraries from package managers, adding dependencies,
    registering third-party libraries, dynamic library loading.

    Results: RegisterLibraryFromRequirementSpecifierResultSuccess (with library name) | RegisterLibraryFromRequirementSpecifierResultFailure (install error)
    """

    requirement_specifier: str
    library_config_name: str = "griptape_nodes_library.json"


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromRequirementSpecifierResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Library registered successfully from requirement specifier.

    Args:
        library_name: Name of the registered library
    """

    library_name: str


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromRequirementSpecifierResultFailure(ResultPayloadFailure):
    """Library registration from requirement specifier failed. Common causes: package not found, installation error, invalid specifier."""


@dataclass
@PayloadRegistry.register
class ListCategoriesInLibraryRequest(RequestPayload):
    """List all categories available in a library.

    Use when: Building category-based UIs, organizing node selection,
    browsing library contents, implementing filters.

    Results: ListCategoriesInLibraryResultSuccess (with categories) | ListCategoriesInLibraryResultFailure (library not found)
    """

    library: str


@dataclass
@PayloadRegistry.register
class ListCategoriesInLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Library categories listed successfully.

    Args:
        categories: List of category dictionaries with names, descriptions, and metadata
    """

    categories: list[dict]


@dataclass
@PayloadRegistry.register
class ListCategoriesInLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Library categories listing failed. Common causes: library not found, library not loaded."""


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataRequest(RequestPayload):
    """Get metadata for a specific library.

    Use when: Inspecting library properties, displaying library information,
    checking library versions, validating library compatibility.

    Results: GetLibraryMetadataResultSuccess (with metadata) | GetLibraryMetadataResultFailure (library not found)
    """

    library: str


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Library metadata retrieved successfully.

    Args:
        metadata: Complete library metadata including version, description, dependencies
    """

    metadata: LibraryMetadata


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Library metadata retrieval failed. Common causes: library not found, library not loaded."""


# "Jumbo" event for getting all things say, a GUI might want w/r/t a Library.
@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryRequest(RequestPayload):
    """Get comprehensive information for a library in a single call.

    Use when: Populating library UIs, implementing library inspection,
    gathering complete library state, optimizing multiple info requests.

    Results: GetAllInfoForLibraryResultSuccess (with comprehensive info) | GetAllInfoForLibraryResultFailure (library not found)
    """

    library: str


@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Comprehensive library information retrieved successfully.

    Args:
        library_metadata_details: Library metadata and version information
        category_details: All categories available in the library
        node_type_name_to_node_metadata_details: Complete node metadata for each node type
    """

    library_metadata_details: GetLibraryMetadataResultSuccess
    category_details: ListCategoriesInLibraryResultSuccess
    node_type_name_to_node_metadata_details: dict[str, GetNodeMetadataFromLibraryResultSuccess]


@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Comprehensive library information retrieval failed. Common causes: library not found, library not loaded, partial failure."""


# The "Jumbo-est" of them all. Grabs all info for all libraries in one fell swoop.
@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesRequest(RequestPayload):
    """Get comprehensive information for all libraries in a single call.

    Use when: Populating complete library catalogs, implementing library browsers,
    gathering system-wide library state, optimizing bulk library operations.

    Results: GetAllInfoForAllLibrariesResultSuccess (with all library info) | GetAllInfoForAllLibrariesResultFailure (system error)
    """


@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Comprehensive information for all libraries retrieved successfully.

    Args:
        library_name_to_library_info: Complete information for each registered library
    """

    library_name_to_library_info: dict[str, GetAllInfoForLibraryResultSuccess]


@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Comprehensive information retrieval for all libraries failed. Common causes: registry not initialized, system error."""


@dataclass
@PayloadRegistry.register
class UnloadLibraryFromRegistryRequest(RequestPayload):
    """Unload a library from the registry.

    Use when: Removing unused libraries, cleaning up library registry,
    preparing for library updates, troubleshooting library issues.

    Args:
        library_name: Name of the library to unload from the registry

    Results: UnloadLibraryFromRegistryResultSuccess | UnloadLibraryFromRegistryResultFailure (library not found, unload error)
    """

    library_name: str


@dataclass
@PayloadRegistry.register
class UnloadLibraryFromRegistryResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Library unloaded successfully from registry."""


@dataclass
@PayloadRegistry.register
class UnloadLibraryFromRegistryResultFailure(ResultPayloadFailure):
    """Library unload failed. Common causes: library not found, library in use, unload error."""


@dataclass
@PayloadRegistry.register
class ReloadAllLibrariesRequest(RequestPayload):
    """WARNING: This request will CLEAR ALL CURRENT WORKFLOW STATE!

    Reloading all libraries requires clearing all existing workflows, nodes, and execution state
    because there is no way to comprehensively erase references to old Python modules.
    All current work will be lost and must be recreated after the reload operation completes.

    Use this operation only when you need to pick up changes to library code during development
    or when library corruption requires a complete reset.
    """


@dataclass
@PayloadRegistry.register
class ReloadAllLibrariesResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """All libraries reloaded successfully. All workflow state has been cleared."""


@dataclass
@PayloadRegistry.register
class ReloadAllLibrariesResultFailure(ResultPayloadFailure):
    """Library reload failed. Common causes: library loading errors, system constraints, initialization failures."""


@dataclass
@PayloadRegistry.register
class LoadLibrariesRequest(RequestPayload):
    """Load all libraries from configuration if they are not already loaded.

    This is a non-destructive operation that checks if libraries are already loaded
    and only performs the initial loading if needed. Unlike ReloadAllLibrariesRequest,
    this does NOT clear any workflow state.

    Use when: Ensuring libraries are loaded at workflow startup, initializing library
    system on demand, preparing library catalog without disrupting existing workflows.

    Results: LoadLibrariesResultSuccess | LoadLibrariesResultFailure (loading error)
    """


@dataclass
@PayloadRegistry.register
class LoadLibrariesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Libraries loaded successfully (or were already loaded)."""


@dataclass
@PayloadRegistry.register
class LoadLibrariesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Library loading failed. Common causes: library loading errors, configuration issues, initialization failures."""


@dataclass
@PayloadRegistry.register
class CheckLibraryUpdateRequest(RequestPayload):
    """Check if a library has updates available via git.

    Use when: Checking for library updates, displaying update status,
    validating library versions, implementing update notifications.

    Args:
        library_name: Name of the library to check for updates

    Results: CheckLibraryUpdateResultSuccess (with update info) | CheckLibraryUpdateResultFailure (library not found, not a git repo, check error)
    """

    library_name: str


@dataclass
@PayloadRegistry.register
class CheckLibraryUpdateResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Library update check completed successfully.

    Args:
        has_update: True if an update is available, False otherwise
        current_version: The current library version
        latest_version: The latest library version from remote
        git_remote: The git remote URL
        git_branch: The current git branch name
    """

    has_update: bool
    current_version: str | None
    latest_version: str | None
    git_remote: str | None
    git_branch: str | None


@dataclass
@PayloadRegistry.register
class CheckLibraryUpdateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Library update check failed. Common causes: library not found, not a git repository, git remote error, network error."""


@dataclass
@PayloadRegistry.register
class UpdateLibraryRequest(RequestPayload):
    """Update a library to the latest version using the appropriate git strategy.

    Automatically detects whether the library uses branch-based or tag-based workflow:
    - Branch-based: Uses git pull --rebase
    - Tag-based: Uses git fetch --tags --force + git checkout (for moving tags like 'latest')

    Use when: Applying library updates, synchronizing with remote changes,
    updating library versions, implementing auto-update features.

    Args:
        library_name: Name of the library to update
        install_dependencies: If True, automatically install dependencies after updating (default: True)

    Results: UpdateLibraryResultSuccess (with version info) | UpdateLibraryResultFailure (library not found, git error, update failure)
    """

    library_name: str
    install_dependencies: bool = True


@dataclass
@PayloadRegistry.register
class UpdateLibraryResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Library updated successfully.

    Args:
        old_version: The previous library version
        new_version: The new library version after update
    """

    old_version: str
    new_version: str


@dataclass
@PayloadRegistry.register
class UpdateLibraryResultFailure(ResultPayloadFailure):
    """Library update failed. Common causes: library not found, not a git repository, git pull error, rebase conflicts."""


@dataclass
@PayloadRegistry.register
class SwitchLibraryBranchRequest(RequestPayload):
    """Switch a library to a different git branch or tag.

    Supports switching to both branches and tags (e.g., 'main', 'develop', 'latest', 'v1.0.0').

    Use when: Switching between branches for development, testing different versions,
    reverting to stable branches, checking out feature branches, or switching to specific tags.

    Args:
        library_name: Name of the library to switch
        ref_name: Name of the branch or tag to switch to

    Results: SwitchLibraryBranchResultSuccess (with ref/version info) | SwitchLibraryBranchResultFailure (library not found, git error, ref not found)
    """

    library_name: str
    ref_name: str


@dataclass
@PayloadRegistry.register
class SwitchLibraryBranchResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Library branch or tag switched successfully.

    Args:
        old_ref: The previous branch or tag name
        new_ref: The new branch or tag name after switch
        old_version: The previous library version
        new_version: The new library version after switch
    """

    old_ref: str
    new_ref: str
    old_version: str
    new_version: str


@dataclass
@PayloadRegistry.register
class SwitchLibraryBranchResultFailure(ResultPayloadFailure):
    """Library ref switch failed. Common causes: library not found, not a git repository, ref not found, git checkout error."""


@dataclass
@PayloadRegistry.register
class DownloadLibraryRequest(RequestPayload):
    """Download a library from a git repository.

    Use when: Installing new libraries from git repositories, downloading third-party libraries,
    setting up development libraries, adding community libraries.

    Args:
        git_url: The git repository URL to clone
        branch_tag_commit: Optional branch, tag, or commit to checkout (defaults to default branch)
        target_directory_name: Optional name for the target directory (defaults to repository name)
        install_dependencies: If True, automatically install dependencies after downloading (default: True)

    Results: DownloadLibraryResultSuccess (with library info) | DownloadLibraryResultFailure (clone error, directory exists)
    """

    git_url: str
    branch_tag_commit: str | None = None
    target_directory_name: str | None = None
    install_dependencies: bool = True


@dataclass
@PayloadRegistry.register
class DownloadLibraryResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Library downloaded successfully.

    Args:
        library_name: Name of the library extracted from griptape_nodes_library.json
        library_path: Full path where the library was downloaded
    """

    library_name: str
    library_path: str


@dataclass
@PayloadRegistry.register
class DownloadLibraryResultFailure(ResultPayloadFailure):
    """Library download failed. Common causes: invalid git URL, network error, target directory already exists, no griptape_nodes_library.json found."""


@dataclass
@PayloadRegistry.register
class InstallLibraryDependenciesRequest(RequestPayload):
    """Install dependencies for a library.

    Use when: Installing or reinstalling dependencies for a library,
    setting up a library's environment, updating dependencies after changes.

    This operation:
    1. Validates the library exists
    2. Gets library metadata for dependencies
    3. Initializes the library's virtual environment
    4. Installs pip dependencies specified in the library metadata
    5. Always installs dependencies without version checks

    Args:
        library_name: Name of the library to install dependencies for

    Results: InstallLibraryDependenciesResultSuccess | InstallLibraryDependenciesResultFailure
    """

    library_name: str


@dataclass
@PayloadRegistry.register
class InstallLibraryDependenciesResultSuccess(ResultPayloadSuccess):
    """Library dependencies installed successfully.

    Args:
        library_name: Name of the library whose dependencies were installed
        dependencies_installed: Number of dependencies that were installed
    """

    library_name: str
    dependencies_installed: int


@dataclass
@PayloadRegistry.register
class InstallLibraryDependenciesResultFailure(ResultPayloadFailure):
    """Library dependency installation failed. Common causes: library not found, no dependencies defined, venv initialization failed, pip install error."""


@dataclass
@PayloadRegistry.register
class SyncLibrariesRequest(RequestPayload):
    """Sync all libraries to latest versions and ensure dependencies are installed.

    Similar to `uv sync` - ensures workspace is in a consistent, up-to-date state.
    This operation:
    1. Downloads missing libraries from git URLs specified in config
    2. Gets all registered libraries (including newly downloaded)
    3. Checks each library for available updates
    4. Updates libraries that have updates available
    5. Installs/updates dependencies for all libraries
    6. Returns comprehensive summary of changes

    Use when: Updating workspace to latest versions, ensuring all libraries are
    up-to-date, setting up development environment, periodic maintenance.

    Args:
        install_dependencies: If True, install dependencies after updating (default: True)

    Results: SyncLibrariesResultSuccess (with summary) | SyncLibrariesResultFailure (sync errors)
    """

    install_dependencies: bool = True


@dataclass
@PayloadRegistry.register
class SyncLibrariesResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Libraries synced successfully.

    Args:
        libraries_downloaded: Number of libraries that were downloaded from git URLs
        libraries_checked: Number of libraries checked for updates
        libraries_updated: Number of libraries that were updated
        update_summary: Dict mapping library names to their update info (old_version -> new_version, or status for downloads)
    """

    libraries_downloaded: int
    libraries_checked: int
    libraries_updated: int
    update_summary: dict[str, dict[str, str]]


@dataclass
@PayloadRegistry.register
class SyncLibrariesResultFailure(ResultPayloadFailure):
    """Library sync failed. Common causes: git errors, network errors, dependency installation failures."""

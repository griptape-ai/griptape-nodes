from __future__ import annotations

import json
import logging
import re
import tomllib
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from pydantic import BaseModel, Field, ValidationError, field_serializer, field_validator

from griptape_nodes.files.path_utils import (
    canonicalize_for_identity,
    canonicalize_for_identity_preserving_symlinks,
    derive_registry_key,
    is_same_file,
    relative_to_keeping_or_following_links,
    resolve_workspace_path,
)
from griptape_nodes.node_library.library_registry import (
    LibraryNameAndVersion,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager

logger = logging.getLogger("griptape_nodes")

# Prefixes of the names derived workflow ids are built from, in uuid.NAMESPACE_URL. Never change
# them: every derived id, and every tab or reference that remembered one, depends on them.
_DERIVED_WORKFLOW_ID_PREFIX = "griptape-nodes:workflow:"
_DERIVED_LIBRARY_WORKFLOW_ID_PREFIX = "griptape-nodes:library-workflow:"


def new_workflow_id() -> str:
    """Mint the permanent id of a new workflow."""
    return uuid.uuid4().hex


def parse_workflow_id(value: str) -> str | None:
    """Return `value` as a workflow id, or None if it is not one.

    A workflow id is any value `uuid.UUID` parses, written as its 32 hex digits, so a dashed
    UUID and its hex form are the same id.
    """
    try:
        return uuid.UUID(value).hex
    except ValueError:
        return None


def derive_workflow_id_for_path(path: str | Path, *, base: Path | None = None) -> str:
    """The id of a workflow file that carries none, until its next save writes it.

    Derived from the path the way the workspace scan names the file, so it is stable across
    restarts, registry refreshes and project switches.
    """
    canonical_path = canonicalize_for_identity_preserving_symlinks(path, base=base)
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{_DERIVED_WORKFLOW_ID_PREFIX}{canonical_path}").hex


def derive_library_workflow_id_for_file(library_name: str, library_root: Path, workflow_file: Path) -> str | None:
    """The derived id of a workflow file inside a library's directory, or None if the file is not in it."""
    path_in_library = relative_to_keeping_or_following_links(workflow_file, library_root)
    if path_in_library is None:
        return None
    return derive_library_workflow_id(library_name, path_in_library)


def derive_library_workflow_id(library_name: str, path_in_library: str | PurePath) -> str:
    """The id of a library workflow that carries none. Library workflows are never written.

    Derived from the library's name and the file's path inside the library, so it survives the
    library being reinstalled somewhere else or bumping its version.
    """
    relative_posix = PurePath(path_in_library).as_posix()
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{_DERIVED_LIBRARY_WORKFLOW_ID_PREFIX}{library_name}/{relative_posix}").hex


# Name of the inline metadata block that carries a workflow's metadata header.
WORKFLOW_METADATA_BLOCK_NAME = "script"

# PEP 723-style inline metadata block: a "# /// <name>" opener, comment-prefixed body lines,
# and a "# ///" closer.
_METADATA_BLOCK_PATTERN = re.compile(r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$")

_TOOL_TABLE = "tool"
_GRIPTAPE_NODES_TABLE = "griptape-nodes"
# How the required table is spelled in messages and in the editor's workflow-load report.
METADATA_TABLE_PATH = f"[{_TOOL_TABLE}.{_GRIPTAPE_NODES_TABLE}]"


class WorkflowMetadataError(Exception):
    """Raised when a workflow file's metadata header cannot be read.

    Callers that only need to know it failed catch this. Callers that report per-stage detail, such
    as the editor's workflow-load report, catch the subclasses below, which carry the values that
    report displays.
    """


class WorkflowMetadataFileError(WorkflowMetadataError):
    """The workflow file itself could not be read."""


class WorkflowMetadataSectionCountError(WorkflowMetadataError):
    """The file does not carry exactly one metadata header."""

    def __init__(self, message: str, *, section_name: str, count: int) -> None:
        super().__init__(message)
        self.section_name = section_name
        self.count = count


class WorkflowMetadataTomlError(WorkflowMetadataError):
    """The metadata header is not valid TOML."""

    def __init__(self, message: str, *, error_message: str) -> None:
        super().__init__(message)
        self.error_message = error_message


class WorkflowMetadataMissingTableError(WorkflowMetadataError):
    """The metadata header carries no `[tool.griptape-nodes]` table."""

    def __init__(self, message: str, *, section_path: str) -> None:
        super().__init__(message)
        self.section_path = section_path


class WorkflowMetadataSchemaError(WorkflowMetadataError):
    """The `[tool.griptape-nodes]` table does not match `WorkflowMetadata`."""

    def __init__(self, message: str, *, section_path: str, error_message: str) -> None:
        super().__init__(message)
        self.section_path = section_path
        self.error_message = error_message


class LibraryNameAndNodeType(NamedTuple):
    library_name: str
    node_type: str


# Type aliases for clarity
type NodeName = str
type ParameterName = str
type ParameterAttribute = str
type ParameterMinimalDict = dict[ParameterAttribute, Any]
type NodeParametersMapping = dict[NodeName, dict[ParameterName, ParameterMinimalDict]]


class WorkflowShape(BaseModel):
    """This structure reflects the input and output shapes extracted from StartNodes and EndNodes inside of the workflow.

    A workflow may have multiple StartNodes and multiple EndNodes, each contributing their parameters
    to the overall workflow shape.

    Structure is:
    - inputs: {start_node_name: {param_name: param_minimal_dict}}
    - outputs: {end_node_name: {param_name: param_minimal_dict}}
    """

    inputs: NodeParametersMapping = Field(default_factory=dict)
    outputs: NodeParametersMapping = Field(default_factory=dict)


class WorkflowMetadata(BaseModel):
    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.22.0"

    # The workflow's permanent identity. None only in files written before schema 0.22.0.
    workflow_id: str | None = None
    name: str
    schema_version: str
    engine_version_created_with: str
    node_libraries_referenced: list[LibraryNameAndVersion]
    node_types_used: set[LibraryNameAndNodeType] = Field(default_factory=set)
    workflows_referenced: list[str] | None = None
    description: str | None = None
    image: str | None = None
    is_griptape_provided: bool | None = False
    is_template: bool | None = False
    # Hidden from the GUI workflow picker. Set on library-internal workflows (e.g. integration tests)
    # that ship inside a library directory but should never surface to users.
    is_internal: bool | None = False
    creation_date: datetime | None = Field(default=None)
    last_modified_date: datetime | None = Field(default=None)
    branched_from: str | None = Field(default=None)
    workflow_shape: WorkflowShape | None = Field(default=None)

    @field_validator("workflow_id", mode="before")
    @classmethod
    def validate_workflow_id(cls, value: Any) -> str | None:
        """Normalize the id to its hex form; treat a malformed one as absent rather than failing the header.

        A header that fails validation makes the workflow unusable, which is out of proportion
        for a damaged id: the file still loads, and gets a derived id until its next save.
        """
        if value is None:
            return None
        if isinstance(value, str):
            workflow_id = parse_workflow_id(value)
            if workflow_id is not None:
                return workflow_id
        logger.warning(
            "Workflow header has a malformed workflow_id %r (expected a UUID). "
            "Ignoring it; the workflow gets a new id when it is next saved.",
            value,
        )
        return None

    @field_serializer("node_types_used")
    def serialize_node_types_used(self, node_types_used: set[LibraryNameAndNodeType]) -> list[list[str]]:
        """Serialize node_types_used as list of tuples for TOML compatibility.

        Sets and NamedTuples are not directly supported by TOML, so we convert the set
        to a list of lists (each inner list represents [library_name, node_type]).
        """
        return [[nt.library_name, nt.node_type] for nt in sorted(node_types_used)]

    @field_validator("node_types_used", mode="before")
    @classmethod
    def validate_node_types_used(cls, value: Any) -> set[LibraryNameAndNodeType]:
        """Deserialize node_types_used from list of lists during TOML loading.

        When loading workflow metadata from TOML files, the node_types_used field
        is stored as a list of [library_name, node_type] pairs that needs to be
        converted back to a set of LibraryNameAndNodeType objects. This validator
        handles the expected input formats:
        - List of lists (from TOML deserialization)
        - Set of LibraryNameAndNodeType (from direct Python construction)
        - Empty list (for workflows with no nodes)
        """
        if isinstance(value, set):
            return value
        if isinstance(value, list):
            return {LibraryNameAndNodeType(library_name=item[0], node_type=item[1]) for item in value}
        msg = f"Expected list or set for node_types_used, got {type(value)}"
        raise ValueError(msg)

    @field_serializer("workflow_shape")
    def serialize_workflow_shape(self, workflow_shape: WorkflowShape | None) -> str | None:
        """Serialize WorkflowShape as JSON string to avoid TOML serialization issues.

        The WorkflowShape contains deeply nested dictionaries with None values that are
        meaningful data (e.g., default_value: None). TOML's nested table format creates
        unreadable output and tomlkit fails on None values in nested structures.
        JSON preserves None as null and keeps the data compact and readable.
        """
        if workflow_shape is None:
            return None
        # Use json.dumps to preserve None values as null, which TOML can handle
        return json.dumps(workflow_shape.model_dump(), separators=(",", ":"))

    @field_validator("workflow_shape", mode="before")
    @classmethod
    def validate_workflow_shape(cls, value: Any) -> WorkflowShape | None:
        """Deserialize WorkflowShape from JSON string during TOML loading.

        When loading workflow metadata from TOML files, the workflow_shape field
        is stored as a JSON string that needs to be converted back to a WorkflowShape
        object. This validator handles the expected input formats:
        - JSON strings (from TOML deserialization)
        - WorkflowShape objects (from direct Python construction)
        - None values (workflows without Start/End nodes)

        If JSON deserialization fails, logs a warning and returns None for graceful
        degradation, consistent with other metadata parsing failures in this codebase.
        """
        if value is None:
            return None
        if isinstance(value, WorkflowShape):
            return value
        if isinstance(value, str):
            try:
                data = json.loads(value)
                return WorkflowShape(**data)
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.error("Failed to deserialize workflow_shape from JSON: %s", e)
                return None
        # Unexpected type - let Pydantic's normal validation handle it
        return value


def find_metadata_blocks(workflow_content: str, block_name: str) -> list[re.Match[str]]:
    """Return every inline metadata block in `workflow_content` whose name is `block_name`."""
    return [match for match in _METADATA_BLOCK_PATTERN.finditer(workflow_content) if match.group("type") == block_name]


def strip_metadata_comment_prefixes(metadata_block: re.Match[str]) -> str:
    """Recover the raw TOML from a metadata block by dropping the comment marker off each line."""
    return "".join(
        line[2:] if line.startswith("# ") else line[1:]
        for line in metadata_block.group("content").splitlines(keepends=True)
    )


def read_workflow_metadata(workflow_file_path: Path) -> WorkflowMetadata:
    """Read the metadata header out of a workflow file.

    Pure file parsing: no registry lookups, no engine requests, and no waiting on library
    registration. Callers that run while libraries are still loading (the library loader itself,
    for instance) can use this directly; `LoadWorkflowMetadata`'s handler wraps it with the file
    checks, dependency checks, and per-stage problem reporting the editor needs.

    Raises:
        WorkflowMetadataFileError: The file could not be read.
        WorkflowMetadataSectionCountError: The file does not carry exactly one metadata header.
        WorkflowMetadataTomlError: The header is not valid TOML.
        WorkflowMetadataMissingTableError: The header has no `[tool.griptape-nodes]` table.
        WorkflowMetadataSchemaError: That table does not match the expected schema.
    """
    try:
        workflow_content = workflow_file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        msg = (
            f"Attempted to read workflow metadata from '{workflow_file_path}'. "
            f"Failed because the file could not be read: {err}"
        )
        raise WorkflowMetadataFileError(msg) from err

    matches = find_metadata_blocks(workflow_content, WORKFLOW_METADATA_BLOCK_NAME)
    if len(matches) != 1:
        msg = (
            f"Attempted to read workflow metadata from '{workflow_file_path}'. Failed because the file has "
            f"{len(matches)} '{WORKFLOW_METADATA_BLOCK_NAME}' metadata sections, and exactly 1 is required. "
            "Open the workflow in the editor and save it to regenerate the header."
        )
        raise WorkflowMetadataSectionCountError(msg, section_name=WORKFLOW_METADATA_BLOCK_NAME, count=len(matches))

    metadata_toml = strip_metadata_comment_prefixes(matches[0])

    # tomllib, not tomlkit: this is a read-only path, and tomlkit builds a formatting-preserving
    # document model that costs ~20x more per header. Only the save path needs tomlkit, to keep the
    # formatting of headers it rewrites.
    try:
        toml_document = tomllib.loads(metadata_toml)
    except tomllib.TOMLDecodeError as err:
        msg = (
            f"Attempted to read workflow metadata from '{workflow_file_path}'. "
            f"Failed because the header is not valid TOML: {err}"
        )
        raise WorkflowMetadataTomlError(msg, error_message=str(err)) from err

    try:
        tool_section = toml_document[_TOOL_TABLE][_GRIPTAPE_NODES_TABLE]
    except (KeyError, TypeError) as err:
        msg = (
            f"Attempted to read workflow metadata from '{workflow_file_path}'. Failed because the header has no "
            f"'{METADATA_TABLE_PATH}' table."
        )
        raise WorkflowMetadataMissingTableError(msg, section_path=METADATA_TABLE_PATH) from err

    try:
        return WorkflowMetadata.model_validate(tool_section)
    except ValidationError as err:
        msg = (
            f"Attempted to read workflow metadata from '{workflow_file_path}'. Failed because the "
            f"'{METADATA_TABLE_PATH}' table does not match the expected schema: {err}"
        )
        raise WorkflowMetadataSchemaError(msg, section_path=METADATA_TABLE_PATH, error_message=str(err)) from err


class WorkflowRegistryError(ValueError):
    """A registry change was refused because it would break one of the registry's invariants."""


class WorkflowPathTakenError(WorkflowRegistryError):
    """Another entry already holds the path, or the name derived from it."""

    def __init__(self, message: str, *, existing: Workflow) -> None:
        super().__init__(message)
        self.existing = existing


class DuplicateWorkflowIdError(WorkflowRegistryError):
    """A different file that is already registered carries the same workflow id."""

    def __init__(self, message: str, *, existing: Workflow) -> None:
        super().__init__(message)
        self.existing = existing


class OpenWorkflowRemovalError(WorkflowRegistryError):
    """The entry belongs to an open workflow, which has to be closed before it can be removed."""


class UnreadableWorkflowHeaderError(WorkflowRegistryError):
    """The workflow's metadata is a placeholder for a header that could not be read, so it must not be written."""


class WorkflowAddressError(ValueError):
    """A request's workflow address names no workflow, or names two different ones."""


class UnknownWorkflowAddressError(WorkflowAddressError):
    """No registered workflow has the id or name a request gave."""


class _IndexKeys(NamedTuple):
    """Where an entry sits in the path and name indexes."""

    file_path: str | None
    name: str
    path_keys: list[str]
    alias_names: list[str]


class _WorkflowRegistry:
    """Workflows known to one engine, keyed by their permanent workflow id.

    Owned by `Engine` and reached through `engine.workflow_registry`. Node libraries, which have
    no engine reference, use the `WorkflowRegistry` classmethods.

    Names and paths are indexes into the id-keyed entries, kept here and nowhere else.
    `set_file_path` is the only way an entry's path changes, so the indexes cannot drift from
    the entries. Lookups never register anything.
    """

    # Prefix of the legacy name of an unsaved (in-memory) workflow: "unsaved:<workflow id>".
    # No path-derived name starts with it: derive_registry_key strips the extension and
    # normalizes separators, but never emits an "unsaved:" literal.
    UNSAVED_KEY_PREFIX: ClassVar[str] = "unsaved:"

    def __init__(
        self,
        config_manager: ConfigManager,
        *,
        is_workflow_open: Callable[[str], bool] | None = None,
    ) -> None:
        self._config_manager = config_manager
        self._is_workflow_open = is_workflow_open
        self._by_id: dict[str, Workflow] = {}
        # Canonical absolute path -> id. Holds every path an entry is known by: its path as named
        # (links kept), the same path with links followed, and the paths of its aliases.
        self._id_by_path: dict[str, str] = {}
        # Legacy name -> id, "unsaved:<id>" included.
        self._id_by_name: dict[str, str] = {}

    def is_open(self, workflow_id: str) -> bool:
        """Whether the workflow with this id is open in the engine."""
        if self._is_workflow_open is None:
            return False
        return self._is_workflow_open(workflow_id)

    def get(self, workflow_id: str) -> Workflow:
        """Return the entry with this id.

        Raises:
            KeyError: No workflow has that id.
        """
        workflow = self._by_id.get(workflow_id)
        if workflow is None:
            msg = f"Attempted to get workflow '{workflow_id}'. Failed because no workflow has that id."
            raise KeyError(msg)
        return workflow

    def find_by_id(self, workflow_id: str) -> Workflow | None:
        """Return the entry with this id, or None."""
        return self._by_id.get(workflow_id)

    def find_by_name(self, name: str) -> Workflow | None:
        """Return the entry with this legacy name ("unsaved:<id>" included), or None.

        An "unsaved:<id>" name may spell the id any way `parse_workflow_id` accepts, such as the
        dashed form earlier engines minted.
        """
        unsaved_id = self.unsaved_name_workflow_id(name)
        if unsaved_id is not None:
            name = f"{self.UNSAVED_KEY_PREFIX}{unsaved_id}"
        workflow_id = self._id_by_name.get(name)
        if workflow_id is None:
            return None
        return self._by_id[workflow_id]

    def unsaved_name_workflow_id(self, name: str) -> str | None:
        """The workflow id in an "unsaved:<id>" name, in its hex form. None for any other name.

        Accepts the dashed "unsaved:<uuid>" names earlier engines minted.
        """
        if not name.startswith(self.UNSAVED_KEY_PREFIX):
            return None
        return parse_workflow_id(name.removeprefix(self.UNSAVED_KEY_PREFIX))

    def find_by_path(self, path: str | Path) -> Workflow | None:
        """Return the entry for the file at `path`, or None. Accepts any path the entry is known by."""
        for path_key in self._path_keys(self.canonical_path(path)):
            workflow_id = self._id_by_path.get(path_key)
            if workflow_id is not None:
                return self._by_id[workflow_id]
        return None

    def resolve_address(
        self,
        *,
        workflow_id: str | None,
        workflow_name: str | None,
        operation: str,
        id_field: str = "workflow_id",
        name_field: str = "workflow_name",
    ) -> Workflow:
        """Return the workflow a request addresses by id, by legacy name, or by both.

        The one place a request's address becomes a registry entry. It never picks: an id or a
        name nobody holds fails, and so do both given for two different workflows, or neither.
        A name is looked up as the registry knows it ("unsaved:<id>" included), never as a
        display name. `operation` completes "Attempted to <operation> workflow ..." in the
        messages, and `id_field` / `name_field` are the request's spelling of the two fields.

        Raises:
            UnknownWorkflowAddressError: No workflow has the id, or the name.
            WorkflowAddressError: Neither is given, or the two name different workflows.
        """
        by_id = None
        if workflow_id is not None:
            by_id = self._find_by_requested_id(workflow_id)
            if by_id is None:
                msg = f"Attempted to {operation} workflow '{workflow_id}'. Failed because no workflow has that id."
                raise UnknownWorkflowAddressError(msg)

        by_name = None
        if workflow_name is not None:
            by_name = self.find_by_name(workflow_name)
            if by_name is None and by_id is None:
                msg = f"Attempted to {operation} workflow '{workflow_name}'. Failed because no workflow has that name."
                raise UnknownWorkflowAddressError(msg)
            if by_id is not None and by_name is not by_id:
                named = "no workflow"
                if by_name is not None:
                    named = f"another workflow (id '{by_name.workflow_id}')"
                msg = (
                    f"Attempted to {operation} workflow '{workflow_id}'. Failed because {id_field} '{workflow_id}' "
                    f"names '{by_id.name}', and {name_field} '{workflow_name}' names {named}. Send only {id_field}."
                )
                raise WorkflowAddressError(msg)

        resolved = by_id
        if resolved is None:
            resolved = by_name
        # Only a request that gives neither field gets here with nothing resolved.
        if resolved is None:
            msg = f"Attempted to {operation} a workflow. Failed because the request names no workflow. Pass {id_field}."
            raise WorkflowAddressError(msg)

        if by_id is None:
            logger.debug(
                "A request to %s addressed workflow '%s' by %s. Addressing by name is deprecated; send %s.",
                operation,
                workflow_name,
                name_field,
                id_field,
            )
        return resolved

    def register_file(
        self,
        path: str | Path,
        metadata: WorkflowMetadata,
        *,
        listed: bool = True,
        metadata_error: str | None = None,
    ) -> Workflow:
        """Register the workflow file at `path` (workspace-relative or absolute).

        The id comes from `metadata.workflow_id`, or is derived from the path when the file
        carries none. A path the registry already holds is refused, and so is an id another
        file holds. A path to a file the registry already holds under another path (the two are
        `os.path.samefile`) becomes an alias of that entry, which is returned.

        `listed=False` keeps the entry out of `list_workflows`, for files registered only
        because they were opened (`push_workflow(file_path=...)`). `metadata_error` is why the
        file's header could not be read, when `metadata` is a placeholder for it.

        Raises:
            ValueError: The file is not on disk.
            WorkflowPathTakenError: Another entry holds the path, or the name derived from it.
            DuplicateWorkflowIdError: Another file holds the id.
        """
        absolute_path = self.canonical_path(path)
        if not absolute_path.is_file():
            msg = f"File path '{absolute_path}' does not exist."
            raise ValueError(msg)

        holder = self.find_by_path(absolute_path)
        if holder is not None and absolute_path in holder.known_paths:
            msg = f"Attempted to register the workflow at '{absolute_path}'. Failed because '{holder.name}' is already registered there."
            raise WorkflowPathTakenError(msg, existing=holder)

        workflow_id = metadata.workflow_id
        if workflow_id is None:
            workflow_id = derive_workflow_id_for_path(absolute_path)

        # The registry knows the file under another path: through a link (the path lookup found
        # it), or a hard link holding the same id. Either way, one workflow known by one more path.
        alias_of = holder
        existing = self._by_id.get(workflow_id)
        if alias_of is None and existing is not None:
            if existing.absolute_path is None or not is_same_file(existing.absolute_path, absolute_path):
                msg = (
                    f"Attempted to register the workflow at '{absolute_path}'. Failed because '{existing.name}' "
                    f"already has its workflow id '{workflow_id}'."
                )
                raise DuplicateWorkflowIdError(msg, existing=existing)
            alias_of = existing

        if alias_of is not None:
            self._add_alias(alias_of, absolute_path)
            return alias_of

        if metadata.workflow_id != workflow_id:
            metadata = metadata.model_copy(update={"workflow_id": workflow_id})
        workflow = Workflow(
            workflow_id=workflow_id,
            metadata=metadata,
            absolute_path=absolute_path,
            listed=listed,
            metadata_error=metadata_error,
        )
        self._add(workflow)
        return workflow

    def register_unsaved(
        self,
        display_name: str,
        working_directory: str | None = None,
        *,
        workflow_id: str | None = None,
        listed: bool = True,
    ) -> Workflow:
        """Register a new unsaved (in-memory) workflow, named "unsaved:<id>".

        `workflow_id` is minted unless given. Only a mirror of another engine's workflow passes
        one, so that both engines call the workflow by the same id.

        Raises:
            DuplicateWorkflowIdError: `workflow_id` is already registered.
        """
        if workflow_id is None:
            workflow_id = new_workflow_id()
        existing = self._by_id.get(workflow_id)
        if existing is not None:
            msg = f"Attempted to register an unsaved workflow. Failed because '{existing.name}' already has the workflow id '{workflow_id}'."
            raise DuplicateWorkflowIdError(msg, existing=existing)

        metadata = WorkflowMetadata(
            workflow_id=workflow_id,
            name=display_name,
            schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
            engine_version_created_with="",
            node_libraries_referenced=[],
            creation_date=datetime.now(UTC),
        )
        workflow = Workflow(
            workflow_id=workflow_id,
            metadata=metadata,
            absolute_path=None,
            working_directory=working_directory,
            listed=listed,
        )
        self._add(workflow)
        return workflow

    def register_unsaved_copy(self, source: Workflow) -> Workflow:
        """Register a new unsaved workflow seeded from `source`, which is how a library workflow opens.

        The copy has an id of its own and no file. It takes the source's display name, description,
        image and shape, is neither library-provided nor a template, and records the source's id as
        its `seeded_from_workflow_id`. The source entry is not changed.
        """
        workflow_id = new_workflow_id()
        source_shape = source.metadata.workflow_shape
        workflow_shape = None
        if source_shape is not None:
            workflow_shape = source_shape.model_copy(deep=True)
        metadata = WorkflowMetadata(
            workflow_id=workflow_id,
            name=source.metadata.name,
            schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
            engine_version_created_with="",
            node_libraries_referenced=[],
            description=source.metadata.description,
            image=source.metadata.image,
            is_griptape_provided=False,
            is_template=False,
            creation_date=datetime.now(UTC),
            workflow_shape=workflow_shape,
        )
        workflow = Workflow(
            workflow_id=workflow_id,
            metadata=metadata,
            absolute_path=None,
            seeded_from_workflow_id=source.workflow_id,
        )
        self._add(workflow)
        return workflow

    def set_file_path(self, workflow: Workflow, new_path: str | Path) -> None:
        """Move `workflow` to the file at `new_path`. The only way an entry's path changes.

        Its id stays the same; its legacy name follows the path. An unsaved workflow becomes a
        saved one. Aliases of the old path are dropped, since they named the old file.

        Raises:
            KeyError: `workflow` is not this registry's entry.
            ValueError: The file is not on disk.
            WorkflowPathTakenError: Another entry holds the path, or the name derived from it.
        """
        if self._by_id.get(workflow.workflow_id) is not workflow:
            msg = f"Attempted to move workflow '{workflow.name}'. Failed because it is not registered."
            raise KeyError(msg)
        absolute_path = self.canonical_path(new_path)
        if not absolute_path.is_file():
            msg = f"File path '{absolute_path}' does not exist."
            raise ValueError(msg)

        holder = self.find_by_path(absolute_path)
        if holder is not None and holder is not workflow:
            msg = f"Attempted to move workflow '{workflow.name}' to '{absolute_path}'. Failed because '{holder.name}' is registered there."
            raise WorkflowPathTakenError(msg, existing=holder)

        self._remove_from_indexes(workflow)
        previous_path = workflow._absolute_path
        previous_aliases = workflow._alias_paths
        workflow._absolute_path = absolute_path
        workflow._alias_paths = []
        try:
            self._add_to_indexes(workflow)
        except WorkflowPathTakenError:
            workflow._absolute_path = previous_path
            workflow._alias_paths = previous_aliases
            self._add_to_indexes(workflow)
            raise

    def remove(self, workflow_id: str) -> Workflow:
        """Remove the entry with this id and return it. An open workflow's entry is refused: close it first.

        Raises:
            KeyError: No workflow has that id.
            OpenWorkflowRemovalError: The workflow is open.
        """
        workflow = self.get(workflow_id)
        if self.is_open(workflow_id):
            msg = f"Attempted to remove workflow '{workflow.name}' from the registry. Failed because it is open. Close it first."
            raise OpenWorkflowRemovalError(msg)
        self._remove_from_indexes(workflow)
        del self._by_id[workflow_id]
        return workflow

    def clear_saved_workflows(self) -> dict[str, Path]:
        """Remove every saved entry ahead of a rescan, except open workflows'. Unsaved entries stay.

        Returns the path each removed id was registered at, so a rescan that finds two files
        with one id can keep the id on the file that had it. Names are rebuilt for the entries
        that stay, because a legacy name is derived against the workspace, which may have
        changed.
        """
        previous_paths: dict[str, Path] = {}
        for workflow in list(self._by_id.values()):
            if workflow.absolute_path is None:
                continue
            if self.is_open(workflow.workflow_id):
                continue
            previous_paths[workflow.workflow_id] = workflow.absolute_path
            del self._by_id[workflow.workflow_id]

        self._id_by_path.clear()
        self._id_by_name.clear()
        for workflow in self._by_id.values():
            self._add_to_indexes(workflow)
        return previous_paths

    def get_workflow_by_name(self, name: str) -> Workflow:
        """Return the entry with this legacy name. Kept for node libraries; prefer `find_by_name`.

        Raises:
            KeyError: No workflow has that name.
        """
        workflow = self.find_by_name(name)
        if workflow is None:
            msg = f"Failed to get Workflow. Workflow with name '{name}' has not been registered."
            raise KeyError(msg)
        return workflow

    def has_workflow_with_name(self, name: str) -> bool:
        """Kept for node libraries; prefer `find_by_name`."""
        return self.find_by_name(name) is not None

    def list_workflows(self) -> dict[str, dict]:
        """Listed workflows' metadata keyed by legacy name. Each carries its `workflow_id`."""
        # Resolved once here rather than per workflow.
        synced_path = self.get_synced_workflows_path()
        return {
            workflow.name: workflow.get_workflow_metadata(is_synced=self._is_in_directory(workflow, synced_path))
            for workflow in self._by_id.values()
            if workflow.listed
        }

    def get_complete_file_path(self, relative_file_path: str) -> str:
        workspace_path = self._config_manager.workspace_path
        resolved_path = resolve_workspace_path(Path(relative_file_path), workspace_path)
        return str(resolved_path)

    def get_synced_workflows_path(self) -> Path:
        synced_directory = self._config_manager.get_config_value("synced_workflows_directory")
        return self._config_manager.get_full_path(synced_directory)

    def get_branches_of_workflow(self, workflow_name: str) -> list[str]:
        """Get the names of all workflows that are branches of the specified workflow."""
        return [workflow.name for workflow in self._by_id.values() if workflow.metadata.branched_from == workflow_name]

    def _find_by_requested_id(self, workflow_id: str) -> Workflow | None:
        """The entry a request's id names. A request may spell it any way `parse_workflow_id` accepts, such as a dashed UUID."""
        parsed_id = parse_workflow_id(workflow_id)
        if parsed_id is None:
            return None
        return self._by_id.get(parsed_id)

    def _is_in_directory(self, workflow: Workflow, directory: Path) -> bool:
        """Whether the workflow's file is inside `directory`. An unsaved workflow is in none."""
        if workflow.file_path is None:
            return False
        complete_file_path = resolve_workspace_path(Path(workflow.file_path), self._config_manager.workspace_path)
        return complete_file_path.is_relative_to(directory)

    def _add(self, workflow: Workflow) -> None:
        self._add_to_indexes(workflow)
        self._by_id[workflow.workflow_id] = workflow

    def _add_alias(self, workflow: Workflow, alias_path: Path) -> None:
        self._remove_from_indexes(workflow)
        workflow._alias_paths.append(alias_path)
        self._add_to_indexes(workflow)

    def _add_to_indexes(self, workflow: Workflow) -> None:
        """Index `workflow` by its paths and names, refusing any another entry holds."""
        index_keys = self._index_keys(workflow)
        for path_key in index_keys.path_keys:
            holder_id = self._id_by_path.get(path_key)
            if holder_id is not None and holder_id != workflow.workflow_id:
                holder = self._by_id[holder_id]
                msg = f"Attempted to register workflow '{index_keys.name}'. Failed because '{holder.name}' is registered at '{path_key}'."
                raise WorkflowPathTakenError(msg, existing=holder)
        for name in [index_keys.name, *index_keys.alias_names]:
            holder_id = self._id_by_name.get(name)
            if holder_id is not None and holder_id != workflow.workflow_id:
                holder = self._by_id[holder_id]
                msg = f"Attempted to register workflow '{name}'. Failed because another workflow is already registered under that name."
                raise WorkflowPathTakenError(msg, existing=holder)

        workflow._file_path = index_keys.file_path
        workflow._name = index_keys.name
        for path_key in index_keys.path_keys:
            self._id_by_path[path_key] = workflow.workflow_id
        for name in [index_keys.name, *index_keys.alias_names]:
            self._id_by_name[name] = workflow.workflow_id

    def _remove_from_indexes(self, workflow: Workflow) -> None:
        for path_key in [key for key, holder_id in self._id_by_path.items() if holder_id == workflow.workflow_id]:
            del self._id_by_path[path_key]
        for name in [key for key, holder_id in self._id_by_name.items() if holder_id == workflow.workflow_id]:
            del self._id_by_name[name]

    def _index_keys(self, workflow: Workflow) -> _IndexKeys:
        if workflow.absolute_path is None:
            return _IndexKeys(
                file_path=None,
                name=f"{self.UNSAVED_KEY_PREFIX}{workflow.workflow_id}",
                path_keys=[],
                alias_names=[],
            )

        file_path = self._registry_form(workflow.absolute_path)
        path_keys = self._path_keys(workflow.absolute_path)
        alias_names = []
        for alias_path in workflow._alias_paths:
            path_keys.extend(self._path_keys(alias_path))
            alias_names.append(derive_registry_key(self._registry_form(alias_path)))
        return _IndexKeys(
            file_path=file_path,
            name=derive_registry_key(file_path),
            path_keys=path_keys,
            alias_names=alias_names,
        )

    def _registry_form(self, absolute_path: Path) -> str:
        """The form `Workflow.file_path` reports: workspace-relative inside the workspace, else absolute."""
        relative_path = relative_to_keeping_or_following_links(absolute_path, self._config_manager.workspace_path)
        if relative_path is None:
            return str(absolute_path)
        return str(relative_path)

    def canonical_path(self, path: str | Path) -> Path:
        """The absolute form the registry knows a workflow file by: workspace-anchored, links kept as named."""
        return canonicalize_for_identity_preserving_symlinks(path, base=self._config_manager.workspace_path)

    @staticmethod
    def _path_keys(absolute_path: Path) -> list[str]:
        """The keys a path is indexed under: as named, and with links followed."""
        kept = str(absolute_path)
        followed = str(canonicalize_for_identity(absolute_path))
        if followed == kept:
            return [kept]
        return [kept, followed]


class WorkflowRegistry:
    """The current engine's workflow registry, for node libraries.

    Kept for node libraries that call these classmethods. Each one forwards to
    `current_engine().workflow_registry`. Engine-internal code uses `engine.workflow_registry`.
    """

    UNSAVED_KEY_PREFIX: ClassVar[str] = _WorkflowRegistry.UNSAVED_KEY_PREFIX

    @classmethod
    def get_workflow_by_name(cls, name: str) -> Workflow:
        return _current_registry().get_workflow_by_name(name)

    @classmethod
    def has_workflow_with_name(cls, name: str) -> bool:
        return _current_registry().has_workflow_with_name(name)

    @classmethod
    def list_workflows(cls) -> dict[str, dict]:
        return _current_registry().list_workflows()

    @classmethod
    def get_complete_file_path(cls, relative_file_path: str) -> str:
        return _current_registry().get_complete_file_path(relative_file_path)

    @classmethod
    def get_branches_of_workflow(cls, workflow_name: str) -> list[str]:
        return _current_registry().get_branches_of_workflow(workflow_name)


def _current_registry() -> _WorkflowRegistry:
    # Deferred import: the engine module imports the event payloads, which import this module.
    from griptape_nodes.retained_mode.engine import current_engine

    return current_engine().workflow_registry


class Workflow:
    """A workflow the registry knows, saved or not.

    A workflow has two possible states:
    - **Saved**: backed by a file on disk. `absolute_path` is the file; `file_path` is the same
      file in the registry's form (workspace-relative inside the workspace, else absolute).
    - **Unsaved**: in-memory only. `file_path` and `absolute_path` are None. Becomes saved when
      the registry's `set_file_path` gives it a file.

    `workflow_id` never changes. Only the registry changes the path, so its indexes stay right.
    """

    def __init__(  # noqa: PLR0913
        self,
        workflow_id: str,
        metadata: WorkflowMetadata,
        absolute_path: Path | None,
        *,
        working_directory: str | None = None,
        listed: bool = True,
        metadata_error: str | None = None,
        seeded_from_workflow_id: str | None = None,
    ) -> None:
        self._workflow_id = workflow_id
        self._metadata = metadata
        self._absolute_path = absolute_path
        # Other paths to the same file (os.path.samefile), so `find_by_path` answers for each.
        self._alias_paths: list[Path] = []
        # The folder an unsaved workflow was created in, which saves and macros use until it has a file.
        self._working_directory = working_directory
        # False for files registered only because they were opened, which `list_workflows` hides.
        self._listed = listed
        # Why the header could not be read, so a placeholder `metadata` is never written back to it.
        self._metadata_error = metadata_error
        # The library workflow this one was opened as a copy of.
        self._seeded_from_workflow_id = seeded_from_workflow_id
        # Path in the registry's form, and the legacy name: the registry sets both when it indexes the entry.
        self._file_path: str | None = None
        self._name = ""

    @property
    def workflow_id(self) -> str:
        return self._workflow_id

    @property
    def metadata(self) -> WorkflowMetadata:
        return self._metadata

    @metadata.setter
    def metadata(self, new_metadata: WorkflowMetadata) -> None:
        """Replace the metadata. A replacement with no id inherits this workflow's; a different id is refused."""
        if new_metadata.workflow_id is not None and new_metadata.workflow_id != self._workflow_id:
            msg = (
                f"Attempted to change the workflow id of '{self._name}' from '{self._workflow_id}' to "
                f"'{new_metadata.workflow_id}'. Failed because a workflow's id never changes."
            )
            raise ValueError(msg)
        if new_metadata.workflow_id is None:
            new_metadata = new_metadata.model_copy(update={"workflow_id": self._workflow_id})
        self._metadata = new_metadata
        # Real metadata replaced the placeholder, so the header problem no longer applies.
        self._metadata_error = None

    def metadata_for_header(self) -> WorkflowMetadata:
        """This workflow's metadata, to build a file's header from.

        Raises:
            UnreadableWorkflowHeaderError: The metadata is a placeholder for a header that could
                not be read. Writing it would replace what the header holds, its library list
                among them, with made-up values.
        """
        if self._metadata_error is not None:
            msg = (
                "its file's metadata header could not be read, and writing new metadata would replace what "
                f"the header holds. Save the workflow to regenerate the header. {self._metadata_error}"
            )
            raise UnreadableWorkflowHeaderError(msg)
        return self._metadata

    @property
    def metadata_error(self) -> str | None:
        """Why the file's header could not be read, when `metadata` is a placeholder for it.

        Set for a file opened despite an unreadable header. Cleared when real metadata replaces
        the placeholder, as a save does.
        """
        return self._metadata_error

    @property
    def name(self) -> str:
        """The legacy registry name: the file path without its extension, or "unsaved:<id>"."""
        return self._name

    @property
    def file_path(self) -> str | None:
        """The file, workspace-relative inside the workspace and absolute outside it. None while unsaved."""
        return self._file_path

    @property
    def absolute_path(self) -> Path | None:
        """The file's absolute path, with links kept as named. None while unsaved."""
        return self._absolute_path

    @property
    def known_paths(self) -> list[Path]:
        """Every path this workflow's file is registered by: its own and its aliases'."""
        if self._absolute_path is None:
            return []
        return [self._absolute_path, *self._alias_paths]

    @property
    def working_directory(self) -> str | None:
        return self._working_directory

    @working_directory.setter
    def working_directory(self, working_directory: str | None) -> None:
        self._working_directory = working_directory

    @property
    def seeded_from_workflow_id(self) -> str | None:
        """The id of the library workflow this one was opened as a copy of, or None if it is not such a copy."""
        return self._seeded_from_workflow_id

    @property
    def listed(self) -> bool:
        """Whether `list_workflows` reports this workflow. False for files registered only because they were opened."""
        return self._listed

    @listed.setter
    def listed(self, listed: bool) -> None:
        self._listed = listed

    @property
    def is_saved(self) -> bool:
        """True if this workflow is backed by a file on disk."""
        return self._absolute_path is not None

    def get_workflow_metadata(self, *, is_synced: bool) -> dict:
        """The header metadata as a dict, plus what the file holds outside the header. `is_synced` comes from the registry."""
        # Convert from the Pydantic schema.
        ret_val = {**self.metadata.model_dump()}

        # The schema doesn't have the file path in it, because it is baked into the file itself.
        # Customers of this function need that, so let's stuff it in.
        ret_val["workflow_id"] = self.workflow_id
        ret_val["file_path"] = self.file_path
        ret_val["is_saved"] = self.is_saved
        ret_val["is_synced"] = is_synced
        return ret_val

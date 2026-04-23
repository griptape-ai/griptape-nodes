"""ProjectFileDestination - project-aware FileDestination built from a situation template."""

import logging
from pathlib import Path

from griptape_nodes.common.macro_parser import ParsedMacro, ParsedVariable
from griptape_nodes.common.project_templates.situation import SituationFilePolicy
from griptape_nodes.files.file import File, FileDestination
from griptape_nodes.files.path_utils import FilenameParts
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectRequest,
    AttemptMapAbsolutePathToProjectResultSuccess,
    GetCurrentProjectRequest,
    GetCurrentProjectResultSuccess,
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
    GetSituationRequest,
    GetSituationResultSuccess,
    MacroPath,
)
from griptape_nodes.retained_mode.file_metadata.sidecar_metadata import (
    SidecarContent,
    SituationMetadata,
    SituationPolicy,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")

FALLBACK_MACRO_TEMPLATE = "{outputs}/{node_name?:_}{file_name_base}{_index?:03}.{file_extension}"


def resolve_file_extension_macro(extension: str, extra_vars: dict[str, str | int] | None = None) -> str | None:
    """Resolve an extension to a folder fragment via the current project's template.

    Looks up the extension (case-insensitively) in the current project's
    `file_extension_macros` mapping. Plain names like `"images"` are returned
    as-is; values containing macro syntax (e.g. `"{outputs}/videos"`) are
    resolved via `GetPathForMacroRequest` against the project's builtins and
    directory definitions, plus any caller-supplied `extra_vars` (e.g.
    `node_name`, `parameter_name`, `sub_dirs`, `_index`). Filename parts
    (`file_name_base`, `file_extension`) are intentionally excluded --
    extension macros are a routing layer, not a filename layer.

    Returns None when the extension is empty, no project is loaded, the
    extension is unmapped, or resolution fails -- so the optional
    `{file_extension_macro?:/}` slot degrades cleanly instead of routing
    unknown types into an arbitrary folder or surfacing as a crash.
    """
    if not extension:
        return None
    project_result = GriptapeNodes.handle_request(GetCurrentProjectRequest())
    if not isinstance(project_result, GetCurrentProjectResultSuccess):
        return None
    raw_macro = project_result.project_info.template.file_extension_macros.get(extension.lower())
    if raw_macro is None:
        return None
    # Plain folder name -- skip the event round-trip.
    if "{" not in raw_macro:
        return raw_macro
    # Filename parts belong to the situation macro's filename section, not
    # the routing layer. Smuggling them through extension macros would let
    # routing encode filenames.
    resolution_vars: dict[str, str | int] = {
        k: v for k, v in (extra_vars or {}).items() if k not in ("file_name_base", "file_extension")
    }
    resolve_result = GriptapeNodes.handle_request(
        GetPathForMacroRequest(parsed_macro=ParsedMacro(raw_macro), variables=resolution_vars)
    )
    if not isinstance(resolve_result, GetPathForMacroResultSuccess):
        logger.warning(
            "Failed to resolve file_extension_macros value for '%s' (%r): %s. Falling back to no routing.",
            extension,
            raw_macro,
            resolve_result.result_details,
        )
        return None
    return str(resolve_result.resolved_path)


def _template_references(parsed_macro: ParsedMacro, variable_name: str) -> bool:
    """Return True if the parsed template has a variable segment with the given name."""
    return any(
        isinstance(segment, ParsedVariable) and segment.info.name == variable_name
        for segment in parsed_macro.segments
    )


def _inject_file_extension_macro(macro_path: MacroPath) -> MacroPath:
    """Populate `file_extension_macro` in a MacroPath's variables when the template needs it.

    No-op when the template doesn't reference `{file_extension_macro...}`, when
    the variable is already set by the caller, or when there's no
    `file_extension` in the variables to look up a mapping for. Otherwise,
    resolves the extension against the current project's
    ``file_extension_macros`` mapping and returns a new MacroPath with the
    value injected.
    """
    if not _template_references(macro_path.parsed_macro, "file_extension_macro"):
        return macro_path
    variables = macro_path.variables
    if "file_extension_macro" in variables:
        return macro_path
    extension = variables.get("file_extension")
    if not isinstance(extension, str) or not extension:
        return macro_path
    resolved = resolve_file_extension_macro(extension, dict(variables))
    if resolved is None:
        return macro_path
    return MacroPath(macro_path.parsed_macro, {**variables, "file_extension_macro": resolved})


SITUATION_TO_FILE_POLICY: dict[str, ExistingFilePolicy] = {
    SituationFilePolicy.CREATE_NEW: ExistingFilePolicy.CREATE_NEW,
    SituationFilePolicy.OVERWRITE: ExistingFilePolicy.OVERWRITE,
    SituationFilePolicy.FAIL: ExistingFilePolicy.FAIL,
    SituationFilePolicy.PROMPT: ExistingFilePolicy.CREATE_NEW,  # PROMPT has no direct mapping; fall back to CREATE_NEW
}


class ProjectFileDestination(FileDestination):
    """A FileDestination that maps written absolute paths back to project macro form.

    After each write, attempts to convert the resulting absolute path to its
    portable macro representation (e.g. ``{outputs}/image.png``).  Falls back
    to the plain absolute path if mapping is not possible.

    Construct directly with a ``MacroPath`` and write policy, or use the
    ``from_situation`` classmethod to build from a situation name and filename.

    When the path template references ``{file_extension_macro...}`` and the
    variable isn't already provided, the extension is looked up in the
    current project's ``file_extension_macros`` mapping and injected into the
    variables. This keeps per-extension routing (images/, videos/, etc.)
    consistent across every caller (``from_situation``, ``FileOutputSetting``,
    etc.) without each of them duplicating the lookup.
    """

    def __init__(
        self,
        file_path: str | MacroPath,
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        append: bool = False,
        create_parents: bool = True,
        file_metadata: SidecarContent | None = None,
    ) -> None:
        if isinstance(file_path, MacroPath):
            file_path = _inject_file_extension_macro(file_path)
        super().__init__(
            file_path,
            existing_file_policy=existing_file_policy,
            append=append,
            create_parents=create_parents,
            file_metadata=file_metadata,
        )

    def write_bytes(self, content: bytes) -> File:
        return self._map_to_macro_file(super().write_bytes(content))

    async def awrite_bytes(self, content: bytes) -> File:
        return self._map_to_macro_file(await super().awrite_bytes(content))

    def write_text(self, content: str, encoding: str = "utf-8") -> File:
        return self._map_to_macro_file(super().write_text(content, encoding))

    async def awrite_text(self, content: str, encoding: str = "utf-8") -> File:
        return self._map_to_macro_file(await super().awrite_text(content, encoding))

    def _map_to_macro_file(self, result_file: File) -> File:
        """Attempt to convert the written path to its portable macro form.

        Returns a File holding the macro template (e.g. ``{outputs}/image.png``)
        when the path is inside a project directory, so callers can store a
        portable reference via ``file.as_macro()``.  Falls back to the original
        File (absolute path) if mapping is not possible.
        """
        map_result = GriptapeNodes.handle_request(
            AttemptMapAbsolutePathToProjectRequest(absolute_path=Path(result_file.resolve()))
        )
        if isinstance(map_result, AttemptMapAbsolutePathToProjectResultSuccess) and map_result.mapped_path is not None:
            return File(map_result.mapped_path)
        return result_file

    @classmethod
    def from_situation(
        cls,
        filename: str,
        situation: str,
        **extra_vars: str | int,
    ) -> "ProjectFileDestination":
        """Build a ProjectFileDestination from a project situation template.

        Looks up the named situation in the current project to obtain the macro
        template and write policy, then constructs the destination.

        Args:
            filename: Filename to parse into base and extension components.
            situation: Situation name to look up in the current project.
            **extra_vars: Additional macro variables (e.g., node_name="MyNode", _index=1).
        """
        result = GriptapeNodes.handle_request(GetSituationRequest(situation_name=situation))

        if isinstance(result, GetSituationResultSuccess):
            situation_obj = result.situation
            macro_template = situation_obj.macro
            on_collision = situation_obj.policy.on_collision
            existing_file_policy = SITUATION_TO_FILE_POLICY.get(on_collision, ExistingFilePolicy.CREATE_NEW)
            create_dirs = situation_obj.policy.create_dirs
        else:
            logger.error("Failed to load situation '%s', using fallback macro template", situation)
            situation_obj = None
            macro_template = FALLBACK_MACRO_TEMPLATE
            existing_file_policy = ExistingFilePolicy.CREATE_NEW
            create_dirs = True

        parts = FilenameParts.from_filename(filename)
        variables: dict[str, str | int] = {
            "file_name_base": parts.stem,
            "file_extension": parts.extension,
            **extra_vars,
        }

        # The {file_extension_macro} slot is populated by ProjectFileDestination's
        # __init__ via _inject_file_extension_macro, so every caller
        # (from_situation, FileOutputSetting, etc.) routes consistently.
        macro_path = _inject_file_extension_macro(MacroPath(ParsedMacro(macro_template), variables))

        file_metadata = (
            SidecarContent(
                situation=SituationMetadata(
                    name=situation,
                    macro=situation_obj.macro,
                    policy=SituationPolicy(
                        on_collision=situation_obj.policy.on_collision,
                        create_dirs=situation_obj.policy.create_dirs,
                    ),
                    variables={k: str(v) for k, v in macro_path.variables.items()},
                ),
            )
            if situation_obj is not None
            else None
        )

        return cls(
            macro_path,
            existing_file_policy=existing_file_policy,
            create_parents=create_dirs,
            file_metadata=file_metadata,
        )

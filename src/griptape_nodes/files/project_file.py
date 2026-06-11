"""ProjectFileDestination - project-aware FileDestination built from a situation template."""

import logging
from pathlib import Path
from typing import NamedTuple

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.project_templates.situation import SituationFilePolicy, SituationTemplate
from griptape_nodes.files.file import File, FileDestination
from griptape_nodes.files.path_utils import FilenameParts
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectRequest,
    AttemptMapAbsolutePathToProjectResultSuccess,
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


SITUATION_TO_FILE_POLICY: dict[str, ExistingFilePolicy] = {
    SituationFilePolicy.CREATE_NEW: ExistingFilePolicy.CREATE_NEW,
    SituationFilePolicy.OVERWRITE: ExistingFilePolicy.OVERWRITE,
    SituationFilePolicy.FAIL: ExistingFilePolicy.FAIL,
    SituationFilePolicy.PROMPT: ExistingFilePolicy.CREATE_NEW,  # PROMPT has no direct mapping; fall back to CREATE_NEW
}


class ResolvedSituation(NamedTuple):
    """Result of looking up a project situation by name.

    Attributes:
        macro_template: The macro template string for the situation.
        existing_file_policy: Mapped file collision policy.
        create_parents: Whether to create intermediate directories.
        situation_obj: Raw situation template, or None when the lookup failed and
            fallback values are in use.
    """

    macro_template: str
    existing_file_policy: ExistingFilePolicy
    create_parents: bool
    situation_obj: SituationTemplate | None


def resolve_situation(
    situation_name: str,
    fallback_macro: str,
    default_policy: ExistingFilePolicy = ExistingFilePolicy.CREATE_NEW,
) -> ResolvedSituation:
    """Look up a situation by name and return its resolved configuration.

    Falls back to fallback_macro and default_policy when the situation cannot be loaded.

    Args:
        situation_name: Situation name to look up in the current project.
        fallback_macro: Macro template to use when the situation cannot be found.
        default_policy: ExistingFilePolicy to use in the fallback case.

    Returns:
        ResolvedSituation with macro_template, existing_file_policy, create_parents,
        and situation_obj (None when falling back).
    """
    result = GriptapeNodes.handle_request(GetSituationRequest(situation_name=situation_name))
    if isinstance(result, GetSituationResultSuccess):
        situation_obj = result.situation
        return ResolvedSituation(
            macro_template=situation_obj.macro,
            existing_file_policy=SITUATION_TO_FILE_POLICY.get(situation_obj.policy.on_collision, default_policy),
            create_parents=situation_obj.policy.create_dirs,
            situation_obj=situation_obj,
        )
    logger.error("Failed to load situation '%s', using fallback macro template", situation_name)
    return ResolvedSituation(
        macro_template=fallback_macro,
        existing_file_policy=default_policy,
        create_parents=True,
        situation_obj=None,
    )


def _attempt_map_to_project(absolute_path: Path) -> str | None:
    """Fire AttemptMapAbsolutePathToProjectRequest; return the mapped macro path string or None."""
    map_result = GriptapeNodes.handle_request(AttemptMapAbsolutePathToProjectRequest(absolute_path=absolute_path))
    if isinstance(map_result, AttemptMapAbsolutePathToProjectResultSuccess) and map_result.mapped_path is not None:
        return map_result.mapped_path
    return None


class ProjectFileDestination(FileDestination):
    """A FileDestination that maps written absolute paths back to project macro form.

    After each write, attempts to convert the resulting absolute path to its
    portable macro representation (e.g. ``{outputs}/image.png``).  Falls back
    to the plain absolute path if mapping is not possible.

    Construct directly with a ``MacroPath`` and write policy, or use the
    ``from_situation`` classmethod to build from a situation name and filename.

    Derivation rules (e.g. ``file_extension_directory``) run centrally inside
    the ``GetPathForMacroRequest`` handler, so any MacroPath stored here gets
    its derived variables filled in at resolution time without callers having
    to pre-apply them.
    """

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
        mapped = _attempt_map_to_project(Path(result_file.resolve()))
        if mapped is not None:
            return File(mapped)
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
        resolved = resolve_situation(situation, FALLBACK_MACRO_TEMPLATE)
        situation_obj = resolved.situation_obj
        existing_file_policy = resolved.existing_file_policy
        create_dirs = resolved.create_parents

        parts = FilenameParts.from_filename(filename)
        variables: dict[str, str | int] = {
            "file_name_base": parts.stem,
            "file_extension": parts.extension,
            **extra_vars,
        }
        # When the filename carries its own relative directory component (e.g.
        # "foo/bar/output.png"), populate sub_dirs so situations with {sub_dirs?:/}
        # route the file into that sub-directory. An explicit sub_dirs kwarg in
        # extra_vars takes precedence. Absolute filenames still flow through the
        # macro; we skip the sub_dirs override for them so we don't feed a
        # leading-slash value into the macro substitution.
        directory_str = str(parts.directory)
        if directory_str and directory_str != "." and not parts.directory.is_absolute() and "sub_dirs" not in variables:
            variables["sub_dirs"] = directory_str

        # Derived variables (e.g. file_extension_directory) are injected by the
        # GetPathForMacroRequest handler at resolve time, so we store only the
        # caller-supplied variables here. The sidecar records the raw inputs;
        # anyone re-resolving the path against the current project gets the
        # same derived values the write used.
        macro_path = MacroPath(ParsedMacro(resolved.macro_template), variables)

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

        # Absolute filenames bypass the situation macro: the caller is declaring
        # an explicit on-disk location, so honor it verbatim rather than treating
        # the leading-slash directory as sub_dirs within {outputs}/etc. Drop the
        # sidecar metadata too -- the situation macro + variables we computed
        # above won't re-resolve to the actual on-disk location, so recording
        # them would produce a dishonest provenance trail.
        if parts.directory.is_absolute():
            return cls(
                filename,
                existing_file_policy=existing_file_policy,
                create_parents=create_dirs,
                file_metadata=None,
            )

        return cls(
            macro_path,
            existing_file_policy=existing_file_policy,
            create_parents=create_dirs,
            file_metadata=file_metadata,
        )

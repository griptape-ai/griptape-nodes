"""ProjectFileDestination - project-aware FileDestination built from a situation template."""

import logging

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.project_templates.situation import SituationFilePolicy
from griptape_nodes.files.file import FileDestination
from griptape_nodes.files.path_utils import FilenameParts
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetSituationRequest,
    GetSituationResultSuccess,
    MacroPath,
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


class ProjectFileDestination(FileDestination):
    """A FileDestination built from a project situation template.

    Resolves the macro template and write policy from the named situation in the
    current project, then delegates all I/O to the parent FileDestination.
    """

    def __init__(
        self,
        filename: str,
        situation: str,
        node_name: str,
        **extra_vars: str | int,
    ) -> None:
        """Build a FileDestination from a project situation template.

        Args:
            filename: Filename to parse into base and extension components.
            situation: Situation name to look up in the current project.
            node_name: Node name for the {node_name} macro variable.
            **extra_vars: Additional macro variables (e.g., _index=1).
        """
        result = GriptapeNodes.handle_request(GetSituationRequest(situation_name=situation))

        if isinstance(result, GetSituationResultSuccess):
            macro_template = result.situation.macro
            on_collision = result.situation.policy.on_collision
            existing_file_policy = SITUATION_TO_FILE_POLICY.get(on_collision, ExistingFilePolicy.CREATE_NEW)
            create_dirs = result.situation.policy.create_dirs
        else:
            logger.error("%s: Failed to load situation '%s', using fallback macro template", node_name, situation)
            macro_template = FALLBACK_MACRO_TEMPLATE
            existing_file_policy = ExistingFilePolicy.CREATE_NEW
            create_dirs = True

        parts = FilenameParts.from_filename(filename)
        variables: dict[str, str | int] = {
            "file_name_base": parts.stem,
            "file_extension": parts.extension,
            "node_name": node_name,
            **extra_vars,
        }

        macro_path = MacroPath(ParsedMacro(macro_template), variables)
        super().__init__(
            macro_path,
            existing_file_policy=existing_file_policy,
            create_parents=create_dirs,
        )

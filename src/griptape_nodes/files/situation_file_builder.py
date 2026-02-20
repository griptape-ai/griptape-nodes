"""Shared utilities for building File objects from project situation templates."""

import logging
from dataclasses import dataclass

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.project_templates.situation import SituationFilePolicy
from griptape_nodes.files.file import FileDestination
from griptape_nodes.files.path_utils import parse_filename_components
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


@dataclass(frozen=True)
class SituationConfig:
    """Configuration resolved from a project situation template.

    Attributes:
        macro_template: The macro template string for path resolution.
        existing_file_policy: The ExistingFilePolicy to apply during file writes.
        on_collision_value: The raw SituationFilePolicy string (for UI display).
    """

    macro_template: str
    existing_file_policy: ExistingFilePolicy
    on_collision_value: str


def fetch_situation_config(situation_name: str, caller_name: str) -> SituationConfig:
    """Fetch situation macro and policy from the project, with fallback defaults.

    Args:
        situation_name: Situation template name (e.g., "save_node_output").
        caller_name: Name of the calling node/component, used in log messages.

    Returns:
        SituationConfig with resolved macro_template, existing_file_policy, and on_collision_value.
    """
    result = GriptapeNodes.handle_request(GetSituationRequest(situation_name=situation_name))

    if isinstance(result, GetSituationResultSuccess):
        on_collision = result.situation.policy.on_collision
        return SituationConfig(
            macro_template=result.situation.macro,
            existing_file_policy=SITUATION_TO_FILE_POLICY.get(on_collision, ExistingFilePolicy.CREATE_NEW),
            on_collision_value=on_collision,
        )

    logger.error(
        "%s: Failed to load situation '%s', using fallback macro template",
        caller_name,
        situation_name,
    )
    return SituationConfig(
        macro_template=FALLBACK_MACRO_TEMPLATE,
        existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        on_collision_value=SituationFilePolicy.CREATE_NEW,
    )


def build_file_from_situation(
    filename: str,
    situation_config: SituationConfig,
    node_name: str,
    *,
    default_extension: str = "png",
    extra_variables: dict[str, str | int] | None = None,
) -> FileDestination:
    """Build a FileDestination with a MacroPath from a situation template and filename.

    Parses the filename into base and extension components, then constructs
    a MacroPath using the provided template and variables.

    Args:
        filename: The filename to parse (e.g., "output.png").
        situation_config: Resolved situation configuration with macro template and policy.
        node_name: Node name for the {node_name} macro variable.
        default_extension: Extension to use if filename has no suffix.
        extra_variables: Additional macro variables to include.

    Returns:
        FileDestination with an unresolved MacroPath and baked-in write policy.
    """
    file_name_base, file_extension = parse_filename_components(filename, default_extension=default_extension)

    variables: dict[str, str | int] = {
        "file_name_base": file_name_base,
        "file_extension": file_extension,
        "node_name": node_name,
        **(extra_variables or {}),
    }

    macro_path = MacroPath(ParsedMacro(situation_config.macro_template), variables)
    return FileDestination(macro_path, existing_file_policy=situation_config.existing_file_policy)

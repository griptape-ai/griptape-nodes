"""Resolve a project situation name into file-write configuration."""

import logging
from typing import NamedTuple

from griptape_nodes.common.project_templates.situation import SituationFilePolicy, SituationTemplate
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import GetSituationRequest, GetSituationResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")

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

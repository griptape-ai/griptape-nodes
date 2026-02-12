"""Utilities for fetching and working with situation templates."""

import logging
from typing import NamedTuple

from griptape_nodes.project.policy_constants import SITUATION_TO_EXISTING_POLICY
from griptape_nodes.project.types import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetSituationRequest,
    GetSituationResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")


class SituationConfig(NamedTuple):
    """Configuration loaded from a situation template."""

    macro_template: str
    policy: ExistingFilePolicy
    create_dirs: bool


def fetch_situation_config(
    situation_name: str,
    node_name: str | None = None,
) -> SituationConfig | None:
    """Fetch situation configuration from ProjectManager.

    Args:
        situation_name: Name of situation to fetch
        node_name: Optional node name for logging context

    Returns:
        SituationConfig with (macro_template, policy, create_dirs), or None if fetch fails
    """
    request = GetSituationRequest(situation_name=situation_name)
    result = GriptapeNodes.ProjectManager().on_get_situation_request(request)

    if not isinstance(result, GetSituationResultSuccess):
        context = f"{node_name}: " if node_name else ""
        logger.warning("%sFailed to fetch situation '%s'", context, situation_name)
        return None

    situation = result.situation

    policy = SITUATION_TO_EXISTING_POLICY.get(
        situation.policy.on_collision,
        ExistingFilePolicy.CREATE_NEW,
    )
    create_dirs = situation.policy.create_dirs

    return SituationConfig(
        macro_template=situation.macro,
        policy=policy,
        create_dirs=create_dirs,
    )

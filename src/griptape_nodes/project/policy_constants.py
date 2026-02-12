"""Policy mapping constants for file save operations.

Centralizes conversion between three policy enum types:
- SituationFilePolicy: Template-level policies (includes PROMPT)
- ExistingFilePolicy: Project-level policies (used in ProjectFileSaveConfig)
- OSExistingFilePolicy: OS event-level policies (used in WriteFileRequest)

Usage:
    from griptape_nodes.project.policy_constants import SITUATION_TO_EXISTING_POLICY

    policy = SITUATION_TO_EXISTING_POLICY.get(
        situation.policy.on_collision,
        ExistingFilePolicy.CREATE_NEW
    )
"""

from griptape_nodes.common.project_templates.situation import SituationFilePolicy
from griptape_nodes.project.types import ExistingFilePolicy
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy as OSExistingFilePolicy,
)

# UI string constants
POLICY_UI_CREATE_NEW = "create new file"
POLICY_UI_OVERWRITE = "overwrite existing file"
POLICY_UI_FAIL = "fail if file exists"

# SituationFilePolicy → ExistingFilePolicy
SITUATION_TO_EXISTING_POLICY = {
    SituationFilePolicy.CREATE_NEW: ExistingFilePolicy.CREATE_NEW,
    SituationFilePolicy.OVERWRITE: ExistingFilePolicy.OVERWRITE,
    SituationFilePolicy.FAIL: ExistingFilePolicy.FAIL,
}

# ExistingFilePolicy → OSExistingFilePolicy
EXISTING_TO_OS_POLICY = {
    ExistingFilePolicy.CREATE_NEW: OSExistingFilePolicy.CREATE_NEW,
    ExistingFilePolicy.OVERWRITE: OSExistingFilePolicy.OVERWRITE,
    ExistingFilePolicy.FAIL: OSExistingFilePolicy.FAIL,
}

# SituationFilePolicy → UI string
SITUATION_POLICY_TO_UI_STRING = {
    SituationFilePolicy.CREATE_NEW: POLICY_UI_CREATE_NEW,
    SituationFilePolicy.OVERWRITE: POLICY_UI_OVERWRITE,
    SituationFilePolicy.FAIL: POLICY_UI_FAIL,
}

# UI string → ExistingFilePolicy
UI_STRING_TO_EXISTING_POLICY = {
    POLICY_UI_CREATE_NEW: ExistingFilePolicy.CREATE_NEW,
    POLICY_UI_OVERWRITE: ExistingFilePolicy.OVERWRITE,
    POLICY_UI_FAIL: ExistingFilePolicy.FAIL,
}

# ExistingFilePolicy → UI string
EXISTING_POLICY_TO_UI_STRING = {
    ExistingFilePolicy.CREATE_NEW: POLICY_UI_CREATE_NEW,
    ExistingFilePolicy.OVERWRITE: POLICY_UI_OVERWRITE,
    ExistingFilePolicy.FAIL: POLICY_UI_FAIL,
}

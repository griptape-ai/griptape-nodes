"""Tests for policy_constants module."""

from griptape_nodes.common.project_templates.situation import SituationFilePolicy
from griptape_nodes.project.policy_constants import (
    EXISTING_POLICY_TO_UI_STRING,
    EXISTING_TO_OS_POLICY,
    POLICY_UI_CREATE_NEW,
    POLICY_UI_FAIL,
    POLICY_UI_OVERWRITE,
    SITUATION_POLICY_TO_UI_STRING,
    SITUATION_TO_EXISTING_POLICY,
    UI_STRING_TO_EXISTING_POLICY,
)
from griptape_nodes.project.types import ExistingFilePolicy
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy as OSExistingFilePolicy,
)


class TestPolicyConstants:
    """Test policy mapping constants."""

    def test_ui_string_constants(self) -> None:
        """Verify UI string constants are defined correctly."""
        assert POLICY_UI_CREATE_NEW == "create new file"
        assert POLICY_UI_OVERWRITE == "overwrite existing file"
        assert POLICY_UI_FAIL == "fail if file exists"

    def test_situation_to_existing_policy_completeness(self) -> None:
        """Verify SITUATION_TO_EXISTING_POLICY covers all convertible SituationFilePolicy values."""
        # PROMPT is intentionally excluded as it requires UI interaction
        expected_keys = {
            SituationFilePolicy.CREATE_NEW,
            SituationFilePolicy.OVERWRITE,
            SituationFilePolicy.FAIL,
        }
        assert set(SITUATION_TO_EXISTING_POLICY.keys()) == expected_keys

    def test_situation_to_existing_policy_values(self) -> None:
        """Verify SITUATION_TO_EXISTING_POLICY maps to correct ExistingFilePolicy values."""
        assert SITUATION_TO_EXISTING_POLICY[SituationFilePolicy.CREATE_NEW] == ExistingFilePolicy.CREATE_NEW
        assert SITUATION_TO_EXISTING_POLICY[SituationFilePolicy.OVERWRITE] == ExistingFilePolicy.OVERWRITE
        assert SITUATION_TO_EXISTING_POLICY[SituationFilePolicy.FAIL] == ExistingFilePolicy.FAIL

    def test_existing_to_os_policy_completeness(self) -> None:
        """Verify EXISTING_TO_OS_POLICY covers all ExistingFilePolicy values."""
        expected_keys = {
            ExistingFilePolicy.CREATE_NEW,
            ExistingFilePolicy.OVERWRITE,
            ExistingFilePolicy.FAIL,
        }
        assert set(EXISTING_TO_OS_POLICY.keys()) == expected_keys

    def test_existing_to_os_policy_values(self) -> None:
        """Verify EXISTING_TO_OS_POLICY maps to correct OSExistingFilePolicy values."""
        assert EXISTING_TO_OS_POLICY[ExistingFilePolicy.CREATE_NEW] == OSExistingFilePolicy.CREATE_NEW
        assert EXISTING_TO_OS_POLICY[ExistingFilePolicy.OVERWRITE] == OSExistingFilePolicy.OVERWRITE
        assert EXISTING_TO_OS_POLICY[ExistingFilePolicy.FAIL] == OSExistingFilePolicy.FAIL

    def test_situation_policy_to_ui_string_completeness(self) -> None:
        """Verify SITUATION_POLICY_TO_UI_STRING covers all convertible SituationFilePolicy values."""
        # PROMPT is intentionally excluded
        expected_keys = {
            SituationFilePolicy.CREATE_NEW,
            SituationFilePolicy.OVERWRITE,
            SituationFilePolicy.FAIL,
        }
        assert set(SITUATION_POLICY_TO_UI_STRING.keys()) == expected_keys

    def test_situation_policy_to_ui_string_values(self) -> None:
        """Verify SITUATION_POLICY_TO_UI_STRING maps to correct UI strings."""
        assert SITUATION_POLICY_TO_UI_STRING[SituationFilePolicy.CREATE_NEW] == POLICY_UI_CREATE_NEW
        assert SITUATION_POLICY_TO_UI_STRING[SituationFilePolicy.OVERWRITE] == POLICY_UI_OVERWRITE
        assert SITUATION_POLICY_TO_UI_STRING[SituationFilePolicy.FAIL] == POLICY_UI_FAIL

    def test_ui_string_to_existing_policy_completeness(self) -> None:
        """Verify UI_STRING_TO_EXISTING_POLICY covers all UI strings."""
        expected_keys = {
            POLICY_UI_CREATE_NEW,
            POLICY_UI_OVERWRITE,
            POLICY_UI_FAIL,
        }
        assert set(UI_STRING_TO_EXISTING_POLICY.keys()) == expected_keys

    def test_ui_string_to_existing_policy_values(self) -> None:
        """Verify UI_STRING_TO_EXISTING_POLICY maps to correct ExistingFilePolicy values."""
        assert UI_STRING_TO_EXISTING_POLICY[POLICY_UI_CREATE_NEW] == ExistingFilePolicy.CREATE_NEW
        assert UI_STRING_TO_EXISTING_POLICY[POLICY_UI_OVERWRITE] == ExistingFilePolicy.OVERWRITE
        assert UI_STRING_TO_EXISTING_POLICY[POLICY_UI_FAIL] == ExistingFilePolicy.FAIL

    def test_existing_policy_to_ui_string_completeness(self) -> None:
        """Verify EXISTING_POLICY_TO_UI_STRING covers all ExistingFilePolicy values."""
        expected_keys = {
            ExistingFilePolicy.CREATE_NEW,
            ExistingFilePolicy.OVERWRITE,
            ExistingFilePolicy.FAIL,
        }
        assert set(EXISTING_POLICY_TO_UI_STRING.keys()) == expected_keys

    def test_existing_policy_to_ui_string_values(self) -> None:
        """Verify EXISTING_POLICY_TO_UI_STRING maps to correct UI strings."""
        assert EXISTING_POLICY_TO_UI_STRING[ExistingFilePolicy.CREATE_NEW] == POLICY_UI_CREATE_NEW
        assert EXISTING_POLICY_TO_UI_STRING[ExistingFilePolicy.OVERWRITE] == POLICY_UI_OVERWRITE
        assert EXISTING_POLICY_TO_UI_STRING[ExistingFilePolicy.FAIL] == POLICY_UI_FAIL

    def test_bidirectional_ui_string_conversion(self) -> None:
        """Verify UI string ↔ ExistingFilePolicy conversion is bidirectional."""
        for ui_string, policy in UI_STRING_TO_EXISTING_POLICY.items():
            assert EXISTING_POLICY_TO_UI_STRING[policy] == ui_string

    def test_chain_conversion_situation_to_os(self) -> None:
        """Verify chained conversion: SituationFilePolicy → ExistingFilePolicy → OSExistingFilePolicy."""
        situation_to_os = {
            SituationFilePolicy.CREATE_NEW: OSExistingFilePolicy.CREATE_NEW,
            SituationFilePolicy.OVERWRITE: OSExistingFilePolicy.OVERWRITE,
            SituationFilePolicy.FAIL: OSExistingFilePolicy.FAIL,
        }

        for situation_policy, expected_os_policy in situation_to_os.items():
            existing_policy = SITUATION_TO_EXISTING_POLICY[situation_policy]
            os_policy = EXISTING_TO_OS_POLICY[existing_policy]
            assert os_policy == expected_os_policy

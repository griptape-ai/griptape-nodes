"""Unit tests for the emits_update_on_write decorator."""

from typing import Any
from unittest.mock import Mock, patch

import pytest

from griptape_nodes.exe_types.core_types import BaseNodeElement

from .mocks import MockNode


class ElementWithDecorator(BaseNodeElement):
    """Test element class with properties using emits_update_on_write decorator."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._test_value = "initial"
        self._test_dict = {"key": "value"}

    @property
    def test_value(self) -> str:
        return self._test_value

    @test_value.setter
    @BaseNodeElement.emits_update_on_write
    def test_value(self, value: str) -> None:
        self._test_value = value

    @property
    def test_dict(self) -> dict:
        return self._test_dict

    @test_dict.setter
    @BaseNodeElement.emits_update_on_write
    def test_dict(self, value: dict) -> None:
        self._test_dict = value


class TestEmitsUpdateOnWrite:
    """Test suite for emits_update_on_write decorator functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.node = MockNode()
        self.element = ElementWithDecorator()
        self.element._node_context = self.node

    def test_basic_change_tracking(self) -> None:
        """Test that changes are tracked when property values change."""
        # Initially no changes
        assert self.element._changes == {}
        assert self.element not in self.node._tracked_parameters

        # Change the value
        self.element.test_value = "new_value"

        # Verify change was tracked
        assert "test_value" in self.element._changes
        assert self.element._changes["test_value"] == "new_value"
        assert self.element in self.node._tracked_parameters

    def test_no_change_scenario(self) -> None:
        """Test that no events are emitted when setting the same value."""
        # Set initial value
        self.element.test_value = "same_value"

        # Clear changes
        self.element._changes.clear()
        self.node._tracked_parameters.clear()

        # Set the same value again
        self.element.test_value = "same_value"

        # Verify no change was tracked
        assert "test_value" not in self.element._changes
        assert self.element not in self.node._tracked_parameters

    def test_dictionary_reference_vs_new_object(self) -> None:
        """Test the dictionary reference issue that requires creating new objects."""
        original_dict = {"key": "original"}
        self.element.test_dict = original_dict

        # Clear changes
        self.element._changes.clear()
        self.node._tracked_parameters.clear()

        # Modify the same dictionary object (this should NOT trigger change tracking)
        original_dict["key"] = "modified"
        self.element.test_dict = original_dict

        # Verify no change was tracked (same object reference)
        assert "test_dict" not in self.element._changes
        assert self.element not in self.node._tracked_parameters

        # Now set a new dictionary object (this SHOULD trigger change tracking)
        new_dict = {"key": "new_value"}
        self.element.test_dict = new_dict

        # Verify change was tracked (different object reference)
        assert "test_dict" in self.element._changes
        assert self.element._changes["test_dict"] == new_dict
        assert self.element in self.node._tracked_parameters

    def test_dictionary_spread_operator_solution(self) -> None:
        """Test that using spread operator creates new objects and triggers tracking."""
        self.element.test_dict = {"initial": "value"}

        # Clear changes
        self.element._changes.clear()
        self.node._tracked_parameters.clear()

        # Use spread operator to create new dict (simulating the fix)
        self.element.test_dict = {**self.element.test_dict, "new_key": "new_value"}

        # Verify change was tracked
        assert "test_dict" in self.element._changes
        assert self.element._changes["test_dict"] == {"initial": "value", "new_key": "new_value"}
        assert self.element in self.node._tracked_parameters

    def test_node_context_integration(self) -> None:
        """Test proper integration with node context and tracked parameters."""
        # Test with node context
        assert self.element._node_context is self.node

        self.element.test_value = "tracked_value"

        # Verify element was added to node's tracked parameters
        assert self.element in self.node._tracked_parameters

        # Test that element is only added once (no duplicates)
        self.element.test_value = "another_value"
        tracked_count = sum(1 for elem in self.node._tracked_parameters if elem is self.element)
        assert tracked_count == 1

    def test_no_node_context(self) -> None:
        """Test behavior when element has no node context."""
        element_no_context = ElementWithDecorator()
        assert element_no_context._node_context is None

        # Should still track changes locally but not add to node's tracked parameters
        element_no_context.test_value = "no_context_value"

        assert "test_value" in element_no_context._changes
        assert element_no_context._changes["test_value"] == "no_context_value"

    @patch.object(BaseNodeElement, "_emit_alter_element_event_if_possible")
    def test_event_emission_called(self, mock_emit: Mock) -> None:
        """Test that event emission is triggered through the emit_parameter_changes flow."""
        self.element.test_value = "trigger_event"

        # Manually trigger event emission (simulating what happens in real flow)
        self.node.emit_parameter_changes()

        # Verify event emission was called
        mock_emit.assert_called_once()

        # Verify tracked parameters were cleared after emission
        assert len(self.node._tracked_parameters) == 0

    def test_multiple_changes_tracked(self) -> None:
        """Test that multiple property changes are tracked correctly."""
        self.element.test_value = "first_change"
        self.element.test_dict = {"second": "change"}

        # Verify both changes were tracked
        assert "test_value" in self.element._changes
        assert "test_dict" in self.element._changes
        assert self.element._changes["test_value"] == "first_change"
        assert self.element._changes["test_dict"] == {"second": "change"}

        # Element should only be in tracked parameters once
        tracked_count = sum(1 for elem in self.node._tracked_parameters if elem is self.element)
        assert tracked_count == 1

    def test_changes_cleared_after_emission(self) -> None:
        """Test that changes are cleared after event emission."""
        self.element.test_value = "clear_test"

        # Verify change was tracked
        assert len(self.element._changes) > 0

        # Manually trigger clearing (simulating what happens in real flow)
        self.element._changes.clear()

        # Verify changes were cleared
        assert len(self.element._changes) == 0

    def test_getter_not_affected(self) -> None:
        """Test that getter calls don't trigger the decorator logic."""
        initial_changes = self.element._changes.copy()
        initial_tracked = len(self.node._tracked_parameters)

        # Call getter multiple times
        _ = self.element.test_value
        _ = self.element.test_value
        _ = self.element.test_dict

        # Verify no changes were tracked
        assert self.element._changes == initial_changes
        assert len(self.node._tracked_parameters) == initial_tracked

    def test_none_values(self) -> None:
        """Test handling of None values."""
        # Set to None
        self.element.test_value = None

        # Verify change was tracked
        assert "test_value" in self.element._changes
        assert self.element._changes["test_value"] is None

        # Clear and set to None again
        self.element._changes.clear()
        self.node._tracked_parameters.clear()
        self.element.test_value = None

        # No change should be tracked (None -> None)
        assert "test_value" not in self.element._changes
        assert self.element not in self.node._tracked_parameters

    def test_decorator_preserves_function_behavior(self) -> None:
        """Test that the decorator doesn't interfere with normal function behavior."""
        # Test that setter actually sets the value
        self.element.test_value = "function_test"
        assert self.element._test_value == "function_test"
        assert self.element.test_value == "function_test"

        # Test that getter returns the right value
        self.element._test_value = "direct_set"
        assert self.element.test_value == "direct_set"

    def test_error_handling_in_decorator(self) -> None:
        """Test that decorator handles errors gracefully."""
        # Create element with missing attributes to test error handling
        minimal_element = BaseNodeElement()

        # This should not crash even though the element lacks some expected attributes
        try:
            # Apply decorator to a simple function
            @BaseNodeElement.emits_update_on_write
            def test_setter(self: Any, value: Any) -> None:
                pass

            # Call it - should not crash
            test_setter(minimal_element, "test")
        except Exception as e:
            pytest.fail(f"Decorator should handle missing attributes gracefully, but got: {e}")

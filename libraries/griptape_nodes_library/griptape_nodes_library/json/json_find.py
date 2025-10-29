import json
import re
from dataclasses import dataclass
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options


@dataclass
class SearchCriteria:
    """Search criteria for JSON finding."""

    search_field: str
    search_value: str
    search_mode: str
    return_mode: str
    case_sensitive: bool


class JsonFind(DataNode):
    """Find items in JSON arrays based on search criteria."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add parameter for input JSON
        self.add_parameter(
            Parameter(
                name="json",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["json", "str", "dict"],
                type="json",
                default_value=None,
                tooltip="Input JSON data to search through (should be an array or contain arrays)",
                ui_options={"placeholder_text": "Enter JSON data here..."},
            )
        )

        # Add parameter for search field path
        self.add_parameter(
            ParameterString(
                name="search_field",
                default_value="",
                tooltip="Dot notation path to the field to search (e.g., 'attributes.content', 'name')",
                placeholder_text="Field path to search (e.g., 'attributes.content')",
            )
        )

        # Add parameter for search value
        self.add_parameter(
            ParameterString(
                name="search_value",
                default_value="",
                tooltip="Value to search for (exact match)",
                placeholder_text="Value to search for",
            )
        )

        # Add parameter for search mode
        self.add_parameter(
            ParameterString(
                name="search_mode",
                default_value="exact",
                tooltip="Search mode: 'exact' for exact match, 'contains' for partial match, 'starts_with' for prefix match",
                placeholder_text="Search mode: exact, contains, starts_with",
                traits={Options(choices=["exact", "contains", "starts_with"])},
            )
        )

        # Add parameter for return mode
        self.add_parameter(
            ParameterString(
                name="return_mode",
                default_value="first",
                tooltip="Return mode: 'first' for first match, 'all' for all matches",
                placeholder_text="Return mode: first, all",
                traits={Options(choices=["first", "all"])},
            )
        )

        # Add parameter for case sensitivity
        self.add_parameter(
            ParameterBool(
                name="case_sensitive",
                default_value=True,
                tooltip="Whether the search should be case sensitive",
            )
        )

        # Add output parameters
        self.add_parameter(
            Parameter(
                name="found_item",
                type="json",
                tooltip="The found item(s) - single item if return_mode is 'first', array if 'all'",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Found item(s) will appear here..."},
            )
        )

        self.add_parameter(
            ParameterInt(
                name="found_count",
                tooltip="Number of items found",
                default_value=0,
                allow_input=False,
                allow_property=False,
            )
        )

        self.add_parameter(
            ParameterInt(
                name="found_index",
                tooltip="Index of the first found item (or -1 if not found)",
                default_value=-1,
                allow_input=False,
                allow_property=False,
            )
        )

    def _extract_field_value(self, item: Any, field_path: str) -> Any:
        """Extract a value from an item using dot notation path."""
        if not field_path:
            return item

        # Split by dots, but preserve array indices
        path_parts = re.split(r"\.(?![^\[]*\])", field_path)
        current = item

        for part in path_parts:
            if not isinstance(current, (dict, list)):
                return None

            current = self._traverse_path_part(current, part)
            if current is None:
                return None

        return current

    def _traverse_path_part(self, current: Any, part: str) -> Any:
        """Traverse a single part of the path (handles array indexing and dict keys)."""
        # Check if this part has array indexing
        array_match = re.match(r"^(.+)\[(\d+)\]$", part)
        if array_match:
            return self._handle_array_indexing(current, array_match)

        # Handle regular dictionary key
        if isinstance(current, dict):
            if part not in current:
                return None
            return current[part]

        return None

    def _handle_array_indexing(self, current: Any, array_match: re.Match[str]) -> Any:
        """Handle array indexing in path traversal."""
        key = array_match.group(1)
        index = int(array_match.group(2))

        if isinstance(current, dict):
            if key not in current:
                return None
            current = current[key]

        if isinstance(current, list):
            if index < 0 or index >= len(current):
                return None
            return current[index]

        return None

    def _matches_search_criteria(
        self, field_value: Any, search_value: str, search_mode: str, *, case_sensitive: bool
    ) -> bool:
        """Check if a field value matches the search criteria."""
        if field_value is None:
            return False

        # Convert to string for comparison
        field_str = str(field_value)
        search_str = str(search_value)

        # Handle case sensitivity
        if not case_sensitive:
            field_str = field_str.lower()
            search_str = search_str.lower()

        # Apply search mode
        if search_mode == "exact":
            return field_str == search_str
        if search_mode == "contains":
            return search_str in field_str
        if search_mode == "starts_with":
            return field_str.startswith(search_str)
        # Default to exact match
        return field_str == search_str

    def _find_items(self, data: Any, criteria: SearchCriteria) -> dict[str, Any]:
        """Find items in the data based on search criteria."""
        if not criteria.search_field or not criteria.search_value:
            return {"found_item": {}, "found_count": 0, "found_index": -1}

        # Ensure data is a list
        data_list = self._ensure_data_is_list(data)
        if data_list is None:
            return {"found_item": {}, "found_count": 0, "found_index": -1}

        # Search through the list
        found_items, first_index = self._search_through_list(data_list, criteria)

        # Return results based on return mode
        return self._format_search_results(found_items, first_index, criteria.return_mode)

    def _ensure_data_is_list(self, data: Any) -> list[Any] | None:
        """Ensure the data is a list, extracting from common array fields if needed."""
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            # Look for common array fields
            for key in ["data", "items", "results", "list"]:
                if key in data and isinstance(data[key], list):
                    return data[key]

        return None

    def _search_through_list(self, data_list: list[Any], criteria: SearchCriteria) -> tuple[list[Any], int]:
        """Search through a list of items for matches."""
        found_items = []
        first_index = -1

        for i, item in enumerate(data_list):
            field_value = self._extract_field_value(item, criteria.search_field)
            if self._matches_search_criteria(
                field_value, criteria.search_value, criteria.search_mode, case_sensitive=criteria.case_sensitive
            ):
                found_items.append(item)
                if first_index == -1:
                    first_index = i

        return found_items, first_index

    def _format_search_results(self, found_items: list[Any], first_index: int, return_mode: str) -> dict[str, Any]:
        """Format the search results based on return mode."""
        if return_mode == "first":
            if found_items:
                return {
                    "found_item": found_items[0],
                    "found_count": len(found_items),
                    "found_index": first_index,
                }
            return {"found_item": {}, "found_count": 0, "found_index": -1}

        # Handle return_mode == "all"
        return {
            "found_item": found_items,
            "found_count": len(found_items),
            "found_index": first_index,
        }

    def _perform_search(self) -> None:
        """Perform the JSON search and set the output values."""
        json_data = self.get_parameter_value("json")
        search_field = self.get_parameter_value("search_field")
        search_value = self.get_parameter_value("search_value")
        search_mode = self.get_parameter_value("search_mode")
        return_mode = self.get_parameter_value("return_mode")
        case_sensitive = self.get_parameter_value("case_sensitive")

        # Parse JSON string if needed
        if isinstance(json_data, str):
            try:
                json_data = json.loads(json_data)
            except json.JSONDecodeError as e:
                msg = (
                    f"JsonFind: Invalid JSON string provided. Failed to parse JSON: {e}. Input was: {json_data[:200]!r}"
                )
                raise ValueError(msg) from e

        # Create search criteria
        criteria = SearchCriteria(
            search_field=search_field,
            search_value=search_value,
            search_mode=search_mode,
            return_mode=return_mode,
            case_sensitive=case_sensitive,
        )

        # Perform the search
        search_results = self._find_items(json_data, criteria)

        # Trigger the SetParameterValueRequest for each parameter
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="found_item", value=search_results["found_item"], node_name=self.name
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="found_count", value=search_results["found_count"], node_name=self.name
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="found_index", value=search_results["found_index"], node_name=self.name
            )
        )

        # publish updates to make sure the ui_updates. Without this, the SetParameterValueRequest worked for
        # downstream nodes, but the ui_updates were not triggered.
        self.publish_update_to_parameter("found_item", search_results["found_item"])
        self.publish_update_to_parameter("found_count", search_results["found_count"])
        self.publish_update_to_parameter("found_index", search_results["found_index"])

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ["json", "search_field", "search_value", "search_mode", "return_mode", "case_sensitive"]:
            self._perform_search()

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node by performing the search."""
        self._perform_search()

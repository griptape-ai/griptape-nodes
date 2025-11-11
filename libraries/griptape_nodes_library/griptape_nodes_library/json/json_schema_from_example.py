"""Generate a JSON schema from an example JSON structure.

This node takes an example JSON object and automatically generates a JSON schema
that describes its structure. This makes it easy to create schemas for structured
output without manually writing JSON schema syntax.
"""

import json
from typing import Any

from json_repair import repair_json
from pydantic import BaseModel, create_model

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options

# Example templates for common schema patterns
EXAMPLE_TEMPLATES = {
    "Custom": "",
    "Simple Object": '{"name": "John", "age": 30, "email": "john@example.com"}',
    "Object with Optional Fields": '{"name": "John", "age": 30, "middle_name": null, "email": "john@example.com"}',
    "Object with Array Field": '{"name": "Product", "tags": ["electronics", "gadgets"], "prices": [19.99, 29.99]}',
    "Object with Nested Object": '{"user": {"name": "John", "address": {"street": "123 Main St", "city": "New York"}}}',
    "Array of Objects": '[{"title": "happy go lucky", "rank": 20}, {"title": "freekin smegadilic", "rank": 35}]',
    "Array of Strings": '["tag1", "tag2", "tag3"]',
    "Array of Numbers": "[1, 2, 3, 4, 5]",
    "Array of Mixed Types": '[1, "two", 3.0, true]',
    "Restaurant Review": '{"restaurant_name": "Joe\'s Pizza", "rating": 5, "price_range": "$$", "cuisine_type": "Italian", "recommended_dishes": ["Margherita", "Pepperoni"]}',
    "Product Information": '{"product_name": "Widget", "price": 29.99, "in_stock": true, "categories": ["electronics", "gadgets"], "specifications": {"weight": 1.5, "dimensions": {"width": 10, "height": 5}}}',
    "User Profile": '{"username": "johndoe", "email": "john@example.com", "age": 30, "active": true, "roles": ["user", "admin"], "metadata": null}',
    "Image Generation Prompt": '{"subject": "a futuristic cityscape", "style": "cyberpunk", "environment": "neon-lit urban night", "lighting": "dramatic neon", "camera": {"angle": "eye-level", "focus": "sharp", "depth_of_field": "shallow"}, "composition": {"position": "centered", "shadow": "dramatic"}, "mood": "energetic", "use_case": "concept art"}',
    "Video Generation Prompt": '{"subject": "hero walking through rain", "style": "film noir", "environment": "dark city street", "lighting": "low-key streetlights", "shots": [{"shot_number": 1, "camera_angle": "low angle", "camera_movement": "slow tracking", "focus": "selective", "depth_of_field": "shallow", "composition": "leading lines", "duration": 3}, {"shot_number": 2, "camera_angle": "eye-level", "camera_movement": "static", "focus": "sharp", "depth_of_field": "deep", "composition": "rule of thirds", "duration": 2}, {"shot_number": 3, "camera_angle": "overhead", "camera_movement": "crane down", "focus": "selective", "depth_of_field": "shallow", "composition": "centered", "duration": 4}], "mood": "mysterious", "use_case": "short film", "color_grade": "desaturated blue", "framerate": 24}',
    "API Request": '{"method": "POST", "endpoint": "/api/users", "headers": {"Content-Type": "application/json", "Authorization": "Bearer token123"}, "body": {"name": "John", "email": "john@example.com"}}',
    "Task List": '{"tasks": [{"id": 1, "title": "Complete project", "status": "in_progress", "due_date": "2024-12-31", "assignee": "Alice"}, {"id": 2, "title": "Review code", "status": "pending", "due_date": "2024-12-25", "assignee": "Bob"}]}',
    "Form Submission": '{"form_id": "contact_form", "fields": {"name": "Jane Doe", "email": "jane@example.com", "message": "Hello world", "newsletter": true}, "timestamp": "2024-01-15T10:30:00Z", "ip_address": "192.168.1.1"}',
    "Event Log": '{"event_type": "user_action", "user_id": "user_123", "action": "click", "target": "button", "metadata": {"page": "/dashboard", "timestamp": 1705312200, "session_id": "sess_456"}}',
    "Configuration Object": '{"app_name": "MyApp", "version": "1.0.0", "settings": {"debug": false, "max_connections": 100, "timeout": 30}, "features": {"feature_a": true, "feature_b": false}, "database": {"host": "localhost", "port": 5432, "name": "mydb"}}',
}


def _infer_list_type(value: list[Any]) -> Any:
    """Infer the Python type for a list value.

    Args:
        value: The list value to infer the type from.

    Returns:
        The inferred Python type annotation for the list.
    """
    if not value:
        return list[Any]

    item_types = {type(item) for item in value}
    if len(item_types) == 1:
        item_type = next(iter(item_types))
        if item_type in (dict, list):
            return list[Any]
        return list[item_type]

    return list[Any]


def _infer_type(value: Any) -> Any:
    """Infer the Python type from a JSON value.

    Args:
        value: The JSON value to infer the type from.

    Returns:
        The inferred Python type annotation.
    """
    if value is None:
        return type(None)

    if isinstance(value, dict):
        return dict[str, Any]

    if isinstance(value, list):
        return _infer_list_type(value)

    return type(value)


def _get_list_field_type(value: list[Any], model_name: str, key: str) -> tuple[Any, Any]:
    """Determine the Pydantic field type for a list value.

    Args:
        value: The list value to determine the type for.
        model_name: The name for the generated model class (for nested models).
        key: The key name (for nested model naming).

    Returns:
        A tuple of (type_annotation, default_value) for the Pydantic field.
    """
    if not value:
        return (list[Any], ...)

    if isinstance(value[0], dict):
        nested_model = _create_pydantic_model_from_dict(value[0], f"{model_name}_{key.capitalize()}Item")
        return (list[nested_model], ...)

    item_types = {type(item) for item in value if item is not None}
    if not item_types:
        return (list[Any], ...)

    if len(item_types) == 1:
        item_type = next(iter(item_types))
        if item_type in (dict, list):
            return (list[Any], ...)
        return (list[item_type], ...)

    type_union = tuple(item_types)
    return (list[type_union], ...)


def _create_pydantic_model_from_dict(data: dict[str, Any], model_name: str = "ExampleModel") -> type[BaseModel]:
    """Create a Pydantic model from a dictionary structure.

    Args:
        data: The dictionary to create a model from.
        model_name: The name for the generated model class.

    Returns:
        A Pydantic model class that matches the structure of the input data.
    """
    field_definitions: dict[str, Any] = {}

    for key, value in data.items():
        if value is None:
            field_definitions[key] = (str | None, None)
        elif isinstance(value, dict):
            nested_model = _create_pydantic_model_from_dict(value, f"{model_name}_{key.capitalize()}")
            field_definitions[key] = (nested_model, ...)
        elif isinstance(value, list):
            field_definitions[key] = _get_list_field_type(value, model_name, key)
        else:
            inferred_type = _infer_type(value)
            field_definitions[key] = (inferred_type, ...)

    return create_model(model_name, **field_definitions)


class CreateAgentSchema(SuccessFailureNode):
    """Generate a JSON schema from an example JSON structure for Agent nodes.

    This node takes an example JSON object or array and automatically generates a JSON schema
    that describes its structure. The generated schema can be used with Agent nodes
    for structured output validation.

    Supports:
    - Objects with nested structures
    - Arrays of objects
    - Arrays of primitives (strings, numbers, booleans)
    - Optional/nullable fields (fields with null values)
    - Empty arrays (generates default schema)
    - Mixed-type arrays (arrays with different types)
    - Objects with array fields

    Examples:
        Object example:
        {
            "name": "John",
            "age": 30,
            "email": "john@example.com",
            "middle_name": null
        }

        Output schema:
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "email": {"type": "string"},
                "middle_name": {"type": ["string", "null"]}
            },
            "required": ["name", "age", "email"]
        }

        Array of objects example:
        [
            {"title": "happy go lucky", "rank": 20},
            {"title": "freekin smegadilic", "rank": 35}
        ]

        Output schema:
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "rank": {"type": "integer"}
                        },
                        "required": ["title", "rank"]
                    }
                }
            },
            "required": ["items"]
        }

        Array of primitives example:
        ["tag1", "tag2", "tag3"]

        Output schema:
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["items"]
        }

        Mixed-type array example:
        [1, "two", 3.0, true]

        Output schema:
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": ["integer", "string", "number", "boolean"]}
                }
            },
            "required": ["items"]
        }
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        """Initialize the CreateAgentSchema node.

        Args:
            name: The name of the node.
            metadata: Optional metadata dictionary.
        """
        super().__init__(name, metadata)

        self.add_parameter(
            ParameterString(
                name="example_template",
                default_value="Custom",
                tooltip="Select a pre-built example template to get started, or choose 'Custom' to write your own.",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=list(EXAMPLE_TEMPLATES.keys()))},
            )
        )

        self.add_parameter(
            Parameter(
                name="example",
                input_types=["json", "str", "dict"],
                type="json",
                default_value="{}",
                tooltip="Example JSON structure to generate a schema from. Provide a sample of the data structure you want.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": '{"name": "John", "age": 30, "email": "john@example.com"}',
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="schema",
                input_types=["json"],
                type="json",
                tooltip="Generated JSON schema that describes the structure of the example.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        # Add status parameters using the helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the schema generation result",
            result_details_placeholder="Details on the schema generation will be presented here.",
        )

    def _try_parse_json(self, json_string: str) -> dict[str, Any] | list[Any] | None:
        """Try to parse a JSON string using repair_json and json.loads.

        Args:
            json_string: The JSON string to parse.

        Returns:
            Parsed dictionary, list, or None if parsing fails.
        """
        try:
            parsed = repair_json(json_string)
            if isinstance(parsed, (dict, list)):
                return parsed
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
                if isinstance(parsed, (dict, list)):
                    return parsed
        except (ValueError, TypeError):
            try:
                parsed = json.loads(json_string)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except json.JSONDecodeError:
                pass

        return None

    def _parse_example_data(self, example_data: Any) -> dict[str, Any] | list[Any] | None:
        """Parse example data into a dictionary or list.

        Args:
            example_data: The example data to parse (dict, list, str, or other).

        Returns:
            Parsed dictionary, list, or None if parsing fails.
        """
        if example_data is None:
            return None

        if isinstance(example_data, (dict, list)):
            return example_data

        if isinstance(example_data, str):
            if not example_data.strip():
                return None
            return self._try_parse_json(example_data)

        return self._try_parse_json(str(example_data))

    def _resolve_schema_refs(self, schema: dict[str, Any], defs: dict[str, Any] | None = None) -> dict[str, Any]:
        """Resolve $ref references in a JSON schema by inlining definitions.

        Args:
            schema: The schema to resolve references in.
            defs: Optional definitions dictionary (extracted from $defs).

        Returns:
            Schema with references resolved.
        """
        if defs is None:
            defs = schema.get("$defs", {})

        if not isinstance(schema, dict):
            return schema

        resolved = {}
        for key, value in schema.items():
            if key == "$ref":
                ref_path = value
                if ref_path.startswith("#/$defs/") and defs:
                    def_name = ref_path.replace("#/$defs/", "")
                    if def_name in defs:
                        return self._resolve_schema_refs(defs[def_name], defs)
                return schema

            if isinstance(value, dict):
                resolved[key] = self._resolve_schema_refs(value, defs)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_schema_refs(item, defs) if isinstance(item, dict) else item for item in value
                ]
            else:
                resolved[key] = value

        return resolved

    def _generate_array_schema(self, parsed_data: list[Any]) -> dict[str, Any]:
        """Generate schema for an array.

        Args:
            parsed_data: The array data to generate schema from.

        Returns:
            Generated JSON schema for the array.

        Raises:
            ValueError: If schema generation fails.
        """
        if not parsed_data:
            return {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {},
                    }
                },
                "required": ["items"],
            }

        first_item = parsed_data[0]

        if isinstance(first_item, dict):
            item_model = _create_pydantic_model_from_dict(first_item, "ArrayItem")
            array_wrapper_model = create_model("ArrayWrapper", items=(list[item_model], ...))
        else:
            item_types = {type(item) for item in parsed_data if item is not None}
            if not item_types:
                array_wrapper_model = create_model("ArrayWrapper", items=(list[Any], ...))
            elif len(item_types) == 1:
                item_type = next(iter(item_types))
                if item_type in (dict, list):
                    array_wrapper_model = create_model("ArrayWrapper", items=(list[Any], ...))
                else:
                    array_wrapper_model = create_model("ArrayWrapper", items=(list[item_type], ...))
            else:
                type_union = tuple(item_types)
                array_wrapper_model = create_model("ArrayWrapper", items=(list[type_union], ...))

        full_schema = array_wrapper_model.model_json_schema()
        defs = full_schema.get("$defs", {})
        json_schema = self._resolve_schema_refs(full_schema, defs)
        json_schema.pop("$defs", None)

        return json_schema

    def _generate_object_schema(self, parsed_data: dict[str, Any]) -> dict[str, Any]:
        """Generate schema for an object.

        Args:
            parsed_data: The object data to generate schema from.

        Returns:
            Generated JSON schema for the object.

        Raises:
            ValueError: If schema generation fails.
        """
        if not parsed_data:
            return {}

        pydantic_model = _create_pydantic_model_from_dict(parsed_data)
        json_schema = pydantic_model.model_json_schema()
        defs = json_schema.get("$defs", {})
        if defs:
            json_schema = self._resolve_schema_refs(json_schema, defs)
            json_schema.pop("$defs", None)

        return json_schema

    def _generate_schema(self) -> dict[str, Any] | None:
        """Generate JSON schema from the example data.

        Returns:
            Generated JSON schema dictionary, or None if generation fails.

        Raises:
            ValueError: If schema generation fails.
        """
        example_data = self.get_parameter_value("example")

        parsed_data = self._parse_example_data(example_data)

        if parsed_data is None:
            return None

        if isinstance(parsed_data, list):
            return self._generate_array_schema(parsed_data)

        if not isinstance(parsed_data, dict):
            return None

        return self._generate_object_schema(parsed_data)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle value changes to update example when template is selected and process schema generation.

        Args:
            parameter: The parameter that was set.
            value: The new value.
        """
        if parameter.name == "example_template":
            template_value = EXAMPLE_TEMPLATES.get(value, "")
            if template_value:
                example_param = self.get_parameter_by_name("example")
                if example_param:
                    self.set_parameter_value("example", template_value)
            return super().after_value_set(parameter, value)

        if parameter.name == "example":
            try:
                json_schema = self._generate_schema()
                if json_schema is not None:
                    self.parameter_output_values["schema"] = json_schema
                    self.publish_update_to_parameter("schema", json_schema)
                else:
                    self.parameter_output_values["schema"] = {}
                    self.publish_update_to_parameter("schema", {})
            except Exception as e:
                logger.debug(f"{self.name}: Failed to generate schema in after_value_set: {e}")
            return super().after_value_set(parameter, value)

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the example and generate a JSON schema."""
        self._clear_execution_status()

        example_data = self.get_parameter_value("example")

        if not example_data:
            error_details = "No example data provided"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            self.parameter_output_values["schema"] = {}
            self.publish_update_to_parameter("schema", {})
            self._handle_failure_exception(ValueError(error_details))
            return

        try:
            json_schema = self._generate_schema()
        except ValueError as e:
            error_details = f"Failed to generate schema: {e}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            self.parameter_output_values["schema"] = {}
            self.publish_update_to_parameter("schema", {})
            self._handle_failure_exception(e)
            return
        except (TypeError, RuntimeError) as e:
            error_details = f"Unexpected error during schema generation: {e}"
            logger.exception(f"{self.name}: {error_details}")
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            self.parameter_output_values["schema"] = {}
            self.publish_update_to_parameter("schema", {})
            self._handle_failure_exception(RuntimeError(error_details))
            return

        if json_schema is None:
            error_details = "Failed to parse example data or generate schema"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            self.parameter_output_values["schema"] = {}
            self.publish_update_to_parameter("schema", {})
            self._handle_failure_exception(ValueError(error_details))
            return

        self.parameter_output_values["schema"] = json_schema
        self.publish_update_to_parameter("schema", json_schema)

        success_details = "JSON schema generated successfully"
        self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")

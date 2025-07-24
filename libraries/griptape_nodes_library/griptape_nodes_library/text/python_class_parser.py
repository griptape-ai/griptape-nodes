import ast
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode


class PythonClassParser(ControlNode):
    """Parses Python file content to extract classes inheriting from RequestPayload or ResultPayload."""

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Input parameter for Python file content
        self.add_parameter(
            Parameter(
                name="file_content",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Python file content to parse",
                ui_options={"multiline": True, "placeholder_text": "Python file content..."},
            )
        )

        # Input parameter for file path (for context)
        self.add_parameter(
            Parameter(
                name="file_path",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="File path for context and error reporting",
            )
        )

        # Output parameter for parsed class information
        self.add_parameter(
            Parameter(
                name="class_info",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="list",
                default_value=[],
                tooltip="List of class information dictionaries",
            )
        )

        # Output parameter for parsing errors
        self.add_parameter(
            Parameter(
                name="parsing_errors",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="str",
                default_value="",
                tooltip="Any errors encountered during parsing",
                ui_options={"multiline": True, "placeholder_text": "Parsing errors will appear here..."},
            )
        )

    def _extract_docstring(self, node: ast.ClassDef) -> str | None:
        """Extract docstring from a class node."""
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            return node.body[0].value.value
        return None

    def _get_class_definition(self, node: ast.ClassDef, lines: list[str]) -> str:
        """Get the class definition including decorators and signature."""
        start_line = node.lineno - 1

        # Find the actual start including decorators
        actual_start = start_line
        for decorator in node.decorator_list:
            actual_start = min(actual_start, decorator.lineno - 1)

        # Find class body start (after colon)
        class_body_start = start_line
        for i in range(start_line, len(lines)):
            if ":" in lines[i]:
                class_body_start = i
                break

        # Return from decorators to end of class signature
        return "\n".join(lines[actual_start : class_body_start + 1])

    def _inherits_from_payload(self, node: ast.ClassDef) -> str | None:
        """Check if class inherits from RequestPayload or ResultPayload."""
        for base in node.bases:
            if isinstance(base, ast.Name):
                if base.id in ("RequestPayload", "ResultPayload"):
                    return base.id
            elif isinstance(base, ast.Attribute):
                # Handle cases like module.RequestPayload
                if base.attr in ("RequestPayload", "ResultPayload"):
                    return base.attr
        return None

    def _get_docstring_location(self, node: ast.ClassDef) -> tuple[int, int] | None:
        """Get the line numbers where the docstring starts and ends."""
        if not node.body:
            return None

        first_stmt = node.body[0]
        if (
            isinstance(first_stmt, ast.Expr)
            and isinstance(first_stmt.value, ast.Constant)
            and isinstance(first_stmt.value.value, str)
        ):
            return (first_stmt.lineno, first_stmt.end_lineno or first_stmt.lineno)
        return None

    def process(self) -> None:
        """Process the node by parsing Python class definitions."""
        file_content = self.parameter_values.get("file_content", "")
        file_path = self.parameter_values.get("file_path", "unknown")

        if not file_content:
            self.parameter_output_values["class_info"] = []
            self.parameter_output_values["parsing_errors"] = "No file content provided"
            self.parameter_values["class_info"] = []
            self.parameter_values["parsing_errors"] = "No file content provided"
            return

        try:
            # Parse the Python code
            tree = ast.parse(file_content)
            lines = file_content.splitlines()

            class_info = []
            errors = []

            # Walk through all nodes in the AST
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if this class inherits from RequestPayload or ResultPayload
                    payload_type = self._inherits_from_payload(node)

                    if payload_type:
                        try:
                            # Extract class information
                            current_docstring = self._extract_docstring(node)
                            docstring_location = self._get_docstring_location(node)
                            class_definition = self._get_class_definition(node, lines)

                            class_data = {
                                "class_name": node.name,
                                "payload_type": payload_type,
                                "has_docstring": current_docstring is not None,
                                "current_docstring": current_docstring or "",
                                "docstring_start_line": docstring_location[0] if docstring_location else None,
                                "docstring_end_line": docstring_location[1] if docstring_location else None,
                                "class_start_line": node.lineno,
                                "class_definition": class_definition,
                                "file_path": file_path,
                            }

                            class_info.append(class_data)

                        except Exception as e:
                            errors.append(f"Error processing class {node.name}: {e!s}")

            # Set output values
            self.parameter_output_values["class_info"] = class_info
            self.parameter_output_values["parsing_errors"] = "\n".join(errors) if errors else ""

            # Also set in parameter_values for get_value compatibility
            self.parameter_values["class_info"] = class_info
            self.parameter_values["parsing_errors"] = "\n".join(errors) if errors else ""

        except SyntaxError as e:
            error_msg = f"Syntax error in {file_path}: {e!s}"
            self.parameter_output_values["class_info"] = []
            self.parameter_output_values["parsing_errors"] = error_msg
            self.parameter_values["class_info"] = []
            self.parameter_values["parsing_errors"] = error_msg

        except Exception as e:
            error_msg = f"Error parsing {file_path}: {e!s}"
            self.parameter_output_values["class_info"] = []
            self.parameter_output_values["parsing_errors"] = error_msg
            self.parameter_values["class_info"] = []
            self.parameter_values["parsing_errors"] = error_msg

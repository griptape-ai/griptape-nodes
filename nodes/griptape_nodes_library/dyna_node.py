import importlib
from typing import get_args, get_origin

import attrs

from griptape_nodes.exe_types.core_types import (
    Parameter,
)
from griptape_nodes.exe_types.node_types import BaseNode


class DynaNode(BaseNode):
    def __init__(self, name: str, metadata: dict) -> None:
        super().__init__(name, metadata)
        library_node_metadata = metadata["library_node_metadata"]
        module = importlib.import_module(library_node_metadata["module"])
        module_class = getattr(module, library_node_metadata["class"])
        method = library_node_metadata["method"]

        self.module_class = module_class
        self.method = method

        self._build_parameters_attrs(self.module_class)

    def process(self) -> None:
        getattr(self.module_class, self.method)(**self.parameter_values)

    def _build_parameters_attrs(self, cls: type) -> None:
        if not attrs.has(cls):
            return

        for field in attrs.fields(cls):
            if field.init is False:
                continue
            if not field.metadata.get("serializable", False):
                continue
            input_types = self._parse_annotation(field.type)
            if not input_types:
                continue

            output_type = input_types[-1]

            tooltip_str = self._prettify_field_name(field.name)

            parameter = Parameter(
                name=field.alias or field.name,
                input_types=input_types,
                output_type=output_type,
                default_value=None,
                tooltip=tooltip_str,
            )

            self.add_parameter(parameter)
        self.parameters.sort(key=lambda x: x.name)

    def _parse_annotation(self, annotation: str) -> list[str]:
        """Given a type annotation, return a list of string representations for each possible type."""
        origin = get_origin(annotation)
        if origin is None:
            return [annotation]

        args = get_args(annotation)
        result = []
        for arg in args:
            if hasattr(arg, "__name__"):
                result.append(arg.__name__)
            else:
                result.append(str(arg))
        return result

    def _prettify_field_name(self, field_name: str) -> str:
        """Convert snake_case or similar to a nicer display string."""
        return field_name.replace("_", " ").title()

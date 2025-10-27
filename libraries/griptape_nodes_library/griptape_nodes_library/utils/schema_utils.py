from typing import Any, Literal

from pydantic import BaseModel, Field, create_model, ConfigDict


def create_pydantic_model_from_schema(values_schema: dict[str, Any], *, strict_schema: bool = True) -> type[BaseModel]:
    schema = values_schema.get("properties", {})
    field_definitions = {}
    defs = values_schema.get("$defs")
    model_name = values_schema.get("title", "DynamicModel")
    for field_name, field_schema in schema.items():
        is_required = field_name in values_schema.get("required", [])
        description = field_schema.get("description")
        default = ... if is_required else field_schema.get("default", None)

        type_ = get_type(
            field_schema,
            defs=defs,
            strict_schema=strict_schema,
        )

        field_definitions[field_name] = (
            type_,
            Field(default, description=description),
        )

    return create_model(
        model_name,
        __config__=ConfigDict(extra="forbid") if strict_schema else {},
        **field_definitions,
    )


def get_type(
    field_schema: dict[str, Any],
    defs: dict[str, Any] | None = None,
    *,
    strict_schema: bool = True,
) -> type | Any:
    field_type = field_schema.get("type")
    enum = field_schema.get("enum")

    if enum is not None:
        return Literal[*enum]

    match field_type:
        case "string" | "str":
            return str
        case "integer" | "int":
            return int
        case "number":
            return float
        case "boolean" | "bool":
            return bool
        case "array" | "list":
            if (items := field_schema.get("items")) is not None:
                if defs is not None and isinstance(items, dict) and "$ref" in items:
                    ref = items["$ref"]
                    ref_name = ref.split("/")[-1]
                    if ref_name in defs:
                        return list[create_pydantic_model_from_schema(defs[ref_name], strict_schema=strict_schema)]
                return list[create_pydantic_model_from_schema(items, strict_schema=strict_schema)]
            return list
        case "object" | "dict":
            return dict
        case _:
            return Any

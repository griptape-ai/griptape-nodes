import json
from pathlib import Path
from typing import Any

from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

payload_type_to_schema: dict[str, dict[str, Any]] = {}

payload_dict = PayloadRegistry.get_registry()

for payload_class_name, payload_class in payload_dict.items():
    schema = payload_class.model_json_schema()
    payload_type_to_schema[payload_class_name] = schema

with Path("event_schemas.json").open("w+") as file:
    for schema in payload_type_to_schema.values():
        file.write(json.dumps(schema, indent=2))
        file.write(",\n\n")

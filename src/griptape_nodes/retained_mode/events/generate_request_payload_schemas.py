import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from griptape_nodes.retained_mode.events.base_events import RequestPayload
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

logger = logging.getLogger("griptape_nodes")

payload_type_to_schema: dict[str, dict[str, Any]] = {}

payload_dict = PayloadRegistry.get_registry()

for payload_class_name, payload_class in payload_dict.items():
    if issubclass(payload_class, RequestPayload):

        class BaseModelPayload(payload_class, BaseModel):
            """BaseModel wrapper to generate JSON schema for the payload."""

        logger.info("Generating schema for %s...", payload_class_name)
        schema = BaseModelPayload.model_json_schema()
        payload_type_to_schema[payload_class_name] = schema
    else:
        logger.info("Skipping %s as it is not a RequestPayload.", payload_class_name)

with Path("request_payload_schemas.json").open("w+") as file:
    file.write(json.dumps(list(payload_type_to_schema.values()), indent=2))

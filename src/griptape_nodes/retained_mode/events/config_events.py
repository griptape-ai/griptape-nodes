from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class GetConfigValueRequest(RequestPayload):
    """Get a specific configuration value.

    Use when: Reading application settings, checking node configurations, retrieving user preferences,
    accessing environment-specific values. Key format: "category.key" or "category.subcategory.key".

    Args:
        category_and_key: Configuration key in format "category.key" or "category.subcategory.key"

    Results: GetConfigValueResultSuccess (with value) | GetConfigValueResultFailure (key not found)
    """

    category_and_key: str


@dataclass
@PayloadRegistry.register
class GetConfigValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Configuration value retrieved successfully.

    Args:
        value: The configuration value (can be any type)
    """

    value: Any


@dataclass
@PayloadRegistry.register
class GetConfigValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Configuration value retrieval failed. Common causes: key not found, invalid category format."""


@dataclass
@PayloadRegistry.register
class SetConfigValueRequest(RequestPayload):
    """Set a specific configuration value.

    Use when: Updating application settings, configuring node behavior, storing user preferences,
    setting environment-specific values. Key format: "category.key" or "category.subcategory.key".

    Args:
        category_and_key: Configuration key in format "category.key" or "category.subcategory.key"
        value: Value to set for the configuration key

    Results: SetConfigValueResultSuccess | SetConfigValueResultFailure (invalid key, value error)
    """

    category_and_key: str
    value: Any


@dataclass
@PayloadRegistry.register
class SetConfigValueResultSuccess(ResultPayloadSuccess):
    """Configuration value set successfully."""


@dataclass
@PayloadRegistry.register
class SetConfigValueResultFailure(ResultPayloadFailure):
    """Configuration value setting failed. Common causes: invalid key format, value validation error."""


@dataclass
@PayloadRegistry.register
class GetConfigCategoryRequest(RequestPayload):
    """Get all configuration values within a category.

    Use when: Retrieving multiple related settings, displaying configuration sections in UIs,
    backing up/restoring configuration groups, bulk configuration operations.

    Args:
        category: Name of the configuration category (None for all categories)

    Results: GetConfigCategoryResultSuccess (with contents dict) | GetConfigCategoryResultFailure (category not found)
    """

    category: str | None = None


@dataclass
@PayloadRegistry.register
class GetConfigCategoryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Configuration category retrieved successfully.

    Args:
        contents: Dictionary of key-value pairs within the category
    """

    contents: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetConfigCategoryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Configuration category retrieval failed. Common causes: category not found, invalid category name."""


@dataclass
@PayloadRegistry.register
class SetConfigCategoryRequest(RequestPayload):
    """Set multiple configuration values within a category.

    Use when: Bulk updating configuration settings, restoring configuration sections,
    applying configuration templates, batch configuration operations.

    Args:
        contents: Dictionary of key-value pairs to set in the category
        category: Name of the configuration category (None for default)

    Results: SetConfigCategoryResultSuccess | SetConfigCategoryResultFailure (invalid category, value errors)
    """

    contents: dict[str, Any]
    category: str | None = None


@dataclass
@PayloadRegistry.register
class SetConfigCategoryResultSuccess(ResultPayloadSuccess):
    """Configuration category updated successfully."""


@dataclass
@PayloadRegistry.register
class SetConfigCategoryResultFailure(ResultPayloadFailure):
    """Configuration category update failed. Common causes: invalid category name, value validation errors."""


@dataclass
@PayloadRegistry.register
class GetConfigPathRequest(RequestPayload):
    """Get the path to the configuration file.

    Use when: Locating configuration files, debugging configuration issues,
    implementing configuration backup/restore, displaying configuration info to users.

    Results: GetConfigPathResultSuccess (with path) | GetConfigPathResultFailure (path not available)
    """


@dataclass
@PayloadRegistry.register
class GetConfigPathResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Configuration path retrieved successfully.

    Args:
        config_path: Path to the configuration file (None if using default/memory config)
    """

    config_path: str | None = None


@dataclass
@PayloadRegistry.register
class GetConfigPathResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Configuration path retrieval failed. Common causes: configuration not initialized, access denied."""


@dataclass
@PayloadRegistry.register
class ResetConfigRequest(RequestPayload):
    """Reset configuration to default values.

    Use when: Recovering from configuration errors, restoring default settings,
    clearing user customizations, troubleshooting configuration issues.

    Results: ResetConfigResultSuccess | ResetConfigResultFailure (reset error)
    """


@dataclass
@PayloadRegistry.register
class ResetConfigResultSuccess(ResultPayloadSuccess):
    """Configuration reset successfully to default values."""


@dataclass
@PayloadRegistry.register
class ResetConfigResultFailure(ResultPayloadFailure):
    """Configuration reset failed. Common causes: file system errors, permission issues, initialization errors."""


@dataclass
@PayloadRegistry.register
class GetConfigSchemaRequest(RequestPayload):
    """Get the JSON schema for the configuration model.

    Use when: Frontend needs to understand field types, enums, and validation rules
    for rendering appropriate UI components (dropdowns, text inputs, etc.).

    Results: GetConfigSchemaResultSuccess (with schema) | GetConfigSchemaResultFailure (schema generation error)
    """


@dataclass
@PayloadRegistry.register
class GetConfigSchemaResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Configuration schema retrieved successfully.

    Args:
        schema: The JSON schema for the configuration model
    """

    schema: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetConfigSchemaResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Configuration schema retrieval failed. Common causes: schema generation error, model validation issues."""

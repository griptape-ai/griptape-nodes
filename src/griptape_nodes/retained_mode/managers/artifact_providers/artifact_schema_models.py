"""Pydantic models for artifact configuration schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, RootModel


class ParameterSchema(BaseModel):
    """Schema for a single generator parameter.

    Example: max_width parameter with type "integer", default 1024
    """

    type: str = Field(description="JSON schema type: 'integer', 'number', 'string', 'boolean'")
    default: Any = Field(description="Default value for this parameter")
    description: str = Field(description="Human-readable description of parameter")


class PreviewFormatSchema(BaseModel):
    """Schema for preview format dropdown configuration."""

    type: str = Field(default="string", description="Always 'string' for format selection")
    enum: list[str] = Field(description="List of available format options (sorted)")
    default: str = Field(description="Default format (e.g., 'webp')")
    description: str = Field(description="Human-readable description of format field")


class PreviewGeneratorSchema(BaseModel):
    """Schema for preview generator dropdown configuration."""

    type: str = Field(default="string", description="Always 'string' for generator selection")
    enum: list[str] = Field(description="List of available generator names (sorted)")
    default: str = Field(description="Default generator name")
    description: str = Field(description="Human-readable description of generator field")


class GeneratorParametersSchema(RootModel[dict[str, ParameterSchema]]):
    """Schema for all parameters of a single generator.

    Maps parameter names to their ParameterSchema definitions.
    Example: {"max_width": ParameterSchema(...), "max_height": ParameterSchema(...)}
    """

    root: dict[str, ParameterSchema]


class GeneratorConfigurationsSchema(RootModel[dict[str, GeneratorParametersSchema]]):
    """Schema for all generator configurations under a provider.

    Maps generator keys to their parameter schemas.
    Example: {"standard_thumbnail_generation": GeneratorParametersSchema(...)}
    """

    root: dict[str, GeneratorParametersSchema]


class PreviewGenerationSchema(BaseModel):
    """Schema for the preview_generation section of a provider."""

    preview_format: PreviewFormatSchema
    preview_generator: PreviewGeneratorSchema
    preview_generator_configurations: GeneratorConfigurationsSchema


class ProviderSchema(BaseModel):
    """Schema for a single artifact provider."""

    preview_generation: PreviewGenerationSchema


class ArtifactSchemas(RootModel[dict[str, ProviderSchema]]):
    """Root schema model for all artifact providers.

    Maps provider keys (e.g., "image") to their ProviderSchema definitions.
    Uses RootModel to return dict directly without wrapper key.
    """

    root: dict[str, ProviderSchema]

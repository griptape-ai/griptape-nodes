"""Tests for LibraryProperty / NodeProperty discriminated unions."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from griptape_nodes.node_library.library_properties import (
    EngineControlNodeProperty,
    ExecuteArbitraryCodeNodeProperty,
    KeySupport,
    KeySupportNodeProperty,
    ModelFamilyNodeProperty,
    ProductionStatus,
    ProductionStatusLibraryProperty,
    ProductionStatusNodeProperty,
    ProxyModelNodeProperty,
    RequiredPermissionsLibraryProperty,
    RequiredPermissionsNodeProperty,
    SpecificModelNodeProperty,
)
from griptape_nodes.node_library.library_registry import (
    CategoryDefinition,
    LibraryMetadata,
    LibrarySchema,
    NodeDefinition,
    NodeMetadata,
)


def _make_library_metadata(**kwargs: Any) -> LibraryMetadata:
    return LibraryMetadata(
        author="test",
        description="test library",
        library_version="1.0.0",
        engine_version="1.0.0",
        tags=[],
        **kwargs,
    )


def _make_node_metadata(**kwargs: Any) -> NodeMetadata:
    return NodeMetadata(
        category="Test",
        description="test node",
        display_name="TestNode",
        **kwargs,
    )


def _make_library_schema(
    *,
    library_properties: list[Any] | None = None,
    node_properties: list[Any] | None = None,
) -> LibrarySchema:
    """Build a minimal valid LibrarySchema with optional property lists on library and a single node."""
    lib_kwargs: dict[str, Any] = {}
    if library_properties is not None:
        lib_kwargs["properties"] = library_properties
    node_kwargs: dict[str, Any] = {}
    if node_properties is not None:
        node_kwargs["properties"] = node_properties

    return LibrarySchema(
        name="Test Library",
        library_schema_version=LibrarySchema.LATEST_SCHEMA_VERSION,
        metadata=_make_library_metadata(**lib_kwargs),
        categories=[{"Test": CategoryDefinition(title="Test", description="test", color="#000", icon="Folder")}],
        nodes=[
            NodeDefinition(
                class_name="TestNode",
                file_path="test_node.py",
                metadata=_make_node_metadata(**node_kwargs),
            )
        ],
    )


class TestMetadataPropertiesDefaults:
    def test_library_metadata_properties_defaults_to_empty(self) -> None:
        metadata = _make_library_metadata()

        assert metadata.properties == []

    def test_node_metadata_properties_defaults_to_empty(self) -> None:
        metadata = _make_node_metadata()

        assert metadata.properties == []


class TestPropertyDiscriminator:
    def test_library_property_discriminator_selects_correct_subclass(self) -> None:
        property_payloads = [
            {"type": "production_status", "status": "BETA"},
            {"type": "required_permissions", "permissions": {"a": "b"}},
        ]
        metadata = LibraryMetadata.model_validate(
            {
                "author": "test",
                "description": "test",
                "library_version": "1.0.0",
                "engine_version": "1.0.0",
                "tags": [],
                "properties": property_payloads,
            }
        )

        assert len(metadata.properties) == len(property_payloads)
        assert isinstance(metadata.properties[0], ProductionStatusLibraryProperty)
        assert metadata.properties[0].status is ProductionStatus.BETA
        assert isinstance(metadata.properties[1], RequiredPermissionsLibraryProperty)
        assert metadata.properties[1].permissions == {"a": "b"}

    def test_node_property_discriminator_selects_correct_subclass(self) -> None:
        property_payloads = [
            {"type": "execute_arbitrary_code"},
            {"type": "key_support", "support": "REQUIRES_CUSTOMER_KEY"},
            {"type": "engine_control"},
            {"type": "proxy_model"},
        ]
        metadata = NodeMetadata.model_validate(
            {
                "category": "Test",
                "description": "test",
                "display_name": "TestNode",
                "properties": property_payloads,
            }
        )

        assert len(metadata.properties) == len(property_payloads)
        assert isinstance(metadata.properties[0], ExecuteArbitraryCodeNodeProperty)
        assert isinstance(metadata.properties[1], KeySupportNodeProperty)
        assert metadata.properties[1].support is KeySupport.REQUIRES_CUSTOMER_KEY
        assert isinstance(metadata.properties[2], EngineControlNodeProperty)
        assert isinstance(metadata.properties[3], ProxyModelNodeProperty)

    def test_unknown_property_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeMetadata.model_validate(
                {
                    "category": "Test",
                    "description": "test",
                    "display_name": "TestNode",
                    "properties": [{"type": "not_a_real_property"}],
                }
            )


class TestProductionStatusSemantics:
    def test_node_properties_absence_means_inherit(self) -> None:
        """Absence of ProductionStatusNodeProperty on a node means 'inherit from library'."""
        metadata = _make_node_metadata()

        assert metadata.properties == []

    def test_node_production_status_round_trip(self) -> None:
        metadata = _make_node_metadata(properties=[ProductionStatusNodeProperty(status=ProductionStatus.BETA)])

        reloaded = NodeMetadata.model_validate(metadata.model_dump())

        assert len(reloaded.properties) == 1
        assert isinstance(reloaded.properties[0], ProductionStatusNodeProperty)
        assert reloaded.properties[0].status is ProductionStatus.BETA

    def test_production_status_node_property_requires_status(self) -> None:
        with pytest.raises(ValidationError):
            ProductionStatusNodeProperty()  # type: ignore[call-arg]


class TestModelPropertiesRequireTermsUrl:
    def test_model_family_requires_terms_url(self) -> None:
        with pytest.raises(ValidationError):
            NodeMetadata.model_validate(
                {
                    "category": "Test",
                    "description": "test",
                    "display_name": "TestNode",
                    "properties": [{"type": "model_family", "family": "OpenAI"}],
                }
            )

    def test_specific_model_requires_terms_url(self) -> None:
        with pytest.raises(ValidationError):
            NodeMetadata.model_validate(
                {
                    "category": "Test",
                    "description": "test",
                    "display_name": "TestNode",
                    "properties": [{"type": "specific_model", "model": "gpt-4o"}],
                }
            )

    def test_model_family_with_terms_url_is_valid(self) -> None:
        metadata = NodeMetadata.model_validate(
            {
                "category": "Test",
                "description": "test",
                "display_name": "TestNode",
                "properties": [
                    {
                        "type": "model_family",
                        "family": "OpenAI GPT",
                        "terms_url": "https://example.com/terms",
                    }
                ],
            }
        )

        assert isinstance(metadata.properties[0], ModelFamilyNodeProperty)
        assert metadata.properties[0].family == "OpenAI GPT"
        assert metadata.properties[0].terms_url == "https://example.com/terms"


class TestRoundTripSerialization:
    def test_every_property_type_round_trips(self) -> None:
        """Build a LibrarySchema with one of every property type; dump to JSON and reload.

        Guards against PayloadRegistry / Pydantic silently dropping discriminator info
        or any field during serialization.
        """
        schema = _make_library_schema(
            library_properties=[
                ProductionStatusLibraryProperty(status=ProductionStatus.PRODUCTION),
                RequiredPermissionsLibraryProperty(permissions={"action": "library::use"}),
            ],
            node_properties=[
                ProductionStatusNodeProperty(status=ProductionStatus.BETA),
                RequiredPermissionsNodeProperty(permissions={"action": "node::use"}),
                ModelFamilyNodeProperty(family="Anthropic Claude", terms_url="https://example.com/a"),
                SpecificModelNodeProperty(model="claude-opus-4-7", terms_url="https://example.com/b"),
                ProxyModelNodeProperty(),
                ExecuteArbitraryCodeNodeProperty(),
                EngineControlNodeProperty(),
                KeySupportNodeProperty(support=KeySupport.REQUIRES_GRIPTAPE_KEY),
            ],
        )

        reloaded = LibrarySchema.model_validate_json(schema.model_dump_json())

        assert reloaded == schema


class TestSchemaVersion:
    def test_schema_version_bumped(self) -> None:
        assert LibrarySchema.LATEST_SCHEMA_VERSION == "0.8.0"


class TestBackwardCompatibility:
    def test_older_schema_loads_with_empty_properties(self) -> None:
        """A library JSON authored before properties existed must still validate."""
        older_json = {
            "name": "Older Library",
            "library_schema_version": "0.6.0",
            "metadata": {
                "author": "someone",
                "description": "old",
                "library_version": "1.0.0",
                "engine_version": "1.0.0",
                "tags": [],
            },
            "categories": [{"Test": {"title": "Test", "description": "test", "color": "#000", "icon": "Folder"}}],
            "nodes": [
                {
                    "class_name": "OldNode",
                    "file_path": "old_node.py",
                    "metadata": {
                        "category": "Test",
                        "description": "old",
                        "display_name": "OldNode",
                    },
                }
            ],
        }

        schema = LibrarySchema.model_validate(older_json)

        assert schema.metadata.properties == []
        assert schema.nodes[0].metadata.properties == []

    def test_older_schema_json_string_loads(self) -> None:
        """Same check via JSON string path (model_validate_json)."""
        older_json_str = json.dumps(
            {
                "name": "Older Library",
                "library_schema_version": "0.6.0",
                "metadata": {
                    "author": "someone",
                    "description": "old",
                    "library_version": "1.0.0",
                    "engine_version": "1.0.0",
                    "tags": [],
                },
                "categories": [{"Test": {"title": "Test", "description": "test", "color": "#000", "icon": "Folder"}}],
                "nodes": [],
            }
        )

        schema = LibrarySchema.model_validate_json(older_json_str)

        assert schema.metadata.properties == []

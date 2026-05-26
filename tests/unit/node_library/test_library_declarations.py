"""Tests for LibraryDeclaration / NodeDeclaration discriminated unions."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from griptape_nodes.node_library.library_declarations import (
    KeySupport,
    KeySupportNodeProperty,
    ProductionStatus,
    ProductionStatusLibraryProperty,
    ProductionStatusNodeProperty,
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


# ---------- Defaults ----------


class TestMetadataDeclarationsDefaults:
    def test_library_metadata_declarations_defaults_to_empty(self) -> None:
        assert _make_library_metadata().declarations == []

    def test_node_metadata_declarations_defaults_to_empty(self) -> None:
        assert _make_node_metadata().declarations == []


# ---------- Discriminator behavior ----------


class TestDeclarationDiscriminator:
    def test_node_production_status_round_trips(self) -> None:
        metadata = _make_node_metadata(declarations=[ProductionStatusNodeProperty(status=ProductionStatus.BETA)])

        rebuilt = NodeMetadata.model_validate(metadata.model_dump())

        assert isinstance(rebuilt.declarations[0], ProductionStatusNodeProperty)
        assert rebuilt.declarations[0].status is ProductionStatus.BETA

    def test_node_key_support_round_trips(self) -> None:
        metadata = _make_node_metadata(declarations=[KeySupportNodeProperty(support=KeySupport.REQUIRES_CUSTOMER_KEY)])

        rebuilt = NodeMetadata.model_validate(metadata.model_dump())

        decl = rebuilt.declarations[0]
        assert isinstance(decl, KeySupportNodeProperty)
        assert decl.support is KeySupport.REQUIRES_CUSTOMER_KEY

    def test_library_production_status_round_trips(self) -> None:
        metadata = _make_library_metadata(
            declarations=[ProductionStatusLibraryProperty(status=ProductionStatus.PRODUCTION)],
        )

        rebuilt = LibraryMetadata.model_validate(metadata.model_dump())

        assert isinstance(rebuilt.declarations[0], ProductionStatusLibraryProperty)
        assert rebuilt.declarations[0].status is ProductionStatus.PRODUCTION

    def test_unknown_node_type_discriminator_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeMetadata.model_validate(
                {
                    "category": "Test",
                    "description": "t",
                    "display_name": "TestNode",
                    "declarations": [{"type": "not_a_real_type"}],
                }
            )

    def test_unknown_library_type_discriminator_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LibraryMetadata.model_validate(
                {
                    "author": "t",
                    "description": "t",
                    "library_version": "1.0.0",
                    "engine_version": "1.0.0",
                    "tags": [],
                    "declarations": [{"type": "not_a_real_type"}],
                }
            )


# ---------- ProductionStatus inheritance semantics ----------


class TestProductionStatusSemantics:
    def test_node_status_overrides_library_status(self) -> None:
        node_metadata = _make_node_metadata(
            declarations=[ProductionStatusNodeProperty(status=ProductionStatus.ALPHA)],
        )

        node_status_decls = [d for d in node_metadata.declarations if isinstance(d, ProductionStatusNodeProperty)]
        assert len(node_status_decls) == 1
        assert node_status_decls[0].status is ProductionStatus.ALPHA

    def test_library_status_alone(self) -> None:
        lib_metadata = _make_library_metadata(
            declarations=[ProductionStatusLibraryProperty(status=ProductionStatus.PRODUCTION)],
        )

        lib_status_decls = [d for d in lib_metadata.declarations if isinstance(d, ProductionStatusLibraryProperty)]
        assert len(lib_status_decls) == 1
        assert lib_status_decls[0].status is ProductionStatus.PRODUCTION


# ---------- Round-trip JSON serialization ----------


class TestRoundTripSerialization:
    def test_full_library_schema_serializes_and_deserializes(self) -> None:
        schema = LibrarySchema(
            name="Test Library",
            library_schema_version=LibrarySchema.LATEST_SCHEMA_VERSION,
            metadata=_make_library_metadata(
                declarations=[ProductionStatusLibraryProperty(status=ProductionStatus.BETA)],
            ),
            categories=[{"Test": CategoryDefinition(title="Test", description="test", color="#000", icon="Folder")}],
            nodes=[
                NodeDefinition(
                    class_name="TestNode",
                    file_path="test_node.py",
                    metadata=_make_node_metadata(
                        declarations=[
                            ProductionStatusNodeProperty(status=ProductionStatus.ALPHA),
                            KeySupportNodeProperty(support=KeySupport.REQUIRES_CUSTOMER_KEY),
                        ],
                    ),
                ),
            ],
        )

        rebuilt = LibrarySchema.model_validate(json.loads(schema.model_dump_json()))

        assert rebuilt.metadata.declarations[0] == ProductionStatusLibraryProperty(status=ProductionStatus.BETA)
        node_decls = rebuilt.nodes[0].metadata.declarations
        assert isinstance(node_decls[0], ProductionStatusNodeProperty)
        assert node_decls[0].status is ProductionStatus.ALPHA
        assert isinstance(node_decls[1], KeySupportNodeProperty)


# ---------- Schema version ----------


class TestSchemaVersion:
    def test_latest_schema_version_is_080(self) -> None:
        assert LibrarySchema.LATEST_SCHEMA_VERSION == "0.8.0"

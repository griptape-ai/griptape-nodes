"""Tests for LibraryDeclaration / NodeDeclaration discriminated unions."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from griptape_nodes.node_library.library_declarations import (
    KeySupport,
    KeySupportNodeProperty,
    LifecycleStage,
    LifecycleStageLibraryProperty,
    LifecycleStageNodeProperty,
    WorkerLibraryCapability,
    WorkerSupport,
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
    def test_node_lifecycle_stage_round_trips(self) -> None:
        metadata = _make_node_metadata(declarations=[LifecycleStageNodeProperty(stage=LifecycleStage.BETA)])

        rebuilt = NodeMetadata.model_validate(metadata.model_dump())

        assert isinstance(rebuilt.declarations[0], LifecycleStageNodeProperty)
        assert rebuilt.declarations[0].stage is LifecycleStage.BETA

    def test_node_key_support_round_trips(self) -> None:
        metadata = _make_node_metadata(declarations=[KeySupportNodeProperty(support=KeySupport.REQUIRES_CUSTOMER_KEY)])

        rebuilt = NodeMetadata.model_validate(metadata.model_dump())

        decl = rebuilt.declarations[0]
        assert isinstance(decl, KeySupportNodeProperty)
        assert decl.support is KeySupport.REQUIRES_CUSTOMER_KEY

    def test_library_lifecycle_stage_round_trips(self) -> None:
        metadata = _make_library_metadata(
            declarations=[LifecycleStageLibraryProperty(stage=LifecycleStage.STABLE)],
        )

        rebuilt = LibraryMetadata.model_validate(metadata.model_dump())

        assert isinstance(rebuilt.declarations[0], LifecycleStageLibraryProperty)
        assert rebuilt.declarations[0].stage is LifecycleStage.STABLE

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


# ---------- LifecycleStage inheritance semantics ----------


class TestLifecycleStageSemantics:
    def test_node_stage_overrides_library_stage(self) -> None:
        node_metadata = _make_node_metadata(
            declarations=[LifecycleStageNodeProperty(stage=LifecycleStage.ALPHA)],
        )

        node_stage_decls = [d for d in node_metadata.declarations if isinstance(d, LifecycleStageNodeProperty)]
        assert len(node_stage_decls) == 1
        assert node_stage_decls[0].stage is LifecycleStage.ALPHA

    def test_library_stage_alone(self) -> None:
        lib_metadata = _make_library_metadata(
            declarations=[LifecycleStageLibraryProperty(stage=LifecycleStage.STABLE)],
        )

        lib_stage_decls = [d for d in lib_metadata.declarations if isinstance(d, LifecycleStageLibraryProperty)]
        assert len(lib_stage_decls) == 1
        assert lib_stage_decls[0].stage is LifecycleStage.STABLE


# ---------- Round-trip JSON serialization ----------


class TestRoundTripSerialization:
    def test_full_library_schema_serializes_and_deserializes(self) -> None:
        schema = LibrarySchema(
            name="Test Library",
            library_schema_version=LibrarySchema.LATEST_SCHEMA_VERSION,
            metadata=_make_library_metadata(
                declarations=[LifecycleStageLibraryProperty(stage=LifecycleStage.BETA)],
            ),
            categories=[{"Test": CategoryDefinition(title="Test", description="test", color="#000", icon="Folder")}],
            nodes=[
                NodeDefinition(
                    class_name="TestNode",
                    file_path="test_node.py",
                    metadata=_make_node_metadata(
                        declarations=[
                            LifecycleStageNodeProperty(stage=LifecycleStage.ALPHA),
                            KeySupportNodeProperty(support=KeySupport.REQUIRES_CUSTOMER_KEY),
                        ],
                    ),
                ),
            ],
        )

        rebuilt = LibrarySchema.model_validate(json.loads(schema.model_dump_json()))

        assert rebuilt.metadata.declarations[0] == LifecycleStageLibraryProperty(stage=LifecycleStage.BETA)
        node_decls = rebuilt.nodes[0].metadata.declarations
        assert isinstance(node_decls[0], LifecycleStageNodeProperty)
        assert node_decls[0].stage is LifecycleStage.ALPHA
        assert isinstance(node_decls[1], KeySupportNodeProperty)


# ---------- WorkerLibraryCapability ----------


class TestWorkerLibraryCapability:
    @pytest.mark.parametrize(
        "support",
        [
            WorkerSupport.SUPPORTS_WORKER_MODE,
            WorkerSupport.REQUIRES_ORCHESTRATOR_MODE,
            WorkerSupport.REQUIRES_WORKER_MODE,
        ],
    )
    def test_round_trips_each_enum_value(self, support: WorkerSupport) -> None:
        capability = WorkerLibraryCapability(support=support)

        rebuilt = WorkerLibraryCapability.model_validate(json.loads(capability.model_dump_json()))

        assert rebuilt.support is support

    def test_rejects_unknown_support_value(self) -> None:
        with pytest.raises(ValidationError):
            WorkerLibraryCapability.model_validate({"type": "worker", "support": "BOGUS"})

    @pytest.mark.parametrize(
        ("support", "expected"),
        [
            (WorkerSupport.SUPPORTS_WORKER_MODE, False),
            (WorkerSupport.REQUIRES_ORCHESTRATOR_MODE, False),
            (WorkerSupport.REQUIRES_WORKER_MODE, True),
        ],
    )
    def test_requires_worker_process_only_for_required_worker_mode(
        self, support: WorkerSupport, *, expected: bool
    ) -> None:
        assert WorkerLibraryCapability(support=support).requires_worker_process() is expected

    def test_library_metadata_round_trips_worker_capability_declaration(self) -> None:
        metadata = _make_library_metadata(
            declarations=[WorkerLibraryCapability(support=WorkerSupport.REQUIRES_WORKER_MODE)],
        )

        rebuilt = LibraryMetadata.model_validate(metadata.model_dump())

        decl = rebuilt.declarations[0]
        assert isinstance(decl, WorkerLibraryCapability)
        assert decl.support is WorkerSupport.REQUIRES_WORKER_MODE

    def test_metadata_without_worker_capability_defaults_to_no_worker(self) -> None:
        # Replays the consumer-site idiom from library_manager.py: when no
        # WorkerLibraryCapability is present, requires_worker falls through to False
        # (i.e. REQUIRES_ORCHESTRATOR_MODE behavior).
        metadata = _make_library_metadata(
            declarations=[LifecycleStageLibraryProperty(stage=LifecycleStage.STABLE)],
        )

        worker_decl = next(
            (d for d in metadata.declarations if isinstance(d, WorkerLibraryCapability)),
            None,
        )
        requires_worker = worker_decl.requires_worker_process() if worker_decl is not None else False

        assert worker_decl is None
        assert requires_worker is False


# ---------- Schema version ----------


class TestSchemaVersion:
    def test_latest_schema_version_is_090(self) -> None:
        assert LibrarySchema.LATEST_SCHEMA_VERSION == "0.9.0"

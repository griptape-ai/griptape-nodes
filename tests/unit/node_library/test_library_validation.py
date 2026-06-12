"""Tests for `validate_library_declarations`."""

from __future__ import annotations

from typing import Any

from griptape_nodes.node_library.library_declarations import (
    KeySupport,
    ModelCatalogLibraryProperty,
    ModelFamily,
    ModelOffering,
    ModelProvider,
    ModelUsageNodeProperty,
)
from griptape_nodes.node_library.library_registry import (
    CategoryDefinition,
    LibraryMetadata,
    LibrarySchema,
    NodeDefinition,
    NodeMetadata,
)
from griptape_nodes.node_library.library_validation import validate_library_declarations
from griptape_nodes.retained_mode.managers.fitness_problems.libraries import (
    DuplicateModelOfferingIdProblem,
    UnresolvedModelUsageReferenceProblem,
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


def _make_schema(
    *,
    library_declarations: list[Any] | None = None,
    nodes: list[NodeDefinition] | None = None,
) -> LibrarySchema:
    lib_kwargs: dict[str, Any] = {}
    if library_declarations is not None:
        lib_kwargs["declarations"] = library_declarations
    return LibrarySchema(
        name="Test Library",
        library_schema_version=LibrarySchema.LATEST_SCHEMA_VERSION,
        metadata=_make_library_metadata(**lib_kwargs),
        categories=[{"Test": CategoryDefinition(title="Test", description="test", color="#000", icon="Folder")}],
        nodes=nodes or [],
    )


def _offering(display_name: str = "X") -> ModelOffering:
    return ModelOffering(display_name=display_name, key_support=KeySupport.REQUIRES_CUSTOMER_KEY)


# ---------- No declarations / clean library ----------


class TestCleanLibrary:
    def test_library_with_no_declarations_has_no_problems(self) -> None:
        schema = _make_schema()

        result = validate_library_declarations(schema)

        assert result.fatal == []
        assert result.warnings == []

    def test_library_with_only_a_clean_catalog_has_no_problems(self) -> None:
        schema = _make_schema(
            library_declarations=[
                ModelCatalogLibraryProperty(
                    providers={
                        "p": ModelProvider(
                            display_name="P",
                            offerings={"o": _offering()},
                        ),
                    },
                ),
            ],
        )

        result = validate_library_declarations(schema)

        assert result.fatal == []
        assert result.warnings == []


# ---------- Duplicate offering ids ----------


class TestDuplicateOfferingIds:
    def test_same_id_under_two_providers_is_fatal(self) -> None:
        schema = _make_schema(
            library_declarations=[
                ModelCatalogLibraryProperty(
                    providers={
                        "anthropic": ModelProvider(
                            display_name="Anthropic",
                            offerings={"shared": _offering()},
                        ),
                        "kling": ModelProvider(
                            display_name="Kling",
                            offerings={"shared": _offering()},
                        ),
                    },
                ),
            ],
        )

        result = validate_library_declarations(schema)

        duplicates = [p for p in result.fatal if isinstance(p, DuplicateModelOfferingIdProblem)]
        assert len(duplicates) == 1
        assert duplicates[0].offering_id == "shared"
        assert sorted(duplicates[0].parent_paths) == ["anthropic", "kling"]

    def test_same_id_under_provider_and_family_is_fatal(self) -> None:
        schema = _make_schema(
            library_declarations=[
                ModelCatalogLibraryProperty(
                    providers={
                        "anthropic": ModelProvider(
                            display_name="Anthropic",
                            families={
                                "claude_4": ModelFamily(
                                    display_name="Claude 4",
                                    offerings={"shared": _offering()},
                                ),
                            },
                            offerings={"shared": _offering()},
                        ),
                    },
                ),
            ],
        )

        result = validate_library_declarations(schema)

        duplicates = [p for p in result.fatal if isinstance(p, DuplicateModelOfferingIdProblem)]
        assert len(duplicates) == 1
        assert sorted(duplicates[0].parent_paths) == ["anthropic", "anthropic/claude_4"]

    def test_unique_ids_pass(self) -> None:
        schema = _make_schema(
            library_declarations=[
                ModelCatalogLibraryProperty(
                    providers={
                        "anthropic": ModelProvider(
                            display_name="Anthropic",
                            offerings={"a": _offering()},
                        ),
                        "kling": ModelProvider(
                            display_name="Kling",
                            offerings={"b": _offering()},
                        ),
                    },
                ),
            ],
        )

        result = validate_library_declarations(schema)

        assert [p for p in result.fatal if isinstance(p, DuplicateModelOfferingIdProblem)] == []


# ---------- Unresolved model usage references ----------


class TestUnresolvedModelUsageReferences:
    def test_node_referencing_missing_offering_is_fatal(self) -> None:
        schema = _make_schema(
            library_declarations=[
                ModelCatalogLibraryProperty(
                    providers={
                        "p": ModelProvider(
                            display_name="P",
                            offerings={"o": _offering()},
                        ),
                    },
                ),
            ],
            nodes=[
                NodeDefinition(
                    class_name="UsesMissing",
                    file_path="x.py",
                    metadata=_make_node_metadata(declarations=[ModelUsageNodeProperty(offering_ids=["nonexistent"])]),
                ),
            ],
        )

        result = validate_library_declarations(schema)

        unresolved = [p for p in result.fatal if isinstance(p, UnresolvedModelUsageReferenceProblem)]
        assert len(unresolved) == 1
        assert unresolved[0].node_name == "UsesMissing"
        assert unresolved[0].offering_id == "nonexistent"

    def test_node_referencing_existing_offering_passes(self) -> None:
        schema = _make_schema(
            library_declarations=[
                ModelCatalogLibraryProperty(
                    providers={
                        "p": ModelProvider(
                            display_name="P",
                            offerings={"o": _offering()},
                        ),
                    },
                ),
            ],
            nodes=[
                NodeDefinition(
                    class_name="UsesExisting",
                    file_path="x.py",
                    metadata=_make_node_metadata(declarations=[ModelUsageNodeProperty(offering_ids=["o"])]),
                ),
            ],
        )

        result = validate_library_declarations(schema)

        assert result.fatal == []

    def test_node_with_no_catalog_and_a_reference_is_fatal(self) -> None:
        schema = _make_schema(
            library_declarations=[],
            nodes=[
                NodeDefinition(
                    class_name="UsesMissing",
                    file_path="x.py",
                    metadata=_make_node_metadata(declarations=[ModelUsageNodeProperty(offering_ids=["o"])]),
                ),
            ],
        )

        result = validate_library_declarations(schema)

        unresolved = [p for p in result.fatal if isinstance(p, UnresolvedModelUsageReferenceProblem)]
        assert len(unresolved) == 1

    def test_multiple_unresolved_references_all_reported(self) -> None:
        schema = _make_schema(
            library_declarations=[],
            nodes=[
                NodeDefinition(
                    class_name="N",
                    file_path="x.py",
                    metadata=_make_node_metadata(declarations=[ModelUsageNodeProperty(offering_ids=["a", "b"])]),
                ),
            ],
        )

        result = validate_library_declarations(schema)

        ids = [p.offering_id for p in result.fatal if isinstance(p, UnresolvedModelUsageReferenceProblem)]
        assert sorted(ids) == ["a", "b"]

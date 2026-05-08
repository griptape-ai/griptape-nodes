"""Tests for LibraryProperty / NodeProperty discriminated unions + catalog validation."""

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
    ModelCatalogLibraryProperty,
    ModelEntitlement,
    ModelUsageNodeProperty,
    PermissionCatalogLibraryProperty,
    PermissionDeclaration,
    ProductionStatus,
    ProductionStatusLibraryProperty,
    ProductionStatusNodeProperty,
    ProxyModelNodeProperty,
    RequiredPermissionsLibraryProperty,
    RequiredPermissionsNodeProperty,
)
from griptape_nodes.node_library.library_registry import (
    CategoryDefinition,
    LibraryMetadata,
    LibrarySchema,
    NodeDefinition,
    NodeMetadata,
)
from griptape_nodes.node_library.library_validation import validate_library_declarations
from griptape_nodes.node_library.permission_builtins import (
    MARKER_EXECUTE_ARBITRARY_CODE,
    RUN_ARBITRARY_PYTHON,
)
from griptape_nodes.retained_mode.managers.fitness_problems.libraries import (
    BuiltinPermissionShadowedProblem,
    PermissionReferenceSite,
    UndeclaredModelUsageReferenceProblem,
    UndeclaredPermissionReferenceProblem,
    UnrecognizedMarkerDiscriminatorProblem,
    UnreferencedCatalogPermissionProblem,
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
    nodes: list[NodeDefinition] | None = None,
) -> LibrarySchema:
    lib_kwargs: dict[str, Any] = {}
    if library_properties is not None:
        lib_kwargs["properties"] = library_properties
    if nodes is None:
        nodes = [
            NodeDefinition(
                class_name="TestNode",
                file_path="test_node.py",
                metadata=_make_node_metadata(),
            )
        ]
    return LibrarySchema(
        name="Test Library",
        library_schema_version=LibrarySchema.LATEST_SCHEMA_VERSION,
        metadata=_make_library_metadata(**lib_kwargs),
        categories=[{"Test": CategoryDefinition(title="Test", description="test", color="#000", icon="Folder")}],
        nodes=nodes,
    )


# ---------- Schema-level tests ----------


class TestMetadataPropertiesDefaults:
    def test_library_metadata_properties_defaults_to_empty(self) -> None:
        assert _make_library_metadata().properties == []

    def test_node_metadata_properties_defaults_to_empty(self) -> None:
        assert _make_node_metadata().properties == []


class TestPropertyDiscriminator:
    def test_library_property_discriminator_selects_correct_subclass(self) -> None:
        payloads = [
            {"type": "production_status", "status": "BETA"},
            {
                "type": "permission_catalog",
                "permissions": {"use_x": {"description": "x"}},
            },
            {
                "type": "model_catalog",
                "entitlements": {
                    "foo": {
                        "display_name": "Foo",
                        "provider": "ProviderX",
                        "terms_url": "https://example.com/terms",
                    }
                },
            },
            {"type": "required_permissions", "names": ["use_x"]},
        ]
        metadata = LibraryMetadata.model_validate(
            {
                "author": "test",
                "description": "test",
                "library_version": "1.0.0",
                "engine_version": "1.0.0",
                "tags": [],
                "properties": payloads,
            }
        )

        assert len(metadata.properties) == len(payloads)
        assert isinstance(metadata.properties[0], ProductionStatusLibraryProperty)
        assert metadata.properties[0].status is ProductionStatus.BETA
        assert isinstance(metadata.properties[1], PermissionCatalogLibraryProperty)
        assert isinstance(metadata.properties[2], ModelCatalogLibraryProperty)
        assert isinstance(metadata.properties[3], RequiredPermissionsLibraryProperty)

    def test_node_property_discriminator_selects_correct_subclass(self) -> None:
        payloads = [
            {"type": "execute_arbitrary_code"},
            {"type": "key_support", "support": "REQUIRES_CUSTOMER_KEY"},
            {"type": "engine_control"},
            {"type": "proxy_model"},
            {"type": "model_usage", "name": "some_model"},
            {"type": "required_permissions", "names": ["use_x"]},
            {"type": "production_status", "status": "EXPERIMENTAL"},
        ]
        metadata = NodeMetadata.model_validate(
            {
                "category": "Test",
                "description": "test",
                "display_name": "TestNode",
                "properties": payloads,
            }
        )

        assert len(metadata.properties) == len(payloads)
        assert isinstance(metadata.properties[0], ExecuteArbitraryCodeNodeProperty)
        assert isinstance(metadata.properties[1], KeySupportNodeProperty)
        assert metadata.properties[1].support is KeySupport.REQUIRES_CUSTOMER_KEY
        assert isinstance(metadata.properties[2], EngineControlNodeProperty)
        assert isinstance(metadata.properties[3], ProxyModelNodeProperty)
        assert isinstance(metadata.properties[4], ModelUsageNodeProperty)
        assert metadata.properties[4].name == "some_model"
        assert isinstance(metadata.properties[5], RequiredPermissionsNodeProperty)
        assert isinstance(metadata.properties[6], ProductionStatusNodeProperty)

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
        assert _make_node_metadata().properties == []

    def test_node_production_status_round_trip(self) -> None:
        metadata = _make_node_metadata(properties=[ProductionStatusNodeProperty(status=ProductionStatus.BETA)])

        reloaded = NodeMetadata.model_validate(metadata.model_dump())

        assert len(reloaded.properties) == 1
        assert isinstance(reloaded.properties[0], ProductionStatusNodeProperty)
        assert reloaded.properties[0].status is ProductionStatus.BETA

    def test_production_status_node_property_requires_status(self) -> None:
        with pytest.raises(ValidationError):
            ProductionStatusNodeProperty()  # type: ignore[call-arg]


class TestModelEntitlement:
    def test_requires_display_name(self) -> None:
        with pytest.raises(ValidationError):
            ModelEntitlement.model_validate({"provider": "OpenAI", "terms_url": "https://example.com/terms"})

    def test_requires_provider(self) -> None:
        with pytest.raises(ValidationError):
            ModelEntitlement.model_validate({"display_name": "X", "terms_url": "https://example.com/terms"})

    def test_requires_terms_url(self) -> None:
        with pytest.raises(ValidationError):
            ModelEntitlement.model_validate({"display_name": "X", "provider": "OpenAI"})

    def test_family_and_model_optional(self) -> None:
        entitlement = ModelEntitlement(
            display_name="Some Provider",
            provider="SomeProvider",
            terms_url="https://example.com/terms",
        )
        assert entitlement.family is None
        assert entitlement.model is None
        assert entitlement.requires_permission is None

    def test_full_granularity_round_trip(self) -> None:
        original = ModelEntitlement(
            display_name="Kling v2",
            provider="Kling",
            family="Kling v2",
            model="kling-v2-master",
            terms_url="https://example.com/kling",
            requires_permission="use_kling",
        )

        reloaded = ModelEntitlement.model_validate(original.model_dump())

        assert reloaded.display_name == "Kling v2"
        assert reloaded.provider == "Kling"
        assert reloaded.family == "Kling v2"
        assert reloaded.model == "kling-v2-master"
        assert reloaded.terms_url == "https://example.com/kling"
        assert reloaded.requires_permission == "use_kling"


class TestModelUsageNodeProperty:
    def test_requires_name(self) -> None:
        with pytest.raises(ValidationError):
            NodeMetadata.model_validate(
                {
                    "category": "Test",
                    "description": "test",
                    "display_name": "TestNode",
                    "properties": [{"type": "model_usage"}],
                }
            )


class TestModelCatalogRoundTrip:
    def test_catalog_round_trips(self) -> None:
        original = ModelCatalogLibraryProperty(
            entitlements={
                "gpt4o": ModelEntitlement(
                    display_name="GPT-4o",
                    provider="OpenAI",
                    family="GPT-4",
                    model="gpt-4o",
                    terms_url="https://openai.com/terms",
                ),
                "kling_v2": ModelEntitlement(
                    display_name="Kling v2",
                    provider="Kling",
                    family="Kling v2",
                    terms_url="https://kling.example/terms",
                    requires_permission="use_kling",
                ),
            }
        )

        reloaded = ModelCatalogLibraryProperty.model_validate(original.model_dump())

        assert set(reloaded.entitlements.keys()) == {"gpt4o", "kling_v2"}
        assert reloaded.entitlements["kling_v2"].requires_permission == "use_kling"


class TestPermissionCatalogRoundTrip:
    def test_catalog_with_entries_and_marker_mapping_round_trips(self) -> None:
        policy_src = 'permit(principal, action == Action::"use_model", resource == Entitlement::"use_openai");'
        original = PermissionCatalogLibraryProperty(
            permissions={
                "use_kling": PermissionDeclaration(description="Access Kling models."),
                "use_openai": PermissionDeclaration(
                    description="Access OpenAI models.",
                    policies=[policy_src],
                ),
            },
            marker_mapping={"execute_arbitrary_code": "use_kling"},
        )

        reloaded = PermissionCatalogLibraryProperty.model_validate(original.model_dump())

        assert reloaded.permissions["use_kling"].description == "Access Kling models."
        assert reloaded.permissions["use_kling"].policies == []
        assert reloaded.permissions["use_openai"].policies == [policy_src]
        assert reloaded.marker_mapping == {"execute_arbitrary_code": "use_kling"}

    def test_permissions_defaults_to_empty(self) -> None:
        """A library using only built-ins + built-in marker mappings needs no `permissions`."""
        catalog = PermissionCatalogLibraryProperty()
        assert catalog.permissions == {}
        assert catalog.marker_mapping == {}

    def test_permission_declaration_policies_defaults_to_empty_list(self) -> None:
        """A permission declared without policies yields an empty list (engine grants when evaluator is stub)."""
        declaration = PermissionDeclaration(description="x")
        assert declaration.policies == []


class TestRoundTripSerialization:
    def test_every_property_type_round_trips(self) -> None:
        """LibrarySchema with one of every property type dumps to JSON and reloads unchanged."""
        schema = _make_library_schema(
            library_properties=[
                ProductionStatusLibraryProperty(status=ProductionStatus.PRODUCTION),
                PermissionCatalogLibraryProperty(
                    permissions={"use_foo": PermissionDeclaration(description="Use Foo.")},
                    marker_mapping={"proxy_model": "use_foo"},
                ),
                ModelCatalogLibraryProperty(
                    entitlements={
                        "foo": ModelEntitlement(
                            display_name="Foo",
                            provider="ProviderX",
                            terms_url="https://example.com/terms",
                            requires_permission="use_foo",
                        )
                    }
                ),
                RequiredPermissionsLibraryProperty(names=["use_foo"]),
            ],
            nodes=[
                NodeDefinition(
                    class_name="TestNode",
                    file_path="test_node.py",
                    metadata=_make_node_metadata(
                        properties=[
                            ProductionStatusNodeProperty(status=ProductionStatus.BETA),
                            RequiredPermissionsNodeProperty(names=["use_foo"]),
                            ModelUsageNodeProperty(name="foo"),
                            ProxyModelNodeProperty(),
                            ExecuteArbitraryCodeNodeProperty(),
                            EngineControlNodeProperty(),
                            KeySupportNodeProperty(support=KeySupport.REQUIRES_GRIPTAPE_KEY),
                        ]
                    ),
                )
            ],
        )

        reloaded = LibrarySchema.model_validate_json(schema.model_dump_json())

        assert reloaded == schema


class TestSchemaVersion:
    def test_schema_version_bumped(self) -> None:
        assert LibrarySchema.LATEST_SCHEMA_VERSION == "0.8.0"


class TestBackwardCompatibility:
    def test_older_schema_loads_with_empty_properties(self) -> None:
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


# ---------- Catalog validation tests ----------


def _catalog(
    *,
    permissions: dict[str, PermissionDeclaration] | None = None,
    marker_mapping: dict[str, str] | None = None,
) -> PermissionCatalogLibraryProperty:
    return PermissionCatalogLibraryProperty(
        permissions=permissions or {},
        marker_mapping=marker_mapping or {},
    )


def _model_catalog(entitlements: dict[str, ModelEntitlement]) -> ModelCatalogLibraryProperty:
    return ModelCatalogLibraryProperty(entitlements=entitlements)


class TestCatalogValidationFatal:
    def test_library_with_no_catalogs_and_only_markers_loads_cleanly(self) -> None:
        """Built-in marker_mapping supplies the permission for ExecuteArbitraryCodeNodeProperty."""
        schema = _make_library_schema(
            nodes=[
                NodeDefinition(
                    class_name="TestNode",
                    file_path="t.py",
                    metadata=_make_node_metadata(properties=[ExecuteArbitraryCodeNodeProperty()]),
                )
            ]
        )

        result = validate_library_declarations(schema)

        assert result.fatal == []
        assert result.warnings == []

    def test_node_permission_reference_resolves_against_library_catalog(self) -> None:
        schema = _make_library_schema(
            library_properties=[_catalog(permissions={"use_x": PermissionDeclaration(description="x")})],
            nodes=[
                NodeDefinition(
                    class_name="TestNode",
                    file_path="t.py",
                    metadata=_make_node_metadata(properties=[RequiredPermissionsNodeProperty(names=["use_x"])]),
                )
            ],
        )

        result = validate_library_declarations(schema)

        assert result.fatal == []

    def test_node_permission_reference_resolves_against_builtin(self) -> None:
        """Built-in names resolve without a library catalog entry."""
        schema = _make_library_schema(
            nodes=[
                NodeDefinition(
                    class_name="TestNode",
                    file_path="t.py",
                    metadata=_make_node_metadata(
                        properties=[RequiredPermissionsNodeProperty(names=[RUN_ARBITRARY_PYTHON])]
                    ),
                )
            ]
        )

        result = validate_library_declarations(schema)

        assert result.fatal == []

    def test_unresolved_node_permission_reference_rejected(self) -> None:
        schema = _make_library_schema(
            nodes=[
                NodeDefinition(
                    class_name="TestNode",
                    file_path="t.py",
                    metadata=_make_node_metadata(properties=[RequiredPermissionsNodeProperty(names=["nope"])]),
                )
            ]
        )

        result = validate_library_declarations(schema)

        assert len(result.fatal) == 1
        problem = result.fatal[0]
        assert isinstance(problem, UndeclaredPermissionReferenceProblem)
        assert problem.reference_site is PermissionReferenceSite.NODE_REQUIRED_PERMISSIONS
        assert problem.permission_name == "nope"
        assert problem.node_name == "TestNode"

    def test_library_permission_cannot_shadow_builtin(self) -> None:
        schema = _make_library_schema(
            library_properties=[
                _catalog(
                    permissions={
                        RUN_ARBITRARY_PYTHON: PermissionDeclaration(description="shadow"),
                    }
                )
            ]
        )

        result = validate_library_declarations(schema)

        shadowed = [p for p in result.fatal if isinstance(p, BuiltinPermissionShadowedProblem)]
        assert len(shadowed) == 1
        assert shadowed[0].permission_name == RUN_ARBITRARY_PYTHON

    def test_library_level_required_permission_must_resolve(self) -> None:
        schema = _make_library_schema(library_properties=[RequiredPermissionsLibraryProperty(names=["nope"])])

        result = validate_library_declarations(schema)

        assert len(result.fatal) == 1
        problem = result.fatal[0]
        assert isinstance(problem, UndeclaredPermissionReferenceProblem)
        assert problem.reference_site is PermissionReferenceSite.LIBRARY_REQUIRED_PERMISSIONS
        assert problem.permission_name == "nope"

    def test_marker_mapping_override_key_must_be_recognized(self) -> None:
        schema = _make_library_schema(
            library_properties=[
                _catalog(
                    permissions={"use_x": PermissionDeclaration(description="x")},
                    marker_mapping={"not_a_marker": "use_x"},
                )
            ]
        )

        result = validate_library_declarations(schema)

        unrecognized = [p for p in result.fatal if isinstance(p, UnrecognizedMarkerDiscriminatorProblem)]
        assert len(unrecognized) == 1
        assert unrecognized[0].marker_key == "not_a_marker"

    def test_marker_mapping_override_value_must_resolve(self) -> None:
        schema = _make_library_schema(
            library_properties=[_catalog(marker_mapping={MARKER_EXECUTE_ARBITRARY_CODE: "undeclared"})]
        )

        result = validate_library_declarations(schema)

        undeclared = [
            p
            for p in result.fatal
            if isinstance(p, UndeclaredPermissionReferenceProblem)
            and p.reference_site is PermissionReferenceSite.MARKER_MAPPING_TARGET
        ]
        assert len(undeclared) == 1
        assert undeclared[0].marker_key == MARKER_EXECUTE_ARBITRARY_CODE
        assert undeclared[0].permission_name == "undeclared"

    def test_marker_mapping_can_override_builtin_target(self) -> None:
        schema = _make_library_schema(
            library_properties=[
                _catalog(
                    permissions={
                        "my_custom_perm": PermissionDeclaration(description="custom"),
                    },
                    marker_mapping={MARKER_EXECUTE_ARBITRARY_CODE: "my_custom_perm"},
                )
            ]
        )

        result = validate_library_declarations(schema)

        assert result.fatal == []

    def test_model_usage_name_must_resolve_against_model_catalog(self) -> None:
        schema = _make_library_schema(
            library_properties=[
                _model_catalog({"foo": ModelEntitlement(display_name="Foo", provider="P", terms_url="https://e.x/t")})
            ],
            nodes=[
                NodeDefinition(
                    class_name="TestNode",
                    file_path="t.py",
                    metadata=_make_node_metadata(properties=[ModelUsageNodeProperty(name="missing")]),
                )
            ],
        )

        result = validate_library_declarations(schema)

        assert len(result.fatal) == 1
        problem = result.fatal[0]
        assert isinstance(problem, UndeclaredModelUsageReferenceProblem)
        assert problem.entitlement_name == "missing"
        assert problem.node_name == "TestNode"

    def test_model_entitlement_requires_permission_must_resolve(self) -> None:
        schema = _make_library_schema(
            library_properties=[
                _model_catalog(
                    {
                        "foo": ModelEntitlement(
                            display_name="Foo",
                            provider="P",
                            terms_url="https://e.x/t",
                            requires_permission="nope",
                        )
                    }
                )
            ]
        )

        result = validate_library_declarations(schema)

        undeclared = [
            p
            for p in result.fatal
            if isinstance(p, UndeclaredPermissionReferenceProblem)
            and p.reference_site is PermissionReferenceSite.MODEL_ENTITLEMENT_REQUIRES_PERMISSION
        ]
        assert len(undeclared) == 1
        assert undeclared[0].entitlement_name == "foo"
        assert undeclared[0].permission_name == "nope"

    def test_valid_model_catalog_and_references_load_cleanly(self) -> None:
        schema = _make_library_schema(
            library_properties=[
                _catalog(permissions={"use_foo": PermissionDeclaration(description="foo")}),
                _model_catalog(
                    {
                        "foo": ModelEntitlement(
                            display_name="Foo",
                            provider="P",
                            terms_url="https://e.x/t",
                            requires_permission="use_foo",
                        )
                    }
                ),
            ],
            nodes=[
                NodeDefinition(
                    class_name="TestNode",
                    file_path="t.py",
                    metadata=_make_node_metadata(properties=[ModelUsageNodeProperty(name="foo")]),
                )
            ],
        )

        result = validate_library_declarations(schema)

        assert result.fatal == []
        assert result.warnings == []


class TestCatalogValidationWarnings:
    def test_declared_permission_not_referenced_yields_warning(self) -> None:
        """A permission declared in the catalog but never referenced surfaces as a warning."""
        schema = _make_library_schema(
            library_properties=[_catalog(permissions={"use_dangling": PermissionDeclaration(description="dangling")})],
        )

        result = validate_library_declarations(schema)

        assert result.fatal == []
        assert len(result.warnings) == 1
        problem = result.warnings[0]
        assert isinstance(problem, UnreferencedCatalogPermissionProblem)
        assert problem.permission_name == "use_dangling"

    def test_declared_permission_referenced_by_node_yields_no_warning(self) -> None:
        schema = _make_library_schema(
            library_properties=[_catalog(permissions={"use_x": PermissionDeclaration(description="x")})],
            nodes=[
                NodeDefinition(
                    class_name="TestNode",
                    file_path="t.py",
                    metadata=_make_node_metadata(properties=[RequiredPermissionsNodeProperty(names=["use_x"])]),
                )
            ],
        )

        result = validate_library_declarations(schema)

        assert result.warnings == []

    def test_declared_permission_referenced_by_marker_mapping_yields_no_warning(self) -> None:
        schema = _make_library_schema(
            library_properties=[
                _catalog(
                    permissions={"use_custom": PermissionDeclaration(description="custom")},
                    marker_mapping={MARKER_EXECUTE_ARBITRARY_CODE: "use_custom"},
                )
            ],
        )

        result = validate_library_declarations(schema)

        assert result.warnings == []

    def test_declared_permission_referenced_by_model_entitlement_yields_no_warning(self) -> None:
        schema = _make_library_schema(
            library_properties=[
                _catalog(permissions={"use_foo": PermissionDeclaration(description="foo")}),
                _model_catalog(
                    {
                        "foo": ModelEntitlement(
                            display_name="Foo",
                            provider="P",
                            terms_url="https://e.x/t",
                            requires_permission="use_foo",
                        )
                    }
                ),
            ],
        )

        result = validate_library_declarations(schema)

        assert result.warnings == []

    def test_declared_permission_referenced_by_library_requirement_yields_no_warning(self) -> None:
        schema = _make_library_schema(
            library_properties=[
                _catalog(permissions={"install_sandbox": PermissionDeclaration(description="install")}),
                RequiredPermissionsLibraryProperty(names=["install_sandbox"]),
            ],
        )

        result = validate_library_declarations(schema)

        assert result.warnings == []

    def test_shadowed_builtin_does_not_also_generate_unreferenced_warning(self) -> None:
        """A shadowing attempt is a fatal problem; we don't also warn about it being unreferenced."""
        schema = _make_library_schema(
            library_properties=[
                _catalog(permissions={RUN_ARBITRARY_PYTHON: PermissionDeclaration(description="shadow")})
            ]
        )

        result = validate_library_declarations(schema)

        assert result.warnings == []

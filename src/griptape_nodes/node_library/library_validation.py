"""Validation for declarative library property references.

After Pydantic shape validation via `LibrarySchema.model_validate()`, cross-references
between properties (a node's `requires_permission` string pointing to a catalog entry,
a `ModelUsageNodeProperty.name` pointing to a model entitlement) need to be resolved
against the library's own declarations plus engine-provided built-ins.

This module's single public entry point is `validate_library_declarations`, which
walks a validated `LibrarySchema` and returns a `LibraryDeclarationValidationResult`
with two lists: `fatal` problems that should block library load, and `warnings` that
should be surfaced alongside a successful load.

The caller folds these into the existing library-loading problem-reporting flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from griptape_nodes.node_library.library_properties import (
    ModelCatalogLibraryProperty,
    ModelUsageNodeProperty,
    PermissionCatalogLibraryProperty,
    RequiredPermissionsLibraryProperty,
    RequiredPermissionsNodeProperty,
)
from griptape_nodes.node_library.permission_builtins import (
    BUILTIN_PERMISSIONS,
    RECOGNIZED_MARKER_DISCRIMINATORS,
)
from griptape_nodes.retained_mode.managers.fitness_problems.libraries import (
    BuiltinPermissionShadowedProblem,
    LibraryProblem,
    PermissionReferenceSite,
    UndeclaredModelUsageReferenceProblem,
    UndeclaredPermissionReferenceProblem,
    UnrecognizedMarkerDiscriminatorProblem,
    UnreferencedCatalogPermissionProblem,
)

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibrarySchema, NodeDefinition


class LibraryDeclarationValidationResult(NamedTuple):
    """Outcome of `validate_library_declarations`.

    - `fatal`: problems that must block library load. Unresolved permission
      references, shadowed built-in permissions, unrecognized marker keys, and
      unresolved `ModelUsageNodeProperty.name` references all go here.
    - `warnings`: problems that should be surfaced but do not block load. A
      catalog permission declared but not referenced anywhere in the library is
      a hygiene concern that surfaces as a warning.
    """

    fatal: list[LibraryProblem]
    warnings: list[LibraryProblem]


class _NodeValidationContext(NamedTuple):
    """Shared state passed through the per-node validation helper.

    Bundles the resolved effective-permission set, the set of declared model
    entitlement names, the accumulating set of referenced permission names, and
    the fatal problem list, so the helper signature stays narrow.
    """

    effective_permissions: set[str]
    declared_entitlements: set[str]
    referenced_permissions: set[str]
    fatal: list[LibraryProblem]


def validate_library_declarations(library_data: LibrarySchema) -> LibraryDeclarationValidationResult:
    """Resolve cross-references within a library.

    All failures are collected; validation does not short-circuit on the first problem.
    """
    fatal: list[LibraryProblem] = []
    warnings: list[LibraryProblem] = []
    library_name = library_data.name

    permission_catalog = _find_permission_catalog(library_data)
    model_catalog = _find_model_catalog(library_data)

    effective_permissions = _build_effective_permissions(library_name, permission_catalog, fatal)
    referenced_permissions: set[str] = set()

    _validate_marker_mapping(library_name, permission_catalog, effective_permissions, referenced_permissions, fatal)
    _validate_model_catalog(library_name, model_catalog, effective_permissions, referenced_permissions, fatal)
    _validate_library_required_permissions(
        library_name, library_data, effective_permissions, referenced_permissions, fatal
    )

    declared_entitlements: set[str] = set(model_catalog.entitlements.keys()) if model_catalog is not None else set()
    node_context = _NodeValidationContext(
        effective_permissions=effective_permissions,
        declared_entitlements=declared_entitlements,
        referenced_permissions=referenced_permissions,
        fatal=fatal,
    )
    for node_def in library_data.nodes:
        _validate_node_properties(library_name, node_def, node_context)

    _collect_unreferenced_declarations(library_name, permission_catalog, referenced_permissions, warnings)

    return LibraryDeclarationValidationResult(fatal=fatal, warnings=warnings)


def _find_permission_catalog(library_data: LibrarySchema) -> PermissionCatalogLibraryProperty | None:
    for prop in library_data.metadata.properties:
        if isinstance(prop, PermissionCatalogLibraryProperty):
            return prop
    return None


def _find_model_catalog(library_data: LibrarySchema) -> ModelCatalogLibraryProperty | None:
    for prop in library_data.metadata.properties:
        if isinstance(prop, ModelCatalogLibraryProperty):
            return prop
    return None


def _build_effective_permissions(
    library_name: str,
    permission_catalog: PermissionCatalogLibraryProperty | None,
    fatal: list[LibraryProblem],
) -> set[str]:
    effective: set[str] = set(BUILTIN_PERMISSIONS.keys())
    if permission_catalog is None:
        return effective
    for name in permission_catalog.permissions:
        if name in BUILTIN_PERMISSIONS:
            fatal.append(BuiltinPermissionShadowedProblem(library_name=library_name, permission_name=name))
            continue
        effective.add(name)
    return effective


def _validate_marker_mapping(
    library_name: str,
    permission_catalog: PermissionCatalogLibraryProperty | None,
    effective_permissions: set[str],
    referenced_permissions: set[str],
    fatal: list[LibraryProblem],
) -> None:
    if permission_catalog is None:
        return
    for marker_key, target in permission_catalog.marker_mapping.items():
        if marker_key not in RECOGNIZED_MARKER_DISCRIMINATORS:
            fatal.append(
                UnrecognizedMarkerDiscriminatorProblem(
                    library_name=library_name,
                    marker_key=marker_key,
                    recognized_markers=tuple(sorted(RECOGNIZED_MARKER_DISCRIMINATORS)),
                )
            )
            continue
        referenced_permissions.add(target)
        if target not in effective_permissions:
            fatal.append(
                UndeclaredPermissionReferenceProblem(
                    library_name=library_name,
                    reference_site=PermissionReferenceSite.MARKER_MAPPING_TARGET,
                    permission_name=target,
                    marker_key=marker_key,
                )
            )


def _validate_model_catalog(
    library_name: str,
    model_catalog: ModelCatalogLibraryProperty | None,
    effective_permissions: set[str],
    referenced_permissions: set[str],
    fatal: list[LibraryProblem],
) -> None:
    if model_catalog is None:
        return
    for entitlement_name, entitlement in model_catalog.entitlements.items():
        if entitlement.requires_permission is None:
            continue
        referenced_permissions.add(entitlement.requires_permission)
        if entitlement.requires_permission not in effective_permissions:
            fatal.append(
                UndeclaredPermissionReferenceProblem(
                    library_name=library_name,
                    reference_site=PermissionReferenceSite.MODEL_ENTITLEMENT_REQUIRES_PERMISSION,
                    permission_name=entitlement.requires_permission,
                    entitlement_name=entitlement_name,
                )
            )


def _validate_library_required_permissions(
    library_name: str,
    library_data: LibrarySchema,
    effective_permissions: set[str],
    referenced_permissions: set[str],
    fatal: list[LibraryProblem],
) -> None:
    for lib_prop in library_data.metadata.properties:
        if not isinstance(lib_prop, RequiredPermissionsLibraryProperty):
            continue
        for name in lib_prop.names:
            referenced_permissions.add(name)
            if name in effective_permissions:
                continue
            fatal.append(
                UndeclaredPermissionReferenceProblem(
                    library_name=library_name,
                    reference_site=PermissionReferenceSite.LIBRARY_REQUIRED_PERMISSIONS,
                    permission_name=name,
                )
            )


def _validate_node_properties(
    library_name: str,
    node_def: NodeDefinition,
    context: _NodeValidationContext,
) -> None:
    node_name = node_def.class_name
    for node_prop in node_def.metadata.properties:
        if isinstance(node_prop, RequiredPermissionsNodeProperty):
            for name in node_prop.names:
                context.referenced_permissions.add(name)
                if name in context.effective_permissions:
                    continue
                context.fatal.append(
                    UndeclaredPermissionReferenceProblem(
                        library_name=library_name,
                        reference_site=PermissionReferenceSite.NODE_REQUIRED_PERMISSIONS,
                        permission_name=name,
                        node_name=node_name,
                    )
                )
        elif isinstance(node_prop, ModelUsageNodeProperty) and node_prop.name not in context.declared_entitlements:
            context.fatal.append(
                UndeclaredModelUsageReferenceProblem(
                    library_name=library_name,
                    node_name=node_name,
                    entitlement_name=node_prop.name,
                )
            )


def _collect_unreferenced_declarations(
    library_name: str,
    permission_catalog: PermissionCatalogLibraryProperty | None,
    referenced_permissions: set[str],
    warnings: list[LibraryProblem],
) -> None:
    """Add a warning for every library-declared permission that nothing references."""
    if permission_catalog is None:
        return
    for name in permission_catalog.permissions:
        if name in BUILTIN_PERMISSIONS:
            # Shadowing is already a fatal problem; no warning needed here.
            continue
        if name in referenced_permissions:
            continue
        warnings.append(UnreferencedCatalogPermissionProblem(library_name=library_name, permission_name=name))

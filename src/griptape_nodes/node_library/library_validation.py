"""Cross-reference validation for declarative library declarations.

After Pydantic shape validation via `LibrarySchema.model_validate()`, references
between declarations (a `ModelUsageNodeProperty.offering_ids` entry pointing to
an offering id in `ModelCatalogLibraryProperty`) need to be resolved against
the library's own declarations.

This module's single public entry point is `validate_library_declarations`,
which walks a validated `LibrarySchema` and returns a
`LibraryDeclarationValidationResult` with two lists: `fatal` problems that
should block library load, and `warnings` that should be surfaced alongside a
successful load.

The caller folds these into the existing library-loading problem-reporting flow.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, NamedTuple

from griptape_nodes.node_library.library_declarations import (
    ModelCatalogLibraryProperty,
    ModelUsageNodeProperty,
    iter_catalog_offerings,
)
from griptape_nodes.retained_mode.managers.fitness_problems.libraries import (
    DuplicateModelOfferingIdProblem,
    LibraryProblem,
    UnresolvedModelUsageReferenceProblem,
)

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibrarySchema


class LibraryDeclarationValidationResult(NamedTuple):
    """Outcome of `validate_library_declarations`.

    - `fatal`: problems that must block library load. Cross-parent duplicate
      offering ids and unresolved `ModelUsageNodeProperty.offering_ids`
      references go here.
    - `warnings`: problems that should be surfaced but do not block load.
      Currently empty by construction; the slot stays in case future
      validation surfaces hygiene-only issues.
    """

    fatal: list[LibraryProblem]
    warnings: list[LibraryProblem]


def validate_library_declarations(library_data: LibrarySchema) -> LibraryDeclarationValidationResult:
    """Resolve cross-references within a library.

    All failures are collected; validation does not short-circuit on the first problem.
    """
    fatal: list[LibraryProblem] = []
    warnings: list[LibraryProblem] = []
    library_name = library_data.name

    catalog = _find_model_catalog(library_data)
    declared_offering_ids: set[str] = set()
    if catalog is not None:
        declared_offering_ids = _check_duplicate_offering_ids(library_name, catalog, fatal)

    _check_unresolved_model_usage(library_name, library_data, declared_offering_ids, fatal)

    return LibraryDeclarationValidationResult(fatal=fatal, warnings=warnings)


def _find_model_catalog(library_data: LibrarySchema) -> ModelCatalogLibraryProperty | None:
    for decl in library_data.metadata.declarations:
        if isinstance(decl, ModelCatalogLibraryProperty):
            return decl
    return None


def _check_duplicate_offering_ids(
    library_name: str,
    catalog: ModelCatalogLibraryProperty,
    fatal: list[LibraryProblem],
) -> set[str]:
    """Walk the catalog and report cross-parent duplicate offering ids.

    Returns the set of declared offering ids (ignoring duplicates) so the caller
    can validate node references against it.
    """
    parents_by_id: dict[str, list[str]] = defaultdict(list)
    for resolved in iter_catalog_offerings(catalog):
        parent_path = resolved.provider_id
        if resolved.family_id is not None:
            parent_path = f"{resolved.provider_id}/{resolved.family_id}"
        parents_by_id[resolved.offering_id].append(parent_path)

    for offering_id, parent_paths in parents_by_id.items():
        if len(parent_paths) > 1:
            fatal.append(
                DuplicateModelOfferingIdProblem(
                    library_name=library_name,
                    offering_id=offering_id,
                    parent_paths=tuple(parent_paths),
                )
            )

    return set(parents_by_id.keys())


def _check_unresolved_model_usage(
    library_name: str,
    library_data: LibrarySchema,
    declared_offering_ids: set[str],
    fatal: list[LibraryProblem],
) -> None:
    for node_def in library_data.nodes:
        for node_decl in node_def.metadata.declarations:
            if not isinstance(node_decl, ModelUsageNodeProperty):
                continue
            for offering_id in node_decl.offering_ids:
                if offering_id in declared_offering_ids:
                    continue
                fatal.append(
                    UnresolvedModelUsageReferenceProblem(
                        library_name=library_name,
                        node_name=node_def.class_name,
                        offering_id=offering_id,
                    )
                )

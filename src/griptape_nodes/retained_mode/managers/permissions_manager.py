"""Permission evaluation manager."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

from griptape_nodes.node_library.library_properties import (
    EngineControlNodeProperty,
    ExecuteArbitraryCodeNodeProperty,
    KeySupportNodeProperty,
    ModelCatalogLibraryProperty,
    ModelUsageNodeProperty,
    PermissionCatalogLibraryProperty,
    ProductionStatusNodeProperty,
    ProxyModelNodeProperty,
    RequiredPermissionsNodeProperty,
)
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.node_library.permission_builtins import BUILTIN_MARKER_MAPPING, BUILTIN_PERMISSIONS
from griptape_nodes.retained_mode.events.permission_events import (
    DenialReason,
    DenialReasonCode,
    EvaluateNodePermissionsRequest,
    EvaluateNodePermissionsResultFailure,
    EvaluateNodePermissionsResultSuccess,
    EvaluatePermissionDenied,
    EvaluatePermissionGranted,
    EvaluatePermissionRequest,
    EvaluatePermissionResultFailure,
    EvaluationFailureCode,
    ListModelEntitlementsRequest,
    ListModelEntitlementsResultFailure,
    ListModelEntitlementsResultSuccess,
    PermissionOutcome,
)

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_properties import ModelEntitlement, NodeProperty
    from griptape_nodes.node_library.library_registry import NodeMetadata
    from griptape_nodes.node_library.workflow_registry import LibraryNameAndNodeType
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class _ResolvedSubject(NamedTuple):
    """Node-metadata + library-catalog context resolved from a `LibraryNameAndNodeType`."""

    node_metadata: NodeMetadata
    permission_catalog: PermissionCatalogLibraryProperty | None
    model_catalog: ModelCatalogLibraryProperty | None


class _SubjectNotFound(NamedTuple):
    """Signals that a subject's library or node type could not be resolved.

    Surfaces as `EvaluatePermissionResultFailure` / `ListModelEntitlementsResultFailure`
    -- a failed evaluation, not a denial.
    """

    code: EvaluationFailureCode
    message: str


class PermissionsManager:
    """Central authority for permission evaluation.

    The manager exposes its behavior exclusively through request handlers on the
    event bus. Callers dispatch `EvaluatePermissionRequest` or
    `ListModelEntitlementsRequest` via `GriptapeNodes.handle_request(...)`; no Python
    method on the manager is part of the public surface.

    `_is_allowed` is the internal hook the real entitlement evaluator will replace;
    the stub currently returns True for every name.
    """

    def __init__(self, event_manager: EventManager | None = None) -> None:
        if event_manager is not None:
            event_manager.assign_manager_to_request_type(
                request_type=EvaluatePermissionRequest,
                callback=self.on_evaluate_permission_request,
            )
            event_manager.assign_manager_to_request_type(
                request_type=ListModelEntitlementsRequest,
                callback=self.on_list_model_entitlements_request,
            )
            event_manager.assign_manager_to_request_type(
                request_type=EvaluateNodePermissionsRequest,
                callback=self.on_evaluate_node_permissions_request,
            )

    def on_evaluate_permission_request(self, request: EvaluatePermissionRequest) -> ResultPayload:
        """Handle an `EvaluatePermissionRequest`."""
        return self._check_permission(subject=request.subject, permission_name=request.permission_name)

    def on_list_model_entitlements_request(self, request: ListModelEntitlementsRequest) -> ResultPayload:
        """Handle a `ListModelEntitlementsRequest`."""
        return self._list_model_entitlements(subject=request.subject)

    def on_evaluate_node_permissions_request(self, request: EvaluateNodePermissionsRequest) -> ResultPayload:
        """Handle an `EvaluateNodePermissionsRequest`."""
        return self._evaluate_node_permissions(subject=request.subject)

    def _is_allowed(self, permission_name: str) -> bool:  # noqa: ARG002
        """Internal hook: returns whether the named permission is granted for the caller.

        The real entitlement evaluator will replace the body of this method. The stub
        grants every permission.
        """
        return True

    def _check_permission(
        self,
        subject: LibraryNameAndNodeType,
        permission_name: str,
    ) -> EvaluatePermissionGranted | EvaluatePermissionDenied | EvaluatePermissionResultFailure:
        """Internal implementation of `EvaluatePermissionRequest`.

        Returns one of three result types:
          - `EvaluatePermissionResultFailure` when the subject (library or node type)
            cannot be resolved.
          - `EvaluatePermissionDenied` when evaluation completed and at least one
            denial reason applied (unknown permission, scope violation, policy denied).
          - `EvaluatePermissionGranted` when evaluation completed with no denial
            reasons.
        """
        resolved = self._resolve_subject(subject)
        if isinstance(resolved, _SubjectNotFound):
            return EvaluatePermissionResultFailure(
                failure_code=resolved.code,
                result_details=resolved.message,
            )

        denial_reasons: list[DenialReason] = []
        effective_catalog = self._build_effective_catalog(resolved.permission_catalog)
        declared = self._resolve_declared_permissions(
            node_metadata=resolved.node_metadata,
            permission_catalog=resolved.permission_catalog,
            model_catalog=resolved.model_catalog,
        )

        if permission_name not in effective_catalog:
            denial_reasons.append(
                DenialReason(
                    code=DenialReasonCode.UNKNOWN_PERMISSION,
                    message=(
                        f"Permission {permission_name!r} is not declared in library "
                        f"{subject.library_name!r}'s effective catalog (built-ins + library permissions)."
                    ),
                )
            )

        if permission_name not in declared:
            denial_reasons.append(
                DenialReason(
                    code=DenialReasonCode.DECLARATION_SCOPE_VIOLATION,
                    message=(
                        f"Node type {subject.node_type!r} in library {subject.library_name!r} did not "
                        f"declare permission {permission_name!r}."
                    ),
                )
            )

        if not self._is_allowed(permission_name):
            denial_reasons.append(
                DenialReason(
                    code=DenialReasonCode.POLICY_DENIED,
                    message=f"Permission {permission_name!r} was denied by policy.",
                )
            )

        if denial_reasons:
            return EvaluatePermissionDenied(
                denial_reasons=denial_reasons,
                result_details=self._describe_denial(subject, permission_name, denial_reasons),
            )

        return EvaluatePermissionGranted(
            result_details=(
                f"Permission {permission_name!r} granted for node type {subject.node_type!r} "
                f"in library {subject.library_name!r}."
            ),
        )

    def _list_model_entitlements(
        self,
        subject: LibraryNameAndNodeType,
    ) -> ListModelEntitlementsResultSuccess | ListModelEntitlementsResultFailure:
        """Internal implementation of `ListModelEntitlementsRequest`.

        Walks the node's `ModelUsageNodeProperty` entries in author-declared order,
        resolves each against the library's `ModelCatalogLibraryProperty.entitlements`,
        and keeps only those whose `requires_permission` is None or granted.

        Returns failure only when the subject itself (library or node type) cannot be
        resolved. An empty permitted list is a success, not a failure.
        """
        resolved = self._resolve_subject(subject)
        if isinstance(resolved, _SubjectNotFound):
            return ListModelEntitlementsResultFailure(
                failure_code=resolved.code,
                result_details=resolved.message,
            )

        if resolved.model_catalog is None:
            return ListModelEntitlementsResultSuccess(
                entitlements=[],
                result_details=(
                    f"Library {subject.library_name!r} declares no ModelCatalogLibraryProperty; "
                    f"returning empty entitlement list."
                ),
            )

        permitted: list[ModelEntitlement] = []
        for node_prop in resolved.node_metadata.properties:
            if not isinstance(node_prop, ModelUsageNodeProperty):
                continue
            entitlement = resolved.model_catalog.entitlements.get(node_prop.name)
            if entitlement is None:
                # Load-time validation guarantees every ModelUsageNodeProperty.name is in the
                # catalog; a miss here means the library state drifted after load, which we
                # treat as "not permitted" rather than raising.
                continue
            if entitlement.requires_permission is None or self._is_allowed(entitlement.requires_permission):
                permitted.append(entitlement)

        return ListModelEntitlementsResultSuccess(
            entitlements=permitted,
            result_details=(
                f"Node type {subject.node_type!r} in library {subject.library_name!r}: "
                f"{len(permitted)} of its declared model entitlements are permitted."
            ),
        )

    def _evaluate_node_permissions(
        self,
        subject: LibraryNameAndNodeType,
    ) -> EvaluateNodePermissionsResultSuccess | EvaluateNodePermissionsResultFailure:
        """Internal implementation of `EvaluateNodePermissionsRequest`.

        Evaluates every permission name the node declares (direct required,
        marker-mapped, and model-entitlement-derived) and buckets them into
        `granted` / `denied` lists. Preserves first-appearance order from the
        node's declared properties so callers can surface results in the same
        order the library author wrote them.

        Returns failure only when the subject itself (library or node type) cannot
        be resolved. A node that declared no permissions is still a success; both
        lists are just empty.
        """
        resolved = self._resolve_subject(subject)
        if isinstance(resolved, _SubjectNotFound):
            return EvaluateNodePermissionsResultFailure(
                failure_code=resolved.code,
                result_details=resolved.message,
            )

        declared_ordered = self._resolve_declared_permissions_ordered(
            node_metadata=resolved.node_metadata,
            permission_catalog=resolved.permission_catalog,
            model_catalog=resolved.model_catalog,
        )

        granted: list[PermissionOutcome] = []
        denied: list[PermissionOutcome] = []
        for name in declared_ordered:
            outcome_result = self._check_permission(subject=subject, permission_name=name)
            if isinstance(outcome_result, EvaluatePermissionGranted):
                granted.append(PermissionOutcome(name=name, reasons=[]))
            elif isinstance(outcome_result, EvaluatePermissionDenied):
                denied.append(PermissionOutcome(name=name, reasons=list(outcome_result.denial_reasons)))
            # _check_permission only returns Failure when the subject is unknown; we
            # resolved the subject above, so a Failure here would be an engine bug.
            # Fall through without appending to either bucket.

        return EvaluateNodePermissionsResultSuccess(
            granted=granted,
            denied=denied,
            result_details=(
                f"Node type {subject.node_type!r} in library {subject.library_name!r}: "
                f"{len(granted)} granted, {len(denied)} denied."
            ),
        )

    def _resolve_subject(self, subject: LibraryNameAndNodeType) -> _ResolvedSubject | _SubjectNotFound:
        try:
            library = LibraryRegistry.get_library(subject.library_name)
        except KeyError:
            return _SubjectNotFound(
                code=EvaluationFailureCode.UNKNOWN_LIBRARY,
                message=f"Library {subject.library_name!r} is not registered.",
            )

        library_data = library.get_library_data()
        node_metadata: NodeMetadata | None = next(
            (node_def.metadata for node_def in library_data.nodes if node_def.class_name == subject.node_type),
            None,
        )
        if node_metadata is None:
            return _SubjectNotFound(
                code=EvaluationFailureCode.UNKNOWN_NODE_TYPE,
                message=(f"Node type {subject.node_type!r} is not declared in library {subject.library_name!r}."),
            )

        return _ResolvedSubject(
            node_metadata=node_metadata,
            permission_catalog=self._find_permission_catalog(library_data.metadata.properties),
            model_catalog=self._find_model_catalog(library_data.metadata.properties),
        )

    @staticmethod
    def _find_permission_catalog(
        properties: list,
    ) -> PermissionCatalogLibraryProperty | None:
        for prop in properties:
            if isinstance(prop, PermissionCatalogLibraryProperty):
                return prop
        return None

    @staticmethod
    def _find_model_catalog(properties: list) -> ModelCatalogLibraryProperty | None:
        for prop in properties:
            if isinstance(prop, ModelCatalogLibraryProperty):
                return prop
        return None

    @staticmethod
    def _build_effective_catalog(permission_catalog: PermissionCatalogLibraryProperty | None) -> set[str]:
        effective: set[str] = set(BUILTIN_PERMISSIONS.keys())
        if permission_catalog is not None:
            # Library-declared names that shadow built-ins would have been rejected by
            # load-time validation; we don't re-enforce that here, just union.
            effective.update(permission_catalog.permissions.keys())
        return effective

    @staticmethod
    def _resolve_declared_permissions(
        *,
        node_metadata: NodeMetadata,
        permission_catalog: PermissionCatalogLibraryProperty | None,
        model_catalog: ModelCatalogLibraryProperty | None,
    ) -> set[str]:
        """Compute the set of permission names this node type declares.

        A permission is considered declared when it appears in any of:
          - `RequiredPermissionsNodeProperty.names` on the node
          - `ModelEntitlement.requires_permission` for an entitlement this node
            references via `ModelUsageNodeProperty`
          - The target of a marker-mapping entry (built-in or library-declared) for a
            marker property the node carries
        """
        return set(
            PermissionsManager._resolve_declared_permissions_ordered(
                node_metadata=node_metadata,
                permission_catalog=permission_catalog,
                model_catalog=model_catalog,
            )
        )

    @staticmethod
    def _resolve_declared_permissions_ordered(
        *,
        node_metadata: NodeMetadata,
        permission_catalog: PermissionCatalogLibraryProperty | None,
        model_catalog: ModelCatalogLibraryProperty | None,
    ) -> list[str]:
        """Same as `_resolve_declared_permissions` but preserves declaration order.

        Returns a list of permission names in the order they first appear when
        walking the node's properties. Duplicates are suppressed (first occurrence
        wins) so the same name referenced by two properties appears only once.

        Callers that surface declarations back to users (error messages, dropdown
        labels) should use this; callers doing set membership / containment checks
        should use `_resolve_declared_permissions`.
        """
        effective_marker_mapping: dict[str, str] = dict(BUILTIN_MARKER_MAPPING)
        if permission_catalog is not None:
            effective_marker_mapping.update(permission_catalog.marker_mapping)

        # dict[str, None] as an ordered-set: preserves insertion order (Python 3.7+)
        # and gives O(1) "already seen" checks without a separate set.
        ordered: dict[str, None] = {}
        for node_prop in node_metadata.properties:
            for name in PermissionsManager._declarations_from_property(
                node_prop=node_prop,
                model_catalog=model_catalog,
                marker_mapping=effective_marker_mapping,
            ):
                ordered.setdefault(name, None)
        return list(ordered.keys())

    @staticmethod
    def _declarations_from_property(  # noqa: PLR0911  -- one return per match arm is clearer than accumulating into a local
        *,
        node_prop: NodeProperty,
        model_catalog: ModelCatalogLibraryProperty | None,
        marker_mapping: dict[str, str],
    ) -> list[str]:
        """Return the permission names `node_prop` implicitly declares, in property-local order.

        Every NodeProperty subclass must be represented in one of the match arms --
        either contributing declarations or explicitly opting out. An unrecognized
        subclass raises NotImplementedError so that adding a new NodeProperty without
        considering its declaration contribution is a loud, development-time failure.
        """
        match node_prop:
            case RequiredPermissionsNodeProperty():
                return list(node_prop.names)

            case ModelUsageNodeProperty():
                # Contributes the entitlement's requires_permission if the library's
                # model catalog declares one for this name. Library load-time validation
                # has already guaranteed the name resolves when a catalog is present.
                if model_catalog is None:
                    return []
                entitlement = model_catalog.entitlements.get(node_prop.name)
                if entitlement is None or entitlement.requires_permission is None:
                    return []
                return [entitlement.requires_permission]

            case ExecuteArbitraryCodeNodeProperty() | EngineControlNodeProperty() | ProxyModelNodeProperty():
                # Capability markers contribute via marker_mapping. A marker without a
                # mapping target (custom marker, or mapping explicitly cleared) contributes
                # nothing -- that's the author saying "this marker is informational only."
                target = marker_mapping.get(node_prop.type)
                if target is None:
                    return []
                return [target]

            case ProductionStatusNodeProperty() | KeySupportNodeProperty():
                # These properties describe the node's lifecycle and key requirements;
                # they don't gate execution on permissions and contribute no declarations.
                return []

            case _:  # pyright: ignore[reportUnreachable]
                # Runtime guard: if a new NodeProperty subclass is added without a
                # corresponding match arm here, raise at the first call site so the
                # omission is caught in development rather than silently dropping
                # declarations. Pyright flags this as unreachable because NodeProperty
                # is a closed union; the guard is defensive against future additions.
                msg = (
                    f"Unhandled NodeProperty subclass {type(node_prop).__name__!r} in "
                    f"_declarations_from_property. Add a match arm for it -- "
                    f"either contributing to declarations or explicitly opting out."
                )
                raise NotImplementedError(msg)

    @staticmethod
    def _describe_denial(
        subject: LibraryNameAndNodeType,
        permission_name: str,
        denial_reasons: list[DenialReason],
    ) -> str:
        codes = ", ".join(reason.code for reason in denial_reasons)
        return (
            f"Permission {permission_name!r} denied for node type {subject.node_type!r} "
            f"in library {subject.library_name!r} ({codes})."
        )

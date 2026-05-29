"""PermissionManager: declarative policy over privileged engine operations.

Single chokepoint: a pre-dispatch hook on `EventManager` is the only place
verdicts are enforced. Everything else here exists to feed that hook with
fresh, well-typed inputs (principal identity, resolved fields, fact tree)
and to surface the resulting decisions over the existing event channels.

State is kept current by listening to formally defined `AppPayload` and
`ExecutionPayload` events, never by polling. Cache invalidation is driven
by the same broadcasts the rest of the engine already emits.
"""

from __future__ import annotations

import dataclasses
import logging
from collections import deque
from dataclasses import dataclass, fields, is_dataclass
from threading import Lock
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from griptape_nodes.retained_mode.events.app_events import ConfigChanged, LibraryLoadedNotification
from griptape_nodes.retained_mode.events.base_events import (
    Payload,
    RequestPayload,
    ResultPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.events.permission_events import (
    GetEffectivePolicyRequest,
    GetEffectivePolicyResultSuccess,
    GrantPermissionRuleRequest,
    GrantPermissionRuleResultFailure,
    GrantPermissionRuleResultSuccess,
    ListPermissionDecisionsRequest,
    ListPermissionDecisionsResultSuccess,
    PermissionDecisionEvent,
    RevokePermissionRuleRequest,
    RevokePermissionRuleResultFailure,
    RevokePermissionRuleResultSuccess,
)
from griptape_nodes.retained_mode.managers.permissions.facts import FactInvalidator, FactRegistry
from griptape_nodes.retained_mode.managers.permissions.matchers import (
    EvaluationResult,
    Principal,
    PrincipalKind,
    evaluate_policy,
)
from griptape_nodes.retained_mode.managers.permissions.schema import (
    Decision,
    PermissionPolicy,
    PermissionRule,
    PermissionSettings,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager, ResultContext

logger = logging.getLogger("griptape_nodes")


PERMISSION_OWN_REQUEST_TYPES: frozenset[str] = frozenset(
    {
        GetEffectivePolicyRequest.__name__,
        GrantPermissionRuleRequest.__name__,
        ListPermissionDecisionsRequest.__name__,
        RevokePermissionRuleRequest.__name__,
    }
)


@dataclass
@PayloadRegistry.register
class PermissionDeniedResult(ResultPayloadFailure):
    """Generic permission-denied result.

    Used when no typed failure payload can be auto-wired for the original
    request. The dispatcher prefers a request-specific failure class when one
    exists (e.g. `WriteFileResultFailure`) so handler-side type assumptions
    keep working; this class is the fall-through.
    """


class PermissionManager:
    """Enforce permission policy over `RequestPayload` dispatch."""

    # Per-layer settings are read straight off `ConfigManager`, ordered
    # highest-priority first so first-match-wins evaluation gives the right
    # precedence: env, then workspace, then project, then user, then
    # defaults. License rules sit ahead of every config layer at evaluation
    # time and are never persisted through this slot.
    _LAYER_ATTRS: tuple[tuple[str, str], ...] = (
        ("env", "env_config"),
        ("workspace", "workspace_config"),
        ("project", "project_config"),
        ("user", "user_config"),
        ("defaults", "default_config"),
    )
    _USER_LAYER_NAME: str = "user"

    def __init__(
        self,
        event_manager: EventManager,
        config_manager: ConfigManager,
    ) -> None:
        self._event_manager = event_manager
        self._config_manager = config_manager
        self._facts = FactRegistry()
        self._policy_lock = Lock()
        # Per-layer settings populated by `_reload_settings`. Each layer's
        # `policy.rules` carry their `granted_by` stamp (auto-applied at load
        # time when not explicitly set) so audit messages identify the source
        # config file.
        self._layer_settings: dict[str, PermissionSettings] = {}
        # Layer names whose `policy.default_decision` should be honored at
        # merge time. A layer is "explicit" when its config block actually
        # contains a `policy.default_decision` key, distinguishing
        # "workspace deliberately set ALLOW" from "workspace's policy was
        # silent and inherited the schema default of ALLOW."
        self._explicit_defaults: set[str] = set()
        # License rules sit ahead of every config layer in evaluation order;
        # set via `set_license_policy()`, never persisted to config.
        self._license_policy: PermissionPolicy = PermissionPolicy(default_decision=Decision.ALLOW)
        self._enabled = True
        self._consent_prompts_enabled = True
        self._audit_max_entries = 1000
        self._audit_lock = Lock()
        self._audit: deque[dict[str, Any]] = deque(maxlen=self._audit_max_entries)
        self._node_stack_lock = Lock()
        self._node_stack: list[dict[str, str | None]] = []
        # Re-entrancy is handled by `EventManager`, which guards the hook chain
        # with a thread-local flag: a fact provider or audit listener that
        # re-enters `handle_request` on the evaluating thread bypasses the
        # chain instead of recursing. A manager-level flag here would have to be
        # thread-local to match, and a shared one would fail open by skipping
        # evaluation for requests dispatched concurrently on other threads, so
        # we deliberately keep no such flag.

        self._reload_settings()

        # Wire the dispatcher hook before any request can be handled.
        event_manager.add_pre_dispatch_hook(self._on_pre_dispatch)

        # Subscribe to formally defined `AppPayload` event types for cache
        # invalidation / policy reloads. NodeStart/Finish principal tracking is
        # done through the explicit push_principal/pop_principal API; the engine
        # does not currently broadcast those execution events through this bus,
        # and we'd rather have the caller be explicit than have a silently-inert
        # listener.
        event_manager.add_listener_to_app_event(ConfigChanged, self._on_config_changed)
        event_manager.add_listener_to_app_event(LibraryLoadedNotification, self._on_library_loaded)

        # Manager-owned request handlers (introspection + grant/revoke).
        event_manager.assign_manager_to_request_type(GetEffectivePolicyRequest, self.on_get_effective_policy_request)
        event_manager.assign_manager_to_request_type(
            ListPermissionDecisionsRequest, self.on_list_permission_decisions_request
        )
        event_manager.assign_manager_to_request_type(GrantPermissionRuleRequest, self.on_grant_permission_rule_request)
        event_manager.assign_manager_to_request_type(
            RevokePermissionRuleRequest, self.on_revoke_permission_rule_request
        )

        # Built-in fact providers. Each maps to a stable, formally defined piece
        # of engine state and uses the appropriate invalidator so providers don't
        # poll. New providers register themselves through `facts.register_provider`
        # the same way.
        self._register_builtin_fact_providers()

    def _register_builtin_fact_providers(self) -> None:
        """Register the facts that ship with the permission system.

        Each provider returns a JSON-serializable value and declares an
        invalidator that maps to a real engine event. The fact tree paths are
        documented in the Permissions reference; new built-ins should be
        added here so they round-trip with the documentation.
        """
        self._facts.register_provider(
            "workspace.path",
            self._fact_workspace_path,
            invalidator=FactInvalidator.ON_CONFIG_CHANGED,
        )
        self._facts.register_provider(
            "engine.id",
            self._fact_engine_id,
            invalidator=FactInvalidator.NEVER,
        )
        self._facts.register_provider(
            "loaded_libraries.names",
            self._fact_loaded_library_names,
            invalidator=FactInvalidator.ON_LIBRARY_LOADED,
        )
        self._facts.register_provider(
            "current_node.library",
            lambda: self._current_node_field("library"),
            invalidator=FactInvalidator.ON_NODE_EXECUTION_BOUNDARY,
        )
        self._facts.register_provider(
            "current_node.node_type",
            lambda: self._current_node_field("node_type"),
            invalidator=FactInvalidator.ON_NODE_EXECUTION_BOUNDARY,
        )
        self._facts.register_provider(
            "current_node.node_name",
            lambda: self._current_node_field("node_name"),
            invalidator=FactInvalidator.ON_NODE_EXECUTION_BOUNDARY,
        )

    def _fact_workspace_path(self) -> str | None:
        try:
            return str(self._config_manager.workspace_path)
        except Exception:
            return None

    def _fact_engine_id(self) -> str | None:
        # Lazy import: EngineIdentityManager imports through the GriptapeNodes
        # singleton chain that this manager itself participates in.
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        try:
            return GriptapeNodes.EngineIdentityManager().active_engine_id
        except Exception:
            return None

    def _fact_loaded_library_names(self) -> list[str]:
        from griptape_nodes.node_library.library_registry import LibraryRegistry

        try:
            return list(LibraryRegistry.list_libraries())
        except Exception:
            return []

    def _current_node_field(self, key: str) -> str | None:
        with self._node_stack_lock:
            top = self._node_stack[-1] if self._node_stack else None
        if top is None:
            return None
        return top.get(key)

    # ------------------------------------------------------------------ public API

    @property
    def facts(self) -> FactRegistry:
        """Fact registry. Managers publish providers / enrichers through this."""
        return self._facts

    @property
    def policy(self) -> PermissionPolicy:
        """Merged view of license + per-layer config rules in evaluation order.

        License rules fire first, followed by config layers in priority order:
        env, then workspace, then project, then user, then defaults. The
        fall-through default is whichever layer's `policy.default_decision` was
        explicitly set first, defaulting to ALLOW; licenses deliberately have
        no default of their own.
        """
        return self._build_merged_policy()

    @property
    def user_policy(self) -> PermissionPolicy:
        """User-layer policy fragment as loaded from `ConfigManager.user_config`.

        Returns a deep copy. To mutate, go through `GrantPermissionRuleRequest`
        / `RevokePermissionRuleRequest`, or reach for `_user_policy` from
        within tests where in-place mutation is the intended interface.
        """
        with self._policy_lock:
            slot = self._layer_settings.get(self._USER_LAYER_NAME)
        if slot is None:
            return PermissionPolicy()
        return slot.policy.model_copy(deep=True)

    @property
    def _user_policy(self) -> PermissionPolicy:
        """Live user-layer policy slot. Internal use; mutation is in-place.

        Created on first access if the user config didn't carry a
        `permissions` block, so callers can mutate `default_decision` /
        `rules` without preloading config. Mutating `default_decision`
        through this handle also flags the user layer as having an explicit
        default so the merged policy honours it at evaluation time.
        """
        with self._policy_lock:
            slot = self._layer_settings.setdefault(self._USER_LAYER_NAME, PermissionSettings())
            self._explicit_defaults.add(self._USER_LAYER_NAME)
            return slot.policy

    @property
    def license_policy(self) -> PermissionPolicy:
        """License-imposed policy fragment as set via `set_license_policy`."""
        with self._policy_lock:
            return self._license_policy.model_copy(deep=True)

    def set_license_policy(self, policy: PermissionPolicy) -> None:
        """Replace the license-imposed policy fragment.

        Whatever loads license files (a future `LicenseManager`) calls this
        with the parsed policy. Rules are stamped with `granted_by =
        "license"` if the caller did not already tag them; this keeps the
        audit log honest about origin without forcing license loaders to
        repeat themselves.

        License rules are held in memory only and are never persisted into
        user config, so a user editing `griptape_nodes_config.json` cannot
        edit a license-imposed `deny` out of existence.
        """
        stamped = policy.model_copy(deep=True)
        for rule in stamped.rules:
            if not rule.granted_by:
                rule.granted_by = "license"
        with self._policy_lock:
            self._license_policy = stamped
        # Audit cache stays valid; only the rule set changed.

    def clear_license_policy(self) -> None:
        """Drop all license-imposed rules. Used by license revocation paths."""
        with self._policy_lock:
            self._license_policy = PermissionPolicy(default_decision=Decision.ALLOW)

    def reload(self) -> None:
        """Re-read settings + policy from `ConfigManager`."""
        self._reload_settings()

    def evaluate(
        self,
        request: RequestPayload,
        *,
        principal: Principal | None = None,
        macro_context: dict[str, str] | None = None,
        context: ResultContext | None = None,
    ) -> EvaluationResult:
        """Evaluate the active policy against `request`. Used by the hook and tests."""
        actor = principal if principal is not None else self._infer_principal(context=context)
        request_fields_dict = _request_fields(request)
        facts = self._facts.build_fact_tree(request)
        macros = macro_context if macro_context is not None else self._macro_context()
        # License rules win by being evaluated first; config layers follow in
        # priority order. Things outside any explicit rule fall through to the
        # merged default decision.
        merged = self._build_merged_policy()
        result = evaluate_policy(
            merged,
            principal=actor,
            request_type_name=type(request).__name__,
            request_fields=request_fields_dict,
            facts=facts,
            macro_context=macros,
        )
        self._record_decision(request, actor, result)
        return result

    def list_recent_decisions(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._audit_lock:
            entries = list(self._audit)
        if limit is None:
            return entries
        # `entries[-0:]` is the whole list and a negative limit slices from the
        # front, both of which would over-share an audit tail, so treat any
        # non-positive limit as "no entries".
        if limit <= 0:
            return []
        return entries[-limit:]

    # ------------------------------------------------------------------ request handlers

    def on_get_effective_policy_request(self, _: GetEffectivePolicyRequest) -> ResultPayload:
        policy_dict = self._build_merged_policy().model_dump(mode="json")
        return GetEffectivePolicyResultSuccess(
            policy=policy_dict,
            result_details=(
                "Returned active permission policy (license rules first, then config layers "
                "in priority order: env, workspace, project, user, defaults)."
            ),
        )

    def on_list_permission_decisions_request(
        self,
        request: ListPermissionDecisionsRequest,
    ) -> ResultPayload:
        decisions = self.list_recent_decisions(request.limit)
        return ListPermissionDecisionsResultSuccess(
            decisions=decisions,
            result_details=f"Returned {len(decisions)} recent permission decision(s).",
        )

    def on_grant_permission_rule_request(self, request: GrantPermissionRuleRequest) -> ResultPayload:
        try:
            rule = PermissionRule.model_validate(request.rule)
        except ValidationError as e:
            return GrantPermissionRuleResultFailure(
                exception=e,
                result_details=f"Attempted to grant permission rule. Failed because rule is invalid: {e}",
            )
        # User-authored rule. Stamp `granted_by` if absent so audit entries
        # round-trip with provenance even after a config reload. License rules
        # use set_license_policy(), which is not exposed as a request type by
        # design; project / workspace / env / defaults rules are read-only at
        # runtime and edited by hand in their respective config files.
        if not rule.granted_by:
            rule = rule.model_copy(update={"granted_by": self._USER_LAYER_NAME})
        with self._policy_lock:
            slot = self._layer_settings.setdefault(self._USER_LAYER_NAME, PermissionSettings())
            slot.policy.rules.append(rule)
        # Persist outside the lock; set_config_value broadcasts ConfigChanged
        # synchronously, and our listener re-acquires _policy_lock.
        if not self._persist_policy():
            return GrantPermissionRuleResultFailure(
                result_details=(
                    f"Attempted to grant permission rule '{rule.id}'. Failed because the rule could "
                    "not be persisted to the user config, so it is not active. Check the engine log "
                    "for the underlying write error."
                )
            )
        return GrantPermissionRuleResultSuccess(
            rule_id=rule.id,
            result_details=f"Granted permission rule '{rule.id}'.",
        )

    def on_revoke_permission_rule_request(self, request: RevokePermissionRuleRequest) -> ResultPayload:
        # Revoke targets the user layer only. Rules from project, workspace,
        # env, and defaults layers are read-only at runtime and edited in their
        # config files; license-imposed rules come and go via set_license_policy
        # / clear_license_policy on the LicenseManager side.
        with self._policy_lock:
            slot = self._layer_settings.get(self._USER_LAYER_NAME)
            if slot is None:
                removed = 0
            else:
                before = len(slot.policy.rules)
                slot.policy.rules = [r for r in slot.policy.rules if r.id != request.rule_id]
                removed = before - len(slot.policy.rules)
        if not removed:
            return RevokePermissionRuleResultFailure(
                result_details=(
                    f"Attempted to revoke permission rule '{request.rule_id}'. Failed because no "
                    "user-layer rule with that id exists. Rules from project, workspace, env, "
                    "and defaults layers, plus license-imposed rules, are read-only at runtime."
                )
            )
        if not self._persist_policy():
            return RevokePermissionRuleResultFailure(
                result_details=(
                    f"Attempted to revoke permission rule '{request.rule_id}'. Failed because the "
                    "change could not be persisted to the user config, so the rule is still active. "
                    "Check the engine log for the underlying write error."
                )
            )
        return RevokePermissionRuleResultSuccess(
            rule_id=request.rule_id,
            result_details=f"Revoked permission rule '{request.rule_id}'.",
        )

    # ------------------------------------------------------------------ event listeners

    def _on_pre_dispatch(self, request: RequestPayload, context: ResultContext) -> ResultPayload | None:
        # The manager's own request types are exempt: denying GetEffectivePolicy
        # would be an unhelpful loop, and the grant/revoke path is itself the
        # tool used to repair a too-restrictive policy.
        if type(request).__name__ in PERMISSION_OWN_REQUEST_TYPES:
            return None
        if not self._enabled:
            return None
        principal = self._infer_principal(context=context)
        result = self.evaluate(request, principal=principal, context=context)
        if result.decision is Decision.ALLOW:
            return None
        if result.decision is Decision.PROMPT:
            mode = "prompt-not-implemented" if self._consent_prompts_enabled else "prompt-disabled"
            return _build_failure_for_request(request, _denied_message(request, result, mode))
        return _build_failure_for_request(request, _denied_message(request, result, "deny"))

    def _on_config_changed(self, event: ConfigChanged) -> None:
        if event.key != "permissions" and not event.key.startswith("permissions."):
            self._facts.invalidate(FactInvalidator.ON_CONFIG_CHANGED)
            return
        self._reload_settings()
        self._facts.invalidate(FactInvalidator.ON_CONFIG_CHANGED)

    def _on_library_loaded(self, _: LibraryLoadedNotification) -> None:
        self._facts.invalidate(FactInvalidator.ON_LIBRARY_LOADED)

    # ------------------------------------------------------------------ helpers

    def _reload_settings(self) -> None:
        cm = self._config_manager
        layer_settings: dict[str, PermissionSettings] = {}
        explicit_defaults: set[str] = set()
        enabled: bool = True
        consent_prompts_enabled: bool = True
        audit_max: int = 1000
        enabled_set = consent_set = audit_set = False

        for layer_name, attr in self._LAYER_ATTRS:
            layer = getattr(cm, attr, None)
            if not isinstance(layer, dict):
                continue
            block = layer.get("permissions")
            if not isinstance(block, dict):
                continue
            try:
                settings = PermissionSettings.model_validate(block)
            except ValidationError:
                logger.exception("Permission settings in '%s' layer failed validation; skipping.", layer_name)
                continue

            # Stamp `granted_by` on rules that didn't carry one so audit entries
            # attribute decisions back to the layer's config file. Round-trip
            # the policy with the stamped rules so subsequent reads see them.
            stamped_rules = [
                rule if rule.granted_by else rule.model_copy(update={"granted_by": layer_name})
                for rule in settings.policy.rules
            ]
            settings.policy = PermissionPolicy(
                rules=stamped_rules,
                default_decision=settings.policy.default_decision,
            )
            layer_settings[layer_name] = settings

            # Highest-priority layer that explicitly set a scalar wins. Lower
            # layers don't override a value already chosen by a higher layer.
            # Presence is checked against the raw block so the schema default
            # (e.g. enabled=True) is treated as "unset" rather than an override.
            if not enabled_set and "enabled" in block:
                enabled, enabled_set = settings.enabled, True
            if not consent_set and "consent_prompts_enabled" in block:
                consent_prompts_enabled, consent_set = settings.consent_prompts_enabled, True
            if not audit_set and "audit_log_max_entries" in block:
                audit_max, audit_set = max(1, settings.audit_log_max_entries), True
            policy_block = block.get("policy")
            if isinstance(policy_block, dict) and "default_decision" in policy_block:
                explicit_defaults.add(layer_name)

        with self._policy_lock:
            self._layer_settings = layer_settings
            self._explicit_defaults = explicit_defaults
        self._enabled = enabled
        self._consent_prompts_enabled = consent_prompts_enabled
        with self._audit_lock:
            if audit_max != self._audit.maxlen:
                self._audit = deque(self._audit, maxlen=audit_max)
            self._audit_max_entries = audit_max

    def _build_merged_policy(self) -> PermissionPolicy:
        """Assemble the active policy: license rules + per-layer rules + default.

        License rules go first so a license-imposed deny wins over a config
        allow. Config layers concatenate in priority order so first-match-wins
        gives "more-specific layer's rule fires before less-specific layer's
        rule". The default decision is whichever layer's
        `policy.default_decision` was explicitly set first; falls back to
        ALLOW so an unconfigured engine behaves as it did before this manager
        existed.
        """
        with self._policy_lock:
            rules: list[PermissionRule] = list(self._license_policy.rules)
            default_decision: Decision | None = None
            for layer_name, _ in self._LAYER_ATTRS:
                slot = self._layer_settings.get(layer_name)
                if slot is None:
                    continue
                rules.extend(slot.policy.rules)
                if default_decision is None and layer_name in self._explicit_defaults:
                    default_decision = slot.policy.default_decision
        return PermissionPolicy(
            rules=rules,
            default_decision=default_decision if default_decision is not None else Decision.ALLOW,
        )

    def _persist_policy(self) -> bool:
        # Only the user-layer settings are persisted. Project / workspace / env
        # / defaults layers are owned by their own config files; license rules
        # live in memory only so a user editing `griptape_nodes_config.json`
        # cannot remove a license-imposed deny by hand.
        with self._policy_lock:
            slot = self._layer_settings.get(self._USER_LAYER_NAME)
            rules = list(slot.policy.rules) if slot is not None else []
            default_explicit = slot is not None and self._USER_LAYER_NAME in self._explicit_defaults
            default_decision = slot.policy.default_decision if slot is not None else PermissionPolicy().default_decision
        expected_ids = [rule.id for rule in rules]
        rule_payload = [rule.model_dump(mode="json") for rule in rules]
        policy_payload: dict[str, Any] = {"rules": rule_payload}
        # Only carry `default_decision` when the user layer actually set one.
        # `set_config_value` merges this delta into the user config file, and
        # `merge_dicts` replaces the `rules` list while preserving every other
        # key the user already set. Dumping a fully-populated `PermissionSettings`
        # instead would write schema defaults (`enabled`,
        # `consent_prompts_enabled`, `audit_log_max_entries`, and a defaulted
        # `policy.default_decision`) that `_reload_settings` would then treat as
        # explicit operator intent, e.g. promoting a defaulted `allow` over a
        # lower layer's explicit `deny`.
        if default_explicit:
            policy_payload["default_decision"] = default_decision.value
        self._config_manager.set_config_value("permissions", {"policy": policy_payload})
        # set_config_value reloads _layer_settings from disk synchronously via the
        # ConfigChanged broadcast, but _write_user_config_delta swallows disk
        # errors (logs and returns). Compare the reloaded user-layer rule ids
        # against what we intended to persist so a silently-dropped write is
        # reported as failure instead of a false success that leaves the operator
        # believing a rule is active.
        with self._policy_lock:
            reloaded = self._layer_settings.get(self._USER_LAYER_NAME)
            reloaded_ids = [rule.id for rule in reloaded.policy.rules] if reloaded is not None else []
        return reloaded_ids == expected_ids

    def _infer_principal(self, context: ResultContext | None) -> Principal:
        with self._node_stack_lock:
            top = self._node_stack[-1] if self._node_stack else None
        if top is not None:
            return Principal(
                kind=PrincipalKind.NODE,
                library=top.get("library"),
                node_type=top.get("node_type"),
                node_name=top.get("node_name"),
            )
        topic = (context or {}).get("response_topic") if context else None
        if topic:
            return Principal(kind=PrincipalKind.CLIENT, topic=str(topic))
        return Principal(kind=PrincipalKind.ENGINE)

    def push_principal(self, *, library: str | None, node_type: str | None, node_name: str | None) -> None:
        """Install a NODE principal on the stack.

        Callers (NodeManager / NodeExecutor / tests) bracket node execution with
        push/pop. This is the single entry point for principal tracking; nothing
        listens for execution events directly because the engine does not
        currently broadcast them through the AppPayload bus.
        """
        with self._node_stack_lock:
            self._node_stack.append({"library": library, "node_type": node_type, "node_name": node_name})
        self._facts.invalidate(FactInvalidator.ON_NODE_EXECUTION_BOUNDARY)

    def pop_principal(self) -> None:
        """Undo `push_principal`."""
        with self._node_stack_lock:
            if self._node_stack:
                self._node_stack.pop()
        self._facts.invalidate(FactInvalidator.ON_NODE_EXECUTION_BOUNDARY)

    def _lookup_node_identity(self, node_name: str) -> dict[str, str | None]:
        """Resolve `(library, node_type)` for a live node by name.

        Reserved for the eventual NodeManager integration that brackets node
        execution with `push_principal`. Not currently called inside the
        manager but kept here so the integration is a one-line wiring change.
        """
        # Lazy import to avoid bootstrap-time circular imports (NodeManager's
        # transitive imports include ConfigManager / Settings, which is the same
        # graph this manager participates in via GriptapeNodes).
        from griptape_nodes.exe_types.node_types import BaseNode
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        try:
            object_manager = GriptapeNodes.ObjectManager()
            node = object_manager.attempt_get_object_by_name_as_type(node_name, BaseNode)
        except Exception:
            node = None
        if node is None:
            return {"library": None, "node_type": None, "node_name": node_name}
        metadata = getattr(node, "metadata", {}) or {}
        return {
            "library": metadata.get("library"),
            "node_type": metadata.get("node_type"),
            "node_name": node_name,
        }

    def _macro_context(self) -> dict[str, str]:
        config = self._config_manager
        macros: dict[str, str] = {}
        try:
            workspace = str(config.workspace_path)
        except Exception:
            workspace = ""
        if workspace:
            macros["workspace"] = workspace
        static_dir = config.get_config_value("static_files_directory")
        if isinstance(static_dir, str) and static_dir:
            macros["static_files_directory"] = static_dir
        return macros

    def _record_decision(
        self,
        request: RequestPayload,
        principal: Principal,
        result: EvaluationResult,
    ) -> None:
        rule_id = result.matched_rule.id if result.matched_rule else None
        inspected_values = {key: _summarise(value) for key, value in result.inspected_values.items()}
        entry = {
            "rule_id": rule_id,
            "decision": result.decision.value,
            "principal_kind": principal.kind.value,
            "principal_label": principal.label(),
            "action_request_type": type(request).__name__,
            "resource_summary": _resource_summary(request),
            "inspected_paths": list(result.inspected_paths),
            "inspected_values": inspected_values,
            "reason": result.reason,
        }
        with self._audit_lock:
            self._audit.append(entry)
        try:
            self._event_manager.broadcast_app_event(
                PermissionDecisionEvent(
                    rule_id=rule_id,
                    decision=result.decision.value,
                    principal_kind=principal.kind.value,
                    principal_label=principal.label(),
                    action_request_type=type(request).__name__,
                    resource_summary=entry["resource_summary"],
                    inspected_paths=list(result.inspected_paths),
                    inspected_values=dict(inspected_values),
                    reason=result.reason,
                )
            )
        except Exception:
            # Never let an event-broadcast failure perturb the dispatcher.
            logger.exception("Failed to broadcast PermissionDecisionEvent.")


# ---------------------------------------------------------------------- module-level helpers


def _request_fields(request: RequestPayload) -> dict[str, Any]:
    """Convert a request payload to a dict for matcher lookups."""
    if is_dataclass(request) and not isinstance(request, type):
        try:
            return dataclasses.asdict(request)
        except (TypeError, ValueError):
            pass
    out: dict[str, Any] = {}
    if hasattr(request, "__dict__"):
        out.update({k: v for k, v in vars(request).items() if not k.startswith("_")})
    return out


def _resource_summary(request: RequestPayload) -> dict[str, Any]:
    """Cheap, JSON-safe summary of request fields for audit/event payloads.

    Trims long collections and stringifies non-primitive values so the audit
    ring buffer stays small and serialisable.
    """
    summary: dict[str, Any] = {}
    if is_dataclass(request) and not isinstance(request, type):
        for field_def in fields(request):
            if field_def.metadata.get("omit_from_result"):
                continue
            value = getattr(request, field_def.name, None)
            summary[field_def.name] = _summarise(value)
    else:
        for key, value in vars(request).items():
            if key.startswith("_"):
                continue
            summary[key] = _summarise(value)
    return summary


_SUMMARY_PRIMITIVES = (str, int, float, bool, type(None))
_SUMMARY_MAX_STR = 256
_SUMMARY_MAX_LIST = 8
_SUMMARY_MAX_DEPTH = 6


def _summarise(value: Any, depth: int = 0) -> Any:
    if isinstance(value, _SUMMARY_PRIMITIVES):
        if isinstance(value, str) and len(value) > _SUMMARY_MAX_STR:
            return value[:_SUMMARY_MAX_STR] + "..."
        return value
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    # Bound recursion so a deeply nested or self-referential payload can't raise
    # RecursionError here and turn an audit record into a denied request. Past
    # the depth bound, fall through to the repr summary below.
    within_depth = depth < _SUMMARY_MAX_DEPTH
    if within_depth and isinstance(value, dict):
        return {k: _summarise(v, depth + 1) for k, v in list(value.items())[:_SUMMARY_MAX_LIST]}
    if within_depth and isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)[:_SUMMARY_MAX_LIST]
        return [_summarise(item, depth + 1) for item in items]
    return repr(value)[:_SUMMARY_MAX_STR]


def _denied_message(request: RequestPayload, result: EvaluationResult, mode: str) -> str:
    rule_label = f"rule '{result.matched_rule.id}'" if result.matched_rule else "default policy"
    qualifier = f"{mode}: {result.reason}" if result.reason else mode
    details = _format_inspected_values(result.inspected_values)
    suffix = f" Inspected: {details}" if details else ""
    # Bracket-free format: the engine's RichHandler runs with markup=True, and
    # `[deny]` / `[resource.file_path=...]` would be parsed as Rich tags and
    # silently elided in the rendered log line. Parens + an `Inspected:`
    # prefix render the same in plain text and survive Rich markup unchanged.
    return (
        f"Attempted to dispatch {type(request).__name__}. "
        f"Failed because permission was denied by {rule_label} ({qualifier}).{suffix}"
    )


# Principal/action axes are tautological in the denial message: the request
# type is already named, and the principal axis is rarely the surprising
# reason a request was blocked. Resource and context fields carry the
# request- and environment-specific values the user usually needs to debug
# "why was this blocked".
_DENIAL_MESSAGE_AXES: tuple[str, ...] = ("resource.", "context.")


def _format_inspected_values(inspected_values: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key, value in inspected_values.items():
        if not key.startswith(_DENIAL_MESSAGE_AXES):
            continue
        parts.append(f"{key}={_summarise(value)}")
    return ", ".join(parts)


def _build_failure_for_request(request: RequestPayload, message: str) -> ResultPayload:
    """Synthesise a failure result of the type the request's manager would have returned.

    Resolves the response type from the corresponding `*ResultFailure` naming
    convention. Falls back to `PermissionDeniedResult` when no companion class
    exists or when a required field cannot be defaulted.
    """
    candidate = _find_failure_companion(type(request))
    if candidate is not None:
        instance = _instantiate_failure(candidate, message)
        if instance is not None:
            return instance
    return PermissionDeniedResult(result_details=message)


def _find_failure_companion(request_class: type[Payload]) -> type[ResultPayloadFailure] | None:
    """Find `<Foo>ResultFailure` for `<Foo>Request` in the same module."""
    name = request_class.__name__
    if not name.endswith("Request"):
        return None
    target_name = name.removesuffix("Request") + "ResultFailure"
    module = __import__(request_class.__module__, fromlist=[target_name])
    candidate = getattr(module, target_name, None)
    if candidate is None or not isinstance(candidate, type):
        return None
    if not issubclass(candidate, ResultPayloadFailure):
        return None
    if issubclass(candidate, ResultPayloadSuccess):
        return None
    return candidate


def _instantiate_failure(failure_class: type[ResultPayloadFailure], message: str) -> ResultPayloadFailure | None:
    """Best-effort construct a failure with sensible defaults for required fields."""
    kwargs: dict[str, Any] = {"result_details": message}
    if is_dataclass(failure_class):
        for field_def in fields(failure_class):
            if field_def.name in kwargs:
                continue
            if field_def.default is not dataclasses.MISSING:
                continue
            if field_def.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                continue
            default = _default_for_failure_field(field_def.name)
            if default is _UNSET:
                return None
            kwargs[field_def.name] = default
    try:
        return failure_class(**kwargs)
    except TypeError:
        return None


_UNSET: Any = object()


def _default_for_failure_field(name: str) -> Any:
    """Provide sensible defaults for a small set of well-known required fields.

    Anything outside this list returns `_UNSET`, which causes the dispatcher to
    fall back to `PermissionDeniedResult` rather than guess.
    """
    if name == "failure_reason":
        from griptape_nodes.retained_mode.events.os_events import FileIOFailureReason

        return FileIOFailureReason.PERMISSION_DENIED
    return _UNSET

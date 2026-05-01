"""Engine-provided built-in permissions and marker mappings.

Libraries reference these names from `requires_permission` and
`RequiredPermissions*.names` without having to declare them in their own catalog.
Libraries may NOT shadow a built-in name in their own
`PermissionCatalogLibraryProperty.permissions` -- shadowing is rejected at load time.

`BUILTIN_MARKER_MAPPING` is the default mapping from capability-marker discriminator
strings to built-in permission names. Libraries can overlay entries on this dict via
`PermissionCatalogLibraryProperty.marker_mapping` to route a marker to a
library-specific permission.

Name constants below are the canonical references; consumers should import the
constants rather than the raw string literals.
"""

from __future__ import annotations

from griptape_nodes.node_library.library_properties import PermissionDeclaration

# ---------- Built-in permission names ----------

RUN_ARBITRARY_PYTHON = "run_arbitrary_python"
ACCESS_ENGINE = "access_engine"
USE_PROXY_MODEL = "use_proxy_model"


# ---------- Marker discriminator names ----------
# These match the `type: Literal["..."]` discriminator strings on the marker property
# classes in library_properties.py (ExecuteArbitraryCodeNodeProperty,
# EngineControlNodeProperty, ProxyModelNodeProperty). They must stay in sync.

MARKER_EXECUTE_ARBITRARY_CODE = "execute_arbitrary_code"
MARKER_ENGINE_CONTROL = "engine_control"
MARKER_PROXY_MODEL = "proxy_model"


# Cedar policies for built-in permissions are intentionally empty for now. They
# will be specified alongside the real Cedar evaluator; the engine currently
# grants every permission regardless of policy content. Authors who want
# library-specific restrictions on these built-ins should declare a separate
# permission in their own catalog rather than shadowing a built-in name.
BUILTIN_PERMISSIONS: dict[str, PermissionDeclaration] = {
    RUN_ARBITRARY_PYTHON: PermissionDeclaration(
        description="Execute arbitrary Python code inside a node.",
    ),
    ACCESS_ENGINE: PermissionDeclaration(
        description="Use direct engine access (EngineNode).",
    ),
    USE_PROXY_MODEL: PermissionDeclaration(
        description="Call a Griptape-hosted model proxy endpoint.",
    ),
}

BUILTIN_MARKER_MAPPING: dict[str, str] = {
    MARKER_EXECUTE_ARBITRARY_CODE: RUN_ARBITRARY_PYTHON,
    MARKER_ENGINE_CONTROL: ACCESS_ENGINE,
    MARKER_PROXY_MODEL: USE_PROXY_MODEL,
}

RECOGNIZED_MARKER_DISCRIMINATORS: frozenset[str] = frozenset(BUILTIN_MARKER_MAPPING.keys())

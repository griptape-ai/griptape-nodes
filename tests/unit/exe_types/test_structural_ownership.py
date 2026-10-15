"""Structural workflow state changes only through the change records in `exe_types/changes.py`.

Undo reverses an edit by reversing its records, so a structural write that skips them cannot be
undone, and nothing else would notice. These tests read the engine's source and fail on a write to
structural state outside the method that owns it, or on a call to an owning method from anywhere
but a record or another owner. To change structure from new code, make the change with
`journal.apply(...)` and one of the records, or add a record.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import griptape_nodes

SOURCE = Path(griptape_nodes.__file__).parent
RECORDS = "exe_types/changes.py"

# Each piece of structural state, by attribute name, and the only methods that may write it.
# `__init__` creates the state empty, so it is allowed everywhere.
OWNED_STATE: dict[str, set[str]] = {
    "_name_to_objects": {
        "ObjectManager.add_object_by_name",
        "ObjectManager.del_obj_by_name",
        "ObjectManager.rename_object",
    },
    "_name_to_parent_flow_name": {
        "NodeManager.register_node",
        "NodeManager.unregister_node",
        "NodeManager.move_node_to_flow",
        "NodeManager.handle_node_rename",
        "NodeManager.handle_flow_rename",
    },
    "_name_to_parent_name": {
        "FlowManager.register_flow",
        "FlowManager.unregister_flow",
        "FlowManager.set_flow_parent",
        "FlowManager.handle_flow_rename",
    },
    "_flow_to_referenced_workflow_name": {"FlowManager.register_flow", "FlowManager.unregister_flow"},
    "connections": {"Connections.link", "Connections.unlink", "FlowManager.reset_global_execution_state"},
    "outgoing_index": {
        "Connections.link",
        "Connections.unlink",
        "NodeManager.handle_node_rename",
        "FlowManager.reset_global_execution_state",
    },
    "incoming_index": {
        "Connections.link",
        "Connections.unlink",
        "NodeManager.handle_node_rename",
        "FlowManager.reset_global_execution_state",
    },
    "nodes": {
        "ControlFlow.add_node",
        "ControlFlow.remove_node",
        "BaseNodeGroup.add_member",
        "BaseNodeGroup.remove_member",
        "BaseNodeGroup.handle_child_node_rename",
        "ASTContainer.add_node",  # Code generation's own tree, not the workflow.
    },
    "parent_group": {"BaseNodeGroup.add_member", "BaseNodeGroup.remove_member"},
    "_parent_group": {"BaseNode.parent_group"},
    "lock": {"NodeManager.set_lock"},
}

# The owning methods, and the only places that may call them: the records, and the owners they build on.
OWNER_CALLERS: dict[str, set[str]] = {
    "register_node": {RECORDS},
    "unregister_node": {RECORDS},
    "move_node_to_flow": {RECORDS},
    "register_flow": {RECORDS},
    "unregister_flow": {RECORDS},
    "set_flow_parent": {RECORDS},
    "rename_object": {RECORDS},
    "rename_parameter": {RECORDS},
    "add_member": {RECORDS},
    "remove_member": {RECORDS},
    "set_lock": {RECORDS},
    "add_object_by_name": {"FlowManager.register_flow", "NodeManager.register_node"},
    "del_obj_by_name": {"FlowManager.unregister_flow", "NodeManager.unregister_node"},
    "handle_node_rename": {"ObjectManager.rename_object"},
    "handle_flow_rename": {"ObjectManager.rename_object", "FlowManager.handle_flow_rename"},
    "handle_child_node_rename": {"NodeManager.handle_node_rename"},
}

# Owners whose names are common elsewhere (graphs, paths), told apart by what they are called on.
OWNER_CALLERS_ON: dict[str, tuple[str, set[str]]] = {
    "add_node": (
        "flow",
        {"NodeManager.register_node", "NodeManager.move_node_to_flow", "NodeManager.handle_node_rename"},
    ),
    "remove_node": (
        "flow",
        {"NodeManager.unregister_node", "NodeManager.move_node_to_flow", "NodeManager.handle_node_rename"},
    ),
    "link": ("connections", {RECORDS}),
    "unlink": ("connections", {RECORDS}),
}

_MUTATORS = {
    "pop",
    "popitem",
    "clear",
    "update",
    "setdefault",
    "append",
    "extend",
    "insert",
    "remove",
    "sort",
    "reverse",
}


@dataclass(frozen=True)
class _Site:
    module: str
    line: int
    function: str
    name: str

    def __str__(self) -> str:
        return f"{self.module}:{self.line} in {self.function or '<module>'} ({self.name})"


def test_structural_state_is_written_only_by_its_owners() -> None:
    """A write outside the owner skips the record, so undo cannot reverse it."""
    writes = [site for site in _scan() if isinstance(site, _Write)]
    strays = [
        site
        for site in writes
        if not site.function.endswith(".__init__") and site.function not in OWNED_STATE[site.name]
    ]

    assert not strays, "Structural state written outside its owner:\n" + "\n".join(map(str, strays))


def test_owning_methods_are_called_only_by_records_and_owners() -> None:
    """An owner called directly makes the change without recording it."""
    strays = []
    for site in _scan():
        if not isinstance(site, _Call):
            continue
        allowed = OWNER_CALLERS[site.name] if site.name in OWNER_CALLERS else OWNER_CALLERS_ON[site.name][1]
        if site.module not in allowed and site.function not in allowed:
            strays.append(site)

    assert not strays, "Owning method called outside a record:\n" + "\n".join(map(str, strays))


def test_every_listed_owner_is_found() -> None:
    """Fails when an owner is renamed or the scan stops seeing it, so the tests above never pass vacuously."""
    seen = {(site.name, site.function) for site in _scan()} | {(site.name, site.module) for site in _scan()}
    listed = {(name, owner) for name, owners in OWNED_STATE.items() for owner in owners}
    listed |= {(name, caller) for name, callers in OWNER_CALLERS.items() for caller in callers}
    listed |= {(name, caller) for name, (_, callers) in OWNER_CALLERS_ON.items() for caller in callers}

    assert listed <= seen, f"Listed but never seen: {sorted(listed - seen)}"


class _Write(_Site):
    pass


class _Call(_Site):
    pass


_cache: list[_Site] = []


def _scan() -> list[_Site]:
    if not _cache:
        for path in sorted(SOURCE.rglob("*.py")):
            module = path.relative_to(SOURCE).as_posix()
            _cache.extend(_Visitor(module).sites_in(ast.parse(path.read_text(encoding="utf-8"))))
    return _cache


class _Visitor(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self._module = module
        self._scope: list[str] = []
        self._sites: list[_Site] = []

    def sites_in(self, tree: ast.AST) -> list[_Site]:
        self.visit(tree)
        return self._sites

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scoped(node.name, node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scoped(node.name, node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scoped(node.name, node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._target(target, node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._target(node.target, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._target(node.target, node)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._target(target, node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr in _MUTATORS:
                self._written(_attributes_in(func.value), node)
            if func.attr in OWNER_CALLERS or (
                func.attr in OWNER_CALLERS_ON and OWNER_CALLERS_ON[func.attr][0] in _last_name(func.value).lower()
            ):
                self._add(_Call, node, func.attr)
        self.generic_visit(node)

    def _scoped(self, name: str, node: ast.AST) -> None:
        self._scope.append(name)
        self.generic_visit(node)
        self._scope.pop()

    def _target(self, target: ast.expr, node: ast.stmt) -> None:
        if isinstance(target, ast.Tuple | ast.List):
            for element in target.elts:
                self._target(element, node)
        elif isinstance(target, ast.Attribute):
            self._written([target.attr], node)
        elif isinstance(target, ast.Subscript):
            self._written(_attributes_in(target), node)

    def _written(self, attributes: list[str], node: ast.AST) -> None:
        for attribute in attributes:
            if attribute in OWNED_STATE:
                self._add(_Write, node, attribute)
                return

    def _add(self, kind: type[_Site], node: ast.AST, name: str) -> None:
        # Methods are named Class.method; a function nested in a method counts as that method.
        function = ".".join(self._scope[:2])
        self._sites.append(kind(module=self._module, line=getattr(node, "lineno", 0), function=function, name=name))


def _attributes_in(node: ast.expr) -> list[str]:
    """The attribute names along an expression such as `self._connections.outgoing_index[a][b]`."""
    attributes = []
    while True:
        if isinstance(node, ast.Attribute):
            attributes.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        else:
            return attributes


def _last_name(node: ast.expr) -> str:
    """What a call is made on, by its nearest name: `flow` for `parent_flow`, `get_flow_by_name(...)`."""
    if isinstance(node, ast.Call):
        return _last_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""

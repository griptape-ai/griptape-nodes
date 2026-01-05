# Developing Nodes (Developer Onboarding)

This page is for developers who are **new to the Griptape Nodes ecosystem** and want to build custom nodes with confidence.

It’s a beginner-friendly “front door” to the deeper, exhaustive technical material in the Node Development Guide (`griptape-nodes-node-development-guide/node-development-guide-v3.md`).

## What you’ll build (mentally) before you write code

At a high level:

- A **Node** is a Python class that defines **parameters** (inputs/outputs/properties) and a `process()` method.
- A **Workflow (Flow)** is a graph of nodes connected by parameters.
- Parameters are both:
    - **UI elements** (what a user sees/edits/connects), and
    - **type-checked connection points** (what can connect to what).

### Choose the right base node type

- **`DataNode`**: use when your node processes data and doesn’t need to branch execution.
- **`ControlNode`**: use when your node needs explicit execution flow (control in/out).
- **`SuccessFailureNode`**: use when you want separate control-flow outputs for success vs failure.
- **Iterative loop nodes**: the engine’s loop primitives are built on `BaseIterativeStartNode` / `BaseIterativeEndNode`.

If you’re unsure, start with a `DataNode` and only graduate to `ControlNode`/loop nodes when you need it.

## How we recommend documenting node development in `griptape-nodes/docs`

To turn a deep guide into newcomer-friendly docs, the key is **progressive disclosure**:

- Start with a short “happy path” for first success.
- Add reference material only after the user has a working mental model.
- Keep advanced patterns in dedicated sections, and always link back to the deeper guide.

### Suggested docs section structure

If we expand this beyond a single page, the docs section under `docs/how_to/` could be organized like this:

- `how_to/developing_nodes.md` (this page): newcomer onboarding + common patterns
- `how_to/node_parameters.md`: parameters, types, traits, containers (reference + examples)
- `how_to/node_lifecycle_and_validation.md`: lifecycle callbacks, validation, connection rules
- `how_to/control_flow_and_async.md`: control flow, iterative nodes, async nodes
- `how_to/publishing_node_libraries.md`: packaging, dependencies, secrets, docs expectations

### How to add a new docs page

1. Add a markdown file under `docs/how_to/` (or a relevant subfolder).
1. Add the page to `mkdocs.yml` under the `nav:` section (usually under **How-To**).
1. Keep headings consistent and prefer short sections with code examples.

## Your first node (minimal example)

This is the smallest useful node you can build: read a string, transform it, emit a string.

```python
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode


class UppercaseText(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="text",
                type="str",
                input_types=["str"],
                tooltip="Input text",
            )
        )

        self.add_parameter(
            Parameter(
                name="uppercased",
                type="str",
                output_type="str",
                tooltip="Uppercased output",
            )
        )

    def process(self) -> None:
        text = self.get_parameter_value("text") or ""
        self.parameter_output_values["uppercased"] = text.upper()
```

## Parameters: the practical model

Every parameter can be used in three “modes”:

- **Input**: accepts a connection from another node
- **Output**: provides a connection to another node
- **Property**: user-configurable value in the node UI

### Use `Parameter*` helpers for common cases

The core engine ships parameter helper constructs under `griptape_nodes.exe_types.param_types.*` such as:

- `ParameterString`, `ParameterInt`, `ParameterFloat`, `ParameterBool`
- `ParameterJson`, `ParameterDict`, `ParameterRange`
- `ParameterImage`, `ParameterAudio`, `ParameterVideo`, `Parameter3D`
- `ParameterButton`

These helpers are useful because they:

- hard-set the intended `type` / `output_type` and common `ui_options`
- often support `accept_any=True` to convert values safely
- expose several UI options as Python properties for runtime updates

If you need a quick reference, see the **Parameter helper constructs** section in `node-development-guide-v3.md`.

### Containers: `ParameterList` and `ParameterDictionary`

- **`ParameterList`**: use when you want “many of the same thing” in a node UI.
    - Retrieval: `get_parameter_list_value()` flattens nested iterables.
    - Note: the current implementation drops falsey items (e.g. `0`, `False`). Preserve those by using `get_parameter_value()` and flattening manually.
- **`ParameterDictionary`**: use when you want ordered key/value entries in the UI.

### Traits: UI behaviors and validation

Traits are attached to parameters to add UI and behavior.

Common traits you’ll use:

- `Options(...)`: dropdowns (choices are stored in `ui_options` for serialization stability)
- `Slider(min_val, max_val)`: slider UI + range validation
- `FileSystemPicker(...)`: file/directory picking UI (with filters and workspace constraints)

## Validation, error handling, and user experience

For newcomers, a good default is:

- Use `validate_before_node_run()` for parameter validation
- Fail early with actionable messages (tell the user what to connect or set)
- If the node can fail but you want the workflow to continue, use `SuccessFailureNode` and route failure explicitly

## Secrets and configuration

When a node needs an API key or other secret:

- Register secrets in the library configuration (`griptape_nodes_library.json`)
- Read secrets via `GriptapeNodes.SecretsManager().get_secret("NAME")`

## Where to look for real examples

- **Standard library nodes**: `libraries/griptape_nodes_library/griptape_nodes_library/`
- **Engine internals** (advanced): `src/griptape_nodes/`

## Next steps

- Read the deeper technical guide: `griptape-nodes-node-development-guide/node-development-guide-v3.md`
- Browse a few nodes in the standard library and copy patterns that match your use case

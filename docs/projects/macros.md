# Macros

A macro is a template string that generates a file path by substituting named variables. Macros are used in situation templates and directory definitions.

Before diving into the full syntax, here are two examples that show what macros look like in practice:

```
Template:  {outputs}/{node_name?:_}{file_name_base}{_index?:03}.{file_extension}

With all variables:
  outputs="outputs", node_name="ImageGen", file_name_base="render", _index=2, file_extension="png"
  → outputs/ImageGen_render002.png

With optional variables omitted:
  outputs="outputs", file_name_base="render", file_extension="png"
  → outputs/render.png
```

`{outputs}` is a directory name that the project system supplies automatically. `{node_name?:_}` is optional — when present, its value is followed by `_`; when absent, the block disappears entirely. `{_index?:03}` is optional and zero-padded to three digits when present.

## Variable syntax reference

### Required variable

```
{variable_name}
```

The variable must be provided. If it is missing when the macro is resolved, resolution fails with an error.

### Optional variable

```
{variable_name?}
```

The `?` marks the variable as optional. If the variable is not provided, the `{}` block — and any format spec — is omitted entirely from the output. The rest of the macro continues normally.

### Separator format

```
{variable_name:separator}
```

Appends `separator` after the variable's value. Any text that is not a recognized keyword (see transformations below) and not a numeric padding is treated as a separator.

This is most useful for building path prefixes that disappear cleanly when the variable is absent. For example, `{node_name?:_}` adds `node_name_` before a filename when the node name is known, but produces nothing at all when it isn't:

```
{node_name?:_}{file_name_base}

  node_name="ImageGen", file_name_base="render"  →  ImageGen_render
  node_name not provided,  file_name_base="render"  →  render
```

Path separators work the same way — `{sub_dirs?:/}` adds a subdirectory prefix only when sub-directories are specified:

```
{outputs}/{sub_dirs?:/}{file_name_base}.{file_extension}

  sub_dirs="lighting/pass_a", file_name_base="render", file_extension="exr"
  → outputs/lighting/pass_a/render.exr

  sub_dirs not provided, file_name_base="render", file_extension="exr"
  → outputs/render.exr
```

### Numeric padding

```
{variable_name:03}
```

Zero-pads the value to the specified width. The variable must hold an integer value.

```
{_index:03}   with _index = 5   → "005"
{_index:04}   with _index = 12  → "0012"
```

Used with `?` for auto-incrementing filenames: `{_index?:03}` is absent on the first save, then becomes `001`, `002`, and so on as needed.

### String transformations

```
{variable_name:lower}    → lowercase
{variable_name:upper}    → UPPERCASE
{variable_name:slug}     → slug-form (spaces to hyphens, safe chars only)
```

For example, if `workflow_name` is `"My Autumn Shoot"`:

```
{workflow_name:lower}  →  "my autumn shoot"
{workflow_name:slug}   →  "my-autumn-shoot"
```

### Default value

```
{variable_name|default_value}
```

If the variable is not provided, `default_value` is used instead.

```
{workflow_name|untitled}   → uses "untitled" if workflow_name is not provided
```

### Chaining format specs

Multiple format specs are separated by `:` and applied left to right. If a separator is used, it must come first:

```
{variable_name:_:lower}    → lowercase value with underscore appended
{variable_name:lower:slug} → lowercase, then slug
```

### Quoted separators

If your separator text matches a keyword like `lower` or `upper`, wrap it in single quotes to treat it as a literal separator:

```
{variable_name:'lower'}    → appends the text "lower" as a separator
```

## Resolution

When a macro is resolved, directory names and builtin variables are supplied automatically by the project system. You only need to provide the variables specific to your operation (like `file_name_base` and `file_extension`).

For example, resolving the `save_node_output` situation macro:

```
Template:   {outputs}/{sub_dirs?:/}{node_name?:_}{file_name_base}{_index?:03}.{file_extension}

Automatic:  outputs → resolved from the "outputs" directory definition → "outputs"
Provided:   node_name="StyleTransfer", file_name_base="portrait", _index=3, file_extension="png"
Result:     outputs/StyleTransfer_portrait003.png
```

Directory names (like `outputs`) are automatically resolved to their configured paths. See [Directories](directories.md).

Builtin variables (like `workflow_name`, `project_dir`) are also supplied automatically. See [Environment & Builtin Variables](environment.md).

## Reverse matching

The macro system can also work in reverse: given an actual path and a macro template, it can extract the values of the variables. This is used when the system needs to identify whether a file belongs to a known project directory and what metadata is encoded in its name.

For example:

```
Template:  {outputs}/{node_name?:_}{file_name_base}{_index?:03}.{file_extension}
Path:      outputs/StyleTransfer_portrait003.png
Extracted: outputs="outputs", node_name="StyleTransfer", file_name_base="portrait", _index=3, file_extension="png"
```

Numeric padding is reversed by parsing the number (`"003"` → integer `3`). Case transformations and slugification cannot be reliably reversed and return the value as-is.

## Image sequences (Nuke-style)

Macros accept Nuke-style sequence tokens for filenames that represent a range of per-frame image files. A sequence token is a placeholder for the *frame number*; it appears **outside** any `{...}` block and is written as either a run of hash characters or a printf specifier.

```
render.####.exr    # hash form: four `#` = four-digit zero-padded frame number
render.%04d.exr    # printf form: equivalent to ####
frame_#.png        # single `#` = any integer frame (no minimum digits on read)
frame_%d.png       # printf with no width = any integer frame
```

A template may contain **at most one** sequence token. Mixing two hash runs, two printf specifiers, or one of each is rejected at parse time.

### Where sequence tokens can appear

A sequence token may appear anywhere in the path — in the basename, the extension stem, or a directory component:

```
render.####.exr             # basename
sequence_####.exr           # anywhere in the basename
frames/####/beauty.exr      # directory component
{outputs}/shot/####.exr     # alongside regular variables
```

### Read and write behave differently (intentionally)

Sequence tokens represent a *set* of files on read but a *single file* on write. The semantics are asymmetric:

- **Write**: pad to the declared width, with overflow allowed. Frame 5 with `####` renders as `0005`. Frame 12345 with `####` renders as `12345` — the number isn't truncated.
- **Read**: the declared width is a **minimum**. `####` matches any integer with **at least four digits**, so it picks up `0001`, `0099`, `12345`, and so on. Files with fewer digits than the declared width (like `render.1.exr` against `####`) are ignored. A single `#` or `%d` effectively matches any frame number.

Negative frames are supported on both sides. The sign is extra to the padding: frame `-5` with `####` renders as `-0005`, not `-005`.

### Working with sequences in code

Parse a template the usual way. If the template contains a sequence token, wrap it in `SequenceTemplate` to access read/write operations:

```python
from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.macro_parser.sequence import (
    MissingFramePolicy,
    SequenceTemplate,
)

macro = ParsedMacro("{outputs}/render.####.exr")

# Calling .resolve() on a sequence macro preserves the sequence token as
# literal text — useful when handing the unexpanded pattern to a downstream
# tool (Nuke itself, ffmpeg, etc.) that performs its own per-frame expansion.
macro.resolve({"outputs": "/workspace/out"}, secrets_manager)
# → "/workspace/out/render.####.exr"

# Render a specific frame for writing.
seq_template = SequenceTemplate(macro)
seq_template.render_frame(5, {"outputs": "/workspace/out"}, secrets_manager)
# → "/workspace/out/render.0005.exr"

# Scan for files matching the pattern. The directory to scan is derived
# from the resolved template — all required variables must be supplied
# (the scan refuses to run when it doesn't know where to look).
sequence = seq_template.scan(
    variables={"outputs": "/workspace/out"},
    secrets_manager=secrets_manager,
    policy=MissingFramePolicy.ERROR,
)
sequence.frames        # sorted [(frame_int, Path), ...]
sequence.first         # lowest scanned frame
sequence.last          # highest scanned frame
sequence.missing       # set of frame numbers in [first, last] that aren't on disk
sequence.shadowed_files  # {frame: [non-winning paths, ...]} for duplicates
```

All filesystem access flows through the `ListDirectoryRequest` event, so
scan inherits the engine's path normalization, permission handling, and
long-path support automatically — no manual directory walking in caller code.

### Missing-frame policy

If a caller asks for a frame that isn't on disk, the `MissingFramePolicy` controls the behavior. Names mirror Nuke's `on_error` Read-node knob.

| Policy              | Behavior                                                                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `ERROR` *(default)* | Raise `MissingFrameError`.                                                                                                                  |
| `NEAREST`           | Return the path of the closest existing frame. Ties resolve toward the lower frame.                                                         |
| `BLACK`             | Return a `MissingFrameMarker(policy=BLACK, frame=N)` sentinel. The caller (e.g., a node-level renderer) synthesizes the actual black frame. |
| `CHECKERBOARD`      | Same as `BLACK`, but with the checkerboard policy on the marker.                                                                            |

Iterate the whole declared range via `sequence.iter_dense()`, which yields `(frame, Path | MissingFrameMarker)` for every frame in `[first, last]` with the policy applied consistently.

### Duplicate frames

If two files on disk resolve to the same frame number — for example `render.0001.exr` and `render.001.exr` both matching `render.####.exr` — the lexicographically-first filename keeps the slot and the others are recorded on `sequence.shadowed_files`. A warning is logged for each duplicate. This matches Nuke's observed behavior (scan-order wins, with lexicographic sort for cross-platform determinism).

### Not related to `{_index}`

`{_index}` is an auto-incrementing integer used for filename collision avoidance on write (the project system scans for the next free index). Sequence tokens (`####` / `%04d`) represent frame numbers supplied by the caller or extracted from disk. The two concepts share a regex-scanning primitive internally but serve different purposes — don't use one where you mean the other.

## Syntax errors

The macro parser reports syntax errors with a position number to help you find the problem:

- Unclosed brace: `{variable_name` (no closing `}`)
- Unmatched closing brace: `variable}name`
- Nested braces: `{outer{inner}}`
- Empty variable: `{}`
- Multiple sequence tokens: `v##_f####.exr` (only one `#` run or `%Nd` per template is allowed)

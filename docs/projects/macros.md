# Macros

A macro is a template string that generates a file path by substituting named variables. Macros are used in situation templates and directory definitions.

## Basic syntax

Variables are written inside curly braces:

```
{variable_name}
```

A macro can mix static text with any number of variables:

```
{outputs}/{workflow_name?:_}{file_name_base}{_index?:03}.{file_extension}
```

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

```
{node_name:_}       → "my_node_"
{sub_dirs:/}        → "renders/"
```

When combined with `?`, the entire block (value + separator) is omitted if the variable is absent:

```
{node_name?:_}{file_name_base}
```

- With `node_name = "render"`, `file_name_base = "frame"`: `render_frame`
- Without `node_name`, `file_name_base = "frame"`: `frame`

### Numeric padding

```
{variable_name:03}
```

Zero-pads the value to the specified width. The variable must hold an integer value.

```
{_index:03}   with _index = 5   → "005"
{_index:04}   with _index = 12  → "0012"
```

### String transformations

```
{variable_name:lower}    → lowercase
{variable_name:upper}    → UPPERCASE
{variable_name:slug}     → slug-form (spaces to hyphens, safe chars only)
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

When a macro is resolved, each variable is replaced with its value (after any format specs are applied) and the result is joined with the surrounding static text.

**Example:**

```
Template:   {outputs}/{node_name?:_}{file_name_base}{_index?:03}.{file_extension}
Variables:  outputs="outputs", node_name="my_node", file_name_base="render", _index=2, file_extension="png"
Result:     outputs/my_node_render002.png
```

**Example without optional variables:**

```
Template:   {outputs}/{node_name?:_}{file_name_base}{_index?:03}.{file_extension}
Variables:  outputs="outputs", file_name_base="render", file_extension="png"
Result:     outputs/render.png
```

Directory names (like `outputs`) are automatically resolved to their configured paths before the macro is resolved. You do not need to provide them as variables — they are supplied by the project system. See [Directories](directories.md).

Builtin variables (like `workflow_name`, `project_dir`) are also supplied automatically. See [Environment & Builtin Variables](environment.md).

## Reverse matching

The macro system can also work in reverse: given an actual path and a macro template, it can extract the values of the variables. This is used when the system needs to identify whether a file belongs to a known project directory and what metadata is encoded in its name.

For example:

```
Template:  {outputs}/{node_name?:_}{file_name_base}{_index?:03}.{file_extension}
Path:      outputs/my_node_render002.png
Extracted: outputs="outputs", node_name="my_node", file_name_base="render", _index=2, file_extension="png"
```

Numeric padding is reversed by parsing the number (`"002"` → integer `2`). Case transformations and slugification cannot be reliably reversed and return the value as-is.

## Syntax errors

The macro parser reports syntax errors with a position number to help you find the problem:

- Unclosed brace: `{variable_name` (no closing `}`)
- Unmatched closing brace: `variable}name`
- Nested braces: `{outer{inner}}`
- Empty variable: `{}`

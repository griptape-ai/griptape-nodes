# Sequences

Griptape Nodes can read directories of numbered files as **sequences** — for example, a render output like `render.0001.exr`, `render.0002.exr`, … `render.0100.exr`, but also dialogue takes (`take_##.wav`), text chunks (`chapter_###.md`), or anything else where a numeric key in the filename groups items into an ordered set. You point a sequence-aware node at a *pattern* (the filename with a placeholder for the number), and the engine finds the matching items on disk, handles gaps, and gives you back a list of entries with their integer numbers and zero-padded string forms.

This page explains the pattern syntax, the policies for handling missing items, and the conventions you should know before authoring a template.

## Pattern syntax

A sequence pattern looks like a filename with a token in place of the item number. Four token forms are supported:

| Token  | Width | Notes                                                         |
| ------ | ----- | ------------------------------------------------------------- |
| `####` | 4     | Each `#` is one digit. `##` = 2-digit, `####` = 4-digit, etc. |
| `%04d` | 4     | C-style printf. `%04d` = 4-digit zero-padded.                 |
| `@@@@` | 4     | Houdini/RV style. Same meaning as `####`.                     |
| `$F4`  | 4     | Houdini variable. Same meaning as `####`.                     |

All four are equivalent; pick whichever matches your pipeline conventions. We recommend `####` or `%04d` for new templates — they're the most widely understood across DCC tools.

A few examples:

```
render.####.exr             item 5 → render.0005.exr
render.%04d.png             item 12 → render.0012.png
take_##.wav                 item 7 → take_07.wav
```

The token always sits in the **filename**. Tokens inside directory components (e.g. `render/####/beauty.exr`) are not supported — keep the number in the filename portion only.

## Combining with macros

Sequence patterns work alongside the project's [macro language](macros.md). The variables get resolved first, then the resulting filename is interpreted as a sequence pattern:

```
{inputs}/shot_a/render.####.exr
```

If `{inputs}` resolves to `/workspace/inputs`, the engine scans `/workspace/inputs/shot_a/` for files matching `render.####.exr`. Macro variables inside `{...}` are completely separate from sequence tokens — they don't share syntax and they're resolved at different stages.

## Width matching is strict

The number of `#` characters (or the `%0Nd` width) declares the **exact** number of digits to match. If your pattern says `####`, the engine matches files with exactly 4 digits in the slot — `render.0001.exr` matches, but `render.001.exr` (3 digits) and `render.12345.exr` (5 digits) do not.

This matches what Nuke does. If your sequence has numbers that overflow the declared padding (e.g., a 4-digit pattern but real numbers go above 9999), use a wider pattern (`#####`) to capture them.

If a directory contains files with mixed padding widths — for example both `render.0001.png` and `render.001.png` — they'll be treated as **separate sequences**. The engine matches the one whose padding matches your declared template; the others are silently ignored.

## Missing-item policies

Real sequences often have gaps — a render that crashed on frame 47, a sparse export that only saved every other take, a chapter that's still unwritten. When you scan a sequence, you choose a **policy** for how those gaps are handled:

| Policy              | What you get                                                                                                                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ABORT`             | Fail fast. Raises `MissingItemError` (with the offending item number) on the first gap inside `[first, last]`. No Sequence is returned.                                                           |
| `SPLIT` *(default)* | One sequence per **contiguous run** of present items. A sequence with items 1–5, 8–12, 15 produces three separate sequences.                                                                      |
| `SKIP`              | One sequence containing only the present items. Gaps are absent from the output (but visible via the sequence's `missing_numbers` set).                                                           |
| `FILL_NEAREST`      | One sequence covering the full `[first, last]` range. Each missing item is filled with the path of the nearest **earlier** present item (or the nearest later one if no earlier neighbor exists). |

Pick `ABORT` when a gap should fail the workflow loudly (e.g. a render that crashed must not silently advance). Pick `SPLIT` when you want to *preserve* the gap structure (each contiguous run is meaningful on its own). Pick `SKIP` when you want a single sparse sequence, or `FILL_NEAREST` for a single dense sequence, regardless of what's actually on disk.

**Domain-specific gap rendering belongs to nodes, not the engine.** If you want a black-frame placeholder, a magenta/yellow checkerboard, a silent audio chunk, an empty text chunk, or anything else synthesized in place of a missing item, scan with `SKIP` and walk `missing_numbers` in your node — render whatever your domain calls for. The engine deliberately stops at "this number isn't on disk"; the node owns the rest.

## Subset clipping

Sequence-aware nodes accept optional `start` and `end` bounds. When supplied, the scan is clipped to that range:

- Items below `start` and above `end` are dropped from the output.
- The original disk range is still reported via `discovered_first` / `discovered_last`, so you can see what existed before the clip.
- Subset bounds outside the discovered range yield an empty result (Failure).

## What you get back

`Sequence` is a Pydantic model — read fields by attribute (`seq.first`, `seq.entries[0].number`). Nodes that operate on sequences should declare their input as `type="Sequence"`; the engine validates the connection by name.

Each `Sequence` carries:

- **`first`** / **`last`** — the active range (after subset clipping).
- **`discovered_first`** / **`discovered_last`** — what was actually on disk, ignoring any subset.
- **`padding`** — the declared zero-padding width (e.g. 4 for `####`).
- **`pattern`** — the canonical pattern (e.g. `render.####.exr`).
- **`directory`** — the directory the scan ran in.
- **`policy`** — which policy was applied.
- **`entries`** — one `SequenceEntry` per item in the active range. Each has:
    - `number` — the integer key (e.g. 5).
    - `padded_number` — the zero-padded form (e.g. `0005`).
    - `path` — the on-disk file path as a plain string. Under `FILL_NEAREST`, gap entries carry the nearest present neighbor's path; cross-check `entry.number in seq.present_numbers` to tell present from filled.
- **`present_numbers`** — the set of numbers actually on disk inside `[first, last]`.
- **`missing_numbers`** — derived from `present_numbers`: the numbers in the active range that aren't on disk (useful for diagnostics under any policy).

## Cases that are intentionally not supported

A few cases are deliberately excluded:

- **Negative numbers**: files like `render.-0005.exr` are filtered out at scan time. The dropped count is reported on the resulting sequence.
- **Sequence tokens in directory components**: patterns like `render/####/beauty.exr` aren't matched. Put the number in the filename.
- **Multi-token patterns**: templates with more than one sequence token (e.g. `v##_f####.exr`, `render.##.##.exr`) are rejected at scan time with a clear error. Use a single token per pattern.
- **Time codes**: not yet supported.

## Where this comes from

Sequence handling is built on [`fileseq`](https://github.com/justinfx/fileseq), the de facto Python library for VFX-style frame-range parsing. We use it as a parser and number-math library; all filesystem listings still flow through the engine's request bus, so the same workspace permissions, path normalization, and Windows-long-path handling that govern other file operations apply here too. fileseq itself uses "frame" terminology throughout — that's an implementation detail; the public API speaks "items" and "numbers" so the same code can serve any numbered-filename sequence, not just images.

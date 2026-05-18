# Image sequences

Griptape Nodes can read directories of numbered image files as **image sequences** — for example, a render output like `render.0001.exr`, `render.0002.exr`, … `render.0100.exr`. You point a sequence-aware node at a *pattern* (the filename with a placeholder for the frame number), and the engine finds the matching frames on disk, handles gaps, and gives you back a list of frames with their integer frame numbers and zero-padded frame strings.

This page explains the pattern syntax, the policies for handling missing frames, and the conventions you should know before authoring a template.

## Pattern syntax

A sequence pattern looks like a filename with a token in place of the frame number. Four token forms are supported:

| Token  | Width | Notes                                                         |
| ------ | ----- | ------------------------------------------------------------- |
| `####` | 4     | Each `#` is one digit. `##` = 2-digit, `####` = 4-digit, etc. |
| `%04d` | 4     | C-style printf. `%04d` = 4-digit zero-padded.                 |
| `@@@@` | 4     | Houdini/RV style. Same meaning as `####`.                     |
| `$F4`  | 4     | Houdini variable. Same meaning as `####`.                     |

All four are equivalent; pick whichever matches your pipeline conventions. We recommend `####` or `%04d` for new templates — they're the most widely understood across DCC tools.

A few examples:

```
render.####.exr             frame 5 → render.0005.exr
render.%04d.png             frame 12 → render.0012.png
shot_a.####.tif             frame 100 → shot_a.0100.tif
```

The token always sits in the **filename**. Tokens inside directory components (e.g. `render/####/beauty.exr`) are not supported — keep the frame number in the filename portion only.

## Combining with macros

Sequence patterns work alongside the project's [macro language](macros.md). The variables get resolved first, then the resulting filename is interpreted as a sequence pattern:

```
{inputs}/shot_a/render.####.exr
```

If `{inputs}` resolves to `/workspace/inputs`, the engine scans `/workspace/inputs/shot_a/` for files matching `render.####.exr`. Macro variables inside `{...}` are completely separate from sequence tokens — they don't share syntax and they're resolved at different stages.

## Width matching is strict

The number of `#` characters (or the `%0Nd` width) declares the **exact** number of digits to match. If your pattern says `####`, the engine matches files with exactly 4 digits in the frame slot — `render.0001.exr` matches, but `render.001.exr` (3 digits) and `render.12345.exr` (5 digits) do not.

This matches what Nuke does. If your sequence has frames that overflow the declared padding (e.g., a 4-digit pattern but real frame numbers go above 9999), use a wider pattern (`#####`) to capture them.

If a directory contains files with mixed padding widths — for example both `render.0001.png` and `render.001.png` — they'll be treated as **separate sequences**. The engine matches the one whose padding matches your declared template; the others are silently ignored.

## Missing-frame policies

Real sequences often have gaps — a render that crashed on frame 47, or a sparse export that only saved every other frame. When you scan a sequence, you choose a **policy** for how those gaps are handled:

| Policy              | What you get                                                                                                                                                                                        |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SPLIT` *(default)* | One sequence per **contiguous run** of present frames. A sequence with frames 1–5, 8–12, 15 produces three separate sequences.                                                                      |
| `ERROR`             | One sequence containing only the present frames. Gaps are absent from the output (but visible via the sequence's `missing_frames` set).                                                             |
| `NEAREST`           | One sequence covering the full `[first, last]` range. Each missing frame is filled with the path of the nearest **earlier** present frame (or the nearest later one if no earlier neighbor exists). |
| `BLACK`             | One sequence covering the full range. Missing frames are marked for synthesis as a solid-black image.                                                                                               |
| `CHECKERBOARD`      | Same as `BLACK` but the synthesized image is a magenta/yellow checkerboard, matching Nuke's visual missing-frame indicator.                                                                         |

Pick `SPLIT` when you want to *preserve* the gap structure (each contiguous run is meaningful on its own). Pick the others when you want a single dense sequence regardless of what's actually on disk.

## Subset clipping

Both sequence-aware nodes accept optional `start_frame` and `end_frame` parameters. When supplied, the scan is clipped to that range:

- Frames below `start_frame` and above `end_frame` are dropped from the output.
- The original disk range is still reported via `discovered_first` / `discovered_last`, so you can see what existed before the clip.
- Subset bounds outside the discovered range yield an empty result (Failure).

Set both to `-1` (the default) to use the discovered range as-is. Negative values are not allowed for either bound.

## What you get back

Each sequence carries:

- **`first`** / **`last`** — the active range (after subset clipping).
- **`discovered_first`** / **`discovered_last`** — what was actually on disk, ignoring any subset.
- **`padding`** — the declared zero-padding width (e.g. 4 for `####`).
- **`pattern`** — the canonical pattern (e.g. `render.####.exr`).
- **`directory`** — the directory the scan ran in.
- **`policy`** — which policy was applied.
- **`entries`** — one record per frame in the active range. Each entry has:
    - `frame` — the integer frame number (e.g. 5).
    - `frame_string` — the zero-padded form (e.g. `0005`).
    - `path` — the on-disk file path, or a missing-frame marker for synthesized slots.
- **`missing_frames`** — the set of frame numbers in the active range that aren't on disk (useful for diagnostics under any policy).

## Frames that are intentionally not supported

A few cases are deliberately excluded:

- **Negative frame numbers**: files like `render.-0005.exr` are filtered out at scan time. The dropped count is reported on the resulting sequence.
- **Sequence tokens in directory components**: patterns like `render/####/beauty.exr` aren't matched. Put the frame number in the filename.
- **Multi-token patterns**: templates with more than one sequence token (e.g. `v##_f####.exr`, `render.##.##.exr`) are rejected at scan time with a clear error. Use a single token per pattern.
- **Time codes**: not yet supported.

## Where this comes from

Sequence handling is built on [`fileseq`](https://github.com/justinfx/fileseq), the de facto Python library for VFX-style frame-range parsing. We use it as a parser and frame-math library; all filesystem listings still flow through the engine's request bus, so the same workspace permissions, path normalization, and Windows-long-path handling that govern other file operations apply here too.

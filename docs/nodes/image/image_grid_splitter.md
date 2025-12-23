# Image Grid Splitter

## What is it?

The Image Grid Splitter node takes a single image that contains a **regular grid** of images and splits it into individual images.

It supports:

- **Auto** grid detection (best-effort)
- **Manual** grid definition (rows/columns)
- A **preview overlay** showing dotted yellow grid lines
- Outputs as both a **list** and **per-cell outputs** (`r1c1`, `r1c2`, etc.)

## When would I use it?

Use this node when you have an image that contains multiple images (e.g., a 2×2 or 3×3 collage) and you want to:

- Extract each tile as its own image for downstream processing
- Feed individual grid cells into other nodes
- Keep both a list output and named per-cell outputs for easy wiring

## How to use it

### Basic setup

1. Add **Image Grid Splitter** to your workflow
1. Connect your grid image to **Input Image**
1. Choose **Grid Detection**:
    - **auto**: the node estimates rows/columns
    - **manual**: you specify **Rows** and **Columns**
1. Review **Preview** to confirm the split boundaries
1. Run the node to generate split images

!!! info "Auto detection is best-effort"

    Auto mode assumes a **regular grid** (equal-sized cells) and may be less accurate when adjacent cells are visually similar.
    If the preview lines don’t match your grid, switch to **manual**.

### Parameters

- **Input Image**: The grid image to split. Accepts `ImageArtifact` or `ImageUrlArtifact`.
- **Grid Detection**:
    - **auto**: detect a regular grid
    - **manual**: use explicit Rows/Columns
- **Rows / Columns** (manual only): Sliders from 1–12.
- **Preview** (output): The original image with dotted yellow grid lines.
- **Detections (auto)** (output group): Detected Rows/Columns/Count (hidden when manual mode is selected).

### Outputs

- **Images**: List of `ImageUrlArtifact` in row-major order (left-to-right, top-to-bottom).
- **Grid Cells**: One `ImageUrlArtifact` output per cell, named:
    - `r1c1`, `r1c2`, ..., `r{row}c{col}`

!!! note "Per-cell outputs are created on run"

    The `r{row}c{col}` outputs are created/updated when you run the node, based on the chosen (or detected) grid size.

## Example

If your input is a 2×2 grid:

- `r1c1` is top-left
- `r1c2` is top-right
- `r2c1` is bottom-left
- `r2c2` is bottom-right

And `Images` will contain `[r1c1, r1c2, r2c1, r2c2]`.

## Common issues

- **Preview grid lines don’t match**: switch to **manual** and set the correct Rows/Columns.
- **Unexpected auto detection**: some grids have weak visual boundaries; manual mode is the reliable fallback.

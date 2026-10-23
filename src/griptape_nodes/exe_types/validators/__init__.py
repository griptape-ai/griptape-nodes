"""Checks a node declares on its inputs and the engine runs at the node's turn, before it runs.

- `base`: what a validator is (`PreRunValidator`, `NodeValidator`) and what the engine reads for it
  (`MediaNeed`, `MediaInfo`).
- `media`: limits on an image, video or audio file, such as `MaxFileSize` or `Duration`.
- `common`: `MaxCount` for a list's length, and `ByParameter` for limits that depend on another
  parameter's value.
"""

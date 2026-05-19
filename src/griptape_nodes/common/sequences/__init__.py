"""Sequence support built on `fileseq`.

This module provides a thin wrapper over `fileseq.FileSequence` that:

- Routes all filesystem I/O through `ListDirectoryRequest` (no `os.scandir` calls).
- Drops negative numbers at scan time (intentional — they're a footgun in
  downstream tools).
- Adds explicit user-facing policy options for handling gaps within a number
  range (`SPLIT`, `ERROR`, `NEAREST`).
- Exposes both the integer key and the zero-padded string form per Sequence
  entry, so downstream nodes can present either form.

`fileseq` is used in `pad_style=PAD_STYLE_HASH1` mode throughout — this is
mandatory for our use case because the default (HASH4) interprets `####` as
16 zeros, not 4. Every public function in this module enforces that style.

Sequence tokens inside directory components (e.g. `v_####_final/beauty.png`)
are NOT supported — fileseq cannot parse them, and we don't reimplement that
case here.
"""

from griptape_nodes.common.sequences.models import (
    MissingItemPolicy,
    Sequence,
    SequenceEntry,
)
from griptape_nodes.common.sequences.scan import scan_sequences

__all__ = [
    "MissingItemPolicy",
    "Sequence",
    "SequenceEntry",
    "scan_sequences",
]

"""Utilities for working with the UV package manager."""

import uv
from xdg_base_dirs import xdg_data_home


def find_uv_bin() -> str:
    """Find the uv binary, checking dedicated Griptape installation first, then system uv.

    Returns:
        Path to the uv binary to use
    """
    # Check for dedicated Griptape uv installation first
    dedicated_uv_path = xdg_data_home() / "griptape_nodes" / "bin" / "uv"
    if dedicated_uv_path.exists():
        return str(dedicated_uv_path)

    return uv.find_uv_bin()

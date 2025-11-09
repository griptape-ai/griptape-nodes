import logging

from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
from griptape_nodes.node_library.library_registry import Library, LibrarySchema

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("griptape_nodes")


class AdvancedMediaLibrary(AdvancedNodeLibrary):
    """Advanced library implementation for the Griptape Nodes Advanced Media Library.

    Handles Windows-specific PyTorch DLL pre-loading before any nodes are loaded.
    """

    def before_library_nodes_loaded(self, library_data: LibrarySchema, library: Library) -> None:  # noqa: ARG002
        """Called before any nodes are loaded from the library.

        On Windows, pre-loads PyTorch DLLs to avoid initialization errors.
        See: https://github.com/pytorch/pytorch/issues/166628#issuecomment-3479375122
        """
        msg = f"Starting to load nodes for '{library_data.name}' library..."
        logger.info(msg)

        # Windows-specific fix: Pre-load PyTorch DLLs to avoid initialization errors
        import contextlib
        import platform
        from pathlib import Path

        if platform.system() == "Windows":
            import ctypes
            import site

            for site_path in site.getsitepackages():
                torch_lib_path = Path(site_path) / "torch" / "lib"
                if torch_lib_path.exists():
                    for dll in ["c10.dll", "torch_cpu.dll", "torch_python.dll"]:
                        dll_path = torch_lib_path / dll
                        if dll_path.exists():
                            with contextlib.suppress(Exception):
                                ctypes.CDLL(str(dll_path))
                    break

    def after_library_nodes_loaded(self, library_data: LibrarySchema, library: Library) -> None:
        """Called after all nodes have been loaded from the library."""

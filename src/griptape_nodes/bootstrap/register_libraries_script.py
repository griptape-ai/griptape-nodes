import logging

from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logging.basicConfig(
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

PATHS = ["REPLACE_LIBRARY_PATHS"]


def register_libraries(library_paths: list[str]) -> None:
    """Register libraries from the specified paths.

    Args:
        library_paths (list[str]): A list of paths to the libraries to register.
    """
    for library_path in library_paths:
        msg = f"Registering library from {library_path}"
        logger.info(msg)
        register_library_request = RegisterLibraryFromFileRequest(file_path=library_path)
        register_library_result = GriptapeNodes.handle_request(register_library_request)

        if register_library_result.failed():
            msg = f"Failed to register library from {library_path}"
            raise ValueError(msg)


if __name__ == "__main__":
    register_libraries(PATHS)

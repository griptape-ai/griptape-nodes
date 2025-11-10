from __future__ import annotations

import binascii
import logging
import os
from pathlib import Path
from urllib.parse import urljoin

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from rich.logging import RichHandler

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

# Whether to enable the static server
STATIC_SERVER_ENABLED = os.getenv("STATIC_SERVER_ENABLED", "true").lower() == "true"
# Host of the static server
STATIC_SERVER_HOST = os.getenv("STATIC_SERVER_HOST", "localhost")
# Port of the static server
STATIC_SERVER_PORT = int(os.getenv("STATIC_SERVER_PORT", "8124"))
# URL path for the static server
STATIC_SERVER_URL = os.getenv("STATIC_SERVER_URL", "/workspace")
# Log level for the static server
STATIC_SERVER_LOG_LEVEL = os.getenv("STATIC_SERVER_LOG_LEVEL", "ERROR").lower()

logger = logging.getLogger("griptape_nodes_api")
logging.getLogger("uvicorn").addHandler(RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True))


async def _create_static_file_upload_url(request: Request) -> dict:
    """Create a URL for uploading a static file.

    Similar to a presigned URL, but for uploading files to the static server.
    """
    base_url = request.base_url
    body = await request.json()
    file_path = body["file_path"].lstrip("/")
    url = urljoin(str(base_url), f"/static-uploads/{file_path}")

    return {"url": url}


async def _create_static_file(request: Request, file_path: str) -> dict:
    """Upload a static file to the static server."""
    if not STATIC_SERVER_ENABLED:
        msg = "Static server is not enabled. Please set STATIC_SERVER_ENABLED to True."
        raise ValueError(msg)

    workspace_directory = Path(GriptapeNodes.ConfigManager().get_config_value("workspace_directory"))
    full_file_path = workspace_directory / file_path

    # Create parent directories if they don't exist
    full_file_path.parent.mkdir(parents=True, exist_ok=True)

    data = await request.body()
    try:
        full_file_path.write_bytes(data)
    except binascii.Error as e:
        msg = f"Invalid base64 encoding for file {file_path}."
        logger.error(msg)
        raise HTTPException(status_code=400, detail=msg) from e
    except (OSError, PermissionError) as e:
        msg = f"Failed to write file {full_file_path}: {e}"
        logger.error(msg)
        raise HTTPException(status_code=500, detail=msg) from e

    static_url = f"http://{STATIC_SERVER_HOST}:{STATIC_SERVER_PORT}{STATIC_SERVER_URL}/{file_path}"
    return {"url": static_url}


async def _list_static_files(file_path_prefix: str = "") -> dict:
    """List static files in the static server under the specified path prefix."""
    if not STATIC_SERVER_ENABLED:
        msg = "Static server is not enabled. Please set STATIC_SERVER_ENABLED to True."
        raise HTTPException(status_code=500, detail=msg)

    workspace_directory = Path(GriptapeNodes.ConfigManager().get_config_value("workspace_directory"))

    # Handle the prefix path
    if file_path_prefix:
        target_directory = workspace_directory / file_path_prefix
    else:
        target_directory = workspace_directory

    try:
        file_names = []
        if target_directory.exists() and target_directory.is_dir():
            for file_path in target_directory.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(workspace_directory)
                    file_names.append(str(relative_path))
    except (OSError, PermissionError) as e:
        msg = f"Failed to list files in static directory: {e}"
        logger.error(msg)
        raise HTTPException(status_code=500, detail=msg) from e
    else:
        return {"files": file_names}


async def _delete_static_file(file_path: str) -> dict:
    """Delete a static file from the static server."""
    if not STATIC_SERVER_ENABLED:
        msg = "Static server is not enabled. Please set STATIC_SERVER_ENABLED to True."
        raise HTTPException(status_code=500, detail=msg)

    workspace_directory = Path(GriptapeNodes.ConfigManager().get_config_value("workspace_directory"))
    file_full_path = workspace_directory / file_path

    # Check if file exists
    if not file_full_path.exists():
        logger.warning("File not found for deletion: %s", file_path)
        raise HTTPException(status_code=404, detail=f"File {file_path} not found")

    # Check if it's actually a file (not a directory)
    if not file_full_path.is_file():
        msg = f"Path {file_path} is not a file"
        logger.error(msg)
        raise HTTPException(status_code=400, detail=msg)

    try:
        file_full_path.unlink()
    except (OSError, PermissionError) as e:
        msg = f"Failed to delete file {file_path}: {e}"
        logger.error(msg)
        raise HTTPException(status_code=500, detail=msg) from e
    else:
        logger.info("Successfully deleted static file: %s", file_path)
        return {"message": f"File {file_path} deleted successfully"}


def start_static_server() -> None:
    """Run uvicorn server synchronously using uvicorn.run."""
    logger.debug("Starting static server...")

    # Create FastAPI app
    app = FastAPI()

    # Register routes
    app.add_api_route("/static-upload-urls", _create_static_file_upload_url, methods=["POST"])
    app.add_api_route("/static-uploads/{file_path:path}", _create_static_file, methods=["PUT"])
    app.add_api_route("/static-uploads/{file_path_prefix:path}", _list_static_files, methods=["GET"])
    app.add_api_route("/static-uploads/", _list_static_files, methods=["GET"])
    app.add_api_route("/static-files/{file_path:path}", _delete_static_file, methods=["DELETE"])

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            os.getenv("GRIPTAPE_NODES_UI_BASE_URL", "https://app.nodes.griptape.ai"),
            "https://app.nodes-staging.griptape.ai",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["OPTIONS", "GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # Mount static files
    workspace_directory = Path(GriptapeNodes.ConfigManager().get_config_value("workspace_directory"))
    static_files_directory = Path(GriptapeNodes.ConfigManager().get_config_value("static_files_directory"))

    app.mount(
        STATIC_SERVER_URL,
        StaticFiles(directory=workspace_directory),
        name="workspace",
    )
    static_files_path = workspace_directory / static_files_directory
    static_files_path.mkdir(parents=True, exist_ok=True)
    # For legacy urls
    app.mount(
        "/static",
        StaticFiles(directory=workspace_directory / static_files_directory),
        name="static",
    )

    try:
        # Run server using uvicorn.run
        uvicorn.run(
            app,
            host=STATIC_SERVER_HOST,
            port=STATIC_SERVER_PORT,
            log_level=STATIC_SERVER_LOG_LEVEL,
            log_config=None,
        )
    except Exception as e:
        logger.error("API server failed: %s", e)
        raise

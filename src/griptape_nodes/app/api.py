from __future__ import annotations

import binascii
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from urllib.parse import urljoin

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from rich.logging import RichHandler

if TYPE_CHECKING:
    from queue import Queue

# Whether to enable the static server
STATIC_SERVER_ENABLED = os.getenv("STATIC_SERVER_ENABLED", "true").lower() == "true"
# Host of the static server
STATIC_SERVER_HOST = os.getenv("STATIC_SERVER_HOST", "localhost")
# Port of the static server
STATIC_SERVER_PORT = int(os.getenv("STATIC_SERVER_PORT", "8124"))
# URL path for the static server
STATIC_SERVER_URL = os.getenv("STATIC_SERVER_URL", "/static")
# Log level for the static server
STATIC_SERVER_LOG_LEVEL = os.getenv("STATIC_SERVER_LOG_LEVEL", "ERROR").lower()

logger = logging.getLogger("griptape_nodes_api")
logging.getLogger("uvicorn").addHandler(RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True))


# Global event queue - initialized as None and set when starting the API
event_queue: Queue | None = None

# Global static directory - initialized as None and set when starting the API
static_dir: Path | None = None


def get_event_queue() -> Queue:
    """FastAPI dependency to get the event queue."""
    if event_queue is None:
        msg = "Event queue is not initialized"
        raise HTTPException(status_code=500, detail=msg)
    return event_queue


def get_static_dir() -> Path:
    """FastAPI dependency to get the static directory."""
    if static_dir is None:
        msg = "Static directory is not initialized"
        raise HTTPException(status_code=500, detail=msg)
    return static_dir


"""Create and configure the FastAPI application."""
app = FastAPI()


@app.post("/static-upload-urls")
async def _create_static_file_upload_url(request: Request) -> dict:
    """Create a URL for uploading a static file.

    Similar to a presigned URL, but for uploading files to the static server.
    """
    base_url = request.base_url
    body = await request.json()
    file_name = body["file_name"]
    url = urljoin(str(base_url), f"/static-uploads/{file_name}")

    return {"url": url}


@app.put("/static-uploads/{file_path:path}")
async def _create_static_file(
    request: Request, file_path: str, static_directory: Annotated[Path, Depends(get_static_dir)]
) -> dict:
    """Upload a static file to the static server."""
    if not STATIC_SERVER_ENABLED:
        msg = "Static server is not enabled. Please set STATIC_SERVER_ENABLED to True."
        raise ValueError(msg)

    file_full_path = Path(static_directory / file_path)

    # Create parent directories if they don't exist
    file_full_path.parent.mkdir(parents=True, exist_ok=True)

    data = await request.body()
    try:
        file_full_path.write_bytes(data)
    except binascii.Error as e:
        msg = f"Invalid base64 encoding for file {file_path}."
        logger.error(msg)
        raise HTTPException(status_code=400, detail=msg) from e
    except (OSError, PermissionError) as e:
        msg = f"Failed to write file {file_path} to {static_dir}: {e}"
        logger.error(msg)
        raise HTTPException(status_code=500, detail=msg) from e

    static_url = f"http://{STATIC_SERVER_HOST}:{STATIC_SERVER_PORT}{STATIC_SERVER_URL}/{file_path}"
    return {"url": static_url}


@app.get("/static-uploads/")
async def _list_static_files(static_directory: Annotated[Path, Depends(get_static_dir)]) -> dict:
    """List all static files in the static server."""
    if not STATIC_SERVER_ENABLED:
        msg = "Static server is not enabled. Please set STATIC_SERVER_ENABLED to True."
        raise HTTPException(status_code=500, detail=msg)

    try:
        file_names = []
        if static_directory.exists():
            for file_path in static_directory.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(static_directory)
                    file_names.append(str(relative_path))
    except (OSError, PermissionError) as e:
        msg = f"Failed to list files in static directory: {e}"
        logger.error(msg)
        raise HTTPException(status_code=500, detail=msg) from e
    else:
        return {"files": file_names}


@app.delete("/static-files/{file_path:path}")
async def _delete_static_file(file_path: str, static_directory: Annotated[Path, Depends(get_static_dir)]) -> dict:
    """Delete a static file from the static server."""
    if not STATIC_SERVER_ENABLED:
        msg = "Static server is not enabled. Please set STATIC_SERVER_ENABLED to True."
        raise HTTPException(status_code=500, detail=msg)

    file_full_path = Path(static_directory / file_path)

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


@app.post("/engines/request")
async def _create_event(request: Request, queue: Annotated[Queue, Depends(get_event_queue)]) -> None:
    from .app import _process_api_event

    body = await request.json()
    _process_api_event(body, queue)


def start_api(static_directory: Path, queue: Queue) -> None:
    """Run FastAPI with Uvicorn in order to serve static files produced by nodes."""
    global event_queue, static_dir  # noqa: PLW0603
    event_queue = queue
    static_dir = static_directory

    if not static_dir.exists():
        static_dir.mkdir(parents=True, exist_ok=True)

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

    app.mount(
        STATIC_SERVER_URL,
        StaticFiles(directory=static_directory),
        name="static",
    )

    uvicorn.run(
        app, host=STATIC_SERVER_HOST, port=STATIC_SERVER_PORT, log_level=STATIC_SERVER_LOG_LEVEL, log_config=None
    )

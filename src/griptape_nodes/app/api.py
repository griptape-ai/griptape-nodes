from __future__ import annotations

import binascii
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from rich.logging import RichHandler

from griptape_nodes.retained_mode.events.base_events import EventRequest, deserialize_event

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
STATIC_SERVER_LOG_LEVEL = os.getenv("STATIC_SERVER_LOG_LEVEL", "info").lower()

logger = logging.getLogger("griptape_nodes_api")


def create_fastapi_app(static_dir: Path, event_queue: Queue) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI()

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
        allow_methods=["OPTIONS", "GET", "POST", "PUT"],
        allow_headers=["*"],
    )

    app.mount(
        STATIC_SERVER_URL,
        StaticFiles(directory=static_dir),
        name="static",
    )

    @app.post("/static-upload-urls")
    async def create_static_file_upload_url(request: Request) -> dict:
        """Create a URL for uploading a static file.

        Similar to a presigned URL, but for uploading files to the static server.
        """
        base_url = request.base_url
        body = await request.json()
        file_name = body["file_name"]
        url = urljoin(str(base_url), f"/static-uploads/{file_name}")

        return {"url": url}

    @app.put("/static-uploads/{file_path:path}")
    async def create_static_file(request: Request, file_path: str) -> dict:
        """Upload a static file to the static server."""
        if not STATIC_SERVER_ENABLED:
            msg = "Static server is not enabled. Please set STATIC_SERVER_ENABLED to True."
            raise ValueError(msg)

        file_full_path = Path(static_dir / file_path)

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

    @app.post("/engines/request")
    async def create_event(request: Request) -> None:
        body = await request.json()
        _process_api_event(body, event_queue)

    return app


def start_api(static_dir: Path, event_queue: Queue) -> None:
    """Run FastAPI with Uvicorn in order to serve static files produced by nodes."""
    app = create_fastapi_app(static_dir, event_queue)

    logging.getLogger("uvicorn").addHandler(
        RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True)
    )

    uvicorn.run(
        app, host=STATIC_SERVER_HOST, port=STATIC_SERVER_PORT, log_level=STATIC_SERVER_LOG_LEVEL, log_config=None
    )


def _process_api_event(event: dict, event_queue: Queue) -> None:
    """Process API events and send them to the event queue."""
    payload = event.get("payload", {})

    try:
        payload["request"]
    except KeyError:
        msg = "Error: 'request' was expected but not found."
        raise RuntimeError(msg) from None

    try:
        event_type = payload["event_type"]
        if event_type != "EventRequest":
            msg = "Error: 'event_type' was found on request, but did not match 'EventRequest' as expected."
            raise RuntimeError(msg) from None
    except KeyError:
        msg = "Error: 'event_type' not found in request."
        raise RuntimeError(msg) from None

    # Now attempt to convert it into an EventRequest.
    try:
        request_event = deserialize_event(json_data=payload)
        if not isinstance(request_event, EventRequest):
            msg = f"Deserialized event is not an EventRequest: {type(request_event)}"
            raise TypeError(msg)  # noqa: TRY301
    except Exception as e:
        msg = f"Unable to convert request JSON into a valid EventRequest object. Error Message: '{e}'"
        raise RuntimeError(msg) from None

    # Add the event to the queue
    event_queue.put(request_event)

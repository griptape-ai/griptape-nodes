"""App package."""

import os

if os.getenv("GTN_USE_WEBSOCKETS", "false").lower() == "true":
    from griptape_nodes.app.app_websocket import start_app
else:
    from griptape_nodes.app.app import start_app

__all__ = ["start_app"]

"""App package."""

import os

if os.getenv("GTN_USE_SESSIONS", "False").lower() == "true":
    from griptape_nodes.app.app_sessions import start_app
else:
    from griptape_nodes.app.app import start_app

__all__ = ["start_app"]

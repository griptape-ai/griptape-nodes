"""App package."""

import os

if os.getenv("GTN_USE_SESSIONS", "False").lower() == "true":
    # Sessions are only available in the staging environment
    os.environ["GRIPTAPE_NODES_API_BASE_URL"] = os.getenv(
        "GRIPTAPE_NODES_API_BASE_URL", "https://api.nodes-staging.griptape.ai"
    )
    from griptape_nodes.app.app_sessions import start_app
else:
    from griptape_nodes.app.app import start_app

__all__ = ["start_app"]

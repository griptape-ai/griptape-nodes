from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


def getenv(service: str, value: str) -> str:
    api_key = GriptapeNodes.get_instance()._config_manager.get_config_value(f"env.{service}.{value}")
    return api_key

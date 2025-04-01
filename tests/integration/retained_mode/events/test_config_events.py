from griptape_nodes.retained_mode.events.config_events import (
    GetConfigValueRequest,
    GetConfigValueResultSuccess,
    SetConfigValueRequest,
)
from griptape_nodes.retained_mode.events.secrets_events import (
    SetSecretValueRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestConfigEvents:
    def test_get_config_value(self) -> None:
        GriptapeNodes.handle_request(SetSecretValueRequest(key="SECRET_KEY", value="secret foo"))
        GriptapeNodes.handle_request(SetConfigValueRequest(category_and_key="nodes.foo.bar", value="$SECRET_KEY"))
        result = GriptapeNodes.handle_request(GetConfigValueRequest(category_and_key="nodes.foo.bar"))

        assert isinstance(result, GetConfigValueResultSuccess)

        assert result.value == "secret foo"

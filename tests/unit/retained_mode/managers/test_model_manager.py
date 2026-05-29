"""Tests for ModelManager methods added for model size support.

Covers:
- `on_handle_get_model_info_request` — token guard and HF API delegation
- `on_handle_search_models_request` — search result handling
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from griptape_nodes.retained_mode.events.model_events import (
    GetModelInfoRequest,
    GetModelInfoResultFailure,
    GetModelInfoResultSuccess,
    SearchModelsRequest,
    SearchModelsResultFailure,
    SearchModelsResultSuccess,
)
from griptape_nodes.retained_mode.managers.model_manager import ModelManager


@pytest.fixture
def model_manager() -> ModelManager:
    """Bare ModelManager without event wiring."""
    return ModelManager.__new__(ModelManager)


# ---------------------------------------------------------------------------
# on_handle_get_model_info_request
# ---------------------------------------------------------------------------


class TestOnHandleGetModelInfoRequest:
    @pytest.mark.asyncio
    async def test_returns_failure_when_no_hf_token(self, model_manager: ModelManager) -> None:
        with patch(
            "griptape_nodes.retained_mode.managers.model_manager.get_token",
            return_value=None,
        ):
            result = await model_manager.on_handle_get_model_info_request(
                GetModelInfoRequest(model_id="microsoft/phi-2")
            )

        assert isinstance(result, GetModelInfoResultFailure)
        assert "No Hugging Face token found" in str(result.result_details)

    @pytest.mark.asyncio
    async def test_returns_success_with_size_and_metadata(self, model_manager: ModelManager) -> None:
        fake_info = SimpleNamespace(
            used_storage=11_125_567_216,
            safetensors=SimpleNamespace(parameters={"F16": 2_779_683_840}),
            author="microsoft",
            pipeline_tag="text-generation",
            library_name="transformers",
            tags=["pytorch"],
            downloads=123_456,
            likes=789,
        )

        with (
            patch(
                "griptape_nodes.retained_mode.managers.model_manager.get_token",
                return_value="hf_token",
            ),
            patch(
                "griptape_nodes.retained_mode.managers.model_manager.hf_model_info",
                return_value=fake_info,
            ),
        ):
            result = await model_manager.on_handle_get_model_info_request(
                GetModelInfoRequest(model_id="microsoft/phi-2")
            )

        assert isinstance(result, GetModelInfoResultSuccess)
        assert result.model_id == "microsoft/phi-2"
        assert result.size_bytes == 11_125_567_216
        assert result.safetensors_parameters == {"F16": 2_779_683_840}
        assert result.author == "microsoft"
        assert result.task == "text-generation"
        assert result.library == "transformers"
        assert result.downloads == 123_456
        assert result.likes == 789

    @pytest.mark.asyncio
    async def test_returns_failure_when_hf_api_raises(self, model_manager: ModelManager) -> None:
        with (
            patch(
                "griptape_nodes.retained_mode.managers.model_manager.get_token",
                return_value="hf_token",
            ),
            patch(
                "griptape_nodes.retained_mode.managers.model_manager.hf_model_info",
                side_effect=ValueError("model not found"),
            ),
        ):
            result = await model_manager.on_handle_get_model_info_request(GetModelInfoRequest(model_id="bad/model"))

        assert isinstance(result, GetModelInfoResultFailure)
        assert "bad/model" in str(result.result_details)

    @pytest.mark.asyncio
    async def test_handles_missing_safetensors_gracefully(self, model_manager: ModelManager) -> None:
        fake_info = SimpleNamespace(
            used_storage=None,
            safetensors=None,
            author=None,
            pipeline_tag=None,
            library_name=None,
            tags=None,
            downloads=None,
            likes=None,
        )

        with (
            patch(
                "griptape_nodes.retained_mode.managers.model_manager.get_token",
                return_value="hf_token",
            ),
            patch(
                "griptape_nodes.retained_mode.managers.model_manager.hf_model_info",
                return_value=fake_info,
            ),
        ):
            result = await model_manager.on_handle_get_model_info_request(GetModelInfoRequest(model_id="some/model"))

        assert isinstance(result, GetModelInfoResultSuccess)
        assert result.size_bytes is None
        assert result.safetensors_parameters is None


# ---------------------------------------------------------------------------
# on_handle_search_models_request
# ---------------------------------------------------------------------------


class TestOnHandleSearchModelsRequest:
    def _make_hf_model(self, model_id: str) -> object:
        return SimpleNamespace(
            id=model_id,
            author=None,
            downloads=None,
            likes=None,
            created_at=None,
            last_modified=None,
            pipeline_tag=None,
            library_name=None,
            tags=None,
        )

    @pytest.mark.asyncio
    async def test_returns_success_with_model_list(self, model_manager: ModelManager) -> None:
        fake_model = self._make_hf_model("org/model")

        with patch(
            "griptape_nodes.retained_mode.managers.model_manager.list_models",
            return_value=[fake_model],
        ):
            result = await model_manager.on_handle_search_models_request(SearchModelsRequest(query="model"))

        assert isinstance(result, SearchModelsResultSuccess)
        assert len(result.models) == 1
        assert result.models[0].model_id == "org/model"

    @pytest.mark.asyncio
    async def test_returns_failure_when_list_models_raises(self, model_manager: ModelManager) -> None:
        with patch(
            "griptape_nodes.retained_mode.managers.model_manager.list_models",
            side_effect=RuntimeError("network error"),
        ):
            result = await model_manager.on_handle_search_models_request(SearchModelsRequest(query="model"))

        assert isinstance(result, SearchModelsResultFailure)

"""Tests for ModelManager methods added for model size support.

Covers:
- `_estimate_size_from_safetensors` — pure size estimation logic
- `on_handle_get_model_info_request` — token guard and HF API delegation
- `on_handle_search_models_request` — estimated_size_bytes propagation
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
# _estimate_size_from_safetensors
# ---------------------------------------------------------------------------


class TestEstimateSizeFromSafetensors:
    def _make_safetensors(self, parameters: dict) -> object:
        return SimpleNamespace(parameters=parameters)

    def test_returns_none_when_no_safetensors_info(self, model_manager: ModelManager) -> None:
        assert model_manager._estimate_size_from_safetensors(None) is None

    def test_returns_none_when_parameters_empty(self, model_manager: ModelManager) -> None:
        info = self._make_safetensors({})
        assert model_manager._estimate_size_from_safetensors(info) is None

    def test_f16_two_bytes_per_param(self, model_manager: ModelManager) -> None:
        info = self._make_safetensors({"F16": 1_000_000})
        assert model_manager._estimate_size_from_safetensors(info) == 2_000_000

    def test_f32_four_bytes_per_param(self, model_manager: ModelManager) -> None:
        info = self._make_safetensors({"F32": 1_000_000})
        assert model_manager._estimate_size_from_safetensors(info) == 4_000_000

    def test_bf16_two_bytes_per_param(self, model_manager: ModelManager) -> None:
        info = self._make_safetensors({"BF16": 1_000_000})
        assert model_manager._estimate_size_from_safetensors(info) == 2_000_000

    def test_i8_one_byte_per_param(self, model_manager: ModelManager) -> None:
        info = self._make_safetensors({"I8": 1_000_000})
        assert model_manager._estimate_size_from_safetensors(info) == 1_000_000

    def test_bool_one_byte_per_element(self, model_manager: ModelManager) -> None:
        # safetensors stores bools as uint8 (1 byte), not bitpacked
        info = self._make_safetensors({"BOOL": 1_000_000})
        assert model_manager._estimate_size_from_safetensors(info) == 1_000_000

    def test_mixed_dtypes_summed(self, model_manager: ModelManager) -> None:
        info = self._make_safetensors({"F32": 500_000, "F16": 500_000})
        # 500k × 4 + 500k × 2 = 3_000_000
        assert model_manager._estimate_size_from_safetensors(info) == 3_000_000

    def test_unknown_dtype_defaults_to_four_bytes(self, model_manager: ModelManager) -> None:
        info = self._make_safetensors({"EXOTIC": 1_000_000})
        assert model_manager._estimate_size_from_safetensors(info) == 4_000_000

    def test_dtype_matching_is_case_insensitive(self, model_manager: ModelManager) -> None:
        info = self._make_safetensors({"f16": 1_000_000})
        assert model_manager._estimate_size_from_safetensors(info) == 2_000_000


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
            result = await model_manager.on_handle_get_model_info_request(
                GetModelInfoRequest(model_id="bad/model")
            )

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
            result = await model_manager.on_handle_get_model_info_request(
                GetModelInfoRequest(model_id="some/model")
            )

        assert isinstance(result, GetModelInfoResultSuccess)
        assert result.size_bytes is None
        assert result.safetensors_parameters is None


# ---------------------------------------------------------------------------
# on_handle_search_models_request — estimated_size_bytes propagation
# ---------------------------------------------------------------------------


class TestOnHandleSearchModelsRequestEstimatedSize:
    def _make_hf_model(self, model_id: str, safetensors=None) -> object:
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
            safetensors=safetensors,
        )

    @pytest.mark.asyncio
    async def test_estimated_size_populated_when_safetensors_present(
        self, model_manager: ModelManager
    ) -> None:
        safetensors = SimpleNamespace(parameters={"F16": 1_000_000})
        fake_model = self._make_hf_model("org/model", safetensors=safetensors)

        with patch(
            "griptape_nodes.retained_mode.managers.model_manager.list_models",
            return_value=[fake_model],
        ):
            result = await model_manager.on_handle_search_models_request(
                SearchModelsRequest(query="model")
            )

        assert isinstance(result, SearchModelsResultSuccess)
        assert result.models[0].estimated_size_bytes == 2_000_000  # 1M × 2 bytes (F16)

    @pytest.mark.asyncio
    async def test_estimated_size_is_none_when_no_safetensors(
        self, model_manager: ModelManager
    ) -> None:
        fake_model = self._make_hf_model("org/model", safetensors=None)

        with patch(
            "griptape_nodes.retained_mode.managers.model_manager.list_models",
            return_value=[fake_model],
        ):
            result = await model_manager.on_handle_search_models_request(
                SearchModelsRequest(query="model")
            )

        assert isinstance(result, SearchModelsResultSuccess)
        assert result.models[0].estimated_size_bytes is None

    @pytest.mark.asyncio
    async def test_returns_failure_when_list_models_raises(
        self, model_manager: ModelManager
    ) -> None:
        with patch(
            "griptape_nodes.retained_mode.managers.model_manager.list_models",
            side_effect=RuntimeError("network error"),
        ):
            result = await model_manager.on_handle_search_models_request(
                SearchModelsRequest(query="model")
            )

        assert isinstance(result, SearchModelsResultFailure)

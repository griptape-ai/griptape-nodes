from pathlib import Path
from unittest.mock import Mock

import pytest

from griptape_nodes.exe_types.param_components.huggingface.huggingface_model_parameter import (
    HuggingFaceModelParameter,
)
from griptape_nodes.exe_types.param_components.huggingface.huggingface_utils import (
    assert_model_has_checkpoint_files,
)

from .mocks import MockNode

_SNAPSHOT_DOWNLOAD = (
    "griptape_nodes.exe_types.param_components.huggingface.huggingface_utils.snapshot_download"
)
_ASSERT_CHECKPOINT = (
    "griptape_nodes.exe_types.param_components.huggingface.huggingface_model_parameter.assert_model_has_checkpoint_files"
)


class ConcreteHFModelParam(HuggingFaceModelParameter):
    """Minimal concrete subclass for testing the abstract base class."""

    def fetch_repo_revisions(self) -> list[tuple[str, str]]:
        return []

    def get_download_commands(self) -> list[str]:
        return []

    def get_download_models(self) -> list[str]:
        return []


class TestAssertModelHasCheckpointFiles:
    def test_passes_with_bin_file(self, tmp_path: Path, mocker: Mock) -> None:
        mocker.patch(_SNAPSHOT_DOWNLOAD, return_value=str(tmp_path))
        (tmp_path / "pytorch_model.bin").write_bytes(b"fake weights")

        assert_model_has_checkpoint_files("org/model", "abc123")

    def test_passes_with_safetensors_file(self, tmp_path: Path, mocker: Mock) -> None:
        mocker.patch(_SNAPSHOT_DOWNLOAD, return_value=str(tmp_path))
        (tmp_path / "model.safetensors").write_bytes(b"fake weights")

        assert_model_has_checkpoint_files("org/model", "abc123")

    def test_raises_when_no_weight_files(self, tmp_path: Path, mocker: Mock) -> None:
        mocker.patch(_SNAPSHOT_DOWNLOAD, return_value=str(tmp_path))
        (tmp_path / "config.json").write_text("{}")
        (tmp_path / "tokenizer.json").write_text("{}")

        with pytest.raises(ValueError, match="no checkpoint files"):
            assert_model_has_checkpoint_files("org/model", "abc123")

    def test_raises_when_snapshot_download_fails(self, mocker: Mock) -> None:
        mocker.patch(_SNAPSHOT_DOWNLOAD, side_effect=Exception("not in cache"))

        with pytest.raises(ValueError, match="could not locate its snapshot"):
            assert_model_has_checkpoint_files("org/model", "abc123")

    def test_error_message_includes_repo_id(self, tmp_path: Path, mocker: Mock) -> None:
        mocker.patch(_SNAPSHOT_DOWNLOAD, return_value=str(tmp_path))

        with pytest.raises(ValueError, match="google/t5-v1_1-xxl"):
            assert_model_has_checkpoint_files("google/t5-v1_1-xxl", "abc123")

    def test_error_message_mentions_model_manager(self, tmp_path: Path, mocker: Mock) -> None:
        mocker.patch(_SNAPSHOT_DOWNLOAD, return_value=str(tmp_path))

        with pytest.raises(ValueError, match="Model Manager"):
            assert_model_has_checkpoint_files("org/model", "abc123")


class TestValidateBeforeNodeRun:
    def test_returns_error_when_repo_revision_fails(self, mocker: Mock) -> None:
        node = MockNode()
        param = ConcreteHFModelParam(node, "model")
        mocker.patch.object(param, "refresh_parameters")
        mocker.patch.object(param, "get_repo_revision", side_effect=RuntimeError("Model download required!"))

        errors = param.validate_before_node_run()

        assert errors is not None
        assert len(errors) == 1
        assert isinstance(errors[0], RuntimeError)

    def test_returns_error_when_checkpoint_check_fails(self, mocker: Mock) -> None:
        node = MockNode()
        param = ConcreteHFModelParam(node, "model")
        mocker.patch.object(param, "refresh_parameters")
        mocker.patch.object(param, "get_repo_revision", return_value=("org/model", "abc123"))
        mocker.patch(_ASSERT_CHECKPOINT, side_effect=ValueError("corrupt or incomplete"))

        errors = param.validate_before_node_run()

        assert errors is not None
        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)

    def test_returns_none_when_all_checks_pass(self, mocker: Mock) -> None:
        node = MockNode()
        param = ConcreteHFModelParam(node, "model")
        mocker.patch.object(param, "refresh_parameters")
        mocker.patch.object(param, "get_repo_revision", return_value=("org/model", "abc123"))
        mocker.patch(_ASSERT_CHECKPOINT)

        result = param.validate_before_node_run()

        assert result is None

    def test_checkpoint_check_called_with_resolved_repo_and_revision(self, mocker: Mock) -> None:
        node = MockNode()
        param = ConcreteHFModelParam(node, "model")
        mocker.patch.object(param, "refresh_parameters")
        mocker.patch.object(param, "get_repo_revision", return_value=("org/model", "deadbeef" * 5))
        mock_check = mocker.patch(_ASSERT_CHECKPOINT)

        param.validate_before_node_run()

        mock_check.assert_called_once_with("org/model", "deadbeef" * 5)

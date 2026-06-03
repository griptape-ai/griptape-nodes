"""Unit tests for the Settings model validators."""

from __future__ import annotations

import pytest

from griptape_nodes.retained_mode.managers.settings import Settings


class TestThreadStorageBackend:
    """The backend field migrates legacy values instead of failing validation.

    A config persisted before Griptape Cloud thread storage was removed carries
    ``thread_storage_backend: "gtc"``. Validation must coerce it to ``"local"``
    rather than raise, otherwise the whole merged config is discarded and every
    other user setting reverts to defaults.
    """

    @pytest.mark.parametrize("value", ["gtc", "whatever", "", None, 123])
    def test_legacy_or_unknown_values_coerce_to_local(self, value: object) -> None:
        assert Settings.model_validate({"thread_storage_backend": value}).thread_storage_backend == "local"

    def test_local_is_preserved(self) -> None:
        assert Settings.model_validate({"thread_storage_backend": "local"}).thread_storage_backend == "local"

    def test_default_is_local(self) -> None:
        assert Settings().thread_storage_backend == "local"

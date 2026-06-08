"""Unit tests for the Settings model validators."""

from __future__ import annotations

import pytest

from griptape_nodes.retained_mode.managers.settings import LibraryDependencyInstallBehavior, Settings


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


class TestLibraryDependencyInstallBehavior:
    """The library_dependency_install_behavior field coerces bad persisted values to ALWAYS.

    A typo or stale value in a persisted config must not fail whole-config
    validation and reset every other user setting to defaults.
    """

    @pytest.mark.parametrize("value", ["typo", "", None, 123, "ALWAYS"])
    def test_unknown_values_coerce_to_always(self, value: object) -> None:
        result = Settings.model_validate({"library_dependency_install_behavior": value})
        assert result.library_dependency_install_behavior == LibraryDependencyInstallBehavior.ALWAYS

    @pytest.mark.parametrize("value", ["always", "never"])
    def test_valid_string_values_are_preserved(self, value: str) -> None:
        result = Settings.model_validate({"library_dependency_install_behavior": value})
        assert result.library_dependency_install_behavior == LibraryDependencyInstallBehavior(value)

    def test_default_is_always(self) -> None:
        assert Settings().library_dependency_install_behavior == LibraryDependencyInstallBehavior.ALWAYS

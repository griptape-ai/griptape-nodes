"""Tests for the main CLI application."""

from __future__ import annotations

import warnings

import pytest
import typer

from griptape_nodes.cli.main import main


class TestMainCallback:
    def test_when_no_update_then_emits_deprecation_warning(self) -> None:
        with pytest.warns(FutureWarning, match="--no-update"), pytest.raises(typer.Exit):
            main(version=True, no_update=True)

    def test_when_without_no_update_then_does_not_emit_deprecation_warning(self) -> None:
        # Error on FutureWarning, scoped so it doesn't leak into other tests.
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            with pytest.raises(typer.Exit):
                main(version=True, no_update=False)

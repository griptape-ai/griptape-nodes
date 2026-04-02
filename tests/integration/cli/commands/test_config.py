"""Integration tests for the config CLI command."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from griptape_nodes.cli.main import app


class TestConfigShow:
    def test_when_no_update_config_show_then_stdout_is_valid_json(self) -> None:
        runner = CliRunner()
        mock_config = {"workspace_directory": "/home/user/workspace", "debug": True}

        with patch("griptape_nodes.cli.commands.config.config_manager") as mock_config_manager:
            mock_config_manager.merged_config = mock_config
            with pytest.warns(FutureWarning, match="--no-update"):
                result = runner.invoke(app, ["--no-update", "config", "show"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == mock_config

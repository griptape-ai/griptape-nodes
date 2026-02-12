
from griptape_nodes.utils.dict_utils import merge_dicts, normalize_secrets_to_register


class TestNormalizeSecretsToRegister:
    """Tests for normalize_secrets_to_register function."""

    def test_list_to_dict(self) -> None:
        """Test that list format is converted to dict with empty string defaults."""
        result = normalize_secrets_to_register(["KEY1", "KEY2", "KEY3"])
        assert result == {"KEY1": "", "KEY2": "", "KEY3": ""}

    def test_dict_unchanged(self) -> None:
        """Test that dict format is returned unchanged."""
        input_dict = {"KEY1": "default1", "KEY2": "", "KEY3": "default3"}
        result = normalize_secrets_to_register(input_dict)
        assert result == input_dict

    def test_none_returns_empty_dict(self) -> None:
        """Test that None returns empty dict."""
        result = normalize_secrets_to_register(None)
        assert result == {}

    def test_empty_list_returns_empty_dict(self) -> None:
        """Test that empty list returns empty dict."""
        result = normalize_secrets_to_register([])
        assert result == {}

    def test_empty_dict_returns_empty_dict(self) -> None:
        """Test that empty dict returns empty dict."""
        result = normalize_secrets_to_register({})
        assert result == {}


class TestMergeDicts:
    """Tests for merge_dicts function."""

    def test_merge_dict_with_list_overwrites(self) -> None:
        """Test that when one side is dict and other is list, list overwrites (no recursive merge error)."""
        base = {"key": {"nested": "value"}}
        override = {"key": ["item1", "item2"]}

        # Should not raise TypeError, list should overwrite dict
        result = merge_dicts(base, override)
        assert result == {"key": ["item1", "item2"]}

    def test_merge_list_with_dict_overwrites(self) -> None:
        """Test that when one side is list and other is dict, dict overwrites."""
        base = {"key": ["item1", "item2"]}
        override = {"key": {"nested": "value"}}

        result = merge_dicts(base, override)
        assert result == {"key": {"nested": "value"}}

    def test_merge_two_dicts_recursively(self) -> None:
        """Test that two dicts are merged recursively."""
        base = {"key": {"a": 1, "b": 2}}
        override = {"key": {"b": 3, "c": 4}}

        result = merge_dicts(base, override)
        assert result == {"key": {"a": 1, "b": 3, "c": 4}}

    def test_merge_lists_when_enabled(self) -> None:
        """Test that lists are merged when merge_lists=True."""
        base = {"key": ["a", "b"]}
        override = {"key": ["b", "c"]}

        result = merge_dicts(base, override, merge_lists=True)
        # Sets deduplicate, order may vary
        assert set(result["key"]) == {"a", "b", "c"}

    def test_merge_lists_disabled_overwrites(self) -> None:
        """Test that lists overwrite when merge_lists=False."""
        base = {"key": ["a", "b"]}
        override = {"key": ["c", "d"]}

        result = merge_dicts(base, override, merge_lists=False)
        assert result == {"key": ["c", "d"]}

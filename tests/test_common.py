import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hermes_xmpp_plugin_common import (  # noqa: E402
    add_xmpp_display_defaults,
    backup_file,
    get_hermes_home,
    get_profile_dir,
    remove_plugin_enabled_entries,
    remove_xmpp_display_defaults,
    validate_avatar_path,
)


def test_get_hermes_home_default(monkeypatch):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    home = get_hermes_home(None)
    assert home == Path.home() / ".hermes"


def test_get_hermes_home_env(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("HERMES_HOME", tmp)
        home = get_hermes_home(None)
        assert home == Path(tmp)


def test_get_profile_dir_default():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        profile_dir = get_profile_dir(home)
        assert profile_dir == home


def test_get_profile_dir_named():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        profile_dir = get_profile_dir(home, "work")
        assert profile_dir == home / "profiles" / "work"


def test_backup_file(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("x: 1\n")
    backup = backup_file(config, ".bak")
    assert backup.exists()
    assert backup.read_text() == "x: 1\n"


def test_add_xmpp_display_defaults_creates_nested_block():
    """Fresh config gets display.platforms.xmpp.tool_progress_grouping: separate."""
    result = add_xmpp_display_defaults("")
    import yaml

    parsed = yaml.safe_load(result)
    assert parsed["display"]["platforms"]["xmpp"]["tool_progress_grouping"] == "separate"


def test_add_xmpp_display_defaults_appends_to_existing_display():
    """An existing display block (with other keys) gains the nested xmpp key."""
    config = "display:\n  compact: false\n  streaming: true\n"
    result = add_xmpp_display_defaults(config)
    import yaml

    parsed = yaml.safe_load(result)
    assert parsed["display"]["compact"] is False
    assert parsed["display"]["platforms"]["xmpp"]["tool_progress_grouping"] == "separate"


def test_add_xmpp_display_defaults_preserves_existing_value():
    """An explicit user value (accumulate) is left untouched."""
    config = (
        "display:\n"
        "  platforms:\n"
        "    xmpp:\n"
        "      tool_progress_grouping: accumulate\n"
    )
    result = add_xmpp_display_defaults(config)
    assert "tool_progress_grouping: accumulate" in result
    assert "tool_progress_grouping: separate" not in result


def test_add_xmpp_display_defaults_idempotent():
    """Running twice yields the same result (no duplicate keys)."""
    once = add_xmpp_display_defaults("display:\n  compact: false\n")
    twice = add_xmpp_display_defaults(once)
    assert once == twice


def test_add_xmpp_display_defaults_not_in_platforms_xmpp():
    """The display key must NOT leak into the top-level platforms.xmpp block."""
    config = (
        "platforms:\n"
        "  xmpp:\n"
        "    enabled: true\n"
        "    omemo_enabled: true\n"
    )
    result = add_xmpp_display_defaults(config)
    import yaml

    parsed = yaml.safe_load(result)
    assert "tool_progress_grouping" not in parsed["platforms"]["xmpp"]
    assert parsed["display"]["platforms"]["xmpp"]["tool_progress_grouping"] == "separate"


def test_validate_avatar_path(tmp_path):
    """Blank is valid; a missing or non-file path is rejected with a message."""
    ok, _msg = validate_avatar_path("")
    assert ok

    ok, msg = validate_avatar_path(str(tmp_path / "nope.png"))
    assert not ok and "does not exist" in msg

    ok, msg = validate_avatar_path(str(tmp_path))  # a directory
    assert not ok and "not a file" in msg

    real = tmp_path / "avatar.png"
    real.write_bytes(b"x")
    ok, _msg = validate_avatar_path(str(real))
    assert ok


def test_remove_xmpp_display_defaults_removes_key():
    """The display key is removed and empty nested blocks collapse."""
    config = (
        "display:\n"
        "  compact: false\n"
        "  platforms:\n"
        "    xmpp:\n"
        "      tool_progress_grouping: separate\n"
    )
    result = remove_xmpp_display_defaults(config)
    import yaml

    parsed = yaml.safe_load(result)
    assert parsed["display"]["compact"] is False
    assert "platforms" not in parsed["display"]


def test_remove_xmpp_display_defaults_keeps_other_display_keys():
    """A display block with other platforms survives; only xmpp's key goes."""
    config = (
        "display:\n"
        "  platforms:\n"
        "    xmpp:\n"
        "      tool_progress_grouping: separate\n"
        "    other:\n"
        "      tool_progress_grouping: accumulate\n"
    )
    result = remove_xmpp_display_defaults(config)
    import yaml

    parsed = yaml.safe_load(result)
    assert "xmpp" not in parsed["display"]["platforms"]
    assert parsed["display"]["platforms"]["other"]["tool_progress_grouping"] == "accumulate"


def test_remove_xmpp_display_defaults_noop_without_key():
    """A config with no xmpp display key is returned unchanged."""
    config = "display:\n  compact: false\n"
    assert remove_xmpp_display_defaults(config) == config


def test_remove_plugin_enabled_entries_block_style():
    """Removes the key from a block-style enabled list, keeps others."""
    config = (
        "plugins:\n"
        "  enabled:\n"
        "    - xmpp-platform\n"
        "    - other/plugin\n"
    )
    result = remove_plugin_enabled_entries(config)
    import yaml

    parsed = yaml.safe_load(result)
    assert parsed["plugins"]["enabled"] == ["other/plugin"]


def test_remove_plugin_enabled_entries_drops_empty_block():
    """A plugins block left with no enabled/disabled keys is dropped."""
    config = "plugins:\n  enabled:\n    - xmpp-platform\n"
    result = remove_plugin_enabled_entries(config)
    import yaml

    assert yaml.safe_load(result) is None
    assert result.strip() == ""


def test_remove_plugin_enabled_entries_flow_style():
    """Removes the key from a flow-style enabled list."""
    config = "plugins:\n  enabled: [xmpp-platform, other/plugin]\n"
    result = remove_plugin_enabled_entries(config)
    import yaml

    parsed = yaml.safe_load(result)
    assert parsed["plugins"]["enabled"] == ["other/plugin"]


def test_remove_plugin_enabled_entries_legacy_key():
    """The legacy platforms/xmpp key is also removed."""
    config = "plugins:\n  enabled:\n    - platforms/xmpp\n    - other/plugin\n"
    result = remove_plugin_enabled_entries(config)
    import yaml

    parsed = yaml.safe_load(result)
    assert parsed["plugins"]["enabled"] == ["other/plugin"]


def test_remove_plugin_enabled_entries_disabled_list():
    """The key is also removed from plugins.disabled."""
    config = (
        "plugins:\n"
        "  disabled:\n"
        "    - xmpp-platform\n"
        "    - other/plugin\n"
    )
    result = remove_plugin_enabled_entries(config)
    import yaml

    parsed = yaml.safe_load(result)
    assert parsed["plugins"]["disabled"] == ["other/plugin"]


def test_remove_plugin_enabled_entries_noop_without_key():
    """A config without this plugin's keys is returned unchanged."""
    config = "plugins:\n  enabled:\n    - other/plugin\n"
    assert remove_plugin_enabled_entries(config) == config

#!/usr/bin/env python3
"""Post-install configuration for the Hermes XMPP plugin.

Run this AFTER ``hermes plugins install`` to finish what the native installer
leaves alone:

  * set ``display.platforms.xmpp.tool_progress_grouping: separate`` so tool
    progress arrives as one message per tool call (XMPP cannot edit a growing
    bubble, so the gateway's ``accumulate`` default does not work here)
  * prompt for an optional bot avatar and store it in the profile .env

Everything else is handled natively: credentials and Python dependencies are
installed by ``hermes plugins install``, and the enablement key comes from
``--enable``. Access control is managed by Hermes core (the allowlist env var
or DM pairing codes), not this script.

Usage:
    python3 post_install.py [options]

Safe to re-run: an existing tool-progress value and avatar are preserved.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

# The common module lives next to this script (we are inside the installed
# plugin directory).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hermes_xmpp_plugin_common import (  # noqa: E402
    add_xmpp_display_defaults,
    backup_file,
    get_hermes_home,
    get_profile_dir,
    validate_avatar_path,
)


def fail(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def _read_avatar(env_path: Path) -> str:
    """Existing XMPP_AVATAR_PATH value from the profile .env, or ''."""
    if not env_path.exists():
        return ""
    for line in env_path.read_text().splitlines():
        if "=" in line and line.split("=", 1)[0].strip() == "XMPP_AVATAR_PATH":
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def _write_avatar(env_path: Path, avatar_path: str) -> None:
    """Upsert XMPP_AVATAR_PATH into the profile .env (deduping any prior line)."""
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    rendered = f'XMPP_AVATAR_PATH="{avatar_path}"'
    out: list[str] = []
    replaced = False
    for line in lines:
        if "=" in line and line.split("=", 1)[0].strip() == "XMPP_AVATAR_PATH":
            if not replaced:
                out.append(rendered if line.strip() != rendered else line)
                replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(rendered)
    env_path.write_text("\n".join(out) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Post-install configuration for the Hermes XMPP plugin "
        "(run after 'hermes plugins install')."
    )
    parser.add_argument("--hermes-home", help="Hermes home directory (default: ~/.hermes)")
    parser.add_argument("--profile", default=None, help="Hermes profile name")
    args = parser.parse_args(argv)

    try:
        hermes_home = get_hermes_home(args.hermes_home)
        profile_dir = get_profile_dir(hermes_home, args.profile)
    except FileNotFoundError as exc:
        fail(str(exc))

    config_path = profile_dir / "config.yaml"
    env_path = profile_dir / ".env"

    print("=" * 60)
    print("Hermes XMPP Plugin - Post-Install Configuration")
    print("=" * 60)
    print(f"Hermes home:   {hermes_home}")
    print(f"Profile dir:   {profile_dir}")

    # 1. Tool-progress grouping (the one display default XMPP needs).
    if not config_path.exists():
        fail(f"config not found: {config_path}")
    backup_path = backup_file(config_path, ".postinstall-backup")
    print(f"Backed up config to {backup_path}")
    text = config_path.read_text()
    new_text = add_xmpp_display_defaults(text)
    if new_text != text:
        config_path.write_text(new_text)
        print("Tool progress set to one message per tool (XMPP cannot edit messages).")
    else:
        print("Tool progress already configured.")

    # 2. Optional avatar (nicety). When there is no terminal (headless install
    # or a piped run), skip the prompt silently and keep any existing avatar.
    existing = _read_avatar(env_path)
    avatar = existing
    if sys.stdin.isatty():
        print(
            "\nOptional avatar image. Recommended: a square PNG or JPEG, "
            "at least 480x480 pixels. The plugin will crop to a centered "
            "square and resize to 480x480."
        )
        prompt = (
            f"Avatar file path [{existing}]: "
            if existing
            else "Avatar file path (leave blank for none): "
        )
        avatar = input(prompt).strip() or existing
        ok, msg = validate_avatar_path(avatar)
        while not ok:
            print(f"WARNING: {msg}")
            avatar = input("Enter a valid avatar file path (or leave blank for none): ").strip()
            ok, msg = validate_avatar_path(avatar)
    if avatar:
        _write_avatar(env_path, avatar)
        print(f"Avatar stored: XMPP_AVATAR_PATH={avatar}")
    elif not existing:
        print("No avatar set (you can add XMPP_AVATAR_PATH in .env later).")

    print("\nPost-install complete.")
    print("Restart the Hermes gateway to load the plugin:")
    print("  hermes gateway restart")
    return 0


if __name__ == "__main__":
    sys.exit(main())

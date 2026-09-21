#!/usr/bin/env python3
"""Clean up after removing the Hermes XMPP plugin.

Run this AFTER ``hermes plugins remove xmpp-platform`` to remove what the core
installer deliberately leaves behind:

  * the ``display.platforms.xmpp.tool_progress_grouping`` key in config.yaml
  * the stale ``xmpp-platform`` / ``platforms/xmpp`` entries in
    ``plugins.enabled`` and ``plugins.disabled``
  * (optionally) the OMEMO key/session store at ``sessions/omemo.json``

It deliberately does NOT touch the ``XMPP_*`` variables in your profile ``.env``
(credentials, allowlist, home channel, avatar) or the core pairing grants for
previously-approved users; those are yours to keep or delete by hand, and this
script prints the exact commands if you want them fully gone.

Usage:
    python3 post_uninstall.py [options]

Safe to re-run: it only removes keys this plugin owns and collapses blocks it
left empty.
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
    backup_file,
    get_hermes_home,
    get_profile_dir,
    remove_plugin_enabled_entries,
    remove_xmpp_display_defaults,
)

_ENV_VARS = (
    "XMPP_USER_JID",
    "XMPP_PASSWORD",
    "XMPP_ALLOWED_USERS",
    "XMPP_ALLOW_ALL_USERS",
    "XMPP_HOME_CHANNEL",
    "XMPP_AVATAR_PATH",
    "XMPP_SERVER",
    "XMPP_PORT",
    "XMPP_OMEMO_ENABLED",
    "XMPP_OMEMO_ALLOW_UNTRUSTED",
    "XMPP_ALLOW_PRIVATE_DOWNLOADS",
)


def fail(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def _env_has(env_path: Path, key: str) -> bool:
    if not env_path.exists():
        return False
    for line in env_path.read_text().splitlines():
        if "=" in line and line.split("=", 1)[0].strip() == key:
            return True
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean up after 'hermes plugins remove xmpp-platform'."
    )
    parser.add_argument("--hermes-home", help="Hermes home directory (default: ~/.hermes)")
    parser.add_argument("--profile", default=None, help="Hermes profile name")
    parser.add_argument(
        "--omemo", action="store_true",
        help="Also delete the OMEMO key/session store (sessions/omemo.json).",
    )
    parser.add_argument(
        "--non-interactive", action="store_true",
        help="Never prompt; makes only the safe, reversible removals.",
    )
    args = parser.parse_args(argv)

    try:
        hermes_home = get_hermes_home(args.hermes_home)
        profile_dir = get_profile_dir(hermes_home, args.profile)
    except FileNotFoundError as exc:
        fail(str(exc))

    config_path = profile_dir / "config.yaml"
    env_path = profile_dir / ".env"
    omemo_path = hermes_home / "sessions" / "omemo.json"

    print("=" * 60)
    print("Hermes XMPP Plugin - Post-Uninstall Cleanup")
    print("=" * 60)
    print(f"Hermes home:   {hermes_home}")
    print(f"Profile dir:   {profile_dir}")

    # 1. Config: tool-progress key + stale plugin entries.
    if config_path.exists():
        backup_path = backup_file(config_path, ".postuninstall-backup")
        print(f"Backed up config to {backup_path}")
        text = config_path.read_text()

        new_text = remove_xmpp_display_defaults(text)
        if new_text != text:
            text = new_text
            print("Removed display.platforms.xmpp.tool_progress_grouping.")
        else:
            print("No tool-progress key to remove.")

        new_text = remove_plugin_enabled_entries(text)
        if new_text != text:
            text = new_text
            print("Removed stale plugins.enabled / plugins.disabled entries.")
        else:
            print("No stale plugins.enabled / plugins.disabled entries.")

        if text != config_path.read_text():
            config_path.write_text(text)
    else:
        print(f"No config at {config_path}; nothing to clean there.")

    # 2. OMEMO store (opt-in).
    if omemo_path.exists():
        if args.omemo or (
            not args.non_interactive
            and input("Delete the OMEMO key/session store? [y/N]: ").strip().lower() in ("y", "yes")
        ):
            omemo_path.unlink()
            print(f"Deleted OMEMO store: {omemo_path}")
        else:
            print(f"Kept OMEMO store (use --omemo to delete): {omemo_path}")

    # 3. Report what we deliberately left behind.
    leftover = [v for v in _ENV_VARS if _env_has(env_path, v)]
    print()
    if leftover:
        print("Left in place (yours to keep or delete):")
        for v in leftover:
            print(f"  - {v}")
        print()
        print("To remove them fully, edit the profile .env:")
        print(f"  {env_path}")
        print("and delete those lines. You can also remove any approved users:")
        print("  hermes pairing list   (see what is approved)")
    else:
        print("No XMPP_* variables found in the profile .env.")

    print()
    print("Post-uninstall complete.")
    print("Restart the gateway to finish:")
    print("  hermes gateway restart")
    return 0


if __name__ == "__main__":
    sys.exit(main())

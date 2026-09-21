"""Common helpers for the Hermes XMPP plugin post-install script.

These helpers deliberately avoid heavy dependencies like PyYAML/ruamel.yaml
so the script can run in a clean environment. They operate on
~/.hermes/config.yaml with regex-based mutations that preserve comments and
formatting as much as possible.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Optional

DEFAULT_HERMES_HOME = Path.home() / ".hermes"


def get_hermes_home(cli_value: Optional[str] = None) -> Path:
    """Resolve the Hermes home directory.

    Priority:
    1. CLI --hermes-home argument
    2. $HERMES_HOME environment variable
    3. Default ~/.hermes
    """
    if cli_value:
        path = Path(cli_value).expanduser().resolve()
    elif os.environ.get("HERMES_HOME"):
        path = Path(os.environ["HERMES_HOME"]).expanduser().resolve()
    else:
        path = DEFAULT_HERMES_HOME

    return path


def get_profile_dir(hermes_home: Path, profile: Optional[str] = None) -> Path:
    """Return the active profile directory.

    If a profile name is provided, use it. Otherwise check $HERMES_PROFILE,
    then look for a sticky default in ~/.hermes/active_profile. Fall back to
    the base hermes_home.
    """
    if profile:
        return hermes_home / "profiles" / profile

    env_profile = os.environ.get("HERMES_PROFILE")
    if env_profile:
        return hermes_home / "profiles" / env_profile

    active_file = hermes_home / "active_profile"
    if active_file.exists():
        active_profile = active_file.read_text().strip()
        if active_profile:
            return hermes_home / "profiles" / active_profile

    return hermes_home


def backup_file(path: Path, suffix: str) -> Path:
    """Create a numbered backup of path."""
    backup_path = path.with_suffix(path.suffix + suffix)
    if backup_path.exists():
        for i in range(1, 100):
            numbered = path.with_suffix(f"{path.suffix}{suffix}.{i}")
            if not numbered.exists():
                backup_path = numbered
                break
    shutil.copy2(path, backup_path)
    return backup_path


def _find_block_bounds(text: str, key: str) -> tuple[int, int]:
    """Return the start/end line indices of a top-level YAML block."""
    pattern = re.compile(rf"^{re.escape(key)}:\s*", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return -1, -1

    start = text[: match.start()].count("\n")
    lines = text.splitlines()
    end = len(lines)

    parent_indent = len(lines[start]) - len(lines[start].lstrip())
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.strip() == "":
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= parent_indent and not line.lstrip().startswith("#"):
            end = i
            break

    return start, end


def add_xmpp_display_defaults(config_text: str) -> str:
    """Ensure XMPP uses one-message-per-tool progress (no XEP-0308 edits).

    The gateway's default tool-progress grouping is ``accumulate`` (edit one
    growing bubble). XMPP's only edit primitive, XEP-0308 Last Message
    Correction, can replace only the immediately-previous message, so an
    accumulate bubble is refused (``not the last message``) whenever
    commentary, an OMEMO re-key stanza, or media lands between tool calls.
    ``separate`` renders each tool as its own message with no edits, which is
    the only grouping XMPP can deliver reliably.

    Writes ``display.platforms.xmpp.tool_progress_grouping: separate``. An
    existing explicit user value is preserved (overwrite=False), so this never
    clobbers a deliberate choice.
    """
    key = "tool_progress_grouping"
    value = "separate"

    # Already set anywhere under display.platforms.xmpp -> leave untouched.
    if _nested_key_exists(config_text, ("display", "platforms", "xmpp"), key):
        return config_text

    lines = config_text.splitlines()

    # Ensure the top-level display: block.
    dstart, dend = _find_block_bounds(config_text, "display")
    if dstart < 0:
        block = (
            "display:\n"
            "  platforms:\n"
            "    xmpp:\n"
            f"      {key}: {value}\n"
        )
        return config_text.rstrip() + "\n\n" + block + "\n"

    dlines = lines[dstart:dend]
    disp_body = _body_indent(dlines) or 2

    # Find platforms: sub-block inside display, if any.
    pstart, pend = _find_indented_block(dlines, "platforms")
    if pstart < 0:
        sub = (
            f"{' ' * disp_body}platforms:\n"
            f"{' ' * (disp_body + 2)}xmpp:\n"
            f"{' ' * (disp_body + 4)}{key}: {value}\n"
        )
        dlines = dlines[:] + sub.splitlines()
        lines[dstart:dend] = dlines
        return "\n".join(lines) + "\n"

    plines = dlines[pstart:pend]
    plat_body = _body_indent(plines) or (disp_body + 2)

    # Find xmpp: sub-block inside platforms, if any.
    xstart, xend = _find_indented_block(plines, "xmpp")
    if xstart < 0:
        sub = (
            f"{' ' * plat_body}xmpp:\n"
            f"{' ' * (plat_body + 2)}{key}: {value}\n"
        )
        plines = plines[:] + sub.splitlines()
    else:
        xlines = plines[xstart:xend]
        xbody = _body_indent(xlines) or (plat_body + 2)
        if _block_has_key(xlines, key):
            return config_text
        xlines = xlines[:] + [f"{' ' * xbody}{key}: {value}"]
        plines[xstart:xend] = xlines

    dlines[pstart:pend] = plines
    lines[dstart:dend] = dlines
    return "\n".join(lines) + "\n"


def _body_indent(block_lines: list) -> int | None:
    """Indent of the first non-empty body line (keys inside a block)."""
    for ln in block_lines[1:]:
        if ln.strip():
            return len(ln) - len(ln.lstrip())
    return None


def _find_indented_block(lines: list, key: str) -> tuple[int, int]:
    """Locate an INDENTED ``key:`` sub-block within ``lines``; returns (start, end)."""
    for i, line in enumerate(lines):
        m = re.match(rf"^(\s+){re.escape(key)}:\s*$", line)
        if not m:
            continue
        indent = len(m.group(1))
        end = len(lines)
        for j in range(i + 1, len(lines)):
            lj = lines[j]
            if lj.strip() == "":
                continue
            if len(lj) - len(lj.lstrip()) <= indent and not lj.lstrip().startswith("#"):
                end = j
                break
        return i, end
    return -1, -1


def _block_has_key(lines: list, key: str) -> bool:
    return any(re.match(rf"^\s+{re.escape(key)}:", ln) for ln in lines)


def _nested_key_exists(config_text: str, path: tuple, key: str) -> bool:
    """True when ``path[0].path[1]...path[n].<key>`` exists (each level indented)."""
    lines = config_text.splitlines()
    cur = lines
    for level in path:
        start, end = _find_indented_block(cur, level)
        if start < 0:
            return False
        cur = cur[start:end]
    return _block_has_key(cur, key)


def validate_avatar_path(path: str) -> tuple[bool, str]:
    """Return (ok, message) for a proposed avatar path.

    A blank path is always valid (no avatar). Otherwise the file must exist
    and be a regular file so a typo is caught at install time instead of
    surfacing as a repeated "avatar path does not exist" warning on every
    gateway restart.
    """
    if not path:
        return True, ""
    p = Path(path).expanduser()
    if not p.exists():
        return False, f"Avatar path does not exist: {p}"
    if not p.is_file():
        return False, f"Avatar path is not a file: {p}"
    return True, ""


# ---- Uninstall cleanup helpers (used by post_uninstall.py) ----

def remove_xmpp_display_defaults(config_text: str) -> str:
    """Remove ``display.platforms.xmpp.tool_progress_grouping`` and collapse
    any ``xmpp``/``platforms`` sub-block left empty under ``display``.

    Only the display key post_install writes is removed; a user's own explicit
    ``platforms.xmpp`` block (top-level) and every other display key are left
    untouched. Returns config_text unchanged when nothing matches.
    """
    key = "tool_progress_grouping"
    dstart, dend = _find_block_bounds(config_text, "display")
    if dstart < 0:
        return config_text

    lines = config_text.splitlines()
    dlines = lines[dstart:dend]

    pstart, pend = _find_indented_block(dlines, "platforms")
    if pstart < 0:
        return config_text
    plines = dlines[pstart:pend]

    xstart, xend = _find_indented_block(plines, "xmpp")
    if xstart < 0:
        return config_text
    xlines = plines[xstart:xend]

    # Drop only the tool_progress_grouping line from the xmpp block.
    kept = [
        ln
        for ln in xlines
        if not re.match(rf"^\s+{re.escape(key)}:", ln)
    ]
    changed = len(kept) != len(xlines)
    xlines = kept

    # Collapse the xmpp block if it now holds nothing but the header line.
    if _block_is_header_only(xlines):
        plines[xstart:xend] = []
        changed = True
    else:
        plines[xstart:xend] = xlines

    # Collapse the platforms block if it now holds nothing but its header.
    if _block_is_header_only(plines):
        dlines[pstart:pend] = []
        changed = True
    else:
        dlines[pstart:pend] = plines

    # Collapse the display block if it now holds nothing but its header.
    if _block_is_header_only(dlines):
        lines[dstart:dend] = []
        changed = True
    else:
        lines[dstart:dend] = dlines

    if not changed:
        return config_text

    result = "\n".join(lines)
    result = re.sub(r"\n\n\n+", "\n\n", result)
    return result.rstrip() + ("\n" if config_text.endswith("\n") else "")


def _block_is_header_only(block_lines: list) -> bool:
    """True when *block_lines* holds only its header line (index 0) plus
    blank/comment lines, i.e. the block has no real body and can be dropped."""
    return all(
        not ln.strip() or ln.lstrip().startswith("#")
        for ln in block_lines[1:]
    )


def remove_plugin_enabled_entries(config_text: str) -> str:
    """Remove this plugin's keys from ``plugins.enabled`` and ``plugins.disabled``.

    Accepts both the canonical ``xmpp-platform`` and the legacy ``platforms/xmpp``
    key in either list. A list left empty is dropped; a ``plugins`` block left
    with no ``enabled``/``disabled`` keys is dropped too.
    """
    keys = {"xmpp-platform", "platforms/xmpp"}

    def _strip_list(block_lines: list, list_key: str) -> list:
        """Return *block_lines* with *keys* removed from the ``list_key`` list.

        Handles both block style (``key:`` then indented ``- item`` lines) and
        flow style (``key: [a, b]``). When no items remain the whole list
        (header + items) is removed; otherwise only the removed items are
        dropped, leaving the ``key:`` header in place.
        """
        out: list = []
        i = 0
        n = len(block_lines)
        while i < n:
            ln = block_lines[i]
            m = re.match(rf"^(\s+){re.escape(list_key)}:(.*)$", ln)
            if not m:
                out.append(ln)
                i += 1
                continue
            indent = len(m.group(1))
            rest = m.group(2)
            # Flow style: ``enabled: [a, b]``.
            if rest.strip().startswith("["):
                inner = rest.strip()[1:-1]
                items = [it.strip().strip("\"'") for it in inner.split(",") if it.strip()]
                kept = [it for it in items if it not in keys]
                if kept:
                    out.append(f"{' ' * indent}{list_key}: [" + ", ".join(kept) + "]")
                i += 1
                continue
            # Block style: the key line is bare; items follow at deeper indent.
            j = i + 1
            while j < n:
                nxt = block_lines[j]
                if nxt.strip() == "":
                    j += 1
                    continue
                if (len(nxt) - len(nxt.lstrip())) > indent and re.match(r"^\s+-", nxt):
                    j += 1
                    continue
                break
            kept_items = []
            for k in range(i + 1, j):
                kln = block_lines[k]
                m2 = re.match(r"^\s+-\s+(\S+)", kln)
                if m2 and m2.group(1).strip("\"'") not in keys:
                    kept_items.append(kln)
            if kept_items:
                out.append(ln)
                out.extend(kept_items)
            # else: drop the header + items entirely.
            i = j
        return out

    lines = config_text.splitlines()

    # Split into segments; each top-level ``plugins:`` block becomes its own
    # isolated line list so mutations never shift indices of later blocks.
    block_starts = [
        i for i, ln in enumerate(lines) if re.match(r"^plugins:\s*$", ln)
    ]
    # Determine each block's end (next top-level non-blank, non-comment line).
    segments: list[tuple[int, int]] = []
    for start in block_starts:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            ln = lines[j]
            if ln.strip() == "":
                continue
            if not ln.startswith((" ", "\t")) and not ln.lstrip().startswith("#"):
                end = j
                break
        segments.append((start, end))

    # Process blocks last-to-first so earlier indices stay valid after edits.
    for start, end in reversed(segments):
        block = lines[start:end]
        for list_key in ("enabled", "disabled"):
            block = _strip_list(block, list_key)
        if _block_is_header_only(block):
            lines[start:end] = []
        else:
            lines[start:end] = block

    result = "\n".join(lines)
    result = re.sub(r"\n\n\n+", "\n\n", result)
    return result.rstrip() + ("\n" if config_text.endswith("\n") else "")


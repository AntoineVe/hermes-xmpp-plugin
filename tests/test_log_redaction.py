"""Regression tests for AES-GCM key redaction in adapter logs (XEP-0454).

``aesgcm://`` URLs carry their decryption key in the URL fragment. The
helpers under test (``_log_safe_url``, ``_redact_aesgcm_in_text``) must be
applied at every call site that logs raw bodies, display texts or download
URLs, otherwise the key leaks into production logs.

The adapter imports the Hermes host framework (``gateway.*``) and the
transcription helper, which are not installable in the test environment.
Lightweight stubs are installed first so the module-level helpers can be
imported; if the real framework is importable, the stubs are skipped.

Driving the full ``_on_message`` path would require a wired-up slixmpp
client, so the call sites themselves are pinned by source assertions:
they must route through the redaction helpers.
"""

import sys
import time
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _install_gateway_stubs() -> None:
    """Stub the Hermes host framework modules missing from the test env."""
    try:
        import gateway  # noqa: F401

        return  # Real framework available; keep it.
    except ModuleNotFoundError:
        pass

    from enum import Enum

    class Platform(str, Enum):
        XMPP = "xmpp"

    class MessageType(str, Enum):
        TEXT = "text"
        PHOTO = "photo"
        AUDIO = "audio"
        VIDEO = "video"
        FILE = "file"
        VOICE = "voice"

    class BasePlatformAdapter:
        pass

    class MessageEvent:
        pass

    class SendResult:
        pass

    gateway = types.ModuleType("gateway")
    config = types.ModuleType("gateway.config")
    config.Platform = Platform
    platforms = types.ModuleType("gateway.platforms")
    shared = types.ModuleType("gateway.platforms._shared")
    shared.get_scoped_secret = lambda *args, **kwargs: None
    shared.yaml_env_setter = None
    base = types.ModuleType("gateway.platforms.base")
    base.BasePlatformAdapter = BasePlatformAdapter
    base.MessageEvent = MessageEvent
    base.MessageType = MessageType
    base.SendResult = SendResult
    base.cache_media_bytes = lambda *args, **kwargs: None
    base.validate_inbound_media_size = lambda *args, **kwargs: None
    tools = types.ModuleType("tools")
    transcription = types.ModuleType("tools.transcription_tools")
    transcription.transcribe_audio = lambda *args, **kwargs: None

    gateway.config = config
    gateway.platforms = platforms
    platforms._shared = shared
    platforms.base = base
    tools.transcription_tools = transcription

    for name, module in {
        "gateway": gateway,
        "gateway.config": config,
        "gateway.platforms": platforms,
        "gateway.platforms._shared": shared,
        "gateway.platforms.base": base,
        "tools": tools,
        "tools.transcription_tools": transcription,
    }.items():
        sys.modules[name] = module


_install_gateway_stubs()

import adapter  # noqa: E402

# Sentinel key: deliberately distinct from the "<redacted>" marker so its
# absence can be asserted verbatim in every test below.
_KEY = "SENTINEL_KEY_abc123"

# ``_log_safe_url`` is the call-site-facing alias of ``_redact_aesgcm_url``
# and must behave identically; every URL-level case below runs on both.
_BOTH_REDACT_FNS = pytest.mark.parametrize(
    "redact_fn",
    [adapter._log_safe_url, adapter._redact_aesgcm_url],
    ids=["log_safe_url", "redact_aesgcm_url"],
)


class TestRedactAesgcmInText:
    """Unit tests for adapter._redact_aesgcm_in_text."""

    def test_text_without_aesgcm_url_unchanged(self):
        text = "plain message with https://example.com/page and no secrets"
        assert adapter._redact_aesgcm_in_text(text) == text

    def test_single_aesgcm_url_fragment_redacted(self):
        text = f"see aesgcm://upload.example.com/file.aesgcm#{_KEY} end"
        result = adapter._redact_aesgcm_in_text(text)
        assert _KEY not in result
        assert "<redacted>" in result
        assert result == "see aesgcm://upload.example.com/file.aesgcm#<redacted> end"

    def test_multiple_aesgcm_urls_all_redacted(self):
        text = (
            f"aesgcm://host-one.tld/a.aesgcm#{_KEY} mid "
            f"aesgcm://host-two.tld/b.aesgcm#{_KEY} tail"
        )
        result = adapter._redact_aesgcm_in_text(text)
        assert _KEY not in result
        assert result.count("<redacted>") == 2
        assert "host-one.tld" in result
        assert "host-two.tld" in result

    def test_aesgcm_url_without_fragment_unchanged(self):
        text = "look at aesgcm://upload.example.com/file.aesgcm please"
        assert adapter._redact_aesgcm_in_text(text) == text

    def test_empty_text_returned_as_is(self):
        assert adapter._redact_aesgcm_in_text("") == ""

    def test_none_returned_as_is(self):
        assert adapter._redact_aesgcm_in_text(None) is None

    def test_plain_text_without_url_unchanged(self):
        assert adapter._redact_aesgcm_in_text("hello world") == "hello world"

    def test_single_url_key_redacted_in_text(self):
        text = f"see aesgcm://host/f#{_KEY} now"
        result = adapter._redact_aesgcm_in_text(text)
        assert _KEY not in result
        assert "<redacted>" in result

    def test_multiple_urls_distinct_keys_all_redacted(self):
        text = f"aesgcm://h1/f#{_KEY}1 and aesgcm://h2/f#{_KEY}2"
        result = adapter._redact_aesgcm_in_text(text)
        assert f"{_KEY}1" not in result
        assert f"{_KEY}2" not in result
        assert _KEY not in result
        assert result.count("<redacted>") == 2

    def test_trailing_punctuation_does_not_leak_key(self):
        # The "." may be swallowed by the masked fragment; the key must not leak.
        text = f"aesgcm://host/f#{_KEY}."
        result = adapter._redact_aesgcm_in_text(text)
        assert _KEY not in result
        assert result.startswith("aesgcm://host/f#")

    def test_closing_quote_preserved_and_key_redacted(self):
        text = f'aesgcm://host/f#{_KEY}"'
        result = adapter._redact_aesgcm_in_text(text)
        assert _KEY not in result
        assert result.endswith('"')
        assert "<redacted>" in result

    def test_redaction_is_idempotent(self):
        text = f"see aesgcm://host/f#{_KEY} and aesgcm://h2/f#{_KEY} end"
        once = adapter._redact_aesgcm_in_text(text)
        assert adapter._redact_aesgcm_in_text(once) == once
        assert _KEY not in once

    def test_large_text_with_many_urls_redacted_quickly(self):
        # 200 KB of text carrying 50 keyed URLs must redact in < 2 seconds.
        padding = "x" * (200 * 1024 // 50)
        text = "".join(
            f"{padding} aesgcm://host{i}/file{i}.aesgcm#{_KEY} " for i in range(50)
        )
        assert len(text) >= 200 * 1024
        start = time.perf_counter()
        result = adapter._redact_aesgcm_in_text(text)
        elapsed = time.perf_counter() - start
        assert _KEY not in result
        assert result.count("<redacted>") == 50
        assert elapsed < 2.0


class TestLogSafeUrl:
    """Sanity tests for adapter._log_safe_url used by the redaction helper."""

    def test_aesgcm_fragment_redacted(self):
        url = f"aesgcm://upload.example.com/file.aesgcm#{_KEY}"
        result = adapter._log_safe_url(url)
        assert _KEY not in result
        assert result == "aesgcm://upload.example.com/file.aesgcm#<redacted>"

    def test_plain_https_url_unchanged(self):
        url = "https://upload.example.com/file.aesgcm"
        assert adapter._log_safe_url(url) == url

    def test_empty_url_returned_as_is(self):
        assert adapter._log_safe_url("") == ""

    @_BOTH_REDACT_FNS
    def test_valid_url_fragment_redacted(self, redact_fn):
        result = redact_fn(f"aesgcm://host/file.aesgcm#{_KEY}")
        assert _KEY not in result
        assert result == "aesgcm://host/file.aesgcm#<redacted>"

    @_BOTH_REDACT_FNS
    def test_malformed_authority_redacted_without_exception(self, redact_fn):
        # The pre-rewrite urlparse-based helper blew up on this input.
        result = redact_fn(f"aesgcm://[invalid]/file#{_KEY}")
        assert _KEY not in result
        assert result == "aesgcm://[invalid]/file#<redacted>"

    @_BOTH_REDACT_FNS
    def test_uppercase_scheme_redacted(self, redact_fn):
        result = redact_fn(f"AESGCM://Host/File#{_KEY}")
        assert _KEY not in result
        assert result == "AESGCM://Host/File#<redacted>"

    @_BOTH_REDACT_FNS
    def test_mixed_case_scheme_redacted(self, redact_fn):
        result = redact_fn(f"AesGcm://Host/File#{_KEY}")
        assert _KEY not in result
        assert result == "AesGcm://Host/File#<redacted>"

    @_BOTH_REDACT_FNS
    def test_url_without_fragment_unchanged(self, redact_fn):
        assert redact_fn("aesgcm://host/file") == "aesgcm://host/file"

    @_BOTH_REDACT_FNS
    def test_https_url_with_fragment_unchanged(self, redact_fn):
        url = "https://host/file#frag"
        assert redact_fn(url) == url

    @_BOTH_REDACT_FNS
    def test_empty_string_unchanged(self, redact_fn):
        assert redact_fn("") == ""

    @_BOTH_REDACT_FNS
    def test_none_url_returned_as_is(self, redact_fn):
        assert redact_fn(None) is None

    @_BOTH_REDACT_FNS
    def test_multiple_hash_signs_only_first_preserved(self, redact_fn):
        result = redact_fn(f"aesgcm://host/file#a#{_KEY}")
        assert _KEY not in result
        assert result == "aesgcm://host/file#<redacted>"
        assert result.count("#") == 1

    @_BOTH_REDACT_FNS
    def test_bare_scheme_without_fragment_unchanged(self, redact_fn):
        assert redact_fn("aesgcm://") == "aesgcm://"

    @_BOTH_REDACT_FNS
    def test_empty_fragment_redacted(self, redact_fn):
        result = redact_fn("aesgcm://host/file#")
        assert result == "aesgcm://host/file#<redacted>"

    @_BOTH_REDACT_FNS
    def test_redaction_is_idempotent(self, redact_fn):
        url = f"aesgcm://host/file.aesgcm#{_KEY}"
        once = redact_fn(url)
        assert redact_fn(once) == once
        assert _KEY not in once


class TestCallSitesRedactKeys:
    """Pin the leak-prone call sites to the redaction helpers.

    A full behavioral test would need a wired-up slixmpp client; these
    source assertions guarantee the regression cannot silently come back.
    """

    source = (REPO_ROOT / "adapter.py").read_text(encoding="utf-8")

    def test_download_failure_warning_is_redacted(self):
        assert 'logger.warning("XMPP: failed to download media from %s", _log_safe_url(url))' in self.source
        assert 'logger.warning("XMPP: failed to download media from %s", url)' not in self.source

    def test_body_debug_log_is_redacted(self):
        assert "_redact_aesgcm_in_text(body)" in self.source

    def test_display_text_debug_log_is_redacted(self):
        assert "_redact_aesgcm_in_text(display_text)" in self.source

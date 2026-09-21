"""Hermes XMPP platform plugin.

Python dependencies are declared in ``pyproject.toml`` and installed into the
Hermes venv by the native ``hermes plugins install`` command; the plugin does
not vendor its own dependency tree.
"""

__version__ = "2.0.0"

from .adapter import register

__all__ = ["register", "__version__"]

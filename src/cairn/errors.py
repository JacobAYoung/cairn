"""Cairn's exception hierarchy.

Everything Cairn raises on an expected, user-actionable problem derives from :class:`CairnError`.
The CLI catches that base type and turns it into a clean non-zero exit with the message — so
command code can ``raise ConfigError("...")`` and trust the boundary to present it well, rather
than printing and exiting itself.
"""

from __future__ import annotations


class CairnError(Exception):
    """Base for all expected, user-facing Cairn errors."""


class ConfigError(CairnError):
    """A config file is missing a required value, malformed, or has an invalid setting."""

"""The configuration package, re-exporting the suite's settings.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains no logic. It re-exports ``Settings`` and the desktop, mobile
and breakpoint constants from ``config.settings`` so callers import them from
``config``.

Fixtures in ``conftest.py`` and the Page Objects import from here. An import
error here stops collection before any test runs.

Specified by ``README.md`` section "Configuration".
"""

from config.settings import (
    DESKTOP_VIEWPORT,
    MOBILE_BREAKPOINT_PX,
    MOBILE_VIEWPORT,
    Settings,
)

__all__ = ["DESKTOP_VIEWPORT", "MOBILE_BREAKPOINT_PX", "MOBILE_VIEWPORT", "Settings"]

"""Runtime configuration for the suite, read once from the environment.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains the ``Settings`` dataclass and its ``from_env`` constructor;
the viewport, breakpoint and timeout constants every layout and assertion check
uses; the two prompt-size bounds of the Claude diagnostics hook; the list of
foreign report paths the crawler skips; and the private ``_env_flag`` and
``_env_int`` readers.

``conftest.py`` builds one ``Settings`` per session, before any browser starts,
and every fixture, Page Object and crawler reads its values from there. A wrong
value here therefore misdirects the whole run, not one test: test modules never
read ``os.environ`` themselves.

**Bad input falls back, never raises.** An unset, empty or malformed variable
resolves to its module default, so a plain ``pytest`` run with no ``.env`` and
no CI secrets works unchanged. A local ``.env`` file is loaded on import when
present; in CI the runner injects the variables and the load does nothing.

**Diagnostics need two things.** The Claude hook is enabled only when
``AI_DIAGNOSTICS_ENABLED`` is truthy and an API key is present, so a fork
without secrets never fails on a missing credential.

Specified by ``README.md`` section "Configuration".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final
from urllib.parse import urljoin

from dotenv import load_dotenv

# OPTIONAL LOCAL FILE. Loads a developer's ``.env`` when one exists and does
# nothing otherwise, which is the CI case.
load_dotenv()

DEFAULT_BASE_URL: Final[str] = "https://apolskiy.github.io/"

#: DESKTOP TIER. The viewport every desktop-side layout assertion runs at.
DESKTOP_VIEWPORT: Final[dict[str, int]] = {"width": 1920, "height": 1080}

#: MOBILE TIER. The viewport every mobile-side layout assertion runs at
#: (iPhone 14 Pro logical pixels).
MOBILE_VIEWPORT: Final[dict[str, int]] = {"width": 390, "height": 844}

#: THE SITE'S BREAKPOINT, its stylesheet's ``max-width``. Any viewport at or
#: below this width must render the stacked mobile layout.
MOBILE_BREAKPOINT_PX: Final[int] = 600

#: FOREIGN, per ``README.md`` section "Coverage Summary" (added 2026-11-10).
#: Path prefixes on this site's host that hold reports another repository
#: publishes. The crawler does not follow them and the weekly link check
#: resolves them as outbound targets. The Test Insights report is not listed
#: and is crawled like any page.
FOREIGN_REPORT_PATH_PREFIXES: Final[tuple[str, ...]] = ("/AP-Harness-QC/", "/AP-Model-QC/")

#: DEFAULT CEILING for Playwright's auto-retrying web-first assertions.
DEFAULT_EXPECT_TIMEOUT_MS: Final[int] = 10_000

#: BOUNDED, per ``README.md`` section "Configuration". The most DOM snapshot
#: characters handed to the Claude diagnostics hook.
MAX_DOM_SNAPSHOT_CHARS: Final[int] = 40_000

#: BOUNDED, per ``README.md`` section "Configuration" (added 2026-08-11). The
#: most browser error log characters handed to the same hook.
MAX_DIAGNOSTICS_CHARS: Final[int] = 8_000


def _env_flag(name: str, *, default: bool = False) -> bool:
    """Return an environment variable read as a boolean flag.

    Args:
        name (str): The environment variable to read.
        default (bool): The value when the variable is unset or empty.

    Returns:
        bool: True when the value is ``1``, ``true``, ``yes`` or ``on`` in any
        case, False for any other non-empty value.
    """
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    """Return an environment variable read as a positive integer.

    Args:
        name (str): The environment variable to read.
        default (int): The value when the variable is unset, not an integer,
            or not positive.

    Returns:
        int: The parsed integer, or ``default`` when it does not parse to a
        positive integer.
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


@dataclass(frozen=True)
class Settings:
    """Hold the suite's runtime configuration as one frozen snapshot.

    Attributes:
        base_url (str): The root URL of the application under test, always
            ending in a slash.
        claude_api_key (str | None): The Anthropic API key the diagnostics hook
            uses, or None when the environment carries none.
        claude_model (str): The model identifier used for failure triage.
        ai_diagnostics_enabled (bool): Whether the Claude diagnostics hook runs.
        expect_timeout_ms (int): The default timeout of web-first assertions.
    """

    base_url: str
    claude_api_key: str | None
    claude_model: str
    ai_diagnostics_enabled: bool
    expect_timeout_ms: int

    @classmethod
    def from_env(cls) -> "Settings":
        """Return settings built from the current process environment.

        Returns:
            Settings: A frozen instance. Each missing variable falls back to its
            module default, so a plain ``pytest`` run needs no configuration.
        """
        base_url = os.getenv("BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or None
        return cls(
            base_url=base_url if base_url.endswith("/") else f"{base_url}/",
            claude_api_key=api_key,
            claude_model=os.getenv("CLAUDE_MODEL", "claude-opus-5").strip() or "claude-opus-5",
            # Decided 2026-07-28: diagnostics stay off unless enabled AND a key is
            # present, so a fork without secrets never fails on a credential.
            ai_diagnostics_enabled=_env_flag("AI_DIAGNOSTICS_ENABLED") and api_key is not None,
            expect_timeout_ms=_env_int("EXPECT_TIMEOUT_MS", DEFAULT_EXPECT_TIMEOUT_MS),
        )

    def resolve_url(self, path: str = "") -> str:
        """Return a relative path joined onto :attr:`base_url`.

        Args:
            path (str): The relative path. An empty string yields the base URL.

        Returns:
            str: The absolute URL of the path.
        """
        return urljoin(self.base_url, path)

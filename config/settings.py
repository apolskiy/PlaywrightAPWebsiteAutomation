"""Environment-driven runtime configuration for the E2E automation framework.

All tunable values (target URL, viewport geometry, Claude diagnostics credentials)
are resolved once from the process environment - optionally hydrated from a local
``.env`` file - so that test modules never read ``os.environ`` directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final
from urllib.parse import urljoin

from dotenv import load_dotenv

# Load a developer-local .env file if present. In CI the variables are injected
# by the workflow runner, and load_dotenv() is a no-op when no file exists.
load_dotenv()

DEFAULT_BASE_URL: Final[str] = "https://apolskiy.github.io/"

#: Viewport used for all desktop-tier assertions.
DESKTOP_VIEWPORT: Final[dict[str, int]] = {"width": 1920, "height": 1080}

#: Viewport used for all mobile-tier assertions (iPhone 14 Pro logical pixels).
MOBILE_VIEWPORT: Final[dict[str, int]] = {"width": 390, "height": 844}

#: The ``max-width`` breakpoint declared by the site stylesheet. Any viewport at
#: or below this width must render the stacked mobile layout.
MOBILE_BREAKPOINT_PX: Final[int] = 600

#: Default ceiling for Playwright's auto-retrying web-first assertions.
DEFAULT_EXPECT_TIMEOUT_MS: Final[int] = 10_000

#: Upper bound on the DOM snapshot handed to the Claude diagnostics hook. Keeps
#: token spend bounded when a failure occurs on a very large page.
MAX_DOM_SNAPSHOT_CHARS: Final[int] = 40_000

#: Upper bound on the browser error log handed to the same hook. Far smaller
#: than the DOM bound because the log is already a summary - but it is not
#: bounded by the page, and a request loop or a script erroring on every frame
#: can produce thousands of near-identical lines.
MAX_DIAGNOSTICS_CHARS: Final[int] = 8_000


def _env_flag(name: str, *, default: bool = False) -> bool:
    """Interpret an environment variable as a boolean flag.

    Args:
        name: Name of the environment variable to read.
        default: Value returned when the variable is unset or empty.

    Returns:
        ``True`` when the raw value is one of ``1``, ``true``, ``yes`` or ``on``
        (case-insensitive); ``False`` for any other non-empty value.
    """
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    """Read a positive integer environment variable, falling back on bad input.

    Args:
        name: Name of the environment variable to read.
        default: Value returned when the variable is unset or not a valid
            positive integer.

    Returns:
        The parsed integer, or ``default`` when parsing fails.
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
    """Immutable snapshot of the framework's runtime configuration.

    Attributes:
        base_url: Root URL of the application under test, always slash-terminated.
        claude_api_key: Anthropic API key used by the AI diagnostics hook, or
            ``None`` when no key is available in the environment.
        claude_model: Model identifier used for failure triage.
        ai_diagnostics_enabled: Master switch for the Claude diagnostics hook.
        expect_timeout_ms: Default timeout applied to web-first assertions.
    """

    base_url: str
    claude_api_key: str | None
    claude_model: str
    ai_diagnostics_enabled: bool
    expect_timeout_ms: int

    @classmethod
    def from_env(cls) -> "Settings":
        """Build a settings instance from the current process environment.

        Returns:
            A fully populated, frozen :class:`Settings` instance. Missing
            variables fall back to the module-level defaults so that a plain
            ``pytest`` invocation works with no configuration at all.
        """
        base_url = os.getenv("BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or None
        return cls(
            base_url=base_url if base_url.endswith("/") else f"{base_url}/",
            claude_api_key=api_key,
            claude_model=os.getenv("CLAUDE_MODEL", "claude-opus-5").strip() or "claude-opus-5",
            # Diagnostics stay off unless explicitly enabled AND a key is present,
            # so a fork without secrets never fails on a missing credential.
            ai_diagnostics_enabled=_env_flag("AI_DIAGNOSTICS_ENABLED") and api_key is not None,
            expect_timeout_ms=_env_int("EXPECT_TIMEOUT_MS", DEFAULT_EXPECT_TIMEOUT_MS),
        )

    def resolve_url(self, path: str = "") -> str:
        """Join a relative path onto :attr:`base_url`.

        Args:
            path: Relative path fragment. An empty string yields the base URL.

        Returns:
            The absolute URL for the requested path.
        """
        return urljoin(self.base_url, path)

"""Auditing of the links a page publishes, separately from the page itself.

This is the one part of the landing-page interaction that is not page
interaction. Everything else a Page Object exposes reads or drives the document
in front of it; these operations issue real HTTP requests to third-party hosts
and merely borrow the browser's request context to do it. That is a different
responsibility with a different failure mode - a rate limiter, a host that is
down, a redirect chain - and it carries state the page has no business owning:
the per-host clock that keeps this suite from tripping the limits it is trying
to observe.

Using the browser's request context rather than a separate HTTP client is
deliberate. It adds no dependency and inherits the browser's redirect handling,
so a target that a real visitor would reach is reported as reachable here.
"""

from __future__ import annotations

import time
from typing import Final
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError, Locator, Page

#: Minimum gap between consecutive requests to the same host, in seconds.
#: Resolving one host's links back-to-back is enough to trip its rate limiter.
OUTBOUND_REQUEST_INTERVAL_SECONDS: Final[float] = 0.4

#: Ceiling on a single outbound request, in milliseconds.
OUTBOUND_REQUEST_TIMEOUT_MS: Final[int] = 20_000


class LinkAuditor:
    """Collects, classifies, and resolves the links a document publishes.

    Args:
        page: The Playwright page whose document is being audited.
        base_url: Absolute URL of the application, used to tell an internal
            target from an outbound one.
    """

    def __init__(self, page: Page, base_url: str) -> None:
        self._page = page
        self._base_url = base_url
        self._last_request_at_host: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    def anchors(self) -> Locator:
        """Locate every anchor in the document, including hidden panels.

        A CSS locator is used here rather than the ``link`` role, and that is
        deliberate. The target is a tabbed single-page application: every panel
        except the active one is ``display: none``, which removes its contents
        from the accessibility tree, so a role-based locator returns only the
        anchors of whichever tab happens to be open - on first load, the profile
        header and the footer alone.

        Link auditing has to cover what the document publishes, not what is
        currently painted, or the project links are never inspected at all. This
        is not hypothetical: the check passed for weeks while inspecting 2 of the
        16 targets the page actually ships.

        Returns:
            A locator resolving to every anchor in the document.
        """
        return self._page.locator("a")

    def published_hrefs(self) -> list[str]:
        """Collect the ``href`` of every anchor on the page.

        Returns:
            One entry per anchor, in document order. Anchors without an ``href``
            contribute an empty string so the caller can flag them.
        """
        anchors = self.anchors()
        return [
            anchors.nth(anchor_index).get_attribute("href") or ""
            for anchor_index in range(anchors.count())
        ]

    def outbound_targets(self) -> list[str]:
        """Collect the distinct off-site ``https`` targets published by the page.

        Returns:
            Unique absolute targets whose host differs from the application's
            own, in first-seen order. Internal page links and ``mailto:`` are
            excluded: neither can rot in a way an HTTP status would reveal.
        """
        own_host = urlparse(self._base_url).netloc
        seen: dict[str, None] = {}
        for href in self.published_hrefs():
            if not href.startswith("https://"):
                continue
            if urlparse(href).netloc == own_host:
                continue
            seen.setdefault(href, None)
        return list(seen)

    def new_tab_count(self) -> int:
        """Count anchors that the decoder marked as opening in a new tab.

        Returns:
            The number of anchors carrying ``target="_blank"``.
        """
        return self._page.locator('a[target="_blank"]').count()

    def unhardened_new_tab_count(self) -> int:
        """Count new-tab anchors missing the ``noopener noreferrer`` hardening.

        Returns:
            The number of ``target="_blank"`` anchors whose ``rel`` attribute
            omits either ``noopener`` or ``noreferrer``. A non-zero result is a
            reverse-tabnabbing exposure.
        """
        return self._page.locator(
            'a[target="_blank"]:not([rel~="noopener"]), '
            'a[target="_blank"]:not([rel~="noreferrer"])'
        ).count()

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def url_status(self, url: str) -> int:
        """Resolve one URL, preferring ``HEAD`` and confirming with ``GET``.

        ``HEAD`` is tried first because the bodies here are large - resolving
        this site's links with ``GET`` transfers several megabytes of HTML that
        is discarded immediately.

        ``HEAD`` support is not universal, though, and a status derived from it
        alone is not trustworthy enough to fail a build on. Measured against the
        targets this site publishes, LinkedIn answers ``405`` to ``HEAD`` while
        answering ``GET``. So the method is only an optimisation for the happy
        path: anything that is not a clean success is re-checked with ``GET``,
        and it is that second answer which is reported.

        Args:
            url: An absolute URL.

        Returns:
            The status a real client would receive.
        """
        status = self._issue_request(url, "head")
        if 200 <= status < 400:
            return status
        return self._issue_request(url, "get")

    def _issue_request(self, url: str, method: str) -> int:
        """Issue one request through the browser's own request context.

        Args:
            url: An absolute URL.
            method: ``"head"`` or ``"get"``.

        Returns:
            The final status code, or ``0`` when the request could not be
            completed at all - a caller cannot distinguish a dead link from a
            dead network without that difference.
        """
        self._pace_request(url)
        try:
            response = getattr(self._page.request, method)(
                url, timeout=OUTBOUND_REQUEST_TIMEOUT_MS
            )
            return int(response.status)
        except PlaywrightError:
            return 0

    def _pace_request(self, url: str) -> None:
        """Hold a minimum gap between consecutive requests to the *same* host.

        Resolving every published link back-to-back is enough to trip GitHub's
        rate limiter, which answers ``429`` on an arbitrary subset of the batch
        and turns a link check into a source of noise.

        The limit being respected is per-host, so the delay is tracked per-host
        too. A global delay would make every target wait on every other, which
        both wastes time and protects nothing: a request to Docker Hub does
        nothing to GitHub's budget. Measured over this site's links, scoping the
        delay per-host cut the batch from 12.8s to 9.5s with no loss of
        protection.

        Args:
            url: The URL about to be requested.
        """
        host = urlparse(url).netloc
        elapsed = time.monotonic() - self._last_request_at_host.get(host, 0.0)
        if elapsed < OUTBOUND_REQUEST_INTERVAL_SECONDS:
            time.sleep(OUTBOUND_REQUEST_INTERVAL_SECONDS - elapsed)
        self._last_request_at_host[host] = time.monotonic()

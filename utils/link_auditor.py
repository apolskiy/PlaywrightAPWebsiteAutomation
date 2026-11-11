"""Collects, classifies and resolves the links a page publishes.

Created: 2026-08-09
Last updated: 2026-11-10

This file contains ``LinkAuditor``, which collects every anchor in a document,
lists its distinct outbound targets, counts the anchors opening a new tab and
those missing ``noopener noreferrer``, and resolves a URL to the HTTP status a
real client would receive. Two constants set the per-host request gap and the
request timeout.

``LandingPage`` owns one auditor as its ``links`` attribute, and the link
checks in ``test_link_obfuscation.py`` read through it. The resolving half
sends real requests to third parties and runs only in the weekly ``external``
check, so a failure there reports link rot and never decides a deploy.

**Anchors are located by CSS, not by the ``link`` role**, so the anchors of
hidden tab panels are included; the role misses everything under
``display: none``.

**Outbound means off-site, plus foreign reports on this host.** ``https``
targets on another host are outbound, and so are the paths listed in
``FOREIGN_REPORT_PATH_PREFIXES``, which the crawler leaves alone. Internal page
links and ``mailto:`` are excluded.

**Resolution tries ``HEAD`` first and confirms with ``GET``.** ``HEAD`` is
tried first because the bodies here are large: resolving this site's links
with ``GET`` alone transfers several megabytes of HTML that is discarded. Any
answer that is not a clean success is re-checked with ``GET``, and that answer
is reported. A request that cannot complete returns ``0``, so a dead network
reads differently from a dead link.

**Requests go through the browser's own request context**, not a separate HTTP
client. That adds no dependency and inherits the browser's redirect handling,
so a target a real visitor would reach is reported as reachable.

**Requests to one host are paced; different hosts are not.** Unpaced, the
batch trips GitHub's rate limiter, which answers ``429`` on an arbitrary subset.

Specified by ``README.md`` section "Key Features" (Outbound Link-Rot Detection
and Link Auditing Covers Hidden Panels).
"""

from __future__ import annotations

import time
from typing import Final
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError, Locator, Page

from config.settings import FOREIGN_REPORT_PATH_PREFIXES

#: PACED PER HOST, per ``README.md`` section "Key Features" (added 2026-07-30).
#: The least gap between consecutive requests to the same host, in seconds.
OUTBOUND_REQUEST_INTERVAL_SECONDS: Final[float] = 0.4

#: BOUNDED. The ceiling of one outbound request, in milliseconds.
OUTBOUND_REQUEST_TIMEOUT_MS: Final[int] = 20_000


class LinkAuditor:
    """Collect, classify and resolve the links a document publishes.

    Args:
        page (Page): The Playwright page whose document is audited.
        base_url (str): The application's absolute URL, which tells an internal
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
        """Return a locator for every anchor in the document, hidden panels included.

        A CSS locator, so anchors inside ``display: none`` panels are found;
        the reason is in ``README.md`` section "Key Features" (Link Auditing
        Covers Hidden Panels).

        Returns:
            Locator: Every anchor in the document.
        """
        return self._page.locator("a")

    def published_hrefs(self) -> list[str]:
        """Return the ``href`` of every anchor on the page.

        Returns:
            list[str]: One entry per anchor, in document order. An anchor
            without an ``href`` contributes an empty string, so the caller can
            flag it.
        """
        anchors = self.anchors()
        return [
            anchors.nth(anchor_index).get_attribute("href") or ""
            for anchor_index in range(anchors.count())
        ]

    def outbound_targets(self) -> list[str]:
        """Return the distinct outbound ``https`` targets the page publishes.

        Returns:
            list[str]: Unique absolute targets in first-seen order: those on
            another host, plus those on this host under
            ``FOREIGN_REPORT_PATH_PREFIXES``. Internal page links and
            ``mailto:`` are excluded.
        """
        own_host = urlparse(self._base_url).netloc
        seen: dict[str, None] = {}
        for href in self.published_hrefs():
            if not href.startswith("https://"):
                continue
            parsed_href = urlparse(href)
            if parsed_href.netloc == own_host and not parsed_href.path.startswith(
                FOREIGN_REPORT_PATH_PREFIXES
            ):
                continue
            seen.setdefault(href, None)
        return list(seen)

    def new_tab_count(self) -> int:
        """Return how many anchors the decoder marked as opening in a new tab.

        Returns:
            int: The number of anchors carrying ``target="_blank"``.
        """
        return self._page.locator('a[target="_blank"]').count()

    def unhardened_new_tab_count(self) -> int:
        """Return how many new-tab anchors lack ``noopener noreferrer``.

        Returns:
            int: The number of ``target="_blank"`` anchors whose ``rel`` omits
            ``noopener`` or ``noreferrer``. Anything above zero is a
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
        """Return the status of one URL, trying ``HEAD`` and confirming with ``GET``.

        A ``HEAD`` answer from 200 to 399 is returned as is; any other answer
        is re-checked with ``GET``, and that answer is returned.

        Args:
            url (str): An absolute URL.

        Returns:
            int: The status a real client would receive, or ``0`` when the
            request could not complete.
        """
        status = self._issue_request(url, "head")
        if 200 <= status < 400:
            return status
        return self._issue_request(url, "get")

    def _issue_request(self, url: str, method: str) -> int:
        """Return the status of one request sent through the browser's context.

        Args:
            url (str): An absolute URL.
            method (str): ``"head"`` or ``"get"``.

        Returns:
            int: The final status code, or ``0`` when the request could not
            complete at all, so a dead network reads differently from a dead
            link.
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
        """Wait until the URL's host is one request interval past its last request.

        The clock is kept per host; requests to different hosts never wait on
        each other. Why per host: ``README.md`` section "Key Features"
        (Outbound Link-Rot Detection).

        Args:
            url (str): The URL about to be requested.

        Returns:
            None
        """
        host = urlparse(url).netloc
        elapsed = time.monotonic() - self._last_request_at_host.get(host, 0.0)
        if elapsed < OUTBOUND_REQUEST_INTERVAL_SECONDS:
            time.sleep(OUTBOUND_REQUEST_INTERVAL_SECONDS - elapsed)
        self._last_request_at_host[host] = time.monotonic()

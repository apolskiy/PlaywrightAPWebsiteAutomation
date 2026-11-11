"""Page Object for any route the sitemap crawler discovers.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains ``RoutePage``, which opens a route and reports its HTTP
status, reads its meta description and locates its document body. It knows
nothing about the portfolio's structure, unlike ``LandingPage``.

``tests/test_dynamic_routes.py`` builds one per discovered route and runs the
per-route health checks through it, so a new page is checked with no
hand-written Page Object and no Playwright call in the test module. A failure
here names a route that does not load, render or describe itself.

**Browser diagnostics come from the base class.** Console errors, failed
requests, responses of 400 and above, and unhandled JavaScript exceptions are
recorded by the ``PageDiagnostics`` collaborator every Page Object inherits from
``BasePage``, reached here as ``route_page.diagnostics``.

Specified by ``README.md`` section "Dynamic Site Discovery" and the Key Features
entry "The Browser's Own Error Log, on Every Page".
"""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class RoutePage(BasePage):
    """Open any route and expose what it rendered.

    Args:
        page (Page): The Playwright page bound to this Page Object.
    """

    def open_route(self, url: str) -> int:
        """Navigate to a route and return the document's HTTP status.

        Args:
            url (str): The absolute URL of the route under test.

        Returns:
            int: The HTTP status of the main document response, or ``0`` when
            the navigation produced no response.
        """
        response = self.page.goto(url, wait_until="domcontentloaded")
        return response.status if response is not None else 0

    def meta_description(self) -> str | None:
        """Return the route's meta description exactly as the markup declares it.

        Returns:
            str | None: The ``content`` of ``<meta name="description">``, or None
            when the page declares no such tag. A missing tag and an empty one
            stay distinct, so the caller can name which mistake it found.
        """
        return self.page.get_attribute('head > meta[name="description"]', "content")

    def document_root(self) -> Locator:
        """Return a locator for the document body.

        Returns:
            Locator: The ``<body>`` element, which a test asserts is visible and
            non-empty to prove the route rendered a DOM root.
        """
        return self.page.locator("body")

"""Generic Page Object for health-checking an arbitrarily discovered route.

Unlike :class:`~pages.landing_page.LandingPage`, this object knows nothing about
the portfolio's structure. It exists so that routes found at runtime by the
sitemap crawler can be exercised without a hand-written Page Object per page,
while still keeping every Playwright call out of the test modules.

Browser-level diagnostics - console errors, failed network requests,
sub-resource responses of 400 and above, and unhandled JavaScript exceptions -
are recorded by the :class:`~utils.page_diagnostics.PageDiagnostics` collaborator
every Page Object inherits from :class:`~pages.base_page.BasePage`, reached here
as ``route_page.diagnostics``. This class used to own that recording itself,
which meant only discovered-route tests ever benefited from it; the landing-page
tests, which are the ones that actually click things, recorded nothing at all.
"""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class RoutePage(BasePage):
    """Page Object that navigates any route and exposes what it rendered.

    Args:
        page: The Playwright page bound to this Page Object.
    """

    def open_route(self, url: str) -> int:
        """Navigate to a route and report the document's HTTP status.

        Args:
            url: Absolute URL of the route under test.

        Returns:
            The HTTP status of the main document response, or ``0`` when the
            navigation produced no response.
        """
        response = self.page.goto(url, wait_until="domcontentloaded")
        return response.status if response is not None else 0

    def meta_description(self) -> str | None:
        """Read the route's meta description exactly as the markup declares it.

        Returns:
            The ``content`` of ``<meta name="description">``, or ``None`` when
            the page declares no such tag. The two cases are kept distinct on
            purpose: a missing tag and a tag left empty are different mistakes,
            and only the caller can say which message is useful.
        """
        return self.page.get_attribute('head > meta[name="description"]', "content")

    def document_root(self) -> Locator:
        """Locate the document body.

        Returns:
            A locator for ``<body>``, used to prove the route rendered a DOM
            root rather than an empty or errored document.
        """
        return self.page.locator("body")

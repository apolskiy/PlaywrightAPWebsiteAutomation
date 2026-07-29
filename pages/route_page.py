"""Generic Page Object for health-checking an arbitrarily discovered route.

Unlike :class:`~pages.landing_page.LandingPage`, this object knows nothing about
the portfolio's structure. It exists so that routes found at runtime by the
sitemap crawler can be exercised without a hand-written Page Object per page,
while still keeping every Playwright call out of the test modules.

Instances record browser-level diagnostics - console errors, failed network
requests, sub-resource responses of 400 and above, and unhandled JavaScript
exceptions - from the moment recording starts until the page is closed.
"""

from __future__ import annotations

from playwright.sync_api import (
    ConsoleMessage,
    Locator,
    Page,
    Request,
    Response,
)

from pages.base_page import BasePage

#: Lowest HTTP status treated as a broken sub-resource.
ERROR_STATUS_THRESHOLD: int = 400


class RoutePage(BasePage):
    """Page Object that navigates any route and records its runtime health.

    Args:
        page: The Playwright page bound to this Page Object.
    """

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self._console_errors: list[str] = []
        self._failed_requests: list[str] = []
        self._broken_resources: list[str] = []
        self._javascript_errors: list[str] = []

    def record_diagnostics(self) -> None:
        """Subscribe to the browser events that reveal a broken page.

        Must be called before navigating: Playwright only delivers events that
        occur after the listener is attached, so subscribing afterwards would
        silently miss every error raised during load.
        """
        self.page.on("console", self._on_console_message)
        self.page.on("requestfailed", self._on_request_failed)
        self.page.on("response", self._on_response)
        self.page.on("pageerror", self._on_page_error)

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

    @property
    def console_errors(self) -> list[str]:
        """Console messages logged at error level.

        Returns:
            One entry per ``console.error`` emitted since recording started.
        """
        return list(self._console_errors)

    @property
    def failed_requests(self) -> list[str]:
        """Requests that never completed.

        Returns:
            One entry per network-level failure, such as a DNS or connection
            error, formatted as ``"<url> (<reason>)"``.
        """
        return list(self._failed_requests)

    @property
    def broken_resources(self) -> list[str]:
        """Sub-resources that responded with an error status.

        Returns:
            One entry per response of 400 or above, formatted as
            ``"<status> <url>"``. The main document is included, so callers that
            assert on the document status separately should expect it here too.
        """
        return list(self._broken_resources)

    @property
    def javascript_errors(self) -> list[str]:
        """Unhandled JavaScript exceptions raised by the page.

        Returns:
            One entry per ``pageerror`` event.
        """
        return list(self._javascript_errors)

    def document_root(self) -> Locator:
        """Locate the document body.

        Returns:
            A locator for ``<body>``, used to prove the route rendered a DOM
            root rather than an empty or errored document.
        """
        return self.page.locator("body")

    def _on_console_message(self, message: ConsoleMessage) -> None:
        """Record a console message emitted at error level.

        Args:
            message: The console message reported by the browser.
        """
        if message.type == "error":
            self._console_errors.append(message.text)

    def _on_request_failed(self, request: Request) -> None:
        """Record a request that failed at the network level.

        Args:
            request: The request that never completed.
        """
        failure_reason = request.failure or "unknown failure"
        self._failed_requests.append(f"{request.url} ({failure_reason})")

    def _on_response(self, response: Response) -> None:
        """Record a response carrying an error status.

        Args:
            response: The response returned for one request.
        """
        if response.status >= ERROR_STATUS_THRESHOLD:
            self._broken_resources.append(f"{response.status} {response.url}")

    def _on_page_error(self, error: object) -> None:
        """Record an unhandled JavaScript exception.

        Args:
            error: The ``pageerror`` payload. Typed loosely because the event
                delivers a JavaScript ``Error`` whose only guaranteed surface is
                its string representation.
        """
        self._javascript_errors.append(str(error))

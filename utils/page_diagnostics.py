"""Records the errors a browser reports while a page is open, split by origin.

Created: 2026-08-11
Last updated: 2026-11-10

This file contains ``BrowserEvent``, one recorded complaint carrying its
category, its description and the URL it came from; ``PageDiagnostics``, the
recorder that subscribes to a page's console, network, response and
``pageerror`` events and reports them; and the category constants both use.

Every Page Object owns one recorder, and the fixtures in ``conftest.py`` arm it
between creating the page and handing it to the test. Tests assert on its
first-party lists, and on any failure ``conftest.py`` attaches its ``report``
to Allure and the pytest report and hands it to the Claude diagnostics hook. A
recorder that was never armed reports so, rather than reporting a clean page.

**It observes and never drives.** Nothing here reads or interacts with the
document; it collects what the browser complains about and renders it as text,
which is why it is a collaborator of the Page Object and not a set of
``BasePage`` methods.

**Recording is armed before navigation.** Playwright delivers only events
raised after a listener is attached, so an error during the first load is lost
to a listener attached later. Arming twice is ignored, so no event is counted
twice.

**First party decides, third party is recorded.** An event is first-party when
it names no resource or names one on the loaded page's host. Assertions read
only the first-party lists; third-party events, such as a GitHub badge that
fails, are still counted and reported. Unhandled JavaScript exceptions are not
split by origin, since the site chose to run the script that raised them.

**The report keeps the split.** The first-party section is where a failure
investigation starts, and the third-party section explains an oddity that is
nobody's bug, so the two are printed separately rather than merged.

Specified by ``README.md`` section "Key Features" (The Browser's Own Error Log,
Origin-Scoped Assertions) and section "Test Design Principles".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from urllib.parse import urlparse

from playwright.sync_api import ConsoleMessage, Page, Request, Response

#: ERROR STATUS. The lowest HTTP status recorded as a broken sub-resource.
ERROR_STATUS_THRESHOLD: Final[int] = 400

#: CATEGORY LABELS, used as dictionary keys, report headings and the assertion
#: messages tests build. Declared once so the three never disagree.
CONSOLE_ERROR: Final[str] = "console error"
FAILED_REQUEST: Final[str] = "failed request"
BROKEN_RESOURCE: Final[str] = "broken resource"
JAVASCRIPT_ERROR: Final[str] = "javascript error"

#: REPORT ORDER. Every category, ordered by how directly it indicts the page:
#: an unhandled exception first, a sub-resource status last.
EVENT_CATEGORIES: Final[tuple[str, ...]] = (
    JAVASCRIPT_ERROR,
    CONSOLE_ERROR,
    FAILED_REQUEST,
    BROKEN_RESOURCE,
)


@dataclass(frozen=True)
class BrowserEvent:
    """Hold one complaint the browser raised while the page was open.

    Attributes:
        category (str): One of the module's category constants.
        description (str): The detail, already formatted for a report.
        source_url (str): The URL the event came from, which decides whether it
            is first-party. Empty when the browser names no resource, which
            counts as first-party.
    """

    category: str
    description: str
    source_url: str


class PageDiagnostics:
    """Record a page's error events and report what was collected.

    Args:
        page (Page): The Playwright page to observe.
    """

    def __init__(self, page: Page) -> None:
        self._page = page
        self._events: list[BrowserEvent] = []
        self._is_recording = False

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self) -> None:
        """Subscribe to the browser events that reveal a broken page.

        A second call is ignored, so no listener is registered twice.

        Returns:
            None
        """
        if self._is_recording:
            return
        self._page.on("console", self._on_console_message)
        self._page.on("requestfailed", self._on_request_failed)
        self._page.on("response", self._on_response)
        self._page.on("pageerror", self._on_page_error)
        self._is_recording = True

    @property
    def is_recording(self) -> bool:
        """Return whether listeners are attached.

        Returns:
            bool: True once :meth:`record` has run. A recorder never armed
            watched nothing, which is not the same as nothing happening.
        """
        return self._is_recording

    # ------------------------------------------------------------------
    # Collected events
    # ------------------------------------------------------------------

    @property
    def events(self) -> list[BrowserEvent]:
        """Return every event recorded so far.

        Returns:
            list[BrowserEvent]: The events in the order the browser raised them.
        """
        return list(self._events)

    @property
    def javascript_errors(self) -> list[str]:
        """Return the unhandled JavaScript exceptions the page raised, any origin.

        Returns:
            list[str]: One entry per ``pageerror`` event.
        """
        return self._descriptions(JAVASCRIPT_ERROR)

    @property
    def console_errors(self) -> list[str]:
        """Return the console messages logged at error level, from any origin.

        Returns:
            list[str]: One entry per ``console.error``, including those a
            third-party sub-resource provoked.
        """
        return self._descriptions(CONSOLE_ERROR)

    @property
    def failed_requests(self) -> list[str]:
        """Return the requests that never completed, from any origin.

        Returns:
            list[str]: One entry per network-level failure, such as a DNS or
            connection error, formatted as ``"<url> (<reason>)"``.
        """
        return self._descriptions(FAILED_REQUEST)

    @property
    def broken_resources(self) -> list[str]:
        """Return the responses carrying an error status, from any origin.

        Returns:
            list[str]: One entry per response of 400 or above, formatted as
            ``"<status> <url>"``. The main document is included.
        """
        return self._descriptions(BROKEN_RESOURCE)

    @property
    def first_party_console_errors(self) -> list[str]:
        """Return the console errors this site is answerable for.

        Returns:
            list[str]: The subset of :attr:`console_errors` raised by the site's
            own origin, or by no resource in particular.
        """
        return self._descriptions(CONSOLE_ERROR, first_party_only=True)

    @property
    def first_party_failed_requests(self) -> list[str]:
        """Return the failed requests addressed to this site's own origin.

        Returns:
            list[str]: The subset of :attr:`failed_requests` sent to the site.
        """
        return self._descriptions(FAILED_REQUEST, first_party_only=True)

    @property
    def first_party_broken_resources(self) -> list[str]:
        """Return the error responses served by this site's own origin.

        Returns:
            list[str]: The subset of :attr:`broken_resources` served by the site
            itself, such as a missing stylesheet, icon or script.
        """
        return self._descriptions(BROKEN_RESOURCE, first_party_only=True)

    @property
    def third_party_problems(self) -> list[str]:
        """Return everything recorded against a host other than this site's.

        Returns:
            list[str]: One entry per third-party event, each prefixed with its
            category.
        """
        return [
            f"[{event.category}] {event.description}"
            for event in self._events
            if not self._is_first_party(event)
        ]

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def counts(self) -> dict[str, int]:
        """Return the number of recorded events by category.

        Returns:
            dict[str, int]: Every category label, present even at zero so a
            missing line never reads as unchecked, plus a ``"total"`` entry.
        """
        by_category = {
            category: len(self._descriptions(category)) for category in EVENT_CATEGORIES
        }
        by_category["total"] = len(self._events)
        return by_category

    def summary(self) -> str:
        """Return the counts rendered as a single line.

        Returns:
            str: A tally naming only the categories that fired, a statement that
            the page raised nothing, or a statement that nothing was recorded.
        """
        if not self._is_recording:
            return "Browser diagnostics were not recorded for this page."
        if not self._events:
            return "No console, network, or JavaScript errors were recorded."
        tally = ", ".join(
            f"{count} {category}{'s' if count != 1 else ''}"
            for category, count in self.counts().items()
            if category != "total" and count
        )
        return f"{len(self._events)} browser events recorded: {tally}."

    def report(self) -> str:
        """Return the full diagnostic log as attachable plain text.

        Returns:
            str: The page URL, the summary line, then a first-party section and
            a third-party section, each printed only when it has entries.
        """
        lines = [
            f"Page: {self._page.url}",
            self.summary(),
        ]
        first_party = [
            f"[{event.category}] {event.description}"
            for event in self._events
            if self._is_first_party(event)
        ]
        third_party = self.third_party_problems
        if first_party:
            lines.append("")
            lines.append(f"First party - asserted ({len(first_party)}):")
            lines.extend(f"  {entry}" for entry in first_party)
        if third_party:
            lines.append("")
            lines.append(f"Third party - recorded only ({len(third_party)}):")
            lines.extend(f"  {entry}" for entry in third_party)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _descriptions(self, category: str, *, first_party_only: bool = False) -> list[str]:
        """Return the descriptions of one category of event.

        Args:
            category (str): The category to filter on.
            first_party_only (bool): Whether to keep only events this site's own
                origin is answerable for.

        Returns:
            list[str]: The matching descriptions, in recorded order.
        """
        return [
            event.description
            for event in self._events
            if event.category == category
            and (not first_party_only or self._is_first_party(event))
        ]

    def _is_first_party(self, event: BrowserEvent) -> bool:
        """Return whether an event belongs to the site under test.

        Args:
            event (BrowserEvent): The recorded event.

        Returns:
            bool: True when the event names no resource, or names one served by
            the same host as the page currently loaded.
        """
        if not event.source_url:
            return True
        return urlparse(event.source_url).netloc.lower() == urlparse(self._page.url).netloc.lower()

    def _on_console_message(self, message: ConsoleMessage) -> None:
        """Record a console message emitted at error level.

        The message's own location is kept, not the page's, so an error a badge
        image logs is attributed to the badge's host.

        Args:
            message (ConsoleMessage): The console message the browser reported.

        Returns:
            None
        """
        if message.type != "error":
            return
        location = message.location or {}
        origin = str(location.get("url") or "")
        self._events.append(
            BrowserEvent(
                category=CONSOLE_ERROR,
                description=f"{message.text}{f' ({origin})' if origin else ''}",
                source_url=origin,
            )
        )

    def _on_request_failed(self, request: Request) -> None:
        """Record a request that failed at the network level.

        Args:
            request (Request): The request that never completed.

        Returns:
            None
        """
        failure_reason = request.failure or "unknown failure"
        self._events.append(
            BrowserEvent(
                category=FAILED_REQUEST,
                description=f"{request.url} ({failure_reason})",
                source_url=request.url,
            )
        )

    def _on_response(self, response: Response) -> None:
        """Record a response carrying an error status.

        Args:
            response (Response): The response returned for one request.

        Returns:
            None
        """
        if response.status < ERROR_STATUS_THRESHOLD:
            return
        self._events.append(
            BrowserEvent(
                category=BROKEN_RESOURCE,
                description=f"{response.status} {response.url}",
                source_url=response.url,
            )
        )

    def _on_page_error(self, error: object) -> None:
        """Record an unhandled JavaScript exception as first-party.

        Args:
            error (object): The ``pageerror`` payload, a JavaScript ``Error``
                whose only guaranteed surface is its string form.

        Returns:
            None
        """
        self._events.append(
            BrowserEvent(
                category=JAVASCRIPT_ERROR,
                description=str(error),
                source_url="",
            )
        )

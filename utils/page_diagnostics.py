"""Recording of the errors a browser reports while a page is open.

Every Page Object owns one of these. It is a collaborator rather than a set of
methods on :class:`~pages.base_page.BasePage` for the same reason
:class:`~utils.link_auditor.LinkAuditor` is one: this is not page interaction.
Nothing here reads or drives the document. It subscribes to browser events,
accumulates whatever the browser complains about, and renders that into
something a human reads after the fact.

Two things follow from that separation and are worth stating.

**Recording must be armed before navigation.** Playwright only delivers events
raised after a listener is attached, so a console error thrown during the very
first load is missed by a listener attached afterwards - silently, which is the
worst way to miss it. The fixtures therefore arm recording between creating the
page and handing it to the test.

**First-party and third-party problems are separated, and only the first are
worth failing a build on.** The site under test embeds CI badge images served by
GitHub. A badge that 503s is a real observation and belongs in the log, but it
says nothing about whether this site works, and asserting on it would make every
test that loads the landing page depend on GitHub being reachable - exactly what
the ``external`` marker exists to prevent. So both are recorded, both are
reported, and the assertions are scoped to the origin the site actually controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from urllib.parse import urlparse

from playwright.sync_api import ConsoleMessage, Page, Request, Response

#: Lowest HTTP status treated as a broken sub-resource.
ERROR_STATUS_THRESHOLD: Final[int] = 400

#: Category labels, used as dictionary keys, in report headings, and in the
#: assertion messages tests build. Declared once so the three never disagree.
CONSOLE_ERROR: Final[str] = "console error"
FAILED_REQUEST: Final[str] = "failed request"
BROKEN_RESOURCE: Final[str] = "broken resource"
JAVASCRIPT_ERROR: Final[str] = "javascript error"

#: Every category, ordered by how directly it indicts the page: an unhandled
#: exception is unambiguous, a sub-resource status is the most circumstantial.
EVENT_CATEGORIES: Final[tuple[str, ...]] = (
    JAVASCRIPT_ERROR,
    CONSOLE_ERROR,
    FAILED_REQUEST,
    BROKEN_RESOURCE,
)


@dataclass(frozen=True)
class BrowserEvent:
    """One complaint the browser raised while the page was open.

    Attributes:
        category: One of the module's category constants.
        description: Human-readable detail, already formatted for a report.
        source_url: URL the event originated from, used to tell a problem in
            this site from a problem at a host it merely embeds. Empty when the
            browser attributes the event to no particular resource, which is
            treated as first-party: an unhandled exception with no location came
            from the document's own scripts.
    """

    category: str
    description: str
    source_url: str


class PageDiagnostics:
    """Subscribes to a page's error events and reports what it collected.

    Args:
        page: The Playwright page to observe.
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

        Safe to call more than once: a second call is ignored rather than
        registering a duplicate set of listeners, which would report every
        error twice and make the counts meaningless.
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
        """Whether listeners are attached.

        Returns:
            ``True`` once :meth:`record` has run. A report from a recorder that
            was never armed means "nothing was watched", not "nothing happened",
            and the two must not read the same.
        """
        return self._is_recording

    # ------------------------------------------------------------------
    # Collected events
    # ------------------------------------------------------------------

    @property
    def events(self) -> list[BrowserEvent]:
        """Every event recorded so far.

        Returns:
            The events in the order the browser raised them.
        """
        return list(self._events)

    @property
    def javascript_errors(self) -> list[str]:
        """Unhandled JavaScript exceptions raised by the page.

        Not split by origin: an unhandled exception is raised by a script this
        site chose to run, whatever host served it.

        Returns:
            One entry per ``pageerror`` event.
        """
        return self._descriptions(JAVASCRIPT_ERROR)

    @property
    def console_errors(self) -> list[str]:
        """Console messages logged at error level, from any origin.

        Returns:
            One entry per ``console.error``, including those a third-party
            sub-resource provoked.
        """
        return self._descriptions(CONSOLE_ERROR)

    @property
    def failed_requests(self) -> list[str]:
        """Requests that never completed, from any origin.

        Returns:
            One entry per network-level failure, such as a DNS or connection
            error, formatted as ``"<url> (<reason>)"``.
        """
        return self._descriptions(FAILED_REQUEST)

    @property
    def broken_resources(self) -> list[str]:
        """Responses carrying an error status, from any origin.

        Returns:
            One entry per response of 400 or above, formatted as
            ``"<status> <url>"``. The main document is included, so a caller
            asserting on the document status separately should expect it here
            too.
        """
        return self._descriptions(BROKEN_RESOURCE)

    @property
    def first_party_console_errors(self) -> list[str]:
        """Console errors this site is answerable for.

        Returns:
            The subset of :attr:`console_errors` raised by the site's own
            origin, or by no resource in particular.
        """
        return self._descriptions(CONSOLE_ERROR, first_party_only=True)

    @property
    def first_party_failed_requests(self) -> list[str]:
        """Failed requests to this site's own origin.

        Returns:
            The subset of :attr:`failed_requests` addressed to the site itself.
        """
        return self._descriptions(FAILED_REQUEST, first_party_only=True)

    @property
    def first_party_broken_resources(self) -> list[str]:
        """Error responses served by this site's own origin.

        Returns:
            The subset of :attr:`broken_resources` served by the site itself -
            a missing stylesheet, icon, or script, rather than an embedded
            badge whose host is having a bad day.
        """
        return self._descriptions(BROKEN_RESOURCE, first_party_only=True)

    @property
    def third_party_problems(self) -> list[str]:
        """Everything recorded against a host other than this site's own.

        Returns:
            One entry per third-party event, each prefixed with its category so
            a mixed list stays readable.
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
        """Count what was recorded, by category.

        Every category is present whether or not it fired, so a reader
        comparing two runs is never left wondering whether a missing line means
        zero or means the category was not checked.

        Returns:
            Mapping of category label to the number of events recorded, plus a
            ``"total"`` entry.
        """
        by_category = {
            category: len(self._descriptions(category)) for category in EVENT_CATEGORIES
        }
        by_category["total"] = len(self._events)
        return by_category

    def summary(self) -> str:
        """Render the counts as a single line.

        Returns:
            A one-line tally naming only the categories that fired, or a plain
            statement that the page raised nothing.
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
        """Render the full diagnostic log as attachable plain text.

        The split by origin is preserved in the output rather than flattened,
        because the two halves answer different questions: the first-party
        section is what a failure investigation starts from, and the
        third-party section is what explains an oddity that is nobody's bug.

        Returns:
            A multi-line report, suitable for an Allure attachment or a pytest
            report section.
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
        """Collect the descriptions of one category of event.

        Args:
            category: The category to filter on.
            first_party_only: Restrict the result to events this site's own
                origin is answerable for.

        Returns:
            The matching descriptions, in the order they were recorded.
        """
        return [
            event.description
            for event in self._events
            if event.category == category
            and (not first_party_only or self._is_first_party(event))
        ]

    def _is_first_party(self, event: BrowserEvent) -> bool:
        """Decide whether an event belongs to the site under test.

        Args:
            event: The recorded event.

        Returns:
            ``True`` when the event names no resource, or names one served by
            the same host as the page currently loaded.
        """
        if not event.source_url:
            return True
        return urlparse(event.source_url).netloc.lower() == urlparse(self._page.url).netloc.lower()

    def _on_console_message(self, message: ConsoleMessage) -> None:
        """Record a console message emitted at error level.

        The message's own location is kept, not the page's. A failing badge
        image logs its console error against the badge's URL, and that is the
        only thing distinguishing it from an error in this site's script.

        Args:
            message: The console message reported by the browser.
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
            request: The request that never completed.
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
            response: The response returned for one request.
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
        """Record an unhandled JavaScript exception.

        Args:
            error: The ``pageerror`` payload. Typed loosely because the event
                delivers a JavaScript ``Error`` whose only guaranteed surface is
                its string representation.
        """
        self._events.append(
            BrowserEvent(
                category=JAVASCRIPT_ERROR,
                description=str(error),
                source_url="",
            )
        )

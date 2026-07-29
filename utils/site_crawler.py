"""Asynchronous Playwright crawler that discovers the site's route surface.

The crawler renders each page with a real browser rather than fetching raw HTML,
because the target application publishes every outbound link as a base64 payload
that only becomes an ``<a href>`` after its ``DOMContentLoaded`` script runs. A
requests-based crawler would therefore discover nothing.

Discovery is breadth-first from the base URL, bounded by both depth and page
count so a link cycle or an unexpectedly large site can never hang a test
session. The resulting sitemap is written to ``reports/sitemap.json`` and is the
input that ``tests/test_dynamic_routes.py`` parameterizes over, so a newly added
page grows the suite automatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

from playwright.async_api import Error as PlaywrightError, Page, async_playwright

LOGGER = logging.getLogger(__name__)

#: Default location of the generated sitemap artifact.
DEFAULT_SITEMAP_PATH: Final[Path] = Path("reports") / "sitemap.json"

#: URL schemes that identify a link as something other than a crawlable page.
NON_CRAWLABLE_SCHEMES: Final[frozenset[str]] = frozenset(
    {"mailto", "tel", "javascript", "sms", "data", "file", "ftp"}
)

#: File extensions that are assets rather than HTML documents.
NON_HTML_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".bmp",
        ".css", ".js", ".mjs", ".json", ".xml", ".txt", ".csv", ".webmanifest",
        ".woff", ".woff2", ".ttf", ".eot",
        ".mp4", ".webm", ".mp3", ".wav",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    }
)

#: Safety rails. The target is a small portfolio; these bounds exist so a
#: pathological link graph cannot stall collection.
DEFAULT_MAX_DEPTH: Final[int] = 3
DEFAULT_MAX_PAGES: Final[int] = 50
DEFAULT_NAVIGATION_TIMEOUT_MS: Final[int] = 20_000


@dataclass(frozen=True)
class DiscoveredRoute:
    """One route found by the crawler.

    Attributes:
        url: Absolute URL of the route, including any fragment it was reached by.
        parent_route: URL the route was discovered from. The seed route records
            an empty string, since nothing linked to it.
        discovered_at: UTC ISO-8601 timestamp of when the route was visited.
        status_code: HTTP status returned for the document, or ``0`` when the
            navigation produced no response at all.
    """

    url: str
    parent_route: str
    discovered_at: str
    status_code: int

    @property
    def route_id(self) -> str:
        """Human-readable identifier used as the pytest parametrization id.

        Returns:
            The path and fragment of the route, e.g. ``/`` or ``/about#team``.
            Characters pytest would mangle in a test id are replaced.
        """
        parsed_url = urlparse(self.url)
        identifier = parsed_url.path or "/"
        if parsed_url.fragment:
            identifier = f"{identifier}#{parsed_url.fragment}"
        return identifier.replace(" ", "_")


@dataclass(frozen=True)
class JavaScriptError:
    """An unhandled JavaScript exception observed while crawling.

    Attributes:
        url: Route on which the exception surfaced.
        message: The error message reported by the page.
    """

    url: str
    message: str


class SiteMapCrawler:
    """Breadth-first Playwright crawler over a site's internal route graph.

    Args:
        base_url: Absolute URL the crawl starts from. Its host defines what
            counts as internal.
        max_depth: Maximum link depth to follow from the seed route.
        max_pages: Hard ceiling on the number of documents visited.
        navigation_timeout_ms: Per-navigation timeout in milliseconds.
    """

    def __init__(
        self,
        base_url: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_pages: int = DEFAULT_MAX_PAGES,
        navigation_timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
    ) -> None:
        self._base_url = base_url
        self._base_host = urlparse(base_url).netloc
        self._max_depth = max_depth
        self._max_pages = max_pages
        self._navigation_timeout_ms = navigation_timeout_ms
        self._javascript_errors: list[JavaScriptError] = []

    @property
    def javascript_errors(self) -> list[JavaScriptError]:
        """Unhandled JavaScript exceptions captured during the last crawl.

        Returns:
            One entry per ``pageerror`` event observed while navigating.
        """
        return list(self._javascript_errors)

    async def crawl(self) -> list[DiscoveredRoute]:
        """Walk the site and return every internal route reachable from the seed.

        Returns:
            The discovered routes in breadth-first order, starting with the seed.
            A route that could not be navigated is still reported, with a status
            code of ``0``, so a broken link surfaces as a failing test rather
            than silently vanishing from the sitemap.
        """
        self._javascript_errors = []
        discovered_routes: list[DiscoveredRoute] = []
        # Deduplicate on the fragment-less URL: '#projects' is a distinct route
        # for reporting, but it is the same document and must not be re-fetched.
        visited_documents: set[str] = set()
        recorded_routes: set[str] = set()
        pending: deque[tuple[str, str, int]] = deque([(self._base_url, "", 0)])

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            page.on("pageerror", self._record_javascript_error)
            try:
                while pending and len(discovered_routes) < self._max_pages:
                    url, parent_route, depth = pending.popleft()
                    document_url = urldefrag(url).url
                    if url in recorded_routes:
                        continue
                    recorded_routes.add(url)

                    status_code = await self._visit(page, url)
                    discovered_routes.append(
                        DiscoveredRoute(
                            url=url,
                            parent_route=parent_route,
                            discovered_at=datetime.now(timezone.utc).isoformat(),
                            status_code=status_code,
                        )
                    )

                    # Only expand a document once, and only while within depth.
                    if document_url in visited_documents or depth >= self._max_depth:
                        continue
                    visited_documents.add(document_url)
                    if status_code == 0:
                        continue
                    for child_url in await self._extract_internal_links(page, url):
                        if child_url not in recorded_routes:
                            pending.append((child_url, url, depth + 1))
            finally:
                await browser.close()

        return discovered_routes

    async def _visit(self, page: Page, url: str) -> int:
        """Navigate to a URL and report the document's HTTP status.

        Args:
            page: The reusable page driving the crawl.
            url: Absolute URL to navigate to.

        Returns:
            The HTTP status code, or ``0`` when navigation failed outright or
            returned no response. Navigation errors are logged rather than
            raised so one unreachable link cannot abort the whole crawl.
        """
        try:
            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=self._navigation_timeout_ms
            )
        except PlaywrightError as navigation_error:
            LOGGER.warning("Crawler could not navigate to %s: %s", url, navigation_error)
            return 0
        return response.status if response is not None else 0

    async def _extract_internal_links(self, page: Page, current_url: str) -> list[str]:
        """Collect the crawlable internal links published by the current page.

        Args:
            page: The page whose DOM should be scanned.
            current_url: URL used to resolve relative and fragment-only hrefs.

        Returns:
            Absolute, deduplicated URLs that pass the internal-link filter, in
            document order.
        """
        try:
            raw_hrefs: list[str] = await page.eval_on_selector_all(
                "a[href]", "anchors => anchors.map(anchor => anchor.getAttribute('href'))"
            )
        except PlaywrightError as extraction_error:
            LOGGER.warning("Could not read links from %s: %s", current_url, extraction_error)
            return []

        internal_links: list[str] = []
        seen_links: set[str] = set()
        for raw_href in raw_hrefs:
            candidate_url = self._normalize(raw_href, current_url)
            if candidate_url is not None and candidate_url not in seen_links:
                seen_links.add(candidate_url)
                internal_links.append(candidate_url)
        return internal_links

    def _normalize(self, raw_href: str | None, current_url: str) -> str | None:
        """Resolve one ``href`` and decide whether it is a crawlable route.

        Relative paths (``/about``) and bare fragments (``#projects``) are
        resolved against the page they were found on. External hosts, non-HTTP
        schemes, and asset files are rejected. Accepted URLs are canonicalized
        so that spellings of the same document - notably an empty path versus
        ``/``, which this site links to itself both ways - collapse to one route
        instead of being crawled and reported twice.

        Args:
            raw_href: The raw attribute value, which may be ``None`` or empty.
            current_url: URL used as the resolution base.

        Returns:
            The canonical absolute URL to crawl, or ``None`` when the link is
            out of scope.
        """
        if not raw_href or not raw_href.strip():
            return None
        href = raw_href.strip()

        scheme = urlparse(href).scheme.lower()
        if scheme in NON_CRAWLABLE_SCHEMES:
            return None

        parsed_url = urlparse(urljoin(current_url, href))
        if parsed_url.scheme.lower() not in {"http", "https"}:
            return None
        if parsed_url.netloc.lower() != self._base_host.lower():
            return None
        if Path(parsed_url.path).suffix.lower() in NON_HTML_EXTENSIONS:
            return None

        return urlunparse(
            (
                parsed_url.scheme.lower(),
                parsed_url.netloc.lower(),
                parsed_url.path or "/",
                parsed_url.params,
                parsed_url.query,
                parsed_url.fragment,
            )
        )

    def _record_javascript_error(self, error: object) -> None:
        """Capture an unhandled JavaScript exception raised by a crawled page.

        Args:
            error: The ``pageerror`` payload emitted by Playwright. It is typed
                loosely because the event delivers an ``Error`` object whose
                only guaranteed surface is its string representation.
        """
        self._javascript_errors.append(
            JavaScriptError(url=self._base_url, message=str(error))
        )

    def build_artifact(self, routes: list[DiscoveredRoute]) -> dict[str, object]:
        """Assemble the JSON document describing a completed crawl.

        Args:
            routes: The routes returned by :meth:`crawl`.

        Returns:
            A mapping with the crawl context, the route records themselves - each
            carrying exactly ``url``, ``parent_route``, ``discovered_at``, and
            ``status_code`` - and any JavaScript errors observed.
        """
        return {
            "base_url": self._base_url,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "route_count": len(routes),
            "routes": [asdict(route) for route in routes],
            "javascript_errors": [asdict(error) for error in self._javascript_errors],
        }

    def write_sitemap(
        self, routes: list[DiscoveredRoute], sitemap_path: Path = DEFAULT_SITEMAP_PATH
    ) -> Path:
        """Persist a crawl result as the JSON sitemap artifact.

        Args:
            routes: The routes returned by :meth:`crawl`.
            sitemap_path: Destination file. Parent directories are created.

        Returns:
            The path the artifact was written to.
        """
        sitemap_path.parent.mkdir(parents=True, exist_ok=True)
        sitemap_path.write_text(
            json.dumps(self.build_artifact(routes), indent=2), encoding="utf-8"
        )
        return sitemap_path


def load_sitemap(sitemap_path: Path = DEFAULT_SITEMAP_PATH) -> list[DiscoveredRoute]:
    """Read a previously generated sitemap artifact.

    Args:
        sitemap_path: Location of the artifact.

    Returns:
        The routes it records, or an empty list when the file is missing or
        cannot be parsed. A corrupt cache degrades to "no cache" so the caller
        simply re-crawls instead of failing collection.
    """
    if not sitemap_path.is_file():
        return []
    try:
        artifact = json.loads(sitemap_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as read_error:
        LOGGER.warning("Ignoring unreadable sitemap at %s: %s", sitemap_path, read_error)
        return []
    return [DiscoveredRoute(**record) for record in artifact.get("routes", [])]


def discover_routes(
    base_url: str,
    sitemap_path: Path = DEFAULT_SITEMAP_PATH,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[DiscoveredRoute]:
    """Run a crawl synchronously and persist the resulting sitemap.

    This is the entry point used from pytest collection, which is synchronous.
    It owns its own event loop, so it must not be called from inside a running
    loop.

    Args:
        base_url: Absolute URL to start crawling from.
        sitemap_path: Destination for the generated artifact.
        max_depth: Maximum link depth to follow.
        max_pages: Hard ceiling on documents visited.

    Returns:
        The discovered routes, which have also been written to ``sitemap_path``.
    """
    crawler = SiteMapCrawler(base_url, max_depth=max_depth, max_pages=max_pages)
    routes = asyncio.run(crawler.crawl())
    crawler.write_sitemap(routes, sitemap_path)
    return routes

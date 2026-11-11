"""Discovers the site's internal routes with a browser and writes them as a sitemap.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains ``SiteMapCrawler``, an asynchronous breadth-first Playwright
crawler; ``DiscoveredRoute``, one route it found with its parent, timestamp and
HTTP status; ``JavaScriptError``, an unhandled exception seen during the walk;
``discover_routes``, the synchronous entry point that crawls and writes
``reports/sitemap.json``; and ``load_sitemap``, which reads that file back.

``tests/test_dynamic_routes.py`` calls ``discover_routes``, or ``load_sitemap``
under ``--use-cached-sitemap``, during collection and parameterizes its health
checks over the result, so a newly published page grows the suite with no test
edit. A route missed here is a route no test checks; a route that fails to load
is still listed, with status ``0``, so it fails a test rather than vanishing.

**It renders, it does not fetch.** The site's links become ``<a href>`` only
after its ``DOMContentLoaded`` script runs, so each page is loaded in a real
browser before its anchors are read.

**Scope and canonical form.** Relative paths and bare fragments resolve against
the page they were found on. External hosts, non-HTTP schemes, asset files and
the report paths in ``FOREIGN_REPORT_PATH_PREFIXES`` are rejected. An accepted
URL is lower-cased in scheme and host and given ``/`` for an empty path, so two
spellings of one document collapse to one route.

**Fragments are routes, not documents.** A fragment URL is recorded as its own
route but its document is fetched and expanded once. Traversal stops at
``max_depth`` and ``max_pages``.

**Nothing here aborts collection.** A navigation error is logged and recorded as
status ``0``, a page whose links cannot be read contributes none, and an
unreadable sitemap cache reads as no cache, so the caller re-crawls.

Specified by ``README.md`` section "Dynamic Site Discovery".
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

from config.settings import FOREIGN_REPORT_PATH_PREFIXES

LOGGER = logging.getLogger(__name__)

#: ARTIFACT. The default location of the generated sitemap.
DEFAULT_SITEMAP_PATH: Final[Path] = Path("reports") / "sitemap.json"

#: REJECTED SCHEMES. A link with one of these is never a crawlable page.
NON_CRAWLABLE_SCHEMES: Final[frozenset[str]] = frozenset(
    {"mailto", "tel", "javascript", "sms", "data", "file", "ftp"}
)

#: REJECTED EXTENSIONS. A path ending in one of these is an asset, not HTML.
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

#: BOUNDED, per ``README.md`` section "Dynamic Site Discovery". Depth, page
#: count and per-navigation timeout, so a link cycle cannot stall collection.
DEFAULT_MAX_DEPTH: Final[int] = 3
DEFAULT_MAX_PAGES: Final[int] = 50
DEFAULT_NAVIGATION_TIMEOUT_MS: Final[int] = 20_000


@dataclass(frozen=True)
class DiscoveredRoute:
    """Hold one route the crawler found.

    Attributes:
        url (str): The absolute URL of the route, with any fragment it was
            reached by.
        parent_route (str): The URL the route was found on; empty for the seed.
        discovered_at (str): The UTC ISO-8601 time the route was visited.
        status_code (int): The document's HTTP status, or ``0`` when the
            navigation produced no response.
    """

    url: str
    parent_route: str
    discovered_at: str
    status_code: int

    @property
    def route_id(self) -> str:
        """Return the identifier used as the route's pytest parametrization id.

        Returns:
            str: The path and fragment, such as ``/`` or ``/about#team``, with
            spaces replaced by underscores.
        """
        parsed_url = urlparse(self.url)
        identifier = parsed_url.path or "/"
        if parsed_url.fragment:
            identifier = f"{identifier}#{parsed_url.fragment}"
        return identifier.replace(" ", "_")


@dataclass(frozen=True)
class JavaScriptError:
    """Hold one unhandled JavaScript exception observed while crawling.

    Attributes:
        url (str): The crawl's base URL, against which the exception is filed.
        message (str): The error message the page reported.
    """

    url: str
    message: str


class SiteMapCrawler:
    """Walk a site's internal route graph breadth-first in a real browser.

    Args:
        base_url (str): The absolute URL the crawl starts from. Its host defines
            what counts as internal.
        max_depth (int): The deepest link level followed from the seed.
        max_pages (int): The most routes recorded.
        navigation_timeout_ms (int): The timeout of each navigation.
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
        """Return the unhandled JavaScript exceptions captured by the last crawl.

        Returns:
            list[JavaScriptError]: One entry per ``pageerror`` event.
        """
        return list(self._javascript_errors)

    async def crawl(self) -> list[DiscoveredRoute]:
        """Return every internal route reachable from the seed.

        Returns:
            list[DiscoveredRoute]: The routes in breadth-first order, seed
            first. A route that could not be navigated is included with status
            code ``0``.
        """
        self._javascript_errors = []
        discovered_routes: list[DiscoveredRoute] = []
        # Decided 2026-07-28: '#projects' is its own route for reporting but the
        # same document, so documents are tracked fragment-less and fetched once.
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
        """Navigate to a URL and return the document's HTTP status.

        Args:
            page (Page): The reusable page driving the crawl.
            url (str): The absolute URL to navigate to.

        Returns:
            int: The HTTP status, or ``0`` when navigation failed or returned no
            response. A navigation error is logged, not raised.
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
        """Return the crawlable internal links the current page publishes.

        Args:
            page (Page): The page whose anchors are read.
            current_url (str): The URL relative and fragment-only hrefs resolve
                against.

        Returns:
            list[str]: Absolute, deduplicated URLs that pass :meth:`_normalize`,
            in document order; empty when the anchors cannot be read.
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
        """Return one ``href`` resolved and canonicalized, or None when out of scope.

        Relative paths (``/about``) and bare fragments (``#projects``) resolve
        against the page they were found on. External hosts, non-HTTP schemes,
        asset files and foreign report paths are rejected. An accepted URL has
        its scheme and host lower-cased and an empty path written as ``/``.

        Args:
            raw_href (str | None): The raw attribute value, possibly None or
                empty.
            current_url (str): The resolution base.

        Returns:
            str | None: The canonical absolute URL to crawl, or None when the
            link is out of scope.
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
        # Added 2026-11-10: a report another project publishes on this host is
        # out of scope like an external host; see FOREIGN_REPORT_PATH_PREFIXES.
        if parsed_url.netloc.lower() != self._base_host.lower() or parsed_url.path.startswith(
            FOREIGN_REPORT_PATH_PREFIXES
        ):
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
        """Record an unhandled JavaScript exception raised by a crawled page.

        Args:
            error (object): The ``pageerror`` payload, a JavaScript ``Error``
                whose only guaranteed surface is its string form.

        Returns:
            None
        """
        self._javascript_errors.append(
            JavaScriptError(url=self._base_url, message=str(error))
        )

    def build_artifact(self, routes: list[DiscoveredRoute]) -> dict[str, object]:
        """Return the JSON document describing a completed crawl.

        Args:
            routes (list[DiscoveredRoute]): The routes :meth:`crawl` returned.

        Returns:
            dict[str, object]: The crawl context, the route records, each with
            exactly ``url``, ``parent_route``, ``discovered_at`` and
            ``status_code``, and any JavaScript errors observed.
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
        """Write a crawl result as the JSON sitemap artifact.

        Args:
            routes (list[DiscoveredRoute]): The routes :meth:`crawl` returned.
            sitemap_path (Path): The destination file; parent directories are
                created.

        Returns:
            Path: The path the artifact was written to.
        """
        sitemap_path.parent.mkdir(parents=True, exist_ok=True)
        sitemap_path.write_text(
            json.dumps(self.build_artifact(routes), indent=2), encoding="utf-8"
        )
        return sitemap_path


def load_sitemap(sitemap_path: Path = DEFAULT_SITEMAP_PATH) -> list[DiscoveredRoute]:
    """Return the routes a previously generated sitemap records.

    Args:
        sitemap_path (Path): The location of the artifact.

    Returns:
        list[DiscoveredRoute]: The recorded routes, or an empty list when the
        file is missing or cannot be read or parsed.
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
    """Run a crawl synchronously, write the sitemap and return its routes.

    The entry point for pytest collection. It starts its own event loop, so it
    must not be called from inside a running loop.

    Args:
        base_url (str): The absolute URL the crawl starts from.
        sitemap_path (Path): The destination of the generated artifact.
        max_depth (int): The deepest link level followed.
        max_pages (int): The most routes recorded.

    Returns:
        list[DiscoveredRoute]: The discovered routes, also written to
        ``sitemap_path``.
    """
    crawler = SiteMapCrawler(base_url, max_depth=max_depth, max_pages=max_pages)
    routes = asyncio.run(crawler.crawl())
    crawler.write_sitemap(routes, sitemap_path)
    return routes

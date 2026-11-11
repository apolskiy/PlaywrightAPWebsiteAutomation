"""Health checks generated for every route the crawler discovers.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains six tests, each run once per discovered route: the route
answers HTTP 200; it loads with a clean first-party console, network and
JavaScript log; it renders a visible, non-empty DOM root; it publishes a meta
description within usable length bounds; and it fits the desktop and the mobile
viewport without horizontal overflow. It also contains the
``pytest_generate_tests`` hook that parameterizes them and ``_resolve_routes``,
which supplies the route list.

The route list is resolved at collection time, before any test runs, by
re-crawling the site or, with ``--use-cached-sitemap``, reading
``reports/sitemap.json``. The tests run on the deployment path. A failure
names the route and means that published page is unreachable, broken,
undescribed or too wide, whichever check failed.

**The route list is not written by hand.** It is resolved once per session and
memoized, since the hook fires once per test function, so publishing a page
grows the suite with no test edit. The crawler always reports its seed URL, so
an unreachable site fails a health check rather than collecting nothing.

**The meta description is checked because nothing else would notice.** Title
and description are all a search result shows, and neither is visible in the
rendered page, so a page can lose its description and pass every other check.
Being parameterized over discovered routes, the check also covers pages not
yet published: one without a description fails on the first run that finds
it. Below 50 characters reads as a placeholder; above 160 is truncated in a
search result.

**Error-log assertions are scoped to the site's own origin**, except unhandled
JavaScript exceptions, which count whoever served the script.

Specified by ``README.md`` sections "Dynamic Site Discovery" and "Key Features"
(Origin-Scoped Assertions).
"""

from __future__ import annotations

import allure
import pytest

from config.settings import DESKTOP_VIEWPORT, MOBILE_VIEWPORT, Settings
from pages.route_page import RoutePage
from utils.site_crawler import (
    DEFAULT_SITEMAP_PATH,
    DiscoveredRoute,
    discover_routes,
    load_sitemap,
)

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Dynamic Route Discovery and Health"

#: MEMOIZED. The discovered routes, keyed by base URL, so the hook that fires
#: once per test function crawls the site once per session.
_DISCOVERED_ROUTES: dict[str, list[DiscoveredRoute]] = {}

#: HEALTHY STATUS. The status a route must return.
EXPECTED_STATUS_CODE = 200

#: BOUNDED (added 2026-08-09). The usable length of a meta description, in
#: characters: shorter reads as a placeholder, longer is truncated in a search
#: result.
MIN_DESCRIPTION_LENGTH = 50
MAX_DESCRIPTION_LENGTH = 160


def _resolve_routes(config: pytest.Config) -> list[DiscoveredRoute]:
    """Return the routes to parameterize over, crawling only when necessary.

    Args:
        config (pytest.Config): The pytest config, read for
            ``--use-cached-sitemap``.

    Returns:
        list[DiscoveredRoute]: The discovered routes, never empty, since the
        crawler always reports its seed URL. An empty or missing cache falls
        back to a crawl.
    """
    framework_settings = Settings.from_env()
    memoized_routes = _DISCOVERED_ROUTES.get(framework_settings.base_url)
    if memoized_routes is not None:
        return memoized_routes

    routes: list[DiscoveredRoute] = []
    if config.getoption("--use-cached-sitemap"):
        routes = load_sitemap(DEFAULT_SITEMAP_PATH)
    if not routes:
        routes = discover_routes(framework_settings.base_url, DEFAULT_SITEMAP_PATH)

    _DISCOVERED_ROUTES[framework_settings.base_url] = routes
    return routes


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parameterize each test taking ``discovered_route`` across every route.

    Test ids are the route paths.

    Args:
        metafunc (pytest.Metafunc): The test function being collected.

    Returns:
        None
    """
    if "discovered_route" in metafunc.fixturenames:
        routes = _resolve_routes(metafunc.config)
        metafunc.parametrize(
            "discovered_route", routes, ids=[route.route_id for route in routes]
        )


@pytest.mark.test_id("PAWA_10001")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route answers with HTTP 200")
@allure.severity(allure.severity_level.BLOCKER)
def test_route_responds_with_http_200(
    desktop_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """Assert a discovered route still answers HTTP 200 when the test runs.

    Args:
        desktop_route_page (RoutePage): The diagnostics-recording route Page
            Object at the desktop viewport.
        discovered_route (DiscoveredRoute): The route this case checks.

    Returns:
        None
    """
    with allure.step(f"Navigate to {discovered_route.url}"):
        observed_status = desktop_route_page.open_route(discovered_route.url)

    with allure.step("Verify the document status is 200"):
        assert observed_status == EXPECTED_STATUS_CODE, (
            f"Route {discovered_route.url} returned HTTP {observed_status}; it was "
            f"discovered from '{discovered_route.parent_route or '(seed)'}' with "
            f"HTTP {discovered_route.status_code} at {discovered_route.discovered_at}."
        )


@pytest.mark.test_id("PAWA_10002")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route loads without console or network errors")
@allure.severity(allure.severity_level.CRITICAL)
def test_route_loads_without_console_or_network_errors(
    desktop_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """Assert a route loads with no first-party error and no JavaScript exception.

    Broken resources, failed requests and console errors count only when they
    belong to the site's own origin; third-party ones are recorded and attached
    but do not decide the verdict. Unhandled JavaScript exceptions count
    whoever served the script. When sub-resources have not settled, each
    message says the list may be incomplete. Design: ``README.md`` section
    "Key Features" (Origin-Scoped Assertions).

    Args:
        desktop_route_page (RoutePage): The diagnostics-recording route Page
            Object at the desktop viewport.
        discovered_route (DiscoveredRoute): The route this case checks.

    Returns:
        None
    """
    with allure.step(f"Navigate to {discovered_route.url}"):
        desktop_route_page.open_route(discovered_route.url)

    with allure.step("Let sub-resources finish before reading the error log"):
        settled = desktop_route_page.settle_sub_resources()

    diagnostics = desktop_route_page.diagnostics
    with allure.step(f"Collect the browser log ({diagnostics.summary()})"):
        allure.attach(
            diagnostics.report(),
            name="Browser diagnostics",
            attachment_type=allure.attachment_type.TEXT,
        )

    unsettled_note = (
        ""
        if settled
        else " Note: sub-resources had not finished loading when the log was read, "
        "so this list may be incomplete."
    )

    with allure.step("Verify no first-party sub-resource returned an error status"):
        assert not diagnostics.first_party_broken_resources, (
            f"Route {discovered_route.url} requested resources of its own that "
            f"failed to load: {diagnostics.first_party_broken_resources}.{unsettled_note}"
        )

    with allure.step("Verify no first-party request failed at the network level"):
        assert not diagnostics.first_party_failed_requests, (
            f"Route {discovered_route.url} had failed network requests to its own "
            f"origin: {diagnostics.first_party_failed_requests}.{unsettled_note}"
        )

    with allure.step("Verify the console logged no first-party errors"):
        assert not diagnostics.first_party_console_errors, (
            f"Route {discovered_route.url} logged console errors: "
            f"{diagnostics.first_party_console_errors}.{unsettled_note}"
        )

    with allure.step("Verify no unhandled JavaScript exception was raised"):
        assert not diagnostics.javascript_errors, (
            f"Route {discovered_route.url} raised unhandled JavaScript exceptions: "
            f"{diagnostics.javascript_errors}."
        )


@pytest.mark.test_id("PAWA_10003")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route renders a visible DOM root")
@allure.severity(allure.severity_level.CRITICAL)
def test_route_renders_a_visible_dom_root(
    desktop_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """Assert a route renders a visible body containing text, not just a 200.

    Args:
        desktop_route_page (RoutePage): The diagnostics-recording route Page
            Object at the desktop viewport.
        discovered_route (DiscoveredRoute): The route this case checks.

    Returns:
        None
    """
    with allure.step(f"Navigate to {discovered_route.url}"):
        desktop_route_page.open_route(discovered_route.url)

    with allure.step("Verify the document body is rendered and non-empty"):
        document_root = desktop_route_page.document_root()
        assert document_root.is_visible(), (
            f"Route {discovered_route.url} returned a document with no visible body."
        )
        assert document_root.inner_text().strip(), (
            f"Route {discovered_route.url} rendered a body containing no text."
        )


@pytest.mark.test_id("PAWA_10004")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route publishes a usable meta description")
@allure.severity(allure.severity_level.NORMAL)
def test_route_publishes_a_meta_description(
    desktop_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """Assert a route declares a non-blank meta description of usable length.

    The length must lie between ``MIN_DESCRIPTION_LENGTH`` and
    ``MAX_DESCRIPTION_LENGTH`` after trimming.

    Args:
        desktop_route_page (RoutePage): The diagnostics-recording route Page
            Object at the desktop viewport.
        discovered_route (DiscoveredRoute): The route this case checks.

    Returns:
        None
    """
    with allure.step(f"Navigate to {discovered_route.url}"):
        desktop_route_page.open_route(discovered_route.url)

    with allure.step("Read the route's meta description"):
        description = desktop_route_page.meta_description()
        allure.attach(
            repr(description),
            name="Meta description",
            attachment_type=allure.attachment_type.TEXT,
        )

    with allure.step("Verify the route declares a description at all"):
        assert description is not None, (
            f"Route {discovered_route.url} publishes no "
            '<meta name="description">. A search engine will then quote whatever '
            "text it finds first, which is not a decision worth leaving to it."
        )

    with allure.step("Verify the description is not blank"):
        trimmed = description.strip()
        assert trimmed, (
            f"Route {discovered_route.url} declares a meta description tag whose "
            "content is empty, which is worse than omitting it: it looks "
            "deliberate."
        )

    with allure.step(
        f"Verify the description is {MIN_DESCRIPTION_LENGTH}-"
        f"{MAX_DESCRIPTION_LENGTH} characters"
    ):
        assert MIN_DESCRIPTION_LENGTH <= len(trimmed) <= MAX_DESCRIPTION_LENGTH, (
            f"Route {discovered_route.url} has a {len(trimmed)}-character meta "
            f"description; usable range is {MIN_DESCRIPTION_LENGTH}-"
            f"{MAX_DESCRIPTION_LENGTH}. Shorter reads as a placeholder, longer is "
            f"truncated in a search result. Content: {trimmed!r}"
        )


@pytest.mark.test_id("PAWA_10005")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route fits the desktop viewport")
@allure.severity(allure.severity_level.NORMAL)
def test_route_fits_the_desktop_viewport(
    desktop_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """Assert a route does not overflow horizontally at 1920x1080.

    Args:
        desktop_route_page (RoutePage): The diagnostics-recording route Page
            Object at the desktop viewport.
        discovered_route (DiscoveredRoute): The route this case checks.

    Returns:
        None
    """
    with allure.step(f"Navigate to {discovered_route.url}"):
        desktop_route_page.open_route(discovered_route.url)

    with allure.step(f"Verify the layout fits {DESKTOP_VIEWPORT['width']}px"):
        assert not desktop_route_page.has_horizontal_overflow(), (
            f"Route {discovered_route.url} overflows the desktop viewport "
            f"horizontally ({desktop_route_page.document_scroll_width()}px wide)."
        )


@pytest.mark.test_id("PAWA_10006")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route fits the mobile viewport")
@allure.severity(allure.severity_level.CRITICAL)
def test_route_fits_the_mobile_viewport(
    mobile_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """Assert a route does not overflow horizontally at 390x844.

    Args:
        mobile_route_page (RoutePage): The diagnostics-recording route Page
            Object at the mobile viewport.
        discovered_route (DiscoveredRoute): The route this case checks.

    Returns:
        None
    """
    with allure.step(f"Navigate to {discovered_route.url}"):
        mobile_route_page.open_route(discovered_route.url)

    with allure.step(f"Verify the layout fits {MOBILE_VIEWPORT['width']}px"):
        assert not mobile_route_page.has_horizontal_overflow(), (
            f"Route {discovered_route.url} overflows the mobile viewport "
            f"horizontally ({mobile_route_page.document_scroll_width()}px wide)."
        )

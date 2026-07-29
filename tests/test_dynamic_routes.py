"""Health checks generated dynamically from the crawler's route discovery.

The route list is not written by hand. At collection time the suite either
re-crawls the site or reuses ``reports/sitemap.json``, then parameterises every
test in this module across whatever it found. Publishing a new HTML page is
therefore all it takes to grow the suite - no test edit required.

Each discovered route is checked for a 200 response, a clean console and network
log, a rendered DOM root, and a layout that fits both the desktop and the mobile
viewport.
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

#: Collection-time memo of the discovered routes, keyed by base URL.
#: ``pytest_generate_tests`` runs once per test function, so without this the
#: site would be crawled once for every test in the module.
_DISCOVERED_ROUTES: dict[str, list[DiscoveredRoute]] = {}

#: Status a route must return to be considered healthy.
EXPECTED_STATUS_CODE = 200


def _resolve_routes(config: pytest.Config) -> list[DiscoveredRoute]:
    """Return the routes to parameterise over, crawling only when necessary.

    Args:
        config: The pytest config, consulted for ``--use-cached-sitemap``.

    Returns:
        The discovered routes. The crawler always reports its seed URL, so this
        never returns an empty list - an unreachable site surfaces as a failing
        health check rather than a silently empty test suite.
    """
    framework_settings = Settings.from_env()
    memoised_routes = _DISCOVERED_ROUTES.get(framework_settings.base_url)
    if memoised_routes is not None:
        return memoised_routes

    routes: list[DiscoveredRoute] = []
    if config.getoption("--use-cached-sitemap"):
        routes = load_sitemap(DEFAULT_SITEMAP_PATH)
    if not routes:
        routes = discover_routes(framework_settings.base_url, DEFAULT_SITEMAP_PATH)

    _DISCOVERED_ROUTES[framework_settings.base_url] = routes
    return routes


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parameterise route-aware tests across every discovered route.

    Args:
        metafunc: The test function being collected.
    """
    if "discovered_route" in metafunc.fixturenames:
        routes = _resolve_routes(metafunc.config)
        metafunc.parametrize(
            "discovered_route", routes, ids=[route.route_id for route in routes]
        )


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route answers with HTTP 200")
@allure.severity(allure.severity_level.BLOCKER)
def test_route_responds_with_http_200(
    desktop_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """A discovered route must still serve a 200 when the test runs.

    Args:
        desktop_route_page: Diagnostics-recording page at the desktop viewport.
        discovered_route: One route supplied by the discovery engine.
    """
    with allure.step(f"Navigate to {discovered_route.url}"):
        observed_status = desktop_route_page.open_route(discovered_route.url)

    with allure.step("Verify the document status is 200"):
        assert observed_status == EXPECTED_STATUS_CODE, (
            f"Route {discovered_route.url} returned HTTP {observed_status}; it was "
            f"discovered from '{discovered_route.parent_route or '(seed)'}' with "
            f"HTTP {discovered_route.status_code} at {discovered_route.discovered_at}."
        )


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route loads without console or network errors")
@allure.severity(allure.severity_level.CRITICAL)
def test_route_loads_without_console_or_network_errors(
    desktop_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """No route may log a console error, break a request, or throw in JavaScript.

    Args:
        desktop_route_page: Diagnostics-recording page at the desktop viewport.
        discovered_route: One route supplied by the discovery engine.
    """
    with allure.step(f"Navigate to {discovered_route.url}"):
        desktop_route_page.open_route(discovered_route.url)

    with allure.step("Verify no sub-resource returned an error status"):
        assert not desktop_route_page.broken_resources, (
            "The route requested resources that failed to load: "
            f"{desktop_route_page.broken_resources}."
        )

    with allure.step("Verify no request failed at the network level"):
        assert not desktop_route_page.failed_requests, (
            f"The route had failed network requests: {desktop_route_page.failed_requests}."
        )

    with allure.step("Verify the console logged no errors"):
        assert not desktop_route_page.console_errors, (
            f"The route logged console errors: {desktop_route_page.console_errors}."
        )

    with allure.step("Verify no unhandled JavaScript exception was raised"):
        assert not desktop_route_page.javascript_errors, (
            "The route raised unhandled JavaScript exceptions: "
            f"{desktop_route_page.javascript_errors}."
        )


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route renders a visible DOM root")
@allure.severity(allure.severity_level.CRITICAL)
def test_route_renders_a_visible_dom_root(
    desktop_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """A 200 response is not enough: the route must render actual content.

    Args:
        desktop_route_page: Diagnostics-recording page at the desktop viewport.
        discovered_route: One route supplied by the discovery engine.
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


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route fits the desktop viewport")
@allure.severity(allure.severity_level.NORMAL)
def test_route_fits_the_desktop_viewport(
    desktop_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """No route may scroll sideways at 1920x1080.

    Args:
        desktop_route_page: Diagnostics-recording page at the desktop viewport.
        discovered_route: One route supplied by the discovery engine.
    """
    with allure.step(f"Navigate to {discovered_route.url}"):
        desktop_route_page.open_route(discovered_route.url)

    with allure.step(f"Verify the layout fits {DESKTOP_VIEWPORT['width']}px"):
        assert not desktop_route_page.has_horizontal_overflow(), (
            f"Route {discovered_route.url} overflows the desktop viewport "
            f"horizontally ({desktop_route_page.document_scroll_width()}px wide)."
        )


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route fits the mobile viewport")
@allure.severity(allure.severity_level.CRITICAL)
def test_route_fits_the_mobile_viewport(
    mobile_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """No route may scroll sideways at 390x844.

    Args:
        mobile_route_page: Diagnostics-recording page at the mobile viewport.
        discovered_route: One route supplied by the discovery engine.
    """
    with allure.step(f"Navigate to {discovered_route.url}"):
        mobile_route_page.open_route(discovered_route.url)

    with allure.step(f"Verify the layout fits {MOBILE_VIEWPORT['width']}px"):
        assert not mobile_route_page.has_horizontal_overflow(), (
            f"Route {discovered_route.url} overflows the mobile viewport "
            f"horizontally ({mobile_route_page.document_scroll_width()}px wide)."
        )

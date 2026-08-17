"""Health checks generated dynamically from the crawler's route discovery.

The route list is not written by hand. At collection time the suite either
re-crawls the site or reuses ``reports/sitemap.json``, then parameterizes every
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

#: Bounds on a useful meta description, in characters. The lower bound rejects a
#: placeholder that technically satisfies "not empty"; the upper one is where
#: search results truncate, so anything beyond it is written for nobody.
MIN_DESCRIPTION_LENGTH = 50
MAX_DESCRIPTION_LENGTH = 160


def _resolve_routes(config: pytest.Config) -> list[DiscoveredRoute]:
    """Return the routes to parameterize over, crawling only when necessary.

    Args:
        config: The pytest config, consulted for ``--use-cached-sitemap``.

    Returns:
        The discovered routes. The crawler always reports its seed URL, so this
        never returns an empty list - an unreachable site surfaces as a failing
        health check rather than a silently empty test suite.
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
    """Parameterize route-aware tests across every discovered route.

    Args:
        metafunc: The test function being collected.
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


@pytest.mark.test_id("PAWA_10002")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route loads without console or network errors")
@allure.severity(allure.severity_level.CRITICAL)
def test_route_loads_without_console_or_network_errors(
    desktop_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """No route may log a console error, break a request, or throw in JavaScript.

    The three network-facing assertions are scoped to the site's own origin,
    and that scoping is the whole reason this test can stay on the deployment
    path. Every project panel embeds a CI badge image served by GitHub, so an
    unscoped assertion here would fail this suite whenever GitHub had a bad
    minute - a third-party dependency arriving through a sub-resource rather
    than through anything the test does on purpose. Third-party problems are
    still recorded and still reported; they simply do not decide the verdict.

    Unhandled JavaScript exceptions are not scoped that way, deliberately: an
    exception is raised by a script this site chose to run, whoever served it.

    Args:
        desktop_route_page: Diagnostics-recording page at the desktop viewport.
        discovered_route: One route supplied by the discovery engine.
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


@pytest.mark.test_id("PAWA_10004")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every discovered route publishes a usable meta description")
@allure.severity(allure.severity_level.NORMAL)
def test_route_publishes_a_meta_description(
    desktop_route_page: RoutePage, discovered_route: DiscoveredRoute
) -> None:
    """A route must describe itself to a search result, within usable bounds.

    The description and the title are the whole of what a search result shows,
    and neither is visible anywhere in the rendered page - so a page can lose
    its description, or never have had one, and look completely healthy to every
    other check in this suite. That is precisely the kind of claim this suite
    exists to hold: invisible from a browser, and wrong until something reads it.

    Being parameterized over discovered routes, this also covers pages that do
    not exist yet: publish one without a description and it fails on the run
    that first discovers it, rather than quietly ranking on nothing.

    Args:
        desktop_route_page: Diagnostics-recording page at the desktop viewport.
        discovered_route: One route supplied by the discovery engine.
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


@pytest.mark.test_id("PAWA_10006")
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

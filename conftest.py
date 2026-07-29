"""Pytest fixtures, viewport provisioning, and AI failure-diagnostics wiring.

Every browser context in this suite is created here with an explicit viewport so
that the responsive assertions in ``tests/test_responsive.py`` are reproducible
rather than dependent on the host window size. The module also installs the
``pytest_runtest_makereport`` wrapper that captures a DOM snapshot, a screenshot,
and - when enabled - a Claude root-cause report for any failing test.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator

import allure
import pytest
from playwright.sync_api import Browser, BrowserContext, Error as PlaywrightError, expect

from config.settings import DESKTOP_VIEWPORT, MOBILE_VIEWPORT, Settings
from pages.base_page import BasePage
from pages.landing_page import LandingPage
from pages.route_page import RoutePage
from utils.claude_inspector import ClaudeTestInspector, FailureContext


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the suite's own command-line options.

    Args:
        parser: The pytest option parser.
    """
    parser.addoption(
        "--use-cached-sitemap",
        action="store_true",
        default=False,
        help=(
            "Reuse reports/sitemap.json instead of re-crawling the site during "
            "collection. Speeds up local iteration; CI should re-crawl so a "
            "newly published page is discovered."
        ),
    )


class DiagnosticsRegistry:
    """Tracks the live Page Object of each running test for failure capture.

    Pytest hooks cannot request fixtures, so the fixtures publish their Page
    Object here and the ``makereport`` hook looks it up by node id. Entries are
    removed during fixture teardown, which runs after the call-phase report.
    """

    def __init__(self) -> None:
        self._pages_by_node_id: dict[str, BasePage] = {}
        self._inspector: ClaudeTestInspector | None = None

    def register_page(self, node_id: str, page_object: BasePage) -> None:
        """Associate a Page Object with the test that owns it.

        Args:
            node_id: Pytest node identifier of the owning test.
            page_object: The Page Object driving that test's browser page. Any
                :class:`~pages.base_page.BasePage` subclass is accepted, so
                landing-page and discovered-route tests share one capture path.
        """
        self._pages_by_node_id[node_id] = page_object

    def release_page(self, node_id: str) -> None:
        """Forget the Page Object owned by a finished test.

        Args:
            node_id: Pytest node identifier of the finished test.
        """
        self._pages_by_node_id.pop(node_id, None)

    def page_for(self, node_id: str) -> BasePage | None:
        """Look up the Page Object owned by a test.

        Args:
            node_id: Pytest node identifier of the test.

        Returns:
            The registered Page Object, or ``None`` for tests that never opened
            a browser page.
        """
        return self._pages_by_node_id.get(node_id)

    def inspector(self, settings: Settings) -> ClaudeTestInspector:
        """Return the shared Claude inspector, building it on first use.

        Args:
            settings: Resolved framework configuration.

        Returns:
            A process-wide :class:`ClaudeTestInspector` instance.
        """
        if self._inspector is None:
            self._inspector = ClaudeTestInspector(settings)
        return self._inspector


DIAGNOSTICS_REGISTRY = DiagnosticsRegistry()


@pytest.fixture(name="framework_settings", scope="session")
def fixture_framework_settings() -> Settings:
    """Resolve the framework configuration once per test session.

    Returns:
        The immutable settings snapshot shared by every fixture and hook.
    """
    return Settings.from_env()


@pytest.fixture(name="configure_assertion_timeout", scope="session", autouse=True)
def fixture_configure_assertion_timeout(framework_settings: Settings) -> None:
    """Apply the configured ceiling to all web-first assertions.

    Args:
        framework_settings: Resolved framework configuration.
    """
    expect.set_options(timeout=framework_settings.expect_timeout_ms)


def _open_context(
    browser: Browser, viewport: dict[str, int], *, javascript_enabled: bool = True
) -> BrowserContext:
    """Create an isolated browser context with a fixed viewport.

    A dedicated context per test guarantees a clean cookie jar, storage, and
    viewport, so tests can run in any order or in parallel without interference.

    Args:
        browser: The session-scoped Playwright browser.
        viewport: Viewport geometry applied to the new context.
        javascript_enabled: Set to ``False`` to exercise a site's ``noscript``
            fallback path.

    Returns:
        The newly created context. The caller owns closing it.
    """
    return browser.new_context(
        viewport=viewport,
        java_script_enabled=javascript_enabled,
        ignore_https_errors=False,
    )


def _provision_landing_page(
    browser: Browser,
    framework_settings: Settings,
    node_id: str,
    viewport: dict[str, int],
    *,
    javascript_enabled: bool = True,
) -> Iterator[LandingPage]:
    """Create an isolated context and yield a landing Page Object.

    Args:
        browser: The session-scoped Playwright browser.
        framework_settings: Resolved framework configuration.
        node_id: Pytest node identifier used to register the page for failure
            diagnostics.
        viewport: Viewport geometry applied to the new context.
        javascript_enabled: Set to ``False`` to exercise the site's ``noscript``
            fallback path.

    Yields:
        A :class:`LandingPage` bound to a fresh, correctly sized page.
    """
    context = _open_context(browser, viewport, javascript_enabled=javascript_enabled)
    landing_page = LandingPage(context.new_page(), framework_settings.base_url)
    DIAGNOSTICS_REGISTRY.register_page(node_id, landing_page)
    try:
        yield landing_page
    finally:
        DIAGNOSTICS_REGISTRY.release_page(node_id)
        context.close()


def _provision_route_page(
    browser: Browser, node_id: str, viewport: dict[str, int]
) -> Iterator[RoutePage]:
    """Create an isolated context and yield a diagnostics-recording route page.

    Recording is switched on before the page is handed to the test, because
    Playwright only delivers events raised after a listener is attached - a
    console error emitted during the very first navigation would otherwise be
    missed.

    Args:
        browser: The session-scoped Playwright browser.
        node_id: Pytest node identifier used to register the page for failure
            diagnostics.
        viewport: Viewport geometry applied to the new context.

    Yields:
        A :class:`RoutePage` that is already recording console, network, and
        JavaScript errors.
    """
    context = _open_context(browser, viewport)
    route_page = RoutePage(context.new_page())
    route_page.record_diagnostics()
    DIAGNOSTICS_REGISTRY.register_page(node_id, route_page)
    try:
        yield route_page
    finally:
        DIAGNOSTICS_REGISTRY.release_page(node_id)
        context.close()


@pytest.fixture(name="desktop_page")
def fixture_desktop_page(
    browser: Browser,
    framework_settings: Settings,
    request: pytest.FixtureRequest,
) -> Iterator[LandingPage]:
    """Provide a landing page rendered at the desktop viewport (1920x1080).

    Args:
        browser: The session-scoped Playwright browser.
        framework_settings: Resolved framework configuration.
        request: Pytest request object, used for the owning node id.

    Yields:
        A navigated :class:`LandingPage` at desktop dimensions.
    """
    yield from _provision_landing_page(
        browser, framework_settings, request.node.nodeid, DESKTOP_VIEWPORT
    )


@pytest.fixture(name="mobile_page")
def fixture_mobile_page(
    browser: Browser,
    framework_settings: Settings,
    request: pytest.FixtureRequest,
) -> Iterator[LandingPage]:
    """Provide a landing page rendered at the mobile viewport (390x844).

    Args:
        browser: The session-scoped Playwright browser.
        framework_settings: Resolved framework configuration.
        request: Pytest request object, used for the owning node id.

    Yields:
        A navigated :class:`LandingPage` at mobile dimensions.
    """
    yield from _provision_landing_page(
        browser, framework_settings, request.node.nodeid, MOBILE_VIEWPORT
    )


@pytest.fixture(name="scriptless_page")
def fixture_scriptless_page(
    browser: Browser,
    framework_settings: Settings,
    request: pytest.FixtureRequest,
) -> Iterator[LandingPage]:
    """Provide a desktop landing page with JavaScript disabled.

    Used to prove the anti-scraping fallback: without scripting the obfuscated
    placeholders must stay encoded and the ``noscript`` contact link must show.

    Args:
        browser: The session-scoped Playwright browser.
        framework_settings: Resolved framework configuration.
        request: Pytest request object, used for the owning node id.

    Yields:
        A :class:`LandingPage` whose context has scripting switched off.
    """
    yield from _provision_landing_page(
        browser,
        framework_settings,
        request.node.nodeid,
        DESKTOP_VIEWPORT,
        javascript_enabled=False,
    )


@pytest.fixture(name="desktop_route_page")
def fixture_desktop_route_page(
    browser: Browser, request: pytest.FixtureRequest
) -> Iterator[RoutePage]:
    """Provide a diagnostics-recording route page at the desktop viewport.

    Args:
        browser: The session-scoped Playwright browser.
        request: Pytest request object, used for the owning node id.

    Yields:
        A :class:`RoutePage` at 1920x1080, recording from the outset.
    """
    yield from _provision_route_page(browser, request.node.nodeid, DESKTOP_VIEWPORT)


@pytest.fixture(name="mobile_route_page")
def fixture_mobile_route_page(
    browser: Browser, request: pytest.FixtureRequest
) -> Iterator[RoutePage]:
    """Provide a diagnostics-recording route page at the mobile viewport.

    Args:
        browser: The session-scoped Playwright browser.
        request: Pytest request object, used for the owning node id.

    Yields:
        A :class:`RoutePage` at 390x844, recording from the outset.
    """
    yield from _provision_route_page(browser, request.node.nodeid, MOBILE_VIEWPORT)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Attach failure diagnostics to the Allure report for failing tests.

    Args:
        item: The test item being reported on.
        call: The phase result produced by pytest.

    Yields:
        Control back to pytest so the downstream hooks build the report.

    Returns:
        The report produced by the wrapped hook implementations, unmodified.
    """
    report = yield
    if report.when == "call" and report.failed:
        _attach_failure_diagnostics(item, _render_failure(call, report))
    return report


def _render_failure(call: pytest.CallInfo, report: pytest.TestReport) -> str:
    """Render a failure into the plain text handed to the AI inspector.

    Args:
        call: The phase result carrying the captured exception, if any.
        report: The report holding the fallback long representation.

    Returns:
        A short-style traceback when an exception was captured, otherwise the
        report's own long representation.
    """
    if call.excinfo is not None:
        return str(call.excinfo.getrepr(style="short"))
    return str(report.longrepr)


def _attach_failure_diagnostics(item: pytest.Item, error_text: str) -> None:
    """Capture page evidence and an optional AI triage report for a failure.

    Diagnostics are best-effort: a browser that already closed must not convert
    a genuine assertion failure into a confusing collection error.

    Args:
        item: The failing test item.
        error_text: Rendered representation of the failure.
    """
    landing_page = DIAGNOSTICS_REGISTRY.page_for(item.nodeid)
    if landing_page is None:
        return

    try:
        dom_snapshot = landing_page.dom_snapshot()
        page_url = landing_page.page.url
        allure.attach(
            landing_page.screenshot_png(),
            name="Screenshot at failure",
            attachment_type=allure.attachment_type.PNG,
        )
        allure.attach(
            dom_snapshot,
            name="DOM snapshot at failure",
            attachment_type=allure.attachment_type.HTML,
        )
    except (PlaywrightError, OSError):
        # The page or its context is already gone; there is nothing to capture.
        return

    settings = Settings.from_env()
    inspector = DIAGNOSTICS_REGISTRY.inspector(settings)
    triage_report = inspector.analyse_failure(
        FailureContext(
            test_name=item.nodeid,
            page_url=page_url,
            error_text=error_text,
            dom_snapshot=dom_snapshot,
        )
    )
    if triage_report is not None:
        allure.attach(
            triage_report,
            name=f"Claude root-cause analysis ({inspector.model})",
            attachment_type=allure.attachment_type.TEXT,
        )

"""Pytest fixtures, hooks and failure-evidence capture for the whole suite.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains the session fixtures ``framework_settings``, ``suite_size``
and ``configure_assertion_timeout``; the per-test page fixtures
``desktop_page``, ``mobile_page``, ``scriptless_page``, ``desktop_route_page``
and ``mobile_route_page``; the hooks ``pytest_addoption``, ``pytest_configure``,
``pytest_collection_modifyitems`` and ``pytest_runtest_makereport``; the
``DiagnosticsRegistry`` and ``SuiteSizeRegistry`` that carry state from fixtures
and collection to those hooks, with their ``ActiveSession`` and ``SuiteSize``
records; and the private helpers that open contexts and attach evidence.

Pytest loads it before any test module. Collection runs through it first, where
test IDs are published and the suite size is measured; then every test receives
its page from a fixture here; then, for a failing test, the report hook attaches
the evidence. A fault here therefore breaks collection, every browser test, or
every failure report, not one case.

**Every test gets its own context and viewport.** Each fixture opens an isolated
browser context at an explicit viewport, arms tracing at once, since a trace
captures only what happens after it starts, and arms the page's error recorder
before the first navigation. The responsive assertions are reproducible because
nothing depends on the host window size.

**Evidence is recorded always and written only on failure.** For a failing test
the report hook attaches, in this order, the browser's error log, a full-page
screenshot, the rendered DOM, the Playwright trace and, when enabled, a Claude
root-cause analysis. The error log is also published as a pytest report section,
so it appears beneath the traceback in the terminal and in
``reports/pytest-report.html``. A passing test discards its trace and writes
nothing. Capturing evidence never replaces the real failure: a closed page or a
failed trace is noted and the test still reports its own error.

**Hooks cannot request fixtures**, so fixtures publish each live session to
``DIAGNOSTICS_REGISTRY`` by node id and the report hook looks it up there.
Teardown releases it after the call-phase report has been built.

**The suite is measured before selection.** ``pytest_collection_modifyitems``
runs ``tryfirst``, ahead of the ``-m`` and ``-k`` filtering pytest applies in
the same hook, and records the counts for ``test_published_suite_size.py``. A
run naming specific files or node ids, or selecting more than one browser
engine, records why its counts cannot be compared with the published figure.

**Output directories exist before anything writes.** ``pytest_configure``
creates them under the rootdir, not the working directory, so a fresh clone or
CI runner never fails on a missing directory wherever ``pytest`` was invoked.

Specified by ``README.md`` sections "Test Design Principles", "Reporting" and
"Test Identity", and the Key Features entry "Published Figures Verify
Themselves".
"""

from __future__ import annotations

import re
from collections.abc import Generator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import allure
import pytest
from playwright.sync_api import Browser, BrowserContext, Error as PlaywrightError, expect

from config.settings import DESKTOP_VIEWPORT, MOBILE_VIEWPORT, Settings
from pages.base_page import BasePage
from pages.landing_page import LandingPage
from pages.route_page import RoutePage
from utils.claude_inspector import ClaudeTestInspector, FailureContext

#: CREATED UP FRONT (added 2026-07-29). The directories the suite writes into,
#: made by ``pytest_configure`` before the session starts.
ARTIFACT_DIRECTORIES: Final[tuple[str, ...]] = (
    "reports",
    "reports/traces",
    "allure-results",
)

#: UNSAFE IN A FILENAME. The characters replaced when a pytest node id becomes a
#: trace file name.
UNSAFE_FILENAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]+")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the suite's own command-line option, ``--use-cached-sitemap``.

    Args:
        parser (pytest.Parser): The pytest option parser.

    Returns:
        None
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


def pytest_configure(config: pytest.Config) -> None:
    """Create the report and artifact directories before the session starts.

    Runs once, ahead of collection and of any reporting plugin's first write,
    and resolves every path against the rootdir.

    Args:
        config (pytest.Config): The active pytest configuration, read for its
            rootdir.

    Returns:
        None
    """
    for directory_name in ARTIFACT_DIRECTORIES:
        (config.rootpath / directory_name).mkdir(parents=True, exist_ok=True)


@dataclass
class ActiveSession:
    """Hold the live browser objects belonging to one running test.

    Attributes:
        page_object (BasePage): The Page Object driving the test's page.
        context (BrowserContext): The browser context that owns the page and
            the tracing session.
        trace_saved (bool): Whether the trace has been written to disk, which
            keeps the same tracing session from being stopped twice, an error
            in Playwright.
    """

    page_object: BasePage
    context: BrowserContext
    trace_saved: bool = field(default=False)


class DiagnosticsRegistry:
    """Track the live browser session of each running test, by node id.

    Fixtures register a session here and the ``makereport`` hook looks it up.
    Entries are removed during fixture teardown, after the call-phase report.
    It also holds the one shared Claude inspector.
    """

    def __init__(self) -> None:
        self._sessions_by_node_id: dict[str, ActiveSession] = {}
        self._inspector: ClaudeTestInspector | None = None

    def register_session(
        self, node_id: str, page_object: BasePage, context: BrowserContext
    ) -> ActiveSession:
        """Register a browser session under the test that owns it.

        Args:
            node_id (str): The pytest node id of the owning test.
            page_object (BasePage): The Page Object driving that test's page.
                Any :class:`~pages.base_page.BasePage` subclass is accepted, so
                landing-page and discovered-route tests share one capture path.
            context (BrowserContext): The browser context backing the page.

        Returns:
            ActiveSession: The registered session, whose ``trace_saved`` the
            caller reads during teardown.
        """
        session = ActiveSession(page_object=page_object, context=context)
        self._sessions_by_node_id[node_id] = session
        return session

    def release_session(self, node_id: str) -> None:
        """Forget the session owned by a finished test.

        Args:
            node_id (str): The pytest node id of the finished test.

        Returns:
            None
        """
        self._sessions_by_node_id.pop(node_id, None)

    def session_for(self, node_id: str) -> ActiveSession | None:
        """Return the session owned by a test.

        Args:
            node_id (str): The pytest node id of the test.

        Returns:
            ActiveSession | None: The registered session, or None for a test
            that never opened a browser page.
        """
        return self._sessions_by_node_id.get(node_id)

    def inspector(self, settings: Settings) -> ClaudeTestInspector:
        """Return the shared Claude inspector, building it on first use.

        Args:
            settings (Settings): The resolved framework configuration.

        Returns:
            ClaudeTestInspector: The one instance shared by the process.
        """
        if self._inspector is None:
            self._inspector = ClaudeTestInspector(settings)
        return self._inspector


DIAGNOSTICS_REGISTRY = DiagnosticsRegistry()


#: INCOMPARABLE RUNS (added 2026-08-04). Why a run's collected size cannot be
#: held against a published figure: it named a subset, or it selected more than
#: one browser engine.
PARTIAL_COLLECTION_REASON: Final[str] = (
    "This run named specific test files or node ids, so the collected counts "
    "describe a subset and cannot be compared with a figure published for the "
    "whole suite."
)
MULTI_ENGINE_REASON: Final[str] = (
    "This run selected more than one browser engine, so every browser-scoped "
    "test is collected once per engine and the totals describe a multi-engine "
    "run rather than the single-engine suite the site quotes."
)


@dataclass(frozen=True)
class SuiteSize:
    """Hold the suite's size, measured before any selection narrowed it.

    Attributes:
        total (int): Every test the suite collects.
        deployment (int): The tests on the deployment path, meaning everything
            not marked ``external``.
        incomparable_reason (str | None): Why these counts must not be compared
            with a figure the site publishes, or None when the comparison holds.
    """

    total: int
    deployment: int
    incomparable_reason: str | None


class SuiteSizeRegistry:
    """Carry the collected suite size from the collection hook to a fixture."""

    def __init__(self) -> None:
        self._size: SuiteSize | None = None

    def record(self, size: SuiteSize) -> None:
        """Store the measurement taken during collection.

        Args:
            size (SuiteSize): The suite size observed before deselection.

        Returns:
            None
        """
        self._size = size

    def current(self) -> SuiteSize:
        """Return the measurement taken during collection.

        Returns:
            SuiteSize: The recorded measurement.

        Raises:
            RuntimeError: When read before collection has run.
        """
        if self._size is None:
            raise RuntimeError("Suite size was read before collection completed.")
        return self._size


SUITE_SIZE_REGISTRY = SuiteSizeRegistry()


@pytest.hookimpl(tryfirst=True)
def _publish_test_ids(items: list[pytest.Item]) -> None:
    """Republish each test's ``test_id`` marker as an Allure label and a JUnit property.

    Runs at collection time, so the label is attached before any reporter builds
    a result. Design: ``README.md`` section "Test Identity", which links
    PortfolioTestInsights, the consumer.

    Args:
        items (list[pytest.Item]): Every collected item, annotated in place. An
            item carrying no marker is left untouched.

    Returns:
        None
    """
    for item in items:
        marker = item.get_closest_marker("test_id")
        if marker is None or not marker.args:
            continue
        test_id = str(marker.args[0])
        item.user_properties.append(("test_id", test_id))
        item.add_marker(allure.label("test_id", test_id))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Publish test IDs and measure the suite before ``-m`` or ``-k`` removes anything.

    Records the total, the deployment-path count and, for a run naming files or
    node ids or selecting several engines, why the counts are incomparable.
    Runs ``tryfirst`` per ``README.md`` Key Features entry "Published Figures
    Verify Themselves".

    Args:
        config (pytest.Config): The active pytest configuration.
        items (list[pytest.Item]): Every collected item, before deselection.

    Returns:
        None
    """
    _publish_test_ids(items)

    names_paths = any(
        str(argument).endswith(".py") or "::" in str(argument)
        for argument in config.invocation_params.args
    )
    # Added 2026-08-04: `--browser` is repeatable and each browser-scoped test is
    # collected once per engine, so a two-engine run measures something else.
    # README.md section "Quick Start".
    selected_engines = config.getoption("browser", default=None) or []

    if names_paths:
        reason: str | None = PARTIAL_COLLECTION_REASON
    elif len(selected_engines) > 1:
        reason = MULTI_ENGINE_REASON
    else:
        reason = None

    SUITE_SIZE_REGISTRY.record(
        SuiteSize(
            total=len(items),
            deployment=sum(
                1 for item in items if item.get_closest_marker("external") is None
            ),
            incomparable_reason=reason,
        )
    )


@pytest.fixture(name="framework_settings", scope="session")
def fixture_framework_settings() -> Settings:
    """Return the framework configuration, resolved once per session.

    Returns:
        Settings: The frozen snapshot shared by every fixture and hook.
    """
    return Settings.from_env()


@pytest.fixture(name="suite_size", scope="session")
def fixture_suite_size() -> SuiteSize:
    """Return the collected suite size, for tests that check what the site claims.

    Returns:
        SuiteSize: The measurement taken during collection.
    """
    return SUITE_SIZE_REGISTRY.current()


@pytest.fixture(name="configure_assertion_timeout", scope="session", autouse=True)
def fixture_configure_assertion_timeout(framework_settings: Settings) -> None:
    """Apply the configured timeout to every web-first assertion.

    Args:
        framework_settings (Settings): The resolved framework configuration.

    Returns:
        None
    """
    expect.set_options(timeout=framework_settings.expect_timeout_ms)


def _open_context(
    browser: Browser, viewport: dict[str, int], *, javascript_enabled: bool = True
) -> BrowserContext:
    """Return a new isolated browser context with a fixed viewport, already tracing.

    Each test gets a clean cookie jar, storage and viewport, and tracing starts
    before the test touches the page.

    Args:
        browser (Browser): The session-scoped Playwright browser.
        viewport (dict[str, int]): The viewport geometry of the new context.
        javascript_enabled (bool): False to exercise a ``noscript`` fallback.

    Returns:
        BrowserContext: The new context, which the caller closes.
    """
    context = browser.new_context(
        viewport=viewport,
        java_script_enabled=javascript_enabled,
        ignore_https_errors=False,
    )
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    return context


def _discard_trace(session: ActiveSession) -> None:
    """Stop tracing without writing an artifact, for a test that passed.

    Args:
        session (ActiveSession): The session whose tracing is torn down. One
            whose trace was already saved on failure is left alone.

    Returns:
        None
    """
    if session.trace_saved:
        return
    try:
        session.context.tracing.stop()
    except PlaywrightError:
        # The context is already gone; there is no tracing session to stop.
        pass


def _provision_landing_page(
    browser: Browser,
    framework_settings: Settings,
    node_id: str,
    viewport: dict[str, int],
    *,
    javascript_enabled: bool = True,
) -> Iterator[LandingPage]:
    """Open an isolated context and yield a landing Page Object, recording errors.

    Args:
        browser (Browser): The session-scoped Playwright browser.
        framework_settings (Settings): The resolved framework configuration.
        node_id (str): The pytest node id the session is registered under for
            failure diagnostics.
        viewport (dict[str, int]): The viewport geometry of the new context.
        javascript_enabled (bool): False to exercise the site's ``noscript``
            fallback.

    Yields:
        LandingPage: A Page Object on a fresh, correctly sized page that is
        already recording browser errors.

    Returns:
        None
    """
    context = _open_context(browser, viewport, javascript_enabled=javascript_enabled)
    landing_page = LandingPage(context.new_page(), framework_settings.base_url)
    landing_page.diagnostics.record()
    session = DIAGNOSTICS_REGISTRY.register_session(node_id, landing_page, context)
    try:
        yield landing_page
    finally:
        _discard_trace(session)
        DIAGNOSTICS_REGISTRY.release_session(node_id)
        context.close()


def _provision_route_page(
    browser: Browser, node_id: str, viewport: dict[str, int]
) -> Iterator[RoutePage]:
    """Open an isolated context and yield a route Page Object, recording errors.

    Recording starts before the page reaches the test, so an error raised during
    the first navigation is caught.

    Args:
        browser (Browser): The session-scoped Playwright browser.
        node_id (str): The pytest node id the session is registered under for
            failure diagnostics.
        viewport (dict[str, int]): The viewport geometry of the new context.

    Yields:
        RoutePage: A Page Object already recording console, network and
        JavaScript errors.

    Returns:
        None
    """
    context = _open_context(browser, viewport)
    route_page = RoutePage(context.new_page())
    route_page.diagnostics.record()
    session = DIAGNOSTICS_REGISTRY.register_session(node_id, route_page, context)
    try:
        yield route_page
    finally:
        _discard_trace(session)
        DIAGNOSTICS_REGISTRY.release_session(node_id)
        context.close()


@pytest.fixture(name="desktop_page")
def fixture_desktop_page(
    browser: Browser,
    framework_settings: Settings,
    request: pytest.FixtureRequest,
) -> Iterator[LandingPage]:
    """Yield a landing page at the desktop viewport (1920x1080).

    Args:
        browser (Browser): The session-scoped Playwright browser.
        framework_settings (Settings): The resolved framework configuration.
        request (pytest.FixtureRequest): The request, read for the owning node id.

    Yields:
        LandingPage: A Page Object at desktop dimensions, recording errors.

    Returns:
        None
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
    """Yield a landing page at the mobile viewport (390x844).

    Args:
        browser (Browser): The session-scoped Playwright browser.
        framework_settings (Settings): The resolved framework configuration.
        request (pytest.FixtureRequest): The request, read for the owning node id.

    Yields:
        LandingPage: A Page Object at mobile dimensions, recording errors.

    Returns:
        None
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
    """Yield a desktop landing page with JavaScript disabled.

    The anti-scraping fallback test uses it: without scripting the obfuscated
    placeholders stay encoded and the ``noscript`` contact link shows.

    Args:
        browser (Browser): The session-scoped Playwright browser.
        framework_settings (Settings): The resolved framework configuration.
        request (pytest.FixtureRequest): The request, read for the owning node id.

    Yields:
        LandingPage: A Page Object whose context has scripting switched off.

    Returns:
        None
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
    """Yield a route page at the desktop viewport, recording errors.

    Args:
        browser (Browser): The session-scoped Playwright browser.
        request (pytest.FixtureRequest): The request, read for the owning node id.

    Yields:
        RoutePage: A Page Object at 1920x1080, recording from the outset.

    Returns:
        None
    """
    yield from _provision_route_page(browser, request.node.nodeid, DESKTOP_VIEWPORT)


@pytest.fixture(name="mobile_route_page")
def fixture_mobile_route_page(
    browser: Browser, request: pytest.FixtureRequest
) -> Iterator[RoutePage]:
    """Yield a route page at the mobile viewport, recording errors.

    Args:
        browser (Browser): The session-scoped Playwright browser.
        request (pytest.FixtureRequest): The request, read for the owning node id.

    Yields:
        RoutePage: A Page Object at 390x844, recording from the outset.

    Returns:
        None
    """
    yield from _provision_route_page(browser, request.node.nodeid, MOBILE_VIEWPORT)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Attach failure evidence to the reports of a test failing in its call phase.

    Args:
        item (pytest.Item): The test item being reported on.
        call (pytest.CallInfo): The phase result produced by pytest.

    Yields:
        None: Control back to pytest, so the wrapped hooks build the report.

    Returns:
        pytest.TestReport: The report the wrapped hooks built, unmodified.
    """
    report = yield
    if report.when == "call" and report.failed:
        _publish_browser_diagnostics(item, report)
        _attach_failure_diagnostics(item, _render_failure(call, report))
    return report


def _browser_diagnostics_text(page_object: BasePage) -> str:
    """Return one page's recorded browser errors as text, tolerating a closed page.

    Args:
        page_object (BasePage): The Page Object driving the failing test.

    Returns:
        str: The rendered diagnostic report, or a note saying why it could not
        be read. It never raises, so the real failure stays the reported one.
    """
    try:
        return page_object.diagnostics.report()
    except PlaywrightError as diagnostics_error:
        return f"Browser diagnostics could not be read: {diagnostics_error}"


def _publish_browser_diagnostics(item: pytest.Item, report: pytest.TestReport) -> None:
    """Append the browser's error log to the pytest report as a section.

    The section appears beneath the traceback in the terminal, the CI log and
    ``reports/pytest-report.html``, per ``README.md`` section "Reporting".

    Args:
        item (pytest.Item): The failing test item.
        report (pytest.TestReport): The report being built for it.

    Returns:
        None
    """
    session = DIAGNOSTICS_REGISTRY.session_for(item.nodeid)
    if session is None:
        return
    report.sections.append(
        ("Browser diagnostics", _browser_diagnostics_text(session.page_object))
    )


def _render_failure(call: pytest.CallInfo, report: pytest.TestReport) -> str:
    """Return a failure as the plain text handed to the AI inspector.

    Args:
        call (pytest.CallInfo): The phase result carrying the captured
            exception, if any.
        report (pytest.TestReport): The report holding the fallback long
            representation.

    Returns:
        str: A short-style traceback when an exception was captured, otherwise
        the report's own long representation.
    """
    if call.excinfo is not None:
        return str(call.excinfo.getrepr(style="short"))
    return str(report.longrepr)


def _trace_path(item: pytest.Item) -> Path:
    """Return the on-disk location of one test's Playwright trace.

    Args:
        item (pytest.Item): The failing test item.

    Returns:
        Path: A ``.zip`` path under ``reports/traces`` named from the node id.
    """
    safe_name = UNSAFE_FILENAME_PATTERN.sub("_", item.nodeid).strip("_")
    return item.config.rootpath / "reports" / "traces" / f"{safe_name}.zip"


def _attach_trace(item: pytest.Item, session: ActiveSession) -> None:
    """Stop tracing, write the trace, and attach it to the Allure report.

    A trace that cannot be written is replaced by a text attachment saying why.

    Args:
        item (pytest.Item): The failing test item.
        session (ActiveSession): The failing test's live browser session.

    Returns:
        None
    """
    if session.trace_saved:
        return
    trace_path = _trace_path(item)
    try:
        session.context.tracing.stop(path=trace_path)
        session.trace_saved = True
        allure.attach(
            trace_path.read_bytes(),
            name="Playwright trace (open with 'playwright show-trace')",
            attachment_type="application/zip",
            extension="zip",
        )
    except (PlaywrightError, OSError) as trace_error:
        # Decided 2026-07-29: a trace is optional evidence, and capturing it must
        # never make a test report something other than its real failure.
        allure.attach(
            f"Playwright trace could not be captured: {trace_error}",
            name="Trace capture failed",
            attachment_type=allure.attachment_type.TEXT,
        )


def _attach_failure_diagnostics(item: pytest.Item, error_text: str) -> None:
    """Attach the error log, screenshot, DOM, trace and optional AI triage for a failure.

    Best effort: when the page is already closed, the error log is still
    attached and the rest is skipped, so the real failure stays the reported one.

    Args:
        item (pytest.Item): The failing test item.
        error_text (str): The rendered failure.

    Returns:
        None
    """
    session = DIAGNOSTICS_REGISTRY.session_for(item.nodeid)
    if session is None:
        return
    page_object = session.page_object

    # Added 2026-08-11: read and attached first, outside the capture block, since
    # the events are in memory and survive a closed page (README.md section
    # "Reporting"). The inspector gets the same text, so the human's report and
    # the model's input cannot disagree.
    browser_diagnostics = _browser_diagnostics_text(page_object)
    allure.attach(
        browser_diagnostics,
        name=f"Browser diagnostics - {page_object.diagnostics.summary()}",
        attachment_type=allure.attachment_type.TEXT,
    )

    try:
        dom_snapshot = page_object.dom_snapshot()
        page_url = page_object.page.url
        allure.attach(
            page_object.screenshot_png(),
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

    _attach_trace(item, session)

    settings = Settings.from_env()
    inspector = DIAGNOSTICS_REGISTRY.inspector(settings)
    triage_report = inspector.analyze_failure(
        FailureContext(
            test_name=item.nodeid,
            page_url=page_url,
            error_text=error_text,
            browser_diagnostics=browser_diagnostics,
            dom_snapshot=dom_snapshot,
        )
    )
    if triage_report is not None:
        allure.attach(
            triage_report,
            name=f"Claude root-cause analysis ({inspector.model})",
            attachment_type=allure.attachment_type.TEXT,
        )

"""Pytest fixtures, viewport provisioning, and failure-diagnostics wiring.

Every browser context in this suite is created here with an explicit viewport so
that the responsive assertions in ``tests/test_responsive.py`` are reproducible
rather than dependent on the host window size.

The module also installs the ``pytest_runtest_makereport`` wrapper that, for any
failing test, attaches to the Allure report: the browser's own error log, a
full-page screenshot, the fully rendered DOM, a Playwright trace of the whole
test, and - when enabled - a Claude root-cause analysis. The error log is
additionally published as a pytest report section, so it appears in the terminal
summary and in ``reports/pytest-report.html`` for anyone not opening Allure.
Recording and tracing both run for every test, but neither artifact is written
unless the test fails, so a green run leaves nothing behind.
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

#: Directories the suite writes into. Created up front so a fresh clone, a
#: cleaned workspace, or a CI runner never fails merely because an output
#: directory is absent.
ARTIFACT_DIRECTORIES: Final[tuple[str, ...]] = (
    "reports",
    "reports/traces",
    "allure-results",
)

#: Characters that are unsafe in a filename, replaced when a pytest node id is
#: turned into a trace file name.
UNSAFE_FILENAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]+")


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


def pytest_configure(config: pytest.Config) -> None:
    """Create the report and artifact directories before the session starts.

    Runs once, ahead of collection and ahead of any reporting plugin writing its
    first file. Paths are resolved against the rootdir rather than the process
    working directory, so the directories land beside the project no matter
    where ``pytest`` was invoked from.

    Args:
        config: The active pytest configuration, used for its rootdir.
    """
    for directory_name in ARTIFACT_DIRECTORIES:
        (config.rootpath / directory_name).mkdir(parents=True, exist_ok=True)


@dataclass
class ActiveSession:
    """The live browser objects belonging to one running test.

    Attributes:
        page_object: The Page Object driving the test's browser page.
        context: The browser context that owns the page, and the tracing session.
        trace_saved: Whether the trace has already been written to disk. Guards
            against stopping the same tracing session twice, which Playwright
            rejects.
    """

    page_object: BasePage
    context: BrowserContext
    trace_saved: bool = field(default=False)


class DiagnosticsRegistry:
    """Tracks the live browser session of each running test for failure capture.

    Pytest hooks cannot request fixtures, so the fixtures publish their session
    here and the ``makereport`` hook looks it up by node id. Entries are removed
    during fixture teardown, which runs after the call-phase report.
    """

    def __init__(self) -> None:
        self._sessions_by_node_id: dict[str, ActiveSession] = {}
        self._inspector: ClaudeTestInspector | None = None

    def register_session(
        self, node_id: str, page_object: BasePage, context: BrowserContext
    ) -> ActiveSession:
        """Associate a browser session with the test that owns it.

        Args:
            node_id: Pytest node identifier of the owning test.
            page_object: The Page Object driving that test's browser page. Any
                :class:`~pages.base_page.BasePage` subclass is accepted, so
                landing-page and discovered-route tests share one capture path.
            context: The browser context backing the page.

        Returns:
            The registered session, so the caller can consult ``trace_saved``
            during teardown.
        """
        session = ActiveSession(page_object=page_object, context=context)
        self._sessions_by_node_id[node_id] = session
        return session

    def release_session(self, node_id: str) -> None:
        """Forget the session owned by a finished test.

        Args:
            node_id: Pytest node identifier of the finished test.
        """
        self._sessions_by_node_id.pop(node_id, None)

    def session_for(self, node_id: str) -> ActiveSession | None:
        """Look up the session owned by a test.

        Args:
            node_id: Pytest node identifier of the test.

        Returns:
            The registered session, or ``None`` for tests that never opened a
            browser page.
        """
        return self._sessions_by_node_id.get(node_id)

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


#: Explains why a run's collected size cannot be held against a published
#: figure, when that is the case.
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
    """How large the suite is, measured before any selection narrowed it.

    Attributes:
        total: Every test the suite collects.
        deployment: Tests that run on the deployment path, meaning everything
            not marked ``external``.
        incomparable_reason: Why these counts must not be compared against a
            figure the site publishes, or ``None`` when the comparison is valid.
    """

    total: int
    deployment: int
    incomparable_reason: str | None


class SuiteSizeRegistry:
    """Carries the collected suite size from the collection hook to a fixture."""

    def __init__(self) -> None:
        self._size: SuiteSize | None = None

    def record(self, size: SuiteSize) -> None:
        """Store the measurement taken during collection.

        Args:
            size: The suite size observed before deselection.
        """
        self._size = size

    def current(self) -> SuiteSize:
        """Return the measurement taken during collection.

        Returns:
            The recorded :class:`SuiteSize`.

        Raises:
            RuntimeError: If read before collection has run.
        """
        if self._size is None:
            raise RuntimeError("Suite size was read before collection completed.")
        return self._size


SUITE_SIZE_REGISTRY = SuiteSizeRegistry()


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Measure the suite before marker or keyword selection removes anything.

    Registered ``tryfirst`` deliberately. Pytest applies ``-m`` and ``-k``
    filtering inside this same hook, so an implementation running later would
    measure one run's selection rather than the size of the suite, and the
    figure published on the site would appear wrong whenever a subset was run.

    Args:
        config: The active pytest configuration.
        items: Every collected item, before any deselection.
    """
    names_paths = any(
        str(argument).endswith(".py") or "::" in str(argument)
        for argument in config.invocation_params.args
    )
    # `--browser` is repeatable, and every browser-scoped test is collected once
    # per engine. A two-engine run therefore collects roughly twice the suite,
    # which is a different measurement rather than a drifted one.
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
    """Resolve the framework configuration once per test session.

    Returns:
        The immutable settings snapshot shared by every fixture and hook.
    """
    return Settings.from_env()


@pytest.fixture(name="suite_size", scope="session")
def fixture_suite_size() -> SuiteSize:
    """Expose the collected suite size to tests that check what the site claims.

    Returns:
        The measurement taken during collection.
    """
    return SUITE_SIZE_REGISTRY.current()


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
    """Create an isolated, tracing browser context with a fixed viewport.

    A dedicated context per test guarantees a clean cookie jar, storage, and
    viewport, so tests can run in any order or in parallel without interference.
    Tracing is armed immediately: a trace can only capture actions that happen
    after it starts, so it must be running before the test touches the page.

    Args:
        browser: The session-scoped Playwright browser.
        viewport: Viewport geometry applied to the new context.
        javascript_enabled: Set to ``False`` to exercise a site's ``noscript``
            fallback path.

    Returns:
        The newly created context. The caller owns closing it.
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
        session: The session whose tracing should be torn down. Sessions whose
            trace was already saved on failure are left alone.
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
    """Create an isolated context and yield a landing Page Object.

    Args:
        browser: The session-scoped Playwright browser.
        framework_settings: Resolved framework configuration.
        node_id: Pytest node identifier used to register the session for failure
            diagnostics.
        viewport: Viewport geometry applied to the new context.
        javascript_enabled: Set to ``False`` to exercise the site's ``noscript``
            fallback path.

    Yields:
        A :class:`LandingPage` bound to a fresh, correctly sized page that is
        already recording browser errors.
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
    """Create an isolated context and yield a diagnostics-recording route page.

    Recording is switched on before the page is handed to the test, because
    Playwright only delivers events raised after a listener is attached - a
    console error emitted during the very first navigation would otherwise be
    missed.

    Args:
        browser: The session-scoped Playwright browser.
        node_id: Pytest node identifier used to register the session for failure
            diagnostics.
        viewport: Viewport geometry applied to the new context.

    Yields:
        A :class:`RoutePage` that is already recording console, network, and
        JavaScript errors.
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
        _publish_browser_diagnostics(item, report)
        _attach_failure_diagnostics(item, _render_failure(call, report))
    return report


def _browser_diagnostics_text(page_object: BasePage) -> str:
    """Render one page's recorded browser errors, tolerating a closed page.

    Args:
        page_object: The Page Object driving the failing test.

    Returns:
        The rendered diagnostic report, or a note explaining why it could not
        be read. Evidence collection must never replace a real failure with a
        different one.
    """
    try:
        return page_object.diagnostics.report()
    except PlaywrightError as diagnostics_error:
        return f"Browser diagnostics could not be read: {diagnostics_error}"


def _publish_browser_diagnostics(item: pytest.Item, report: pytest.TestReport) -> None:
    """Attach the browser's error log to the pytest report as a section.

    Allure is the richer report, but it is not always the one being read - a CI
    log and ``reports/pytest-report.html`` are both closer to hand. A pytest
    section reaches all three, and appears directly beneath the traceback of
    the test it belongs to.

    Args:
        item: The failing test item.
        report: The report being built for it.
    """
    session = DIAGNOSTICS_REGISTRY.session_for(item.nodeid)
    if session is None:
        return
    report.sections.append(
        ("Browser diagnostics", _browser_diagnostics_text(session.page_object))
    )


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


def _trace_path(item: pytest.Item) -> Path:
    """Build the on-disk location of one test's Playwright trace.

    Args:
        item: The failing test item.

    Returns:
        A path under ``reports/traces`` whose name is derived from the node id.
    """
    safe_name = UNSAFE_FILENAME_PATTERN.sub("_", item.nodeid).strip("_")
    return item.config.rootpath / "reports" / "traces" / f"{safe_name}.zip"


def _attach_trace(item: pytest.Item, session: ActiveSession) -> None:
    """Stop tracing, write the artifact, and attach it to the Allure report.

    Args:
        item: The failing test item.
        session: The failing test's live browser session.
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
        # A trace is a nice-to-have. Never let capturing evidence become the
        # reason a test reports something other than its real failure.
        allure.attach(
            f"Playwright trace could not be captured: {trace_error}",
            name="Trace capture failed",
            attachment_type=allure.attachment_type.TEXT,
        )


def _attach_failure_diagnostics(item: pytest.Item, error_text: str) -> None:
    """Capture page evidence and an optional AI triage report for a failure.

    Diagnostics are best-effort: a browser that already closed must not convert
    a genuine assertion failure into a confusing collection error.

    Args:
        item: The failing test item.
        error_text: Rendered representation of the failure.
    """
    session = DIAGNOSTICS_REGISTRY.session_for(item.nodeid)
    if session is None:
        return
    page_object = session.page_object

    # Read and attached first, and outside the capture block below: the events
    # are already in memory, so this is the one piece of evidence that survives
    # a page which has closed under the test. The same text is handed to the
    # inspector further down, so the report a human reads and the log the model
    # reasons from cannot disagree.
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

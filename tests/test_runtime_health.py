"""Runtime health of the landing page while it is being used, not just loaded.

``tests/test_dynamic_routes.py`` already checks every discovered route for a
clean browser log, but it checks it at rest: navigate, read the log, done. That
covers the load path and nothing else, which leaves the site's only scripted
behaviour - the tab router and the base64 link decoder - unwatched. An exception
thrown when a tab is clicked breaks the page for a visitor while every existing
check stays green, because each one asserts on a locator that simply never
resolves and reports a timeout that says nothing about the cause.

This module drives the page the way a visitor does and then asks the browser
what it thought of it.
"""

from __future__ import annotations

import allure

from pages.landing_page import LandingPage, NavigationTab
import pytest

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Runtime Health Under Interaction"


@pytest.mark.test_id("PAWA_10042")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Using every tab raises no error the browser can see")
@allure.severity(allure.severity_level.CRITICAL)
def test_visiting_every_tab_raises_no_browser_errors(desktop_page: LandingPage) -> None:
    """Walking the whole tab strip must leave the browser's error log clean.

    The walk is one test rather than one per tab on purpose. The router is a
    state machine over a shared page: the interesting failures are the ones that
    need a *sequence* - a listener bound twice, a panel left visible, a decoder
    that runs a second time over already-decoded markup - and a per-tab test
    that reloads between clicks would reset the very state that produces them.

    Network assertions are scoped to the site's own origin. Every project panel
    embeds a CI badge served by GitHub, and those images are fetched as the
    panels are revealed, so an unscoped assertion would make this test - and the
    deployment signal it feeds - depend on GitHub being reachable. Third-party
    problems are recorded and reported all the same; they are just not the
    verdict.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    with allure.step("Visit every tab in the order a visitor meets them"):
        for tab in NavigationTab:
            landing_page.open_tab(tab)

    with allure.step("Let sub-resources finish before reading the error log"):
        settled = landing_page.settle_sub_resources()

    diagnostics = landing_page.diagnostics
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
    visited = ", ".join(tab.label for tab in NavigationTab)

    with allure.step("Verify no unhandled JavaScript exception was raised"):
        assert not diagnostics.javascript_errors, (
            f"Visiting {visited} raised unhandled JavaScript exceptions: "
            f"{diagnostics.javascript_errors}. The site's only script is the tab "
            "router and the link decoder, so an exception here means one of the "
            "two stopped working for every visitor."
        )

    with allure.step("Verify the console logged no first-party errors"):
        assert not diagnostics.first_party_console_errors, (
            f"Visiting {visited} logged console errors: "
            f"{diagnostics.first_party_console_errors}.{unsettled_note}"
        )

    with allure.step("Verify no first-party request failed at the network level"):
        assert not diagnostics.first_party_failed_requests, (
            "The page failed to fetch resources from its own origin: "
            f"{diagnostics.first_party_failed_requests}.{unsettled_note}"
        )

    with allure.step("Verify no first-party sub-resource returned an error status"):
        assert not diagnostics.first_party_broken_resources, (
            "The page requested resources of its own that failed to load: "
            f"{diagnostics.first_party_broken_resources}.{unsettled_note}"
        )

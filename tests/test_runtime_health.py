"""Tests that using the landing page, not just loading it, leaves the browser log clean.

Created: 2026-08-11
Last updated: 2026-11-10

This file covers one behavior: visiting every tab in navigation order, then
letting sub-resources settle, leaves no unhandled JavaScript exception, no
first-party console error, no first-party request failed at the network level,
and no first-party sub-resource with an error status.

The case runs on the deployment path. ``tests/test_dynamic_routes.py`` reads
each route's log at rest, after load only, which never runs the site's scripted
behavior, the tab router and the base64 link decoder. A failure here means one
of the two raised or broke a request while a visitor used the page, which other
checks would surface only as a locator timeout naming no cause.

**One walk, not one case per tab.** The router is a state machine over a shared
page, and its likely failures need a sequence: a listener bound twice, a panel
left visible, a decoder running again over decoded markup. A per-tab case that
reloads between clicks would reset the state that produces them.

**Only first-party network problems fail the case.** Third-party ones, such as
the GitHub badge images revealed with each panel, are recorded and reported but
are not the verdict. When sub-resources have not settled, the failure message
says the list may be incomplete.

Specified by ``README.md`` sections "Key Features" (The Browser's Own Error Log,
on Every Page; Origin-Scoped Assertions) and "Coverage Summary".
"""

from __future__ import annotations

import allure
import pytest

from pages.landing_page import LandingPage, NavigationTab

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Runtime Health Under Interaction"


@pytest.mark.test_id("PAWA_10042")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Using every tab raises no error the browser can see")
@allure.severity(allure.severity_level.CRITICAL)
def test_visiting_every_tab_raises_no_browser_errors(desktop_page: LandingPage) -> None:
    """Assert walking the whole tab strip leaves the browser's error log clean.

    Asserts no JavaScript exception at all, and no console error, failed
    request or error-status sub-resource from the site's own origin. The full
    log, third-party events included, is attached to the report.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
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
